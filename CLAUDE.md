# CLAUDE.md

## Project Overview

**InvestmentMonitor** — Portfolio dashboard & alert system for monitoring a globally diversified fund/ETF portfolio (16 positions, EUR 143K). Built with Streamlit (Python), free data APIs (yfinance, mstarpy), SQLite for persistence, and Plotly for interactive charts.

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
- **Data**: yfinance (prices, FX, themes), mstarpy (fund ratings)
- **DB**: SQLite (portfolio.db, gitignored)
- **Language**: Python 3.13
- **Tests**: pytest (56 tests passing)

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit entrypoint with st.navigation (sidebar collapsed by default) |
| `pages/1_dashboard.py` | **Single scrollable page**: portfolio + markets + performance + risk + alerts + Morningstar |
| `pages/5_alerts.py` | Alert rules config + history + acknowledge + seed defaults |
| `pages/6_portfolio_management.py` | Add/edit/remove/import positions |
| `pages/1_portfolio_overview.py` | Legacy (kept for reference, not in navigation) |
| `pages/2_performance_analysis.py` | Legacy (content merged into dashboard) |
| `pages/3_risk_analysis.py` | Legacy (content merged into dashboard) |
| `pages/4_market_signals.py` | Legacy (content merged into dashboard) |
| `data/database.py` | SQLite schema (7 tables) + CRUD + seed_default_alerts |
| `data/market_data.py` | yfinance + mstarpy wrapper with st.cache_data + CLI variants |
| `data/calculations.py` | Sharpe, drawdown, VaR, beta, regime score |
| `data/alerts_engine.py` | 13 alert rule types (7 original + 6 new) |
| `components/charts.py` | 16+ reusable Plotly chart builders (incl. theme_momentum_bar) |
| `components/metrics.py` | st.metric card helpers |
| `components/formatters.py` | Currency/percent formatting |
| `config/settings.py` | Constants, colors, cache TTLs, theme/FX/Morningstar configs |
| `cli/daily_update.py` | n8n cron CLI (comprehensive daily briefing + alerts) |

## Commands

```bash
# Run app
./venv/Scripts/streamlit.exe run app.py

# Run tests
./venv/Scripts/python.exe -m pytest tests/ -v

# CLI daily briefing (for n8n)
./venv/Scripts/python.exe -m cli.daily_update
```

## SQLite Schema (7 tables)

- **positions**: ticker, units, cost_basis, purchase_date, sector, asset_class, notes
- **portfolio_values**: date, total_value, total_cost, daily_return, benchmark
- **price_history**: ticker, date, OHLCV (cache)
- **alert_config**: alert_type, ticker, threshold, direction, enabled
- **alert_history**: config_id, triggered_at, message, severity, acknowledged
- **regime_history**: date (UNIQUE), score, vix, yield_spread, momentum_pct
- **morningstar_cache**: isin (PK), fund_name, star_rating, previous_star_rating, medalist_rating, category, risk_rating

## Caching Strategy

| Data | TTL | Source |
|------|-----|--------|
| Prices | 5 min | yfinance via @st.cache_data |
| Positions | 1 min | SQLite |
| Sector/Theme ETFs | 1 hour | yfinance |
| Treasury yields | 1 hour | yfinance |
| FX rates | 5 min | yfinance |
| Morningstar | 24 hours | mstarpy |

## Data Sources (all free, no API keys)

- **yfinance**: Prices, FX, VIX, yields, sector ETFs, theme ETFs, benchmark indices (unlimited)
- **mstarpy**: Fund star ratings, medalist ratings, categories, risk ratings

## Benchmark Indices

| Name | Ticker |
|------|--------|
| S&P 500 | ^GSPC |
| Nasdaq | ^IXIC |
| IBEX 35 | ^IBEX |

## Alert Types (13)

### Original (7)
1. price_drop — single-day drop exceeds threshold
2. drawdown — drawdown from peak exceeds threshold
3. volatility_spike — 30-day vol exceeds threshold
4. rebalance_drift — position weight drifts from target
5. vix_spike — VIX exceeds level
6. correlation_break — portfolio correlation spike
7. total_loss — total P&L below threshold

### New (6)
8. market_regime_change — regime score drops vs 5-day avg
9. sector_rotation — theme ETF 1M return reversal
10. correlation_spike — mean pairwise correlation exceeds threshold
11. concentration_risk — theme weight exceeds limit
12. currency_risk — daily FX move exceeds threshold
13. morningstar_downgrade — fund star rating dropped

### Pre-configured Seed Rules (34)
- 3 portfolio P&L, 3 VIX, 1 correlation, 2 regime
- 8 price drops (5% volatile, 4% others), 5 drawdowns
- 5 theme rotation, 3 concentration, 2 currency, 2 Morningstar
- Call `seed_default_alerts()` — idempotent, only seeds if empty

## Portfolio Theme Groups

| Theme | Tickers | ETF Benchmark |
|-------|---------|---------------|
| Korea | IKRA.AS, HKOR.L, 0P0000ZXLI.F | EWY |
| Commodities/Mining | 0P0001843K.F, 0P00000B0T, REMX.L, GGMUSY.SW | GDX, COPX |
| Nuclear/Uranium | NUCL.L, U3O8.DE | URA |
| Semiconductors | SMH.DE | SMH |
| Global Equity | ES0113693032, LU0496367763 | — |
| Europe | ES0138792033, 0P0000Z2NB.F | — |
| Emerging Asia | 0P0001CDI0.F | EEM |

## Daily Briefing (CLI)

Always sends comprehensive email (not just when alerts fire).
All language is plain/accessible (no financial jargon):
- How your portfolio is doing: value, today's change, total gain/loss
- What's happening in markets: mood (Pessimistic/Mixed/Optimistic), Fear Index (VIX), interest rate gap
- Major stock markets: S&P 500, Nasdaq, IBEX 35
- Warnings: triggered alerts grouped by severity
- Your investment themes: 1M returns for benchmark ETFs
- Biggest winners & losers today
- Worth a look (big drops): positions with >15% drawdown
- Fund rating changes: Morningstar star changes

Subject: `InvestmentMonitor: 3 warning(s) | Mood: Pessimistic (28) | 2026-03-01`

## Branding

- Primary: #FF002A
- Positive: #00C853
- Negative: #FF1744
- Dark theme (Streamlit dark)

## Implementation Status

- Phase 1: Foundation + All 6 Pages (COMPLETE)
- Phase 2: Comprehensive Alerts & Market Intelligence (COMPLETE)
  - 6 new alert evaluators, 34 seeded rules, Morningstar integration
  - Theme/FX/correlation monitoring, daily briefing email
  - Plain language throughout (no financial jargon)
  - Benchmark indices: S&P 500, Nasdaq, IBEX 35
  - 56 tests passing
- Phase 3: VPS deployment (planned)
