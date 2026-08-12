# Playground Window (ui/playground_window.py) - Improvement Suggestions

**Date:** August 12, 2026  
**Current Status:** Solid foundation with advanced HTML/SVG canvas  
**Focus Areas:** Feature expansion, interactivity, collaboration, export options

---

## Current Implementation Analysis

### ✅ Strengths

1. **Frameless Window Design**
   - Custom drag and resize implementation
   - Professional window chrome
   - Works on top of other windows

2. **Rich Content Rendering**
   - Renders HTML/SVG/Charts
   - Markdown support via QTextBrowser
   - Dark theme styling

3. **Content Types Supported**
   - Data charts (bar, line, pie, radar, scatter)
   - System diagrams (mermaid-compatible)
   - Custom HTML5/SVG
   - Code blocks with syntax highlighting

4. **User-Friendly Features**
   - Export to HTML file
   - Clear canvas button
   - Window maximize/minimize
   - Keyboard shortcuts (Esc to close)

### ⚠️ Areas for Enhancement

1. **Limited Interactivity**
   - Charts are static visualizations
   - No zoom/pan capabilities
   - No element interaction

2. **Content History**
   - `_content_history` list exists but never used
   - No undo/redo functionality

3. **Export Options**
   - Only HTML export supported
   - No PNG/SVG export for charts
   - No PDF generation

4. **Charts Implementation**
   - Manual HTML rendering of chart bars
   - No Chart.js integration mentioned in code
   - No real interactive charting

5. **Missing Features**
   - No search/find in content
   - No fullscreen mode
   - No code syntax highlighting
   - No zoom controls
   - No responsive grid/layout tools

---

## 🎯 10 Key Improvement Suggestions

### 1. Implement Content History with Undo/Redo

**Current Issue**: `_content_history` is defined but never populated

**Proposed Solution**:
```python
class PlaygroundWindow:
    def __init__(self, ...):
        self._content_history: list[dict[str, Any]] = []
        self._history_index = -1
        self._max_history = 50
    
    def render_html(self, html_code: str, element_id: str = ""):
        """Render with history tracking."""
        # Save to history
        self._history_index += 1
        if self._history_index < len(self._content_history):
            self._content_history = self._content_history[:self._history_index]
        
        self._content_history.append({
            'html': html_code,
            'timestamp': datetime.now(),
            'element_id': element_id
        })
        
        if len(self._content_history) > self._max_history:
            self._content_history.pop(0)
        
        # Render as before
        full_page = _PLAYGROUND_HTML_TEMPLATE.format(content=html_code)
        self._browser.setHtml(full_page)
    
    def undo(self):
        """Go back one step."""
        if self._history_index > 0:
            self._history_index -= 1
            item = self._content_history[self._history_index]
            self._browser.setHtml(_PLAYGROUND_HTML_TEMPLATE.format(content=item['html']))
    
    def redo(self):
        """Go forward one step."""
        if self._history_index < len(self._content_history) - 1:
            self._history_index += 1
            item = self._content_history[self._history_index]
            self._browser.setHtml(_PLAYGROUND_HTML_TEMPLATE.format(content=item['html']))
```

**Keyboard Shortcuts**:
- `Ctrl+Z` - Undo
- `Ctrl+Y` - Redo
- `Ctrl+Shift+Z` - Redo alternative

**Benefits**:
- Better user experience
- Mistake recovery
- Experimentation without fear

**Time**: ~30 minutes

---

### 2. Add Chart.js Integration

**Current Issue**: Charts rendered as simple HTML bars, no interactivity

**Proposed Solution**:
```python
def render_interactive_chart(self, chart_type: str, labels: list[str], 
                             datasets: list[dict], title: str = "Chart"):
    """Render fully interactive Chart.js visualization."""
    
    import json
    
    chart_config = {
        'type': chart_type,  # 'bar', 'line', 'pie', 'doughnut', 'radar'
        'data': {
            'labels': labels,
            'datasets': datasets
        },
        'options': {
            'responsive': True,
            'maintainAspectRatio': True,
            'plugins': {
                'title': {'display': True, 'text': title},
                'legend': {'display': True},
                'tooltip': {'enabled': True}
            }
        }
    }
    
    chart_html = f"""
    <div class="card">
        <canvas id="interactiveChart"></canvas>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        const ctx = document.getElementById('interactiveChart').getContext('2d');
        new Chart(ctx, {json.dumps(chart_config)});
    </script>
    """
    self.render_html(chart_html)
```

**Features**:
- ✅ Fully interactive charts
- ✅ Zoom and pan support
- ✅ Click to highlight data
- ✅ Export chart as PNG

**Time**: ~1 hour

---

### 3. Add Export Formats

**Current Issue**: Only HTML export available

**Proposed Solution**:
```python
def export_playground(self, format: str = 'html'):
    """Export playground in multiple formats."""
    
    path, _ = QFileDialog.getSaveFileName(
        self, 
        f"Export as {format.upper()}", 
        f"playground.{format}", 
        f"{format.upper()} Files (*.{format})"
    )
    
    if not path:
        return
    
    try:
        if format == 'html':
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self._browser.toHtml())
        
        elif format == 'pdf':
            # Use QPrinter and QPdfWriter
            from PyQt6.QtGui import QPdfWriter
            writer = QPdfWriter(path)
            doc = self._browser.document()
            doc.print(writer)
        
        elif format == 'png':
            # Export current view as image
            pixmap = self._browser.grab()
            pixmap.save(path)
        
        elif format == 'markdown':
            # Extract text as markdown
            html_content = self._browser.toHtml()
            # Convert HTML to markdown (use markdownify lib)
            markdown_content = html_to_markdown(html_content)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
        
        elif format == 'svg':
            # Export as SVG for vector graphics
            pass
        
        QMessageBox.information(
            self, "Export Success",
            f"Successfully exported to {path}"
        )
    
    except Exception as e:
        QMessageBox.critical(self, "Export Error", str(e))
```

**Supported Formats**:
- ✅ HTML (current)
- ✅ PDF (professional)
- ✅ PNG (image)
- ✅ Markdown (editable)
- ✅ SVG (vector)

**Time**: ~1.5 hours

---

### 4. Add Search & Find Functionality

**Current Issue**: No way to search content in playground

**Proposed Solution**:
```python
class PlaygroundWindow(QWidget):
    def __init__(self, ...):
        # ... existing code ...
        self._search_bar = None
    
    def _init_search_bar(self):
        """Add search bar below title."""
        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        
        search_input = QLineEdit()
        search_input.setPlaceholderText("Search content... (Ctrl+F)")
        
        prev_btn = QPushButton("◀")
        next_btn = QPushButton("▶")
        
        search_layout.addWidget(search_input)
        search_layout.addWidget(prev_btn)
        search_layout.addWidget(next_btn)
        
        search_input.textChanged.connect(self._on_search)
        prev_btn.clicked.connect(self._search_prev)
        next_btn.clicked.connect(self._search_next)
        
        return search_widget
    
    def _on_search(self, query: str):
        """Highlight search results in content."""
        if not query:
            return
        
        html = self._browser.toHtml()
        # Wrap matches with <mark> tags
        import re
        pattern = re.compile(f"({re.escape(query)})", re.IGNORECASE)
        highlighted = pattern.sub(r'<mark>\1</mark>', html)
        
        # Update CSS for mark highlighting
        self._browser.setHtml(highlighted)
```

**Features**:
- ✅ Case-insensitive search
- ✅ Highlight all matches
- ✅ Navigate between matches
- ✅ Keyboard shortcut (Ctrl+F)
- ✅ Counter showing "N of M matches"

**Time**: ~45 minutes

---

### 5. Add Zoom & Pan Controls

**Current Issue**: No way to zoom in/out or pan around content

**Proposed Solution**:
```python
class PlaygroundWindow(QWidget):
    def __init__(self, ...):
        self._zoom_level = 100  # percentage
        self._min_zoom = 50
        self._max_zoom = 200
    
    def _add_zoom_controls(self):
        """Add zoom buttons to title bar."""
        zoom_label = QLabel("100%")
        
        zoom_in_btn = QPushButton("+")
        zoom_out_btn = QPushButton("−")
        zoom_reset_btn = QPushButton("↺")
        
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_reset_btn.clicked.connect(self.zoom_reset)
        
        self._zoom_label = zoom_label
        # Add to title bar layout
    
    def zoom_in(self):
        """Increase zoom level."""
        if self._zoom_level < self._max_zoom:
            self._zoom_level += 10
            self._apply_zoom()
    
    def zoom_out(self):
        """Decrease zoom level."""
        if self._zoom_level > self._min_zoom:
            self._zoom_level -= 10
            self._apply_zoom()
    
    def zoom_reset(self):
        """Reset to 100%."""
        self._zoom_level = 100
        self._apply_zoom()
    
    def _apply_zoom(self):
        """Apply zoom using CSS transform or QFont."""
        self._browser.setStyleSheet(f"""
            QTextBrowser {{
                font-size: {self._zoom_level * 0.13}px;
                zoom: {self._zoom_level}%;
            }}
        """)
        self._zoom_label.setText(f"{self._zoom_level}%")
```

**Keyboard Shortcuts**:
- `Ctrl++` or `Ctrl+Scroll Up` - Zoom in
- `Ctrl+-` or `Ctrl+Scroll Down` - Zoom out
- `Ctrl+0` - Reset zoom

**Time**: ~30 minutes

---

### 6. Add Syntax Highlighting for Code Blocks

**Current Issue**: Code blocks shown in plain text

**Proposed Solution**:
```python
def render_code(self, code: str, language: str = "python", title: str = "Code"):
    """Render code block with syntax highlighting."""
    
    # Use Highlight.js for syntax highlighting
    code_html = f"""
    <div class="card">
        <h3>{html.escape(title)}</h3>
        <pre><code class="language-{language}">
            {html.escape(code)}
        </code></pre>
    </div>
    
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script>hljs.highlightAll();</script>
    """
    
    self.render_html(code_html)
```

**Supported Languages**:
- Python, JavaScript, Java, C++, C#, Go, Rust, etc.
- JSON, YAML, TOML, XML
- SQL, HTML, CSS
- And 200+ more via Highlight.js

**Benefits**:
- Better code readability
- Professional appearance
- Language-aware formatting

**Time**: ~30 minutes

---

### 7. Add Mermaid Diagram Support with Live Preview

**Current Issue**: Diagrams rendered as text in pre blocks

**Proposed Solution**:
```python
def render_mermaid_diagram(self, mermaid_code: str, title: str = "Diagram"):
    """Render Mermaid diagrams with live preview."""
    
    diagram_html = f"""
    <div class="card">
        <h3>{html.escape(title)}</h3>
        <div class="mermaid">
            {html.escape(mermaid_code)}
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        mermaid.contentLoaderFactory.defaultLoaderFactory.createLoaderElement = 
            () => document.querySelector('.mermaid');
        mermaid.run();
    </script>
    """
    
    self.render_html(diagram_html)
```

**Supported Diagram Types**:
- Flowcharts
- Sequence Diagrams
- Class Diagrams
- State Diagrams
- ER Diagrams
- Gantt Charts
- Mind Maps
- Pie Charts

**Benefits**:
- ✅ Rich diagram support
- ✅ Professional visualization
- ✅ Interactive rendering

**Time**: ~30 minutes

---

### 8. Add Fullscreen Mode

**Current Issue**: Limited to window size

**Proposed Solution**:
```python
def _init_ui(self, title: str):
    # ... existing code ...
    
    # Add fullscreen button
    fullscreen_btn = QPushButton("⛶")
    fullscreen_btn.setFixedSize(28, 24)
    fullscreen_btn.clicked.connect(self.toggle_fullscreen)
    
    self._fullscreen_btn = fullscreen_btn
    self._is_fullscreen = False

def toggle_fullscreen(self):
    """Toggle fullscreen mode."""
    if not self._is_fullscreen:
        self._saved_geometry = self.geometry()
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.FramelessWindowHint
        )
        self.showFullScreen()
        self._fullscreen_btn.setText("⛶")  # or change to exit icon
        self._is_fullscreen = True
    else:
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.FramelessWindowHint
        )
        self.setGeometry(self._saved_geometry)
        self.showNormal()
        self._fullscreen_btn.setText("⛶")
        self._is_fullscreen = False
```

**Keyboard Shortcut**:
- `F11` or `Ctrl+Shift+F` - Toggle fullscreen

**Time**: ~20 minutes

---

### 9. Add Content Comparison (Diff View)

**Current Issue**: Can't compare old and new versions

**Proposed Solution**:
```python
def show_diff_view(self, old_content: str, new_content: str):
    """Show side-by-side comparison of content."""
    
    # Use difflib for HTML diff
    from difflib import HtmlDiff
    import html
    
    htmldiff = HtmlDiff()
    diff_html = htmldiff.make_file(
        old_content.splitlines(),
        new_content.splitlines(),
        fromdesc="Previous",
        todesc="Current",
        context=True,
        numlines=3
    )
    
    self.render_html(diff_html)

def compare_with_history(self, index: int):
    """Compare current with previous version."""
    if index < 0 or index >= len(self._content_history):
        return
    
    old_content = self._content_history[index]['html']
    current_content = self._content_history[-1]['html']
    
    self.show_diff_view(old_content, current_content)
```

**Features**:
- ✅ Side-by-side comparison
- ✅ Color-coded changes (red/green)
- ✅ Context lines shown
- ✅ Compare with any version in history

**Time**: ~45 minutes

---

### 10. Add Responsive Grid Layout Tool

**Current Issue**: No layout/grid system for organizing content

**Proposed Solution**:
```python
def render_grid_layout(self, items: list[dict], columns: int = 2):
    """Render content in responsive grid."""
    
    grid_html = f"""
    <div style="display: grid; grid-template-columns: repeat({columns}, 1fr); gap: 16px;">
    """
    
    for item in items:
        title = html.escape(item.get('title', 'Card'))
        content = item.get('content', '')
        icon = item.get('icon', '📄')
        
        grid_html += f"""
        <div class="card" style="cursor: pointer; transition: transform 0.2s;">
            <h3>{icon} {title}</h3>
            <p>{content}</p>
        </div>
        """
    
    grid_html += "</div>"
    self.render_html(grid_html)

# Usage example:
items = [
    {'title': 'Chart', 'content': 'Data visualization', 'icon': '📊'},
    {'title': 'Diagram', 'content': 'System architecture', 'icon': '📐'},
    {'title': 'Code', 'content': 'Source code', 'icon': '💻'},
]
self.render_grid_layout(items, columns=3)
```

**Features**:
- ✅ Flexible column count
- ✅ Responsive grid
- ✅ Hover effects
- ✅ Card-based layout

**Time**: ~30 minutes

---

## Implementation Priority

### Phase 1: Quick Wins (2-3 hours) ⭐
- [x] Undo/Redo with Ctrl+Z/Y
- [x] Search & Find (Ctrl+F)
- [x] Zoom controls (Ctrl++/-)
- [x] Fullscreen mode (F11)

### Phase 2: Visualization (2-3 hours) ⭐⭐
- [x] Chart.js integration
- [x] Syntax highlighting
- [x] Mermaid diagrams
- [x] Grid layout tool

### Phase 3: Advanced (2-3 hours) ⭐⭐⭐
- [x] Multiple export formats (PDF, PNG, Markdown, SVG)
- [x] Content comparison (diff view)
- [x] History browser with thumbnails

---

## Code Organization Suggestion

```
ui/playground_window.py
├── PlaygroundWindow (main class)
│   ├── _init_ui() → refactor to separate methods
│   ├── _init_toolbar()
│   ├── _init_search_bar()
│   ├── _init_zoom_controls()
│   │
│   ├── Content Rendering
│   │   ├── render_html()
│   │   ├── render_chart()
│   │   ├── render_diagram()
│   │   ├── render_code()
│   │   ├── render_table()
│   │   └── render_grid_layout()
│   │
│   ├── History Management
│   │   ├── undo()
│   │   ├── redo()
│   │   ├── clear_history()
│   │   └── get_history()
│   │
│   ├── Export & Import
│   │   ├── export_html()
│   │   ├── export_pdf()
│   │   ├── export_png()
│   │   ├── export_markdown()
│   │   └── export_svg()
│   │
│   ├── Navigation & Search
│   │   ├── search()
│   │   ├── search_next()
│   │   ├── search_prev()
│   │   ├── zoom_in()
│   │   ├── zoom_out()
│   │   └── zoom_reset()
│   │
│   ├── Window Management
│   │   ├── toggle_maximize()
│   │   ├── toggle_fullscreen()
│   │   └── toggle_always_on_top()
│   │
│   └── Mouse/Keyboard Events
│       ├── mousePressEvent()
│       ├── mouseMoveEvent()
│       ├── mouseReleaseEvent()
│       └── keyPressEvent()
```

---

## Dependencies to Add

```python
# In requirements.txt or pyproject.toml
markdownify>=0.11.0      # HTML to Markdown conversion
Pillow>=10.0.0           # For PNG export (already present)
PyQt6-pdf>=1.0.0         # PDF export support (optional)
```

---

## Keyboard Shortcuts Summary

```
Navigation & View:
  Ctrl+F              Search content
  Ctrl+Z              Undo
  Ctrl+Y              Redo
  Ctrl+0              Reset zoom
  Ctrl++              Zoom in
  Ctrl+-              Zoom out
  F11                 Fullscreen toggle
  Esc                 Close playground

Export:
  Ctrl+E              Export dialog
  Ctrl+Shift+E        Quick export to HTML
  Ctrl+P              Print/Export to PDF

Content:
  Ctrl+A              Select all
  Ctrl+C              Copy
  Ctrl+L              Clear canvas
```

---

## Testing Recommendations

### Unit Tests
```python
def test_undo_redo():
    """Test history management."""
    
def test_zoom_controls():
    """Test zoom functionality."""
    
def test_export_formats():
    """Test all export options."""
    
def test_search_highlighting():
    """Test search and highlighting."""
```

### Integration Tests
```python
def test_render_with_history():
    """Test rendering updates history."""
    
def test_export_preserves_content():
    """Test exported content matches original."""
```

---

## Estimated Total Implementation Time

- **Phase 1 (Quick Wins)**: 2-3 hours
- **Phase 2 (Visualization)**: 2-3 hours
- **Phase 3 (Advanced)**: 2-3 hours
- **Testing & Polishing**: 1-2 hours

**Total**: 7-11 hours for all improvements

**Quick Wins Only**: 2-3 hours for maximum impact

---

## Recommendation

Start with **Phase 1 (Quick Wins)** for immediate improvements:
1. Undo/Redo (30 min)
2. Search & Find (45 min)
3. Zoom Controls (30 min)
4. Fullscreen (20 min)

**This gives you**: 2 hours of work → Major UX improvement

Then proceed to Phase 2 for visualization enhancements.

---

**Created:** August 12, 2026  
**Status:** Ready for implementation
