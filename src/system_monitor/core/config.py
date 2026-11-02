"""本地配置读写（记住窗口位置、主题、告警阈值）。

用标准库 json 存到 `%APPDATA%\\SystemMonitor\\settings.json`。
为什么不放在项目目录？因为项目可能在只读位置，而 APPDATA 一定可写，
这也是 Windows 上应用程序存用户配置的惯用位置。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_APP_DIR_NAME = "SystemMonitor"
_FILE_NAME = "settings.json"

# 默认配置。新增配置项时在这里加默认值，老配置文件也能自动兼容。
DEFAULTS: dict[str, Any] = {
    "pos_x": None,          # 窗口左上角 X（None 表示用默认位置）
    "pos_y": None,          # 窗口左上角 Y
    "width": 216,           # 窗口宽度（像素，未乘缩放系数）
    "height": 84,           # 窗口高度
    "theme": "dark",        # dark / light
    "warn_threshold": 80,   # 超过这个百分比算“危险”
    "always_on_top": True,  # 是否窗口置顶
}


def config_path() -> Path:
    """返回配置文件的完整路径（不保证文件已存在）。"""
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    return root / _APP_DIR_NAME / _FILE_NAME


def load_config() -> dict[str, Any]:
    """读取配置；文件不存在或内容损坏时返回默认值。

    注意返回的是“默认值 + 文件里的值”的合并结果，
    这样以后新增配置项时，旧配置文件不会导致 KeyError。
    """
    data = dict(DEFAULTS)
    path = config_path()

    try:
        with path.open("r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return data

    if isinstance(saved, dict):
        # 只接受已知的键，避免配置文件被乱改后带进奇怪字段
        for key in DEFAULTS:
            if key in saved:
                data[key] = saved[key]

    return data


def save_config(updates: dict[str, Any]) -> bool:
    """把若干配置项写回文件（与已有内容合并）。返回是否成功。

    写文件失败（比如磁盘满、权限问题）不应让程序崩溃，
    所以这里吞掉异常并返回 False，让调用方决定提示与否。
    """
    data = load_config()
    data.update({k: v for k, v in updates.items() if k in DEFAULTS})

    path = config_path()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        return False

    return True
