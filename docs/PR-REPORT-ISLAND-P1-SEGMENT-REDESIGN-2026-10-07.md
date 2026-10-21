# 灵动岛 P1：段化重设计（多指标段 + 收缩流水线）

> **基线**：`1d058e2`（整合分支 `integration/2026-10-07-night-batch` HEAD，docs 终审修复对齐批）
> **分支**：`feature/island-segment-redesign`　**日期**：2026-10-07
> **提交**：`04bda0f`（Slice A/B 段契约+采样底座）、`0765028`（Slice C 配置键+设置页）、
> `26dbaa9`（Slice D1 段化渲染）、`bfe4b74`（Slice D2 收缩流水线）、`7947a18`（截图自审包络修正）
> **范围**：17 个文件（实现 7、测试 10），`+4912 / −228`（不含本报告）
> **关联**：设计裁决稿 `.scratch/ISLAND-UI-SYNTHESIS-20261007.md`（冲突以它为准）、
> 施工单 `.scratch/ISLAND-P1-SLICE-AB/C/D-SPEC-20261007.md`、
> issue #172（网络槽，本 PR 废止其「网络接管信息槽」语义，已就地标注）、
> 实机截图 `.scratch/island-p1-shots/`

## 一、核心特性

旧灵动岛的信息槽是**一个**槽位：#172 引入的网络开关会「接管」整个信息槽——开了网络
就看不到时间（before 图 `before-island-network-takeover.png`：槽里只剩 `↓↑` 读数）。
想同时看「时间 + CPU + 内存 + 网络」结构上没门；且网络槽每秒来一份快照就写一次窗口
几何（`setFixedSize`），多宠/多段场景下这是持续的 GUI 线程负担与潜在抖动源。

P1 把信息槽重设计为**段序列**：主信息段（时间/自定义/余额/峰谷四模式，不再被接管）
+ 任意数量的指标段（`island_metrics` 列表序 = 用户优先级），竖线分隔、字段盒定宽
右对齐；总宽不设段数上限，触发线 = 屏宽 − 32px，超线自动走收缩流水线。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 段化信息槽 | 主信息段恒在，指标段按 `island_metrics` 追加；`--` 四态兜底（sampling 不伪造 0 读数） |
| 2 | CPU/内存指标段 | 共享 `SysMonitor` 一条采样线程，按段订阅，0 订阅即停采样；隐藏保订阅停线程 |
| 3 | 网络指标段 | 复用 `format_network_slot` 5 列定宽槽契约；盒样本取「千兆满速+近秒级延迟」现实包络 |
| 4 | 收缩流水线 | 名字省略(96→40px) → 名字隐藏 → 尾部整段折「+N」chip → custom 主信息省略(96px) → 保底 |
| 5 | 折叠态采样联动 | 被折进 +N 的段即时退订（网络整条收口/cpu·mem 按 id 退订），展开恢复、首轮按四态 `--` |
| 6 | 三分区伸长锚点 | 自由胶囊变宽时固定贴屏侧（左 1/3 定左缘/右 1/3 定右缘/中间定中心）；停靠细条与卡片不介入 |
| 7 | 设置页三开关 | 「桌面组件 · 灵动岛指标」网络/CPU/内存三行，典范序写回；旧键 `island_network_enabled=true` 单向迁移 |

**红线 / 不变量**：
- **宽度白名单**：采样值变化永不触发 `_update_size`/`setFixedSize`（结构保证：采样值进不了
  `_plan_inputs` 键）；只有「可见项/名字/段模板/字体指纹/DPR/收缩预算」变化才重算几何。
- **四态不伪造**：无快照/退订恢复首轮一律 `--`，不显示伪造的 `0B`/`0%`。
- 信号/物理/停靠/hover peek/卡片/单击路由/置顶保活语义**零改动**（既有套件全绿为证）。
- 数字跳动不推邻居：指标段盒宽由声明样本兜住，读数在盒内右对齐伸缩。

## 二、修改文件说明

`git diff --numstat 1d058e2..HEAD`（5 提交合计）：

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/island_segments.py` | +244 / −0 | **新增**（Slice A）：段注册表（cpu/mem/network id 与格式化器）、`format_field_box` 定宽盒（超宽右省略+warning 硬护栏）、四态契约（ok/sampling/unavailable/error → `--`）、`LABEL_GAP_PX` 等段常量 |
| `pet/sys_monitor.py` | +335 / −0 | **新增**（Slice B）：CPU/内存共享采样器——一条线程多订阅者，0 订阅不采样；`SysSample` 快照带 state/error_reason（sampling 与「读数是 0」分得开）；CPU 差分首样本报 None 而非 0 |
| `pet/island_layout.py` | +395 / −0 | **新增**（D2 下沉）：零 Qt 纯布局层——`_InfoSeg`/`_SegPlacement`/`place_info_segments`（段间 19px、竖线居中、盒内右对齐）、`plan_info_row` 收缩阶梯、`apply_shrink`/`chip_segment`/`anchored_x`/`elide_to_width`；`_NETWORK_BOX_SAMPLE` 包络修正（`7947a18`） |
| `pet/dynamic_island.py` | +612 / −94 | 岛本体段化（D1）：`_compose_info_segments` 段序列（主信息四模式平移入段、**删除网络接管分支**）、`_row_plan`/`_plan_inputs` 宽度白名单、设备槽接线（`_sync_sys_slot`/`_tick_sys`，仿网络槽幂等/休眠口径）；收缩接入（D2）：`_compute_row_plan`/`_sync_fold_sampling`/拖拽冻结/落定重算/`_update_size` 锚点；`_network_segment` max(样本,现文案) 包络兜底（`7947a18`） |
| `pet/config.py` | +49 / −1 | `island_metrics` 四处登记（默认值/reload 白名单/归一化/schema 集合）+ `_clean_island_metrics`（非 list→[]、非 str 丢弃、去重保序、未知 id 丢弃、不设上限）+ `island_network_enabled=true` 旧档单向迁移（network 追加尾 + 旧键置 False，保留键防降级炸档） |
| `pet/settings_network.py` | +103 / −41 | 岛侧三行「灵动岛指标 · 网络/CPU/内存」（典范序写回、探测间隔行联动、子宠页置灰）；**删除已失效的「网络接管」行隐藏逻辑**（D1 语义变更残留，hint 文案同步对齐） |
| `pet/modern_settings_dialog.py` | +2 / −2 | 小节标题改「桌面组件」（净 0 行，行数预算 2426 不变） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_island_segments.py` | +351 / −0 | Slice A 段契约（注册表/字段盒/四态/省略护栏） |
| `tests/test_sys_monitor.py` | +479 / −0 | Slice B 采样器（订阅生命周期/共享线程/快照四态/0 订阅停采样） |
| `tests/test_island_metrics_config.py` | +182 / −0 | Slice C 配置键（归一化/迁移/白名单/设置页写回/旧用户升级回归） |
| `tests/test_island_segment_render.py` | +647 / −0 | D1 段管线契约 24 例 + `7947a18` 包络用例（几何纯函数/白名单/像素级探针） |
| `tests/test_island_device_slot.py` | +342 / −0 | D1 设备槽接线 14 例（订阅/休眠/采样 tick 不摸几何） |
| `tests/test_island_shrink_pipeline.py` | +640 / −0 | D2 收缩契约 31 例（逐级触发/尾部优先/逆序恢复/chip/锚点/折叠退订/多屏迁移/错输入护栏） |
| `tests/test_island_network_slot.py` | +60 / −19 | 适配段化语义（`--` 占位取代伪造 `0B`），未删用例 |
| `tests/test_settings_network.py` | +136 / −16 | 三开关行 + 「接管隐藏」删除后的新依赖语义（断言更强：自定义文本行只跟内容选择走） |
| `tests/test_config_schema.py` | +24 / −10 | `island_metrics` schema 登记 |
| `tests/test_architecture.py` | +7 / −0 | 零 Qt 白名单登记 `island_segments.py` 与 `island_layout.py` |

### 未改动（看似相关但故意没动）

- `pet/net_monitor.py`：5 列定宽槽串契约是跨模块产品契约（弹窗/测试同源），段化只消费不改写。
- 四个 `tests/test_dynamic_island_*.py`：既有用例一行未删未改（语义零改动证据）。
- `pet/dsh_state.py`：「待确认」八态收敛已具备，状态点体系接入属 P2。
- 停靠细条停采样：K3 设计稿提出，但与「停靠语义零改动」冲突，留独立 slice（见七）。

## 三、实现要点

**段管线**（`dynamic_island.py` 类内 → `island_layout.py` 纯函数）：

```
_capsule_width() / _content_cache()   ← 自然宽与绘制的唯一来源
  └─ _row_plan()                      ← 按 _plan_inputs 白名单键缓存
       ├─ _compose_info_segments()    ← 当刻段列表（主信息 + 指标段 + 四态兜底）
       ├─ plan_info_row()             ← 收缩阶梯（取第一个 fits 的级；都不 fits 取保底）
       │     L0 静止 → L1 名字 40px → L2 名字隐藏 → L3+k 尾折 k 段+chip
       │     → L3+n+1 custom 主信息 96px → 保底
       └─ _sync_fold_sampling(plan)   ← 折叠段退订/展开恢复
绘制：apply_shrink(plan, 当刻段列表) → place_info_segments() → 逐段+chip 落位
```

三个关键取舍：

1. **计划只存结构，不存段对象**。第一版把段快照存进计划，采样值一变内容层就拿旧文案
   （被 D1 冻结用例 `test_content_cache_key_covers_segment_text_and_state` 当场抓住）。
   改成「计划管几何结构、`apply_shrink` 从当刻段列表套文案」后，几何与像素不可能各自漂移。
2. **字段盒 = max(声明样本, 现文案)**（主信息段 D1 起、网络段 `7947a18` 起）。包络内读数
   在盒内右对齐、不推邻居；包络外（余额明细串、G 级速率、四位毫秒）宁可岛变宽也不静默
   右省略——`box_text` 本就在白名单键里，加宽走正规几何路径。网络样本不取 G 级病态最坏
   形态：那会让典型 K 级读数在盒内留出 ~45px 空白（截图自审发现，见五）。
3. **布局层零 Qt 下沉**（`island_layout.py`）：收缩规则在无窗口/无字体/无屏幕的替身上可测
   （D2 的 31 例大多不碰 QApplication），`dynamic_island.py` 行数预算才兜得住
   （D1 净 +471 行后不下沉必破 D1+D2 合计 +600 的预算）。

**配置迁移**：`island_network_enabled=true` 旧档 → `network` 追加进 `island_metrics` 尾部 +
旧键置 False（键保留：降级回旧版不会读到非法值炸档）。`_net_enabled()` 改读列表成员，
带 list/tuple 类型守卫（防脏字符串子串误中）。

## 四、性能分析

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen python -m pytest -q <探针用例>`（探针内嵌于
`tests/test_island_segment_render.py` / `test_island_shrink_pipeline.py`，n=200~500 次均值）；
环境：Windows 11 / Python 3.13 / PySide6 / 本机（2560×1440）。

| 指标 | 实测 | 归属 |
|---|---|---|
| 采样 tick 的窗口几何写入（`setFixedSize`/`_update_size`） | **0 次 / 120 tick**（300 tick 复测同为 0） | 既有缺陷消除：旧网络段每秒 1 次 `setFreeGeometry+setFixedSize` |
| 行计划缓存命中（每秒采样 tick 的稳态路径） | 47µs | 新增 |
| 行计划重算（含收缩候选阶梯排版） | 434µs，**只在输入真变时触发**（时间跳分钟/配置/换屏） | 新增 |
| `apply_shrink`（当刻文案套结构） | 66µs（D1 等价 `place_info_segments` 71µs） | 新增 |
| 内容层位图重建（值变化时） | 238–302µs/次，每秒 1–2 次/槽 | 既有（持平） |
| `_update_size`（结构变化才走） | 0.119–0.138 ms/次 | 既有（频率大降） |
| `_width_key`/`_fonts_key` 键构造 | 45µs / 22µs | 新增 |
| 岛总宽（实测窗口） | 175px(名字+时间) → 506px(+CPU+内存+网络三段) | 用户可见 |

**结论**：① 稳态开销**下降**——采样 tick 从「每秒一次窗口几何写入」降为 47µs 键比较 +
一次 `update()`（<1µs）；② 新增路径（计划重算 434µs）只在结构变化时触发，频率是分钟级
或事件级，不是秒级；③ **无新增系统调用/网络/磁盘**；新增线程 1 条（`pet-sys-monitor`，
cpu+mem 共用，0 订阅即停），网络槽沿用既有线程未新增；④ 内存仅小对象缓存（计划 + 段
列表，字节级~KB 级），无新增常驻缓冲区；折叠态退订后采样器 `subscriber_count` 2→0 实测成立。

## 五、实机运行记录

**现场复现（旧缺陷）**：`D:/dsh-pet`（整合分支部署实例，PID 34204）开启网络槽后信息槽
只剩 `↓↑` 读数、时间被吃掉——截图 `.scratch/island-p1-shots/before-island-network-takeover.png`。

**用户可见行为确认**（computer-use 实机截图，wt-island 工作区 `python -m pet`，读真实
`%APPDATA%/dsh-pet-standalone/config.json`）：

1. 基线：`p1-baseline-name-time-175px.png`（175×44：头像 + shenshen + 13:55 + 状态点）。
2. 配置写入 `island_metrics=["cpu","mem","network"]` 重启：
   `p1-segments-before-envelope-fix-508px.png`（508×44 五段：名字 + **14:06** + CPU 28% +
   内存 72% + ↓2K ↑19K 54ms，时间与网络共存——#172 接管缺陷消除）。
3. **截图自审发现缺陷**：3x 放大（`p1-zoom3-before-envelope-fix.png`）网络段数值右对齐后，
   竖线与 `↓` 之间有 ~45px 死空白——盒样本取了 G 级病态最坏形态（`↓1023G ↑1023G 1000ms`），
   典型 K 级读数根本填不满。→ `7947a18` 改现实包络 + max 兜底后复截
   （`p1-segments-after-envelope-fix-506px.png` / `p1-zoom3-after-envelope-fix.png`）：
   留白收到 ~30px 的结构性下限（5 列速率槽 + M 级不抖动包络的物理下限，见七）。
4. 验毕已将 `island_metrics` 键从用户真实配置移除（验证未污染用户档位）。

**活体探针**（真实 `SysMonitor` + 真实 psutil，D1 记录）：show 前监视器已建、订阅
{cpu,mem}、**线程列表为空**；show 后 `pet-sys-monitor` 线程在跑、定时器 1000ms、段显示
`[('primary','','12:58','ok'),('cpu','CPU','20%','ok'),('mem','内存','80%','ok')]`；
hide 后线程消失、定时器停。

**边界与失败路径**：① 网络无快照显示 `--`（不伪造 `↓ 0B ↑ 0B`），复订阅首轮同口径；
② 未知指标 id 降级 `--` 段（label 截 6 字符），不崩不留洞；③ 旧档迁移实机探针（Slice C）：
`island_network_enabled=true` → 落盘为 `island_metrics=["network"]` + 旧键 False → 设置页
改写典范序 → 岛定时器联动，全链绿。

**无法自动验证项**：收缩的「真实窄屏/跨屏拖拽」没有第二块物理屏可拖——替代证据是
`_narrow_to()` 实测搜索（从宽往窄找第一个满足谓词的屏宽，真实字体）逐级验证
1400→200px 六档（1400px L0 全段 726 宽 / 700px L1 名字省略 / 620px L4 折 mem +1chip /
500px L5 折 cpu+mem / 380px L6 三折 173 宽 / 200px 保底截断），见
`tests/test_island_shrink_pipeline.py` 窗口级用例。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | All checks passed |
| 聚焦（岛+设置+架构） | `pytest -q tests/test_dynamic_island_*.py tests/test_island_*.py tests/test_sys_monitor.py tests/test_net_monitor.py tests/test_settings_network.py tests/test_architecture.py` | **392 passed**（D2 后） |
| 受影响时序族复跑 | `pytest -q tests/test_flight_frame_pacing.py` | 5 passed（全量期 2 例红为并发实机启停负载所致，单独复跑全绿） |
| 全量（D1 后） | `python -m pytest -q` | 5067 passed, 11 skipped |
| 全量（D2 后） | `python -m pytest -q` | 5098 passed, 11 skipped |
| 全量（`7947a18` 后终验） | `python -m pytest -q` | **5099 passed, 11 skipped**（667s，空闲机无并发负载） |
| 断言有效性 | D1/D2 各 slice 均先红后绿（红证据见各交付记录：ImportError/AttributeError/断言失败 → 绿） | 通过 |
| 架构红线 | `tests/test_architecture.py` | 10 passed（含两个新模块零 Qt 登记） |

## 七、已知限制与后续

- **网络段 ~30px 结构性留白**：5 列定宽速率槽 +「K↔M 不跨档抖动」包络的物理下限；
  再收紧会让看视频/下载（M 级常态）时岛宽随档位来回跳，权衡后取稳定。
- **chip 告警点**只留接口（`ShrinkPlan.chip_alert` 已真算、有测试），P2 告警色接入后点亮。
- **停靠细条仍照常采样**（既有行为，K3 设计稿要求全停）：与「停靠语义零改动」冲突，
  建议独立 slice（一行闸门 + 兄弟段联动）。
- **P2**（视觉打磨）：高光/暗边、状态点四态体系（绿=完成/待确认=accent 空心环/错误=红）、
  卡片重设计、单位弱化（α×70%，需段契约加 `unit` 字段）、结构变化 120–150ms 交叉淡化。
- **P3**（扩展接口）：第三方段公开注册接口（不碰 QPainter 的契约面）+ GPU 指标占位。
- `custom_text` 手改配置塞 `\n` 会画出胶囊外（旧代码同然，非回归，未在本 PR 处理）。

## 八、风险与回滚

**新持久设置准入记录**（`docs/SETTINGS-CHANGE-GATES.md` 口径）：

```text
setting_id        island_metrics（list[str]，段 id 有序列表）
domain_id/group   桌面组件 / 灵动岛（设置页三行：网络/CPU/内存，典范序写回）
default           []（全关 = 旧行为，安全默认）
capability        全平台（psutil / net_monitor 既有能力，无新平台分支）
disclosure_level  primary
dependency        dynamic_island.enabled ∧ show_info；探测间隔行联动 network 成员
commit_policy     immediate（写回即 refresh_from_config）
migration         island_network_enabled=true → network 追加尾 + 旧键置 False（键保留）
recovery          非法值归一化 []（非 list/非 str/未知 id 逐级丢弃，不崩不炸档）
search_aliases    灵动岛指标 / CPU / 内存 / 网络（各行 objectName 独立可搜）
```

**影响面**：仅灵动岛信息槽渲染与设置页「桌面组件」小节；不碰动画/碰撞/聊天/DSH 联动。
**回滚**：`git revert 04bda0f 0765028 26dbaa9 bfe4b74 7947a18`。注意迁移是单向的——
回滚代码后旧版读到的 `island_network_enabled` 已是 False（网络槽关、信息槽回 `info_mode`），
若需恢复旧网络槽行为，手动把该键改回 true；`island_metrics` 键对旧版是无名键，归一化丢弃，不炸档。
