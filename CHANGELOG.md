# Changelog

依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/) 與 SemVer．

## [Unreleased]

### 新增 (Added)
- K 線圖週期切換：日／週／月／季／年 K
  - `analytics.aggregator.aggregate_to_timeframe()` 純函式 + `Timeframe` enum
  - ChartPage 工具列新增「週期」下拉，切換後即時重繪不重新抓資料
  - 蠟燭 / 量柱 / MACD 柱寬隨週期自動放大 (週=7d、月=30d、季=91d、年=365d)
  - 形態偵測仍以原始日線執行，避免聚合後樣本不足

### 強化 (Enhanced)
- 切換股票代號時 K 線圖自動置中：`KLineChart` 及 Volume/RSI/MACD 副圖
  每次 `_redraw` 呼叫 `enableAutoRange()`，使新標的的可視範圍即時 fit
- 軸刻度字體放大 (pointSize 11)、tooltip pointSize 13、legend pointSize 12
  改善小視窗閱讀性
- K 線蠟燭新增**圖內漂浮 OHLC 資訊框** (`pg.TextItem`)：
  滑鼠移到蠟燭上時直接在圖面上顯示日期/開高低收/量/漲跌幅，
  與上方 header tooltip 同步；錨點依游標位置自動切換 (左/右、上/下)
  避免被遮蔽；主題切換時底色 / 邊框同步重套

### 統計
- 486 tests 全綠 (+16 from v0.1.1)
- ruff / mypy strict 全綠

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
