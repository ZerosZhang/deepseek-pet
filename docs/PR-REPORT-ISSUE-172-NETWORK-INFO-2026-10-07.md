# issue #172：灵动岛网络槽与「网络信息」弹窗

> **基线**：`589d25f`（merge #208 免打扰）；本批两个提交经 `3c54e32`（主功能）与 `277117a`
> （置灰对齐）并入 integration
> **分支**：`feature/issue-172-network-info`　**提交**：`c0c2e70`（主功能）、`7ce25c8`（置灰对齐）
> **日期**：2026-10-07
> **范围**：`c0c2e70` 23 个文件 `+3195 / −4`；`7ce25c8` 7 个文件 `+195 / −45`（合计 24 个不同文件）
> **关联**：issue #172；菜单/配置/行数预算与 #209、#228 并序（并入后实测预算 2426）
> **互链**：网络与系统代理口径见 [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md)；
> **Runtime Disabled** 语义见 [`../CONTEXT.md`](../CONTEXT.md)；设置准入/准出见
> [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)；必备证据章节见
> [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在 [`INDEX.md`](INDEX.md) 的
> 「PR 报告存档」。

## 一、核心特性

两件事：**①** 灵动岛多一个「网络信息」槽，显示实时上下行速率与 UDP 延迟
（`↓ 2K ↑ 1K 50ms`）；**②** 右键菜单「工具与帮助」新增「网络信息」弹窗，展示公网 IP、
IP 属地、是否在中国大陆、Google / GitHub 连通性，每项带 HTTP 状态与耗时，底部写明数据源
与耗时。弹窗**只在用户打开时取一次**，不轮询、不后台上报；**岛槽相反——只要它在跑就按
间隔持续发 UDP 探测包**（速率读本机计数器零流量，延迟必须发包才测得出来；默认 1 秒间隔约
13.2 MB/天，设置页文案按当前间隔实时显示）。岛槽的「在跑」是**三态与**：网络槽开着
AND 岛可见 AND 显示信息槽（`DynamicIsland._net_active`），任一条不满足即停采样、不发包。
第三态（信息槽）由后续的终审修复 `05b7a5e`（「岛网络槽补第三态」，已并入集成分支）补上，
本批当时的条件是「网络槽开着 AND 岛可见」。

数据源有两处刻意的取舍：**属地源优先国内（太平洋电脑网 IP 库，响应体是 GBK）、失败才回退
ip-api.com**——把出口 IP 交给谁是有取舍的，境内源够用时不多给一家海外服务；**延迟探测打
阿里公共 DNS `223.5.5.5:53`**（Anycast、境内、IP 字面量免解析、查询内容无隐私），
**绝不默认打国外地址**。

第二批（`7ce25c8`）是一次**契约对齐**：`network_info_menu_enabled` 关掉时，入口从
「整条消失」改为**保留位置、置灰、并解释原因**，对齐 [`../CONTEXT.md`](../CONTEXT.md) 的
**Runtime Disabled** 词条；编排器状态列从「此平台不可用」变成「已停用」。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 岛网络槽 | `↓ 2K ↑ 1K 50ms` 定宽文案；1 秒刷新（可设，默认 1.0s）；开关是槽内容的**唯一所有者** |
| 2 | 弹窗四组信息 | 公网 IP / IP 属地 / 是否在中国大陆 / Google、GitHub 可达性（各带状态与耗时），失败逐字段显示「获取失败」+原因 |
| 3 | 双源回退 | 属地源 A（太平洋电脑网）失败 → 源 B（ip-api.com）；两端都免 key、无 cookie、单次 GET |
| 4 | 硬广不猜 | 「是否在中国」口径是出口 IP 属地；认不出的省份/英文地名判为**「判定不了」**，不硬猜 |
| 5 | 隐藏即休眠 | 岛隐藏 → 读取定时器停 + 采样线程停；关掉灵动岛 → 对象一起收口 |
| 6 | Runtime Disabled 对齐 | 菜单开关关掉 → 入口**保留、置灰、带说明**；能力不可用（无回调）才整条不出现 |

**红线 / 不变量**：
- **弹窗**取数只在用户主动动作时发生：打开按需取一次、属地/连通性各一次 GET；**无轮询**；
  （岛槽是另一条路：开启后按间隔**持续发 UDP 探测包**，见第四节与第七节）
- 岛槽关闭时采样线程与定时器**必须真的停掉**（不是空转）；
- 网络槽开关为真时，`_info_text` 网络分支是**唯一接入点**——不发新槽位、不改 `_visible_parts`；
- 出口口径分两类，**别混**：属地与连通性的 HTTP **一律跟随系统代理**
  （`network_info._default_opener()` = `build_opener()`）；**延迟探测是 UDP，走 OS 路由**
  ——普通 HTTP 代理不代理 UDP，它测的是不经代理那条路径的 RTT；
- 弹窗在宿主销毁后不得崩溃（`shiboken6.isValid` 探活）。

## 二、修改文件说明

### 2.1 `c0c2e70`（主功能）

`git log --numstat c0c2e70`：

```
27	0	pet/app.py
27	0	pet/config.py
4	0	pet/context_menus/legacy.py
21	0	pet/context_menus/registry.py
21	0	pet/context_menus/shared.py
96	1	pet/dynamic_island.py
1	0	pet/menu_templates/modern-default-v1.json
6	1	pet/modern_settings_dialog.py
477	0	pet/net_monitor.py
387	0	pet/network_info.py
267	0	pet/network_info_dialog.py
200	0	pet/settings_network.py
11	0	pet/sprite_menu_facade.py
8	1	tests/test_architecture.py
81	0	tests/test_config_schema.py
242	0	tests/test_island_network_slot.py
2	0	tests/test_menu_layout.py
434	0	tests/test_net_monitor.py
289	0	tests/test_network_info.py
201	0	tests/test_network_info_dialog.py
189	0	tests/test_network_info_menu.py
181	0	tests/test_settings_network.py
23	1	tests/test_sprite_menu_parity.py
```

**新增（4 个产品模块 + 6 个测试文件）**

> *〔2026-10-07 终审修复对齐（`05b7a5e`）：`pet/net_monitor.py` 的「每 run 独立停止事件与
> socket」现为**每代三件套 + 发布前代核验**，见 §9.1〕*

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/net_monitor.py`（新） | +477 / −0 | **零 Qt** 采样核心：`read_counters`（psutil 懒导入，缺失返回 `None`）、`NetRateMeter`（Δ字节/Δt + EMA 平滑、计数器回绕按 0）、`UdpLatencyProbe`（DNS 查询载荷 UDP 往返、事务号匹配、ICMP 即判不通）、`format_network_slot`（定宽文案）、`NetMonitor`（后台线程 + 快照 + 每 run 独立停止事件与 socket）。 |
| `pet/network_info.py`（新） | +387 / −0 | **零 Qt** 数据层：`decode_json_body`（UTF-8→GB18030）、`parse_pconline` / `parse_ip_api`、`is_china_geo`（国家码优先、省名兜底、港澳台=非大陆、认不出=`None`）、`NetworkInfoProbe.collect`（属地源顺序 + 连通性 HEAD）、展示文案纯函数。 |
| `pet/network_info_dialog.py`（新） | +267 / −0 | 非模态小窗：卡片 12px 圆角 / 13px 正文 / 7px 字段、强调色 `#0a84ff`（待办面板同款令牌）、后台线程取一次、`shiboken6.isValid` 探活、失败逐字段「获取失败」+原因、「重新获取」按钮。 |
| `pet/settings_network.py`（新） | +200 / −0 | 设置页控件 / 行 / 保存：三条行 + 依赖显隐 + 保存委托 + 间隔行**按字体度量给宽**。 |
| `tests/test_net_monitor.py` / `test_network_info.py` / `test_network_info_dialog.py` / `test_network_info_menu.py` / `test_island_network_slot.py` / `test_settings_network.py`（新） | +434 / +289 / +201 / +189 / +242 / +181 | 全部注入替身，**零真实外网请求**。 |

**修改**

> *〔2026-10-07 终审修复对齐（`05b7a5e` + `ddbea79`）：本表 `pet/app.py` 行需补**弹窗单例
> 随父销毁收口**；`pet/settings_network.py` 另有 **+7/−0** 子宠页置灰（三键），
> 见 §9.1 / §9.2〕*

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/config.py` | +27 / −0 | 三键默认值（`island_network_enabled=False`、`network_probe_interval_seconds=1.0`、`network_info_menu_enabled=True`）、reload 白名单、`_normalize_pet_settings`（间隔走 `net_monitor.clamp_interval` 单一真值）、`Config.set` 归一化白名单。 |
| `pet/dynamic_island.py` | +96 / −1 | 网络槽：`_net_enabled` / `_net_interval`、`_info_text` 网络分支、`_sync_network_slot` / `_pause_network_slot` / `_tick_network`、`_make_net_monitor`（测试替换点）、hide / show / refresh 接线。 |
| `pet/context_menus/shared.py` | +21 / −0 | `network_info_menu_enabled`（两套建造器共用一个**显隐门**）+ `add_network_info`。**注意**：这条显隐口径在 `7ce25c8` 里已被**置灰对齐取代**（入口不再消失，见 2.2 与 §3.3），本行只是如实记录 `c0c2e70` 当时的状态。 |
| `pet/context_menus/registry.py` | +21 / −0 | label / icon / spec + `_network_info_available`（available 门，同 `music_*` 先例）+ `disabled_reason`。 |
| `pet/context_menus/legacy.py` | +4 / −0 | 旧版菜单同一门接入。 |
| `pet/menu_templates/modern-default-v1.json` | +1 / −0 | 「工具与帮助」内 `check_update` 之后加节点（**根节点 id 列表不变**，不影响其它快照）。 |
| `pet/sprite_menu_facade.py` | +11 / −0 | `on_network_info` → `AppShell.open_network_info`（overlay 侧）。 |
| `pet/app.py` | +27 / −0 | `_wire_window` 注入 `win.on_network_info`、`AppShell.network_info_dialog` 单例 + `open_network_info` / `_network_info_finished`。 |
| `pet/modern_settings_dialog.py` | +6 / −1 | import 1 行、岛页挂小节 3 行、保存委托 1 行；菜单域是既有「内容与布局」行的追加（净 0）。 |
| `tests/test_config_schema.py` | +81 / −0 | 快照三键。 |
| `tests/test_architecture.py` | +8 / −1 | 预算校准 + 新模块纳入纯逻辑零 Qt 守卫。 |
| `tests/test_menu_layout.py` / `tests/test_sprite_menu_parity.py` | +2 / −0 / +23 / −1 | 新入口纳入 legacy + modern 树比对与点击路由。 |

### 2.2 `7ce25c8`（置灰对齐）

`git log --numstat 7ce25c8`：

```
11	11	pet/context_menus/registry.py
21	6	pet/context_menus/shared.py
3	0	pet/modern_settings_dialog.py
4	1	tests/test_architecture.py
43	0	tests/test_menu_layout.py
81	24	tests/test_network_info_menu.py
32	3	tests/test_sprite_menu_parity.py
```

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/context_menus/shared.py` | +21 / −6 | 新增 `NETWORK_INFO_DISABLED_REASON = "已在设置里关闭「网络信息」菜单入口"`（置灰文案**单源**）；`add_network_info` 只在**回调缺失**时返回 `None`（能力不可用＝整条不出现），开关关掉时**仍建项但 `setEnabled(False)` + tooltip**（legacy 建造器直接调它，故置灰在此落地）。 |
| `pet/context_menus/registry.py` | +11 / −11 | `network_info` 的 `available` 只认回调（`_callback_available`），开关判定挪到 `enabled=_network_info_enabled`，`disabled_reason=NETWORK_INFO_DISABLED_REASON`；删掉旧 `_network_info_available`。`music_*` 的隐藏先例未动。 |
| `pet/modern_settings_dialog.py` | +3 / −0 | `_sync_menu_action_states` 把 `network_info` 移出 `enabled_actions`（开关关时），并接上开关 `toggled` → 即时刷新；编排器状态列从「此平台不可用」变成「已停用」。 |
| `tests/test_network_info_menu.py` | +81 / −24 | 两条门分开断言（`available`=回调、`enabled`=开关）；建造器置灰 + tooltip + 置灰项不触发回调；modern `populate` 渲染置灰并带说明；默认开启仍可用。 |
| `tests/test_sprite_menu_parity.py` | +32 / −3 | 原「关掉即消失」断言改为**真实 overlay 菜单树里仍存在但 `isEnabled() is False` 且有 tooltip**（legacy + modern 两套模板），另加默认启用断言。 |
| `tests/test_menu_layout.py` | +43 / −0 | 新增编排器状态列用例（配置态初始「已停用」/「已启用」+ 页面切换即时刷新，且**不回写布局树**）。 |
| `tests/test_architecture.py` | +4 / −1 | 行数预算常量同步。 |

### 未改动（看起来相关但故意没动）

- `music_*` 的「功能没开就不出现在菜单里」先例（`_music_lyric_configured`）：**刻意未动**——
  #172 的置灰对齐只针对本入口，避免顺手改掉另一条已被接受的产品决策。
- `docs/NETWORK-PROXY-AND-VPN-2026-09-22.md`：那是「实测数字」档案，本次的请求都没有采集
  实测值，**不往里填推断**。
- 岛卡片（展开态）里不加网络信息行。

## 三、实现要点

### 3.1 数据源与出口策略（本批最关键的决策）

- **延迟探测目标 `223.5.5.5:53`**（阿里公共 DNS，Anycast、境内、IP 字面量免解析、查询内容
  无隐私），**绝不默认打国外地址**。载荷是**合法 DNS A 查询**（`www.aliyun.com`，32 字节）
  ——用合法查询才指望解析器回包，发垃圾包会被静默丢弃、延迟永远测不出来。单次在网约
  **160 字节**（含 IP/UDP 头）。
- **出口口径分两类，别混**：
  - **属地 / 连通性的 HTTP 跟随系统代理**（`_default_opener()` = `build_opener()`，与 TTS /
    更新同口径，不做逐功能绕过）。因此开着代理 / 全局 VPN 时**属地显示的是出口节点**位置
    ——「在中国大陆：否」可能是代理造成的，弹窗 hint 明写这一条（属 feature，不是缺陷）。
  - **延迟探测是 UDP**（`223.5.5.5:53`），走 **OS 路由**：普通 HTTP/HTTPS 代理**不代理
    UDP**，所以它测的是不经代理那条路径的 RTT；只有全隧道 VPN 才会连它一起接管
    （那时显示的才是隧道内 RTT）。
- **属地源顺序**：优先**太平洋电脑网 IP 库**（境内可达、免 key、中文字段，响应体是 **GBK**
  ——按 UTF-8 硬解会乱码，故解码顺序 UTF-8→gb18030）；仅在它失败时回退 **ip-api.com**
  （`lang=zh-CN`）。`src/ip/isp` 与失败原因都如实展示。
- **「是否在中国」口径**：出口 IP 属地是否中国大陆，依据源给的国家码（`CN`）；源只给省市时
  按 31 个大陆省级行政区匹配，港澳台判为「否」，认不出的省名/英文地名判为**「判定不了」**。

### 3.2 岛上槽位接入方式（按既有信息槽惯例，未发明第二套）

> **【2026-10-07 就地标注 · 语义已废止】** 本节描述的「`island_network_enabled` 开启即由
> 网络信息**接管**信息槽内容」已被 **灵动岛 P1 段化重设计**（`feature/island-segment-redesign`，
> 报告 [`PR-REPORT-ISLAND-P1-SEGMENT-REDESIGN-2026-10-07.md`](PR-REPORT-ISLAND-P1-SEGMENT-REDESIGN-2026-10-07.md)）
> 废止：信息槽改为段序列（主信息段恒在 + `island_metrics` 指标段），网络只是其中一个
> 指标段，不再接管；`island_network_enabled` 已单向迁移进 `island_metrics`；「网络槽开着时
> 隐藏信息槽内容/自定义短文本两行」的依赖逻辑也已删除（`info_mode` 始终生效）。定宽槽串
> （速率 5 列 / 延迟 5 列）与「隐藏即休眠」两条契约仍然成立并被段化架构沿用。以下原文
> 保留作历史对照。

灵动岛现有信息槽架构是：`show_info` 控制显隐 + `info_mode` 选内容（时间/余额峰谷/余额/
自定义），文案由 `_info_text()` 出、胶囊宽度按文本宽度算。本次接入的方式：

- `island_network_enabled` 开启即**由网络信息接管信息槽内容**（关闭回到 `info_mode`）——
  开关是网络槽的**唯一所有者**，避免「开关开了但槽里还显示时间」这种看不出生效的状态；
  `_info_text` 是唯一接入点，不发新槽位、不改 `_visible_parts`。
- 文案**定宽**（速率 5 列 / 延迟 5 列右对齐）：胶囊宽度按文本算，**不定宽会每秒左右抖**。
- 设置页依赖链沿用同族机制：**岛开关 → 显示信息槽 → 网络槽开关**；网络槽开着时
  「信息槽内容 / 自定义短文本」自动隐藏（那时它不生效），关掉自动恢复。依赖位是 AND 叠加
  的字典位，与 `settings_pet_controls` 各写各的键、**与调用顺序无关**。
- 生命周期：**隐藏即休眠**（读取定时器停 + 采样线程停，socket 由线程自己收口，**不在 GUI
  线程 join**）；间隔改动即时生效不必重建线程；关闭则连对象一起收口。

### 3.3 两条门的语义分离（`7ce25c8` 的核心）

`add_network_info` 的两条门语义不同、**必须分开**：

| 门 | 判据 | 关掉时用户看到 |
|---|---|---|
| `available`（能力） | 回调是否存在（纯桌宠变体无此回调） | **整条不出现** |
| `enabled`（开关） | `network_info_menu_enabled` | **保留位置、置灰、tooltip 说明原因**（Runtime Disabled） |

第一批实现把开关放在了 `available` 上（入口会整个消失），与 [`../CONTEXT.md`](../CONTEXT.md)
的 **Runtime Disabled** 契约冲突：契约要求「功能开关关掉应保留位置、灰掉并解释」。
`7ce25c8` 把开关挪到 `enabled` + `disabled_reason`，并让 `add_network_info` 不再在开关关闭时
返回 `None`。副作用须知：菜单编排器状态列从「此平台不可用」变成「已停用」。

## 四、性能分析

**方法（可复现）**：采样与探测的耗时用本机直接测量；岛上槽刷新成本引用仓库既有实测的
CJK 文字 shaping 数字（同一实现路径）。功能侧全部走注入替身，**本次没有采集真实外网请求的
实测数字**，故不更新 [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md)
的实测表。
环境：Windows / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属 |
|---|---|---|
| 岛槽刷新（默认 1 秒间隔） | 每秒重建一次内容层缓存；既有实现里 **CJK 文字 shaping ≈ 6ms/次 → 约 0.6% 单核**（开槽用户可感知；关掉或把间隔调大即回落） | 新增（仅开关打开时） |
| 延迟探测单次在网字节 | 约 **160 字节**（`net_monitor.PROBE_BYTES_PER_ROUND = 160`，含 IP/UDP 头）；载荷 32 字节合法 DNS A 查询 | 新增 |
| 弹窗取数 | 一次 `collect`：属地 1 次 GET（+失败回退 1 次） + 连通性 HEAD ×2；**只在打开/点「重新获取」时** | 新增（离散） |
| 稳态开销（岛槽关闭、弹窗未开） | **零** —— 采样线程与定时器都不启动；`NetMonitor` 对象不构造 | 既有路径不变 |
| 隐藏即休眠 | 岛隐藏 → 定时器停 + 采样线程停（socket 由线程自己收口，**不在 GUI 线程 join**） | 新增（可停） |
| 新增线程 | 岛槽开启时 1 个常驻采样线程（`pet-net-monitor`，随开关/显隐起停）；弹窗 1 个短命线程 | 新增 |
| 新增网络 | **岛槽在跑就持续发包**（在跑 = 网络槽开着 AND 岛可见 AND 显示信息槽，见 `_net_active`）：速率读本机计数器（零流量），但延迟每周期一次 UDP 往返（1 发 1 收、约 0.16 KB）——默认 1 秒间隔 **13.2 MB/天**（`settings_network._traffic_hint` 实测：0.5s→26.4 / 2s→6.6 / 60s→0.2 MB/天），设置页文案按当前间隔实时显示；弹窗按需 1~4 个 HTTP 请求 | 新增（在跑即持续） |
| 新增磁盘 | 无 | — |
| 新增第三方依赖 | **无**（`psutil` 本就在 `requirements.txt`） | — |

**结论**：① **稳态开销零变化**——岛槽关闭时采样线程与定时器都不启动，弹窗不开则不取数；
② **新增路径绝对成本**：岛槽开启时每秒一次内容层重建（CJK shaping ≈6ms ≈0.6% 单核），
属「开了才付」的可见成本，已写进用户可见的间隔设置；③ **岛槽在跑就持续发探测包**（在跑 =
网络槽开着 AND 岛可见 AND 显示信息槽）——速率读本机计数器零流量，但**延迟必须发包才
测得出来**（每周期一次 UDP 往返、约 0.16 KB，默认 1 秒间隔 **13.2 MB/天**；设置页文案按
当前间隔实时算并显示，见 `settings_network._interval_hint`），弹窗那 1~4 个 HTTP 请求只在
用户打开时发生；④ **内存有界**——`NetMonitor` 持最新快照与短窗口速率状态，无累积缓存。

## 五、实机运行记录

**主代理本机真机验收（真实桌面、真实进程、真实鼠标输入驱动的产品实例）**：

- **弹窗（逐条照用）**：显示公网 IP **161.153.127.239** / **Arizona 凤凰城（Oracle，代理
  出口）** / Google **204** · GitHub **200** / 数据源 **ip-api.com**（**前序源 403 回退**）。
  即：① 属地源 A（太平洋电脑网）在真实网络上返回 403、回退到源 B 成功，**回退链在真机
  跑通**；② 属地结果如实展示为**代理出口节点**（Arizona / Oracle）——正是第三节写明的
  代理口径，不是缺陷；③ 连通性两项都带出真实 HTTP 状态码；④ 弹窗底部如实署名实际使用的
  数据源。
- **岛槽（逐条照用）**：显示 **「↓ 2K ↑ 1K 50ms」**——定宽文案在真实进程里按预期渲染
  （速率 + 延迟三段齐全）。
- **Runtime Disabled（逐条照用）**：**菜单关掉后入口置灰带说明**——第二批 `7ce25c8` 的
  契约对齐在真机生效：开关关掉后入口**不消失**，而是灰掉并且在悬停时给出
  「已在设置里关闭「网络信息」菜单入口」。

**本机真实环境（自动化在真实 Windows 平台跑过）**：`test_network_info_dialog.py` 的
`test_apply_snapshot_is_a_noop_on_deleted_dialog` 走真实 `shiboken6` 探活路径；其**变异验证**
（删掉 `isValid` 探活）在真机上必红（`RuntimeError: Internal C++ object already deleted`）。

**边界与失败路径（实机/自动已验证）**：

- 属地源 A 失败（真机 403）→ 自动回退源 B 并在界面署名实际源（真机已跑通）。
- 「判定不了」路径：源只给省市时按 31 个大陆省级行政区匹配，港澳台=「否」，认不出的
  省名/英文地名=「判定不了」（**不硬猜**）。
- 弹窗在宿主销毁后 `apply_snapshot` 为空操作不崩（真实 `shiboken6` 探活）。
- 岛隐藏 → 采样线程与定时器停（自动化断言线程消失）。

**无法自动验证的能力（如实登记）**：

- **延迟探测目标在本机代理/VPN 环境下是否回包**：实现按规范未在测试里发真实请求；真机
  **已确认延迟有值（50ms）**，故该风险在验收中关闭。
- **断网失败路径未做实机对照**：把系统代理指到死端口后的逐字段「获取失败」+原因，只有
  自动化覆盖，未做真机断网实测。
- **三态延迟对照（直连 / 全局 VPN / 死端口代理）未逐态实测**：真机只取了常态（走代理）一态。
- **观感未验收**：弹窗在明/暗主题下的观感、以及系统字体放大后间隔输入框内 `60.0 秒` 是否
  被裁（已按字体度量放宽，本机默认字体下原基类 92px 是零余量）——都需要人眼确认。
- **`whois.pconline.com.cn` 是 HTTP**（免费源基本都是 http，ip-api 免费档同样只支持 http）：
  明文请求且服务方可见用户出口 IP，这是属地查询的固有代价，界面 hint 已写明口径。

## 六、测试与验证

> *〔2026-10-07 终审修复对齐（`05b7a5e`）：本节的切片与聚焦计数已过期，增量见 §9.3
> （新增 +206 行测试，含代隔离/单例收口/三态的变异复验）〕*

**红 → 绿（两批各自 test-first）**

**第一批 `c0c2e70`（含 4 次变异验证：新测试确实会因缺陷变红）**

| # | 变异 | 结果 |
|---|---|---|
| 1 | `Config.set` 未列入归一化白名单 | `test_set_normalizes_network_keys` **红**（`assert 'false' is False`）→ 补白名单 → 绿（**真实缺陷，非测试写错**） |
| 2 | 属地认不出的省名首版返回 `False`（把「判不了」误判成「不在中国」） | 期望 `None` **红** → `_normalize_region` 未识别返回空串 → 绿 |
| 3 | 把注册表 spec 换回 `_callback_available`（去掉 cfg 门） | `test_gate_default_on_...` / `test_availability_helper_...` **红** → 恢复 → 绿 |
| 4 | `_info_text` 网络分支改恒 `False` | `test_network_slot_on_starts_worker_and_shows_sample` / `..._lost_probe_shows_dashes` **红** → 恢复 → 绿 |
| 5 | 删掉弹窗 `shiboken6.isValid` 探活 | `test_apply_snapshot_is_a_noop_on_deleted_dialog` **红**（`RuntimeError: Internal C++ object already deleted`）→ 恢复 → 绿 |
| 6 | 行数预算：接线后 `test_modern_settings_dialog_py_line_budget` | **红**（2420 > 2415）→ 按仓库规程校准常量（带日期注释）→ 绿 |

既有快照两处（`test_menu_layout` 的注册集合与「工具与帮助」子菜单清单）因新增节点红 →
按实现同步 → 绿。

**第二批 `7ce25c8`（先改断言 → 红 → 实现 → 绿）**

先改断言 → 因 `NETWORK_INFO_DISABLED_REASON` 不存在 / 门还在 `available` 而**红** →
实现后绿。**变异复验**：临时删掉 `add_network_info` 的置灰分支 →
`test_add_network_info_keeps_disabled_entry_when_switch_off` 与
`test_network_info_entry_greyed_out_when_switched_off` **红（2 failed）** → 恢复 → 绿。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `ruff check pet/ tests/` | **All checks passed**（两批各跑一次） |
| 聚焦（第一批） | 本轮新增 6 文件 + `test_config_schema` / `test_architecture` / `test_menu_layout` / `test_sprite_menu_parity` | **226 passed** |
| 聚焦（第二批） | 架构 / 配置 / 采样 / 数据层 / 弹窗 / 菜单 / 岛槽 / 设置行 / 菜单布局 / parity | **237 passed** |
| 全量（`c0c2e70`） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4527 passed, 11 skipped**（exit 0，11m56s） |
| 全量（`7ce25c8`） | 同上 | **4532 passed, 11 skipped**（exit 0，10m24s） |
| 空白检查 | `git diff --check` | 通过 |
| 集成全量（当晚最终树） | `QT_QPA_PLATFORM=offscreen python -m pytest -q`（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

无新增第三方依赖；无打包改动（`pet/menu_templates` 已在三端构建脚本里 `--add-data`）。

## 七、已知限制与后续

> *〔2026-10-07 终审修复对齐（`05b7a5e`）：新增两条（弹窗单例失效可自愈重建 / 换代即丢
> 窗口），详见 §9.4〕*

1. **实测数字只有真机数字、没有采集**：本次没有把请求耗时写进
   [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md) 的实测表
   ——那是「实测数字」档案，不宜填推断。真机验收里拿到了 ip-api 回退成功的现场，但未记录
   各端点耗时。
2. **岛槽每秒刷新有可感知成本，且会持续发包**：CJK shaping ≈6ms/次 ≈0.6% 单核（第四节），
   且**延迟不发包就测不出来**——在跑期间按间隔持续发 UDP 探测（默认 1 秒间隔约
   **13.2 MB/天**，第四节；设置页文案按当前间隔实时算）。开槽用户可感知；关掉、关掉
   「显示信息槽」或把间隔调大即回落。这是「开了才付」的可见成本，不做优化（优化需缓存
   文本层，属另一刀）。
3. **属地源是 HTTP**：明文请求、服务方可见出口 IP（见第五节）。
4. **UDP 53 被屏蔽时延迟恒显示 `--`**：此时可按建议改为探测网关，代价是要读 Windows 路由表
   （未做）。本机验收已确认 `223.5.5.5` 回包，故本机风险关闭，但其他网络环境不保证。
5. **`network_info_menu_enabled` 的语义已变更**：第二批起它是 **enabled 门**（置灰）而非
   available 门（隐藏）。**本条为现行口径**，第一批的实现与描述已被取代。
6. **未做**：岛卡片（展开态）里的网络信息行；弹窗的亮/暗主题与放大字体观感验收。

## 八、风险与回滚

- **影响面**：三个新配置键，默认值下岛槽**关**、菜单入口**开**、间隔 1.0s；用户不开岛槽
  就不产生采样线程、不发探测包。新增一个非模态弹窗与一条菜单项（两个模板都接）。网络出口
  分两类：**弹窗的 HTTP 只在用户主动打开时发生**；**岛槽在跑期间按间隔持续发 UDP 探测包**
  （默认 1 秒间隔约 13.2 MB/天，见第四节；关掉开关 / 关掉「显示信息槽」/ 调大间隔即停或
  减量）。
- **配置迁移**：`island_network_enabled`（默认 `False`）、`network_probe_interval_seconds`
  （默认 `1.0`，走 `net_monitor.clamp_interval` 单一真值）、`network_info_menu_enabled`
  （默认 `True`）；老配置无此键 → 取默认。无落盘数据迁移。
- **隐私/网络面**：弹窗会把出口 IP 交给两家属地源（A 优先国内、B 是海外）；
  岛槽的 UDP 探测载荷是**无隐私内容的公共 DNS 查询**，目标固定境内 Anycast。
- **回滚**：`git revert` 两个提交即可，无残留状态（config 里多出的三个键退化为无害未知键；
  采样线程随开关/对象收口，不残留；弹窗单例随进程退出消失）。**注意**：`7ce25c8` 依赖
  `c0c2e70`（它改的是同一批代码的门语义），逐个 cherry-pick 会冲突，应按顺序一起回滚。
- **合并冲突面**：`tests/test_architecture.py`（行数预算常量 + 纯逻辑模块名单）、
  `pet/menu_templates/modern-default-v1.json`（`tools_help` 内加节点，用户自定义布局由
  `merge_default_menu_actions` 自动补上）、`tests/test_config_schema.py`（两份字面量快照）、
  `tests/test_sprite_menu_parity.py`（legacy + modern 树比对）。当晚与 #209 / #228 在菜单与
  快照处撞车，按合并提交的并序结论为准（并入后实测预算 **2426**）。
- **分支状态**：两个提交分别经 `3c54e32` 与 `277117a` 并入
  `integration/2026-10-07-night-batch`；分支未 push、PR 未开。


## 九、终审修复对齐（2026-10-07 追加）

> 按 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) 的「后续轮次在同一文档追加新章节、
> 保留新旧对照，不要重写覆盖」约定**追加**：上文记录的是各提交当时的树，本节只记终审修复
> 带来的增量。上文对应位置已就地加注「2026-10-07 终审修复对齐（提交 `<sha>`）」。
> （岛槽**三态**的增量已在 §1 / §4 / §7 就地加注，本节不重复。）

### 9.1 §2 修改文件说明的增量（`05b7a5e`）

| 文件 | 本批增量 | 要点 |
|---|---|---|
| `pet/net_monitor.py` | +49 / −12 | **采样的「代（generation）」隔离**：`stop()` 立刻允许 `start()`，而上一轮可能仍卡在收包里，故每一代独立 **generation token + 独立 `NetRateMeter` + 独立停止事件**；`_publish` 发布前核验「自己还是不是当前代」，**旧代晚到的结果与回调一起丢弃**；**速率基线不跨代共用**（两代重叠读计数器不会把基线推来推去），新一代第一轮重建基线——宁可少报一个周期的速率也不报错值 |
| `pet/app.py` | +24 / −3 | **弹窗单例随父销毁收口**：`destroyed` 信号**按对象身份**收口（旧窗晚到的信号不得清掉新实例）；复用路径先查 `shiboken6.isValid`，失效对象直接丢弃重建，不再抛 `RuntimeError: Internal C++ object already deleted` |

**由此修订的两处上文口径**：

1. **§2 对 `NetMonitor` 的描述**「后台线程 + 快照 + **每 run 独立停止事件与 socket**」已不完整：
   现行是**每代三件套**（token / meter / 停止事件）且**发布前做代核验**；§4 性能表里
   「隐藏即休眠 → 采样线程停」也随之多一层含义——换代即丢窗口，旧代在途结果不会污染新代快照。
2. **§2 的 `pet/app.py` 行**（「`network_info_dialog` 单例 + `open_network_info` /
   `_network_info_finished`」）需补上销毁收口与失效重建两条。

### 9.2 §2 设置行的增量（`ddbea79`）

`pet/settings_network.py` 另有 **+7 / −0**：网络三键（岛开关 `island_network_check` /
间隔 `network_probe_interval_spin` / 菜单入口 `network_info_menu_check`）在**子宠页置灰** +
tooltip「仅主桌宠可设置」。理由与免打扰、天气、foobar 同族——这些键不在
`PER_SLOT_SETTING_KEYS` 里（进程级/全局语义，不是逐宠偏好），子宠设置进程写的是
`config-slot-N.json` 而运行期读主配置，原先属「能保存、运行时不消费」的静默死开关。
收口函数：新增的 `settings_widgets.mark_main_pet_only()`（主宠页一个不动、幂等、
控件不存在时静默跳过）。

### 9.3 §6 测试与验证的增量

`05b7a5e` 新增 **+206 / −0**：`tests/test_net_monitor.py` +84、`tests/test_island_network_slot.py` +47、
`tests/test_network_info_menu.py` +75。新增覆盖与**变异复验**：

- M8 代隔离：**旧代晚到不得覆盖新代**（阻塞式收包 + 事件编排，第一代收口由其 socket 关闭
  确认）、新一代重新建基线两例；去掉代核验 / 共用 meter **各让对应用例变红**，恢复绿。
- M9 单例收口：销毁后重开、单例被静默失效后重开、旧 `destroyed` 信号晚到三例；去掉
  `isValid` 复现 `RuntimeError`，去掉身份核对让「晚到信号清掉新实例」变红。
- m4 三态：三态（岛开关 / 信息槽 / 网络槽）与岛不可见两例；不去看 `show_info` 即变红。
- 聚焦 240 passed；全量 `4539 passed, 11 skipped`（该提交自报口径）。

上文 §6 的两批红→绿切片与聚焦计数（226 / 237）**因此过期**。

### 9.4 §7 已知限制与后续的增量

- **新增**：**弹窗单例可被静默失效后自动重建**（不再抛 `deleted`）——即「宿主销毁 → 重开」
  这条路径现在是自愈的，不再是"必须重启桌宠"。
- **新增**：**换代即丢窗口**——`stop()` / `start()` 快速交替（隐藏-显示抖动）时，上一代
  在途的那一拍速率会被丢弃（新一代重建基线），表现为偶尔少显示一拍速率，而不会显示错值。
- 岛槽三态的成本收益（关掉「显示信息槽」即停采样与刷新、丢弃快照）已在 §7 第 2 条就地加注。
