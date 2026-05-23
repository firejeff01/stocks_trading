# 系統架構設計 (System Architecture)

| 項目 | 內容 |
| --- | --- |
| 文件版本 | v0.1 |
| 建立日期 | 2026-05-23 |
| 對應 PM 版本 | `pm/requirements.md` v0.3、`pm/event_storming.md` v0.1、`pm/release_plan.md` v1.0 |
| 文件範圍 | 系統整體分層、跨層通訊、Bounded Context 對應的模組邊界、執行模式、部署視角；不涉及單一類別細節（見 `component_design.md`） |

## 0. 文件閱讀地圖

| 想了解 | 看哪節 |
| --- | --- |
| 整體分層長什麼樣 | §1 高階架構圖 |
| 7 個 Bounded Context 怎麼對應到程式碼 | §2 BC ↔ Module 對照 |
| 每層職責與依賴規則 | §3 分層架構 |
| Strategy → Signal → Order 怎麼跑 | §4 核心執行管線 |
| NewsPipeline 怎麼非同步處理 | §5 NewsPipeline 設計（v2.0） |
| GUI 與 CLI 怎麼共用 | §6 執行模式 |
| MSI 裝完長什麼樣 | §7 Deployment 視角 |
| v1.0 → v1.5 → v2.0 的擴充點 | §8 階段擴充策略 |

---

## 1. 高階架構圖

採取**四層 + 橫切**的分層架構，並以 BC 切分縱向模組。每個版本在同一架構上漸進長出。

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              使用者介面層 (Presentation)                       │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ PySide6 GUI (src/stocks_trading/ui/)                                    │  │
│ │  MainWindow ─ TopBar(ModeBadge / NextSchedule / ThemeToggle)            │  │
│ │  Pages: Dashboard / Strategy / Backtest / SignalLog / Settings          │  │
│ │  v1.5+: Chart   v2.0+: News                                            │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ CLI Entry (src/stocks_trading/cli.py)   ←─ Windows Task Scheduler 觸發  │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ 呼叫 Service（同步 / Qt thread / asyncio）
┌──────────────────────────────────┴───────────────────────────────────────────┐
│                            應用服務層 (Application / Service)                  │
│  ModeManager  StrategyRunner  RiskGuard      BacktestEngine                  │
│  SchedulerService  NotificationService  AccountQueryService                  │
│  IndicatorEngine  PatternDetector (v1.5+)                                    │
│  NewsPipeline ─ Collector / Analyzer / TickerMapper / Ranker / CostGuard /   │
│                 WatchlistService (v2.0+)                                     │
└────────────┬──────────────┬──────────────┬──────────────┬────────────────────┘
             │              │              │              │
             ▼              ▼              ▼              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              領域層 (Domain)                                 │
│  純 Python dataclass / Value Object，不依賴任何外部 SDK                       │
│  Signal / Order / Position / Account / DailyPnL                             │
│  ModeState / RiskRule / BacktestResult                                      │
│  KbarSeries / Indicator / Pattern                                           │
│  NewsArticle / NewsAnalysis / WatchlistItem / LlmCostRecord                 │
└────────────┬───────────────────────────────────────────────────────────────┘
             │ 透過 Repository / Provider 介面進出
┌────────────┴───────────────────────────────────────────────────────────────┐
│                          基礎建設層 (Infrastructure)                          │
│ ┌── Broker 介面 ──────────┐  ┌── MarketData ─────────┐  ┌── LLM ───────┐   │
│ │ BaseBroker             │  │ MarketDataProvider     │  │ LlmClient    │   │
│ │ ├ ShioajiBroker (v1.5) │  │ ├ ShioajiKbarsProvider │  │ └ Anthropic  │   │
│ │ ├ SimulatedBroker      │  │ ├ YfinanceProvider     │  │   (v2.0+)    │   │
│ │ └ EmailBroker (v1.5)   │  │ └ KbarsCacheRepository │  └──────────────┘   │
│ └────────────────────────┘  └────────────────────────┘                     │
│ ┌── NewsSource (v2.0+) ──┐  ┌── Storage ────────────┐  ┌── Notify ────┐   │
│ │ BaseNewsSource         │  │ SqliteEngine          │  │ SmtpNotifier │   │
│ │ ├ RssSource (yfin/CNBC/│  │ Repositories          │  │ EmailRenderer│   │
│ │ │  Reuters/TC/Verge/   │  │ MigrationRunner       │  │ Templates    │   │
│ │ │  ArsTechnica)        │  │ BackupService         │  └──────────────┘   │
│ │ ├ RedditSource         │  └───────────────────────┘                     │
│ │ └ EdgarSource          │  ┌── Security ───────────┐  ┌── Scheduler ─┐   │
│ └────────────────────────┘  │ DpapiVault            │  │ APScheduler   │   │
│                             │ SecretsManager        │  │ Adapter       │   │
│                             └───────────────────────┘  └──────────────┘   │
└────────────────────────────────────────────────────────────────────────────┘
             ▲ 橫切：Logging / AppLogService / AuditLogService / Theme / I18n

外部依賴：Shioaji · yfinance · Anthropic Claude · RSS · Reddit · SEC EDGAR ·
         SMTP (Gmail) · Windows DPAPI · Windows Task Scheduler
```

> 設計鐵則：**依賴只向下** — UI 只能呼叫 Service；Service 只能呼叫 Domain 與 Infrastructure 介面；Domain 不依賴任何下層；Infrastructure 透過介面被 Service 呼叫（DIP）。

---

## 2. Bounded Context ↔ Module 對照

對應 `event_storming.md` §0 的 7 個 BC，每個 BC 在程式碼中有清楚的目錄歸屬，方便日後拆分為獨立 package。

| BC | 目錄 | Service 元件 | Infrastructure 元件 | Read Model |
| --- | --- | --- | --- | --- |
| BC-1 模式管理 | `core/mode/` | `ModeManager` | `ModeStateRepository`（config + DB）| `SystemStatusView` |
| BC-2 市場資料 | `data/` | `MarketDataService` | `YfinanceProvider`、`ShioajiKbarsProvider`、`KbarsCacheRepository` | `ChartKbarsView` |
| BC-3 策略與回測 | `strategies/` `backtest/` `core/scheduler.py` | `StrategyRunner`、`BacktestEngine`、`SchedulerService` | — | `TodaySignalsView`、`BacktestMetricsView` |
| BC-4 交易執行與風控 | `core/risk/` `brokers/` `core/trading/` | `RiskGuard`、`TradingService` | `BaseBroker` + 3 個實作、`OrderRepository`、`PositionRepository`、`AccountRepository` | `CurrentPositionsView`、`SignalLogView`、`DashboardKpiView` |
| BC-5 新聞情緒分析 (v2.0) | `news/` | `NewsPipeline`（含 5 個 sub-service） | `BaseNewsSource` + adapters、`AnthropicLlmClient`、`NewsRepository`、`WatchlistRepository` | `NewsFeedView`、`WatchlistView`、`LlmCostMeterView` |
| BC-6 圖表與技術分析 (v1.5) | `analytics/` `ui/widgets/` | `IndicatorEngine`、`PatternDetector` | （純運算，無外部依賴） | `IndicatorPanelView`、`PatternListView`、`SparklineView` |
| BC-7 通知 | `notify/` | `NotificationService` | `SmtpNotifier`、Jinja2 範本 | — |

橫切（非 BC）：
- `security/` — DPAPI 加密。
- `storage/` — SQLite 連線、Schema migration、Backup。
- `logging/` — `AppLogService`、`AuditLogService`（對應 PM review I-14、E-3）。
- `ui/theme/` — 深淺色主題、市場慣例顏色切換（對應 FR-CH-03 colour-by-market）。

---

## 3. 分層架構與依賴規則

### 3.1 四層各自的職責

| 層 | 職責 | 不能做的事 |
| --- | --- | --- |
| Presentation | UI 事件處理、表單驗證（form-level）、顯示格式化、主題、I18n | 直接呼叫 Shioaji / yfinance / SMTP；直接寫 DB |
| Application/Service | 用例編排、跨 BC 協調、交易邊界、寫 audit log | 含商業規則細節（推到 Domain）；含 UI 狀態 |
| Domain | 商業規則、計算、不可變值物件、Aggregate root 行為 | 任何 IO、任何第三方 SDK import |
| Infrastructure | 與外部世界對話、把外部資料 marshal 到 Domain 物件 | 寫商業規則；做用例編排 |

### 3.2 依賴反轉的具體實踐

- 所有 **外部資源** 都用 `abc.ABC` 介面，介面定義在「呼叫方」的 BC 目錄下，**實作放在 infrastructure**：
  - `brokers/base.py: BaseBroker` ← 由 `core/trading/trading_service.py` 注入
  - `data/providers/base.py: MarketDataProvider` ← 由 `data/market_data_service.py` 注入
  - `news/sources/base.py: BaseNewsSource` ← 由 `news/collector.py` 注入
  - `notify/notifier_base.py: BaseNotifier` ← 由 `notify/notification_service.py` 注入
  - `news/llm/base.py: LlmClient` ← 由 `news/analyzer.py` 注入
- **DI 容器**：v1.0 採極簡作法 — 在 `app.py` / `cli.py` 的 entry point 用一個 `Container` 類別手動 wire；不引入 dependency-injector 等套件（單人專案 over-engineering 風險）。
- **可測試性**：所有外部依賴介面化 → 測試用 FakeBroker / FakeMarketData / FakeNotifier；對應 PM review 5.5 工時表中 M0~M6 各 milestone 的單元測試覆蓋率 ≥ 70%（NFR-MNT-01）。

### 3.3 例外：UI 直連 Read Model 的捷徑

純展示型查詢（KPI 卡片、清單 view）若每次都走 Service 層會讓 UI 響應變慢。採取：

- `read_models/` 目錄定義 view 物件（dataclass，無行為）。
- `read_models/projections.py` 提供 `DashboardProjection.get_kpi(account_id)` 之類的查詢函式，**直接查 DB（read-only）**，不經過 Service。
- 寫入仍一律走 Service 層 → 才能加 audit log、emit domain event。

---

## 4. 核心執行管線

### 4.1 Strategy → Signal → RiskGuard → Broker（每日自動執行）

對應 `event_storming.md` §8.1 與 PM `requirements.md` §10.2。

```
TaskScheduler 觸發 cli.py daily_run --mode=auto
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Container.build_runtime() ── wire 所有 Service & Repo                │
│                                                                      │
│  1. ModeManager.get_current() ──▶ ModeState(SIMULATION|LIVE)         │
│     └─ 若 LIVE 已 > 24h → 自動 SimulationModeRestored、SendAlertEmail │
│  2. MarketDataService.refresh_universe(symbols)                      │
│     └─ Shioaji kbars → 失敗 fallback yfinance                        │
│     └─ ValidateKbars → 缺漏 / 跳空 / 0 價 → KbarsValidationFailed     │
│  3. StrategyRunner.run_all(active_strategies)                        │
│     for each Strategy:                                               │
│       Signal[] = strategy.generate(market_snapshot, holdings)        │
│       publish SignalGenerated event                                  │
│  4. RiskGuard.evaluate(signal) ── 逐筆 ──▶ Approved / Rejected        │
│     ├ 規則順序：SymbolWhitelist → SinglePositionRisk(1%)              │
│     │           → TotalExposure(80%) → DailyLossLimit                │
│     │           → MarketHours → BlacklistTicker                      │
│     └ Daily Loss 熔斷：僅攔截 entry/add，不攔截 exit/stop-loss        │
│  5. TradingService.dispatch(approved_signals)                        │
│     根據 (mode, market) 選 Broker：                                   │
│       (SIM, TW)  → SimulatedBroker.place_order()                     │
│       (SIM, US)  → SimulatedBroker.place_order()                     │
│       (LIVE, TW) → ShioajiBroker.place_order() + AttachStopLoss      │
│       (LIVE, US) → EmailBroker.send_signal()                         │
│  6. T+1 開盤 reconciliation（次日早上單獨 job）                       │
│     SimulatedBroker.reconcile_t_plus_1() 依 T+1 open 計算成交         │
│     ShioajiBroker.fetch_fills() 拉真實成交                            │
│  7. AccountQueryService.snapshot_daily_pnl()                         │
│  8. NotificationService.send_daily_summary(mode)                     │
└─────────────────────────────────────────────────────────────────────┘
```

**T+1 成交的工程實作**：
- 訊號於 T 日 14:00（台股）或 05:30（美股）收盤後產生，**狀態寫 `PENDING_T+1_OPEN`**。
- 次一交易日 09:01（台股）/ 22:31（美股，台北時間）排程觸發 `SimulatedBroker.reconcile_t_plus_1()`：
  - 抓取 T+1 開盤價 → 若跳空 |open - T_close| / T_close > 5% → 狀態改 `UNFILLED_GAP`
  - 否則狀態改 `FILLED`，扣手續費 0.1425% / 0.18% 與滑價 0.05%。
- 回測引擎走相同 reconcile 函式（共用 `core/trading/fill_engine.py`），避免回測與模擬偏離（NFR-MNT-02 對應）。

### 4.2 模式切換管線

對應 `event_storming.md` §8.2。

```
User clicks ModeBadge
   │
   ▼
ModeManager.request_switch(target=LIVE)
   │
   ├ pre-check (parallel):
   │   ShioajiConnectionChecker.verify() ─ try 登入 + 拉 kbars
   │   SignalLockChecker.has_pending() ─ 檢查 PENDING_T+1_OPEN 是否有未對帳
   │
   ▼
UI 顯示 ModeSwitchDialog:
   - 警告文案 (紅底)
   - 對話框內顯示 "X 帳本目前 N 筆部位將被凍結"  ← FR-MM-10
   - 要求輸入 "LIVE" 字串
   - 顯示 ShioajiConnectionChecker 結果
   │
   ▼
ModeManager.confirm_switch(confirmation_string="LIVE")
   ├ validate: string == "LIVE" (case sensitive)
   ├ persist: ModeState.mode=LIVE, switched_at=now()  → config + DB audit
   ├ start 24h timer (apscheduler one-shot job)
   ├ emit LiveModeActivated → UI 訂閱者重新 query 對應帳本
   └ TopBar.refresh() ─ 重畫成紅色
```

**24h 自動回 SIM**：用 `apscheduler` 的 `DateTrigger` 排在 `switched_at + 24h`；觸發時呼叫 `ModeManager.auto_revert()` → emit `SimulationModeRestored` → 寄告警信。**回到 SIM 時 LIVE 帳本資料完全保留**（FR-MM-09），下次手動切回 LIVE 仍需二段確認且顯示「您仍有 N 筆未平倉實盤部位」（PM I-1 + FR-MM-09）。

### 4.3 訊號狀態機

```
                   StrategyRunner / WatchlistService.promote
                              │
                              ▼
                  ┌───── PENDING_RISK_CHECK ─────┐
                  │                              │
            RiskGuard.approve               RiskGuard.reject
                  │                              │
                  ▼                              ▼
       PENDING_T+1_OPEN              REJECTED_RISK (terminal)
       (台美股模擬)                   ↑
       PENDING_SHIOAJI_FILL             │ DailyLossLimit
       (台股 LIVE)                       │
       MANUAL_PENDING                     ↓
       (美股 LIVE，等使用者下單)       app_log + audit_log
            │       │
   reconcile_t_plus_1 / fetch_fills / 自然衰退
            │       │
            ▼       ▼
        FILLED    UNFILLED_GAP   FAILED
       (terminal) (terminal)    (terminal, 加掛 SendAlertEmail)

       MANUAL_PENDING ── (使用者超過 EXPIRY 未回應) ──▶ EXPIRED (terminal)
```

對應 PM review I-3：美股 `MANUAL_PENDING` 的 EXPIRY 定為「美股開盤後 30 分鐘」；過期後寄催信，狀態進 `EXPIRED`。

---

## 5. NewsPipeline 設計 (v2.0)

NewsPipeline 是**長時間 IO bound** 的批次作業（每日兩次），與其他流程隔離；採非同步管線，每個階段都是獨立 service，事件以 in-process queue 串接。

### 5.1 整體管線

```
APScheduler trigger (06:00 / 21:30 Asia/Taipei, DST aware)
       │
       ▼  ─── NewsPipeline.run() ───────────────────────────────────────
       │
       │  Stage 1: Collector  (asyncio.gather 並行各 source)
       │   ┌─ RssSource(CNBC,Reuters,TC,Verge,Ars,yfinance_news)
       │   ├─ RedditSource(r/stocks, r/investing, r/SecurityAnalysis)
       │   └─ EdgarSource(8-K filings, last 24h)
       │
       │   each fetch:
       │     - httpx.AsyncClient with timeout=15s, retry x3 (exp backoff)
       │     - rate limit per source (avoid 429)
       │     - language detect (langdetect)，非英文 → drop（PM E-8）
       │   ↓ emit ArticleFetched per article
       │
       ▼
       │  Stage 2: Deduper
       │   - URL hash exact match → drop
       │   - 標題 rapidfuzz.ratio >= 0.85 vs 過去 7 天 → drop
       │   - 通過 → 寫 news_articles → emit ArticleStored
       │
       ▼
       │  Stage 3: Analyzer (asyncio queue, max_concurrency=3)
       │   for each ArticleStored:
       │     - CostGuard.precheck() → 若預算剩餘 < $0.01 則 stop
       │     - LlmClient.analyze(article)
       │       (anthropic SDK, prompt cache system prompt)
       │     - Parse JSON output, validate by pydantic schema
       │     - 寫 news_analysis, 寫 llm_cost_daily
       │     - emit ArticleAnalyzed | AnalysisFailed (max 2 retry)
       │
       ▼
       │  Stage 4: TickerMapper
       │   for each ArticleAnalyzed:
       │     - 對 tickers[] 中每個候選 ticker:
       │       a) 內建 alias table (NVIDIA → NVDA) lookup
       │       b) yfinance Ticker(t).info 驗證 (cache 30 days)
       │     - 計算 confidence (alias hit / yfinance hit / context score)
       │     - 寫 news_tickers (含 confidence)
       │     - emit TickerMapped | TickerConfidenceLow
       │
       ▼
       │  Stage 5: Ranker
       │   - 對今日所有 confidence >= 0.7 的 (article, ticker) 對:
       │     score = impact_score × source_credibility × recency_decay
       │             × multi_source_bonus
       │   - 按 ticker 聚合，找出 ≥3 來源者 → StrongSignalMarked
       │   - 取 Top N (預設 10) → 寫 watchlist 候選池（pending）
       │
       ▼
       │  Stage 6: DigestComposer + Notifier
       │   - 渲染 HTML（看多 / 看空兩區 + 弱訊號 ticker list, PM C2.14/15）
       │   - SmtpNotifier.send(subject="[SIM] 新聞情緒摘要 - ...")
       │
       ▼  ─── NewsPipeline.complete() ──────────────────────────────────
```

### 5.2 非同步策略

- 整個 pipeline 跑在 GUI process 的 **背景 asyncio loop**（Qt event loop 共存：透過 `qasync` 套件橋接），CLI mode 則直接跑在主 loop。
- Analyzer 是瓶頸（LLM API call ~2-5s/article）→ 限制 `max_concurrency=3` 避免 rate-limit 與成本爆衝。
- 全程使用 `asyncio.Queue` 在各 stage 之間傳遞 event，每個 stage 一個 task，failure 不會整管線停。
- 若 GUI 開啟時觸發排程而 GUI 卡住 → fallback 改寫 db flag，下次啟動時補抓（避免漏分析）。

### 5.3 CostGuard 設計

- **預檢查 (pre-check)**：每篇文章發送前估算 token 數（input prompt ~3k + content ~1k + output ~0.5k），預估成本若 > 剩餘預算 → 停。
- **記錄 (post-check)**：呼叫完成後從 anthropic SDK response 取得實際 `usage.input_tokens` / `output_tokens` → 寫 `llm_cost_daily`。
- **觸發停損**：累計成本 > $0.30 → `LlmBudgetExceeded` → 寄告警信 + 停止後續 article 處理。已分析完成的不影響。
- **時區**：每日重置以 `Asia/Taipei` 00:00 為界（對應 PM I-12）。

### 5.4 兩段核可的工程實作

```
StorageView: watchlist (status=pending)
       │
       ▼  使用者於 GUI 點「加入 Watchlist」
WatchlistService.add_from_candidate(candidate_id)
       └─ insert watchlist row (added_at=now, expires_at=now+7d, status=pending)

       (時間經過... 可能幾小時或幾天)

       ▼  使用者於 GUI 點「→ 轉為交易訊號」
WatchlistService.promote(item_id)
       ├─ insert signals row (strategy="news_promoted_<item_id>", side, target_price)
       ├─ RiskGuard.evaluate(signal) ──▶ approved / rejected
       ├─ 若 approved → 立即（FR-NS-22 + PM I-10）走 TradingService.dispatch
       │   - 美股 LIVE → EmailBroker 寄獨立 "[SIM] 新聞訊號" 主旨信
       │   - 台股 LIVE → ShioajiBroker.place_order
       └─ 更新 watchlist.status = promoted
```

---

## 6. 執行模式：GUI vs CLI

兩者共用同一套 Service / Domain / Infrastructure，差別僅在 **進入點** 與 **事件 loop**。

### 6.1 GUI Mode (`app.py`)

- 用 `qasync` 把 PySide6 的 Qt event loop 與 Python `asyncio` event loop 整合 → 同一個 loop 可同時處理 UI 與 async I/O。
- `MainWindow` 啟動時 `Container.build_runtime()` 注入所有 Service。
- 內部 APScheduler 跑在 background thread，但 callback 透過 `loop.call_soon_threadsafe` 回到主 loop 執行 Service。
- 主控台、設定頁等對 Service 的呼叫，使用 `QThreadPool` 包裝避免阻塞 UI（NFR-PER-02：< 200ms 回應）。

### 6.2 CLI Mode (`cli.py`)

- 由 Windows Task Scheduler 以 `StocksTrading.exe --cli daily_run` 觸發。
- 純 asyncio main loop，無 UI 元件 import（避免帶上 PySide6 啟動成本）。
- Sub-commands：
  - `daily_run` — 每日策略執行（14:00 台、05:30 美）
  - `reconcile_t_plus_1` — T+1 成交對帳（09:01 台、22:31 美）
  - `news_collect` — 新聞抓取（06:00、21:30）
  - `backup` — 每日 DB 備份（22:00）
  - `cleanup` — 日誌與快取清理（每週日 03:00）
- Task Scheduler XML 範本由 MSI 安裝時放入 `%LOCALAPPDATA%\StocksTrading\scheduled_tasks\` 並提示使用者匯入。

### 6.3 共用元件邊界

| 元件 | GUI | CLI | 備註 |
| --- | --- | --- | --- |
| Service 層 | ✅ | ✅ | 完全共用 |
| Domain 層 | ✅ | ✅ | 完全共用 |
| Infrastructure 層 | ✅ | ✅ | 完全共用 |
| `ui/*` | ✅ | ❌ | CLI 不 import |
| `qasync` | ✅ | ❌ | CLI 用純 `asyncio.run` |
| `apscheduler` | ✅（內部排程，顯示「下次執行時間」） | ❌（外部 Task Scheduler 已負責） | |

---

## 7. Deployment 視角

### 7.1 MSI 安裝後目錄結構

```
C:\Program Files\StocksTrading\                  ← 安裝目錄 (NFR-DEP-02)
├── StocksTrading.exe                            ← GUI entry (cx_Freeze frozen)
├── StocksTrading-cli.exe                        ← CLI entry
├── python311.dll, base_library.zip              ← cx_Freeze frozen runtime
├── lib/
│   ├── PySide6/, shioaji/, anthropic/, ...      ← frozen packages
│   └── stocks_trading/                          ← 應用程式 source 編譯後
├── resources/
│   ├── icons/, themes/, email_templates/        ← 靜態資源
│   └── scheduled_tasks/                         ← Task Scheduler .xml 範本
└── uninstall.exe

%LOCALAPPDATA%\StocksTrading\                    ← 使用者資料（升級不動）
├── config.json                                  ← 明文設定（不含密碼）
├── secrets.dat                                  ← DPAPI 加密密碼
├── app.db                                       ← SQLite 主檔
├── backups/
│   ├── 20260523_140230.db.gz                    ← 每日備份（保留 30 天）
│   └── monthly_202604.db.gz                     ← 月底快照（保留 12 個月）
├── logs/
│   ├── app.log                                  ← rotating file handler
│   └── archived/2026-04.log.gz                  ← 壓縮歸檔（保留 90 天）
└── cache/
    └── ticker_aliases.json                      ← yfinance ticker lookup cache
```

設計重點對應 PM review I-8（備份）、I-14（日誌保留）：
- `BackupService` 在每日 daily_run 完成後執行 → `app.db` 拷貝 + gzip → 寫入 `backups/YYYYMMDD.db.gz`。
- `logs/app.log` 用 Python `logging.handlers.TimedRotatingFileHandler`（daily），保留 90 天，超過則 gzip 移到 `archived/`。
- `audit_log` 表獨立於 `app_log`，**不自動清理**（PM E-3：操作審計保留 365 天，且不可刪除）。

### 7.2 安裝與升級流程

```
首次安裝:
  MSI 執行 → 解壓 Program Files → 建立 %LOCALAPPDATA%\StocksTrading\ 空目錄
  → 寫入 default config.json → 首次啟動執行 schema migration v0 → v_current

升級安裝 (e.g. v1.0 → v1.5):
  MSI 偵測舊版 → 解壓覆蓋 Program Files\ 內容
  → %LOCALAPPDATA% 完全不動  (對應 NFR-DEP-04, PM I-9)
  → 首次啟動時 MigrationRunner.upgrade():
      1. 備份當前 app.db → backups/pre_upgrade_v1.5.db.gz
      2. 依 schema_version 表決定要跑哪些 migration script
      3. 跑完更新 schema_version；失敗則還原備份並停止
  → 寄出告警信「升級到 v1.5 完成，已備份」

解除安裝:
  預設保留 %LOCALAPPDATA% 資料；
  進階選項提供「同時刪除使用者資料」勾選框（預設不勾）。
```

### 7.3 v1.0 LIVE 模式封鎖機制

對應 PM `release_plan.md` §2.1：v1.0 LIVE 模式 UI 隱藏 / 灰階。
- **後端完整實作雙帳本** —`ModeManager`、`accounts.mode` 欄位、`orders.mode` 欄位、Broker 抽象、SimulatedBroker 全部到位。
- **UI 層**：`TopBar` 的 ModeBadge 顯示 "SIM"，**LIVE 切換 toggle disabled**，hover tooltip 顯示 `v1.5 開放，預計 YYYY-MM-DD`（對應 PM 風險表 "v1.0 LIVE UI 灰階使用者誤以為壞掉"）。
- **v1.5 解鎖**：MSI 升級後，`FeatureFlag.live_mode_enabled=True`（config.json 或內建常數），UI 自動解鎖。

---

## 8. 階段擴充策略 (v1.0 → v1.5 → v2.0)

設計鐵則：**v1.0 一定要把 v2.0 的擴充點先留好，但不實作**。下表列出每個 BC 在各版本的狀態：

| BC | v1.0 | v1.5 | v2.0 |
| --- | --- | --- | --- |
| BC-1 模式管理 | ✅ 後端完整，UI 隱藏 LIVE | ✅ UI 開放 LIVE 切換 | — |
| BC-2 市場資料 | ✅ kbars 抓取 + 快取 | — | — |
| BC-3 策略 + 回測 | ✅ Dual Momentum + backtrader | — | — |
| BC-4 交易執行 | ✅ SimulatedBroker + RiskGuard | ✅ + ShioajiBroker + EmailBroker | — |
| BC-5 新聞分析 | ❌ 不存在 | ❌ 不存在 | ✅ 整個 NewsPipeline + GUI |
| BC-6 圖表 | ❌ 不存在 | ✅ IndicatorEngine + PatternDetector + ChartPage | — |
| BC-7 通知 | ✅ SMTP 核心 + 每日摘要 + 告警 | ✅ + 美股訊號 Email + 下單檢核清單 | ✅ + Daily News Digest |

### 8.1 v1.0 預留的 v2.0 擴充點

| 擴充點 | 留在哪 | 做法 |
| --- | --- | --- |
| News 相關 5 張表 schema | `storage/migrations/0003_add_news.sql` 寫好但 v1.0 **不執行**，或 v1.0 已建空表 | 建議直接建空表，v2.0 直接寫入即可，免 migration 風險 |
| `signals.strategy` 欄位接受 "news_promoted" prefix | Domain 不做任何 enum 限制 | 已自然支援 |
| GUI 主視窗預留 News / Chart 分頁的 nav 位置 | `MainWindow.NAV_ITEMS` 列表 | v1.0 用 `enabled=False` 標記，v1.5/v2.0 翻成 True |
| `BaseNotifier` 介面同時支援 `send_signal` / `send_digest` | `notify/notifier_base.py` 介面定好 | v1.0 只實作 `send_summary` / `send_alert`，其他方法 `raise NotImplementedError` |

### 8.2 v1.5 預留的 v2.0 擴充點

| 擴充點 | 做法 |
| --- | --- |
| Watchlist 卡片「查看 K 線」按鈕 | v1.5 的 ChartPage 已有 `open_chart(symbol)` API，v2.0 直接呼叫 |
| Pattern 過濾器（FR-CH-27） | v1.5 IndicatorEngine 輸出 `IndicatorSnapshot`，v2.0 的 RiskGuard 可訂閱檢查（**v2.0 之後再考慮**） |

---

## 9. 與 PM Review 的對應

下表確認 §architecture 解決了 PM `requirements_review.md` 中的多項 issues / enhancements：

| PM Review 項 | 在本架構文件中解決於 |
| --- | --- |
| I-1 雙帳本資料隔離 | §4.2 模式切換管線、§7.1 `accounts.mode` 欄位 |
| I-2 多幣別計算（80% 上限） | §4.1 RiskGuard 規則順序（細節見 `data_design.md`） |
| I-3 美股訊號 EXPIRY | §4.3 訊號狀態機 `MANUAL_PENDING → EXPIRED` |
| I-4 訊號逐筆審查 / 熔斷只擋 entry | §4.1 RiskGuard 規則順序 |
| I-5 Pattern 過濾器明示 | §8.2 v2.0 之後再考慮，預留追溯記錄欄位 |
| I-6 24h 計時器語意 | §4.2 LIVE 進入後 24h 自動回 SIM |
| I-7 DST 處理 | §5.1 NewsPipeline trigger 標註 `Asia/Taipei, DST aware` |
| I-8 資料庫備份 | §7.1 backups/ 目錄、§6.2 CLI `backup` sub-command |
| I-9 MSI 升級保留資料 | §7.2 升級流程 |
| I-10 Watchlist 立即下單 | §5.4 promote 立即走 dispatch |
| I-11 T+1 開盤價成交 | §4.1 fill_engine、§4.3 訊號狀態機 |
| I-12 LLM 預算重置時點 | §5.3 CostGuard 以 Asia/Taipei 00:00 為界 |
| I-13 測試信 [TEST] 前綴 | 由 NotificationService 在組裝主旨時加上（細節見 `component_design.md`） |
| I-14 日誌保留 | §7.1 `logs/archived/` 90 天 |
| E-3 audit_log | §2 橫切表、§7.1 audit_log 不自動清理 |

---

## 10. 已知架構風險與決策說明

| 風險 | 決策 | 備註 |
| --- | --- | --- |
| **單檔 SQLite** 在資料量成長後是否瓶頸？ | 接受。MVP 預估 10 年內每張表 < 100 萬列，SQLite 完全 OK；若日後資料爆量再考慮 DuckDB / PostgreSQL | |
| 為何不用 message queue / event bus？ | 單機桌面 app + 單人使用，引入 RabbitMQ / Redis 是 over-engineering；in-process `asyncio.Queue` + domain events 已足夠 | NewsPipeline 也是 in-process |
| Service 層直接呼叫 Repository，沒有 CQRS | 接受。讀寫流量極低，CQRS 只會增加維護成本 | 但保留 `read_models/` 目錄作為純查詢出口（§3.3） |
| `qasync` 是否成熟？ | 風險中。是 PySide6 + asyncio 唯一可行整合方案；若 v2.0 開發發現 bug 過多，fallback 是把 NewsPipeline 放 thread pool 跑 | 已在 `tech_decisions.md` 列管 |
| ShioajiBroker 含 native DLL，frozen 後是否能載入？ | 風險高（v1.5 才會踩到）；cx_Freeze 已知對 native DLL 處理有坑，需先做 PoC | 詳見 `tech_decisions.md` |
