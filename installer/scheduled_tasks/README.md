# Windows Task Scheduler 範本

定時跑 `stocks-trading-cli`：每日交易例行 (`daily-routine`) 與新聞情緒分析 (`news`)。

| 檔案 | 觸發 | 動作 |
| --- | --- | --- |
| `tw_market_close.xml` | 週一~五 14:00 (台北) | `daily-routine --skip-if-done` + 寄摘要 |
| `us_market_close.xml` | 週二~六 05:30 (台北) | `daily-routine --skip-if-done` + 寄摘要 |
| `news_daily.xml` | 每天 06:30 (台北) | 跑新聞情緒分析 (`news --tickers ...`) + 寄 digest |

> **標的來源**：`daily-routine` 不再於 XML 寫死 `--tickers`，改讀設定頁
> 「每日標的」(`config.json` 的 `daily.tickers`，預設美股科技股)。會依 ticker
> 形狀自動分流（4 碼純數字→台股、其餘→美股），所以一個 task 就同時涵蓋兩個市場。
>
> **`--skip-if-done`**：若該帳本今天已有快照就略過，不重複產生訊號。配合
> StartWhenAvailable（關機/睡眠錯過時開機補跑）與「登入時」觸發，可達到
> 「每天只真正跑一次、但盡量不漏跑」。GUI 主控台的「立即重跑今日」也是同一套邏輯。
>
> `news` 會抓這些個股的 yfinance 新聞 + CNBC RSS，用 `claude -p` (你的 Max
> 訂閱) 分析；**會消耗 Max 額度**（每篇約 $0.06），受設定頁「每日分析上限」把關。

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
| `<Arguments>` | 子命令形式，預設 `daily-routine --skip-if-done`（標的讀 `config.daily.tickers`）；要先觀察可加 `--dry-run` |
| `<StartBoundary>` | 第一次觸發時間（之後每週重複）；日期不影響，只看時間 |

## 3. 匯入

開啟「工作排程器」(`taskschd.msc`) → 匯入工作 → 選 XML；或用指令列：

```cmd
schtasks /create /tn "StocksTrading-TW" /xml installer\scheduled_tasks\tw_market_close.xml /f
schtasks /create /tn "StocksTrading-US" /xml installer\scheduled_tasks\us_market_close.xml /f
schtasks /create /tn "StocksTrading-News" /xml installer\scheduled_tasks\news_daily.xml /f
```

匯入後可右鍵「執行」手動觸發一次驗證。

## 4. 正式啟用

預設 `<Arguments>` 已是 `daily-routine --skip-if-done`（會真正寫入並寄日報）。
若想先觀察幾次，可暫時加 `--dry-run`（不寫 DB、不寄信），確認無誤後再拿掉。

## 5. Email 設定

要寄日報必須先在 GUI「設定」分頁填好 SMTP（Gmail App Password）。
排程跑的時候會讀同一份 `%LOCALAPPDATA%\StocksTrading\config.json`。

## 排程時間建議

| 市場 | 收盤 | 建議排程 (台灣時區) |
| --- | --- | --- |
| 台股 | 13:30 | 14:00（收盤後 + 餘裕） |
| 美股 | 04:00 隔日（冬令） | 05:30 隔日 |
