# Windows Task Scheduler 範本

定時跑 `stocks-trading-cli`：每日交易例行 (`daily-routine`) 與新聞情緒分析 (`news`)。

| 檔案 | 觸發 | 動作 |
| --- | --- | --- |
| `tw_market_close.xml` | 週一~五 14:00 (台北) | 跑台股策略 (`daily-routine --tickers 0050`) + 寄摘要 |
| `us_market_close.xml` | 週二~六 05:30 (台北) | 跑美股策略 (`daily-routine --tickers SPY,QQQ,IWM`) + 寄摘要 |
| `news_daily.xml` | 每天 06:30 (台北) | 跑新聞情緒分析 (`news --tickers ...`) + 寄 digest |

> `daily-routine` 會依 ticker 形狀自動分流（4 碼純數字→台股、其餘→美股），
> 所以台股範本放台股代號、美股範本放美股代號即可。
>
> `news` 會抓這些個股的 yfinance 新聞 + CNBC RSS，用 `claude -p` (你的 Max
> 訂閱) 分析；**會消耗 Max 額度**（每篇約 $0.06），預設帶 `--dry-run`
> 先觀察，且受設定頁「每日分析上限」把關。

## 1. 先手動確認 CLI 可跑

MSI 安裝後（exe 名稱為 `StocksTrading-cli.exe`），或從原始碼安裝後
（`stocks-trading-cli`），先手動試一次：

```powershell
where.exe StocksTrading-cli      # 確認實際安裝路徑
StocksTrading-cli daily-routine --tickers SPY,QQQ --dry-run
```

`--dry-run` 不寫 DB、不寄信，只印計算結果，適合先驗證流程。

## 2. 確認 / 調整範本

打開對應 XML，視需要調整：

| 欄位 | 說明 |
| --- | --- |
| `<Command>` | CLI exe 絕對路徑；預設 `%LOCALAPPDATA%\Programs\StocksTrading\StocksTrading-cli.exe`，請用步驟 1 的 `where` 結果替換 |
| `<Arguments>` | 子命令形式 `daily-routine --tickers ... --strategy ... --dry-run` |
| `<StartBoundary>` | 第一次觸發時間（之後每週重複）；日期不影響，只看時間 |

## 3. 匯入

開啟「工作排程器」(`taskschd.msc`) → 匯入工作 → 選 XML；或用指令列：

```cmd
schtasks /create /tn "StocksTrading-TW" /xml installer\scheduled_tasks\tw_market_close.xml /f
schtasks /create /tn "StocksTrading-US" /xml installer\scheduled_tasks\us_market_close.xml /f
schtasks /create /tn "StocksTrading-News" /xml installer\scheduled_tasks\news_daily.xml /f
```

匯入後可右鍵「執行」手動觸發一次驗證。

## 4. 正式啟用（移除 `--dry-run`）

確認連續幾次 dry-run 都正常後，把 `<Arguments>` 裡的 `--dry-run` 拿掉，
排程就會真正寫入訊號並寄出日報。

## 5. Email 設定

要寄日報必須先在 GUI「設定」分頁填好 SMTP（Gmail App Password）。
排程跑的時候會讀同一份 `%LOCALAPPDATA%\StocksTrading\config.json`。

## 排程時間建議

| 市場 | 收盤 | 建議排程 (台灣時區) |
| --- | --- | --- |
| 台股 | 13:30 | 14:00（收盤後 + 餘裕） |
| 美股 | 04:00 隔日（冬令） | 05:30 隔日 |
