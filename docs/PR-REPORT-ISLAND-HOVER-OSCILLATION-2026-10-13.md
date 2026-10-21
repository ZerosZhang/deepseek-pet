# 灵动岛「靠边半隐藏」hover 振荡修复（交付证据）

> **基线**：`47b6bfe`（Merge PR #259 fix/edge-tts-proxy；分支从 `1ab73fe` 切出后
> 已 rebase 到它，`docs/INDEX.md` 的登记行冲突按"两行都留"解）
> **分支**：`fix/island-hover-oscillation`　**日期**：2026-10-13
> **范围**：4 个文件（实现 1、测试 1、文档 2——本报告与 `INDEX.md` 登记）
> **关联**：无对应 issue（用户实机反馈：鼠标移到靠边细条上不点击，岛反复
> 出现→隐藏→出现，周期约 1s）

## 一、核心特性

灵动岛停在左/右边缘时收成 16×64 的竖条，鼠标靠近滑出完整胶囊（高 44）。两者都
以细条中心居中，于是细条上下各露出 **10px**——光标停在这 10px 里时：

1. 细条盖着光标 → `enterEvent` → 滑出胶囊；
2. 胶囊比细条矮，上/下缘**越过光标**（光标此刻已在窗外）→ Qt 合成 `leaveEvent`；
3. 800ms 后 `_dock_back` 收回细条 → 细条重新盖住**同一像素** → 回到第 1 步。

第 3 步的判据只有 `_mode` / `_hover_peek`，不看光标在哪，于是回路自持。修复把
"鼠标走了没有"从「窗口矩形」换成「**可 hover 区 = 当前窗口矩形 + 细条矩形**」
（逐矩形判包含），收回前复检光标仍在区内就不收回。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 死区悬停不再振荡 | 光标停在细条死区：滑出后保持滑出，不再 800ms 一收一放 |
| 2 | 收口不丢 | 光标真的离开可 hover 区后，仍在一个收回周期（800ms）内收成细条 |
| 3 | 上下停靠零影响 | 上下停靠的滑出矩形完全覆盖细条，本来就无死区，行为逐位不变 |

**红线 / 不变量**：

- `_hover_rects()` 推导出的细条矩形必须**就是**收回后窗口落到的那个矩形
  （`_target_rect()` 的停靠收口公式，测试 `test_derived_strip_rect_is_the_retract_target`
  钉住），否则"光标在区内就不收回"这条推论不成立；
- 判据是**逐矩形并集**，不是 `QRect.united` 的**包围盒**——包围盒会把"胶囊下缘外
  那 10px 横带"划进区内（那里收回去完全安全，见
  `test_hover_zone_excludes_the_band_below_the_capsule`）；
- 上下停靠、非停靠态、拖拽、单击展开卡片、采样闸门（细条态停采样）等既有语义
  一律不动。

## 二、修改文件说明

`git diff --numstat`：`pet/dynamic_island.py` **+41 / −1**；新增
`tests/test_island_hover_oscillation.py`（**+389**）。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/dynamic_island.py` | +41 / −1 | ① `QtGui` 导入补 `QCursor`（判据唯一新增的输入）；② 「悬停」段新增 `_hover_rects()` 与 `_cursor_in_hover_zone()`（`_hover_rects` 在 docked 态用 `strip_rect_for` 按当前窗口推导细条矩形，`_cursor_in_hover_zone` = 逐矩形 `contains(QCursor.pos())`）；③ `_dock_back` 进入前复检：光标仍在区内 → 不收回、只把收回表延后一拍（**唯一的收回决策点**，细条单击的滑出预览共用它）；④ `leaveEvent` 的 `_dock_back_timer.start()` 补注释说明为什么**不在**这里按区拦表 |

细节（逐行理由）：

- `_dock_back` 的复检分支**不是**单纯 `return`：复检通过（光标还在区内）时重新
  `start()` 收回表。理由见第三节——只 `return` 会让"光标先停在死区、随后移出细条"
  这条路径没有任何事件能再把收回找回来（实机实测 3s 不回收，见第五节证据 ③）。
- `leaveEvent` 的 `_dock_back_timer.start()` **保持原样**（仍是无条件起表）：起表
  本身不改变任何可见状态，收回与否一律由 `_dock_back` 的复检决定。判据收在一个
  入口，避免"三处各写一份"。

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_island_hover_oscillation.py` | +389（新文件） | 8 个用例（3 组参数化：left/right 两组、top/bottom 一组，共 **12 例**）：死区悬停不振荡（左右各一）、光标真离开后必须收口（左右各一）、可 hover 区覆盖整条细条、上下停靠无死区且照常收回（上下各一）、细条单击（死区）不振荡、非停靠态区=窗口矩形、**判据不是包围盒**（胶囊下缘外 10px 横带不在区内）、**推导细条矩形 == 收回落点**（左右各一） |

测试的光标位置用 `QCursor.setPos()` 直接驱动（offscreen 平台实测可写可回读，见
`_put_cursor` 里的回读断言）——这是**操作系统边界**（真实鼠标位置没有别的确定性
注入方式），不算替身；副作用（全局光标）由 autouse fixture 复位。OS 语义用
`_os_hover()` 复刻：窗口在光标停着时缩小/移走会产生一次合成的 `leaveEvent`
（只在"圈内→圈外"的沿上发一次）。

### 未改动（有意不动）

| 文件 | 为什么不动 |
|---|---|
| `pet/dynamic_island.py::_target_rect` / `_apply_fixed_size` / `strip_rect_for` | 几何与视觉是锁定面：本修复只改**判据**，不动任何尺寸/位置公式，所以既有「收回不漂移」用例（`test_dynamic_island_revamp.py::test_left_edge_hover_cycles_do_not_drift`）逐项照旧 |
| `pet/dynamic_island.py::mouseReleaseEvent` | 细条单击预览（`_hover_peek = True` + `animate_to` + 起收回表）**故意不加第二份判据**：它的收回同样走 `_dock_back`，在那里复检即可；在单击点按区拦表反而会漏掉收口（单击时窗口还没变成胶囊，判据算出来的区就是细条本身，表永远不会起 → 滑出永久钉住） |
| `pet/dynamic_island.py::enterEvent` | 进入即滑出，无振荡入口 |
| 采样闸门 / 卡片 / 拖拽路径 | 与光标位置无关，且都有既有用例守着 |

## 三、实现要点

**判据**：`_hover_rects()` = `(窗口矩形,)`（非 docked）或 `(窗口矩形, 细条矩形)`
（docked，细条矩形由 `strip_rect_for(窗口矩形, dock_edge, 可用区)` 推导，与
`_target_rect()` 的收口公式同源）。`_cursor_in_hover_zone()` =
`any(rect.contains(QCursor.pos()))`。

**为什么是"并集"而不是"窗口矩形"**：滑出胶囊**不包含**细条（左右停靠：细条
16×64、胶囊 ≈194×44，同心），光标停在死区时它确实"已经离开窗口"，但它没有离开
"岛会响应 hover 的那片像素"。收回后细条立刻盖住它，就会 `enterEvent` 再来一次。

**为什么是"逐矩形判包含"而不是 `QRect.united`**：`united()` 给的是**包围盒**，
对左右停靠会额外覆盖"胶囊下缘外那 10px 横带"（x 在胶囊区间、y 在细条区间但不在
胶囊区间）——那里的光标既不在胶囊也不在细条，收回去完全安全。用包围盒会让收回被
无谓拖后到光标走得更远才发生（这处偏差是先按包围盒实现、被"真实光标的 leave 事件
落在 (189,444) 却不收表"实测抓到后改的）。

**为什么复检不通过时要"延后一拍"而不是"直接 return"**（本批唯一偏离原定修法的
一处，有实测依据）：只 return 少一个 retry，会留下一条**永久钉住**路径——光标停在
死区时 Qt 合成的 leave 发生在"区内"，若按区把它拦下，光标随后走出细条时窗口和
光标都不再动，**不会再有任何事件**来触发收回。第五节证据 ③ 实机复现了它（3s 不
回收）。因此收回表照常起，判据只在 `_dock_back` 里生效：复检不过 → 延后 800ms 再
判 → 光标真走了下一拍就收口（实测离开后 17ms 开始收回动画、172ms 落定）。

**细条单击为什么共用同一入口**：`mouseReleaseEvent` 的细条单击分支只负责"滑出 +
起表"，收回与否是 `_dock_back` 的事。单击时光标本来就停在细条上（正因如此才点得
到），复检会判定"仍在区内"从而不收回——这正是要的：**收回必须在不会立刻被
`enterEvent` 反转的时刻发生**。

**开销模型**：新增的只有"每次离开/每次收回表到点时一次 `QCursor.pos()` + 一次
`strip_rect_for`"。没有新增定时器（复用原有的单发 `_dock_back_timer`）、线程、
网络、磁盘或文件句柄。

## 四、性能分析

**方法（可复现）**：

```bash
python .scratch/bench_hover_zone.py 3        # 真 windows 插件，不建窗口、不抢光标
python .scratch/probe_summary.py             # 汇总实机探针日志
python .scratch/island_hover_probe.py left 2.5 3.0   # 见第五节
```

环境：Windows / Python 3.13.7 / PySide6 6.11.2 / 屏 2560×1392 / DPR 1.0。

| 指标 | 实测 | 归属 |
|---|---|---|
| `_cursor_in_hover_zone()` 单次 | 中位 **19.5 µs**（最好 19.39 / 最差 27.63，n=200000×3） | 新增 |
| ├ `strip_rect_for()` 单算 | 中位 3.52 µs | 复用既有纯函数 |
| ├ `_current_screen()`（含 `screenAt`） | 中位 3.15 µs | 既有 |
| └ `QCursor.pos()`（Win32 `GetCursorPos`） | 中位 3.53 µs（另一次运行 2.32 µs） | 新增系统调用 |
| 死区悬停 2.5s 内几何变化帧（修复后） | **11 帧**（= 一次滑出动画，末帧 0.20s），之后 2.32s 静止 | 修复前对照见下 |
| 死区悬停 6s 内"滑出→收回"回缩次数（修复前） | **6 次**（末帧 5.99s）⇒ 约 1.02s 一轮，每轮 ~19 帧几何变化 + 2 次 `setFixedSize` + 2 次采样器收/放 | 被消除 |
| 外部鼠标干扰检出（锁位写回） | 可用的 3 轮：0 次（修复后左停靠）/ 6 次（反证实验）/ 未计数（修复前那轮是早版探针，格式里没有该字段） | 环境噪声，见第五节 |

**结论（逐条）**：

1. **稳态开销**：不变。判据只在 `leaveEvent` 与 `_dock_back` 两处调用，都是
   事件级（人驱动，每秒最多几次）而非每帧路径；岛静止且光标不在附近时一次都不
   调用（`_dock_back` 要求 `_hover_peek` 为真，滑出态才有）。
2. **新增路径的绝对成本与触发频率**：19.5 µs/次。最坏频率 = 光标停在死区且岛处于
   滑出态时，收回表以 800ms 一拍复检 ⇒ **≤1.25 次/秒 ⇒ ≤24 µs/秒（单核的
   0.0024%）**；光标离开死区或停在胶囊上（`enterEvent` 停表）后归零。
3. **有无新的系统调用 / 网络 / 磁盘 / 线程**：只多一次 `GetCursorPos`（user32，最坏
   1.25 次/秒）。**无**新增线程、定时器、socket、文件读写或句柄；采样器
   （net/sys/gpu/fps）的收发完全由既有 `_sync_content_sampling` 决定。
4. **内存与缓存**：每次调用产生一个 1~2 元素的元组与 1~2 个 `QRect`，立即释放，
   无长驻对象、无缓存增长。
5. **净收益**：修复前死区悬停每秒重建一次"收回→滑出"（~19 帧几何变化 + 2 次
   `setFixedSize` + 2 次采样器收/放，即每秒重建一次网络/设备采样器与随之的线程、
   定时器、退订/订阅），修复后同一窗口 0 帧、0 次重建。

## 五、实机运行记录

探针 `.scratch/island_hover_probe.py`：**真实 Windows 插件**、真实屏幕、真实鼠标
（`SetCursorPos` 驱动并逐 tick 写回锁位），建真窗口 `DynamicIsland`（停靠左/右），
阶段 1 把光标锁在细条死区像素，阶段 2 移到可 hover 区之外，每 10ms 采样一次窗口
几何与 hover/peek 状态。**未启动整个桌宠进程**（原因见"未做"一节）。

**① 根因现场复现（修复前，`.scratch/probe-left-prefix.log`，光标锁在 (7,392)，
细条 `(0,390,16,64)`，死区各 10px）**：

```
  t= 0.026s  (0, 390, 16, 64, 'peek', 'docked', True, '-')
  t= 0.087s  (0, 397, 138, 50, 'peek', 'docked', False, 'back-timer')
  t= 0.903s  (0, 400, 194, 44, 'strip', 'docked', False, '-')      ← 收回
  t= 1.048s  (0, 390, 20, 64, 'peek', 'docked', True, '-')         ← 又被盖住 → 再滑出
  ...
  t= 5.913s  (0, 400, 194, 44, 'strip', 'docked', False, '-')
阶段 1 回缩（滑出→收回）次数 = 6
```

6s 内 6 次回缩、末帧 5.99s ⇒ 周期 ≈1.02s，自持不衰减。

**② 修复后同一场景（`.scratch/probe-fixed-left.log`，外部干扰 0 次）**：

```
  t= 0.195s [park] (0, 400, 194, 44, 'peek', 'docked', False, 'back-timer')  ← 滑出完成
  （此后 2.3s 无任何状态变化，光标一直锁在死区）
  t= 2.517s [away] (0, 400, 194, 44, 'strip', 'docked', False, '-')   ← 光标移出后收口
  t= 2.689s [away] (0, 390, 16, 64, 'strip', 'docked', False, '-')
阶段 1 回缩（滑出→收回）次数 = 0
阶段 2 回缩次数 = 1
采样 503 tick，检出外部鼠标干扰 0 次
```

**③ 为什么复检要"延后一拍"（反证实验）**：把 `leaveEvent` 也按区拦表（即"只离开
窗口不算离开"的最直白实现），同一探针得到 —— 阶段 1 稳定（0 次回缩），**阶段 2
一个状态帧都没有**（光标移出细条后岛停在 194×44 的滑出态 3s 不回收），日志
`.scratch/probe-planB-union-left.log`（干扰 6 次）。这正是"永久钉住"的实机证据，
也是本批采用"判据只在 `_dock_back` 生效 + 延后一拍"的依据。

**④ 边界与"本该失败"的观察**：

- **上下停靠**：`test_flat_dock_has_no_dead_zone_and_keeps_retracting` 断言滑出矩形
  完全覆盖细条、光标停在细条内时根本不产生合成 leave（`_cursor_inside is True`），
  移出后照常收回——修复对上下停靠是零改变；
- **判据过宽会怎样**：包围盒实现下，光标移到胶囊下缘外 3px（`(191,447)`，既不在
  胶囊也不在细条）时判为"仍在区内"、不收回——被
  `test_hover_zone_excludes_the_band_below_the_capsule` 钉住（该用例同时断言这个点
  确实落在包围盒内，说明两条实现的差别是真实的）；
- **光标离开后不许钉住**：`test_dead_zone_peek_retracts_once_the_cursor_leaves`
  同时验证"收口之后同一轮悬停还能再滑出"，防止判据把滑出一起锁死。

**⑤ 环境噪声的如实登记（探针有被外部鼠标污染的时候）**：探针的
"检出外部鼠标干扰 N 次"是逐 tick 判 `QCursor.pos() != 目标` 的结果（写回前读到偏差
即计数）。本机桌面同时在被人/其它进程使用（另有两个 `python -m pytest` 进程在用同一
个桌面会话），有三轮运行 **513/513、506/506、508/508 tick 全部偏离**（`SetCursorPos`
写下去立刻被改回去，光标根本不在死区）——那三轮
（`.scratch/probe-prefix-left.log`、`.scratch/probe-fixed-right.log`）**采不到任何
有效数据**，本文不引用其结论，只作噪声记录。**可靠运行的判据是干扰计数低且时间线
自洽**（修复后左停靠 0 次、反证实验 6 次；修复前那轮用的是早版探针、格式里没有该
字段，按时间线自洽判定），`probe_summary.py` 会自动把
干扰 ≥30 的运行标为"被外部鼠标污染"。因此**右停靠只有 offscreen 确定性测试覆盖**
（`test_dead_zone_peek_retracts_once_the_cursor_leaves[right]` 等左右参数化用例），
实机证据是左停靠。

**⑥ 未做的实机项与原因**：

- **未启动整个桌宠进程（`python -m pet`）做端到端肉眼确认**：本机桌面当时有另一个
  会话正在跑 GUI 测试（`python -m pytest` 两个进程在跑，其中包含窗口置顶/前台相关
  的用例），再叠一个 topmost 的岛窗口会污染对方的测量。改用**真窗口 + 真光标**的
  探针覆盖同一条代码路径（`DynamicIsland` 的 enter/leave/收回 + 真实 Windows 插件
  的合成事件）；
- **右停靠未取到干净的实机证据**：光标被外部进程钉在屏幕中部（508/508 tick 偏离），
  无法把它放到右边缘的 16px 细条里；右停靠由左右参数化的确定性用例覆盖；
- **未在 macOS / Linux 实机验证**：本机只有 Windows；判据用的是 Qt 的
  `enterEvent`/`leaveEvent`/`QCursor.pos()`，平台无关，但"窗口几何变化时合成
  leave"这件事在三端的确切时机**未验证**（本修复不假设它一定发生，只是保证即使它
  发生也不会形成回路）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/dynamic_island.py tests/test_island_hover_oscillation.py` | `All checks passed!` |
| 新回归（红·实现缺口） | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_island_hover_oscillation.py -q`（未改动的产品代码 + 最终测试文件） | **10 failed / 2 passed**（`_hover_rects`/`_cursor_in_hover_zone` 尚不存在 → `AttributeError`），日志 `.scratch/redcheck-impl.log` |
| 新回归（红·行为缺口） | 同上，实现到位但注入缺陷（`if self._cursor_in_hover_zone():` → `if False:`） | **3 failed / 9 passed**，失败正文即振荡帧：`assert not [(False, (0, 294, 110, 56)), (True, (0, 291, 38, 62)), (True, (0, 297, 180, 51)), ...]`（`收回 → 再滑出` 完整一轮；左右两档各一条 + 细条单击一条），日志 `.scratch/redcheck-injected.log` |
| 新回归（绿） | 同上，恢复实现 | **12 passed**（连跑 3 遍：1.88s / 1.90s / 1.67s，无 flake） |
| 点名必绿的既有用例 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_dynamic_island_revamp.py tests/test_island_dock_sampling.py -q` | **42 passed**（与改动前基线 42 完全一致；这两份文件手工驱动 `enterEvent(None)`/`leaveEvent(None)`/`_dock_back()`，offscreen 光标默认在 (10,10)，落在细条之外的 y 区间 ⇒ 仍走收回分支） |
| 灵动岛全族 | `QT_QPA_PLATFORM=offscreen python -m pytest $(ls tests/test_dynamic_island*.py tests/test_island_*.py) -q` | **702 passed**（37 个文件，83s，含本批 12 例） |
| 交付证据纪律 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr_report_discipline.py -q` | **137 passed**（含对本报告三节标题与 INDEX 登记的校验） |
| 岛相邻域（非岛族但会构造岛/读岛配置） | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_first_batch_features.py tests/test_overlay_geometry_parity.py tests/test_overlay_peripherals.py tests/test_overlay_shell.py tests/test_desktop_pet_features.py -q` | **161 passed** |

**红→绿证据链**：先写测试（红两段都录了——实现缺口 10 failed / 2 passed，行为缺口
3 failed / 9 passed）→ 实现 → 绿 12 passed；既有 42 例与全族 702 例在两段之间保持绿。

## 七、已知限制与后续

1. **判据依赖"合成 leave 会在窗口移出光标时发生"这一 Qt 行为**：本修复不假设它，
   但只在它成立时才有可见症状；若某平台不合成 leave，则连原 bug 也不存在。
2. **死区内的复检是轮询（800ms 一拍）**：光标停在死区时收回表会持续复检（设计如
   此，见第三节）。代价 ≤1.25 次/秒 × 19.5 µs；换来的是"光标真走了必定收口"。
3. **未覆盖的病态场景**：多屏拼接空洞、切换 DPI/分辨率瞬间的可用区变化——既有的
   `_clamp_to_screen` / `_target_rect` 负责，本修复不改变其口径。
4. **未做全量测试套件的完整复跑**（灵动岛全族已全绿）：改动只在 `dynamic_island.py`
   的悬停/收回判据，接口、落盘、线程与平台分发均未变；按 `AGENTS.md` 的
   "focused plus related tests are sufficient" 口径走聚焦 + 相关族。

## 八、风险与回滚

- **影响面**：仅 `DynamicIsland` 的停靠悬停收回判据；不动几何、绘制、配置键与落盘
  结构，**无新增配置键、无迁移**。
- **开关**：没有独立开关；「靠边半隐藏」（`dock_edge != "none"`）关闭时判据只返回
  窗口矩形，行为与既有完全一致。
- **回滚**：`git revert` 即可，无残留状态（不写配置、不留文件）。回滚后原振荡会回来
  （本报告 §五① 可复现）。
- **最坏情形**：判据误判为"仍在区内"⇒ 滑出比预期多停留一拍（≤800ms）；误判为
  "已离开"⇒ 回到原振荡。两侧都有用例钉住（`test_hover_zone_excludes_the_band_below_the_capsule`
  与 `test_side_dock_dead_zone_hover_does_not_oscillate`）。

---

> **纪律测试结果**：`tests/test_pr_report_discipline.py` → **137 passed**（本文件按模板逐字
> 包含「修改文件说明」「性能分析」「实机运行记录」三节，并已在 `docs/INDEX.md` 的
> 「PR 报告存档」登记）。
