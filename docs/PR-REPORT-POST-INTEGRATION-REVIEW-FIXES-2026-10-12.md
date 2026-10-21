# PR 报告：#247–#251 集成收口 + 终审修复批（镜像信封/退役回收/代次家族）

> **基线**：`dca44a7`（Merge PR #243）　**分支**：`fix/post-integration-and-pr247-251`　**日期**：`2026-10-12`
> **范围**：44 个文件（实现 18 / 测试 20 / 文档 6）
> **关联**：[`PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md`](PR-REPORT-PRODUCT-INTEGRATION-2026-10-11.md)、五份被集成 PR 各自的报告（CHAT-MARKDOWN / CHAT-TIMELINE-BOTTOM-BLANK / CHAT-TIME-AWARENESS / CHAT-THINKING-WEB-SEARCH / FRAMESEQ-NO-CONSOLE，均 2026-10-12）

## 一、本批做了什么

两条主线：

**A. 集成 PR #247–#251，并修复集成过程本身造成的功能丢失。**
五个 PR 的冲突解决曾整文件覆盖（`--theirs`），导致 #248（聊天底部空白修复）、#249（Markdown 渲染）
在 `pet/chat/widgets.py` 上被 #251 冲掉、`docs/INDEX.md` 回退到旧版（丢失 #243 以来全部登记）、
`pet/quick_chat.py` 丢失 `switch_character`/`request_in_flight`/`_request_presentation_valid` 三个 seam。
本批以补丁级三方合并重做：五个 PR 的功能全部存活且互相兼容（Markdown × 思考面板 × 时间感知共存），
INDEX.md 以 main 为准重新登记五份新报告。

**B. 两份终审（astra F1–F6 + ops X1–X4）逐条核实后的修复。**
核实结论先行：9 项中 6 项确认真实、3 项部分真实（机制对但频率/定位有偏差），0 项幻觉。
「ops v2 曾建议撤回 #243 的 H2/H3/H4」被同渠道最终终审明确否定（H2-V2 递归已消除且正确），不撤回。

| 编号 | 问题 | 修法 |
|---|---|---|
| X1 | 镜像信封判据只在合成数据下成立：真实 `user/message` 无 turn/step 字段（真实桥日志 213 条实证），每条都重新发号并覆盖会话表 → 两个 DSH 实例镜像同一会话时同一回合提醒两次 | 镜像判据只认 `turn/start`；`user/message` 不覆盖已记录的回合身份；测试夹具全部改成真实形状 + 补「A 整封→B 整封越过冷却」回归 |
| X2 | 注入过滤词表过时（只挡 `plugin`，当前 DSH 还有 `agent-instructions`/`skill-catalog`/`skill-invocation`） | 改白名单：`sourceKind ∈ {"user",""}` 才算真人输入（fail-closed） |
| F1 | frameseq clip/worker 进程级钉表 append-only，切角色（新建库）后旧 clip 永久泄漏 | 四步退役协议：停止接收（`_retire_lock`）→ 队列屏障 → worker 在自己线程销毁 → 注销强引用；close 即清显示缓存；库被丢（无 shutdown）时经 `destroyed` 补排回收 |
| F2 | 回合身份只记最新一轮：迟到旧回合起点覆盖新回合记录、跨轮产生第二个完成身份 | `(sessionId, sourceTurn)` 有界绑定表（512）；旧回合重投不推进当前回合；收尾用所属回合的 token |
| F3 | `dsh_state_changed`/`dsh_user_message` 信号无代次（生产路径暂触发不到，加固） | 信号携带发出时代次，接收端统一过 `_dsh_convergence_current` 闸；管理器出口签名不变 |
| F4 | `reasonKind=error` 的回合收敛为 success → 绿点+done 音效+「干完活啦」 | 收敛器分流 error 终态（不产生成功身份）；补呈现链：error 收尾带 source 产出并解本写者锁存（否则被锁存闸吞掉），`_on_dsh_converged_state` 新增 error 分支注入呈现管线（撤忙碌动画/失败口径） |
| F5 | 歌词关闭重开后旧采样冒充新代结果并提前清忙门 | 每次派发捕获不可变令牌随结果信号返回；回调只接受当前在途令牌，不匹配连忙门都不清；`_reset` 作废令牌同时结清忙门 |
| F6 | `started` 在 `send()` 返回前同步发出 → `_started` 的 id 过滤恒命中，停止按钮永不进忙态（100% 必现） | 现代/经典聊天窗改为先生成 request id 再传入 `send(request_id=...)`；快捷气泡改 QueuedConnection（鸭子类型替身约束，见遗留） |
| X3 | 打字机排空期关聊天窗：回复永不落库 + 重开卡忙碌态 | `closeEvent` 先走完成落库路径再 `_reset()`；真流式中关窗的取消路径不变（有护栏测试） |
| 岛墙（用户实机报告） | 关掉岛碰撞 → 宠在岛下方进入边缘探头 → 再开碰撞，墙注册到探头宠身上把它挤出姿态（气泡随之错位）；且停靠细条会注册出直径 44 的怪圆墙 | `island_bridge.sync_geometry` 补回旧 `_wall_active` 两条豁免（停靠细条未悬停探出/几何动画中不设墙）；`sprite_collision.tick` 对 `probe_active` 的 sprite 与静态成员的 pair 进 ignored_pairs（宠-宠不豁免），探头收回后自动恢复 |
| CI-AV | Windows hosted runner（3.11.9 toolcache + PySide6 6.12.0）单进程整跑反复 access violation（崩点漂移三处，main 同环境亦红） | `scripts/ci_shards.py`：收集序四等分、四个独立 pytest 进程（堆状态不跨片积累）；Linux/macOS 保持单进程整跑；`test_ci_workflows.TestWindowsShardRunner` 三条守卫钉住步骤形状与忽略清单同源 |
| X4 | 多 DSH 修复缺真实桥数据验证 | 见「三、实机」节——真实桥日志统计已作为 X1 证据；两个真实例实机跑仍未做（诚实登记） |

另外两笔小的：FPS 权限文案「注销并重新登录后生效」→「注销或重启电脑后生效」（4 处）；
`web_search` 四行接入设置页默认值标记（默认值写入 `_default_chat_data()`，守住「默认值只有一份」的
机器守卫），「深度思考与联网」分组补引导描述。

## 二、修改文件说明

### 实现（18 个）

| 文件 | 增删 | 改了什么 + 为什么 |
|---|---|---|
| `pet/dsh_state.py` | +241/−70 | X1（`_observe_start`：真实形状 user/message 只刷 LRU 不发号不覆盖）+ X2（白名单 `is_human_user_message`）+ F2（`_turn_tokens` 有界绑定表）+ F4（`_TURN_END_ERROR_REASONS` 分流 + error 收尾专属分支带 source、解本写者锁存） |
| `pet/agent_link.py` | +74/−27 | F3（两条收敛信号带代次 + `_dsh_convergence_current` 统一闸，管理器出口签名不变）+ F4 呈现分支（`to_state == "error"` → `notify_dsh_state("error")`）+ 两处过时 docstring 同步 |
| `pet/island_bridge.py` | +16/−2 | 岛墙豁免补回：`sync_geometry` 在停靠细条未悬停探出、几何动画中两种状态不设墙（对齐旧 `_wall_active`） |
| `pet/sprite_collision.py` | +26/−1 | 探头豁免：`_ignored_pairs` 合并宠-宠禁用 pair 与探头×静态成员 pair |
| `pet/frameseq_clip.py` | +237/−31 | F1 退役协议：`_retire_lock`/`retire()`/`retired` 信号/`reap_retired_objects()`/`_on_worker_retired()`；close 清 `_img/_pm`；`_retired_workers` 有界 |
| `pet/library.py` | +36/−4 | F1 库侧：`destroyed` 触发的钉表补排回收（切角色丢旧库路径） |
| `pet/music_lyric_controller.py` | +62/−25 | F5：`_request_seq`/`_inflight_token`/`_pending_token` 取代可变 `_dispatch_generation` 单槽；信号带令牌 |
| `pet/chat/widgets.py` | +203/−59 | #248 恢复（Preferred + showEvent 贴底）+ #249 恢复（Markdown 接线）+ #251（思考/联网面板）+ F6（先取 id 再 send）+ X3（closeEvent 排空期落库 + `_reset`） |
| `pet/chat/legacy_widgets.py` | +13/−1 | F6 同构修复（经典聊天窗） |
| `pet/quick_chat.py` | +13/−4 | 恢复 main 的 `switch_character`/`_invalidate_in_flight_request`/`request_in_flight`/`_request_presentation_valid`（集成误删）+ #251 `_activity` + F6 QueuedConnection |
| `pet/chat/providers.py` | +194/−12 | #251：reasoning_content 分流、检索阶段、按 provider 的思考参数 |
| `pet/chat/web_search.py` | +225/−0 | #251：四引擎检索模块（新文件） |
| `pet/chat/models.py` | +53/−7 | #251：`WebSearchSettings`、ProviderConfig 思考字段、`ChatMessage.reasoning/activity` |
| `pet/chat/ai_settings_page.py` | +103/−3 | #251：「深度思考与联网」分组 7 行 |
| `pet/chat/markdown_view.py` | +76/−0 | #249：Markdown 渲染模块（恢复） |
| `pet/chat/prompt.py` | +43/−2 | #250：时间感知（system 末尾 + 历史用户消息前缀） |
| `pet/chat/service.py` | +11/−1 | #251：activity 信号 |
| `pet/config.py` | +13/−0 | `_default_chat_data()` 补 `web_search` 默认值（默认值标记的可比来源；与 WebSearchSettings 数据类一致）+ #251 密钥卫生 |
| `pet/frameseq_provision.py` | +5/−9 | #247：`_creation_flags()` 补 `CREATE_NO_WINDOW` |
| `pet/settings_default_marks.py` | +5/−0 | web_search 四行默认值路径登记 |
| `pet/settings_page_guide.py` | +1/−0 | 「深度思考与联网」组描述 |
| `pet/settings_network.py` | +2/−2 | FPS 权限文案「注销或重启电脑后生效」 |
| `pet/fps_permission.py` | +2/−2 | 同上（授权结果两条消息） |
| `pet/modern_settings_dialog.py` | +12/−0 | #251：AI 页分组挂接 |
| `scripts/ci_shards.py` | +89/−0 | 新文件：CI 分片执行器（收集序四等分 + 独立进程 + 收集失败即报错） |
| `.github/workflows/pr-test.yml` | +13/−1 | Windows 主套件走分片步骤；Linux/macOS 不变 |
| `pet/file_interpret.py` | +2/−0 | #251：识图链路的 activity 透传 |
| `docs/INDEX.md` | +5/−0 | 以 main 为准恢复全部登记 + 五份新报告入场 |

### 测试（20 个）

新增/更新围绕每条修复的红→绿回归：dsh_state（+259：真实形状夹具 + 15 条新回归）、
mid_attach_done（+74：镜像真链路 + error 两链）、frameseq_clip（+208：退役协议 4 新 2 更新）、
music_lyric（+141：迟到采样守卫 + 重进音乐模式）、chat_subsystem（+237：F6 忙态 3 条 + X3 排空关窗 2 条 +
markdown 共存适配）、agent_link（+124：代次闸 3 条）、quick_chat（切角色断言适配 #250 时间前缀）等。
`test_ci_workflows.py` 新增 TestWindowsShardRunner 三条守卫；`test_chat_subsystem.py` /
`test_island_fps_integration.py` / `test_fps_monitor.py` / `test_dsh_mid_attach_done.py` 五处
慢 runner 竞态加固（裸断言改泵等待、预算放宽——macOS/Windows CI 实测翻车点）。
`test_chat_markdown.py`（+70）、`test_chat_thinking_web_search.py`（+511）、`test_chat_time_awareness.py`（+106）、
`test_frameseq_no_console.py`（+26）为被集成 PR 自带。岛墙修复：`test_island_bridge.py` +2 条（细条/动画不设墙）、
`test_sprite_collision.py` +2 条（探头豁免 + 非探头对照）、`test_island_bridge_velocity.py` 松手断言适配
动画期撤墙口径（成员条目删除或速度归零均满足"不留幽灵速度"）。

## 三、性能分析

- **F1 退役回收**（实机量化探针，30 个真 clip 各上一帧后 close + GC）：改前 `_LIVE_CLIPS=30`/
  `_LIVE_WORKERS=30`/QImage 存活 30（泵到超时也收不回）；改后三项全 0。稳态回放路径零新增
  （回收只在 close/库销毁时触发）；`retire` 走同线程队列 FIFO，不阻塞投递。
- **F2 回合绑定表**：每会话每回合一条 4 元组，容量 512 淘汰；起点/收尾各一次 dict 查找，常数级。
- **X2 白名单**：`sourceKind` 一次成员判断替代一次相等判断，同量级。
- **F3 代次闸**：接收端一次整数比较；信号多带一个 int。
- **F5 令牌**：派发/回调各一次不可变对象比较；删掉了一次代次读改写的竞态面。
- **F6**：UI 侧把 id 生成从 service 内挪到调用点（一次 `uuid4().hex`），无新增路径。
- **X3**：closeEvent 仅在 `_pending_finish_text` 非 None（排空窗口）时多走一次既有落库路径。
- **#249 Markdown**（引用其自测）：渲染+排版为纯文本 3.5 倍（6000 字 26.0 vs 7.5 ms），流式自适应节流
  把超 18ms 拍数 433→55。#250 时间感知：组装 8.6→198 µs/次。
- **岛墙豁免**：细条/动画判断是两次 getattr；探头豁免每 tick 仅在存在探头宠时构造
  O(探头数 × 静态成员数) 的 pair 集合（常态为空、零分配路径不变）。
- 全部改动无新增线程/网络/磁盘/系统调用（frameseq 回收用的是既有线程与事件循环）。

## 四、实机运行记录

- **真实桥日志统计**（`%APPDATA%/dsh-pet-bridge/dsh*.jsonl`）：213 条 `user/message` 的 step/turn
  字段全空、33 条 `turn/start` 全部带 `turn:N`——X1 修复的直接证据基础。
- **红→绿证据**（每条修复均先写失败测试再改产品代码）：F1 四条退役用例改前 4 failed（10s 事件泵
  超时）→ 36 passed；F5 主用例连跑 5 次全红 → 全绿；F6 三条忙态用例 failed → passed；X3 关窗丢回复
  `['提问'] != ['提问','回复全文']` → 落库一致；F4 呈现链用 stash 拔掉 error 分支复红、恢复复绿。
- **邻域回归**：dsh 域 366 passed；frameseq/library 族 109+57+44 passed；music 族 258 passed；
  chat 域 160+177+90 passed；quick_chat/island_chat 37 passed；settings 域 321 passed；ruff 全仓零告警。
- **全量门禁**：见 PR 描述（同 SHA 全量 + 时序族高负载复跑结果）。
- **诚实登记（未验）**：真实 GUI 桌面运行未做（全部证据为 offscreen Qt + 真实事件循环/真实线程）；
  两个真实 DSH 实例镜像同一会话的实机验证（X4）未做——需要装新桥起两个实例；macOS/Linux 无 runner。

## 五、遗留风险

1. F2 绑定表满 512 后被挤出的旧回合再迟到会重新发号（与既有有界记忆取舍同类，已写进文档）。
2. F3 闸门比代次值不比对象身份；`gen=None` 默认值是为兼容同步直调路径（生产唯一 emit 点恒带 gen）。
3. F1：共享预取线程已死时退役不落（回落旧行为，安全方向）；closed clip 的 `start()` 未硬闸（空转
   定时器，不产生新泄漏）。
4. F5 旧用例 `:1705` 偏弱（关了不重开场景可能没走到守卫），建议后续加固；语义变化：被丢弃的结果
   不再清忙门，忙门由作废方结清。
5. quick_chat 的 F6 用 QueuedConnection 而非显式 id（鸭子类型替身约束）；`pet/file_interpret.py:296`
   同型写法未改（`_on_started` 为空体，无用户可见后果）。
6. X3 复用 `_complete_finished` 会带出 `pet_link.success()` 与可能的系统通知（仅在排空窗口关窗时，
   此时回复确实刚完成，判断可接受）。
7. 镜像副本的 `user_message` 输出被丢弃（保持状态机安静的代价；生产侧无第二消费者，行为不变）。
