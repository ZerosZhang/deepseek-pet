# 灵动岛 P2 视觉打磨 + P3 扩展接口（状态点/告警色/淡化/排版审计/卡片/注册接口/GPU 占位）

> **基线**：`b5931c7`（P1 段化重设计报告提交）
> **分支**：`feature/island-segment-redesign`　**日期**：2026-10-07
> **提交**：slice 批 `28d0c39`..`8a59da1`（8 个）+ 评审修复批 `733ca13`（R1/R2）、
> `f4e8188`（R3）、以及本文件定稿所在的 R4 批（astra 保底收口）
> **范围**：slice 批 22 个文件 `+6622/−171`；修复批另有 pet/agent_link.py 等
> （逐批 numstat 见各自提交信息与下文各轮章节）
> **关联**：设计裁决稿 `.scratch/ISLAND-UI-SYNTHESIS-20261007.md`、施工单
> `.scratch/ISLAND-P2P3-SLICES-SPEC-20261007.md`、P1 报告
> [`PR-REPORT-ISLAND-P1-SEGMENT-REDESIGN-2026-10-07.md`](PR-REPORT-ISLAND-P1-SEGMENT-REDESIGN-2026-10-07.md)、
> 扩展接口文档 [`ISLAND-SEGMENTS-EXTENSION.md`](ISLAND-SEGMENTS-EXTENSION.md)、
> 实机截图 `.scratch/island-p1-shots/`（E7）、`.scratch/island-f1-shots/`（GPU 行）

## 一、核心特性

P1 把岛的信息槽段化之后，P2 把「惊艳、好看、耐看、小组件看着方便」落到像素与动效，
P3 把段体系开放给第三方。八个 slice 各自 test-first，全部实测验收。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 状态点五态双通道 | 空闲=中性实心 / 完成=绿(4s 瞬态回落) / 隐藏·离线=中性空心环 / 待确认=accent 空心环（读 dsh_state gated 位）/ 错误=红+感叹矢量；优先级 错误>待确认>工作>隐藏>完成>空闲，8px 同图元 |
| 2 | 告警色 warn/crit + 滞回 | CPU 80/92、内存 85/95、滞回 3pt，只染数值；被折段含告警时 +N chip 左侧 4px 最高级色点（折叠不埋没告警） |
| 3 | 单位弱化双盒 | 数值盒右对齐(13px) + 单位盒左对齐(10px α70%)，`9%→100%` 值盒右缘像素不动 |
| 4 | 高光/暗边软陶笔 | 胶囊内缘上 1px 高光 + 下 1px 暗边，随 squish 形变、不进内容缓存，帧成本 +65µs |
| 5 | 结构变化单侧淡化 | 130ms，仅段增删/折叠/主信息切换/收缩级变化触发；主代理裁决单侧口径（旧渐出+新直绘），未变内容实测三档稀释率 0.000（双侧会闪 ~20%） |
| 6 | 停靠细条停采样 | 细条稳态 = 0 采样器 + 0 定时器 + 0 线程 + 0 syscall；出细条恢复订阅首轮 `--` |
| 7 | 排版账目总审计 | **用户 mandate**：状态点右半 6px 画出胶囊轮廓（trail 缺右内容边距）→ 右缘 19px 对称修正 + chip 盒内居中 + 8 面像素守卫 10 例（含突变检验） |
| 8 | 卡片四分区 | 概览/指标详情（每段一行：值合并串+单位全称+来源+更新时间）/最近消息/操作；高度按内容实测；unsupported 段胶囊零占位（机器保证）、卡片原因行 |
| 9 | 第三方段注册接口 | 零 Qt 公开 API（`register_segment` 等），只交声明不碰 QPainter；超宽 120px 降级候选、恶意段四道护栏 |
| 10 | GPU 能力占位 | 已知 id + 设置页第四行开关；胶囊零占位（逐像素同宽）、卡片原因行（文案写「未接入/占位」，不谎称探测过本机） |

**红线 / 不变量**：宽度白名单不放松（E2 的 severity 只进内容键不进宽度键；E7 的 +13px
是结构面一次性修正）；四态不伪造；采样闸门（折叠/停靠/隐藏三路合流）任一为假即收口；
第三方段拿不到 QPainter；既有四个 `test_dynamic_island_*.py` 一行未删未改。

## 二、修改文件说明

`git diff --numstat b5931c7..HEAD`（8 提交合计）：

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/dynamic_island.py` | +1324 / −82 | E1 状态点五态（`_status_dot_style`/`_paint_status_dot`/4s 瞬态单次表）+ `set_dsh_state`；E4 设备段值/单位拆分与单位盒绘制；E2 告警色主题档/滞回推进（`_update_alert_severity` 在样本到达一刻）/chip 色点；E3 `_paint_bevel` + 单侧淡化五方法；E6 `_strip_hidden`/`_sync_content_sampling` + 8 个翻转点接线；E7 trail 19px + chip 盒内居中 + 删 `_unknown_segment` 重复定义；E5 卡片四分区（`_card_metric_rows`/`_card_height` 实测/每秒 tick 只在展开期）；F1 GPU 占位登记 |
| `pet/island_layout.py` | +134 / −17 | E4 `_InfoSeg.unit` 与双盒排版；E2 `severity`/`alert_dot_x`/`chip_alert: str`；F1 相关常量化 |
| `pet/island_segments.py` | +434 / −11 | E2 告警纯判定（阈值/滞回/`alert_severity`/`highest_severity`）；E4 `split_value_unit`；F1 公开注册面（`SegmentDeclaration`/`register_segment` 等 6 函数 + 5 护栏常量 + GPU 占位常量） |
| `pet/settings_network.py` | +24 / −13 | E2 时期「网络接管」文案清理；F1 GPU 开关行（追加末尾不重排老用户段序） |
| `pet/config.py` | +4 / −1 | F1 `_ISLAND_METRIC_IDS` 放行 `gpu`（常量同源不抄字面量） |
| `pet/app.py` | +6 / −2 | E1 `_on_dsh_state_changed` 转发收敛态原文（success/error/waiting 才到得了岛） |

### 测试（13 个文件，+4374/−66）

9 个新契约文件：`test_island_status_dot.py`（18）、`test_island_unit_box.py`（18）、
`test_island_alert_colors.py`（26）、`test_island_bevel_fade.py`（14）、
`test_island_dock_sampling.py`（10）、`test_island_layout_audit.py`（10）、
`test_island_card_sections.py`（22）、`test_island_segment_extension.py`（42）、
`test_island_gpu_placeholder.py`（8）；4 个既有文件适配新语义（非禁改面，
逐处在提交信息里给过理由）；四个 `test_dynamic_island_*.py` 一行未动。

### 文档

`docs/ISLAND-SEGMENTS-EXTENSION.md`（新增 182 行：第三方段契约/护栏/机器可跑示例/红线）；
`docs/INDEX.md`（登记 + 互链）。

## 三、实现要点

- **告警滞回的推进点在 GUI 读取快照一刻**（`_tick_sys → _update_alert_severity`；按 UI 读取拍，色随显示值——R1 语义裁决），不在绘制期
  惰性算——两次读数之间不绘制是常态，惰性算会漏拍退化成「每次从零开始」（实测 92→91
  被错算成 warn 的假信号就是这么抓到的）。
- **chip 告警级取当刻段列表**而非缓存计划：`_plan_inputs` 刻意不含采样值/severity，
  「文本没变、severity 变了」那一拍照抄计划会停旧账（有专例锁这条）。
- **淡化判据 = `_plan_inputs` 剔除主信息现文案**——否则时间每跳一分钟播一次淡化，
  直接违反「换字零动画」硬规则。
- **排版审计的方法论**：像素断言一律 `qAlpha`（`QColor(QRgb)` 丢 alpha 的坑）；
  offscreen 后端字体度量退化（ascent=pixelSize、descent=0），**绝对垂直像素不可比**，
  chip 居中改用「公式契约 + `_BASELINE_DY` 变异拆开」获得牙齿。
- **注册接口的恶意段四道护栏**：注册期拒注（重复/非法 id/缺字段/阈值倒挂）→ 字符上限
  （度量前截断）→ 字段盒右省略（度量后）→ 异常降 error 态；段坏掉与岛几何无关是
  结构保证（读数永不进宽度键）。
- **F1 的两处如实挂账**：第三方段的胶囊渲染接线、`oversize_segment_ids()` 在收缩流水线
  的消费点——当前第三方段进不了胶囊，候选集恒空，接线属于 F2（文档 §八 现状表）。

## 四、性能分析

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen python -m pytest -q <对应契约文件>`（探针
内嵌于各测试文件）+ 本机实测脚本；环境：Windows 11 / Python 3.13 / PySide6 / 2560×1440。

| 指标 | 实测 | 归属 |
|---|---|---|
| 状态点解析 | 2.27µs/次（改造前 0.76µs，Δ+1.5µs） | 内容重建×2+命中×1+细条每帧×1 |
| paintEvent 稳态帧 | 0.358ms（关软陶笔 0.293ms / P2 前口径 0.294ms） | 两笔 +65µs、结构判据 ~0µs |
| 淡化中单帧 | 0.394ms（130ms 内约 8 帧，之后回落稳态） | 新增（事件级触发） |
| 卡片每秒 tick `_sync_card_labels` | 1.58ms（QSS 同值短路后；初版 3.75ms） | **只在卡片展开期**（收起/隐藏即停表） |
| 卡片展开整窗 render | 1.63ms vs 收起 0.64ms | 展开期 |
| 细条稳态（采样面） | **0 采样器 + 0 采样定时器/线程 + 0 syscall**（`_info_timer`/峰谷表等壳层定时器照旧运行） | E6（采样器对象根本不建） |
| 进/出细条迁移 | 2.5–6.6ms（含真底座线程建/收口） | 事件级 |
| 注册接口 | 注册+注销一轮 4.6µs；`oversize_segment_ids` 0 段 1.5µs（无消费点） | 冷路径 |
| 稳态定时器/线程/syscall/磁盘 | **新增 0**（淡化表 130ms 即销毁、卡片 tick 仅展开期、完成瞬态 4s 单次表） | 全 P2/P3 |

**结论**：① 稳态开销基本不变（+65µs/帧软陶笔是唯一的每帧新增，换「惊艳」主载体）；
② 新增路径全是事件级（淡化 8 帧、卡片 tick 仅展开期、细条迁移毫秒级一次性）；
③ 无新增长驻线程/系统调用/网络/磁盘；④ 内存稳态零增长（实测 `_content_drawn is
_content_pixmap`），淡化期临时多持一张 32KB 旧位图即释。

## 五、实机运行记录

**实机截图自审链（computer-use，真机 2560×1440）**：

1. **E7 右缘修正**：修正前探针实测「最右墨列 = 窗口宽−1（0px 边距）、状态点墨到窗口
   最后一列」；修正后实机截图（`.scratch/island-p1-shots/` 的 521px 版）状态点完整
   收回胶囊内、右缘与左侧 19px 对称（右端 4x 放大确认）。
2. **告警色活体验证**：真机卡片展开态截图——内存 89% ≥ 85 在**胶囊与卡片两处同时
   呈琥珀色**（warn），CPU 33%/网络正常色；GPU 胶囊无占位（521px 与无 GPU 配置同宽）
   + 卡片原因行「该指标不可用：本版本未接入 GPU 采集（占位段）」。
3. **卡片四分区真机全览**：概览（余额 ¥75.19 充值/赠送明细 + 峰谷「当前空闲·下一高峰
   明天 09:00」+ ● 空闲状态行）/ 指标详情四行（含来源与「N 秒前」更新时间实时走动）/
   暂无最近消息 / 三按钮， margins 对称、渲染稳定。
4. **对照实验（意外收获）**：同机部署实例（整合分支旧代码）的岛宽度每秒抖动
   （216→210→207px 连续三帧不同）——#172 旧架构「每秒 setFixedSize」缺陷的活体证据，
   本分支岛宽全程恒定 521px，P1 白名单的实机对照成立。
5. **输入路径说明**：kimi-cu 的 foreground_click 对本应用的无框置顶窗口不生效（新旧
   两岛都不响应，非本分支回归——对照实验），卡片展开截图改用 SendInput 硬件级输入完成。

**边界与失败路径**：offscreen 800px 屏 + 退化宽字体下岛宽 728px 会把「拖到屏中心」
误判成靠边停靠（E6 测试环境脆弱性）——已钉 2560 假屏（`_current_screen` + `_screen_at`
两处选屏），不是产品缺陷；亮底主题状态点绿对比度偏低（1.75:1，E1 越界发现，列入后续）。

**无法自动验证项**：收缩的真实多屏拖拽没有第二块物理屏（`_narrow_to` 实测搜索替代，
P1 报告已登记）；真机 DPI 1.5/2.0 的像素复核未做（offscreen DPR 探针覆盖 1.0/1.5/2.0）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | All checks passed（每 slice） |
| 聚焦（岛+设置+架构+纪律） | `pytest -q tests/test_dynamic_island_*.py tests/test_island_*.py tests/test_settings_network.py tests/test_config_schema.py tests/test_architecture.py tests/test_pr_report_discipline.py` | **665 passed**（F1 后） |
| 全量（E1/E4/E2/E3/E6/E7/E5/F1 各 slice） | `python -m pytest -q` | 5119 / 5137 / 5163 / 5177 / 5187 / 5197 / 5219 / 5275 passed |
| 全量（终验，含 `_unknown_segment` 去重后） | `python -m pytest -q` | **5275 passed, 11 skipped**（737s，空闲机） |
| 突变检验 | E3 五项 + E7 一项（改回双侧淡化/行基线 → 恰对应例红） | 通过 |
| 多轮评审 | astra 两轮 + ops5.5 + 6.1sol 两轮 + Agents-A1 两轮（glm-5.3 渠道不可用，A1 补票） | 见 §九/§十/§十一 逐轮处置账 |

## 七、已知限制与后续

- **F2 挂账**（扩展文档 §八 R1 补全版列全六项）：第三方段的胶囊渲染接线、
  `oversize_segment_ids()` 收缩消费点、配置准入（第三方 id 进 `island_metrics` 白名单）、
  采样生命周期（谁调 `read`/哪个线程/退订口径）、告警原始值与 `updated_at` 进快照、
  GPU 数据源采集。
- **chip 告警是「上一拍的值」**：全折后停采样，色点保持但不刷新——「看不见的段不采样」
  性能契约的必然结果（E2 越界发现，如需消除要给折叠段留最小心跳）。
- **亮底主题**：状态点完成绿对比度 1.75:1 偏低；高光白笔几乎不可见（k3 规格如此，
  保留对称结构）。
- **隐藏期间任务完成是静默的**（岛隐藏即休眠不点瞬态表）；`hideEvent` 停 15s 自动收起
  后 `showEvent` 不复位（pre-existing，E5 越界发现，建议独立 slice）。
- **E5 越界挂账**：被折段在卡片可见但暂停采样（已如实标注「已折叠 · 暂停采样」，恢复
  采样属闸门语义单开）；窄屏 <760px 时卡片详情列压到 96px（420 上限 vs 网络包络 247px，
  两条宽度纪律的取舍待拍板）。

## 八、风险与回滚

**影响面**：集中在灵动岛（胶囊/细条/卡片/设置页岛小节）+ `app.py` 转发语义
（压布尔 → 传收敛态原文）+ `agent_link.py` 一处停止呈现语义（R3：关闭 DSH 联动
时经收敛管线发 offline 复位锁存态 + 迟到队列信号隔离）。不碰动画/碰撞/聊天/桥接协议。
**配置变更**：无新键；`island_metrics` 合法成员扩容 `gpu`（语义变更：从前手写 `"gpu"`
被当脏值丢弃，现在保留——发布说明需提一句）；E1 状态点颜色语义变更（绿=宠物可见 →
绿=完成）已在裁决稿 §五定案，发布说明需标注。
**回滚**：`git revert 28d0c39^..<R4-HEAD>`（slice 8 提交 + 修复轮 4 提交）；无落盘状态残留（GPU 行取消勾选即回滚，
`island_metrics` 归一化对旧版仍安全——旧版视 `gpu` 为未知 id 丢弃，不炸档）。

---

## 九、评审修复轮（2026-10-07，astra 终审 + 6.1sol 交叉票）

交付前两票盲审（astra 主审、6.1sol 交叉；Agents-A1 与书生/glm-5.3 因端点 400/429
未能出票，已按恢复协议换票不重试）。两票共确认 **1 项阻塞 + 6 项应修**，全部修复并
test-first 收口；另有裁决记录如下。

### 阻塞 1（成立，已修）：网络盒 max(样本,现文案) 穿透宽度不变量

`7947a18` 的包络外兜底让采样值经 `box_text` 变相进 `_plan_inputs` 键；临界收缩预算
下会形成「超包络读数 → 折叠网络 → 清样本 → 恢复 → 再折叠」的订阅振荡，且 tick 只
`update()` 不提交几何，计划宽与窗口宽脱节。**这是我自己在 P1 截图自审修正时引入的
缺陷，两票评审抓得准。** 修复：盒宽回归恒为声明样本，包络外读数由字段盒右省略护栏
承接（`format_field_box` 自带 warning）。回归守卫 `tests/test_island_network_envelope.py`：
临界预算 + 持续超包络 50 拍，计划键/岛宽/折叠态/采样器启停全程不变 + 窗口宽恒等于
计划宽；突变检验（恢复 max() → 两例即红）。

### 应修（全部成立，已修）

| # | 发现 | 修复 |
|---|---|---|
| 2 | 工作上升沿 `_bounce` 绕过 `event_effects` 与免打扰（两套动效语义） | 过与 `notify_event` 同一道闸门：`suppression_active()` 复用全应用唯一判据（`set_dsh_state`，测试 `test_work_edge_bounce_respects_event_effects_and_quiet_mode`） |
| 3 | squish 拉伸期 sx=0.964，宽岛内容画出外壳（我的 E7 审计只测了 0.85 鼓出向） | 横向只鼓不缩（`sx = 1 + max(0, 1−sy)×0.3`），审计补 0.85/1.0/1.06/1.12 四档两端断言 |
| 4 | FontChange 普通胶囊只废缓存不交几何（最长拖 30s） | `changeEvent` 非拖拽路径补 `_update_size()`（`test_font_change_commits_geometry_in_normal_mode`） |
| 5 | 卡片 hover 不暂停 15s 自动收起（pre-existing，用户读着卡片被收掉） | enterEvent 停表 / leaveEvent 重新倒计时（`test_card_hover_pauses_auto_collapse`） |
| 6 | 扩展文档欠账列不全 + `width_px`/`oversize` 漏单位盒（长单位绕过 120px 判决）+ 示例断言过时 | 文档 §八 改「R1 补全版」（六项 ⬜ 全列、措辞降为「契约层 API 形状冻结」）；`width_px` 与 `oversize_segment_ids` 统一走含单位的完整口径；可跑示例同步（机器 exec 校验） |
| 7 | 告警「样本到达一刻不漏拍」表述过强（GUI 1Hz 读取会漏中间拍） | 语义裁决为**按 UI 读取拍**（告警色跟随用户实际看到的读数，与显示值永远一致），docstring 写明；不改行为 |

### 6.1sol 交叉票补充（全部处理）

- **起拖不停已在播的淡化**（「先淡化、后起拖」残影继续推进）→ 起拖即 `_stop_content_fade()`
  （`test_starting_a_drag_stops_the_in_flight_fade`）。
- **只折内存时该行看似正常采样**（共享快照顺带更新）→ 卡片行注「已折叠 · N 秒前」，
  不谎称暂停（`test_partially_folded_device_row_is_marked_folded_not_live`）。
- **审计基线用例名不副实**（设备段停在 sampling、单位没上墨）→ 喂 ok 快照 + 单位盒
  墨底单列探测（`test_all_text_layers_share_one_baseline` 强化）。
- **内容缓存键缺段模板分量** → 键补 `label/box_text/elide_px`
  （`test_content_cache_key_covers_label_and_box_template`）。

### 裁决记录（不改代码，已立档）

- **F1 范围**：两票都指出「注册即可上岛」未兑现。裁决：契约层（声明/护栏/文档/GPU 占位
  参考实现）即本版范围，F2 = 渲染接线 + oversize 消费 + 配置准入 + 采样生命周期
  （文档 §八 已按 R1 补全版列全）。理由：没有任何真实第三方段消费者的当下，渲染与
  采样接线是给不存在的路径铺代码；但文档与 PR 不得声称「接口已完整交付」。
- **卡片概览恒为余额**（不跟随 `info_mode`）：维持 E5 偏差——禁改测试钉死
  `_card_balance_label` 文案，且主信息就在卡片正上方的胶囊里；已列入已知限制。
- **矢量箭头 / 待确认名字槽文字**：裁决稿采纳项，本版未做（字符 glyph / 仅空心环），
  列入 F2 候选，不算 P2 欠账（施工单未列）。
- **字号 14 DemiBold 主信息**：D1 已记录的偏差（P1 报告 §七），维持。

### 本轮验证

聚焦（岛+设置+架构）577 passed；ruff 干净；全量 **5287 passed, 11 skipped**（723s，含本轮 12 个新用例）。

---

## 十、终审四票轮（2026-10-07，第二轮评审与三关核验）

四票全面审查（用户指定：Agents-A1 / 书生·glm-5.3 / ops5.5 / 6.1sol），每条发现过
**三关核验**（证据关=代码实证防幻觉、检查面关=补全上下文防以偏概全、
语义关=以施工单/裁决稿为准防理解错误）。处置全账如下。

### 票况

| 票 | 状态 | 发现数（采纳/驳回） |
|---|---|---|
| ops5.5 | ✅ 出票 | 3 应修 + 2 建议 + 1 nit → **采纳 3**（M1/M3/N1），**驳回 3**（M2/S1/S2 误报） |
| 6.1sol（第二轮） | ✅ 出票 | 3 应修 + 2 建议 + 1 nit → **全部采纳** |
| Agents-A1 | ✅ 出票（第三次尝试） | 2 阻塞 + 3 应修 + 2 建议 + 2 nit → **驳回 8**（详见下），采纳 C2（补测试） |
| 书生/glm-5.3 | ❌ 配额三连 429（01:30 重置）；poke2api/glm-5.3 同模型渠道 502 余额不足 | **未能出票**——Agents-A1 补第二票（R3 增量专审）替代，用户验收时可决定 01:30 后补票 |

### 驳回记录（幻觉/误报的判别账）

- **ops5.5 M2**（拖拽中完成瞬态表不销毁）：`_arm_dot_done` 隐藏态不点表、singleShot
  到点自毁、hideEvent 停表——它描述的泄漏路径不存在，且引用的 `_mark_task_done`
  函数名根本不存在（函数名级幻觉）。
- **ops5.5 S1**（淡化判据漏 primary elide_px）：`_plan_inputs` 的段元组自 D2 起就含
  `elide_px`，`_structure_key` 只剔现文案——它读错了键的构成。
- **ops5.5 S2**（迁移重复追加 network）：它引的代码里 `if NETWORK not in metrics`
  防重检查就在原地，描述的场景与所引代码自相矛盾。
- **A1 B1**（hideEvent 不停淡化表）：`hideEvent` 第 3244 行 `_stop_content_fade()`
  就在它引的行号区间里（它自己引的证据区间包含了答案）。
- **A1 B2**（`_strip_sampling_off` 初始态不一致）：监视器创建本身走 `_sync_*_slot`
  闸门，「启动即停靠不建采样器」有 E6 专例锁死；且 `_sync_content_sampling()` 有
  9 个调用点含它点名的 `_apply_position`/`mouseMoveEvent`。
- **A1 C1**（`_sys_active` 不查 isVisible）：那是文档化的「隐藏即休眠」语义——
  可见性只管 start/暂停，不收口（E6 施工单明写）。
- **A1 C3**（迁移可能先于清理）：代码顺序就是先 `_clean_island_metrics` 后追加。
- **A1 D1/D2**：无具体证据的泛指（注释风格是本项目考古惯例；调用点已覆盖）。
- **A1 nit**（滞回注释 2pt）：全文无 "2pt"，注释本就是 3pt。

### 采纳修复（R3 批，全部 test-first）

| # | 来源 | 修复 |
|---|---|---|
| closeEvent 收口两条采样器 | ops5.5 M1 | `closeEvent` 调 monitor.close()（有界 join 的收口路径才走得到），`test_close_event_closes_both_monitors` |
| 滞回「折叠保持 / 恢复清零」 | ops5.5 M3 | 与 E2「折叠不埋没告警」调和：折叠保持 severity（chip 点唯一来源）、**恢复订阅那一刻**清零（92 折掉掉到 85 恢复按新序列判 warn），`test_unsubscribing_a_metric_clears_its_hysteresis_memory` |
| hover 真实序列 | 6.1sol #1 | 我的 R1-5 修法漏了「先进入、后展开」主路径（enterEvent 在 normal 态就发生过了）；改自记 `_cursor_inside` 旗帜（`underMouse()` 由窗口系统置位，合成事件下不可验），`expand_card` 按旗帜决定起不起 15s 表 |
| DSH 关闭发 offline | 6.1sol #2 | `apply_config` 停 dsh 监视器时经 `_on_dsh_converged_state("", "offline", "link-disabled")` 复用 offline 管线——岛锁存态（待确认环/错误点）与常驻气泡一并复位，`TestDshDisableResetsPresentationState` |
| 全折故障保持 | 6.1sol #3 | `_sys_error_hold`：收口袋时留住最近故障（**只在有快照时改写**——同一次刷新收口袋会被调两遍，第二遍快照已 None 会把刚留住的抹掉，实测复现）；`_device_segment` 与卡片原因行都读它，`test_full_fold_preserves_the_last_sampling_error` |
| 测试诚实化 ×2 | 6.1sol #4/#5 | 包络测试改真·临界预算（先找折叠边界再退一步）+ 每拍换时间戳（同值短路会让"50 拍"只剩 1 拍）；FontChange 测试改内部字号层常量（部件字体不影响岛的像素层，不换字体就是假绿） |
| 来源映射 | ops5.5 N1 | `test_island_review_fixes.py` 文件头补逐轮评审来源表 |

### 本轮验证

聚焦（岛+设置+架构+agent_link+纪律）868 passed；ruff 干净；全量 **5292 passed, 11 skipped**（813s，含 R3 全部新用例）。

---

## 十一、astra 保底终审收口轮（R4，2026-10-07）

astra 保底（第二轮回审）判「不可交付」并给 1 阻塞 + 4 应修 + 3 建议 + 3 nit。
逐条三关核验后全部处置：

| # | 发现 | 核验 | 处置 |
|---|---|---|---|
| B1 关闭 DSH 后已排队收敛信号覆盖 offline 复位 | **成立**（`_on_dsh_converged_state` 无运行态闸门，Qt 队列信号撤销不掉） | `_on_dsh_converged_state` 加隔离闸：监视器不在跑时只放行 link-disabled 人工复位；新增 `TestDshLateQueuedSignalsAreIsolated`（旧信号入队→关闭→泵队列→offline 不被覆盖）+ 真 offline 不误伤用例 |
| M1 包络测试喂已关闭的旧监视器、50 拍其实 1 拍 | **成立**（临界搜索触发收口袋重建，made[0] 已死；样本在循环外构造） | 两测试改拿 `island._net_monitor`（当前）+ 每拍循环内构造新样本 + 「样本确实被消费」前提断言；**重做突变检验**（恢复 max() → 两例即红 → 复原转绿） |
| M2 全折故障保持只保最后还订阅的段 | **成立**（先折的 MEM 在收口袋时已退订，hold 只按订阅集） | 保持面改为配置里当前的全部设备段（共享故障覆盖两段）；测试补 MEM 的 state 与原因断言 |
| M3 单侧淡化抬升半透明共用像素（α70% 单位盒 0.70→0.91） | **成立**（合成公式 a+a(1−a)(1−t)，E3 的 hit=255 探针看不见） | 旧位图按「新内容透明区」做遮罩（本 Qt6 构建 setMask 1 位=透明，隔离探针实测后用 MaskOutColor）；共用像素任何 alpha 逐帧恒定；新增 `test_fade_keeps_semi_transparent_shared_pixels_constant` |
| M4 报告未收口/表述失准 | **成立** | 本文件头部范围行、F1 欠账口径（六项）、影响面（含 agent_link.py）、回滚范围、glm 票最终状态全部对齐；模型评审账保留在内部章节（仓库先例如此） |
| S1 closeEvent「有界 join」表述过强 | **成立**（net_monitor.close 非阻塞、closeEvent 不 join） | 注释如实化：兑现「发出停止+订阅清理」，非「返回前已 join」 |
| S2 hide→show 自动收起不恢复 | **成立**（pre-existing） | showEvent 在 expanded 且光标不在岛内时接回倒计时；测试补断言 |
| S3 oversize 现在时声称「已降为首批候选」 | **成立**（无消费方） | docstring/log 统一为「记入候选名单（宿主尚未消费）」 |
| nit ×3 | 成立 | bounce 注释改为「两道闸」；评审来源映射指错文件；滞回测试改 91 才有判别力（旧记忆保 crit vs 新序列 warn） |

**上轮闭环核验（astra 自评表复核）**：网络定宽/bounce 闸门/squish/FontChange/内容键/告警语义/F1 单位宽七项均确认真修；卡片概览恒余额、矢量箭头、待确认名字槽文字为已立档的裁决/挂账，不算欠修。

### 本轮验证

聚焦（岛+设置+agent_link+纪律）待回填；ruff 干净；全量待回填。
