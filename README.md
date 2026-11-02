# System Monitor · 内存悬浮窗

Windows 桌面上的一个小挂件：默认 **216×84 像素**、无边框、始终置顶，一眼就能看出内存紧不紧张，提醒你"快爆了，赶紧保存"。窗口大小可以自己拖，**尺寸也会被记住**。

技术栈：**PySide6**（界面）+ **psutil**（采集）+ **uv**（环境管理）。

## 界面

```
┌───────────────────────────────┐
│   ╭───╮                      │
│  ╱ 52% ╲    可用 7.6 GB      │
│  ╲     ╱    正常             │
│   ╰───╯                    ◢ │  ← 右下角小三角：拖它改大小
└───────────────────────────────┘
```

- 圆环中间是 **内存占用率**
- 右侧第一行：**可用内存**
- 右侧第二行：**状态**（正常 / 偏高 / 内存告急）
- 鼠标悬停可看总内存、已用、可用、精确百分比

## 三档颜色

| 状态 | 占用率 | 颜色 | 效果 |
|------|--------|------|------|
| 正常 | < 60% | 绿 `#3fb950` | 无 |
| 偏高 | 60% ~ 阈值 | 橙 `#d29922` | 无 |
| 内存告急 | ≥ 阈值（默认 80%） | 红 `#f85149` | **边框闪烁 + 托盘图标变红** |

## 交互

| 操作 | 效果 |
|------|------|
| 按住左键拖动 | 移动窗口，松手后**自动记住位置** |
| 拖动右下角小三角 ◢ | 改变窗口大小（小窗口内所有内容等比缩放），松手后**记住尺寸** |
| 双击 | 立即刷新一次 |
| 悬停 | 显示完整内存数字 |
| **右键** | 弹出菜单（见下） |
| 左键点托盘图标 | 显示 / 隐藏悬浮窗 |

窗口大小限制在 **132×52 ~ 520×260** 之间，右键菜单里还有四个一键档位：

| 档位 | 尺寸 |
|------|------|
| 小 | 168×66 |
| 中（默认） | 216×84 |
| 大 | 288×112 |
| 特大 | 384×150 |

右键菜单内容：

- 切换浅色 / 深色主题
- 窗口置顶（可关，关掉后会被其他窗口遮挡）
- 告警阈值：70% / 80% / 85% / 90%
- 窗口大小：小 / 中 / 大 / 特大
- 开机自启
- 退出

## 运行

```powershell
# 方式一：uv 入口脚本
uv run system-monitor

# 方式二：模块方式
uv run python -m system_monitor

# 方式三：直接双击
run.bat
```

首次运行前确保依赖已安装：

```powershell
uv sync
```

> ⚠️ 本项目的 `.venv` 必须基于 **python.org 官方 CPython**（由 uv 管理），
> 不能基于 Anaconda 的 Python，否则 PySide6 会报
> `ImportError: DLL load failed ... 找不到指定的程序`。
> 如果遇到该问题：`conda deactivate` → 删除 `.venv` → `uv sync`。

## 开机自启

在右键菜单勾选「开机自启」后，会向注册表写入：

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  SystemMonitor = "…\.venv\Scripts\pythonw.exe" -m system_monitor --cwd "<项目根>"
```

- 使用 `pythonw.exe` 启动，**不会闪黑色控制台窗口**
- 写在 `HKCU`（当前用户），**不需要管理员权限**
- `--cwd` 参数解决开机时工作目录不确定、`sys.path` 找不到包的问题
- 想手动检查或删除：

```powershell
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name SystemMonitor
Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name SystemMonitor
```

- 删除 `.venv` 或移动项目目录后，需要先取消勾选再重新勾选一次

## 配置文件

窗口位置、主题、阈值、是否置顶都存在：

```
%APPDATA%\SystemMonitor\settings.json
```

```json
{
  "pos_x": 1650,
  "pos_y": 24,
  "theme": "dark",
  "warn_threshold": 80,
  "always_on_top": true
}
```

想恢复默认位置，删掉这个文件或把 `pos_x` / `pos_y` 改成 `null` 即可。

> 为什么不放在项目目录？因为项目可能在只读位置，而 `%APPDATA%` 一定可写。

## 目录结构

```
src/system_monitor/
├─ __init__.py        # 入口 main()
├─ __main__.py        # python -m system_monitor
├─ app.py             # 启动流程、--cwd 参数处理、托盘挂载
├─ core/              # 数据层（不 import Qt）
│  ├─ utils.py        # format_bytes / format_percent
│  ├─ memory.py       # MemorySnapshot + collect_memory()
│  ├─ autostart.py    # 开机自启（winreg 读写 HKCU）
│  └─ config.py       # 配置读写（%APPDATA%\SystemMonitor）
└─ ui/                # 界面层（不 import psutil / winreg）
   ├─ gauge.py        # 自绘环形进度表 RingGauge
   ├─ floating_window.py  # 悬浮窗本体
   └─ tray.py         # 托盘图标（动态显示百分比）

tools/
├─ smoke_test.py      # 离屏冒烟测试（不出窗口）
└─ render_preview.py  # 渲染三张预览图，检查视觉效果

docs/ARCHITECTURE.md  # 架构与原理说明（推荐先读）
```

## 测试

```powershell
# 数据层
uv run python -c "from system_monitor.core.memory import collect_memory; print(collect_memory())"

# 界面冒烟测试（不弹窗，可加 QT_QPA_PLATFORM=windows 让文字正常渲染）
uv run python tools/smoke_test.py

# 生成预览图 preview_dark.png / preview_light.png / preview_alert.png
uv run python tools/render_preview.py
```

> 💡 用 `QT_QPA_PLATFORM=offscreen` 跑测试时，Qt 找不到字体目录，中文和数字会渲染成方块，
> 这只是离屏环境的问题，不影响真实窗口。想看正常文字请用 `QT_QPA_PLATFORM=windows`。

详细原理、代码讲解、常见坑见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 规划中

- 进程分析（哪个程序在吃内存）
- C 盘 / 磁盘空间监控
- 内存历史曲线
