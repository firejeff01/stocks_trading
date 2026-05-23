# StocksTrading Packaging

## 用 Windows Task Scheduler 自動每天跑 daily-routine

### 1. 確認 CLI 已安裝
裝完套件後應該有：
```powershell
where.exe stocks-trading-cli
# → C:\Users\<你>\AppData\Local\Programs\Python\Python311\Scripts\stocks-trading-cli.exe
# (或 venv / Program Files 路徑，視你的安裝方式)
```

先手動試一次確認可跑：
```powershell
stocks-trading-cli daily-routine --tickers SPY,QQQ --dry-run
```

### 2. 編輯範本
打開 `packaging/windows_scheduler_template.xml`，把這幾個欄位改成你的環境：

| 欄位 | 範例 | 說明 |
|------|------|------|
| `<Author>` | `Jeff` | 顯示用，隨意填 |
| `<UserId>` | `DESKTOP-XXX\Jeff` | 你的 Windows 帳號 (`whoami` 查) |
| `<Command>` | `C:\Path\to\stocks-trading-cli.exe` | 步驟 1 找到的絕對路徑 |
| `<WorkingDirectory>` | 同上目錄 | 可放放 logs |
| `<StartBoundary>` | `2026-06-01T18:00:00` | 第一次跑時間 (之後每日重複) |

### 3. 匯入
- 開啟「工作排程器」(`taskschd.msc`)
- 右側「動作」→「匯入工作...」→ 選編輯後的 XML
- 確認「觸發程序」分頁時間正確、「動作」分頁路徑無誤
- 按確定後可右鍵手動觸發一次驗證

### 4. 移除 `--dry-run`
範本預設 `--dry-run` 不寫 DB / 不寄信，先用這個跑幾次確認流程 OK 再拿掉．

### 5. Email 設定
要寄日報必須先在 GUI 的「設定」分頁填好 SMTP (Gmail App Password)．
排程器跑的時候會讀同一份 `%LOCALAPPDATA%\StocksTrading\config.json`．

## 排程時間建議

| 市場 | 收盤 | 建議排程時間 (台灣時區) |
|------|------|------------------------|
| 台股 | 13:30 | 18:00 (收盤後 + 安全餘裕) |
| 美股 | 04:00 隔日 (台灣冬令) | 06:00 隔日 |

混合策略：跑兩個排程任務，一個 18:00 跑台股、一個 06:00 跑美股．
