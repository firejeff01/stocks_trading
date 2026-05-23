# 技術選型與風險決策 (Technology Decisions & Risks)

| 項目 | 內容 |
| --- | --- |
| 文件版本 | v0.1 |
| 建立日期 | 2026-05-23 |
| 對應 PM 版本 | `pm/requirements.md` v0.3（附錄 A 技術棧）、`pm/release_plan.md` v1.0 |
| 文件範圍 | 關鍵技術選型的「選什麼 / 為什麼 / 替代方案 / 踩坑風險與緩解」；不重複 PM 附錄 A 的套件清單 |

## 0. 文件閱讀導引

每個決策段落採用統一格式：
- **決策**：選了什麼版本 / 套件
- **替代方案**：考慮過但沒選的選項
- **理由**：為何這樣選
- **踩坑風險 (Real Gotcha)**：實際開發會卡在哪
- **緩解**：怎麼準備

依重要性與踩坑機率排序：
1. cx_Freeze 打包（最大不確定性）
2. Shioaji 整合（v1.5 致命瓶頸）
3. PySide6 + qasync（v1.0 GUI 核心）
4. 技術指標套件（TA-Lib vs pandas-ta）
5. 回測框架（backtrader 等）
6. K 線圖表（pyqtgraph 等）
7. Anthropic SDK（v2.0 整合）
8. Schema migration 工具
9. DPAPI 加密細節

---

## 1. 桌面 GUI 框架 — PySide6 vs PyQt6 vs Tkinter

### 1.1 決策
**PySide6**（Qt for Python 官方版）。

### 1.2 替代方案
| 候選 | 評估 |
| --- | --- |
| PyQt6 (Riverbank) | 商用授權成本高（GPL or 商業授權 USD 550/dev）；個人專案無強動機 |
| Tkinter | 內建免依賴，但元件醜、無內建 K 線元件、深色主題實作工作量大 |
| Electron + Python backend | bundle 體積爆炸（~150MB+）、不熟 JS 生態、桌面雙程序架構複雜 |
| Dear PyGui | 即時 GPU render 適合 dashboard，但對 form / dialog / settings 等 CRUD 介面支援差 |
| Toga / Kivy | 跨平台優先設計，但 PM 明確只 Windows；不需要 cross-platform tax |

### 1.3 理由
- PySide6 LGPL 授權，個人專案完全免費。
- 與 pyqtgraph、qasync 整合成熟（v1.5/v2.0 直接利用）。
- Qt Designer `.ui` 檔 / qss 主題機制成熟，深色模式切換相對好做（FR-UI-05~10）。
- Frozen by cx_Freeze 經驗多，社群文件豐富。

### 1.4 踩坑風險

**Risk A：qasync 把 Qt event loop 與 asyncio 整合，但「卡住 UI」的坑很多**。
- 任何 `await long_io()` 若沒在 worker thread 中跑，UI 仍會卡。
- `qasync.QEventLoop` 與 PySide6 6.6+ 的相容性需驗證（v1.0 開發初期就要測）。

**Risk B：訊號槽（signal/slot）在跨 thread 時序問題**。
- 從 background thread 直接修改 Widget 屬性會 segfault；必須用 `QMetaObject.invokeMethod` 或 `QObject.moveToThread`。

**Risk C：高 DPI（4K / 縮放 150%）的繪圖模糊與字距錯亂**。
- 必須在 main 設 `QApplication.setHighDpiScaleFactorRoundingPolicy(...)`。

**Risk D：深色 / 明亮即時切換（FR-UI-08）需所有自訂 widget 都支援 `palette()` 動態變更**。
- pyqtgraph K 線顏色、tooltip 樣式、Email 預覽器 HTML 都要重繪。

### 1.5 緩解
- M0 第一週做 `qasync + 簡單按鈕觸發 async sleep + 主題切換` 的 spike，驗證可行性。
- 訂下 thread 規則：所有 Service 呼叫必須走 `QThreadPool` 或 `QRunnable`，UI 端只透過 `Signal` 收結果。
- 高 DPI 在 `app.py` 最上層強制設 Qt scale policy。
- 主題切換由 `ThemeManager` 統一管理 palette + qss + 圖表色票，所有 widget 訂閱 `theme_changed` signal。

---

## 2. MSI 打包 — cx_Freeze vs PyInstaller + WiX vs briefcase

### 2.1 決策
**cx_Freeze + `bdist_msi`（v1.0），保留 PyInstaller + WiX 為 fallback**。

### 2.2 替代方案
| 候選 | 評估 |
| --- | --- |
| **PyInstaller + WiX Toolset** | 業界標準；WiX 配置複雜（XML）；安裝畫面客製化最強；學習曲線陡 |
| cx_Freeze | 內建 `bdist_msi`，一條龍從 setup.py 打 MSI；客製能力弱；社群比 PyInstaller 小 |
| briefcase (BeeWare) | 跨平台一致；對 Windows MSI 支援尚可，但對 PySide6 + native DLL 整合不成熟 |
| Inno Setup + PyInstaller | Inno 不是 MSI 而是 .exe；不符 NFR-DEP-01 「MSI」要求 |
| Nuitka | 編譯成原生 binary、效能好，但對 PySide6 / shioaji native dependencies 相容性風險高 |

### 2.3 理由
- PM `requirements.md` 附錄 A 已寫明 `cx_Freeze (bdist_msi)`，與 NFR-DEP-01 對齊。
- 個人專案、單一 Windows 目標、不需華麗安裝畫面 → cx_Freeze 夠用。
- 從 `setup.py` 一鍵打 MSI，CI/CD 簡單（PowerShell 一行）。
- 升級保留資料（NFR-DEP-04）容易：MSI 的 `UpgradeCode` 機制 + 我們的 `%LOCALAPPDATA%` 與安裝路徑分離設計。

### 2.4 踩坑風險

**Risk A：cx_Freeze 對 native DLL（shioaji、TA-Lib 二進位）的 freeze 經常漏帶 dependency**。
- shioaji 套件內附 `solshioaji.dll`、`libssl-1_1-x64.dll` 等；frozen 後可能放錯路徑或被誤判為「未使用」剝離。
- 症狀：在開發機跑沒問題，安裝到乾淨 Windows 上 `import shioaji` 直接 ImportError。

**Risk B：`bdist_msi` 不支援自訂安裝精靈頁面、不能加 EULA、不能跑 custom action**。
- 若 v1.5 需要安裝時自動詢問 CA 憑證路徑 → cx_Freeze 做不到，需要切到 WiX。

**Risk C：MSI `UpgradeCode` 與 `ProductCode` 規則複雜，弄錯會導致「升級變成兩個版本同時存在」**。
- `UpgradeCode` 必須在所有版本固定不變；`ProductCode` 每版必須換。

**Risk D：Windows SmartScreen 警告**。
- 未簽署的 MSI 在 Windows 11 跑會被 SmartScreen 攔截，使用者要點「仍要執行」。
- 自簽憑證可解一半（內部信任後），但別人的機器仍會警告。

**Risk E：cx_Freeze 對 PySide6 6.6+ 的相容性偶有問題**。
- Qt plugins（imageformats、platforms\qwindows.dll）若沒被打包 → app 啟動黑屏無錯誤訊息。

### 2.5 緩解
- **M0 預作 PoC**：第 1 週末就做一次最簡 cx_Freeze build，含 PySide6 main window + sqlite3 寫入，安裝到乾淨 Win11 VM 驗證可跑。
- **DLL whitelist**：寫一個 `installer/dll_check.py` 腳本，自動 diff 開發機 site-packages 中所有 .dll 與 frozen 後 `lib/` 中的 .dll，差異列出來逐個 review。
- **打包目錄結構固定**：所有 native DLL 強制放 `lib/`，PySide6 plugins 強制放 `lib/PySide6/plugins/`。
- **`UpgradeCode` 寫在 README 開頭並 commit 到 git**，禁止任何人改動。
- **自簽憑證 + 加入 SmartScreen Reputation**：使用一段時間後 SmartScreen 會自動信任（個人專案唯一可行解）。
- **若 v1.5 / v2.0 需要更強客製 → 改用 PyInstaller + WiX**；MVP 不要過早優化。

---

## 3. 技術指標 — TA-Lib vs pandas-ta

### 3.1 決策
**pandas-ta**（v1.0 / v1.5），保留未來改 TA-Lib 的可能性。

### 3.2 替代方案
| 候選 | 評估 |
| --- | --- |
| **TA-Lib (C 原生 + Python wrapper)** | 計算最快、業界最廣；但安裝需 C 編譯，Windows 上裝 wheel 通常 OK，frozen 經常出問題 |
| pandas-ta | 純 Python，安裝零摩擦；速度比 TA-Lib 慢 3~10 倍，但 MVP 資料量小可接受 |
| 自寫 numpy 實作 | 控制最強、依賴最少；維護成本高、容易和外部工具（TradingView）數值不一致 |
| finta | 純 Python；社群小、長期維護不確定 |

### 3.3 理由
- PM 附錄 A 寫「TA-Lib 或 pandas-ta」，給 SA 決定。
- 對 Dual Momentum（v1.0）僅需 SMA 等基礎指標，速度不是瓶頸。
- 對 v1.5 K 線（FR-CH-10~14）的 MA/Bollinger/RSI/MACD，pandas-ta 全部支援。
- Frozen 風險：TA-Lib 是 native lib，cx_Freeze 過去常出問題（見 §2.4 Risk A 類似情境）。
- 數值正確性：PM `release_plan.md` v1.5 Exit Criteria「與外部驗證誤差 < 0.01%」── pandas-ta 內部公式與 TradingView 一致性高，過去案例不大會出問題；但仍要寫對拍測試。

### 3.4 踩坑風險

**Risk A：pandas-ta RSI 與 TradingView 預設不同**。
- pandas-ta 預設用 SMA-based smoothing，TradingView 用 Wilder's smoothing。
- 同樣參數 RSI(14)，pandas-ta 與 TradingView 可能差 1~2 點。

**Risk B：MACD 算法差異**。
- 不同來源對「signal line」是否用 EMA 起始填零、是否含 warmup period，數值差異微小但顯著。

**Risk C：pandas-ta 對 pandas 2.x 的相容性**。
- pandas-ta 開發放緩，需鎖定 pandas 版本（< 2.2 或測試後決定）。

### 3.5 緩解
- M1 同時跑 pandas-ta 與「自寫 numpy 對拍」測試（5 種 indicator × 3 個 ticker × 1000 個 timestamp），記錄誤差。
- 若 RSI 差異 > 0.01%：在 `IndicatorEngine` 內 override，改用 `pandas_ta.rsi(close, length=14, talib=False, ...)` 並指定 Wilder smoothing。
- 對外驗收（v1.5 Exit）用 TradingView 截圖比對 3 個指標的當日值。
- 若 pandas-ta 未來廢棄 → `IndicatorEngine` 是純函式介面，可無痛換 TA-Lib（介面不變）。

---

## 4. 回測框架 — backtrader vs vectorbt vs zipline

### 4.1 決策
**backtrader**（v1.0）。

### 4.2 替代方案
| 候選 | 評估 |
| --- | --- |
| **backtrader** | 事件驅動、API 直觀、文件多；速度慢；維護放緩 |
| vectorbt | 向量化、超快、UI 很潮；學習曲線陡；API 偏 numpy 寫法，與策略類別差異大 |
| zipline-reloaded | Quantopian 開源後接手；安裝複雜（需要 bcolz 等）；偏美股市場 |
| 自寫事件迴圈 | 控制最強、能保證與實盤一致；MVP 階段工作量大 |
| QuantConnect Lean (Python) | C# 為主、與 .NET 整合；超出本專案技術棧 |

### 4.3 理由
- PM 附錄 A 已決定 backtrader，符合「事件驅動 + Python」雙條件。
- FR-BT-02 要求「回測使用與實盤相同的策略物件」── backtrader 支援把 `BaseStrategy` 包成 backtrader `Strategy`，介面接的算自然（但實際上 backtrader 自己的 Strategy 類別才是主導）。
- 已知 backtrader 維護放緩，但對 v1.0 標的數（10 檔以內）、時間範圍（10 年日線）完全綽綽。

### 4.4 踩坑風險

**Risk A：backtrader 的 fill model 預設用「下一根 bar 的 open」很好 ── 但本專案的 PM I-11 規定 T+1 開盤價成交，需要驗證 backtrader 預設行為與我們的 `FillEngine` 是否一致**。
- 否則「實盤模擬」與「回測」分歧（NFR-MNT-02 對齊不通過）。

**Risk B：backtrader 內建 commission scheme 設計成「按筆固定」或「按比例」，可能不符台股的 0.1425% + 賣方 0.3% 證交稅組合**。
- 需自寫 `CommInfo` subclass。

**Risk C：backtrader 的 cerebro engine 一次跑完全部標的，記憶體吃滿**。
- v1.0 規模可忽略；若 v3.0 擴展到 100+ 標的時要重評。

**Risk D：backtrader 沒有原生 multi-currency 支援**。
- v1.0 標的池有台股（TWD）+ 美股（USD）混合；需自行做匯率轉換。

### 4.5 緩解
- **共用 FillEngine**：把 T+1 開盤成交、跳空保護、滑價、手續費全部抽到 `core/trading/fill_engine.py`。backtrader 用一層 adapter 把 cerebro 的「下單事件」轉接到我們的 FillEngine。這樣保證回測與 SimulatedBroker **走同一份程式碼**。
- **commission subclass**：寫 `TwCommissionInfo(bt.CommInfoBase)` 與 `UsCommissionInfo`，依 side 計算稅金。
- **多幣別**：在 backtrader 內部把所有金額轉成 TWD（呼叫 `FxService.to_twd(amount, currency)`）作為 portfolio value 計算單位；單個 symbol 仍以原幣計。
- **若日後跑大量 walkforward / 參數掃描 → 評估 vectorbt**。MVP 不引入。

---

## 5. K 線圖表 — pyqtgraph vs mplfinance vs lightweight-charts-python

### 5.1 決策
**主互動 K 線：pyqtgraph（v1.5）；回測靜態圖匯出：mplfinance；E2E 場景仍考慮 lightweight-charts-python 但暫不採用**。

### 5.2 替代方案
| 候選 | 評估 |
| --- | --- |
| **pyqtgraph** | 與 PySide6 同 Qt 引擎；GPU 加速；互動極順；K 線需自寫 GraphicsItem |
| mplfinance | matplotlib 包裝，K 線 ready-to-use；但對 Qt 整合差、滑鼠互動不順 |
| lightweight-charts-python | TradingView 開源的 chart 引擎包裝；視覺極佳；但依賴 WebView2、與 PySide6 整合等於另開一個瀏覽器 process |
| plotly + QWebEngineView | 同上 WebView 包袱；archive 操作不順 |
| FinPlot | 基於 pyqtgraph 的金融專用包裝；社群小 |

### 5.3 理由
- FR-CH-04 (十字游標)、FR-CH-05 (縮放平移)：pyqtgraph 原生最順；mplfinance 互動性差。
- FR-CH-06 sparkline 迷你縮圖：用 pyqtgraph 同一個元件套用不同尺寸即可；mplfinance 每個都重畫一次很慢。
- 主題切換：pyqtgraph 顏色全部可動態改 palette，與 ThemeManager 整合容易。
- v1.5 Exit Criteria「K 線圖渲染 1000 根 < 200ms」：pyqtgraph 在普通筆電可達 60+ fps，安全。
- 回測結果輸出 PNG 給人看（FR-BT-05），用 mplfinance 比較漂亮，且檔案小。

### 5.4 踩坑風險

**Risk A：pyqtgraph 沒有內建 K 線元件**。
- 必須自寫 `CandleStickItem(pg.GraphicsObject)`，~200 行；參考社群範例（finplot 等）。

**Risk B：高頻 mouse move 事件對 RSI/MACD 副圖 tooltip 更新會卡**。
- 需要 throttle（每 50ms 才更新一次 tooltip）。

**Risk C：時間軸（datetime）與 pyqtgraph 預設的 float x-axis 整合需自寫 AxisItem**。
- 一般 charting library 都已內建這層；pyqtgraph 是 general purpose 沒有。

**Risk D：mplfinance 依賴 matplotlib，frozen 後 backend 處理需注意（用 Agg 不用 Qt5Agg）**。

**Risk E：FR-CH-03「台股紅漲綠跌、美股綠漲紅跌」── pyqtgraph 元件需依 market 動態切色**。
- 多 chart 同時顯示時要小心 state pollution。

### 5.5 緩解
- M5.7a 第一週把「pyqtgraph 自寫 K 線元件」當第一個 deliverable，先求能畫對；後續再加技術指標。
- 把 CandleStickItem 寫成接受 `(palette, market)` 參數 → 切 market 時整個重畫，不在 item 內部判 market（避免狀態跨 chart）。
- mplfinance 寫成獨立 `backtest/png_exporter.py`，與主圖完全隔離；只在「匯出 PNG」按鈕觸發時用。

---

## 6. Anthropic SDK 整合 (v2.0)

### 6.1 決策
- **`anthropic` 官方 Python SDK (async client)**
- **Model：`claude-haiku-4-5`**（FR-NS-07 預設；可從設定頁切到 sonnet）
- **Prompt caching：啟用 system prompt 段落 cache**
- **Output：要求 JSON 格式並用 pydantic 驗證**

### 6.2 為什麼這樣選

| 議題 | 決策 | 理由 |
| --- | --- | --- |
| 用哪家 LLM | Anthropic Claude | PM 拍板；本人有偏好（context 強、JSON 穩） |
| sync vs async client | async (`AsyncAnthropic`) | 與 NewsPipeline 的 asyncio 整合 |
| 模型 | claude-haiku-4-5 預設 | 成本最低；每日預算 $0.30，haiku 約可分析 30~50 篇 |
| Structured output | 在 system prompt 強制 JSON + pydantic schema 驗證 | Anthropic 雖支援 tool use 但對 simple JSON 採 explicit prompt 比較直接 |
| Prompt caching | 啟用 system prompt 段落 cache | 同一個 system prompt 重複用，節省 90% input cost |

### 6.3 Prompt Caching 策略細節

對應 FR-NS-09 + PM C 文中提及。

```python
# system prompt 結構 (~3000 tokens)
SYSTEM_PROMPT = """
[Persona] You are a financial news analyst...
[Output Schema] Return JSON: { tickers: [...], sentiment: -1..1, ... }
[Few-shot examples]
  Example 1: ... → {...}
  Example 2: ... → {...}
  Example 3: ... → {...}
[Rules] 1. Do not invent tickers; ...
"""

# 呼叫時：
message = client.messages.create(
    model="claude-haiku-4-5",
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}     # ← 標記 cache
        }
    ],
    messages=[{"role": "user", "content": article.raw_text}],
    max_tokens=1500,
)
```

成本估算（假設 haiku-4-5 定價類似 haiku-3-5）：
- system prompt 3000 tokens × 第一次 $0.80/M = $0.0024（cache write）
- 後續 87 篇命中 cache → input cost 變 $0.08/M × 3000 = $0.00024 per call → 省 90%
- 加上 article 平均 1000 tokens × $0.80/M = $0.0008
- output 平均 500 tokens × $4/M = $0.0020
- **每篇平均 ~$0.003**，87 篇 = $0.26 → 落在 $0.30 budget 內

### 6.4 踩坑風險

**Risk A：Claude 偶有 JSON 中含 markdown code fence ` ```json ... ``` `**。
- pydantic parse 會掛掉。
- 緩解：先用 regex 剝 code fence，再 `json.loads`，再 pydantic validate。

**Risk B：Claude 對「未提及任何 ticker」的新聞會「強行擠出一個 ticker」**。
- LLM 幻覺（PM 風險表）。
- 緩解：(a) system prompt 明確「若新聞無明確 ticker → tickers=[]」；(b) TickerMapper 要求 confidence ≥ 0.7 才入排序。

**Risk C：Anthropic rate limit (free tier 50 req/min)**。
- 假設一次抓 100 篇 → 兩分鐘內打完。
- 緩解：max_concurrency=3 + `asyncio.Semaphore`，已內建 retry。

**Risk D：token 估算偏差 → 預算超支**。
- 緩解：CostGuard 在每次 response 後從 `response.usage` 取得真實 tokens，更新 `llm_cost_daily`。precheck 用 `tiktoken` 或粗估（1 token ≈ 4 char）。

**Risk E：v2.0 上線時 Anthropic SDK 已更新，model name 可能變動**。
- 緩解：model 寫在 config 不寫死；保留 `claude-sonnet-4-5` 等 fallback。

**Risk F：Anthropic API key 洩漏風險**。
- 緩解：DPAPI 加密儲存於 `secrets.dat`；不允許 log 中 print key（FR-NS-13 + NFR-SEC-02）。

### 6.5 緩解總結
- 所有 LLM 互動透過 `LlmClient` 介面 → 未來換 model / vendor 不影響上層。
- 嚴格 schema 驗證 + 失敗 retry 2 次（FR-NS-12）。
- CostGuard 雙重保險：precheck（估算）+ postcheck（真實）。
- 在開發環境用 `MockLlmClient` 跑單元測試，永不打真實 API。

---

## 7. Shioaji 整合 (v1.5)

### 7.1 決策
- 使用 **永豐 shioaji 官方 Python SDK**
- Broker 抽象：`ShioajiBroker` 在 v1.5 加入，與 SimulatedBroker 共用 `BaseBroker` 介面
- CA 憑證流程：使用者於設定頁輸入路徑與密碼，DPAPI 加密儲存
- 登入時機：lazy（首次 `place_order` 才登入），但 `ShioajiConnectionChecker` 在切換 LIVE 前主動驗證

### 7.2 為什麼分到 v1.5

對應 `release_plan.md` v1.5 Entry Criteria。理由：
- v1.0 不需實盤 → 不需 Shioaji，省一大票風險。
- Shioaji 需要 CA 憑證簽署（一年期），新使用者申請週期 1~2 週。
- Shioaji 套件含 native DLL，cx_Freeze 整合風險高（見 §2 Risk A）。

### 7.3 踩坑風險

**Risk A：Shioaji 套件內含 `solshioaji.dll` 等 native DLL，cx_Freeze 不一定能正確帶入**。
- 症狀：在開發機可跑、frozen 後 `shioaji.Shioaji()` 直接 segfault 或 ImportError。
- 緩解：M0 預作 PoC（frozen + import shioaji + 不登入，純載入 module 看是否成功）。

**Risk B：CA 憑證處理**。
- Shioaji 要求 `.pfx` 檔案 + 密碼 → 必須儲存於 fixed path。
- CA 憑證有效期 1 年，過期後 API 全部失效。
- 緩解：(a) PM 已要求 SystemStatus 顯示「CA 憑證到期天數」；(b) 設定頁顯示到期提醒；(c) 寫 audit_log 記錄 CA 更新時點。

**Risk C：Shioaji 登入流程繁複**：`api.login(person_id, password)` → `api.activate_ca(ca_path, ca_passwd, person_id)` → 還要 `api.fetch_contracts()` 拉合約清單（耗時 5~10 秒）。
- 第一次登入特別慢；GUI 上要有 progress 顯示。
- 緩解：將登入流程封裝成 `ShioajiSessionManager`，提供 async API + 進度回報事件。

**Risk D：條件停損單（FR-EX-01）API 形式**。
- Shioaji 的條件單 (`api.place_cond_order`) 文件不算詳盡，需參考 sample code 與社群 issue。
- 緩解：M5（v1.5 第一個 milestone）先做小額（1 股）的條件單 PoC。

**Risk E：API 配額限制**。
- 永豐免費版有 query / order 配額；超量會降級或被擋。
- 緩解：寫一個 `ShioajiRateLimiter` 包裝（每秒不超過 5 query）；超出 → wait + log。

**Risk F：Shioaji 對 macOS / Linux 不支援**，但這對本專案沒影響（Windows-only）。

**Risk G：Shioaji 登入要連線到永豐伺服器，公司網路防火牆可能擋**。
- 緩解：設定頁加「測試連線」按鈕；明確告知防火牆需要允許的 host 與 port。

**Risk H：模擬下單 vs 實盤下單的 API 差異**。
- 永豐有自己的 simulation account（PM 開放議題 #1），與本系統的 SimulatedBroker 是兩件事。
- v1.5 設計：`ShioajiBroker` 一律打實盤；模擬走本系統 `SimulatedBroker`，不混用永豐 simulation。

### 7.4 緩解總結
- **M0 spike**：1 小時的 frozen + shioaji import 測試（不登入）→ 確認打包不爆。
- **M5 spike**：1 天的小額條件單 PoC（v1.5 第一週）→ 確認 API 流程通暢。
- **保留 simulation 之路**：永豐 simulation account 暫不整合，留作未來 option。
- **完整告警**：CA 到期 < 30 天就寄 Email；< 7 天每天提醒。

---

## 8. Schema Migration 工具 — alembic vs 自寫

### 8.1 決策
**自寫**（v1.0）；介面預留以便未來切換 alembic。

### 8.2 替代方案
| 候選 | 評估 |
| --- | --- |
| **alembic** | 業界標準；需先有 sqlalchemy；自動偵測 schema diff；上線級成熟 |
| yoyo-migrations | 純 SQL；簡潔；社群小 |
| 自寫 | 完全控制；~150 行；無外部依賴 |

### 8.3 理由
- v1.0 **不引入 sqlalchemy ORM**（直接寫 SQL + sqlite3 module），避免兩套 schema model 同步。
- alembic 強制 sqlalchemy → 引入後 ORM 風格會擴散到整個 codebase，over-engineering。
- 自寫 MigrationRunner 在 `data_design.md` §3 已詳述，~150 行可滿足：版本表、順序執行、強制備份、rollback。
- 介面預留：`schema_version` 表結構與 alembic 的 `alembic_version` 概念一致，未來若引入 sqlalchemy 可手動 sync 表內容。

### 8.4 踩坑風險

**Risk A：自寫 migration 缺少 schema diff 偵測**。
- 工程師手寫 DDL 時忘記更新 schema_version → 升級遺漏。
- 緩解：(a) 規定 `MIGRATIONS` list 在 `__init__.py` 維護；(b) CI 加 lint 檢查 version 嚴格遞增。

**Risk B：自寫 rollback 不可靠**。
- ALTER TABLE 在 SQLite 限制多（不能 DROP COLUMN < 3.35），rollback 經常做不到。
- 緩解：強制 pre-migration backup（已在 §3 規範）；rollback 改用「restore backup」而非真執行 down_sql。

**Risk C：未來引入 sqlalchemy + alembic 時，自寫 schema_version 與 alembic_version 衝突**。
- 緩解：未來引入時手動 INSERT alembic_version 對齊；過渡期可接受。

### 8.5 緩解
- M0 一次性把 §3 的 MigrationRunner 寫好寫紮實，附 unit test（測「乾淨資料庫 → migrate → schema 正確」+「升級失敗 → 自動還原備份」兩種情境）。
- README 寫清楚「新增 migration 的 SOP」。

---

## 9. DPAPI 加密細節

### 9.1 決策
- 使用 **pywin32** 套件包裝 Windows DPAPI
- **CryptProtectData / CryptUnprotectData** 兩個 API
- 加密 scope：**CURRENT_USER**（同一台機器同一個 user 才能解密）
- 解密失敗 fallback：清空 secrets.dat，**強制重新輸入**所有密碼

### 9.2 為什麼選 DPAPI 不選 Fernet

PM `requirements.md` FR-NT-02 寫「Windows DPAPI 或 Fernet」。

| 候選 | 評估 |
| --- | --- |
| **Windows DPAPI** | OS 級別、無需自管 key；缺點：跨機器不可用、user 帳號損毀就沒了 |
| Fernet (cryptography) | 跨平台；需要自管 master key（藏哪？也是個問題） |
| keyring (Windows Credential Manager) | 內建 secure；但每個 key 一個 entry，secrets 多時不好管 |

選 DPAPI 因為：
- 本專案 Windows-only，無跨平台需求。
- DPAPI 不需要管理 master key，最省心。
- 若 user 帳號損毀 → 整個 Windows 都掛了，secrets.dat 不解密本身就不是大問題（使用者重灌就重輸入）。

### 9.3 secrets.dat 檔案結構

```
secrets.dat (binary 檔)
├── header (8 bytes magic: "STSEC001")
├── DPAPI-encrypted blob (內容是 JSON):
│   {
│     "shioaji.api_key":     "<plaintext>",
│     "shioaji.secret_key":  "<plaintext>",
│     "shioaji.person_id":   "<plaintext>",
│     "shioaji.password":    "<plaintext>",
│     "shioaji.ca_password": "<plaintext>",
│     "smtp.host":           "<plaintext>",
│     "smtp.port":           "587",
│     "smtp.username":       "<plaintext>",
│     "smtp.password":       "<plaintext>",
│     "anthropic.api_key":   "<plaintext>"
│   }
```

寫入：`win32crypt.CryptProtectData(plaintext_bytes, None, None, None, None, 0)`
讀取：`win32crypt.CryptUnprotectData(encrypted_bytes, None, None, None, 0)`

### 9.4 踩坑風險

**Risk A：CryptUnprotectData 失敗時的 fallback**。
- 失敗情境：(a) 換了 user 帳號；(b) Windows 重灌後 user SID 變了；(c) 檔案損毀。
- 緩解：try/except → 顯示對話框「密碼解密失敗，請重新輸入設定」→ 把 secrets.dat rename 成 `.dat.bak`（保留 forensic）+ 觸發 OnboardingWizard。

**Risk B：DPAPI 加密的資料無法跨機器移轉**。
- 使用者換電腦 → secrets.dat 無法解密。
- 緩解：在文件明示「換電腦需重新輸入所有密碼」；config.json 因為是明文可直接帶過去。

**Risk C：pywin32 在 frozen 後可能 import 失敗**。
- pywin32 依賴 `pythoncomXX.dll`、`pywintypesXX.dll`。
- 緩解：cx_Freeze 的 `include_files` 顯式指定這些 DLL；M0 PoC 包含這項驗證。

**Risk D：密碼欄位被 log / debug 印出**。
- 緩解：(a) `SecretsManager.get()` 不允許在 logger 內呼叫；(b) 統一在 settings page 顯示為 `****`（NFR-SEC-02）。

**Risk E：JSON 內含 `password` 鍵的字串容易被 git accidentally committed**。
- 緩解：在 .gitignore 加入 `*.dat`、`secrets*`；commit hook 檢查內容。

### 9.5 緩解總結
- 寫一個 `SecretsManager` 介面（`get / set / remove / has`）封裝 DPAPI；上層 service 永遠透過介面取密碼，**不直接呼叫 pywin32**。
- 測試用 `InMemorySecretsManager`，繞過 DPAPI。
- 解密失敗 → 友善引導使用者重輸入；不要直接 crash。

---

## 10. 其他次要決策（彙整）

### 10.1 SMTP 套件 — aiosmtplib vs smtplib

**aiosmtplib**（與 asyncio 整合）；smtplib 是 sync，在 GUI 內會卡 event loop。

### 10.2 HTTP client — httpx vs aiohttp vs requests

**httpx**（asyncio 友善 + sync 也支援）；aiohttp 也行，但 httpx 學習曲線更友善 + 與 trafilatura 整合好。

### 10.3 RSS 解析 — feedparser

**feedparser**，業界標準 30 年了，無爭議。

### 10.4 HTML 主文萃取 — trafilatura

**trafilatura**（PM 附錄 A 已列）；勝於 newspaper3k / readability 的開源實作，準確率高、相依少。

### 10.5 標題相似度 — rapidfuzz

**rapidfuzz**（C 加速，比 fuzzywuzzy 快 10x）；對 87 篇文章去重 < 100ms。

### 10.6 Reddit API — praw vs 純 JSON

**praw**（read-only mode 不需 client credential）；praw 對 rate limit 處理較佳。

### 10.7 SEC EDGAR — sec-edgar-downloader

**sec-edgar-downloader**（PM 附錄 A 已列）；主要抓 8-K filings。

### 10.8 Logging — Python stdlib logging

**stdlib logging + TimedRotatingFileHandler**；不引入 loguru 等（理由：MVP 階段無強動機）。

### 10.9 設定檔 — config.json + pydantic-settings

**config.json 明文 + `pydantic-settings` 解析**；schema-驗證、預設值、env override 一站搞定。

### 10.10 測試框架 — pytest + pytest-qt

**pytest**（已是 Python 業界標準）；pytest-qt 用於 GUI 元件測試（NFR-MNT-01 70% 覆蓋率要求 GUI 部分有覆蓋）。

### 10.11 Lint / type — ruff + mypy

**ruff**（取代 flake8 + isort + 部分 pylint）；**mypy** strict mode；PM 附錄 A 已列。

### 10.12 任務排程 — apscheduler (內部) + Windows Task Scheduler (外部)

**apscheduler `AsyncIOScheduler`**（在 GUI 內顯示「下次執行」、跑新聞收集、跑 24h auto-revert）；
**Windows Task Scheduler**（GUI 沒開時的可靠觸發）；兩者**對同一個 job 不可重複觸發**，避免互相干擾：
- daily_run 與 reconcile 一律由 Windows Task Scheduler 觸發（CLI mode）。
- apscheduler 只用於 GUI 內部的 24h auto-revert、UI 顯示用，**不執行下單**。

### 10.13 Pandas 版本

**鎖定 pandas 2.x（最新 stable）**；但需要先驗證 pandas-ta 相容性（§3 Risk C）。

### 10.14 yfinance 風險

yfinance 是 unofficial scraper，**Yahoo 隨時可能改 endpoint 讓它壞掉**。
緩解：fallback 已設計（Shioaji 為 TW primary、yfinance 為 fallback；US 則只能 yfinance）→ 若 yfinance 整個壞了，影響 US 完全 down，台股 fallback 也 down，需手動修。**保留 v3.x 引入付費 API（Polygon, Alpaca）的 option**。

---

## 11. 整體技術風險快查表

| 風險 | 影響範圍 | 機率 | 優先處理 milestone |
| --- | --- | --- | --- |
| cx_Freeze + native DLL 打包失敗 | 整個專案無法交付 | 中 | M0 第一週 PoC |
| Shioaji 整合卡住 | v1.5 阻塞 | 中 | M5 第一週 PoC |
| qasync 與 PySide6 整合 bug | GUI 階段卡住 | 低-中 | M3 第一週驗證 |
| pandas-ta 與 TradingView 數值不一致 | v1.5 Exit Criteria 不過 | 中 | M5.7 對拍測試 |
| Anthropic API 成本失控 | v2.0 預算炸 | 低（有 CostGuard） | M5.5b 整合測試 |
| yfinance 被 Yahoo 改壞 | 全產品掛 | 中-高（時間維度） | 接受風險；保留付費 API option |
| DPAPI 解密失敗 | 設定遺失 | 低 | OnboardingWizard fallback |
| backtrader 與 SimulatedBroker fill 邏輯偏離 | 回測結果不可信 | 中 | M1 + M2 對拍 |
| SQLite 損毀 | 全部歷史資料遺失 | 低（但後果嚴重） | M0 BackupService |
| 24h 自動回 SIM 計時器在程式關閉時遺失 | LIVE 模式無限持續，誤觸下單 | 中 | M3：apscheduler 持久化 + 啟動時補檢查 |

---

## 12. 未決議題（留給 SA / 開發中決策）

下列議題目前**先不決定**，留作 v1.5 / v2.0 開發時依當時情境拍板：

1. **永豐 Shioaji 官方 simulation account 是否整合**（PM 開放議題 #1）── 預設不整合；若 v1.5 實盤前發現本系統模擬與實盤偏離 > 20% 再考慮接入。
2. **paid news API 升級時機**（PM 開放議題 #6）── v2.0 paper 跑 3 個月後依品質評估。
3. **Sonnet 混合策略**（PM 開放議題 #7）── v2.0 後若 haiku 對某類新聞分析品質差，再加 routing：重要 catalysts（earnings/M&A/8-K）走 sonnet、其他走 haiku。
4. **中文新聞**（PM 開放議題 #8）── v3.x 之後再評估。
5. **持倉相關新聞優先告警**（PM 開放議題 #9）── v2.0 release 後一個 minor version 加入。
