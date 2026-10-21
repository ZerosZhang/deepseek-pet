# 产品成果台账（当前状态快照，2026-10-11 重写）

> **这是什么**：一份**当前状态快照**——哪些能力已在源码里、哪些已在真机包上实测过、
> 哪些还没做，以及每条结论的证据在哪。**不是** PR 交付报告，**不表示**任何功能已通过最终验收，
> **更不代表三端已通过**。
> **本文件于 2026-10-11 全量重写**：此前版本是多日追加的中途快照，历史过程（各轮红/绿、
> 过期数字、当时的授权口径、当时的写者状态）已完整留存在各自的专项报告与本地交接里；
> 本文件**不再保留**那些中途口径——凡本文件未列的旧数字，以对应专项报告为准，
> **不要**当成当前状态，也不要据此重新调试已经收口的问题。
> **基线**：分支 `release/2026-10-08-candidate`，`HEAD = 7b3fe8209ca622822d8b6807c647602ca7376d03`
> （写此快照时未变）+ 未提交的整树改动（`git status --porcelain` 共 **141** 条：103 改 / 38 新增；
> 其中一条 `docs/PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md` 是另一写者在本批期间新生成的 PR 报告草稿）。
> **未 commit、未 push、未建 PR、未部署新构建**。
> 配套语义基准（下一步应当达到的契约）：[`PRODUCT-NEXT-STEPS-SPEC-2026-10-09.md`](PRODUCT-NEXT-STEPS-SPEC-2026-10-09.md)。

> **增量备注（2026-10-11 晚；不回填上文与 §一 的任何计数——上面的「141 条」是那次快照的时点值，
> 现为 142 条：`103 改 / 39 新增`）**：本轮补完两轮**外部配置变更热应用实证**——包态合成输入
> （喂按桥接 writer 字段构造的合成 JSONL，**不是真实 DSH 会话**）六场景按设计反应，并留下
> **overlay 拓扑下外部改 `agent_link.dsh` 不重应用**这条观察；它已在源码侧被定性为**真缺陷**
> 并做最小接线（`pet/app.py` +25/−1）+ 新增 5 条回归（先 **4 failed / 1 passed**，后 **5 passed**）。
> 因此现有两个候选包——GUI 实测用的 `0ddb5c00…` 与包态输入验证用的 `01f4b99f…`——**都不含**
> 该修复，包态证据要等重新打包。本增量的测试只有聚焦 / 相关集（相关 **1497 passed**，**非全量**）；
> 针对它的两份独立代码审查此时并行进行、**尚未返回**；三端预推仍无人工许可（**未推、未 dispatch**）。
> 摘要、根因与证据索引见
> [`PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md`](PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md) §十一。

## 状态词（本文件统一口径）

- **已实测（真机包）**：在真实 Windows 桌面上、对**具体的候选包**跑过，有命令/输出/窗口证据。
- **已实现（源码）**：代码在树里，有专项报告与聚焦/相关集测试证据；本轮**未重跑**，不等于已验收。
- **部分**：链路的一段已接、另一段未接，或只有静态契约没有消费方。
- **未完成**：没做，或做了但缺关键一环。
- **待裁决**：实现已存在，但语义/默认值需要产品决定，未决定前不对外陈述为缺陷。

## 〇、授权边界（2026-10-11 现行，优先于本文件其余表述）

- **已授权**：本版本的本地开发、测试、构建、本机实机验收；继续收口并做全产品确认。
- **已授权（条件触发）**：本版问题收口**且全产品确认后**，自主 `commit` / `push` / 创建本版 PR，
  不必再等用户上线。**该授权不等于允许提前提交**，也**不包含**合并他人 PR、发布 Release、
  关闭/评论他人 issue。
- **已授权（待执行）**：为跑三端 runner 而**把本候选推到远端验证分支**（fork / 测试分支）的
  `commit` + `push` + 手动 CI。用户已明确授权后续 fork/CI/PR 全权推进，**不再以缺 push 许可阻塞**
  （此前"等人工答复"的口径作废）。执行时仍**不** merge 他人 PR、不发 Release、不传产物到公开
  artifact、不动 upstream main/tag；三端真跑仍以"跑过什么就写什么"为口径。
- **本版之后另立**：作者的 `phase3-worker` DLC 分支评估（精确远端地址与 SHA 只留在本地交接
  `.scratch/product-release-continuation-20261009/HANDOFF.md`），独立工作区、下一版，不混入本版 PR。
- **禁止**：覆盖他人脏文件、改用户配置/注册表/系统、读用户真实桥目录当端到端证据。

## 一、当前机器与真机证据（唯一可引用的"最新"）

| 证据 | 范围 | 真实结果 | 报告（仓库相对路径） |
|---|---|---|---|
| 机器门：**最近一次覆盖到 close 增量的全量** | 558 文件冻结树（既有全产品 + close 增量） | 主套件 **6312 passed / 13 skipped / 0 failed**（941.61s）+ 扇出 **30 passed** = **6342 / 13 / 0**；ruff、diff-check、node 检查全 exit 0；NO-DRIFT；源 digest `1ea59288…` | `.scratch/product-close-approved-machine-gate-20261011/REPORT.md`、同目录 `GATES_DONE.json` |
| 增量 A：单宠关闭入口 + 坏档案文案 | `pet/overlay_shell.py`、`pet/app.py`、`pet/sprite_menu_facade.py` + 3 个测试文件 | 相关集 **277 passed**；外围再一轮 **202 passed**；隔离副本消融 **7 failed**（先红后绿，未回退真树）；ruff / diff-check exit 0 | `.scratch/product-single-close-entry-20261011/REPORT.md` |
| 增量 B：DSH 中途挂载完成提醒 | `pet/agent_link.py`、`pet/dsh_state.py` + 2 个测试文件（新增 1） | related 11 文件 **407 passed / 1 skipped**；focused **50 passed**；探针 25/25 + 收口 4/4；ruff exit 0 | `.scratch/product-dsh-midattach-fix-20261011/REPORT.md` |
| 增量 C：三端 CI 最小接线 | 4 个 workflow + 2 个 build shell + 新素材供给入口 + 2 个测试文件 | 相关集 **481 passed / 1 skipped**；新测试先红（31 failed / 11 passed）后绿；真素材门 106 clip PASS、零转换 | `.scratch/product-three-platform-gates-20261011/REPORT.md` |
| 独立代码审查（两份，互不代签） | close-flow 增量 | 两份均为**代码层 PASS**；**发布层仍是 CONDITIONAL**（新包构建、GUI、安装器、三端等发布证据各自独立） | `.scratch/product-final-review-*/REVIEW-CLOSE-FLOW-GLOBAL-FINAL.md`、`.scratch/product-settings-discard-final-20261011/FOLLOWUP-CLOSE-FLOW-GLOBAL-FINAL.md`（精确目录名见本地交接） |
| 真机 GUI（对候选包） | 候选包 exe `0ddb5c00…` | 设置"保存失败/代次过期"四出口真点；子泡点击开快速对话且 netstat 零连接；坏 slot0 档案字节未动、修好免重启恢复；托盘正常退出 + 重启恢复；实验进程全部正常退出、未碰用户实例 | `.scratch/product-close-approved-gui-20261011/REPORT.md` |
| 性能（源码态基线） | 1/3 宠 × 岛指标关/开 × 3 轮，12 次实测 | 12 次全部 exit 0、源 hash 前后一致；数字与口径修订见报告 §0.1 / §2.5 | `.scratch/product-perf-20261010/PERF-COMMON-GATE-REPORT-2026-10-10.md` |
| G2 提醒承载与事件身份（源码态） | 事件摄入账本 + 承载迁移 + 隐藏期新请求 / pending / resolved 唯一匹配 | 五文件 **51 passed**；承载按同 event ID + 剩余 TTL 迁移；身份账本有界 512 / 900s；resolved 唯一匹配经独立复核 CLOSED | `.scratch/product-g2-alerts-final-20261010/REPORT.md`、`.scratch/product-g2-events-final-20261010/G2-EVENT-DELIVERY-REPORT.md`、`.scratch/product-final-review-*/REVIEW-FOLLOWUP3.md` |

**关键覆盖边界（不得省略）**：本版历史上**跑过多次全量套件**，表中那一行只是**最近一次覆盖到
close 增量**的机器门（冻结窗口 2026-10-11 02:37–02:55），覆盖的是"既有全产品 + close 增量"那一棵树；
**此后的三个增量 A/B/C 都晚于该冻结点**，目前只有各自的相关集证据——**已跑过的全量（含更早那些次）都不包含它们**。
两份独立代码审查票同样只覆盖到 close 增量：**"新增量已通过审查"与"最新树已全量通过"都不成立。**
（另：候选包 `0ddb5c00…` 也不含 A/B/C 三个增量，见 §三.3。）

## 二、能力现状快照

| 域 | 现状 | 说明与证据 |
|---|---|---|
| 灵动岛（主信息段 + 系统段 + 折叠） | **已实现（源码）** | 时间/余额/峰谷定宽与 CPU/内存/网络同屏；S1–S4 收缩 + `+N` chip；告警两级 + 滞回；状态点五态。聚焦证据见 `.scratch/product-island-extensions-20261010/REPORT.md` 等 |
| 游戏帧率（灵动岛 `fps` 段） | **已实现（源码）；真实读数未验** | 后端 = 随 Windows 包分发的官方 PresentMon（`resources/presentmon/`，构建期两道门校验名称/sha256/x86-64）；主值口径 = 目标应用的 **Present 帧率**（按 `(pid, swapchain)` 分窗，多链不相加，上屏帧率只进详情）；设置 3 行（指标开关 + 跟随前台 / 指定程序的 2 个进程级键），默认关。设置页真机布局四组合实测通过（`ALL LAYOUT CHECKS PASSED`）。**没有任何真实帧数据**，权限阻塞见 §三.12；证据见 [`PR-REPORT-GAME-FPS-2026-10-11.md`](PR-REPORT-GAME-FPS-2026-10-11.md) |
| 第三方岛段（组件清单→准入→采样→胶囊/卡片→超宽折叠→卸载） | **已实现（源码）** | 整条链已接（`gpu` 段改为真实读数）；契约与约束见 [`ISLAND-SEGMENTS-EXTENSION.md`](ISLAND-SEGMENTS-EXTENSION.md) §八/§九。**缺**冻结包上真实示例组件的实机目视 |
| 设置界面（分类/搜索/已修改标记/默认值/重置作用域） | **已实现（源码）** | 重置作用域按 `SlotRoutedConfig` 类型判定而非实例名；保存失败不关窗、草稿留在控件里。准入/准出见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) |
| 设置表单：代次过期、discard、会话结束收口 | **已实测（真机包）+ 两份代码票 PASS** | 候选包上三出口（继续编辑 / Esc / 放弃并关闭）真点通过，重开为新基线；全局草稿与每表单 Config 隔离。发布层证据另算 |
| 多宠与身份（per-slot 路由、逐只退出、留空、恢复） | **已实现（源码）；单宠入口为增量 A** | 关闭这只 ≠ 退出应用；关最后一只后进程/托盘/壳级服务都在；0 只时托盘给"生成 / 恢复 slot0"。**仍待废除**：`_exit_main_pet` 的"无子宠即 `app.quit()`、有子宠则提升 `_spawned[0]`"语义（规范已裁决废除，尚未实现） |
| DSH 联动（减法后摄入 + 完成/失败语义） | **已实现（源码）；中途挂载为增量 B** | 仅 `turn/end→success` 触发完成提醒；`execution/failed` 不误报完成、免打扰下照常弹。增量 B 把判据从"管线上一状态"换成 live 记录身份，覆盖中途挂载/基线 idle/已 SUCCESS/关开残留四条来向 |
| 媒体与歌词（三源并发、过期采样、标题清洗） | **已实现（源码）** | 网络前提见 [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md)：系统代理/VPN 会让三源全部超时，歌词请求刻意绕过代理 |
| 语音报时（免打扰、抢播、watchdog） | **已实现（源码）** | 三处闸共用 `_quiet_muted()`；占用判据收敛为 `_channel_idle()`；超时自愈走 `stop()` + 清空音源 |
| 天气 / 网络信息 / 免打扰 | **已实现（源码）** | 免打扰四档 + 暂存队列 + 全屏联动；去重口径见 §三.8 |
| 内存与子进程（手动回收、共享采样、无窗子进程） | **已实现（源码）** | Windows 无窗子进程补 `CREATE_NO_WINDOW`；CPU/内存共享采样 |
| 打包与构建门（预转素材硬门、三端 CI 接线） | **部分** | Windows 非 GIF 构建的帧序列硬门已在 `build_onedir.ps1`；mac/Linux 素材门与新素材供给入口为增量 C，**未真跑**。见 [`ONEDIR_PACKAGING.md`](ONEDIR_PACKAGING.md) |
| 旧版右键菜单退役 | **已实现（源码）** | 模板分发机制已删并有防复活守卫；**能力仍在**（布局/显隐/别名/图标覆盖），不称"全删"；经典聊天设置对话框仍在，待清理审计 |

## 三、真实未完成 / 阻断（全部保留，不得被单个族的绿顶掉）

1. **安装包（installer）未构建**：本机只有 Inno 6.2.2，不支持原 ISS 的 `x64compatible`；
   降级到 `x64` 的试包已明确**不是通用交付物**。需要**现代 compiler**——须用户另授权系统安装，
   或在工作区隔离构建新 toolchain。旧 `setup` 不得当发布物。
2. **macOS / Linux 没有本候选的真实 runner 证据**：CI 接线已落盘（手动 `source_ref`、
   记录双 SHA 与工具链、素材 cache key、非 GIF 素材门、Windows 两个变体 AppId 分开），
   **未推送、未触发远端 runner**。真实 OS runner 结果缺失时**不能称三端通过**。
3. **最新包不含最后三个增量**：候选包 `0ddb5c00…` 只到 close 增量；增量 A（单宠关闭入口）、
   B（DSH 中途挂载）、C（CI 接线）**不在该包内**，需下一次构建带上并做最小 GUI 复验。
   桌面装机版本仍是更旧的程序，**本版未复核、未部署新构建**。
4. **全产品功能实机仍缺**：同包新装 / 更新 / 预转 106 素材且无首次转换 / 真实播放器歌词 /
   正常退出 / 资源占用，尚未在最新包上完整覆盖。
5. **真实 DSH 端到端未做**：现有证据是"真实记录形状 + 真实文件 + 真 monitor/manager 链路 +
   真 worker 线程"，**不是真实 DSH 会话**。且桥不落盘 `reason.kind`，`aborted` / `blocked` /
   未达阈值的 `kind=error` 回合仍会被报成"已完成"——治本要桥透传该字段，属**另案**，
   本轮不猜任何取值。
6. **OBS 冻结包复测未做**：源码态实测 WGC 通（透明/动态帧）、BitBlt 99.4% 纯黑不可用并已在设置文案
   明示；**未验**窗口移动/尺寸跟随、Automatic 方式、以及 `auto_hide_fullscreen` 与捕获窗的冲突裁决。
7. **性能共同门只有源码态基线**：绝对预算（门槛）未锁、旧打包基线未跑故**无 before/after、不判回归**、
   长期（小时级）内存趋势未验。**注意 GPU 一项**：GPU 段真实读数**早已在更早的候选包上实机观察**过
   （CPU / 内存 / GPU 三段随负载刷新，GPU 34%→18%→47%，父流程截图确认岛内 `GPU 39%`，
   见 `.scratch/product-candidate-gui-20261010/REPORT.md` §4.3）；**只是性能共同门那一轮没有复核 GPU 读数值**，
   不能写成"GPU 从未核过"。
8. **G2 事件身份与承载：现状已实现**（证据见 §一 表末行），此处只登记真实边界与**唯一的待确认项**：
   - 摄入身份 = `(来源, 会话, 事件名, 源 ID)`，无源 ID 时 = `(来源, 代次, 读取游标)`；账本**有界 512 条 / TTL 900 秒 /
     关监测即清**，**文本不进键**（同文不同事件永远是两条合法事件）。证据
     `.scratch/product-g2-events-final-20261010/G2-EVENT-DELIVERY-REPORT.md`。
     **声音冷却与 60 秒同名节流是另一套用户侧性能节流，既不是身份去重、也不替代身份去重**——
     早期"某族已覆盖"的说法只证明了冷却行为，两者不可混谈。
   - 承载：关闭 / 隐藏 / 屏迁移按**同 event ID + 同剩余 TTL** 交接给新的可见承载宠，不重响、不重新入队、旧副本收掉，
     主位回归不抢回；隐藏期新请求有出口、管理 pending 表有界 256、resolved 恢复按 source/namespace 唯一匹配
     （已由独立复核转 CLOSED）。证据 `.scratch/product-g2-alerts-final-20261010/REPORT.md`。
   - **如实保留的边界（不是待裁决）**：账本只在内存，**不承诺崩溃后 exactly-once**（超 TTL 或被 FIFO 淘汰后仍可能重放）；
     Cursor transcripts 与 OpenCode sqlite 两路各走自己的单调游标循环、**未接账本**（构造上不可重复投递）；
     300ms 防抖窗内的一次重复隐藏会让副本约 0.3 秒不可见（既有语义）。
   - **唯一仍待受影响确认的是最新一个增量**：DSH 中途挂载完成提醒的身份通道（§一 增量 B）——
     它改的是**完成提醒判据**，与上面的摄入身份是两套机制，不要合并成一条。
9. **本版集成 PR 报告：草稿已生成，但未提交、未 push、未建 PR** ——
   [`PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md`](PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md)
   （未跟踪文件；口径"基线 → 当前工作树"，按"已验 / 未验"分栏，未验项在其 §七）。
   对外动作按 §〇 授权边界执行：三端验证分支的 fork/commit/push 与手动 CI **已授权（待执行）**。
10. **DLC 未开工**：作者的 `phase3-worker` 分支评估属**下一版**，本版不混入。
11. **未纳入本版范围**：扫码、pi 支持、多屏弹射限制、余额副标题断行点等属**新 feature 请求**，
    不在本版擅自加入。（游戏帧率原先也列在这一条里「仅问过可行性」，2026-10-11 已由本树实现
    ——现状见 §二，权限阻塞见 §三.12。）
12. **游戏帧率：真实读数未验（权限阻塞，需用户本人授权加组并重新登录才能解）**：整条链路已在源码里实现
    （§二），但**本机普通权限下官方采集程序起不了 ETW 会话**，原文
    `error: failed to start trace session: access denied.` / `PresentMon requires either
    administrative privileges or to be run by a user in the "Performance Log Users" user
    group.`，退出码 6（2026-10-11 12:40 用当前产品命令行复现，原文见
    [`PR-REPORT-GAME-FPS-2026-10-11.md`](PR-REPORT-GAME-FPS-2026-10-11.md) §五）。
    因此**没有任何真实帧数据**，所有读数断言都在替身/纯逻辑层；**不得**把这套测试说成
    "性能/帧率已验证"。**权限方案（2026-10-12 定稿）**：设置页「授予采集权限…」一次性把当前账户加入
    `Performance Log Users`（按 SID，系统弹一次管理员授权窗口，`pet/fps_permission.py`），
    桌宠本体始终普通权限；10-11 的「按需 UAC 独立助手」已整体归档、不随包（见
    [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 2026-10-12 条）。设置行与单测已完成；
    授权窗口必须由用户本人确认，本机**从未执行过加组**：真实加组、重新登录后的 ETW 采集与
    任何真实帧读数**全部未验证**。打包侧只剩后端两道门，**新候选包里的路径与出数未在真包上验证**。

## 四、GitHub 开放对象适用性（8 PR / 13 issue，已分类）

完整台账：`.scratch/product-gh-triage-20261011/SUMMARY.md`（只读核真，**未**评论/合并/关闭/推送）。
"已分类"**不等于**"已修/已合/可关闭"。

- **#234（回合成功结束不弹完成提醒）**：本版已**独立等价实现且更强**（增量 B 覆盖四条来向），
  因此**不为它整段合并 #235**。
- **#235**：仅剩"中途挂载回合静默"子条件与本版同源，已由增量 B 收口；方法上仍是"读取方修复"，
  不采纳其收敛器 error 注入方案（与本版明文契约相反）。
- **#237（merge main + 6 项兼容改动）**：**不整合**——本体混入残缺接线（调用点传了本版不存在的参数、
  引用了不存在的信号），采纳即真崩；其自述与 diff 不一致属"说明与 diff 不符"，不对作者作人身定性。
- **#236（自定义联动示例）**：协议面可用，**示例本身有三处缺陷**（`%APPDATA%` 环境变量不展开、
  轮转责任写反、相对链接少一层）→ **改完再收**。
- **#214（启动 DSH 桌面端）**：已解决（显式入口 + 探测 + 未装提示均已在源码）；`auto` 按用户决定只拉服务。
- **#229 / #211 / #172 / #232**：本版已有更宽实现/existing 覆盖/不同接口/独立变体，均**不整合**。
- **其余 issue**：多数已有实现或属新 feature（如 OBS 场景差异、foobar 无真机、多屏限制偏好），
  逐条留在最终清单核适用性，**本轮不做结论**。

## 五、下一步（可自主继续的部分）

1. **本地可做**：按 §三.3 用含 A/B/C 的树**再跑一次覆盖当前树的全量机器门**（本版历史上已跑过多次全量，
   这里要的是"覆盖当前字节的那一次"，不必重跑历史）；提交前 `git status` 核对未跟踪的新测试文件与脚本一并 `git add`。
2. **本地可做**：最新包构建出来后做最小 GUI 复验——单宠托盘"退出这只"、0 只"生成 / 恢复 slot0"、
   正常退出 + 重启、子泡点击。
3. **已授权（待执行）**：三端验证分支的 fork/commit/push 与手动 CI（§〇）；执行时仍不 merge /
   发 Release / 传公开产物。平行可在本地核对 workflow 与素材门。
   **顺序不变**：先把 FPS 权限路径收口并验收（§三.12）→ 再三端验证分支与 PR → **DLC 最后**
   （独立工作区、下一版）。
4. **需要用户决策**：安装器现代 compiler 的取得路径（系统安装授权 / 隔离构建）。
   （G2 的摄入身份与承载交接**已是现行实现**，不再作为待裁决项；见 §三.8。）
5. **本版收口后**：把已生成的 PR 报告草稿 `docs/PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md`
   核对 `PR-REPORT-TEMPLATE.md` 的三节硬要求（修改文件说明 / 性能分析 / 实机运行记录）后收口，
   PR 描述放摘要 + 链接；`docs/INDEX.md` 的登记由文档写者按新文档入场规则处理。

## 六、交接与相关文档

- **断点与完整证据索引**：`.scratch/product-release-continuation-20261009/HANDOFF.md`
  （`.scratch/` 不入库，含精确的产物 SHA、包路径与后台票编号）。
- **本文档重写说明**：2026-10-11 全量重写，只保留"当前状态 + 证据索引"；历史中途口径
  （旧红名单、进行中快照、当时的写者状态）**已删除**，其原始记录在各专项报告与交接文件里，
  需要追溯请查对应目录，**不要**把旧数字当当前状态。
- 相关：[`PRODUCT-NEXT-STEPS-SPEC-2026-10-09.md`](PRODUCT-NEXT-STEPS-SPEC-2026-10-09.md)（语义基准）、
  [`PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md`](PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md)（本版集成 PR 报告**草稿**，未提交未发布）、
  [`ISLAND-SEGMENTS-EXTENSION.md`](ISLAND-SEGMENTS-EXTENSION.md)（岛段契约 §八/§九）、
  [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)、[`ONEDIR_PACKAGING.md`](ONEDIR_PACKAGING.md)、
  [`DEV-HANDOVER.md`](DEV-HANDOVER.md) §8.2/§8.3（证据格式）、[`ACCEPTANCE_TESTS.md`](ACCEPTANCE_TESTS.md)、
  [`INDEX.md`](INDEX.md)、[`../CONTEXT.md`](../CONTEXT.md)（术语表）。
