# 架构与原理说明

这份文档解释代码**为什么这么写**，适合边看代码边读。

---

## 一、整体分层

```
┌────────────────────────────────────────────┐
│  app.py     启动：QApplication → 窗口 → 托盘  │
└───────────────┬────────────────────────────┘
                │
     ┌──────────┴──────────┐
     ▼                     ▼
┌─────────────┐      ┌──────────────┐
│   ui/       │      │   core/      │
│ 只画界面     │─────▶│ 只提供数据    │
│ 不碰系统 API │      │ 不 import Qt │
└─────────────┘      └──────────────┘
```

**两条铁律**：

1. `core/` 里**不出现** `from PySide6...`
2. `ui/` 里**不出现** `import psutil` / `import winreg`

好处：想换界面框架（比如改成 Web）只改 `ui/`；想在命令行输出数据，直接调 `core/` 即可，不用启动 Qt。

---

## 二、文件职责

| 文件 | 职责 | 关键函数 |
|------|------|----------|
| `core/utils.py` | 字节数格式化成 `7.6 GB` | `format_bytes` |
| `core/memory.py` | 采集内存，返回 `MemorySnapshot` 数据类 | `collect_memory()` |
| `core/autostart.py` | 读写注册表实现开机自启 | `set_autostart()` / `is_autostart_enabled()` |
| `core/config.py` | 读写 `%APPDATA%\SystemMonitor\settings.json` | `load_config()` / `save_config()` |
| `ui/gauge.py` | 自绘环形进度表 | `RingGauge.set_value()` / `set_diameter()` |
| `ui/resize_handle.py` | 右下角拖拽缩放把手 | `ResizeHandle.resize_dragged` |
| `ui/floating_window.py` | 悬浮窗：布局、拖动、缩放、菜单、告警 | `FloatingWindow` |
| `ui/tray.py` | 托盘图标，动态画出百分比 | `build_tray_icon()` |
| `app.py` | 组装上面所有东西 | `run()` |

---

## 三、为什么是"悬浮窗"而不是"主窗口"

普通窗口（`QMainWindow`）有三个不适合"提醒"的属性：

1. **占地方** —— 一开就挡住半个屏幕
2. **会被遮挡** —— 切到浏览器就看不见了
3. **有标题栏和任务栏按钮** —— 视觉噪音大

悬浮窗通过三个窗口标志解决：

```python
flags = (
    Qt.WindowType.FramelessWindowHint      # 去掉标题栏和边框
    | Qt.WindowType.Tool                   # 不在任务栏显示按钮
    | Qt.WindowType.WindowStaysOnTopHint   # 永远在最上层
)
self.setWindowFlags(flags)
```

### 三个必须知道的副作用

**① 无边框 = 不能拖动**
原生标题栏的拖动功能没了，必须自己实现：

```python
def mousePressEvent(self, event):
    # 记住"鼠标点在哪"相对于"窗口左上角"的偏移
    self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

def mouseMoveEvent(self, event):
    # 移动时保持这个偏移不变，窗口就跟着鼠标走了
    if self._drag_offset is not None:
        self.move(event.globalPosition().toPoint() - self._drag_offset)
```

关键点：用 `globalPosition()`（屏幕坐标）而不是 `position()`（窗口内坐标），否则窗口一动坐标就乱了。

**② `Tool` 窗口 = 没有关闭按钮**
必须提供退出途径。这里给了两条：右键菜单「退出」+ 托盘右键「退出」。

**③ `WA_TranslucentBackground` = QSS 背景不可靠**
设了透明背景后，用 QSS 给 QWidget 设 `background-color` + `border-radius` 经常失效（表现为方块黑底）。
所以背景改用 `QPainter` 手绘：

```python
def paintEvent(self, event):
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QBrush(QColor(bg)))
    painter.setPen(QPen(QColor(border), 1.2))
    painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
```

`adjusted(1, 1, -1, -1)` 很关键：往里缩 1 像素，否则边框只画出一半（因为线宽 1.2 会被裁掉一半）。

---

## 四、环形进度表怎么画

`RingGauge` 完全手绘，不用 `QProgressBar`（长条形塞不进小悬浮窗）。

```python
# 底环：完整的 360 度暗色圆
painter.drawArc(rect, 0, 360 * 16)

# 进度环：从 12 点开始顺时针
span = -int(360 * 16 * (value / 100))
painter.drawArc(rect, 90 * 16, span)
```

### 角度单位是坑

Qt 的 `drawArc` 有两个反直觉的地方：

1. **单位是 1/16 度**，所以 360 度要写 `360 * 16`
2. **正角度是逆时针**，想顺时针画必须用**负数**

起点 `90 * 16` 表示从 3 点钟方向逆时针转 90 度，即 12 点钟方向。

### 线宽要留边距

圆环画在 `rect` 的边界上时，一半线宽会被裁掉。所以：

```python
margin = self._thickness / 2 + 1
rect = QRectF(margin, margin, width - 2*margin, height - 2*margin)
```

---

## 五、告警与闪烁

### 三档颜色

```python
if percent >= self._warn_threshold:   # 红
elif percent >= 60:                   # 橙
else:                                 # 绿
```

注意：`_current_ring_color()` 里必须**重新按百分比判断**，不能只判断 `self._is_warn`。
否则处于"偏高"（橙色）时切换主题，圆环会被错误地画成绿色（因为 `_is_warn` 是 False）。

### 呼吸闪烁

只在危险状态才启动定时器，避免常态下白白耗电：

```python
if new_warn != self._is_warn:
    self._is_warn = new_warn
    if new_warn:
        self._blink_timer.start()   # 600ms 交替一次
    else:
        self._blink_timer.stop()
        self._blink_on = False
        self.update()

def _on_blink(self):
    self._blink_on = not self._blink_on
    self.update()   # 触发重绘，paintEvent 里据此把边框画成红色
```

---

## 六、窗口缩放

无边框窗口还有个副作用：**没有系统边框可以用来拉伸**。所以右下角放了一个 `ResizeHandle`。

### 把手只报告位移，不动窗口

```python
# resize_handle.py
def mousePressEvent(self, event):
    self._origin = event.globalPosition().toPoint()   # 记住按下点

def mouseMoveEvent(self, event):
    # 发出“相对按下点的累计位移”，调用方自己加到原始尺寸上
    self.resize_dragged.emit(event.globalPosition().toPoint() - self._origin)
```

调用方这样处理，好处是位移始终相对**按下瞬间的尺寸**，不会因为"边改边算"而漂移：

```python
def _on_resize_started(self):
    self._resize_origin_size = self.size()      # 基准

def _on_resize_dragged(self, delta):
    w = clamp(self._resize_origin_size.width() + delta.x(), MIN_WIDTH, MAX_WIDTH)
    h = clamp(self._resize_origin_size.height() + delta.y(), MIN_HEIGHT, MAX_HEIGHT)
    self.resize(w, h)
```

### 为什么布局全部用"比例"算

窗口能被随意拉伸，就不能再写死 `setContentsMargins(12, 10, 14, 10)` 这种像素值，
否则拉大后内容挤在左上角、拉小后文字被裁。`_relayout()` 里所有尺寸都从窗口宽高推导：

```python
scale = ((width / 216) + (height / 84)) / 2      # 1.0 = 默认尺寸

side = max(6, int(width * 0.055))                 # 边距按宽度百分比
gauge_diameter = min(height - 2*top - 2,          # 圆环不超可用高度
                     int(width * 0.42))           # 也不挤占右侧文字
detail_px = max(8, int(13 * scale))               # 字号随 scale
```

`RingGauge.set_diameter()` 内部再按直径等比换算线宽和字体，所以圆环永远不会"溢出"或被裁边。

### QSS 的一个坑：颜色与字号会互相覆盖

`setStyleSheet()` 是**整体替换**，不是增量合并。如果 `_relayout()` 只写 `font-size`、
`apply_theme()` 只写 `color`，后调用的那个会把先前的抹掉（现象：改完大小后文字变色 / 切完主题后字号变回默认）。

所以两处都统一调 `_refresh_text_colors()`，在里面一次写完 `color + font-family + font-size`。

### 尺寸也要记忆

`closeEvent` 和缩放结束时都会 `save_config({"width": ..., "height": ...})`，
下次启动按配置 `resize()`，并夹在最小 / 最大范围内（防止手改配置文件写出离谱的数值）。

---

## 七、位置记忆

### 保存时机

- 拖动松手（`mouseReleaseEvent`）
- 关闭窗口（`closeEvent`）

### 恢复与校验

```python
visible = area.adjusted(-self.width() + 40, -self.height() + 40, 0, 0)
if visible.contains(candidate):
    self.move(candidate)
```

为什么要校验？**换显示器**是最常见的坑：笔记本外接 4K 屏时把窗口拖到副屏（x=2000），
拔掉外屏后主屏只有 1920 宽，窗口就跑到了屏幕外，用户再也找不到它。

校验规则：窗口左上角必须落在"可用区域向外扩展 (宽-40, 高-40)"的范围内，
即至少留 40 像素露在屏幕上。

### 默认位置

右上角，留 24 像素边距：

```python
area = QGuiApplication.primaryScreen().availableGeometry()
self.move(area.right() - self.width() - 24, area.top() + 24)
```

用 `availableGeometry()` 而不是 `geometry()`，因为前者会避开任务栏。

---

## 八、托盘图标

### 动态绘制

每次刷新都重画一张 32×32 的小图，这样托盘区也能看到实时百分比：

```python
def build_tray_icon(percent, color):
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    # ...画圆环 + 中间数字
    painter.end()
    return QIcon(pixmap)
```

### 两个容易踩的坑

**① 托盘对象不能是局部变量**

```python
tray = TrayIcon(window)   # 如果是局部变量，函数返回后 Python 会回收它
tray.show()               # 图标就"凭空消失"了
```

Python 的垃圾回收会连底层 C++ 对象一起删掉。解决办法是把它挂在一个长期存活的对象上：

```python
window._tray = tray   # 让 window 持有引用
```

**② 必须关掉"最后一个窗口关闭就退出"**

```python
app.setQuitOnLastWindowClosed(False)
```

否则用户一点「隐藏悬浮窗」，窗口一关，整个程序就退出了，托盘图标也没了。

---

## 九、开机自启原理

### 写哪里

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

三种可选位置对比：

| 位置 | 权限 | 作用范围 | 结论 |
|------|------|----------|------|
| `HKLM\...\Run` | **需要管理员** | 所有用户 | ❌ 每次开机弹 UAC，体验差 |
| 启动文件夹 | 不需要 | 当前用户 | ⚠️ 放的是 `.lnk`，路径变动易失效 |
| `HKCU\...\Run` | **不需要** | 当前用户 | ✅ 采用 |

### 命令行怎么写

```
"…\.venv\Scripts\pythonw.exe" -m system_monitor --cwd "<项目根>"
```

三个细节：

1. **`pythonw.exe` 而不是 `python.exe`** —— 后者会弹一个黑色控制台窗口
2. **`-m system_monitor`** —— 不写死脚本路径，包内部重构也不影响
3. **`--cwd "<项目根>"`** —— 开机时进程的当前工作目录是 `C:\Windows\System32`，
   这会导致 `sys.path` 里没有 `src`，`import system_monitor` 直接失败。
   `--cwd` 让程序自己 `os.chdir()` 并 `sys.path.insert(0, src)`

### `--cwd` 的处理

在 `app.py` 里、`QApplication` 创建**之前**就处理掉，并且从参数列表里**摘除**，
否则 Qt 会把它当成自己的参数报错：

```python
def _prepare_import_path(argv):
    remaining = []
    i = 0
    while i < len(argv):
        if argv[i] == "--cwd" and i + 1 < len(argv):
            os.chdir(argv[i + 1])
            sys.path.insert(0, str(Path(argv[i + 1]) / "src"))
            i += 2          # 跳过 --cwd 和它的值
            continue
        remaining.append(argv[i])
        i += 1
    return remaining
```

### 失败回滚

写注册表可能因为权限、杀软拦截而失败。失败时**不能**让菜单项停在"已勾选"状态，
否则用户以为设置成功了。所以菜单开关这样做：

```python
def _on_autostart_toggled(self, checked):
    ok, message = set_autostart(checked)
    if not ok:
        self.setToolTip(message)
        print(f"[System Monitor] {message}", flush=True)
```

（上一版用 `QCheckBox` 时还需要 `blockSignals()` 防止程序化 `setChecked()` 反过来触发写入；
现在改用右键菜单，菜单每次弹出都重新读取真实注册表状态，天然不会有这个问题。）

---

## 十、刷新节奏

```
QTimer(1000ms) ──▶ refresh() ──▶ collect_memory()
                                    │
                                    ├─▶ 更新 detail_label / state_label
                                    ├─▶ gauge.set_value()
                                    ├─▶ _update_alert_state()   判断颜色与闪烁
                                    └─▶ snapshot_changed.emit() ──▶ 托盘更新图标
```

为什么是 1 秒？`psutil.virtual_memory()` 本身开销很小（读一次系统 API，微秒级），
1 秒足够及时发现内存暴涨，又不会让 CPU 占用升上去。

`collect_memory()` 返回 `None` 时（比如 psutil 异常），界面显示「读取失败」而不是崩溃。

---

## 十一、常见坑速查

| 现象 | 原因 | 解决 |
|------|------|------|
| 文字全是方块 □□□ | 离屏平台找不到字体 | 用 `QT_QPA_PLATFORM=windows` |
| 窗口有黑底方块 | QSS 背景在透明窗口上失效 | 改用 `QPainter` 在 `paintEvent` 画 |
| 托盘图标消失 | 托盘对象被 GC 回收 | `window._tray = tray` 持有引用 |
| 隐藏窗口后程序退出 | 默认"最后窗口关闭即退出" | `setQuitOnLastWindowClosed(False)` |
| 无边框窗口拖不动 | 没有原生标题栏 | 自己实现 `mousePress/Move/ReleaseEvent` |
| 无边框窗口拉不大 | 没有系统边框 | 右下角 `ResizeHandle` 转发位移 |
| 缩放时把手不在右下角 | 子控件不跟随布局 | `resizeEvent` 里 `move()` 到右下 + `raise_()` |
| 改完大小文字被裁 | 边距/字号写死像素 | 全部按窗口宽高比例推导 |
| 缩放后文字颜色变回默认 | `setStyleSheet` 整体覆盖 | 颜色+字号在同一处写 |
| 圆环画出一半被裁 | 线宽超出绘图区 | `rect` 往里缩 `thickness/2 + 1` |
| 进度方向反了 | Qt 正角度是逆时针 | span 用负数 |
| 换显示器后窗口找不到 | 保存的位置在屏幕外 | 恢复时校验是否在可见区域内 |
| 切主题后颜色错乱 | 只判断了 `_is_warn` | 按百分比重新计算三档颜色 |
| 开机启动报 `ModuleNotFoundError` | 工作目录不对 | `--cwd` 参数 + `sys.path.insert` |
| PySide6 导入报 DLL 错误 | venv 基于 Anaconda Python | `conda deactivate` → 删 `.venv` → `uv sync` |
