# 元件設計 (Component & Interface Design)

| 項目 | 內容 |
| --- | --- |
| 文件版本 | v0.1 |
| 建立日期 | 2026-05-23 |
| 對應 PM 版本 | `pm/requirements.md` v0.3、`pm/event_storming.md` v0.1、`pm/release_plan.md` v1.0 |
| 文件範圍 | 各 Service / Broker / Domain 元件的類別介面、方法簽名、依賴關係；不含 DB schema（見 `data_design.md`）、不含技術選型理由（見 `tech_decisions.md`） |

## 0. 設計慣例

- 所有公開介面以 `abc.ABC` 表示；具體實作以介面 + 後綴命名（`BaseBroker` → `ShioajiBroker`）。
- 方法簽名使用 Python `typing`（PEP 604 `X | None`）。
- 不可變值物件用 `@dataclass(frozen=True, slots=True)`；可變狀態（aggregate state）用 `@dataclass(slots=True)`。
- 所有 IO 介面方法都標 `async`（asyncio）；純計算方法為同步。
- 例外體系：定義 `StocksTradingError` 為 root；各 BC 自有子類（`BrokerError`、`RiskRejectedError`、`LlmBudgetExceededError`）。

---

## 1. BC-1 模式管理

### 1.1 ModeState (Domain Value Object)

```python
# core/mode/domain.py
from enum import Enum
from datetime import datetime

class Mode(str, Enum):
    SIMULATION = "SIMULATION"
    LIVE = "LIVE"

@dataclass(frozen=True, slots=True)
class ModeState:
    mode: Mode
    switched_at: datetime              # UTC
    confirmed_by_user: bool             # SIM→LIVE 才會為 True
    auto_revert_at: datetime | None     # switched_at + 24h（僅 LIVE）

    def is_expired(self, now: datetime) -> bool:
        return self.mode == Mode.LIVE and self.auto_revert_at is not None and now >= self.auto_revert_at
```

### 1.2 ModeManager (Service)

```python
# core/mode/mode_manager.py
class ModeManager:
    def __init__(
        self,
        repo: ModeStateRepository,
        shioaji_checker: ShioajiConnectionChecker,
        signal_lock_checker: SignalLockChecker,
        scheduler: SchedulerService,
        notifier: NotificationService,
        audit_log: AuditLogService,
    ): ...

    def get_current(self) -> ModeState: ...
    def request_switch(self, target: Mode) -> SwitchPreflightResult: ...
        # 回傳：connection_ok / pending_signals / frozen_position_count
        # 並 emit ModeSwitchRequested 事件

    def confirm_switch(self, target: Mode, confirmation: str | None) -> ModeState:
        """
        target=LIVE → 必須 confirmation == "LIVE"（FR-MM-03）
        target=SIM  → confirmation 忽略
        """
        # 寫 audit_log（誰、何時、target、confirmation_ok）
        # 排程 24h auto_revert one-shot job
        # emit LiveModeActivated / SimulationModeActivated

    def auto_revert(self) -> ModeState:
        """24h 計時器到期觸發"""
        # emit SimulationModeRestored + 寄告警信
        # LIVE 帳本資料保留不刪除 (FR-MM-09)

    def can_reset_account(self, account_id: int) -> bool:
        """FR-MM-11：實盤帳本若仍有未平倉部位，禁止重置"""
```

### 1.3 ShioajiConnectionChecker (Infrastructure)

```python
# core/mode/shioaji_checker.py
class ShioajiConnectionChecker:
    """在切換 LIVE 之前預檢驗 Shioaji 可正常登入；只做連線測試不下單"""
    async def verify(self) -> ConnectionCheckResult:
        # try shioaji.Shioaji() + login + activate_ca
        # 回傳 status / api_quota_left / ca_expiry_days
```

### 1.4 ModeStateRepository

```python
# core/mode/repository.py
class ModeStateRepository(ABC):
    def load(self) -> ModeState: ...
    def save(self, state: ModeState) -> None: ...

class FileModeStateRepository(ModeStateRepository):
    """寫 config.json 的 mode 區段；同步寫一份 audit_log row"""
```

依賴：`ModeManager` 注入時必須先初始化 `Container.shioaji_checker`；v1.0 因 UI 隱藏 LIVE，`shioaji_checker` 可為 `NullShioajiChecker`（永遠回傳 not-available）。

---

## 2. BC-2 市場資料

### 2.1 KbarSeries / Kbar (Domain)

```python
# data/domain.py
@dataclass(frozen=True, slots=True)
class Kbar:
    symbol: str
    market: Market       # Market.TW | Market.US
    date: date           # 交易日
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

@dataclass(frozen=True, slots=True)
class KbarSeries:
    symbol: str
    market: Market
    bars: tuple[Kbar, ...]    # tuple 強制不可變

    def to_dataframe(self) -> pd.DataFrame: ...
    def last_n(self, n: int) -> "KbarSeries": ...
```

### 2.2 MarketDataProvider (Infrastructure 介面)

```python
# data/providers/base.py
class MarketDataProvider(ABC):
    @property
    def name(self) -> str: ...        # "shioaji" / "yfinance"
    @property
    def supported_markets(self) -> set[Market]: ...

    async def fetch_kbars(self, symbol: str, market: Market,
                           start: date, end: date) -> KbarSeries: ...
    async def fetch_realtime_quote(self, symbol: str, market: Market) -> Quote | None: ...
```

實作：
- `YfinanceProvider` — sync yfinance 套件包進 thread executor；ticker 規則：US 原樣、TW 加 `.TW`。
- `ShioajiKbarsProvider` — 使用 `shioaji.contracts.Contracts.Stocks[symbol]` + `api.kbars(...)`；僅 v1.5+ 注入；v1.0 不掛載。

### 2.3 MarketDataService (Service)

```python
# data/market_data_service.py
class MarketDataService:
    def __init__(self,
                 primary_providers: dict[Market, MarketDataProvider],   # TW→shioaji, US→yfinance
                 fallback_providers: dict[Market, MarketDataProvider],  # TW→yfinance
                 cache_repo: KbarsCacheRepository,
                 validator: KbarValidator,
                 app_log: AppLogService): ...

    async def get_kbars(self, symbol: str, market: Market,
                        start: date, end: date,
                        force_refresh: bool = False) -> KbarSeries:
        """
        1. cache hit & not expired & not force_refresh → 回 cache
        2. primary provider → 失敗則 fallback
        3. validator.validate() → 失敗則 emit KbarsValidationFailed + 告警
        4. 寫 kbars_cache
        """

    async def refresh_universe(self, symbols: Iterable[tuple[str, Market]]) -> RefreshReport:
        """每日 daily_run 開頭呼叫，並行 fetch"""
```

### 2.4 KbarValidator (Domain Service)

```python
# data/validator.py
class KbarValidator:
    def validate(self, series: KbarSeries) -> ValidationReport:
        """
        檢查：
        - 缺漏交易日（依市場交易日曆）
        - any close <= 0 或 NaN
        - 跳空 |today.open - yesterday.close| / yesterday.close > 30%
        - 量為負
        """
```

---

## 3. BC-3 策略與回測

### 3.1 Signal (Domain Aggregate Root)

```python
# strategies/domain.py
class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"     # MVP 不啟用
    COVER = "COVER"

class SignalStatus(str, Enum):
    PENDING_RISK_CHECK = "PENDING_RISK_CHECK"
    PENDING_T_PLUS_1_OPEN = "PENDING_T+1_OPEN"
    PENDING_SHIOAJI_FILL = "PENDING_SHIOAJI_FILL"
    MANUAL_PENDING = "MANUAL_PENDING"       # 美股 LIVE
    FILLED = "FILLED"
    UNFILLED_GAP = "UNFILLED_GAP"
    REJECTED_RISK = "REJECTED_RISK"
    EXPIRED = "EXPIRED"                     # 美股 MANUAL_PENDING 過期
    FAILED = "FAILED"

@dataclass(slots=True)
class Signal:
    id: int | None              # None 直到 persist
    strategy_id: str
    symbol: str
    market: Market
    side: SignalSide
    target_price: Decimal
    stop_loss_price: Decimal | None
    suggested_qty: int           # 數量（股 / 張）
    reason: str                  # 策略原因（顯示於 Email）
    generated_at: datetime       # UTC
    status: SignalStatus
    filter_passed: list[str]     # 通過的 RiskGuard rule / Pattern filter 名稱（PM I-5）

    def is_terminal(self) -> bool: ...
    def transition_to(self, new_status: SignalStatus, reason: str | None = None) -> None: ...
```

### 3.2 BaseStrategy (Domain)

```python
# strategies/base.py
class BaseStrategy(ABC):
    @property
    def strategy_id(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def universe(self) -> list[tuple[str, Market]]: ...
    @property
    def rebalance_schedule(self) -> RebalanceSchedule: ...  # MONTHLY_LAST / WEEKLY / DAILY

    @abstractmethod
    def generate(self,
                 snapshot: MarketSnapshot,
                 holdings: list[Position],
                 params: StrategyParams) -> list[Signal]: ...
```

### 3.3 DualMomentumStrategy

```python
# strategies/dual_momentum.py
class DualMomentumStrategy(BaseStrategy):
    strategy_id = "dual_momentum_v1"
    name = "Dual Momentum (雙動能輪動)"

    def __init__(self, indicator_engine: IndicatorEngine): ...

    def generate(self, snapshot, holdings, params: DualMomentumParams) -> list[Signal]:
        """
        params:
          lookback_days=252
          top_n=2
          abs_momentum_threshold_pct=4.0      # 年化
          rebalance="MONTHLY_LAST"
        步驟：
        1. 對 universe 內每檔計算 lookback_days 累積報酬
        2. 篩掉 abs_momentum < threshold 的標的（持現金）
        3. 取前 top_n
        4. 比對目前 holdings：差集即賣 / 補進的 Signal
        """
```

### 3.4 StrategyRunner (Service)

```python
# strategies/runner.py
class StrategyRunner:
    def __init__(self, market_data: MarketDataService, strategies: list[BaseStrategy],
                 risk_guard: RiskGuard, trading: TradingService,
                 signal_repo: SignalRepository, account_repo: AccountRepository,
                 mode_manager: ModeManager): ...

    async def run_daily(self, market: Market) -> StrategyRunReport:
        """
        被 cli.py daily_run 呼叫；步驟見 architecture.md §4.1
        為每個 active strategy 並行執行
        """

    async def run_single(self, strategy_id: str, market: Market) -> StrategyRunReport: ...
```

### 3.5 BacktestEngine (Service)

```python
# backtest/engine.py
class BacktestEngine:
    def __init__(self, market_data: MarketDataService,
                 fill_engine: FillEngine,    # 共用 SimulatedBroker 內的 T+1 邏輯
                 indicator_engine: IndicatorEngine): ...

    def run(self, request: BacktestRequest) -> BacktestResult: ...

@dataclass(frozen=True, slots=True)
class BacktestRequest:
    strategy: BaseStrategy
    params: StrategyParams
    universe: list[tuple[str, Market]]
    start: date
    end: date
    initial_capital_twd: Decimal
    initial_capital_usd: Decimal
    commission_rate_tw: Decimal = Decimal("0.001425")
    commission_rate_us: Decimal = Decimal("0.0018")
    slippage_rate: Decimal = Decimal("0.0005")
    benchmark_symbol: str = "SPY"
    enable_gap_protection: bool = True

@dataclass(frozen=True, slots=True)
class BacktestResult:
    equity_curve: list[tuple[date, Decimal]]
    trades: list[BacktestTrade]
    annual_return_pct: Decimal
    cumulative_return_pct: Decimal
    max_drawdown_pct: Decimal
    sharpe_ratio: Decimal
    win_rate_pct: Decimal
    total_trades: int
```

**FR-BT-02 落地**：BacktestEngine 與實盤共用兩個元件：
1. `IndicatorEngine`（指標計算）
2. `FillEngine`（T+1 開盤成交 + 跳空保護），實際是 `SimulatedBroker` 內抽出的純函式 module

### 3.6 SchedulerService (Service)

```python
# core/scheduler.py
class SchedulerService:
    """
    GUI mode：管 APScheduler，顯示「下次執行時間」於主控台。
    CLI mode：不啟動 scheduler；由 Windows Task Scheduler 直接呼叫 sub-commands。
    """
    def __init__(self, scheduler: AsyncIOScheduler): ...

    def schedule_daily_jobs(self, mode: Mode) -> None: ...
    def schedule_one_shot(self, run_at: datetime, callback: Callable) -> str: ...  # 用於 24h auto-revert
    def get_next_runs(self) -> list[NextRunInfo]: ...
```

---

## 4. BC-4 交易執行與風控

### 4.1 BaseBroker (Infrastructure 介面)

對應 NFR-MNT-02 + PM release_plan §8 風險表「v1.5 才實作的 ShioajiBroker 與 v1.0 SimulatedBroker 介面不一致」→ M0 階段就鎖定介面 + contract test。

```python
# brokers/base.py
class BaseBroker(ABC):
    @property
    def name(self) -> str: ...               # "shioaji" / "simulated" / "email"
    @property
    def supported_markets(self) -> set[Market]: ...
    @property
    def is_live(self) -> bool: ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderAck: ...
    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> None: ...
    @abstractmethod
    async def fetch_fills(self, since: datetime) -> list[FillReport]: ...
    @abstractmethod
    async def fetch_balance(self) -> AccountBalance: ...

@dataclass(frozen=True, slots=True)
class OrderRequest:
    signal_id: int
    symbol: str
    market: Market
    side: SignalSide
    qty: int
    price: Decimal | None       # market order = None
    order_type: OrderType       # LIMIT / MARKET / MOC / MOO
    stop_loss_price: Decimal | None
    time_in_force: TimeInForce  # DAY / IOC / FOK
    mode: Mode                  # 寫入 orders.mode 欄位

@dataclass(frozen=True, slots=True)
class OrderAck:
    broker_order_id: str          # SimulatedBroker 用 UUID; Shioaji 用真實 id
    accepted_at: datetime
    status: OrderStatus           # ACCEPTED / REJECTED_BY_BROKER / PENDING_T+1
    rejection_reason: str | None
```

### 4.2 SimulatedBroker

```python
# brokers/simulated.py
class SimulatedBroker(BaseBroker):
    """
    純檔案邏輯：寫 orders 表狀態=PENDING_T+1_OPEN
    成交對帳由 FillEngine 在 reconcile_t_plus_1 job 統一處理
    """
    def __init__(self, order_repo: OrderRepository,
                 fill_engine: FillEngine,
                 commission_config: CommissionConfig): ...

    is_live = False
    supported_markets = {Market.TW, Market.US}

    async def place_order(self, order: OrderRequest) -> OrderAck:
        # 寫 orders 表，status=PENDING_T+1_OPEN
        # 立刻回傳 OrderAck（不等成交）

    async def fetch_fills(self, since: datetime) -> list[FillReport]:
        # 從 orders 表撈 status=FILLED 且 filled_at > since
```

### 4.3 ShioajiBroker (v1.5+)

```python
# brokers/shioaji.py
class ShioajiBroker(BaseBroker):
    """
    台股實盤；下單同時掛條件停損單（FR-EX-01）。
    """
    def __init__(self, api: Shioaji,                  # 注入時已 logged-in + CA activated
                 order_repo: OrderRepository,
                 stop_loss_strategy: StopLossOrderStrategy): ...

    is_live = True
    supported_markets = {Market.TW}

    async def place_order(self, order: OrderRequest) -> OrderAck:
        # 1. 組 Shioaji order: api.Order(...)
        # 2. api.place_order(contract, order) → 回傳 trade
        # 3. 若 stop_loss_price 設定 → 立刻掛條件停損單
        # 4. 寫 orders 表，shioaji_order_id, status=PENDING_SHIOAJI_FILL
        # 5. 若 Shioaji 拒單 → status=FAILED, raise BrokerError

    async def cancel_order(self, broker_order_id: str) -> None: ...
    async def fetch_fills(self, since: datetime) -> list[FillReport]:
        # api.list_trades() filter
```

### 4.4 EmailBroker (v1.5+)

```python
# brokers/email_broker.py
class EmailBroker(BaseBroker):
    """
    美股 LIVE：不下單，寄訊號 Email（FR-EX-02）。
    成交由使用者手動於永豐 APP 完成；訊號狀態保持 MANUAL_PENDING。
    """
    def __init__(self, notifier: NotificationService,
                 order_repo: OrderRepository,
                 manual_expiry_minutes: int = 30):  # PM I-3
        ...

    is_live = True
    supported_markets = {Market.US}

    async def place_order(self, order: OrderRequest) -> OrderAck:
        # 1. 渲染 HTML email（含下單檢核清單、策略原因、當前持倉）
        # 2. notifier.send_us_signal_email(...)
        # 3. 寫 orders 表，status=MANUAL_PENDING, expires_at=now+30min
        # 4. 排程一個 expire 檢查 job

    async def fetch_fills(self, since: datetime) -> list[FillReport]:
        # 美股 LIVE 系統無法知道是否成交；只能在 reconcile_t_plus_1 時
        # 用 yfinance 開盤價推測（target_price > T+1 open 視為已成交）
        # 這是 "best effort"，使用者也可手動於 GUI 標記成交
```

### 4.5 FillEngine (Domain Service)

```python
# core/trading/fill_engine.py
class FillEngine:
    """T+1 開盤價成交邏輯；回測與 SimulatedBroker 共用"""

    def __init__(self, commission_config: CommissionConfig,
                 slippage_rate: Decimal,
                 gap_protection_threshold: Decimal = Decimal("0.05")): ...

    def fill_at_open(self,
                      order: Order,
                      t_close: Decimal,
                      t_plus_1_open: Decimal) -> FillResult:
        """
        FillResult:
          status = FILLED | UNFILLED_GAP
          fill_price = t_plus_1_open ± slippage   (BUY 加滑價、SELL 減滑價)
          commission = qty * fill_price * commission_rate
          tax (台股賣出) = qty * fill_price * 0.003
        """
        gap_pct = abs(t_plus_1_open - t_close) / t_close
        if self.enable_gap_protection and gap_pct > self.gap_protection_threshold:
            return FillResult(status=UNFILLED_GAP, ...)
        # 否則填單
```

### 4.6 RiskGuard (Service)

```python
# core/risk/risk_guard.py
class RiskGuard:
    """
    規則按順序執行（fail-fast）；任一規則 reject → signal.status = REJECTED_RISK，
    寫入 app_log 與 audit_log。
    對應 PM I-4：逐筆審查，不全擋。
    """
    def __init__(self, rules: list[RiskRule], account_repo: AccountRepository,
                 position_repo: PositionRepository, pnl_repo: DailyPnlRepository,
                 fx_service: FxService,        # PM I-2 多幣別折算
                 blacklist_repo: BlacklistRepository): ...

    async def evaluate(self, signal: Signal, mode: Mode) -> RiskDecision:
        """
        逐條 rule.check(signal, context) → 任何 violated 立即回 reject
        通過則：signal.filter_passed = [rule.name for rule in rules]
        """

class RiskRule(ABC):
    name: str
    @abstractmethod
    def check(self, signal: Signal, ctx: RiskContext) -> RuleResult: ...

# 內建 rules (按優先順序)：
class BlacklistRule(RiskRule): ...              # ticker / source 黑名單
class MarketHoursRule(RiskRule): ...            # 非交易日 / 收盤已過
class SinglePositionRiskRule(RiskRule):         # FR-RM-01 單筆 1%
    """risk_pct = (target_price - stop_loss) * qty / account_equity"""
class TotalExposureRule(RiskRule):              # FR-RM-02 總持倉 80%
    """已持倉 + 本次新進場 ≤ 80% of equity（多幣別折 TWD 計算）"""
class DailyLossLimitRule(RiskRule):             # FR-RM-03
    """
    僅檢查 entry/add signal；exit / stop-loss / cover 不檢查 (PM I-4)
    """
class StopLossRequiredRule(RiskRule):           # 進場必須有 stop_loss
```

### 4.7 TradingService (Service)

```python
# core/trading/trading_service.py
class TradingService:
    """
    根據 (mode, market) 路由到對應 Broker；
    處理跨 BC 的 Signal → Order → Position 編排。
    """
    def __init__(self,
                 brokers: dict[tuple[Mode, Market], BaseBroker],
                 risk_guard: RiskGuard,
                 signal_repo: SignalRepository,
                 order_repo: OrderRepository,
                 position_repo: PositionRepository,
                 mode_manager: ModeManager,
                 notifier: NotificationService,
                 audit_log: AuditLogService): ...

    async def dispatch(self, signals: list[Signal]) -> list[DispatchResult]:
        """主進入點：被 StrategyRunner / WatchlistService.promote 呼叫"""

    async def cancel(self, order_id: int) -> None: ...
```

### 4.8 AccountQueryService

```python
# core/trading/account_query.py
class AccountQueryService:
    """主控台 / KPI 卡片的 read-side 入口"""
    def get_kpi(self, mode: Mode) -> DashboardKpi: ...
    def get_current_positions(self, mode: Mode, market: Market | None) -> list[PositionView]: ...
    def get_today_signals(self, mode: Mode) -> list[SignalView]: ...
    def get_equity_curve(self, mode: Mode, days: int = 90) -> list[tuple[date, Decimal]]: ...
    def snapshot_daily_pnl(self, mode: Mode) -> None: ...
```

---

## 5. BC-5 新聞情緒分析 (v2.0)

### 5.1 NewsArticle / NewsAnalysis / WatchlistItem (Domain)

```python
# news/domain.py
@dataclass(frozen=True, slots=True)
class NewsArticle:
    id: int | None
    source: NewsSource              # enum: yfinance / cnbc / reuters / ars / techcrunch / verge / reddit / edgar
    url: str
    url_hash: str                   # sha256(url)[:16]
    title: str
    published_at: datetime          # UTC
    lang: str                       # ISO-639-1
    raw_text: str
    fetched_at: datetime

@dataclass(frozen=True, slots=True)
class NewsAnalysis:
    article_id: int
    model: str                      # "claude-haiku-4-5"
    sentiment: float                # -1.0 ~ 1.0
    impact_score: float             # 0.0 ~ 10.0
    summary: str
    catalysts: list[str]            # ["earnings_beat", "guidance_raise"]
    tickers: list[TickerCandidate]
    cost_usd: Decimal
    analyzed_at: datetime

@dataclass(frozen=True, slots=True)
class TickerCandidate:
    ticker: str
    confidence: float
    rationale: str

class WatchlistStatus(str, Enum):
    PENDING = "pending"
    PROMOTED = "promoted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"

@dataclass(slots=True)
class WatchlistItem:
    id: int | None
    ticker: str
    market: Market
    side: SignalSide
    source_article_ids: list[int]
    score: float
    status: WatchlistStatus
    added_at: datetime
    expires_at: datetime
```

### 5.2 BaseNewsSource (Infrastructure 介面)

```python
# news/sources/base.py
class BaseNewsSource(ABC):
    @property
    def name(self) -> NewsSource: ...
    @property
    def credibility_default(self) -> float: ...    # 0.0 ~ 1.0

    @abstractmethod
    async def fetch(self, since: datetime, limit: int = 100) -> list[RawArticle]: ...

# 實作（每個 ~80-150 行）：
class RssNewsSource(BaseNewsSource):              # 通用 RSS adapter (CNBC/Reuters/.../yfinance)
    def __init__(self, feed_url: str, source_name: NewsSource): ...
class RedditNewsSource(BaseNewsSource):           # praw + r/stocks 等
class EdgarNewsSource(BaseNewsSource):            # sec-edgar-downloader
```

### 5.3 Deduper

```python
# news/deduper.py
class Deduper:
    def __init__(self, repo: NewsArticleRepository,
                 title_similarity_threshold: float = 0.85): ...

    async def is_duplicate(self, candidate: RawArticle) -> bool:
        # 1. url_hash 完全相符 → True
        # 2. 過去 7 天 title rapidfuzz.ratio >= threshold → True
        # 3. else False
```

### 5.4 NewsCollector

```python
# news/collector.py
class NewsCollector:
    def __init__(self, sources: list[BaseNewsSource],
                 deduper: Deduper,
                 article_repo: NewsArticleRepository,
                 blacklist: BlacklistRepository,
                 lang_filter: LanguageFilter): ...

    async def collect(self) -> CollectReport:
        """
        並行抓取所有 enabled sources；每個 source 失敗 retry 3 次（exp backoff）。
        Lang filter：非英文直接 drop（PM E-8）。
        Source blacklist：在抓取階段過濾，省 LLM 成本（PM E-7）。
        """
```

### 5.5 LlmClient + Anthropic 實作

```python
# news/llm/base.py
class LlmClient(ABC):
    @abstractmethod
    async def analyze(self, article: NewsArticle,
                       prompt_template: str) -> LlmAnalysisRaw: ...

# news/llm/anthropic_client.py
class AnthropicLlmClient(LlmClient):
    def __init__(self,
                 api_key_provider: SecretsManager,   # 從 secrets.dat 取
                 model: str = "claude-haiku-4-5",
                 system_prompt: str = ...,           # 啟用 prompt caching
                 max_retries: int = 2):              # FR-NS-12
        ...

    async def analyze(self, article, prompt_template) -> LlmAnalysisRaw:
        # 1. 組 messages，system 部分標記 cache_control
        # 2. anthropic.AsyncAnthropic().messages.create(...)
        # 3. response.usage → 計算 input/output tokens 與成本
        # 4. parse content[0].text → json.loads → pydantic 驗證 schema
        # 5. raise AnalysisFailed (max 2 retries)
```

### 5.6 NewsAnalyzer (Service)

```python
# news/analyzer.py
class NewsAnalyzer:
    def __init__(self, llm: LlmClient,
                 cost_guard: CostGuard,
                 analysis_repo: NewsAnalysisRepository,
                 app_log: AppLogService,
                 max_concurrent: int = 3): ...

    async def analyze_pending(self) -> AnalyzeReport:
        """
        撈所有 news_articles 中 沒有對應 news_analysis 的 → 逐篇分析
        使用 asyncio.Semaphore(max_concurrent) 控制併發
        每篇前先 CostGuard.can_spend(estimated_cost) → 否則跳過
        """
```

### 5.7 CostGuard

```python
# news/cost_guard.py
class CostGuard:
    def __init__(self, cost_repo: LlmCostRepository,
                 daily_budget_usd: Decimal = Decimal("0.30"),
                 tz: str = "Asia/Taipei",                # PM I-12
                 notifier: NotificationService): ...

    def daily_used(self, on_date: date | None = None) -> Decimal: ...
    def daily_remaining(self) -> Decimal: ...

    def can_spend(self, estimated_cost: Decimal) -> bool:
        return self.daily_used() + estimated_cost <= self.daily_budget_usd

    def record(self, model: str, input_tokens: int, output_tokens: int, cost_usd: Decimal) -> None:
        """寫 llm_cost_daily，並檢查是否超出 → 寄告警 + emit LlmBudgetExceeded"""
```

### 5.8 TickerMapper

```python
# news/ticker_mapper.py
class TickerMapper:
    def __init__(self, alias_table: TickerAliasTable,
                 yf_validator: YfinanceTickerValidator,
                 confidence_threshold: float = 0.7): ...

    async def map(self, analysis: NewsAnalysis) -> list[MappedTicker]:
        """
        對 analysis.tickers 中每個候選：
          1. alias_table.lookup(name) → 命中加 0.5 confidence
          2. yf_validator.exists(ticker) → 命中加 0.3
          3. context_score (來自 LLM rationale 內含的相關詞) → 加 0.2
        """
```

### 5.9 Ranker

```python
# news/ranker.py
class Ranker:
    def __init__(self, source_credibility: dict[NewsSource, float],
                 recency_half_life_hours: float = 24,
                 multi_source_threshold: int = 3): ...

    def rank(self, mapped_articles: list[MappedArticle]) -> list[Candidate]:
        """
        對每個 ticker：
          score = sum_over_articles(impact * source_cred * recency_decay)
          if unique_sources >= 3 → strong_signal=True, score *= 1.5
        返回排序好的 Top N（預設 10）
        """
```

### 5.10 WatchlistService

```python
# news/watchlist_service.py
class WatchlistService:
    def __init__(self, repo: WatchlistRepository,
                 risk_guard: RiskGuard,
                 trading: TradingService,
                 signal_repo: SignalRepository,
                 audit_log: AuditLogService,
                 expiry_days: int = 7): ...

    def add_from_candidate(self, candidate: Candidate) -> WatchlistItem: ...
    def dismiss(self, item_id: int, reason: str) -> None: ...
    def promote(self, item_id: int) -> Signal:
        """
        第二段核可：item → Signal → RiskGuard → TradingService.dispatch（立即）
        對應 PM I-10
        """
    def expire_old(self) -> int: ...
        # 每日 cleanup job 呼叫；> expires_at 則 status=expired
    def report_fake_news(self, article_id: int) -> None:
        # 觸發 SourceCredibilityAdjusted
```

### 5.11 NewsPipeline (Orchestrator)

```python
# news/pipeline.py
class NewsPipeline:
    """串接 Collector → Analyzer → TickerMapper → Ranker → Digest"""
    def __init__(self, collector, analyzer, ticker_mapper, ranker,
                 watchlist_service, digest_composer, notifier,
                 cost_guard): ...

    async def run(self) -> PipelineReport:
        """
        被 cli.py news_collect 或 GUI APScheduler 呼叫；
        若 GUI mode 跑在 qasync loop。
        """
```

---

## 6. BC-6 圖表與技術分析 (v1.5+)

### 6.1 IndicatorEngine (Domain Service)

對應 FR-CH-16 + PM release_plan §7 「技術指標數值正確 < 0.01% 誤差」。

```python
# analytics/indicators.py
class IndicatorEngine:
    """
    純函式 module；無外部依賴；回測與即時圖表共用。
    底層用 pandas-ta（見 tech_decisions.md §3）。
    """
    @staticmethod
    def sma(close: pd.Series, period: int) -> pd.Series: ...
    @staticmethod
    def ema(close: pd.Series, period: int) -> pd.Series: ...
    @staticmethod
    def bollinger(close: pd.Series, period: int = 20, k: float = 2.0) -> BollingerBands: ...
    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series: ...
    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> MacdResult: ...

    @classmethod
    def snapshot(cls, kbars: KbarSeries, params: IndicatorParams) -> IndicatorSnapshot:
        """單次計算所有 indicator，回傳給 chart / pattern detector / KPI 用"""

@dataclass(frozen=True, slots=True)
class IndicatorSnapshot:
    ma: dict[int, pd.Series]      # {5: ..., 10: ..., 20: ..., 60: ..., 200: ...}
    bollinger: BollingerBands
    rsi: pd.Series
    macd: MacdResult
    volume_ratio_20d: pd.Series   # vol / vol.rolling(20).mean()
```

### 6.2 PatternDetector

```python
# analytics/patterns.py
class PatternDetector:
    """形態偵測；輸入 IndicatorSnapshot 與 KbarSeries → 輸出 Pattern[]"""

    def detect(self, kbars: KbarSeries, snapshot: IndicatorSnapshot,
               lookback_days: int = 60) -> list[Pattern]: ...

@dataclass(frozen=True, slots=True)
class Pattern:
    pattern_type: PatternType         # GOLDEN_CROSS / DEATH_CROSS / VOLUME_SURGE /
                                       # BOLL_UPPER_BREAK / BOLL_LOWER_BREAK /
                                       # RSI_OVERBOUGHT / RSI_OVERSOLD
    triggered_at: date
    severity: float                   # 0.0 ~ 1.0
    description: str                  # "MA5 上穿 MA20"

# 內部偵測函式：
def _detect_golden_cross(ma5: pd.Series, ma20: pd.Series, ...) -> list[Pattern]: ...
def _detect_death_cross(...) -> list[Pattern]: ...
def _detect_volume_surge(vol_ratio: pd.Series, threshold: float = 2.0) -> list[Pattern]: ...
def _detect_boll_break(close: pd.Series, bb: BollingerBands) -> list[Pattern]: ...
def _detect_rsi_extreme(rsi: pd.Series, overbought: float = 70, oversold: float = 30) -> list[Pattern]: ...
```

**FR-CH-26 嚴格規定**：`PatternDetector` 輸出**只給 UI 顯示**；不被 `TradingService` / `StrategyRunner` 訂閱。v1.0/v1.5 完全不暴露給 RiskGuard。v2.0 之後若要做 FR-CH-27 過濾器，需另寫 `PatternFilterStrategy` 包裝（明示 opt-in）。

---

## 7. BC-7 通知

### 7.1 BaseNotifier

```python
# notify/notifier_base.py
class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage) -> SendReceipt: ...

@dataclass(frozen=True, slots=True)
class EmailMessage:
    subject: str
    html_body: str
    text_body: str             # plaintext fallback
    to: list[str]
    cc: list[str] = field(default_factory=list)
    attachments: list[Path] = field(default_factory=list)
```

### 7.2 SmtpNotifier

```python
# notify/smtp_notifier.py
class SmtpNotifier(BaseNotifier):
    def __init__(self, host: str, port: int,
                 username: str,
                 password_provider: SecretsManager,
                 from_address: str,
                 use_tls: bool = True,
                 timeout_s: int = 30): ...

    async def send(self, message: EmailMessage) -> SendReceipt:
        # aiosmtplib 寄送；retry 3 次（exp backoff）；
        # 失敗 → emit EmailDeliveryFailed
```

### 7.3 NotificationService (Service)

```python
# notify/notification_service.py
class NotificationService:
    """
    對 BC-3/4/5 提供高階 API；負責：
    - 主旨加 [SIM] / [LIVE] / [ALERT] / [TEST] 前綴 (FR-MM-06, PM I-13)
    - 渲染 Jinja2 範本
    - 主題色彩繫結（明亮 / 深色）→ Email 預覽
    """
    def __init__(self, notifier: BaseNotifier,
                 mode_manager: ModeManager,
                 renderer: EmailRenderer,
                 config: NotificationConfig): ...

    async def send_test_email(self) -> SendReceipt:
        # 主旨 = "[TEST] StocksTrading 測試信"

    async def send_us_signal_email(self, signal: Signal, context: SignalEmailContext) -> SendReceipt:
        # 主旨 = "[LIVE] 美股訊號 - YYYY-MM-DD - 買進 QQQ"
        # 內含：訊號表、策略原因、當前持倉、下單檢核清單 (FR-EX-02, PM C2.6/2.7)

    async def send_daily_summary(self, summary: DailySummary) -> SendReceipt: ...
    async def send_alert(self, alert: AlertEvent) -> SendReceipt: ...
    async def send_news_digest(self, digest: NewsDigest) -> SendReceipt:
        # 主旨含當日成本 (FR-NS-28)
```

### 7.4 EmailRenderer

```python
# notify/renderer.py
class EmailRenderer:
    def __init__(self, template_dir: Path, theme: Theme): ...

    def render(self, template_name: str, context: dict) -> tuple[str, str]:
        """回傳 (html, plaintext)"""

# templates/
#   us_signal.html.j2
#   us_signal.txt.j2
#   daily_summary.html.j2
#   daily_summary.txt.j2
#   news_digest.html.j2          # 看多 / 看空分區 + 弱訊號列表（PM C2.14/2.15）
#   news_digest.txt.j2
#   alert.html.j2
#   alert.txt.j2
#   test.html.j2
```

---

## 8. 橫切元件

### 8.1 SecretsManager (security/secrets.py)

```python
class SecretsManager:
    """DPAPI 加密儲存 + 解密；對應 NFR-SEC-01"""
    def __init__(self, vault_path: Path): ...

    def get(self, key: str) -> str:
        """key 例：'shioaji.password', 'shioaji.ca_password',
                  'smtp.password', 'anthropic.api_key'
        若 vault 損毀 → raise SecretsVaultCorruptedError，提示使用者重新輸入
        """
    def set(self, key: str, value: str) -> None: ...
    def remove(self, key: str) -> None: ...
    def has(self, key: str) -> bool: ...

# security/dpapi.py — 底層
class DpapiVault:
    """pywin32 win32crypt.CryptProtectData / CryptUnprotectData 包裝"""
```

### 8.2 AppLogService / AuditLogService

```python
# logging/app_log.py
class AppLogService:
    """系統日誌（連線、錯誤、警告等）；對應 app_log 表"""
    def log(self, level: LogLevel, module: str, message: str,
            context: dict | None = None) -> None: ...

# logging/audit_log.py
class AuditLogService:
    """敏感操作審計；對應 audit_log 表 (PM E-3)
    保留 365 天不可刪除；獨立於 app_log。
    """
    def record(self, actor: str, action: AuditAction,
                target: str, before: dict | None, after: dict | None) -> None: ...

class AuditAction(str, Enum):
    MODE_SWITCH = "mode_switch"
    RISK_PARAM_CHANGE = "risk_param_change"
    SETTINGS_CHANGE = "settings_change"
    WATCHLIST_PROMOTE = "watchlist_promote"
    ACCOUNT_RESET = "account_reset"
    BACKUP_RESTORE = "backup_restore"
```

### 8.3 FxService (對應 PM I-2)

```python
# core/fx/fx_service.py
class FxService:
    """多幣別折算 → 統一 TWD 計算總部位 80%"""
    def __init__(self, provider: FxRateProvider): ...

    def to_twd(self, amount: Decimal, currency: Currency) -> Decimal: ...
    def daily_rate(self, currency: Currency, on_date: date) -> Decimal: ...

class FxRateProvider(ABC):
    async def get_rate(self, currency: Currency, on_date: date) -> Decimal: ...

# v1.0 用簡化版：yfinance 取 USD/TWD ETF 收盤價當匯率
class YfinanceFxProvider(FxRateProvider): ...
```

---

## 9. 元件依賴矩陣（重點）

| 元件 | 依賴的介面 | 被誰使用 |
| --- | --- | --- |
| `ModeManager` | `ModeStateRepository`, `ShioajiConnectionChecker`, `NotificationService` | `TopBar`, `StrategyRunner`, `TradingService` |
| `StrategyRunner` | `MarketDataService`, `RiskGuard`, `TradingService`, `BaseStrategy[]` | `cli.py daily_run`, GUI `StrategyPage` |
| `RiskGuard` | `AccountRepository`, `PositionRepository`, `DailyPnlRepository`, `FxService`, `BlacklistRepository` | `TradingService`, `WatchlistService.promote` |
| `TradingService` | `BaseBroker[]`, `RiskGuard`, repos, `NotificationService` | `StrategyRunner`, `WatchlistService.promote`, GUI 手動下單（v1.5） |
| `SimulatedBroker` | `OrderRepository`, `FillEngine` | `TradingService` |
| `ShioajiBroker` | `shioaji.Shioaji` (lazy init), `OrderRepository` | `TradingService` |
| `EmailBroker` | `NotificationService`, `OrderRepository` | `TradingService` |
| `FillEngine` | （無；純函式） | `SimulatedBroker`, `BacktestEngine`, `cli reconcile_t_plus_1` |
| `IndicatorEngine` | （無；純函式） | `DualMomentumStrategy`, `BacktestEngine`, `ChartPage`, `PatternDetector` |
| `PatternDetector` | `IndicatorEngine` | `ChartPage` only |
| `NewsPipeline` | `BaseNewsSource[]`, `LlmClient`, `CostGuard`, `TickerMapper`, `Ranker`, `WatchlistRepository`, `NotificationService` | `cli news_collect`, GUI APScheduler |
| `NotificationService` | `BaseNotifier`, `EmailRenderer`, `ModeManager` | 各 BC |
| `SecretsManager` | `DpapiVault` | 任何需要密碼/API key 的元件 |

---

## 10. v1.0 必要實作清單

對應 `release_plan.md` §2.1 v1.0 範圍，下表列出 M0~M6a 階段每個 milestone 對應的元件：

| Milestone | 必須完成的元件 |
| --- | --- |
| M0 | `ModeState`, `Mode`, `BaseBroker` 介面, `ModeStateRepository`, `SecretsManager`, `DpapiVault`, `MigrationRunner`, `AppLogService`, `AuditLogService`（介面與骨架） |
| M1 | `Kbar`, `KbarSeries`, `MarketDataProvider`, `YfinanceProvider`, `ShioajiKbarsProvider`, `MarketDataService`, `KbarValidator`, `KbarsCacheRepository`, `IndicatorEngine`（基礎版供 Dual Momentum 用）, `BaseStrategy`, `DualMomentumStrategy`, `BacktestEngine`, `FillEngine` |
| M2 | `Signal`, `Order`, `Position`, `Account`, `SimulatedBroker`, `RiskGuard`（含 4 條核心 rule）, `TradingService`, `AccountQueryService`, `FxService`, `StrategyRunner`, `SchedulerService` |
| M3 | `MainWindow`, `TopBar`, `DashboardPage`, `StrategyPage`, `BacktestPage`, `SignalLogPage`, `SettingsPage`, theme manager, `ModeManager`（含 24h 計時器、但 UI 隱藏 LIVE） |
| M4a | `BaseNotifier`, `SmtpNotifier`, `NotificationService`, `EmailRenderer`, daily_summary / alert / test 三套範本 |
| M6a | `MigrationRunner` 完整, `BackupService`, MSI 打包 setup, Task Scheduler XML 範本 |

v1.5 / v2.0 各新增元件清單見 `release_plan.md` §3.1 / §4.1。
