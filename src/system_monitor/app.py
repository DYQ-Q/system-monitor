"""应用启动流程：创建 QApplication → 显示悬浮窗 → 创建托盘图标 → 进入事件循环。

为什么单独放一个 app.py？
- __init__.py 只暴露 main()，保持入口简短
- 以后要加命令行参数、单实例检查、日志初始化，都在这里改，不影响包导入
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from system_monitor.ui.floating_window import FloatingWindow
from system_monitor.ui.tray import TrayIcon


def _prepare_import_path(argv: list[str]) -> list[str]:
    """解析 --cwd 参数：开机自启时把工作目录切到项目根，保证能找到 system_monitor 包。

    返回去掉 --cwd 之后的参数列表，交给 QApplication 使用。
    （Qt 会自己解析剩下的 Qt 专用参数，我们不干预。）
    """
    remaining: list[str] = []
    index = 0

    while index < len(argv):
        arg = argv[index]

        if arg == "--cwd" and index + 1 < len(argv):
            target = argv[index + 1]
            if Path(target).is_dir():
                os.chdir(target)
                # 把 src 目录加入模块搜索路径，这样 -m system_monitor 能找到包
                src_dir = str(Path(target) / "src")
                if src_dir not in sys.path:
                    sys.path.insert(0, src_dir)
            index += 2
            continue

        remaining.append(arg)
        index += 1

    return remaining


def run() -> int:
    """启动图形界面，返回进程退出码。"""
    argv = _prepare_import_path(sys.argv)

    # 高 DPI 缩放：让界面在 125% / 150% 缩放的屏幕上不发虚
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv)
    app.setApplicationName("System Monitor")
    app.setApplicationDisplayName("System Monitor · 内存悬浮窗")
    app.setStyle("Fusion")  # Fusion 风格在不同 Windows 版本上表现一致

    # 关键：关掉“最后一个窗口关闭就退出程序”的默认行为。
    # 因为我们允许把悬浮窗隐藏到托盘，此时程序应该继续运行。
    app.setQuitOnLastWindowClosed(False)

    window = FloatingWindow()
    window.show()

    tray = TrayIcon(window)
    tray.show()

    # 把 tray 挂到 window 上，避免被垃圾回收（否则托盘图标会凭空消失）
    window._tray = tray

    return app.exec()

