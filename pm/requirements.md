# 自動化股票交易系統 — 需求文件

| 項目 | 內容 |
| --- | --- |
| 文件版本 | v0.3 (Draft) |
| 建立日期 | 2026-05-23 |
| 最後更新 | 2026-05-23 (落地 Q1/Q2/Q3 決策 + 分階段釋出) |
| 文件擁有者 | gamma.jeff.lin@gmail.com |
| 目標讀者 | 開發者本人（同時為使用者） |
| 狀態 | 規劃中（待確認後進入設計階段） |

---

## 1. 專案總覽

### 1.1 背景

開發者持有永豐金證券帳戶，具備程式開發能力但對量化交易策略仍在學習階段。希望透過自動化系統降低手動操作負擔、移除情緒影響，並透過模擬模式安全地學習策略表現後再以小額實盤驗證。

### 1.2 目標

1. 提供一套可在 Windows 上以 **MSI 安裝檔**部署的桌面應用程式。
2. 支援 **模擬模式 (Paper Trading)** 與 **實盤模式 (Live)** 兩種操作，使用者可透過明顯的開關切換。
3. 台股：透過永豐 Shioaji Python API 進行**全自動**訊號運算與下單。
4. 美股：透過程式運算訊號，以 **Email 通知**使用者，由使用者手動至永豐 APP 完成下單（半自動）。
5. 提供基本回測能力，讓使用者上線前先驗證策略。
6. 內建風險控管機制，避免單筆部位或單日損失超過上限。
7. 每日自動蒐集國外專業財經與科技新聞，透過 LLM 分析後產出「**選股候選清單 (Watchlist)**」並寄送 Email 摘要；候選需使用者人工核可才轉為交易訊號。

### 1.3 非目標 (Out of Scope, MVP 階段不做)

- 高頻 / 盤中即時交易（系統以日線收盤後決策為主）。
- 多使用者帳戶、權限管理。
- 雲端部署、Web 多端同步。
- 期貨、選擇權、加密貨幣等衍生品。
- 自行訓練 ML / 深度學習選股模型（外部 LLM API 分析新聞屬於範圍內）。
- 做空、保證金交易、融資融券。
- 新聞驅動的全自動下單（新聞模組僅輸出 Watchlist，下單動作需使用者人工核可）。

---

## 2. 利害關係人與使用者

| 角色 | 描述 | 主要關注 |
| --- | --- | --- |
| 開發者 / 使用者 | 唯一使用者，同時負責開發、維運、實際下單 | 系統穩定、訊號正確、不被誤觸成實盤 |
| 永豐金證券 (Shioaji) | 台股 API 服務提供者 | API 配額、合約簽署、CA 憑證使用合規 |
| Yahoo Finance / 其他資料源 | 美股、台股歷史與日線資料 | 資料正確性、抓取頻率不被封鎖 |
| Anthropic Claude API | 新聞 LLM 分析（情緒、實體萃取、影響評分） | API 成本控制、回應穩定 |
| 新聞來源 (RSS / NewsAPI / Reddit / SEC EDGAR) | 提供國外財經與科技新聞 | 來源可靠、避免假新聞 |
| SMTP 服務 (Gmail) | Email 通知傳遞通道 | 寄件成功率、認證安全 |

---

## 3. 使用者情境 (Use Cases)

### UC-01 首次安裝與設定
使用者下載 MSI 安裝檔，雙擊安裝後在「設定」頁輸入 Shioaji 帳密、CA 憑證路徑、Email 寄件設定，並選擇預設啟動模式為「模擬模式」。

### UC-02 每日收盤後執行策略（自動）
- **觸發**：Windows Task Scheduler 於每日台股收盤後 14:00、美股收盤後 05:30（台北時間）觸發。
- **流程**：抓取最新日線 → 計算策略訊號 → 風控檢查 → 若為實盤則下單（台股自動 / 美股寄信）→ 寫入交易日誌 → 寄送每日摘要 Email。

### UC-03 啟動 GUI 檢視持倉與訊號
使用者手動開啟桌面應用程式，於「主控台」檢視當日訊號、目前持倉、未實現損益、累計績效曲線。

### UC-04 切換模擬 / 實盤模式
使用者於頂欄按下「模式切換」按鈕，系統彈出**二次確認對話框**並要求重新輸入確認字串（例如「LIVE」）才允許切換到實盤；切換到模擬則無需確認。對話框需顯示「即將切換到 Y 帳本，目前 X 帳本有 N 筆部位將被凍結（可查詢不可下單）」。**SIM 與 LIVE 是雙帳本完全隔離**，切換 = 切換顯示與下單目標的帳本，非當前模式的資料不消失。

### UC-05 執行歷史回測
使用者於「回測」頁選擇策略、起訖日期、標的清單，按下執行後檢視績效曲線、Sharpe、最大回撤等指標。

### UC-06 接收 Email 通知
使用者於信箱收到：
- 美股訊號通知（即時，包含建議買賣標的、價格、數量、停損價）。
- 每日交易摘要（收盤後，包含當日成交、持倉、損益）。
- **每日新聞情緒摘要 (News Digest)**，包含 Top N 候選標的、新聞重點、買賣建議。
- 系統異常告警（API 連線失敗、Shioaji 登入失敗等）。

### UC-07 新聞分析與選股流程
1. 系統於每日 06:00 (台北、美股盤後) 與 21:30 (美股盤前) 自動抓取多源新聞。
2. 經 Claude API 分析後產出結構化資料（tickers、sentiment、catalyst、impact_score）。
3. 排序後選出 Top N 候選標的，寄出 Daily News Digest Email。
4. 使用者於 GUI「新聞情緒」頁瀏覽候選清單，可逐筆「加入 Watchlist」。
5. Watchlist 中的標的需使用者再次點擊「轉為交易訊號」，才會經過 RiskGuard 並送入下單流程（模擬或實盤）。
6. 兩段式核可確保新聞驅動的判斷不會在使用者沒注意時自動下單。

---

## 4. 功能需求 (Functional Requirements)

### 4.1 模式管理 (Mode Management)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-MM-01 | 系統需有全域「執行模式」狀態，僅有 `SIMULATION` 與 `LIVE` 兩值 | P0 |
| FR-MM-02 | 預設啟動模式為 `SIMULATION`，安裝完成後第一次啟動強制為模擬 | P0 |
| FR-MM-03 | 從 `SIMULATION` 切換到 `LIVE` 需二次確認（輸入字串 "LIVE"） | P0 |
| FR-MM-04 | UI 全程顯示當前模式色彩警示：模擬=綠色、實盤=紅色 | P0 |
| FR-MM-05 | 模式狀態需持久化（重啟程式後保留），但若距上次切換 > 24 小時則自動回到模擬模式 | P1 |
| FR-MM-06 | 所有寄出的 Email 標題需明確標示 `[SIM]` 或 `[LIVE]` | P0 |
| FR-MM-07 | 在模擬模式下，所有下單動作走「模擬 broker」介面，不得呼叫真實 Shioaji 下單 API | P0 |
| FR-MM-08 | **雙帳本完全隔離**：SIM 與 LIVE 各有獨立 `account_id`，部位 / 訊號 / Watchlist / 委託紀錄各自一套，切換模式 = 切換顯示哪本；非當前模式的帳本資料保留但凍結（可查詢、不可下單） | P0 |
| FR-MM-09 | 24h 自動回到 SIM 時：LIVE 帳本的部位 / 掛單 / 訊號**繼續存在不消失**；重新進入 LIVE 仍需二段確認，並彈出提示「您仍有 N 筆未平倉實盤部位」 | P0 |
| FR-MM-10 | 切換模式對話框需顯示「即將從 X 帳本切到 Y 帳本，X 帳本目前有 N 筆部位將被凍結（可查詢不可下單）」 | P0 |
| FR-MM-11 | 實盤帳本若仍有未平倉部位，禁止使用「重置帳本資料」功能 | P0 |

### 4.2 策略引擎 (Strategy Engine)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-SE-01 | 提供至少一支內建策略：**Dual Momentum (雙動能輪動)** | P0 |
| FR-SE-02 | 策略以可插拔架構設計，未來可加入新策略而不修改核心 | P1 |
| FR-SE-03 | 策略參數可於 UI 編輯（回看天數、再平衡頻率、標的清單） | P0 |
| FR-SE-04 | 策略需獨立輸出「訊號物件」（標的、方向、建議價、數量、停損價），不直接呼叫下單 | P0 |
| FR-SE-05 | 同一策略可同時運行於台股、美股（不同標的池） | P1 |

### 4.3 資料層 (Data Layer)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-DL-01 | 台股日線資料：優先使用 Shioaji `kbars`；失敗時退回 yfinance | P0 |
| FR-DL-02 | 美股日線資料：使用 yfinance（免費、夠用） | P0 |
| FR-DL-03 | 資料抓取後快取於本地 SQLite，避免重複抓取 | P0 |
| FR-DL-04 | 提供「強制更新」按鈕清除快取重抓 | P1 |
| FR-DL-05 | 每次抓取需驗證資料完整性（缺漏天數、價格 ≤ 0、極端跳空） | P1 |

### 4.4 執行層 (Execution Layer)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-EX-01 | 台股下單透過 Shioaji `place_order`，下單同時掛停損條件單 | P0 |
| FR-EX-02 | 美股下單：發送結構化 Email 至設定信箱，內容含完整下單指令（標的、數量、價格、停損） | P0 |
| FR-EX-03 | 模擬模式下，下單寫入「模擬交易表」並以 **T+1 日開盤價**成交（訊號於 T 日收盤產生 → T+1 開盤掛單），扣除假設手續費 + 滑價（預設 0.05%）；**禁止使用 T 日收盤價成交（look-ahead bias）**。回測引擎需遵循相同規則。 | P0 |
| FR-EX-04 | 所有下單動作（含模擬）需寫入交易日誌，欄位包含時間、模式、標的、方向、價量、結果 | P0 |
| FR-EX-05 | 實盤下單失敗（API 錯誤）需自動寄出告警 Email | P0 |
| FR-EX-06 | **跳空保護（選配，預設開啟）**：T+1 開盤跳空超過 ±5%（相對 T 日收盤價）時，模擬視為「未成交」並寫入訊號日誌，反映實盤可能不會追漲殺跌；門檻可於 UI 調整 | P1 |
| FR-EX-07 | 訊號狀態需區分 `PENDING_T+1_OPEN`、`FILLED`、`UNFILLED_GAP`、`REJECTED_RISK`、`MANUAL`（美股）、`FAILED`，於訊號日誌頁清楚標示 | P1 |

### 4.5 風險控管 (Risk Management)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-RM-01 | 單筆部位風險上限：預設 1%（停損距離 × 部位大小 ≤ 帳戶 1%） | P0 |
| FR-RM-02 | 總持倉部位上限：預設 80%（保留 20% 現金） | P0 |
| FR-RM-03 | 單日最大虧損上限：超過則停止當日所有新進場（已有部位仍可正常停損） | P0 |
| FR-RM-04 | 策略產生的訊號若違反風控規則，需被攔截並寫入日誌，不得下單 | P0 |
| FR-RM-05 | 風控參數可於 UI 調整，但實盤模式下調整需二次確認 | P1 |

### 4.6 通知系統 (Notification)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-NT-01 | 支援 SMTP（TLS）寄送 Email，使用者於設定頁輸入 host/port/account/password | P0 |
| FR-NT-02 | 密碼以 Windows DPAPI 或 Fernet 加密儲存，不得明碼寫入設定檔 | P0 |
| FR-NT-03 | 訊號通知 Email 為 HTML 格式，含表格、顏色標示、操作指引 | P0 |
| FR-NT-04 | 提供「寄送測試信」按鈕驗證設定正確 | P0 |
| FR-NT-05 | 系統異常（連線失敗、未捕捉例外）需自動寄出告警信 | P0 |
| FR-NT-06 | 每日收盤後寄一封摘要信（當日成交、未實現損益、明日訊號預告） | P1 |

### 4.7 回測 (Backtesting)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-BT-01 | 提供回測介面，使用者選策略、起訖日、初始資金、標的池後執行 | P0 |
| FR-BT-02 | 回測使用與實盤相同的策略物件，避免邏輯分歧 | P0 |
| FR-BT-03 | 輸出指標：年化報酬、累積報酬、最大回撤、Sharpe、勝率、交易次數 | P0 |
| FR-BT-04 | 輸出績效曲線圖（與基準指數比較） | P0 |
| FR-BT-05 | 可匯出回測結果為 CSV / PNG | P1 |

### 4.8 使用者介面 (UI)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-UI-01 | 桌面應用程式，使用 PySide6 (Qt) | P0 |
| FR-UI-02 | 主要分頁：**主控台、策略、回測、訊號日誌、設定** | P0 |
| FR-UI-03 | 頂欄固定顯示：當前模式、目前時間、台股 / 美股盤前盤中盤後狀態、最近一次資料同步時間 | P0 |
| FR-UI-04 | 所有金額顯示需可切換 TWD / USD（依市場別） | P1 |
| FR-UI-05 | 支援淺色 / 深色主題切換，於頂欄提供明顯的 toggle 按鈕 | P1 |
| FR-UI-06 | 應用程式關閉時最小化到系統匣（系統匣 icon 顯示當前模式色） | P1 |
| FR-UI-07 | 主題設定需持久化（重啟保留），預設依循 Windows 系統主題（系統明亮 → 明亮、系統深色 → 深色） | P1 |
| FR-UI-08 | 主題切換時所有頁面、圖表、Email 預覽即時切換不需重啟 | P1 |
| FR-UI-09 | 深色版下 K 線顏色維持市場慣例（綠/紅）但對比加強；圖表背景使用深灰非純黑 | P1 |
| FR-UI-10 | 模式色彩（模擬綠、實盤紅）在深色版下使用較飽和的色階以維持顯眼度 | P0 |

### 4.9 排程與背景作業 (Scheduling)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-SC-01 | 由 Windows Task Scheduler 觸發 CLI 模式執行（無 GUI 也能跑策略） | P0 |
| FR-SC-02 | GUI 開啟時，可在內部排程器看到「下次執行時間」 | P1 |
| FR-SC-03 | 排程任務執行的 log 可由 GUI 「訊號日誌」頁檢視 | P0 |

### 4.10 新聞情緒分析與選股建議 (News & Sentiment)

**目的：** 自動蒐集國外專業財經與科技新聞，透過 LLM 分析後產出「選股候選清單」，協助使用者捕捉技術指標看不到的基本面催化劑（產品發表、財報、併購、監管事件等）。

**安全設計原則：**
1. 永不自動下單（候選 → Watchlist → 訊號 需兩段人工核可）。
2. 多源交叉驗證（至少 3 個獨立來源提及才標示為強訊號）。
3. 成本上限可控（每日 LLM 預算上限，超過自動跳過）。
4. 黑名單機制（可永久排除特定 ticker 或來源）。

#### 4.10.1 資料抓取 (Collector)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-NS-01 | 每日於台北時間 06:00（美股盤後）與 21:30（美股盤前）兩次抓取新聞 | P0 |
| FR-NS-02 | 預設來源：yfinance news、CNBC RSS、Reuters RSS、Ars Technica RSS、TechCrunch RSS、The Verge RSS、Reddit JSON (r/stocks、r/investing、r/SecurityAnalysis)、SEC EDGAR 8-K filings | P0 |
| FR-NS-03 | 來源清單可於 UI 啟用 / 停用、新增自訂 RSS URL | P1 |
| FR-NS-04 | 抓取結果去重（依 URL hash + 標題相似度 ≥ 0.85） | P0 |
| FR-NS-05 | 原文 raw_text 儲存於 SQLite，方便事後重新分析 | P0 |
| FR-NS-06 | 抓取失敗（網路、429、5xx）自動重試 3 次（指數退避） | P0 |

#### 4.10.2 LLM 分析 (Analyzer)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-NS-07 | 使用 Anthropic Claude API（預設 `claude-haiku-4-5` 控制成本） | P0 |
| FR-NS-08 | 每篇新聞輸出結構化 JSON：`{tickers: [], sentiment: -1..1, catalysts: [], impact_score: 0..10, summary: string, lang: string}` | P0 |
| FR-NS-09 | 分析時使用 prompt caching（system prompt 部分快取），降低成本 | P1 |
| FR-NS-10 | 每日 LLM API 成本上限（預設 USD 0.3），於 UI 可調 | P0 |
| FR-NS-11 | 累計成本超過上限時自動停止分析、寄出告警信、寫入 app_log | P0 |
| FR-NS-12 | 失敗的 LLM 呼叫不重試超過 2 次，且記錄錯誤 | P0 |
| FR-NS-13 | API key 以 Windows DPAPI 加密儲存 | P0 |

#### 4.10.3 對應與排序 (Mapper & Ranker)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-NS-14 | TickerMapper 將文本中的公司名稱對應到實際 ticker（yfinance lookup + 內建對照表） | P0 |
| FR-NS-15 | 對應信心度低於 0.7 的 ticker 需標示「未確認」，不進入排序 | P1 |
| FR-NS-16 | Ranker 排序公式：`score = impact_score × source_credibility × recency_decay × multi_source_bonus` | P0 |
| FR-NS-17 | 同一標的若被 ≥ 3 個獨立來源提及，標示「強訊號」；單一來源僅標「弱訊號」 | P1 |
| FR-NS-18 | 來源信用度可於 UI 調整（預設：Reuters/SEC > yfinance > 主流科技媒體 > Reddit） | P2 |
| FR-NS-19 | 輸出 Top N 候選清單（預設 N=10），含買賣方向、理由摘要 | P0 |

#### 4.10.4 Watchlist 與核可流程 (Approval)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-NS-20 | GUI 新增「新聞情緒」分頁，可瀏覽新聞 feed、候選清單、watchlist | P0 |
| FR-NS-21 | 候選清單僅進入 Watchlist，**絕不**自動產生交易訊號 | P0 |
| FR-NS-22 | 使用者於 Watchlist 點擊「轉為訊號」後，訊號需通過 RiskGuard 才下單 | P0 |
| FR-NS-23 | 提供「黑名單」功能：永久排除指定 ticker 或來源 | P1 |
| FR-NS-24 | 提供「假新聞回報」按鈕，標記後該來源信用度自動下調 | P2 |
| FR-NS-25 | Watchlist 項目預設 7 天後自動過期移除 | P1 |

#### 4.10.5 通知與報告 (Digest)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-NS-26 | 每日抓取後寄送 Daily News Digest Email | P0 |
| FR-NS-27 | Digest 內容含：Top 10 候選標的、每則摘要、影響評分、來源清單、買賣建議方向 | P0 |
| FR-NS-28 | Digest 標題標示 [SIM] / [LIVE] 與當日累計 LLM 成本 | P1 |
| FR-NS-29 | 強訊號於 Digest 中以紅 / 綠醒目色標示 | P1 |

### 4.11 K 線圖表與技術分析 (Chart & Technical Analysis)

**目的：** 提供視覺化價量分析輔助決策；技術指標僅供參考，**不獨立觸發下單**（策略訊號才會下單）。

#### 4.11.1 圖表呈現

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-CH-01 | 新增「圖表」分頁，可選擇任一標的（持倉、Watchlist、自訂）顯示 K 線 | P0 |
| FR-CH-02 | 支援時間週期：日線 (預設)、週線、月線、60 分線 | P0 |
| FR-CH-03 | K 線顏色：台股紅漲綠跌、美股綠漲紅跌（依市場切換） | P0 |
| FR-CH-04 | 滑鼠移動顯示十字游標 + 對應 OHLC / 量 tooltip | P0 |
| FR-CH-05 | 支援縮放、平移、縮回原始視野 | P0 |
| FR-CH-06 | 持倉列表 / Watchlist 每列右方顯示近 30 日 sparkline 迷你 K 線縮圖 | P1 |
| FR-CH-07 | 回測頁的績效曲線下方加入「策略進出場點位於 K 線」視圖 | P1 |
| FR-CH-08 | 圖表可匯出 PNG | P2 |

#### 4.11.2 技術指標 (Indicators)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-CH-10 | 移動平均線：MA5 / MA10 / MA20 / MA60 / MA200，可獨立勾選顯示 | P0 |
| FR-CH-11 | 布林通道 (Bollinger Bands)：20 日 ± 2σ | P1 |
| FR-CH-12 | 成交量柱狀圖（下方副圖） | P0 |
| FR-CH-13 | RSI (14)：副圖，標示超買 70 / 超賣 30 水平線 | P1 |
| FR-CH-14 | MACD：DIF / DEA / 柱狀 | P1 |
| FR-CH-15 | 指標參數可於 UI 調整（如 RSI 期間、布林標準差倍數） | P2 |
| FR-CH-16 | 指標計算使用統一函式（避免回測與即時繪圖結果不一致） | P0 |

#### 4.11.3 自動形態 / 訊號提示 (Pattern Detection)

| 編號 | 需求 | 優先級 |
| --- | --- | --- |
| FR-CH-20 | 偵測黃金交叉（MA5 上穿 MA20）與死亡交叉（MA5 下穿 MA20） | P1 |
| FR-CH-21 | 偵測價格突破布林上軌 / 跌破下軌 | P1 |
| FR-CH-22 | 偵測 RSI 進入超買 (≥70) / 超賣 (≤30) 區 | P1 |
| FR-CH-23 | 偵測成交量爆量（當日量 > 20 日均量 × 2） | P1 |
| FR-CH-24 | 偵測到的形態於 K 線上以標籤標示（黃金叉 / 爆量等） | P1 |
| FR-CH-25 | 形態提示於「圖表」分頁右側列表呈現，提供近期觸發的形態時點 | P1 |
| FR-CH-26 | 提示**僅供參考**，不可直接觸發下單；UI 需明確標示「非交易訊號」 | P0 |
| FR-CH-27 | 可選擇將形態提示「加入策略訊號的條件過濾器」（進階用，僅讓策略訊號需同時滿足 K 線形態才下單） | P2 |

---

## 5. 非功能性需求 (Non-Functional Requirements)

### 5.1 安全性 (Security)
- **NFR-SEC-01**：Shioaji 帳密、CA 密碼、SMTP 密碼一律加密儲存（Windows DPAPI 優先）。
- **NFR-SEC-02**：設定檔不得記錄完整密碼（即便加密）於日誌中，僅顯示 `****`。
- **NFR-SEC-03**：MSI 安裝程式建議簽署（自簽 OK，避免 Windows SmartScreen 全面攔截）。
- **NFR-SEC-04**：應用程式更新時不得覆寫使用者的設定與資料庫。

### 5.2 可靠性 (Reliability)
- **NFR-REL-01**：策略執行需在交易日當天 100% 完成，失敗時必須寄出告警。
- **NFR-REL-02**：資料抓取需有重試機制（指數退避，最多 3 次）。
- **NFR-REL-03**：所有外部 API 呼叫設置 timeout，避免無限阻塞。

### 5.3 效能 (Performance)
- **NFR-PER-01**：策略運算（單日決策、< 30 個標的）需於 30 秒內完成。
- **NFR-PER-02**：GUI 操作回應時間 < 200ms（不卡頓）。
- **NFR-PER-03**：回測 10 年日線、5 個標的需於 60 秒內完成。

### 5.4 可維護性 (Maintainability)
- **NFR-MNT-01**：核心模組需有單元測試覆蓋率 ≥ 70%。
- **NFR-MNT-02**：所有 Shioaji 呼叫透過抽象介面，方便替換成模擬實作或日後切換券商。
- **NFR-MNT-03**：策略類別繼承自共同基底類別，新增策略 ≤ 200 行即可完成。

### 5.5 部署 (Deployment)
- **NFR-DEP-01**：交付為 MSI 安裝檔（使用 `cx_Freeze` 之 `bdist_msi` 產出）。
- **NFR-DEP-02**：安裝路徑預設 `C:\Program Files\StocksTrading\`，使用者資料於 `%LOCALAPPDATA%\StocksTrading\`。
- **NFR-DEP-03**：MSI 內含開始選單捷徑、桌面捷徑、解除安裝項目。
- **NFR-DEP-04**：MSI 升級需保留使用者資料（設定、資料庫、日誌）。

---

## 6. 系統架構概觀

```
┌────────────────────────────────────────────────────────────────┐
│                    PySide6 桌面 GUI                             │
│  主控台 │ 策略 │ 回測 │ 新聞情緒 │ 訊號日誌 │ 設定             │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────────────┐
│                     應用服務層 (Service)                        │
│  StrategyRunner │ ModeManager │ NotificationService             │
│  BacktestEngine │ RiskGuard   │ SchedulerService                │
│  NewsPipeline   │ CostGuard   │ WatchlistService                │
│  IndicatorEngine│ PatternDetector (K 線分析)                    │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────┬──────────┬┴────────┬──────────────┬─────────────┐
│ MarketData   │ NewsData │ Broker  │ LLM Client   │ Notifier    │
│ ┌─yfinance   │ ┌─RSS    │ ┌─Shio… │ ┌─Anthropic │ SmtpNotifier│
│ └─Shioaji    │ ├─NewsAPI│ ├─Simul…│ │ (Claude)  │             │
│   kbars      │ ├─Reddit │ └─Email │ └─PromptCach│ Storage:    │
│              │ └─EDGAR  │  (US)   │              │ SQLite      │
└──────────────┴──────────┴─────────┴──────────────┴─────────────┘
                           │
                    外部依賴 (External)
   Shioaji · yfinance · SMTP · Anthropic API · RSS feeds · EDGAR
```

**設計重點：**
- `Broker` 為抽象介面，`ShioajiBroker` / `SimulatedBroker` / `EmailBroker` 為三種實作。
- `ModeManager` 決定當前要把訊號送到哪個 Broker。
- `NewsPipeline` 為獨立模組：Collector → Analyzer → Mapper → Ranker → WatchlistService；產出**僅進 Watchlist**，不直接觸發訊號。
- `CostGuard` 監控 LLM API 累計成本，超過上限自動停止分析並告警。
- `IndicatorEngine` 統一計算 MA / Bollinger / RSI / MACD（回測與即時繪圖共用同一函式，避免分歧）。
- `PatternDetector` 偵測黃金 / 死亡交叉、爆量、布林突破等形態，輸出標記給 K 線圖；**不獨立觸發下單**。
- GUI、CLI、Scheduler 都呼叫同一套 Service 層，邏輯統一。

---

## 7. 資料模型

### 7.1 主要表格 (SQLite)

| 表格 | 欄位 | 說明 |
| --- | --- | --- |
| `accounts` | id, name, mode, broker, init_capital, created_at | 帳戶（模擬 / 實盤分開兩列） |
| `positions` | account_id, symbol, market, qty, avg_price, stop_loss, opened_at | 當前持倉 |
| `orders` | id, account_id, mode, symbol, side, qty, price, stop_loss, status, placed_at, filled_at | 委託紀錄 |
| `signals` | id, strategy, symbol, side, target_price, stop_loss, generated_at, sent | 策略產生的訊號 |
| `daily_pnl` | account_id, date, equity, realized_pnl, unrealized_pnl | 每日損益快照 |
| `kbars_cache` | symbol, date, open, high, low, close, volume | 日線快取 |
| `app_log` | ts, level, module, message | 系統日誌 |
| `news_articles` | id, source, url, url_hash, title, published_at, lang, raw_text, fetched_at | 原始新聞 |
| `news_analysis` | article_id, model, sentiment, impact_score, summary, catalysts_json, tickers_json, cost_usd, analyzed_at | LLM 分析結果 |
| `news_tickers` | article_id, ticker, confidence | 新聞 ↔ ticker 對應（多對多） |
| `watchlist` | id, ticker, market, side, source_articles_json, score, status, added_at, expires_at | 候選清單（status: pending/promoted/dismissed/expired）|
| `llm_cost_daily` | date, model, calls, input_tokens, output_tokens, cost_usd | 每日 LLM 成本累計 |
| `blacklist` | type (ticker/source), value, reason, added_at | 黑名單 |

### 7.2 設定檔
- `%LOCALAPPDATA%\StocksTrading\config.json`（明文設定，不含敏感資料）
- `%LOCALAPPDATA%\StocksTrading\secrets.dat`（DPAPI 加密，Shioaji / SMTP 密碼）

---

## 8. Email 通知格式

### 8.1 訊號通知（美股，盤後即時寄出）

| 欄位 | 內容 |
| --- | --- |
| 寄件人 | StocksTrading Bot `<your@gmail.com>` |
| 標題 | `[SIM] 美股訊號 - 2026-05-23 - 買進 QQQ` 或 `[LIVE] ...` |
| 內容 | HTML 表格，含標的、建議價、數量、停損、策略原因、執行截止時間 |

### 8.2 每日摘要

| 欄位 | 內容 |
| --- | --- |
| 標題 | `[SIM] 每日摘要 - 2026-05-23` |
| 內容 | 當日成交清單、持倉表、未實現損益、明日訊號預告、累計績效 |

### 8.3 系統告警

| 欄位 | 內容 |
| --- | --- |
| 標題 | `[ALERT] StocksTrading - <錯誤類型>` |
| 內容 | 錯誤訊息、發生時間、堆疊摘要、建議行動 |

### 8.4 每日新聞摘要 (Daily News Digest)

| 欄位 | 內容 |
| --- | --- |
| 標題 | `[SIM] 新聞情緒摘要 - 2026-05-23 - 5 強訊號 / 12 候選 / $0.18` |
| 內容 | Top 10 候選標的清單（含買賣方向、影響分、來源數、摘要連結）；強訊號醒目色標示；當日累計 LLM 成本 |
| 收件動作 | 使用者進 GUI「新聞情緒」頁逐筆審核，加入 Watchlist 後再轉訊號 |

---

## 9. 第一階段內建策略：Dual Momentum

### 9.1 邏輯
1. 每月最後一個交易日執行再平衡。
2. 計算標的池中每檔過去 12 個月（252 交易日）的累積報酬。
3. 篩選掉「絕對動能」< 美國 10 年期公債殖利率（或 0%）的標的 → 視為持有現金。
4. 從通過絕對動能的標的中選取「相對動能」前 N 名（預設 N=2）。
5. 平均加碼，下個月持有。

### 9.2 標的池（預設）
- **美股**：SPY、QQQ、IWM、EFA、VNQ、TLT、GLD（含安全資產候選）
- **台股**：0050、0056、00878、00919（ETF 為主，避免個股風險）

### 9.3 參數（可調整）
| 參數 | 預設值 |
| --- | --- |
| 回看期 (lookback_days) | 252 |
| 持倉檔數 (top_n) | 2 |
| 再平衡頻率 | 月線 |
| 絕對動能門檻 | 4% 年化 |
| 單筆風險 | 1% |

---

## 10. 操作流程 (主要 Flow)

### 10.1 模式切換 (Sim → Live)
```
使用者點擊頂欄 [模擬模式] 按鈕
  ↓
彈出對話框：「警告！即將切換到實盤模式」+ 風險提示
  ↓
要求輸入確認字串 "LIVE"
  ↓
驗證 Shioaji 連線、CA 憑證
  ↓
連線成功 → 切換完成，UI 變紅
連線失敗 → 維持模擬模式，顯示錯誤
```

### 10.2 每日策略執行
```
Scheduler 觸發 (cli mode)
  ↓
讀取當前模式 → 載入對應 Broker 實作
  ↓
資料層更新最新日線 (Shioaji + yfinance)
  ↓
StrategyRunner 執行所有啟用策略 → 產生 Signal[]
  ↓
RiskGuard 過濾違反風控的訊號
  ↓
For each signal:
  - 台股 → ShioajiBroker.place_order() 或 SimulatedBroker.place_order()
  - 美股 → EmailBroker.send_signal() （實盤）或 SimulatedBroker.simulate_fill() （模擬）
  ↓
寫入 orders / positions / signals 表
  ↓
NotificationService 寄送每日摘要
```

---

## 11. 風險與假設

### 11.1 風險
| 風險 | 影響 | 緩解 |
| --- | --- | --- |
| 切換到實盤造成意外下單 | 高 | 二次確認 + 顏色警示 + 模式自動 24h 重置 |
| Shioaji API 配額或穩定性問題 | 中 | 抓取失敗時退回 yfinance、異常告警 |
| 美股訊號 Email 漏看導致錯失執行 | 中 | 同時推送桌面通知（Toast）、每日摘要再次提醒 |
| MSI 安裝後缺少 Python runtime | 高 | cx_Freeze 內含 frozen Python，不依賴系統安裝 |
| 模擬模式績效與實盤偏離過大 | 中 | 模擬器內建滑價、手續費、稅費假設，定期校準 |
| **LLM 幻覺：分析輸出虛構的 ticker 或編造影響** | **高** | **TickerMapper 信心度門檻、要求 LLM 引用原文片段、絕不自動下單** |
| **新聞來源含假消息 / pump-and-dump 內容** | **高** | **多源交叉驗證（≥ 3 來源才標強訊號）、來源信用度權重、黑名單機制** |
| **LLM API 成本失控** | **中** | **每日預算上限、CostGuard 監控、超過上限自動停止並告警** |
| **新聞滯後：等系統分析完，價格已反映** | **中** | **每日盤前盤後兩次抓取、可疊加技術面過濾（不孤立使用新聞訊號）** |
| **使用者過度依賴 LLM 推薦，跳過自己思考** | **高** | **Watchlist 兩段核可流程、Email 提醒「不構成投資建議」、3 個月 paper 驗證後才實盤** |
| **雙帳本介面混淆**：使用者忘記當前看的是哪本 | 中 | UI 全程顯眼色彩標示（綠/紅）、頂欄持續顯示「目前帳本：SIM / LIVE」+ 部位數、切換對話框完整說明 |
| **v1.0 LIVE 模式 UI 灰階期間使用者誤以為壞掉** | 低 | LIVE 按鈕 hover 顯示「v1.5 開放，預計 YYYY-MM-DD」、README 明確說明 |
| **分階段釋出時資料庫 schema 升級風險** | 中 | v1.0 開始即內建 schema migration 機制（alembic 或自寫 version table），保留 schema 變更歷史 |

### 11.2 假設
- 使用者僅在 Windows 11 上執行，不需跨平台。
- 使用者具備 SMTP 帳號（Gmail App Password 或自架 SMTP）。
- 永豐 Shioaji API 短期內仍維持目前的免費政策。
- 使用者了解「過去績效不代表未來」，能接受策略可能虧損。

---

## 12. 里程碑與交付計畫 — 分階段釋出 (v1 → v1.5 → v2)

> 設計原則：單人開發最大風險是動力斷掉。早點有東西能跑、邊用邊修，比一條龍 15 週才上線好。每個階段交付**獨立可用**的 MSI 安裝檔。

### 12.1 v1.0 — Paper Trading MVP (累計 ~7 週)

**目標：** 使用者可安裝 MSI、跑 Dual Momentum 策略、做完整回測、收每日摘要 Email、純模擬累積績效。
**LIVE 模式：UI 隱藏 / 灰階提示「v1.5 開放」**。

| 里程碑 | 內容 | 預估 |
| --- | --- | --- |
| M0 | 專案骨架、Broker 抽象介面、SQLite schema、DPAPI 設定加密 | 1 週 |
| M1 | yfinance / Shioaji 行情抓取、Dual Momentum、backtrader 回測引擎 (T+1 規則) | 1 週 |
| M2 | SimulatedBroker、訊號 → T+1 開盤成交 → 雙帳本損益計算 | 1 週 |
| M3 | PySide6 GUI 主控台 / 策略 / 回測 / 設定 / 訊號日誌；深色主題 | 2 週 |
| M4a | SMTP 核心 + 每日摘要 Email + 系統告警 | 0.5 週 |
| M6a | cx_Freeze + MSI 打包基礎、開始選單捷徑、Task Scheduler 範本 | 1 週 |
| **v1.0 出貨** | 完整 paper trading 系統可裝可跑 | **~6.5 週** |
| v1.0 entry criteria | 模擬連續成功跑 5 個交易日無例外 | — |
| v1.0 exit criteria | paper trading 至少 1 個月，無資料遺失、無 critical bug | — |

### 12.2 v1.5 — 實盤 + K 線圖表 (+4 週、累計 ~11 週)

**目標：** 開啟實盤模式（雙帳本切換 + 二段確認）、台股自動下單、美股 Email 通知、加 K 線圖表輔助決策。
**前提：** v1.0 paper 跑滿 1 個月以上、Shioaji 簽署完成、CA 憑證安裝完畢。

| 里程碑 | 內容 | 預估 |
| --- | --- | --- |
| M5 | ShioajiBroker 實盤下單、台股條件停損單、EmailBroker (US)、RiskGuard 完整啟用 | 1.5 週 |
| M4b | 訊號通知 Email HTML 範本、美股下單檢核清單 | 0.5 週 |
| M5.7 | pyqtgraph K 線元件、IndicatorEngine (MA/Boll/RSI/MACD)、PatternDetector、圖表分頁、Dashboard sparkline、回測進出場視覺化 | 2 週 |
| 整合測試 | LIVE↔SIM 切換壓力測試、實盤前最終驗收 | 0.5 週 |
| **v1.5 出貨** | 實盤 + 圖表完整 | **~4.5 週** |
| v1.5 entry criteria | v1.0 paper 跑滿 1 個月、雙帳本切換無 bug、Shioaji 模擬下單通過 | — |
| v1.5 exit criteria | 台股小額實盤跑 2 週無異常、雙帳本資料正確隔離 | — |

### 12.3 v2.0 — 新聞情緒模組 (+3 週、累計 ~14 週)

**目標：** 加入 LLM 新聞分析，自動產出 Watchlist 候選，使用者人工核可後轉訊號。
**前提：** v1.5 實盤運作穩定 + Anthropic API key 申請完成。

| 里程碑 | 內容 | 預估 |
| --- | --- | --- |
| M5.5a | NewsCollector：RSS / Reddit / EDGAR 多源抓取 + 去重 | 0.5 週 |
| M5.5b | LLMAnalyzer：Claude (haiku-4-5) 整合、prompt caching、CostGuard 每日預算 | 0.7 週 |
| M5.5c | TickerMapper + Ranker：公司名對應 ticker、多源加權排序 | 0.5 週 |
| M5.5d | Watchlist GUI + 兩段核可流程、新聞情緒分頁 | 0.8 週 |
| M5.5e | Daily News Digest Email 範本、強訊號醒目色 | 0.3 週 |
| 整合測試 | LLM 端對端、成本控管驗證 | 0.2 週 |
| **v2.0 出貨** | 完整新聞情緒輔助 | **~3 週** |
| v2.0 entry criteria | v1.5 實盤穩定 ≥ 1 個月、Anthropic API 申請完成 | — |
| v2.0 exit criteria | Watchlist 推薦準確度 paper 跑 1 個月可接受、無成本失控 | — |

### 12.4 持續階段

| 階段 | 內容 |
| --- | --- |
| **M7 - Paper Trading 持續驗證** | v1.0 起即可開始；建議至少 3 個月 paper 才考慮實盤 |
| **M8 - 實盤小額** | v1.5 起；建議 1 萬 TWD 以下、單筆 ≤ 1% 風險、跑滿 1 個月後評估擴大 |
| **未來功能** | 中文新聞、付費 API 升級、選擇權、多策略並行（v3+） |

### 12.5 工時與 buffer

| 項目 | 工時 |
| --- | --- |
| v1.0 核心 | 6.5 週 |
| v1.5 核心 | 4.5 週 |
| v2.0 核心 | 3.0 週 |
| **核心合計** | **14 週** |
| 風險 buffer（單人開發、踩坑、需求改動）+ 30% | +4 週 |
| **建議總工時上限** | **~18 週** |

> 若某階段提前完成，盡可能擴大 paper trading 時間而非提早進下一階段（驗證越久越安全）。

---

## 13. 開放議題 (Open Questions)

### 13.0 已解決議題 (Resolved)

| 議題 | 決策 | 日期 |
| --- | --- | --- |
| 模式切換時殘留資料處理 | 雙帳本完全隔離（FR-MM-08~11） | 2026-05-23 |
| 模擬成交價基準 | T+1 日開盤價 + 跳空保護（FR-EX-03/06/07） | 2026-05-23 |
| 工時與交付策略 | 分階段釋出 v1.0 → v1.5 → v2.0（§12 重構） | 2026-05-23 |

### 13.1 未解決議題

1. **永豐 Shioaji 模擬下單**：永豐有提供官方 simulation account，是否在本系統中與「模擬模式」整合？目前規劃為兩種模擬並存（永豐自己的 simulation 與本系統自己的模擬資料庫），需後續評估。
2. **CA 憑證自動更新**：永豐 CA 憑證每年需更新一次，是否在 UI 內提供提醒？
3. **Email 雙向**：是否要解析回信（例如使用者回覆 "DONE" 表示已手動下單）以更新訊號狀態？MVP 不做。
4. **稅費假設**：模擬模式扣的台股交易稅、美股 ECN/SEC 費，是否要可調整？
5. **多策略並行**：是否允許多支策略同時跑於同一帳戶？資金如何分配？目前設計為 MVP 階段只支援單策略。
6. **新聞來源升級時機**：MVP 用免費 RSS / Reddit / EDGAR；何時升級到付費 API（NewsAPI、Polygon News、Benzinga）？建議 paper trading 3 個月後若免費來源覆蓋率不足再升級。
7. **LLM 模型升級**：預設使用 claude-haiku-4-5 控制成本，但 sonnet 對複雜分析（如解讀財報）更精準。是否要提供「重要新聞用 sonnet、其他用 haiku」的混合策略？
8. **新聞語言**：MVP 僅處理英文新聞；中文財經新聞（中央社、鉅亨、MoneyDJ）是否納入？需評估 Claude 對中文金融術語的準確度。
9. **持倉相關新聞優先**：是否對「當前已持倉的標的」相關新聞優先分析、優先寄出告警？(例如持有 QQQ 時，QQQ 相關財報新聞即時提示)

---

## 附錄 A：技術棧 (Tech Stack)

| 類別 | 套件 |
| --- | --- |
| 語言 | Python 3.11+ |
| GUI | PySide6 |
| 圖表 | **pyqtgraph (互動 K 線)**、**mplfinance (回測靜態圖匯出)**、matplotlib |
| 技術指標 | **TA-Lib 或 pandas-ta**（指標計算統一函式） |
| 永豐 API | shioaji |
| 美股資料 | yfinance |
| 回測 | backtrader |
| 資料處理 | pandas、numpy |
| 資料庫 | SQLite (via sqlalchemy) |
| 加密 | Windows DPAPI (pywin32) |
| 排程 | Windows Task Scheduler (外部) + apscheduler (內部) |
| 打包 | cx_Freeze (bdist_msi) |
| 測試 | pytest、pytest-qt |
| Lint | ruff、mypy |
| **LLM API** | **anthropic (Claude SDK)** |
| **新聞抓取** | **feedparser (RSS)、httpx、praw (Reddit)、sec-edgar-downloader** |
| **HTML 解析** | **trafilatura（萃取主文）、beautifulsoup4** |
| **相似度去重** | **rapidfuzz（標題比對）** |

## 附錄 B：目錄結構草案

```
stocks_trading/
├── pm/                       # 本資料夾，需求 / 設計文件
│   ├── requirements.md
│   └── requirements.html
├── src/stocks_trading/
│   ├── __init__.py
│   ├── app.py                # GUI 進入點
│   ├── cli.py                # CLI 進入點 (Scheduler 用)
│   ├── core/
│   │   ├── mode_manager.py
│   │   ├── risk_guard.py
│   │   └── scheduler.py
│   ├── brokers/
│   │   ├── base.py           # Broker 抽象
│   │   ├── shioaji_broker.py
│   │   ├── simulated_broker.py
│   │   └── email_broker.py
│   ├── data/
│   │   ├── yf_provider.py
│   │   └── shioaji_provider.py
│   ├── strategies/
│   │   ├── base.py
│   │   └── dual_momentum.py
│   ├── backtest/
│   │   └── engine.py
│   ├── analytics/
│   │   ├── indicators.py       # MA / Bollinger / RSI / MACD 計算
│   │   └── patterns.py         # 黃金交叉、爆量等形態偵測
│   ├── news/
│   │   ├── collector.py        # RSS / Reddit / EDGAR 抓取
│   │   ├── sources/            # 各來源 adapter
│   │   ├── analyzer.py         # Claude API 呼叫
│   │   ├── prompts.py          # System / user prompt 範本
│   │   ├── ticker_mapper.py
│   │   ├── ranker.py
│   │   ├── cost_guard.py
│   │   └── watchlist_service.py
│   ├── notify/
│   │   ├── smtp_notifier.py
│   │   └── templates/
│   ├── storage/
│   │   ├── models.py
│   │   └── repository.py
│   ├── security/
│   │   └── dpapi.py
│   └── ui/
│       ├── main_window.py
│       ├── pages/
│       │   ├── dashboard.py
│       │   ├── strategy.py
│       │   ├── backtest.py
│       │   ├── chart.py        # K 線 + 技術指標
│       │   ├── news.py         # 新聞情緒 + Watchlist
│       │   ├── signal_log.py
│       │   └── settings.py
│       ├── widgets/
│       │   ├── kline_chart.py  # pyqtgraph K 線元件 (主控台 / 回測共用)
│       │   ├── sparkline.py    # 列表用迷你縮圖
│       │   └── indicator_panel.py
├── tests/
├── installer/
│   └── build_msi.py          # cx_Freeze setup
├── requirements.txt
└── README.md
```
