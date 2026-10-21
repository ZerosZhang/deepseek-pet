# PR 报告：免打扰语音静音闸 + 音频通道占用收口 + ffmpeg 控制台窗口（2026-10-08 夜 ～ 10-09 凌晨）

> **基线**：`9eedd70~1`（`release/2026-10-08-candidate` 上「终审链收口」三轮之后）
> **分支**：`release/2026-10-08-candidate`（本地专用，不推送）　**日期**：2026-10-09
> **HEAD**：`4a1e796`（2026-10-09 05:16）
> **范围**：10 个提交、14 个文件（实现 6、测试 6、文档 2），`+1354 / −53`
> **关联**：[`PR-REPORT-ISSUE-208-QUIET-MODE-2026-10-07.md`](PR-REPORT-ISSUE-208-QUIET-MODE-2026-10-07.md)
> （本批是那份报告 §3.3「免打扰期间语音也静音」口径变更的落地实现，并补上其后续暴露的
> 音频通道排队家族缺陷）、[`PR-REPORT-RELEASE-CANDIDATE-DEPLOY-2026-10-08.md`](PR-REPORT-RELEASE-CANDIDATE-DEPLOY-2026-10-08.md)
> （本批的构建冒烟与第八轮部署接在该报告之后）、[`PR-REPORT-REVIEW-FIXES-2-2026-10-08.md`](PR-REPORT-REVIEW-FIXES-2-2026-10-08.md)
> （同一分支上紧邻的一批：交付证据写法与消融矩阵口径与本文一致）
> **必备证据章节**见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在
> [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

一个晚上做了三件事，全部落在用户能直接听见/看见的地方：

**① 免打扰期间语音真的不出声**（`9eedd70`、`f04dd02`）。此前落地的是「免打扰只压气泡」，
用户显式开启的朗读照响；产品随后拍板改为**免打扰（含全屏等效）期间不出声**。落地方式是
在音频通道的**三处入口**过同一道闸：`_fire`（合成入口，缓存命中 / 即时合成 / 待补播都经此）、
`_handle_synthesized`（回放出口）、`speak()` 的排队入口（免打扰期间不排队）。判据复用
`window_alerts.quiet_blocked` → `quiet_mode`，**不新增第二套免打扰判定**。语音按**丢弃**
处理而不是补播：14:00 的报时在 15:00 再响没有意义。点击自言自语是交互应答，由调用侧
`speak(..., respect_quiet=False)` 显式豁免，豁免**随队携带**（通道忙时排队不丢口径）。

**② 「合成完成却没起播」导致的语音静默滞留家族收口**（`1f1e457`、`47d5427`、`3bb97e5`、
`49714b7`、`4a1e796`）。这五个提交修的是同一族缺陷，根因一句话：**待播队列的出队口只有
媒体终止事件（EndOfMedia）一处，而「合成完成却没起播」的每一种结局都不产生该事件**——
预合成只记路径、免打扰丢弃、合成失败、已停止，四条路子都会让排在其后的豁免语音无声滞留，
直到被后续偶然事件覆盖。修法是把这个家族一次性收敛：占用判据收敛成
`_channel_idle()`（无合成在飞 ∧ 播放器未接管）一条不变量、出队收口到 `_on_synthesized`
的 `finally`、合成代次作废旧任务、播放那一刻重判接管、回队不盖新。

**③ ffmpeg 转换不再闪终端窗口 + 两处测试隔离**（`22f0150`、`caf1c67`、`9d70d78`）。
`_creation_flags()` 只有低优先级位、漏了 `CREATE_NO_WINDOW`，每次转换都闪出一个默认终端
窗口（开机自启的集中供给时段最刺眼）。另两笔是测试卫生：文件末尾多余空行、碰撞音效延迟
回调跨用例污染。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 免打扰静音三处闸 | `_fire` / `_handle_synthesized` / `speak()` 排队入口共用 `_quiet_muted()`；预合成一并跳过（省一次 TTS 网络请求） |
| 2 | 豁免随队携带 | 新增 `_pending_respect_quiet`，入队置位、出队消费后复位默认值；免打扰期间尊重免打扰的那条**入队即丢弃** |
| 3 | 「不起播即出队」统一收口 | `_drain_pending_speech()` / `_drain_queued_fire()` 两个出队口共用一条判据，收口在 `_on_synthesized` 的 `finally` |
| 4 | 通道真空闲是唯一不变量 | `_channel_idle() = not _busy and not _player_engaged()`；旧判据 `_player_busy`（只看 `playbackState`）无调用方后删除 |
| 5 | 合成代次 | `_synthesis_generation` 每次起合成与 watchdog 释放时递增，worker 回调由闭包带回动身时的代次（信号首参），不符即整条丢弃 |
| 6 | 播放时刻重判接管 | `_handle_synthesized` 两个播放出口在动手播放那一刻再判一次 `_player_engaged()`，被接管就回队不顶播 |
| 7 | 回队不盖新 | 两个回队点都是「槽非空即弃旧」：槽里已有更新的请求时，这次较旧的完成结果丢弃 |
| 8 | watchdog 前移 | `_release_stale_busy()` 提到 `enabled` 判定**之前**（报时关掉、只剩节日提醒/点击自言的组合下，它是唯一的超时自愈入口） |
| 9 | ffmpeg 隐藏控制台 | `_creation_flags()` 补 `CREATE_NO_WINDOW`（与既有低优先级位取或） |
| 10 | 测试隔离两笔 | `tests/test_music_lyric.py` 末尾空行；碰撞用例 teardown 排空延迟音效回调 |

**红线 / 不变量**：

- **气泡语义逐字不变**：免打扰期间的报时/节日**气泡**仍走 `defer_quiet` 进暂存队列，
  退出后统一汇报；被丢弃的只有声音。
- **交互应答免打扰照常出声**（issue #208 口径）：点击自言自语 / 预缓存台词走
  `respect_quiet=False`，且该口径**随队携带**——通道忙时排队不丢豁免。
- **`_fire` 的 busy 门刻意保持「只判合成在飞」**：它是「到点即报 / 立即报时」入口，
  在那里加播放器判据会让同一方法里两条路径（缓存命中直接起播 / 非命中排队）自相矛盾，
  还会把时间敏感的报时推到当前音频播完。
- **`_play_only` / `_play_and_bubble` 自身不加占用判据**：守卫在调用方——回队的语义
  只能由调用方给（报时回 `_queued_fire`、外部播报回 `_pending_speech`）。
- **`_pending_speech` 的形状不变**（仍是纯文本、深度 1 队列）：口径存在并行字段里，
  既有契约与用例原样保留。
- **排队契约的方向**：入口方向是「后来的覆盖前面的」（只留最新一条），回队方向**不许
  倒灌成旧的盖新的**。
- **frameseq 转换参数一行未动**：只加窗口隐藏位（阶段一固化参数来自 FEASIBILITY.md
  的实测坑，禁止改动）。

## 二、修改文件说明

`git diff --numstat 9eedd70~1..4a1e796` 汇总：**14 文件、`+1354 / −53`**（实现 6、
测试 6、文档 2）。以下逐提交给出「改了什么 + 为什么」与该提交的 numstat。

### `9eedd70` fix(voice-chime): 免打扰期间语音报时/节日语音不出声

口径变更的落地：**同一道闸两处落地**——`_fire`（合成入口，缓存命中 / 即时合成 / 排队
补播都经此处，并在**查缓存与合成之前**返回，所以预合成一并跳过，省一次 TTS 网络请求）
与 `_handle_synthesized`（回放出口，覆盖「合成期间才进入免打扰」的那条）。判据复用
`window_alerts.quiet_blocked`，不新增第二套判定。`speak()` 默认 `respect_quiet=True`——
新调用方漏传时是「不出声」，而不是「免打扰期间突然响一声」。设置页三处说明文案同步
（语音报时「启用」行、节日「语音播报」行、免打扰组描述），issue #208 报告补 §3.3，
`docs/INDEX.md` 对应那行同步。

```
1	1	docs/INDEX.md
16	2	docs/PR-REPORT-ISSUE-208-QUIET-MODE-2026-10-07.md
3	1	pet/app.py
2	1	pet/festival_settings.py
2	1	pet/settings_page_guide.py
74	9	pet/voice_chime_service.py
1	1	pet/voice_chime_settings.py
26	0	tests/test_festival.py
5	0	tests/test_settings_page_guide.py
185	1	tests/test_voice_chime_service.py
```

新增 14 例测试（手动与全屏等效免打扰、缓存命中、预合成跳过、合成在飞、退出免打扰后恢复、
交互应答豁免、两处文案同步），先红后绿；分别摘掉三处静音闸做消融，对应主用例各自转红。

### `f04dd02` fix(voice-chime): 排队语音补齐免打扰契约

`9eedd70` 的三处闸遗漏了 `speak()` 的**忙通道排队分支**：该分支只存文本、不存
`respect_quiet`，出队时回落默认 `True`。由此两种错误行为：① 免打扰中点击自言（豁免）
在通道忙时排队，出队时豁免丢失被误静音；② 免打扰中通道忙时节日语音被**排队**而不是
丢弃，免打扰结束后补播一条已过期的提醒。修法：新增 `_pending_respect_quiet`（与既有
`_synthesis_respect_quiet` 同一并行字段模式），入队随文本一起置位、出队消费后复位；
`speak()` 的忙通道分支先过闸——尊重免打扰的那条**入队即丢弃**（与 `_fire` 的丢弃不补播
同语义），豁免的那条把口径随队携带。出队时免打扰状态仍**现读**，所以「入队后、出队前才
开免打扰」照样在出队这一拍被闸丢弃。

```
31	7	pet/voice_chime_service.py
84	2	tests/test_voice_chime_service.py
```

新增 3 例（豁免随队携带 / 免打扰期间不入队不合成 / 入队后出队前才开免打扰仍被闸丢弃），
消融矩阵：摘掉入队闸 → 仅第 2 条红；摘掉携带字段写入 → 仅第 1 条红；保留字段但出队不
消费 → 仅第 1 条红。

### `caf1c67` style(test): 去掉 `test_music_lyric.py` 末尾多余空行

`git diff --check` 报 `new blank line at EOF`。只删这一行，不改其它内容。

```
0	1	tests/test_music_lyric.py
```

### `1f1e457` fix(voice-chime): 免打扰丢弃合成结果时排空待播队列

合成结果因免打扰被丢弃时不起播，就没有 EndOfMedia，而 `_pending_speech` 唯一的出队入口
正是该事件的回调——免打扰期间在飞的那次合成一完成，排在其后的豁免语音（交互应答）就
无声滞留。把出队逻辑抽成 `_drain_pending_speech()`，媒体终止回调与「合成完成但不起播」
路径共用；免打扰丢弃分支在 `return` 前调用它。`error` 分支与 `_stopped` 分支保持既有
行为不变。

```
21	1	pet/voice_chime_service.py
58	0	tests/test_voice_chime_service.py
```

回归测试走真实入口（不手工清 `_busy`、不人工发终止事件）；摘掉丢弃分支里的这次调用，
主用例转红。

### `22f0150` fix(frameseq): ffmpeg 转换子进程隐藏控制台窗口

`_creation_flags()` 只有 `BELOW_NORMAL_PRIORITY_CLASS`，漏了 `CREATE_NO_WINDOW`——
每次转换都闪出一个默认终端窗口（fps 探测走 `imageio_ffmpeg` 内部已隐藏，只有**转换这
一处**直接 `Popen`）。test-first：先断言 flags 含 `CREATE_NO_WINDOW` 转红，补上后转绿；
用例同时锁「低优先级档位不能丢」与「POSIX 返回 0」。

```
8	2	pet/frameseq_provision.py
16	0	tests/test_frameseq_provision.py
```

### `9d70d78` test(overlay): teardown 排空延迟音效回调

`sprite_sound._submit` 用 `QTimer.singleShot(0, ...)` 把播放推迟到下一轮事件循环；碰撞
用例 teardown 不排空时，0.7 音量的碰撞音漏进后序用例的 `play_sound` 打桩
（`collision_toggle` → `per_slot_settings` / `sprite_sound` 顺序跑固定红，单独跑绿，
基线 `main` 同样存在——astra / ops5.5 两路审查独立定性一致）。修法是 teardown 调两次
`QApplication.processEvents()`（回调执行本身也可能再投递事件）。

```
5	0	tests/test_overlay_collision_toggle.py
```

三文件序列 64 passed。

### `47d5427` fix(voice-chime): 「合成完成却没起播」统一在收口排空待播队列

预合成完成只记录 `_precache_path` 就 `return`，既不起播也不产生 EndOfMedia。复现链：
报时点前 60s 预合成在飞（`_busy=True`）→ 用户开启免打扰 → 点击自言（无本地缓存）以
`respect_quiet=False` 入队 → 预合成完成不起播 ⇒ 豁免语音滞留。修法：把「不起播就出队」
收敛到 `_on_synthesized` 的 `finally` 一处——先结算报时排队项（报时优先；它若起了合成，
待播语音会被 busy 门重新入队、豁免随队携带），再在通道未被接管时就地出队。预合成 /
免打扰丢弃 / 合成失败 / 已停止四类结局一次覆盖；静音丢弃分支里上一轮那次出队调用随之
删除，避免双出队路径。

判据用新增的 `_player_engaged`（`PlayingState` **或** `LoadingMedia`）而非已有的
`_player_busy`：实机实测（`QMediaPlayer` + `QAudioOutput`，offscreen）`setSource` 后
立刻 `play()` 那一刻 `playbackState` 仍是 `StoppedState`、`mediaStatus` 才是
`LoadingMedia`（约 300ms 后转 `PlayingState`），而收口正是在那一刻跑——用后者会把刚
接管的通道误判成空出，待播语音当场抢播、掐掉刚起播的那一段。

```
54	14	pet/voice_chime_service.py
173	4	tests/test_voice_chime_service.py
```

回归测试：预合成完成出队豁免语音、预合成完成仍只记路径不播放、失败完成出队、起了播时
队列留给 EndOfMedia，外加 `_player_engaged` 判据真值表；摘掉收口守护后主用例与失败用例
转红，仅换成 `_player_busy` 则起播用例转红。

### `3bb97e5` fix(voice-chime): 占用判据收敛为「通道真空闲」一条不变量

两个 P2 同源：占用判定散在四个调用点、各判各的。收敛成 `_channel_idle()`（无合成在飞
∧ 播放器未接管），两个补播队列的出队口各自内置它：不空闲就原样留队，等下一拍（合成
完成 / EndOfMedia 终止 / 合成超时自愈）再来。

- `speak` / `play_file` 的入口门改用同一判据；换判据后 `_player_busy` 无调用方残留，删除。
- `_fire` 的 busy 门刻意保持「只判合成在飞」（理由见 §一 红线）。
- P2-1：待播语音不再在合成在飞时被 `_fire` 的 busy 门迁进 `_queued_fire`（迁过去就
  离开了 EndOfMedia 出口），也不会在报时刚起播时被补播顶掉。
- P2-2：合成超时自愈释放 `_busy` 后一并结算待播语音（此前只结算报时排队项）。
- `_on_media_status` 的终止态改为排空**两个**队列：被占用判据留过队的报时排队项若不在
  这一拍结算，就要等下一次合成完成（最坏等到下个报时点）。
- `_on_synthesized` 的 `finally` 简化为连续两次 drain（判据已在 drain 内部），调用点不再各自判。

```
80	60	pet/voice_chime_service.py
155	1	tests/test_voice_chime_service.py
```

三处消融（两个 drain 的内置判据、watchdog 的出队调用）各自对应用例转红。

### `49714b7` fix(voice-chime): watchdog 前移 + 合成代次 + 播放时刻重判接管

三个 P2 都出在「状态与任务/时刻不匹配」上，一并收口：

- **watchdog 前移**：`_on_tick` 原来在 `enabled` 判定之后才跑 `_release_stale_busy`，而
  报时关掉、只剩节日提醒 / 点击自言时本服务照样在跑同一个通道（AppShell 的懒创建门控
  支持这种组合）——那时唯一的超时自愈入口永远执行不到，一个不回调的 worker 会永久占住
  `_busy`，通道再也不出声。
- **合成代次**：回调协议只有 path/text/error，没有任务身份，于是超时释放后旧任务的迟到
  回调会取走**新任务**的 role / 免打扰口径 / busy 锁——该被静音的旧提醒出声、应豁免的
  新语音被静音。改为每次起合成与 watchdog 释放时递增 `_synthesis_generation`，worker
  回调由闭包带回动身时的代次（信号首参，worker 仍是三参回调），入口比对不一致就整条
  丢弃，一个字段都不碰。
- **播放时刻重判接管**：合成期间别的音频可以合法起播（报时走缓存例外，该路径不看通道
  占用），而合成完成后的 `_play_only` 会 `setSource` + `play` 把在播的那一段顶掉（音源
  被替换、永远等不到 EndOfMedia）。两个播放出口在动手播放那一刻再判一次
  `_player_engaged()`：被接管就不播、改为回队，等下一拍按既有口径出队。

```
97	16	pet/voice_chime_service.py
233	19	tests/test_voice_chime_service.py
```

回归测试：报时关闭时 watchdog 仍释放并结算队列、迟到回调被丢弃且不碰新任务状态、播放
时刻被接管时回队而不顶播（speak 与 play 两条出口各一）。既有测试的调用点随私有回调签名
更新（补代次实参，**断言未改**）；三个「这次完成起了播」的用例把通道接管改由 `play()`
驱动（真实时序：起播在先、接管在后），断言同样未改。

### `4a1e796` fix(voice-chime): 回队不盖新——槽非空即弃旧完成结果

`_handle_synthesized` 的两个播放出口在「被接管则回队」时是**无条件写槽**。断链：
`speak("older-A", respect_quiet=False)` 起 A 合成 → A 在飞时 `speak("newer-B")` 入队
（深度 1，按契约留最新一条）→ C 经缓存命中起播 → A 完成发现被接管，回队时用 A 覆盖 B
及其旗 → C 结束后出队的是过期的 A，**B 永久丢失**。`role=play` 同型（旧报时完成回队
覆盖 `_queued_fire` 里的新排队项）。两个回队点改为同一语义：槽非空 → 丢弃这次较旧的完成
结果（debug 日志），槽内那条及其旗原样保留；槽为空才回队。判定与写槽都在 GUI 线程的
同一个槽里，没有并发窗口。

```
20	1	pet/voice_chime_service.py
96	0	tests/test_voice_chime_service.py
```

回归测试：speak 出口与 play 出口各一条复现链（断言槽里仍是更新的 B、旧结果不出声、丢弃
留有 debug 日志、C 结束后出队的是 B）；既有两条「槽为空照常回队」的用例保持绿。摘掉
两处「槽非空弃旧」后只这两条转红。

### 未改动（故意）

- `pet/window_alerts.py`：`quiet_blocked` / `defer_quiet` 一字未改——本批是它的**消费方**，
  判据同源是这次改动的核心约束。
- `pet/quiet_mode.py`：免打扰状态机完全没动（没有新档位、没有新配置键）。
- `pet/frameseq_provision.py` 的 `_ffmpeg_argv` / 转换参数：阶段一固化参数禁止改动，
  本批只加窗口隐藏位。
- `pet/voice_chime.py` 的纯逻辑层（`chime_slot` / `build_chime_sentence` / `next_chime_in_seconds`）：
  本批全是通道调度与排队语义，不涉报时判定本身。
- 其它引用 `voice_chime` 的测试文件：测试隔离只修了实测复现的
  `tests/test_overlay_collision_toggle.py` 一处（同族其它文件未甄别，见 §七）。

## 三、实现要点

**1）为什么静音有「三处闸」而不是一处。** 音频通道有三条进入路径，缺任何一条都会漏：
`_fire` 是**合成入口**（缓存命中直接播、非命中起合成、排队补播都经此），`_handle_synthesized`
是**回放出口**（覆盖「合成期间才进入免打扰」的那条），`speak()` 的排队分支是**入队口**
（免打扰期间入队就是「留到免打扰结束后补播」，与丢弃语义相反）。三处共用 `_quiet_muted()`，
它只是 `window_alerts.quiet_blocked` 的取宿主持有者——**没窗口就返回 False**（无 GUI 的
测试替身 / 纯逻辑调用没有全屏避让，免打扰也无从谈起）。

**2）为什么队列字段要「随队携带」而不是出队时现判。** 出队时现读免打扰状态能保证
「入队后、出队前才开免打扰」照样被闸丢弃（这一点确实保留），但**读不出**「这一条当初是
不是豁免的」——交互应答的豁免是调用侧在**入队那一刻**给的语义，必须跟着文本走。

**3）为什么把「不起播就出队」收敛到 `finally` 一处。** 这个家族的病灶是**出队口只有
一个（EndOfMedia）**，而「合成完成却没起播」有四种结局都不产生该事件。逐结局补调用
（`1f1e457` 就是这么修的）能治当下那一处，但下一个新结局还会再漏。收口到
`_on_synthesized` 的 `finally` 之后，**任何**完成路径都会走一次出队；判据（通道是否
空闲）内置在 drain 内部，调用点不再各自判——所以 `finally` 里就是连续两次 drain。

**4）为什么占用判据必须是「无合成在飞 ∧ 播放器未接管」。** 两个子判据各自都有实测的
反例：只看 `_busy` 会漏掉「别的音频正在出声」（补播会顶掉它），只看 `playbackState`
会漏掉「刚 `setSource` 的 300ms 窗口」（那一刻是 `StoppedState` + `LoadingMedia`）。
`_channel_idle()` 是把这两条合成一条不变量，四个调用点（两个出队口 + 两个入口门）都读它。
`_fire` 是唯一例外且刻意（见 §一 红线）。

**5）为什么用「代次」而不是「比对 path」。** 回调协议只有 path/text/error，而
`_synthesis_role` / `_synthesis_respect_quiet` / `_busy` 是**单槽位全局状态**——超时释放
后旧任务迟到回调会取走新任务的口径与锁。path 不能当身份（同一个文本哈希到同一个缓存
路径，新旧任务可能同 path）。代次由闭包在 emit 时补进信号首参随信号跨线程，
`_on_synthesized` 入口比对不一致就整条丢弃——**一个字段都不碰**。

**6）为什么回队要「槽非空即弃旧」。** 排队契约的方向性：入口方向是「后来的覆盖前面的」
（深度 1 队列，只留最新一条），回队方向如果无条件写槽，就变成「旧的盖新的」——
`4a1e796` 的复现链里 B 会被过期的 A 永久顶掉。判定与写槽都在 GUI 线程的同一个槽里，
没有并发窗口，所以不需要锁。

**7）为什么 watchdog 必须前移。** 它是**唯一的合成超时自愈入口**。「报时关掉、只剩节日
提醒 / 点击自言」是一个合法配置组合，此时服务照样在跑同一个音频通道；watchdog 被
`enabled` 短路掉，一个不回调的 worker 就会永久占住 `_busy`，通道再也不出声。前移之后
`enabled=False` 时其余逻辑照旧短路，稳态只多一次 `if not self._busy: return`。

## 四、性能分析

**方法（可复现）**：`python - <<'PY'` 内联脚本，`timeit.repeat(..., number=20000, repeat=3)`
取最优后除以次数（µs/次）；Qt 对象用真 `QMediaPlayer` + `QAudioOutput`（`QT_QPA_PLATFORM=offscreen`），
服务实例用 `object.__new__` 只装本次判据需要的字段（与测试替身同手法）。
环境：Windows 11 / Python 3.13.7 / PySide6 6.11.2，本机 `D:/dsh-pet-src-wt-release`。

| 指标 | 实测 | 归属（热路径 / 新增 / 被替换） |
|---|---|---|
| `window_alerts.quiet_blocked(host)` | **0.384 µs/次** | 既有判据（#208 报告记 0.42 µs，同口径复测一致）；新增的调用点是三处闸 |
| `_player_engaged()`（真 QMediaPlayer） | **4.903 µs/次** | 新增判据：每次出队口与入口门各一次 |
| `_channel_idle()` | **5.071 µs/次** | 新增：= `_busy` 读 + `_player_engaged()` |
| `_drain_pending_speech()` 空队列早退 | **5.095 µs/次** | 新增：三个触发点各一次 |
| `_release_stale_busy()`（watchdog **前移后每拍都跑**） | **0.045 µs/次** | 新增到稳态：tick 周期 20 s |
| `_creation_flags()` | **0.185 µs/次** | 既有路径：每次 ffmpeg 转换一次 |
| `playbackState()` 单判（**被替换**的旧 `_player_busy` 口径） | 0.393 µs/次 | 对照 |
| `playbackState() or mediaStatus()`（新口径的原语） | 1.561 µs/次 | 对照 |
| `from PySide6.QtMultimedia import QMediaPlayer`（模块已缓存） | 2.905 µs/次 | **新增判据里 4.903 µs 的主要构成** |

**结论**：

1. **稳态开销**：唯一新增到稳态的是 watchdog 前移带来的每拍一次 `_busy` 布尔读，
   **0.045 µs / 20 s ≈ 2.3e-9 的 CPU 占比**（且只在 `_busy=False` 时不变量短路）。
   三处静音闸只在**音频事件**上跑（报时点 / 节日提醒 / 点击自言），不是每帧也不是每秒。
2. **新增路径的绝对成本与触发频率**：判据链单次 ≈ 5.1 µs（`_channel_idle`），一次音频
   事件最多触发 4 次（两个入口门 + 两个出队口），合计 **< 25 µs**；与之相比同一条路径
   上的合成是**百毫秒到秒级**的网络 + 编码，播放是秒级音频。触发频率 = 报时点 / 节日
   提醒 / 点击自言，事件级而非定时级。`_player_engaged` 里 4.903 µs 中有 2.905 µs 是
   每次调用都执行一次的**惰性 import 语句**（模块已缓存，只查 `sys.modules`）——这是本
   模块既有的「顶层不 import Qt」纪律（纯逻辑层要能在无 Qt 环境测试）的既定代价，
   与同族方法一致，未单独优化。
3. **有无新的系统调用 / 网络 / 磁盘 / 线程**：**无新增**。反向地，免打扰期间**少了**
   一次 TTS 网络请求（预合成提前返回）与一次缓存写盘（合成结果被丢弃）——实机差分证据
   见 §五 第 1 条（免打扰下 120 秒内 `voice_chime_cache` 零文件变动）。`CREATE_NO_WINDOW`
   不新增系统调用，它把每次转换附带的一次**控制台窗口创建**去掉（实机证据见 §五 第 2 条）。
   没有新线程：`_drain_*` 全是 GUI 线程内的同步调用。
4. **内存与缓存有没有增长**：新增字段全是标量或 None（`_synthesis_generation` int、
   `_pending_respect_quiet` bool、`_synthesis_now` datetime|None、`_queued_fire` 由 5 元组
   变 6 元组），**无缓存、无列表增长、无常驻容器**。`_quiet_muted` 命中时直接返回，
   不构造任何对象。

**测试侧开销**：新增 35 例测试函数（`git diff 9eedd70~1..4a1e796 -- tests/ | grep -c "^+    def test_"`），
集中在 `tests/test_voice_chime_service.py`（7 个提交累计 `+963` 行）。回填时复跑 voice_chime
族 5 文件 **372 passed in 18.86s**（本机 offscreen，见 §六）。

## 五、实机运行记录

部署机（Windows）上的真实环境操作，**非 CI、非 mock**；命令与原始观察如下。

**1）免打扰静音差分（`voice_chime_cache` 文件级证据，主代理亲测）**

- **无免打扰**：菜单点「立即报时」→ `voice_chime_cache` **新增一个 mp3**，文件时间戳
  **02:37:55**（合成 → 写缓存 → 播放，全链路走通）。
- **免打扰**（菜单子项显示「剩余 14:37」）：同样点「立即报时」→ **120 秒内该目录零文件变动**
  （没有新 mp3、没有时间戳变化）。即：预合成被跳过、没有合成网络请求、没有写盘——与
  §四 结论 ③ 的「少了 1 次网络 + 1 次写盘」逐条对上。
- **菜单状态确认**：免打扰子项显示「**15 分钟·进行中**」，并提供「**提前结束**」；
  未开启时该项置灰（菜单结构不随状态变形，与 #208 报告口径一致）。

**2）Windows Terminal 弹窗根治（`22f0150`）**

- **修复前**：每次 ffmpeg 转换闪出一个 Windows Terminal 窗口，窗口标题是 `imageio_ffmpeg`
  的 ffmpeg 路径（即「谁在弹窗」在标题里自证）。
- **修复后**：启动期帧序列首跑供给**完整跑完**（日志 6 轮「新转 0」，即供给侧把该转的
  都转完、后续每轮无新增），全程 **零终端进程**——`tasklist` 过滤 `WindowsTerminal`
  **无匹配**。

**3）第八轮构建冒烟与部署实例**

`scripts/build_onedir.ps1` 冒烟全过（exe 启动 OK / `--settings` 启动 OK），portable
**zip 163.6 MB**；部署实例 **PID 25868**，启动工作集 **170 MB**，灵动岛 **五段渲染正常**。

**4）本机（工作副本）复跑的验证**（回填本报告时执行，非部署机）：

```
$ QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_voice_chime_service.py \
    tests/test_voice_chime.py tests/test_voice_chime_edge_voice.py \
    tests/test_festival.py tests/test_quiet_mode.py
372 passed, 2 warnings in 18.86s
```

（`2 warnings` 是 `pet/persona_phrases.py:122` 的既有 `DeprecationWarning`，与本批无关。）

**边界与失败路径的实机/进程内观察**：

- 免打扰**退出后**恢复发声：合成走即时合成回退路径（预合成在免打扰期间被跳过，
  退出后第一次报时点实测能出声）。
- 交互应答在免打扰期间**照常出声**（点击自言 `respect_quiet=False`），且通道忙时
  排队后仍是豁免——这是 `f04dd02` 修的第 ① 种错误行为，用「真线程 + 真事件」在进程内
  复现（见 §六 消融表）。
- `_player_engaged` 的 `LoadingMedia` 窗口是**实测**到的：`setSource` 后立刻 `play()`
  那一刻 `playbackState == StoppedState`、`mediaStatus == LoadingMedia`，约 300ms 后转
  `PlayingState`——这条实测直接决定了 `3bb97e5` / `47d5427` 的判据选择。

**无法自动/肉眼验证的部分（如实登记，不用沉默代替结论）**：

- 「合成在飞 × 免打扰开启 × 点击自言排队 × 预合成完成」这条**四要素精确交错**没有在
  真机 GUI 上肉眼复现（它要求挂钟、免打扰状态与合成耗时同时对齐）。复现方式改为在
  **进程内**用真 `VoiceChimeService` + 真线程事件把四个要素按序摆出来（`4a1e796` /
  `47d5427` 的回归用例就是这么写的），并以消融证明断言有牙。
- astra / ops5.5 两路审查对 `9d70d78` 的跨用例污染定性一致（顺序跑红、单独跑绿、
  基线 `main` 同型），但它**不是**本批产品代码引入的缺陷。

## 六、测试与验证

| 门 | 命令 / 来源 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | **零告警**（每提交前逐文件跑，收尾全树跑） |
| 聚焦（voice_chime 族） | `tests/test_voice_chime_service.py` 等族内文件 | 逐轮递增 **355 → 370 → 372 passed**（每个 fix commit 都有红→绿 + 消融记录，见各 commit message） |
| 聚焦（回填时复跑） | 见 §五 第 4 条 | **372 passed** in 18.86s |
| 全量（HEAD `4a1e796`，16:42） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **5545 passed, 11 skipped, 0 failed** |
| 全量（中间轮） | 同上，各轮回归 | **5510 / 5524 / 5527 / 5530 / 5535 / 5539 / 5543** 均全绿（逐轮递增，无红） |
| 断言有效性（消融） | 逐条把产品文件回滚到该提交之前重跑对应 focused | 各 commit message 已记录：三处静音闸 / 入队闸 / 携带字段 / 收口守护 / 两个 drain 的内置判据 / watchdog 出队调用 / 代次比对 / 播放时刻重判 / 两处「槽非空弃旧」，**每一项都有一条对应用例转红** |
| 测试隔离修复的判别力 | 三文件序列（`collision_toggle` → `per_slot_settings` / `sprite_sound`） | 修复前顺序跑固定红、单独跑绿；修复后 **64 passed** |
| 回退校验 | `git diff --check`（`caf1c67`） | 文件末尾空行报告消失 |
| 构建冒烟（第八轮） | `scripts/build_onedir.ps1` | exe 启动 OK、`--settings` 启动 OK；zip **163.6 MB** |
| 审查链 | astra **七轮**（前六轮不放行共计 **10 个 P2** 全部核真修复销项，第七轮放行）+ ops5.5 **六轮**（测试隔离 P1 除外全放行，最终轮放行） | 全部销项，最终轮两路放行 |

新增用例 **35 条**（`git diff 9eedd70~1..4a1e796 -- tests/ | grep -c "^+    def test_"`）：
静音闸 14、排队契约 3、丢弃排空 2、ffmpeg 窗口 1、收口出队 5、占用判据 4、代次/接管/watchdog 4、
回队不盖新 2。

## 七、已知限制与后续

- **免打扰期间语音是「丢弃」不是「补播」**：这是产品口径（时间敏感的报时补播无意义），
  与气泡的「攒着退出后统一汇报」刻意不同。若将来产品要改口径，只需把 `_fire` 的
  `return` 换成入队——但要注意入队后出队时 `_quiet_muted()` 会**现读**再丢一次。
- **`_fire` 的 busy 门刻意不判播放器**（只判合成在飞）：这是「到点即报」入口的取舍，
  代价是「正在播别的音频时立刻报时」会排队而不是打断。改判据前先读 §一 红线里的两条理由。
- **`_player_engaged()` 拿不到判据时按「未接管」处理**（QtMultimedia 缺失 / 测试替身）：
  取向是「出队总比滞留安全」，代价是极端情况下可能顶掉一段音频。
- **判据链里有 2.905 µs 是每次调用的惰性 import 语句**（既定纪律的代价，见 §四 结论 ②）。
  若将来这条路径真的变成热路径，正确做法是把 `QMediaPlayer` 的枚举值缓存到
  `_ensure_player`（模块里已有 `_terminal_statuses` 这个先例），而不是改顶层 import 纪律。
- **测试隔离只修了一处**：`9d70d78` 只修实测复现的 `tests/test_overlay_collision_toggle.py`
  的 teardown；同族其它「投递延迟回调 + 打桩」的组合未甄别，同类污染可能仍在别处潜伏。
- **`CREATE_NO_WINDOW` 只治「转换」这一处弹窗**：fps 探测走 `imageio_ffmpeg`（内部已用
  `STARTUPINFO` 隐藏），其它 `Popen` 点不在本批范围。
- **本报告的三条实机证据来自部署机（主代理操作）**，回填时只能复核其中可离线复算的部分
  （§五 第 4 条与本报告自身的 `git log` / numstat 数值）。

## 八、风险与回滚

- **影响面**：全部集中在音频通道 `pet/voice_chime_service.py`（以及它的三处文案与一处
  ffmpeg 标志位）。配置面零改动，菜单/设置页结构零改动。
  - 免打扰静音只影响「免打扰生效期间的语音报时 / 节日语音 / 外部播报」；
  - 占用判据与代次只影响「合成在飞 / 播放中 / 超时自愈」三个时点上的排队与补播决策；
  - `CREATE_NO_WINDOW` 只影响 Windows 上转换子进程的窗口可见性（POSIX 返回 0，行为不变）。
- **开关与配置**：本批**没有新增配置键**，也没有配置迁移。`respect_quiet` 是**代码层**
  形参（默认 `True`），不进配置。
- **回滚**：10 个提交互相独立、可按需单独 `git revert`：
  `9eedd70`（静音闸）/ `f04dd02`（排队契约）/ `caf1c67`（空行）/ `1f1e457`（丢弃排空）/
  `22f0150`（控制台窗口）/ `9d70d78`（测试隔离）/ `47d5427`（收口出队）/ `3bb97e5`（占用判据）/
  `49714b7`（代次与接管）/ `4a1e796`（回队不盖新）。
  回滚后**无残留状态**：本批不写任何持久化字段，唯一落盘产物是 `voice_chime_cache`
  下的 mp3（按「文本+音色+语速+音调」哈希命名，回滚后旧文件仍可命中、不会失效），
  以及 `_synthesis_generation` 这类进程内计数器（随进程消失）。
  **顺序注意**：`9eedd70`→`f04dd02`→`1f1e457`→`47d5427`→`3bb97e5`→`49714b7`→`4a1e796`
  是一条递进链（后一个修的是前一个暴露的边界），单独 revert 中间一环会留下半套判据——
  建议按链倒序回滚，或整批一起 revert。
