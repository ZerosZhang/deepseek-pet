# PR 报告：issue #216 余额气泡峰谷副标题参与高度预算（`PR-REPORT-ISSUE-216-BALANCE-SUBTITLE-2026-10-07.md`）

> **基线**：`0ba442c`（整合分支 `integration/2026-10-07-night-batch`，四份交付报告与 INDEX 登记）
> **分支**：`feature/issue-216-balance-subtitle`　**日期**：2026-10-07
> **范围**：4 个文件（实现 1、测试 1、报告 1、索引 1）
> **关联**：上游 issue #216（v4.2.1 报告）；相关实现 `pet/speech_bubble.py`（气泡控件）、
> `pet/app.py::_show_balance_payload`（余额文案 → `show_bubble(subtitle=...)`）；
> 相关文档 [`BUGFIX-AND-FEATURES-2026-08-24.md`](BUGFIX-AND-FEATURES-2026-08-24.md)（呼吸泡尺寸口径）。

## 一、核心特性

issue #216 报告余额气泡的峰谷副标题「DeepSeek 当前高峰 · 下一空闲 18:00」——
①跨到气泡轮廓外 ②换行后第二行被窗口底边裁掉 ③未着色的灰字落在深色桌面上看不清。
报告人给的推测（「气泡高度预算只按正文行数算，副标题没参与」）经复现**成立**，且实测
**两条**独立机制，都指向同一句话：

| # | 机制 | 触发条件 | 症状 |
|---|---|---|---|
| M1 | 副标题宽度上限写死 248px、不随「气泡文字大小」缩放也不跟随气泡变宽；Qt 按高度定尺寸时用**未夹取**的宽度算行数，布局与绘制却按 248 夹取 | 气泡内宽 > 248px（`bubble_text_scale` > ~1.02 或长正文把列宽撑开） | 副标题多出一行 → 高度预算少一行 → 末行被自己的 label 裁（②），气泡也跟着矮一截 |
| M2 | 吐气水泡画布高度只按**正文**算：正文盒先把内高吃满，副标题只能吃边角 | 呼吸泡 + 任意副标题（默认设置即可复现） | 副标题分配高度 < 要画的行高 → 末行被裁（②）；被裁剩的半行落在有机轮廓之外（水泡底部两角向内收）→ 文字画到透明区（①③） |

**用户可见变化**：带副标题的气泡（余额峰谷、提醒建议、文件解读提示等）不再被裁；
呼吸泡在带副标题时按需等比放大画布（形状不变，只是整体大一圈），四个标准泡**尺寸逐像素不变**
（实测 200×79 / 243×98 / 305×118 / 447×161 前后一致，只是副标题用满了气泡本来就有的文本列）。

**红线 / 不变量**：
1. 无副标题的气泡几何**零变化**（回归面收窄，`test_bubble_without_subtitle_geometry_is_unchanged` 锁死）；
2. 带副标题的普通/交互气泡**不被副标题撑爆**：宽度上限同时受「正文 label 宽」与
   「本次文本列宽」夹取——交互气泡的列宽是未缩放的 248，实测（`file_interpret` 形态，
   文字缩放 200%）气泡 268px ≤ 248+26，长副标题不会把它撑到聊天窗宽；
3. 歌词「标题优先」气泡的锁宽/锁高语义不变（`title_first` 分支的显式 `setWordWrap` 判定不动）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/speech_bubble.py` | +152 / −5 | 副标题宽度上限同口径 + 呼吸泡把副标题算进高度预算 + 副标题安全内边距 |

逐处说明：

1. **`__init__` 去掉写死的 `setMaximumWidth(248)`**，改由 `set_style` 按
   `BUBBLE_TEXT_COLUMN × 气泡文字大小` 设初值（`_subtitle_width_floor()`）——样式与字号
   变更时同样重挂，与同处的字号样式表同步。
2. **新增 `_sync_subtitle_max_width(label_width, column)`**：把上限抬到
   `max(正文 label 宽度, min(248 × 缩放, 本次文本列宽))`。修 M1：只要上限 ≥ 气泡真实内宽，
   Qt 定高与布局/绘制两端就同口径，不会再凭空多一行；另一头由 `column` 收口——正文窄时保持
   原上限，交互气泡的列宽未缩放（`BUBBLE_TEXT_COLUMN`），所以长副标题也不会把它撑到聊天窗宽。
   调用点两处：`show_text` 定完 label 尺寸后（传本次实际列宽；呼吸泡传 `None`）、呼吸泡
   `_configure_breath_content` 内。
3. **新增 `_breath_size_for_subtitle(bubble_size) -> (画布尺寸, 正文盒高)`**：修 M2。
   呼吸泡是宽高比锁定的画布（240:195，文字内高 = 画布高 × 95/195），原公式
   `label_height = max(42, inner)` 会把内高吃满。新口径固定为
   `label_height = max(BREATH_LABEL_MIN_H, inner − 副标题预留)`；仍放不下时按需要的总内高
   **等比放大画布**（`h = need × 195/95`、`w = h × 240/195`，最多迭代 3 次收敛，因为画布变宽
   会让副标题少一行）。
4. **新增 `_breath_label_height` / `_breath_subtitle_reserve` / `_breath_subtitle_inset`**：
   呼吸泡的正文盒高度与副标题预留量的唯一出处（不重复公式）。`_breath_subtitle_reserve` 里对
   `heightForWidth` 的 **-1 回退**（歌词「标题优先」会关掉 `wordWrap`，此时 QLabel 的
   `heightForWidth` 返回 -1）退回 `sizeHint().height()`，否则预留量会被算成 0。
5. **副标题左右安全内边距 `BREATH_SUBTITLE_SIDE_INSET = 14`**（参考画布 240 宽的比例，按画布等比）：
   只作用于呼吸泡的副标题（`setContentsMargins`），非呼吸泡形态在 `set_style` 复位为 0。
   依据：有机轮廓底部两角向内收到画布宽的 ~13% / ~86%，左对齐的副标题末行正好压在轮廓外沿上
   （像素实测：不给内边距时呼吸泡副标题有 27~46 个墨迹像素画在轮廓外，给 14 后为 0）。
   正文盒不动（正文居中，天然避让两角）。
6. **`set_style` 的 else 分支复位副标题 `contentsMargins(0,0,0,0)`**：呼吸泡 → 标准泡切换时不残留内边距。

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_bubble_subtitle_budget.py` | 新增 +199 | 17 条：4 标准泡 × 3 档文字缩放（1.5/2.0/3.0）的副标题预算、呼吸泡 3 档（1.0/1.5/2.0）的预算 + 轮廓内含 + 画布内高容得下正文盒与副标题、无副标题几何不变、交互气泡宽度红线（`file_interpret` 确认气泡带副标题的形态） |

判据都是机器可判定的：`QLabel.heightForWidth(实际宽度)`（与真实绘制同源的「要画多高」）
≥ 分配高度；宽度上限 ≥ 气泡内宽；文字底边 ≤ 已绘制轮廓；呼吸泡再做一次**像素级**轮廓内含
（渲染两次取差 = 文字墨迹，逐个用 `QPainterPath.contains` 判内外，容差 4 像素吸收抗锯齿）。

### 未改动（明确声明）

- **双字词断行（「赠送」被拆开）不做**：副标题走 QLabel 富文本自身排版，不在本改动的
  `_wrap_bubble_lines`（正文字符级换行 + 避头尾）路径上，要做得另造 CJK 断词布局器，超出本 issue 范围；
- **`app.py::_show_balance_payload` / `balance.py` 未动**：文案与颜色策略（高峰红/低谷绿 +
  预设前景色）本身是对的，灰字看不清是「文字被画到气泡外」的后果，随 M1/M2 修复自动消失；
- **`speech_bubble_text.py` 未动**：纯函数区的分页/列宽口径不变。

## 三、实现要点

**为什么 M1 是「Qt 定高口径 ≠ 绘制口径」**（探针实测，`QT_SCALE_FACTOR=1.75`、`bubble_text_scale=2.0`、
正文「余额情况：余额 ¥12.34」）：

```
adjustSize 前：sub_maxWidth=248  sub.heightForWidth(248)=69（3 行）
               布局 sizeHint=(398,134)   widget.sizeHint()=(398,111)   ← 差一行
adjustSize 后：widget=398x111  sub 分到 46px（2 行，按未夹取的 372 宽算的）
绘制时：      sub 实际宽度 248（被上限夹取）→ 要 69px，只有 46px → 第 3 行被裁
```

Qt 的 `QWidget::sizeHint()`（含 heightForWidth 分支）按**未夹取**的宽算行数，而布局与绘制按
`maximumWidth` 夹取；两者只有在「上限 ≥ 真实内宽」时才等价。改法就是把上限抬到内宽，
而不是去猜行数。

**为什么呼吸泡要「让位 + 必要时放大」而不是只让位**：正文盒退到下限仍放不下时，
若只让位会把正文挤成一条缝（正文本身也被裁）；等比放大画布保证两边都完整，且水泡轮廓
由 `_build_breath_bubble_geometry` 按画布宽高各自换算（`sx`/`sy`），等比缩放下水泡形状不变。
备选方案「让位 + 允许正文裁」被否（引入新的裁切）；「只放大不让位」也被否（带副标题的呼吸泡会
放大 60% 以上，观感突变）。

**为什么偏移量用比例常量而不是测轮廓**：轮廓是 5 段三次贝塞尔，安全区的精确矩形要逐行扫描
路径求交（成本高、且矩形安全区对有机形状本来就是近似）。实测「底部两角内收到画布宽 ~13%」是
这条曲线的稳定性质，用 14/240 的左右内边距即可覆盖（实测有 4px 余量），并且随画布等比缩放。

## 四、性能分析

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen python tools/../issue216_probe13.py`（探针脚本
不进仓库，命令与脚本见本节末）；环境：Windows 10 x64 / CPython 3.13.7 / PySide6 6.11.2 /
offscreen 平台 / 每形态 1000 次 `show_text`（预热 20 次后取样，取中位数与 p95）。
被测量路径：`PetSpeechBubble.show_text`（气泡每次显示的唯一入口，余额/提醒/自言自语都走它）。

| 指标（median / p95，ms） | 修复前 | 修复后 | 归属 |
|---|---|---|---|
| 标准泡 · 无副标题 | 0.314 / 1.574 | 0.300 / 1.402 | 热路径（噪声内，−0.014） |
| 标准泡 · 带副标题 | 0.455 / 1.465 | 0.479 / 1.712 | 热路径（噪声内，+0.024） |
| 标准泡 · 带副标题 scale=2.0 | 0.483 / 1.598 | 0.472 / 1.560 | 同上（−0.011） |
| 呼吸泡 · 带副标题 | 0.434 / 1.534 | **0.847 / 1.948** | 新增路径（每次显示 1~2 次高度测量，+0.41） |

**结论**：

1. **稳态开销**：标准泡无副标题（自言自语/普通气泡，最高频）在测量噪声内（±0.03ms）；
   标准泡带副标题同样在噪声内。三个标准泡档位的差值都 ≤ 0.024ms。
2. **新增路径的绝对成本与触发频率**：呼吸泡 + 副标题每次显示 +0.41ms（0.43 → 0.85ms），
   来自 1~2 次 `QLabel.heightForWidth`（富文本走 QTextDocument 排版）。触发频率由调用方决定：
   余额气泡（`balance_refresh_minutes` 默认 0 = 不自动刷新，只有用户点余额/缓存命中）、
   提醒气泡（审批/看门狗）、文件解读提示——都是**离散事件**，不是每帧路径；0.85ms 相对
   60fps 的 16.7ms 帧预算约 5%，且只在气泡出现那一拍付。（已做一步省算：呼吸泡的高度测量
   结果由 `_breath_size_for_subtitle` 返回给调用方复用，不再重复 `heightForWidth`；
   省下的约 0.08ms 见上面「优化前 0.915ms」的中间测量。）
3. **有没有新的系统调用 / 网络 / 磁盘 / 线程**：没有。改动只做内存里的度量与布局；
   呼吸泡新增的只是 QLabel 度量与 `QSize` 运算，不碰 IO。
4. **内存与缓存**：没有新增缓存/容器/常驻对象；`_breath_size_for_subtitle` 的中间量全是局部
   `QSize`/`int`，函数返回即释放。呼吸泡画布在带副标题时变大（168×137 → 187×152，约 +39% 面积），
   是**额外绘制面积**而非常驻内存；气泡是透明 Tool 窗、按需重绘（`_breath_geometry_key` /
   `_surface_geometry_key` 签名缓存未变），静止期零重绘。

## 五、实机运行记录

**本机真实环境**：Windows 10 x64、屏幕 2560×1440、DPR 1.0、Qt 平台插件 `windows`、
应用字体 **Microsoft YaHei UI 9pt**、PySide6 6.11.2、CPython 3.13.7。
探针建**独立**气泡小窗（不启动 pet 应用、不碰正在运行的桌宠进程——验证前后
`Get-Process -Id 33084` 均在同一进程上，`dsh-pet-standalone-webm-chat`，启动时间 2026/10/7 2:14:14），
命令与原始输出：

```
python %TEMP%\issue216_probe12.py      # 真平台 + 真字体，逐例打印几何/分配够不够/轮廓外墨迹数
平台插件=windows 屏幕=2560x1440 DPR=1.0 逻辑DPI=96 字体=Microsoft YaHei UI 9.0pt
```

**修复前（同一探针，真机真字体）** —— 复现了报告的核心症状：

| 用例 | 副标题分配/需要 | 轮廓外墨迹 | 判读 |
|---|---|---|---|
| `classic_top` scale=3.0 | 76px / **114px** | 0 | **末行被裁**（「分配够=否」） |
| `breath_bubble` scale=3.0 | 97px / **114px** | **113 px** | 末行被裁 + 文字画在轮廓外 |
| `breath_bubble` scale=2.0 | 50 / 50 | **13 px** | 文字压在水泡轮廓外沿 |
| `breath_bubble` scale=1.0（充值/赠送正文） | 26 / 26 | **53 px** | 同上（正文更长 → 水泡更宽，副标题仍贴边） |
| `breath_bubble` scale=1.0 | 26 / 26 | 4 px | 同上（轻） |
| `classic_top` scale=1.0 / 1.5 / 2.0 | 够 | 0 | 该档未触发 |

**修复后（同机同探针）**：9 个用例全部「分配够=是」且「轮廓外墨迹=0」：

```
classic_top    scale=1.0  气泡=200x79   sub=(13,39,174,23) hfw=13 分配够=是 上限=248 正文宽=142
classic_top    scale=1.5  气泡=243x98   sub=(13,43,217,38) hfw=38 分配够=是 上限=372 正文宽=217
classic_top    scale=2.0  气泡=305x118  sub=(13,51,279,50) hfw=50 分配够=是 上限=496 正文宽=279
classic_top    scale=3.0  气泡=447x161  sub=(13,68,421,76) hfw=76 分配够=是 上限=744 正文宽=421
breath_bubble  scale=1.0  气泡=187x152  sub=(22,92,124,26) hfw=26 分配够=是 上限=248 轮廓外墨迹=0
breath_bubble  scale=1.5  气泡=252x205  sub=(29,121,168,38) hfw=38 分配够=是 上限=372 轮廓外墨迹=0
breath_bubble  scale=2.0  气泡=336x273  sub=(39,161,224,50) hfw=50 分配够=是 轮廓外墨迹=0
breath_bubble  scale=3.0  气泡=504x410  sub=(59,242,336,76) hfw=76 分配够=是 轮廓外墨迹=0
breath_bubble  scale=1.0（充值/赠送正文） 气泡=196x159 sub=(23,97,131,26) 分配够=是 轮廓外墨迹=0
```

四个标准泡的**气泡尺寸与修复前逐像素一致**（200×79 / 243×98 / 305×118 / 447×161），
即 M1 的修复没有付出任何尺寸代价；呼吸泡带副标题时按需变大（168×137 → 187×152）。

**DPR 复核**：同一探针在 `QT_SCALE_FACTOR=1.75`（DPR 1.75，模拟报告人的大 DPR 环境）与
`QT_SCALE_FACTOR=2.0` 下重跑，9 个用例同样「分配够=是、轮廓外墨迹=0」。

**边界与失败路径**：
- 无副标题的气泡：几何断言 `bubble.height() == label.height() + 上下边距` 成立（零变化）；
- 图像气泡（配图自言自语）：`_breath_size_for_subtitle` 早退，尺寸实测与修复前一致（231×188）；
- 交互（审批/提问）气泡：列宽仍是基础 248px 不缩放，副标题上限退化为 248px 与原行为一致
  （`_sync_subtitle_max_width` 里 `max(248, label_width≤248) = 248`）。

**无法自动验证的能力**（诚实登记）：
- **未在报告人的机器 / 未在 175% 缩放的真机桌面上目视确认**：本机 DPR 1.0，`QT_SCALE_FACTOR`
  只是模拟 DPR（屏幕逻辑分辨率随之变小，见输出 1463×823），不等价于真机 175% 缩放；
- **未做真实桌面截图目视**：探针把气泡窗口 grab 成 PNG 存档
  （`%TEMP%\issue216_real\*.png`，修复前/后同名覆盖，最后一组为修复后），未在真桌面截图对比；
- **未用报告人的字体复现**：本机 YaHei 下副标题在标准泡里恰好一行（174px 宽），
  报告人截图是两行——**裁切是字体度量相关的**，本机复现到的裁切实例是 `classic_top scale=3.0`
  与 `breath_bubble scale=3.0`（分配 76/97 vs 需要 114）。
- **无 macOS 机器**：`.agents/skills/desktop-pet-ui-style/SKILL.md` 要求的「真 Cocoa 截图」
  本次无法提供（本机 Windows）；该 skill 的其余要求已满足——文字布局改用字体度量而非固定高度、
  复用既有气泡控件（未新增视觉基元）、`git diff --check` 与全量套件见第六节。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | `All checks passed!` |
| 回归红（先跑） | `QT_QPA_PLATFORM=offscreen pytest -q tests/test_bubble_subtitle_budget.py` | **15 failed / 1 passed**（`DPR 1.0` 与 `QT_SCALE_FACTOR=1.75` 两轮同结果；失败原文见下）。红的 15 条是「副标题被裁 / 上限窄于内宽 / 轮廓外墨迹」；唯一先绿的是「无副标题几何不变」（对照项，本就不该红）。后来补的「交互气泡宽度红线」是**护栏杆**（改前后都绿，防的是未来把上限放开）。 |
| 回归绿（改后） | 同上 | **17 passed** |
| 聚焦 | `pytest -q tests/test_speech_bubble.py tests/test_sprite_bubble.py tests/test_bubble_text_scale.py tests/test_bubble_subtitle_budget.py tests/test_music_lyric.py tests/test_alert_queue.py tests/test_flight_bubble_suppression.py tests/test_overlay_bubble_wiring.py` | 206 passed（含改前基线） |
| 关联（按被改符号 grep 出的文件） | `pytest -q tests/test_desktop_pet_features.py tests/test_quick_chat.py tests/test_architecture.py` | 108 passed |
| 交付报告纪律 | `pytest -q tests/test_pr_report_discipline.py` | 85 passed（本报告 + INDEX 登记在册） |
| 空白/行尾 | `git diff --check` | 干净（exit 0） |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | 见下「全量结果」 |
| 消融式复核（改前 96 例病态 → 改后 0） | `issue216_probe4.py`（300 组合 = 5 风格 × 4 正文 × 5 文字缩放 × 3 DPR 档） | 修复前 96 broken（SF=1.0 与 SF=1.75 各一轮），修复后 **0 broken / 0 broken** |

红→绿原文（第一条）：

```
E  AssertionError: classic_top scale=1.5: 副标题宽度上限 248px 窄于气泡内宽 286px——定高口径与绘制口径分叉，副标题会多出一行
E  AssertionError: classic_top scale=2.0: 副标题被自己的 label 裁——分配 46px，按 248px 宽排版需要 69px（气泡 398x111）
E  AssertionError: breath_bubble scale=1.0: 副标题被自己的 label 裁——分配 30px，按 112px 宽排版需要 36px（气泡 168x137）
15 failed, 1 passed in 1.55s
```

**全量结果**：`4440 passed, 11 skipped, 232 warnings in 694.46s (0:11:34)`
（`QT_QPA_PLATFORM=offscreen python -m pytest -q`，本机 Windows 10 / CPython 3.13.7 / PySide6 6.11.2；
其中 17 条是本次新增的回归用例，即修复前基线为 4423 passed / 11 skipped）。

**未跑的门禁**：本改动不涉线程/时序/并发（气泡是单线程 GUI 对象，无新增线程/定时器），
故未做「受影响时序族高负载复跑」；`tests/test_architecture.py` 的行数预算用例随关联门跑过
（`pet/speech_bubble.py` 无行数预算）。

## 七、已知限制与后续

1. **呼吸泡带副标题会变大**：最小画布 168×137 → 187×152（+27% 宽），这是为了让正文盒和副标题
   都完整。若 owner 认为观感突变不可接受，可改为「让正文盒缩到正文真实高度（不放大画布）」，
   代价是正文文字上移约 20px（当前实现改动更小、语义更直白）。
2. **超长副标题仍会被裁，且这是既有边界**（本次严格变好、未引入回归）：呼吸泡画布有 320×缩放
   的设计上限（`BREATH_CANVAS_MAX_W`，与 `_breath_size_for_content` 同源），实测（offscreen，
   `issue216_probe14.py`）：

   | 用例（正文「余额情况：余额 ¥12.34」） | 修复前 分配/需要 | 修复后 分配/需要 |
   |---|---|---|
   | 呼吸泡 · 150 字副标题 · scale=1.0 | 30 / 166 | **78 / 106**（仍裁，但好很多） |
   | 呼吸泡 · 150 字副标题 · scale=3.0 | 97 / 660 | **310 / 310（不再裁）** |
   | 呼吸泡 · 400 字副标题 · scale=3.0 | 97 / 1745 | 332 / 835（仍裁） |
   | 标准泡 · 150 字副标题 · scale=3.0 | 310 / 660 | 240 / 310（仍裁） |

   说明：不带缩放时约 ≤100 字的副标题已能完整放下（修复前约 ≤50 字）；再长属于「气泡不该承载的
   长度」，需要另立需求（例如副标题超长时截断加省略号，走 `truncate_bubble_text`）。
3. **双字词断行未做**（理由见「未改动」）。
4. **未做「窗口可用高度保护」**：issue 建议里的第三条本次未实现——实测症状的裁切边界是
   **副标题 label 自身矩形**（不是屏幕/窗口边界），`_place` 已有的超高顶边贴齐逻辑未参与其中；
   只有当气泡整体高于屏幕可用区时才会撞到屏幕下边界，那是另一个问题（放大到 300% 时可见），
   本次不夹带。
5. **副标题颜色未单独改**：③「灰字在深色桌面看不清」是文字画到气泡外的后果（背景透明 → 露出桌面），
   M1/M2 修好后文字回到气泡内，预设前景色在其背景上对比度本就足够（`glass_right` 深色泡用浅字、
   其余浅色泡用深字）。若 owner 仍要「副标题背景自适应取色」，属于另一条需求（需先定义
   "实际背景"的判定口径），不在本 issue 范围内。
6. **报告人环境的实证复现缺口**：本机无法完全复刻报告人的字体/缩放组合（见「无法自动验证」），
   已用「机制 + 像素」两级证据替代；建议合并后在报告人机器上按 issue 回复模板确认。

## 八、风险与回滚

- **影响面**：只有 `PetSpeechBubble` 的副标题宽度上限与呼吸泡画布/正文盒计算；
  标准泡尺寸实测不变，呼吸泡仅在「带副标题」时变大；无副标题路径零变化。
- **开关/配置**：没有新增配置键，没有配置迁移；`bubble_text_scale` / `self_talk_bubble_style`
  语义不变。
- **回滚**：`git revert <本分支提交>` 即可，无落盘数据、无残留状态（气泡是纯运行时对象）。
- **风险点**：呼吸泡画布放大后 `_breath_size_for_content` 的宽高比关系仍成立（等比放大），
  `test_desktop_pet_features.py` 的呼吸泡尺寸口径用例已随聚焦门跑过（108 passed）。

## 九、合并注意点

- **分支拓扑**：`feature/issue-216-balance-subtitle` 从 `integration/2026-10-07-night-batch`
  （`0ba442c`）切出，只改 `pet/speech_bubble.py` + 新增一个测试文件 + 本报告 + `docs/INDEX.md`；
  与整合分支上其它批次（三端穿透 / 直播捕获 / #219 / #220）**无文件重叠**，预期无冲突。
- **上游同区改动需留意**：任何同时改 `speech_bubble.py` 的「副标题宽度上限 / `show_text` 定尺寸顺序 /
  呼吸泡尺寸」的改动会与本分支语义重叠；`_subtitle_width_floor` / `_sync_subtitle_max_width` /
  `_breath_size_for_subtitle` 三个方法名是本分支新增的唯一接缝。
- **未执行的外部动作**（须 owner 点头）：push、开 PR、在上游 issue #216 下回复。
  建议的关闭口径（供 owner 参考）：
  > 已定位：副标题的高度预算没进气泡尺寸计算，两条路径都修了（标准泡的宽度上限口径 +
  > 吐气水泡的画布高度预算），回归用例与真机渲染都已验证。请更新到含本次修复的版本后，
  > 若仍能复现，请附上「气泡样式 / 气泡文字大小 / 系统缩放」三项设置。
- **不夹带**：本次不含「窗口可用高度保护」「副标题背景自适应取色」「双字词断行」三项
  （理由见第七节），它们若要落地应各自独立成单。
- **回滚后残留**：无（无配置键、无落盘状态）；回滚即恢复旧观感（呼吸泡带副标题时变小、
  副标题可能再次被裁）。

---

## 附：探针脚本（不进仓库，均可重跑）

| 脚本（`%TEMP%` 下） | 作用 |
|---|---|
| `issue216_probe4.py` | 300 组合布局 fuzz（风格 × 正文 × 文字缩放 × DPR 档），输出「有病」清单 |
| `issue216_probe9.py` | 像素级：副标题墨迹是否落在已绘制轮廓内 |
| `issue216_probe12.py` | 真机（真平台插件 + 真字体 + 本机 DPR）复核 + PNG 存档 |
| `issue216_probe13.py` | `show_text` 耗时对照（n=1000） |
