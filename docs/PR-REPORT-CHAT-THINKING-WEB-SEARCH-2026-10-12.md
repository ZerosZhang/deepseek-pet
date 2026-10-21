# PR 报告：AI 对话的深度思考展示 + 联网搜索 + 思考过程随会话保存

> **基线**：`ee699c7`（Merge PR #233 feature/agent-link-subtraction）
> **分支**：`feat/chat-thinking-web-search`　**日期**：`2026-10-12`
> **范围**：14 个文件（实现 11、测试 1、文档 1 + INDEX 登记）
> **关联**：与 [#248](https://github.com/MerZlin/dsh-pet-indesktop/pull/248)（时间线空白）和 Markdown 渲染 PR 同改 `pet/chat/widgets.py`，改的是不同位置；
> 功能方向事先与维护者沟通过（独立对话 API 最初参照 SillyTavern 的接法，未考虑思考与联网）

## 一、核心特性

1. **深度思考看不到**：DeepSeek V4 默认开启思考，流式增量里的 `delta.reasoning_content` 被 `SSEParser` 丢弃——用户既看不到思维链，
   也没法开关思考或调强度。
2. **不能联网**：DeepSeek（及多数 OpenAI 兼容服务）API 没有内置联网，问实时信息只能靠训练数据瞎答。
3. **思考过程重开就没了**：（本 PR 内的后续修复）思维链只在内存，重启或切换会话后历史回复上的思考面板消失（用户实机报告）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 思维链展示 | 解析 `reasoning_content`（及 OpenRouter 等网关的 `reasoning`），以 `StreamEvent('reasoning')` 送到界面；回复上方可折叠面板，正文开始输出时自动收起 |
| 2 | 思考开关 / 强度 | 按 provider：跟随模型默认（不发参数）/ 开启 / 关闭；开启时 `reasoning_effort` 低/高/最大（DeepSeek V4 格式 `thinking: {type}` + `reasoning_effort`） |
| 3 | 思考耗尽 token 的明确报错 | 只有思维链、`finish_reason=length` 时提示「深度思考用完了最大输出 Token（当前 N）…建议 8192 以上」，替代「模型未返回任何内容」 |
| 4 | 联网搜索 | 正式回答前，用**非思考模式 + 工具调用**让模型决定要不要搜、搜什么（`web_search` / `fetch_url`，最多 3 轮、每轮 4 次调用）；资料并入 system 后正式回答（不带 tools），末尾列参考来源；闲聊不触发 |
| 5 | 搜索引擎 | 百度（默认，免 Key）、DuckDuckGo（免 Key）——二者互为兜底；博查、Tavily（需 Key）。纯 urllib，无新依赖 |
| 6 | 降级 | provider 不支持 tools（如 400）→ 状态提示「联网检索不可用」后直接回答；搜索失败的原因交给模型、不中断回答 |
| 7 | 思考过程保存 | `ChatMessage` 新增可选 `reasoning` / `activity`，随回复落盘，重开会话以收起状态回显；**不进模型上下文** |

**红线 / 不变量**：
- 正文增量仍以 `str` 产出；思维链与进度是另一种类型 `StreamEvent`，只拼接 `str` 的旧调用方不受影响（`SSEParser.feed()` 也保持只返回正文）。
- 「跟随模型默认」不发送任何新参数：非 DeepSeek 服务默认零行为变化（`thinking` 参数只在显式选择或 base_url 含 `deepseek.com` 时发送）。
- 联网默认关闭；文件解读（`file_interpret.py`）不走联网。
- 会话文件：无思考内容的消息不写新键，旧文件与旧版本读取均兼容。
- 明文 Key 不落盘：搜索 Key 优先存系统钥匙串，`Config._redacted_data` 写盘时剔除 `chat.web_search.api_key`（与 provider Key 同策略）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/chat/providers.py` | +194 / −12 | `SSEParser.feed_events()`（content / reasoning / finish_reason）+ 兼容的 `feed()`；`StreamEvent`；`thinking_payload()`；`OpenAICompatibleProvider` 拆成 `_open` / `_stream_answer` / `_complete_json` / `_run_tool` / `_research`；`inject_search_context()` 把资料并入首条 system（不改原列表）。 |
| `pet/chat/web_search.py` | +225 / −0（新增） | 四个引擎的请求与解析（百度/DDG 解析为纯函数便于测试）、人机验证识别（百度安全验证页、DDG anomaly 页）与免 Key 引擎互为兜底、`fetch_page_text`（仅 http/https，读 2MB 上限，去脚本/导航取正文，截 5000 字）、`format_results`。 |
| `pet/chat/models.py` | +53 / −7 | `ProviderConfig.thinking` / `reasoning_effort`（容错解析）与运行时字段 `web_search`（不随 provider 落盘）；`WebSearchSettings`（全局）；`ChatSettings.web_search` + `attach_runtime()`，`active_config` 自动带上联网设置；`ChatMessage.reasoning` / `activity`（空值不落盘）。 |
| `pet/chat/service.py` | +11 / −1 | worker 识别 `StreamEvent` → `activity_received(kind, text)`；`ChatService.activity(request_id, kind, text)` 信号（QueuedConnection，与既有信号同口径）。 |
| `pet/chat/widgets.py` | +137 / −4 | `MessageBubble` 思考/联网折叠面板（80 ms 合并刷新）、`restore_thinking` / `thinking_record`；`ChatWindow._activity`；首个正文增量收起面板；完成时把思维链与进度随回复保存；`_load` 回显；错误/停止时收起面板（停止时有思考内容的气泡保留）。 |
| `pet/chat/ai_settings_page.py` | +103 / −3 | 新分组「深度思考与联网」7 行设置（见下表）；随 provider 草稿保存思考设置；搜索 Key 进钥匙串；「最大输出 Token」上限 32768→131072 并提示开启思考时建议 8192+；依赖可见性（强度仅在开启时显示、Key 仅在付费引擎时显示）。 |
| `pet/modern_settings_dialog.py` | +12 / −0 | 新分组纳入「AI 与对话」页的 `claim` 布局。 |
| `pet/chat/legacy_widgets.py` | +7 / −0 | 经典窗口：状态栏显示「深度思考中… / 正在搜索：…」。 |
| `pet/quick_chat.py` | +6 / −0 | 快捷气泡：提示行同上。 |
| `pet/config.py` | +3 / −0 | 写盘剔除 `chat.web_search.api_key`。 |
| `pet/file_interpret.py` | +2 / −0 | 文件解读的 provider 副本 `web_search=None`（内容已随消息给出，省一次检索请求）。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_chat_thinking_web_search.py` | +511 / −0（新增，22 条） | SSE 思维链/finish_reason；`thinking_payload` 各模式；设置 round trip 与脏值清洗；**搜索 Key 不落盘**；本地 HTTP 假端点：思维链事件 + thinking 参数、思考耗尽报错、检索→注入→回答全链路（检索阶段显式关思考、正式回答不带 tools、原列表不被改写）、模型判定无需搜索、tools 不支持时降级、搜索失败交给模型；DDG/百度解析、正文提取、人机验证识别与兜底、付费引擎缺 Key；`ChatService.activity` 与正文分流；气泡面板展开/收起；设置页持久化；**思考过程落盘兼容 + 关闭重开后回显且不进模型上下文**。网络边界全部用本地假端点 / monkeypatch，不访问外网。 |

### 新增设置（按 `docs/SETTINGS-CHANGE-GATES.md` 的准入记录）

| setting_id | 归属 | 默认 | 依赖 | 保存 | 迁移 / 恢复 |
|---|---|---|---|---|---|
| `thinking_mode`（`chat.providers.*.thinking`） | AI 与对话 / 深度思考与联网 | `auto`（不发参数） | — | 随设置页保存 | 缺键=auto；非法值→auto |
| `reasoning_effort`（`chat.providers.*.reasoning_effort`） | 同上 | `high` | 仅 `thinking=enabled` 时显示与发送 | 同上 | 缺键/非法→high |
| `web_search_enabled`（`chat.web_search.enabled`） | 同上 | 关 | — | 同上 | 缺键=关 |
| `web_search_engine` | 同上 | `baidu` | 联网开启时显示 | 同上 | 非法→baidu |
| `web_search_key` | 同上 | 空 | 联网开启且引擎为博查/Tavily 时显示 | 钥匙串；不可用时仅内存 | 写盘剔除明文 |
| `web_search_max_results` | 同上 | 5（1–10） | 联网开启时显示 | 同上 | 越界夹取 |
| `web_search_fetch_pages` | 同上 | 开 | 联网开启时显示 | 同上 | 缺键=开 |

三端共用同一 setting ID 与语义，无平台分支。未做：`compact/standard/wide` 三档宽度与明暗主题的截图矩阵（见第七节）。

## 三、实现要点

- **为什么检索走单独一轮非思考请求，而不是在正式回答里挂 tools**：DeepSeek 思考模式带 tools 时要求回传**历史所有轮次**的
  `reasoning_content`（缺失即 400），而会话历史不（也不应）把思维链发回模型。拆成「非思考 + tools 的检索阶段」与
  「按设置思考、不带 tools 的回答阶段」，两边都满足 API 约束，也让不支持 tools 的服务能干净降级。
- **免 Key 引擎的取舍**：实测 cn.bing.com 无 Cookie 抓取返回与查询无关的结果（反爬），未采用；搜狗/360 直接跳验证页；百度可用，
  DDG 在海外网络可用。频繁请求两者都会要求人机验证——**识别后如实报错并换另一个兜底，不尝试绕过**，设置说明里引导需要稳定联网的用户用付费 API。
- **思考过程落盘**：只存界面回显用的两项，`PromptBuilder` 仍只取 `content`，不增加 token。

## 四、性能分析

**方法（可复现）**：offscreen，`MessageBubble` 宽 700；6000 字思维链按每 15 ms 一个 4 字增量推送（1500 个），统计 `append_reasoning`
与合并后的面板刷新（含 `heightForWidth`）。网络耗时为本机一次性探测。
环境：Windows 11 Pro 22631 / AMD Ryzen 7 7800X3D / Python 3.11.5 / PySide6 6.12.0

| 指标 | 实测 | 归属 |
|---|---|---|
| `append_reasoning` 单次 | 中位 6.6 µs（n=1500） | 新增，每个思维链增量 |
| 面板刷新（80 ms 合并） | 1500 个增量 → 243 次刷新；中位 1.84 ms，p90 3.08 ms，最大 4.00 ms | 新增，思考期间 |
| 未开联网时的额外请求 | 0 | — |
| 开联网时的额外请求 | 每次提问 +1 次非流式检索判定（max_tokens 1024）；需要搜索时每轮再 +1，外加每次 web_search / fetch_url 一次 HTTP | 新增，按次 |
| 搜索 / 读网页单次耗时（本机探测） | DuckDuckGo 0.60–0.62 s；读 api-docs.deepseek.com 一页 0.83 s；超时上限 `min(provider 超时, 20 s)` | 新增 |
| 检索判定请求的模型耗时 | **未测**（需要真实 API Key；由用户在实机上使用，见第五节） | — |
| 会话文件增长 | 每条带思考的回复多存思维链原文（量级与回复正文相当） | 新增，落盘 |

**结论**：① 未开联网、模型不返回思维链时稳态零开销；② 思考展示的 GUI 成本为每 80 ms 至多一次 ≤4 ms 的刷新；联网的主要成本是网络往返
（判定请求 + 搜索/读页，每次提问至少多一次 API 调用，按量计费的服务会多一点费用）；③ 新增网络访问仅在用户开启联网后发生，访问目标为所选引擎
与模型选择读取的网页；无新线程（检索在既有 `_Worker` 线程内同步完成，可被取消）；④ 内存：思维链随气泡驻留，落盘后随会话文件增长。

## 五、实机运行记录

- **根因（本机）**：DeepSeek 官方文档（Thinking Mode）写明 V4 默认开启思考、思维链在 `delta.reasoning_content`；基线 `SSEParser` 只读 `delta.content`。
- **用户可见行为（本机打包版，用户本人的 DeepSeek Key）**：安装含本功能的构建后，用户开启深度思考与联网搜索实际提问，反馈「我试了一下功能都可以」（2026-10-12）。
- **思考过程丢失的修复**：用户随后报告「以前回答的思考没了」（重启/切换会话后），确认属于「只在内存」问题；修复后用例覆盖「回答 → 关窗口 → 重开 → 面板在、思维链不进上下文」，
  已装入用户本机构建；用户对该修复本身尚未单独回报。
- **免 Key 引擎实测（本机，同一 IP 连续探测十余次后）**：百度返回「百度安全验证」页、DDG 返回 anomaly 验证页——识别逻辑据此实现；
  首次探测时两者均返回正常结果（百度「DeepSeek V4 发布」前 4 条与查询相关；DDG「今天北京天气」前 4 条为天气站）。
- **离屏截图核验**：联网 + 思考 + 回答的完整一轮，收起态显示「💭 已联网搜索并深度思考（71 字）」，展开后依次为搜索进度与思维链。
- **未验证**：博查 / Tavily 未用真实 Key 实测（只按官方 API 文档实现并以假端点测试）；macOS / Linux 未验证。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | All checks passed |
| 聚焦 | `pytest -q tests/test_chat_thinking_web_search.py tests/test_chat_subsystem.py tests/test_chat_service.py tests/test_file_interpret.py tests/test_api_provider_list.py tests/test_overlay_chat_proactive.py tests/test_requested_regressions.py tests/test_vision.py tests/test_architecture.py` | 272 passed, 3 skipped |
| 断言有效性 | 基线上跑新测试文件 | collection error（`ImportError: cannot import name 'WebSearchSettings'`） |
| 全量 | `python -m pytest -q`（CI 同款 ignore 参数 + 隔离族） | 见 PR 描述（Python 3.11.5，Windows） |

## 七、已知限制与后续

- 免 Key 引擎依赖网页结构，页面改版会失效；频繁使用会触发人机验证（如实报错，不绕过）。
- 未做设置页三档宽度 × 明暗主题的截图矩阵；本机只核验了默认宽度、浅色主题下分组与依赖可见性。
- 经典窗口与快捷气泡只显示状态文字，没有折叠面板。
- 本 PR 之前产生的回复没有保存思维链，无法回显。

## 八、风险与回滚

- 影响面：所有经 `OpenAICompatibleProvider.stream` 的对话（默认设置下行为不变：不发新参数、不联网）；AI 设置页新增一个分组。
- 配置：新增 `chat.web_search` 与 provider 下 `thinking` / `reasoning_effort`；缺键全部回落默认，回滚后旧版本忽略这些键。
- 会话文件：可能出现 `reasoning` / `activity` 两个新键，旧版本读取时忽略。
- 回滚 = `git revert`；已写入的上述键无害残留。
