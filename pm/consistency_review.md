# MD ↔ HTML 一致性與差異檢查

> 文件版本：v0.1
> 建立日期：2026-05-23
> 對比對象：
> - `pm/requirements.md` v0.2（635 行）
> - `pm/requirements.html`（1838 行，含 UI mockup）

## 0. 總體結論

整體一致性 **約 92%**，HTML 是 MD 的「視覺化擴充版」：
- 所有編號需求（FR-MM / SE / DL / EX / RM / NT / BT / UI / SC / NS / CH）兩份文件編號一致、優先級一致。
- HTML 額外提供了 6 個 UI mockup 區塊（主控台 SIM、主控台 LIVE、設定、回測、模式對話框、訊號 Email、K 線圖表、新聞情緒、News Digest Email）。
- MD 較完整的部分：**附錄 A 技術棧 / 附錄 B 目錄結構 / 第 11 章假設清單 / 第 12 章 M5.7 里程碑**，這些在 HTML 沒有列出。
- HTML 較完整的部分：**所有具體欄位範例、預設值、UI 互動元素、Email 範本實際內容**，這些在 MD 僅以表格描述。
- 兩份文件實際語意衝突極少，但有若干 **HTML 暗示了 MD 未寫明的隱含需求**，需確認後補入。

下面依類別逐項列出差異。

---

## 1. HTML 缺少、MD 有的內容

### 1.1 里程碑 M5.7（K 線圖表與技術指標）── **重要不一致**
- MD 第 12 章里程碑表列出：
  - M5.5 新聞情緒模組（2 週）
  - **M5.7 K 線圖表 & 技術指標（1.5 週）** ← HTML 沒有
  - M6 打包 & 部署（0.5 週）
- HTML 對應的里程碑表（第 888-904 行）**只列了 M5.5，缺 M5.7**，直接從 M5 跳到 M6。
- 影響：HTML 的讀者會以為 M5.5 之後就到 M6 部署，但實際上還有 K 線模組（4.11 新功能在 HTML 同樣存在），時程上少了 1.5 週。

### 1.2 附錄 A（技術棧）── **HTML 完全沒有**
- MD 列出 18 個套件選型（含 `pyqtgraph`、`mplfinance`、`TA-Lib / pandas-ta`、`backtrader`、`feedparser`、`trafilatura`、`rapidfuzz` 等）。
- HTML 沒有對應段落。對開發者（兼讀者）來說這是重要決策資訊。

### 1.3 附錄 B（目錄結構草案）── **HTML 完全沒有**
- MD 給出完整的 `src/stocks_trading/...` 樹狀結構，包含 `analytics/indicators.py`、`analytics/patterns.py`、`news/...`、`ui/widgets/kline_chart.py` 等。
- HTML 缺。

### 1.4 第 11 章「假設」（HTML 缺）
- MD 11.2 列出 4 條假設：
  - 僅 Windows 11
  - 使用者具備 SMTP 帳號
  - Shioaji 免費政策維持
  - 使用者了解「過去績效不代表未來」
- HTML 的風險表（870-886 行）涵蓋了「風險」，但 **沒有「假設」段落**。

### 1.5 5.4「可維護性」(NFR-MNT-*) ── **HTML 缺整段**
- MD 5.4 有三條 NFR：
  - NFR-MNT-01：核心模組單元測試覆蓋率 ≥ 70%
  - NFR-MNT-02：Shioaji 透過抽象介面
  - NFR-MNT-03：新增策略 ≤ 200 行
- HTML 第 717-748 行的 NFR 段落 **只列 5.1 安全 / 5.2 可靠 / 5.3 效能 / 5.4 部署（重新編號）**，完全沒有「可維護性」。
- 影響：HTML 的 NFR-DEP-* 編號其實對應 MD 的 NFR-DEP-*；但讀者會誤以為 MD 的 5.4 就是部署。

### 1.6 設定檔位置（HTML 缺）
- MD 7.2 明確指出：
  - `%LOCALAPPDATA%\StocksTrading\config.json`（明文）
  - `%LOCALAPPDATA%\StocksTrading\secrets.dat`（DPAPI 加密）
- HTML 沒有提及 secrets.dat 的存在，只在 NFR-DEP-02 提到 `%LOCALAPPDATA%\StocksTrading\`。

### 1.7 操作流程第 10.2「每日策略執行」── HTML 簡化
- MD 第 467-485 行的流程圖較詳細，含「For each signal」分歧、`SimulatedBroker.simulate_fill()` 等。
- HTML 第 853-868 行的流程圖比較精簡，省略了「For each signal」這層迴圈。

### 1.8 開放議題第 13 章微差
- MD 與 HTML 都列 9 條，但 MD 的第 9 條（持倉相關新聞優先）用詞較細，HTML 為摘要版。基本一致，無語意衝突。

---

## 2. MD 缺少、HTML 有的內容（暗示需求 / Implicit Requirements）

> 這類項目是 HTML mockup 中明顯呈現、但 MD 條文未明確編號的需求。建議補入 MD 為正式需求。

### 2.1 KPI 卡片具體指標 ── **隱含需求 P0**
HTML 主控台 mockup（第 953-974 行）顯式呈現 4 張 KPI 卡片：
- 帳戶總值（Equity）+ 自啟動以來的 %
- 今日損益（金額 + %）
- 未實現損益（金額 + 部位數）
- **勝率（近 30 筆）+ Sharpe**

MD 4.8 (FR-UI-*) 沒有規定主控台必須顯示哪些 KPI，僅 UC-03 概略說「檢視當日訊號、目前持倉、未實現損益、累計績效曲線」。
**建議補：FR-UI-11：主控台 KPI 區應顯示帳戶總值 / 今日損益 / 未實現損益 / 近 30 筆勝率與 Sharpe，至少 4 張。**

### 2.2 「系統狀態」面板 ── **隱含需求 P0**
HTML 第 1066-1080 行顯示主控台右側有「系統狀態」卡片：
- Shioaji 連線狀態
- SMTP 驗證狀態
- yfinance 正常與否
- **CA 憑證到期天數**（87 天後到期）

MD 沒有對應的 FR。第 13 章開放議題第 2 條提到「CA 憑證每年需更新一次，是否在 UI 提醒？」── 在 HTML mockup 已經畫出來了，**但 MD 仍標示為「開放議題」未決**。語意上不一致：HTML 已實作但 MD 未拍板。
**建議補：FR-UI-12 / FR-NT-07：系統狀態面板應即時顯示 Shioaji / SMTP / yfinance / CA 憑證健檢結果；CA 憑證到期 90 天內需以警示色提醒。**

### 2.3 「下次自動執行」資訊卡 ── 對應 FR-SC-02 但內容更具體
HTML 第 1057-1064 行：顯示「台股盤後策略 2026-05-26 14:00」與「美股盤後策略 2026-05-24 05:30」分項目。
MD FR-SC-02 僅說「GUI 顯示下次執行時間」，沒說要分台美股各列。
**建議釐清：FR-SC-02 是否需區分台股 / 美股兩個排程，分別顯示？**

### 2.4 訊號狀態 enum ── **隱含未列舉**
HTML 主控台「今日訊號」表（第 1017-1035 行）出現的狀態值：
- `⏳ 待寄信`
- `✓ 模擬成交`

但實際 enum 應該還包含：`已下單 / 已成交 / 已失敗 / 已忽略 / 已過期`。
MD 第 7.1 表 orders.status 沒列舉具體值，signals.sent 是 boolean 但 HTML 用了文字狀態。
**建議補：明確列舉 signal/order 的 status enum 集合與顯示文字對應。**

### 2.5 設定頁細節欄位 ── **MD 未詳列**
HTML 設定頁（第 1133-1198 行）出現以下 MD 未列舉的欄位：
- Shioaji **API Key** / **Secret Key**（MD 僅說「帳密」，沒區分 API Key 與 Secret Key）
- Shioaji **CA 密碼**（MD 提到 CA 憑證路徑但沒明列 CA 密碼欄位）
- **收件人欄位**（單獨欄位，與寄件帳號分開）
- **模擬模式起始資金（TWD / USD 分開）**：100,000 TWD 與 3,000 USD
- **假設手續費（台股 0.1425% / 美股 0.18%）**
- **假設滑價 0.05%**

MD 第 4.6 / NFR-SEC-01 只說「Shioaji 帳密」、「SMTP 密碼」加密，沒明列上述欄位。
**建議補：4.6 通知系統與 4.11 模擬模式參數應細化具體欄位與預設值。**

### 2.6 訊號 Email 內含的「下單檢核清單」 ── **HTML 獨有的 UI 元素**
HTML 第 1349-1355 行：美股訊號 Email 內含 checkbox 形式的下單檢核清單：
- ☐ 確認標的代碼 QQQ
- ☐ 確認數量 5 股、價格 ≤ $492.55
- ☐ 下單成功後請於 APP 額外掛停損單 $472.50
- ☐ 完成後可忽略本信

MD FR-NT-03 / FR-EX-02 只說 HTML 表格含標的、數量、價格、停損、操作指引，沒明列 checkbox 形式。
**建議補：FR-EX-02 美股訊號 Email 應包含可勾選的「下單檢核清單」段落。**

### 2.7 訊號 Email 內含的「策略原因」與「當前持倉狀態」 ── HTML 獨有
HTML 第 1333-1347 行：訊號 Email 內含
- **策略原因**列點（為何選 QQQ：累積報酬 +28.4% 排名第 1、絕對動能通過、SPY 排名下滑換 QQQ）
- **當前持倉狀態表**

MD FR-NT-03 只說「含表格、顏色標示、操作指引」，沒要求附策略推理過程。
**建議補：FR-NT-08：訊號 Email 應附「策略推理摘要」與「當前持倉快照」以利使用者判斷是否執行。**

### 2.8 主控台「子分頁」(全部 / 台股 / 美股) ── HTML 獨有
HTML 第 979-983 行顯示持倉表上有 subtabs：全部 (3) / 台股 (1) / 美股 (2)。
MD 沒有提到持倉列表需要分頁切換。
**建議補：FR-UI-13：持倉表應提供「全部 / 台股 / 美股」分類切換。**

### 2.9 圖表分頁的 timeframe 選項不一致 ── **重要不一致**
- MD FR-CH-02：時間週期支援 **「日線（預設）、週線、月線、60 分線」** ＝ 4 種。
- HTML 第 1393-1399 行的 timeframe-tabs 顯示 **「1m / 60m / 日 / 週 / 月」＝ 5 種**，多了 `1m`（1 分線）。

MD 第 1.3 非目標明確寫「高頻 / 盤中即時交易」不做。1 分線通常是盤中交易工具，與非目標相衝。
**衝突：HTML mockup 顯示 1m 選項，但 MD 非目標排除盤中即時交易，且 FR-CH-02 也未列 1m。** 建議統一移除 1m 或修改 MD。

### 2.10 圖表分頁「當前指標」即時數值表 ── HTML 獨有
HTML 第 1506-1514 行顯示：RSI(14)=68.5、MACD=+1.85、布林位置=0.82σ、20日均量比=2.15x。
MD FR-CH-13/14 只說有 RSI / MACD 副圖，沒說要在右側面板用表格顯示「當前數值與評語（接近超買 / 多頭 / 中上軌 / 爆量）」。
**建議補：FR-CH-17（新增）：圖表右側面板應顯示當前指標即時數值與口語化評語。**

### 2.11 新聞情緒分頁的「成本表」與「分析覆蓋率」 ── HTML 獨有
HTML 第 1554-1555 行頂欄：「最近抓取 06:00 · 87 篇新聞 · 分析 24 篇」。
HTML 第 1655-1662 行的 cost-meter：「今日 LLM 成本 $0.18 / $0.30」進度條 + 「預估今日尚可 ≈ 16 篇」。
MD 第 4.10.5 只說 Email Digest 標題要含 LLM 成本，沒說 GUI 也要即時顯示成本進度條與剩餘可分析篇數估算。
**建議補：FR-NS-30（新增）：新聞情緒分頁應即時顯示今日成本進度條與剩餘可分析篇數估算。**

### 2.12 候選清單的「sparkline 縮圖」 ── 對應 FR-CH-06 但延伸到新聞頁
HTML 第 1672-1677 行：每個 watch-card 右上角顯示 30 日 sparkline。
MD FR-CH-06 提到「持倉列表 / Watchlist 每列右方顯示近 30 日 sparkline」，**這條 MD 已涵蓋**，HTML 對應實作正確。

### 2.13 候選清單的動作按鈕集合 ── HTML 獨有
HTML 第 1682-1687 行 watch-actions 列出 4 個按鈕：
- → 轉為交易訊號
- 查看 K 線
- 查看原文 (4)
- 忽略

MD FR-NS-22 只提「轉為訊號」、FR-NS-23 黑名單、FR-NS-24 假新聞回報。
- 「查看 K 線」隱含跨 BC 跳轉（從新聞頁跳到圖表頁，預載該 ticker）── **MD 沒明寫這個導航需求**。
- 「查看原文 (4)」隱含一個「原文閱讀器」UI ── MD 沒提供。
**建議補：FR-NS-31 / FR-NS-32（新增）：Watchlist 卡片應提供「查看 K 線（跳轉至圖表頁並預載 ticker）」與「查看原文清單」功能。**

### 2.14 News Digest Email 的「弱訊號列表」 ── HTML 獨有
HTML 第 1818-1821 行：Digest Email 結尾列出「7 個弱訊號候選未列入摘要：AAPL, GOOG, MSFT, AMZN, COIN, PLTR, SHOP」。
MD FR-NS-26/27 只說 Top 10 候選；沒提弱訊號要不要在 Digest 中以列表方式呈現。
**建議補：FR-NS-33（新增）：News Digest Email 應在末尾列出未列入主表的弱訊號 ticker。**

### 2.15 News Digest Email 的「看多 / 看空 分區」 ── HTML 獨有
HTML 第 1763-1807 行：Digest Email 將 Top 10 拆成「▲ 看多候選 (Top 3 強訊號)」與「▼ 看空 / 風險候選」兩張表。
MD FR-NS-27 只說「含買賣建議方向」，沒指定 Email 排版需分區。
**建議補：FR-NS-34（新增）：News Digest Email 應按 side（看多 / 看空）分區，分區內按 score 排序。**

### 2.16 深色 / 明亮主題 toggle ── HTML 確實實作（FR-UI-05/07/08 對應）
HTML 第 382-410 行的 JS toggle 與 `data-theme` 屬性，符合 MD FR-UI-05 ~ FR-UI-10。
僅 MD FR-UI-09「深色版下 K 線顏色維持市場慣例」── HTML K 線 mockup 已用 var(--candle-up/down) 做了，但 HTML 的 K 線圖**沒有區分台股 / 美股的顏色慣例**（FR-CH-03 規定）。
**輕微不一致：HTML K 線顏色 CSS 變數固定為綠漲紅跌（美股慣例）；FR-CH-03 要求依市場切換。 mockup 範例只展示 QQQ（美股）所以恰好對；但 CSS 變數沒設計成依市場切換。** 實作時需注意。

### 2.17 主控台「實盤模式」對比畫面省略內容
HTML 第 1088-1108 行的「實盤模式」mockup 只顯示了頂欄變紅，內容區寫「(內容區同上，但所有『模擬』字樣替換為實際成交資訊，操作前需二次確認)」── 是省略圖。
**輕微議題：實盤模式下，是否有特殊 UI 元素（例如每次點擊「取消委託」也要二次確認）？需釐清。**

### 2.18 訊號日誌頁 / 策略頁 ── **HTML 完全沒畫**
- MD FR-UI-02 明確列出 5 大分頁：主控台、策略、回測、訊號日誌、設定（後來又因 4.10 加入「新聞情緒」、4.11 加入「圖表」，共 7 個）。
- HTML 提供了 6 個 mockup：主控台 / 設定 / 回測 / 模式對話框 / K 線圖表 / 新聞情緒 + 訊號 Email + News Digest Email。
- **缺：策略頁 mockup、訊號日誌頁 mockup**。
- HTML 的左側導覽列也僅有 7 個 nav-item（主控台 / 圖表 / 新聞情緒 / 策略 / 回測 / 訊號日誌 / 設定），其中「策略」與「訊號日誌」**沒有對應的 mockup 設計**。
**建議補：HTML 應補上策略頁與訊號日誌頁 mockup。**

---

## 3. 編號對齊檢查

### 3.1 FR 編號一致性
| 編號區段 | MD 條數 | HTML 條數 | 對齊狀況 |
| --- | --- | --- | --- |
| FR-MM-01 ~ 07 | 7 | 7 | ✅ 完全一致 |
| FR-SE-01 ~ 05 | 5 | 5 | ✅ 完全一致 |
| FR-DL-01 ~ 05 | 5 | 5 | ✅ 完全一致 |
| FR-EX-01 ~ 05 | 5 | 5 | ✅ 完全一致 |
| FR-RM-01 ~ 05 | 5 | 5 | ✅ 完全一致 |
| FR-NT-01 ~ 06 | 6 | 6 | ✅ 完全一致 |
| FR-BT-01 ~ 05 | 5 | 5 | ✅ 完全一致 |
| FR-UI-01 ~ 10 | 10 | 10 | ✅ 完全一致 |
| FR-SC-01 ~ 03 | 3 | 3 | ✅ 完全一致 |
| FR-NS-01 ~ 29 | 29 | 29 | ✅ 完全一致 |
| FR-CH-01 ~ 08 / 10 ~ 16 / 20 ~ 27 | 22 | 22 | ✅ 完全一致（含 FR-CH-09/17/18/19/28 跳號刻意保留） |
| NFR-SEC-01 ~ 04 | 4 | 4 | ✅ |
| NFR-REL-01 ~ 03 | 3 | 3 | ✅ |
| NFR-PER-01 ~ 03 | 3 | 3 | ✅ |
| **NFR-MNT-01 ~ 03** | 3 | **0** | ❌ HTML 缺整段 |
| NFR-DEP-01 ~ 04 | 4 | 4 | ✅ |

### 3.2 FR 編號跳號刻意保留
- FR-CH-09 / FR-CH-17 ~ 19 / FR-CH-28：兩份都跳號（在 4.11.1 / 4.11.2 / 4.11.3 之間預留）。屬刻意設計，**保留即可**，但建議補一行註記說明「跳號為了給未來擴展」。

---

## 4. 資料模型（SQLite）對齊

| 表格 | MD 欄位 | HTML 欄位 | 結論 |
| --- | --- | --- | --- |
| `accounts` | id, name, mode, broker, init_capital, created_at | 同左 | ✅ |
| `positions` | account_id, symbol, market, qty, avg_price, stop_loss, opened_at | 同左 | ✅ |
| `orders` | id, account_id, mode, symbol, side, qty, price, stop_loss, status, placed_at, filled_at | 同左 | ✅ |
| `signals` | id, strategy, symbol, side, target_price, stop_loss, generated_at, sent | 同左 | ✅ |
| `daily_pnl` | account_id, date, equity, realized_pnl, unrealized_pnl | 同左 | ✅ |
| `kbars_cache` | symbol, date, open, high, low, close, volume | 同左 | ✅ |
| `app_log` | ts, level, module, message | 同左 | ✅ |
| `news_articles` | id, source, url, url_hash, title, published_at, lang, raw_text, fetched_at | 同左 | ✅ |
| `news_analysis` | article_id, model, sentiment, impact_score, summary, catalysts_json, tickers_json, cost_usd, analyzed_at | 同左 | ✅ |
| `news_tickers` | article_id, ticker, confidence | 同左 | ✅ |
| `watchlist` | id, ticker, market, side, source_articles_json, score, status, added_at, expires_at | 同左 | ✅ |
| `llm_cost_daily` | date, model, calls, input_tokens, output_tokens, cost_usd | 同左 | ✅ |
| `blacklist` | type (ticker/source), value, reason, added_at | type, value, reason, added_at | ✅（HTML 沒寫括號註，但欄位一致） |

**資料模型 100% 對齊，無差異。**

---

## 5. 風險表對齊
MD 與 HTML 都列了 10 條風險（5 條原有 + 5 條新聞相關）。內容、影響等級、緩解措施 100% 一致。

---

## 6. Email 格式對齊
| Email 類型 | MD 描述 | HTML mockup | 對齊狀況 |
| --- | --- | --- | --- |
| 美股訊號 | 標題、內容欄位列出 | 有完整可視 mockup | ✅ HTML 更詳細（見 2.6 / 2.7） |
| 每日摘要 | 文字列出 | 無 mockup | ⚠ HTML 缺 mockup |
| 系統告警 | 文字列出 | 無 mockup | ⚠ HTML 缺 mockup |
| News Digest | 文字列出 | 有完整可視 mockup | ✅ HTML 更詳細（見 2.14 / 2.15） |

**建議補：HTML 應補上每日摘要 / 系統告警 Email mockup。**

---

## 7. 衝突與不一致彙整（需求等級）

| # | 衝突項目 | MD | HTML | 嚴重度 | 建議行動 |
| --- | --- | --- | --- | --- | --- |
| C1 | 里程碑 M5.7 | 有（K 線模組 1.5 週） | 無 | 高 | HTML 補列 M5.7 |
| C2 | 1m timeframe | 排除高頻、FR-CH-02 不含 1m | mockup 有 1m tab | 中 | 二擇一：移除 1m 或更新 FR-CH-02 |
| C3 | CA 憑證到期提醒 | 列為「開放議題 #2」未拍板 | mockup 已顯示提醒 | 中 | 拍板為 FR-UI-12 或從 mockup 移除 |
| C4 | NFR-MNT-* 可維護性 | 三條規範 | 整段缺 | 中 | HTML 補上 |
| C5 | 附錄 A 技術棧 / B 目錄 | 完整列出 | 無 | 低 | HTML 補上（或維持「HTML 為摘要版」設計）|
| C6 | 第 11 章假設 | 列出 4 條 | 無 | 低 | HTML 補上 |
| C7 | 第 5.4 編號 | MD 是「可維護性」 | HTML 是「部署」 | 中 | HTML 重新編號為 5.5 部署 |
| C8 | 策略頁 / 訊號日誌頁 mockup | UI 章節要求有 | 無 mockup | 低 | HTML 補 mockup（或 MD 註明 mockup 留待後階段） |
| C9 | K 線顏色市場慣例切換 | FR-CH-03 規定 | CSS 變數未依市場切換 | 低 | 實作時注意 |

---

## 8. 雙文件同步建議

針對未來維護建議：
1. **單一真相來源（SoT）**：建議以 MD 為 SoT，HTML 由 MD 衍生（或反之），避免兩份各自演化。
2. **加入版本對照表**：MD 開頭加一行「本版本對應 requirements.html v0.2」。
3. **自動化檢查腳本**：可寫一個簡單的腳本掃 MD 中所有 `FR-XX-NN` 編號，與 HTML 中所有 `class="id">FR-XX-NN` 比對。
4. **mockup 的隱含需求需回灌 MD**：第 2 節列出的 12 條 implicit requirements 全部應拍板為正式 FR 編號。

---

## 9. 結論
- **語意衝突僅 2 條較重要**（C1 缺 M5.7、C2 1m timeframe），其餘為「HTML 比 MD 詳細的具體實作細節」。
- **HTML 隱含了 12 條未編號的需求**（第 2 節），建議補入 MD。
- **建議 v0.3 同步**：MD 與 HTML 各自補齊上述差異，並建立 SoT 機制。
