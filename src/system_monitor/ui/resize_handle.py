"""右下角的“拖拽缩放”把手。

无边框窗口没有系统提供的边框，用户没有地方拖动来改变大小。
这里在右下角画一个小三角（Windows 上常见的“可缩放”视觉暗示），
鼠标按住它拖拽就能改变窗口尺寸。

设计要点：
- 只负责“报告鼠标拖了多少”，不直接改窗口大小
  这样调用方（FloatingWindow）可以统一处理最小尺寸、配置保存等逻辑
- 光标改成斜向双箭头（SizeFDiagCursor），和系统行为一致
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

HANDLE_SIZE = 12  # 把手本身的点击区域边长


class ResizeHandle(QWidget):
    """右下角缩放把手。

    信号：
    - resize_started()          开始拖拽
    - resize_dragged(QPoint)    拖拽过程中的累计位移（相对按下点）
    - resize_finished()         松手
    """

    resize_started = Signal()
    resize_dragged = Signal(QPoint)
    resize_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(HANDLE_SIZE, HANDLE_SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("拖动改变窗口大小")
        self._color = "#6e7781"
        self._origin: QPoint | None = None

    def set_color(self, color: str) -> None:
        """设置三角斜纹的颜色（跟随主题）。"""
        self._color = color
        self.update()

    # ---------- 鼠标事件 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.globalPosition().toPoint()
            self.resize_started.emit()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            # 发出“相对按下点的总位移”，调用方自己加到原始尺寸上
            self.resize_dragged.emit(event.globalPosition().toPoint() - self._origin)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None:
            self._origin = None
            self.resize_finished.emit()
            event.accept()

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:  # noqa: N802
        """画三条从右下角发散的短斜线，形成经典的缩放把手外观。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(QColor(self._color))
        pen.setWidthF(1.0)
        painter.setPen(pen)

        size = float(self.width())
        # 三条平行斜线，长度递减，从右下角向外发散
        for length in (size * 0.30, size * 0.55, size * 0.80):
            start = size - length
            painter.drawLine(
                QPointF(start, size - 1),
                QPointF(size - 1, start),
            )

        painter.end()
