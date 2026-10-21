# 游戏帧率（灵动岛 `fps` 段）· PR 报告（2026-10-11）

> **基线**：分支 `release/2026-10-08-candidate`，`HEAD = 7b3fe8209ca622822d8b6807c647602ca7376d03`
> ＋未提交的整树改动（本批期间树上有并行分工同时改文件，本文所有行数取**写作时点**）＋未跟踪文件。
> **日期**：2026-10-11（写作时点 12:47 +08:00；实机证据的时点各自标注）
> **范围**：本功能按**三段分工**交付——① 后端与探针 ② 设置与岛接线 ③ 打包与文档（本文作者）。
> 三段的文件与实测数据由各自交接提供；**本文对每一段标注它的来源**，作者本人未复跑的部分不冒充已验。
> **关联**：后端交接 `.scratch/product-game-fps-20261011/HANDOFF.md`（后端/探针的完整证据）、
> [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 的 2026-10-11 条（设置准入/准出）、
> [`ONEDIR_PACKAGING.md`](ONEDIR_PACKAGING.md)「随包分发的第三方二进制」、
> [`PRODUCT-STATUS-2026-10-09.md`](PRODUCT-STATUS-2026-10-09.md) §二／§三.12。
> **一句话结论**：链路已实现、可按现有脚本构建、后端与许可随包并有两道构建门；
> **但本机普通权限下采不到任何真实帧**（ETW `access denied`），因此
> **本报告不包含任何一个真实 FPS 数字，也不得被读成"FPS 已验收 / 性能已验证"**。

## 一、核心特性

灵动岛新增一段**游戏的 Present 帧率**：用户打开「灵动岛指标 · 游戏帧率」后，桌宠按需
启动一个**随包分发的官方独立采集程序**，读出**目标应用真正呈现到屏幕上的帧数**，
以定宽读数上岛、详情进展开卡片。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 真实数据源 | 官方 PresentMon v2.6.0 独立控制台程序（ETW 上的显卡 Present 事件），**不是**桌宠动画帧率、**不是** GPU 占用推算、**不是**窗口抓取帧数 |
| 2 | 口径明确 | 主值 = 目标应用 Present 帧率（`MsBetweenPresents` 均值）；按 `(pid, swapchain)` 分窗、**多条链不相加**；上屏帧率（`DisplayedTime`）只在详情里另起一句并注明是另一口径 |
| 3 | 目标可控 | 默认跟随前台程序；可选「指定程序」模式填**一个纯 exe 名**（只按镜像名匹配进程，**永不执行**它）。不猜目标——不替你挑一个"帧率最高的程序" |
| 4 | 默认关闭 + 有界 | 出厂 `island_metrics` 仍为空列表；关闭／折叠／隐藏／退出即停会话，恢复先清旧值；会话**不按时间回收**，内存有界靠后端输出行缓冲上限（`MAX_BUFFERED_LINES = 4096`），长时间无帧走诊断 |
| 5 | 不虚报 | 没有读数恒显示 `--`（不是 0）；权限被拒／缺后端时卡片写**真实原因**，不编读数；非 Windows 整段按不支持、不占位 |
| 6 | 随包即用 | 用户不需要自己找工具：后端与它的 MIT 许可随 Windows 包分发，**不装 MSI、不注册服务、不装驱动、不写注册表** |

**红线 / 不变量**：

- 与桌宠动画帧率、GPU 占用、窗口抓取帧数**不可混算、不可互相替代**（文案与代码同源）。
- 一个应用实例**只有一场** ETW 采集会话（多宠共用），会话名每次唯一；**从不**用
  `--stop_existing_session` 抢占别人的会话、**从不** `--restart_as_admin` 静默提权。
- 非 Windows **不加载也不捆**这个 Windows 二进制；**只支持 x86-64**，不塞 ARM64。
- 打包侧：后端缺失或换版**必须在构建期中止**——缺件时产品不会崩，只会让这一段永远不出数，
  界面看不出来。

## 二、修改文件说明

### 2.1 打包与文档（本文作者，逐文件）

| 文件 | 本批增删 | 改动意图 |
|---|---|---|
| `resources/presentmon/PresentMon-2.6.0-x64.exe` | **新增**（二进制 980320 B） | 官方 v2.6.0 release 的独立控制台程序，sha256 `b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af`（与 release API 的 `digest` 一致），**仅复制核验过的这一份** |
| `resources/presentmon/LICENSE.txt` | **新增**（二进制 1067 B） | 同一 release 源码树的 MIT 原文，**逐字未改**；与源码树里那份的可证明同一性：本地 `git hash-object` = git blob `7ddce0e2636d1f6e0c21cfc0151e552c88062ccb` = v2.6.0 树中 `LICENSE.txt` 的 `sha` |
| `scripts/verify_presentmon.py` | **新增 196 行** | 校验门：存在 + 文件名 = `game_fps.BACKEND_EXE_NAME` + sha256 = `game_fps.REQUIRED_SHA256` + PE 头机器类型 = x86-64。**期望值从产品模块 import**（不抄第二份字面量）；`--json` 便于机器读；支持 `--path` 以便同一实现校验产物里那一份 |
| `tests/test_presentmon_packaging.py` | **新增 321 行 / 24 例** | 打包面测试：资源本体（只有那一个 x64 exe + 许可）、门有牙（截断／ARM64／改名／缺失四例真跑子进程判红）、构建接线（源码文本断言）、非 Windows 不捆、冻结布局契约（`sys._MEIPASS` 假布局）、文档与许可登记 |
| `scripts/build_onedir.ps1` | **+29 / −0**（本批即为该文件全部未提交改动） | 三处：① PyInstaller **之前**跑校验门（非零 `throw`）；② `--add-data "resources\presentmon;resources\presentmon"`（四个 Windows 变体都有）；③ **产物里**再验一次（`_internal\resources\presentmon\<exe>`，文件名从 `pet/game_fps.py` 读，脚本里不写第二份字面量） |
| `THIRD_PARTY_NOTICES.md` | **+56 / −0**（本批即为该文件全部未提交改动） | 新增第 6 节：来源仓库／release、版本、sha256、字节数、许可（MIT, Intel）、为什么不是 pip 依赖、分发边界（不装服务/驱动/注册表、仅 Windows、按需子进程）、随包位置、升级时必须同时改的四处、MIT 原文照抄 |
| `docs/ONEDIR_PACKAGING.md` | **+34 / −1**（文件总 +103/−2，其余属其它批次） | 新增「随包分发的第三方二进制」小节（资源表、只 Windows、只有 x86-64、两道门各挡什么、升级要改哪里、手工取得方式与"构建不联网"的取舍）；冒烟清单加一条产物检查项 |
| `docs/SETTINGS-CHANGE-GATES.md` | **+44 / −0**（文件总 +109/−1，其余属其它批次） | 新增 2026-10-11 变更记录：2 个进程级键 + `island_metrics` 的 `fps` 成员 + 3 行设置，按准入 6 条与准出 5 条逐项写清（键形态与安全契约、依赖与恢复、文案纪律、TDD 覆盖、真机布局、跨平台口径） |
| `docs/PRODUCT-STATUS-2026-10-09.md` | **+15 / −2**（未跟踪文件，无 diff 可比） | §二 能力现状表新增「游戏帧率」一行（**已实现（源码）；真实读数未验**）；§三 第 11 条把"FPS 仅问过可行性"改成指向新状态，并新增第 12 条把**权限阻塞**写成独立阻断项（原文、退出码、复现时点、最小权限动作、以及"不许读成已验证"） |
| `docs/PRODUCT-NEXT-STEPS-SPEC-2026-10-09.md` | **+10 / −0**（未跟踪文件，无 diff 可比） | §七「剩余完整范围」追记第 5 条：把游戏帧率写进本版交付范围（后端随包 + 两道门 + 口径 + 默认关 + 非 Windows 不支持），并把**权限阻塞**与"冻结包/整进程树开销留 G4 与性能共同门"写成它的验收条件——**取代此前"FPS 与本版无关"的状态** |
| `AGENTS.md` | **+9 / −0**（文件总 +32/−4，其余属其它批次） | Context pointers 新增一条：动 FPS 链路／`resources/presentmon/`／`fps` 成员／两道构建门之前必读什么；并写明**本机真实帧读数未验**、不得把 FPS 数字当已验证 |
| `docs/INDEX.md` | **+2 / −1**（文件总 +7/−3，其余属其它批次） | 「PR 报告存档」登记本文（含"没有任何真实帧数据"的显式警示）；`THIRD_PARTY_NOTICES.md` 行的「何时必读」扩到"把任何第三方二进制随包分发时" |
| `.gitignore` | **+6 / −0**（本批即为该文件全部未提交改动） | 说明块：`resources/presentmon/` 下的二进制是**刻意入库**的（同 `assets/icon.ico` 先例），并指向通知文件与构建门。目录本身不被任何规则忽略，此段是说明而非白名单 |

**方法（可复现）**：`git diff -U0 -- <文件>` 看本批 hunk；未跟踪文件按当前行数计。
共享文件（`AGENTS.md` / `docs/INDEX.md` / `docs/ONEDIR_PACKAGING.md` /
`docs/SETTINGS-CHANGE-GATES.md`）同时含本分支其它批次的改动，上表"本批"一列是**本批加入的那几段**，
与文件总 numstat 的差额属于其它批次，不做合并陈述。

### 2.2 功能其它分工（清单与来源，不在本文作者的验证范围内）

| 段 | 文件 | 来源 |
|---|---|---|
| 后端与探针 | `pet/game_fps.py`、`pet/fps_monitor.py`、`tests/test_game_fps.py`、`tests/test_fps_monitor.py`（写作时点行数 757 / 1159 / 522 / 1100；**同树有并行分工仍在改这几个文件，数字会再变**，本文不复述） | `.scratch/product-game-fps-20261011/HANDOFF.md`（含权限现场、性能实测、设计取舍与已知边界；**该交接的时点早于树的后续改动**，引用其 argv 等具体值前须复核——本文 §5.1 用的是作者自己复现的那条命令行） |
| 设置 | `pet/config.py`（2 个键的常量/默认/归一/reload 白名单/set 归一）、`pet/settings_network.py`（3 行 + 保存回写）、`pet/settings_search.py`（口语别名「帧数」）、`pet/settings_default_marks.py` 快照、`tests/test_settings_game_fps.py`（606 行 / 27 例）、`tests/test_settings_default_marks.py`、`tests/test_settings_copy_lint.py` | 见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 2026-10-11 条；本文 §六 复跑了其中三个测试文件（79 passed） |
| 岛接线 | `pet/island_segments.py`（`FPS` 段 id 与口径注释）、`pet/island_fps.py`（写作时点 603 行：段状态机 + 进程级唯一采集器宿主）、`pet/dynamic_island.py`（订阅/呈现接线） | 同上（设置页真机布局证据由本文作者复跑，见 §五） |

### 2.3 未改动（刻意，避免评审误以为漏了）

- `packaging/dsh-pet.iss`：安装器是**整目录递归拷贝**（`Source: "{#MyAppDir}\*"`），
  资源落进 onedir 产物即随之分发，不需要新增条目。
- `scripts/build_linux.sh` / `scripts/build_macos.sh`：非 Windows 平台**不加载也不捆**
  这个 Windows 后端（由 `tests/test_presentmon_packaging.py::TestOtherPlatformsDoNotBundleIt`
  钉住），产品在那两个平台上整段按不支持呈现。
- `.github/workflows/build-windows.yml`：Windows CI 构建走 `scripts/build_onedir.ps1`，
  两道门自动生效，无需改 workflow（测试里有一条守卫这条调用关系）。
- 根目录 `dsh-pet-standalone-webm-chat.spec`：这是 **PyInstaller 生成物**
  （`.gitignore` 收 `*.spec`、未被任何脚本或 workflow 引用、也不编码 `--distpath`），
  改它对构建没有任何影响；构建真源是 `scripts/build_onedir.ps1`，接线已落在那里。
  **刻意不改生成物**——若维护者希望这份本地生成物也保持一致，请显式说明，我再补。
- 其它 `pet/**`、`tests/**`：本分工的独占范围是打包与文档，**一行未改**（新建的
  `tests/test_presentmon_packaging.py` 是独立打包测试，不改动任何既有测试文件）。

## 三、实现要点（打包与文档这一面）

1. **单一真相源**：期望的文件名与摘要只有一份，在 `pet/game_fps.py`
   （`BACKEND_EXE_NAME` / `REQUIRED_SHA256` / `BACKEND_RELATIVE_DIR`）。校验门
   `import pet.game_fps` 取它们（该 import 链只有 `pet/__init__.py` + `pet/island_segments`，
   标准库，不拉 PySide6）；构建脚本要文件名也走 python 读常量；测试反过来断言门里
   **不存在**这两个常量的定义。
2. **两道门，各挡一类失败**（都在 `scripts/build_onedir.ps1`）：
   - **构建前**：源目录里的文件必须对 → 挡住"换机/升级时拿错文件"；
   - **产物里**：打完包之后按同一判据再验 `_internal\resources\presentmon\` 下那一份 →
     挡住"`--add-data` 的源目录缺失时 PyInstaller 一声不响地不拷"以及"拷坏/被后续步骤删掉"。
   第一道门单独不够：`--add-data` 的语义是"源目录存在就整目录拷"，源不在时构建是绿的。
3. **架构门是产品代码里没有的那一条**：`game_fps.platform_support()` 只看
   `sys.platform`（不查机器类型），而上游 release 的 x64 与 ARM64 是**两个不同文件**。
   校验门因此读 PE 头（`e_lfanew` → `IMAGE_FILE_HEADER.Machine`，零依赖、纯标准库）
   并要求 `0x8664`——**混进 ARM64 二进制在构建期就红**，而不是等用户在 ARM 机器上
   看到一段永远采不到数的读数。
4. **许可随包**：`--add-data` 打的是整个 `resources/presentmon/` 目录，因此
   `LICENSE.txt` 与二进制**一起进产物**（安装器再整目录装到用户机器）——MIT 要求的
   声明随附不靠"仓库里有一份通知文件"。测试断言目录里**只有**这两样，多一个 exe
   就要多验一份。
5. **构建期不联网**：不做 fetch 脚本、不在 CI 下载。理由是仓库的既有处置方式——
   构建必需的二进制**入库**（先例 `assets/icon.ico`：`.gitignore` 里专门放行并注明
   "入库保证克隆后可构建"）。联网取二进制会让干净克隆/CI/离线构建多一个外部依赖，
   且与"hash 已经锁死"相比收益不明。手工取得方式写进了 `ONEDIR_PACKAGING.md`，
   自证命令就是同一道门。
6. **非 Windows / 非 x64 的边界写在文档与测试里**：Linux/macOS 构建脚本零引用
   （文本断言）；`x86-64` 是唯一的架构（文档明写"不要新增 arm64 变体"，测试断言目录里
   没有 ARM 命名的资产）。

## 四、性能分析

**方法（可复现）**：本机 Windows，`python` 3.13.7，`git rev-parse HEAD` =
`7b3fe820…`。命令与样本量逐项标注；打包侧所有数字由本文作者实测。

| 指标 | 实测 | 归属 |
|---|---|---|
| 校验门单次运行（子进程墙钟，n=5） | min **0.163 s** / median **0.167 s** / max **0.187 s** | **新增**（构建期） |
| 其中 sha256 计算（980320 B，n=10） | **0.964 ms/次** | 新增；墙钟其余部分是解释器启动与 `import pet.game_fps` |
| 一次 Windows 构建新增的门成本 | **≈0.33 s**（同一条门跑两次：源码侧 + 产物侧） | 新增；构建本身是分钟级 |
| 新增二进制与许可占产物体积 | **981387 B ≈ 0.94 MiB**（980320 + 1067，磁盘占用，不是常驻内存） | 新增（仅 Windows 产物） |
| 打包面测试 | `pytest -q tests/test_presentmon_packaging.py` → **24 passed / 5.07 s**（含 4 次真跑子进程的门判定） | 新增（测试期） |
| 运行期新增开销 | **0**：没有新增 import、没有新增线程、没有新增定时器；**运行期不校验摘要**（`game_fps` 明确写了不做，理由：每次启动读 980KB 只为一个 CI 该做的事） | 无变化 |
| 采集子进程自身开销 | 未测（本机权限不足以起会话）——**不给数字** | 后端分工的实测项（见其交接；本机测不到的部分照实留空） |

**结论**（逐条回答）：

1. **稳态开销有没有变化**：没有。本批只改构建脚本、文档与新增两个文件；
   产品运行时既不 import 校验门、也不在启动时读那个二进制（运行期不校验摘要，
   这是刻意的取舍，见上表）。
2. **新增路径的绝对成本与触发频率**：构建期两次子进程调用（每次 ≈0.17 s，一次构建一次）；
   打包测试里 4 次真跑（≈0.6 s）。产品路径新增的是"按需起采集子进程"，只在该指标开启且
   有目标时发生，开销数字属后端分工，本机因权限被拒**测不到**。
3. **有没有引入新的系统调用 / 网络 / 磁盘 / 线程**：构建期新增**读一个 981 KB 文件**
   （sha256）；**没有**网络（不下载）、**没有**写入（有测试断言跑完资源目录逐字节不变）、
   **没有**新线程。运行期新增的只有"起一个子进程"，那是后端分工的行为且只在该段开启时发生。
4. **内存与缓存有没有增长**：没有新增缓存；磁盘上多了 981 KB/包（仅 Windows）。
   运行期内存增量归后端分工（其交接给了有界缓冲的口径：行 4096 条、stderr 20 行、
   原因 120 字符、链 8 条 × 每条 240 帧）。

## 五、实机运行记录

**全部为本机真实环境**（Windows，not CI，not mock）。时点逐条标注；命令可直接复跑。

### 5.1 根因/前提的现场复现：普通权限下采集起不来（2026-10-11 12:40:49 +0800）

用**当前产品命令行拼装器**直接起随包后端（不是手写参数，所以复现的就是产品会发的那条命令）：

```
session = dsh-pet-fps-32844-1-7f64db67
argv    = --session_name dsh-pet-fps-32844-1-7f64db67 --output_stdout --no_console_stats
          --no_track_input --no_track_gpu --terminate_on_proc_exit --process_id 32844
exit    = 6        stdout = 0 字节
stderr  =
  warning: PresentMon requires elevated privilege in order to query processes that are
           short-running or started on another account.  Without it, those processes will
           be listed as '<unknown>' and they can't be targeted by --process_name nor trigger
           --terminate_on_proc_exit.
  error: failed to start trace session: access denied.
         PresentMon requires either administrative privileges or to be run by a user in the
         "Performance Log Users" user group.  View the readme for more details.
```

收口：`--session_name <本场> --terminate_existing_session` → 退出码 **7**（本来就没有这场会话）；
`psutil` 扫 `PresentMon*` → **0 个**残留进程。

**结论**：本机（用户 `me`，未提权、不在 `Performance Log Users` 组）**采不到任何真实帧**。
本轮**没有**提权、**没有**改用户组、**没有**装 MSI/服务、**没有**写注册表。

**权限方案已追补为「按需 UAC 独立助手」**（2026-10-11，见 §九）：用户点一次
「授权本次采集」，由 `runas` 拉起一个随包分发的独立小助手去读 ETW——**桌宠本体不提权、
不加 `Performance Log Users` 组、不改注册表、不装服务**。因此本节原先那句「最小权限动作
二选一（加组 / 桌宠以管理员身份运行）」**已过期，不要再照它执行**：加组是不可逆的系统级
改动，整桌宠提权会把桌宠自己（连同插件、聊天、用户配置）一起放进高完整性域。本节的
12:40 复现与官方原文仍然成立（"普通权限下采不到"这个事实没变），变的只是解阻塞的方式。

### 5.2 校验门对真文件的判定

```
$ python scripts/verify_presentmon.py
检查：D:\dsh-pet-src-wt-release\resources\presentmon\PresentMon-2.6.0-x64.exe
  文件名：PresentMon-2.6.0-x64.exe（期望 PresentMon-2.6.0-x64.exe）[OK]
  大小：980320 字节
  sha256：b2a706bc…f1af[OK]
  架构：x86-64[OK]
OK: 帧率采集后端完整（名称 / sha256 / x86-64 三项一致）      # exit 0
```

### 5.3 门的失败路径（真跑，不是读代码）

| 输入 | 退出码 | 判定的问题 |
|---|---|---|
| 同一份文件截断到 100000 B | 1 | `sha256` 不符 |
| 只把 PE 头的 Machine 字段改成 `0xAA64`（文件名仍是 `-x64`） | 1 | `架构不是 x86-64：实际 ARM64` |
| 内容相同但改名为 `PresentMon-2.6.0-x64 (1).exe` | 1 | `文件名不符`（sha256 判 OK，正好证明两条判据各自独立） |
| 不存在的路径 | 1 | `文件不存在或不是普通文件` |

另有断言有效性消融：**临时摘掉** `--add-data "resources\presentmon;…"` 那一行后，
接线用例立刻变红（1 failed）；恢复后文件 `sha256` 与改动前**逐字节相同**。

### 5.4 构建脚本语法（不构建，只解析）

```
$ powershell -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile(<build_onedir.ps1>,…)"
PARSE OK
```

### 5.5 设置页：真实 `windows` 平台插件（**不是 offscreen**）四组合实测

`.scratch/game-fps/real_plugin_layout_probe.py`（2026-10-11 12:39 复跑）——
四种窗口/字体组合下量三行的几何，判据是行不越出视口、滚到底后真的可见、
程序名输入框装得下自己的内容、标签说明不被纵向裁切：

| 组合 | 三行几何（left/width/viewport/可见/高） | 结果 |
|---|---|---|
| 900×760 明色，foreground（输入框置灰） | 1/632/634 visible，128 / 83 / 98 | PASS |
| 900×760 明色，process | 1/632/634 visible，128 / 130 / 145 | PASS |
| 1200×820 暗色，process | 1/932/934 visible，98 / 115 / 115 | PASS |
| 720×560 暗色 + 1.5 倍字体 | 1/452/454 visible，158 / 113 / 128 | PASS |

末行输出 `ALL LAYOUT CHECKS PASSED`（exit 0）。截图脚本
`.scratch/game-fps/settings_capture.py` 同时复跑并重新生成四张图
（`01-light-900-foreground.png`、`02-light-900-process.png`、`03-dark-1200-process.png`、
`04-dark-720-font1.5.png`，2026-10-11 12:40）。

### 5.6 许可与来源的可核验性（离线）

- exe：`sha256` = `b2a706bc…f1af`，980320 B，与 GitHub release API 的 `digest`/`size` 一致。
- `LICENSE.txt`：本地 `git hash-object` = `7ddce0e2636d1f6e0c21cfc0151e552c88062ccb`，
  **等于 v2.6.0 源码树里 `LICENSE.txt` 的 git blob sha**（用 release 的 tree JSON 离线比对，
  不依赖再次联网）。
- `THIRD_PARTY_NOTICES.md` 第 6 节里那段许可正文与随包 `LICENSE.txt` **逐字相同**
  （有测试守卫）。

### 5.7 本批**没有**做的实机验证（不拿沉默当结论）

- **没有构建新包**（"不构建大包"是本次授权边界）：因此
  `sys._MEIPASS` → `_internal` 的真实映射、冻结包里那一份的路径与哈希、
  以及"打包后 sys._MEIPASS 下能解析到后端"**未在真包上验证**。替代证据是
  `tests/test_presentmon_packaging.py::TestFrozenLayoutContract` 用假 `_MEIPASS`
  布局把 `--add-data` 目标目录 ↔ `bundled_backend_path()` 的契约钉住，
  这是**契约证据，不是真包证据**。
- **没有真实 FPS 读数**（§5.1 的权限阻塞），因此没有帧率数值、没有"开关前后桌宠 + 采集
  子进程合计 CPU/内存/线程/句柄"的实机对比数字——后者依赖能真正起会话。
- **没有做原生 GUI 目视**：设置页证据是可跑的几何断言 + 截图，不是人眼验收；
  岛上那一段的呈现依赖 GUI 实测（属岛接线分工，本轮同样受权限阻塞影响）。
- macOS / Linux 未跑（本机就是 Windows），只能给"构建脚本零引用 + 测试断言"的静态证据。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check scripts/verify_presentmon.py tests/test_presentmon_packaging.py` | **All checks passed**（exit 0） |
| 空白/行尾 | `git diff --check -- <本批全部文件>` | exit 0（仅 `docs/INDEX.md` 的 LF→CRLF 提示） |
| 打包面聚焦 | `python -m pytest -q tests/test_presentmon_packaging.py` | **24 passed / 5.07 s** |
| 打包相关集 | `pytest -q tests/test_presentmon_packaging.py tests/test_frameseq_bundle_gate.py tests/test_bundle_slim.py tests/test_ci_workflows.py tests/test_architecture.py` | **161 passed / 11.26 s** |
| 设置面（本文档所述契约的机器证据） | `pytest -q tests/test_settings_game_fps.py tests/test_settings_default_marks.py tests/test_settings_copy_lint.py` | **79 passed / 26.39 s** |
| 构建脚本语法 | PowerShell `Parser::ParseFile` 解析 `scripts/build_onedir.ps1` | **PARSE OK** |
| 断言有效性 | 摘掉 `--add-data` 行重跑接线用例 | **1 failed（红）**；恢复后逐字节一致 |
| 文档纪律 | `pytest -q tests/test_pr_report_discipline.py` | **119 passed / 1.70 s**（本文含三个必备章节且已在 `docs/INDEX.md` 登记，由该文件逐条校验） |
| **本批最终相关集（一次跑完，收尾时点）** | `pytest -q tests/test_presentmon_packaging.py tests/test_pr_report_discipline.py tests/test_frameseq_bundle_gate.py tests/test_bundle_slim.py tests/test_ci_workflows.py tests/test_architecture.py tests/test_settings_game_fps.py tests/test_settings_default_marks.py tests/test_settings_copy_lint.py` | **359 passed / 43.20 s / 0 failed** |
| 全量 | `python -m pytest -q` | **未跑（刻意）**：本批只动打包脚本与文档 + 两个新文件；同树有并行分工在改 `pet/**`，此刻的全量结果会混入它们的中间态。全量归父级收口时跑，基线以届时为准 |

## 七、已知限制与后续

1. **真实帧读数未验 = 本功能最大的一条**（不是"暂时没测"，是**权限阻塞**）。
   解阻塞方式 = **按需 UAC 独立助手**（2026-10-11 追补，见 §九）：用户点「授权本次采集」后
   助手以管理员令牌读 ETW，桌宠本体不提权、不加 `Performance Log Users` 组。
   **UAC 安全桌面由用户本人确认**，工具不自动点同意——因此真实提权链路与任何 FPS 数字，
   本报告一条都不给。
   解阻塞后的验收步骤（起一个受控呈现窗口、切前台、暂停/关窗看状态变化、与
   `--output_file` 的同一段 CSV 按同一口径复算）已写在后端交接 §6。
2. **冻结包未验**：新候选包未构建（授权边界内不做）。构建时必须看到两道门都过，
   并在真包里确认 `_internal\resources\presentmon\` 有 exe 与 `LICENSE.txt`。
3. **二进制是否入库待用户拍板**：本轮**未执行任何 `git add`**。按仓库既有先例
   （`assets/icon.ico`）它应当入库——否则干净克隆与 CI 的 Windows 构建会在第一道门
   就红（这是**刻意的响**，不是缺陷）。若不打算入库，必须同时改掉构建门与
   `tests/test_presentmon_packaging.py` 的跳过口径，并接受"干净克隆打不出带 FPS 的包"。
4. **架构判据**（integration 批已补）：产品层原本只看 `sys.platform`，Windows on ARM64 上
   会认为"支持"并去起这个 x64 exe。现已加**架构闸门**
   （`game_fps.machine_architecture` / `platform_problem`：读 `PROCESSOR_ARCHITECTURE` /
   `PROCESSOR_ARCHITEW6432`，**不**用会派生 WMI 子进程的 `platform.machine()`），
   ARM64 与其它架构按 `unsupported` 降级、卡片写明原因（"ARM64 未验证"）、设置页文案
   同步说明"Windows x64"。**ARM64 上仍无实机验证**——降级是诚实，不是已验证支持。
5. **`--add-data` 是整目录**：将来往 `resources/presentmon/` 放第二个文件会自动进包；
   当前有测试要求该目录**只有** exe + `LICENSE.txt`，所以新增文件会先让测试红，
   逼一次显式决定（要不要验、要不要随包）。
6. **根 `.spec` 是生成物**（未跟踪、未被引用），本批刻意未改（见 §2.3）。
7. macOS / Linux 的"不捆"只有静态证据（脚本零引用 + 测试），没有真 runner 结果。
8. **因本功能而变旧的计数注释**：integration 批已全部更正。改法是**去掉写死的个数**而不是
   改成"五"——每加一个内置段就要改一遍的计数迟早再变假：`pet/config.py`（`island_metrics`
   默认值注释）、`pet/dynamic_island.py`（`_unavailable_reasons` 注释）、
   `pet/island_segments.py`（GPU 段的"与另三个内置段同规"）、
   `pet/settings_network.py::metric_rows`、`docs/ISLAND-SEGMENTS-EXTENSION.md`（准入口径
   两处，指向 `BUILTIN_SEGMENT_IDS` 而不是个数）。
9. **岛隐藏 / 全屏场景的文案与行为**（integration 批核对）：岛的隐藏只**停采集线程并保留
   订阅**（`FpsSlot.pause`），段被折进 `+N` / 收进细条 / 关掉开关才**退订收口**；桌宠被
   「全屏时自动隐藏」藏起来时**岛仍常驻**（`AppShell._sync_dynamic_island` 的既有语义），
   所以全屏游戏期间读数照常。设置页文案据此只说"开启后才启动采集"，不承诺越权能力。
10. **退出收口已接线并有实测**（integration 批）：`AppShell._teardown_fps_capture` 在
   `aboutToQuit`（正常退出，发官方终止命令）与 `_on_session_end`（关机/注销，**不派生
   任何进程**，issue #111 纪律）各做一次**有界收口**；顺带修掉两个使"有界收口"名不副实
   的缺陷（宿主 `close` 的 join 被前一次 `stop()` 清空线程引用后变成空操作；退出路径的
   join 预算小于一场会话自己的最坏收口）。实测（`probe/exit_teardown_probe.py`，真
   子进程走真收口代码，**把孩子的身份换成长时间运行的 python 进程**——因为本机起不了
   ETW 会话）：旧路径（只退订）调用方 0.0003s 返回、孩子还活着、3.09s 后才被守护线程
   收掉；新路径关机口径 0.022s 返回且**一条进程都不派生**、孩子已死；正常退出口径
   3.067s、派生 1 条官方终止命令（会话名唯一）、孩子已死。**仍未验**：真机上"那场
   ETW 会话是否真被内核随登录会话回收"（无采集权限，代码与报告都如实这么写）。

## 八、风险与回滚

- **影响面**：仅 Windows 构建产物（+0.94 MiB）与构建流程（+≈0.33 s）。产品运行期
  本批零改动：不 import 校验门、启动不读二进制、不开开关不起子进程。
- **开关**：岛指标 `fps` **默认关**（出厂 `island_metrics` 仍为空列表）；关闭／折叠／
  隐藏／退出即停采集；两个进程级键默认 `foreground` + 空程序名（空 = 没有目标）。
- **配置迁移**：两个键都是**新键**，老配置读进来取默认，不写回；没有删除任何键，
  没有旧键/旧入口/旧别名的去向问题。
- **落盘残留**：无。本批没有新增任何落盘状态（没有缓存、没有会话文件、没有注册表）。
- **回滚**：`git revert` 本批（或撤掉 `resources/presentmon/` + 还原
  `scripts/build_onedir.ps1` 的三处）后：构建回到"不捆后端"的旧状态，此时产品**不会崩**，
  那一段按"缺少内置采集程序"呈现（这正是构建门存在的原因）。回滚后需同时撤掉
  `docs/INDEX.md` / `PRODUCT-STATUS` / `SETTINGS-CHANGE-GATES` 里对应的表述，
  以免文档继续声称功能可用。`resources/presentmon/` 留在树里无害（不被任何代码加载），
  但它是一份 981 KB 的第三方二进制，回滚时应一并清理。

## 九、追补（2026-10-11 下午）：按需 UAC 独立助手的打包接线与校验

> 本节是**同一交付的追补批**，作者与 §一–§八 不同（同一工作树、同一分支，未构建新包）。
> 它做两件事：① 把权限方案从"加组 / 桌宠提权"改成**按需 UAC 独立助手**并作废早先那条建议
> （§5.1 与 §七.1 已就地更正）；② 把原生助手的**构建与校验**接进 Windows 打包脚本，
> 并让产物校验在 `-SkipBuild` 下**照样执行**。**本批没有构建任何包、没有部署、没有跑全量**。

### 9.1 权限方案（取代早先的建议）

| | 早先（本篇 §5.1/§7 原口径） | 现行（本批） |
|---|---|---|
| 解阻塞方式 | 把用户加进 `Performance Log Users` 组，**或**桌宠以管理员运行（后者本篇不采用） | **按需 UAC 独立助手**：设置页「授权本次采集」→ 主进程确认 → `runas` 拉起随包助手读 ETW |
| 桌宠本体 | 若选第二条会被整体提权（连同插件/聊天/用户配置） | **永不提权**（助手清单是 `asInvoker`；只有用户点 UAC 那一下会提权那个小助手） |
| 系统改动 | 加组是系统级、不可逆 | **不改组、不装服务/计划任务、不改注册表**；关功能/退出即退出助手，不保留跨重启权限 |
| 弹 UAC 的时机 | — | **只有用户点那一个操作**：开关、开机恢复、切目标、隐藏/显示、暂停恢复、重试退避都不弹；UAC 上点"否"= 取消，不重试不循环弹 |

**仍然成立的事实**（本节不推翻 §5.1 的实测）：本机普通权限下官方程序起不了 ETW 会话
（`access denied`，退出码 6），**本机从未执行过 `runas`**，因此**没有任何真实帧数据**。

### 9.2 本批文件（改了什么 + 为什么）

| 文件 | 行数 | 说明 |
|---|---|---|
| `scripts/verify_fps_helper.py` | **新增 508 行** | 助手随包完整性硬门：本体 ↔ 身份元数据 ↔ **内嵌 PresentMon 摘要**三者自洽；判据全部来自 `pet/fps_elevation_transport.py` / `pet/game_fps.py` / `pet/fps_elevation_protocol.py`（门里不写第二份字面量），零 Qt、不写盘 |
| `tests/test_fps_helper_packaging.py` | **新增 646 行** | **44 条**：资源本体 / 嵌入摘要一致性 / 门有牙（11 种篡改 + 只有 `--self-test` 能抓的一条）/ 构建接线（含 `-SkipBuild` 的 PowerShell AST 结构断言）/ 冻结布局契约 / 文档登记 |
| `scripts/build_onedir.ps1` | `+43 / −0` | 助手编译（`-SkipBuild` 时跳过）+ 源产物校验 + `--add-data "resources\fps-helper;…"` + **产物内校验（在 `if (-not $SkipBuild)` 块之外）**。与 `--add-data` 相关的行都不含第二个文件名字面量（名字从产品常量取） |
| `docs/ONEDIR_PACKAGING.md` | 本批新增 41 行一节（文件累计 `+152 / −2`，含同日另一批的后端一节） | 「按需 UAC 采集助手：`resources/fps-helper/`」：谁产出它、三道校验收在哪、判据为什么不是"exe 在不在"、未签名/未提权/未验证边界；冒烟清单加两条 |
| `docs/SETTINGS-CHANGE-GATES.md` | 本批新增 16 行一条（文件累计 `+125 / −1`） | 新的权限模型条目（含"**不持久化已获权限**""设置侧接线属整合批、当前文案尚未改"） |
| `.gitignore` | 本批 +7（文件累计 `+13`） | 说明 `resources/fps-helper/` 是**刻意入库**的产物（同 `resources/presentmon/` 先例） |
| `docs/INDEX.md` | 本批 2 行行内改写（文件累计 `+8 / −4`） | `ONEDIR_PACKAGING` 与 FPS 报告两行补上助手的门与边界 |
| `AGENTS.md` | 本批把游戏帧率指针那段 10 行改写为 20 行（+20 / −10；两段都在未提交的同一棵树上，相对 HEAD 都算新增，文件累计 `+44 / −5` 里另有同日另一批） | 指针改为"按需 UAC 助手"口径，并把"加组 / 提权"的旧建议标为已取代 |
| `docs/PRODUCT-STATUS-2026-10-09.md`（未跟踪） | 193 行，本批改 4 处 | 权限模型、三端 push 许可 = **已授权（待执行）**（三处） |
| `docs/PRODUCT-NEXT-STEPS-SPEC-2026-10-09.md`（未跟踪） | 281 行，本批改 3 处 | 授权边界补 fork/验证分支 + 手动 CI；FPS 阻塞的解阻塞方式改写 |
| `docs/PR-REPORT-GAME-FPS-2026-10-11.md`（未跟踪） | 333 行，本批 `+49 / −9` 左右 | 本节 + §5.1/§七.1 两处就地更正 |
| 产物 `resources/fps-helper/**`（未跟踪） | 2 个文件 | 原生侧产出，**本批只读并锁定**（值见 §9.4），没有重新编译、没有改动 |

`git status` 本批前后都是**未提交**状态：本批**没有** `git add` / `commit` / `push` / 远端动作。

### 9.3 判据：为什么不能只判"exe 在不在"

助手把 PresentMon 的 980 320 字节**嵌在自己的 RCDATA 里**（运行期不读
`resources/presentmon/` 的那一份），所以：

- **缺件**不会让产品崩：`--add-data` 在源目录缺失时一个错都不报，运行期只把能力判成
  `unsupported`（用户连"授权本次采集"都点不出来），**界面上完全正常**。
- **换版**同样看不出来：助手里嵌的是别的版本后端时，**普通权限路径**（子进程跑随包后端）
  与**提权路径**（助手跑内嵌后端）会按不同版本出数——两条路径在界面上无从区分。

所以本批的门判的是**三者自洽**：`助手本体` ↔ `身份元数据` ↔ `内嵌后端摘要 == 实际随包
PresentMon 的 sha256 == pet/game_fps.py::REQUIRED_SHA256`。其中"内嵌摘要"有两层证据：
元数据里固化的值（可被篡改），以及 `--self-test` **真跑一次助手**读它**实测**出来的值
（不可被元数据篡改，见 §9.4 的对照实验）。门**不锁某个具体哈希**——助手重新编译后哈希
会变，锁的是"包内这三份东西自洽"，这样原生侧重建不会把门弄红。

### 9.4 实测证据（命令 + 输出，全部本机真跑）

**(a) 门对真产物判 OK**（`--self-test` 会真跑一次助手自检：不连管道、不核父进程、
不释放资源、不碰 ETW、不采集，因此可以在构建管线里跑）：

```
$ python scripts/verify_fps_helper.py --self-test
检查：D:\dsh-pet-src-wt-release\resources\fps-helper
  助手：1327104 字节  sha256=c6dea0e7…f3e8[OK]
  架构：x86-64[OK]  清单：asInvoker, uiAccess=false[OK]
  签名：NotSigned（signed=False）——未签名候选，UAC 会显示未知发布者
  内嵌后端（元数据）：b2a706bc…f1af  实际随包后端：b2a706bc…f1af[一致]
  助手自检：result=PASS  实测内嵌 sha256=b2a706bc…f1af  heartbeat=5000ms[OK]
OK: 采集助手与身份元数据自洽，且内嵌后端与随包后端同版本      # exit 0
```

**(b) 本批锁定的当前产物（改前改后都没动过它们）**：

| 项 | 值 |
|---|---|
| `resources/fps-helper/dsh-pet-fps-helper.exe` | 1 327 104 B，sha256 `c6dea0e74b22f7630237d6a5445cc39027e20fe23d47d888d2b057e76371f3e8` |
| `…identity.json` | 7 836 B，sha256 `a3b83f03de270a2372f3c18aa6280f5a071a74229c28173598a89260f2c322ba`，`built_at_utc=2026-10-11T06:48:26Z` |
| 内嵌后端 | `PresentMon-2.6.0-x64.exe`，980 320 B，sha256 `b2a706bc…f1af`（= `REQUIRED_SHA256`） |
| 助手自检原始输出（关键行） | `backend.sha256 == backend.sha256_expected`、`backend.ok=1`、`protocol.codec_tests=51 codec_failures=0`、`result=PASS`（exit 0） |
| **与传输层报告的 hash 对账** | `TRANSPORT.md` 引用的是更早一次构建（`11ac220d…`，1 325 568 B，`built_at 06:42:04Z`），当前产物是 `c6dea0e7…`（06:48:26Z）。**同一个交付里两个 hash 不是矛盾，是两次构建**（本机同源码两次构建逐字节相同）；为免"报告与产物对不上"，本批用**当前**产物重跑了传输层对它的运行期核验：`pytest -q tests/test_fps_elevation_protocol.py tests/test_fps_elevation_transport.py` → **99 passed**（含 `test_real_helper_handshake_over_real_pipe` 用真助手走完 `HELLO→ACK→PING→PONG→CLOSE`、`test_real_pipe_round_trip_with_same_logon_client`、`test_adapter_drives_the_real_fps_monitor`），即**当前这份产物能通过传输层的构建身份核验** |

**(c) 门有牙：11 种"不对的那一份"逐个判红**（真跑子进程看退出码，不看代码；
夹具先自证为绿，再逐个变异）：

| 变异 | 退出码 | 门指出的问题 |
|---|---|---|
| 助手截断到 100 000 B | 1 | `sha256 与身份元数据不符`（两者不是同一批产物） |
| 助手改名（内容不变） | 1 | `助手本体缺失`（产物只认一个名字） |
| 元数据 `exe` 指向别的文件名 | 1 | `元数据里记的 exe 名不是 dsh-pet-fps-helper.exe` |
| 元数据 `sha256` 改一位 | 1 | `sha256 与身份元数据不符` |
| 元数据 `size_bytes` 改成 1 | 1 | `助手大小与身份元数据不符` |
| 元数据 `schema` 换成别的产品 | 1 | `schema 不是本助手的` |
| 元数据 `signed=true`（状态仍 NotSigned） | 1 | `自相矛盾的签名声明比没有声明更危险` |
| 元数据清单改成 `requireAdministrator` | 1 | `助手必须不自称提权（runas 由用户明确触发）` |
| 元数据里的内嵌后端摘要换成别的值 | 1 | `内嵌后端的摘要与实际随包后端不一致` |
| 产物里缺兄弟目录 `_internal\resources\presentmon` | 1 | `随包 PresentMon 后端不在`（**不回落仓库资源**） |
| 显式指一个截断的后端文件 | 1 | `随包后端 sha256 不符`（不是只看文件在不在） |

**(d) 只有 `--self-test` 能抓住的那一条（本批最关键的对照实验）**：把助手内嵌的后端字节
改掉 1 个字节（RCDATA 是逐字节副本，偏移可定位），再把元数据同步成**改后文件**的哈希。
于是元数据面**全对**——schema、哈希、大小、内嵌摘要与实际随包后端——只读元数据这一层
**判 OK**；真跑一次助手自检才露馅：

```
$ python scripts/verify_fps_helper.py --path <改过的包>            # 元数据面：exit 0，problems=[]
$ python scripts/verify_fps_helper.py --path <改过的包> --self-test
  助手 --self-test 没有 PASS（退出码 1，result='FAIL'）
  backend.sha256=c1542f22… != backend.sha256_expected=b2a706bc…  backend.ok=0   # exit 1
```

这就是构建脚本两道门都带 `--self-test` 的理由：**元数据哈希是"自洽性"，不是"二进制里真是
这一版"**——后者只能由助手自己回读内嵌资源算出来。

**(e) `-SkipBuild` 也校验产物（PowerShell AST 结构断言，不靠缩进猜)**：用 PowerShell 自己的
解析器找出顶格的 `if (-not $SkipBuild) {` 块，逐条命令判归属：

```
GUARDS=2
VERIFY=2            # 两道 verify_fps_helper.py 调用
  verify @… guarded_by_skipbuild=False
  verify @… guarded_by_skipbuild=False
BUILD=1 PYI=3
VERIFY_UNGUARDED=2  # 两道都在块外 ⇒ -SkipBuild 照旧校验
BUILD_GUARDED=1     # 编译助手在块内（可跳过）
PYI_GUARDED=2       # PyInstaller 在块内（证明找到的确实是"重跑构建"那个块）
SKIPBUILD_SAFE      # exit 0
```

**(f) 构建脚本语法 + 静态检查 + 聚焦/相关集**：

| 门 | 命令 | 结果 |
|---|---|---|
| PowerShell 语法 | `Parser::ParseFile(scripts\build_onedir.ps1)` | **PARSE OK** |
| 静态检查 | `python -m ruff check scripts/verify_fps_helper.py tests/test_fps_helper_packaging.py` | **All checks passed** |
| 本批聚焦 | `pytest -q tests/test_fps_helper_packaging.py` | **44 passed / 8.17 s / 0 failed** |
| 传输层对当前产物的运行期核验 | `pytest -q tests/test_fps_elevation_protocol.py tests/test_fps_elevation_transport.py` | **99 passed / 5.42 s**（含三条真机用例，见 §9.4(b)） |
| 打包与文档相关集（逐文件） | `pytest -q` 逐文件跑：`test_presentmon_packaging` / `test_pr_report_discipline` / `test_ci_workflows` / `test_architecture` / `test_settings_copy_lint` / `test_settings_game_fps` | **24 / 119 / 50 / 15 / 3 / 72 passed**；与上面那份合计 **327 passed / 37.30 s / 0 failed**（一次跑完） |
| 全量 | `python -m pytest -q` | **未跑（刻意）**：同树另有并行写者，此刻的全量结果会混入它们的中间态；全量归父级收口时统一跑 |

### 9.5 未验证与边界（硬边界，别读成已验证）

1. **真实 UAC 提权、ETW 会话创建、真实 FPS 读数、提权下的受保护释放成功分支 / job 收口 /
   硬杀后的 ETW 残留**：全部**未验证**。UAC 安全桌面必须由用户本人确认，工具不自动点同意；
   本机从未执行过 `runas`。
2. **未签名**：助手是本地构建候选，`Get-AuthenticodeSignature` 实测 `NotSigned`，UAC 会显示
   "未知发布者"。不创建、也不信任自签证书。**元数据哈希不是签名**：它与 exe 同在**可写的
   便携目录**里，能写这个目录的人可以在核对之前把两者一起换掉——本门减少置换窗口，
   **不宣称绝对安全**。
3. **协议契约与 Python 层的 DACL 分歧仍是实机待核**：契约
   （`native/fps_helper/protocol.md` §1）建议父进程把管道 DACL 写成 `user_sid:(RW)+SYSTEM:(RW)`，
   Python 层实际收紧为**只授权当前 logon SID**（不含 SYSTEM）。UAC 分裂令牌下两者是同一
   登录会话、理论上仍连得上，**但真实提权下从未联调**。这一条**只作为"待核"记录，不算已解决**
   （写文档不等于验证），也**不因此放宽任何权限**；真实提权联调时若助手连不上管道，先看诊断里的
   `logon_sid` 与 `CreateNamedPipeW` 错误码。
4. **本批没有构建包**（授权边界：不构建整包、不部署）：冻结包里
   `_internal\resources\fps-helper\` 的实际路径、`slim_bundle` 会不会动它、真包上两道门的
   实际输出，**都未在真包上验证**。替代证据是"`--add-data` 目标 ↔ 运行期
   `default_helper_dir()`"的契约用例（假 `_MEIPASS` 布局）+ §9.4(e) 的 AST 结构断言——
   **是契约证据，不是真包证据**。
5. **本批没有跑 CI、没有跑三端 runner**。`build_onedir.ps1` 现在会**编译**助手，因此 Windows
   构建机需要可用的 VS C++ 工具链（`vswhere`/`vcvars64`/`rc`/`cl`/`dumpbin`）。
   GitHub 的 `windows-2022` 镜像通常自带 VS2022 C++ 工具链，但**本机没有跑过 CI，不写成已验证**；
   首次跑 CI 时若 Windows job 在这一步红，先核工具链定位（`-SkipBuild` 可复用入库产物，
   但**它不能产出新包**）。
6. **助手是常驻进程**（授权期间包括暂停采集时）：不承诺零开销/零进程；空闲 CPU 与内存数字
   见原生报告（本批未复测）。
7. **设置侧的「授权本次采集」操作与文案接线不在本批**（**当时**口径：该包只登记模型）：
   同日稍后的应用整合批已把这条接线做完——两行控件、（主进程）确认框、状态轮询、
   未授权时卡片补可行动的一句，全部落地；**现行状态以 §十 为准**，本条的"不在本批"
   只描述当时那一刀。指标行里"首次使用可能需要在系统里授予相应权限"这句**仍在**
   （`pet/settings_network.py` 的 `island_fps` 行）：普通权限机器本来就照常出读数。

### 9.6 回滚（本批）

撤掉 `scripts/verify_fps_helper.py` + `tests/test_fps_helper_packaging.py`，还原
`scripts/build_onedir.ps1` 的四处（编译调用、源校验、`--add-data`、产物校验）即可：构建回到
"不捆助手"的旧状态，产品**不会崩**（运行期判成 `unsupported`）。文档侧要同时撤掉/回改
`ONEDIR_PACKAGING.md`、`SETTINGS-CHANGE-GATES.md`、`INDEX.md`、`AGENTS.md` 里对应表述，
否则文档会继续声称这条权限路径可用。`resources/fps-helper/` 留在树里不被任何代码加载（无害），
但它是两份共约 1.3 MB 的产物，回滚时应一并清理。

## 十一、追补（2026-10-12）：权限模型改为一次性加入 `Performance Log Users` 组（取代 §九、§十）

§九、§十描述的「按需 UAC 独立助手」已**整体归档**：`native/fps_helper/**`、
`resources/fps-helper/`、`scripts/{build,verify}_fps_helper.*`、`pet/fps_elevation_*`、
`pet/fps_authorization.py` 及其测试移入 `.scratch/product-fps-uac-20261011/archived-uac-helper/`，
`build_onedir.ps1` 与 `app.py` 不再引用。§九、§十保留为历史记录，**其中的接线与随包描述不再代表产品现状**。

- **为什么换**：常驻提权进程 + 自产未签名原生程序 + 跨进程授权协议，维护面与安全面远大于
  "让普通账户能读 ETW"这件事本身；官方本来就给了 `Performance Log Users` 这条正路。
- **现在怎么做**：`pet/fps_permission.py` —— 按 SID `S-1-5-32-559` 判定/加组（不依赖系统语言）；
  当前用户取进程令牌 SID（不信环境变量），严格校验后才进脚本；两层 PowerShell 用系统目录绝对路径、
  `-EncodedCommand`；管理员脚本带执行期限；已是成员即幂等成功；仅原生 `ERROR_CANCELLED` 算取消；
  组判定用进程内 `CheckTokenMembership`；跨设置进程的「待重新登录」由 `NetLocalGroupGetMembers` 按 SID 查实际组成员。设置页灵动岛帧率段一行 `game_fps_permission`
  （仅 Windows、跟随帧率开关显隐、没有配置键、进程级后台授权任务 + `QTimer` 轮询回填）。
- **审查修复（2026-10-12，astra 盲审）**：原版用 `_ps_quote` 只转义 ASCII 单引号、账户名取自环境变量
  ——弯引号可注入管理员脚本（blocker）；另有裸名 `powershell.exe`、超时不终止提权、所有异常冒充取消、
  SID 子串判定、`whoami` 同步阻塞 GUI、授权任务随窗口关闭失联、待重新登录随窗口丢失。以上按上条修复并补测；
  astra 复审指出设置页是独立进程、内存状态跨不过进程边界，遂改为以账户实际组成员关系为真值（超时后已通过期限检查的加组无法取消，按幂等 + 重新查询收口）。
- **状态口径**：已具备 / 已授权待重新登录 / 未授权。组成员关系只进新登录令牌，
  **"已加入"不说成"已能采集"**。
- **已验**：`tests/test_fps_permission.py`、`tests/test_settings_fps_permission.py`（45 passed）；
  本机令牌 API 真跑返回合法 SID 与 `missing`；生成脚本经 PowerShell Parser 0 语法错误，过期分支真跑退出码 3。
- **未验**：真实提权加组（本机从未执行）、重新登录后的真实 ETW 会话与任何真实帧读数、真实独立设置子进程关闭/重开端到端、新候选包。
- **回滚**：删 `pet/fps_permission.py` 与设置行即可，产品回到"无权限时显示采集原文"的状态，不会崩。
