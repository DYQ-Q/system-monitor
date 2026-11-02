"""内存信息采集。

这个模块是“取数”的地方：调用 psutil 向 Windows 要内存数据，
然后装进一个 MemorySnapshot 对象里返回。它完全不认识 Qt / 界面，
所以以后要写命令行版本、导出报告，都可以直接复用这里的代码。
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class MemorySnapshot:
    """某一时刻的内存快照（相当于拍了一张照片）。

    字段单位说明：
    - total / used / available 单位都是字节（Byte）
    - percent 是 psutil 直接算好的占用率（0~100，float）
    """

    total: int
    used: int
    available: int
    percent: float

    @property
    def free(self) -> int:
        """“完全空闲”的内存大小。

        说明：Windows 上 available 包含了“可被立刻回收的缓存”，
        而 free 是真正一点没用的内存，所以 free 通常小于 available。
        界面上展示 available 更贴近真实体验。
        """
        return max(self.total - self.used, 0)


def collect_memory() -> MemorySnapshot | None:
    """采集一次内存信息。

    返回 None 表示本次采集失败（极少见），调用方应当显示 “N/A” 而不是崩溃。
    """
    try:
        vm = psutil.virtual_memory()
    except Exception:  # noqa: BLE001 - 采集失败不应让界面崩溃
        return None

    return MemorySnapshot(
        total=int(vm.total),
        used=int(vm.used),
        available=int(vm.available),
        percent=float(vm.percent),
    )
