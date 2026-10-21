# PR 报告：产品级审查确认的 5 项缺陷修复（第二轮：C1–C5）

> **基线**：`23e57be`（分支 `release/2026-10-08-candidate`，本地分支不推送）
> **分支**：`release/2026-10-08-candidate`　**日期**：2026-10-08
> **范围**：12 个文件（实现 5、测试 5、文档 2），`+957 / −53`；其中代码与测试
> 10 个文件 `+680 / −53`。6 个提交（5 条修复各一 + 1 条交付证据文档）
> **关联**：[`PR-REPORT-REVIEW-FIXES-2026-10-08.md`](PR-REPORT-REVIEW-FIXES-2026-10-08.md)
> （同一轮审查的第一批 8 项 B1–B8）。本报告是同一分支的第二轮（C1–C5）。

## 一、核心特性

同一轮产品级审查确认的第二批 5 项缺陷。前 4 项都是**用户可见的数据/行为丢失**，
第 5 项是提醒时间点错位：

| # | 现象 | 根因一句话 |
|---|---|---|
| C1 | 桌宠隐藏时，联动反馈气泡一到，岛聊天里正在生成的 AI 回答**凭空消失且不进历史** | 反馈面复用同一个岛气泡 `show_feedback()` → `show_reply()` 把 `_active_request_id` 清成 None，真实完成回调按 request_id 匹配后静默 return（落库排在这个检查之后，一并跳过） |
| C2 | 待办「保存」点下去像成功了，条目下次打开却没了 | `TodoStore.save()` IO 失败返回 False，`set_items()` 不检查，面板照常 `close_editor()` + `reload_items()`；下一次 `apply_config()` 用磁盘覆盖内存 |
| C3 | 合法 JSON 里的脏配置让程序**打不开**（连设置恢复入口都进不去） | 枚举键裸判成员（list/dict → `TypeError: unhashable`）与数值键溢出（`10**400` → `OverflowError`、`Infinity/NaN` 撞 `int()`）都能从 `Config()` 构造里抛；启动与独立设置页都没有 try |
| C4 | 关掉歌词后，屏幕上仍会冒出歌词 | 关闭只停表 + `_reset()`，卡在 WinRT 里的在途采样回来时回调只看窗口可见性：`_reset()` 清空的 `_current_key` 让迟到结果被当成"新歌"，重新取词 + 上屏 |
| C5 | 每日 00:02 的待办，提前 5 分钟的提醒要等到 00:00 才响 | `_fire_datetimes` 对 daily 无条件用 `now.date()` 组 due：23:57 算到的是**当天已过**的 00:02（提前档落在昨天），两档一起走"出窗静默盖戳" |

**红线 / 不变量**：

- C1 不动无在途请求时的预览契约（`show_reply` 仍是"只展示、不发送、不落库"），
  也不动改道失败仍返回 False 的调用方契约（`window_alerts.redirect_hidden_bubble`
  的调用方维持"改道失败即放弃"）。
- C2 不动正常保存路径（成功语义、`close_editor()` + `reload_items()` 顺序不变），
  不动 `TodoStore.save` 的"失败只返回 False、不抛"约定。
- C3 不动任何**合法值**的归一化结果（逐键用例含合法值保留断言），不动
  `_clean_island_coordinate` 的 ±100000 口径与 `None = 未定位` 语义。
- C4 不动正常采样链路（开启态每拍照常推进），不动 `_sample_stop` / 常驻采样线程
  的复用语义（`_sampling` 照常清，不引入永久停摆）。
- C5 不动 once 的触发语义与盖戳键格式（`<触发时刻日期>T<HH:MM>#<phase>`），
  不新增当天 + 次日双发。

## 二、修改文件说明

`git diff --numstat 23e57be..HEAD`：

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/quick_chat.py` | +9 / −0 | 新增 `QuickChatBubble.request_in_flight()`（C1）：`_active_request_id is not None or service.busy`。把"气泡里有没有自己发出的、未到终态的请求"变成一个**有名有据**的判据——任何"接管气泡显示"的外部入口（目前是岛反馈面）都必须先问它，预览式改写会清掉 request_id、让真实回调静默返回。 |
| `pet/app.py` | +11 / −1 | `_island_feedback_bubble` 在调用 `show_feedback` **之前**问 `request_in_flight()`，在途则返回 False（C1）：丢弃本轮反馈让调用方维持原丢弃行为，**不排队**（瞬时状态压到回答之后等于送过期消息，与 `_on_global_chat_finished` 的"气泡在场则跳过"同一取舍）。docstring 写明这条取舍与理由。 |
| `pet/todo_reminder.py` | +47 / −13 | ① `set_items()` 返回 `bool`，**落盘成功才提交内存态**（C2）：失败保持内存原样并返回 False；② 新增 `store_path()` 供失败提示指路（C2）；③ `_fire_datetimes` 的 daily 天选择改为"当天那次已过且次日那次的提前档已到点则取次日"（C5）；④ `summarize_next` 的 daily 分支同样按"due 已过即取次日"选天（C5 同族残留，旧实现只认 `fired_due_slot`，跨午夜与戳未落盘两种情形都会把「下一条」留空）。 |
| `pet/todo_panel.py` | +33 / −7 | ① `_save_items` 返回落盘结果，新增 `_persist_or_warn()`（C2）：失败弹 `QMessageBox.warning`（标题「保存失败」，正文写明"这次改动没有保存"+ 条目文件路径）；② `save_editor` 落盘失败**不收编辑器**（草稿留在控件里，可原地改路径后重试），成功才 `close_editor()` + `reload_items()`；③ 勾选/删除两条同路走 `_persist_or_warn`，删除失败不再把正在编辑的编辑器收掉。**附注**：本文件首行的 UTF-8 BOM 随本次编辑写回被移除——它是全仓 884 个受版本控制文件中**唯一**一个带 BOM 的源文件（`git ls-tree -r 23e57be` 逐 blob 扫描实测 1/883），Python 3 与全部工具链都不依赖它（全仓 grep：只有 `scripts/check_bundle_encoding.py` 处理**打包文本资源**的 BOM 容忍，与源码无关），移除后与其余文件一致；如实登记，避免评审把它当成漏改。 |
| `pet/config.py` | +42 / −32 | C3 家族化收口：① `context_menu_template` / `chat_ui_style` 改 `str()` 后再判成员（原写法 list/dict 抛 `TypeError: unhashable`）；② `_clean_island_coordinate` 改为**先在整数域比上限、再对浮点判有限性**（顺序反了会在大整数上先抛 `OverflowError`）；③ `dynamic_island.opacity`、`chat_background_opacity`、`modern_chat_background_opacity`、`modern_chat_card_opacity`、`_clean_menu_appearance` 的圆角/字号改走既有 `_float_or_default` 再取整（替换手写 `float()/int()` + 只捕 TypeError/ValueError 的写法）；④ `_float_or_default` 补 NaN 分支回默认（与 `net_monitor.clamp_interval`、`speech_bubble_text.clamp_bubble_text_scale` 同规；原先 NaN 会落到区间**上限**，是 max/min 参数顺序的副产品）；⑤ `normalize_quiet_minutes` 与 `reload()` 的 `version` 解析补 `OverflowError`。 |
| `pet/music_lyric_controller.py` | +20 / −0 | C4 代次守卫：① 新增类级 `_generation` / `_dispatch_generation`；② `_reset()`（所有关闭路径——`sync_enabled(False)`、`set_music_mode_enabled(False)`、`shutdown()`——的汇聚点）递增代次；③ `_on_tick` 派发时记下本拍所属代次；④ `_on_playback_ready` 先清 `_sampling`（保证采样不停摆）再校验代次，不符直接丢弃。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_island_chat.py` | +106 / −0 | C1：真 `ChatService` + 真 `QThread` + 真 `SessionStore` + 真 `QWidget`，网络 provider 用可控替身（卡在事件上）。主用例走真实序列"发送 → 在途 → 联动反馈 → 完成"，断言反馈被拒（返回 False）、回答上屏、**磁盘会话文件**里有 `["user","assistant"]`；非回归用例断言请求结束后反馈照常预览。 |
| `tests/test_todo_reminder.py` | +162 / −0 | C2：真实文件系统错误（把 `todo_items.json` 做成**目录**，`os.replace` 撞 WinError 5，不打桩 `save()`）→ 编辑器不关、草稿还在、有失败提示（含路径）、内存无幽灵条目；障碍解除后重试成功且只落一条。C5：纯函数 4 条（23:57 发 lead / 00:00 不重复 / due 正点 / lead=0 与 once 行为不变）+ `summarize_next` 跨午夜指向次日 + **服务级** 1 条（真 `TodoReminderService` + 真 store + 真气泡：23:57 冒泡、盖戳落盘、午夜重启不重复、00:02 正点再冒）。 |
| `tests/test_config_schema.py` | +146 / −0 | C3：逐键脏值用例（枚举键 list/dict、坐标 ±`10**400`、opacity 超限/NaN/±inf、三个不透明度键的 ±inf/NaN、菜单外观圆角字号、顶层 version）+ 合法值保留的非回归 + **全键 × 全脏值穷举探针**（145 键 × 8 脏值，新增裸 `in {...}` / `int()` / `float()` / `math.isfinite()` 立刻红并指出键与脏值）。 |
| `tests/test_music_lyric.py` | +104 / −0 | C4：真控制器 + 真采样线程，SMTC 采样换成卡在事件上的替身。主用例"卡住 → 关闭 → 放开 → 迟到回调"断言不取词、不上屏；非回归断言开启态回调照常推进；第三条断言关闭再开启后新一代采样正常（代次不串）。 |

### 未改动（故意）

- `pet/window_alerts.py`：改道调用方的"失败即放弃"语义一字未改（C1 的"让路"就是
  走这条既有契约返回 False，没有引入新分支行为）。
- `pet/todo_reminder.py` 的 `TodoStore.save` / `load`：读写实现不动（C2 只改
  **谁检查返回值**与**内存何时提交**；`load` 遇目录仍是 `OSError → []`）。
- `pet/chat/service.py` / `pet/chat/session_store.py`：C1 的修法不动聊天链路
  （request_id 匹配与原子追加落盘照旧），只在反馈面加了一道前置问询。
- `pet/music_detect.py` / 采样线程生命周期：C4 只加代次判据，**不动**
  `_sample_stop` / 常驻线程复用 / `_sampling` 单飞这三条既有纪律。

## 三、实现要点

**C1：为什么"丢弃"而不是"排队"。** 反馈气泡的内容是「正在认真想办法 / 开始干活」
这类**瞬时状态**，它的价值在于"此刻"。排队到回答之后再弹，用户看到的是对已经完成
的事情说"正在做"，比不弹更糟——同一取舍在 `_on_global_chat_finished` 里已经存在
（气泡在场则跳过预览）。所以让路的实现就是返回 False，让调用方走既有的"丢弃"分支。
判据落在气泡自己身上（`request_in_flight()`）：`_active_request_id` 是**同步**写入
的（`_send` 里 `self.service.send(...)` 的赋值与其它 GUI 线程代码互不交错），比
`service.busy`（依赖 worker 线程真的跑起来）更可靠，所以两者取或。

**C2：为什么回滚内存而不是保留。** `_items` 是提醒调度的真值源。保留一份"没落盘
却被当成已保存"的副本有两个后果：① 提醒会为下次 `apply_config()` 就消失的条目按时
冒泡；② 失败时编辑器按契约不收（仍在"新建"态），用户再点一次保存会把内存里的那条
**再追加一遍**。回滚后内存 == 磁盘，失败是诚实的；用户输入一个字都没丢——它留在
编辑器控件里（与设置对话框"保存失败不关窗、草稿留在控件里"是同一条契约）。

**C3：为什么是家族化而不是逐键打补丁。** 这 12 个崩溃点分三族，每族都有**既有的
正确写法**：枚举键 = 先 `str()` 再判成员（文件里 `dialogue_mode` / `media_prewarm`
早就这么写）；数值键 = 走 `_float_or_default`（`_float_or_default` 的注释里本来就
写着"OverflowError 必须接住"）；坐标 = 复用 `_clean_island_coordinate`。本轮把这
三族的**偏离者**改回同族写法，并补了两处真缺口（`_float_or_default` 的 NaN 分支、
`_clean_island_coordinate` 的判定顺序）。穷举探针是防复发的机器判据。

**C4：为什么用代次而不是"检查 enabled"。** 直接查配置开关会漏掉"菜单临时退出音乐
模式"（`_user_mode_off`，不写配置）与窗口关闭（`shutdown`）两条路径。代次把"当前
这一拍是否仍然有效"归纳成一个整数：**所有**关闭路径都经 `_reset()`，代次变化即
等价于"不再启用"，不需要枚举关闭路径。代次由派发侧写、回调侧读，同一时刻只允许
一拍在途（既有 `_sampling` 保证），因此单槽位就够，无需改动 `_playback_ready` 的
信号签名（既有 20+ 处直接驱动该回调的用例一字未改）。

**C5：为什么取次日不会双发。** 提前档的盖戳键按**触发时刻**的日期拼（`23:57` 那天
的键是 `2026-09-04T00:02#lead`），午夜后重算同一个 occurrence 得到的键一致；且
"取次日"只在 `now < 次日 due` 时发生（`now >= 次日提前档` 但还没到正点），正点档
的键（`2026-09-05T00:02#due`）是另一条，互不干扰。旧实现连"当天已过"的档都盖了戳
（`2026-09-04T00:02#due`），现在这一格不再被无谓盖戳，但它永远处于"已过期"状态，
不会在别处被当成待触发。

## 四、性能分析

**方法（可复现）**：临时脚本 `_bench_fixes.py`（`timeit`，`repeat=3` 取最优；测完
删除，脚本内容见下），同一台机器上先用当前实现、再 `git checkout 23e57be -- pet/`
回滚到基线跑同一份脚本。环境：Windows 11（10.0.26300）/ Python 3.13.7 / PySide6 6.11.2。

| 指标 | 基线（`23e57be`） | 本批（HEAD） | 归属 |
|---|---|---|---|
| `Config()` 构造（含读盘 + reload + 归一化） | 541.8 µs/次 | **524.0 µs/次** | 既有路径（启动 1 次、设置保存 1 次/次） |
| `advance_todo_state`（10 条，白天） | 89.2 µs/次 | 89.9 µs/次（+0.7） | 热路径：30 s 一拍 |
| `advance_todo_state`（10 条，23:57 跨午夜档） | 90.1 µs/次 | 97.6 µs/次（+7.5） | 同上，仅"当天那次已过"时多一次比较 + 一次 `timedelta` |
| `summarize_next`（10 条，白天） | 70.8 µs/次 | 68.0 µs/次（−2.8） | 面板重载 / 气泡文案 |
| `summarize_next`（10 条，23:57） | 71.7 µs/次 | 75.2 µs/次（+3.5） | 同上（基线此处提前 `continue` 返回空串，故看起来更快） |
| 采样回调的代次比较 | — | **0.045 µs/次** | 新增：1 Hz（真实负载是同一回调里已有的 tracker 计算） |
| `request_in_flight()`（属性读 + 或） | — | **0.051 µs/次** | 新增：只在联动反馈改道时调用（DSH 事件级） |

**结论**：

1. **稳态开销**：`Config()` 归一化净变快（−3.3%，`str()` 与 `_float_or_default` 比
   `try/except int()` 更快，且少了 3 处异常路径）。待办 tick 每 30 s 一拍，跨午夜
   档 +7.5 µs/拍（10 条条目），即 **0.0000075 秒 / 30 秒 ≈ 2.5e-7 的 CPU 占比**；
   白天档 ±0.8% 在测量噪声内。采样回调每秒多一次整数比较（0.045 µs）。
2. **新增路径的绝对成本与触发频率**：`request_in_flight()` 0.051 µs，触发频率 =
   DSH 联动反馈事件（人工/任务级，不是定时器）；代次比较 0.045 µs × 1 Hz。
   两项加起来 < 0.05 µs/s，相对同一个回调里已有的歌词定位计算可忽略。
3. **有无新的系统调用 / 网络 / 磁盘 / 线程**：**无新增**。反向地，C4 让"关闭歌词后
   迟到的采样"不再触发取词 —— 那是一次**网络请求**（三个歌词源的 HTTP）与一次
   后台线程（`music-lyric-fetch`），本批把它省掉了。C2 失败路径同样少一次无效写盘
   （失败后不再继续 `reload_items` 之外的路径）。C3 全是纯计算。
4. **内存与缓存有没有增长**：新增字段只有两个整数（`_generation` /
   `_dispatch_generation`），无缓存、无列表增长。C2 的改动在失败时**不**复制条目
   列表（原实现无论如何都替换 `_items`），内存占用略降。

**测试侧开销**：新增用例给套件带来 `test_config_schema` 的穷举探针
（145 键 × 8 脏值 = 1160 次 `Config()` 构造，**5.9 s**，`--durations` 实测）与其余
4 个文件的事件等待（各自 < 2 s）。

## 五、实机运行记录

本机 Windows 11 / Python 3.13.7，均为**真实环境**（非 CI、非 mock）。桌面 GUI 肉眼
确认**本批未做**（原因见本节末）。

**1）C3 根因现场复现 + 修复后同命令对照**（真实加载路径：`APPDATA` 指向含脏
`config.json` 的目录，走 `_default_base()` → `Config()`，与启动路径同一个入口）：

```bash
$ APPDATA=/tmp/e2e_appdata python -c "from pet.config import Config; Config()"
  File "D:\dsh-pet-src-wt-release\pet\config.py", line 1576, in _normalize_pet_settings
    if self.data.get("context_menu_template") not in {"legacy", "modern"}:
TypeError: unhashable type: 'list'          # 基线：启动即崩

$ APPDATA=/tmp/e2e_appdata python -c "...（修复后，打印归一化结果）"
启动 OK: {'context_menu_template': 'modern', 'chat_ui_style': 'modern',
          'chat_background_opacity': 100, 'modern_chat_card_opacity': 10,
          'quiet_minutes_default': 30}
appearance: 18 13
island: None None 1.0
```

输入文件的脏值包含 `[1,2]` / `{"a":1}` / `Infinity` / `-Infinity` / `NaN` /
400 位整数字面量（覆盖本次确认的全部三族）。

**2）C2 真实文件系统错误**（WinError 5，非打桩）：把 `todo_items.json` 做成目录后
点保存，日志实测：

```
ERROR pet.todo_reminder:todo_reminder.py:244 待办条目写入失败：<tmp>\dsh-pet-standalone\todo_items.json
PermissionError: [WinError 5] 拒绝访问。: '<tmp>\...\todo_items.json.49940.tmp' -> '<tmp>\...\todo_items.json'
```

修复后同一场景：编辑器不关闭、草稿 `买奶` 仍在控件里、弹出「保存失败」提示（含路径）、
内存条目为空（与磁盘同真值）；`os.rmdir` 修好后重试一次成功且只落一条。

**3）C4 真实线程/事件复现**：真 `MusicLyricController` + 真常驻采样线程，采样替身卡在
`release_first.wait()`（模拟 WinRT 不返回）。关闭歌词 → 放行 → 迟到采样回到主线程：
基线 `fetched=[(('夜曲','周杰伦'), ...)]`（重新取词）、`win.shown` 非空（上屏）；修复后
两者皆空。

**4）C1 真实链路**：真 `ChatService`（`QThread` worker）+ 真 `SessionStore` + 真
`QWidget` 岛气泡，网络 provider 换成卡在事件上的替身。修复前实测：`returns=True`、
`output='DSH 正在认真想办法……'`、**磁盘会话文件的 roles = `['user']`**（回答丢失）。
修复后：`returns=False`、`output='在的呀，我一直在听'`、磁盘 roles = `['user','assistant']`。

**5）C5 服务级真实 tick**：真 `TodoReminderService` + 真 `todo_items.json` + 真气泡
回调，`_on_tick(now=datetime(2026,9,4,23,57))`：基线 `bubbles == []`（不提醒）、
00:00 才补发；修复后 23:57 当拍 `bubbles == ['⏰ 待办提醒：吃药（00:02）']`，盖戳
`2026-09-04T00:02#lead` 落盘，午夜后新建服务重读不重复，00:02 正点档照常冒。

**边界与失败路径的实机观察**：C2 用例刻意走真实 `PermissionError`（不是伪造异常）；
C4 用例刻意让采样**真的卡在**线程事件上（不是伪造回调顺序）；C3 用例的脏值全部来自
`json.dumps` 写盘后再 `json.loads` 读回（等价于手改文件）。

**用户可见行为的确认**：本批**没有** desktop GUI 肉眼确认（真实桌宠窗口 + 真
SMTC/DSH 事件）。原因与排查证据：C1/C4/C5 的触发条件是"桌宠隐藏 + 联动事件"、
"歌词开关关掉且采样在途"、"跨午夜时刻"，都要求挂钟跨过特定时刻或外部程序（DSH 会话
/ 网易云）配合，无法在无人值守的这一步确定性地复现；本批改动的全部判定点都已下沉到
可注入时钟/可注入采样的纯逻辑与管理类，因此用真实 Qt 对象 + 真实线程 + 真实文件系统
在进程内复现了用户路径（上表 1–5），未做 GUI 肉眼确认。若需要肉眼确认，建议的验证
脚本是：隐藏桌宠 → 触发一次 DSH 联动气泡的同时在岛上发问（C1）；设置里关掉歌词时
正播放（C4）；把待办改成"每天 00:02 + 提前 5 分钟"等到 23:57（C5）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | All checks passed（每条提交前逐文件跑，收尾全树跑） |
| 聚焦（C1） | `pytest -q tests/test_island_chat.py` | 24 passed（基线 22 + 新增 2） |
| 聚焦（C1 族） | `pytest -q tests/test_island_chat.py tests/test_chat_subsystem.py tests/test_chat_service.py tests/test_chat_shared_behavior.py tests/test_overlay_chat_proactive.py` | 201 passed, 1 skipped |
| 聚焦（C2/C5） | `pytest -q tests/test_todo_reminder.py` | 45 passed（基线 38 + 新增 7） |
| 聚焦（C3） | `pytest -q tests/test_config_schema.py` | 61 passed（基线 52 + 新增 9） |
| 聚焦（C3 族） | `pytest -q tests/test_config_schema.py tests/test_config_domains.py tests/test_config_instance.py tests/test_config_key_migration.py tests/test_config_reload_null.py tests/test_config_sound.py tests/test_dynamic_island_revamp.py tests/test_bubble_text_scale.py tests/test_net_monitor.py` | 194 passed |
| 聚焦（C4） | `pytest -q tests/test_music_lyric.py` | 94 passed（基线 91 + 新增 3） |
| 聚焦（C4 族） | `pytest -q tests/test_lyric_sources.py tests/test_now_playing_media_type.py tests/test_now_playing_session.py tests/test_music_detect.py tests/test_music_title.py tests/test_music_sing_grace.py tests/test_music_sing_timer.py tests/test_overlay_music_sing.py tests/test_music_player_settings.py tests/test_music_player_cache.py` | 162 passed |
| 断言有效性（消融） | 逐条把产品文件回滚到基线后重跑该条 focused | 见下表，5 条全部"修复前红、修复后绿" |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q tests` | **5491 passed, 11 skipped**, 329 warnings in 1068.52s（`EXIT=0`） |

新增用例 21 条（`git diff 23e57be..HEAD -- tests/ | grep -c "^+def test_"` 实测 21：
C1 2 / C2 2 / C3 9 / C4 3 / C5 5）。

**消融（ablation）证据**——把产品文件单独回滚到 `23e57be` 后再跑新增用例：

| # | 回滚的文件 | 消融结果（重跑新增 focused） |
|---|---|---|
| C1 | `pet/app.py`（保留 `quick_chat.py`） | `test_island_feedback_yields_to_inflight_request` FAILED（`assert True is False`），非回归条照常 PASS |
| C2 | `pet/todo_reminder.py` + `pet/todo_panel.py` | 两条 FAILED（`_editor_card.isHidden() is True`；`items()` 被写入内存后的 `[...] == []`） |
| C3 | `pet/config.py` | 8 FAILED / 1 passed（探针把 12 个键 × 脏值逐个列出；合法值保留条照常 PASS） |
| C4 | `pet/music_lyric_controller.py` | 两条 FAILED（`fetched` 出现取词、`shown` 非空），开启态非回归条 PASS |
| C5 | `pet/todo_reminder.py` → `d8c8a3f~1` | 两条 FAILED（`summarize_next` 返回 `''`；服务级 `bubbles == []`） |

**全量**（最后一条 docs 提交之前冻结的代码/测试树上跑的，本报告随后只补记结果、未动
任何代码或测试）：

```
$ QT_QPA_PLATFORM=offscreen python -m pytest -q tests
5491 passed, 11 skipped, 329 warnings in 1068.52s (0:17:48)
EXIT=0
```

（聚焦基线计数按各自文件在本批之前最后一次单独运行的结果登记；三个文件在基线上是
合并跑的，故 C2/C5 记 38、C3 记 52。）

## 七、已知限制与后续

- **C1 的行为是"丢弃本轮反馈"，不是"延后显示"**：在途期间到达的联动状态气泡会被
  丢掉（与"岛反馈面不可用"时同一条丢弃路径）。理由见 §三。若产品上认为"这些状态
  必须留痕"，正确做法是入一条有界队列并在回答落屏后合并去重，而不是改回覆盖。
- **C2 失败时的条目只活在编辑器草稿里**：用户点「取消」/关面板仍会丢草稿（与设置
  对话框一致）。没有做"自动重试写盘"——磁盘侧问题（目录被占/只读/空间）需要用户
  介入，反复重试只会在日志里刷错误。
- **C3 覆盖的是 `Config` 的归一化面**：设置页/消费方自己直接 `float(config.get(...))`
  的地方不在本轮范围（探针口径是"全键 × 全脏值 → `Config()` 必须构造成功"）。
- **C4 只保证"关闭后的迟到采样不生效"**：关闭**瞬间**已经上屏的歌词不会被撤回
  （那需要主动清气泡，属于另一个决定）。
- **C5 覆盖 daily 跨午夜的提前档**：`lead_minutes` 上限 60 分钟（配置已夹取），所以
  跨一天就够；若将来允许更长的提前量，`_fire_datetimes` 的"取次日"需要推广成
  "取下一个未过期的 occurrence"。

## 八、风险与回滚

- **影响面**：C1 只影响"桌宠隐藏 + 联动反馈 + 岛聊天在途"三者同时成立的窗口；
  C2 只影响保存失败路径（成功路径逐字未变）；C3 只影响脏值/非预期类型的输入
  （合法值逐键断言不变）；C4 只影响"关闭/复位之后回来的采样"；C5 只影响
  `daily` 且 `lead_minutes > 0` 且 due 落在午夜后 `lead` 分钟内的条目。
- **开关与配置**：本批**没有新增配置键**，也没有配置迁移（脏值归一化是既有键的
  行为收紧，落盘值仍是同一个键）。
- **回滚**：5 个提交互相独立，可单独 `git revert`（`9460ccf` C1 / `fd11719` C2 /
  `6ed6168` C3 / `a007d6a` C4 / `9be653d` C5）。回滚后**无残留状态**：C3 之前的
  脏值归一化结果（如 `context_menu_template: []` → `'modern'`）本来就是可接受的
  落盘值；C2 之前的"内存里有、磁盘上没有"条目只在进程内存在，回滚不会把它写回磁盘。
