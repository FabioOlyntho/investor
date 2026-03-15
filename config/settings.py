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
RISK_FREE_TICKER = "^IRX"  # 13-week Treasury
VIX_TICKER = "^VIX"

# Major benchmark indices to track
BENCHMARK_INDICES = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "IBEX 35": "^IBEX",
}
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

# Theme ETFs (for sector rotation and context monitoring)
THEME_ETFS = {
    "Korea": "EWY",
    "Rare Earth": "REMX",
    "Uranium": "URA",
    "Semiconductors": "SMH",
    "Gold Miners": "GDX",
    "Copper": "COPX",
    "Emerging Markets": "EEM",
    "KOSPI": "^KS11",
}

# Portfolio theme groupings (ticker → theme)
THEME_TICKER_GROUPS = {
    "Korea": ["IKRA.AS", "HKOR.L", "0P0000ZXLI.F"],
    "Commodities/Mining": ["0P0001843K.F", "LU0172157280", "REMX.L", "GGMUSY.SW"],
    "Nuclear/Uranium": ["U3O8.DE"],
    "Semiconductors": ["SMH.DE"],
    "Global Equity": ["ES0113693032", "LU0496367763"],
    "Europe": ["ES0138792033", "0P0000Z2NB.F"],
    "Emerging Asia": ["LU0329678410"],
}

# Ticker → real ISIN for mstarpy fund lookups
FUND_ISIN_MAP = {
    "ES0113693032": "ES0113693032",
    "LU0496367763": "LU0496367763",
    "0P0001843K.F": "LU1223083087",
    "LU0172157280": "LU0172157280",
    "LU0329678410": "LU0329678410",
    "0P0000ZXLI.F": "LU0301657293",
    "0P0000Z2NB.F": "LU0524465548",
    "ES0138792033": "ES0138792033",
}

# Price scale factors for tickers that resolve to wrong share class
# 0P0000ZXLI.F = JPM Korea Equity C class (~245 EUR), A class is ~24.83 EUR
PRICE_SCALE_FACTORS = {
    "0P0000ZXLI.F": 0.10134,
}

# Currency overrides for tickers where yfinance returns None
CURRENCY_OVERRIDES = {
    "SMH.DE": "EUR",
}

# FX pairs for currency risk monitoring
FX_PAIRS = {"EUR/USD": "EURUSD=X", "EUR/GBP": "EURGBP=X", "EUR/CHF": "EURCHF=X"}

# Morningstar cache
MORNINGSTAR_CACHE_TTL = 86400  # 24h in seconds

# Alert defaults — descriptions in plain language
ALERT_TYPES = {
    "price_drop": "A fund or ETF lost too much in a single day",
    "drawdown": "A fund or ETF has fallen too far from its best price",
    "volatility_spike": "A fund is swinging up and down more than usual (high instability)",
    "rebalance_drift": "One position grew or shrank too much compared to your plan",
    "vix_spike": "The Fear Index (VIX) is high — markets are nervous",
    "correlation_break": "Everything in your portfolio is moving in the same direction (bad for diversification)",
    "total_loss": "Your whole portfolio is losing more than you set as a limit",
    "market_regime_change": "Market mood shifted quickly (from calm to nervous, or the opposite)",
    "sector_rotation": "A sector related to your investments is falling over the past month",
    "correlation_spike": "All your investments are moving together — less protection if things go wrong",
    "concentration_risk": "Too much of your money is in one theme (e.g. Korea, mining)",
    "currency_risk": "The euro moved a lot against another currency today — affects your returns",
    "morningstar_downgrade": "A fund's Morningstar star rating went down (less recommended by analysts)",
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

# AI Advisor
ADVISOR_LLM_PROVIDER = os.getenv("ADVISOR_LLM_PROVIDER", "google")
ADVISOR_LLM_MODEL = os.getenv("ADVISOR_LLM_MODEL", "")  # empty = use provider default
ADVISOR_QA_PROVIDER = os.getenv("ADVISOR_QA_PROVIDER", "")  # empty = same as main
ADVISOR_QA_MODEL = os.getenv("ADVISOR_QA_MODEL", "")  # empty = same as main
ADVISOR_CACHE_DAILY_TTL = 43200    # 12 hours
ADVISOR_CACHE_REBALANCE_TTL = 86400  # 24 hours
ADVISOR_CACHE_OPPORTUNITY_TTL = 86400  # 24 hours
ADVISOR_DAILY_QUERY_LIMIT = 10
