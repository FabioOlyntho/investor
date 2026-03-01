# CLAUDE.md

## Project Overview

**InvestmentMonitor** — Portfolio dashboard & alert system for monitoring a globally diversified fund/ETF portfolio. Built with Streamlit (Python), free data APIs (yfinance, mstarpy), SQLite for persistence, and Plotly for interactive charts.

## Architecture

```
Browser → Streamlit (port 8501)
               |
    +----------+----------+
    |          |          |
 yfinance   mstarpy   SQLite
 (prices)  (ratings) (local DB)
```

## Tech Stack

- **Framework**: Streamlit >= 1.40
- **Charts**: Plotly
- **Data**: yfinance (prices), mstarpy (fund ratings)
- **DB**: SQLite (portfolio.db, gitignored)
- **Language**: Python 3.13
- **Tests**: pytest (33 tests passing)

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit entrypoint with st.navigation |
| `pages/1_portfolio_overview.py` | Main dashboard: 4 metrics + 4 charts |
| `pages/2_performance_analysis.py` | Returns, benchmark, monthly heatmap |
| `pages/3_risk_analysis.py` | Volatility, drawdown, correlation, VaR |
| `pages/4_market_signals.py` | VIX, yield curve, sector momentum, regime |
| `pages/5_alerts.py` | Alert config + history + acknowledge |
| `pages/6_portfolio_management.py` | Add/edit/remove/import positions |
| `data/database.py` | SQLite schema (5 tables) + CRUD |
| `data/market_data.py` | yfinance wrapper with st.cache_data |
| `data/calculations.py` | Sharpe, drawdown, VaR, beta, regime score |
| `data/alerts_engine.py` | 7 alert rule types |
| `components/charts.py` | 15+ reusable Plotly chart builders |
| `components/metrics.py` | st.metric card helpers |
| `components/formatters.py` | Currency/percent formatting |
| `config/settings.py` | Constants, colors, cache TTLs |
| `cli/daily_update.py` | n8n cron CLI (alerts + email) |

## Commands

```bash
# Run app
./venv/Scripts/streamlit.exe run app.py

# Run tests
./venv/Scripts/python.exe -m pytest tests/ -v

# CLI alert check (for n8n)
./venv/Scripts/python.exe -m cli.daily_update
```

## SQLite Schema (5 tables)

- **positions**: ticker, units, cost_basis, purchase_date, sector, asset_class
- **portfolio_values**: date, total_value, total_cost, daily_return, benchmark
- **price_history**: ticker, date, OHLCV (cache)
- **alert_config**: alert_type, ticker, threshold, direction, enabled
- **alert_history**: config_id, triggered_at, message, severity, acknowledged

## Caching Strategy

| Data | TTL | Source |
|------|-----|--------|
| Prices | 5 min | yfinance via @st.cache_data |
| Positions | 1 min | SQLite |
| Sector ETFs | 1 hour | yfinance |
| Treasury yields | 1 hour | yfinance |

## Data Sources (all free, no API keys)

- **yfinance**: Prices, FX, VIX, yields, sector ETFs (unlimited)
- **mstarpy**: Fund ratings, risk metrics (Phase 4)

## Alert Types

1. price_drop — single-day drop exceeds threshold
2. drawdown — drawdown from peak exceeds threshold
3. volatility_spike — 30-day vol exceeds threshold
4. rebalance_drift — position weight drifts from target
5. vix_spike — VIX exceeds level
6. correlation_break — portfolio correlation spike
7. total_loss — total P&L below threshold

## Branding

- Primary: #FF002A
- Positive: #00C853
- Negative: #FF1744
- Dark theme (Streamlit dark)

## Implementation Status

- Phase 1: Foundation + All 6 Pages (COMPLETE)
- Phase 2: Analytics refinement (planned)
- Phase 3: Market signals + Alerts CLI (planned)
- Phase 4: VPS deployment + Morningstar (planned)
