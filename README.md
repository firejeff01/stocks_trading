# StocksTrading

個人自動化股票交易系統 — 台股自動下單 (永豐 Shioaji)、美股訊號通知 (半自動)。

**目前最新版本：v1.1.0 (K 線圖表 + Paper Trading + 風控)** — 詳見 [CHANGELOG.md](CHANGELOG.md)。

## 安裝 (一般使用者)

下載最新 `.msi` 檔 (從 [Releases](https://github.com/firejeff01/stocks_trading/releases))，雙擊安裝。

第一次啟動會自動在 `%LOCALAPPDATA%\StocksTrading\` 建立 `app.db`，預設 SIM 模式。

> Windows SmartScreen 可能警告「不明來源」(MSI 未簽署)，按「**更多資訊** → **仍要執行**」即可。

## 從原始碼啟動 (開發者)

### 環境

- Python 3.11+
- Windows 11
- venv：`py -3.11 -m venv .venv`

### 安裝依賴

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 啟動 GUI

```powershell
.\.venv\Scripts\python.exe -m stocks_trading.app
```

### 跑測試

```powershell
.\.venv\Scripts\python.exe -m pytest
```

### Lint / 型別檢查

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

### 打包 MSI

```powershell
.\.venv\Scripts\python.exe installer\build_msi.py bdist_msi
```
產出 `installer\dist\stocks_trading-X.Y.Z-win64.msi`。

## 文件結構

- `pm/` — PM 階段需求文件 (v0.3 凍結)
- `sa/` — SA 階段系統分析與架構設計
- `src/stocks_trading/` — 主程式碼
- `tests/` — pytest 測試套件 (635 tests 全綠)
- `installer/` — cx_Freeze 打包腳本 + Task Scheduler 範本

## 開發原則

- **TDD**：每個元件先寫失敗測試 (RED) → 最小實作 (GREEN) → 重構 (REFACTOR)
- **不破壞 main branch**：commit 前必先過 ruff + mypy strict + pytest
- **每個 release tag 對應 MSI**

## 模組結構

```
src/stocks_trading/
├── app.py                          GUI 進入點
├── domain/                         不可變值物件 + entity (Mode/Money/Signal etc.)
├── brokers/                        Broker 抽象 + SimulatedBroker
├── storage/                        SQLite migration (升級前自動備份) + repositories
├── security/                       DPAPI 加密
├── config/                         兩層設定 (明文 + 加密)
├── data/                           yfinance / Shioaji 行情 + MarketDataRouter
├── analytics/                      指標 (MA/EMA/RSI/Bollinger/MACD) + 形態偵測 + 週期聚合
├── strategies/                     BaseStrategy + DualMomentum + MeanReversion
├── backtest/                       FillEngine + PortfolioState + BacktestEngine
├── paper_trading/                  PaperTradingService + 費用計算 + 帳本重置
├── risk/                           RiskGuard 風控閘門 (單筆 / 曝險 / 熔斷)
├── notify/                         SMTP + Email builders + NotificationService
├── concurrency/                    AsyncFetcher (UI 非同步抓資料)
├── cli/                            stocks-trading-cli (daily-routine / backtest / signal-list)
└── ui/                             PySide6 GUI 6 分頁 (含 K 線圖表) + widgets
```

## 里程碑進度

- [x] PM 階段 (v0.3 需求)
- [x] SA 階段 (架構 / 元件 / 資料 / 技術選型)
- [x] **M0** 地基 (domain / broker abstract / migration / DPAPI)
- [x] **M1** 資料層 + Dual Momentum + FillEngine
- [x] **M2** Repositories + SimulatedBroker + BacktestEngine
- [x] **M3** PySide6 GUI + 明暗主題
- [x] **M4a** SMTP + 每日摘要 + 系統告警
- [x] **M6a** cx_Freeze MSI 打包 + Task Scheduler 範本
- [x] **→ v1.0 Paper Trading MVP release** ←
- [x] **Paper Trading**：PaperTradingService + CLI daily-routine + SIM 帳本 + 績效曲線
- [x] **MeanReversion** 策略 (RSI 逆勢)
- [x] **M5.7 (v1.5)**：K 線圖表 + 技術指標 (MA/RSI/MACD/Bollinger) + 形態偵測
- [x] **RiskGuard 風控**：單檔上限 (預設 20% 資金) / 總曝險 / 單日熔斷
- [x] **→ v1.1.0 release** ←
- [ ] M5 (v1.5)：實盤模式、ShioajiBroker、Email Broker for US
- [ ] M5.5 (v2.0)：新聞情緒分析

## License

Proprietary — 個人使用。
