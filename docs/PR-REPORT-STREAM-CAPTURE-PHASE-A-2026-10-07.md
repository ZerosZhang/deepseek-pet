# 直播捕获 Phase A：兼容开关接通为重启级拓扑切换

> **基线**：`ee699c7`（Merge PR #233 from MerZlin/feature/agent-link-subtraction）
> **分支**：`feature/stream-capture-reconnect`（已并入 `integration/2026-10-07-night-batch`）
> **提交**：`9f4f55d`（接通）→ `142aed7`（审查修复六条）
> **日期**：2026-10-07
> **范围**：16 个文件（实现 7、测试 8、文档 2，其中 1 个新测试文件），净 `+935 / −156`
> **状态**：分支未 push、PR 未开；本批六分支整合终全量 **4413 passed, 11 skipped**
> （`integration/2026-10-07-night-batch`，2026-10-07）
> **关联**：issue #231（OBS 捕获黑屏与枚举不到）；T4 设计原文
> `.scratch/single-overlay-window/PHASE4_DESIGN.md:76-83`；
> [`PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md`](PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md)
> §B8（当时把该开关定为「置灰 + 暂不支持」，**本批推翻**）；
> [`PR-REPORT-PHASE4-4-RETIRE-MULTIPROCESS-2026-09-23.md`](PR-REPORT-PHASE4-4-RETIRE-MULTIPROCESS-2026-09-23.md)
> （slot 文件锁退役的背景）；报告体裁与必备章节见
> [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在
> [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

**问题**：默认拓扑（overlay 单合成窗）下，设置页的「直播捕获兼容模式」开关被
**整体置灰 + 文案改成"暂不支持"**（`400e8df`，2026-10-01），于是开着新版的用户
**唯一入口被摘掉**——OBS 连窗口都枚举不到（overlay 窗是 `TOOLWINDOW`，OBS 列表
会过滤掉它）。而这个开关的「重启级切换」设计（T4）**从来没落地过**：`a28bb4d`
（2026-09-24）先写了承诺文案，`400e8df` 把承诺改成了置灰 + 理由。

本批做的事**不是"恢复被删的功能"，而是"把 T4 已批准但从未实现的重启级切换真正
实现出来"**——并把 OBS 黑屏的真正边界如实写进 README。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 开关不再置灰，勾选 = **重启级**切换 | 保存后重启桌宠即走 legacy 单窗路径（标题「dsh-pet 桌宠」、`Qt.Window` 而非 `Qt.Tool`），此时 **OBS 能枚举到并选中它** |
| 2 | 拓扑判定新增第二输入 | `is_overlay_topology()` 由「只看 env」变为「显式 env 优先，否则 `not 主配置捕获开关`」，**进程内快照一次**（T5 定死：不做运行期切换） |
| 3 | 重启时多宠**收拢为主宠物**且**清单保留** | 不构造 `OverlayShell` ⇒ 多宠不复活；`overlay-active-pets.json` **不删**，取消勾选再重启即全部回来 |
| 4 | 单实例门扩张到 **两个拓扑都抢** | `overlay_instance_gate` 的 `is_required()` 删除，`acquire_overlay_instance_gate()` 无条件建门；legacy 下双击第二实例被拒（退出码 0 + 留痕） |
| 5 | 捕获模式下手动「生小肥鱼」被拦截并解释 | 冒泡「直播捕获兼容模式仅主宠物」（4s），不出现第二个同名窗口 |
| 6 | `--slot N` 窗能力跟随主配置 | 主配置捕获开启时压过窗口自己那份，避免"走 legacy 却仍是 Tool 窗"的半套状态 |
| 7 | 取消勾选**不再热切换** | 重启级开关不得运行期回撤（否则一点设置就把正在被 OBS 捕获的窗口当场变回 Tool 窗 = 断源） |
| 8 | 子宠设置页该行置灰 + tooltip | 「仅主桌宠可设置」（该键只读主配置，子宠页勾选永远不生效 = 死开关） |

**红线 / 不变量**：
- **捕获模式是重启级，不是热切换**：进程内拓扑判定不许翻（`_CAPTURE_SNAPSHOT`），
  设置页文案与行为必须同口径（「保存后重启桌宠生效」）；
- **活跃宠清单不许删**：「关掉开关就回来」的前提是清单保留——所以捕获模式下
  「一键退出子肥鱼」静默无效**是有意为之**，不要顺手清；
- **显式 `PET_RENDER_TOPOLOGY` 仍压过配置**：dev 逃生门与开发隔离靠它，且该路径下
  保留原有的**运行期即时切换**语义（那是开发期分流，不是用户开关）；
- **`pet/platform_win.py`、legacy 穿透路径零改动**；`PetWindow` 本身只加能力位与
  重启级判断，**没有**改它的渲染/事件路径。

## 二、修改文件说明

`git diff --numstat ee699c7 142aed7`：16 个文件，净 `+935 / −156`
（下表是两条提交合并后的**净 diff**；`9f4f55d` 单独是 12 文件 `+571/−139`，
`142aed7` 单独是 13 文件 `+420/−73`）。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/overlay_settings_command.py` | +144 / −6 | 拓扑判定加第二输入。新增 `STREAM_CAPTURE_KEY`、`topology_config_path()`（复用 `config._default_base()/APP_DIR_NAME`，与 `pet/app.py` 同口径、**不另拼路径**）、`_read_stream_capture_mode(path)`（`OSError`/`ValueError`/非对象一律 `False`；布尔清洗复用 `config._bool_or_default`，手改 `"true"/"1"/"on"` 也算开启）、`stream_capture_mode_enabled()`（**按配置路径快照一次**）、`reset_topology_snapshot()`（测试/诊断）、`_explicit_env_verdict()` / `env_forces_legacy()`；`is_overlay_topology()` → 显式 env 优先，否则 `not 捕获开关`。第二轮追加：`capture_switch_is_restart_level()`（:180）、`effective_stream_capture_mode(window_value)`（:196）；目录 seam 从函数内 import 提到**模块级**（夹具与用例都能注入） |
| `pet/settings_pet_controls.py` | +31 / −18 | 删掉 overlay 置灰块与其专用文案 `STREAM_CAPTURE_OVERLAY_HINT`；新增 `STREAM_CAPTURE_RESTART_HINT = 基础文案 + "重启后生效；重启时多只桌宠会先收拢为主宠物。"`（T4 逐字口径）；`stream_capture_hint()` 分流：显式 env legacy → 原提示逐字，其余 → 重启级文案。第二轮追加：子宠页（`host.config.instance_id` 非空）`setEnabled(False)` + tooltip「仅主桌宠可设置」。文案落在本模块，`modern_settings_dialog.py` 行数预算零影响 |
| `pet/overlay_instance_gate.py` | +25 / −31 | 删 `is_required()`，`acquire_overlay_instance_gate()` **无条件建门**（返回类型不再 `\| None`）；docstring 说明语义已从「overlay 拓扑门」变为「桌宠进程单实例门」。**锁名 `overlay-instance.lock` 与留痕名 `pet-overlay-gate.log` 刻意保留**（跨版本稳定，改名只会留孤儿锁；模块 docstring 注明「overlay 是历史名」）。第二轮把全部日志/注释口径由「overlay 单实例进程门」改为「桌宠单实例进程门 / 已有实例持有进程门」 |
| `pet/app.py` | +43 / −19 | `main()` 的门判定去掉 `is not None`（两拓扑都抢）；`start()` 拓扑分流处加 `logging.info('渲染拓扑: %s', ...)` 一行可 grep 证据；注释写明捕获模式走 legacy、`OverlayShell` 不构造 ⇒ 多宠不复活、清单不删。第二轮：`spawn_pet()` 入口在 `not is_overlay_topology()` 时记日志 + `win.show_bubble("直播捕获兼容模式仅主宠物", duration_ms=4000)` 后 `return`（**显式 env legacy 也拦**：同拓扑同语义） |
| `pet/window.py` | +14 / −2 | `PetWindow.__init__` 的有效捕获值改走 `effective_stream_capture_mode()`（**不改写 slot 文件**，只影响本次窗口能力的有效值）；`refresh_pet_settings` 在 `capture_switch_is_restart_level()` 时只 `logging.info("…改动重启后生效")`、**不调** `set_stream_capture_mode`（显式 env legacy 走 else 分支，保持原有即时切换） |
| `pet/overlay_shell.py` | +7 / −4 | 两处陈旧描述同步（模块头 T5 段 + `is_overlay_topology()` docstring）：判定输入已含主配置捕获开关 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_overlay_settings_command.py` | +113 / −4 | autouse 快照清理夹具 + `_pin_config()`（把门的配置路径钉到 tmp，**不读开发机真实 `config.json`**）。12 条：配置 true→legacy、宽松布尔 `True/"true"/"1"/" yes "/"on"`、四种坏配置（缺失/损坏/非对象/**路径被目录占住**）→ overlay 且不抛、显式 env 压过配置、**快照一次**（盘上改动不改本进程判定）、路径解析复用 config 口径 |
| `tests/test_background_service_gates.py` | +129 / −7 | `_start_shell` 扩三个可选参数（`topology=None` 不设 env / `prepare(config)` / `ui_create`），零行为变化。新增 `test_stream_capture_mode_boots_legacy_single_window`（真 `AppShell.start()` 生产路径：建 `PetWindow`、**无 overlay 壳**、实例数 1、活跃宠清单 `[1,2]` 原样保留）+ overlay 对照组；第二轮追加 `test_capture_mode_refuses_manual_spawn`（走真接线 `PetWindow._wire_window` 挂上的菜单回调，断言 `spawn_in_process_window` 零调用、实例数仍 1、气泡文案）+ 对照组 `test_overlay_topology_still_spawns_on_menu_action`（overlay 下同一回调照生，`spawned == [1]`，证明非空转） |
| `tests/test_overlay_instance_gate.py` | +69 / −30 | 删 `test_topology_check_forwards_to_overlay_shell` / `test_legacy_topology_has_no_gate`，改为 `test_gate_is_topology_independent`（legacy / 空 / overlay / 大写，四个拓扑都抢、都被拒）与 `test_legacy_topology_also_holds_the_gate`；`test_main_legacy_topology_skips_gate…` → `also_takes_gate…`（锁被抢过留痕、退出后释放、仍不建 slots/）；新增 `test_main_legacy_topology_refuses_second_instance` |
| `tests/test_stream_capture_window_switch.py`（**新**） | +118 / −0 | 3 条：`test_slot_window_follows_main_capture_switch`（窗口类型 `Qt.Window`、标题「dsh-pet 桌宠」、气泡挂主窗，且 `config-slot-1.json` **盘上仍是 false**）、`test_slot_window_keeps_own_switch_when_main_capture_off`（对照组）、`test_runtime_switch_refused_when_topology_came_from_config`（改配置 + refresh 后标题/类型不变 + 日志在） |
| `tests/test_stream_capture_copy.py` | +156 / −20 | 翻转「暂不支持」断言 → `RESTART_HINT`；新增已勾选状态共用同文案、**两拓扑下控件都不置灰**（`isEnabled()` / 点击）、显式 env legacy 逐字原提示、配置 true 翻转拓扑判定；第二轮追加 `test_stream_capture_check_disabled_on_child_page`（含点击无效 + tooltip 文案）与 `..._child_row_also_disabled_in_legacy` |
| `tests/test_settings_overlay_copy.py` | +16 / −12 | T2 两条：置灰 → 可点 + 重启级文案；点击送达覆盖两拓扑 |
| `tests/test_overlay_shell.py` | +26 / −0 | 显式锁死「门的配置路径必须在本用例临时目录内」，并在**同一份路径**写 `true` 证明判定读的就是它 |
| `tests/conftest.py` | +25 / −0 | autouse 夹具 `_isolate_topology_config`：把 `overlay_settings_command._default_base` 钉到 `tmp_path` + 清快照。**全仓所有用例自动接入**（不只本轮新增文件） |

### 文档

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `README.md` | +11 / −2 | 「保存后立即生效」→「**保存后重启桌宠生效**」；补「重启时多只桌宠收拢为主宠物（清单保留，取消勾选再重启即回来）」；新增 **已知限制**段：分层窗口下 BitBlt / 游戏捕获读不到画面（**黑屏属预期，不是没生效**），请用「Windows 10（1903 及更高版本）」模式，内容面修复另票跟踪 |
| `AGENTS.md` | +8 / −1 | 「Two render topologies」段补：拓扑判定还读持久键 `stream_capture_mode`（主配置、进程内快照一次），捕获模式 = 重启级切到 legacy 单窗，多宠收拢且清单保留 |

### 未改动（看起来相关但故意没动）

| 文件 | 为什么不动 |
|---|---|
| `pet/overlay_shell.py` 的渲染/多宠逻辑本体 | 本批只是在启动分流处**不构造它**；壳内部一行未改（多宠不复活靠"不构造"，不靠删代码） |
| 活跃宠清单 `overlay-active-pets.json` 的读写 | **保留是设计前提**（关掉开关就回来）；捕获模式不清、不写 |
| `pet/window_screen.set_stream_capture_mode` | 运行期热切换的本体保留（显式 env legacy 下仍用它）；本批只在其调用点加 restart-level 前提 |
| `pet/slot_manager.py` 的 slot 播种 | 播种逻辑未改；`--slot N` 的窗口能力改由 `effective_stream_capture_mode` 在**读取处**归并 |
| `.scratch/single-overlay-window/PHASE4_DESIGN.md` | T4 设计原文，作为本批的依据保留原样 |
| `docs/PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md` §B8 | 历史归档报告；它记录的「置灰 + 暂不支持」决策被本批推翻，按 `AGENTS.md` 的历史报告豁免**不回改**，语义变更由**本报告**承接 |

## 三、实现要点

### 3.1 两个产品决策（开工前拍板，也是本批唯一的"语义选择"）

**决策一：捕获模式下多宠收拢为主宠物，清单保留**（T4 原意，对齐 v4.2.1 行为）。
另一种选法是"保持 N 窗"——但那会让 OBS 源列表出现 N 个同名窗口，且要复活已退役的
多进程多宠层，成本与收益都反向。收拢的实现方式是**不构造 `OverlayShell`**
（多宠的唯一形态是进程内 sprite，壳不建就不复活），因此**不需要**在捕获模式里写
任何"关掉多宠"的代码；清单不删则保证"关掉开关再重启就全回来"。

**决策二：单实例门改为「两个拓扑都抢」**（双开门）。`overlay_instance_gate` 原本
只在 overlay 拓扑生效（`is_required()`），而 slot 文件锁在 Phase 4.4a/4.4b 已退役
——一旦捕获模式切到 legacy，**用户双击就会起来第二个完整实例**（v4.2.1 时代有 slot
锁兜着）。两条路：① 改门为两拓扑都抢；② 捕获模式明确放弃单实例保护并写进文档。
**选 ①**：捕获模式下的桌宠同样是完整实例（建窗、存位置、落盘配置），双开同样互踩。
实现是删掉 `is_required()` 让 `acquire_overlay_instance_gate()` 无条件建门；**锁名与
留痕名刻意不改**（跨版本稳定，改名只会留下孤儿锁）。

### 3.2 `is_overlay_topology()` 的语义变更与**爆炸半径控制**

改前：`return os.environ.get(PET_RENDER_TOPOLOGY, "").strip().lower() != "legacy"`
——**env-only**，而 `PET_RENDER_TOPOLOGY` 不进 Config / 设置页 / schema，所以对最终
用户来说"永远是 overlay"。

改后：`显式 env 优先，否则 not 主配置捕获开关`，且**按配置路径快照一次**
（`_CAPTURE_SNAPSHOT`，T5 要求"启动时定死，不做运行时切换"）。

这是一次**语义扩张**，爆炸半径靠四条控制：

1. **快照键 = 配置路径**，同一进程内改盘不翻拓扑（消除"读到一半的配置"这类竞态），
   测试用 `reset_topology_snapshot()` 清；
2. **不能直接 `Config()`**：`Config` 构造期会做 legacy 迁移 / 副槽落种（**有写盘副作
   用**），且 `pet/app.py` 的门必须在 `Config` 之前跑——所以走**直读 `config.json`**
   （`topology_config_path()` 复用 `config._default_base()/APP_DIR_NAME`，不另拼路径）；
3. **显式 env 仍压过配置**：`PET_RENDER_TOPOLOGY=legacy` 是 dev 逃生门，且该路径下
   保留原有的**运行期即时切换**语义（`capture_switch_is_restart_level()` 在这种进程里
   读 False）——开发隔离与"用户开关"两条语义因此不混淆；
4. **测试隔离推广到全仓**：`tests/conftest.py` 的 autouse 夹具把 `_default_base` 钉到
   `tmp_path` 并清快照，**所有用例**（不只本轮新增文件）都在"空临时目录"这个确定性
   输入下判定。红证据：`git stash` 掉 conftest 单文件后跑
   `tests/test_overlay_shell.py`，失败信息是
   `AssertionError: 门的配置路径必须在本用例临时目录内 … 'C:\Users\me\AppData\Roaming\dsh-pet-standalone\config.json'`
   ——即审查说的「开发机 mock 主配置 true 即红」的真实症状。

**语义现在同时决定四件事**（后续改拓扑判定必须一并回归这四处）：渲染壳、多宠复活、
手动 spawn 可用性、运行期捕获热切换。

### 3.3 审查修复六条（`142aed7`，逐条都有红证据）

两轮独立审查（6.1sol 主审 4 Major + 3 Minor + 1 Nit；A1 交叉审无 Blocker/Major）
合计报出的问题里，**六条被判定为必须修**：

| # | 问题（来源） | 修法与取舍 | 红证据（撤掉修复后的真实失败） |
|---|---|---|---|
| 1 | **子宠设置页该开关可操作但保存后重启仍不生效**（主审 Major 1）——子宠页写 `config-slot-N.json`，而拓扑只读主配置 | `pet/settings_pet_controls.py`：`config.instance_id` 非空即 `setEnabled(False)` + tooltip「仅主桌宠可设置」。**选置灰而非不渲染**：① `modern_settings_dialog.py` 有行数预算，条件化 `window_rows` 要在那里加行；② 仓库对"子宠页不能设"的既有做法就是置灰 + tooltip（可 hover 说明原因，隐藏则无声消失）；③ 主宠页两拓扑下都不受影响（双取值断言仍绿） | `assert True is False where True = ToggleSwitch.isEnabled()`（两条用例都红） |
| 2 | **捕获模式没有阻止运行期重新生成多窗**（主审 Major 2）——legacy 主窗仍无条件接线 `on_spawn_pet` | `pet/app.py:3042-3056`：`spawn_pet()` 入口在非 overlay 拓扑时记日志 + 冒泡后 `return`。**选「点击时拒绝 + 冒泡」而非「菜单项禁用」**：菜单项保留可见、点下去有解释，比灰着不说话更好；`on_spawn_pet` 接线本身没动，用户可见入口仍是同一条 | `AssertionError: 单窗形态下不得再拉进程内窗口 / assert [1] == []` |
| 3 | **`--slot N` 可能走 legacy 却仍是 OBS 枚举不到的 Tool 窗**（主审 Major 3）——拓扑取主配置、窗口能力取 slot 配置 | 新增 `effective_stream_capture_mode(window_value)`（:196）：主配置开启时返回 True 压过窗口自己那份；`PetWindow.__init__` 的有效值改走它。**不改写 slot 文件** | `assert False is True where False = PetWindow._stream_capture_mode`（主 true + slot false 时窗口连捕获旗标都没有） |
| 4 | **取消勾选会立即撤掉捕获窗口能力**，与新文案自相矛盾（主审 Minor 1） | 新增 `capture_switch_is_restart_level()`（:180）；`refresh_pet_settings` 在该条件下只记日志、**不调** `set_stream_capture_mode`；显式 env legacy 走 else 分支保持即时切换 | `AssertionError: 重启级开关不得运行期回撤 / assert False is True`（老代码把旗标当场撤了） |
| 5 | **旧拓扑契约测试受真实用户配置污染**（主审 Minor 2）——清 env 后直接断言默认 overlay | `tests/conftest.py` autouse 夹具（见 3.2 第 4 条）+ `overlay_settings_command` 的目录 seam 提到模块级 + `test_overlay_shell.py` 锁死"门的配置路径在本用例临时目录内" | `git stash` 掉 conftest 后：`AssertionError: 门的配置路径必须在本用例临时目录内 '…\AppData\Roaming\dsh-pet-standalone\config.json'` |
| 6 | **门日志/注释仍残留旧拓扑语义**（主审 Nit）——legacy 拒绝时仍记「overlay 拓扑已有实例」 | `overlay_instance_gate.py` 的 docstring 与六条日志文案、`pet/app.py:1155-1161/:2036/:2062-2070` 全部改口径；锁文件名与留痕名保留（并注明「overlay 是历史名」） | 文案类，靠 code review 复核（无行为断言） |

**主审报出但本批有意不收的一条**：`test_background_service_gates.py` 里"恢复多宠"
的对照测试只断言壳启动、不读清单（主审 Minor 3，指真实的 `_restore_spawned_pets()`
完全失效该测试仍会通过）。它的完整修法需要"开启→收拢→关闭→恢复"的**真实持久化
round trip**，属独立一条测试改造；本批保证的是"清单在捕获启动分支**没有被删**"
（`test_stream_capture_mode_boots_legacy_single_window` 断言 `[1,2]` 原样保留），
**恢复链路的端到端覆盖留给后续**（如实登记，见第七节）。

### 3.4 BitBlt 黑屏属预期行为（**Phase B 另票，README 已写明**）

**根因是勘查阶段本机实测定位的**（不是推测）：`WA_TranslucentBackground` → Qt 用
`WS_EX_LAYERED` + `UpdateLayeredWindow`（**窗口 DC 里没有内容**）→ BitBlt 读到全黑。
A/B 四臂实测（同一份红色填充的 Qt 窗，唯一差别是透明与窗旗标）：

| 臂 | 窗口旗标 | exstyle | BitBlt(窗口DC) 非黑 | `PrintWindow(full)` 非黑 |
|---|---|---|---|---|
| A 透明 | Frameless+Tool | `LAYERED=1` | **0.0%** | 100% |
| B 不透明 | Frameless+Tool | `LAYERED=0` | **100%** | 100% |
| C 透明 | Frameless+**Window**（= 捕获模式旗标） | `LAYERED=1` | **0.0%** | 100% |
| D 不透明 | Frameless+**Window** | `LAYERED=0` | **100%** | 100% |

**端到端复现**（不需要 OBS，用的是 OBS BitBlt 同一条 GDI 路径）：

```text
ffmpeg -f gdigrab -i title="dsh-pet-standalone-webm-chat" -frames:v 1 \
  -vf signalstats,metadata=print -f null -
→ YAVG=16  YMAX=16      # = 纯黑
```

（该窗口此刻在屏幕上肉眼可见；screen-DC 取同一块是 100% 非黑。）

**关键判断**：捕获模式只把 Tool 换成普通窗口，**不改变呈现方式**——所以
"接通入口"不会顺带修好黑屏。**"直播捕获兼容"从没承诺过内容面可读**，
README 的承诺只到"列表里能看到并选中它"。本批因此：

- 在 README 新增**已知限制**段，明确写"BitBlt / 游戏捕获读不到画面（黑屏属预期，
  不是没生效），请用 Windows 10（1903 及更高版本）模式"；
- 把内容面修复**另立 Phase B 票**（先做零代码甄别：让报 issue 的用户补 OBS 完整
  版本号、Win10 模式下拉里选中的窗口标题、B站直播伴侣能否正常捕获——维护者
  2026-10-05 已问、用户未回）；
- `WGC`（Win10 模式）全黑的原因**未定位**（三条候选都是弱证据），如实登记。

## 四、性能分析

**方法（可复现）**：真进程探针（offscreen + **临时 `APPDATA`**，不碰用户真实配置
目录、无任何窗口弹出）+ focused 测试族计时。
环境：Windows 10 x64 / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属 |
|---|---|---|
| `is_overlay_topology()` 首次调用 | 一次 `config.json` 直读（小文件，∝ 文件大小） | 新增（每进程一次） |
| `is_overlay_topology()` 第 2..N 次调用 | **纯 dict 命中，无磁盘 IO** | 新增（快照） |
| 启动分流（`overlay_topology = is_overlay_topology()` + 一行 `logging.info`） | 一次函数调用 + 一行日志 | 新增（每进程一次） |
| `effective_stream_capture_mode(window_value)` | 快照命中 + 一次 `bool()` | 新增（每次建 `PetWindow`，即每进程/每窗一次） |
| `capture_switch_is_restart_level()` | 快照命中（同上） | 新增（每次 `refresh_pet_settings`，即设置变更时） |
| 单实例门（`acquire_overlay_instance_gate`） | 一次文件锁获取/留痕追加；legacy 与 overlay 同一份代码路径 | 既有（本批只是**去掉拓扑前提**，成本不变） |
| 稳态开销（桌宠运行期热路径） | **零变化**：本批不触及 tick / 渲染 / 物理 / 轮询任一热路径 | 零 |
| 新的磁盘 / 网络 / 线程 / 定时器 | **无**。磁盘只有：每进程一次 `config.json` 读、门的既有文件锁与留痕、重置级设置保存时的既有原子写 | 零（新增部分） |
| 内存 | 无长驻增长：`_CAPTURE_SNAPSHOT` 是 `dict[Path, bool]`（**≤ 进程内配置路径条数**，正常为 1），无缓存容器、无长驻大对象 | 新增（可忽略） |
| 捕获模式下的窗数量 | **1**（探针实测：`实例数 1`、overlay 壳 `None`） | 新增行为 |

**结论**（逐条回答）：

1. **稳态开销有没有变化、变了多少**：**没有变化**。改动集中在**启动那一刻的
   判定**（每进程一次）与**用户交互的离散动作**（勾选保存、点「生小肥鱼」、
   改设置触发 refresh）。没有任何代码进入每 tick 或每帧路径。
2. **新增路径的绝对成本与触发频率**：`is_overlay_topology()` 首次 = 一次小文件读
   （触发频率：每进程一次）；其后 = 纯内存字典命中（触发频率：拓扑判定被调用处，
   仓库内为 `app.start()` 首次 + 共享子系统 + 设置页文案，均为启动期/低频）；
   `effective_stream_capture_mode` / `capture_switch_is_restart_level` = 快照命中
   （建窗时 / 设置变更时）。全部相对"启动一个从 DS 服务到 ffmpeg 的桌宠"可忽略。
3. **有没有引入新的系统调用 / 网络 / 磁盘 / 线程**：新增 **0** 线程、**0** 网络、
   **0** 定时器；磁盘只多了一次 `config.json` 读（每进程一次，且本来启动就要读
   配置——本批只是提前到门之后、`Config` 之前，用直读避免 `Config` 的写盘副作用）。
   **方向上的收益**：捕获模式下不再构造 `OverlayShell`（不建多宠）、不再复活多宠。
4. **内存与缓存有没有增长**：`_CAPTURE_SNAPSHOT` 是模块级 dict，**键 = 配置路径**，
   正常进程内只有 1 条；无其他缓存或长驻容器。捕获模式下少一个 `OverlayShell`
   与若干 sprite，实际内存是**下降**。
5. **测试隔离带来的额外成本**（`conftest.py` autouse 夹具）：每用例一次
   `monkeypatch.setattr` + 清 dict，纯内存操作；实测 focused 137 条连跑 3 遍结果
   一致、耗时无异常（见第六节）。

## 五、实机运行记录

本机：Windows 10 x64，真实开发机（非 CI、非 mock）。

1. **前提现场复现（旧行为真实存在，真进程 + 真 HWND）**：对正在运行的真实桌宠进程
   （pid 26584）读窗口扩展样式：

   ```text
   overlay 全屏窗 hwnd=329068  exstyle=0x080800a8 bits=[TOPMOST|TRANSPARENT|TOOLWINDOW|LAYERED|NOACTIVATE]
   很小的可见窗 hwnd=918098 exstyle=0x008080088 bits=[TOPMOST|TOOLWINDOW|LAYERED|NOACTIVATE]
   ```

   **每个 Qt 顶层窗口都挂 `WS_EX_LAYERED` 且都带 `TOOLWINDOW`** —— `TOOLWINDOW`
   在 = OBS 列表会过滤掉（这正是 issue 的原始症状）。对透明窗调
   `GetLayeredWindowAttributes` 返回 **0**（没有任何 `LWA_*` 属性）→ 内容走
   `UpdateLayeredWindow` 逐像素推送，**窗口 DC 里是空的**；对照组普通 `STATIC`
   不透明窗 BitBlt 读到 100%（证明探针本身没坏）。
2. **旧实现下的红探针**（临时探针，已删）：`RED-PROBE overlay_shell=<OverlayShell>
   instances=1 ui=[] config=True` ——即**原实现下捕获模式仍走 overlay 壳、不建
   legacy 窗**（多宠会被复活，OBS 也枚举不到）。
3. **实现后的真进程验证**（offscreen + 临时 `APPDATA`，不进用户真实配置目录，
   无任何窗口弹出）：

   ```text
   capture on ： is_overlay_topology()=False、PetWindow 存在: True、标题 'dsh-pet 桌宠'、
                 窗口类型 1 = Qt.Window（非 Tool）、overlay 壳 None、实例数 1，
                 启动日志 INFO 渲染拓扑: legacy(单窗 PetWindow)
   capture off： is_overlay_topology()=True、无 PetWindow、overlay 壳 <OverlayShell ...>
   ```

   复跑命令（源 worktree）：

   ```bash
   mkdir -p /tmp/pa && QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dsh-pet-src-wt-capture" \
     APPDATA="C:/Users/me/AppData/Local/Temp/pa" \
     python "C:/Users/me/AppData/Local/Temp/probe_capture_mode.py" on   # 或 off
   ```

4. **用户可见行为的确认**：**未做真实 GUI 目视验收**（本会话只有 headless 后端）。
   需要人眼确认的两格是：任务栏出现图标 + 标题为「dsh-pet 桌宠」；以及 OBS 窗口
   捕获列表里确实能选到它并看到画面。**人工烟测步骤见下**（第 7 条），留给合并前
   的实机点验。
5. **边界与失败路径（已自动验证）**：
   - 双开保护：legacy 拓扑下第二实例在 `AppShell` 之前被拒
     （`test_main_legacy_topology_refuses_second_instance`），锁被抢过留痕、退出后释放；
   - 捕获模式下手动「生小肥鱼」→ `spawn_in_process_window` **零调用** + 气泡文案
     （`test_capture_mode_refuses_manual_spawn`）；overlay 下同一回调照生（对照组）；
   - 子宠页该行**置灰**、点击无效、tooltip 文案正确（两拓扑各一条）；
   - 取消勾选后**窗口当场不变**（不撤捕获旗标）+ 日志出现「改动重启后生效」；
   - 坏配置（缺失/损坏/非对象/路径被目录占住）→ 判定为 overlay 且**不抛异常**。
6. **无 OBS 的等价验收手段（勘查阶段全部在本机跑通过，可固化为 `tools/win_capture_probe.py`）**：
   ① 可枚举性探针（`EnumWindows` + `GetWindowExStyle` 判 `TOOLWINDOW`/`LAYERED`）；
   ② 黑屏探针（`GetWindowDC` → `BitBlt` → `GetDIBits` 数非黑像素占比）；
   ③ WGC 类判定代理（`PrintWindow(PW_RENDERFULLCONTENT)` 同法数像素）；
   ④ 端到端一行（`ffmpeg -f gdigrab` 看 `YAVG/YMAX` 是否 16）。
   **对照组必带**：不透明非分层窗 = 100%；**离屏/隐藏窗 = 0%**（实测 `x=-4000` 与
   `hide()` 都是 0%）→「隐藏一个捕获孪生窗」这条路走不通；**被遮挡但在屏内的窗 = 100%**
   → 遮挡无害。
7. **人工烟测步骤（给 owner / 用户验收用，两轮交接口径一致）**：

   1. `python -m pet`（前台跑，可见日志）——默认应看到 `渲染拓扑: overlay(单合成窗)`。
   2. 托盘/右键 →「桌宠设置」→「窗口与系统」→「直播捕获兼容」：**开关不再置灰**
      （**子宠页该行现在是灰的**，主宠页可点），说明文字为「…重启后生效；重启时
      多只桌宠会先收拢为主宠物。」勾选 → 保存。
   3. 完全退出桌宠（托盘 → 退出；确认桌面无桌宠、任务栏无图标）后重启
      `python -m pet`。预期：日志 `渲染拓扑: legacy(单窗 PetWindow)`；任务栏出现
      图标；`WM` 标题为「dsh-pet 桌宠」；先前的多只小肥鱼不出现。
   4. 捕获模式下手动右键「生小肥鱼」→ 应冒泡「直播捕获兼容模式仅主宠物」，
      不出现第二个窗。
   5. OBS：来源 → 窗口捕获 → 模式选 **「Windows 10（1903 及更高版本）」** 或直播姬
      的对应模式 → 列表里应能选到「dsh-pet 桌宠」并看到画面。
      **预期内的失败样本（不是 bug）**：同一窗口源切到「BitBlt」/「游戏捕获」→ 黑屏
      （分层窗口限制，README 已写明，Phase B 处理）。
   6. 捕获模式下去设置页**取消勾选并保存** → **窗口当场不变**（不撤捕获旗标），
      日志出现「…改动重启后生效」；重启后回到 overlay，之前的小肥鱼应全部回来
      （活跃宠清单未被删）。
   7. 双开保护：捕获模式（legacy）下双击桌面快捷方式 → 第二实例静默退出
      （退出码 0），`<config dir>\pet-overlay-gate.log` 追加 `refused pid=...`。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | `All checks passed`（两条提交前各跑一次） |
| 空白检查 | `git diff --check` | clean |
| 受影响测试族连跑 **3 遍** | 捕获/门/设置相关文件 | **137 passed × 3**（新用例全是同步直调，无 sleep、无线程赌时序） |
| 聚焦（本报告撰写时在**整合分支**复测） | `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_overlay_settings_command.py tests/test_overlay_instance_gate.py tests/test_stream_capture_copy.py tests/test_stream_capture_window_switch.py tests/test_settings_overlay_copy.py tests/test_background_service_gates.py tests/test_overlay_shell.py` | **125 passed**（32 / 14 / 8 / 3 / 27 / 13 / 28） |
| 全量（`9f4f55d`，接通） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4326 passed, 11 skipped**（`-v` 版同数，EXIT=0。注：中间一轮在 66% 处无 summary 中断——同时段另有 pytest 进程在跑同一仓库、CPU 争用；随后重跑完整通过，无 FAILED 记录） |
| 全量（`142aed7`，审查修复后） | 同上 | **4334 passed, 11 skipped**，0 failed（较上轮 +8，正好是本轮新增用例数） |
| 真进程复核（修复后） | offscreen + 临时 `APPDATA` 探针 | `渲染拓扑: legacy(单窗 PetWindow)`、`PetWindow 存在: True`、标题 `dsh-pet 桌宠`、窗口类型 `1 = Qt.Window`（非 Tool）、无 overlay 壳 |
| 本批整合终全量 | `integration/2026-10-07-night-batch` | **4413 passed, 11 skipped** |
| 交付纪律 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr_report_discipline.py -q` | 见本文末（登记后全绿） |

**红 → 绿（test-first，两条提交各一轮）**

第一轮（`9f4f55d`，改前 `git stash` 掉 `pet/` 与 README 后跑全部受影响文件）：
**`12 failed, 46 passed, 32 errors`**，其中关键行为红：

```text
assert False is True                      # stream_capture_check.isEnabled()；点击后 isChecked() 仍 False（置灰未撤）
AssertionError: legacy / assert None is not None   # acquire_overlay_instance_gate 在 legacy 返回 None
FileNotFoundError: ...\pet-overlay-gate.log        # legacy 不建门
AssertionError: 已有实例在运行：不得建到 AppShell 这一层  # legacy 第二实例照建完整实例
```

另用临时红探针（已删）跑原代码下的启动路径：
`RED-PROBE overlay_shell=<OverlayShell> instances=1 ui=[] config=True`。
改后 focused 全绿（`90 passed`，连跑 3 遍同一结果）。

第二轮（`142aed7`，六条修复）逐条红证据见 3.3 表；改后 focused `137 passed × 3`。

**断言有效性**：3.3 表每行的"红证据"列即为变异证据——撤掉修复即红，且失败信息
指出的正是被破坏的那条语义（`assert [1] == []`、「重启级开关不得运行期回撤」、
`isEnabled()` 为假 等），不是笼统的收集期错误。第三轮（`7f1b627` / `94174f8`，
属三端线）未触及本批文件。

## 七、已知限制与后续

### 7.1 Phase A 范围外的已知限制（**发布说明要点**）

1. **BitBlt / 游戏捕获仍是黑屏**（分层窗口限制，属预期行为）。Phase A 只保证
   **可枚举 / 可选中**；内容面（呈现面）修复是 **Phase B 另票**。README 已如实写明，
   并向用户指明用「Windows 10（1903 及更高版本）」模式。
2. **WGC（Win10 模式）全黑的原因未定位**：三条候选（选错窗口 / 帧拿到了但 alpha
   处理不对 / OBS 版本与 GPU 差异）证据都不足。需要用户侧数据（OBS 完整版本号、
   下拉里选中的窗口标题、B站直播伴侣能否捕获）——维护者 2026-10-05 已问、**用户至
   今未回**。本机未安装 `winrt-Windows.Graphics.Capture`，无法自证。
3. **#231 上报者跑的是哪个构建**未确认：时间线指向 `v4.2.1`（2026-09-23，legacy、
   开关可用），而 2026-10-04 时 main 已是 overlay 且开关置灰。**这只影响叙事，不
   影响修法**。
4. **色键路线的屏幕观感未验证**：不透明窗 + `LWA_COLORKEY` 方案已验证 BitBlt
   仍 100% 可读（读到的底色是色键色），但"抗锯齿边缘出现色键描边"这一点**无法用
   探针验证，需要实机肉眼看**——这是 Phase B 若走该路线的必验项。

### 7.2 未做 / 建议跟进

1. **子宠页该行的文案仍是重启级说明**（tooltip 里才是「仅主桌宠可设置」）；若要
   hint 文案也带一句「仅主桌宠可设置」，是 1 行改动。
2. **「恢复多宠」的对照测试只断言壳启动、不读清单**（主审 Minor 3）：真实的
   `_restore_spawned_pets()` 完全失效该测试仍会通过。完整修法是"开启→收拢→关闭→
   恢复"的**真实持久化 round trip**（用例只写了清单 `[1,2]`，未创建对应 slot 配置；
   真实恢复路径会把缺身份条目摘掉）——本批**没有**做这条改造。
3. **`test_background_service_gates.py` 的清理依赖 `try...finally`**（A1 交叉审的
   观察）：目前无并发问题，但若有人启用 `pytest-xdist` 需调整为 autouse 夹具。
4. **设置页提示文案在"已重启进 legacy"后仍显示「重启后生效」**（A1 交叉审第 7 条）：
   勾选 → 重启 → 本进程已是 legacy，但设置页仍显示重启级文案。设计上是解释按钮
   作用而非状态角标，**不算错误**；若要区分"已生效 vs 未重启"，属独立改进。
5. **`legacy` 拓扑自此是严格单窗**：捕获模式与显式 env 逃生门下都不能再生小肥鱼。
   若上游有依赖 legacy 多窗的用法，需重新评估。
6. **分支未 push、PR 未开**（见文末状态）。

## 八、风险与回滚

- **影响面**：拓扑判定（`is_overlay_topology`）、启动分流、单实例门、设置页一处
  开关与一处子宠页置灰、`PetWindow` 的窗口能力位与重启级判断。
  *〔2026-10-07 终审修复对齐（`ddbea79`）：现另有**一处拓扑条件置灰**——非 overlay 下
  `drop_gravity` 置灰（捕获模式接通使 legacy 成为真实路径的同族收口），见 §9〕*
  **默认用户（未勾选捕获模式）路径逐字节不变**：默认分支上 `stream_capture_mode`
  为假 → `is_overlay_topology()` 仍返回 True（等价于旧的 env-only 结果）→ 走
  `OverlayShell`，多宠照常。
- **用户可见变化**：① 设置页该开关**不再置灰**、文案改为"重启后生效"；② 勾选并
  重启后桌面只有一个「dsh-pet 桌宠」窗口（多宠收拢、清单保留）、OBS 能枚举到它；
  ③ 该模式下「生小肥鱼」被拒并冒泡；④ 子宠页该行置灰；⑤ legacy 下双击不再能开
  第二实例。
- **配置迁移**：**无新键、无格式变更、无迁移代码**。`stream_capture_mode` 是既有键
  （默认 `False`、既有白名单），本批只是给它接了**拓扑语义**。老配置里残留的
  `true` 在升级后会**立即生效**（下次启动即走 legacy 单窗）——这是**有意的行为
  变更**（它本来就是用户勾过的意图），README 与设置页文案都已说明重启级语义。
- **回滚**：`git revert` 两个提交即可（或丢弃分支），**无落盘残留**：本批不新增配置
  键、不写新文件、不改锁名与留痕名（`overlay-instance.lock` / `pet-overlay-gate.log`
  名称刻意保留正是为了回滚干净）；活跃宠清单在捕获模式下**未被删**，所以回滚后
  多宠照常恢复。唯一残留是"用户若在捕获模式期间改过设置"这类正常配置内容。
- **风险等级与本批的门禁口径**：本批改变的是**应用生命周期分流**（属
  `AGENTS.md` 的"全量门"改动），因此走了：两轮**独立**审查（6.1sol 主审 + A1 交叉
  审，结论分别为"需修后可合"与"未见阻断性问题"）+ 六条修复 + 修复后真进程复核 +
  全量套件 + 受影响族 3 遍。整合分支终全量 **4413 passed, 11 skipped**。


## 九、终审修复对齐（2026-10-07 追加）

> 按 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) 的「后续轮次在同一文档追加新章节、
> 保留新旧对照」约定**追加**：上文正文不改，本节只记后续收口对本文叙述的影响。

### 9.1 捕获模式多了一处**拓扑条件**置灰（`ddbea79` 的 M5）

`drop_gravity`（静止放手下落，#219）只被 sprite 路径消费（`pet_sprite` /
`BehaviorController`），legacy 的 `PetWindow` **没有对应行为**。**捕获模式接通后 legacy 已是
真实用户路径**，所以 `pet/settings_pet_controls.py` 在**非 overlay 拓扑**（捕获模式，或显式
`PET_RENDER_TOPOLOGY=legacy`）下把该开关 `setEnabled(False)` + tooltip
**「仅单合成窗（overlay）拓扑生效」**（判定走 `overlay_settings_command.is_overlay_topology()`，
与本文 §一 的拓扑判定**同一判据**）。

**对本文的影响**：§八「影响面」列的「设置页一处开关与一处子宠页置灰」现在**多一处拓扑条件
置灰**。它**不是 Phase A 引入的**，而是 Phase A 把 legacy 变成真实路径之后的**同族收口**——
即本次接通带走了一条"以前不会有人踩、现在会"的死开关。

### 9.2 两个置灰维度是独立的（避免误读）

| 维度 | 判据 | 生效范围 |
|---|---|---|
| **拓扑维度**（本节） | `is_overlay_topology()` | 非 overlay（捕获模式 / 显式 env legacy）下 `drop_gravity` 置灰 |
| **子宠维度**（`ddbea79` + `a25858e` 的 `mark_main_pet_only`） | `dialog.config.instance_id` 非空 | 子宠页把进程级/全局键置灰 + 「仅主桌宠可设置」 |

两者**可同时生效**（捕获模式下的子宠页两处都会灰）。同节的**拖动物理 / 甩出力度**等
legacy **真的消费**，保持可用——刻意不"一刀切"。

### 9.3 与本文「重启级」语义的关系

该开关的可用性在**设置页构建时**按当时的拓扑求值，因此与本文 §六「取消勾选并保存 →
窗口当场不变」同属**重启级**语义：拓扑变了要**重启**才反映到这一行的可用状态。
