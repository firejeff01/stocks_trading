# Changelog

依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/) 與 SemVer．

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
