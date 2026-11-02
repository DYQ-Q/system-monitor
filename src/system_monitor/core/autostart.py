"""开机自启控制。

原理很简单：Windows 有一个“启动文件夹”的注册表位置
    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
往这里写一个“名字 = 启动命令”的字符串，用户下次登录时 Windows 就会自动执行它。

为什么用 HKCU 而不是 HKLM？
- HKCU 只影响“当前用户”，不需要管理员权限
- HKLM 是“所有用户”，写它需要 UAC 提权，杀毒软件也更容易拦

本模块只依赖 Python 标准库 winreg，不需要额外安装任何包。
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

# 注册表里显示的名字（也是删除项时用的键名）
APP_NAME = "SystemMonitor"

# 开机自启的注册表位置
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _project_root() -> Path:
    """找到项目根目录（即包含 pyproject.toml 的目录）。

    开发期用 `uv run` 启动时，可执行文件是 .venv\\Scripts\\python.exe，
    不能直接拿它当自启命令，否则会打开一个空的 Python 交互环境。
    所以我们要拼出“pythonw.exe + 项目路径 + -m system_monitor”这种完整命令。
    """
    # 本文件位于 <root>/src/system_monitor/core/autostart.py
    return Path(__file__).resolve().parents[3]


def startup_command() -> str:
    """返回开机时应该执行的完整命令行字符串。

    两种情况：
    1. 打包成 exe 运行：直接返回 exe 自己的路径
    2. 源码运行：pythonw.exe -m system_monitor（pythonw 不弹黑色控制台窗口）
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 等打包工具会把原始 exe 路径放在 sys.executable
        return f'"{sys.executable}"'

    root = _project_root()

    # 优先用同目录下的 pythonw.exe（无控制台窗口），找不到就退回 python.exe
    exe_dir = Path(sys.executable).parent
    pythonw = exe_dir / "pythonw.exe"
    launcher = pythonw if pythonw.exists() else Path(sys.executable)

    return f'"{launcher}" -m system_monitor --cwd "{root}"'


def is_autostart_enabled() -> bool:
    """查询当前用户是否已开启开机自启。读注册表失败时视为未开启。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_autostart(enabled: bool) -> tuple[bool, str]:
    """开启或关闭开机自启。

    返回 (是否成功, 说明文字)，界面层拿来说明文字直接显示给用户。
    这里不抛异常，因为“写注册表失败”是很常见的情况
    （比如被安全软件拦截、注册表权限受组策略限制），
    应该提示用户，而不是让程序崩溃。
    """
    command = startup_command()

    try:
        # KEY_SET_VALUE 表示我们要写值，CreateKey 保证键存在
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass  # 本来就没开启，删除失败也无所谓
    except OSError as exc:
        return False, f"操作注册表失败：{exc}"

    if enabled:
        return True, f"已开启开机自启，登录后将自动运行：{command}"
    return True, "已关闭开机自启"
