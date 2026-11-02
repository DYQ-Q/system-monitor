"""悬浮窗用的紧凑控件。

只有两个东西：
- RingGauge：一个自绘的“环形进度表”，中间写百分比
- 圆形进度用 QPainter 手绘，比 QProgressBar 更适合小尺寸悬浮窗

为什么手绘而不是用 QProgressBar？
QProgressBar 是长条形的，塞进 200 像素宽的悬浮窗里几乎看不见。
圆环在小空间里更醒目，而且一眼就能判断“满没满”。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RingGauge(QWidget):
    """环形进度表。

    - value：0~100 的百分比
    - color：当前圆环颜色（由外部按阈值决定）

    尺寸由外部通过 set_diameter() 控制，线宽和字号按直径等比换算，
    这样窗口拉大缩小时圆环不会“错位”或文字溢出。
    """

    def __init__(
        self,
        diameter: int = 74,
        thickness: int = 7,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value: float = 0.0
        self._color = QColor("#3fb950")
        self._track_color = QColor("#2b3138")
        self._text_color = QColor("#e6edf3")
        self._diameter = diameter
        self._thickness = thickness

        self.setFixedSize(diameter, diameter)

    # ---------- 外部接口 ----------

    def set_value(self, value: float) -> None:
        """设置百分比并重绘。"""
        new_value = max(0.0, min(float(value), 100.0))
        if abs(new_value - self._value) > 0.05:
            self._value = new_value
            self.update()

    def set_diameter(self, diameter: int) -> None:
        """改变圆环直径，线宽与字号按比例同步缩放。

        比例基准取默认的 62 像素：直径 62 时线宽 7、字号 12pt。
        """
        diameter = max(28, int(diameter))
        if diameter == self._diameter:
            return

        self._diameter = diameter
        # 线宽至少 3，否则太细看不清；字号至少 7pt，否则糊成一团
        self._thickness = max(3.0, diameter * 7.0 / 62.0)
        self.setFixedSize(diameter, diameter)
        self.update()

    def text_point_size(self) -> float:
        """返回当前直径下应使用的字号（供测试与调试）。"""
        return max(7.0, self._diameter * 12.0 / 62.0)

    def set_colors(self, ring: str, track: str, text: str) -> None:
        """设置圆环 / 底环 / 文字颜色（主题切换时调用）。"""
        self._color = QColor(ring)
        self._track_color = QColor(track)
        self._text_color = QColor(text)
        self.update()

    def set_ring_color(self, ring: str) -> None:
        """只改圆环颜色（告警变色时调用）。"""
        self._color = QColor(ring)
        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 规定命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        margin = self._thickness / 2 + 1
        rect = QRectF(
            margin,
            margin,
            self.width() - 2 * margin,
            self.height() - 2 * margin,
        )

        # 底环：整整一圈的暗色
        track_pen = QPen(self._track_color)
        track_pen.setWidthF(self._thickness)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # 进度环：从 12 点方向开始，顺时针画
        # Qt 的角度单位是 1/16 度，所以乘以 16；顺时针用负角度
        span = -int(360 * 16 * (self._value / 100.0))

        if span != 0:
            value_pen = QPen(self._color)
            value_pen.setWidthF(self._thickness)
            value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(value_pen)
            painter.drawArc(rect, 90 * 16, span)

        # 中间文字：百分比
        # 显式指定字体族，避免取到空字体族导致中文/数字显示成方块
        font = QFont("Microsoft YaHei UI")
        font.setStyleHint(QFont.StyleHint.SansSerif)
        font.setPointSizeF(self.text_point_size())  # 随圆环直径缩放
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(self._text_color))

        text = f"{int(round(self._value))}%"
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

        painter.end()


def angle_for(percent: float) -> float:
    """把百分比换算成角度（0~360），供调试与单元测试使用。"""
    return max(0.0, min(percent, 100.0)) * 3.6
