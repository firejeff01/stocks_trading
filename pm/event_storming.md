# 事件風暴分析：自動化股票交易系統

> 文件版本：v0.1
> 建立日期：2026-05-23
> 文件擁有者：gamma.jeff.lin@gmail.com
> 依據需求文件：`pm/requirements.md` v0.2 + `pm/requirements.html`
> 分析方法：Event Storming（Big Picture + Process Level）

---

## 0. Bounded Contexts（建議的限界上下文）

依據需求文件中的職責邊界與獨立性，建議切分為下列 7 個 Bounded Context：

| BC 編號 | 名稱（中文 / 英文） | 核心職責 | 對應需求 | 對應服務元件 |
| --- | --- | --- | --- | --- |
| BC-1 | 模式管理 Mode Management | 切換 SIM ↔ LIVE、提供全域模式狀態、24h 自動回模擬 | FR-MM-* | `ModeManager` |
| BC-2 | 市場資料 Market Data | 抓取 / 快取台美股日線、提供策略與圖表用資料 | FR-DL-* | `MarketDataProvider`, `kbars_cache` |
| BC-3 | 策略與回測 Strategy & Backtesting | Dual Momentum 策略、訊號生成、歷史回測 | FR-SE-*, FR-BT-*, FR-SC-* | `StrategyRunner`, `BacktestEngine`, `SchedulerService` |
| BC-4 | 交易執行與風控 Trading Execution | 風控檢查、下單（Shioaji / Email / Simulated）、持倉與委託記錄 | FR-EX-*, FR-RM-* | `RiskGuard`, `Broker` 抽象與 3 個實作 |
| BC-5 | 新聞情緒分析 News & Sentiment | 抓取新聞 → LLM 分析 → ticker mapping → 排序 → Watchlist | FR-NS-* | `NewsPipeline`, `CostGuard`, `WatchlistService` |
| BC-6 | 圖表與技術分析 Chart & Technical Analysis | K 線繪製、指標計算、形態偵測（不獨立觸發下單） | FR-CH-* | `IndicatorEngine`, `PatternDetector` |
| BC-7 | 通知 Notification | Email 寄送（訊號 / 摘要 / 告警 / News Digest） | FR-NT-*, FR-NS-26~29 | `NotificationService`, `SmtpNotifier` |

**橫切關注（非獨立 BC，但跨多個 BC）：**
- 安全（DPAPI 加密、密碼遮蔽）— NFR-SEC-*
- UI / 主題（PySide6 + 深淺色）— FR-UI-*
- 部署與升級（MSI、資料保留）— NFR-DEP-*

---

## 1. Actors（行為者）

| 類別 | Actor | 觸發行為 |
| --- | --- | --- |
| 人類 | 開發者 / 使用者（唯一） | UI 操作、模式切換、Watchlist 核可、回測、設定 |
| 系統 | Windows Task Scheduler | 每日定時觸發 CLI 策略執行 |
| 系統 | APScheduler（GUI 內部排程） | GUI 開啟時顯示下次執行時間、觸發新聞抓取 06:00 / 21:30 |
| 系統 | CostGuard | 累計 LLM 成本超過上限時停止分析 |
| 系統 | RiskGuard | 對所有訊號進行風控檢查 |

---

## 2. External Systems（外部系統）

| 外部系統 | 用途 | 對應 BC |
| --- | --- | --- |
| 永豐 Shioaji API | 台股下單、kbars 日線 | BC-2, BC-4 |
| yfinance | 美股日線、台股退回方案、ticker lookup | BC-2, BC-5 |
| Anthropic Claude API (haiku-4-5) | 新聞情緒分析 | BC-5 |
| RSS Feeds（CNBC / Reuters / Ars Technica / TechCrunch / The Verge） | 新聞原文抓取 | BC-5 |
| Reddit JSON API（r/stocks, r/investing, r/SecurityAnalysis） | 社群新聞 / 討論 | BC-5 |
| SEC EDGAR | 8-K filings | BC-5 |
| SMTP (Gmail) | Email 通知傳遞 | BC-7 |
| Windows DPAPI | 機敏資料加密 | 橫切 |
| Windows Task Scheduler | 外部排程觸發 CLI | BC-3 |

---

## 3. Aggregates（聚合根）

| 聚合 | BC | 接收 Commands | 產生 Domain Events | 對應資料表 |
| --- | --- | --- | --- | --- |
| `ModeState` | BC-1 | RequestModeSwitch, ConfirmLiveSwitch, AutoRevertMode | ModeSwitchRequested, LiveModeActivated, SimulationModeRestored | (config.json) |
| `KbarsCache` | BC-2 | FetchKbars, ForceRefreshKbars | KbarsFetched, KbarsValidationFailed | `kbars_cache` |
| `Strategy` (DualMomentum) | BC-3 | RunStrategy, UpdateStrategyParams | SignalGenerated | (in-memory) |
| `Backtest` | BC-3 | RunBacktest, ExportBacktestResult | BacktestCompleted, BacktestExported | (in-memory + 匯出檔) |
| `Signal` | BC-3 / BC-4 | PromoteToOrder | SignalRiskApproved, SignalRiskRejected | `signals` |
| `Account` | BC-4 | InitializeAccount | AccountCreated | `accounts` |
| `Order` | BC-4 | PlaceOrder, MarkOrderFilled, MarkOrderFailed | OrderPlaced, OrderFilled, OrderFailed | `orders` |
| `Position` | BC-4 | OpenPosition, ClosePosition, UpdateStopLoss | PositionOpened, PositionClosed, StopLossTriggered | `positions` |
| `DailyPnL` | BC-4 | SnapshotDailyPnL | DailyPnLSnapshotted | `daily_pnl` |
| `NewsArticle` | BC-5 | CollectArticle, DeduplicateArticle | ArticleCollected, ArticleDuplicated, ArticleStored | `news_articles` |
| `NewsAnalysis` | BC-5 | AnalyzeArticle | ArticleAnalyzed, AnalysisFailed | `news_analysis`, `news_tickers` |
| `LlmCostBudget` | BC-5 | RecordLlmCost, CheckBudget | LlmCostRecorded, LlmBudgetExceeded | `llm_cost_daily` |
| `Watchlist` | BC-5 | AddToWatchlist, PromoteWatchlistItem, DismissWatchlistItem, ExpireWatchlistItem | WatchlistItemAdded, WatchlistItemPromoted, WatchlistItemDismissed, WatchlistItemExpired | `watchlist` |
| `Blacklist` | BC-5 | AddBlacklistEntry, ReportFakeNews | BlacklistEntryAdded, SourceCredibilityAdjusted | `blacklist` |
| `Chart` | BC-6 | OpenChart, ToggleIndicator, ChangeTimeframe | ChartOpened, IndicatorComputed, PatternDetected | (in-memory) |
| `EmailMessage` | BC-7 | SendSignalEmail, SendDigestEmail, SendDailySummaryEmail, SendAlertEmail, SendTestEmail | EmailSent, EmailDeliveryFailed | (SMTP) |
| `AppLog` | 橫切 | WriteLog | LogEntryWritten | `app_log` |

---

## 4. Domain Events（全部事件清單，過去式）

### BC-1 模式管理
- 🟠 `ModeSwitchRequested` 模式切換已請求（使用者按下頂欄按鈕）
- 🟠 `LiveConfirmationStringEntered` 實盤確認字串已輸入
- 🟠 `ShioajiConnectionVerified` Shioaji 連線已驗證
- 🟠 `ShioajiConnectionFailed` Shioaji 連線已失敗
- 🟠 `LiveModeActivated` 實盤模式已啟用
- 🟠 `SimulationModeActivated` 模擬模式已啟用
- 🟠 `SimulationModeRestored` 模擬模式已自動回復（24 小時後）
- 🟠 `ModeStatePersisted` 模式狀態已持久化

### BC-2 市場資料
- 🟠 `KbarsFetched` 日線資料已抓取
- 🟠 `KbarsCached` 日線資料已快取
- 🟠 `KbarsValidationFailed` 日線資料驗證未通過（缺漏 / 價格異常 / 跳空）
- 🟠 `ShioajiKbarsFailed` Shioaji kbars 抓取失敗（觸發 fallback）
- 🟠 `YfinanceFallbackUsed` yfinance 備援已啟用
- 🟠 `KbarsForceRefreshed` 日線快取已強制清除重抓

### BC-3 策略與回測
- 🟠 `StrategyExecutionTriggered` 策略執行已觸發（Scheduler / 手動）
- 🟠 `SignalGenerated` 訊號已產生
- 🟠 `StrategyExecutionCompleted` 策略執行已完成
- 🟠 `StrategyParamsUpdated` 策略參數已更新
- 🟠 `BacktestStarted` 回測已開始
- 🟠 `BacktestCompleted` 回測已完成
- 🟠 `BacktestExported` 回測結果已匯出（CSV / PNG）

### BC-4 交易執行與風控
- 🟠 `SignalRiskApproved` 訊號已通過風控
- 🟠 `SignalRiskRejected` 訊號已被風控攔截
- 🟠 `DailyLossLimitTriggered` 單日虧損熔斷已觸發
- 🟠 `OrderPlaced` 委託已送出（Shioaji 或模擬）
- 🟠 `OrderFilled` 委託已成交
- 🟠 `OrderFailed` 委託已失敗
- 🟠 `StopLossOrderAttached` 停損條件單已附掛（台股）
- 🟠 `UsSignalEmailDispatched` 美股訊號 Email 已寄出
- 🟠 `PositionOpened` 部位已建立
- 🟠 `PositionClosed` 部位已平倉
- 🟠 `StopLossTriggered` 停損已觸發
- 🟠 `DailyPnLSnapshotted` 每日損益已快照
- 🟠 `RiskParamsAdjusted` 風控參數已調整

### BC-5 新聞情緒分析
- 🟠 `NewsCollectionTriggered` 新聞抓取已觸發（06:00 / 21:30）
- 🟠 `ArticleCollected` 新聞原文已抓取
- 🟠 `ArticleDuplicated` 新聞已判定為重複（去重）
- 🟠 `ArticleStored` 新聞已入庫
- 🟠 `ArticleCollectionFailed` 來源抓取已失敗（重試 3 次後）
- 🟠 `ArticleAnalysisRequested` 新聞 LLM 分析已請求
- 🟠 `ArticleAnalyzed` 新聞已分析完成（sentiment / impact / tickers）
- 🟠 `AnalysisFailed` 新聞分析已失敗（重試 ≤ 2 次後）
- 🟠 `TickerMapped` 公司名 → ticker 已對應
- 🟠 `TickerConfidenceLow` ticker 對應信心度過低（< 0.7）
- 🟠 `LlmCostRecorded` LLM 成本已記錄
- 🟠 `LlmBudgetExceeded` LLM 預算已超出
- 🟠 `LlmAnalysisAutoStopped` LLM 分析已自動停止
- 🟠 `CandidateRanked` 候選標的已排序
- 🟠 `StrongSignalMarked` 強訊號已標示（≥ 3 來源）
- 🟠 `WatchlistItemAdded` Watchlist 項目已加入
- 🟠 `WatchlistItemPromoted` Watchlist 項目已轉為交易訊號
- 🟠 `WatchlistItemDismissed` Watchlist 項目已忽略
- 🟠 `WatchlistItemExpired` Watchlist 項目已自動過期（7 天）
- 🟠 `BlacklistEntryAdded` 黑名單項目已加入
- 🟠 `FakeNewsReported` 假新聞已回報
- 🟠 `SourceCredibilityAdjusted` 來源信用度已調整

### BC-6 圖表與技術分析
- 🟠 `ChartOpened` 圖表已開啟（指定標的）
- 🟠 `TimeframeChanged` 時間週期已切換
- 🟠 `IndicatorToggled` 技術指標已切換顯示
- 🟠 `IndicatorComputed` 技術指標已計算
- 🟠 `PatternDetected` K 線形態已偵測（黃金叉 / 死亡叉 / 爆量 / 布林突破 / RSI 超買超賣）
- 🟠 `ChartExportedPng` 圖表已匯出 PNG

### BC-7 通知
- 🟠 `EmailComposed` Email 已組裝（含 [SIM]/[LIVE] 標題）
- 🟠 `EmailSent` Email 已寄出
- 🟠 `EmailDeliveryFailed` Email 寄送已失敗
- 🟠 `TestEmailSent` 測試信已寄出
- 🟠 `DailySummaryEmailSent` 每日摘要已寄出
- 🟠 `NewsDigestEmailSent` 新聞情緒摘要已寄出
- 🟠 `AlertEmailSent` 告警信已寄出

---

## 5. Commands（命令）

依 BC 整理；每個 Command 對應到一個或多個 Domain Event。

### BC-1 模式管理
- 🔵 `RequestModeSwitch`（由使用者觸發）
- 🔵 `ConfirmLiveSwitch(confirmation_string)`（由使用者觸發）
- 🔵 `VerifyShioajiConnection`（由 ModeManager 觸發）
- 🔵 `RevertToSimulationMode`（由 24h 計時器觸發）
- 🔵 `PersistModeState`（由 ModeManager 觸發）

### BC-2 市場資料
- 🔵 `FetchKbars(symbol, market, date_range)`（由 StrategyRunner / Chart 觸發）
- 🔵 `ForceRefreshKbars(symbol)`（由使用者觸發）
- 🔵 `ValidateKbars(payload)`（由 KbarsCache 自動觸發）

### BC-3 策略與回測
- 🔵 `RunStrategy(strategy_id, mode)`（由 Scheduler / 使用者觸發）
- 🔵 `UpdateStrategyParams(params)`（由使用者觸發）
- 🔵 `RunBacktest(strategy, date_range, capital, universe)`（由使用者觸發）
- 🔵 `ExportBacktestResult(format)`（由使用者觸發）

### BC-4 交易執行與風控
- 🔵 `EvaluateSignalRisk(signal)`（由 StrategyRunner 觸發 → RiskGuard 執行）
- 🔵 `PlaceOrder(signal, mode, market)`（由 RiskGuard 通過後觸發）
- 🔵 `AttachStopLossOrder(order)`（由 ShioajiBroker 觸發，台股限定）
- 🔵 `SimulateFill(order)`（由 SimulatedBroker 觸發）
- 🔵 `DispatchUsSignalEmail(signal)`（由 EmailBroker 觸發，美股實盤限定）
- 🔵 `SnapshotDailyPnL()`（由 Scheduler 收盤後觸發）
- 🔵 `AdjustRiskParams(params)`（由使用者觸發；實盤下需二次確認）

### BC-5 新聞情緒分析
- 🔵 `TriggerNewsCollection(schedule)`（06:00 / 21:30 觸發）
- 🔵 `CollectArticleFromSource(source)`（NewsCollector）
- 🔵 `DeduplicateArticle(article)`（NewsCollector）
- 🔵 `RequestLlmAnalysis(article)`（NewsAnalyzer）
- 🔵 `MapTickers(analysis_result)`（TickerMapper）
- 🔵 `RankCandidates(analyses)`（Ranker）
- 🔵 `CheckLlmBudget()`（CostGuard，每次分析前後）
- 🔵 `AutoStopLlmAnalysis()`（CostGuard 觸發）
- 🔵 `AddToWatchlist(candidate)`（由使用者觸發）
- 🔵 `PromoteWatchlistItem(item_id)`（由使用者觸發 — 第二段核可）
- 🔵 `DismissWatchlistItem(item_id)`（由使用者觸發）
- 🔵 `ExpireWatchlistItem()`（由 Scheduler 每日觸發，> 7 天的項目）
- 🔵 `AddBlacklistEntry(type, value)`（由使用者觸發）
- 🔵 `ReportFakeNews(article_id)`（由使用者觸發）

### BC-6 圖表與技術分析
- 🔵 `OpenChart(symbol)`（由使用者觸發）
- 🔵 `ChangeTimeframe(tf)`（由使用者觸發；可為 1m / 60m / 日 / 週 / 月，HTML mockup 顯示有 1m，需與需求 FR-CH-02 對齊 — 見 consistency_review）
- 🔵 `ToggleIndicator(indicator)`（由使用者觸發）
- 🔵 `ComputeIndicators(symbol, kbars)`（由 Chart 內部觸發）
- 🔵 `DetectPatterns(symbol, kbars)`（由 Chart 內部觸發）
- 🔵 `ExportChartPng()`（由使用者觸發）

### BC-7 通知
- 🔵 `SendTestEmail()`（由使用者於設定頁觸發）
- 🔵 `SendSignalEmail(signal)`（由 EmailBroker 觸發）
- 🔵 `SendDailySummaryEmail(summary)`（由 Scheduler 觸發）
- 🔵 `SendNewsDigestEmail(digest)`（由 NewsPipeline 完成後觸發）
- 🔵 `SendAlertEmail(error)`（由任何例外路徑觸發）

---

## 6. Policies / Reactions（政策與反應規則）

> 格式：當 {Domain Event} 發生 → 執行 {Command / 動作}

### BC-1 模式管理
- 🔴 當 `ModeSwitchRequested`（SIM → LIVE）→ 顯示二次確認對話框並驗證 Shioaji 連線
- 🔴 當 `LiveConfirmationStringEntered` 且字串 == "LIVE" 且 `ShioajiConnectionVerified` → 執行 `ActivateLiveMode`
- 🔴 當 `LiveModeActivated` → 啟動 24h 計時器、發出 ModeStatePersisted
- 🔴 當 24h 計時器到期且仍處 LIVE → 執行 `RevertToSimulationMode`
- 🔴 當 `ShioajiConnectionFailed` → 維持 SIM、UI 顯示錯誤、寫入 app_log

### BC-2 市場資料
- 🔴 當 `ShioajiKbarsFailed`（台股）→ 自動觸發 `FetchKbars` via yfinance（fallback）
- 🔴 當 `KbarsValidationFailed` → 寫入 app_log、`SendAlertEmail`（NFR-REL-01）
- 🔴 當 fetch 失敗 → 指數退避重試最多 3 次

### BC-3 策略與回測
- 🔴 當 Windows Task Scheduler 觸發 14:00 / 05:30 → `RunStrategy`
- 🔴 當 `SignalGenerated` → 自動觸發 `EvaluateSignalRisk`
- 🔴 當 `StrategyExecutionCompleted` → 自動觸發 `SendDailySummaryEmail`、`SnapshotDailyPnL`

### BC-4 交易執行與風控
- 🔴 當 `SignalRiskApproved` 且市場 == 台股 → 觸發 `PlaceOrder` via ShioajiBroker (LIVE) 或 SimulatedBroker (SIM)
- 🔴 當 `SignalRiskApproved` 且市場 == 美股 且 LIVE → 觸發 `DispatchUsSignalEmail` via EmailBroker
- 🔴 當 `SignalRiskApproved` 且市場 == 美股 且 SIM → 觸發 `SimulateFill` via SimulatedBroker
- 🔴 當 `SignalRiskRejected` → 寫入 app_log，不下單
- 🔴 當 `DailyLossLimitTriggered` → 攔截當日所有新進場訊號（已有部位仍可正常停損）
- 🔴 當 `OrderPlaced`（台股）→ 自動 `AttachStopLossOrder`
- 🔴 當 `OrderFailed` 且 mode == LIVE → 自動 `SendAlertEmail`
- 🔴 當 `OrderFilled` → 更新 Position、寫入 orders 表

### BC-5 新聞情緒分析
- 🔴 當 `NewsCollectionTriggered` → 依設定來源並行抓取
- 🔴 當 `ArticleCollected` 且去重通過 → 觸發 `RequestLlmAnalysis`
- 🔴 當 `ArticleAnalyzed` → 觸發 `MapTickers`
- 🔴 當 `TickerMapped` 且 confidence ≥ 0.7 → 進入候選排序
- 🔴 當 `TickerConfidenceLow`（< 0.7）→ 標示「未確認」，不進入排序
- 🔴 當所有 article 分析完成 → 觸發 `RankCandidates` → 產出 Top N → 觸發 `SendNewsDigestEmail`
- 🔴 當 candidate 來自 ≥ 3 個獨立來源 → 觸發 `StrongSignalMarked`
- 🔴 每次 LLM 呼叫完成 → 觸發 `LlmCostRecorded`、`CheckLlmBudget`
- 🔴 當 `LlmBudgetExceeded` → 觸發 `AutoStopLlmAnalysis` + `SendAlertEmail` + 寫入 app_log
- 🔴 當 ticker 或 source 在黑名單 → 抓取 / 分析階段直接過濾
- 🔴 當 `FakeNewsReported` → 觸發 `SourceCredibilityAdjusted`（自動下調來源信用度）
- 🔴 當 `WatchlistItemPromoted` → 產生 Signal → 進入 BC-4 風控與下單流程
- 🔴 每日定期 → 觸發 `ExpireWatchlistItem`（> 7 天項目）

### BC-6 圖表與技術分析
- 🔴 當 `OpenChart` → 自動 `FetchKbars`（若快取已有則直接讀取）、`ComputeIndicators`、`DetectPatterns`
- 🔴 當 `PatternDetected` → 標示於 K 線；UI 顯示「非交易訊號」警語（FR-CH-26）
- ⚠ 注意：形態偵測 **不會** 自動觸發任何 BC-4 的命令（FR-CH-26 嚴格規定）
- 🔴（P2 進階）當 FR-CH-27 啟用 → `PatternDetected` 可作為 Strategy Signal 的條件過濾器

### BC-7 通知
- 🔴 當任何 BC 拋出 Unhandled Exception → 觸發 `SendAlertEmail`（FR-NT-05）
- 🔴 當 Email 主旨組裝時 → 依當前 `ModeState` 加 `[SIM]` / `[LIVE]` 前綴（FR-MM-06）

---

## 7. Read Models（讀取模型 / 投影）

對應 UI mockup 中各分頁顯示的資料聚合視圖：

| Read Model | 提供給哪個畫面 | 來源資料 |
| --- | --- | --- |
| `DashboardKpiView` | 主控台 KPI 卡片：帳戶總值、今日損益、未實現損益、勝率 | `daily_pnl` + `positions` + `orders` |
| `CurrentPositionsView` | 主控台「當前持倉」表 | `positions` join `kbars_cache` 取現價 |
| `TodaySignalsView` | 主控台「今日訊號」表 | `signals` (today) join `orders` |
| `EquityCurveView` | 主控台、回測「績效曲線」圖 | `daily_pnl` 序列 |
| `NextScheduleView` | 主控台「下次自動執行」 | APScheduler 內部狀態 |
| `SystemStatusView` | 主控台「系統狀態」：Shioaji / SMTP / yfinance / CA 憑證到期 | 即時健檢結果 |
| `NewsFeedView` | 新聞情緒「今日新聞」流 | `news_articles` join `news_analysis` |
| `WatchlistView` | 新聞情緒「候選清單」 | `watchlist` (status=pending) |
| `LlmCostMeterView` | 新聞情緒「今日成本」 | `llm_cost_daily` |
| `ChartKbarsView` | 圖表「K 線 + MA / 副圖」 | `kbars_cache` + `IndicatorEngine` 計算結果 |
| `PatternListView` | 圖表右側「近期形態提示」 | `PatternDetector` 計算結果 |
| `IndicatorPanelView` | 圖表右側「當前指標」表（RSI / MACD / 布林位置 / 量比） | `IndicatorEngine` 即時計算 |
| `SparklineView` | 持倉 / Watchlist 列尾 30 日縮圖 | `kbars_cache` 末 30 日 |
| `BacktestMetricsView` | 回測「績效指標」KPI | `BacktestEngine` 輸出 |
| `SignalLogView` | 訊號日誌頁 | `signals` + `orders` + `app_log` |
| `SettingsView` | 設定頁（API、SMTP、風控、模擬參數） | config.json（敏感欄位顯示 ****）|

---

## 8. User Journey 時間軸（事件流）

### 8.1 每日自動策略執行流（台股：14:00 / 美股：05:30 台北時間）

```
[Actor] Windows Task Scheduler
   │
   ▼
🔵 RunStrategy(mode=current)
   │
   ▼
🟠 StrategyExecutionTriggered
   │
   ├──▶ 🔵 FetchKbars (each symbol in universe)
   │       │
   │       ├──▶ 🟠 KbarsFetched / 🟠 ShioajiKbarsFailed
   │       │       └──🔴 fallback to yfinance → 🟠 YfinanceFallbackUsed
   │       └──▶ 🟠 KbarsCached
   │
   ▼
   [Strategy 計算] (Dual Momentum)
   │
   ▼
🟠 SignalGenerated (× N 檔)
   │
   ▼
🔵 EvaluateSignalRisk(signal) ── for each
   │
   ├──▶ 🟠 SignalRiskApproved
   │       │
   │       ├── 台股 → 🔵 PlaceOrder (Shioaji or Simulated)
   │       │           ├──▶ 🟠 OrderPlaced
   │       │           ├──▶ 🟠 StopLossOrderAttached (台股 only)
   │       │           └──▶ 🟠 OrderFilled / 🟠 OrderFailed
   │       │                   └─ Failed: 🔴 → 🔵 SendAlertEmail (LIVE)
   │       │
   │       └── 美股 LIVE → 🔵 DispatchUsSignalEmail
   │                       └──▶ 🟠 UsSignalEmailDispatched + 🟠 EmailSent
   │            美股 SIM  → 🔵 SimulateFill → 🟠 OrderFilled (假設成交)
   │
   └──▶ 🟠 SignalRiskRejected → 寫入 app_log（不下單）
            └─ 若 🟠 DailyLossLimitTriggered → 攔截所有新進場
   │
   ▼
🟠 PositionOpened / PositionClosed
   │
   ▼
🔵 SnapshotDailyPnL
   │
   ▼
🟠 DailyPnLSnapshotted
   │
   ▼
🔵 SendDailySummaryEmail
   │
   ▼
🟠 DailySummaryEmailSent (標題含 [SIM]/[LIVE])
   │
   ▼
🟠 StrategyExecutionCompleted
```

### 8.2 模式切換流（SIM → LIVE）

```
[Actor] 使用者
   │
   ▼ 點擊頂欄 [模擬模式] 按鈕
🔵 RequestModeSwitch(target=LIVE)
   │
   ▼
🟠 ModeSwitchRequested
   │
   ▼ 系統並行：(a) 顯示警告對話框  (b) 預先檢測
🔵 VerifyShioajiConnection
   │
   ├──▶ 🟠 ShioajiConnectionVerified
   │       │
   │       ▼ UI 對話框等待輸入
   │   [Actor] 使用者輸入 "LIVE"
   │       │
   │       ▼
   │   🔵 ConfirmLiveSwitch(confirmation="LIVE")
   │       │
   │       ▼
   │   🟠 LiveConfirmationStringEntered
   │       │
   │       ▼ 驗證字串完全相符
   │   🟠 LiveModeActivated（UI 變紅、模式 badge 閃爍）
   │       │
   │       ▼
   │   🔴 啟動 24h 計時器
   │       │
   │       └─（24h 後）→ 🔵 RevertToSimulationMode → 🟠 SimulationModeRestored
   │
   └──▶ 🟠 ShioajiConnectionFailed
           │
           ▼
       UI 顯示錯誤 + 維持 SIM
           │
           ▼
       🔵 SendAlertEmail（可選）
```

> 反向（LIVE → SIM）：無需確認，直接 `SimulationModeActivated`，UI 變綠。

### 8.3 新聞分析流（每日 06:00 / 21:30）

```
[Actor] APScheduler (06:00 或 21:30)
   │
   ▼
🔵 TriggerNewsCollection
   │
   ▼
🟠 NewsCollectionTriggered
   │
   ▼ 對每個啟用來源並行
🔵 CollectArticleFromSource (RSS / Reddit / EDGAR / yfinance news)
   │
   ├──▶ 🟠 ArticleCollected
   │       │
   │       ▼
   │   🔵 DeduplicateArticle (URL hash + 標題相似度 ≥ 0.85)
   │       │
   │       ├──▶ 🟠 ArticleStored (新文章)
   │       │
   │       └──▶ 🟠 ArticleDuplicated → 丟棄
   │
   └──▶ 🟠 ArticleCollectionFailed (3 次重試後)
            └─ 寫入 app_log
   │
   ▼ 對每篇 ArticleStored
🔵 CheckLlmBudget
   │
   ├── 預算內 → 🔵 RequestLlmAnalysis (Claude API)
   │              │
   │              ├──▶ 🟠 ArticleAnalyzed
   │              │       │ → 結構化 JSON {tickers, sentiment, catalysts, impact, summary, lang}
   │              │       ▼
   │              │   🟠 LlmCostRecorded → 更新 llm_cost_daily
   │              │       │
   │              │       ▼
   │              │   🔵 MapTickers (yfinance lookup + 內建表)
   │              │       │
   │              │       ├──▶ 🟠 TickerMapped (confidence ≥ 0.7)
   │              │       └──▶ 🟠 TickerConfidenceLow (< 0.7) → 標示「未確認」
   │              │
   │              └──▶ 🟠 AnalysisFailed (≤ 2 次重試)
   │
   └── 超出預算 → 🟠 LlmBudgetExceeded
                   │
                   ▼
               🟠 LlmAnalysisAutoStopped
                   │
                   ├──▶ 🔵 SendAlertEmail
                   └──▶ 寫入 app_log
   │
   ▼ 所有分析完成
🔵 RankCandidates
   │
   ▼
   score = impact × source_credibility × recency × multi_source_bonus
   │
   ├──▶ 🟠 CandidateRanked
   │       │
   │       └─ 若 sources ≥ 3 → 🟠 StrongSignalMarked
   │
   ▼ Top N (預設 10)
🔵 SendNewsDigestEmail
   │
   ▼
🟠 NewsDigestEmailSent
   標題：「[SIM] 新聞情緒摘要 - 2026-05-23 - 5 強訊號 / 12 候選 / $0.18」
```

### 8.4 Watchlist 兩段核可 → 訊號轉換流

```
[Actor] 使用者（收到 Digest Email 後進入「新聞情緒」分頁）
   │
   ▼ 第一段核可（候選清單 → Watchlist）
🔵 AddToWatchlist(candidate_id)
   │
   ▼
🟠 WatchlistItemAdded（status=pending, expires_at=now+7d）
   │
   ▼ ─── 可能停留多日 ───
   │
   ▼ 第二段核可（Watchlist → Signal）
[Actor] 使用者點擊「→ 轉為交易訊號」
   │
   ▼
🔵 PromoteWatchlistItem(item_id)
   │
   ▼
🟠 WatchlistItemPromoted（status=promoted）
   │
   ▼ 進入 BC-4 風控流程
🔵 EvaluateSignalRisk(signal)
   │
   ├──▶ 🟠 SignalRiskApproved → 進入下單流程（同 8.1）
   │
   └──▶ 🟠 SignalRiskRejected → 寫入 app_log，標記原因（如「總持倉已 80%」）

[平行情境]
- 使用者點「忽略」→ 🔵 DismissWatchlistItem → 🟠 WatchlistItemDismissed
- 使用者點「假新聞」→ 🔵 ReportFakeNews → 🟠 SourceCredibilityAdjusted
- 7 天到期 → 🔵 ExpireWatchlistItem → 🟠 WatchlistItemExpired (status=expired)
```

### 8.5 模擬 → 實盤訊號轉換流（同一訊號的兩種終態）

> 此流程說明：同一個 `Signal` 物件在不同 `ModeState` 下會經過完全不同的 Broker 實作，但前段（策略生成、風控）邏輯一致。

```
                       🟠 SignalGenerated
                              │
                              ▼
                       🔵 EvaluateSignalRisk
                              │
                              ▼
                       🟠 SignalRiskApproved
                              │
                       讀取 ModeState
                              │
              ┌───────────────┴───────────────┐
              │                               │
        mode = SIMULATION                mode = LIVE
              │                               │
              ▼                               ▼
      ┌─ 台股 ─ SimulatedBroker        ┌─ 台股 ─ ShioajiBroker
      │   .simulate_fill()             │   .place_order() + AttachStopLoss
      │   依日線收盤價 / 隔日開盤價       │   ├── 🟠 OrderPlaced
      │   扣除假設手續費 + 滑價           │   ├── 🟠 StopLossOrderAttached
      │   🟠 OrderFilled (mode=SIM)     │   └── 🟠 OrderFilled / OrderFailed
      │                                │       └─ Failed → SendAlertEmail
      │                                │
      └─ 美股 ─ SimulatedBroker        └─ 美股 ─ EmailBroker
          .simulate_fill()                .send_signal()
          🟠 OrderFilled (mode=SIM)       🟠 UsSignalEmailDispatched
                                          🟠 EmailSent
                                          （由使用者手動於永豐 APP 下單）
              │                               │
              └───────────────┬───────────────┘
                              ▼
                         寫入 `orders` 表
                         （mode 欄位區分 SIM / LIVE）
                              │
                              ▼
                       🟠 PositionOpened / PositionClosed
                              │
                              ▼
                          更新 `positions`
```

> 關鍵設計：`mode` 欄位寫入 `orders`、`accounts`、Email 標題；確保 SIM / LIVE 帳本完全隔離（FR-MM-07）。

---

## 9. 跨 BC 互動摘要

| 來源 BC | 事件 | 目標 BC | 觸發的命令 |
| --- | --- | --- | --- |
| BC-3 | SignalGenerated | BC-4 | EvaluateSignalRisk |
| BC-4 | SignalRiskApproved | BC-4 (內部 Broker) | PlaceOrder / DispatchUsSignalEmail / SimulateFill |
| BC-4 | OrderFailed | BC-7 | SendAlertEmail |
| BC-4 | StrategyExecutionCompleted | BC-7 | SendDailySummaryEmail |
| BC-5 | WatchlistItemPromoted | BC-4 | EvaluateSignalRisk (新訊號) |
| BC-5 | NewsDigestRanked | BC-7 | SendNewsDigestEmail |
| BC-5 | LlmBudgetExceeded | BC-7 | SendAlertEmail |
| BC-1 | LiveModeActivated | BC-4 | (切換 Broker 實作) |
| BC-1 | LiveModeActivated | BC-7 | (Email 標題改 [LIVE]) |
| BC-2 | KbarsValidationFailed | BC-7 | SendAlertEmail |
| BC-6 | PatternDetected | （無）| **明示斷開：不觸發 BC-4 任何 command** |

---

## 10. Hotspots（需求文件中未明確的灰色地帶，留待 consistency_review 與 requirements_review 處理）

事件風暴中發現的「需要釐清的疑問」，已轉至：
- `pm/consistency_review.md`：MD 與 HTML 不一致之處
- `pm/requirements_review.md`：模糊或缺漏的業務規則
