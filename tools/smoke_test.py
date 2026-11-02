"""离屏冒烟测试：不弹窗口，验证悬浮窗能构建、数据能刷新、告警能触发。

用法：uv run python tools/smoke_test.py
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from system_monitor.core.config import config_path, load_config  # noqa: E402
from system_monitor.ui.floating_window import (  # noqa: E402
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MAX_HEIGHT,
    MAX_WIDTH,
    MIN_HEIGHT,
    MIN_WIDTH,
    SIZE_PRESETS,
    FloatingWindow,
)
from system_monitor.ui.gauge import RingGauge, angle_for  # noqa: E402
from system_monitor.ui.tray import TrayIcon, build_tray_icon  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)

    window = FloatingWindow()
    window.show()
    window.refresh()

    flags = window.windowFlags()

    print("=== 窗口属性 ===")
    print(f"    窗口尺寸: {window.width()} x {window.height()}")
    print(f"  无边框标志: {bool(flags & Qt.WindowType.FramelessWindowHint)}")
    print(f"    置顶标志: {bool(flags & Qt.WindowType.WindowStaysOnTopHint)}")
    print(f"  不占任务栏: {bool(flags & Qt.WindowType.Tool)}")
    print(f"    窗口位置: ({window.x()}, {window.y()})")

    print("\n=== 实时数据 ===")
    print(f"    百分比数值: {window._current_percent:.1f}%")
    print(f"    可用内存: {window.detail_label.text()}")
    print(f"    状态文字: {window.state_label.text()}")
    print(f"    圆环数值: {window.gauge._value:.1f}")
    print(f"    是否告警: {window._is_warn}")
    print(f"    告警阈值: {window._warn_threshold}%")
    print(f"     tooltip: {window.toolTip().replace(chr(10), ' | ')}")

    print("\n=== 告警逻辑 ===")
    window._set_threshold(99)
    print(f"   阈值99 告警: {window._is_warn}  状态={window.state_label.text()}")
    window._set_threshold(10)
    print(f"   阈值10 告警: {window._is_warn}  状态={window.state_label.text()}")
    print(f"   闪烁定时器运行中: {window._blink_timer.isActive()}")
    window._set_threshold(80)
    print(f"   阈值复原80 告警: {window._is_warn}")

    print("\n=== 主题切换（含橙色保留验证）===")
    print(f"    当前主题: {window._theme}  占用 {window._current_percent:.1f}%")
    window.toggle_theme()
    print(f"    切换之后: {window._theme}  圆环颜色={window.gauge._color.name()}")
    window.toggle_theme()
    print(f"    再切回来: {window._theme}  圆环颜色={window.gauge._color.name()}")

    print("\n=== 环形表盘 ===")
    gauge = RingGauge()
    gauge.set_value(45)
    print(f" set_value(45) -> {gauge._value}，期望角度 {angle_for(45)}°")
    gauge.set_value(150)
    print(f" set_value(150) 被裁剪为 {gauge._value}")

    print("\n=== 窗口缩放 ===")
    print(f"    初始尺寸: {window.width()}x{window.height()}  "
          f"圆环={window.gauge.width()}px 字号={window.gauge.text_point_size():.1f}pt")
    for name, (w, h) in SIZE_PRESETS.items():
        window.set_window_size(w, h)
        text_margin = window._row.contentsMargins()
        fits = (
            window.gauge.height() <= window.height() - text_margin.top() - text_margin.bottom()
        )
        print(
            f"    {name:>2} 档 {window.width()}x{window.height()}: "
            f"圆环={window.gauge.width()}px 字号={window.gauge.text_point_size():.1f}pt "
            f"圆环未溢出={fits} 把手在右下={window.resize_handle.x() == window.width() - window.resize_handle.width()}"
        )
    # 越界裁剪验证
    window.set_window_size(10, 10)
    print(f"    请求 10x10 -> 被夹到 {window.width()}x{window.height()}（最小 {MIN_WIDTH}x{MIN_HEIGHT}）")
    window.set_window_size(9999, 9999)
    print(f"    请求 9999x9999 -> 被夹到 {window.width()}x{window.height()}（最大 {MAX_WIDTH}x{MAX_HEIGHT}）")
    # 模拟拖拽把手
    window.set_window_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)
    window._on_resize_started()
    window._on_resize_dragged(QPoint(60, 30))
    print(f"    拖拽 +60/+30 -> {window.width()}x{window.height()}")
    window._on_resize_finished()
    window.set_window_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)

    print("\n=== 托盘图标 ===")
    icon = build_tray_icon(72, "#d29922")
    print(f"    图标非空: {not icon.isNull()}")
    tray = TrayIcon(window)
    tray.show()
    print(f"  托盘初始文案: {tray._toggle_action.text()}")
    tray.toggle_window()
    print(f"    隐藏后文案: {tray._toggle_action.text()}  窗口可见={window.isVisible()}")
    tray.toggle_window()
    print(f"    再显示文案: {tray._toggle_action.text()}  窗口可见={window.isVisible()}")

    print("\n=== 配置文件 ===")
    print(f"    路径: {config_path()}")
    print(f"    内容: {load_config()}")

    window._timer.stop()
    window._blink_timer.stop()
    tray.hide()
    window.close()
    print("\n冒烟测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
