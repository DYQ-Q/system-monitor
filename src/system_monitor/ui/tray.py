"""系统托盘图标。

悬浮窗虽然小，但有时也想让它彻底消失（比如全屏看电影）。
托盘图标提供“显示/隐藏”和“退出”两个操作，程序不会因为窗口被隐藏而退出。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from system_monitor.ui.floating_window import (
    COLOR_DANGER,
    COLOR_OK,
    COLOR_WARN,
    FloatingWindow,
)


def build_tray_icon(percent: float, color: str) -> QIcon:
    """动态生成托盘图标：一个小圆环 + 中间百分比数字。

    每次刷新都重画一个 32x32 的小图，这样托盘区也能看到实时占用率。
    """
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    rect = QRectF(3, 3, size - 6, size - 6)

    track_pen = QPen(QColor("#4a5058"))
    track_pen.setWidthF(3)
    painter.setPen(track_pen)
    painter.drawEllipse(rect)

    value_pen = QPen(QColor(color))
    value_pen.setWidthF(3)
    value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(value_pen)
    painter.drawArc(rect, 90 * 16, -int(360 * 16 * max(0.0, min(percent, 100.0)) / 100))

    if percent >= 1:
        font = QFont("Segoe UI", 7)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(color)))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), f"{percent:.0f}")

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """托盘图标，绑定到悬浮窗。"""

    def __init__(self, window: FloatingWindow) -> None:
        super().__init__()
        self._window = window

        self.setToolTip("System Monitor · 内存监控")
        self.setIcon(build_tray_icon(0, "#3fb950"))

        self._menu = QMenu()
        self._toggle_action = QAction("隐藏悬浮窗", self)
        self._toggle_action.triggered.connect(self.toggle_window)
        self._menu.addAction(self._toggle_action)

        self._menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit)
        self._menu.addAction(quit_action)

        self.setContextMenu(self._menu)

        # 左键单击托盘图标：显示 / 隐藏悬浮窗
        self.activated.connect(self._on_activated)

        # 悬浮窗每秒采集到新数据时，同步更新托盘图标
        window.snapshot_changed.connect(self._on_snapshot)

    def _on_snapshot(self, snapshot) -> None:
        threshold = getattr(self._window, "_warn_threshold", 80)

        if snapshot.percent >= threshold:
            color = COLOR_DANGER
        elif snapshot.percent >= 60:
            color = COLOR_WARN
        else:
            color = COLOR_OK

        self.setIcon(build_tray_icon(snapshot.percent, color))

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window()

    def toggle_window(self) -> None:
        """显示 ↔ 隐藏 悬浮窗。"""
        if self._window.isVisible():
            self._window.hide()
            self._toggle_action.setText("显示悬浮窗")
        else:
            self._window.show()
            self._toggle_action.setText("隐藏悬浮窗")

    def _quit(self) -> None:
        """真正退出程序：先关窗口（触发保存位置），再退出应用。"""
        self._window.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()
