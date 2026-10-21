# issue #210：右键菜单「回收内存」

> **基线**：`0ba442c`（四份交付报告与 INDEX 登记）；本提交经 `95bd2f3` 并入 integration，
> 菜单节点由 `589d25f` 与 #208 并序（`quiet_mode` → `memory_trim`）
> **分支**：`feature/issue-210-memory-trim`　**提交**：`67f1785`　**日期**：2026-10-07
> **范围**：11 个文件（实现 5、测试 5、菜单模板 1），净 `+1573 / −2`
> **关联**：issue #210
> **互链**：设置准入（命令类不进设置页）见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)；
> 纯逻辑层零 Qt 守卫见 [`../AGENTS.md`](../AGENTS.md) 与 `tests/test_architecture.py`；
> 必备证据章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在
> [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

右键菜单「工具」段新增一条**「回收内存」**：点击后把本机**普通进程**的工作集交给 Windows
的 `EmptyWorkingSet` 回收，数秒后冒一条气泡汇报结果（`已回收：N 个进程，跳过 M，无权限 K`）。
菜单点击**立刻关闭不冻结**（worker 在后台线程跑，结果经队列信号回 GUI 线程）。

设计上是**保守优先**：宁可少回收也不误伤。过滤真值表把「自己」「pid 0/4（内核伪进程）」
「自己的后代」放在**无条件跳过**的最前面——其中「跳过自己的后代」是超出 issue 原文的一处
加固，依据是本仓库的解码 ffmpeg 读者就是自己的子进程（仓库记录其工作集 47→64MB），抖它
等于动画当场掉帧。非 Windows 上整条菜单项不出现。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 菜单入口 | 「工具」段 `todo_panel` 之后（`tools` section）；非 Windows 整条不出现 |
| 2 | 后台执行 | 菜单立刻关闭；`run_in_background` 起 worker；结果经 `_MemoryTrimBridge` 排队回 GUI 线程 |
| 3 | 过滤真值表 | 自身 / 内核伪进程 / 自己的后代 / 前台（可配） / 名单内系统进程 / 工作集太小 |
| 4 | 汇报口径 | `已回收：N 个进程，跳过 M，无权限 K`；四类 reason 全部可解释 |
| 5 | 两个配置键 | `mem_skip_foreground`（默认 `True`）、`mem_min_size_mb`（默认 `50.0`），热读、无需重启 |

**红线 / 不变量**：
- `pet/memory_trim.py` 必须是**零 Qt 纯逻辑模块**（已纳入 `tests/test_architecture.py` 的机器守卫）；
- 句柄纪律：任何成功 `OpenProcess` 都必须有 `CloseHandle` 配对（单测断言**数量相等**，
  含跳过/失败路径）；
- 访问权限只用最小必要集合，**显式拒绝**升级成 `PROCESS_ALL_ACCESS`；
- 读不出工作集时**绝不盲调** `EmptyWorkingSet`；
- 非 Windows 上不显示入口。

## 二、修改文件说明

`git log --numstat 67f1785`：

```
15	0	pet/config.py
2	0	pet/context_menus/legacy.py
17	0	pet/context_menus/registry.py
95	0	pet/context_menus/shared.py
520	0	pet/memory_trim.py
1	0	pet/menu_templates/modern-default-v1.json
3	0	tests/test_architecture.py
56	0	tests/test_config_schema.py
2	0	tests/test_desktop_pet_features.py
854	0	tests/test_memory_trim.py
8	2	tests/test_menu_layout.py
```

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/memory_trim.py`（新） | +520 / −0 | 纯逻辑层（**零 Qt**）：过滤真值表 `decide_target`、编排 `trim_working_sets`、ctypes 薄封装 `Win32ProcessApi`（kernel32 / psapi / user32）、后台入口 `run_in_background`、汇报口径 `TrimReport.text`。 |
| `pet/context_menus/shared.py` | +95 / −0 | `add_memory_trim`（菜单项，Windows 门）+ `trigger_memory_trim`（读配置 → 起 worker → 队列信号回气泡）+ `_MemoryTrimBridge`（worker→GUI 跨线程投递/保活，口径同既有 `_MusicLaunchBridge`）。 |
| `pet/context_menus/registry.py` | +17 / −0 | 注册 `memory_trim` 规格 + `_memory_trim_available`（走 `memory_trim.is_supported()`，与执行层**同一判据**）+ `ACTION_LABELS` / `ACTION_ICONS`（图标复用现有矢量 `clear`）。 |
| `pet/context_menus/legacy.py` | +2 / −0 | legacy 扁平布局在「Agent 联动」之后接入同一 builder（无图标，符合 legacy 约定）。 |
| `pet/menu_templates/modern-default-v1.json` | +1 / −0 | 默认布局 `tools` 段 `todo_panel` 之后插入 `memory_trim`；用户自定义布局由既有 `_merge_future_default_actions` 自动补上，**无需迁移**。 |
| `pet/config.py` | +15 / −0 | 键登记**五处**：默认值 `mem_skip_foreground=True` / `mem_min_size_mb=50.0`、reload 白名单、`_normalize_pet_settings`（布尔防 `bool("false")` 误开；阈值夹 [0, 8192]）、`Config.set` 归一化触发名单。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_memory_trim.py`（新） | +854 / −0 | 46 条：过滤真值表、句柄必关（数量守恒）、汇报口径、权限失败、后台线程、平台分派、菜单可用性（modern / legacy / facade）、配置读取。 |
| `tests/test_config_schema.py` | +56 / −0 | 白名单快照加两键；脏值归一化 + `set()` 归一化 + 默认值断言。 |
| `tests/test_menu_layout.py` | +8 / −2 | 默认布局节点快照 + 渲染清单（Windows 分支差量）。 |
| `tests/test_desktop_pet_features.py` | +2 / −0 | modern 菜单扁平清单（Windows 分支）。 |
| `tests/test_architecture.py` | +3 / −0 | 把 `memory_trim.py` 加进「纯逻辑层零 Qt」机器守卫名单。 |

### 未改动（看起来相关但故意没动）

- **设置页**：按 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 的「命令类不进入
  设置页」准入条款，**未加设置行**（与 `music_player_paths` / `pnpm_bin` 同类：只存在于
  `config.json`）。
- 自动/定时回收：本批只做菜单点击触发（见第七节）。
- 非 Windows 分支的实现：整条入口不出现，不写假实现。

## 三、实现要点

### 3.1 过滤真值表（判定顺序即优先级）

| # | 进程 | 条件 | 结论 | reason |
|---|---|---|---|---|
| 1 | 自己（`os.getpid()`） | 永远 | skip（**连 `OpenProcess` 都不做**） | `self` |
| 2 | pid 0 / 4（Idle / System） | 永远 | skip（内核伪进程） | `system-critical` |
| 3 | 自己的后代（进程树快照） | 永远 | skip | `own-child` |
| 4 | 当前前台进程 | `mem_skip_foreground=true`（默认） | skip；置 false 则 trim | `foreground` |
| 5 | 名单名（csrss / smss / services / lsass / winlogon / wininit / dwm / fontdrvhost / MsMpEng / NisSrv / System…，casefold、去 `.exe`） | 永远 | skip | `system-critical` |
| 6 | 工作集 < `mem_min_size_mb`（默认 50MB，**含端点**：等于阈值算达标） | 否 | trim | `too-small` / `ok` |
| 7 | `OpenProcess` 失败（受保护 / 其它会话 / 未提权） | — | 计入失败，安静跳过 | `open-failed` |
| 8 | 工作集读不出来（返回负值） | — | 计入失败，**绝不盲调** | `query-failed` |
| 9 | `EmptyWorkingSet` 返回失败 | — | 计入失败 | `trim-failed` |

### 3.2 三条实现纪律

1. **访问权限用最小必要集合**：`PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_QUOTA`
   （`0x1100`），显式拒绝升级成 `PROCESS_ALL_ACCESS` / `QUERY_INFORMATION`。
2. **句柄类型必须纠正**：`HANDLE` 的 `restype=c_void_p`——默认 `c_int` 会截断 64 位句柄。
   *〔2026-10-07 终审修复对齐（`9dbc893`）：本条纪律当时**只落到了 `OpenProcess`/`CloseHandle`**，
   进程树快照三件套漏在外面（真实缺陷：句柄泄漏）——现已补齐签名 + 统一失效判定，见 §9.1〕*
3. **句柄纪律**：编排里 `CloseHandle` 只出现在**唯一一处 `finally`**；单测断言
   「成功 `OpenProcess` 数 == `CloseHandle` 数」，含跳过与失败路径；进程树快照的句柄同样在
   `finally` 收尾。

### 3.3 一处超出 issue 原文的加固（可一行移除）

**跳过自己的子进程。** 依据是本仓库的解码 ffmpeg 读者就是自己的子进程（仓库记录其工作集
47→64MB），回收它等于动画当场掉帧。真机实测 `own_child_pids()` 确实抓到了自己 spawn 的子进程。

## 四、性能分析

**方法（可复现）**：不入库的探针脚本 `/tmp/probe_memtrim.py`、`/tmp/probe_cmp.py`、
`/tmp/probe_e2e.py`（交付后删除），本机真实进程枚举 + 真实 Win32 调用。
环境：Windows / Python 3.13.7 / PySide6 6.11.2，本机在跑约 400 个进程。

| 指标 | 实测 | 归属 |
|---|---|---|
| 「不执行只评估」全量扫描（真实枚举 + 真实过滤，`empty_working_set` 替成记录，**未对任何真实进程下手**） | 404 个进程 → 会回收 **14**、跳过 **188**（`too-small` 185 / `foreground` 1 / `system-critical` 1 / `self` 1）、无权限 **204**；**总耗时 0.03s** | 新增 |
| 单进程 `EmptyWorkingSet` 端到端（只对自己 spawn 的子进程） | 工作集 **211.6MB → 0.0MB** | 新增 |
| `PROCESS_MEMORY_COUNTERS` 布局正确性 | 对 6 个进程（explorer / nvcontainer / StartMenuExperienceHost / SearchHost / msedgewebview2 / NVIDIA Overlay）本模块读数与 PowerShell `WorkingSet64` **逐字节一致（ratio 1.000）** | 新增 |
| 菜单点击的 GUI 线程占用 | worker 在后台线程；菜单**立刻关闭**，无冻结 | 新增 |
| 稳态开销（不点菜单） | **零** —— 无定时器、无线程、无缓存；唯一新增是菜单构建期一次 `is_supported()` 判空 | 既有路径不变 |
| 新增线程 | 每次点击 1 个短命 worker；**用完即退**，非常驻 | 新增（离散） |
| 新增系统调用 | 每次点击 ≈ 400 次 `OpenProcess` + 若干 `QueryWorkingSetEx` / `EmptyWorkingSet`（0.03s 内完成）；不点则 0 | 新增（离散） |
| 新增网络 / 磁盘 | **0 / 0** | — |
| 内存 | 无缓存、无对象池；报告对象随 worker 结束释放 | — |

**结论**：① **稳态开销零变化**——不点菜单时该功能不参与运行（无定时器/线程/缓存）；
② **新增路径成本 0.03s 量级且完全在后台线程**（所以放 GUI 线程会卡、但后台成本可忽略——
这也是必须用 worker 的实测依据）；③ **未引入常驻线程/网络/磁盘**，`OpenProcess` 系列只在
用户点击时发生；④ **内存零增长**（无缓存、无对象池）。

## 五、实机运行记录

**主代理本机验收（真实桌面、真实进程）**：

- **用户可见行为确认（逐条照用）**：点击菜单后气泡出现 **「已回收：21 个进程…」**——
  这是本条目的**前置基础证据**，证明：① 菜单项真实存在且在真实进程里可点；② 后台 worker
  真实跑完并把结果经队列信号送回 GUI 线程（气泡文案里的回收计数是真实扫描结果，非占位）。

**本机真实 Win32 证据（会话内做的，均为只读或只对自己 spawn 的子进程）**：

1. **ctypes 接线真机跑通**：`Win32ProcessApi()` 三个 DLL 加载 + `argtypes` 全部被真实函数
   接受；`list_pids()` 枚举 404 个 pid，`foreground_pid()` 有值，`image_name` /
   `working_set_bytes` 对自身进程正常返回（此前单元替身无法覆盖 `argtypes` 合法性）。
   *〔2026-10-07 终审修复对齐（`9dbc893`）：这条真机探针**没有覆盖 `own_child_pids` 走的
   进程树快照路径**，而该路径当时正缺签名（真实缺陷）——补证见 §9.4〕*
2. **`PROCESS_MEMORY_COUNTERS` 布局校验**：6 个进程读数与 PowerShell `WorkingSet64`
   逐字节一致（ratio 1.000）——证明结构体定义没写错。
3. **端到端（只对自己 spawn 的子进程下手）**：`open_process`（TRIM_ACCESS）成功 →
   `EmptyWorkingSet` 返回 `True` → 子进程工作集 **211.6MB → 0.0MB**；同时过滤层把它判为
   `skip/own-child`，`own_child_pids()` 也正确包含它（加固生效）。子进程随后被 kill 回收。
4. **全量扫描（不执行只评估）**：404 个进程 → 会回收 14、跳过 188、无权限 204，总耗时 0.03s
   （见第四节）。**未对任何真实进程下手。**

**边界与失败路径（实机/自动已验证）**：

- **前台保护**：`mem_skip_foreground=true`（默认）时前台进程被 skip；置 `false` 后同样会被
  回收（`reason=foreground` 进 trim 分支）。
- **自身与子进程保护**：自身 `self` 跳过、自己 spawn 的子进程 `own-child` 跳过——单测断言
  「成功 `OpenProcess` 数 == `CloseHandle` 数」覆盖含跳过路径。
- **「无权限」计数偏大是预期**：未提权运行时约半数系统进程打不开（无权限 204 / 404），
  这是诚实口径，不是缺陷。
- **非 Windows**：整条菜单项不出现（`darwin` 单元用例覆盖）。

**无法自动验证的能力（如实登记）**：

- **未做真实 GUI 目视验收的逐条对照**（「点完菜单立刻关闭且不冻结」的观感），只有菜单
  构建与后台线程的自动化断言 + 主代理的真机点击气泡证据。
- **多实例场景未验**：多开桌宠实例时，实例 A 会回收实例 B 的工作集（只保护「自己」这一个
  pid，不做同程序实例识别）——见第七节。
- **未在非管理员权限与管理员权限两种运行态下各跑一遍对照**（无权限计数会不同）。

**一次诚实记录的失败（非本交付的缺陷）**：中间有一次未拆分的整跑在 ~25%（`test_festival.py`
附近）**无任何 failure 输出、无 summary 地直接退出**（EXIT=1）——属仓库文档里记载的
「原生崩溃 / 无 summary」形态。当时同机另有**两个第三方 pytest 进程并发**（15.6GB 内存只剩
5.1GB）；按仓库 CI 纪律拆成两段后同树全绿，未再复现。

## 六、测试与验证

> *〔2026-10-07 终审修复对齐（`9dbc893`）：本节计数已过期，增量见 §9.2——
> `tests/test_memory_trim.py` +146/−0（46 → **54** 例，含签名级回归）〕*

**红 → 绿（先写测试、后写实现）**

```text
git stash push 只回退产品接线（registry/legacy/JSON/config，保留新模块与测试）
$ QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_memory_trim.py
8 failed, 36 passed        # 菜单/配置接线类全红
$ git stash pop
46 passed
```

接线确实是新加的行为，而非既有能力。另修了三处由本改动引起的**既有快照红**：
`test_menu_layout` 默认布局/渲染清单、`test_desktop_pet_features` modern 菜单清单
（均只加 Windows 分支差量）。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | **All checks passed** |
| 空白检查 | `git diff --check` | 干净 |
| 聚焦 | `tests/test_memory_trim.py` | **46 passed** |
| 聚焦（族） | `test_memory_trim + config_schema + menu_layout + architecture + desktop_pet_features + sprite_menu_parity + sprite_menu_facade` | **274 passed**（含 overlay parity，证明两条菜单路径与窗口基准逐项一致） |
| 全量（按仓库 CI 自身的拆分） | 主套件（ignore 3 个 webm 生命周期文件 + `test_low_priority_warm_interaction_yield.py`） | **4402 passed / 11 skipped** |
| 全量（被隔离的 4 个文件单独跑） | — | **68 passed** |
| 全量合计 | — | **4470 passed / 11 skipped**，与上一轮未拆分整跑的 4469+1（新增用例）一致 |
| 集成全量（当晚最终树） | `QT_QPA_PLATFORM=offscreen python -m pytest -q`（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

无新增第三方依赖（`ctypes` 是标准库）；无打包改动。

## 七、已知限制与后续

> *〔2026-10-07 终审修复对齐（`9dbc893`）：新增一条「快照三件套曾缺 ctypes 签名」（**已修**，
> 留档），详见 §9.3〕*

1. **多实例互回收**：多开桌宠实例时，实例 A 会回收实例 B 的工作集——只保护「自己」这一个
   pid，不做同程序实例识别。若产品在意，需要加「同镜像名实例」识别（一行判据，但要定义
   语义：是保护还是互相回收）。
2. **「无权限」计数偏大**：未提权运行时约半数系统进程打不开（真机 404 个进程里 204 个无权限），
   这是预期的诚实口径；提权运行会变小，但**不打算**为此要求提权（回收用户态进程工作集是
   锦上添花型优化，不值得要管理员权限）。
3. **无定时/自动回收**：仅菜单点击触发。设计上不自动——自动回收会周期性抖别人进程的工作集，
   收益不确定而副作用（首次访问磁盘 IO）可感知。
4. **无设置页开关**：两个配置键（`mem_skip_foreground` / `mem_min_size_mb`）只能手改
   `config.json`（按 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 的「命令类不进
   设置页」条款）。热读，改完无需重启。
5. **非 Windows 无实现**：只隐藏入口，不提供近似功能。

## 八、风险与回滚

- **影响面**：新增一条菜单项（Windows 上两个模板都接）+ 一个纯逻辑模块 + 两个配置键。用户
  不点菜单就零变化（无定时器、无线程、无缓存）。过滤层无条件跳过自身/内核伪进程/自己的
  后代，**不触碰**当前前台进程（默认）与系统关键进程名单。
- **配置迁移**：全新键 `mem_skip_foreground`（默认 `True`）、`mem_min_size_mb`（默认 `50.0`）；
  老配置无此键 → 取默认；手改脏值由 `_normalize_pet_settings` 收口（布尔防 `bool("false")`
  误开；阈值夹 [0, 8192]）。无落盘数据迁移。
- **回滚**：`git revert 67f1785` 即可，无残留状态（config 里多出的两个键退化为无害未知键；
  worker 是短命线程，随点击结束退出；已回收的工作集由操作系统按需重新换入，**不可逆但无害**
  ——`EmptyWorkingSet` 只丢弃可再换回的物理页，不丢数据）。
- **合并冲突面**：`pet/menu_templates/modern-default-v1.json`（一行插入）、`pet/config.py`
  （三处插入点）、`pet/context_menus/registry.py`（4 处插入点）、
  `tests/test_menu_layout.py` + `tests/test_desktop_pet_features.py` 的期望清单。当晚与
  #208 的插入锚点都选在 `todo_panel` 之后，由 `589d25f` 并序为 `quiet_mode` → `memory_trim`。
  `tests/test_config_schema.py` 的两份**字面量**快照（`RELOAD_WHITELIST_SNAPSHOT` /
  `DEFAULTS_SNAPSHOT`）是最容易撞的地方：与本分支同时改 config 键的 PR 合并时两侧键都要
  保留，否则该测试立刻红。
- **分支状态**：本提交经 `95bd2f3` 并入 `integration/2026-10-07-night-batch`；
  分支未 push、PR 未开。


## 九、终审修复对齐（2026-10-07 追加）

> 按 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) 的「后续轮次在同一文档追加新章节、
> 保留新旧对照，不要重写覆盖」约定**追加**：上文记录的是各提交当时的树，本节只记终审修复
> 带来的增量。上文对应位置已就地加注「2026-10-07 终审修复对齐（提交 `<sha>`）」。
>
> **定位说明**：本节对应的上文位置是 **§3.2 第 2 条（句柄类型必须纠正）** 与
> **§5 第 1 条（ctypes 接线真机跑通）**——上文 **§7 并没有一条「ABI 可疑」**，故按
> "确曾存在、现已修"补记在 §9.3 的 §7 增量里，而不是去改一条不存在的限制。

### 9.1 事实：同一类缺陷在快照三件套上确实存在过（`9dbc893`）

`pet/memory_trim.py` **+35 / −2**。上文 §3.2 第 2 条警告过「`HANDLE` 的 `restype` 必须是
`c_void_p`，默认 `c_int` 会截断 64 位句柄」，但这条纪律当时**只落到了 `OpenProcess` /
`CloseHandle`**：进程树快照三件套漏在外面。

| 函数 | 旧实现 | 后果 |
|---|---|---|
| `CreateToolhelp32Snapshot` | **无 argtypes/restype** | 快照句柄按默认 `c_int` 接收 → **64 位句柄被截断**；`INVALID_HANDLE_VALUE(-1)` 也可能读成正数 ⇒ **「快照失败」被当成有效句柄**：句柄泄漏，后续 `Process32*` 拿着垃圾句柄 |
| `Process32FirstW` / `Process32NextW` | 无签名 | 入口指针宽度未声明 |
| 失效判定 | `handle == c_void_p(-1).value` | 只在「本机恰好返回无符号全 1」时成立 |

**修法**：三个函数补签名（快照句柄走 `c_void_p`，与既有 `OpenProcess`/`CloseHandle` 同口径；
`Process32FirstW`/`NextW` 入口按 `POINTER(_ProcessEntry32W)` 声明、`restype=c_int`）；失效判定
收敛到单一 `_invalid_handle()`——**NULL / −1 / 无符号全 1 / 32 位全 1（截断形态）一律算失效**，
`own_child_pids` 与 `CloseHandle` **共用**它，失效句柄**不再进 `CloseHandle`**。

### 9.2 §6 测试与验证的增量

`tests/test_memory_trim.py` **+146 / −0**（46 → **54** 例）。新增：三件套的**签名断言**
（句柄 `restype` 必须是指针宽度、入口必须是 `LPPROCESSENTRY32W`）、五种失效表示下返回空集合
且**不碰** `CloseHandle`/`Process32FirstW`、合法高位句柄不被误杀、判定函数真值表。

**顺带修正一处错误的替身**（属上文 §6 的"替身面"问题，不是产品缺陷）：`Process32FirstW` /
`NextW` 原本各持一个游标，等于把「快照里只有第一个进程」喂给被测代码——共用游标后才是真枚举
语义。这条修正说明上文 §6 的 `test_own_child_pids_walks_the_process_tree` 当时**只验证了单节点
枚举**，其覆盖强度低于报告的表述。

### 9.3 §7 已知限制与后续的增量

- **新增（已修，留档）**：**快照三件套曾缺 ctypes 签名**（见 §9.1）——属真实缺陷（句柄泄漏
  路径），现已随 `9dbc893` 修复并加了签名级回归。上文 §7 没有列出这条，是因为写报告时真机
  探针只覆盖了 `Win32ProcessApi()` 建对象与 `list_pids`/`foreground_pid`/`image_name`/
  `working_set_bytes`（`OpenProcess` 系），**没有覆盖 `own_child_pids` 走的那条快照路径**。
- §7 第 1 条（多实例互回收）**未变**：只保护「自己」这一个 pid，不做同程序实例识别。
- §7 第 5 条（非 Windows 无实现）**未变**。

### 9.4 §5 实机运行记录的增量（`9dbc893` 的真机证据）

上文 §5 第 1 条写「三个 DLL 加载 + `argtypes` 全部被真实函数接受」——这句在新签名到位后才
**完整成立**。补三条真机证据：

```text
三个函数的签名在真实 Win32 函数上生效
对自建子进程 own_child_pids 仍能命中
连续 200 次快照后本进程句柄数 138 → 138（无泄漏）
CreateFileW 双向验证：指针语义返回 18446744073709551615、截断语义返回 -1，两者都被判失效
```

第 4 条是关键——它用同一台机器上的两种语义形态**双向**验证了 `_invalid_handle()` 的真值表，
而不是只赌"本机恰好返回全 1"。
