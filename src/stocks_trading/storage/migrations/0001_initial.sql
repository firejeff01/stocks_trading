-- 0001_initial — 初始 schema (v1.0 一次預建 v2.0 空表，降低升級風險)
-- 對應 SA data_design.md §1 全部 17 張表 + seed data
-- 注意：schema_version 表由 MigrationRunner 自動建立，不在此檔內
--
-- 設計決策：accounts.id、signals.id 採 TEXT UUID 與 domain 對齊；
-- 其他資料表 PK 仍用 INTEGER (append log 性質)．

-- =========================================================================
-- §1.2 accounts (雙帳本隔離根節點)
-- =========================================================================
CREATE TABLE accounts (
    id              TEXT    PRIMARY KEY,                -- UUID 字串
    name            TEXT    NOT NULL,
    mode            TEXT    NOT NULL CHECK (mode IN ('SIMULATION', 'LIVE')),
    broker          TEXT    NOT NULL,
    currency        TEXT    NOT NULL CHECK (currency IN ('TWD', 'USD')),
    init_capital    TEXT    NOT NULL,
    current_equity  TEXT    NOT NULL,
    is_frozen       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    UNIQUE (mode, broker, currency)
);

-- =========================================================================
-- §1.3 positions
-- =========================================================================
CREATE TABLE positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT    NOT NULL REFERENCES accounts(id),
    symbol          TEXT    NOT NULL,
    market          TEXT    NOT NULL CHECK (market IN ('TW', 'US')),
    qty             INTEGER NOT NULL,
    avg_price       TEXT    NOT NULL,
    stop_loss       TEXT,
    opened_at       TEXT    NOT NULL,
    last_updated_at TEXT    NOT NULL,
    UNIQUE (account_id, symbol)
);
CREATE INDEX idx_positions_account ON positions (account_id);
CREATE INDEX idx_positions_symbol  ON positions (symbol, market);

-- =========================================================================
-- §1.5 signals (注意：先於 orders，因 orders 有 FK 指向 signals)
-- =========================================================================
CREATE TABLE signals (
    id                  TEXT    PRIMARY KEY,            -- UUID 字串
    strategy_id         TEXT    NOT NULL,
    symbol              TEXT    NOT NULL,
    market              TEXT    NOT NULL CHECK (market IN ('TW', 'US')),
    side                TEXT    NOT NULL CHECK (side IN ('BUY','SELL','COVER')),
    target_price        TEXT    NOT NULL,
    stop_loss_price     TEXT,
    suggested_qty       INTEGER NOT NULL,
    reason              TEXT    NOT NULL,
    generated_at        TEXT    NOT NULL,
    status              TEXT    NOT NULL CHECK (status IN (
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
    filter_passed_json  TEXT,
    mode                TEXT    NOT NULL CHECK (mode IN ('SIMULATION','LIVE')),
    account_id          TEXT    NOT NULL REFERENCES accounts(id),
    notified_at         TEXT
);
CREATE INDEX idx_signals_status        ON signals (status);
CREATE INDEX idx_signals_generated_at  ON signals (generated_at);
CREATE INDEX idx_signals_strategy      ON signals (strategy_id);
CREATE INDEX idx_signals_account       ON signals (account_id);

-- =========================================================================
-- §1.4 orders
-- =========================================================================
CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id          TEXT    NOT NULL REFERENCES accounts(id),
    signal_id           TEXT    REFERENCES signals(id),
    mode                TEXT    NOT NULL CHECK (mode IN ('SIMULATION', 'LIVE')),
    symbol              TEXT    NOT NULL,
    market              TEXT    NOT NULL CHECK (market IN ('TW', 'US')),
    side                TEXT    NOT NULL CHECK (side IN ('BUY','SELL','COVER')),
    order_type          TEXT    NOT NULL CHECK (order_type IN ('LIMIT','MARKET','MOC','MOO')),
    qty                 INTEGER NOT NULL,
    price               TEXT,
    stop_loss           TEXT,
    status              TEXT    NOT NULL CHECK (status IN (
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
    shioaji_order_id    TEXT,
    fill_price          TEXT,
    commission          TEXT,
    tax                 TEXT,
    placed_at           TEXT    NOT NULL,
    filled_at           TEXT,
    expires_at          TEXT,
    metadata_json       TEXT
);
CREATE INDEX idx_orders_account_status ON orders (account_id, status);
CREATE INDEX idx_orders_signal         ON orders (signal_id);
CREATE INDEX idx_orders_placed_at      ON orders (placed_at);

-- =========================================================================
-- §1.6 daily_pnl
-- =========================================================================
CREATE TABLE daily_pnl (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT    NOT NULL REFERENCES accounts(id),
    date            TEXT    NOT NULL,
    equity          TEXT    NOT NULL,
    cash            TEXT    NOT NULL,
    realized_pnl    TEXT    NOT NULL DEFAULT '0',
    unrealized_pnl  TEXT    NOT NULL DEFAULT '0',
    drawdown_pct    TEXT,
    snapshotted_at  TEXT    NOT NULL,
    UNIQUE (account_id, date)
);
CREATE INDEX idx_daily_pnl_date ON daily_pnl (date);

-- =========================================================================
-- §1.7 kbars_cache
-- =========================================================================
CREATE TABLE kbars_cache (
    symbol          TEXT    NOT NULL,
    market          TEXT    NOT NULL CHECK (market IN ('TW','US')),
    date            TEXT    NOT NULL,
    open            TEXT    NOT NULL,
    high            TEXT    NOT NULL,
    low             TEXT    NOT NULL,
    close           TEXT    NOT NULL,
    volume          INTEGER NOT NULL,
    source          TEXT    NOT NULL CHECK (source IN ('shioaji','yfinance')),
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (symbol, market, date)
);
CREATE INDEX idx_kbars_fetched_at ON kbars_cache (fetched_at);

-- =========================================================================
-- §1.8 app_log
-- =========================================================================
CREATE TABLE app_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    level           TEXT    NOT NULL CHECK (level IN ('DEBUG','INFO','WARN','ERROR','CRITICAL')),
    module          TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    context_json    TEXT
);
CREATE INDEX idx_app_log_ts    ON app_log (ts);
CREATE INDEX idx_app_log_level ON app_log (level);

-- =========================================================================
-- §1.9 audit_log
-- =========================================================================
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    actor           TEXT    NOT NULL,
    action          TEXT    NOT NULL CHECK (action IN (
                        'mode_switch',
                        'risk_param_change',
                        'settings_change',
                        'watchlist_promote',
                        'account_reset',
                        'backup_restore',
                        'strategy_param_change'
                    )),
    target          TEXT,
    before_json     TEXT,
    after_json      TEXT,
    success         INTEGER NOT NULL DEFAULT 1,
    error_message   TEXT
);
CREATE INDEX idx_audit_ts     ON audit_log (ts);
CREATE INDEX idx_audit_action ON audit_log (action);

-- =========================================================================
-- §1.10 news_articles (v2.0 預建)
-- =========================================================================
CREATE TABLE news_articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL CHECK (source IN (
                        'yfinance','cnbc','reuters','ars_technica',
                        'techcrunch','the_verge','reddit','edgar'
                    )),
    url             TEXT    NOT NULL,
    url_hash        TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    published_at    TEXT    NOT NULL,
    lang            TEXT    NOT NULL,
    raw_text        TEXT    NOT NULL,
    fetched_at      TEXT    NOT NULL,
    UNIQUE (url_hash)
);
CREATE INDEX idx_news_source        ON news_articles (source);
CREATE INDEX idx_news_published_at  ON news_articles (published_at);
CREATE INDEX idx_news_fetched_at    ON news_articles (fetched_at);

-- =========================================================================
-- §1.11 news_analysis (v2.0 預建)
-- =========================================================================
CREATE TABLE news_analysis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id          INTEGER NOT NULL REFERENCES news_articles(id),
    model               TEXT    NOT NULL,
    sentiment           REAL    NOT NULL,
    impact_score        REAL    NOT NULL,
    summary             TEXT    NOT NULL,
    catalysts_json      TEXT    NOT NULL,
    tickers_json        TEXT    NOT NULL,
    input_tokens        INTEGER NOT NULL,
    output_tokens       INTEGER NOT NULL,
    cost_usd            TEXT    NOT NULL,
    analyzed_at         TEXT    NOT NULL,
    UNIQUE (article_id, model)
);
CREATE INDEX idx_news_analysis_article ON news_analysis (article_id);
CREATE INDEX idx_news_analysis_at      ON news_analysis (analyzed_at);

-- =========================================================================
-- §1.12 news_tickers (v2.0 預建)
-- =========================================================================
CREATE TABLE news_tickers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES news_articles(id),
    analysis_id     INTEGER NOT NULL REFERENCES news_analysis(id),
    ticker          TEXT    NOT NULL,
    confidence      REAL    NOT NULL,
    rationale       TEXT,
    UNIQUE (analysis_id, ticker)
);
CREATE INDEX idx_news_tickers_ticker  ON news_tickers (ticker);
CREATE INDEX idx_news_tickers_article ON news_tickers (article_id);

-- =========================================================================
-- §1.13 watchlist (v2.0 預建)
-- =========================================================================
CREATE TABLE watchlist (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id              TEXT    NOT NULL REFERENCES accounts(id),
    ticker                  TEXT    NOT NULL,
    market                  TEXT    NOT NULL CHECK (market IN ('TW','US')),
    side                    TEXT    NOT NULL CHECK (side IN ('BUY','SELL')),
    source_article_ids_json TEXT    NOT NULL,
    score                   REAL    NOT NULL,
    is_strong_signal        INTEGER NOT NULL DEFAULT 0,
    status                  TEXT    NOT NULL CHECK (status IN ('pending','promoted','dismissed','expired')),
    promoted_signal_id      TEXT    REFERENCES signals(id),
    added_at                TEXT    NOT NULL,
    expires_at              TEXT    NOT NULL,
    closed_at               TEXT
);
CREATE INDEX idx_watchlist_status ON watchlist (status);
CREATE INDEX idx_watchlist_ticker ON watchlist (ticker, account_id);

-- =========================================================================
-- §1.14 llm_cost_daily (v2.0 預建)
-- =========================================================================
CREATE TABLE llm_cost_daily (
    date            TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    calls           INTEGER NOT NULL DEFAULT 0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd        TEXT    NOT NULL DEFAULT '0',
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (date, model)
);

-- =========================================================================
-- §1.15 blacklist (v2.0 預建)
-- =========================================================================
CREATE TABLE blacklist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT    NOT NULL CHECK (type IN ('ticker','source')),
    value           TEXT    NOT NULL,
    reason          TEXT,
    added_at        TEXT    NOT NULL,
    added_by        TEXT    NOT NULL DEFAULT 'user',
    UNIQUE (type, value)
);

-- =========================================================================
-- §1.16 source_credibility (v2.0 預建)
-- =========================================================================
CREATE TABLE source_credibility (
    source              TEXT    PRIMARY KEY,
    credibility         REAL    NOT NULL CHECK (credibility BETWEEN 0 AND 1),
    fake_news_reports   INTEGER NOT NULL DEFAULT 0,
    last_adjusted_at    TEXT    NOT NULL
);

-- =========================================================================
-- §1.17 chart_patterns_cache (v1.5 預建)
-- =========================================================================
CREATE TABLE chart_patterns_cache (
    symbol          TEXT    NOT NULL,
    market          TEXT    NOT NULL CHECK (market IN ('TW','US')),
    timeframe       TEXT    NOT NULL,
    pattern_type    TEXT    NOT NULL,
    triggered_at    TEXT    NOT NULL,
    severity        REAL    NOT NULL,
    description     TEXT    NOT NULL,
    computed_at     TEXT    NOT NULL,
    PRIMARY KEY (symbol, market, timeframe, triggered_at, pattern_type)
);

-- =========================================================================
-- SEED：accounts 雙帳本 × 雙幣別共 4 列 (UUID 與 seed_accounts.py 同步)
-- LIVE 預設 is_frozen=1，待 v1.5 首次切到實盤時由使用者解凍並設定 init_capital
-- =========================================================================
INSERT INTO accounts (id, name, mode, broker, currency, init_capital, current_equity, is_frozen, created_at) VALUES
    ('11111111-0000-4000-8000-000000000001', 'Default-SIM-TW',  'SIMULATION', 'simulated', 'TWD', '100000.00', '100000.00', 0, datetime('now')),
    ('11111111-0000-4000-8000-000000000002', 'Default-SIM-US',  'SIMULATION', 'simulated', 'USD',   '3000.00',   '3000.00', 0, datetime('now')),
    ('11111111-0000-4000-8000-000000000003', 'Default-LIVE-TW', 'LIVE',       'shioaji',   'TWD',       '0.00',       '0.00', 1, datetime('now')),
    ('11111111-0000-4000-8000-000000000004', 'Default-LIVE-US', 'LIVE',       'email_us',  'USD',       '0.00',       '0.00', 1, datetime('now'));

-- =========================================================================
-- SEED：source_credibility 八大來源預設信用度
-- 順序：EDGAR > Reuters > CNBC > yfinance > Ars > TechCrunch > The Verge > Reddit
-- =========================================================================
INSERT INTO source_credibility (source, credibility, fake_news_reports, last_adjusted_at) VALUES
    ('edgar',        0.95, 0, datetime('now')),
    ('reuters',      0.90, 0, datetime('now')),
    ('cnbc',         0.75, 0, datetime('now')),
    ('yfinance',     0.70, 0, datetime('now')),
    ('ars_technica', 0.65, 0, datetime('now')),
    ('techcrunch',   0.60, 0, datetime('now')),
    ('the_verge',    0.60, 0, datetime('now')),
    ('reddit',       0.30, 0, datetime('now'));
