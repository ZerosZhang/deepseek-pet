# issue #208：免打扰模式（四档时长、暂存队列、全屏联动）

> **基线**：`95bd2f3`（merge #210 回收内存）；本提交经 `589d25f` 并入 integration
> **分支**：`feature/issue-208-quiet-mode`　**提交**：`c90a7d1`　**日期**：2026-10-07
> **范围**：23 个文件（实现 16、测试 6、文档 1），净 `+1276 / −5`
> **关联**：issue #208；菜单项与 #210 并序（`quiet_mode` → `memory_trim`）
> **互链**：设置准入/准出见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)；术语
> **Quiet Mode** 已按该文档 §5 写入 [`../CONTEXT.md`](../CONTEXT.md)；气泡门禁契约见
> [`PR-REPORT-FLIGHT-BEH-BATCH-2026-09-27.md`](PR-REPORT-FLIGHT-BEH-BATCH-2026-09-27.md)；
> 必备证据章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在
> [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

给桌宠加一个**进程级**的免打扰：右键 →「免打扰」→ 选 15/30/60/120 分钟（30 为默认档），
期间**普通提醒**不冒泡、不弹系统通知，而是进一个**有界暂存队列**；到点或「提前结束」时
用**一条**气泡汇报暂存内容（`免打扰期间有 N 条提醒：…`）。全局全屏播放时也等效进入免打扰
（可关：`quiet_also_on_fullscreen`）。 *〔2026-10-07 终审修复对齐（`87e9adb`）：汇报改为
**交付确认制**（有交付目标才排空，否则保留暂存重试）→ §9.2〕*

关键设计取舍：**免打扰只压「普通提醒」这一个语义类别**。审批 / 提问 / interaction /
lifecycle / turn·end / task_complete / execution-failed / agent·request-error / session·end /
balance 这些**状态类**事件一律穿透（免打扰期间该批的还是照批）；自言自语 / 点击台词 /
联动状态气泡 / 歌词 / 音频也不压——否则桌宠会变成「点了没反应」。这条边界写成了显式真值表
并用 15 条断言锁死。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 四档时长 | `15 / 30 / 60 / 120` 分钟，档位唯一来源 `QUIET_MINUTE_CHOICES`；子菜单标题带剩余时间（`免打扰 · 剩余 14:58`） |
| 2 | 暂存队列 | `QUIET_QUEUE_LIMIT = 20` 条短文本的有界 deque；**免打扰开启前已入队的普通提醒一并转存** |
| 3 | 全屏等效 | `quiet_also_on_fullscreen`（默认开）复用既有「全屏时自动隐藏」探针，不另起第二套检测 |
| 4 | 到期/提前结束汇报 | 到点自动结束并汇报；菜单「提前结束（剩余 …）」在未开启时置灰（菜单结构不随状态变形） |
| 5 | 进程级共享 | `shared_quiet_state()` 单例 + `SharedSubsystems.quiet`，多宠共享一份状态；ticker 只在免打扰生效期间以 1Hz 运行 |
| 6 | 设置页两行 | 默认档位 + 全屏联动开关，落在「自动化与联动」域 |

**红线 / 不变量**：
- `window_alerts.bubble_blocked` 契约**不得**把免打扰包进去（否则连点击台词一起压掉，表现为
  「点了没反应」）——`window_alerts.py` 的 docstring 已把这条写成纪律；
- 状态类事件（审批/提问/interaction/lifecycle/…）在免打扰期间**必须照常上屏且按钮可点**；
- 免打扰关闭时全部通道回到改动前的逐条行为；ticker 不在生效期外运行（空闲零开销）；
- `_release_qt_lifetimes` 必须纳入 `subs.quiet`（漏了会有解释器退出期 Qt 生命周期风险）。

## 二、修改文件说明

`git log --numstat c90a7d1`：

```
13	0	CONTEXT.md
6	0	pet/app.py
40	0	pet/config.py
2	0	pet/context_menus/legacy.py
6	0	pet/context_menus/registry.py
65	0	pet/context_menus/shared.py
6	0	pet/festival_service.py
1	0	pet/menu_templates/modern-default-v1.json
4	0	pet/modern_settings_dialog.py
23	1	pet/multi_window_shared.py
5	0	pet/overlay_shell.py
8	0	pet/proactive.py
292	0	pet/quiet_mode.py
94	0	pet/settings_quiet.py
9	0	pet/todo_reminder.py
5	0	pet/voice_chime_service.py
93	0	pet/window_alerts.py
7	0	tests/conftest.py
4	1	tests/test_architecture.py
2	0	tests/test_config_schema.py
1	0	tests/test_desktop_pet_features.py
7	1	tests/test_menu_layout.py
604	0	tests/test_quiet_mode.py
```

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/quiet_mode.py`（新） | +292 / −0 | 进程级纯状态机：`QuietState`（倒计时/档位/暂存队列 + 全屏等效标志，**注入时钟**可无 sleep 测试）、`QuietTicker`（QObject + 1Hz QTimer，**只在免打扰生效期间运行**）、`shared_quiet_state()` 单例。多宠共享一份 → 抑制天然是进程级的。 |
| `pet/settings_quiet.py`（新） | +94 / −0 | 设置页「免打扰」两行的控件 / 行装配 / 保存（与 `settings_music` / `settings_file_interpret` 同口径；因行数预算独立成模块）。 *〔2026-10-07 终审修复对齐（`ddbea79`）：+4 / −1，两键在子宠页置灰 → §9.1〕* |
| `pet/window_alerts.py` | +93 / −0 | 新增 `quiet_blocked(host)`（唯一判据转发 + 取配置）、`defer_quiet(text)`（入暂存队列）、`report_quiet_summary(host, items)`（一条气泡汇报）；`show_alert` 在 `isVisible()` 判定**之前**按 `alert_survives_suppression` 分流——**放在可见性之前是刻意的**：全屏避让会藏起桌宠，先走「不可见」分支就把提醒丢掉/改道了，暂存队列永远收不到东西；`pump_alerts` 把免打扰前已入队的普通提醒一并转存。顶层 `from . import quiet_mode`。 |
| `pet/config.py` | +40 / −0 | `QUIET_MINUTE_CHOICES=(15,30,60,120)` / `DEFAULT_QUIET_MINUTES=30` / `DEFAULT_QUIET_ALSO_ON_FULLSCREEN=True` / `QUIET_QUEUE_LIMIT=20` + `normalize_quiet_minutes()`（档位**唯一来源**，菜单/设置页/倒计时共用，避免两处漂移）；新键 `quiet_minutes_default` / `quiet_also_on_fullscreen` 进默认值 dict、reload 白名单、`set()` 归一化名单、`_normalize_pet_settings`（档位取最近档、布尔防 `"false"` 误开）。 |
| `pet/context_menus/shared.py` | +65 / −0 | `add_quiet_mode_menu()`：子菜单标题（开启时带剩余时间）、四档（标「默认」/「进行中」）、「提前结束（剩余 …）」（未开启置灰）；`end_quiet_mode(pet)` 提前结束并汇报。 |
| `pet/context_menus/registry.py` | +6 / −0 | `quiet_mode` action（无能力判定，两个宿主都可用）+ 标签/图标。 |
| `pet/context_menus/legacy.py` | +2 / −0 | legacy 扁平布局接上（`icons=False`，与既有约定一致）。 |
| `pet/menu_templates/modern-default-v1.json` | +1 / −0 | 默认布局加 `quiet_mode` 根节点（`todo_panel` 之后）；`merge_default_menu_actions` 自动把它插进老用户已保存的布局，无需迁移。 |
| `pet/multi_window_shared.py` | +23 / −1 | `SharedSubsystems` 持 `QuietTicker`，结束时经 `MultiWindowProxy` 汇报到首个可见窗；`stop_all()` 停表；`_release_qt_lifetimes` 纳入 `subs.quiet`。 |
| `pet/app.py` | +6 / −0 | `_on_shared_fullscreen` 广播时通知免打扰——放在按 `auto_hide_fullscreen` 的逐窗过滤**之前**（`quiet_also_on_fullscreen` 是独立偏好）。 |
| `pet/overlay_shell.py` | +5 / −0 | overlay 侧全屏回调同样通知（两条拓扑共用同一判据，不另起探测）。 |
| `pet/festival_service.py` / `pet/voice_chime_service.py` / `pet/todo_reminder.py` / `pet/proactive.py` | +6 / +5 / +9 / +8 | 四个「普通提醒」生产者在各自**降级链之前**过 `quiet_blocked`：不冒、进暂存队列。 |
| `pet/modern_settings_dialog.py` | +4 / −0 | 只接线：import 1 + 小节行 1（+注释 1）+ 保存回写 1。控件/行/保存全在 `settings_quiet`。 |
| `CONTEXT.md` | +13 / −0 | 新增 **Quiet Mode** 术语（[`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) §5：改变 Shared UX Contract 时更新）。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_quiet_mode.py`（新） | +604 / −0 | 45 例：纯逻辑、抑制真值表、菜单、设置页、进程级广播、真实事件循环（含到期自动结束与 ticker 汇报）。 |
| `tests/conftest.py` | +7 / −0 | 逐用例复位进程级免打扰单例（同 `mem_debug` / `webm_clip` 的收口纪律）。 |
| `tests/test_architecture.py` | +4 / −1 | 行数预算 2415 → **2419**（本次 +4 行纯接线）。 |
| `tests/test_config_schema.py` | +2 / −0 | 两份快照加 2 键。 |
| `tests/test_menu_layout.py` / `tests/test_desktop_pet_features.py` | +7 / −1 / +1 / −0 | 根菜单清单 + 渲染顺序断言同步。 |

### 未改动（看起来相关但故意没动）

- `pet/window.py`（legacy 拓扑）：免打扰走的是共享子系统 + 菜单建造器，两条拓扑共用，
  legacy 窗口内一行未改。
- 音频通道（报时朗读、节日朗读）：免打扰**只压气泡与同一条提醒的系统通知**，不压用户显式
  开启的持续音/朗读（见第七节）。〔2026-10-08 口径变更：**报时与节日语音改为免打扰期间静音**，
  见 3.3；点击自言的交互应答语义不变〕
- 歌词气泡：不在本门控范围。

## 三、实现要点

### 3.1 抑制判定真值表（判定顺序即语义边界）

| 事件 / 通道 | 判据 | 免打扰关 | 手动免打扰 | 全屏+开关开 | 全屏+开关关 |
|---|---|---|---|---|---|
| 普通提醒（watchdog 卡住 / 硬失败）`show_alert` | `alert_survives_suppression=False` | 上屏 | **暂存** | **暂存** | 上屏 |
| 免打扰前已入队的普通提醒 | 同上 | 上屏 | **转存暂存** | **转存暂存** | 上屏 |
| 审批 / 提问 / interaction / lifecycle / turn·end / task_complete / execution-failed / agent·request-error / session·end / balance | `alert_survives_suppression=True` | 上屏 | **上屏（含按钮）** | **上屏** | 上屏 |
| 待办提醒 / 节日提醒 / 报时气泡 / 识屏答复 | `quiet_blocked` | 上屏 | **暂存**（同一条系统通知一并压住） | **暂存** | 上屏 |
| 识屏先兆「让我看看……」 | 不判 | 上屏 | 上屏 | 上屏 | 上屏 |
| 自言自语 / 点击台词 | `bubble_blocked`（**不含**免打扰） | 上屏 | **上屏** | 上屏 | 上屏 |
| 联动状态气泡 | `show_bubble` 直发 | 上屏 | **上屏** | 上屏 | 上屏 |
| 歌词气泡 / 音频（报时朗读、节日朗读） | 不判（气泡）；语音见 3.3 | 照旧 | **语音静音**（3.3） | **语音静音**（3.3） | 照旧 |

### 3.3 口径变更（2026-10-08）：免打扰期间语音也静音

首发口径是「免打扰只压气泡，不压用户显式开启的朗读」；产品随后拍板改为**免打扰（含全屏
等效）期间不出声**。落地在音频通道 `pet/voice_chime_service.py` 的同一道闸（`_quiet_muted`，
判据仍是 `window_alerts.quiet_blocked` → `quiet_mode`，不新增第二套判定）：

- 报时语音与节日语音（`_fire` 合成入口 / `_handle_synthesized` 回放出口）**丢弃，不补播**——
  语音是时间敏感的（14:00 的报时 15:00 再响没有意义），与气泡「攒着退出后统一汇报」刻意不同；
  预合成一并跳过（省一次 TTS 网络请求）。
- **气泡语义逐字不变**：仍走 `defer_quiet` 进暂存队列。
- **点击自言自语（含预缓存台词）是交互应答，不受影响**：调用侧 `speak(..., respect_quiet=False)`
  显式豁免，与上表「自言自语 / 点击台词」一行同口径。

### 3.2 三个关键取舍

1. **分流点在 `show_alert` 的可见性判定之前**：全屏避让会藏起桌宠，若先走「不可见」分支，
   提醒会被丢掉或改道，暂存队列永远收不到东西。把免打扰分流提到可见性之前，才让「全屏 +
   免打扰」这个组合真正把提醒存住。
2. **状态类事件穿透是刻意的**：免打扰的语义是「别打扰我，但别耽误我批事」。若把审批/提问
   也压住，用户会错过需要交互的请求——那不是免打扰，是失联。
3. **全屏判定复用既有探针**：`quiet_also_on_fullscreen` 不再起第二套全屏检测，它挂在
   「全屏时自动隐藏」的广播上（该开关关掉时全屏探测不跑，本项也就随之不生效；设置页 hint
   已如实写明）。代价是一个显式依赖，收益是零重复探测。

## 四、性能分析

**方法（可复现）**：`python -c` 热路径微基准（预热后 20 万次均值），配合
`QT_QPA_PLATFORM=offscreen python -m pytest -q` 全量计时。
环境：Windows / Python 3.13.7 / PySide6 6.11.2，单进程桌宠。

| 指标 | 实测 | 归属 |
|---|---|---|
| `quiet_blocked(host)` 单次判定 | **0.42 µs**（预热后 20 万次均值） | 新增 |
| 门控调用频率 | 等于提醒/气泡**事件本身**的频率（分钟级），非每帧 | 新增（离散） |
| `QuietTicker` 轮询成本 | 1Hz QTimer，**只在免打扰生效期间存在**；未生效时不建表、不跑。 *〔2026-10-07 终审修复对齐（`87e9adb`）：结算未确认交付期间**继续跑**（重试到有交付目标），存活区间 = 免打扰窗口 ∪ 待交付窗口 → §9.2〕* | 新增（仅生效期） |
| 空闲（免打扰关）稳态开销 | 零——唯一新增是两次 `Config.get` 判空与一个布尔短路 | 既有路径不变 |
| 暂存队列内存 | 有界 deque，上限 **20** 条短文本（`QUIET_QUEUE_LIMIT`） | 新增（有界） |
| 新增线程 / 网络 / 磁盘 / 系统调用 | **0 / 0 / 0 / 0**（ticker 是 Qt 定时器，不是线程） | — |

**结论**：① **稳态开销零变化** —— 免打扰关闭时该功能在运行期完全不参与（唯一新增是
事件入口的一次微秒级判空）；② **新增路径只在离散的提醒/气泡事件上触发**，0.42 µs/次，
相对于冒一次气泡本身（毫秒级绘制）可忽略；③ **未引入任何新的系统调用/网络/磁盘/线程** ——
全屏联动复用既有广播，不另起探测；④ **内存只多一个有界 deque（≤20 条短文本）**，
无缓存增长。

## 五、实机运行记录

**主代理本机验收（真实桌面、真实进程、真实鼠标输入驱动的产品实例）**：

- **用户可见行为确认（逐条照用）**：#208 生产实例**右键 →「免打扰」→「15 分钟」→ 重开菜单
  显示「免打扰 · 剩余 14:58」→「提前结束」→ 恢复**，全程由**真实鼠标输入驱动**。
  即：① 菜单档位选择生效；② 子菜单标题的剩余时间在真实进程中按秒递减并正确渲染；
  ③ 「提前结束」入口在生效期由灰变可点、点击后立即结束免打扰。

**根因/前提的现场复现**：本轮是新增功能，无「修复前症状」可复现；等价的前置证据是红→绿
切片——**仅在保留新模块与 config 的前提下回退全部接线**，15 条行为断言转红（见第六节），
证明「菜单入口 / 暂存队列 / 全屏联动 / 设置行 / 汇报面」确实是本次新加的行为，而非既有能力。

**边界与失败路径（实机/自动已验证）**：

- 免打扰期间触发一条 DSH 审批/提问 → 审批气泡**照常出现、按钮可点**（真值表第 3 行）；
  点桌宠 → 仍会回应台词（`bubble_blocked` 不含免打扰）。
- 免打扰前已入队的普通提醒，在免打扰开启后被 `pump_alerts` 转存而非丢弃。
- 到期自动结束（15 分钟档）手点验证成本高，由真实事件循环 + 假钟的
  `test_expiry_ends_quiet_and_returns_queued_once` 与
  `test_ticker_reports_queued_alerts_when_quiet_expires` 覆盖；实机可按需等满 15 分钟。

**无法自动验证的能力（如实登记）**：**未做设置页截图**，也未验证三档宽度/放大字体/High
DPI 下的换行；原因与残留风险见第七节。免打扰设置的视觉项（两行在「自动化与联动」页的
排布观感）需要人眼确认。

**一次需要报备的旁支**：过程中发现 3 个并发的僵尸 pytest（一次被误判为「仍在跑」的全量
运行 + 两个已打印 summary 却不退出的残留），全部 kill；收工前 `pytest` 进程数 = 0，
**用户桌宠进程全程未触碰**。

## 六、测试与验证

> *〔2026-10-07 终审修复对齐（`87e9adb`）：本节的用例清单与计数已过期，增量见 §9.3——
> `tests/test_quiet_mode.py` +372/−16（45 → 57 例）〕*

**红 → 绿（先写测试、后写实现）**

回退命令（保留新模块与 config，避免整体 import 失败掩盖信号）：

```text
git stash push -- pet/app.py pet/context_menus pet/festival_service.py pet/menu_templates \
  pet/modern_settings_dialog.py pet/multi_window_shared.py pet/overlay_shell.py pet/proactive.py \
  pet/todo_reminder.py pet/voice_chime_service.py pet/window_alerts.py
```

```text
$ pytest tests/test_quiet_mode.py -q
15 failed, 30 passed in 3.58s
FAILED test_alert_truth_table_by_event_type[watchdog-False]      # 普通提醒没被拦下
FAILED test_fullscreen_equivalent_queues_ordinary_alert
FAILED test_quiet_drains_preequed_ordinary_alerts
FAILED test_report_quiet_summary_uses_one_bubble                  # 无汇报面
FAILED test_end_quiet_mode_reports_and_clears
FAILED test_quiet_menu_* / test_default_duration_setting_*        # 无菜单入口
FAILED test_both_window_menu_paths_expose_quiet_entry[legacy/modern]
FAILED test_overlay_facade_host_can_build_quiet_menu
FAILED test_legacy_menu_entry_is_a_submenu_with_durations
FAILED test_appshell_fullscreen_broadcast_flips_quiet            # 全屏不联动
FAILED test_settings_rows_live_in_automation_domain_and_round_trip # 无设置行
```

`git stash pop` 后：**148 passed in 18.41s**（含 `test_quiet_mode` / `menu_layout` /
`config_schema` / `architecture`）。红了的是**接线**；绿的 30 例是纯状态机与 config 层
（新模块，无「改动前」基线可比）。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | All checks passed |
| 空白检查 | `git diff --check` | 干净 |
| 聚焦 | `pytest tests/test_quiet_mode.py -q` | **45 passed** |
| 聚焦（族） | 加 `menu_layout / config_schema / architecture` | 148 passed |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4466 passed, 11 skipped, 232 warnings in 681s**（EXIT=0） |
| 集成全量（当晚最终树） | 同上（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

## 七、已知限制与后续

> *〔2026-10-07 终审修复对齐（`87e9adb`）：新增一条——汇报依赖「有交付目标」，
> 详见 §9.4〕*

1. **全屏联动依赖既有开关**：`quiet_also_on_fullscreen` 复用的是「全屏时自动隐藏」的探针；
   该开关关掉时全屏探测不跑，本项也就不生效。设置页 hint 已如实写明这条依赖，**没有另起
   第二套全屏检测**。
2. **音频不压**：免打扰只压气泡与「同一条提醒的系统通知」；语音报时朗读、节日朗读、歌词
   照旧——用户显式开启的持续音/常驻展示不在此列（`voice_chime_show_bubble` 本就与声音解耦）。
   若产品要连声音一起静，需要另开一刀（涉及音频通道排队语义）。
3. **两处待产品拍板的口径**（均按 issue 规格实现，可一行回退）：
   - **自言自语/点击台词穿透**：按「状态类事件一律穿透」字面实现（`bubble_blocked` 不含
     免打扰）。若其实想压掉，改 `window_alerts.bubble_blocked` 一处即可，但会连带压掉点击回应。
   - **到期自动结束**只有假钟 + 真实事件循环的自动化证据，未做「等满 15 分钟」的真机长跑。
4. **未做视觉验收**：设置页「免打扰」两行的三档宽度 / 放大字体 / High DPI 未核验（本会话
   无 GUI 截图能力）；行归属有自动化断言（不落「待分类（开发期）」）。
5. **行数预算**：`modern_settings_dialog.py` 2415 → **2419**（本次 +4 行纯接线，按仓库既有
   约定带日期注释校准）。后续分支若叠加越线，按合并后的实测值再校准，**不要压行**。

## 八、风险与回滚

- **影响面**：默认（不开启免打扰）下用户零变化；唯一的新增运行期成本是提醒/气泡事件入口
  一次 0.42 µs 的判定。菜单默认布局新增一个根节点 `quiet_mode`（位于 `todo_panel` 与
  `voice_chime_now` 之间），老用户自定义布局由 `merge_default_menu_actions` 自动补齐。
- **配置迁移**：两个全新键 `quiet_minutes_default`（默认 `30`）与
  `quiet_also_on_fullscreen`（默认 `True`）；老配置无此键 → 取默认；手改脏值（字符串布尔 /
  非档位数字）由 `normalize_quiet_minutes` 与 `_bool_or_default` 收口。无落盘数据迁移。
- **回滚**：`git revert c90a7d1` 即可，**无残留状态**——config 里多出的两个键会被
  `Config.data` 忽略、退化为无害未知键；进程级单例随进程退出消失；`SharedSubsystems.quiet`
  的移除不残留线程或定时器。
- **合并冲突面**：`pet/menu_templates/modern-default-v1.json`、
  `tests/test_menu_layout.py`、`tests/test_desktop_pet_features.py` 三处根菜单顺序是热点
  （当晚确实与 #210 在此并序）；`tests/test_config_schema.py` 两份快照是字面量，多分支同时
  加键时数字要对齐；`SharedSubsystems` 新增的 `self.quiet` 同时进了 `stop_all()` 与
  `_release_qt_lifetimes`，**解冲突时别丢这两行**。
- **一条给后来者的纪律**：**别把免打扰塞进 `bubble_blocked`**——那会连自言自语/点击台词
  一起压掉（表现为「点了没反应」）。`window_alerts.py` 的 docstring 已写明。
- **分支状态**：本提交经 `589d25f` 并入 `integration/2026-10-07-night-batch`；
  分支未 push、PR 未开。


## 九、终审修复对齐（2026-10-07 追加）

> 按 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) 的「后续轮次在同一文档追加新章节、
> 保留新旧对照，不要重写覆盖」约定**追加**：上文记录的是各提交当时的树，本节只记终审修复
> 带来的增量。上文对应位置已就地加注「2026-10-07 终审修复对齐（提交 `<sha>`）」。

### 9.1 §2 修改文件说明的增量

`ddbea79`（+25 新增 `pet/settings_widgets.py`，四模块各接一处）——§2 的 `settings_quiet.py`
行（+94）现在另有 **+4 / −1**：

- 免打扰两键（默认档位 selector + 全屏联动 toggle）在**子宠页置灰** + tooltip
  「仅主桌宠可设置」。理由：子宠的独立设置进程写 `config-slot-N.json`，而这两个键**不在**
  `PER_SLOT_SETTING_KEYS` 里，overlay 的 `_SpriteConfig` 只对 per-slot 键逐 sprite 取源
  → 运行期读的是主配置，子宠页改了等于没改，原先属「能保存、运行时不消费」的静默死开关。
  这是**有意不加进** `PER_SLOT_SETTING_KEYS`：免打扰是进程级语义，不是逐宠偏好。
- 收口函数是新增的 `settings_widgets.mark_main_pet_only()`（幂等；主宠页一个不动；控件因
  平台条件不存在时静默跳过）。

### 9.2 抑制真值表与性能分析的增量（`87e9adb`）

`87e9adb` 改了 7 个文件：`pet/quiet_mode.py` +67/−23、`pet/multi_window_shared.py` +39/−6、
`pet/app.py` +11/−3、`pet/context_menus/shared.py` +17/−4、`pet/overlay_shell.py` +9/−2、
`pet/festival_service.py` +6/−6、`pet/voice_chime_service.py` +6/−5。**四点推翻上文的旧口径**：

| # | 上文口径 | 现行口径 |
|---|---|---|
| 1 | §1/§3.1「到点或提前结束即**排空**暂存并汇报」 | **交付确认制**：`take_report` 只给快照，排空发生在 `ack_report`；没有可交付目标（`MultiWindowProxy.has_presentation_target` 为假 / `show_alert` 返回无窗接手）时**保留暂存、1Hz 表下一拍重试**。旧口径的实测后果：退出全屏是「先结算、后恢复窗口」，汇报只投向可见窗而此刻窗还隐藏着 ⇒ 暂存已排空、提醒**静默丢失** |
| 2 | §3.2 第 1 条「分流提到 `show_alert` 的可见性判定之前」（只覆盖 `show_alert`） | **分流先于呈现筛选**推广到全部通道：节日/报时的判定原先在 `isVisible` 分支**内**（宿主隐藏即落到系统通知，压不住也不进队列）；共享联动代理先按可见窗筛选，隐藏窗的普通提醒在**到达门控之前**就被丢掉。两处改为判定先于可见性/呈现目标筛选 |
| 3 | §3.1 未提入场时序 | **入场锁边沿**：`start` 与 `set_fullscreen(True)` 入场即置位——此前首个 1Hz tick 之前退出全屏会留下「暂存非空、永不汇报」的死状态（测试手工调 `check_end` 才补上） |
| 4 | §3.1 真值表「提前结束」行 = 结束并汇报 | **`end_now` 只停计时**，不再自行排空/汇报：提前结束与到期、退出全屏走**同一条**交付链，避免两条路径各丢一次或各报一次 |

**§4 性能分析的增量**：上文「`QuietTicker` 只在免打扰生效期间运行」需要补一句——**结算未确认
交付期间它继续跑**（重试直到有交付目标）。即表的存活区间由「免打扰窗口」扩为「免打扰窗口 ∪
待交付窗口」。稳态仍为零（不进免打扰就不建表），无新增线程/网络/磁盘。

### 9.3 §6 测试与验证的增量

`tests/test_quiet_mode.py` **+372 / −16**（45 → 57 例）。新增覆盖：全屏进 → 暂存 → 全屏出 →
恢复 → 收到汇报的完整组合链（真实扇出顺序 + 真实代理 + 真实 `SharedSubsystems` 处理链）、
overlay 拓扑结算次序（监听器在状态翻转那一刻读 overlay 可见性）、**无交付目标时不清空不停表**、
目标恢复后补报、隐藏代理/隐藏宿主的节日与报时入队、入场边沿三例。

### 9.4 §7 已知限制与后续的增量

- 第 1 条（全屏联动依赖既有开关）不变。
- **新增**：**汇报依赖「有交付目标」**。所有窗口都隐藏（或该拓扑下无可见窗）期间，暂存的
  提醒不会丢，但要等到有目标才交付；1Hz 表在此期间保持运行（这是 §9.2 第 1 条的成本）。
- §7 第 3 条的两个待产品拍板口径（自言自语/点击台词穿透、音频不压）**未变**。
