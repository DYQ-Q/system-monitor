"""通用小工具函数（纯计算，不依赖 psutil / Qt）。"""

from __future__ import annotations


def format_bytes(value: float, precision: int = 1) -> str:
    """把字节数转换成人类可读的字符串。

    例如：16106127360 -> "15.0 GB"

    psutil 返回的容量单位都是字节（Byte），直接显示会是一大串数字，
    这个函数把它换成 GB / MB 这种更容易看懂的单位。
    """
    if value is None or value < 0:
        return "N/A"

    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(value)
    index = 0

    # 每次除以 1024，直到数值小于 1024 或到达最大单位
    while size >= 1024 and index < len(units) - 1:
        size /= 1024.0
        index += 1

    # 字节单位不需要小数位
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.{precision}f} {units[index]}"


def format_percent(value: float, precision: int = 1) -> str:
    """把百分比数值格式化成字符串，例如 42.3 -> "42.3%"。"""
    if value is None:
        return "N/A"
    return f"{value:.{precision}f}%"
