"""SQLite database schema and CRUD operations."""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import DB_PATH


def get_db_path() -> Path:
    return DB_PATH


@contextmanager
def get_connection(db_path: Optional[Path] = None):
    """Context manager for SQLite connections with WAL mode."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None):
    """Create all tables if they don't exist."""
    with get_connection(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                units REAL NOT NULL DEFAULT 0,
                cost_basis REAL NOT NULL DEFAULT 0,
                purchase_date TEXT NOT NULL,
                sector TEXT NOT NULL DEFAULT 'Other',
                asset_class TEXT NOT NULL DEFAULT 'Equity',
                currency TEXT NOT NULL DEFAULT 'EUR',
                target_weight REAL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS portfolio_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_value REAL NOT NULL,
                total_cost REAL NOT NULL,
                daily_return REAL,
                benchmark_value REAL,
                benchmark_return REAL
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL NOT NULL,
                volume INTEGER,
                UNIQUE(ticker, date)
            );

            CREATE TABLE IF NOT EXISTS alert_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                ticker TEXT,
                threshold REAL NOT NULL,
                direction TEXT NOT NULL DEFAULT 'below',
                severity TEXT NOT NULL DEFAULT 'warning',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_id INTEGER,
                triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
                message TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'warning',
                acknowledged INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (config_id) REFERENCES alert_config(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS regime_history (
                date TEXT NOT NULL UNIQUE,
                score REAL NOT NULL,
                vix REAL,
                yield_spread REAL,
                momentum_pct REAL
            );

            CREATE TABLE IF NOT EXISTS morningstar_cache (
                isin TEXT PRIMARY KEY,
                fund_name TEXT,
                star_rating INTEGER,
                previous_star_rating INTEGER,
                medalist_rating TEXT,
                category TEXT,
                risk_rating TEXT,
                last_updated TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date
                ON price_history(ticker, date);
            CREATE INDEX IF NOT EXISTS idx_portfolio_values_date
                ON portfolio_values(date);
            CREATE INDEX IF NOT EXISTS idx_alert_history_triggered
                ON alert_history(triggered_at);
            CREATE INDEX IF NOT EXISTS idx_regime_history_date
                ON regime_history(date);
        """)


# --- Positions CRUD ---

def get_positions(db_path: Optional[Path] = None) -> pd.DataFrame:
    """Return all positions as a DataFrame."""
    with get_connection(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT * FROM positions ORDER BY sector, ticker", conn
        )
    return df


def get_position(position_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM positions WHERE id = ?", (position_id,)
        ).fetchone()
    return dict(row) if row else None


def add_position(
    ticker: str, name: str, units: float, cost_basis: float,
    purchase_date: str, sector: str, asset_class: str,
    currency: str = "EUR", target_weight: float = None,
    notes: str = "", db_path: Optional[Path] = None
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO positions
               (ticker, name, units, cost_basis, purchase_date, sector,
                asset_class, currency, target_weight, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, name, units, cost_basis, purchase_date, sector,
             asset_class, currency, target_weight, notes)
        )
        return cursor.lastrowid


def update_position(position_id: int, db_path: Optional[Path] = None, **kwargs) -> bool:
    ALLOWED_FIELDS = {
        "ticker", "name", "units", "cost_basis", "purchase_date",
        "sector", "asset_class", "currency", "target_weight", "notes"
    }
    fields = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
    if not fields:
        return False
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [position_id]
    with get_connection(db_path) as conn:
        conn.execute(
            f"UPDATE positions SET {set_clause} WHERE id = ?", values
        )
    return True


def delete_position(position_id: int, db_path: Optional[Path] = None) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM positions WHERE id = ?", (position_id,)
        )
        return cursor.rowcount > 0


# --- Price History ---

def save_price_history(ticker: str, df: pd.DataFrame, db_path: Optional[Path] = None):
    """Save OHLCV data for a ticker (upsert)."""
    if df.empty:
        return
    with get_connection(db_path) as conn:
        for idx, row in df.iterrows():
            dt = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            conn.execute(
                """INSERT OR REPLACE INTO price_history
                   (ticker, date, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ticker, dt,
                 row.get("Open"), row.get("High"),
                 row.get("Low"), row.get("Close"),
                 row.get("Volume"))
            )


def get_price_history(
    ticker: str, start_date: str = None, end_date: str = None,
    db_path: Optional[Path] = None
) -> pd.DataFrame:
    query = "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ?"
    params = [ticker]
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date"
    with get_connection(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params, parse_dates=["date"])
    if not df.empty:
        df.set_index("date", inplace=True)
    return df


def get_latest_prices(tickers: list[str], db_path: Optional[Path] = None) -> dict[str, float]:
    """Return latest close price for each ticker."""
    result = {}
    with get_connection(db_path) as conn:
        for ticker in tickers:
            row = conn.execute(
                """SELECT close FROM price_history
                   WHERE ticker = ? ORDER BY date DESC LIMIT 1""",
                (ticker,)
            ).fetchone()
            if row:
                result[ticker] = row["close"]
    return result


# --- Portfolio Values ---

def save_portfolio_value(
    dt: str, total_value: float, total_cost: float,
    daily_return: float = None, benchmark_value: float = None,
    benchmark_return: float = None, db_path: Optional[Path] = None
):
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO portfolio_values
               (date, total_value, total_cost, daily_return,
                benchmark_value, benchmark_return)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (dt, total_value, total_cost, daily_return,
             benchmark_value, benchmark_return)
        )


def get_portfolio_values(
    start_date: str = None, end_date: str = None,
    db_path: Optional[Path] = None
) -> pd.DataFrame:
    query = "SELECT * FROM portfolio_values"
    params = []
    conditions = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date"
    with get_connection(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params, parse_dates=["date"])
    return df


# --- Alert Config ---

def get_alert_configs(db_path: Optional[Path] = None) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM alert_config ORDER BY alert_type", conn
        )


def add_alert_config(
    alert_type: str, threshold: float, direction: str = "below",
    severity: str = "warning", ticker: str = None,
    db_path: Optional[Path] = None
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO alert_config
               (alert_type, ticker, threshold, direction, severity)
               VALUES (?, ?, ?, ?, ?)""",
            (alert_type, ticker, threshold, direction, severity)
        )
        return cursor.lastrowid


def update_alert_config(config_id: int, db_path: Optional[Path] = None, **kwargs) -> bool:
    ALLOWED = {"alert_type", "ticker", "threshold", "direction", "severity", "enabled"}
    fields = {k: v for k, v in kwargs.items() if k in ALLOWED}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [config_id]
    with get_connection(db_path) as conn:
        conn.execute(
            f"UPDATE alert_config SET {set_clause} WHERE id = ?", values
        )
    return True


def delete_alert_config(config_id: int, db_path: Optional[Path] = None) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM alert_config WHERE id = ?", (config_id,)
        )
        return cursor.rowcount > 0


# --- Alert History ---

def add_alert_history(
    message: str, severity: str = "warning",
    config_id: int = None, db_path: Optional[Path] = None
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO alert_history (config_id, message, severity)
               VALUES (?, ?, ?)""",
            (config_id, message, severity)
        )
        return cursor.lastrowid


def get_alert_history(
    limit: int = 50, unacknowledged_only: bool = False,
    db_path: Optional[Path] = None
) -> pd.DataFrame:
    query = "SELECT * FROM alert_history"
    if unacknowledged_only:
        query += " WHERE acknowledged = 0"
    query += " ORDER BY triggered_at DESC LIMIT ?"
    with get_connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=[limit])


def acknowledge_alert(alert_id: int, db_path: Optional[Path] = None) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "UPDATE alert_history SET acknowledged = 1 WHERE id = ?",
            (alert_id,)
        )
        return cursor.rowcount > 0


def alert_fired_today(
    alert_type: str, ticker: str = None, db_path: Optional[Path] = None
) -> bool:
    """Check if an alert of this type+ticker already fired today (dedup)."""
    today = date.today().isoformat()
    with get_connection(db_path) as conn:
        query = """SELECT COUNT(*) as cnt FROM alert_history ah
                   JOIN alert_config ac ON ah.config_id = ac.id
                   WHERE ac.alert_type = ? AND ah.triggered_at >= ?"""
        params = [alert_type, today]
        if ticker:
            query += " AND ac.ticker = ?"
            params.append(ticker)
        row = conn.execute(query, params).fetchone()
        return row["cnt"] > 0


# --- Regime History ---

def save_regime_score(
    dt: str, score: float, vix: float = None,
    yield_spread: float = None, momentum_pct: float = None,
    db_path: Optional[Path] = None
):
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO regime_history
               (date, score, vix, yield_spread, momentum_pct)
               VALUES (?, ?, ?, ?, ?)""",
            (dt, score, vix, yield_spread, momentum_pct)
        )


def get_regime_history(
    limit: int = 10, db_path: Optional[Path] = None
) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM regime_history ORDER BY date DESC LIMIT ?",
            conn, params=[limit]
        )


# --- Morningstar Cache ---

def save_morningstar_rating(
    isin: str, fund_name: str = None, star_rating: int = None,
    previous_star_rating: int = None, medalist_rating: str = None,
    category: str = None, risk_rating: str = None,
    db_path: Optional[Path] = None
):
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO morningstar_cache
               (isin, fund_name, star_rating, previous_star_rating,
                medalist_rating, category, risk_rating, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (isin, fund_name, star_rating, previous_star_rating,
             medalist_rating, category, risk_rating)
        )


def get_morningstar_cache(db_path: Optional[Path] = None) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM morningstar_cache ORDER BY isin", conn
        )


def get_morningstar_rating(
    isin: str, db_path: Optional[Path] = None
) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM morningstar_cache WHERE isin = ?", (isin,)
        ).fetchone()
    return dict(row) if row else None


# --- Seed Default Alerts ---

def seed_default_alerts(db_path: Optional[Path] = None):
    """Seed 34 pre-configured alert rules if none exist."""
    configs = get_alert_configs(db_path)
    if not configs.empty:
        return  # Already has rules

    rules = [
        # Portfolio P&L
        ("total_loss", None, -5.0, "below", "warning"),
        ("total_loss", None, -10.0, "below", "critical"),
        ("total_loss", None, -15.0, "below", "critical"),
        # VIX
        ("vix_spike", None, 25.0, "above", "warning"),
        ("vix_spike", None, 30.0, "above", "warning"),
        ("vix_spike", None, 35.0, "above", "critical"),
        # Correlation
        ("correlation_spike", None, 0.75, "above", "warning"),
        # Regime
        ("market_regime_change", None, 15.0, "below", "warning"),
        ("market_regime_change", None, 25.0, "below", "critical"),
        # Price drops — volatile (uranium, rare earth, gold)
        ("price_drop", "NUCL.L", 5.0, "below", "warning"),
        ("price_drop", "U3O8.DE", 5.0, "below", "warning"),
        ("price_drop", "REMX.L", 5.0, "below", "warning"),
        ("price_drop", "GGMUSY.SW", 5.0, "below", "warning"),
        # Price drops — semi/korea/mining
        ("price_drop", "SMH.DE", 4.0, "below", "warning"),
        ("price_drop", "IKRA.AS", 4.0, "below", "warning"),
        ("price_drop", "HKOR.L", 4.0, "below", "warning"),
        ("price_drop", "0P0001843K.F", 4.0, "below", "warning"),
        # Drawdowns — volatile
        ("drawdown", "NUCL.L", 20.0, "below", "warning"),
        ("drawdown", "U3O8.DE", 20.0, "below", "warning"),
        ("drawdown", "REMX.L", 20.0, "below", "warning"),
        # Drawdowns — semi/korea
        ("drawdown", "SMH.DE", 15.0, "below", "warning"),
        ("drawdown", "IKRA.AS", 15.0, "below", "warning"),
        # Theme rotation
        ("sector_rotation", "EWY", 10.0, "below", "warning"),
        ("sector_rotation", "URA", 15.0, "below", "warning"),
        ("sector_rotation", "REMX", 15.0, "below", "warning"),
        ("sector_rotation", "SMH", 10.0, "below", "warning"),
        ("sector_rotation", "GDX", 10.0, "below", "warning"),
        # Concentration
        ("concentration_risk", "Korea", 25.0, "above", "warning"),
        ("concentration_risk", "Commodities/Mining", 30.0, "above", "warning"),
        ("concentration_risk", "Global Equity", 30.0, "above", "warning"),
        # Currency
        ("currency_risk", "EUR/USD", 2.0, "above", "warning"),
        ("currency_risk", "EUR/GBP", 2.0, "above", "warning"),
        # Morningstar
        ("morningstar_downgrade", None, 1.0, "below", "warning"),
        ("morningstar_downgrade", None, 2.0, "below", "critical"),
    ]

    for alert_type, ticker, threshold, direction, severity in rules:
        add_alert_config(
            alert_type=alert_type, threshold=threshold,
            direction=direction, severity=severity,
            ticker=ticker, db_path=db_path,
        )
