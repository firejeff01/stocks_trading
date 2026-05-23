# Windows Task Scheduler 範本

## 用途
這兩個 XML 範本用來在 Windows Task Scheduler 註冊自動排程，讓 StocksTrading 每日定時跑策略並寄出摘要 Email．

| 檔案 | 觸發 | 動作 |
| --- | --- | --- |
| `tw_market_close.xml` | 週一~五 14:00 (台北) | 跑台股策略 + 寄摘要 |
| `us_market_close.xml` | 週二~六 05:30 (台北) | 跑美股策略 + 寄摘要 |

## 匯入方式

開啟「Windows 工作排程器」(taskschd.msc)，匯入 → 選 XML 檔．

或用指令列：
```cmd
schtasks /create /tn "StocksTrading-TW" /xml installer\scheduled_tasks\tw_market_close.xml /f
schtasks /create /tn "StocksTrading-US" /xml installer\scheduled_tasks\us_market_close.xml /f
```

## ⚠ v1.0 重要限制

v1.0 的 `StocksTrading-cli.exe` **尚未實作 `--daily-routine` 參數**，僅作預留．
排程登記後執行會直接 exit (沒做任何事)．

完整的自動化每日策略執行 + email 摘要將在 **v1.5** 完成（M5 Shioaji broker
與 position repository 完成後）．

v1.0 期間建議：
- 手動開啟 GUI 每日操作
- 把排程登記起來但暫停 (Disabled)，等 v1.5 啟用

## 修改觸發時間

時間在 `<StartBoundary>2026-01-01T14:00:00</StartBoundary>` 處．
日期不影響，只看時間部分．要改 13:30 改成 `2026-01-01T13:30:00` 即可．
