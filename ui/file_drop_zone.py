import platform
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QDragEnterEvent, QDropEvent, QPixmap, QPainterPath
from PyQt6.QtWidgets import QWidget, QFileDialog, QVBoxLayout

_OS = platform.system()

# --- Helpers ---
def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c

_FILE_ICONS = {
    "image":   ("ðŸ–¼", "#00d4ff"), "video":   ("ðŸŽ¬", "#ff6b00"),
    "audio":   ("ðŸŽµ", "#cc44ff"), "pdf":     ("ðŸ“„", "#ff4444"),
    "word":    ("ðŸ“", "#4488ff"), "excel":   ("ðŸ“Š", "#44bb44"),
    "code":    ("ðŸ’»", "#ffcc00"), "archive": ("ðŸ“¦", "#ff8844"),
    "pptx":    ("ðŸ“Š", "#ff6622"), "text":    ("ðŸ“ƒ", "#aaaaaa"),
    "data":    ("ðŸ”§", "#88ddff"), "unknown": ("ðŸ“Ž", "#888888"),
}

_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)

        self._current_file: str | None = None
        self._preview_pixmap: QPixmap | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0

        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent | None):
        if e is None:
            return
        mime = e.mimeData()
        if mime is not None and mime.hasUrls():
            e.acceptProposedAction()
            self._drag_over = True
            self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self._canvas.update()

    def dropEvent(self, e: QDropEvent | None):
        if e is None:
            return
        self._drag_over = False
        mime = e.mimeData()
        if mime is not None:
            urls = mime.urls()
            if urls:
                path = urls[0].toLocalFile()
                if Path(path).is_file():
                    self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True
        self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False
        self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._preview_pixmap = None
        self._canvas.update()
        self.file_selected.emit("")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for Raphael", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._preview_pixmap = None
        if path:
            try:
                cat = _file_category(Path(path))
                if cat == "image":
                    self._preview_pixmap = QPixmap(path)
            except Exception:
                pass
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        # Background color
        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else "#010d14"))
        p.setBrush(QBrush(bg_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        # Border color
        if z._current_file:   border_col = qcol("#00ff88", 200) # Green
        elif z._drag_over:    border_col = qcol("#00d4ff", 230) # Cyan
        elif z._hovering:     border_col = qcol("#1a5c7a", 200) # Bright Blue
        else:                 border_col = qcol("#0d3347", 160) # Dark Blue

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol("#007a99" if not hover else "#00d4ff")
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))

        p.setFont(QFont("Consolas", 8))
        p.setPen(QPen(qcol("#007a99" if not hover else "#8ffcff"), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")

        p.setFont(QFont("Consolas", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code")

    def _paint_drag_over(self, p, W, H):
        _cx, cy = W / 2, H / 2
        p.setFont(QFont("Consolas", 20))
        p.setPen(QPen(qcol("#00d4ff"), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")

        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol("#00d4ff"), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)  # type: ignore[arg-type]
        cat  = _file_category(path)
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x = 12
        block_y = 12
        block_size = H - 24 # 76px

        # Draw image preview if available, otherwise draw generic emoji icon
        if cat == "image" and self._z._preview_pixmap and not self._z._preview_pixmap.isNull():
            p.save()
            path_clip = QPainterPath()
            path_clip.addRoundedRect(QRectF(block_x, block_y, block_size, block_size), 4, 4)
            p.setClipPath(path_clip)
            scaled_pixmap = self._z._preview_pixmap.scaled(
                block_size, block_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            px_w = scaled_pixmap.width()
            px_h = scaled_pixmap.height()
            p.drawPixmap(
                block_x + (block_size - px_w) // 2,
                block_y + (block_size - px_h) // 2,
                scaled_pixmap
            )
            p.restore()
        else:
            icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
            p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
            p.setPen(QPen(qcol(icon_col), 1))
            p.drawText(QRectF(block_x, 0, block_size, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_size + 12
        tw = W - tx - 38

        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol("#d8f8ff"), 1))
        name = path.name if len(path.name) <= 24 else path.name[:21] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Consolas", 7))
        p.setPen(QPen(qcol("#3a8a9a"), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Consolas", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 30: par = "â€¦" + par[-29:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        # Clear button ✖
        p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        p.setPen(QPen(qcol("#ff3355", 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✖")

    def mousePressEvent(self, e):
        z = self._z
        # If clicked near the close cross ✖, clear the file
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)

