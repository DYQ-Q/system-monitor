"""渲染悬浮窗截图，便于检查视觉效果（不弹真实窗口）。

用法：uv run python tools/render_preview.py
输出：preview_dark.png / preview_light.png / preview_alert.png
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from system_monitor.core.memory import MemorySnapshot
from system_monitor.ui.floating_window import FloatingWindow


def render(window: FloatingWindow, filename: str) -> None:
    """把窗口画到图片里，放大 3 倍便于看清细节。"""
    window.repaint()
    pixmap = window.grab()
    scaled = pixmap.scaled(
        pixmap.width() * 3,
        pixmap.height() * 3,
    )
    scaled.save(filename)
    print(f"已生成 {filename}  ({pixmap.width()}x{pixmap.height()} → 放大 3 倍)")


def main() -> int:
    app = QApplication(sys.argv)

    window = FloatingWindow()

    # 场景一：深色 + 正常（52%）
    window.apply_theme("dark")
    window._apply_snapshot(
        MemorySnapshot(
            total=17008422912,
            used=8844376880,
            available=8164046032,
            percent=52.0,
        )
    )
    window._blink_on = False
    render(window, "preview_dark.png")

    # 场景二：浅色 + 偏高（72%）
    window.apply_theme("light")
    window._apply_snapshot(
        MemorySnapshot(
            total=17008422912,
            used=12246064496,
            available=4762358416,
            percent=72.0,
        )
    )
    render(window, "preview_light.png")

    # 场景三：深色 + 告急（91%），闪烁亮帧
    window.apply_theme("dark")
    window._apply_snapshot(
        MemorySnapshot(
            total=17008422912,
            used=15477664850,
            available=1530758062,
            percent=91.0,
        )
    )
    window._blink_on = True
    render(window, "preview_alert.png")

    window._timer.stop()
    window._blink_timer.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
