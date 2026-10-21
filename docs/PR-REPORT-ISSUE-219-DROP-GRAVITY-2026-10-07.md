# issue #219：静止放手下落开关（`drop_gravity`）

> **基线**：`ee699c7`（Merge PR #233 from MerZlin/feature/agent-link-subtraction）
> **分支**：`feature/issue-219-drop-gravity-toggle`　**日期**：2026-10-07
> **范围**：10 个文件（实现 5、测试 3、文档 2）
> **关联**：issue #219（用户原声：B 站评论区「静止放手下落」诉求，开关形式已获产品 owner 拍板）
> **互链**：设置变更准入/准出见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)；抛掷物理的既有调参定案见
> [`PR-REPORT-THROWN-ISLAND-PUMP-2026-09-24.md`](PR-REPORT-THROWN-ISLAND-PUMP-2026-09-24.md)；
> 报告体裁与必备章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在 [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

拖动物理打开时，松手速度低于 `physics.DEAD_ZONE_SPEED`（500 px/s）一律视为
「静止放下」——直接停住，**半空松手就停在半空**。issue 要求把它变成一个默认关闭
的开关：打开后低速松手不再停半空，而是以**零初速**进入现成的 throw 物理链路，
由重力自然落地、落地静止。

issue 原文点的是旧路径 `pet/window.py` 的 `mouseReleaseEvent`（window.py:3255-3259），
但当前默认拓扑是 overlay/sprite 世界（`PET_RENDER_TOPOLOGY` 缺省即 overlay，legacy
只是 dev 逃生门），同一语义在新路径的落点是 `PetSprite.on_release`
（`pet/pet_sprite.py:1097-1103`）。探针实测（见第五节）确认新路径**确实存在**该行为：
半空低速松手后 `interaction_state=normal`、`velocity=(0,0)`、`pos.y` 纹丝不动。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 新配置键 `drop_gravity` | 默认 `False` = 逐字节保持现状；`True` = 低速松手零初速受重力落地 |
| 2 | 设置页「拖拽与弹射」组新增「静止放手下落」 | 与「拖动物理」相邻，`commit_policy=on_finish`（关设置页统一写回） |
| 3 | 贴地松手不绕抛掷接管 | 已经贴地时走老路（原地放下），不白付一次悬空 clip 绑定 + 整池落地预热 |
| 4 | config → sprite 运行期接线 | 启动 / `refresh_settings` 热改 / 子宠 spawn 三处同步，per-slot 键 |

**红线 / 不变量**：
- 开关关闭（默认）时 `PetSprite.on_release` 的行为数与历史逐字节一致，默认路径零变化；
- 高速甩出（≥ DEAD_ZONE_SPEED）判定与初速估算完全不动；
- 贴地松手不弹跳（复用链路里靠 `GROUND_BOUNCE_STOP_VY=120` 与 8ms 子步保证）；
- legacy 拓扑路径（`pet/window.py`）按仓库政策「只修崩溃」不动。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/pet_sprite.py` | +36 / −1 | ① `__init__` 新增 `drop_gravity = False`（集成层写入，默认关=旧行为）；② 新增 `_at_ground()`：地面线 = `set_pos` 钳制域的最深下界（传 `+inf` 让既有 `_clamp_axis` 返回它的 upper，含小屏兜底），与 `ThrowPhysicsController._sprite_bounds` 的 bottom 同源（壳对 sprite 与 physics 喂同一个 bounds），容差 1px 同 `physics.is_at_rest`；③ `on_release` 低速分支改两出口：`drop_gravity and not _at_ground()` → 零初速 `THROWN`，否则维持原地放下（`NORMAL`）。 |
| `pet/config.py` | +6 / −0 | 默认值 dict（`"drop_gravity": False`）、`reload()` 白名单、`_normalize_pet_settings`（`_bool_or_default`，防手改字符串 `"false"` 被 `bool()` 误开——仓库 #129 同族规约）、`set()` 归一化名单，四处登记。 |
| `pet/overlay_shell.py` | +3 / −1 | `PER_SLOT_SETTING_KEYS` 加 `drop_gravity`（与 `drag_physics` 同级：逐 sprite 取自己那份配置，子宠缺键回退主配置、主宠提升时随 slot 带过去）；`_apply_sprite_settings_to` 下发 `sprite.drop_gravity = bool(cfg.get(...))`。 |
| `pet/settings_pet_controls.py` | +4 / −0 | 新增 `host.drop_gravity_check`（既有 `ToggleSwitch` 模式，初值读 config）。 |
| `pet/modern_settings_dialog.py` | +3 / −1 | 「拖拽与弹射」组加一个 `SettingRow("drop_gravity", …)`；域页归属 `claim("drop_gravity")` 加进同一组；`_apply`（`_save`）写回 `config.set("drop_gravity", …)`。行数 2394 → 2397（预算 2407，**未触线**）。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_sprite_physics.py` | +161 / −0 | 5 条行为用例（见第六节红→绿表）：开关开→零初速进抛掷链并落地静止；开关关→停半空（默认路径）；贴地松手→立即静止不弹跳；零初速贴地进链也不弹（复用链路的性质固定）；贴地松手不提交落地预热 / 不打飞行期 pin（含半空对照）。 |
| `tests/test_drop_gravity_toggle.py`（新） | +175 / −0 | 配置契约（默认关、set→save→重载 round trip、字符串布尔不误开）、config→sprite（启动 / 热改 / 子宠 spawn）、per-slot 逐只语义（改子宠 slot 不带跑主宠）、设置页（行存在、读初值、勾选后 `_save` 写回、与 `drag_physics` 同域页）。共 7 条。 |
| `tests/test_config_schema.py` | +1 / −0 | `RELOAD_WHITELIST_SNAPSHOT` 登记 `drop_gravity`（默认值快照由 `白名单 ∪ 特例键` 推出，随之覆盖——新增键漏登记即红）。 |

### 未改动（看起来相关但故意没动）

- `pet/window.py`（legacy 拓扑）：政策「只修崩溃」；`PET_RENDER_TOPOLOGY=legacy` 是
  dev 逃生门，该路径下开关不生效（见第七节）。
- `pet/context_menus/*`、`pet/menu_templates/*`：issue 只要设置页开关，右击菜单不加
  动作（加动作要动菜单模板/注册表/菜单布局快照，属另一件事）。
- `pet/sprite_menu_facade.py`：那里是右键菜单的 per-slot 持久化入口，本次无菜单项，
  故无 `set_drop_gravity`。

## 三、实现要点

1. **判定点选在新架构的松手协议口**：`PetSprite.on_release` 是唯一「低速 → 停半空」
   决策点（探针实测坐实），改动就落在它的低速分支；`ThrowPhysicsController` 与
   `physics.throw_step` 一行未改，落地/弹跳/静止判定全部复用。
2. **零初速而非「重力初速」**：`velocity = (0,0)` 后进 `THROWN`，位置积分由
   `sprite_physics._advance_thrown` 的 ≤8ms 子步完成——语义就是「静止放手下落」，
   不含任何甩出残余（与 issue 措辞一致）。
3. **贴地短路（与最朴素的写法不同，理由可测）**：朴素写法「开着开关就一律进
   `THROWN`」在贴地松手时会白付一次飞行接管——`BehaviorController._enter_thrown`
   绑悬空 clip 并调 `_warm_landing_idles`（后台逐条拉 ffmpeg 预热 idle 首帧 +
   打 `_ffr_landing_pinned`），而物理下一 tick 就把零初速贴地 sprite 判回静止，
   预热当即被 `_unpin_landing_idles` 摘掉。实测（第四节）GUI 线程 3 tick
   0.477ms → 1.996ms、后台多两次预热、多 3 次 clip 绑定，且中间会画一帧悬空姿态。
   故贴地这一路走老路，并用两条测试锁死（行为面 + 预热/pin 面）。
4. **不依赖 `drag_physics`（有意的取舍）**：issue 语境是「拖拽物理下」，但
   `drag_physics` 默认**关**，且拖动物理关时低速松手同样是「原地放下、半空卡住」
   （`on_release` 把初速强制归零后仍走同一分支）。若把新开关挂在 `drag_physics`
   之下，默认配置的用户打开它**什么都不会发生**（死开关）。因此 `drop_gravity`
   独立生效：拖动物理关时甩出惯性仍不生效（初速仍归零），只是「停在哪」变成
   「落到地上」。设置页文案明确写了这一条。
5. **贴地判定不另抄几何式**：`_at_ground()` 向既有 `_clamp_axis` 问「最深下界」
   （传 `+inf`），与 `throw_step` 的地板线天然同源；无 bounds 时返回 `False`
   （宁可进链也不假定已落地）。

## 四、性能分析

**方法（可复现）**：临时探针脚本（不入库，本次交付后删除）以
`QT_QPA_PLATFORM=offscreen python _probe_219*.py` 在本机运行；装配与
`tests/test_sprite_physics.py` 相同（真 `PetSprite` + 真 `ThrowPhysicsController`
+ 真 `BehaviorController`，假 clip/假钟）。
环境：Windows / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属 |
|---|---|---|
| 默认路径（开关关）低速松手成本 | 与改动前逐字节同分支：`drop_gravity` 为假时 `_at_ground()` 根本不求值（`and` 短路），0 次额外调用、0 分配 | 既有 |
| 开关开 + 半空松手落地耗时（y=100 → 地板 420，含弹跳链） | **191 tick ≈ 3.18 s**（60Hz），终态 `normal` / `pos.y=420` / `velocity=(0,0)`；同高度纯自由落体仅需 0.68s，其余是 `RESTITUTION=0.68` 的弹跳尾巴（与既有抛掷同链、同口径） | 新增（复用既有链） |
| 开关开 + 贴地松手（短路命中） | 3 tick 内：clip 绑定 3 次（与现状同）、落地预热提交 **0** 次、GUI 线程 **0.477 ms** | 新增 |
| 朴素写法（贴地也进 THROWN）对照 | 3 tick 内：clip 绑定 **6** 次（多绑悬空 clip + 落地回待机再绑 idle）、落地预热提交 **2** 次（后台 ffmpeg）、GUI 线程 **1.996 ms** | 被否决的备选 |
| `_at_ground()` 单次成本 | 一次 `_clamp_domain()`（含可能的 body 几何 memo 命中）+ 一次 `_clamp_axis`，纯浮点、无分配；只在「开关开 + 低速松手」这一离散事件上调用 | 新增 |

**结论**：① 稳态开销零变化——默认关时该改动在运行期完全不参与（唯一新增是一个
布尔字段与一次短路求值）；② 新增路径只在「开关开 + 低速松手」这个离散用户动作上
触发，绝对成本 = 一次贴地判定（浮点级），随后复用既有抛掷物理；③ 未引入任何新的
系统调用/网络/磁盘/线程：贴地短路反而是**减少**后台 ffmpeg 预热提交（每次贴地
松手省 2 次）；④ 内存无增长（1 个实例布尔字段 + 0 缓存）。半空下落那 3.18s 的
弹跳尾巴是复用既有抛掷链的固有形态，未调参（`RESTITUTION`/`GROUND_BOUNCE_STOP_VY`
都是既有定案值，见 [`PR-REPORT-THROWN-ISLAND-PUMP-2026-09-24.md`](PR-REPORT-THROWN-ISLAND-PUMP-2026-09-24.md)）。

## 五、实机运行记录

**本机真实进程、headless 后端**（`QT_QPA_PLATFORM=offscreen`，真 `PetSprite` /
真物理控制器 / 真行为控制器，非 mock）。四段探针原始输出（脚本临时生成，交付后
删除；等价断言已固化进第六节的测试）：

```text
=== 探针 1：现行架构低速松手（drag_physics=True，半空） ===
state = normal | velocity = QPointF(0.000000, 0.000000) | pos.y = 100.0     ← 坐实「停半空」在新路径存在
=== 探针 2：零初速 THROWN 贴地（py == FLOOR_Y）===
after 1 tick: state = normal | vel = QPointF(0, 0) | pos.y = 420.0 | FLOOR_Y = 420   ← 贴地不弹、一 tick 静止
=== 探针 3：零初速 THROWN 半空 → 重力落地（tick 计数）===
ticks = 191 | wall ≈ 3.183 s | final state = normal | pos.y = 420.0 | vel = QPointF(0, 0)
=== 探针 4：贴地进 THROWN 的弹跳核查（逐 tick 轨迹）===
trace(y, vy, state) = [(420.0, 0.0, 'normal'), (420.0, 0.0, 'normal'), (420.0, 0.0, 'normal')]
--- A：现状（贴地松手 = normal） ---  clip 绑定 = ['act1','act1','idle1']  预热 0  GUI 0.477 ms
--- B：朴素写法（贴地也进 THROWN） --- clip 绑定 = ['drag1','idle1','idle2','idle1','idle2','act1']  预热 2  GUI 1.996 ms
--- C：半空进 THROWN（真下落，对照） --- pin = {'idle1': True, 'idle2': True}  预热 0（本次窗口内未提交）
```

**用户可见行为**：本次改动**未做真实 GUI 目视验收**——本会话只有 headless
后端，未启动桌宠窗口、未在真实桌面上拖拽。原因与残留风险如实登记在第七节；
需要人眼确认的两条（半空松手看到宠物落下、贴地松手看到原地不动）留给合并前的
实机点验：打开设置 → 桌宠 → 拖拽与弹射 → 勾「静止放手下落」→ 保存 →
把宠物拖到屏幕中部松手（应落到屏幕底）→ 再拖到底部松手（应原地不动、不弹跳）。

**边界与失败路径（已自动验证）**：`drop_gravity` 关时半空松手仍停半空
（`test_drop_gravity_off_slow_release_stays_in_the_air`）；手改 `config.json` 写入
字符串 `"false"` 不会把开关误开（`test_drop_gravity_toggle.py`）；sprite 未挂
活动区（无 bounds）时 `_at_ground()` 返回 `False`、走抛掷链而不是假定落地。

## 六、测试与验证

**红→绿（先写测试、后写实现）**

| 用例 | 写实现前 | 实现后 |
|---|---|---|
| `test_drop_gravity_slow_release_falls_to_ground`（开关开→零初速进 thrown→落地静止） | **红**：`assert 'normal' == 'thrown'` | 绿 |
| `test_drop_gravity_off_slow_release_stays_in_the_air`（开关关→停半空） | **红**：`AttributeError: 'PetSprite' object has no attribute 'drop_gravity'` | 绿 |
| `test_drop_gravity_grounded_slow_release_rests_without_bounce`（贴地→立即静止不弹跳） | 绿（现状本就是「立即静止」，它是**防回退**用例） | 绿 |
| `test_grounded_drop_skips_thrown_capture_and_landing_warm`（贴地不白付飞行接管） | 绿（同上，防回退） | 绿 |
| `tests/test_drop_gravity_toggle.py` 全 7 条 | **红**（6 failed：无该 config 键 / 无该 sprite 字段 / 无该设置行；后补的 per-slot 用例随实现已绿） | 绿 |
| `test_config_schema.py::test_reload_whitelist_snapshot_matches_current` | **红**（快照未登记新键） | 绿 |

**一条时序教训（本轮踩到并修正）**：`test_grounded_drop_skips_thrown_capture_and_landing_warm`
第一版用「数 `warm_calls`」验证起飞预热，单跑绿、**全量跑红**——预热提交在
`_WARM_EXECUTOR`（max_workers=1，整个测试会话共享）里异步执行，全量套件里队列
常排着别的用例的预热，断言数到的是「队列进度」而不是「有没有提交」。修正为
`monkeypatch` 掉 `_WARM_EXECUTOR.submit` 直接记录提交载荷（同步、与 worker 进度
无关），既去掉了时序赌注，也不再真跑 ffmpeg。复现方式：先用 `threading.Event`
占住单 worker 再跑该用例——修正前必红、修正后必绿（已实测两遍）。

**断言有效性（临时注入缺陷，证明用例能区分新旧实现）**：把实现临时改成朴素写法
（`if self.drop_gravity:`，即贴地也进 THROWN）后重跑——

```text
FAILED test_drop_gravity_grounded_slow_release_rests_without_bounce   ('thrown' == 'normal')
FAILED test_grounded_drop_skips_thrown_capture_and_landing_warm       state_of → 'thrown'
2 failed, 2 passed
```
还原实现后 27 passed。即两条「防回退」用例确实钉住了贴地短路。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | All checks passed! |
| 聚焦 | `pytest -q tests/test_sprite_physics.py tests/test_drop_gravity_toggle.py tests/test_config_schema.py tests/test_overlay_sprite_settings.py tests/test_architecture.py tests/test_settings_interaction_tabs.py tests/test_settings_and_resources.py` | 95 passed |
| 受影响面 | 追加 `test_desktop_pet_features.py / test_overlay_window.py / test_overlay_shell.py / test_overlay_dead_switches.py / test_pet_sprite*.py / test_overlay_per_slot_settings.py / test_sprite_menu_facade.py` | 211 passed（1 既有 DeprecationWarning） |
| 全量（第一轮，发现 1 条新用例的时序赌注见下） | `QT_QPA_PLATFORM=offscreen python -m pytest -q --basetemp=C:/pt219b` | 1 failed / 4319 passed / 11 skipped（唯一红项是本轮新增用例，修正后 ②） |
| 全量（第二轮，修正后） | `QT_QPA_PLATFORM=offscreen python -m pytest -q --basetemp=C:/pt219c` | **4321 passed, 11 skipped, 0 failed**（527.19s；231 warnings 全为既有 DeprecationWarning） |
| 行数预算 | `tests/test_architecture.py::test_modern_settings_dialog_py_line_budget` | 2397 ≤ 2407，**未触线、未校准预算** |

## 七、已知限制与后续

1. **未做真实 GUI 目视验收**（见第五节）：本会话无桌面后端。需要人眼确认的是
   观感而非逻辑（落下过程、落地静止），逻辑面已有行为 5 条 + 配置/设置/per-slot
   7 条自动化用例。
2. **legacy 拓扑不生效**：`pet/window.py` 的 `mouseReleaseEvent`（:3255-3259）
   按政策「只修崩溃」不动，`PET_RENDER_TOPOLOGY=legacy`（dev 逃生门）下开关无效。
   默认拓扑是 overlay，故不面向用户提示；若将来 legacy 复活需补这条等价分支。
3. **半空下落会带弹跳**：复用既有抛掷链（`RESTITUTION=0.68` /
   `GROUND_BOUNCE_STOP_VY=120`），满屏高度下落约 8 次弹跳、数秒才静止——这是
   既有抛掷的调参定案（[`PR-REPORT-THROWN-ISLAND-PUMP-2026-09-24.md`](PR-REPORT-THROWN-ISLAND-PUMP-2026-09-24.md)），本次
   不另调参。若产品希望「静止放下」是不弹的软落地，需要单独设计（会与抛掷手感
   解耦，属新需求）。
4. **右击菜单无入口**：只在设置页（issue 范围）。

## 八、风险与回滚

- **影响面**：默认关 → 未打开该开关的用户零变化（分支短路在 `drop_gravity` 上，
  关时连贴地判定都不求值）；打开后才改变低速松手去向。
- **配置迁移**：全新键，老配置无此键 → 取默认 `False`；无旧键/旧入口需要处理。
  手改脏值（字符串布尔）由 `_normalize_pet_settings` 收口。
- **回滚**：`git revert` 即可，无落盘残留（config 里的多余键会被 `Config.data`
  忽略；已打开过开关的用户回滚后该键退化为无害未知键，行为回到「停半空」）。

## 九、设置变更记录（对照 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)）

### 9.1 准入（6 条）

| 准入条目 | 结论 |
|---|---|
| 它是偏好 | ✓「静止放手的去向」是长期行为偏好，不是一次性命令 |
| 低频且跨任务 | ✓ 设一次长期有效，无需在交互中频繁切换 |
| 有可靠默认值 | ✓ 默认关 = 现行行为（争议行为不做默认变更） |
| 归属唯一 | ✓ 桌宠域 / 拖拽与弹射组（`claim("drop_gravity")`，与 `drag_physics` 同行分组） |
| 值得让用户决策 | ✓ 两种手感都合理，产品无法推断；issue 已由产品 owner 拍板做开关 |
| 契约完整 | ✓ 见 9.2 |

### 9.2 准入记录

```text
setting_id             drop_gravity
domain_id / group_id   桌宠 / 拖拽与弹射
title / description    静止放手下落 / 松开鼠标时若几乎没动（速度低于甩出死区），宠物不再停在半空，
                       而是以零初速受重力自然落下、落地静止。贴地松手不弹跳；与「拖动物理」无关：
                       关掉拖动物理时甩出的惯性仍不生效。
search_aliases         无（设置页搜索按行标题与标签文本匹配，无需额外别名）
default                False（= 现状，行为零变化）
capability_requirement 无（纯本地物理，无服务/权限依赖）
platform_availability  Windows / macOS / Linux 一致，无平台分支
disclosure_level       primary（与「拖动物理」同组同级）
dependency             无显隐依赖（刻意不挂 drag_physics 之下，见第三节第 4 条——挂在下面会成死开关）
preview_target        无专用预览（桌面拖拽即真实生效）
commit_policy          on_finish（关闭设置页统一写回，与同组各键一致）
migration              全新键：老配置无此键 → 默认 False；无旧键/旧入口需要迁移
recovery               不想用就关回默认（行为逐字节还原）；脏值（字符串布尔）由归一化收口到 False/True
```

### 9.3 准出（5 大项）

1. **契约** ✓ 见 9.2；失败路径有默认值与安全入口（关掉即回现状），不影响设置页可用性。
2. **TDD** ✓ 先红后绿（第六节）：默认值、持久化 round trip、config→sprite 同步、
   子宠 spawn、设置页往返、脏值归一化、行为面 5 条全部覆盖。
   不适用：迁移（全新键）、平台 capability matrix（无平台差异）、深链（无此机制）。
3. **布局与可访问性** —— **视觉项未做**：新行沿用既有 `SettingRow` + `ToggleSwitch`
   （与相邻「拖动物理」同构，键盘/焦点/主题继承），行文案较长会正常换行；三档宽度、
   放大字体、High DPI 的核验未做（本会话无 GUI 后端，原因见第五节）。行归属有
   自动化断言（不落「待分类（开发期）」、与 `drag_physics` 同域页）。
4. **跨平台** ✓ 纯本地逻辑 + 键盘/主题继承，无平台分支代码；真实 GUI 验收仅
   本机 Windows headless（如实声明，mac/Linux 未跑）。
5. **视觉与文档** ✓ 本次更新 [`INDEX.md`](INDEX.md) 登记；未改 Shared UX Contract /
   Settings System 模型 / Menu Action Model，`CONTEXT.md` 无需更新（组内新增同构控件）。
