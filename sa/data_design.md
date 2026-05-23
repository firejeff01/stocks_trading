# 資料設計 (Data Design)

| 項目 | 內容 |
| --- | --- |
| 文件版本 | v0.1 |
| 建立日期 | 2026-05-23 |
| 對應 PM 版本 | `pm/requirements.md` v0.3（§7 資料模型）、`pm/requirements_review.md` I-1/I-2/I-8/I-9/I-11/I-12/I-14、`pm/release_plan.md` v1.0（§6 資料庫遷移策略） |
| 文件範圍 | SQLite schema DDL、migration 機制、雙帳本隔離、時區處理、快取與備份策略、訊號狀態機；不含 ORM 程式碼（見 `component_design.md`） |

## 0. 設計原則

1. **All timestamps 統一 UTC（ISO-8601 with 'Z' suffix）**；顯示層才轉成 local time（PM I-7、I-12）。
2. **單一 SQLite 檔（`app.db`）**，不拆分；表用 `mode` 欄位 / FK 達成雙帳本隔離。
3. **所有金額用 `TEXT` 儲存為 Decimal 字串**，避免 SQLite REAL 浮點誤差。
4. **所有 enum 用 `TEXT` + CHECK constraint**，禁用 INTEGER enum（debug 友善）。
5. **不用 ON DELETE CASCADE 跨大表**，避免誤刪歷史資料；改在 application 層 soft-delete。
6. **schema_version 從 v1.0 第一天就有**，是 migration 機制的核心。
7. v2.0 新聞相關 5 張表 schema **在 v1.0 就建空表**（PM `release_plan.md` §6.3 + 本文件 §3 migration 策略）→ v2.0 升級不需 schema migration，降低風險。

---

## 1. 完整 Schema DDL

依下面列出的順序執行（FK 必須先有 parent table）。所有 DDL 都包在 `0001_initial.sql` migration 內。

### 1.1 schema_version（migration 機制核心）

```sql
CREATE TABLE schema_version (
    version       INTEGER PRIMARY KEY,        -- 1, 2, 3, ... 嚴格單調遞增
    name          TEXT    NOT NULL,           -- "0001_initial", "0002_add_xxx"
    applied_at    TEXT    NOT NULL,           -- ISO-8601 UTC
    checksum      TEXT    NOT NULL,           -- migration script 內容 SHA-256
    success       INTEGER NOT NULL DEFAULT 1, -- 0 = rolled back
    error_message TEXT
);

-- 啟動時若此表不存在 → 視為 fresh install，跑全部 migration
-- 啟動時讀 MAX(version) → 比對程式內建版本，差距則跑 missing migration
```

### 1.2 accounts（雙帳本隔離的根節點）

```sql
CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,                   -- "Default-SIM" / "Default-LIVE"
    mode            TEXT    NOT NULL                    -- 'SIMULATION' | 'LIVE'
                       CHECK (mode IN ('SIMULATION', 'LIVE')),
    broker          TEXT    NOT NULL,                   -- 'simulated' | 'shioaji' | 'email_us'
    currency        TEXT    NOT NULL                    -- 'TWD' | 'USD'
                       CHECK (currency IN ('TWD', 'USD')),
    init_capital    TEXT    NOT NULL,                   -- Decimal 字串，例：'100000.00'
    current_equity  TEXT    NOT NULL,                   -- 即時資產淨值快照（每日 PnL snapshot 後更新）
    is_frozen       INTEGER NOT NULL DEFAULT 0,         -- 1 = 凍結（24h auto revert 後的 LIVE）
    created_at      TEXT    NOT NULL,                   -- ISO-8601 UTC
    UNIQUE (mode, broker, currency)
);

-- v1.0 初次啟動 seed 四列（雙帳本 × 雙幣別）：
-- (Default-SIM-TW,   SIMULATION, simulated, TWD, '100000.00', '100000.00', 0)
-- (Default-SIM-US,   SIMULATION, simulated, USD,   '3000.00',   '3000.00', 0)
-- (Default-LIVE-TW,  LIVE,       shioaji,   TWD,       '0.00',       '0.00', 1)
-- (Default-LIVE-US,  LIVE,       email_us,  USD,       '0.00',       '0.00', 1)
-- LIVE 預設 is_frozen=1，等 v1.5 首次切換到 LIVE 時才解凍 init_capital 由使用者輸入
```

**雙帳本隔離的工程實作（對應 PM I-1）**：
- 任何查詢部位 / 訂單 / 訊號的 service 都必須帶 `mode` 參數 → 透過 `account_id` 過濾。
- ModeManager 切換時不動 DB，只改 `mode_state.json`；UI 重新訂閱 `account_id` 即可。
- 24h 自動回 SIM 時，LIVE 帳本資料保留，僅 `accounts.is_frozen = 1`（UI 標示「凍結」）；下次手動切回 LIVE 時 `is_frozen = 0`。

### 1.3 positions

```sql
CREATE TABLE positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    symbol          TEXT    NOT NULL,
    market          TEXT    NOT NULL                    -- 'TW' | 'US'
                       CHECK (market IN ('TW', 'US')),
    qty             INTEGER NOT NULL,                   -- 正數 = long；MVP 不支援 short
    avg_price       TEXT    NOT NULL,                   -- Decimal
    stop_loss       TEXT,                                -- Decimal，nullable
    opened_at       TEXT    NOT NULL,                   -- 首次建倉時間 UTC
    last_updated_at TEXT    NOT NULL,                   -- 任何加減倉、停損調整都更新
    UNIQUE (account_id, symbol)                          -- 一檔股票同帳戶只有一筆 row
);
CREATE INDEX idx_positions_account ON positions (account_id);
CREATE INDEX idx_positions_symbol  ON positions (symbol, market);
```

### 1.4 orders

```sql
CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id          INTEGER NOT NULL REFERENCES accounts(id),
    signal_id           INTEGER REFERENCES signals(id), -- 可為 NULL（手動下單時）
    mode                TEXT    NOT NULL                -- 冗餘存放，方便篩選
                           CHECK (mode IN ('SIMULATION', 'LIVE')),
    symbol              TEXT    NOT NULL,
    market              TEXT    NOT NULL CHECK (market IN ('TW', 'US')),
    side                TEXT    NOT NULL CHECK (side IN ('BUY','SELL','COVER')),
    order_type          TEXT    NOT NULL                -- 'LIMIT' | 'MARKET' | 'MOC' | 'MOO'
                           CHECK (order_type IN ('LIMIT','MARKET','MOC','MOO')),
    qty                 INTEGER NOT NULL,
    price               TEXT,                            -- LIMIT 才有；MARKET 為 NULL
    stop_loss           TEXT,                            -- 進場單附帶的停損價
    status              TEXT    NOT NULL                -- 見 §4 狀態機
                           CHECK (status IN (
                               'PENDING_T+1_OPEN',
                               'PENDING_SHIOAJI_FILL',
                               'MANUAL_PENDING',
                               'FILLED',
                               'UNFILLED_GAP',
                               'REJECTED_BY_BROKER',
                               'CANCELLED',
                               'FAILED'
                           )),
    rejection_reason    TEXT,
    shioaji_order_id    TEXT,                            -- v1.5 LIVE 才有
    fill_price          TEXT,                            -- 實際成交價（含滑價後）
    commission          TEXT,                            -- 手續費
    tax                 TEXT,                            -- 稅（台股賣出 0.3%）
    placed_at           TEXT    NOT NULL,                -- UTC
    filled_at           TEXT,                            -- UTC，nullable
    expires_at          TEXT,                            -- MANUAL_PENDING 的過期時間（PM I-3）
    metadata_json       TEXT                             -- 額外資訊（如 Pattern filter 通過記錄）
);
CREATE INDEX idx_orders_account_status ON orders (account_id, status);
CREATE INDEX idx_orders_signal         ON orders (signal_id);
CREATE INDEX idx_orders_placed_at      ON orders (placed_at);
```

### 1.5 signals

```sql
CREATE TABLE signals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id         TEXT    NOT NULL,                -- 'dual_momentum_v1' | 'news_promoted_<id>'
    symbol              TEXT    NOT NULL,
    market              TEXT    NOT NULL CHECK (market IN ('TW', 'US')),
    side                TEXT    NOT NULL CHECK (side IN ('BUY','SELL','COVER')),
    target_price        TEXT    NOT NULL,                -- Decimal
    stop_loss_price     TEXT,
    suggested_qty       INTEGER NOT NULL,
    reason              TEXT    NOT NULL,                -- 顯示於 Email
    generated_at        TEXT    NOT NULL,                -- UTC
    status              TEXT    NOT NULL                 -- 見 §4 狀態機
                           CHECK (status IN (
                               'PENDING_RISK_CHECK',
                               'PENDING_T+1_OPEN',
                               'PENDING_SHIOAJI_FILL',
                               'MANUAL_PENDING',
                               'FILLED',
                               'UNFILLED_GAP',
                               'REJECTED_RISK',
                               'EXPIRED',
                               'FAILED'
                           )),
    filter_passed_json  TEXT,                             -- ["SinglePositionRisk","TotalExposure","DailyLossLimit"]
                                                          -- 對應 PM I-5
    mode                TEXT    NOT NULL CHECK (mode IN ('SIMULATION','LIVE')),
    account_id          INTEGER NOT NULL REFERENCES accounts(id),
    notified_at         TEXT                              -- Email 已寄出時間
);
CREATE INDEX idx_signals_status        ON signals (status);
CREATE INDEX idx_signals_generated_at  ON signals (generated_at);
CREATE INDEX idx_signals_strategy      ON signals (strategy_id);
CREATE INDEX idx_signals_account       ON signals (account_id);
```

### 1.6 daily_pnl

```sql
CREATE TABLE daily_pnl (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    date            TEXT    NOT NULL,                    -- 'YYYY-MM-DD'（依市場交易日，以 Asia/Taipei 為準）
    equity          TEXT    NOT NULL,                    -- 當日收盤後總資產 Decimal
    cash            TEXT    NOT NULL,
    realized_pnl    TEXT    NOT NULL DEFAULT '0',        -- 當日已實現損益
    unrealized_pnl  TEXT    NOT NULL DEFAULT '0',        -- 當日未實現損益
    drawdown_pct    TEXT,                                 -- 相對歷史高點的回撤
    snapshotted_at  TEXT    NOT NULL,                    -- UTC
    UNIQUE (account_id, date)
);
CREATE INDEX idx_daily_pnl_date ON daily_pnl (date);
```

### 1.7 kbars_cache

```sql
CREATE TABLE kbars_cache (
    symbol          TEXT    NOT NULL,
    market          TEXT    NOT NULL CHECK (market IN ('TW','US')),
    date            TEXT    NOT NULL,                    -- 'YYYY-MM-DD'，交易日
    open            TEXT    NOT NULL,
    high            TEXT    NOT NULL,
    low             TEXT    NOT NULL,
    close           TEXT    NOT NULL,
    volume          INTEGER NOT NULL,
    source          TEXT    NOT NULL CHECK (source IN ('shioaji','yfinance')),
    fetched_at      TEXT    NOT NULL,                    -- UTC
    PRIMARY KEY (symbol, market, date)
);
CREATE INDEX idx_kbars_fetched_at ON kbars_cache (fetched_at);
```

**快取過期策略（PM §快取策略）**：
- 當日交易日（market open）：cache 視為 hot，5 分鐘內 valid（避免分鐘級重抓）。
- 歷史完整交易日（market closed 後）：cache 永久 valid（不會變動）。
- 強制刷新（FR-DL-04）：UI 按鈕觸發 `DELETE FROM kbars_cache WHERE symbol = ? AND market = ?`。
- 清理：每週日 cli `cleanup` 排程刪除 5 年前的 kbars（保留 5 年 enough for 252 lookback + 回測）。

### 1.8 app_log（系統日誌）

```sql
CREATE TABLE app_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,                    -- UTC
    level           TEXT    NOT NULL                     -- 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'
                       CHECK (level IN ('DEBUG','INFO','WARN','ERROR','CRITICAL')),
    module          TEXT    NOT NULL,                    -- 'strategy.runner' / 'broker.shioaji' / ...
    message         TEXT    NOT NULL,
    context_json    TEXT                                  -- 額外 metadata
);
CREATE INDEX idx_app_log_ts    ON app_log (ts);
CREATE INDEX idx_app_log_level ON app_log (level);
```

**保留策略（PM I-14）**：
- 預設保留 90 天；cli `cleanup` 每週執行 `DELETE FROM app_log WHERE ts < datetime('now', '-90 days')`。
- 設定頁可調整保留天數（30~365）。
- 同時提供「匯出近 N 天 zip」功能（從 GUI 設定頁觸發）。

### 1.9 audit_log（敏感操作審計）— 對應 PM E-3

```sql
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,                    -- UTC
    actor           TEXT    NOT NULL,                    -- 'user' | 'system' | 'scheduler'
    action          TEXT    NOT NULL                     -- enum 字串
                       CHECK (action IN (
                           'mode_switch',
                           'risk_param_change',
                           'settings_change',
                           'watchlist_promote',
                           'account_reset',
                           'backup_restore',
                           'strategy_param_change'
                       )),
    target          TEXT,                                 -- 'account.id=1', 'signal.id=42'
    before_json     TEXT,
    after_json      TEXT,
    success         INTEGER NOT NULL DEFAULT 1,
    error_message   TEXT
);
CREATE INDEX idx_audit_ts     ON audit_log (ts);
CREATE INDEX idx_audit_action ON audit_log (action);

-- 不參與一般 cleanup；保留 365 天（PM E-3）
-- 清理由獨立 job 跑：DELETE FROM audit_log WHERE ts < datetime('now', '-365 days')
```

### 1.10 news_articles (v2.0；v1.0 預建空表)

```sql
CREATE TABLE news_articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL                     -- enum
                       CHECK (source IN (
                           'yfinance','cnbc','reuters','ars_technica',
                           'techcrunch','the_verge','reddit','edgar'
                       )),
    url             TEXT    NOT NULL,
    url_hash        TEXT    NOT NULL,                    -- sha256(url)[:16]，去重用
    title           TEXT    NOT NULL,
    published_at    TEXT    NOT NULL,                    -- UTC
    lang            TEXT    NOT NULL,                    -- ISO-639-1: 'en','zh',...
    raw_text        TEXT    NOT NULL,                    -- 完整原文（壓縮？v1.0 不壓縮，文章本身不大）
    fetched_at      TEXT    NOT NULL,                    -- UTC
    UNIQUE (url_hash)
);
CREATE INDEX idx_news_source        ON news_articles (source);
CREATE INDEX idx_news_published_at  ON news_articles (published_at);
CREATE INDEX idx_news_fetched_at    ON news_articles (fetched_at);
```

### 1.11 news_analysis (v2.0)

```sql
CREATE TABLE news_analysis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id          INTEGER NOT NULL REFERENCES news_articles(id),
    model               TEXT    NOT NULL,                 -- 'claude-haiku-4-5'
    sentiment           REAL    NOT NULL,                 -- -1.0 ~ 1.0（這個用 REAL 可接受，僅 ranking）
    impact_score        REAL    NOT NULL,                 -- 0.0 ~ 10.0
    summary             TEXT    NOT NULL,
    catalysts_json      TEXT    NOT NULL,                 -- '["earnings_beat","guidance_raise"]'
    tickers_json        TEXT    NOT NULL,                 -- '[{"ticker":"NVDA","confidence":0.9,"rationale":"..."}]'
    input_tokens        INTEGER NOT NULL,
    output_tokens       INTEGER NOT NULL,
    cost_usd            TEXT    NOT NULL,                 -- Decimal 字串（成本需精確）
    analyzed_at         TEXT    NOT NULL,                 -- UTC
    UNIQUE (article_id, model)                            -- 同篇若用同 model 不重複分析
);
CREATE INDEX idx_news_analysis_article ON news_analysis (article_id);
CREATE INDEX idx_news_analysis_at      ON news_analysis (analyzed_at);
```

### 1.12 news_tickers (v2.0)

```sql
CREATE TABLE news_tickers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES news_articles(id),
    analysis_id     INTEGER NOT NULL REFERENCES news_analysis(id),
    ticker          TEXT    NOT NULL,
    confidence      REAL    NOT NULL,                     -- 0.0 ~ 1.0
    rationale       TEXT,                                  -- 為何對應到此 ticker
    UNIQUE (analysis_id, ticker)
);
CREATE INDEX idx_news_tickers_ticker  ON news_tickers (ticker);
CREATE INDEX idx_news_tickers_article ON news_tickers (article_id);
```

### 1.13 watchlist (v2.0)

```sql
CREATE TABLE watchlist (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id              INTEGER NOT NULL REFERENCES accounts(id),
    ticker                  TEXT    NOT NULL,
    market                  TEXT    NOT NULL CHECK (market IN ('TW','US')),
    side                    TEXT    NOT NULL CHECK (side IN ('BUY','SELL')),
    source_article_ids_json TEXT    NOT NULL,                  -- '[42, 87, 103]'
    score                   REAL    NOT NULL,
    is_strong_signal        INTEGER NOT NULL DEFAULT 0,        -- ≥ 3 sources
    status                  TEXT    NOT NULL                   -- 'pending'|'promoted'|'dismissed'|'expired'
                               CHECK (status IN ('pending','promoted','dismissed','expired')),
    promoted_signal_id      INTEGER REFERENCES signals(id),    -- promote 後寫入
    added_at                TEXT    NOT NULL,                  -- UTC
    expires_at              TEXT    NOT NULL,                  -- UTC, default added_at+7d
    closed_at               TEXT                                -- promote / dismiss / expire 時間
);
CREATE INDEX idx_watchlist_status ON watchlist (status);
CREATE INDEX idx_watchlist_ticker ON watchlist (ticker, account_id);
```

### 1.14 llm_cost_daily (v2.0)

```sql
CREATE TABLE llm_cost_daily (
    date            TEXT    NOT NULL,                    -- 'YYYY-MM-DD' 以 Asia/Taipei 為準（PM I-12）
    model           TEXT    NOT NULL,
    calls           INTEGER NOT NULL DEFAULT 0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd        TEXT    NOT NULL DEFAULT '0',        -- Decimal 字串
    updated_at      TEXT    NOT NULL,                    -- UTC
    PRIMARY KEY (date, model)
);
```

### 1.15 blacklist (v2.0)

```sql
CREATE TABLE blacklist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT    NOT NULL                     -- 'ticker' | 'source'
                       CHECK (type IN ('ticker','source')),
    value           TEXT    NOT NULL,                    -- ticker symbol 或 source 名稱
    reason          TEXT,
    added_at        TEXT    NOT NULL,                    -- UTC
    added_by        TEXT    NOT NULL DEFAULT 'user',     -- 'user' | 'auto_fake_news'
    UNIQUE (type, value)
);
```

### 1.16 source_credibility (v2.0；對應 FR-NS-18/24)

```sql
CREATE TABLE source_credibility (
    source              TEXT    PRIMARY KEY,            -- 同 news_articles.source enum
    credibility         REAL    NOT NULL                 -- 0.0 ~ 1.0
                           CHECK (credibility BETWEEN 0 AND 1),
    fake_news_reports   INTEGER NOT NULL DEFAULT 0,
    last_adjusted_at    TEXT    NOT NULL                -- UTC
);

-- seed 預設值 (FR-NS-18 順序：Reuters/SEC > yfinance > 主流科技媒體 > Reddit)：
-- ('reuters',      0.90, 0, ...)
-- ('edgar',        0.95, 0, ...)
-- ('cnbc',         0.75, 0, ...)
-- ('yfinance',     0.70, 0, ...)
-- ('ars_technica', 0.65, 0, ...)
-- ('techcrunch',   0.60, 0, ...)
-- ('the_verge',    0.60, 0, ...)
-- ('reddit',       0.30, 0, ...)
-- 每次 FakeNewsReported → credibility -= 0.05（最低 0.05）
```

### 1.17 chart_patterns_cache (v1.5；對應 release_plan §6.3)

```sql
-- 快取 PatternDetector 結果，避免每次切換圖表重算
CREATE TABLE chart_patterns_cache (
    symbol          TEXT    NOT NULL,
    market          TEXT    NOT NULL CHECK (market IN ('TW','US')),
    timeframe       TEXT    NOT NULL,                    -- 'D','W','M','60m'
    pattern_type    TEXT    NOT NULL,
    triggered_at    TEXT    NOT NULL,                    -- 形態觸發日（YYYY-MM-DD）
    severity        REAL    NOT NULL,
    description     TEXT    NOT NULL,
    computed_at     TEXT    NOT NULL,                    -- UTC
    PRIMARY KEY (symbol, market, timeframe, triggered_at, pattern_type)
);

-- 當 kbars_cache 該 symbol 新增資料時 → 重算對應 patterns（cli reconcile_t_plus_1 內順帶執行）
```

---

## 2. v1.0 預建 v2.0 空表的策略

對應 `release_plan.md` §6.3 + `architecture.md` §8.1：**v1.0 的 `0001_initial.sql` 一次性建出所有表**（含 v2.0 的 news/watchlist 系列）。

理由：
- **降低 v2.0 升級風險**：使用者升級時不需跑 schema migration，因為表已存在 → 直接寫入即可。
- **多花的空間幾乎零**：空表只佔 page header。
- **代碼集中**：所有 schema 在一個 migration script 內，未來 review 容易。

v1.5 / v2.0 真正需要的 migration：
- `0002_v1_5_add_shioaji_order_id.sql`（其實上面已預先放在 orders 表）→ v1.5 可能完全不需 migration
- `0003_v1_5_chart_patterns_cache.sql`（若 v1.0 沒預建）
- v2.0 因表已預建，**極可能完全不需 migration**

---

## 3. Migration 機制

### 3.1 Contract（給工程師實作的契約）

`storage/migrations/` 目錄下放：
- `__init__.py` 列出 `MIGRATIONS: list[Migration]`（嚴格遞增 version）
- `0001_initial.py` — 包含 §1 全部 DDL + seed data
- `0002_*.py` 等後續 migration

每個 migration 是一個 dataclass：

```python
@dataclass(frozen=True)
class Migration:
    version: int                  # 1, 2, 3...
    name: str                     # '0001_initial'
    up_sql: str                   # DDL 字串（可多句，以 ; 分隔）
    down_sql: str | None          # rollback DDL（可 None 表示不支援回滾）
    seed_callable: Callable[[Connection], None] | None  # 寫 default rows
    checksum: str                 # sha256(up_sql + seed signature)
```

### 3.2 MigrationRunner 行為

```
app start (or cli command "migrate")
  ↓
1. 連線 app.db（若不存在則 sqlite3.connect 自動建檔）
2. 檢查 schema_version 表是否存在
   - 不存在 → 視為 fresh install，目標版本 = MIGRATIONS[-1].version
   - 存在   → current = MAX(version), 目標 = MIGRATIONS[-1].version
3. if current == target → exit OK
4. else: 取出 (current, target] 區間的所有 migration
5. 強制 backup：cp app.db backups/pre_migration_v{current}_to_v{target}_{ts}.db.gz
6. for each migration in sequence:
     BEGIN;
       run up_sql
       if seed_callable → seed_callable(conn)
     COMMIT;
     INSERT INTO schema_version (version, name, applied_at, checksum, success)
7. 若任一步驟失敗：
     ROLLBACK; restore backup; insert schema_version (success=0, error_message=...)
     寄 alert email；exit non-zero
```

### 3.3 Schema Version 與 App Version 對應

| App Version | schema_version |
| --- | --- |
| v1.0.0 ~ v1.0.x | 1 |
| v1.5.0 ~ v1.5.x | 1 或 2（看是否新增 migration） |
| v2.0.0 ~ v2.0.x | 1 或 2 |
| v3.x | 預期 ≥ 3 |

由於 v1.0 已預建 v2.0 表，**v1.0 → v2.0 升級 schema_version 仍可能維持 1**。新增欄位才會 bump。

### 3.4 自寫 vs Alembic

採用 **自寫 MigrationRunner**（見 `tech_decisions.md` §8）：
- 不引入 sqlalchemy（v1.0 不需 ORM 複雜性）→ alembic 依賴 sqlalchemy，不合算。
- 自寫 ~150 行可滿足 MVP；schema 變更頻率低（每個 release 至多 1~2 次）。
- 介面預留：未來若引入 sqlalchemy，可在保留 `schema_version` 表的情況下無痛切換 alembic（alembic 也用 version table）。

---

## 4. 訊號狀態機

對應 `architecture.md` §4.3。下圖以資料庫狀態欄位呈現：

```
                       策略觸發 / Watchlist.promote
                                │
                                ▼
                      ┌─ PENDING_RISK_CHECK ─┐
                      │                       │
                RiskGuard.approve         RiskGuard.reject
                      │                       │
                      ▼                       ▼
       ┌─ 依 (mode, market) 路由 ──┐    REJECTED_RISK ────┐
       │                              │   (terminal)        │
   (SIM, *)            (LIVE, TW)     │                     │
       │                  │       (LIVE, US)                │
       ▼                  ▼           ▼                     │
PENDING_T+1_OPEN  PENDING_SHIOAJI_FILL  MANUAL_PENDING      │
       │                  │           │   (expires_at)      │
       │                  │           │                     │
       │ reconcile_t+1    │ Shioaji   │ user 確認 / 推測    │
       │                  │ fill push │ 成交 / EXPIRY       │
       ▼                  ▼           ▼                     │
   ┌───────┴──────┐    FILLED      FILLED  EXPIRED          │
   │              │    or          (terminal)               │
FILLED        UNFILLED_GAP         FAILED                   │
(terminal)    (terminal)           (terminal)               │
                                      │                     │
                                      └── 寄 alert email ──┘
```

### 4.1 狀態轉移規則

| From | To | 觸發 | 副作用 |
| --- | --- | --- | --- |
| (none) | PENDING_RISK_CHECK | StrategyRunner / Watchlist.promote | insert signals row |
| PENDING_RISK_CHECK | PENDING_T+1_OPEN | RiskGuard.approve + mode=SIM | insert orders (status=PENDING_T+1_OPEN) |
| PENDING_RISK_CHECK | PENDING_SHIOAJI_FILL | RiskGuard.approve + LIVE + TW | Shioaji place_order + 取得 broker_order_id |
| PENDING_RISK_CHECK | MANUAL_PENDING | RiskGuard.approve + LIVE + US | EmailBroker 寄訊號信；expires_at=now+30min |
| PENDING_RISK_CHECK | REJECTED_RISK | RiskGuard.reject | 寫 app_log；不下單 |
| PENDING_T+1_OPEN | FILLED | reconcile_t_plus_1 + 跳空 ≤ 5% | 更新 orders、寫 positions、寫 daily_pnl |
| PENDING_T+1_OPEN | UNFILLED_GAP | reconcile_t_plus_1 + 跳空 > 5% | 寫 app_log；不開倉 |
| PENDING_SHIOAJI_FILL | FILLED | Shioaji push deal report | 更新 orders；寫 positions |
| PENDING_SHIOAJI_FILL | FAILED | Shioaji reject / timeout | 寄 alert email |
| MANUAL_PENDING | FILLED | 使用者 GUI 標記 / yfinance 推測 | 更新 orders、positions；視為已下單 |
| MANUAL_PENDING | EXPIRED | scheduler 檢查 expires_at < now | 寫 app_log；寄催信 |
| 任何 PENDING | FAILED | 任何例外路徑 | 寄 alert email、寫 app_log |

### 4.2 與 orders.status 的對應

`orders` 與 `signals` 兩張表的 status 是**獨立但同步**：
- `signals.status` 是 business view；`orders.status` 是 broker view。
- 例：`signals.status = PENDING_T+1_OPEN` ↔ `orders.status = PENDING_T+1_OPEN`（1:1）。
- 例外：訊號 reject 時，`signals.status = REJECTED_RISK` 但**不會插入 orders row**。
- 兩者透過 `orders.signal_id` FK 關聯。

---

## 5. 雙帳本資料隔離規則（彙整）

對應 PM I-1、FR-MM-08~11、`architecture.md` §4.2、§7.1。

| 表 | 隔離欄位 | 隔離規則 |
| --- | --- | --- |
| accounts | mode (本身) | 一個 (mode, broker, currency) 一列 |
| positions | account_id → accounts.mode | 透過 account FK |
| orders | account_id + mode (冗餘) | 雙重保險（mode 欄位用於快速 filter） |
| signals | account_id + mode | 同上 |
| daily_pnl | account_id | 透過 account FK |
| kbars_cache | （無）| 全 mode 共用快取（行情資料無 mode 區別） |
| app_log | context_json 可含 mode | 不強制隔離（debug 用） |
| audit_log | target 可含 account_id | 不強制隔離 |
| news_* | （無） | 新聞與 mode 無關，全 mode 共用 |
| watchlist | account_id | 透過 account FK |
| llm_cost_daily | （無） | 全帳本共用 |
| blacklist | （無） | 全帳本共用（避免 SIM 黑名單和 LIVE 不一致） |

**重置帳本資料（FR-MM-11）**：
- 只允許 reset `accounts.mode=SIMULATION` 的帳本。
- LIVE 帳本若有 `SELECT COUNT(*) FROM positions WHERE account_id IN (... LIVE accounts) > 0` 則**禁止 reset**。
- Reset 動作 = DELETE 該 account_id 下所有 positions / orders / signals / daily_pnl + UPDATE accounts.current_equity = init_capital，**寫 audit_log**。

---

## 6. 時區處理規則

### 6.1 統一規則

| 場景 | 規則 |
| --- | --- |
| DB 儲存所有 `*_at` timestamp | UTC ISO-8601 `'2026-05-23T14:00:00Z'` |
| `daily_pnl.date` / `llm_cost_daily.date` | `'YYYY-MM-DD'`，依 **Asia/Taipei** 交易日 |
| `kbars_cache.date` | `'YYYY-MM-DD'`，依**該市場時區**的交易日（TW=Asia/Taipei、US=America/New_York） |
| `news_articles.published_at` | UTC（從來源拉到後立即轉 UTC） |
| `watchlist.expires_at` | UTC |
| Email 內容顯示時間 | Asia/Taipei（使用者所在地） |
| Email 主旨日期 | Asia/Taipei（"2026-05-23"） |
| GUI 顯示時間 | Asia/Taipei |
| LLM 預算重置時點 | Asia/Taipei 00:00（PM I-12） |
| Scheduler trigger | Asia/Taipei，且 **DST aware**（PM I-7：21:30 抓美股盤前需依 DST 微調） |

### 6.2 DST 處理（PM I-7）

對應 FR-NS-01 「美股盤前 21:30 抓取」這條規則的問題：美股有夏令時間（EDT vs EST），盤前盤後固定時間在 UTC 上是 ± 1 小時偏移，台北時間 21:30 對應的「美股盤前」可能變動。

**工程實作**：
- 不要寫 `cron(hour=21, minute=30, timezone='Asia/Taipei')`。
- 改寫成「美股盤前 X 小時觸發」的相對時間：
  ```python
  # 計算美股當日開盤的台北時間（自動 DST）
  ny_open = datetime(today_us, 9, 30, tzinfo=ZoneInfo('America/New_York'))
  trigger_at_tw = (ny_open - timedelta(hours=1)).astimezone(ZoneInfo('Asia/Taipei'))
  scheduler.add_job(news_collect, run_date=trigger_at_tw)
  ```
- 每日的 trigger 由 scheduler 自動更新；不寫死。
- 06:00 抓取美股盤後 → 改成 `ny_close + 1.5h`，同樣自動 DST。

### 6.3 Python 套件選擇

- 用 `zoneinfo`（Python 3.11+ stdlib），不引入 `pytz`。
- `datetime.now(tz=ZoneInfo('UTC'))` 取 UTC；轉換用 `.astimezone(ZoneInfo('Asia/Taipei'))`。
- 寫 DB 時統一 `dt.isoformat() + 'Z'`（已是 UTC 才合理）。
- 讀 DB 時 `datetime.fromisoformat(s.replace('Z', '+00:00'))`。

---

## 7. 快取策略

### 7.1 kbars_cache

詳見 §1.7。重點：
- 收盤後抓的歷史 K 線永久有效；無需 TTL。
- 當日盤中若需即時報價（v1.5 ChartPage），**不寫 kbars_cache**，另走 `realtime_quote` API 不快取。
- 強制刷新只 DELETE 對應 row，不刷整表。

### 7.2 ticker_aliases.json（檔案快取）

對應 §1.12 news_tickers 的 yfinance validation：

- 路徑：`%LOCALAPPDATA%\StocksTrading\cache\ticker_aliases.json`
- 結構：`{"NVDA": {"valid": true, "checked_at": "2026-05-23T10:00:00Z"}, ...}`
- TTL：30 天
- 過期 → 重新呼叫 yfinance Ticker.info 驗證

### 7.3 news_analysis 不快取

每篇 article 一旦分析過，`news_analysis` row 永久保留，**不重複呼叫 LLM**（成本考量）。
若需 re-analyze（例如換 model），insert 新 row（UNIQUE constraint `(article_id, model)` 允許不同 model 共存）。

---

## 8. 資料庫備份策略 (對應 PM I-8)

### 8.1 觸發時機

| 觸發 | 動作 |
| --- | --- |
| 每日 daily_run 結束（22:00 cli） | `BackupService.daily()` |
| Schema migration 前 | `BackupService.pre_migration(version_from, version_to)` |
| 使用者於設定頁手動點「立即備份」 | `BackupService.manual()` |
| Account reset 前 | `BackupService.pre_reset(account_id)` |

### 8.2 儲存位置與命名

```
%LOCALAPPDATA%\StocksTrading\backups\
├── daily\
│   ├── 20260520.db.gz
│   ├── 20260521.db.gz
│   ├── ... (保留 30 天)
├── monthly\
│   ├── 202604.db.gz
│   ├── 202603.db.gz
│   ├── ... (保留 12 個月)
├── pre_migration\
│   └── v1_to_v2_20260601_140230.db.gz
├── pre_reset\
│   └── account3_20260605_103015.db.gz
└── manual\
    └── 20260530_201020.db.gz   (保留最近 10 個)
```

### 8.3 備份實作

```python
class BackupService:
    def __init__(self, db_path: Path, backup_root: Path,
                 daily_retention: int = 30,
                 monthly_retention_months: int = 12): ...

    def daily(self) -> Path:
        """每日呼叫；先用 SQLite backup API 寫到 temp file → gzip → 移到 daily/"""
        # SQLite backup API 是 online backup，不需 stop DB
        # 月底（last day of month）順帶複製到 monthly/
        # 清理超過 retention 的舊備份

    def pre_migration(self, from_v: int, to_v: int) -> Path: ...
    def manual(self) -> Path: ...
    def restore(self, backup_path: Path) -> None:
        """從備份還原 → 先 close 所有 DB 連線 → 用備份覆蓋 → 重啟"""
```

### 8.4 還原流程

1. GUI 設定頁「從備份還原」→ 列出所有 backups。
2. 使用者選擇後**強制二次確認**（顯示「將覆蓋現有 app.db，無法復原」）。
3. App 自動：(a) 暫停 scheduler；(b) close DB connections；(c) 現有 `app.db` 移到 `app.db.before_restore`；(d) gunzip 備份檔覆蓋；(e) 重啟 app；(f) 寫 audit_log。
4. 若還原後 schema_version 落後當前 app 版本 → 自動再跑 migration。

---

## 9. SQLite 設定與效能

### 9.1 pragmas（每次連線設定）

```sql
PRAGMA journal_mode = WAL;            -- write-ahead log，讀寫並發較好
PRAGMA synchronous = NORMAL;          -- 在 WAL 下 NORMAL 即可（FULL 太慢、OFF 不安全）
PRAGMA foreign_keys = ON;             -- SQLite 預設關閉，必開
PRAGMA busy_timeout = 5000;           -- 5 秒等鎖，避免立刻 SQLITE_BUSY
PRAGMA cache_size = -20000;           -- 20MB cache（負值 = KB）
PRAGMA temp_store = MEMORY;
```

### 9.2 連線管理

- v1.0 用單一 `sqlite3.Connection`（GUI mode 一條、CLI mode 一條），透過 mutex 序列化寫入（NFR-PER 不需要高併發）。
- 如果未來引入 sqlalchemy，再考慮 connection pool。
- 大量寫入（如 news collect 一次 87 篇）用 `executemany` + 顯式 transaction。

---

## 10. ER 簡圖（核心關聯）

```
                ┌─────────────────────┐
                │     accounts        │
                │  (mode=SIM|LIVE)    │
                └───┬─────────┬───────┘
                    │1        │1
        ┌───────────┴┐       ┌┴──────────┐
        │N           │       │N          │
   ┌────▼─────┐  ┌───▼────┐  ▼       ┌───▼──────┐
   │ positions│  │  orders │  signals │  daily_pnl│
   └──────────┘  └────┬────┘  ┌──┴─┐  └──────────┘
                      │N      │1   │
                      │       │    │N
                      └───────►signal_id
                              │
                              │
                ┌─────────────┴────────────┐
                │  watchlist (v2.0)        │
                │   promoted_signal_id ────┘
                │   source_article_ids ────┐
                └──────────────────────────┘
                                            │
                                            ▼
   ┌──────────────────┐  ┌───────────────┐  ┌─────────────┐
   │ news_articles    │──│ news_analysis │──│news_tickers │
   │ (url_hash unique)│  │ (article_id)  │  │(analysis_id)│
   └──────────────────┘  └───────┬───────┘  └─────────────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │ llm_cost_daily│
                         └───────────────┘
                                 │
                                 │           ┌────────────┐
                                 └──relates──│ blacklist  │
                                             │source_credi│
                                             └────────────┘

   橫切：
   - schema_version  ── 與所有表無關，獨立
   - app_log         ── 與所有表 loose-coupled（context_json）
   - audit_log       ── 與所有表 loose-coupled（target 字串）
   - kbars_cache     ── 行情快取，無 FK
   - chart_patterns_cache (v1.5) ── 與 kbars_cache loose-coupled
```

---

## 11. 與 PM Review 的對應彙整

| PM Review 項 | 在 data_design 中解決於 |
| --- | --- |
| I-1 雙帳本隔離 | §1.2 accounts.mode、§5 隔離規則表 |
| I-2 多幣別折算 | §1.2 accounts.currency（隔離單位）、由 FxService 在 RiskGuard 統一折 TWD |
| I-3 美股訊號 EXPIRY | §1.4 orders.expires_at、§4 狀態機 MANUAL_PENDING → EXPIRED |
| I-4 訊號逐筆審查 | §4 狀態機（每個 signal 獨立轉移） |
| I-5 通過的過濾條件記錄 | §1.5 signals.filter_passed_json |
| I-7 DST 處理 | §6.2 |
| I-8 資料庫備份 | §8 完整章節 |
| I-9 MSI 升級保留資料 | §3 migration 機制（強制備份、版本表） |
| I-11 T+1 開盤價成交 | §1.4 orders.status、§4 PENDING_T+1_OPEN → FILLED |
| I-12 LLM 預算 Asia/Taipei | §1.14 llm_cost_daily.date、§6.1 規則表 |
| I-14 日誌保留 | §1.8 app_log 90 天、§1.9 audit_log 365 天 |
| E-3 audit_log 表 | §1.9 完整定義 |
| E-7 黑名單 ticker / source 行為不同 | §1.15 blacklist.type；應用層在 Collector / Ranker 分別 query |
