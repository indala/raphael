"""Weather tool — get current weather and forecast."""

from modules import weather as _weather


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather and forecast for any location worldwide. Free, no API key needed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name (e.g. 'London', 'Tokyo', 'New York')",
                        },
                        "forecast_days": {
                            "type": "integer",
                            "description": "Number of forecast days (0 = current only, max 7)",
                            "default": 0,
                        },
                    },
                    "required": ["location"],
                },
            },
        },
    ]


def get_weather(location: str, forecast_days: int = 0) -> str:
    """Get current weather (and optional forecast) for a location."""
    return _weather.get_weather(location, forecast_days)
