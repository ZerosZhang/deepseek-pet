# issue #191：现代对话窗末条消息下方空白随轮数增长

> **基线**：`70ef156`（#216 峰谷副标题高度预算，integration 当时 tip；本提交为 fast-forward 直落）
> **分支**：`feature/issue-191-chat-bottom-blank`　**提交**：`d2d7d9a`　**日期**：2026-10-07
> **范围**：2 个文件（实现 1、测试 1），净 `+62 / −1`
> **关联**：issue #191（用户原声：现代对话窗「对话越多，底部空白越大」）
> **互链**：必备证据章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；对话窗渲染契约见
> [`../CONTEXT.md`](../CONTEXT.md)；本文已登记在 [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

现代对话窗（设置里显示名「肥鱼版 DeepSeek」，`config.py` 默认 `modern`）在会话变长后，
**末条消息下方出现一块随轮数单调增长的空白**，长会话能吃掉大半个视口。根因不是「每个
气泡多一个空行」，而是 Qt 布局账目错位：`wordWrap` 的 `QLabel.sizeHint()` 高度按
启发式宽度算，**大于**实际排版宽度下的 `heightForWidth()` 高度，而助手气泡的纵向
`QSizePolicy.Minimum` 把这个偏大的 `sizeHint` 当成**行最小高**；差额累计后被时间线末尾
唯一的 Expanding 空白垫吃下，于是「每条助手回复固定往底部堆 17px」，与轮数成正比。

修法是**一行策略改动**：助手气泡纵向 `Minimum` → `Preferred`（用户气泡仍是 `Minimum`，
它没有这个病）。修复前后逐条气泡/正文几何在三种窗口尺寸下逐行比对**逐字节相同**，
即只改了「布局对行最小高的记账」，没有任何绘制变化。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 底部空白不再随轮数增长 | 5/10/20 条消息实测末条下方空白 30/75/150px → 全部 **0px** |
| 2 | 外观零变化 | 24 行气泡/正文几何 pre/post 逐字节相同，`CLIPPED=[]`（无裁剪） |
| 3 | 助手气泡仍撑满可用宽度 | 水平策略 `Expanding` 未动 |
| 4 | 短会话顶对齐行为保留 | 末尾 Expanding 垫**留着**（1~4 条消息时它合法占 315/228/140/53px 并随内容增加归零） |

**红线 / 不变量**：
- 用户气泡的纵向策略与外观逐字节不变；
- 助手气泡宽度仍撑满可用时间线宽度（水平 `Expanding` / `_update_bubble_widths` 的 min/max 夹取不动）；
- 消息行插入位置仍在末尾空白垫之前（`insertLayout(count()-1, row)`）；
- 经典窗（`legacy_widgets.py`）一行不动。

## 二、修改文件说明

`git log --numstat d2d7d9a`：

```
6	1	pet/chat/widgets.py
56	0	tests/test_chat_subsystem.py
```

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/chat/widgets.py` | +6 / −1 | `MessageBubble.__init__` 的 `setSizePolicy(...)`：纵向由 `QSizePolicy.Policy.Minimum` 改为 `QSizePolicy.Policy.Preferred if role == "assistant" else QSizePolicy.Policy.Minimum`，并附 5 行注释记录机制与实测数字（75 vs 45、20 条 150px→0）。改的是**行最小高的记账口径**，不碰任何绘制参数。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_chat_subsystem.py` | +56 / −0 | 新增模块级 `_trailing_blank_below_last_message()`（量「末条消息行底边 → 时间线内容区底边」，已扣布局下边距）+ `test_modern_chat_trailing_blank_does_not_grow_with_message_count`，插在 `test_assistant_message_expands_to_available_timeline_width` 之后（同属消息行布局族）。走真实 `_add` 路径灌 5/10/20 条消息。 |

### 未改动（看起来相关但故意没动）

- `pet/chat/legacy_widgets.py`：经典窗实测无病（末尾空白垫恒为 0、末条气泡下空白恒为
  24px 的底边距），一行不动。
- 另两条已被探针证明能消症状的路线**刻意不采用**：① `_update_bubble_widths` 改
  `setFixedWidth`（动的是宽度，影响面更大）；② 摘掉末尾 Expanding 垫（它同时负责短会话
  顶对齐，摘了得用 `setAlignment(Qt.AlignTop)` 替代）。本报告第八节记了取舍理由。

## 三、实现要点

1. **机制闭环（一句话版）**：`_update_bubble_widths` 每次 `_add` 把助手气泡钉成固定宽 →
   气泡里 `wordWrap` 的 body 标签 `sizeHint()` 高度按启发式宽度算（实测 51 vs 实际 34）→
   气泡纵向 `Minimum` 把这个偏大的 `sizeHint` 当行最小高 → 时间线布局总最小高被抬高 →
   `setWidgetResizable(True)` 把内容控件撑到该最小高 → 「布局最小高 − 行实际高度」的差额
   （17px × AI 回复数）只能给唯一的 Expanding 项，即末尾空白垫。
2. **为什么选 `Preferred` 而不是另外两条**：改动面最小（1 行），且**外观零变化是可证的**
   ——三档窗口尺寸 × 每种 8 条消息共 24 行几何逐字节比对无差异，说明只动了记账，没动绘制。
   `pet/chat/widgets.py` 内无其它消费者读气泡的纵向策略，`MessageBubble` 也无其它引用方，
   故不存在"改了策略顺带改了别处"的隐性影响面。
3. **只改助手气泡**：用户气泡纵向保持 `Minimum`——全用户消息会话实测空白恒为 0，
   没有可修的账目错位，不动它可把变更面再收窄一半。
4. **末尾 Expanding 垫保留**：它是「短会话内容顶对齐」的现有实现（1~4 条消息时占
   315/228/140/53px，内容撑满后自然归零）。摘掉它需要引入替代的对齐机制，属另一件事。

## 四、性能分析

**方法（可复现）**：诊断探针 `C:\Users\me\AppData\Local\Temp\dsh191_probe{1..8}.py`
（不入库，交付后删除）；修复侧的对比探针 `dsh191_visual.py`。
环境：Windows / Python 3.13.7 / PySide6 6.11.2；窗口 695×661、滚动视口 442px，
真实 `windows` 平台 + `WA_DontShowOnScreen`（不上屏，但字体度量真实）。

**① 空白随轮数单调增长（真实平台，修复前）**

| 消息数 | 助手回复数 | 末尾空白垫 (px) | 末条气泡下方空白 (px) | 内容总高 | 滚动上限 |
|---|---|---|---|---|---|
| 5 | 2 | 34 | 58 | 544 | 102 |
| 10 | 5 | 85 | 109 | 1065 | 623 |
| 20 | 10 | 170 | 194 | 2089 | 1647 |
| 40 | 20 | 340 | 364 | 4154 | 3712 |

空白垫 ÷ 助手回复数 = **17.0px**，四条数据完全一致。

**② 像素级证据**（渲染 PNG 后扫视口内连续纯白行）：
n=10 → **116px**（视口 26%）／n=20 → **201px**（45%）／n=40 → **371px**（84%）；
对照组（撤掉助手气泡固定宽）n=40 仅 **31px**（就是常态底边距）。
渲染图 `Temp\dsh191_bottom_40.png` 与 `dsh191_bottom_40_nowidthforce.png`。

**③ 逐控件定位**（单条助手回复）：

```text
bubble    width=635  sizeHint.h=84  heightForWidth=67   → 幻影 +17
  body    width=635  sizeHint.h=51  heightForWidth=34   → 幻影 +17   ← 元凶（wordWrap QLabel）
  tools                sizeHint.h=28
  行       geom=67    minimumSize=84                     → 行最小高比实际高多 17 → 全落入末尾垫
```

**④ 修复前 / 修复后对照（同一探针、同一棵树，仅换 `pet/chat/widgets.py`）**

| 消息数 | 修复前 blank | 修复后 blank | 修复前 host_h | 修复后 host_h |
|---|---|---|---|---|
| 5 | 30 | **0** | 522 | 492 |
| 10 | 75 | **0** | 1019 | 944 |
| 20 | 150 | **0** | 1999 | 1849 |

前一行行的 layout `min` 从 78 掉到 48，末尾垫从 150 掉到 0——正是机制闭环。

**⑤ 反证实验（三个独立开关都能消症状，修复前）**：n=20，基线末条下方 174px / 末尾垫
150px；撤掉助手气泡固定宽 → **24 / 0**；气泡纵向 `Minimum`→`Preferred` → **24 / 0**；
摘掉末尾 Expanding 垫 → **24 / 0**。

**结论**：① **稳态开销零变化**——`QSizePolicy` 枚举值改一个（`Minimum`=1 → `Preferred`=4），
布局求解走 Qt 内部同一套缓存，不新增任何计算量；② **新增路径无绝对成本**，本改动甚至
**减少**布局求解量（时间线总最小高 1999→1849，即少解 150px 的分配）；③ **未引入新的
系统调用 / 网络 / 磁盘 / 线程**；④ **内存零增长**——无新增对象、无缓存，仅改一个策略枚举。
条件性开销：`Preferred` 允许气泡被压到 `sizeHint` 之下，实际视口足够时不会触发；
`CLIPPED=[]` 证明无裁剪。

## 五、实机运行记录

**主代理本机验收（真实桌面、真实进程、真实鼠标输入驱动的产品实例）**：

- **用户可见行为确认**：对话窗多轮历史**底部无随轮数增长的空白**——即在真实桌面实例上
  复现原文症状不再出现（修复前同窗口实测 20 条消息 150px，修复后 0）。

**本机真实 Qt 平台（`windows` 插件，非 offscreen）自动验证**：新回归测试在真实 Windows
平台下 `1 passed`（窗口用 `WA_DontShowOnScreen`，不闪桌面）。

**修复前的现场复现（原始输出片段）**：

```text
=== dsh191_probe3（真实 windows 平台，WA_DontShowOnScreen，695×661） ===
消息数   5 | 助手 2  | 末尾空白垫  34px | 末条气泡下空白  58px | 内容总高  544
消息数  10 | 助手 5  | 末尾空白垫  85px | 末条气泡下空白 109px | 内容总高 1065
消息数  20 | 助手10  | 末尾空白垫 170px | 末条气泡下空白 194px | 内容总高 2089
消息数  40 | 助手20  | 末尾空白垫 340px | 末条气泡下空白 364px | 内容总高 4154
空白垫 ÷ 助手回复数 = 17.0px
```

**边界与失败路径（实机/自动已验证）**：

- 经典窗对照：n=5/10/20/40 × 两种窗口尺寸，末尾空白垫**恒为 0**、末条气泡下空白恒为
  24px —— 证明不是「所有聊天窗都这样」。
- 形状探针（post-fix）：全助手 20 条 / 全用户 20 条 / 混合 20 条 / 全短句 30 条，再各追加
  10 条助手消息，空白**全程恒为 0**；窗口缩小 200×120 后仍为 0。
- 几何对照（pre/post）：695×661、1180×700、560×520 三种尺寸、每种 8 条消息共 24 行，
  `bubble/body` 宽高与 `heightForWidth` 全部逐字节相同，`CLIPPED=[]`。

**无法自动验证的能力（如实登记）**：**未取到 issue 截图**——附件 URL 本机连续 5 次连接
超时，且当时模型无法读图。「报 issue 的是现代窗」靠三条旁证：① 默认 `modern`；② 截图
尺寸 695×661 超出经典窗最大宽度 560（经典窗物理上不可能是这个尺寸）；③ 探针恰好在
695×661 复现出与描述一致的现象（含 695<880 的窄版无侧栏布局）。诚实边界：探针为
离屏/不上屏窗口，**未在 reporter 实机 DPI/字体下复现**，绝对像素值会随字体变化，
但「17px/条 → 单调增长」是结构性结论。

**一次需要报备的异常（非本次交付的失败）**：rebase 后第一次全量在 03:50:34 于 67% 处
中断（exit 1、无 summary、输出在缓冲区被截断）。排查结论是**外部终止**：无任何 FAILED
输出、输出死于进度条中途（缓冲区未 flush，符合被 TerminateProcess/taskkill 的特征），
且 03:51:25 有兄弟代理的新 pytest 进程起来（03:44–03:50 期间机器上有另一代理在跑测试）。
已排除两个本仓嫌疑点后静默重跑同一棵树 → 全绿，未复现。

## 六、测试与验证

**红 → 绿（先写测试、后写实现）**

| 用例 | 写实现前 | 实现后 |
|---|---|---|
| `test_modern_chat_trailing_blank_does_not_grow_with_message_count` | **红**：`max([45, 75]) > 24` | 绿：`[0, 0]` |

断言取**方向式**而非「极差 ≤ 24」：messages<5 时内容比视口矮，空白很大是**合法**的
（实测 1→5 条为 315/228/140/53/0 递减）。双向极差断言会在「5 条尚未撑满视口」的机器上
假红，方向断言在那边仍然成立。

**判别力（反证实验已固化）**：探针 D 的三个独立变体各自都能把空白压到常数，说明
「行最小高记账」是唯一机制；其中被采纳的那一条正是本实现。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | `All checks passed!`（最终提交后复跑） |
| 聚焦（chat 族） | `test_chat_subsystem / chat_themes / chat_attachments / chat_shared_behavior / chat_safe_emit / quick_chat / island_chat / overlay_chat_proactive` | `229 passed, 1 skipped` |
| 聚焦（追加回归族） | 加 `requested_regressions + first_batch_features` | `284 passed, 2 skipped` |
| 真实 Windows 平台 | 新回归测试，不带 offscreen | `1 passed` |
| 全量（rebase 前，基 `0ba442c`） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | `4422 passed, 11 skipped`，EXIT=0 |
| 全量（最终提交 `d2d7d9a`，基 `70ef156`，含 #216） | 同上 | **`4441 passed, 11 skipped`**，EXIT=0 |
| 集成全量（当晚最终树） | `QT_QPA_PLATFORM=offscreen python -m pytest -q`（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

提交信息只改过措辞，**tree hash 前后均为 `8725f1ae…`**，故上述全量结果对最终提交逐字有效。

## 七、已知限制与后续

1. **绝对像素值依赖字体度量**：17px/条是「本机 Windows 默认字体 + 695×661 视口 +
   442px 滚动视口」口径下的实测值；换字体/换缩放后单个气泡的幻影高度会变，但
   「幻影高度 = sizeHint − heightForWidth」这一结构关系与「随轮数单调增长」的性质不变。
2. **未在 reporter 实机 DPI/字体下复现**（见第五节）。
3. **短会话的空白是合法的**：内容未撑满视口时末尾垫会占高度，这是顶对齐的既有设计，
   不是缺陷；回归测试用方向断言把这一区分写进了断言里。
4. **未做**：issue 后半段提到的「直播适配 OBS 黑屏」不属本条——它已被随后落地的
   「直播捕获 Phase A」重写覆盖（见
   [`PR-REPORT-STREAM-CAPTURE-PHASE-A-2026-10-07.md`](PR-REPORT-STREAM-CAPTURE-PHASE-A-2026-10-07.md)），
   对话空白这半没有被任何后续提交碰过（本分支的改动对象与那份报告无交集）。

## 八、风险与回滚

- **影响面**：`pet/chat/widgets.py` 单个 `setSizePolicy` 参数；唯一消费者是
  `MessageBubble` 的父布局。已实测「改前改后几何逐字节相同」，故**外壳观感风险为零**；
  风险集中在「极端窄视口下气泡是否被压扁」——`Preferred` 允许压缩，实测最小到 200×120
  仍无裁剪（`CLIPPED=[]`）。
- **配置迁移**：无新增配置键、无落盘数据变更。
- **回滚**：`git revert d2d7d9a` 即可，无残留状态。回滚后可临时规避：
  聊天设置 →「对话窗口」切到**「肥鱼牌小手机」**（经典窗实测不受影响）。
- **合并冲突面**：9 个兄弟分支（#216/219/220/211/228/210/172/208/209）相对 integration
  **都不碰** `pet/chat/widgets.py` 与 `tests/test_chat_subsystem.py`（已实测），冲突面为空。
- **分支状态**：本提交已 fast-forward 落入 `integration/2026-10-07-night-batch`；
  分支均未 push、PR 未开。
