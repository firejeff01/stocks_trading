# StocksTrading

個人自動化股票交易系統 — 台股自動下單 (永豐 Shioaji)、美股訊號通知 (半自動)。

## 文件結構

- `pm/` — 需求文件（v0.3 凍結）
- `sa/` — 系統分析與架構設計
- `src/stocks_trading/` — 主程式碼
- `tests/` — pytest 測試套件
- `docs/` — ADR 與開發紀錄（後續加入）

## 開發環境

- Python 3.11+
- Windows 11
- venv：`py -3.11 -m venv .venv`
- 安裝依賴（dev）：
  ```
  .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
  ```
- 跑測試：
  ```
  .\.venv\Scripts\python.exe -m pytest
  ```
- Lint / 型別檢查：
  ```
  .\.venv\Scripts\python.exe -m ruff check .
  .\.venv\Scripts\python.exe -m mypy
  ```

## 開發原則

- **TDD**：每個元件先寫失敗測試 (RED) → 最小實作 (GREEN) → 重構 (REFACTOR)
- **不破壞 main branch**：每個 milestone 一條 feature branch、完成 + 自測通過再 merge
- **每個 release tag 對應 MSI**：使用者可裝可跑可解除安裝

## 當前進度

- [x] PM 階段（需求文件 v0.3）
- [x] SA 階段（架構 / 元件 / 資料 / 技術選型）
- [x] **M0 完成**：domain layer / Broker 抽象 / SQLite migration + 初始 schema / DPAPI / ConfigStore
- [ ] M1：資料抓取 (yfinance + Shioaji)、Dual Momentum 策略、回測引擎 (T+1 規則)
- [ ] M2：SimulatedBroker、雙帳本損益
- [ ] M3：PySide6 GUI 五大分頁
- [ ] M4a：SMTP + 每日摘要
- [ ] M6a：cx_Freeze MSI 打包
- [ ] → v1.0 Paper Trading MVP release

## TDD 規範

每個元件都遵守 RED → GREEN → REFACTOR：
1. 先寫測試使其失敗 (RED)
2. 寫最小程式碼讓測試通過 (GREEN)
3. 在測試保持綠燈下重構 (REFACTOR)
4. ruff / mypy strict / pytest 全綠才 commit

## 模組結構

```
src/stocks_trading/
├── domain/           # 純 domain：Mode/Side/Money/Symbol/Account/Signal
├── brokers/          # Broker 抽象 + 三實作 (M2/M5)
├── storage/          # SQLite migration + schema
├── security/         # DPAPI 加密 wrapper
└── config/           # 兩層設定 (明文 + 加密)
```

## License

Proprietary — 個人使用。
