"""Chart generation tool — static PNG or interactive HTML."""


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "generate_chart",
                "description": "Generate a chart from data and save it to the outputs folder. Can be static (PNG) or interactive (HTML).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chart_type": {
                            "type": "string",
                            "enum": ["line", "bar", "pie", "scatter"],
                            "description": "The type of chart to generate",
                        },
                        "title": {
                            "type": "string",
                            "description": "Chart title",
                        },
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Labels for the data points",
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Values for the data points",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["static", "interactive"],
                            "description": "Format of the chart: 'static' (matplotlib PNG) or 'interactive' (plotly HTML). Default is 'static'.",
                        },
                    },
                    "required": ["chart_type", "title", "labels", "values"],
                },
            },
        },
    ]


def generate_chart(
    chart_type: str,
    title: str,
    labels: list[str],
    values: list[float],
    format: str = "static",
) -> str:
    """Generate a chart (static PNG via matplotlib or interactive HTML via plotly)."""
    try:
        from modules import chart_gen
        if format == "interactive":
            filepath = chart_gen.create_plotly_chart(chart_type, title, labels, values)
            return f"Chart saved to `{filepath}`\nOpen the HTML file in a browser to view the interactive chart."
        else:
            filepath = chart_gen.create_matplotlib_chart(chart_type, title, labels, values)
            return f"![{title}]({filepath})"
    except Exception as e:
        return f"Failed to generate chart: {e}"
