"""
Upstox API Client — fetches portfolio, holdings, market data from Upstox.

Uses UPSTOX_ANALYTICS_API from config (JWT token).
Base URL: https://api.upstox.com/v2/

Market quote and historical APIs work without IP whitelisting.
Portfolio/holdings APIs require the requesting IP to be whitelisted in the
Upstox account settings (returns 401 otherwise).
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.upstox.com/v2"

# ── Instrument key resolution ──────────────────────────────
# Runtime cache populated by the Instruments Search API.
# Starts empty and grows as symbols are looked up.
_INSTRUMENT_CACHE: dict[str, str] = {}


def _search_instrument(query: str) -> str | None:
    """
    Use the Upstox Instruments Search API to look up an instrument key.

    Accepts: trading symbol ('RELIANCE'), ISIN ('INE002A01018'), or name.
    Returns instrument key (e.g. 'NSE_EQ|INE002A01018') or None.

    Results are cached locally to avoid repeated API calls.
    """
    import urllib.request
    import json

    headers = _headers()
    if headers is None:
        return None

    url = (
        f"{_BASE_URL}/instruments/search"
        f"?query={urllib.request.quote(query)}"  # type: ignore[attr-defined]
        f"&exchanges=NSE&segments=EQ&records=1"
    )
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=10
        ) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success" and data.get("data"):
                instrument = data["data"][0]
                key = instrument.get("instrument_key")
                symbol = instrument.get("trading_symbol", "")
                if key:
                    _INSTRUMENT_CACHE[query.upper()] = key
                    if symbol and symbol.upper() != query.upper():
                        _INSTRUMENT_CACHE[symbol.upper()] = key
                return key  # type: ignore[no-any-return]
    except Exception as e:
        logger.debug("Instrument search failed for '%s': %s", query, e)
    return None


def _resolve_symbol(symbol_or_key: str) -> str | None:
    """
    Resolve a display symbol to an instrument key.

    Accepts:
    - Trading symbol: 'RELIANCE', 'TCS', 'HINDALCO'
    - With exchange prefix: 'NSE:RELIANCE'
    - ISIN: 'INE002A01018'
    - Raw instrument key: 'NSE_EQ|INE002A01018'

    Uses the Instruments Search API. Results are cached for speed.
    """
    s = symbol_or_key.upper().strip()

    # 1. Already an instrument key
    if s.startswith("NSE_EQ|") or s.startswith("BSE_EQ|"):
        return s

    # 2. Strip exchange prefix
    if ":" in s:
        s = s.split(":", 1)[1].strip()

    # 3. Check runtime cache
    if s in _INSTRUMENT_CACHE:
        return _INSTRUMENT_CACHE[s]

    # 4. ISIN pattern (12 chars starting with INE)
    if len(s) == 12 and s.startswith("INE"):
        result = _search_instrument(s)
        if result:
            return result
        # Best-effort fallback: construct key from ISIN
        return f"NSE_EQ|{s}"

    # 5. Dynamic search via API
    logger.info("Looking up instrument key for '%s'...", s)
    return _search_instrument(s)


# ── HTTP helpers ────────────────────────────────────────────


def _headers():
    """Build auth headers from the configured API key."""
    from config import UPSTOX_API_KEY
    if not UPSTOX_API_KEY:
        logger.warning("UPSTOX_ANALYTICS_API is not configured")
        return None
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {UPSTOX_API_KEY}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Origin": "https://upstox.com",
        "Referer": "https://upstox.com/",
    }


def _get(path: str, params: dict | None = None) -> tuple[int, str]:
    """Make a GET request. Returns (status_code, body_string)."""
    headers = _headers()
    if headers is None:
        return 0, "Error: UPSTOX_ANALYTICS_API key is not configured. Set it in settings.toml (or via Settings dialog / Endpoints tab)"

    import urllib.request
    import urllib.error

    url = f"{_BASE_URL}{path}"
    if params:
        qs = "&".join(
            f"{k}={urllib.request.quote(str(v))}" for k, v in params.items()  # type: ignore[attr-defined]
        )
        url = f"{url}?{qs}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        logger.debug("Upstox HTTP %d: %s", e.code, body)
        return e.code, body
    except urllib.error.URLError as e:
        logger.error("Upstox connection error: %s", e)
        return 0, f"Error: Could not reach Upstox API — {e.reason}"
    except Exception as e:
        logger.error("Upstox request failed: %s", e)
        return 0, f"Error: Request failed — {e}"


def _parse_json_raw(raw: str) -> dict | list | str:
    """Safe JSON parse, returning raw string on failure."""
    import json
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return raw


def _is_ip_restricted(status_code: int, body: str) -> bool:
    """Check if the error is about static IP restriction."""
    return status_code == 401 and "static IP" in body


def _ip_restricted_message() -> str:
    return (
        "⚠️ Portfolio data is not available because the Upstox API requires "
        "your IP address to be whitelisted.\n\n"
        "To fix this:\n"
        "1. Log in to your Upstox account\n"
        "2. Go to Account Settings → API → Manage API Access\n"
        "3. Whitelist your current IP address\n"
        "4. Regenerate your API token"
    )


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────


def get_holdings() -> str:
    """
    Fetch user's long-term holdings with P&L.

    Requires IP whitelisting in Upstox account.
    """
    status, raw = _get("/portfolio/long-term-holdings")
    if _is_ip_restricted(status, raw):
        return _ip_restricted_message()
    if status != 200:
        return _format_error(status, raw)

    data = _parse_json_raw(raw)
    if isinstance(data, str):
        return raw

    if isinstance(data, dict) and data.get("status") == "success":
        holdings = data.get("data", [])
        if not holdings:
            return "No holdings found in your portfolio."

        lines = ["📊 **Your Portfolio Holdings:**\n"]
        total_pl = 0
        total_invested = 0
        for h in holdings:
            symbol = h.get("tradingsymbol", "?")
            quantity = int(h.get("quantity", 0))
            buy_price = float(h.get("buy_price", h.get("average_price", 0)))
            ltp = float(h.get("ltp", 0))
            pl = float(h.get("pnl", 0))
            pl_percent = float(h.get("pnl_percent", 0))
            invested = buy_price * quantity or 0

            total_pl += pl  # type: ignore[assignment]
            total_invested += invested  # type: ignore[assignment]

            emoji = "🟢" if pl >= 0 else "🔴"
            lines.append(
                f"{emoji} **{symbol}** — Qty: {quantity:,} | "
                f"Avg: ₹{buy_price:.2f} | LTP: ₹{ltp:.2f} | "
                f"P&L: ₹{pl:+,.2f} ({pl_percent:+.2f}%)"
            )

        lines.append(f"\n**Summary:** Total Invested: ₹{total_invested:,.2f} | "
                      f"Total P&L: ₹{total_pl:+,.2f}")
        return "\n".join(lines)

    return raw


def get_positions() -> str:
    """Fetch current day positions."""
    status, raw = _get("/positions")
    if _is_ip_restricted(status, raw):
        return _ip_restricted_message()
    if status != 200:
        return _format_error(status, raw)

    data = _parse_json_raw(raw)
    if isinstance(data, str):
        return raw

    if isinstance(data, dict) and data.get("status") == "success":
        positions = data.get("data", [])
        if not positions:
            return "No open positions."

        lines = ["📈 **Current Positions:**\n"]
        total_pl = 0
        for p in positions:
            symbol = p.get("tradingsymbol", "?")
            qty = int(p.get("quantity", 0))
            buy = float(p.get("buy_price", 0))
            ltp = float(p.get("ltp", 0))
            pl = float(p.get("pnl", 0))
            total_pl += pl  # type: ignore[assignment]
            emoji = "🟢" if pl >= 0 else "🔴"
            lines.append(
                f"{emoji} **{symbol}** — {qty:,} shares | "
                f"Buy: ₹{buy:.2f} | LTP: ₹{ltp:.2f} | P&L: ₹{pl:+,.2f}"
            )
        lines.append(f"\n**Total Position P&L:** ₹{total_pl:+,.2f}")
        return "\n".join(lines)

    return raw


def get_market_quote(symbol: str) -> str:
    """
    Get real-time market quote for a stock.

    Args:
        symbol: NSE symbol (e.g. 'RELIANCE', 'TCS') or instrument key
    """
    instr_key = _resolve_symbol(symbol)
    if not instr_key:
        return (
            f"Could not resolve '{symbol}' to an instrument key. "
            f"If this is a legitimate NSE stock symbol, check that "
            f"it is actively trading on NSE."
        )

    status, raw = _get(
        "/market-quote/quotes",
        {"instrument_key": instr_key},
    )
    if status != 200:
        return _format_error(status, raw)

    data = _parse_json_raw(raw)
    if isinstance(data, str):
        return raw

    if isinstance(data, dict) and data.get("status") == "success":
        quotes = data.get("data", {})
        # The key in response includes the instrument key format
        quote_key = next(iter(quotes), None)
        if not quote_key:
            return f"No quote data for {symbol}"

        q = quotes[quote_key]
        last_price = float(q.get("last_price", 0))
        net_change = float(q.get("net_change", 0))
        pct_change = (net_change / (last_price - net_change) * 100) if (last_price - net_change) else 0
        volume = int(q.get("volume", 0))
        ohlc = q.get("ohlc", {})
        open_p = float(ohlc.get("open", 0))
        high = float(ohlc.get("high", 0))
        low = float(ohlc.get("low", 0))
        close = float(ohlc.get("close", 0))
        display_symbol = q.get("symbol", symbol)
        ltt = q.get("last_trade_time", "")
        # Convert Unix timestamp (ms) to readable format
        if ltt and ltt.isdigit():
            try:
                from datetime import datetime as dt
                ts = int(ltt) / 1000
                ltt = dt.fromtimestamp(ts).strftime("%H:%M:%S")
            except (ValueError, OSError):
                pass

        emoji = "🟢" if net_change >= 0 else "🔴"
        return (
            f"{emoji} **{display_symbol}** — ₹{last_price:.2f}\n"
            f"Change: ₹{net_change:+,.2f} ({pct_change:+.2f}%)\n"
            f"Day Range: ₹{low:.2f} — ₹{high:.2f}\n"
            f"Open: ₹{open_p:.2f} | Prev Close: ₹{close:.2f}\n"
            f"Volume: {volume:,}\n"
            f"Avg Price: ₹{float(q.get('average_price', 0)):.2f}\n"
            f"Last Trade: {ltt}"
        )

    return raw


def get_historical_candle(
    symbol: str,
    interval: str = "day",
    days_back: int = 30,
) -> str:
    """
    Fetch historical price data with technical indicators.

    Args:
        symbol: NSE symbol or instrument key
        interval: '1minute', '5minute', '30minute', 'day', 'week', 'month'
        days_back: Number of days to go back (max ~365)
    """
    instr_key = _resolve_symbol(symbol)
    if not instr_key:
        return (
            f"Could not find instrument key for '{symbol}'. "
            f"Known symbols in cache: {', '.join(sorted(_INSTRUMENT_CACHE.keys())[:20])}..."
        )

    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    to_str = to_date.strftime("%Y-%m-%d")
    from_str = from_date.strftime("%Y-%m-%d")

    import urllib.request
    path = f"/historical-candle/{urllib.request.quote(instr_key, safe='')}/{interval}/{to_str}/{from_str}"  # type: ignore[attr-defined]
    status, raw = _get(path)

    if status != 200:
        return _format_error(status, raw)

    data = _parse_json_raw(raw)
    if isinstance(data, str):
        return raw

    if isinstance(data, dict) and data.get("status") == "success":
        candles = data.get("data", {}).get("candles", [])
        if not candles:
            return f"No historical data for {symbol} ({interval}, {days_back}d)"

        # Each candle: [timestamp, open, high, low, close, volume, oi]
        closes = [float(c[4]) for c in candles if len(c) > 4]
        if not closes:
            return f"No price data for {symbol}"

        high_all = max(closes)
        low_all = min(closes)
        start = closes[0]
        end = closes[-1]
        change = end - start
        pct = (change / start * 100) if start else 0

        # Moving averages
        sma_5 = sum(closes[-5:]) / min(5, len(closes)) if len(closes) >= 5 else None
        sma_10 = sum(closes[-10:]) / min(10, len(closes)) if len(closes) >= 10 else None
        sma_20 = sum(closes[-20:]) / min(20, len(closes)) if len(closes) >= 20 else None

        # Volatility
        daily_changes = [
            abs(closes[i] - closes[i-1]) / closes[i-1] * 100
            for i in range(1, len(closes))
        ] if len(closes) > 1 else []
        avg_volatility = sum(daily_changes) / len(daily_changes) if daily_changes else 0

        # Trend signal
        if sma_5 and sma_20:
            if end > sma_5 > sma_20:
                trend = "🟢 Strong uptrend (price > SMA5 > SMA20)"
            elif end > sma_20 > sma_5:
                trend = "🟡 Moderate uptrend but short-term weakening"
            elif end < sma_5 < sma_20:
                trend = "🔴 Strong downtrend (price < SMA5 < SMA20)"
            elif end < sma_20 < sma_5:
                trend = "🟡 Moderate downtrend but short-term recovering"
            else:
                trend = "⚪ Mixed / range-bound"
        else:
            trend = "⚪ Insufficient data for trend analysis"

        display_symbol = symbol.upper()
        lines = [
            f"📉 **{display_symbol} — {interval} chart ({days_back}d)**\n",
            f"Candles: {len(candles)} | Period: {from_str} → {to_str}",
            f"Start: ₹{start:.2f} → End: ₹{end:.2f} ({pct:+.2f}%)",
            f"Range: ₹{low_all:.2f} — ₹{high_all:.2f}",
            f"Avg Volatility: {avg_volatility:.2f}%\n",
            "**Technical Indicators:**",
        ]
        if sma_5:
            signal_5 = "🟢 Above" if end >= sma_5 else "🔴 Below"
            lines.append(f"  SMA(5): ₹{sma_5:.2f} — Price {signal_5}")
        if sma_10:
            signal_10 = "🟢 Above" if end >= sma_10 else "🔴 Below"
            lines.append(f"  SMA(10): ₹{sma_10:.2f} — Price {signal_10}")
        if sma_20:
            signal_20 = "🟢 Above" if end >= sma_20 else "🔴 Below"
            lines.append(f"  SMA(20): ₹{sma_20:.2f} — Price {signal_20}")

        lines.append(f"\n**Trend:** {trend}")

        # Support/resistance levels (simple)
        if len(closes) >= 20:
            support = min(closes[-20:])
            resistance = max(closes[-20:])
            lines.append("\n**Key Levels (20-day):**")
            lines.append(f"  Support: ₹{support:.2f} | Resistance: ₹{resistance:.2f}")
            mid = (support + resistance) / 2
            if end > mid:
                lines.append("  Price is in the upper half — bullish bias")
            else:
                lines.append("  Price is in the lower half — bearish bias")

        return "\n".join(lines)

    return raw


def get_portfolio_summary_raw() -> dict | str:
    """
    Fetch raw portfolio holdings data for aggregation.

    Returns parsed dict or error string.
    """
    status, raw = _get("/portfolio/long-term-holdings")
    if _is_ip_restricted(status, raw):
        return {"error": _ip_restricted_message()}
    if status != 200:
        return {"error": _format_error(status, raw)}

    data = _parse_json_raw(raw)
    if isinstance(data, str):
        return {"error": raw}
    return data if isinstance(data, dict) else {"error": "Unexpected response format"}


def _format_error(status: int, body: str) -> str:
    """Format an API error into a user-friendly message."""
    try:
        import json
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            err_list = parsed.get("errors", [])
            if err_list:
                msg = err_list[0].get("message", str(err_list[0]))
                return f"Error: Upstox API returned HTTP {status} — {msg}"
    except (json.JSONDecodeError, TypeError):
        pass
    return f"Error: Upstox API returned HTTP {status}"
