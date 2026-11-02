"""桌面悬浮窗：常驻桌面角落，提醒你内存快满了。

设计要点（都是为了“小”和“不打扰”）：
- 无边框（FramelessWindowHint）：没有标题栏，只占一小块
- 置顶（WindowStaysOnTopHint）：不会被别的窗口盖住
- 不占任务栏（Tool）：托盘区才是它的“家”
- 鼠标按住任意位置可拖动；位置自动记忆
- 右键菜单：主题、置顶、阈值、开机自启、退出
- 内存超阈值：圆环变红 + 窗口轻微呼吸闪烁
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from system_monitor.core.autostart import is_autostart_enabled, set_autostart
from system_monitor.core.config import load_config, save_config
from system_monitor.core.memory import MemorySnapshot, collect_memory
from system_monitor.core.utils import format_bytes
from system_monitor.ui.gauge import RingGauge
from system_monitor.ui.resize_handle import ResizeHandle

REFRESH_INTERVAL_MS = 1000  # 每秒刷新

# 窗口尺寸限制。太小时文字放不下，太大就失去“悬浮小挂件”的意义
MIN_WIDTH, MIN_HEIGHT = 132, 52
MAX_WIDTH, MAX_HEIGHT = 520, 260

# 默认尺寸（M 档）：216x84
DEFAULT_WIDTH, DEFAULT_HEIGHT = 216, 84

# 右键菜单里的预设尺寸档位：名称 -> (宽, 高)
SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "小": (168, 66),
    "中": (216, 84),
    "大": (288, 112),
    "特大": (384, 150),
}

# 三档颜色：正常 / 偏高 / 危险
COLOR_OK = "#3fb950"
COLOR_WARN = "#d29922"
COLOR_DANGER = "#f85149"

COLOR_OK_LIGHT = "#1a7f37"
COLOR_WARN_LIGHT = "#9a6700"
COLOR_DANGER_LIGHT = "#cf222e"


def _scale_factor(width: int, height: int) -> float:
    """把窗口尺寸换算成“缩放倍数”，1.0 表示默认的 216x84。

    取宽高比例的平均值，这样非等比拉伸时字号也会跟着适度变化。
    """
    return ((width / DEFAULT_WIDTH) + (height / DEFAULT_HEIGHT)) / 2.0


class FloatingWindow(QWidget):
    """内存悬浮窗。"""

    # 采集到新数据时发出，方便以后接历史记录
    snapshot_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self._config = load_config()
        self._theme: str = str(self._config.get("theme", "dark"))
        self._warn_threshold: int = int(self._config.get("warn_threshold", 80))
        self._drag_offset: QPoint | None = None
        self._is_warn: bool = False
        self._blink_on: bool = False
        self._suppress_save: bool = True
        self._current_percent: float = 0.0

        # 缩放相关状态
        self._resize_origin_size = None   # 按下把手时窗口的原始尺寸 QSize
        self._font_scale: float = 1.0     # 当前字号缩放倍数

        self._setup_window_flags()
        self._build_ui()
        self._apply_theme()

        # 数据定时器
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        # 告警呼吸效果：只有在危险状态时才跑
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(600)
        self._blink_timer.timeout.connect(self._on_blink)

        self._restore_position()
        self.refresh()

    # ---------- 窗口外观 ----------

    def _setup_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint      # 无边框
            | Qt.WindowType.Tool                   # 不占任务栏
        )

        # 按上次保存的配置决定是否置顶
        if bool(self._config.get("always_on_top", True)):
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("内存悬浮窗")

        # 不再 setFixedSize：允许自由缩放，但限制在合理区间内
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.setMaximumSize(MAX_WIDTH, MAX_HEIGHT)

        width = int(self._config.get("width", DEFAULT_WIDTH) or DEFAULT_WIDTH)
        height = int(self._config.get("height", DEFAULT_HEIGHT) or DEFAULT_HEIGHT)
        self.resize(
            max(MIN_WIDTH, min(width, MAX_WIDTH)),
            max(MIN_HEIGHT, min(height, MAX_HEIGHT)),
        )

    def _build_ui(self) -> None:
        # 圆环表盘（中间显示百分比），初始直径按窗口尺寸算出
        self.gauge = RingGauge(diameter=62, thickness=7)

        # 右侧两行文字：可用内存 + 状态
        self.detail_label = QLabel("可用 --")
        self.detail_label.setObjectName("detailText")

        self.state_label = QLabel("内存正常")
        self.state_label.setObjectName("stateText")

        self._text_col = QVBoxLayout()
        self._text_col.setContentsMargins(0, 0, 0, 0)
        self._text_col.setSpacing(3)
        self._text_col.addStretch(1)
        self._text_col.addWidget(self.detail_label)
        self._text_col.addWidget(self.state_label)
        self._text_col.addStretch(1)

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(12, 10, 14, 10)
        self._row.setSpacing(14)
        self._row.addWidget(self.gauge, 0, Qt.AlignmentFlag.AlignVCenter)
        self._row.addLayout(self._text_col, 1)

        # 右下角缩放把手（子控件，浮在布局之上，不参与布局计算）
        self.resize_handle = ResizeHandle(self)
        self.resize_handle.raise_()
        self.resize_handle.resize_started.connect(self._on_resize_started)
        self.resize_handle.resize_dragged.connect(self._on_resize_dragged)
        self.resize_handle.resize_finished.connect(self._on_resize_finished)

        # 初始就按当前窗口尺寸把边距、圆环、字号算一遍
        self._relayout()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """窗口尺寸变化时重算布局，并把把手钉在右下角。"""
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        """按当前窗口尺寸重算边距、圆环直径与字号。

        所有尺寸都从“窗口宽高”推导出来，而不是写死像素值，
        这样窗口无论拉多大，内容都能等比铺开、不会被裁掉。
        """
        width = max(self.width(), MIN_WIDTH)
        height = max(self.height(), MIN_HEIGHT)
        scale = _scale_factor(width, height)
        self._font_scale = scale

        # 边距随尺寸微调：小窗口用更小的边距，给内容腾地方
        side = max(6, int(round(width * 0.055)))
        top = max(5, int(round(height * 0.11)))
        self._row.setContentsMargins(side, top, side + 6, top)
        self._row.setSpacing(max(6, int(round(scale * 14))))
        self._text_col.setSpacing(max(1, int(round(scale * 3))))

        # 圆环直径：高度上留 2px 余量（RingGauge 内部还要给线宽留边），
        # 同时不超过宽度的 42%，避免挤压右侧文字
        gauge_diameter = min(
            height - 2 * top - 2,
            max(24, int(round(width * 0.42))),
        )
        self.gauge.set_diameter(gauge_diameter)

        # 字号跟着缩放倍数走（颜色也在同一个函数里重写，避免 QSS 互相覆盖）
        self._refresh_text_colors()

        # 把手固定在右下角
        handle_size = self.resize_handle.width()
        self.resize_handle.move(
            width - handle_size, height - handle_size
        )
        self.resize_handle.raise_()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """自绘圆角背景。

        为什么不用 QSS 给 QWidget 设背景？
        因为窗口设了 WA_TranslucentBackground（透明），
        QSS 的圆角背景在这种窗口上不可靠；用 QPainter 画最稳。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        colors = self._theme_colors()
        bg = colors["bg"]
        border = colors["border"]

        # 危险时闪一下红色边框
        if self._is_warn and self._blink_on:
            border = COLOR_DANGER

        # 圆角半径随窗口高度变化，小窗口用小圆角才协调
        radius = max(8, min(16, self.height() // 7))

        painter.setBrush(QBrush(QColor(bg)))
        painter.setPen(QPen(QColor(border), 1.2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)
        painter.end()

    # ---------- 刷新数据 ----------

    def refresh(self) -> None:
        """每秒调用一次：取数据 → 更新文字与圆环 → 判断是否需要告警。"""
        snapshot = collect_memory()

        if snapshot is None:
            self._current_percent = 0.0
            self.detail_label.setText("读取失败")
            self.state_label.setText("")
            self.gauge.set_value(0)
            return

        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot: MemorySnapshot) -> None:
        percent = max(0.0, min(snapshot.percent, 100.0))

        self._current_percent = percent
        self.detail_label.setText(f"可用 {format_bytes(snapshot.available)}")
        self.gauge.set_value(percent)

        self._update_alert_state(percent)

        # 备注：把详细信息挂到 tooltip 上，鼠标悬停就能看到完整数字
        self.setToolTip(
            f"总内存 {format_bytes(snapshot.total)}\n"
            f"已用 {format_bytes(snapshot.used)}\n"
            f"可用 {format_bytes(snapshot.available)}\n"
            f"占用率 {percent:.1f}%"
        )

        self.snapshot_changed.emit(snapshot)

    def _update_alert_state(self, percent: float) -> None:
        """根据占用率切换颜色，并开启/关闭呼吸闪烁。"""
        danger_color = COLOR_DANGER if self._theme == "dark" else COLOR_DANGER_LIGHT

        if percent >= self._warn_threshold:
            self.state_label.setText("内存告急")
            self.gauge.set_ring_color(danger_color)
            new_warn = True
        elif percent >= 60:
            self.state_label.setText("偏高")
            self.gauge.set_ring_color(
                COLOR_WARN if self._theme == "dark" else COLOR_WARN_LIGHT
            )
            new_warn = False
        else:
            self.state_label.setText("正常")
            self.gauge.set_ring_color(
                COLOR_OK if self._theme == "dark" else COLOR_OK_LIGHT
            )
            new_warn = False

        if new_warn != self._is_warn:
            self._is_warn = new_warn
            if new_warn:
                self._blink_timer.start()   # 进入危险：开始闪烁
            else:
                self._blink_timer.stop()    # 恢复安全：停止闪烁
                self._blink_on = False
                self.update()

    def _on_blink(self) -> None:
        """闪烁定时器：交替切换边框亮/暗，形成“呼吸”效果。"""
        self._blink_on = not self._blink_on
        self.update()

    # ---------- 主题 ----------

    def _theme_colors(self) -> dict[str, str]:
        """返回当前主题下用到的所有颜色。"""
        if self._theme == "dark":
            return {
                "text_main": "#e6edf3",
                "text_sub": "#8b949e",
                "text_state": "#8b949e",
                "track": "#2b3138",
                "bg": "#22272e",
                "border": "#3d444d",
                "handle": "#6e7781",
            }
        return {
            "text_main": "#1f2328",
            "text_sub": "#6e7781",
            "text_state": "#6e7781",
            "track": "#eaeef2",
            "bg": "#ffffff",
            "border": "#d0d7de",
            "handle": "#8c959f",
        }

    def _refresh_text_colors(self) -> None:
        """只刷新两行文字的颜色，保留当前字号。

        为什么单独拆出来？
        QSS 的 setStyleSheet 是整体覆盖的：如果 _relayout 只写 font-size、
        apply_theme 只写 color，后者会把前者抹掉。所以颜色和字号必须拼在
        同一段样式里一起写，两边都调这个函数。
        """
        colors = self._theme_colors()
        scale = self._font_scale
        detail_px = max(8, int(round(13 * scale)))
        state_px = max(7, int(round(11 * scale)))
        family = "Microsoft YaHei UI"

        self.detail_label.setStyleSheet(
            f"color: {colors['text_sub']}; font-family: '{family}'; "
            f"font-size: {detail_px}px;"
        )
        self.state_label.setStyleSheet(
            f"color: {colors['text_state']}; font-family: '{family}'; "
            f"font-size: {state_px}px; letter-spacing: 1px;"
        )

    def apply_theme(self, theme: str) -> None:
        """切换主题并立即生效。"""
        self._theme = theme
        colors = self._theme_colors()

        self._refresh_text_colors()
        self.gauge.set_colors(
            ring=self._current_ring_color(),
            track=colors["track"],
            text=colors["text_main"],
        )
        self.resize_handle.set_color(colors["handle"])

        # 构造期应用默认主题时不必写文件，避免每次启动都碰磁盘
        if not self._suppress_save:
            save_config({"theme": theme})

        self.update()

    def _current_ring_color(self) -> str:
        """按当前占用率与主题，返回应有的圆环颜色。

        注意：必须按百分比重新判断，不能只看 self._is_warn，
        否则“偏高”（橙色）状态切主题后会被错误地画成绿色。
        """
        dark = self._theme == "dark"
        percent = self._current_percent

        if percent >= self._warn_threshold:
            return COLOR_DANGER if dark else COLOR_DANGER_LIGHT
        if percent >= 60:
            return COLOR_WARN if dark else COLOR_WARN_LIGHT
        return COLOR_OK if dark else COLOR_OK_LIGHT

    def _apply_theme(self) -> None:
        """构造期调用：应用配置里的主题（不重复写配置文件）。"""
        theme = self._theme
        self._suppress_save = True
        self.apply_theme(theme)
        self._suppress_save = False

    def toggle_theme(self) -> None:
        """供菜单调用：在深色与浅色之间切换。"""
        self.apply_theme("light" if self._theme == "dark" else "dark")

    # ---------- 拖动与位置记忆 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """按下左键：记录鼠标相对窗口左上角的偏移，供拖动使用。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """按住左键移动：让窗口跟着鼠标走。"""
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """松开左键：结束拖动并把新位置写进配置。"""
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            save_config({"pos_x": self.x(), "pos_y": self.y()})
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击立即刷新一次（不必等下一秒）。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.refresh()
            event.accept()

    # ---------- 拖拽缩放 ----------

    def _on_resize_started(self) -> None:
        """按下把手：记住窗口当前尺寸，作为后续累加的基准。"""
        self._resize_origin_size = self.size()

    def _on_resize_dragged(self, delta: QPoint) -> None:
        """拖动把手：在基准尺寸上加上位移，并夹在最小 / 最大尺寸之间。"""
        if self._resize_origin_size is None:
            return

        new_width = max(
            MIN_WIDTH,
            min(self._resize_origin_size.width() + delta.x(), MAX_WIDTH),
        )
        new_height = max(
            MIN_HEIGHT,
            min(self._resize_origin_size.height() + delta.y(), MAX_HEIGHT),
        )
        self.resize(new_width, new_height)

    def _on_resize_finished(self) -> None:
        """松开把手：清空基准并保存尺寸。"""
        self._resize_origin_size = None
        save_config({"width": self.width(), "height": self.height()})

    def set_window_size(self, width: int, height: int) -> None:
        """按像素设置窗口尺寸（供右键菜单的档位调用）。"""
        self.resize(
            max(MIN_WIDTH, min(width, MAX_WIDTH)),
            max(MIN_HEIGHT, min(height, MAX_HEIGHT)),
        )
        save_config({"width": self.width(), "height": self.height()})

    def _restore_position(self) -> None:
        """恢复上次的位置；没有记录或位置已不在屏幕内则放到右上角。"""
        pos_x = self._config.get("pos_x")
        pos_y = self._config.get("pos_y")

        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None

        if pos_x is not None and pos_y is not None and area is not None:
            candidate = QPoint(int(pos_x), int(pos_y))
            # 校验：窗口必须至少有一部分在可见区域内（换显示器后常见问题）
            visible = area.adjusted(-self.width() + 40, -self.height() + 40, 0, 0)
            if visible.contains(candidate):
                self.move(candidate)
                return

        if area is not None:
            # 默认放右上角，留 24 像素边距
            self.move(area.right() - self.width() - 24, area.top() + 24)
        else:
            self.move(100, 100)

    # ---------- 右键菜单 ----------

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键弹出菜单：主题、置顶、告警阈值、开机自启、退出。"""
        menu = QMenu(self)

        theme_action = QAction(
            "切换浅色主题" if self._theme == "dark" else "切换深色主题", self
        )
        theme_action.triggered.connect(self.toggle_theme)
        menu.addAction(theme_action)

        top_action = QAction("窗口置顶", self)
        top_action.setCheckable(True)
        top_action.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        top_action.toggled.connect(self._on_topmost_toggled)
        menu.addAction(top_action)

        # 告警阈值子菜单
        threshold_menu = menu.addMenu("告警阈值")
        for value in (70, 80, 85, 90):
            act = QAction(f"{value}%", self)
            act.setCheckable(True)
            act.setChecked(self._warn_threshold == value)
            act.triggered.connect(lambda _checked=False, v=value: self._set_threshold(v))
            threshold_menu.addAction(act)

        # 尺寸子菜单：一键切换预设档位
        size_menu = menu.addMenu("窗口大小")
        current = (self.width(), self.height())
        for name, (w, h) in SIZE_PRESETS.items():
            act = QAction(f"{name}（{w}×{h}）", self)
            act.setCheckable(True)
            act.setChecked(current == (w, h))
            act.triggered.connect(
                lambda _checked=False, ww=w, hh=h: self.set_window_size(ww, hh)
            )
            size_menu.addAction(act)

        menu.addSeparator()

        auto_action = QAction("开机自启", self)
        auto_action.setCheckable(True)
        auto_action.setChecked(is_autostart_enabled())
        auto_action.toggled.connect(self._on_autostart_toggled)
        menu.addAction(auto_action)

        menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())

    def _on_topmost_toggled(self, checked: bool) -> None:
        """切换置顶：修改窗口标志后必须重新 show()，否则窗口会消失。"""
        pos = self.pos()

        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.show()
        self.move(pos)  # 改标志会把窗口重置到别处，这里挪回来

        save_config({"always_on_top": checked})

    def _set_threshold(self, value: int) -> None:
        """设置告警阈值并立刻按新阈值重新判断一次。"""
        self._warn_threshold = value
        save_config({"warn_threshold": value})

        snapshot = collect_memory()
        if snapshot is not None:
            self._update_alert_state(snapshot.percent)

    def _on_autostart_toggled(self, checked: bool) -> None:
        """开关开机自启，失败就把菜单项状态改回去并提示。"""
        ok, message = set_autostart(checked)

        if not ok:
            # 没有界面提示框，用 tooltip 文本 + 控制台输出兜底
            self.setToolTip(message)
            print(f"[System Monitor] {message}", flush=True)

    # ---------- 生命周期 ----------

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭前停掉所有定时器并记住位置。"""
        self._timer.stop()
        self._blink_timer.stop()
        save_config({"pos_x": self.x(), "pos_y": self.y()})
        super().closeEvent(event)

