"""
Typewriter-style activity log widget for Raphael HUD.
Color-coded by tag: you, ai, err, file, sys.
"""

import os
import re
import html
from urllib.parse import quote, unquote
from typing import Any
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QPixmap, QTextCharFormat, QTextCursor, QFont, QTextDocument
from PyQt6.QtWidgets import QTextBrowser, QApplication

# Try importing mistune for markdown AST parsing
try:
    import mistune
    _markdown_parser = mistune.create_markdown(plugins=['table'], renderer=None)
except ImportError:
    _markdown_parser: Any | None = None  # type: ignore[no-redef]


# ── Tag colors ────────────────────────────────────────────────────────────────

_TAG_COLORS = {
    "you":  QColor("#00d4ff"),  # cyan — user
    "ai":   QColor("#00ff88"),  # green — assistant
    "err":  QColor("#ff3366"),  # red — error
    "file": QColor("#ff6b00"),  # orange — file events
    "sys":  QColor("#888888"),  # gray — system
}

_DEFAULT_COLOR = QColor("#cccccc")


def _tag_color(tag: str) -> QColor:
    return _TAG_COLORS.get(tag, _DEFAULT_COLOR)


def _render_table_to_html(token: dict) -> str:
    """Helper to compile a mistune table token into a styled dark-themed HTML table."""
    html_output = ['<table width="100%" style="border-collapse: collapse; margin: 10px 0; border: 1px solid #1a2a35; font-family: Consolas, monospace; font-size: 11px;">']

    for part in token.get("children", []):
        part_type = part.get("type")
        if part_type == "table_head":
            html_output.append('<tr style="background-color: #0b1a24;">')
            for cell in part.get("children", []):
                cell_text = _render_inline_to_text(cell.get("children", []))
                html_output.append(f'<th style="border: 1px solid #1a2a35; padding: 6px 10px; text-align: left; color: #00d4ff; font-weight: bold;">{cell_text}</th>')
            html_output.append('</tr>')
        elif part_type == "table_body":
            for row in part.get("children", []):
                html_output.append('<tr>')
                for cell in row.get("children", []):
                    cell_text = _render_inline_to_text(cell.get("children", []))
                    html_output.append(f'<td style="border: 1px solid #1a2a35; padding: 6px 10px; color: #cccccc;">{cell_text}</td>')
                html_output.append('</tr>')

    html_output.append('</table>')
    return "".join(html_output)


def _render_inline_to_text(children: list) -> str:
    """Helper to convert inline tokens inside a cell to standard HTML/plain text."""
    result = []
    for token in children:
        token_type = token.get("type")
        if token_type == "text":
            result.append(html.escape(token.get("raw", "")))
        elif token_type == "strong":
            inner = _render_inline_to_text(token.get("children", []))
            result.append(f"<b>{inner}</b>")
        elif token_type == "emphasis":
            inner = _render_inline_to_text(token.get("children", []))
            result.append(f"<i>{inner}</i>")
        elif token_type == "codespan":
            result.append(f"<code>{html.escape(token.get('raw', ''))}</code>")
        elif token_type == "link":
            inner = _render_inline_to_text(token.get("children", []))
            result.append(inner)
    return "".join(result)


def _preprocess_markdown(text: str) -> str:
    """Preprocess markdown to fix common LLM formatting issues like table row concatenation with '||'
    and mismatched column counts which cause mistune to fail table parsing."""
    parts = text.split("```")
    for i in range(len(parts)):
        if i % 2 == 0:
            content = parts[i]
            if "|" in content and "||" in content:
                content = content.replace("||", "|\n|")

            lines = content.split('\n')
            in_table = False
            header_cols = 0
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('|') and (stripped.endswith('|') or stripped.count('|') >= 2):
                    if '---|' in stripped or '--:|' in stripped or ':-:|' in stripped or '---' in stripped:
                        new_lines.append(line)
                        continue

                    pipes = stripped.count('|')
                    cols = pipes - 1 if stripped.endswith('|') else pipes

                    if not in_table:
                        in_table = True
                        header_cols = cols
                        new_lines.append(line)
                    else:
                        current_cols = cols
                        if current_cols < header_cols:
                            diff = header_cols - current_cols
                            if line.endswith('|'):
                                line = line[:-1] + ('|' * diff) + '|'
                            else:
                                line = line + ('|' * diff)
                        new_lines.append(line)
                else:
                    in_table = False
                    new_lines.append(line)
            parts[i] = '\n'.join(new_lines)

    return "```".join(parts)


def _parse_tokens_to_typing_items(tokens: list, tag: str, widget: QTextBrowser) -> list[tuple]:
    """Recursively traverse mistune AST tokens to generate a list of typing actions."""
    base_color = _tag_color(tag)

    base_fmt = QTextCharFormat()
    base_fmt.setForeground(base_color)
    base_fmt.setFontFamily("Consolas")
    base_fmt.setFontPointSize(11)

    typing_items: list[tuple] = []

    def traverse(node_list: list, fmt: QTextCharFormat, parent_type: str | None = None, list_level: int = 0, item_index: int = 1, is_ordered: bool = False):
        for token in node_list:
            t_type = token.get("type")

            if t_type == "paragraph":
                traverse(token.get("children", []), fmt, t_type, list_level, item_index, is_ordered)
                if parent_type != "list_item":
                    typing_items.append(("char", "\n", fmt))

            elif t_type == "heading":
                attrs = token.get("attrs", {})
                level = attrs.get("level", token.get("level", 2))
                h_fmt = QTextCharFormat(fmt)
                h_fmt.setFontWeight(QFont.Weight.Bold)
                size = 13 + (6 - min(6, level))
                h_fmt.setFontPointSize(size)
                h_fmt.setForeground(QColor("#00d4ff"))

                traverse(token.get("children", []), h_fmt, t_type, list_level, item_index, is_ordered)
                typing_items.append(("char", "\n", h_fmt))

            elif t_type == "strong":
                strong_fmt = QTextCharFormat(fmt)
                strong_fmt.setFontWeight(QFont.Weight.Bold)
                traverse(token.get("children", []), strong_fmt, t_type, list_level, item_index, is_ordered)

            elif t_type == "emphasis":
                italic_fmt = QTextCharFormat(fmt)
                italic_fmt.setFontItalic(True)
                traverse(token.get("children", []), italic_fmt, t_type, list_level, item_index, is_ordered)

            elif t_type == "codespan":
                code_text = token.get("raw", "")
                code_fmt = QTextCharFormat(fmt)
                code_fmt.setFontFamily("Consolas")
                code_fmt.setForeground(QColor("#ffd700"))  # Gold
                code_fmt.setBackground(QColor("#0f1f2e"))  # Dark blue background
                code_fmt.setAnchor(True)
                code_fmt.setAnchorHref(f"cmd:{quote(code_text)}")

                for char in code_text:
                    typing_items.append(("char", char, code_fmt))

            elif t_type == "link":
                attrs = token.get("attrs", {})
                url = attrs.get("url", token.get("link", ""))
                link_fmt = QTextCharFormat(fmt)
                link_fmt.setAnchor(True)
                link_fmt.setAnchorHref(url)
                link_fmt.setForeground(QColor("#00d4ff"))
                link_fmt.setFontUnderline(True)

                traverse(token.get("children", []), link_fmt, t_type, list_level, item_index, is_ordered)

            elif t_type == "list":
                ordered = token.get("attrs", {}).get("ordered", token.get("ordered", False))
                if parent_type == "list_item":
                    typing_items.append(("char", "\n", fmt))
                for idx, child in enumerate(token.get("children", [])):
                    traverse([child], fmt, t_type, list_level + 1, item_index=idx + 1, is_ordered=ordered)

            elif t_type == "list_item":
                bullet_fmt = QTextCharFormat(fmt)
                bullet_fmt.setForeground(QColor("#00d4ff"))
                bullet_fmt.setFontWeight(QFont.Weight.Bold)

                # Apply indentation based on list level
                indent_spaces = "    " * (list_level - 1)
                if indent_spaces:
                    typing_items.append(("char", indent_spaces, fmt))

                # Determine prefix (number or bullet)
                prefix = f"{item_index}.  " if is_ordered else "•  "
                typing_items.append(("char", prefix, bullet_fmt))

                traverse(token.get("children", []), fmt, t_type, list_level, item_index, is_ordered)

                # Only add trailing newline if the last child was not a nested list
                children = token.get("children", [])
                has_nested_list = children and children[-1].get("type") == "list"
                if not has_nested_list:
                    typing_items.append(("char", "\n", fmt))

            elif t_type == "table":
                html_table = _render_table_to_html(token)
                typing_items.append(("html", html_table))
                typing_items.append(("char", "\n", fmt))

            elif t_type == "block_code":
                code_content = token.get("raw", "")
                clean_content = code_content.rstrip()
                info = token.get("attrs", {}).get("info", "")

                # HTML escape content and quote copy URL
                escaped_code = html.escape(clean_content)
                encoded_code = quote(clean_content)

                # Render code box wrapping in a fully-supported nested table layout
                html_code = (
                    f'<table width="100%" style="background-color: #1e293b; border-collapse: collapse; margin-top: 8px; margin-bottom: 8px; border: 1px solid #334155;">'
                    f'<tr>'
                    f'<td style="padding: 0;">'
                    f'<table width="100%" style="background-color: #0f172a; border-collapse: collapse;">'
                    f'<tr>'
                    f'<td style="padding: 8px 12px; color: #94a3b8; font-size: 10px; font-family: Consolas, monospace; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid #334155;">'
                    f'{info or "code"}'
                    f'</td>'
                    f'<td style="padding: 8px 12px; text-align: right; border-bottom: 1px solid #334155; width: 70px;">'
                    f'<a href="copy:{encoded_code}" style="color: #38bdf8; text-decoration: none; font-family: Consolas, monospace; font-size: 11px; font-weight: bold;">📋 Copy</a>'
                    f'</td>'
                    f'</tr>'
                    f'</table>'
                    f'<table width="100%" style="border-collapse: collapse;">'
                    f'<tr>'
                    f'<td style="padding: 12px; background-color: #1e293b; word-wrap: break-word;">'
                    f'<pre style="margin: 0; padding: 0; color: #e2e8f0; white-space: pre-wrap; font-family: Consolas, monospace; font-size: 11px; line-height: 150%; word-wrap: break-word;">{escaped_code}</pre>'
                    f'</td>'
                    f'</tr>'
                    f'</table>'
                    f'</td>'
                    f'</tr>'
                    f'</table>'
                )
                typing_items.append(("html", html_code))
                typing_items.append(("char", "\n", fmt))

            elif t_type == "block_quote":
                quote_text = ""
                for child in token.get("children", []):
                    if child.get("type") == "paragraph":
                        quote_text += _render_inline_to_text(child.get("children", []))

                # Render quote block using table to guarantee left border and background
                html_quote = (
                    f'<table width="100%" style="border-collapse: collapse; margin-top: 8px; margin-bottom: 8px;">'
                    f'<tr>'
                    f'<td style="border-left: 3px solid #00d4ff; padding-left: 10px; color: #888888; font-style: italic; font-family: Consolas, monospace; font-size: 11px;">'
                    f'{quote_text}'
                    f'</td>'
                    f'</tr>'
                    f'</table>'
                )
                typing_items.append(("html", html_quote))
                typing_items.append(("char", "\n", fmt))

            elif t_type == "thematic_break":
                html_hr = '<table width="100%" style="border-collapse: collapse; margin: 12px 0;"><tr><td style="border-top: 1px solid #334155; height: 1px; font-size: 1px; line-height: 1px;">&nbsp;</td></tr></table>'
                typing_items.append(("html", html_hr))
                typing_items.append(("char", "\n", fmt))

            elif t_type == "text":
                raw_text = token.get("raw", "")
                pattern = r'(".*?")'
                segments = re.split(pattern, raw_text)

                for segment in segments:
                    if not segment:
                        continue

                    if segment.startswith('"') and segment.endswith('"') and len(segment) >= 2:
                        inside_text = segment[1:-1]
                        quote_fmt = QTextCharFormat(fmt)
                        quote_fmt.setForeground(QColor("#00ff88"))
                        quote_fmt.setAnchor(True)
                        quote_fmt.setAnchorHref(f"cmd:{quote(inside_text)}")

                        typing_items.append(("char", '"', fmt))
                        for char in inside_text:
                            typing_items.append(("char", char, quote_fmt))
                        typing_items.append(("char", '"', fmt))
                    else:
                        for char in segment:
                            typing_items.append(("char", char, fmt))

            elif t_type == "block_text":
                traverse(token.get("children", []), fmt, t_type, list_level, item_index, is_ordered)

            elif t_type in ("image", "inline_image"):
                attrs = token.get("attrs", {})
                src = attrs.get("url", token.get("src", ""))
                alt = attrs.get("alt", token.get("alt", ""))
                if src:
                    abs_path = os.path.abspath(src)
                    if os.path.exists(abs_path):
                        pixmap = QPixmap(abs_path)
                        if not pixmap.isNull():
                            viewport_w = 400
                            vp = widget.viewport()
                            if vp is not None:
                                viewport_w = vp.width()
                            max_w = max(100, viewport_w - 40)
                            if pixmap.width() > max_w:
                                pixmap = pixmap.scaledToWidth(
                                    max_w, Qt.TransformationMode.SmoothTransformation
                                )
                            img_url = QUrl.fromLocalFile(abs_path)
                            doc = widget.document()
                            if doc is not None:
                                doc.addResource(
                                    QTextDocument.ResourceType.ImageResource, img_url, pixmap
                                )
                            widget._cached_images[abs_path] = img_url.toString()  # type: ignore[attr-defined]
                            encoded = quote(abs_path.replace("\\", "/"))
                            img_html = (
                                f'<a href="imgview:{encoded}" '
                                f'style="display:inline-block;text-decoration:none;">'
                                f'<img src="{img_url.toString()}" '
                                f'alt="{html.escape(alt)}" '
                                f'style="cursor:pointer;border-radius:6px;'
                                f'border:1px solid #1a2a35;" />'
                                f'</a>'
                            )
                            typing_items.append(("html", img_html))
                    typing_items.append(("char", "\n", fmt))

    traverse(tokens, base_fmt)
    return typing_items


class LogWidget(QTextBrowser):
    """Activity log with typewriter-style markdown rendering and clickable actions."""

    log_signal = pyqtSignal(str, str)  # tag, text
    stream_signal = pyqtSignal(str, str)  # tag, token (for streaming)
    command_clicked = pyqtSignal(str)   # text of clicked command

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # Enable selectability and clickable links
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        # We override mouseReleaseEvent instead of using anchorClicked + setSource
        # to avoid QTextBrowser's internal navigation adding history entries.

        self.setStyleSheet("""
            QTextBrowser {
                background-color: #00060a;
                color: #cccccc;
                border: 1px solid #1a2a35;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
            QScrollBar:vertical {
                background: #00060a;
                width: 8px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #1a2a35;
                border-radius: 4px;
                min-height: 20px;
            }
        """)

        self._buffer: list[tuple[str, list[tuple]]] = []  # pending log entries: (tag, typing_items)
        self._stream_buffer = ""
        self._typing_index = 0
        self._typing_tag = ""
        self._typing_items: list[tuple] = []
        self._cached_images: dict[str, str] = {}  # abs_path → QUrl cache key, for responsive resize
        self._active_steps = []
        self._steps_store = {}
        self._current_session_id = None

        self._typing_timer = QTimer(self)
        self._typing_timer.timeout.connect(self._type_char)
        self._typing_timer.setInterval(6)

        # Fast-forward: Space or click skips remaining typewriter animation
        self._skip_requested = False

        self.log_signal.connect(self._enqueue)
        self.stream_signal.connect(self._append_token)

    def start_steps_session(self, session_id: str):
        """Initialize a new execution steps tracking session."""
        self._current_session_id = session_id
        self._active_steps = []

    def add_step(self, tool_name: str, status: str, details: str):
        """Add an execution step to the active tracking session."""
        self._active_steps.append({
            "tool": tool_name,
            "status": status,
            "details": details
        })

    def commit_steps(self):
        """Commit the active steps session and render a collapsible details link in the log."""
        if not self._current_session_id or not self._active_steps:
            return

        session_id = self._current_session_id
        steps = list(self._active_steps)
        self._active_steps.clear()
        self._current_session_id = None

        # Save to store
        self._steps_store[session_id] = {
            "steps": steps,
            "expanded": False,
            "range": (0, 0)
        }

        # Build collapsed HTML
        collapsed_html = self._build_collapsed_steps_html(session_id, len(steps))

        # Insert at the end of the text browser
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        start_pos = cursor.position()
        cursor.insertHtml(collapsed_html)
        end_pos = cursor.position()

        # Save the range mapping
        self._steps_store[session_id]["range"] = (start_pos, end_pos)
        self.ensureCursorVisible()

    def toggle_steps(self, session_id: str):
        """Toggle the expansion state of a steps block and replace its document content."""
        store = self._steps_store.get(session_id)
        if not store:
            return

        expanded = not store.get("expanded", False)
        store["expanded"] = expanded

        start_pos, end_pos = store["range"]
        steps = store["steps"]

        if expanded:
            html_content = self._build_expanded_steps_html(session_id, steps)
        else:
            html_content = self._build_collapsed_steps_html(session_id, len(steps))

        # Save old scroll value to prevent viewport jumping
        scrollbar = self.verticalScrollBar()
        old_val = scrollbar.value() if scrollbar is not None else 0

        # Select the existing steps block range and insert replacement HTML
        cursor = self.textCursor()
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertHtml(html_content)

        # Update range mapping based on new text boundaries
        new_end_pos = cursor.position()
        store["range"] = (start_pos, new_end_pos)

        # Shift the positions of all subsequently committed steps blocks by the offset change
        offset = new_end_pos - end_pos
        if offset != 0:
            for sid, other_store in self._steps_store.items():
                if sid == session_id:
                    continue
                o_start, o_end = other_store["range"]
                if o_start >= end_pos:
                    other_store["range"] = (o_start + offset, o_end + offset)

        if scrollbar is not None:
            scrollbar.setValue(old_val)

    def _build_collapsed_steps_html(self, session_id: str, num_steps: int) -> str:
        return (
            f'<br>'
            f'<a href="toggle_steps:{session_id}" style="color: #00d4ff; text-decoration: none; font-family: Consolas; font-size: 11px; font-weight: bold;">'
            f'⚡ Ran {num_steps} step{"s" if num_steps > 1 else ""} [Show Details ▼]'
            f'</a>'
            f'<br>'
        )

    def _build_expanded_steps_html(self, session_id: str, steps: list) -> str:
        # Build badges row
        badges = []
        for step in steps:
            tool = step["tool"]
            status = step["status"]
            badge_color = "#00d4ff" if status == "success" else "#ff3366"
            bg_color = "#071624" if status == "success" else "#24070e"
            border_color = "#1a354a" if status == "success" else "#4a1a24"

            tool_label = tool.replace("_", " ").title()
            badges.append(
                f'<span style="background-color: {bg_color}; color: {badge_color}; border: 1px solid {border_color}; border-radius: 4px; padding: 2px 6px; font-family: Consolas; font-size: 10px; margin-right: 4px;">'
                f'{tool_label}'
                f'</span>'
            )
        badges_row = " ".join(badges)

        # Build detailed list
        details = []
        for step in steps:
            tool = step["tool"]
            status = step["status"]
            desc = step["details"]
            icon = "✓" if status == "success" else "✗"
            color = "#00ff88" if status == "success" else "#ff3366"

            tool_label = tool.replace("_", " ").title()
            # Escape HTML to prevent formatting issues
            import html
            escaped_desc = html.escape(desc)

            details.append(
                f'<div style="margin-top: 4px; font-family: Consolas; font-size: 11px;">'
                f'  <span style="color: {color}; font-weight: bold;">{icon} {tool_label}</span>: '
                f'  <span style="color: #888888;">{escaped_desc}</span>'
                f'</div>'
            )
        details_list = "".join(details)

        return (
            f'<br>'
            f'<a href="toggle_steps:{session_id}" style="color: #00d4ff; text-decoration: none; font-family: Consolas; font-size: 11px; font-weight: bold;">'
            f'⚡ Ran {len(steps)} step{"s" if len(steps) > 1 else ""} [Hide Details ▲]'
            f'</a>'
            f'<table width="100%" style="margin-top: 6px; margin-bottom: 6px; border-left: 2px solid #00d4ff; padding-left: 8px;">'
            f'  <tr>'
            f'    <td style="padding: 0;">'
            f'      <div style="margin-bottom: 6px;">{badges_row}</div>'
            f'      {details_list}'
            f'    </td>'
            f'  </tr>'
            f'</table>'
            f'<br>'
        )

    def write_log(self, tag: str, text: str):
        """Thread-safe log write (can be called from any thread)."""
        self.log_signal.emit(tag, text)

    def stream_token(self, tag: str, token: str):
        """Append a single token to the current log entry in real-time (thread-safe)."""
        self.stream_signal.emit(tag, token)

    def _enqueue(self, tag: str, text: str):
        if self._stream_buffer:
            self._remove_last_chars(len(self._stream_buffer))
            self._stream_buffer = ""
        items = self._parse_text_to_typing_items(tag, text)
        self._buffer.append((tag, items))
        if not self._typing_timer.isActive():
            self._start_next()

    def _append_token(self, tag: str, token: str):
        """Slot: append a token to the current position in real-time.
        Called from any thread via stream_signal."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(_tag_color(tag))
        fmt.setFontFamily("Consolas")
        fmt.setFontPointSize(11)
        cursor.insertText(token, fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._stream_buffer += token

    def _remove_last_chars(self, n: int):
        if n <= 0:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        pos = cursor.position()
        move_len = min(n, pos)
        if move_len > 0:
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, move_len)
            cursor.removeSelectedText()
            self.setTextCursor(cursor)

    def _parse_text_to_typing_items(self, tag: str, text: str) -> list[tuple]:
        if _markdown_parser is not None:
            try:
                text = _preprocess_markdown(text)
                tokens = _markdown_parser(text)
                return _parse_tokens_to_typing_items(tokens, tag, self)  # type: ignore[arg-type]
            except Exception:
                pass

        # Fallback to plain text typing if mistune is not available or fails
        base_color = _tag_color(tag)
        base_fmt = QTextCharFormat()
        base_fmt.setForeground(base_color)
        base_fmt.setFontFamily("Consolas")
        base_fmt.setFontPointSize(11)
        return [("char", char, base_fmt) for char in text]

    def _start_next(self):
        if not self._buffer:
            return
        tag, items = self._buffer.pop(0)
        self._typing_tag = tag
        self._typing_items = items
        self._typing_index = 0
        self._typing_timer.start()

    def _type_char(self):
        if self._typing_index >= len(self._typing_items):
            self._typing_timer.stop()
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            fmt = QTextCharFormat()
            fmt.setForeground(_tag_color(self._typing_tag))
            fmt.setFontFamily("Consolas")
            fmt.setFontPointSize(11)
            cursor.insertText("\n", fmt)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
            self._skip_requested = False
            self._start_next()
            return

        # Fast-forward: flush all remaining items instantly
        if self._skip_requested:
            self._flush_remaining()
            return

        item = self._typing_items[self._typing_index]
        item_type = item[0]

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        if item_type == "char":
            _, char, fmt = item
            cursor.insertText(char, fmt)
        elif item_type == "html":
            _, html_content = item
            # Create a separate paragraph block for HTML sections to isolate styling
            cursor.insertBlock()
            cursor.insertHtml(html_content)
            cursor.insertBlock()

        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._typing_index += 1

    def _flush_remaining(self):
        """Instantly render all remaining typing items and advance to next buffer entry."""
        self._typing_timer.stop()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        for item in self._typing_items[self._typing_index:]:
            item_type = item[0]
            if item_type == "char":
                _, char, fmt = item
                cursor.insertText(char, fmt)
            elif item_type == "html":
                _, html_content = item
                cursor.insertBlock()
                cursor.insertHtml(html_content)
                cursor.insertBlock()

        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._typing_index = len(self._typing_items)
        self._skip_requested = False
        # Finish current entry and start next
        fmt = QTextCharFormat()
        fmt.setForeground(_tag_color(self._typing_tag))
        fmt.setFontFamily("Consolas")
        fmt.setFontPointSize(11)
        cursor.insertText("\n", fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._start_next()

    def keyPressEvent(self, event):
        """Space bar fast-forwards the typewriter animation."""
        if event.key() == Qt.Key.Key_Space and self._typing_timer.isActive():
            self._skip_requested = True
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click fast-forwards the typewriter animation."""
        if self._typing_timer.isActive():
            self._skip_requested = True
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        """Intercept link clicks to prevent QTextBrowser from navigating (which hides chat)."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        # Check if click landed on an anchor
        cursor = self.cursorForPosition(event.position().toPoint())
        if cursor.charFormat().isAnchor():
            href = cursor.charFormat().anchorHref()
            if href.startswith("copy:"):
                text = unquote(href[5:])
                QApplication.clipboard().setText(text)  # type: ignore[union-attr]
                event.accept()
                return
            elif href.startswith("cmd:"):
                command = unquote(href[4:])
                QApplication.clipboard().setText(command)  # type: ignore[union-attr]
                self.command_clicked.emit(command)
                event.accept()
                return
            elif href.startswith("toggle_steps:"):
                session_id = href[13:]
                self.toggle_steps(session_id)
                event.accept()
                return
            elif href.startswith("imgview:"):
                path = unquote(href[8:]).replace("/", "\\")
                if os.path.exists(path):
                    os.startfile(path)
                event.accept()
                return
            else:
                # External link — open in browser
                import webbrowser
                webbrowser.open(href)
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        """Re-scale cached images when the widget is resized."""
        super().resizeEvent(event)
        vp = self.viewport()
        viewport_w = vp.width() if vp is not None else 400
        if self._cached_images:
            max_w = max(100, viewport_w - 40)
            doc = self.document()
            if doc is not None:
                for abs_path, url_str in list(self._cached_images.items()):
                    if not os.path.exists(abs_path):
                        continue
                    pixmap = QPixmap(abs_path)
                    if pixmap.isNull():
                        continue
                    if pixmap.width() > max_w:
                        pixmap = pixmap.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
                    doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(url_str), pixmap)
        doc = self.document()
        if doc is not None:
            doc.setTextWidth(viewport_w - 10)

    def clear_log(self):
        self._buffer.clear()
        self._typing_timer.stop()
        self.clear()
