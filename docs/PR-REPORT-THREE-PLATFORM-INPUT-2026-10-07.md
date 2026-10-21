# 三端批次：非 Windows 逐像素输入穿透 + macOS 关窗口阴影

> **基线**：`ee699c7`（Merge PR #233 from MerZlin/feature/agent-link-subtraction）
> **分支**：`feature/three-platform-input-region`（已并入 `integration/2026-10-07-night-batch`）
> **提交**：`2288870`（穿透实现）→ `320d448`（mac 阴影）→ `7f1b627`（审查修复轮）→ `94174f8`（测试缺口跟进）
> **日期**：2026-10-07
> **范围**：7 个文件（实现 4、测试 3、文档 0，其中 2 个新测试文件），净 `+1201 / −20`
> **状态**：分支未 push、PR 未开；本批六分支整合终全量 **4413 passed, 11 skipped**
> （`integration/2026-10-07-night-batch`，2026-10-07）
> **关联**：issue #229（macOS 窗口系统阴影）；上游在飞 PR #229（同机制的 mac 修法）；
> [`PR-REPORT-FULL-REVIEW-FIXES-2026-10-03.md`](PR-REPORT-FULL-REVIEW-FIXES-2026-10-03.md)
> 把「非 Windows 拓扑穿透」列为**发布阻断级**遗留项，本批即该条的收口；
> 报告体裁与必备章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；
> 本文已登记在 [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

新架构的默认拓扑是**一个全屏透明 overlay 窗**承载全部 sprite
（`pet/overlay_window.py`）。逐像素穿透此前**只有 Windows 实现**——所以在
Linux / macOS 上，整屏 overlay 就是一个整屏输入区，**桌面点击被整块吞掉**；
这是被 [`PR-REPORT-FULL-REVIEW-FIXES-2026-10-03.md`](PR-REPORT-FULL-REVIEW-FIXES-2026-10-03.md)
登记为「发布阻断级」的遗留项。本批把它补齐，顺带修掉 macOS 桌宠窗口外圈的系统
阴影黑边（issue #229）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 非 Windows 逐像素穿透（新 `pet/platform_passthrough.py`） | 纯判定层 `passthrough_decision`（与 Windows 侧**逐条同序同真值表**，离线可穷举）+ 薄 Qt 层 `QtPerPixelInputController`（同档位 10/50/100ms、同判定输入、同生命周期形状） |
| 2 | 落点写**两处**：属性 + 原生标志 | `window.setAttribute(WA_TransparentForMouseEvents, …)` **加** `window.windowHandle().setFlag(Qt.WindowTransparentForInput, …)`。**只写属性这个 P0 实际没修好**——见第三节第 1 条 |
| 3 | 显示契约三拍（`7f1b627`） | showEvent 同步收敛 → `singleShot(0)` 延迟对账（**先清再立**真重放）→ 10/50ms 轮询接管常规收敛 |
| 4 | macOS 关窗口系统阴影 | `pet/platform_mac.py` 新增 `_mac_no_window_shadow_flag()`，注入 `OverlayWindow.__init__` 与 legacy 的 `build_window_flags`（普通模式 + **直播捕获模式**都覆盖） |
| 5 | win32 路径一行未动 | `pet/platform_win.py` 零改动；`pet/overlay_window.py` 的 Windows 分支原样保留 |

**红线 / 不变量**：
- **与 Windows 侧判定语义逐条一致**：分派顺序（手动穿透 > 拖拽/不可见 > 盒外 >
  逐像素）不许变；全部 32 种布尔输入组合穷举比对（第六节）；
- **`pet/platform_win.py` 与 legacy 穿透路径零改动**（`pet/window.py` 的唯一改动
  是 mac 阴影标志那一行，见第二节）；
- **手动穿透开关不被自动逻辑清掉**：`stop()` 只清穿透态，`mouse_through` 是用户
  意愿，保留；
- **档位协议不变**：10ms（盒内）/ 50ms（盒外空转）/ 100ms（拖拽降频），与 Windows
  同值；
- **拖拽期恒不穿透**：拖拽必须持续收到鼠标事件。

## 二、修改文件说明

`git diff --numstat ee699c7 94174f8 -- pet tests`：7 个文件，净 `+1201 / −20`
（下表的增删是四条提交合并后的**净 diff**；其中 688 − 0 的测试文件在三条提交里
累计写过 525/149/42 行）。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/platform_passthrough.py`（**新**，289 行） | +289 / −0 | ① 纯判定层 `passthrough_decision(*, mouse_through, press_active, visible, inside_bounds, transparent_pixel)`（:69）——与 `platform_win.WindowsPerPixelInputController.should_click_through` **逐条同序同真值表**，可离线穷举；② 薄 Qt 层 `QtPerPixelInputController`（:93）：同档位（`NORMAL=10` / `IDLE=50` / `DRAG=100` ms）、同判定输入（`mouse_through` / `_press_global` / `isVisible()` / `mapFromGlobal` + `_is_transparent_at`），廉价事实短路后才算命中（不查 sprite alpha）；③ `_handle_win_id(win, handle)`（:173）**活读**句柄；④ `_apply_through(enabled, *, force)`（:185）属性与标志双写，`force=True` 时**先写 False 再写目标值**；⑤ `resume()`（:230）同步收敛 + 重开轮询表 + 排延迟对账；⑥ `_reconcile_after_show()`（:243）；⑦ `set_drag_active` / `stop`（:259/:275）与 Windows 侧同形。文件头写明**显示契约三拍**与未实测边界 |
| `pet/overlay_window.py` | +28 / −9 | 任务一：`showEvent` 平台分派改为 win32→原控制器（`_set_windows_no_activate` 仍 win32 专属，分支内原样）、其它→`QtPerPixelInputController`；**首次创建与恢复都走 `resume()`**（原来首次只起表）→ `show()` 返回时穿透态已收敛；顺手修掉两处已过期注释（文件头「非 Windows 穿透留待后续」、协议字段处「QRegion setMask 为后续阶段」）。任务二：`__init__` 构造 flags 时带上 mac 无阴影标志（+5/−1）。`hideEvent`/`closeEvent` 的 stop/resume 未改（两侧自动对称） |
| `pet/platform_mac.py` | +22 / −0 | 新增 `_mac_no_window_shadow_flag()`：darwin 返回 `NoDropShadowWindowHint`，其它平台返回 `Qt.WindowType(0)`（`flags \|= 0` 天然 no-op，调用点不必判平台）。docstring 写明 Qt cocoa 插件直接把它翻成 `[NSWindow setHasShadow:NO]`（qtbase 6.8 `QCocoaWindow::setWindowFlags`，`qcocoawindow.mm:726`），故**不用 objc ctypes**；并写明注入点必须在 **flags 构造处**（可见窗口上 `setWindowFlag` 会重建原生窗口、频闪）。平台知识与既有 `_keep_macos_tool_window_visible` 同处一模块 |
| `pet/window.py` | +5 / −1 | `build_window_flags` 带上 mac 无阴影标志，覆盖 legacy 主窗普通模式与**直播捕获模式**（`set_stream_capture_mode` 重算 flags 时自动带上）。这是 legacy 唯一的改动（该文件本就有 mac 专属块）。4482 行 ≤ 预算 4671 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_platform_passthrough.py`（**新**） | +688 / −0 | **37 条**：判定真值表 7 条（纯函数 + 协议入口各一遍）、短路不查 alpha、盒外短路、真 QWidget 上属性/标志切换 + 状态未变不重写 + **外部改写收敛**（属性侧与标志侧各一）+ 句柄变化重放、`stop()` 保留手动穿透、档位与拖拽降频、showEvent 平台分派（linux monkeypatch / win32 真跑各一）、hide→show 对称、隐藏期不轮询、close 释放、真 overlay 按-拖-放档位、与 Windows 控制器**逐条判定对齐**（win32 专属）、首显同步收敛、显示后对账在**三判据全读一致**的最坏情形下仍真重放、挂起对账在隐藏后不写回 |
| `tests/test_platform_mac_shadow.py`（**新**） | +143 / −0 | **9 条**：标志 darwin 分派（参数化）、overlay 主窗带/不带、`on_top` 改 flags 后标志仍在、`build_window_flags` 普通/捕获两种模式、真 `PetWindow` 普通→捕获→普通切换后仍带标志、非 darwin 逐位不变 |
| `tests/test_overlay_hidden_polling.py` | +26 / −10 | 三条 `skipif(os.name != "nt")` 用例的注释与 reason 由「逐像素穿透控制器仅 Windows 创建（posix 未实现）」改为「本组替身打的是 `platform_win` 的模块级入口，故仅 Windows」，并指向新的非 Windows 同形用例；`test_tray_hide_and_screen_migration_stay_paired` 的断言从 `if os.name == "nt"` 里**提出**，两平台都钉「新 overlay 必须重新有控制器并在轮询」+「**旧 overlay 的控制器必须已停表**」，控制器类型按 `sys.platform` 断言（与产品分派同一个键）；去掉 `test_matches_windows_controller_decisions` 的 win32 skipif（它只用 `object.__new__` 读判定、不碰 user32，posix 同样可跑——posix CI 从此有一条真对齐用例） |

### 未改动（看起来相关但故意没动）

| 文件 | 为什么不动 |
|---|---|
| `pet/platform_win.py` | Windows 侧已生产验证（扩展样式位、句柄变化重放、低频校正都有实机依据）；两边真正共用的只有「轮询档位 + 判定真值表」，抽公共基类要动它，风险大于收益。跨平台一致性改由测试钉住 |
| `pet/window.py` 的 legacy 穿透路径（`_set_windows_click_through` 等） | 政策「只修崩溃」；本批对 legacy 的唯一改动是 mac 阴影标志那一行 |
| `pet/window_placement.py`、`pet/overlay_shell.py` | 与本批无关；`overlay_shell` 的 `on_top` 开关走 `setWindowFlag`，标志保留由测试覆盖（不改代码） |
| `docs/` 下既有报告 | 本批为新增报告，不回改历史归档 |

## 三、实现要点

### 3.1 为什么落点必须写两处（这是本批最关键的技术判断）

任务书原本只说「落点 = `WA_TransparentForMouseEvents`」。照做之后发现**只写属性
这个 P0 并没有修好**：Qt 6.8 里属性→标志的 `QWidgetPrivate::adjustFlags` **只在
窗口创建 / `setWindowFlags` 时跑**（`qwidget.cpp:933/995/11020`），窗口已创建后再
设属性**不下发平台层**——offscreen 实测 `windowHandle().flags()` 不变，属性本身
只影响应用内投递。而跨应用穿透的入口只有窗口标志（X11 XFixes 输入形状 /
macOS `setIgnoresMouseEvents:` / Windows `WS_EX_TRANSPARENT`）。因此**同时补写**
`windowHandle().setFlag(Qt.WindowTransparentForInput, …)`：这个标志走平台
`setWindowFlags`，**不重建原生窗口**（`QWidget::setWindowFlag` 走 `setParent` 才会），
正是 10ms 级切换能用的原因。

### 3.2 两轮独立审查收敛出的同一条 Major：X11 上穿透会静默丢失

**主审（6.1sol）与交叉审（glm-5.3）各自独立报出同一条 Major**，措辞与证据不同、
结论一致——这是双方都指到真缺陷的信号：

> `resume()`/轮询读的是 `QWidget` **缓存**的 `winId()`。而 X11 上置顶（`on_top`）
> 标志触发的原生重建发生在 `QXcbWindow::show()`，**晚于** `showEvent`。重建后的新
> XCB 窗口**沿用旧的 `m_transparent=True` 缓存**，于是新窗口创建时的
> `setTransparentForMouseEvents(True)` **早退**、空输入区域不重建；同时句柄读起来
> 还是旧值 → 属性/标志/句柄三条跳过判据**全都读起来「已一致」** → 轮询永久跳过 →
> **X11 上整屏 overlay 持续吞点击**。这正是本 PR 要修的发布阻断项换个形态复发。

**修法两条（`7f1b627`，`pet/platform_passthrough.py`，Windows 路径一行未动）**：

1. **句柄判据改用活读** —— 新增 `_handle_win_id(win, handle)`（:173）：优先
   `QWindow::winId()`（`platformWindow->winId()` 活读，X11 上是新 XID），无 handle
   才退到 `QWidget::winId()`（**widget 侧缓存，平台重建时不更新——正是漏检来源**）。
   判到句柄变化 → 真重放。
2. **显示后强制对账** —— `resume()` 末尾排
   `QTimer.singleShot(0, window, self._reconcile_after_show)`（:243）；
   `_reconcile_after_show`（:246）**不看缓存、也不看状态是否「已一致」**，直接对
   当前目标态调用 `_apply_through(enabled, force=True)`。

**为什么必须「先清再立」**（Major 的机制核心）：新 XCB 窗口的 `m_transparent` 已经
是 `True`，**同名写入会被早退吃掉**。先写 `False` 则走
`setTransparentForMouseEvents(false)`（缓存是 True，**不早退**）→ 输入区域设回整窗、
`m_transparent=false`；**再写 `True` 就不早退** → 空输入区域才真正建立。

**覆盖路径**：`resume()` 是 `showEvent` 的唯一入口，所以对账在 hide→show **与
`on_top` 开关**（`overlay_shell` 的 `setWindowFlag` + `show`）两条路径上都会排；
另外常规 10ms 轮询也会借活读判据自愈。

**安全性**：`_reconcile_after_show` 在 `stop()` 停表后早退（**挂起的对账不会把已
清掉的穿透态写回**）；整体包 `try/except (AttributeError, OSError, RuntimeError)`
——它是异步投递，死包装器上的 Qt 调用会冒成 unraisable（同 `overlay_window._alive`
口径）。

### 3.3 审查的另外两条 Minor 也一并收口

- **首显同步收敛**：`pet/overlay_window.py:211-216` 的 Qt 分支由「首次创建只起表、
  否则 resume」改为**两种情况都走 `resume()`**——于是 `show()` 返回时穿透态已收敛
  且顺带排上延迟对账。交叉审实测到的空窗是真实存在的：只读探针下首次 `show()`
  返回后属性与原生 flag **均为 False**，要显式 `refresh()` 才为 True；而事件循环
  积压时首拍可推迟到 **139–169 ms**（见 3.5）。Windows 分支未动。
- **死状态清理**：`_applied_through` 在判据改读活状态后**只写不读**，是死字段
  （`grep -rn _applied_through pet tests` → 空），已删除。交叉审点出「Windows 版真
  读它做缓存校验，残留字段会误导维护者以为它是判据」——这条已修。

### 3.4 macOS 阴影改走纯 Qt 标志（**与任务书指定的 objc 路线不同，理由可测**）

任务书指定 objc `setHasShadow:NO`。实际选型时读 Qt 源码发现 cocoa 插件**已经**把
`Qt::NoDropShadowWindowHint` 直接翻成 `[NSWindow setHasShadow:NO]`
（qtbase 6.8 `QCocoaWindow::setWindowFlags`，`qcocoawindow.mm:726`；窗口创建路径的
`hasShadow` 由同一份 flags 决定），于是改用纯 Qt 标志，理由三条：

1. **等价效果**（同一份 flags 是唯一真源，Qt 每次重建原生窗口都按它重新下发）；
2. **可在 offscreen 真的断言**（objc 路线在 macOS CI 上要按
   `_mac_set_window_level` 的 cocoa/offscreen 守卫写法防段错误）；
3. **无 objc ABI / 段错误面**，且与上游在飞 PR #229 的写法一致。

**注入点刻意选在 flags 构造处**（`OverlayWindow.__init__`、`build_window_flags`）：
可见窗口上 `setWindowFlag` 会重建原生窗口（频闪，
`window_screen.set_stream_capture_mode` 就是被迫走这条路的先例），而构造处天然覆盖
「捕获模式开关重算 flags」这条路径，无需每次显示补写。**交付前请勿把 `build_window_flags`
的 darwin 判断改成别的写法**（例如在 `PetWindow.__init__` 一次性设标志）——捕获模式
开关会重算 flags，flags 工厂是唯一不会丢的注入点。

### 3.5 跑全量时抓到的一次真实假红（本批最值得留档的教训，已修）

第一次全量跑时**本批新写的三条「真事件循环」用例失败**。诊断结果：在大量测试之后，
单次 `app.processEvents()` 会阻塞 **139 ms**（实测），真定时器**首拍 169 ms 才到**
（空载单跑是 11 ms）——原先用 60/200/300 ms 的固定 pump 预算等不到 10ms 定时器。

修法（**只改测试**）：新增 `_wait_until(cond, timeout_ms=5000)` 事件同步等待；
判定类断言改为显式 `refresh()` 驱动（`resume()` 本来就同步 refresh，显示后立即收敛
是确定性断言）；`_pump` 只保留给「这段时间内不得有 X」这类**方向安全的否定断言**。
修后在前置 30 文件 + 失败用例的组合里连跑 2× 稳定绿。

**同族风险提醒（未动，值得跟进）**：仓库既有的 `_pump(400)` 式用例（如
`tests/test_overlay_hidden_polling.py`）只是因为它跑在套件较前位置才没暴露。

### 3.6 测试缺口跟进（`94174f8`，纯测试改动）

第二轮把三条覆盖缺口补上，**每条先验证能红**：

| 缺口 | 改法 | 红证据（注入变异） |
|---|---|---|
| 档位对齐在 posix 上是硬编码 | `test_poll_tiers_match_windows_protocol` 删掉硬编码 `(10, 50)` / `100`，改为从 `WindowsPerPixelInputController` 直接取三个常量逐值比对，三平台都断言 | `IDLE_POLL_INTERVAL_MS = 50 → 51` → 对应用例红 |
| 迁移链路的控制器断言被 `if os.name == "nt"` 包住（posix CI 不执行） | 断言提出，两平台都钉「新 overlay 重开表 + **旧 overlay 已停表**」，类型按 `sys.platform` 断 | 同时抑制 `hideEvent`/`closeEvent` 的 `stop()` → 「旧 overlay 的控制器必须已停表」红；伪装 `sys.platform=linux` 的探针下 posix isinstance 断言红 |
| 标志侧外部改写无同形用例 | 新增 `test_external_flag_write_is_converged_back`（同句柄下外部翻掉 `WindowTransparentForInput`，轮询须收回目标态） | 跳过判据改成 `flag_ok = True`（不看标志）→ 新用例红，属性侧用例仍绿 |

**无需改产品即绿**说明这是覆盖缺口而不是行为缺陷（原跳过判据本就同时读属性与标志）。
前提也核查过：`platform_win` 在 posix **可 import**——依据是 `gh pr checks 233` 显示
`test (ubuntu-latest) pass 6m34s` / `macos-latest pass` / `windows-latest pass`，而该
job 跑全量套件（只 ignore 4 个 webm 文件），其中 `tests/test_overlay_hidden_polling.py`、
`tests/test_input_controller_drag.py` 都是**模块级** `from pet import platform_win`。

## 四、性能分析

**方法（可复现）**：源 worktree 内的探针脚本（`QT_QPA_PLATFORM=offscreen`，真
`OverlayWindow` + 5 个 sprite，`refresh()` 直接计时，先做一次预热调用再计时）。
环境：Windows 10 x64 / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属（热路径 / 新增 / 既有） |
|---|---|---|
| 稳态 `refresh()`（盒内透明区、5 个 sprite、落点 no-op） | **19.94 µs/tick** | 新增；**推算占用：10ms 档 = 0.199% 单核，50ms 档 = 0.040% 单核** |
| 状态真翻转（`setAttribute` + `QWindow::setFlag`） | **4.66 µs/次** | 新增；**只在悬停变化时发生**，不是每 tick |
| 首次显示同步收敛（`resume()` 里的同步 `refresh()`） | 一次 `refresh()` = 上述 19.94 µs | 新增；每次 show 一次 |
| 显示后延迟对账（`singleShot(0)` → `_reconcile_after_show`） | 一次 `_apply_through(force=True)` = 两次写入 ≈ 2 × 4.66 µs | 新增；每次 show 一次 |
| 轮询档位切换 | 一次 `setInterval`（纯内存写） | 新增；拖拽按下/松手各一次 |
| 与 Windows 侧判定一致的成本 | `pass` 级纯布尔短路，探针分辨率以下 | 与既有 Windows 控制器同形 |
| **真实平台调用成本**（X11 的 XFixes 输入形状 / macOS `setIgnoresMouseEvents:`） | **本机测不到**（见下） | 未知，**如实登记** |

**结论**（逐条回答）：

1. **稳态开销有没有变化、变了多少**：非 Windows 上从「**零穿透控制器**（整屏输入区、
   桌面点击全被吞）」变成 **19.94 µs/tick**；按 10ms 档折算 **0.199% 单核**
   （50ms 空转档 0.040%）。Windows 侧稳态**零变化**（`platform_win` 一行未动，
   分派分支内原样）。新增的成本换来的是原本**完全不可用**的能力。
2. **新增路径的绝对成本与触发频率**：状态真翻转 4.66 µs/次，只在**光标悬停态变化**
   时触发（不是每 tick）；首显收敛与延迟对账各一次 `refresh()` / 双写，触发频率 =
   每次显示。写属性/写标志都是纯 Qt 内存操作（`testAttribute` / `flags()`），
  非 Windows 落点**不碰原生句柄**。
3. **有没有引入新的系统调用 / 网络 / 磁盘 / 线程**：**没有**。唯一新增的常驻物是
   一个 `QTimer`（以 overlay 为父对象，随窗销毁）；没有新线程、没有网络、没有磁盘写。
   注意 `refresh()` 每 tick 调一次 `QCursor.pos()` —— 这是**既有** Windows 实现同款
   代理，其平台成本见下条。
4. **内存与缓存有没有增长**：无增长。控制器随窗口创建/销毁（`QTimer` 以 window 为
   父对象，`deleteLater` 探针确认窗口与 timer 同时失效）；本批还**删掉了**一个死
   字段 `_applied_through`。无新增缓存容器。

**诚实边界（性能口径的一部分）**：**真实平台调用成本本机测不到**——19.94 µs / 4.66 µs
都是 **Qt 侧 + offscreen** 的数字。交叉审特别提醒：非 Windows 10ms 档每拍
`QCursor.pos()` 在 **X11 上是同步 X round-trip**，比 Win32 `GetCursorPos` 贵
（`WinCtl` 侧也是同一代理，但它有实机依据；非 Windows 侧没有）。**这一格留给有
X11 / macOS 显示会话的人**。

## 五、实机运行记录

本机：Windows 10 x64，真实开发机（非 CI、非 mock），**没有 X11 / macOS 显示会话**。
因此本节的诚实口径是：**Windows 真机 + 假件探针**能证明什么、不能证明什么，逐条写清。

1. **能在本机真实验证的部分（已跑）**：
   - **真值表穷举**（主审只读穷举，第六节复核）：全部 **32 种布尔输入组合**与
     Windows `should_click_through` **32/32 一致**；
   - **真 QWidget 上的属性/标志切换**：真窗口 `show/hide/close`、真
     `setAttribute` + `windowHandle().setFlag`，断言属性与标志的实际取值；
   - **生命周期真事件**：真 overlay 的 hide→show→close，断言控制器停表/重开表对称；
   - **`singleShot` 的真实调度**：真 overlay 的 `showEvent → resume → singleShot`
     接缝，把平台句柄换成「新窗口 + 缓存自称已穿透」的假件（**最坏情形：属性、标志、
     句柄三条判据全读一致，正常轮询永久跳过**），断言对账仍写出
     `[(FLAG, False), (FLAG, True)]`，属性写入末两项为 `[(ATTR, False), (ATTR, True)]`
     ——即**先清再立**真的发生了；
   - **`on_top` 开关的真实触发路径**：`setWindowFlag(WindowStaysOnTopHint, …) + show()`，
     关/开各一次都断言穿透态仍在；
   - **`--slot N` 窗口能力**（另一条线）：见 [`PR-REPORT-STREAM-CAPTURE-PHASE-A-2026-10-07.md`](PR-REPORT-STREAM-CAPTURE-PHASE-A-2026-10-07.md)。
2. **前提现场复现**：`python -m pytest tests/test_platform_passthrough.py -q`（实现前）
   → `ImportError: cannot import name 'platform_passthrough' from 'pet'`（**收集期
   1 error**）——即"这个能力此前完全不存在"，不是"行为不对"。
3. **用户可见行为的确认**：**未做真实 GUI 目视验收**。本机只有 Windows + offscreen，
   没有 Linux / macOS 显示会话，无法在真实合成器上点桌面确认"点击穿透过去了"、
   也无法肉眼看 macOS 阴影消失。**这是本批最大的验证缺口**，发布说明必须标注（见
   第七节第 1 条）。
4. **边界与失败路径（已自动验证）**：
   - `stop()` 后**挂起的对账不得把穿透态写回**（`test_pending_reconcile_does_not_reapply_after_hide`）；
   - 状态未变时**不重写**（避免每 tick 白写平台层）；
   - **外部改写会被收敛回来**（属性侧与标志侧各一条用例）；
   - 光标在窗口包围盒外 → 恒不穿透且降频到 50ms；
   - 拖拽中 → 恒不穿透且降频到 100ms；
   - 手动穿透开关在 `stop()` 后**仍保留**（自动逻辑不许覆盖用户意愿）。
5. **可复现的实机核对法（留给有对应平台的人）**：
   - **Linux（X11）**：`PET_RENDER_TOPOLOGY=overlay QT_QPA_PLATFORM=xcb python -m pet`
     → 在 overlay 透明区点击桌面（桌面/文件管理器应有反应）；再开菜单「鼠标穿透」
     验证宠物本身不可点；最后**切换「置顶」开关**（本轮 Major 的唯一已知触发路径）
     再重复一次穿透验证。
   - **macOS**：同一拓扑下确认窗口外圈无系统阴影黑边（普通模式与直播捕获模式各看
     一次），并在透明区点击确认穿透。
6. **CI 能证明什么、不能证明什么（重要）**：
   `gh pr checks 233` 显示 ubuntu / macOS / windows 三平台全绿，但
   **CI 全平台固定 `QT_QPA_PLATFORM=offscreen`**（`.github/workflows/pr-test.yml`），
   **不运行 XCB / Cocoa 后端**——所以 CI 绿**不等于**跨应用穿透被验证过，它只证明
   "状态机、判定与接线在三平台解释器上都对"。**发布说明需标注这一点。**

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | `All checks passed`（每条提交前都跑过） |
| 空白检查 | `git diff --check` | clean |
| 聚焦（11 个相关文件） | 两个新文件 + overlay/input-controller/capture/architecture 等 | **184 passed**（源 worktree，测试缺口轮结束后） |
| 本报告撰写时复测（整合分支） | `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_platform_passthrough.py tests/test_platform_mac_shadow.py tests/test_overlay_hidden_polling.py` | **其中 passthrough 37 / mac_shadow 9 / hidden_polling 7 条全部通过**（三文件合计 53 条全绿） |
| 全量（源 worktree，测试缺口轮结束） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4353 passed, 11 skipped, 0 failed**（EXIT=0，519.62s；`grep -c "^FAILED"` → 0）。自洽：上轮 4352 + 新增 1 例 |
| 全量（首轮，含 3 条假红） | 同上 | `4348 passed, 11 skipped`（3 条新用例因事件循环积压假红，见 3.5，修正后重跑绿） |
| 真值表穷举（主审独立复核） | 只读穷举 32 种布尔组合，与 `platform_win` 逐值比对 | **32/32 一致**（含短路顺序与"短路时不付 alpha 查询成本"） |
| 架构红线 | `tests/test_architecture.py` | 通过（`window.py` 4482 ≤ 预算 4671，无需校准） |
| 交付纪律 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr_report_discipline.py -q` | 见本文末（登记后全绿） |

**红 → 绿（test-first，逐轮）**

| 轮次 | 用例 | 写实现前 | 实现后 |
|---|---|---|---|
| `2288870` | `tests/test_platform_passthrough.py` 整文件 | **红**：`ImportError: cannot import name 'platform_passthrough' from 'pet'`（收集期 1 error） | **32 passed** |
| `320d448` | `tests/test_platform_mac_shadow.py` | **红**：`7 failed, 2 passed` | **9 passed** |
| `7f1b627` | 三条显示契约用例 | **红**：`3 failed, 32 passed`（`test_first_show_converges…`、`test_show_reconcile_replays…`、`test_recreated_native_window_replays…`——后者的红正是"读 widget 缓存 winId 会漏检"的直接证据） | **36 passed**（旧 32 + 新 4） |
| `94174f8` | 三条测试缺口 | 每条注入变异后**红**（见 3.6 表） | **37 passed** |

**断言有效性（变异验证，证明用例有牙）**

| 注入的缺陷 | 结果 |
|---|---|
| 抹掉 `_apply_through` 里的窗口标志写入 | **3 failed / 29 passed**（只写属性 → 3 条用例红，说明它们钉的是真行为） |
| 抹掉 `showEvent` 里 Qt 控制器的创建 | **5 failed / 27 passed** |
| 把对账里的 `force=True` 去掉 | `test_show_reconcile_replays…` 红（**1 failed / 34 passed**） |
| 把 `showEvent` 的 `resume()` 去掉 | **3 failed / 32 passed** |
| 档位常量 `IDLE_POLL_INTERVAL_MS = 50 → 51` | 对应用例红 |
| 跳过判据改成 `flag_ok = True`（不看标志） | 新用例红，属性侧用例仍绿 |
| 同时抑制 `hideEvent` 与 `closeEvent` 的 `stop()` | 「旧 overlay 的控制器必须已停表」红 |
| 伪装 `sys.platform=linux` + 把 Qt 分支换成 Windows 控制器 | posix 的 isinstance 断言红 |

## 七、已知限制与后续

### 7.1 未实测项（**诚实登记，发布说明需标注**）

1. **X11 真实跨应用穿透**：本机 Windows 无法执行。机制依据是 Qt 6.8 源码
   （`QXcbWindow::create/setWindowFlags` → XFixes 输入形状）；
   **已知边界：缺 XFixes 扩展时 `QXcbWindow::setTransparentForMouseEvents` 会静默
   早退**（`qxcbwindow.cpp:1279-1281`）。**发布说明需标注**。
2. **macOS 真实跨应用穿透**（`[NSWindow setIgnoresMouseEvents:]`）：同上，需实机。
3. **Wayland 原生会话**（非 XWayland）Qt 是否消费该标志**未验证**；生产 Linux 会被
   `pet/app._default_xcb_platform_on_wayland` 强制走 xcb，即 XWayland + XFixes 路径。
   **发布说明需标注 Wayland 非原生支持**。
4. **macOS 阴影真的消失**：只断言到「标志在窗口 flags 里」这一层；真机（含 `.app`
   构建）需人看。这也是上游 PR #229 声明验过的部分。
5. **真桌面上的定时器行为**：所有测量都是 offscreen；真合成器上的首拍与穿透切换
   手感未测。
6. **原生窗口重建后的重放**：offscreen 下 `setWindowFlag` 后 `winId()` **不变**（实测），
   所以「句柄变化 → 重放」只被假件用例覆盖，**没有真实重建的端到端证据**——本轮
   Major 的修复因此与本机口径一致地属于"接缝已验证、平台行为待实机"。
7. **CI 是 offscreen**：三平台 CI 全绿**验不了真实穿透**（见第五节第 6 条）。这既是
   限制也是发布说明必须写明的一点。
8. **X11 上「置顶开关切换后穿透仍在」**（本轮 Major 的真实释放点）：本机只能验证
   接缝与状态机，`m_transparent` 缓存行为无法在这里执行——**请 CI ubuntu + 实机确认**。

### 7.2 其它限制与后续

1. **上游在飞 PR #229 与本批改同一个 `build_window_flags` 的同一行**
   （`flags | NoDropShadowWindowHint`，darwin 限定），机制完全相同、无文本冲突：
   谁先合谁的另一处变 no-op 重复。**但它的方案没覆盖 overlay 主窗**
   （`build_window_flags` 不被 overlay 使用），所以 overlay 那半必须保留我们的。
2. **本提交改变了穿透的显示时序契约**（showEvent 同步收敛 + 显示后强制对账），
   `pet/platform_passthrough.py` 顶部「显示契约」小节写了三拍——**后续若有人再动
   `showEvent` 的分派，必须保住这三拍**。
3. **同族风险提醒**：仓库既有的 `_pump(400)` 式用例（如
   `tests/test_overlay_hidden_polling.py`）只是因为它跑在套件较前位置才没暴露事件
   循环积压问题；这是可跟进的独立改进（本轮未动）。
4. **posix 上的用例计数会 +1**：去掉 `test_matches_windows_controller_decisions` 的
   win32 skipif 后，posix CI 从「有窗口就跳」变成有一条真对齐用例；迁移用例里也多
   两条断言。**若 ubuntu/macOS CI 有"计数硬编码"类检查需留意**。
5. **Windows 侧既有的同形缺口未修**：主审指出的「首次显示无同步收敛」在 Windows
   构造路径上同款存在（协议上是"对齐"的，故本批保持 Windows 分支不动）；以及
   `stop()` 里 `self._timer.stop()` 在 try 外（窗口/定时器 C++ 对象已销毁后再调会
   抛未捕获 `RuntimeError`，与 Windows 版同构、触发面窄）。
6. **分支未 push、PR 未开**（见文末状态）。

## 八、风险与回滚

- **影响面**：默认拓扑（overlay）下的**输入穿透行为**是唯一的产品行为变更——非
  Windows 上从"整屏吞点击"变为"按目标态穿透"；Windows 侧零变化（`platform_win`
  一行未动）；legacy `pet/window.py` 只有 mac 阴影标志那一行。
- **开关**：无新增配置键、无设置页项。穿透跟随既有 `mouse_through` 手动开关与
  `drag_physics` 拖拽态，语义未变。
- **配置迁移**：无（不新增键、不改 schema）。
- **回滚**：`git revert` 四个提交即可（或丢弃分支），**无落盘残留**——本批不写任何
  持久化状态、无缓存格式变化、无迁移代码。回滚后非 Windows 回到"整屏吞点击"的
  发布阻断状态，**若发布前回滚，必须在发布说明里恢复该已知限制**（这也是它不能
  被静默回滚的原因）。
- **与整批其它分支的交互**：本批与 #219 / #220 / #211 / service-target 的文件集不
  相交；与直播捕获线的**唯一交互点**是 `pet/window.py`
  （那边改 `PetWindow.__init__` 的捕获模式有效值、`refresh_pet_settings` 的
  restart-level 判断，本批只改 `build_window_flags` 的 flags 组成）——
  整合后全量 **4413 passed, 11 skipped**，`window.py` 行数 4482 ≤ 预算 4671。
