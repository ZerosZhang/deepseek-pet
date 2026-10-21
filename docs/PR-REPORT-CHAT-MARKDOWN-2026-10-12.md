# PR 报告：AI 对话窗口回复支持 Markdown 渲染

> **基线**：`ee699c7`（Merge PR #233 feature/agent-link-subtraction）
> **分支**：`feat/chat-markdown-render`　**日期**：`2026-10-12`
> **范围**：5 个文件（实现 2、测试 2、文档 1 + INDEX 登记）
> **关联**：与 [#248](https://github.com/MerZlin/dsh-pet-indesktop/pull/248)（时间线空白修复）同改 `pet/chat/widgets.py`，但改的是不同函数，互不依赖

## 一、核心特性

现代风格 AI 对话窗口里，模型回复中的 `**加粗**`、列表、表格、代码块原样显示成 Markdown 源码。本 PR 让**助手气泡**按 Markdown 渲染，
用户自己发的消息仍是纯文本（用户打的 `*`、`#` 不会被误当格式）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | GitHub 方言渲染 | 标题、加粗/斜体、有序/无序列表、表格、引用、行内代码、代码块、链接（可点击，系统浏览器打开） |
| 2 | 原始 HTML 不渲染 | `MarkdownNoHTML`：模型输出里的 `<b>`、`<img>` 等按字面显示（联网/网页内容可能诱导模型吐标签） |
| 3 | 单换行保留 | 标准 Markdown 会把单换行并成一段，桌宠回复常用单换行分句；围栏代码块内不处理 |
| 4 | 表格可紧跟文字行 | md4c 不允许表格打断段落，模型常写「如下：」换行就画表——检测到表头时补一个空行 |
| 5 | 复制原文 | 复制按钮复制 Markdown 源码；新增 `MessageBubble.content` 作为读取原文的公开接口 |
| 6 | 流式节流 | 单次渲染+排版超过 8 ms 时，流式期间的重排合并到定时器（50–250 ms 自适应），结束时立刻渲染终稿 |

**红线 / 不变量**：用户气泡、错误提示（`请求失败：…`）保持纯文本；会话落盘的 `content` 仍是模型原文（不存 HTML）；
打字机节奏、流式跟随/贴底逻辑不变；不引入第三方依赖（用 Qt 自带 md4c：`QTextDocument.setMarkdown`）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/chat/markdown_view.py` | +76 / −0（新增） | `preserve_line_breaks()`：段内单换行→硬换行（行尾两空格），代码块内原样，表头前补空行；`markdown_to_html()`：`QTextDocument.setMarkdown(GitHub \| NoHTML)` → `toHtml()`，去掉文档级 `<body style>`（让气泡沿用 QSS 字体字号），代码片段统一换等宽字体 + 浅底色，h1/h2 各缩一档，链接着主题蓝。 |
| `pet/chat/widgets.py` | +44 / −5 | `MessageBubble`：助手气泡用 `TextBrowserInteraction` + `setOpenExternalLinks`；`set_content(text, *, markdown=None)` 记原文并按角色决定渲染方式；新增 `_render_body()`（实际渲染，记录耗时）、`content` 属性、流式节流定时器；`set_state()` 离开流式状态时冲刷待渲染内容；复制按钮改复制原文。`ChatWindow._error`：错误文案 `markdown=False`。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_chat_markdown.py` | +70 / −0（新增） | 单换行/代码块处理；表格紧跟文字行仍成表；加粗/代码/表格/链接渲染、原始 HTML 转义、不覆盖气泡字体；助手气泡渲染但复制原文、用户气泡与错误文案纯文本；慢渲染在流式期间被节流、结束时冲刷。 |
| `tests/test_chat_subsystem.py` | +5 / −5 | 既有两条用例原来断言 `bubble.body.text()` 等于原文；助手正文现在是渲染后的 HTML，改为断言新公开接口 `bubble.content`（语义不变：读气泡原文）。 |

### 未改动（故意）

- 经典风格对话窗（`legacy_widgets.py`）与快捷对话气泡（`quick_chat.py`）：版式空间与交互不同，本 PR 只做现代窗口。
- 会话存储与 `PromptBuilder`：落盘与发给模型的都是原文。

## 三、实现要点

- **为什么用 `toHtml()` 而不是 `QLabel.setTextFormat(MarkdownText)`**：后者无法关闭原始 HTML（`MarkdownNoHTML` 只在
  `QTextDocument.setMarkdown` 上可设），也无法统一代码字体与链接色。
- **代码字体替换**：去掉文档级字体后，正文里剩下的 `font-family` 声明只来自代码片段；Qt 按平台写入的等宽族名不同（Windows 实测
  `'Courier New'`，offscreen 为 `'monospace'`），所以按「正文里所有 font-family」统一替换，不写死族名。
- **节流**：先实测再定阈值（第四节）。8 ms 以下照常逐拍渲染，打字机观感不变；超过后按上次耗时 ×4（夹在 50–250 ms）合并。

## 四、性能分析

**方法（可复现）**：offscreen，`MessageBubble` 宽 700，正文 `heightForWidth(660)` + `processEvents()`，每档 n=20 取中位；
流式模拟：6000 字回复每 18 ms 追加 10 字（600 拍），对比节流开/关。
环境：Windows 11 Pro 22631 / AMD Ryzen 7 7800X3D / Python 3.11.5 / PySide6 6.12.0

| 回复长度 | `markdown_to_html` | 渲染+排版（Markdown） | 渲染+排版（纯文本，即基线行为） |
|---|---|---|---|
| 1000 字 | 0.56 ms | 4.16 ms | 0.99 ms |
| 3000 字 | 1.63 ms | 12.69 ms | 3.24 ms |
| 6000 字 | 3.49 ms | 26.03 ms | 7.51 ms |
| 12000 字 | 7.69 ms | 52.63 ms | 14.48 ms |

| 6000 字流式（600 拍） | 节流开（本 PR） | 节流关 |
|---|---|---|
| 实际渲染次数 | 253 | 600 |
| 单拍中位 / p90 / 最大 | 9.58 / 17.91 / 23.9 ms | 29.85 / 48.19 / 61.7 ms |
| 超过 18 ms 的拍数 | 55 | 433 |
| GUI 线程忙碌合计 | 5.37 s | 17.43 s |

**结论**：① 稳态（无输出时）零开销；② 新增成本在渲染：同长度下 Markdown 渲染+排版约为纯文本的 3.5 倍，
短回复（≤1000 字）每拍约 4 ms，打字机观感不变；长回复由节流兜住（6000 字超拍数 433→55）；终稿只渲染一次；
③ 无新的系统调用、网络、磁盘或线程（每个助手气泡多一个单次 `QTimer`）；④ 内存：每个气泡多存一份原文字符串（与 `QLabel` 内的 HTML 同量级）。

## 五、实机运行记录

- **用户可见行为**：本机打包版（`scripts/build_onedir.ps1`，webm-chat 变体）安装含本功能的构建后，用户确认「markdown 好了」（2026-10-12）。
- **离屏截图核验（本机 Windows，`QT_QPA_FONTDIR=C:/Windows/Fonts`）**：一条含二级/三级标题、3 列表格、有序列表、引用、行内代码、Python 代码块与链接的回复——
  表格带边框、代码等宽带底色、链接为蓝色下划线；同会话用户消息里的 `**顺便**` 保持字面。
- **失败路径**：`请求失败：<x> **原样**` 按纯文本显示（用例覆盖）；模型输出 `<b>raw</b>` 显示为字面（用例覆盖）。
- **未验证**：macOS / Linux 上等宽族名与字体回退（替换逻辑不依赖族名，但未真机看过效果）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | All checks passed |
| 断言有效性 | 基线 `ee699c7` 上跑 `tests/test_chat_markdown.py` | collection error（模块不存在） |
| 聚焦 | `pytest -q tests/test_chat_markdown.py tests/test_chat_subsystem.py tests/test_requested_regressions.py tests/test_file_interpret.py tests/test_overlay_chat_proactive.py` | 219 passed, 2 skipped |
| 全量 | `python -m pytest -q`（CI 同款 ignore 参数 + 隔离族） | 见 PR 描述（Python 3.11.5，Windows） |

## 七、已知限制与后续

- 经典窗口与快捷对话气泡未接入。
- 代码块没有语法高亮、没有「复制代码」按钮。
- 流式中途未闭合的代码块会先按代码块显示，闭合后恢复（md4c 行为）。

## 八、风险与回滚

影响面：现代风格对话窗口的助手气泡显示。无新增配置键，会话文件格式不变。回滚 = `git revert`，无残留状态。
