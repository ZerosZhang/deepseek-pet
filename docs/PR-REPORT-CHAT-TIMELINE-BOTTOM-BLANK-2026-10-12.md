# PR 报告：AI 对话窗口最新消息下方大片空白 + 重新打开不回到最新回复（#191）

> **基线**：`ee699c7`（Merge PR #233 feature/agent-link-subtraction）
> **分支**：`fix/chat-timeline-bottom-blank`　**日期**：`2026-10-12`
> **范围**：3 个文件（实现 1、测试 1、文档 1 + INDEX 登记）
> **关联**：[#191](https://github.com/MerZlin/dsh-pet-indesktop/issues/191)「随着对话越来越多，对话最底下的空白会越来越大」（本 PR 只处理该 issue 的第一个问题；同 issue 里的 OBS 直播捕获黑屏不在范围内）

## 一、核心特性

现代风格 AI 对话窗口（`pet/chat/widgets.py::ChatWindow`）打开后滚动条已在最底，但视口里是一片空白，
要手动往上拉才能看到最新回复；对话越长空白越大。根因（逐层量化见第三节）：`MessageBubble` 的纵向尺寸策略是
`QSizePolicy.Minimum`——**sizeHint 即最小高度**；而折行 `QLabel` 的 sizeHint 是按「非实际宽度」折行估出的高度，
明显偏高。`QScrollArea(widgetResizable=True)` 取 `max(视口, 最小高度, heightForWidth)` 作为内容高度，
于是每个气泡多出的高度累加到时间线末尾的伸缩空间里，成为最新消息下方的空白。

另一半：窗口「关闭」只是 `hide()` 复用，重新打开时没有任何贴底动作，停在上次关闭时的位置。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 不再出现底部空白 | 气泡纵向策略改为 `Preferred`（可收缩），时间线高度按 `heightForWidth` 的真实值排版 |
| 2 | 打开即回到最新回复 | `ChatWindow.showEvent`：非系统自发的 show（菜单/灵动岛打开）调用既有 `_bottom(always=True)`；系统自发 show（从最小化还原）保留阅读位置 |

**红线 / 不变量**：气泡横向策略、宽度计算（`_update_bubble_widths`）不变；流式输出的跟随/上翻暂停逻辑
（`_stream_follow_output` / `_scroll_pin` / `rangeChanged` 补贴底）不变；关闭=隐藏复用的语义不变。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/chat/widgets.py` | +11 / −1 | `MessageBubble.__init__`：纵向 `QSizePolicy.Minimum` → `Preferred`（附根因注释）。`ChatWindow.showEvent`（新增）：`event.spontaneous()` 为假时 `self._bottom(always=True)`。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_chat_timeline_scroll.py` | +96 / −0（新增） | 40 条长短不一消息的会话：① 打开后最新回复底边在视口内、下方空白 ≤ 80px；② 上翻到顶后关闭再打开，滚动条回到最大值且最新回复贴底。真实 Qt 事件循环，布局落定用宽预算轮询（不赌固定 sleep）。 |

### 未改动（故意）

- 经典风格对话窗（`pet/chat/legacy_widgets.py`）：本 issue 截图是现代风格窗口，未复现经典窗口有同类问题，不扩大改动面。
- 考虑过同时给气泡正文 `QLabel` 设 `setMinimumHeight(1)`（压低折行标签的 minimumSizeHint）：**消融实验证明多余**（见第六节），已删除。

## 三、实现要点

逐层测量（本机 offscreen，900×700 窗口，40 条消息，基线代码）：

| 层 | 值 |
|---|---|
| 时间线 `heightForWidth(视口宽)`（真实需要的高度） | 17486 px |
| 最后一个气泡的实际底边（时间线坐标） | 17462 px |
| 时间线 `layout().minimumSize().height()` | **27476 px** |
| `QScrollArea` 给时间线的高度 | 27476 px（= 最小高度） |
| 最长一条回复的正文 `QLabel`：`sizeHint` 高 / 实际高 / `minimumSizeHint` 高 | **3273** / 1545 / 105 px |
| 同一气泡（`MessageBubble`）：实际高 / `minimumSizeHint` 高 | 1578 / 138 px |

`QScrollArea` 的可调整控件分支先取 `qSmartMinSize`，有 heightForWidth 时再与 `heightForWidth` 取最大值，
所以只要最小高度偏高，heightForWidth 再准也没用。`Minimum` 策略让 `qSmartMinSize` 直接返回 sizeHint；
改成 `Preferred` 后返回 minimumSizeHint（很小），最终高度由 heightForWidth 决定，空白消失。
气泡位于 `QScrollArea` 内、时间线高度跟着 heightForWidth 走，不存在被压扁的场景。

## 四、性能分析

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen python bench_timeline.py`（脚本内容附在 PR 描述）——构造同一个 40 条消息会话，
「打开」= 构造 `ChatWindow` + `show()` + 30 次 `processEvents()`（n=5 取中位）；「流式单拍」= 末尾追加一个助手气泡，
300 次 `set_content(累积文本) + _update_conversation_height() + processEvents()`。基线与本分支用 `git stash` 交替各跑 3 轮。
环境：Windows 11 Pro 22631 / AMD Ryzen 7 7800X3D / Python 3.11.5 / PySide6 6.12.0

| 指标 | 基线 `ee699c7`（3 轮） | 本分支（3 轮） | 归属 |
|---|---|---|---|
| 打开耗时中位 | 202.5 / 189.4 / 188.2 ms | 196.3 / 203.7 / 190.4 ms | 既有路径，差异在噪声内 |
| 时间线高度（900 宽） | 23429 px | 19184 px | — |
| 最新回复下方空白 | **4269 px**（5/5 次） | **24 px**（5/5 次，= 布局下边距） | — |
| 流式单拍中位 | 3.07 / 3.13 / 3.04 ms | 3.93 / 3.83 / 3.82 ms | 热路径（打字机 18 ms/拍） |
| 流式单拍 p90 | 5.43 / 5.29 / 5.15 ms | 6.59 / 6.18 / 6.39 ms | 同上 |

**结论**：① 稳态（窗口空闲）无变化；② 流式输出单拍 **+0.8 ms**（中位 3.08 → 3.86 ms，三轮一致，不是噪声）——
布局现在按 heightForWidth 计算真实高度，而不是直接拿缓存的 sizeHint 当最小高度；在 18 ms 的打字机节拍里占比由
~17% 升到 ~21%，只在生成回复期间发生；打开窗口耗时不变；`showEvent` 新增路径只是调用既有 `_bottom()`（同步一次
`setValue` + 两个 singleShot），每次打开窗口触发一次；③ 无新的系统调用、网络、磁盘或线程；④ 时间线控件高度
变小（23429 → 19184 px），内存无增长。

## 五、实机运行记录

**根因复现（本机 Windows，offscreen 平台，基线代码）**：900×700 窗口打开 40 条消息会话，1.5 s 后测量：
`bar 27004/27004 | viewport h=472 | last bubble top=-5360 bottom=-4646 | blank below last=5118`——滚动条在底，
最新气泡在视口**上方** 4646 px 处，下方 5118 px 空白；离屏截图为整片空白，与 #191 附图一致。
同脚本「上翻后关闭再打开」：`bar 200/27004`，停在旧位置。

**修复后（同脚本）**：首次打开 `blank below last=24`；上翻后重开 `bar 21910/21910 | blank below last=24`；
重开前改窗口尺寸 `bar 16914/16914 | blank below last=24`。

**用户可见行为**：本机打包版（`scripts/build_onedir.ps1`，webm-chat 变体）的用户在日常使用中报告「对话框打开老是不会自动回到最后一次回答，
页面最下是空白的，要手动往回拉」；安装含本修复的构建（2026-10-12）后，同一用户确认「空白好了」：打开对话窗口直接停在最新回答，底部无空白。

**边界**：从最小化还原（系统自发 show）不强制贴底——未在真机上逐一验证各种还原方式（任务栏点击 / Win+D 等）的 `spontaneous()` 取值，
即便为假也只是多贴一次底，不会出错。macOS / Linux 未验证（改动不含平台分支）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | All checks passed |
| 断言有效性 | 基线 `widgets.py` 上跑新用例 | **2 failed** |
| 消融：去掉 `Preferred` | 同上 | 2 failed（根因修复） |
| 消融：去掉 `showEvent` 贴底 | 同上 | 1 failed（重开用例） |
| 消融：额外给正文 QLabel `setMinimumHeight(1)` | 去掉它 | 2 passed → 多余，已从 PR 删除 |
| 聚焦 | `pytest -q tests/test_chat_timeline_scroll.py tests/test_chat_subsystem.py tests/test_requested_regressions.py` | 见 PR 描述 |
| 全量 | `python -m pytest -q` | 见 PR 描述（Python 3.11.5，Windows） |

## 七、已知限制与后续

- #191 的第二个问题（OBS 捕获黑屏）未处理。
- 流式单拍 +0.8 ms 未做进一步优化（例如按拍合并高度重算）；当前量级不构成卡顿。

## 八、风险与回滚

影响面：现代风格对话窗口的气泡布局与窗口打开时的滚动位置。无新增配置键、无落盘变化。回滚 = `git revert`，无残留状态。
