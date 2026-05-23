# 分階段釋出計畫 (Release Plan)

| 項目 | 內容 |
| --- | --- |
| 文件版本 | v1.0 |
| 建立日期 | 2026-05-23 |
| 對應需求版本 | `requirements.md` v0.3 |
| 適用範圍 | StocksTrading 自動化交易系統 |

---

## 1. 釋出策略總覽

### 1.1 為什麼分階段
- **單人開發最大風險是動力斷掉**：15 週才上線、中途任何挫折都可能讓專案做廢。
- **早期驗證需求**：跑 paper 一週後常會發現要改的東西，越早跑越早改。
- **價值階梯**：每個版本都是「獨立可用」的產品，而不是半成品。

### 1.2 三個里程碑版本

```
v1.0  Paper Trading MVP      (Week 7)   ← 可裝、可跑、純模擬
  ↓
v1.5  實盤 + K 線圖表          (Week 11)  ← 加實盤、加技術分析
  ↓
v2.0  新聞情緒模組            (Week 14)  ← 加 LLM 輔助選股
  ↓
v3.0+ 未來功能                          ← 中文新聞、付費 API、選擇權...
```

每個版本 **獨立交付 MSI 安裝檔**，安裝後即可使用該版本所有功能。

---

## 2. v1.0 — Paper Trading MVP

### 2.1 範圍 (Scope)

**包含 (In Scope):**

| 模組 | 內容 | 對應需求 |
| --- | --- | --- |
| 資料層 | yfinance (美股+台股) / Shioaji kbars (台股) / SQLite 快取 | FR-DL-01~05 |
| 策略 | Dual Momentum (台股+美股) | FR-SE-01~05 |
| 回測 | backtrader 引擎、T+1 開盤價成交、績效指標、曲線圖 | FR-BT-01~05 |
| 模擬交易 | SimulatedBroker、T+1 開盤成交、跳空保護、雙帳本損益計算 | FR-EX-03/06/07 |
| 模式管理 | 內部支援 SIM / LIVE 雙帳本架構，**但 UI 隱藏 LIVE 切換** | FR-MM-01/02/07/08 |
| 風控 | 單筆風險上限、總部位上限、單日熔斷（僅作用於 SIM 帳本） | FR-RM-01~04 |
| GUI | PySide6 五大分頁：主控台 / 策略 / 回測 / 訊號日誌 / 設定 | FR-UI-01~03 |
| 主題 | 明亮 / 深色切換、預設依循 Windows 系統 | FR-UI-05/07/08/09 |
| Email | SMTP 核心 + 每日摘要 + 系統告警 | FR-NT-01/02/04/05/06 |
| 排程 | Windows Task Scheduler 範本、CLI 模式 | FR-SC-01/02/03 |
| 安全 | DPAPI 加密 SMTP 密碼、設定檔不含明碼 | NFR-SEC-01~02 |
| 打包 | cx_Freeze MSI 基礎版、開始選單 + 桌面捷徑 | NFR-DEP-01~03 |
| Schema 管理 | SQLite 內建 version table + migration 機制 | NFR-MNT-* |

**明確排除 (Out of Scope, 留給 v1.5+):**
- ❌ ShioajiBroker 實盤下單（UI 上 LIVE 模式 toggle 隱藏 / 灰階）
- ❌ EmailBroker (US 訊號通知 Email)
- ❌ K 線圖表、技術指標、形態偵測
- ❌ 新聞情緒分析模組
- ❌ Watchlist GUI

### 2.2 里程碑工作分解

| M# | 內容 | 工時 | 依賴 |
| --- | --- | --- | --- |
| M0 | 專案骨架、Broker 抽象、SQLite schema、DPAPI 加密、schema migration | 1 週 | — |
| M1 | yfinance / Shioaji kbars、Dual Momentum、backtrader (T+1) | 1 週 | M0 |
| M2 | SimulatedBroker、雙帳本、T+1 開盤成交、跳空保護 | 1 週 | M1 |
| M3 | PySide6 GUI 五大分頁、深色主題 toggle | 2 週 | M2 |
| M4a | SMTP 核心 + 每日摘要 + 系統告警 | 0.5 週 | M2 |
| M6a | cx_Freeze MSI 打包 + 安裝測試 | 1 週 | M3, M4a |
| **合計** | | **6.5 週** | |

### 2.3 Entry / Exit Criteria

**Entry to v1.0 development:**
- ✅ requirements.md v0.3 鎖定
- ✅ SA 技術分析文件完成
- ✅ Anthropic API key, Shioaji API key 不必有（v1.0 不需要）
- ✅ Python 3.11+ + Windows 11 開發環境

**Exit (v1.0 release ready):**
- ✅ Paper trading 模擬連續 5 個交易日無 exception
- ✅ 回測引擎與 SimulatedBroker 在相同訊號下結果一致 (T+1 規則一致)
- ✅ MSI 在乾淨 Windows 上安裝成功、設定保留、解除安裝乾淨
- ✅ Email 寄送、Task Scheduler 觸發、CLI 模式均通過手動驗收
- ✅ 主題切換無 UI 跑版
- ✅ 雙帳本架構即使 UI 沒開放也已實作完整（後續 v1.5 不需重構）

### 2.4 v1.0 已知限制 / Known Limitations
- LIVE 模式 UI 灰階，hover 顯示「v1.5 開放」
- 美股訊號目前僅以 daily summary email 通知（無專屬訊號信）
- 無 K 線圖、無新聞分析

---

## 3. v1.5 — 實盤 + K 線圖表

### 3.1 範圍

**新增 (新功能):**

| 模組 | 內容 | 對應需求 |
| --- | --- | --- |
| ShioajiBroker | 實盤下單、條件停損單、CA 憑證流程 | FR-EX-01/05 |
| 模式切換 UI | 二段確認、輸入 "LIVE"、24h 自動回 SIM | FR-MM-03~06/09/10 |
| 雙帳本 UI | 切換時顯示「X 帳本 N 筆部位將凍結」、實盤未平倉禁止重置 | FR-MM-10/11 |
| EmailBroker (US) | 美股訊號專屬 HTML Email、下單檢核清單 | FR-EX-02/NT-03 |
| K 線圖表 | pyqtgraph 主圖、時間週期、十字游標、縮放 | FR-CH-01~08 |
| 技術指標 | MA / Bollinger / Volume / RSI / MACD、IndicatorEngine 統一函式 | FR-CH-10~16 |
| 形態偵測 | 黃金/死亡交叉、布林突破、RSI 超買賣、爆量 | FR-CH-20~26 |
| Sparkline | 主控台持倉列表迷你縮圖 | FR-CH-06 |
| 回測進出場視覺化 | 回測結果圖上標示策略買賣點 | FR-CH-07 |
| 風控完整啟用 | 實盤模式下 RiskGuard 全部規則啟用 | FR-RM-01~05 |

**保留排除:**
- ❌ 新聞情緒分析模組（留給 v2.0）

### 3.2 里程碑工作分解

| M# | 內容 | 工時 | 依賴 |
| --- | --- | --- | --- |
| M5 | ShioajiBroker、條件停損單、EmailBroker (US)、RiskGuard 完整 | 1.5 週 | v1.0 |
| M4b | 訊號通知 Email HTML 範本、美股下單檢核清單 | 0.5 週 | M5 |
| M5.7a | pyqtgraph K 線元件、十字游標、縮放、時間週期 | 0.8 週 | v1.0 |
| M5.7b | IndicatorEngine：MA / Bollinger / Volume / RSI / MACD | 0.5 週 | M5.7a |
| M5.7c | PatternDetector：4 種形態 + 標籤標示 | 0.4 週 | M5.7b |
| M5.7d | 圖表分頁 + sparkline + 回測進出場視覺化 | 0.3 週 | M5.7c |
| 整合測試 | LIVE↔SIM 切換壓力、雙帳本資料隔離、實盤驗收 | 0.5 週 | M5, M5.7d |
| **合計** | | **4.5 週** | |

### 3.3 Entry / Exit Criteria

**Entry to v1.5 development:**
- ✅ v1.0 release ≥ 1 個月，paper trading 持續執行
- ✅ 永豐 Shioaji API 申請完成、CA 憑證取得
- ✅ Shioaji simulation account 測試通過
- ✅ v1.0 雙帳本架構驗證無 bug

**Exit (v1.5 release ready):**
- ✅ Shioaji 真實下單（小額 1 股 / 1 張）成功 + 條件單成功
- ✅ 模式切換 SIM↔LIVE 連續 20 次無資料污染
- ✅ 24h 自動回 SIM 機制驗證通過
- ✅ K 線圖渲染 1000 根 < 200ms
- ✅ 技術指標計算結果與外部驗證（如 TradingView）誤差 < 0.01%
- ✅ 美股訊號 Email 收件人實際收到、HTML 渲染正確
- ✅ 台股實盤 2 週、單筆 ≤ 1% 風險、無 critical bug

### 3.4 v1.5 已知限制
- 無新聞分析
- 美股仍需手動下單（永豐 API 不支援美股自動）

---

## 4. v2.0 — 新聞情緒模組

### 4.1 範圍

**新增:**

| 模組 | 內容 | 對應需求 |
| --- | --- | --- |
| NewsCollector | RSS (CNBC/Reuters/TechCrunch/Ars/Verge)、Reddit JSON、SEC EDGAR、去重 | FR-NS-01~06 |
| LLMAnalyzer | Anthropic Claude (haiku-4-5)、結構化 JSON、prompt caching | FR-NS-07~13 |
| CostGuard | 每日 LLM 預算上限 $0.3 USD、超過自動停止並告警 | FR-NS-10/11 |
| TickerMapper | 公司名 → ticker 對應、信心度門檻 | FR-NS-14/15 |
| Ranker | 多因子排序（影響 × 來源信用 × 時效 × 多源加成） | FR-NS-16~19 |
| Watchlist GUI | 新聞情緒分頁、候選清單、兩段核可 | FR-NS-20~25 |
| 黑名單 | 排除 ticker / 來源、假新聞回報 | FR-NS-23/24 |
| Daily Digest | Top 10 候選、強訊號醒目色、LLM 成本顯示 | FR-NS-26~29 |

### 4.2 里程碑工作分解

| M# | 內容 | 工時 | 依賴 |
| --- | --- | --- | --- |
| M5.5a | NewsCollector + 7 個來源 adapter + 去重 | 0.5 週 | v1.5 |
| M5.5b | LLMAnalyzer + Claude 整合 + CostGuard | 0.7 週 | M5.5a |
| M5.5c | TickerMapper + Ranker | 0.5 週 | M5.5b |
| M5.5d | Watchlist GUI + 兩段核可流程 | 0.8 週 | M5.5c |
| M5.5e | Daily News Digest Email 範本 | 0.3 週 | M5.5c |
| 整合測試 | 端對端、成本上限驗證、強/弱訊號分類 | 0.2 週 | M5.5d, M5.5e |
| **合計** | | **3.0 週** | |

### 4.3 Entry / Exit Criteria

**Entry to v2.0 development:**
- ✅ v1.5 release ≥ 1 個月、實盤運作穩定
- ✅ Anthropic API key 申請完成 + 信用卡 billing 設定
- ✅ 確認新聞來源 RSS / Reddit 等可正常存取

**Exit (v2.0 release ready):**
- ✅ Watchlist 連續 5 個交易日推薦無 LLM 幻覺（虛構 ticker）
- ✅ CostGuard 在超過 $0.3 時正確停止並寄告警
- ✅ 兩段核可流程驗證通過（必須手動點才下單）
- ✅ Daily Digest 寄送 5 個交易日無漏寄
- ✅ 強訊號（≥3 來源）與弱訊號分類正確

### 4.4 持續 paper 階段
- v2.0 release 後 paper 跑 1 個月，觀察 Watchlist 推薦準確度
- 若採用率 < 30% 或勝率 < 50%，**不要實盤啟用新聞驅動訊號**

---

## 5. Git Tag / 版本命名規範

### 5.1 Tag 命名

採用 **Semantic Versioning (SemVer)**：`MAJOR.MINOR.PATCH`

| 變更類型 | Tag 規則 | 範例 |
| --- | --- | --- |
| 階段釋出 | MAJOR.MINOR 主版 | `v1.0.0`, `v1.5.0`, `v2.0.0` |
| Bug 修正 | PATCH+1 | `v1.0.1`, `v1.0.2` |
| 小功能（不破壞 API） | MINOR+1 | `v1.0.0` → `v1.1.0` |
| Schema 升級 | MINOR+1，README 註明 migration | `v1.2.0` |
| Breaking change | MAJOR+1 | `v1.x` → `v2.0.0` |

### 5.2 Pre-release Tag

開發中版本：`v1.0.0-alpha.1`, `v1.0.0-beta.1`, `v1.0.0-rc.1`

### 5.3 Branch 策略（單人開發）

```
main (穩定，每個 release 打 tag)
  ↓
dev (整合中)
  ↓
feature/M0-skeleton  ← 短命 feature branch
feature/M5.7-charts
hotfix/v1.0.1-fix-mode-switch
```

- `main` 永遠可編譯、可裝、可跑
- `dev` 用來累積尚未 release 的功能
- 每個 milestone 一個 feature branch，完成 + 自我 review 後 merge 進 dev
- Release 時把 dev merge 進 main 並打 tag

### 5.4 Tag 與 MSI 對應

每個 release tag 必須產出對應的 MSI 檔，命名：
```
StocksTrading-1.0.0-x64.msi
StocksTrading-1.5.0-x64.msi
StocksTrading-1.5.1-x64.msi  ← hotfix
```

---

## 6. 跨版本資料庫遷移策略

### 6.1 為什麼這很重要
- 你會在每個版本之間 paper trading 1 個月以上
- 升級到下個版本時**絕不能丟掉前版本累積的資料**

### 6.2 機制

從 M0 開始就要做：
1. SQLite 內建 `schema_version` 表（單列、紀錄當前 schema 版本號）
2. `src/stocks_trading/storage/migrations/` 目錄存 `0001_initial.sql`, `0002_add_news.sql`, ...
3. 應用程式啟動時：
   - 讀 `schema_version`
   - 若 < 程式內建版本 → 依序執行未跑過的 migration
   - 跑前先 backup 整個 db 為 `app.db.bak.20260523_140230`
4. Migration 失敗時還原 backup 並寄出告警

### 6.3 版本間 Schema 變更預期

| 版本 | 新增 / 變更的表 |
| --- | --- |
| v1.0 → v1.0.x | 通常無 schema 變更（patch only） |
| v1.0 → v1.5 | 新增 `chart_patterns_cache`（形態偵測快取）；`orders` 表加 `shioaji_order_id` 欄位 |
| v1.5 → v2.0 | 新增 `news_articles`, `news_analysis`, `news_tickers`, `watchlist`, `llm_cost_daily`, `blacklist` |

---

## 7. 測試重點分版本

| 版本 | 重點測試 |
| --- | --- |
| v1.0 | 模擬成交正確性（T+1 規則）、回測 vs SimulatedBroker 一致性、Schema migration、MSI 安裝、Email 寄送 |
| v1.5 | Shioaji 實盤連線 + 條件單、模式切換壓力（連續 50 次）、雙帳本資料隔離、K 線渲染效能 (1000 candles < 200ms)、技術指標數值正確 |
| v2.0 | LLM 端對端、CostGuard 上限觸發、Watchlist 兩段核可不可繞過、新聞去重、強/弱訊號分類 |

每個版本 release 前必須跑完對應的測試清單，**全綠才打 tag**。

---

## 8. 風險與緩解

| 風險 | 緩解 |
| --- | --- |
| v1.0 雙帳本架構設計錯誤，v1.5 開放 LIVE 時才暴露 | 即使 UI 沒開放，後端的 SIM/LIVE 雙帳本邏輯在 v1.0 就要實作完整並通過測試 |
| v1.5 才實作的 ShioajiBroker 與 v1.0 SimulatedBroker 介面不一致 | M0 階段就鎖定 Broker 抽象介面、寫好 contract test |
| Paper trading 時間不夠就跳實盤 | 強制 Entry criteria：v1.0 paper ≥ 1 個月才能進 v1.5 開發 |
| MSI 升級時破壞使用者資料 | Schema migration 強制 backup，且資料儲存於 `%LOCALAPPDATA%` 與安裝目錄分離 |
| 工時嚴重低估、某階段拖太久 | 18 週為總工時上限，超過則砍 v2.0 功能或延後 |

---

## 9. Definition of Done (DoD)

每個 M# 完成的判準：

1. ✅ 程式碼通過 ruff + mypy
2. ✅ 對應的單元測試覆蓋率 ≥ 70%
3. ✅ 該功能在 GUI / CLI 兩種模式下手動驗收通過
4. ✅ README 對應段落更新
5. ✅ 該 milestone 的 Entry criteria 文件登記為「已滿足」
6. ✅ 該 branch 已 merge 進 dev，CI 通過

每個版本 release 的判準：

1. ✅ 所有 M# 通過 DoD
2. ✅ 對應版本的 Exit criteria 全部滿足
3. ✅ MSI 可在乾淨 Windows 11 上安裝、使用、解除安裝
4. ✅ Schema migration 從前一版升級驗證通過
5. ✅ Tag 打上、Release notes 撰寫完成
6. ✅ 該版本對應的 Open Questions 已澄清或明確記錄到下版本
