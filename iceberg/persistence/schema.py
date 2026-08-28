SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS capital_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    starting_capital TEXT NOT NULL,
    daily_starting_capital TEXT NOT NULL,
    available_cash TEXT NOT NULL,
    broker_available_cash TEXT,
    settled_cash TEXT NOT NULL,
    unsettled_cash TEXT NOT NULL,
    deployed_capital TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    market_value TEXT NOT NULL,
    total_equity TEXT NOT NULL,
    user_distribution TEXT NOT NULL,
    next_day_capital TEXT NOT NULL,
    current_trading_date TEXT,
    snapshot_created_at TEXT,
    consecutive_losses INTEGER NOT NULL,
    broker_state_known INTEGER NOT NULL,
    portfolio_state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_snapshots (
    trading_date TEXT PRIMARY KEY,
    snapshot_created_at TEXT NOT NULL,
    daily_starting_capital TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS funding_events (
    funding_id TEXT PRIMARY KEY,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    confirmed_at TEXT,
    effective_trading_date TEXT,
    external_reference TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
    symbol TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL,
    average_price TEXT NOT NULL,
    cost_basis TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
    order_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    execution_price TEXT NOT NULL,
    gross_value TEXT NOT NULL,
    transaction_costs TEXT NOT NULL,
    net_cash_flow TEXT NOT NULL,
    timestamp TEXT,
    status TEXT NOT NULL,
    rejection_reason TEXT,
    slippage TEXT NOT NULL,
    gross_pnl TEXT NOT NULL,
    net_pnl TEXT NOT NULL,
    charge_schedule_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_ids (
    decision_id TEXT PRIMARY KEY,
    order_id TEXT
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    order_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emergency_stop (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active INTEGER NOT NULL,
    allow_position_exits INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    decision_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    strategy TEXT NOT NULL,
    market_regime TEXT,
    confidence TEXT,
    key_signals TEXT NOT NULL,
    features TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    proposed_price TEXT NOT NULL,
    approved_quantity INTEGER NOT NULL,
    estimated_costs TEXT NOT NULL,
    capital_required TEXT NOT NULL,
    risk_result TEXT NOT NULL,
    rejection_reason TEXT,
    authorization_id TEXT,
    order_id TEXT,
    execution_price TEXT,
    slippage TEXT NOT NULL,
    gross_pnl TEXT NOT NULL,
    transaction_costs TEXT NOT NULL,
    net_pnl TEXT NOT NULL,
    charge_schedule_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    portfolio_state TEXT NOT NULL,
    broker_state_known INTEGER NOT NULL,
    reason TEXT,
    updated_at TEXT
);
"""
