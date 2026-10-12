import time
import math
import random

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPointF, QRectF
from PyQt5.QtWidgets import QWidget, QGraphicsOpacityEffect
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient


class AmbientBackground(QWidget):
    def __init__(self, palette, anim_cfg, parent=None):
        super().__init__(parent)
        self.bg = QColor(palette.get('bg', '#0A0C0F'))
        self.accent = QColor(palette.get('accent', '#EEEEEE'))
        self._t0 = time.monotonic()
        self._dots = []
        for _ in range(64):
            self._dots.append((
                random.random(),
                random.random(),
                random.uniform(0.4, 1.4),
                random.uniform(0.5, 1.6),
            ))
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)
        self.set_anim(anim_cfg)

    def set_palette(self, palette):
        self.bg = QColor(palette.get('bg', '#0A0C0F'))
        self.accent = QColor(palette.get('accent', '#EEEEEE'))
        self.update()

    def set_anim(self, anim_cfg):
        self._particles = bool(anim_cfg.get('particles'))
        self._scanline = bool(anim_cfg.get('scanline'))
        if self._particles or self._scanline:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self.bg)

        if self._particles or self._scanline:
            t = time.monotonic() - self._t0
            w = self.width()
            h = self.height()

        if self._particles:
            p.setRenderHint(QPainter.Antialiasing, True)
            for (rx, ry, speed, size) in self._dots:
                x = rx * w
                y = ((ry * h + t * 9.0 * speed) % (h + 24.0)) - 12.0
                pulse = 0.5 + 0.5 * math.sin(t * (0.5 + speed * 0.5) + rx * 6.283)
                c = QColor(self.accent)
                c.setAlphaF(0.05 + 0.16 * pulse)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                r = 1.0 + size * 3.0
                p.drawEllipse(QPointF(x, y), r, r)

        if self._scanline:
            p.setRenderHint(QPainter.Antialiasing, False)
            phase = (t * 0.10) % 1.0
            x0 = -w + phase * (w * 2.0)
            grad = QLinearGradient(x0, 0, x0 + w * 0.4, h)
            c1 = QColor(self.accent); c1.setAlphaF(0.0)
            c2 = QColor(self.accent); c2.setAlphaF(0.045)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            p.setPen(Qt.NoPen)
            p.setBrush(grad)
            p.drawRect(self.rect())

            c3 = QColor(self.accent); c3.setAlphaF(0.04)
            p.setPen(QPen(c3, 1))
            for i in range(4):
                yy = int((h * 0.25 * i + t * 5.0) % h)
                p.drawLine(0, yy, w, yy)

        p.end()


def fade_in(widget, duration=340, delay=0, on_done=None):
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b'opacity', widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    if on_done is not None:
        anim.finished.connect(on_done)
    if delay:
        QTimer.singleShot(delay, anim.start)
    else:
        anim.start()
    widget._fade_anim = anim
    return anim


def fade_out(widget, duration=260, on_done=None):
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b'opacity', widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.InCubic)
    if on_done is not None:
        anim.finished.connect(on_done)
    anim.start()
    widget._fade_anim = anim
    return anim


class PulseRepainter:
    def __init__(self, view, anim_cfg):
        self.view = view
        self.enabled = bool(anim_cfg.get('selection_pulse'))
        self.timer = QTimer(view)
        self.timer.setInterval(33)
        self.timer.timeout.connect(lambda: view.viewport().update())

    def set_enabled(self, on):
        self.enabled = bool(on)
        self.sync()

    def sync(self):
        has_sel = False
        sm = self.view.selectionModel()
        if sm is not None:
            has_sel = bool(sm.hasSelection())
        active = self.enabled and has_sel
        if active and not self.timer.isActive():
            self.timer.start()
        elif not active and self.timer.isActive():
            self.timer.stop()


def pulse_alpha(enabled, t=None):
    if not enabled:
        return 1.0
    t = time.monotonic() if t is None else t
    return 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * 4.0))