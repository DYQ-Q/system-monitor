"""核心数据层：只负责“取数据 / 改系统设置 / 存配置”，不涉及任何界面代码。"""

from system_monitor.core.autostart import (
    is_autostart_enabled,
    set_autostart,
    startup_command,
)
from system_monitor.core.config import load_config, save_config
from system_monitor.core.memory import MemorySnapshot, collect_memory
from system_monitor.core.utils import format_bytes, format_percent

__all__ = [
    "MemorySnapshot",
    "collect_memory",
    "format_bytes",
    "format_percent",
    "is_autostart_enabled",
    "set_autostart",
    "startup_command",
    "load_config",
    "save_config",
]
