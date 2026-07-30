"""
Chart generation module.
Creates static (matplotlib) and interactive (plotly) charts.
"""

from pathlib import Path


def create_matplotlib_chart(
    chart_type: str,
    title: str,
    labels: list,
    values: list,
    filename: str | None = None,
) -> str:
    """
    Create a chart using matplotlib and save as PNG.

    Returns:
        File path to the saved chart.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import config
    output_dir = Path(getattr(config, "CHART_DIR", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        import re
        safe = title.replace(" ", "_").lower()[:30]
        safe = re.sub(r'[\(\)\[\]{}%]', '', safe)
        filename = f"{safe}.png"

    filepath = output_dir / filename
    plt.figure(figsize=(10, 6))

    if chart_type == "line":
        plt.plot(labels, values, marker="o", linewidth=2, color="#2563eb")
    elif chart_type == "bar":
        colors = ["#3b82f6"] * len(labels)
        plt.bar(labels, values, color=colors)
    elif chart_type == "pie":
        plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
        plt.axis("equal")
    elif chart_type == "scatter":
        plt.scatter(range(len(values)), values, color="#3b82f6", s=100)
        plt.xticks(range(len(labels)), labels)

    plt.title(title, fontsize=14, pad=20)
    plt.tight_layout()
    plt.savefig(filepath, dpi=150)
    plt.close()

    return str(filepath)


def create_plotly_chart(
    chart_type: str,
    title: str,
    labels: list,
    values: list,
    filename: str | None = None,
) -> str:
    """
    Create an interactive chart using plotly and save as HTML.

    Returns:
        File path to the saved HTML file.
    """
    import config
    import plotly.graph_objects as go
    output_dir = Path(getattr(config, "CHART_DIR", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        import re
        safe = title.replace(" ", "_").lower()[:30]
        safe = re.sub(r'[\(\)\[\]{}%]', '', safe)
        filename = f"{safe}_interactive.html"

    filepath = output_dir / filename

    if chart_type in ("line", "scatter"):
        fig = go.Figure(data=go.Scatter(
            x=labels, y=values, mode="lines+markers"
        ))
    elif chart_type == "bar":
        fig = go.Figure(data=go.Bar(x=labels, y=values))
    elif chart_type == "pie":
        fig = go.Figure(data=go.Pie(labels=labels, values=values))
    else:
        fig = go.Figure(data=go.Bar(x=labels, y=values))

    fig.update_layout(title=title)
    fig.write_html(str(filepath))

    return str(filepath)
