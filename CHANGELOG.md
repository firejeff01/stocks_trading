# Changelog

依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/) 與 SemVer．

## [Unreleased]

### 新增 (Added) — v2.0 新聞情緒分析模組

完整的新聞情緒 pipeline：用使用者的 Claude Max (`claude -p`) 分析新聞、多因子
排序候選、進觀察清單、**兩段手動核可**後轉為手動訊號．

**分析核心**
- `LLMAnalyzer` ABC + `ClaudeCliAnalyzer`：走本機 `claude -p` (Claude Max 訂閱)
  → 結構化 JSON (sentiment/impact/summary/catalysts/tickers)；注入式 CliRunner
  可測、容錯重試、claude 不在 / 未登入分類處理．
- `CostGuard`：每日用量上限 (以呼叫次數為主，因 claude -p 每篇約 $0.06~0.08)．

**蒐集**
- `NewsCollector` + `SourceAdapter`：多來源聚合、url_hash 去重、單一來源失敗隔離．
- `RssAdapter` (RSS 2.0 / Atom，純標準庫)、`YFinanceNewsAdapter` (個股新聞)．

**排序 / 觀察清單**
- `TickerMapper`：信心門檻 + 黑名單過濾 (反 LLM 幻覺)．
- `Ranker`：多因子排名 (影響 × 來源信用 × 時效衰減 × 多源加成)、強訊號 ≥3 來源．
- watchlist / news_tickers / blacklist / source_credibility / audit_log repos．

**核可 / 通知**
- `WatchlistPromotionService`：兩段手動晉升 → MANUAL_PENDING signal (使用者填
  進場/停損價，service 不發明價格)、寫 audit_log、防重複晉升．
- `NewsDigestBuilder`：每日 Top 10 候選 HTML email (強訊號醒目色 + LLM 用量)．
- `WatchlistPage` GUI (📰 新聞候選 分頁) + 兩段確認對話框．

**整合**
- `run_news_pipeline`：collect → analyze (CostGuard 守門) → map → rank →
  watchlist → digest，錯誤隔離、dry-run．
- CLI `stocks-trading-cli news`、`news_daily.xml` 排程範本、設定頁新聞參數群組．

### 修正 (Fixed)
- RSS 抓取帶 User-Agent，修 CNBC HTTP 403．

### 統計
- 773 tests 全綠、ruff / mypy strict 全綠．
- DB schema (7 張 news 表) v1.0 即預建，v2.0 無新 migration．

## [1.1.0] — 2026-05-31 — K 線圖表 + Paper Trading + 風控

繼 v1.0 之後累積的功能整合釋出：完整 paper trading 自動化、K 線技術分析、
風險控管，並修正多項打包 / 文件 / migration 安全問題。

> **版本對齊**：套件版本由內部 0.x 體系改為與 git tag 一致的 1.x
> (0.1.1 → 1.1.0)，自此 `__version__`、MSI、git tag 三者同號。

### 新增 (Added)

**Paper Trading 自動化**
- `PaperTradingService`：`settle_pending` 用隔日開盤價結算 PENDING 訊號、
  `FeeCalculator` (台股 0.0855% + 0.3% 證交稅、美股 0.5% min USD 35、滑價 0.05%)、
  `snapshot_equity` 每日績效快照
- CLI `stocks-trading-cli daily-routine`：抓資料 → 結算 → 跑策略 → 寫訊號 →
  快照 → 寄日報；依 ticker 形狀自動分流 SIM-TW / SIM-US
- CLI `backtest` / `signal-list` 子命令
- DashboardPage：SIM-TW / SIM-US KPI + 績效曲線；訊號日誌頁接 SignalRepository
- SettingsPage：SIM 帳本起始資金 + 重置 (`ResetService`，二次確認，保留訊號歷史)

**風險控管 (RiskGuard)**
- `risk/guard.py`：單檔資金上限 (名目 ≤ X% × equity，預設 20%) / 總曝險上限 /
  單日熔斷，接進 paper trading 買進路徑 (超限縮股、額度耗盡或熔斷 → `REJECTED_RISK`)
- 設定頁「風險控管」群組新增「單檔上限」「單日熔斷 (%)」欄位 + 說明；
  CLI 讀設定注入 RiskGuard

**策略**
- `MeanReversionStrategy`：RSI 超買超賣逆勢 (BUY/SELL)；CLI `--strategy` 可選

**K 線圖表 + 技術分析 (M5.7)**
- 指標：MA / EMA / RSI (Wilder) / Bollinger / MACD (`analytics/indicators.py`)
- 形態偵測：黃金/死亡交叉、布林上下軌突破、RSI 超買賣、爆量 (`analytics/patterns.py`)
- 週期聚合：日/週/月/季/年 K (`analytics/aggregator.py`)
- ChartPage：pyqtgraph 蠟燭主圖 (MA overlay / 十字游標 / 圖內 OHLC 浮框) +
  Volume / RSI / MACD 切換式副圖 + 形態清單；換股自動置中、非同步抓資料、
  成交量軸用「萬/億」單位、價格四捨五入 2 位

**資料安全**
- Migration 升級前自動整檔備份 (`<db>.bak.<timestamp>`)、失敗自動還原 (release_plan §6.2)

### 修正 (Fixed)
- `StocksTrading-cli.exe` 原誤指向 `app.py` 會啟動 GUI；改指 `cli/main.py` 才真正跑 CLI
- Task Scheduler 範本參數從不存在的 `--daily-routine --market` 改為正確子命令
  `daily-routine --tickers ...`；移除「v1.0 未實作」的過時說明；合併重複範本
- daily-routine 日報「今日 PnL」改算真實差額 (不再寫死 0)
- 文件漂移：README 版本 / 測試數 / 里程碑勾選 / 模組結構全面更新為現況
- mypy strict 對測試碼的漏網 error (先前被 `.mypy_cache` 遮蔽) 一併修正

### 統計
- 635 tests 全綠
- ruff / mypy strict 全綠 (`--no-incremental` 清查確認)

## [0.1.1] — 2026-05-23 — UI 接資料層 + Shioaji 行情

UI 真正接通 yfinance / Shioaji，回測頁可實際執行．

### 新增 (Added)
- `ToggleSwitch` 自繪滑動式開關 widget (取代主題切換按鈕)
- BacktestPage 日期欄行事曆 popup (使用者體驗)
- `ShioajiDataProvider`：永豐 API 行情抓取 (login/fetch_bars/logout)
  - 自動聚合 minute kbars → daily Bar
  - sj_factory DI 注入便利測試
- SettingsPage 新增「永豐 Shioaji API」區塊
  - API Key + Secret Key 兩欄 (兩者 DPAPI 加密)
  - 「測試連線」按鈕
- `MarketDataRouter`：TW→Shioaji / US→yfinance 統一介面
  - Shioaji 未登入時自動 fallback yfinance
- BacktestPage `▶ 執行回測` 按鈕啟用：
  - 「標的 (CSV)」欄位 (4 碼數字 → TW、否則 → US)
  - 同步抓資料 → 跑 BacktestEngine → 顯示績效
- Dashboard KPI 顯示真實 SIM-US 帳本 equity ($3000 seed)
- 應用程式啟動時自動嘗試 Shioaji login (失敗不阻擋)

### 強化 (Enhanced)
- .gitignore：排除 `pm/api_key/`、`api_key.txt`、CA 憑證 (*.pfx/.p12)

### 統計
- 410 tests 全綠 (+39 from v0.1.0)
- ruff / mypy strict 全綠

## [0.1.0] — 2026-05-23 — v1.0 Paper Trading MVP

第一個可裝可跑的 release．**僅模擬模式 (paper trading)**，實盤模式留給 v1.5．

### 新增 (Added)

**M0 — 地基**
- Domain values：`Mode` / `Side` / `Currency` / `Market` / `Money` / `Symbol`
- Domain entities：`Account` (雙帳本) / `Signal` (含 9 狀態狀態機)
- `BaseBroker` 抽象介面 + `OrderResult` 值物件
- SQLite migration runner (檔名 `NNNN_description.sql`)
- `0001_initial.sql`：17 張表 + 4 seed accounts (SIM/LIVE × TWD/USD)
- Windows DPAPI 加密 wrapper (`DpapiCipher`)
- `ConfigStore`：明文設定 (config.json) + DPAPI 加密 secrets (secrets.dat)

**M1 — 資料層 + 策略**
- `Bar` (OHLCV) 值物件，Decimal 精度
- `KbarsRepository` SQLite 快取
- `YFinanceProvider` (DI 注入 downloader 便利測試)
- `IndicatorEngine`：cumulative_return / SMA
- `BaseStrategy` ABC + `DualMomentumStrategy`
- `FillEngine` 純函式：T+1 開盤成交 + 5% 跳空保護
  → BacktestEngine 與 SimulatedBroker 共用，杜絕回測偏離

**M2 — Broker + 回測**
- `AccountRepository` / `SignalRepository`
- `PortfolioState` in-memory 模擬 (現金 / 持倉 / 已實現損益 / 勝率)
- `SimulatedBroker` 兩階段：`place_order` → `reconcile_at_open`
- `BacktestEngine` 整合策略 + FillEngine + Portfolio
  → 輸出 equity curve、total/annualized return、max drawdown、win rate

**M3 — PySide6 GUI**
- `ThemeManager` 明暗主題切換 + 偏好持久化
- `MainWindow`：sidebar 5 nav + topbar (mode 標籤 + 時鐘 + 主題切換)
- 主控台 (KPI 卡片 + 持倉表 + 訊號表)
- 策略 (Dual Momentum 參數)
- 回測 (參數 form + 績效顯示)
- 訊號日誌 (狀態過濾)
- 設定 (SMTP / 風控)
- App 進入點 `stocks-trading` (pip console script)

**M4a — Email 通知**
- `EmailMessage` 不可變值物件
- `SmtpClient` (STARTTLS + DI 注入便利測試)
- `DailySummaryBuilder` (HTML 收盤摘要)
- `SystemAlertBuilder` ([ALERT] 告警)
- `NotificationService` 整合 + `from_config` 工廠
- 設定頁「寄送測試信」按鈕

**M6a — 打包**
- `cx_Freeze` MSI 安裝檔 (~260 MB)
- 兩個 .exe：`StocksTrading.exe` (GUI) + `StocksTrading-cli.exe` (CLI 預留)
- Windows Task Scheduler XML 範本 (預留 v1.5 使用)

### 已知限制 (Known Limitations)

- **實盤模式 UI 灰階** — 不能在 v1.0 切到 LIVE．v1.5 開放 (M5)
- **`StocksTrading-cli.exe --daily-routine` 預留未實作** —
  自動排程跑策略 + 寄摘要要等 v1.5
- **K 線圖表未實作** — v1.5 (M5.7)
- **新聞情緒分析未實作** — v2.0 (M5.5)
- **MSI 未簽署** — 安裝時 Windows SmartScreen 可能警告，按「仍要執行」即可
- **`StocksTrading-cli.exe --daily-routine` 預留未實作** —
  自動排程跑策略 + 寄摘要要等 v1.5

### 統計

- 371 tests 全綠
- ruff / mypy strict 全綠
- 40 個 commits（含 PM + SA 規劃階段）
