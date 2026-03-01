"""Currency, percent, and number formatting helpers."""


def fmt_currency(value: float, currency: str = "EUR", decimals: int = 2) -> str:
    """Format a number as currency."""
    if value is None:
        return "N/A"
    symbols = {"EUR": "\u20ac", "USD": "$", "GBP": "\u00a3", "CHF": "CHF "}
    symbol = symbols.get(currency, f"{currency} ")
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.{decimals}f}"


def fmt_percent(value: float, decimals: int = 2) -> str:
    """Format a number as percentage."""
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def fmt_number(value: float, decimals: int = 2) -> str:
    """Format a plain number with thousands separator."""
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"


def fmt_change(value: float, currency: str = None) -> str:
    """Format a change value with color indicator prefix."""
    if value is None:
        return "N/A"
    if currency:
        return fmt_currency(value, currency)
    return fmt_percent(value)


def delta_color(value: float) -> str:
    """Return 'normal', 'inverse', or 'off' for st.metric delta_color."""
    if value is None:
        return "off"
    return "normal"
