"""Upstox Analytics tools — portfolio, market quotes, historical data."""

from actions import upstox_api


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_portfolio_holdings",
                "description": "Get user's stock portfolio holdings with P&L, buy price, LTP, and total returns",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_positions",
                "description": "Get current intraday positions with P&L",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_market_quote",
                "description": "Get real-time market quote for an NSE stock symbol (price, change, day range, volume)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "NSE stock symbol (e.g. 'RELIANCE', 'TCS', 'INFY', 'HDFCBANK')",
                        },
                    },
                    "required": ["symbol"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_historical_data",
                "description": "Get historical price data with technical indicators (SMA, volatility) for analysis",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "NSE stock symbol (e.g. 'RELIANCE', 'TCS')",
                        },
                        "interval": {
                            "type": "string",
                            "description": "Candle interval",
                            "enum": ["1minute", "5minute", "30minute", "day", "week", "month"],
                            "default": "day",
                        },
                        "days_back": {
                            "type": "integer",
                            "description": "Number of days of history (max 365)",
                            "default": 30,
                        },
                    },
                    "required": ["symbol"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_portfolio_summary",
                "description": "Get a comprehensive portfolio summary: holdings, P&L, sector exposure, top gainers/losers",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    ]


def get_portfolio_holdings() -> str:
    """Get user's portfolio holdings."""
    return upstox_api.get_holdings()


def get_positions() -> str:
    """Get current day positions."""
    return upstox_api.get_positions()


def get_market_quote(symbol: str) -> str:
    """Get real-time market quote."""
    return upstox_api.get_market_quote(symbol)


def get_historical_data(symbol: str, interval: str = "day", days_back: int = 30) -> str:
    """Get historical price data."""
    return upstox_api.get_historical_candle(symbol, interval, days_back)


def get_portfolio_summary() -> str:
    """
    Aggregated portfolio summary — uses holdings data to compute
    additional analytics like sector breakdown, concentration risk, etc.
    """
    data = upstox_api.get_portfolio_summary_raw()

    if isinstance(data, dict) and "error" in data:
        return str(data["error"])

    if not isinstance(data, dict) or data.get("status") != "success":
        return "No portfolio data available."

    holdings = data.get("data", [])
    if not holdings:
        return "No holdings found."

    total_pl = 0.0
    total_invested = 0.0
    top_gainer = None
    top_loser = None

    for h in holdings:
        symbol = h.get("tradingsymbol", "?")
        qty = int(h.get("quantity", 0))
        buy = float(h.get("buy_price", h.get("average_price", 0)))
        pl = float(h.get("pnl", 0))
        pl_pct = float(h.get("pnl_percent", 0))

        total_pl += pl
        total_invested += buy * qty

        if top_gainer is None or pl_pct > top_gainer[2]:
            top_gainer = (symbol, pl, pl_pct)
        if top_loser is None or pl_pct < top_loser[2]:
            top_loser = (symbol, pl, pl_pct)

    total_current = total_invested + total_pl
    overall_return_pct = (total_pl / total_invested * 100) if total_invested else 0

    lines = [
        "📊 **Portfolio Summary**\n",
        f"**Total Invested:** ₹{total_invested:,.2f}",
        f"**Current Value:** ₹{total_current:,.2f}",
        f"**Total P&L:** ₹{total_pl:+,.2f} ({overall_return_pct:+.2f}%)",
        f"**Holdings:** {len(holdings)} stocks\n",
    ]

    if top_gainer:
        lines.append(
            f"🏆 **Top Gainer:** {top_gainer[0]} — "
            f"₹{top_gainer[1]:+,.2f} ({top_gainer[2]:+.2f}%)"
        )
    if top_loser:
        lines.append(
            f"⚠️ **Top Loser:** {top_loser[0]} — "
            f"₹{top_loser[1]:+,.2f} ({top_loser[2]:+.2f}%)"
        )

    lines.append(f"\n{_concentration_warning(holdings, total_invested)}")
    lines.append(f"\n{_diversification_score(len(holdings))}")

    return "\n".join(lines)


def _concentration_warning(holdings: list, total_invested: float) -> str:
    """Check if portfolio is over-concentrated in any single stock."""
    if not holdings or not total_invested:
        return ""

    warnings = []
    for h in holdings:
        qty = int(h.get("quantity", 0))
        buy = float(h.get("buy_price", h.get("average_price", 0)))
        weight = (buy * qty / total_invested * 100) if total_invested else 0
        if weight > 30:
            warnings.append(
                f"⚠️ **High Concentration:** {h.get('tradingsymbol', '?')} "
                f"is {weight:.0f}% of your portfolio — consider diversifying."
            )

    if not warnings:
        return "✅ Portfolio concentration looks balanced (no single stock >30%)."
    return "\n".join(warnings)


def _diversification_score(num_holdings: int) -> str:
    """Score portfolio diversification based on number of holdings."""
    if num_holdings >= 15:
        return f"✅ **Well diversified** — {num_holdings} stocks across your portfolio."
    elif num_holdings >= 8:
        return f"📊 **Moderate diversification** — {num_holdings} stocks."
    elif num_holdings >= 3:
        return f"⚠️ **Under-diversified** — only {num_holdings} stocks. Consider adding more."
    else:
        return f"🔴 **Highly concentrated** — only {num_holdings} stock(s). High risk!"
