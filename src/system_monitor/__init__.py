"""System Monitor · Windows 系统检测工具。

对外只暴露一个 main() 函数，pyproject.toml 里的
    system-monitor = "system_monitor:main"
就是指向它，所以 `uv run system-monitor` 可以启动程序。
"""

from __future__ import annotations


def main() -> None:
    """程序入口：启动图形界面。"""
    from system_monitor.app import run

    raise SystemExit(run())


__all__ = ["main"]

