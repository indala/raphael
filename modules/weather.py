"""
Weather module — free, no API key required.
Uses Open-Meteo API (open-meteo.com) for geocoding + weather data.
"""

import json
import logging
from datetime import datetime
from urllib.request import urlopen, Request

logger = logging.getLogger(__name__)


def get_weather(location: str, forecast_days: int = 0) -> str:
    """
    Fetch current weather (and optional forecast) for a location.

    Args:
        location: City name (e.g. 'London', 'Tokyo', 'New York')
        forecast_days: Number of forecast days (0 = current weather only, max 7)

    Returns:
        Formatted string with weather data, or error message.
    """
    # ── 1. Geocode location → lat/lon ──
    coords = _geocode(location)
    if coords is None:
        return f"Could not find location: {location}"

    lat, lon, resolved_name = coords

    # ── 2. Fetch weather ──
    return _fetch_weather(lat, lon, resolved_name, forecast_days)


def _geocode(location: str) -> tuple[float, float, str] | None:
    """Resolve a city name to (lat, lon, display_name) via Open-Meteo Geocoding."""
    import urllib.parse
    encoded = urllib.parse.quote(location.strip())
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=3&language=en&format=json"

    try:
        req = Request(url, headers={"User-Agent": "Raphael/1.0"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.error("Geocoding API error: %s", e)
        return None

    if not data.get("results"):
        return None

    result = data["results"][0]
    lat = result["latitude"]
    lon = result["longitude"]
    name = result.get("name", location)
    country = result.get("country", "")
    admin1 = result.get("admin1", "")
    display = f"{name}"
    if admin1:
        display += f", {admin1}"
    if country and country not in display:
        display += f", {country}"

    return (lat, lon, display)


def _fetch_weather(lat: float, lon: float, display_name: str, forecast_days: int) -> str:
    """Fetch weather data from Open-Meteo API."""
    # Build params
    params = (
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        f"weather_code,wind_speed_10m,wind_direction_10m,pressure_msl,uv_index"
        f"&daily=temperature_2m_max,temperature_2m_min,weather_code,"
        f"precipitation_probability_max,wind_speed_10m_max"
        f"&timezone=auto&forecast_days={max(1, forecast_days)}"
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"

    try:
        req = Request(url, headers={"User-Agent": "Raphael/1.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return f"Weather API error: {e}"

    current = data.get("current", {})
    daily = data.get("daily", {})
    current_units = data.get("current_units", {})

    # ── Build output ──
    lines = [f"**Weather for {display_name}**"]
    lines.append("")

    # Current conditions
    if current:
        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        code = current.get("weather_code")
        wind = current.get("wind_speed_10m")
        wind_dir = current.get("wind_direction_10m")
        pressure = current.get("pressure_msl")
        uv = current.get("uv_index")

        temp_u = current_units.get("temperature_2m", "°C")
        wind_u = current_units.get("wind_speed_10m", "km/h")

        lines.append(f"🌡️  **Current:** {temp}{temp_u} (feels like {feels}{temp_u})")
        lines.append(f"☁️  **Condition:** {_weather_description(code)}")
        lines.append(f"💧 **Humidity:** {humidity}%")
        lines.append(f"🌬️ **Wind:** {wind} {wind_u} {_wind_direction(wind_dir)}")
        lines.append(f"🔵 **Pressure:** {pressure} hPa")
        if uv is not None:
            lines.append(f"☀️ **UV Index:** {uv}")
        lines.append("")

    # Forecast
    if forecast_days > 0 and daily:
        times = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        precip = daily.get("precipitation_probability_max", [])

        lines.append(f"**📅 {forecast_days}-Day Forecast:**")
        for i in range(min(len(times), forecast_days)):
            day = _format_day(times[i])
            high = highs[i] if i < len(highs) else "?"
            low = lows[i] if i < len(lows) else "?"
            wcode = codes[i] if i < len(codes) else 0
            rain = precip[i] if i < len(precip) else None
            desc = _weather_description(wcode)
            rain_str = f"  ☔ {rain}%" if rain is not None else ""
            lines.append(f"  {day}: {desc}  {low}–{high}{temp_u}{rain_str}")

    return "\n".join(lines).strip()


def _weather_description(code: int) -> str:
    """Map WMO weather codes to readable text."""
    if code == 0: return "Clear sky"
    if code == 1: return "Mainly clear"
    if code == 2: return "Partly cloudy"
    if code == 3: return "Overcast"
    if code in (45, 48): return "Foggy"
    if code in (51, 53, 55): return "Drizzle"
    if code in (56, 57): return "Freezing drizzle"
    if code in (61, 63, 65): return "Rain"
    if code in (66, 67): return "Freezing rain"
    if code in (71, 73, 75): return "Snowfall"
    if code == 77: return "Snow grains"
    if code in (80, 81, 82): return "Rain showers"
    if code in (85, 86): return "Snow showers"
    if code == 95: return "Thunderstorm"
    if code in (96, 99): return "Thunderstorm with hail"
    return "Unknown"


def _wind_direction(deg: float | None) -> str:
    """Convert wind direction degrees to compass direction."""
    if deg is None: return ""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(deg / 22.5) % 16
    return dirs[idx]


def _format_day(date_str: str) -> str:
    """Format ISO date string to readable day name."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        if dt.date() == now.date():
            return "Today"
        tomorrow = now.replace(day=now.day + 1)
        if dt.date() == tomorrow.date():
            return "Tomorrow"
        return dt.strftime("%A")  # Monday, Tuesday, etc.
    except ValueError:
        return date_str
