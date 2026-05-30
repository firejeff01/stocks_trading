# StocksTrading Packaging

## Windows Task Scheduler 自動排程

排程範本與完整匯入說明已統一收斂到：

➡ **[`installer/scheduled_tasks/`](../installer/scheduled_tasks/README.md)**

該目錄提供台股 / 美股各一個範本（不同觸發時間），參數已是正確的子命令形式
（`daily-routine --tickers ... --dry-run`），並含逐步匯入、路徑確認、正式啟用說明。

> 早期此處曾有一份獨立的 `windows_scheduler_template.xml`，為避免與
> `installer/scheduled_tasks/` 重複 / 不一致已移除，請改用上面連結的範本。
