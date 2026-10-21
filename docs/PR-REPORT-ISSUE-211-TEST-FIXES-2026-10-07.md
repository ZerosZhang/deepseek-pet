# issue #211：真桌面测试修复吸收（假屏放大 + 关多屏快照 + MAX_PATH + reader 有界等待）

> **基线**：`ee699c7`（Merge PR #233 from MerZlin/feature/agent-link-subtraction）
> **分支**：`feature/issue-211-test-fixes-absorb`（已并入 `integration/2026-10-07-night-batch`）
> **提交**：`b09a502`　**日期**：2026-10-07
> **范围**：4 个文件（实现 0、测试 4、文档 0），`+74 / −14`——**产品代码零改动**
> **状态**：分支未 push、PR 未开；本批六分支整合终全量 **4413 passed, 11 skipped**
> （`integration/2026-10-07-night-batch`，2026-10-07）
> **关联**：上游 #211（旧架构时期的测试基建批，9 条真桌面失败用例的修复）；
> 报告体裁与必备章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；
> 时序测试纪律见 [`PR-MERGE-LESSONS-2026-09-12.md`](PR-MERGE-LESSONS-2026-09-12.md)；
> 本文已登记在 [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

上游 #211 是一份**测试基建批**：9 条用例在开发者真桌面上红、在 CI 的 offscreen
上绿（"自己机器红、CI 绿"）。本批按**当前架构**（单合成窗 overlay / 桩件布局已
变）逐条重新评估后，只吸收仍然成立的 4 个测试文件；其余 8 个文件属旧的协作流程
条款（AGENTS.md 经验条目、AI-LESSONS、RETRO-CADENCE、`scripts/retro_check.py`、
`.gitignore`/`pytest.ini` 产物收口、`docs/INDEX.md`、PR 报告本身），基于 #215 之
前的架构与被废弃的节奏机制，**按产品 owner 决策不收**。

**产品代码 0 改动**：本批只让 4 个测试文件在真桌面（不设 `QT_QPA_PLATFORM`）下
从红转绿，同时**不削弱任何断言**——每处放宽都用注入探针证明「原来的红是真的红、
放宽后仍能区分新旧实现」。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 假屏放大 1920×1200 → 4096×3072 | 两个拖拽族文件的假屏尺寸必须**显著大于被测目标**：窗口初始位置是 `PetWindow` **构造时按运行机真实屏幕**算的（假屏在构造之后才装上），真桌面偏右下时合帧目标落到假屏外、被正常贴边钳位 |
| 2 | 关掉多屏活动区域快照（autouse fixture） | #186 的 `window_placement.desktop_area()` 走 `QGuiApplication.screens()`，**绕过**测试假屏；本机单屏复现不出，用注入 2×1920×1080 快照的探针证明 9 条必红 |
| 3 | 长图片名重复 8 → 3 次 | `tmp_path` 已有 ~90 字符，`*8` 拼出 **262 字符**绝对路径，超 Windows `MAX_PATH`（260）；不开长路径支持的机器上 `Image.save()` 直接 `FileNotFoundError` |
| 4 | reader / 元数据探测改有界等待 | `webm_clip.start()` 之后 reader 在**新线程**里跑，紧接 `assert spy.read_frames_calls` 只是赌调度；注入 300ms 启动延迟后原断言必红 |

**红线 / 不变量**：
- **断言强度不许下降**：两处放宽（路径长度、等待式断言）都有注入探针证明仍有牙
  （见第四、五节），不是"把红的改绿"；
- 多屏钳位语义**没有被删除**，只是从这两个拖拽族文件里让位——它仍由
  `tests/test_multi_screen_interaction.py`（17 条）与 `tests/test_edge_reachability.py`
  专职锁定；
- 产品代码一行未改：`pet/` 下无任何文件出现在本提交的 diff 里。

## 二、修改文件说明

`git diff --numstat ee699c7 b09a502`：4 个文件，`+74 / −14`，全部在 `tests/`。

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_drag_move_coalescing.py` | +25 / −3 | `_BigScreen` 假屏 1920×1200 → **4096×3072**（`availableGeometry`/`geometry` 两处）并把 docstring 改成**实测机制**（原注释只说"offscreen 屏只有 800×600"，没写真正原因是构造期真实屏幕推导出的初始位置）；新增 `@pytest.fixture(autouse=True) _single_screen_desktop`，用 `monkeypatch.setattr(window_placement, "desktop_area", lambda: None)` 关掉 #186 的多屏快照。共 13 条 |
| `tests/test_pet_interaction_locks.py` | +20 / −3 | 同一对改动（假屏同尺寸 + 同名 autouse fixture），docstring 指向 `test_drag_move_coalescing` 的同名假屏说明。共 17 条 |
| `tests/test_desktop_pet_features.py` | +5 / −1 | `test_image_directory_picker_opens_right_drawer_with_three_column_masonry`：`"very-long-image-name-" * 8` → `* 3`，并在原位写明 262 > 260 的数值理由与"截断 + tooltip 全名两条断言照旧有牙"的实测口径。共 96 条 |
| `tests/test_session_end_ffmpeg_guard.py` | +24 / −7 | 新增模块级 `_wait_until(pred, timeout=10.0)`（有界轮询，同 `tests/test_agent_link_threads.py` 的 `wait_until` 惯例）；`test_control_group_spawns_normally_without_session_end` 的两条"对照组必须发生"断言（`read_frames_calls`、`count_calls`）改为等待式，**顺手把仓库既有的内联轮询（后者本来就在）收进同一 helper**，同一函数里不再有两种写法；预算仍 10s（没有缩 CI 宽预算）。共 27 条 |

### 实现 / 文档

**无**。本批不新建、不修改任何产品代码与文档文件；本文本身在 `docs/` 下新增
（见第六节的纪律门）。

### 未改动（看起来相关但故意没动）

| 文件 | 为什么不动 |
|---|---|
| `pet/window_placement.py`（`desktop_area()`） | 多屏活动区域快照是 #186 的**产品语义**（多显示器下把宠物钳在可见桌面内），本批只是让两个拖拽族测试不再依赖真实桌面，**没有**改产品行为 |
| `pet/window.py`（`build_window_flags` / 构造期初始位置） | 「初始位置按真实屏幕算」是既有设计，真桌面红是**测试假屏不够大**，不是产品缺陷 |
| `tests/test_multi_screen_interaction.py`、`tests/test_edge_reachability.py` | 多屏钳位与贴边语义的专职 owner，本批复核它们仍绿（第六节），不重复断言 |
| `tests/test_chat_subsystem.py`、`tests/test_context_menu_lifecycle.py`、`tests/test_effects_integration.py` | 这三个文件里也有 1920×1080 级别的假屏，**存在同类隐患但未做全量甄别**——见第七节第 1 条（诚实登记，不在本批范围） |
| 上游 #211 的其余 8 个文件 | 协作流程条款 + PR 报告，基于旧架构与已废弃的节奏机制，owner 决策不收 |

## 三、实现要点

1. **假屏尺寸是"比测试目标更大的无边界环境"，不是随便放大**。原 1920×1200 在
   offscreen 下够用（CI 屏小、初始位置也小），但在真桌面上 `PetWindow` 构造时按
   运行机屏幕算出的初始位置偏右下，由它推导的合帧目标会超出 1920×1200 → 被贴边
   钳位 → 断言（期望是未钳位的坐标）必红。取 4096×3072 后所有被测目标都落在边界
   内，钳位不再参与本文件的判定——**被钳位的语义没有消失，只是不再由这两个文件
   承担**。
2. **多屏快照必须显式关掉，不能靠"本机单屏"侥幸**。`desktop_area()` 走的是
   `QGuiApplication.screens()`，与测试里 `app.setProperty(...)`/替身屏**不是同一
   条取数路径**，假屏盖不住它。autouse fixture 把它钉成 `None`，等于声明"本文件
   只在单屏语义下判定"；这条声明是可测的——注入 2×1920×1080 快照后不关即 9 条全红。
3. **等待式断言用轮询而不是事件**。这里**必须**是轮询：spy 的 `read_frames`
   返回 `None`，reader 在 `next(gen)` 处就抛异常，`clip._reader_ready.wait()`
   （`pet/webm_clip.py` 里 reader 正常收尾才 `set()`）在这个用例里永远走不到——
   事件式同步反而会把用例变成"必然超时"。轮询 10s 宽预算与
   [`PR-MERGE-LESSONS-2026-09-12.md`](PR-MERGE-LESSONS-2026-09-12.md) 的
   「poll state with a wide budget」一致。
4. **同处两种写法合并**：`test_session_end_ffmpeg_guard.py` 里 `count_calls` 那半
   的轮询**仓库里本来就有**（`b3ddaf1` "对照组元数据探测改宽预算轮询"），本批不
   重复吸收，只是把它收进同一 helper——同一函数、同一竞态，不再出现第二套写法。
5. **上游提交里唯一没吸收的半条**：`.gitignore` / `pytest.ini` 的测试产物收口。
   它与本批 4 个文件无关，且已被仓库现状覆盖（`.pytest_cache` / `.ruff_cache` 已在
   `.gitignore` 内）。
6. **上游报告的归因被实测纠正**：PR 自述把真桌面红归因于"身体框 309×259 装不下"，
   实测 `catalog.character_body_box('shenshen')` = `(212,60,428,330)` 即 216×270，
   真正机制是构造期初始位置。docstring 按实测重写（保留"为什么"而不是保留结论）。

## 四、性能分析

**本批不改变任何运行期行为**（产品代码零改动、无新配置键、无新分支进入 `pet/`），
因此"稳态开销"的正确答案是**零变化**——但"零"本身要有可复现的测量口径，下面是
在整合分支上实测的数字，供后来者复核。

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen python -m pytest -q --basetemp=C:/pt_rep_c <4 files>`
环境：Windows 10 x64 / Python 3.13.7 / PySide6 6.11.2 / 本机真实屏幕 2560×1440。

| 指标 | 实测 | 归属 |
|---|---|---|
| 4 个文件的测试执行时间（offscreen，整合分支） | **153 passed in 8.75s** | 测试基建；本批后新增耗时 ≈ 0（改动都是 docstring、一个 fixture、一个 helper） |
| `_wait_until` 命中即返回的轮询步长 | `time.sleep(0.01)`，命中通常在 1–2 步内；上限 10s | 新增（测试进程内，不在产品进程） |
| `_single_screen_desktop` fixture 的每用例成本 | 一次 `monkeypatch.setattr`（属性替换，无 IO） | 新增（测试进程内） |
| 假屏面积变化 1920×1200 → 4096×3072 | 只影响 `availableGeometry()` / `geometry()` 的返回值（一个 `QRect` 字面量），**不分配任何缓冲区、不建窗口** | 测试替身 |
| 长路径 262 字符 → 约 130 字符 | 少 5 次目录名重复拼接；`Image.save()` 在小文件上从 `FileNotFoundError` 变为正常写盘 | 测试数据 |
| 产品运行期（`pet/` 任意热路径） | **0 变化**：本提交 diff 不含 `pet/` 下任何文件 | 零 |

**结论**：① 稳态开销**零变化**——`pet/` 无任何文件被改动，桌宠进程的行为与内存
与本批无关；② 新增路径只在测试进程内（一个 fixture + 一个 10s 上限的轮询 helper），
触发频率 = 每用例一次；③ **未引入任何新的系统调用 / 网络 / 磁盘 / 线程**（产品侧
没有新代码；测试侧 `_wait_until` 只做 `time.monotonic()` + `time.sleep()`，属于
既有测试惯例）；④ 内存无增长（无缓存、无长驻容器）。

## 五、实机运行记录

本机：Windows 10 x64，**真实开发机**（非 CI）。四段探针原始证据（探针脚本放在仓库
外的 `C:\Users\me\AppData\Local\Temp\wt211-probe\`，交付时未入库）：

1. **根因现场复现（真桌面，不设 `QT_QPA_PLATFORM`，跑未修改的 HEAD 代码）**：

   ```text
   7 failed, 23 passed
   test_normal_drag_records_latest_target_and_drops_intermediate:
       assert QPoint(1611, 941) == QPoint(2527, 1333)     # 被贴边钳位
   test_shift_drag_requires_shift:
       assert QPoint(1459, 919) != QPoint(1459, 919)      # 拖动被钳回原位
   ```

   上游 #211 PR 报告里出现的 `(1611, 941)` 在本机**逐位复现**；同一文件在 offscreen
   下 `13 passed`（把 HEAD 版本拷成临时文件跑过，跑完即删）——这就是"自己机器红、
   CI 绿"的直接证据。

2. **多屏快照注入探针（本机单屏，硬件复现不出来）**：用探针插件把
   `pet.window_placement.desktop_area` 替成 2×1920×1080 的 `DesktopArea`
   （模拟真实多显示器运行机）跑上面两个拖拽文件：

   ```text
   未加 fixture：9 failed, 21 passed   （drag 6 + interaction_locks 3）
   加 fixture 后：30 passed
   ```

   即 #186 的多屏快照走 `QGuiApplication.screens()` 会**绕过**测试假屏。

3. **慢调度注入探针（证明等待式断言不是恒过）**：
   `-p slowreader_plugin` 给 reader 线程注入 300ms 启动延迟，跑 session guard 整文件
   ——原断言 `assert []` **必红**；改等待式后同一注入下 **27 passed**。
   **反向对照**（`-p noreader_plugin`，reader 线程永不启动）：等待式断言 10s 后
   仍然红（失败耗时 `11.10s`）——**不是恒过**，这是它"有牙"的机器证据。

4. **MAX_PATH 数值证据（本机不能复现故障，如实说明）**：

   ```text
   tmp_path 前缀 ≈ 90 字符
   "02-" + "very-long-image-name-" * 8 + ".jpg" = 262 字符 > MAX_PATH 260
   本机 HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1
   → 所以本机现在通过；PR 作者的环境（LongPathsEnabled=0）是 FileNotFoundError
   ```

   改动**没有弱化断言**：用探针实测卡片（宽 134px）——绘制文本被截成
   `02-very-l…`（**10 字符**），tooltip 仍是**70 字符**全名，即"截断 + tooltip
   全名"两条断言照旧有牙。

**用户可见行为**：本批**不改变任何用户可见行为**（产品代码零改动），因此没有
"用户看到什么"这一格；替代证据是「同一个测试文件在真桌面与 offscreen 下同口径
全绿」：真桌面 13 / 17 / 27 / 96，offscreen 13 / 17 / 27 / 96。

**边界与失败路径（已自动验证）**：reader 线程**永不启动**时等待式断言仍红
（`11.10s` 失败，见第 3 条）；注入多屏快照时不关 `desktop_area()` 仍红
（`9 failed`）——两条都证明"放宽"之后仍能区分新旧实现。

**无法自动验证的能力（诚实登记）**：**没有跑「真桌面全量套件」**（不设
`QT_QPA_PLATFORM` 跑 4000+ 条）——那会在用户桌面上真开窗口，且本机单屏复现不出
多屏问题。已确认的边界是：这 4 个文件在真桌面下全绿，其余文件未做同类甄别。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | `All checks passed!` |
| 4 个文件（offscreen，整合分支复测） | `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_drag_move_coalescing.py tests/test_pet_interaction_locks.py tests/test_desktop_pet_features.py tests/test_session_end_ffmpeg_guard.py` | **153 passed in 8.75s**（13 / 17 / 96 / 27） |
| 同 4 个文件（真桌面，源 worktree） | 不设 `QT_QPA_PLATFORM` | 13 / 17 / 27 / 96 **全绿**（改动前 7 failed） |
| 相邻回归 | edge_reachability + drag + locks + session-guard + webm_reader_lifecycle + move_sync + desktop_pet_features | **233 passed** |
| 多屏语义 owner | `pytest -q tests/test_multi_screen_interaction.py` | **17 passed**（语义没被删掉） |
| 多屏快照注入探针 | `-p disksnapshot_plugin`（两个拖拽文件） | 修复前 **9 failed** → 修复后 **30 passed** |
| 慢调度注入探针 | `-p slowreader_plugin`（session guard 整文件） | 修复前对照组红 → 修复后 **27 passed** |
| 反向探针（不得恒过） | `-p noreader_plugin` | 等待式断言 10s 后**仍红**（`11.10s`） |
| 全量（源 worktree） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4307 passed, 11 skipped**（567.8s） |
| 本批整合终全量 | `integration/2026-10-07-night-batch` | **4413 passed, 11 skipped** |
| 交付纪律 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr_report_discipline.py -q` | 见本文末（登记后全绿） |

**红 → 绿（本批是"先有红、再吸收修复"）**：

| 用例/文件 | 修复前 | 修复后 |
|---|---|---|
| `test_drag_move_coalescing.py`（真桌面） | **6 failed**（`QPoint(1611, 941) == QPoint(2527, 1333)`） | 13 passed |
| `test_pet_interaction_locks.py`（真桌面） | **1 failed**（`test_shift_drag_requires_shift`） | 17 passed |
| 两文件 + 多屏快照注入探针 | **9 failed** | 30 passed |
| `test_session_end_ffmpeg_guard.py` + 300ms 调度延迟 | 对照组断言**必红**（`assert []`） | 27 passed |
| `test_desktop_pet_features.py`（`LongPathsEnabled=0` 的机器） | `FileNotFoundError`（262 字符路径） | 96 passed |

**断言有效性**：见第五节第 3、4 条与上表——三处"放宽"各自都有反向注入证明仍能
区分新旧实现（多屏快照不关仍红、reader 不启动仍红、长名截断与 tooltip 仍在）。

## 七、已知限制与后续

1. **同类隐患未做全量甄别**：`test_chat_subsystem` / `test_context_menu_lifecycle` /
   `test_effects_integration` 里也有 1920×1080 级别的假屏，理论上存在同一类
   「小假屏 + 真桌面初始位置」隐患。需要时可按同样手法（真桌面跑一遍）单独扫，
   不属本批范围。
2. **本机单屏，多屏问题只能靠注入探针**：`desktop_area()` 的真实多显示器行为在
   本机无法端到端复现（探针是替身快照，证明的是"这条取数路径能绕过假屏"）。
3. **长路径故障本机不可复现**：`LongPathsEnabled=1` 是既定事实，所以"262 字符
   一定失败"这一条的证据强度是**数值 + 上游现象**，不是本机故障复现（如实登记）。
4. **上游 #211 的处置建议**：建议在 GitHub 上**关闭而非合并**——4 个测试文件的
   修复已在本 fork 以适配当前架构的形式吸收，其余 8 个文件按 owner 决策不收，且
   PR 自述的归因（身体框 309×259）与当前实测不符。**外部动作（评论/关闭）未执行**，
   按对外提交纪律等 owner 明确点头。
5. **分支未 push、PR 未开**（见文末状态）。

## 八、风险与回滚

- **影响面**：仅 `tests/` 下 4 个文件，产品代码与运行期行为零影响。合并后 CI 的
  用例计数不变（都是既有用例改造，无新增/删除用例）。
- **配置迁移**：无新键、无落盘格式变化。
- **回滚**：`git revert b09a502` 即可，无任何残留状态（测试专用改动，不产生持久
  化数据、不写配置文件）。回滚后这 4 个文件重新变成"真桌面红、CI 绿"。
- **与本批其它分支的交互**：本批与 #219 / #220 / service-target / 三端 / 直播捕获
  五条线的文件集**不相交**（只在 `tests/` 下四个与拖拽、会话结束、设置图片抽屉相关
  的文件上），合并冲突面为零；整合后全量 **4413 passed, 11 skipped**。
