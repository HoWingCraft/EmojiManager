import time

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QColor, QPainter, QPen, QFont


class PRTSSplash(QWidget):
    finished = pyqtSignal()

    def __init__(self, palette, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.palette = palette
        self.progress = 0.0
        self._t0 = time.monotonic()
        self._emitted = False
        self.resize(640, 340)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        self.progress = min(100.0, self.progress + 1.8)
        self.update()
        if self.progress >= 100.0 and not self._emitted:
            self._emitted = True
            self.timer.stop()
            QTimer.singleShot(260, self.finished.emit)

    def _c(self, key, fallback):
        return QColor(self.palette.get(key, fallback))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        bg = self._c('black', '#000000')
        deep = self._c('bg', '#0E0E0E')
        accent = self._c('accent', '#EEEEEE')
        white = self._c('white', '#FFFFFF')
        dim = self._c('text_dim', '#9A9A9A')
        faint = self._c('text_faint', '#737373')
        border = self._c('border', '#383838')
        soft = self._c('border_soft', '#4D4D4D')

        p.fillRect(self.rect(), bg)
        t = time.monotonic() - self._t0
        cx = self.width() / 2.0

        #终端窗口框
        frame = QRectF(cx - 170, 46, 340, 88)
        p.setPen(QPen(border, 1))
        p.setBrush(deep)
        p.drawRect(frame)

        #标题栏
        p.setPen(QPen(soft, 1))
        p.drawLine(QPointF(frame.left(), frame.top() + 20), QPointF(frame.right(), frame.top() + 20))
        p.setPen(Qt.NoPen)
        p.setBrush(soft)
        for i in range(3):
            p.drawRect(QRectF(frame.left() + 12 + i * 12, frame.top() + 7, 7, 7))

        #光标
        p.setFont(QFont('Consolas', 14, QFont.Bold))
        p.setPen(QPen(accent))
        p.drawText(QRectF(frame.left() + 14, frame.top() + 30, 24, 24), Qt.AlignVCenter | Qt.AlignLeft, '>')
        if int(t * 2.0) % 2 == 0:
            p.fillRect(QRectF(frame.left() + 36, frame.top() + 33, 12, 18), white)
        p.setPen(QPen(dim))
        p.drawText(QRectF(frame.left() + 58, frame.top() + 30, frame.width() - 72, 24),
                   Qt.AlignVCenter | Qt.AlignLeft, 'PRTS://BOOT')

        #TITLE-
        p.setFont(QFont('Consolas', 34, QFont.Bold))
        p.setPen(QPen(white))
        p.drawText(QRectF(0, frame.bottom() + 22, self.width(), 46), Qt.AlignCenter, 'PRTS')

        #副标题
        p.setFont(QFont('Consolas', 9))
        p.setPen(QPen(accent))
        p.drawText(QRectF(0, frame.bottom() + 74, self.width(), 18), Qt.AlignCenter,
                   'Wellcome // ┌(。Д。)┐')

        #载入
        bar_x = self.width() * 0.22
        bar_w = self.width() * 0.56
        bar_y = self.height() - 74.0
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(bar_x, bar_y, bar_w, 2.0))
        p.setPen(Qt.NoPen)
        p.setBrush(white)
        p.drawRect(QRectF(bar_x, bar_y, bar_w * self.progress / 100.0, 2.0))

        dots = '.' * (1 + int(self.progress / 100.0 * 6))
        p.setFont(QFont('Consolas', 9))
        p.setPen(QPen(faint))
        p.drawText(QRectF(0, bar_y + 12, self.width(), 18), Qt.AlignCenter,
                   'INITIALIZING - {}%  {}'.format(int(self.progress), dots))
        p.end()