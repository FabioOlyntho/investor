"""Application constants, colors, and defaults."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "portfolio.db"

# Branding
APP_NAME = "InvestmentMonitor"
PRIMARY_COLOR = "#FF002A"
POSITIVE_COLOR = "#00C853"
NEGATIVE_COLOR = "#FF1744"
NEUTRAL_COLOR = "#78909C"
BEIGE = "#ADAB96"
CREAM = "#e7e6df"

# Chart colors (diversified palette for multiple series)
CHART_COLORS = [
    "#FF002A", "#00C853", "#2979FF", "#FF9100",
    "#AA00FF", "#00BFA5", "#FFD600", "#D500F9",
    "#64DD17", "#00B8D4", "#FF6D00", "#304FFE",
]

# Sector colors (consistent mapping)
SECTOR_COLORS = {
    "Equity - Global": "#2979FF",
    "Equity - US": "#FF002A",
    "Equity - Europe": "#00C853",
    "Equity - Emerging": "#FF9100",
    "Fixed Income": "#AA00FF",
    "Real Estate": "#00BFA5",
    "Commodities": "#FFD600",
    "Cash": "#78909C",
    "Alternative": "#D500F9",
}

# Market data
DEFAULT_BENCHMARK = "IWDA.AS"  # iShares MSCI World
RISK_FREE_TICKER = "^IRX"  # 13-week Treasury
VIX_TICKER = "^VIX"
YIELD_TICKERS = {
    "3M": "^IRX",
    "2Y": "2YY=F",
    "5Y": "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}
SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Disc.": "XLY",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Comm. Services": "XLC",
    "Consumer Staples": "XLP",
}

# Cache TTLs (seconds)
PRICE_CACHE_TTL = 300       # 5 minutes
POSITION_CACHE_TTL = 60     # 1 minute
SECTOR_CACHE_TTL = 3600     # 1 hour
YIELD_CACHE_TTL = 3600      # 1 hour

# Alert defaults
ALERT_TYPES = {
    "price_drop": "Single-day price drop exceeds threshold",
    "drawdown": "Drawdown from peak exceeds threshold",
    "volatility_spike": "30-day annualized volatility exceeds threshold",
    "rebalance_drift": "Position weight drifts from target by threshold",
    "vix_spike": "VIX exceeds threshold level",
    "correlation_break": "Portfolio correlation exceeds threshold",
    "total_loss": "Total portfolio P&L drops below threshold",
}

SEVERITY_COLORS = {
    "critical": "#FF1744",
    "warning": "#FFD600",
    "info": "#2979FF",
}

# Email
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "fabio.olyntho@recodme.es")

# Trading days per year (for annualization)
TRADING_DAYS = 252
