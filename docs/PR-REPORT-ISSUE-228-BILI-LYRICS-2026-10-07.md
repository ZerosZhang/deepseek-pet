# issue #228：B 站标题清洗与 foobar2000 窗口标题源

> **基线**：`3c54e32`（merge #172 网络信息）；本提交经 `1c812a6` 并入 integration（预算回调 2423）
> **分支**：`feature/issue-228-bili-lyrics`　**提交**：`5ec61d0`　**日期**：2026-10-07
> **范围**：13 个文件（实现 8、测试 5），净 `+1568 / −16`，含 3 个新文件
> **关联**：issue #228
> **互链**：网络与系统代理口径（歌词请求**故意绕过代理**）见
> [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md)；
> 设置准入/准出见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)；
> 音乐会话语义（浏览器媒体会话否决表）见
> [`PR-REPORT-SMTC-MEDIA-TYPE-2026-10-06.md`](PR-REPORT-SMTC-MEDIA-TYPE-2026-10-06.md)；
> 必备证据章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在
> [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

两件事：**①** 浏览器里放 B 站/YouTube 的音乐视频时，把「网页标题」清洗成
`(歌名, 歌手)` 再去搜歌词（此前直接拿整条标题搜，命中率低）；**②** 新增
**foobar2000 窗口标题源**——foobar2000 默认**不注册 SMTC**，此前完全无歌词能力，现在可以
通过解析它的窗口标题拿到正在播放的曲目。

两条需求的关键设计决策都在**「不猜」**上：

- 「`A - B` 到底是歌名-歌手还是歌手-歌名」字符串本身判不出来。押错的代价**不是搜不到，
  而是贴错歌词**（把歌名当歌手名去校验）。所以没有歌名号（`《》`）时，把整条清洗结果
  **同时当作歌名与歌手**：搜索串是拼接（与顺序无关），歌手校验是**子串包含**，整条标题
  必然包含歌手名。实网对照证明两种顺序都能拿到同样的 63 行歌词（见第四节）。
- foobar2000 的窗口标题是**用户可配置的 titleformat 串**，出厂默认值随版本/主题变化、
  网上查不到稳定契约。因此格式串**必须可配置**，不能硬编码一份；匹配不上就**退回不猜**。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 网页标题清洗 | 站点后缀 / UP主段 / 噪声标签 / 书名号歌名 / 歌手就近段；**只删片段、不改写** |
| 2 | 顺序不可知时不猜 | 无书名号时整条结果同时作歌名与歌手（与顺序无关的 haystack 策略） |
| 3 | 误伤防护 | 清洗结果为空或不足 2 字 → **连歌手一起整体退回原始入参** |
| 4 | 只对浏览器会话生效 | 判据复用 `now_playing.is_browser_session`；原生播放器给的是结构化字段，**原样用** |
| 5 | foobar2000 标题源 | 进程检测（2s TTL 缓存）+ Win32 窗口标题枚举（只认可见顶层窗口）+ 可配置 titleformat 解析 |
| 6 | SMTC 优先 | SMTC 在播时**一次都不问** foobar；foobar 源不覆盖 SMTC 跟踪位 |
| 7 | 气泡标题不变 | 显示仍是**原始网页标题**，只有取词用清洗后的查询词 |

**红线 / 不变量**：
- `clean_web_title()` 是**只删不改**：单测断言**输出是输入的子序列**（不补字、不改字）；
- 原生播放器会话（网易云/QQ 音乐等）**不做清洗**——SMTC 给的是结构化字段；
- SMTC 在播时**不查 foobar**（省一次进程/窗口扫描），且 foobar 结果**不覆盖** SMTC 跟踪位；
- 歌词请求仍走 `_build_opener()`（`ProxyHandler({})` 直连），**网络路径零改动**；
- `pet/music_title.py` 必须零 Qt（已纳入机器守卫）。

## 二、修改文件说明

`git log --numstat 5ec61d0`：

```
26	0	pet/config.py
166	0	pet/foobar_playing.py
3	6	pet/modern_settings_dialog.py
56	3	pet/music_lyric_controller.py
398	0	pet/music_title.py
76	4	pet/now_playing.py
65	0	pet/settings_music.py
16	0	pet/settings_pet_controls.py
7	1	tests/test_architecture.py
5	2	tests/test_config_schema.py
438	0	tests/test_lyric_sources.py
111	0	tests/test_music_player_settings.py
201	0	tests/test_music_title.py
```

### 实现

> *〔2026-10-07 终审修复对齐：本表 **3 行**已被修订——`pet/music_title.py`（`0a67bdf`：
> 格式串解析改分段扫描，去 ReDoS，+218/−34）、`pet/settings_music.py` 与
> `pet/settings_pet_controls.py`（`ddbea79` + `a25858e`：子宠页置灰补齐），见 §9.1 / §9.3〕*

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/music_title.py`（新） | +398 / −0 | 纯函数**零 Qt**。`clean_web_title()`（站点后缀 / UP主段 / 噪声标签 / 书名号歌名 / 歌手就近段 / 不猜 haystack / 误伤退回）+ `parse_foobar_title()`（titleformat→正则：`%title%` / `%artist%` 取名、其它占位符通配、`[...]`→`(?:...)?`、`''` 字面量、`$if(...)` 按字面处理→匹配不上退回不猜）+ **空闲启发式**（标题只剩程序名/占位符即判「无曲目」；**分辨不出暂停**，见第七节）。已加入 `test_architecture` 的「纯逻辑模块零 Qt」名单。 |
| `pet/foobar_playing.py`（新） | +166 / −0 | 进程检测（psutil，**2s TTL 缓存**）+ 窗口标题枚举（Win32 `EnumWindows`，只认 `GetWindow(hwnd, GW_OWNER)==0` 的可见顶层窗口——滤掉「参数选项」这类从属对话框，免得把 "Preferences" 当歌名；多条时取最长）+ `read_track()`。 |
| `pet/now_playing.py` | +76 / −4 | 新增 `_read_foobar_playback()`；`_read_async` 在 `snapshot is None or not snapshot.playing` 时**才**问 foobar（SMTC 在播时一次都不问）；新增 `is_foobar_source()` 供调用方判断「别拿它覆盖 SMTC 跟踪位」；`get_now_playing()` 新增两个 **keyword-only** 参数（默认关，向后兼容）。 |
| `pet/music_lyric_controller.py` | +56 / −3 | `_foobar_lyrics_enabled()` / `_foobar_title_format()`（脏值按关/自动）；`_lyric_query()`（**只有浏览器才洗标题**）；`_sample_loop` 把两个键带给 `now_playing`；`_on_playback_ready` 里 `if not now_playing.is_foobar_source(app_id)` 才更新 `_tracked_app_id`。 |
| `pet/config.py` | +26 / −0 | 两键四处登记（默认值 dict ＋ reload 白名单 ＋ `_normalize_pet_settings` ＋ `set()` 归一化名单）：布尔走 `_bool_or_default`（防 `"false"` 被 `bool()` 误开），格式串非字符串回落 `""` 并截到 **120 字**。 |
| `pet/settings_pet_controls.py` | +16 / −0 | **Windows 才建** `foobar_lyrics_check` + `foobar_title_format_edit`（`setMaxLength(120)`），与 `music_browser_media_check` 同处、同平台条件。 |
| `pet/settings_music.py` | +65 / −0 | `foobar_lyrics_supported()` / `foobar_lyrics_rows()`（仅 Windows，两行）+ **`save_source_settings()`**（把两个来源开关 ＋ 格式串的写回集中到这里）。 |
| `pet/modern_settings_dialog.py` | +3 / −6（净 −3） | 2415 → **2412**。行构造 1 行改用 `... + settings_music.foobar_lyrics_rows(self)`、claim 加两个 id（都是**改行不加行**）；原来 4 行的 browser_media 写回换成 1 行 `settings_music.save_source_settings(self)`。预算同步回调到 2412。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_music_title.py`（新） | +201 / −0 | 真值表 **17 条**真实风格标题 + 误伤防护 4 条 + **子序列不变式** + foobar 解析 8 条。 |
| `tests/test_lyric_sources.py`（新） | +438 / −0 | 源优先级（SMTC 在播 > foobar > 无）4 条、跟踪位 1 条、采样线程传参 1 条、清洗门 4 条、配置归一化 2 条、窗口挑选 2 条。 |
| `tests/test_music_player_settings.py` | +111 / −0 | 平台闸门 / 控件缺失 / 保存跳过缺控件 5 条。 |
| `tests/test_config_schema.py` | +5 / −2 | 两份快照同步（白名单 **127 + 特例 5 = 132**）。 |
| `tests/test_architecture.py` | +7 / −1 | 行数预算 2412 + 纯逻辑模块名单（新增 `music_title.py`）。 |

### 未改动（看起来相关但故意没动）

- **网络路径**：歌词请求仍走 `_build_opener()`（`ProxyHandler({})` 直连），一行未改。
- **`browser_media` 的既有否决表**（`now_playing._BROWSER_APP_IDS`）：本批只**复用**
  `is_browser_session`，不改表。
- **气泡标题**：仍显示原始网页标题（按「任务一 = 取词前处理」的口径刻意不改；见第七节）。
- **没有写任何「检测 foobar 组件是否存在」的猜测代码**：组件（`foo_mediacontrol`）无法可靠
  检测，写了才是摆设；推荐它的文案只出现在设置行与 docstring 里。

## 三、实现要点

### 3.1 为什么是「窗口标题源 + 推荐组件」而不是别的

**foobar2000 默认不注册 SMTC**，官方安装包里没有任何系统媒体控制集成；社区路线是装组件
[`dumbie/foo_mediacontrol`](https://github.com/dumbie/foo_mediacontrol)。可选路径三条：

| 路线 | 结论 |
|---|---|
| **a. 窗口标题解析**（本批实现） | foobar 的窗口标题是用户可配置的 **titleformat 串**（Preferences → Display → Default User Interface）。出厂默认值随版本/主题变化、**网上查不到稳定契约**，社区常见写法有 `%artist% - %title%`、`[%artist%][ - %title%]`。因此格式串**必须可配置**，不能硬编码一份。 |
| **b. 装组件走 SMTC** | 走现有 SMTC 采样，**代码零改动**，装好即支持。写在设置行文案里作为「更可靠路线」推荐。 |
| c. 读播放信息文件/接口 | 无标准，放弃。 |

**没有两条都做一半**：b 只出现在设置行文案与 docstring，没有写任何组件检测猜测代码。

### 3.2 「顺序不可知时不猜」——本批最关键的取舍

`A - B` 的顺序判不出来（YouTube 是「歌名 - 歌手」、中文曲库常相反）。押错的代价不是
「搜不到」，而是**把歌名当歌手名去校验 → 贴错歌词**。所以：

- 没有歌名号（`《》`）时，把**整条清洗结果同时当作歌名与歌手**；
- 搜索串是 `title + " " + artist`（**拼接，与顺序无关**）；
- 歌手校验 `music_lyric._name_matches` 是**子串包含**，整条标题必然包含歌手名。

**实网对照证明这策略成立**（同一链路，仅差顺序）：

```text
周杰伦 - 晴天_哔哩哔哩_bilibili  → ('周杰伦 - 晴天', '周杰伦 - 晴天') → 63 行
晴天 - 周杰伦_哔哩哔哩_bilibili  → ('晴天 - 周杰伦', '晴天 - 周杰伦') → 63 行
```

唯一不塞 haystack 的情形：**单段、且没有任何被剥掉的内容**（如 `晴天`）。它本身不含歌手
信息，硬塞会让「标题就叫《周杰伦》的视频」把任意周杰伦的歌的歌词贴上来。

### 3.3 清洗规则真值表（`tests/test_music_title.py`，17 条）

| 原始标题 | → (歌名, 歌手) |
|---|---|
| `【4K】周杰伦《晴天》官方MV_哔哩哔哩_bilibili` | `(晴天, 周杰伦)` |
| `周杰伦《晴天》_哔哩哔哩_bilibili` | `(晴天, 周杰伦)` |
| `【周杰伦】《晴天》官方MV - 哔哩哔哩` | `(晴天, 周杰伦)` |
| `《晴天》- 周杰伦 - 哔哩哔哩` / `《晴天》 周杰伦 - 哔哩哔哩` | `(晴天, 周杰伦)` |
| `【1080P】周杰伦《晴天》【Hi-Res无损】_哔哩哔哩_bilibili` | `(晴天, 周杰伦)` |
| `【纯享版】周杰伦《晴天》现场版_哔哩哔哩_bilibili` | `(晴天, 周杰伦)` |
| `【歌单】周杰伦《晴天》无损音质_哔哩哔哩_bilibili` | `(晴天, 周杰伦)` |
| `【4K修复】周杰伦《晴天》高清MV` | `(晴天, 周杰伦)` |
| `《晴天》- Jay Chou - 哔哩哔哩` | `(晴天, Jay Chou)` |
| `《官方MV》周杰伦《晴天》_哔哩哔哩_bilibili`（歌名在**第二对**书名号） | `(晴天, 周杰伦)` |
| `晴天 - 周杰伦_哔哩哔哩_bilibili` | `(晴天 - 周杰伦, 晴天 - 周杰伦)` 不猜 |
| `周杰伦 - 晴天 (Official MV) - 哔哩哔哩` | `(周杰伦 - 晴天, 周杰伦 - 晴天)` 不猜 |
| `周杰伦 - 晴天【官方MV】 - 哔哩哔哩` | `(周杰伦 - 晴天, 周杰伦 - 晴天)` 不猜 |
| `【初音ミク】千本桜「ボカロ」UP主: 某某某 - 哔哩哔哩` | `(初音ミク千本桜, 初音ミク千本桜ボカロ)` |
| `周杰伦 - 晴天 (Official Music Video) - YouTube` | `(周杰伦 - 晴天, 周杰伦 - 晴天)` |
| `Jay Chou 周杰倫《晴天》MV - YouTube Music` | `(晴天, Jay Chou 周杰倫)` |

**误伤防护证据**：`_哔哩哔哩_bilibili` → 退回原文；`【4K】《晴》_哔哩哔哩_bilibili`
（书名号内只剩 1 字）→ 退回原文 ＋ 原歌手；`"   "` → 原样返回；`晴天` → `(晴天, "")` 原样。

**括号两套待遇（刻意，非疏漏）**：`【】[]（）()` 删括号留内容（可能是质量标签→命中噪声表
整组删，也可能是 `【周杰伦】` 这类歌手前缀→内容留着还能当歌手）；`「」『』` 按需求口径当
分区标签整组删；被删的内容仍留在 "haystack" 里参与歌手子串校验
（`ヨルシカ「ただ君に晴れ」` → `(ヨルシカ, ヨルシカただ君に晴れ)`，仍能命中）。

### 3.4 源优先级与跟踪位

| 情形 | 行为 |
|---|---|
| SMTC 会话在播 | **不问 foobar**（省一次进程/窗口扫描），且 foobar 结果**不覆盖** SMTC 跟踪位 |
| SMTC 无在播会话 | 问 foobar；命中则作为播放源 |
| 两者都没有 | 无播放源（既有行为） |

`foobar_playing.FOOBAR_APP_ID` 与 `now_playing.is_foobar_source()` 是「不抢 SMTC 跟踪位」
的**唯一判据**，不得在别处复制一份字符串比较。

## 四、性能分析

**方法（可复现）**：本机直接计时（`time.perf_counter` 包裹真实调用，重复取热态值），
在跑约 396 个进程的机器上。
环境：Windows / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属 |
|---|---|---|
| `psutil.process_iter(["name"])` | 冷 **25.8ms** / 热 **2.5–2.9ms**；**2s TTL 缓存**后平均 **≈1.3ms/拍** | 新增 |
| Win32 `EnumWindows` 窗口标题枚举 | 热 **0.66–0.79ms**/次（只在 foobar 在跑**且无 SMTC 在播会话**时才跑，**1s 一拍**） | 新增 |
| `get_now_playing()` 热态 | **9.7ms**（既有） | 既有 |
| `get_now_playing(allow_foobar=True)` 且 foobar **未运行** | **0.01ms**（pid 短路） | 新增路径的最优情形 |
| 稳态开销（foobar 未运行、SMTC 在播） | **零新增** —— `_read_async` 的条件短路使 foobar 路径根本不被求值 | 既有路径不变 |
| 新增线程 / 网络 / 磁盘 | **0 / 0 / 0** —— 进程扫描跑在**既有歌词采样线程**上，不新增线程 | — |
| 歌词缓存 | key 变为**清洗后的查询词**；条目数**上限逻辑不变** | 新增（键语义变化） |

**结论**：① **稳态开销零变化**——foobar 未运行或 SMTC 正在播时，foobar 路径被条件短路，
新增成本为 0；② **新增路径绝对成本与触发频率**：最坏情形（foobar 在跑、无 SMTC 会话）
≈1.3ms + 0.7ms ≈ **2ms/拍（1Hz）**，即约 **0.2% 单核**，且**不在主线程**；③ **未引入新的
系统调用类别**（`EnumWindows` 是 Win32 GUI 调用，非 I/O），**无网络、无磁盘、无线程**；
④ **内存零增长**——TTL 缓存只存一个 pid 列表与时间戳，歌词缓存条目数上限逻辑不变。

## 五、实机运行记录

**主代理本机真机验收（真实桌面、真实进程、真实鼠标输入/播放驱动）**：

- **用户可见行为确认（逐条照用）**：**Edge 播放 B 站【4K修复】周杰伦 - 晴天MV → 日志
  「歌词取词完成: 周杰伦 - 晴天MV 2160P修复版 -> 63行, 耗时 2.84s」（lrclib 404 后兜底源
  命中）+ 唱歌动画（蓝色音符）**。即：① 浏览器会话确实进入歌词链路，清洗后的查询词在真实
  搜索链路上命中 63 行歌词（耗时 2.84s）；② 第一个歌词源 404 时**兜底源接住**，没有变成
  「静默无歌词」；③ 桌宠真的进了唱歌动画状态（蓝色音符可见）。
- **如实登记（未拍到的部分）**：**歌词气泡本体未拍到照**——即「气泡里显示的歌词文字」
  这一观感没有截图证据，只有日志里的取词成功记录与唱歌动画的目视确认。这不是"已验证"，
  而是"部分验证"。

**真机联网对照（本机真实网络、真实外网请求，非 pytest）**：

```text
$ fetch_lyrics(原样标题, "")                    → 0 行
$ fetch_lyrics(*clean_web_title(...))           → 44 行 / 87 行
  《晴天》服务到「故事的小黃花」；《孤勇者》87 行
  缓存目录指向临时目录，未污染用户歌词缓存
```

这条对照**直接量化了清洗的收益**：不清洗时 0 行，清洗后 44 / 87 行。只做了 2 首 × 2 种查询，
是抽样而非全量。

**Win32 通路的真机探针**：`_window_titles_for_pids(explorer.exe 的 pid)` → 返回
`['Program Manager']`（无属主窗口过滤生效），热态 **0.66–0.79ms/次**。

**边界与失败路径（实机/自动已验证）**：

- **foobar 播放状态分辨不了（本路线的固有局限）**：窗口标题里**没有播放状态**，`parse_foobar_title`
  只能靠**启发式**——标题退回程序名（`_IDLE_RE`）或解析不出歌名时返回 `None`（"无曲目"）。
  因此**暂停是分辨不出来的**：暂停时标题仍是上一首 ⇒ **没在播时可能继续显示上一首**
  （`now_playing.py:386-397` 已写明这条口径，配置键默认关、设置页文案也如实写了）。
  这正是本批推荐 **b 路线（装 `foo_mediacontrol` 走 SMTC）** 的原因——SMTC 给的是结构化
  播放状态，那条路没有这个局限。真机无 foobar 可验，见下。
- **平台闸门**：非 Windows 不出现 foobar 设置行（`foobar_lyrics_supported()` 门）。
- **缺控件时不写坏值**：保存时控件缺失则跳过该键（单测覆盖），不会把开关写成 `False`。
- **顺序不可知**：两种顺序的真机/实网对照都拿到 63 行，证明不猜策略成立。

**无法自动验证的能力（如实登记）——本机没有装 foobar2000**：

关键探针结果（**为什么不能自动**的排查证据，不是沉默）：`HKLM` / `HKCU` 的 Uninstall
三项注册表、`Get-Process`、以及 `C:` / `D:` 顶层与 `Program Files*` / `C:\Users\me` /
`ProgramData` 的**深度 3 扫描**，全部未发现 foobar2000。因此：

- foobar 路径**无法在本机做端到端实机复现**——必须先装 foobar2000（或到别的机器上验）。
  **没有用假数据把它写成「已验证」。**
- 可用证据止于：`read_track()` 的每一环（`foobar_pids()` 真实进程扫描、`EnumWindows` 真
  枚举、titleformat 解析、`Playback` 构造）都有单测 + 探针覆盖，但**缺「真 foobar 窗口」
  这一环**。

## 六、测试与验证

> *〔2026-10-07 终审修复对齐（`0a67bdf`）：本节计数已过期，增量见 §9.2——
> `tests/test_music_title.py` +139（含**耗时上限**断言），`test_music_player_settings.py` +58〕*

**红 → 绿（test-first）**

```text
$ pytest tests/test_music_title.py
ImportError: cannot import name 'music_title'        # 红（模块尚不存在）
# 实现后
16 passed
```

**判别力（变异体验证，改坏 → 变红 → 还原 → 变绿，全部已还原）**

| 变异 | 结果 |
|---|---|
| 站点后缀不再剥除 | **2 failed**（真值表 + 空结果退回原文） |
| 结果不足 2 字时不退回原文 | **2 failed**（两条误伤防护） |
| 顺序不可知时不猜（haystack）失效 | **1 failed**（真值表） |
| foobar 格式串解析失效 | **2 failed** |
| foobar 空闲识别失效（`test_parse_rejects_idle_and_empty_titles`） | **1 failed** |
| SMTC 在播时也去问 foobar | **1 failed** |
| foobar 覆盖 SMTC 跟踪位 | **1 failed** |
| 所有会话都清洗标题 | **1 failed**（原生播放器被误洗） |
| foobar 设置行去掉平台闸门 | **1 failed** |
| 缺控件时把开关写成 False | **1 failed** |

十条变异全部有牙，说明测试不是摆设。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `ruff check pet/ tests/` | **All checks passed!** |
| 空白检查 | `git diff --check` | 干净；两份配置快照同步；`modern_settings_dialog.py` 实测 **2412 行**（预算同步调到 2412） |
| 聚焦 | `test_music_title / test_lyric_sources / test_music_player_settings / test_config_schema / test_architecture / test_music_lyric / test_now_playing_media_type / test_now_playing_session_probe / test_music_detect / test_menu_layout` | **289 passed** |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4459 passed, 11 skipped**（跑了两遍，最终提交版本那遍 698s） |
| 集成全量（当晚最终树） | 同上（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

未采集改动前基线数（worktree 原本干净，改动全为增量）。无新增第三方依赖
（`psutil` 已在 `requirements.txt`）。

## 七、已知限制与后续

> *〔2026-10-07 终审修复对齐（`0a67bdf`）：新增一条——自定义格式串有解析上界
> （条件段 >16 / 标题 >400 字符主动退回「不猜」），详见 §9.4〕*

1. **本机没有 foobar2000，foobar 路径未端到端实机验证**（见第五节的探针结果）。要验收需
   先装 foobar2000；若对不上，把 foobar 的「显示 → 默认用户界面 → 窗口标题」里的那串**原样**
   填进设置页格式输入框即可。**没有用假数据把它写成「已验证」。**
2. **窗口标题源分辨不出播放状态（a 路线的固有局限）**：foobar 的窗口标题里没有暂停/停止
   信息，`parse_foobar_title` 只能靠**启发式**——标题退回程序名（`_IDLE_RE`）或解析不出歌名
   时判「无曲目」。因此**暂停分辨不出来**（标题仍是上一首），**没在播时可能继续显示上一首**；
   某些配置下停止后标题也保留上一首，同样会误判为在播。这是选 a 路线的代价，也正是本批
   推荐 **b 路线（装 `foo_mediacontrol` 走 SMTC）** 的原因（SMTC 给结构化播放状态，无此局限）。
   `now_playing.py:386-397` 与设置页文案都已如实写明。
3. **歌词气泡本体未拍到照**（真机只确认了日志取词成功 + 唱歌动画），见第五节。
4. **气泡标题仍显示原始网页标题**（如 `我在唱《【4K修复】周杰伦 - 晴天MV…》`），取词才用
   清洗后的查询词——按「任务一 = 取词前处理」的口径刻意没改。是否也显示清洗后的歌名是
   **留给产品决策**的一项。
5. **标题里完全没有歌手信息时**（如只剩 `晴天`、artist 为空）`_name_matches` 仍会挡掉所有
   候选——这是取词器既有的设计，本批没动。
6. **行数预算回调到 2412**（原 2415）：本批净减 3 行换来（把 browser_media 的 4 行写回搬进
   `settings_music.save_source_settings`）。并入 integration 后，与其他批次叠加的最终实测预算
   为 **2426**（见合并提交）。
7. **未做**：不装 foobar 时的近似能力；`docs/PR-REPORT` 之外没有新增研究文档。

## 八、风险与回滚

- **影响面**：两个新配置键，默认 `foobar_lyrics=false` / `foobar_title_format=""`（自动）。
  默认关时新增路径**完全不被求值**（`_read_async` 的条件短路 + `_lyric_query` 的门），
  用户零变化。清洗只对**浏览器会话**生效——原生播放器的结构化字段照旧原样使用。
- **配置迁移**：全新键；缺键回落默认（关 / 自动），**无历史数据要迁移**。手改脏值由
  `_normalize_pet_settings` 收口（布尔走 `_bool_or_default`，格式串非字符串回落 `""` 并截到
  120 字）。
- **数据面副作用**：歌词**缓存 key 变为清洗后的查询词**——旧 key 的缓存条目变冷（不删，
  按既有上限逻辑自然淘汰）。这是唯一会「看起来像缓存失效」的地方，不丢数据。
- **回滚**：`git revert 5ec61d0` 即可，无残留状态（config 里多出的两个键退化为无害未知键；
  缓存多出的条目由既有淘汰逻辑处理）。回滚后浏览器歌词回到「拿整条网页标题去搜」，
  **不会报错，只是命中率回落**。
- **合并冲突面**：`tests/test_config_schema.py` 两份字面量快照（#228 并入当时是
  **127 + 5 = 132**；**集成分支当前实测已涨到 139 + 5 = 144**，冲突时按当时的实测值对齐，
  别照抄本条数字）；`tests/test_architecture.py`（行数预算常量 + 纯逻辑模块名单）；
  `pet/modern_settings_dialog.py`（本批净减 3 行，与其它加行的批次会在此撞车——当晚的
  并序结论写在合并提交里）。`now_playing.get_now_playing()` 新增的是 **keyword-only** 参数
  （默认关），旧调用点无需改；但 `_read_async` 在无 WinRT 时**不再直接返回 `None`**（先问
  foobar）——若有分支在同一函数上加逻辑需要留意。
- **分支状态**：本提交经 `1c812a6` 并入 `integration/2026-10-07-night-batch`；
  分支未 push、PR 未开。


## 九、终审修复对齐（2026-10-07 追加）

> 按 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) 的「后续轮次在同一文档追加新章节、
> 保留新旧对照，不要重写覆盖」约定**追加**：上文记录的是各提交当时的树，本节只记终审修复
> 带来的增量。上文对应位置已就地加注「2026-10-07 终审修复对齐（提交 `<sha>`）」。

### 9.1 §2 修改文件说明的增量（`0a67bdf`）

| 文件 | 本批增量 | 要点 |
|---|---|---|
| `pet/music_title.py` | +218 / −34 | foobar 格式串解析**从「翻译成正则」改为分段扫描**（去正则回溯爆炸，见下）；两处旧错误顺带修正 |
| `tests/test_music_title.py` | +139 / −0 | 病态格式串耗时上限、超复杂条件段退回不猜、固定种子有界模糊、首尾空白字面量兼容 |

**为什么必须改（ReDoS · 实测）**：`"%title%" + "%album%" * 8 + "X"`（64 字符，**未超配置的
120 字上限**）在旧实现下是组合爆炸——每个占位符翻成 `.+?`、条件段翻成可选组，匹配失败前要把
n 个字符切给 k 个字段的所有分法试一遍。本机同一输入的实测：

```text
标题 "a"*30 → 0.26s      "a"*40 → 4.13s      "a"*50 → 34.03s     （旧实现）
同一输入修复后 → 0.023ms                                            （新实现）
```

这条路径跑在**歌词采样线程**上，而 CPython 的正则回溯**持 GIL**——采样线程被钉住等于
**歌词与切歌检测一起停摆**。现行实现：字面量用 `str.find` / 只含字面字符与空白类的小正则
（**无嵌套量词，不存在回溯**）定位，字段取两段字面量之间的文本；相邻字段间没有字面量时，
只有一个「关心字段」就整段给它、两个以上判这次匹配失败。所有循环与展开都有**硬上限**
（条件段候选 **≤16** 条、参与匹配的标题 **≤400** 字符）——病态输入从「慢失败」变成**毫秒级
快速失败**。

**顺带修掉旧实现的两处错误**（差分对照 **336 组**：**301 组一致、35 组不同**，差异全部落在
下述两族，其余格式串逐组一致）：

1. `%title% %artist%` 这类**只以空格分隔**的格式串：旧实现把空白放宽成 `\s*`，会在位置 0
   匹配到空段，切出 `(晴, 天 周杰伦)` 这种碎片或直接判成解析不了；
2. `%artist% - %title% [%length%]`：旧实现**恒返回 `None`**（整条链路当作「没有曲目」），
   而它是常见的窗口标题写法。

### 9.2 §3.3 / §6 的增量

- **§3.3 真值表与 §3.1 的取舍**：上文「匹配不上退回不猜」这条不变量**不足以覆盖 ReDoS**
  ——现行多一条**上界**：超复杂条件段（候选 >16）与超长标题（>400 字符）**主动退回不猜**，
  而不是慢慢试。这是刻意的取舍：宁可少认几个病态格式串，也不能钉住采样线程。
- **§6 测试与验证**：新增**耗时上限断言**（毫秒级），把上文只靠真值表覆盖的「解析正确性」
  补成「正确性 + 有界性」两维。上文 §6 的变异表各行（含 `foobar 格式串解析失效 → 2 failed`）
  仍成立，无需修订；但**聚焦/全量计数已过期**（`test_music_title.py` +139）。

### 9.3 §2 设置行的增量（`ddbea79` + `a25858e`）

| 控件 / 键 | 增量 | 说明 |
|---|---|---|
| foobar 两键（`foobar_lyrics_check` / `foobar_title_format_edit`） | `pet/settings_music.py` +4 / −1、`pet/settings_pet_controls.py` +6 | 子宠页置灰 + tooltip「仅主桌宠可设置」（键在 `PER_SLOT_SETTING_KEYS` 之外，运行期读主配置 ⇒ 子宠页改了不生效） |
| `music_browser_media_enabled` | `pet/settings_music.py` +11（`a25858e`） | 与 foobar **同处 `_SOURCE_SWITCHES`、同一读取形态**，上一批漏在外；不只灰一半，免得同一行块里留「仍可点、同样不生效」的兄弟开关 |
| `music_player_paths` | 同上 | 右键菜单读 host 配置面（`context_menus/shared` 的 `pet.cfg.get`），overlay 下由 `_SpriteConfig` 转发到主配置，同理 |
| 「自动检测播放器」按钮 | 同上 | 它只服务上面两行（搜到的路径填进没人读的控件），子宠页一并置灰，免得留个点了没用的入口 |

主宠页不受影响；legacy 下子宠窗自读生效这一点**不改变默认拓扑下的死键判定**。收口函数是
新增的 `settings_widgets.mark_main_pet_only()`（主宠页一个不动、幂等）。测试：
`tests/test_music_player_settings.py` +58（两条，与上批 foobar 两条同规）。

### 9.4 §7 已知限制与后续的增量

- **新增**：**自定义格式串有解析上界**——条件段候选 >16 条、标题 >400 字符时**主动退回
  「不猜」**（判为无曲目）。这是 ReDoS 修复的代价：极复杂的 titleformat 串不会慢，但也
  不会被解析；这类用户应改走 b 路线（`foo_mediacontrol` → SMTC）或简化格式串。
- §7 第 2 条（窗口标题源分辨不出播放状态）**未变**，且现在有另一条独立理由支持 b 路线。
- §7 第 6 条的合并注意点数字（`139 + 5 = 144`）仍为现行值。
