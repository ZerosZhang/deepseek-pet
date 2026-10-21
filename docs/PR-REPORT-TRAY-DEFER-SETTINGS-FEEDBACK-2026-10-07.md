# 托盘设置入口延迟派发 + 设置交不出去时的可见反馈

> **基线**：`70ef156`（修 #216 峰谷副标题高度预算）；本分支两个提交经 `aa72d75` 并入
> integration
> **分支**：`fix/menu-deferred-dispatch-and-deadkey`　**提交**：`c0934ab`（缺陷 1）、
> `80e5502`（缺陷 2）　**日期**：2026-10-07
> **范围**：6 个文件（实现 3、测试 3），净 `+389 / −6`，含 2 个新测试文件
> **关联**：issue #4 同族（macOS 原生菜单跟踪会话中开窗被抑制 → 首次点击无反应）
> **互链**：菜单延迟派发的既有机制见
> [`CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md`](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md)；
> 设置进程隔离的既有测试口径见 `tests/test_settings_process_isolation.py`；必备证据章节见
> [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在 [`INDEX.md`](INDEX.md) 的
> 「PR 报告存档」。

## 一、核心特性

两个独立缺陷，同一类根因家族（**原生菜单跟踪会话里做窗口操作会被抑制**）：

1. **托盘「桌宠设置 / AI 设置」第一次点击没反应**——托盘菜单由 `QSystemTrayIcon` 原生弹出，
   回调此前是裸 `menu.addAction(text, callback)`，**在原生菜单跟踪会话里内联执行**。macOS 上
   托盘菜单是 AppKit 原生 NSMenu，跟踪会话中新建/激活窗口会被 AppKit 抑制，表现为「第一次
   点了没反应」（issue #4 同族）。右键菜单路径早有解法（`close_on_trigger` + `menu.exec()`
   返回后派发），但托盘菜单**进程里没有那个收口点**。
2. **设置进程交不出去时静默无反应**——`settings_process_isolation`（默认 `True`，设置界面
   **没有入口**的隐藏 config 键）手工置 `false` 时，legacy 拓扑有进程内设置窗兜底，**overlay
   拓扑没有**（没有 `PetWindow` 可挂 parent），`OverlayShell.open_settings_for` 直接
   `return False`——菜单项看着可用，点下去毫无反应，用户没有任何线索。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 托盘设置入口延迟派发 | `shared.add_tray_action`：先 `menu.close()`，再 50ms×60 轮询确认菜单真关了才执行回调 |
| 2 | 病态时不吞点击 | 3s 内菜单仍报未关闭 → **照旧执行回调**（宁可晚执行也不吞掉用户的点击） |
| 3 | 交不出去时可见反馈 | `open_settings_for` 返回 False 即冒气泡说明原因 + `logging.warning`；气泡被抑制时日志仍留痕 |
| 4 | 按原因分文案 | 「开关被关」（点名 `settings_process_isolation`，用户能在 config.json 改回来）／「独立设置进程没拉起来，稍后重试或看日志」 |
| 5 | 反馈收在唯一路由点 | 托盘 + 右键 facade 的 `on_open_modern_settings` / `on_open_settings` 三条入口自动都有 |

**红线 / 不变量**：
- 托盘**其余条目按最小面不动**（只改「AI 设置」「桌宠设置」两处 + overlay 同名入口）；
- 交出去**成功**的路径必须保持**完全静默**（不新增噪声）；无 `AppShell` 的替身场景同样静默；
- 回调**永不被吞**：3s 上限到达即强制执行；
- 轮询链由闭包持有菜单与回调，最长 3 秒，**不长期吊住对象**；定时器不绑 context（`AppShell`
  不是 QObject）。

## 二、修改文件说明

### 2.1 缺陷 1 — `c0934ab`（`git log --numstat c0934ab`）

```
6	3	pet/app.py
66	0	pet/context_menus/shared.py
5	2	pet/overlay_shell.py
6	0	tests/test_overlay_tray_routing.py
135	0	tests/test_tray_settings_deferred_dispatch.py
```

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/context_menus/shared.py` | +66 / −0 | 新增 `run_after_menu_closed(menu, callback)` 与 `add_tray_action(menu, text, callback)`。**为什么托盘不能复用 `defer_menu_callback`**：① 那条路依赖 `menu.exec()` 返回后的 `take_deferred_menu_callbacks` 派发点，而托盘菜单由 `QSystemTrayIcon` 原生弹出，进程里没有这个收口点；② 它用 `menu.isVisible()` 判断「是否在菜单里」，而 macOS 托盘菜单是 AppKit 原生 NSMenu（Qt 侧 QMenu 从不 `show()`，`isVisible()` **恒为 False**）——判定会直接退回内联执行，正是要避开的。因此本路径的规则是「**菜单先关、等它真的不在了再执行**」：先按其既有 `close_on_trigger` 语义 `menu.close()`，再用定时器轮询确认（预算 `50ms × 60 ≈ 3s`，与 `app.py::_present_dialog` 同口径）。Cocoa 的菜单跟踪跑在自身 run loop 模式，会压住这次定时器，命令自然落在跟踪会话结束之后。 |
| `pet/app.py` | +6 / −3 | `:3550-3551` 托盘「AI 设置 / 桌宠设置」改用 `add_tray_action`；`:48` 补 import。其余托盘条目按最小面不动。 |
| `pet/overlay_shell.py` | +5 / −2 | `:2962` overlay 托盘的同名「桌宠设置」入口同口径（同一入口的另一个拓扑：缺陷 2 的点击反馈如果内联冒泡，在原生跟踪会话里同样会被抑制）；`:91` 补 import。 |
| `tests/test_tray_settings_deferred_dispatch.py`（新） | +135 / −0 | 三个用例：legacy 托盘两个入口（参数化）+ overlay 托盘入口——菜单可见期内回调**不得执行**、点击后菜单**先关**、关闭后**执行一次**。 |
| `tests/test_overlay_tray_routing.py` | +6 / −0 | `test_tray_settings_entry_uses_main_identity` 只管身份路由，时序改成**宽预算轮询**（原断言 `== [""]` 不变）。 |

### 2.2 缺陷 2 — `80e5502`（`git log --numstat 80e5502`）

```
29	1	pet/overlay_shell.py
142	0	tests/test_overlay_settings_unavailable_feedback.py
```

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/overlay_shell.py` | +29 / −1 | `open_settings_for`（`:4089`）在 opener 返回 `False` 时调 `_notify_settings_unavailable`（`:4108`）：按原因分两条文案冒气泡 + `logging.warning`，并**点名 `settings_process_isolation`**。`open_settings_for` 的 docstring 补「交不出去时必须给可见反馈」。 |
| `tests/test_overlay_settings_unavailable_feedback.py`（新） | +142 / −0 | 5 个用例：真闸门（`AppShell.__new__` 桩 + `settings_process_isolation=false`，同 `test_settings_process_isolation._bare_shell` 口径）→ 返回 `False` 且气泡点名该键；拉起失败走**另一条**文案且**不误报**成开关被关；交出去成功与无 `AppShell` 两种情形**保持静默**；托盘点击的用户路径端到端可见反馈。 |

### 未改动（看起来相关但故意没动）

- **legacy 托盘「AI 对话 / 快速对话」**：仍是裸 `menu.addAction`（本次只改设置入口两项，按
  最小面）。**「AI 对话」只靠 `_defer_while_popup_active`（键 `QApplication.activePopupWidget()`）
  部分保护**——按该文件自己的注释，Cocoa 原生菜单跟踪期这个值**可能为 None**，即只被部分
  保护。见第七节。
- **macOS Dock 菜单**（`app.py:3357 _install_macos_dock_menu` 的「桌宠设置 / AI 对话」）：
  仍是裸 `menu.addAction`；Dock 菜单同样跑在原生会话里。
- 托盘其余条目、设置窗口本体、`settings_process_isolation` 的默认值与语义：一行未动。

## 三、实现要点

### 3.1 缺陷 1 修法：为什么是「先关、再轮询确认」

| 候选 | 否决/采纳理由 |
|---|---|
| 复用 `defer_menu_callback` | **否决**：依赖 `menu.exec()` 返回点，托盘菜单没有；且其判定用 `isVisible()`，在 macOS NSMenu 上恒 False → 退回内联执行（正是要避开的） |
| 直接把回调扔到 `QTimer.singleShot(0)` | **否决**：一个事件循环轮次不保证原生跟踪会话已结束（Cocoa 跟踪跑在自身 run loop 模式） |
| **先 `menu.close()`，再 50ms 轮询确认已关**（采纳） | 有明确判据（菜单真的不在了）、有硬上限（3s）、病态时**不吞点击**（到上限强制执行）；与 `app.py::_present_dialog` 同口径 |

关键性质：**语义是「永远晚一个事件循环、且要等菜单真关」**。将来任何「同步 `action.trigger()`
后立刻断言」的测试都必须改成轮询（本次已改一处：`test_overlay_tray_routing.py`）。

### 3.2 缺陷 2 修法：为什么是气泡而不是「菜单项置灰 + tooltip」

写进代码 docstring 的三条理由：

1. 该键在设置界面**没有任何入口**——置灰只说明「不可用」、**说不出原因**，用户也没有补救
   路径；
2. **tooltip 在 macOS 原生菜单上根本不显示**，而 mac 正是这条缺陷家族的主战场（legacy 拓扑
   有进程内设置窗兜底，只有 overlay 会走到这里）；
3. 反馈收在 `open_settings_for` 这个**唯一路由点**——托盘、右键 facade 的
   `on_open_modern_settings` / `on_open_settings` 三条入口自动都有；置灰得在每个菜单构建处
   各写一遍，且**构建期冻结的状态**在用户改完 config.json 后就是错的（该键改动**无需重启**）。

气泡被抑制时日志仍留痕（`logging.warning`），保证「没看到气泡」也能排查。

## 四、性能分析

**方法（可复现）**：不入库的临时探针 `/tmp/probe_tray_latency.py`、`/tmp/probe_tray_latency3.py`
（本次交付后删除），在本 worktree 内以 `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python <probe>`
运行；样本量为脚本内循环次数；测量的是真实 `pet.context_menus.shared` 的函数。
环境：Windows / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属 |
|---|---|---|
| 正常路径 `trigger → 回调` 延迟（菜单本就不在显示态） | **min 0ms / median 0ms / max 4ms**（n=50，单位 ms） | 新增 |
| 轮询判定单次成本 `_menu_open(menu)` | **0.338 µs**（n=200 000 均值） | 新增 |
| 最坏路径（菜单「一直开着」，把 `_menu_open` 钉成 `True`） | 回调在 **3740 ms** 时**仍然执行**（设计上限 `60 × 50ms = 3000ms` 名义值；实测墙钟略高，因 `singleShot(50)` 在探针的 `processEvents` 循环里有定时器松弛）——**证明回调不会被吞** | 新增（病态上限） |
| 轮询间隔 / 上限 | `_MENU_CLOSE_POLL_MS = 50`、`_MENU_CLOSE_POLL_MAX = 60` → 名义上限 3.0s | 新增 |
| 稳态开销（不点托盘设置） | **零** —— 只在 `triggered` 信号里发生，不点则一行不跑；**无定时器常驻、无轮询常驻** | 既有路径不变 |
| 缺陷 2 新增路径成本 | 一次 `Config.get` 判空 + 一次 `logging.warning` + 一次 `show_bubble`（仅**失败**路径；成功路径完全静默） | 新增 |
| 新增线程 / 网络 / 磁盘 / 系统调用 | **0 / 0 / 0 / 0** —— 用的是 Qt 定时器，不是线程 | — |
| 内存 | 轮询链由闭包持有菜单与回调，**最长 3 秒**后释放；`QTimer.singleShot` 不绑 context（`AppShell` 不是 QObject），故不长期吊住对象 | 新增（有界、短命） |

**测量边界（如实登记）**：离屏平台下 `QMenu.show()` **不会**进入 `isVisible() == True` 的状态
（探针实测：`visible=True` 的样本延迟仍为 0ms，说明菜单没被算作「开着」），所以「真的开着
菜单时会等多久」这一段**无法在离屏下自然复现**，只能用把 `_menu_open` 钉成 `True` 的方式
测出**上限行为**。真机 Windows 路径的语义由测试覆盖（真实 `isVisible` 时序），macOS 的
NSMenu 行为**无法在本机实测**（见第七节）。

**结论**：① **稳态开销零变化**——不点托盘设置入口时该改动完全不参与（无常驻定时器/轮询）；
② **新增路径绝对成本**：正常路径是**一个事件循环轮次**（实测中位 0ms、最大 4ms），退出方式
是 `menu.close()` + 一次 0.338 µs 的可见性判定；③ **未引入新的线程/网络/磁盘/系统调用**；
④ **内存有界且短命**（闭包最长 3 秒）。

## 五、实机运行记录

**主代理本机真机验收（真实桌面、真实进程、真实树）**：

- **集成全量在当晚最终树上的真机运行**：`integration/2026-10-07-night-batch` 最终树
  **4828 passed, 11 skipped**（`QT_QPA_PLATFORM=offscreen python -m pytest -q`）——本分支两个
  提交包含在该树内，故其在真机上的回归面已被全量套件覆盖。
- **如实登记（缺一条专门的真机点验）**：**本次没有针对「托盘设置入口第一次点击是否生效」
  与「设置交不出去时是否冒气泡」做专门的真机鼠标点验**（不像 #208/#209/#172/#228/#221 那样
  有一条逐条可引的真机验收记录）。本报告的实机证据止于：① 上述集成全量在真实机器上通过；
  ② 第五节下方的探针输出（真实 Qt 平台，非 mock）；③ 第七节列出的 macOS 不可验边界。
  **不把「自动化全绿」说成「真机点过」。**

**本机真实 Qt 的探针原始输出（不是 mock，是真实 `pet.context_menus.shared` 函数）**：

```text
$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python /tmp/probe_tray_latency3.py
_menu_open 单次 = 0.338 us (n=200000)
钉成 True 时 trigger->回调 = [3740] ms；预期上限 = 60*50 = 3000 ms
菜单已关时 trigger->回调 ms: min=0 median=0 max=4 (n=50)
```

**根因/前提的现场复现（改动前，红）**：

```text
$ QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_tray_settings_deferred_dispatch.py
3 failed
  AI 设置：菜单还开着，回调不许内联执行 / assert ['ai'] == []
  桌宠设置：菜单还开着，回调不许内联执行 / assert ['pet'] == []
  菜单还开着，设置入口不许内联执行 / opened == [_SettingsIdentity]

$ QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_overlay_settings_unavailable_feedback.py
3 failed, 2 passed   # 三条反馈用例气泡实测为 ''（静默）；两条「保持静默」守卫用例本来就过
```

**边界与失败路径（实机/自动已验证）**：

- 交出去**成功** → **完全静默**（不新增噪声）；**无 `AppShell`** 的替身场景同样静默。
- 独立设置进程**拉起失败** → 走**另一条**文案，**不误报**成「开关被关」。
- 菜单 3s 内仍报未关闭 → 回调**照旧执行**（探针实测 3740ms 时执行；测试覆盖）。
- 每次点击回调**只执行一次**（测试断言）。

**无法自动验证的能力（如实登记）**：

- **macOS 原生 NSMenu 行为无法在本机（Windows）实测**。依据是该仓库既有的实测注释
  （`app.py::open_quick_chat`）与 `_present_dialog` 的同款设计，不是本次现场探针。若要验收，
  建议在真 mac 上手工点一次托盘设置入口看首次点击是否生效。
- **离屏平台下菜单不会进入可见态**，所以「真开着菜单时的等待」只有上限行为证据（见第四节）。

## 六、测试与验证

**红 → 绿（两个缺陷各自 test-first）**

| 缺陷 | 写实现前 | 实现后 |
|---|---|---|
| 1（托盘延迟派发） | **3 failed**（见第五节的原始输出） | **3 passed in 1.18s** |
| 2（交不出去可见反馈） | **3 failed, 2 passed**（三条反馈用例气泡实测为 `''`；两条「保持静默」守卫用例本来就过） | **5 passed in 1.28s** |

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `ruff check pet/ tests/` | `All checks passed!`（两次改动后各跑一次，含提交后复跑） |
| 聚焦 | `test_tray_settings_deferred_dispatch / test_overlay_settings_unavailable_feedback / test_overlay_tray_routing / test_tray_icon_ready` | **42 passed** |
| 聚焦（扩面） | `test_overlay_per_slot_settings / test_settings_process_isolation / test_sprite_menu_parity / test_sprite_menu_facade / test_overlay_app_hosts` | **119 passed** |
| 聚焦（菜单族） | `test_menu_layout / test_menu_tree_release / test_harness_lifecycle / test_desktop_pet_features / test_requested_regressions` | **288 passed, 1 skipped** |
| 全量（`c0934ab` 状态） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4443 passed, 11 skipped, exit 0**（647s） |
| 全量（最终状态 `80e5502`） | 同上 | **4448 passed, 11 skipped, exit 0**（632s；+5 = 缺陷 2 的新用例） |
| 集成全量（当晚最终树） | 同上（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

提交用**显式路径** `git add`；未 push、未动主仓与其它 worktree、**未运行/终止任何用户进程**
（桌宠进程未触碰）。

## 七、已知限制与后续

1. **macOS 原生 NSMenu 的「`isVisible()` 恒 False + Cocoa run loop 压住定时器」无法在本机
   实测**（依据是仓库既有实测注释与 `_present_dialog` 的同款设计）。Windows / offscreen 路径
   有测试覆盖。真 mac 上建议手工点一次托盘设置入口看首次点击是否生效。
2. **刻意未覆盖的同族点**（父代理可决定是否另开单）：
   - legacy 托盘「**AI 对话 / 快速对话**」仍是裸 `menu.addAction`；「AI 对话」只靠
     `_defer_while_popup_active`（键 `QApplication.activePopupWidget()`）部分保护——按该文件
     自己的注释，Cocoa 原生菜单跟踪期这个值**可能为 None**。
   - **macOS Dock 菜单**（`app.py:3357 _install_macos_dock_menu` 的「桌宠设置 / AI 对话」）
     同样是裸 `menu.addAction`，而 Dock 菜单同样跑在原生会话里。
3. **`add_tray_action` 的语义是「永远晚一个事件循环、且要等菜单真关」**：将来任何同步
   `action.trigger()` 后立刻断言的测试都必须改成轮询（本次已改一处）。回调不会被吞：菜单
   3s 内仍报未关闭时照旧执行。
4. **中间提交依赖同批测试改动**：`c0934ab` 依赖 `test_overlay_tray_routing.py` 的轮询改写。
   squash 合并无影响；**若逐个 cherry-pick，必须把该测试一并带走**。
5. **`_notify_settings_unavailable` 的文案分两种原因**：若以后 `open_settings_process` 增加
   新的 `False` 分支，需要同步扩这条分支文案，否则会**误报成「开关被关」**。
6. **未做专门的真机点验**（见第五节）。

## 八、风险与回滚

- **影响面**：托盘「AI 设置 / 桌宠设置」两个入口 + overlay 托盘的「桌宠设置」，行为从
  「内联执行」改为「菜单关闭后执行」；其余托盘条目一行未动。缺陷 2 只在**失败**路径新增
  一条气泡与一条日志（成功路径保持静默）。
- **配置迁移**：**无新增/变更配置键**（`settings_process_isolation` 是既有键，本次只补它的
  失败反馈）。无落盘数据迁移。
- **行为副作用**：`add_tray_action` 的语义变化对**测试**有传染性（同步断言必须改轮询，已在
  `test_overlay_tray_routing.py` 落实）。对用户可见的副作用是点击后设置窗晚一个事件循环
  出现——实测中位 0ms、最大 4ms，不可感知。
- **回滚**：`git revert 80e5502 c0934ab`（两个提交都要退，`c0934ab` 是前置）。回滚后无残留
  状态：无新增配置键、无落盘数据、无定时器残留（轮询链最长 3 秒自行结束；回滚时若恰有
  在途轮询，它执行的是**用户本来就点的那次回调**，不产生额外副作用）。
- **合并冲突面**：`pet/context_menus/shared.py`（当晚多条批次都改这个文件）与
  `pet/overlay_shell.py`（#172 的菜单置灰与 #228 的设置行接线也动过它）；
  `tests/test_overlay_tray_routing.py` 的时序改写与其它菜单测试族可能撞车。
- **分支状态**：两个提交经 `aa72d75`（第二父提交 `80e5502`，其父为 `c0934ab`）一并并入
  `integration/2026-10-07-night-batch`；分支未 push、PR 未开。
