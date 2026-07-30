"""
Animated HUD canvas for Raphael.
Draws pulsing state indicators, spinning rings, particle effects,
and status text at 60fps via QTimer.
"""

import math
import random

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QConicalGradient, QFont,
                         QPainter, QPen,
                         QRadialGradient)
from PyQt6.QtWidgets import QWidget
import contextlib


# ── Color palette ──────────────────────────────────────────────────────

C_BG        = QColor("#00060a")
C_CYAN      = QColor("#00d4ff")
C_GREEN     = QColor("#00ff88")
C_ORANGE    = QColor("#ff6b00")
C_PINK      = QColor("#ff3366")
C_YELLOW    = QColor("#ffd700")
C_GRID      = QColor("#0a1a2a")
C_TEXT      = QColor("#aaaaaa")
C_WHITE     = QColor("#ffffff")

_STATE_COLORS = {
    "INITIALISING": QColor("#00d4ff"),
    "LISTENING":    QColor("#00ff88"),
    "SPEECHING":    QColor("#00d4ff"),
    "THINKING":     QColor("#ffd700"),
    "SPEAKING":     QColor("#ff6b00"),
    "SLEEPING":     QColor("#336677"),
    "MUTED":        QColor("#ff3366"),
    "IDLE":         QColor("#336677"),
    "CHAT":         QColor("#8888ff"),
}


class HudCanvas(QWidget):
    """Custom-painted HUD with animated state indicators."""

    # Thread-safe signals for cross-thread updates
    _state_signal = pyqtSignal(str)
    _muted_signal = pyqtSignal(bool)
    _mic_available_signal = pyqtSignal(bool)
    _transcription_signal = pyqtSignal(str)
    _mic_level_signal = pyqtSignal(float)

    # Mouse interaction signal
    mouse_clicked = pyqtSignal(str)  # "left" or "right"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #00060a;")

        # ── State ──
        self._state = "INITIALISING"
        self._muted = False
        self._mic_available = True
        self._transcription = ""      # last transcribed text
        self._mic_level = 0.0         # 0.0–1.0 from MicLevelMonitor

        # ── Animation interpolators ──
        self._pulse = 0.0          # 0..1
        self._ring_rot = 0.0       # degrees
        self._halo_radius = 0.0    # expands on SPEAKING
        self._particles: list[dict] = []
        self._blink = False

        # ── Timers ──
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._step)
        self._anim_timer.start(16)  # ~60fps

        # Spawn particles
        self._spawn_particles(20)

        # Connect thread-safe signals to actual setters
        self._state_signal.connect(self._set_state)
        self._muted_signal.connect(self._set_muted)
        self._mic_available_signal.connect(self._set_mic_available)
        self._transcription_signal.connect(self._set_transcription)
        self._mic_level_signal.connect(self._set_mic_level)

    # ── Public API (thread-safe — use signals) ──

    def set_state(self, state: str):
        try:
            self._state_signal.emit(state.upper())
        except RuntimeError:
            pass  # event dispatcher already destroyed during shutdown

    def set_muted(self, muted: bool):
        with contextlib.suppress(RuntimeError):
            self._muted_signal.emit(muted)

    def set_audio_input_available(self, available: bool):
        with contextlib.suppress(RuntimeError):
            self._mic_available_signal.emit(available)

    def set_transcription(self, text: str):
        """Display the latest transcribed text on the HUD."""
        with contextlib.suppress(RuntimeError):
            self._transcription_signal.emit(text)

    def set_mic_level(self, level: float):
        """Update the live mic level display (0.0–1.0)."""
        with contextlib.suppress(RuntimeError):
            self._mic_level_signal.emit(level)

    # ── Internal setters (always on GUI thread) ──

    def _set_state(self, state: str):
        self._state = state

    def _set_muted(self, muted: bool):
        self._muted = muted

    def _set_mic_available(self, available: bool):
        self._mic_available = available

    def _set_transcription(self, text: str):
        self._transcription = text

    def _set_mic_level(self, level: float):
        self._mic_level = max(0.0, min(1.0, level))

    def color(self) -> QColor:
        if not self._mic_available:
            return QColor("#555555")
        if self._muted:
            return C_PINK
        return _STATE_COLORS.get(self._state, C_CYAN)

    # ── Animation step ──

    def _step(self):
        dt = 0.016  # 16ms
        state = self._state

        # Update pulse
        speed = 2.0 if state == "SPEAKING" else (1.5 if state == "THINKING" else 1.0)
        self._pulse = (self._pulse + dt * speed) % 1.0

        # Update ring rotation
        rot_speed = 60 if state == "SPEAKING" else (40 if state == "THINKING" else 20)
        self._ring_rot = (self._ring_rot + dt * rot_speed) % 360

        # Halo radius — expands during SPEAKING
        target_halo = 80 if state == "SPEAKING" else 0
        self._halo_radius += (target_halo - self._halo_radius) * dt * 4

        # Blink
        self._blink = int(self._pulse * 4) % 2 == 0

        # Particles
        for p in self._particles:
            p["x"] += p["vx"] * dt * 60
            p["y"] += p["vy"] * dt * 60
            p["life"] -= dt
            p["size"] = max(0.5, p["size"] - dt * 0.5)

        # Remove dead, spawn new
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        self._particles = [p for p in self._particles if p["life"] > 0]
        if len(self._particles) < 15:
            self._spawn_particles(3, cx, cy)

        self.update()

    def _spawn_particles(self, count: int, cx: float | None = None, cy: float | None = None):
        if cx is None:
            cx = self.width() / 2
        if cy is None:
            cy = self.height() / 2
        color = self.color()
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.5, 2.0)
            self._particles.append({
                "x": cx + random.uniform(-60, 60),
                "y": cy + random.uniform(-60, 60),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "life": random.uniform(0.5, 2.0),
                "size": random.uniform(1.5, 4.0),
                "color": QColor(
                    min(255, color.red() + random.randint(-30, 30)),
                    min(255, color.green() + random.randint(-30, 30)),
                    min(255, color.blue() + random.randint(-30, 30)),
                    180,
                ),
            })

    # ── Paint ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # Background
        p.fillRect(0, 0, w, h, C_BG)

        # Grid dots
        self._draw_grid(p, w, h)

        # Halo (background glow when speaking)
        if self._halo_radius > 1:
            self._draw_halo(p, cx, cy)

        # Outer ring (spinning)
        self._draw_outer_ring(p, cx, cy)

        # Mic level arc (outside outer ring)
        self._draw_mic_level(p, cx, cy)

        # Scanner arc
        self._draw_scanner(p, cx, cy)

        # Crosshairs
        self._draw_crosshair(p, cx, cy)

        # Particles
        self._draw_particles(p)

        # Center indicator
        self._draw_center_dot(p, cx, cy)

        # Status text
        self._draw_status(p, cx, h)

        p.end()

    def _draw_grid(self, p: QPainter, w: int, h: int):
        p.setPen(QPen(C_GRID, 0.5))
        spacing = 40
        for x in range(spacing, w, spacing):
            for y in range(spacing, h, spacing):
                p.drawPoint(QPointF(x, y))

    def _draw_halo(self, p: QPainter, cx: float, cy: float):
        r = self._halo_radius
        grad = QRadialGradient(cx, cy, r)
        c = self.color()
        c.setAlpha(30)
        grad.setColorAt(0.0, c)
        c2 = QColor(c)
        c2.setAlpha(0)
        grad.setColorAt(1.0, c2)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _draw_outer_ring(self, p: QPainter, cx: float, cy: float):
        r = 80 + 5 * math.sin(self._pulse * math.pi * 2)
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        # Arc segments
        color = self.color()
        pen = QPen(color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)

        segments = 3
        arc_len = 60  # degrees per arc
        gap = 360 / segments - arc_len
        for i in range(segments):
            start = self._ring_rot + i * (arc_len + gap)
            p.drawArc(rect, int(start * 16), int(arc_len * 16))

        # Inner ring
        r2 = r - 15
        rect2 = QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2)
        dim_color = QColor(color)
        dim_color.setAlpha(60)
        p.setPen(QPen(dim_color, 1))
        p.drawArc(rect2, 0, 360 * 16)

    def _draw_mic_level(self, p: QPainter, cx: float, cy: float):
        """Draw a live mic level arc outside the outer ring.

        The arc fills from the bottom (270°) clockwise as the mic
        level increases.  Color shifts from green → yellow → orange
        so the user can see both quiet and loud input at a glance.
        """
        level = self._mic_level
        # Don't draw during IDLE / SLEEPING / MUTED unless there is
        # actually signal (avoids a dim arc being distracting)
        if level < 0.02:
            return

        r = 105 + 3 * math.sin(self._pulse * math.pi * 2)

        # Map level 0→1 to arc span 0→270 degrees (leave 90° gap at
        # the top so it looks like a proper meter)
        span_deg = min(270, int(level * 270))
        start_deg = 135 * 16  # start at bottom-left (135° = 7:30)

        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        # Color ramp: green (0.0) → yellow (0.5) → orange (1.0)
        if level < 0.5:
            t = level / 0.5
            c = QColor(
                int(0 + 255 * t),         # R: 0 → 255
                255,                       # G: 255
                int(136 - 136 * t),        # B: 136 → 0
            )
        else:
            t = (level - 0.5) / 0.5
            c = QColor(
                255,                               # R: 255
                int(255 - 255 * t),                # G: 255 → 0
                int(max(0, 68 - 68 * t)),          # B: 68 → 0
            )

        # Glow behind the arc
        glow = QColor(c)
        glow.setAlpha(30)
        p.setPen(QPen(glow, 8))
        p.drawArc(rect, start_deg, span_deg * 16)

        # Main arc
        c.setAlpha(200)
        pen = QPen(c, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, start_deg, span_deg * 16)

        # Small numerical indicator below the HUD
        p.setPen(QColor("#888888"))
        font = QFont("Consolas", 8)
        p.setFont(font)
        p.drawText(QRectF(cx - 20, cy + r + 10, 40, 16),
                   Qt.AlignmentFlag.AlignCenter, f"{int(level * 100)}%")

    def _draw_scanner(self, p: QPainter, cx: float, cy: float):
        """Spinning scanner wedge."""
        color = self.color()
        color.setAlpha(40)
        grad = QConicalGradient(cx, cy, self._ring_rot)
        color_start = QColor(color)
        color_start.setAlpha(80)
        grad.setColorAt(0.0, color_start)
        color_end = QColor(color)
        color_end.setAlpha(0)
        grad.setColorAt(0.08, color_end)
        grad.setColorAt(1.0, color_end)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPie(QRectF(cx - 80, cy - 80, 160, 160),
                  int(self._ring_rot * 16), (30 * 16))

    def _draw_crosshair(self, p: QPainter, cx: float, cy: float):
        color = self.color()
        color.setAlpha(60)
        p.setPen(QPen(color, 1))
        gap = 15
        arm = 40
        # Horizontal
        p.drawLine(QPointF(cx - arm, cy), QPointF(cx - gap, cy))
        p.drawLine(QPointF(cx + gap, cy), QPointF(cx + arm, cy))
        # Vertical
        p.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy - gap))
        p.drawLine(QPointF(cx, cy + gap), QPointF(cx, cy + arm))

    def _draw_particles(self, p: QPainter):
        for pt in self._particles:
            c = pt["color"]
            c.setAlpha(int(max(0, min(255, c.alpha() * pt["life"]))))
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["size"], pt["size"])

    def _draw_center_dot(self, p: QPainter, cx: float, cy: float):
        color = self.color()
        intensity = 0.6 + 0.4 * math.sin(self._pulse * math.pi * 2)

        # Outer glow
        glow_r = 20 + 8 * (1 - intensity)
        grad = QRadialGradient(cx, cy, glow_r)
        c_glow = QColor(color)
        c_glow.setAlpha(int(60 * intensity))
        grad.setColorAt(0.0, c_glow)
        c_end = QColor(color)
        c_end.setAlpha(0)
        grad.setColorAt(1.0, c_end)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # Core
        core_r = 4 + 2 * (1 - intensity)
        c_core = QColor(color)
        c_core.setAlpha(int(255 * intensity))
        p.setBrush(QBrush(c_core))
        p.setPen(QPen(QColor(color), 1))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

    def _draw_status(self, p: QPainter, cx: float, h: float):
        # State indicator
        state_text = self._state
        if not self._mic_available:
            state_text = "NO MIC"
        elif self._muted:
            state_text = "MUTED"
        p.setPen(C_TEXT)
        font = QFont("Consolas", 11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, h - 60, cx * 2, 30),
                   Qt.AlignmentFlag.AlignCenter, state_text)

        # Transcription text (shown prominently below state)
        if self._transcription:
            txt = self._transcription
            if len(txt) > 60:
                txt = txt[:57] + "..."
            p.setPen(QColor("#cccccc"))
            font2 = QFont("Consolas", 13)
            font2.setBold(False)
            p.setFont(font2)
            p.drawText(QRectF(40, h - 95, cx * 2 - 80, 40),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, txt)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_clicked.emit("left")
        elif event.button() == Qt.MouseButton.RightButton:
            self.mouse_clicked.emit("right")
        super().mousePressEvent(event)

