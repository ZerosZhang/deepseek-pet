# issue #209：查看天气 + 多城市（国内源优先、国外源兜底）

> **基线**：`0ba442c`（四份交付报告与 INDEX 登记）；本提交经 `bc34ac5` 并入 integration
> **分支**：`feature/issue-209-weather`　**提交**：`34bdce1`　**日期**：2026-10-07
> **范围**：24 个文件（实现 14、测试 10），净 `+2484 / −7`
> **关联**：issue #209；菜单/配置/行数预算与 #172、#228 并序（并入后实测预算 2421）
> **互链**：网络与系统代理口径见 [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md)；
> 设置准入/准出见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)；必备证据章节见
> [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在 [`INDEX.md`](INDEX.md) 的
> 「PR 报告存档」。

## 一、核心特性

新增「查看天气」与「天气城市」两个右键入口：右键 →「查看天气」按**当前城市**取实况并冒
气泡；「天气城市」是一个子菜单，用来增删城市和切换当前城市（加城市走一个搜索 + 手填兜底
的对话框）。取数走**两个源、两套出口**：国内源（中国天气网）**显式直连**，国外源
（open-meteo）**跟随系统代理**——前者在国内走代理慢 7~11 倍，后者两侧相当且能覆盖
「只有代理能出网」的已知缺口。任一源成功即出数；两源都失败时**把两个源各自的原因都写进
气泡**，不静默。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 实况气泡 | `鹿城 晴 16.4℃，西北风 1级，湿度 76%（中国天气网）`，成功停 8s / 失败 12s |
| 2 | 多城市 | 增删城市、切换当前城市、列表上限 **12**、删除当前城市自动重指；持久化到 config |
| 3 | 城市名容错 | 带后缀名（`鹿城区`）先按原名搜、搜不到用归一化名重搜；取数侧也对存量值试两个变体 |
| 4 | 双源兜底 | 源 A（中国天气网）失败 → 源 B（open-meteo，走代理）；**两源原因都上报** |
| 5 | 全路径不静默 | 未选城市 / 功能关闭 / 搜索无结果 / 城市已满 / 两源都失败，各有具名文案 |
| 6 | 设置页「互动 → 天气」 | 三行：启用天气（默认**开**）、当前城市、城市列表 |

**红线 / 不变量**：
- 取数**只在用户主动点击时发生**（不轮询、不后台刷新）；
- 「未选城市」「功能已关闭」这两条引导路径**不发请求、不起线程**，且**不解忙门**
  （否则用户点第二下会被静默忽略）；
- 单请求超时 6s、总预算 15s；预算耗尽后后续请求直接按超时失败，**不再发出**；
- 宿主窗口销毁后回调必须被丢弃而不是崩溃（`shiboken6.isValid` 探活，同余额桥口径）。

## 二、修改文件说明

`git log --numstat 34bdce1`：

```
16	0	pet/app.py
22	0	pet/config.py
10	0	pet/context_menus/icons.py
3	0	pet/context_menus/legacy.py
30	0	pet/context_menus/registry.py
2	0	pet/menu_templates/modern-default-v1.json
2	0	pet/modern_settings_dialog.py
7	2	pet/settings_interaction.py
102	0	pet/settings_weather.py
14	0	pet/sprite_menu_facade.py
538	0	pet/weather.py
382	0	pet/weather_menu.py
176	0	pet/weather_service.py
1	0	pet/window.py
9	1	tests/test_architecture.py
49	0	tests/test_config_schema.py
1	0	tests/test_desktop_pet_features.py
10	2	tests/test_menu_layout.py
6	2	tests/test_settings_interaction_tabs.py
4	0	tests/test_sprite_menu_parity.py
352	0	tests/test_weather.py
352	0	tests/test_weather_menu.py
247	0	tests/test_weather_service.py
149	0	tests/test_weather_settings.py
```

### 实现

> *〔2026-10-07 终审修复对齐（`9d922d6`）：本表 **5 行**的增删数与语义已被修订——
> `pet/weather.py`（归一化改可逆 + 查询侧变体 + `read_bounded`）、`pet/weather_service.py`
> （结算与呈现解耦）、`pet/weather_menu.py`（地区码身份 + `textEdited` 作废候选）、
> `pet/settings_weather.py`（子宠页置灰）、`pet/config.py`（**新增第四键 `weather_city_codes`**），
> 增量见 §9.1 / §9.4〕*

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/weather.py`（新） | +538 / −0 | 纯逻辑 + 取数（**无 Qt**）：城市名归一化/容错、城市列表操作（去重·上限 12·删当前城市重指）、WMO 码/风向/风力等级中文映射、源 A/B 响应解析、`WeatherClient`（`http=` / `clock=` 可注入，单请求超时 6s + 总预算 15s）、`WeatherError` 与失败文案。 |
| `pet/weather_service.py`（新） | +176 / −0 | `WeatherService`（AppShell 持有）：忙门、`pet-weather` 后台线程、`_WeatherBridge`（queued 信号回 GUI 线程）、气泡落地；「无城市 / 功能关闭」走**不联网的直接冒泡**且不解忙门。 |
| `pet/weather_menu.py`（新） | +382 / −0 | 「查看天气」「天气城市」两个建造器、城市增删改的配置写入、`WeatherCityDialog`（搜索 + 手填兜底）、搜索线程桥；`dialog_factory` / `search` / `run_async` 可注入。 |
| `pet/settings_weather.py`（新） | +102 / −0 | 「互动 · 天气」标签的控件创建 / 行装配 / 保存委托；城市列表上限与「当前城市必须在列表里」的保存语义。 |
| `pet/config.py` | +22 / −0 | 三键（`weather_enabled=True` / `weather_city=""` / `weather_city_list=[]`）四处登记：默认值 dict、reload 白名单、`_normalize_pet_settings`（懒导入 weather，保持单一来源）、`set()` 归一化名单。 |
| `pet/app.py` | +16 / −0 | `AppShell.show_weather(parent)` 懒建服务单例 + `self._weather_service = None` + `_wire_window` 注入 `win.on_show_weather`（与聊天能力无关）。 |
| `pet/window.py` | +1 / −0 | `self.on_show_weather = None`（与 `on_show_balance` 同处）。 |
| `pet/sprite_menu_facade.py` | +14 / −0 | overlay 侧 `on_show_weather` 属性 → `AppShell.show_weather`；父窗传壳（与 `on_show_balance` 同口径，但不受聊天门控）。 |
| `pet/context_menus/registry.py` | +30 / −0 | 注册 `weather` / `weather_cities` 两个 action（标签、矢量图标、`available` / `enabled` + `disabled_reason`）；`weather_cities` 是**builder 自带子菜单**的 action 节点（同 `character`/`size`/`quick_launch` 先例）。 |
| `pet/context_menus/legacy.py` | +3 / −0 | 旧版扁平布局接上两个入口（放在「回到右下角」之前）。 |
| `pet/context_menus/icons.py` | +10 / −0 | 新增 `weather` 语义矢量图标（太阳 + 八射线，单色描边语言）。 |
| `pet/menu_templates/modern-default-v1.json` | +2 / −0 | 默认布局在 `todo_panel` 之后插入 `weather`、`weather_cities`（section=tools）。老用户布局由 `merge_default_menu_actions` 自动补齐。 |
| `pet/settings_interaction.py` | +7 / −2 | 互动域加第三个页内标签「天气」，挂 `settings_weather.build_weather_tab`（与 `file_interpret` 同口径：行不在 `all_rows` 快照里，无需 claim）。 |
| `pet/modern_settings_dialog.py` | +2 / −0 | 只有两行接线：`from . import settings_weather` + `_write_config` 里 `settings_weather.save_weather_settings(self)`。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_weather.py`（新） | +352 / −0 | 69 例：城市名归一化/容错、列表操作与上限、WMO/风向映射、双源解析、超时与总预算、失败文案。**HTTP 出口注入，零真实外网请求**。 |
| `tests/test_weather_service.py`（新） | +247 / −0 | 11 例：忙门、线程桥、气泡落地与时长、无城市/功能关闭的短路与「不解忙门」、宿主销毁丢弃。 |
| `tests/test_weather_menu.py`（新） | +352 / −0 | 21 例：两个建造器、城市增删改写入、对话框搜索与手填兜底、搜索失败/无结果文案、已满 12 告警。 |
| `tests/test_weather_settings.py`（新） | +149 / −0 | 8 例：三行存在与初值、保存语义（当前城市必须在列表里）、上限。 |
| `tests/test_architecture.py` | +9 / −1 | 行数预算 2415 → **2417**（见第七节）。 |
| `tests/test_config_schema.py` | +49 / −0 | 白名单快照加 3 键 + 脏值归一化用例（`"false"` 不误开、列表去空去重、超上限截断）。 |
| `tests/test_menu_layout.py` | +10 / −2 | 默认布局节点表、resolver 期望表、真实 QMenu 渲染表三处加入两个新条目。 |
| `tests/test_desktop_pet_features.py` | +1 / −0 | 现代菜单标签清单加两条。 |
| `tests/test_settings_interaction_tabs.py` | +6 / −2 | 标签契约加第三个标签 + 行归属 + 组名 `["天气"]`。 |
| `tests/test_sprite_menu_parity.py` | +4 / −0 | 基准 `PetWindow` 镜像 `_wire_window` 加 `on_show_weather`；`_StubAppShell` 加 `show_weather`。 |

### 未改动（看起来相关但故意没动）

- `CONTEXT.md`：未引入新领域术语；天气沿用既有 **Runtime Disabled** / **Capability
  Unavailable** 语义，无词条可加。
- `docs/NETWORK-PROXY-AND-VPN-2026-09-22.md`：那是「实测数字」档案，本次的源延迟实测见本文
  第四节，**不往它的表格里填推断**。
- `README.md` 功能条目：归发布方。

## 三、实现要点

### 3.1 双源 × 双出口（本批最关键的决策）

**决策：国内源（中国天气网）显式直连；国外源（open-meteo）跟随系统代理。**
不放全局绕过、不改用户代理设置——沿用
[`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md) §四的口径，
只是把「逐功能」细化成「**逐源**」。实现落在 `pet/weather.py::_default_http(use_proxy=...)`，
测试逐个请求断言 `use_proxy`，代理策略有机器护栏。

三条理由见第四节实测：① 国内源走代理慢 7~11 倍，而点一次「查看天气」要连发两个请求，
慢代理下会重演歌词取词那次的「点了像坏了」；② open-meteo 两侧相当（差 0.2~0.3s），
跟随代理几乎无代价，却覆盖了「只有代理能出网」的用户；③ 两个源走不同出口还带来冗余——
全局代理挡住国内源时，走代理的 open-meteo 仍能出数（真机冒烟里强制源 A 失败后它 2.17s
拿到数据）。

### 3.2 失败口径真值表（判定顺序即用户可见行为）

| 场景 | 代码路径 | 用户看到 |
|---|---|---|
| `weather_enabled=False` | 菜单项置灰 + tooltip「天气功能已在设置中关闭」；服务端也拦 | 气泡「天气功能已在设置中关闭（设置 → 互动 → 天气）」 |
| 未选城市（`weather_city` 与列表都空） | 不发请求、不起线程 | 「还没选天气城市：右键菜单 → 天气城市 → 添加城市…」 |
| 源 A 成功 | 直连 2 请求 | 「鹿城 晴 16.4℃，西北风 1级，湿度 76%（中国天气网）」 |
| 源 A 失败、源 B 成功 | 直连失败 → 走代理 2 请求 | 「北京 晴 15.9℃，西风 1级，湿度 44%（open-meteo）」+ 日志 `天气取数失败 <城市>（中国天气网）：<原因>` |
| 两源都失败 | 抛 `WeatherError`，文案含**两个源各自的原因** | 「天气获取失败（北京）：中国天气网：请求超时；open-meteo：网络连接失败：…」 |
| 预算耗尽（15s） | 后续请求直接按超时失败，不再发出 | 同上，原因里带「请求超时」 |
| 城市名带后缀（鹿城区） | 源 A 原名搜不到 → 用归一化名重搜；取数侧也对存量值试两个变体 | 正常出「鹿城 …」 |
| 添加城市搜索失败 | `search_cities` 返回 `([], 原因)`，不抛 | 对话框状态栏「搜索失败：<原因>（可以直接添加你输入的城市名）」 |
| 搜索无结果 | 同上、原因空 | 「没有找到这个城市（可以直接添加你输入的城市名）」 |
| 城市已满 12 | `add_city` 返回错误，列表原样 | 告警框「最多只能有 12 个城市」 |
| 连点 / 取数中再点 | 忙门 | 静默忽略（不叠请求）；「无城市 / 已关闭」的引导气泡**不**解忙门 |
| 宿主窗口已销毁 | `shiboken6.isValid` 探活 | 丢弃，不崩（同余额桥） |

> *〔2026-10-07 终审修复对齐（`9d922d6`）：本表 **3 行**的语义已变——
> 「城市名带后缀」、「宿主窗口已销毁」、「预算耗尽」；修订后的行见 §9.2〕*

### 3.3 两个默认值的取舍

- `weather_enabled` 默认 **开**：纯拉取型功能，不点不联网、不主动冒泡；默认关只会让第一次
  点击撞一句「功能已关闭」。这与报时/节日这类**主动打扰型**默认关的判断标准一致。
- `weather_city` 默认 **空**、**不猜城市**：气泡永远会报城市名，猜错（比如默认北京）比给
  一句可执行的引导更糟；代价是首次使用要添加一次城市。

## 四、性能分析

**方法（可复现）**：源码与代理延迟对比用本机直接测量（2026-10-07，同机、同网络、
同一时段各 3 次取**中位**）：`py -c` 逐端点调用；功能侧端到端用**不入库**的
`weather_smoke.py` 手动跑。
环境：Windows / Python 3.13.7 / PySide6 6.11.2；系统代理 `http://127.0.0.1:7890`。

**① 源延迟（3 次中位）——「国内源直连 / 国外源跟代理」决策的实测依据**

| 端点 | 直连 | 走代理 | 倍率 |
|---|---|---|---|
| 中国天气网·城市检索 | **0.09s** | 0.63s | 慢约 **7×** |
| 中国天气网·实况 | **0.05s** | 0.57s | 慢约 **11×** |
| open-meteo·geocoding | 1.14s | 1.43s | 慢 0.29s |
| open-meteo·forecast | 0.85s | 1.02s | 慢 0.17s |

**② 端到端（真机联网冒烟，非 pytest）**

```text
$ py weather_smoke.py
鹿城      0.90s    （源 A 直连）
鹿城区    0.75s    （容错生效：原名搜不到 → 归一化名重搜）
北京      0.49s    （源 A 直连）
强制源 A 失败 → open-meteo 2.17s 出数
两源都失败   → 文案点名两个源
城市检索「鹿城区」→ 11 条候选，鹿城排第一
```

| 指标 | 实测 | 归属 |
|---|---|---|
| 稳态开销（未点菜单、未开设置页） | **零** —— 服务懒建（`AppShell.show_weather` 首次点击才构造）、无轮询、无后台刷新 | 既有路径不变 |
| 新增路径成本 | 一次点击 = 1~4 个 HTTP 请求，冷启动总时长 0.49s~2.17s（见上）；单请求超时 6s、总预算 15s 硬顶 | 新增（离散用户动作） |
| 新增线程 | 取数 1 个短命后台线程（`pet-weather`）+ 搜索对话框 1 个；**用完即退**，非常驻 | 新增（短命） |
| 新增网络 | 仅用户主动点击时；源 A 直连不计入代理、源 B 跟随系统代理 | 新增（离散） |
| 新增磁盘 | 仅城市列表写回 config（既有原子写路径） | 新增（极低频） |
| 内存 | 服务单例 + 城市列表（上限 12 条短文本），**无响应缓存增长** | 新增（有界） |

**结论**：① **稳态开销零变化**——不点菜单时该功能在运行期完全不参与（服务未构造、无定时器、
无线程）；② **新增路径成本有界**——每个请求 6s 超时、整条链 15s 总预算，之后不再发请求；
③ **未引入常驻线程/轮询/后台刷新**，网络只在用户主动动作时发生；④ **内存有界**——城市列表
上限 12 条，无响应缓存。

## 五、实机运行记录

**主代理本机验收（真实桌面、真实进程、真实鼠标输入驱动的产品实例）**：

- **用户可见行为确认（逐条照用）**：**添加城市「鹿城区」→ 11 候选鹿城（浙江）→ 气泡
  「鹿城 晴 15.6℃，西北风 1级，湿度 79%（中国天气网）」**。即：① 城市名容错在真实进程中
  生效（输入带后缀的「鹿城区」，搜索返回 11 条候选且「鹿城（浙江）」排第一）；② 添加后
  第一次取数即在气泡里给出城市名 + 天气 + 风向风力 + 湿度 + **数据源署名**。

**根因/前提的现场复现**：本轮为新增功能，无「修复前症状」可复现。等价前置证据是红→绿切片
（第六节）：新模块尚不存在时四条切片各自全红（`ImportError` / `ModuleNotFoundError` /
8 failed），实现后全绿。

**真机联网冒烟（本机真实网络、真实外网请求）**：见第四节 ②——四条路径（源 A 直连 / 容错
重搜 / 强制源 A 失败走源 B / 两源都失败）与城市检索都在真实网络上跑通，数字取自真实响应。

**边界与失败路径（实机/自动已验证）**：

- 两源都失败时气泡**点名两个源各自的原因**，不是静默、不是空白（真机冒烟已跑）。
- 未选城市时点「查看天气」→ 出引导气泡且**不发请求**（自动化覆盖 + 忙门不解）。
- 城市已满 12 → 告警框「最多只能有 12 个城市」，列表原样。
- 宿主窗口销毁后回调丢弃不崩（`shiboken6.isValid`，与余额桥同口径）。

**无法自动验证的能力（如实登记）**：

- **设置页与对话框的视觉观感未验收**：`WeatherCityDialog` 用的是原生 Qt 控件（没有自定义
  QSS，主进程也不装全局 QSS，与 `QInputDialog` / `QMessageBox` 先例一致），亮/暗主题下的
  观感需要人眼确认。
- **legacy 多进程槽位下的城市列表写的是该槽自己的配置**（overlay 与主窗路径都是主配置）——
  属已知边界，未专门处理。
- 断网路径的 15s 上限只有自动化覆盖，未在真机做「拔网线等满 15 秒」的实测。

## 六、测试与验证

> *〔2026-10-07 终审修复对齐（`9d922d6`）：本节的切片与计数已过期，增量见 §9.5
> （四个既有测试文件净增约 +369/−42，新增/改写约 30 条）〕*

**红 → 绿（先写测试、后写实现）**

| 切片 | 红灯证据 | 绿灯 |
|---|---|---|
| 纯逻辑 | `ImportError: cannot import name 'weather' from 'pet'`（69 条全收集失败） | **69 passed** |
| 服务层 | `ModuleNotFoundError: No module named 'pet.weather_service'` | **11 passed** |
| 菜单层 | `ModuleNotFoundError: No module named 'pet.weather_menu'` | **21 passed** |
| 设置页 | 回退 `settings_interaction.py` / `config.py` / `modern_settings_dialog.py` 到 `HEAD~1` 后跑新用例 | **8 failed**（缺标签/缺行/缺键）→ 恢复后 **8 passed** |

设置页那一片是「先写测试、后写实现」的完整闭环：8 条断言确实因缺实现而红，且恢复工作树
后 `git status` 复检干净。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | **All checks passed** |
| 空白检查 | `git diff --check` | 干净 |
| 全量（提交后树上复跑） | `QT_QPA_PLATFORM=offscreen python -m pytest -q --timeout=600` | **4532 passed, 11 skipped, 0 failed in 11:33**（collect 4543） |
| 真机联网冒烟 | `py weather_smoke.py`（不在 pytest 里） | 见第四节 ② |
| 集成全量（当晚最终树） | `QT_QPA_PLATFORM=offscreen python -m pytest -q`（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

无新增第三方依赖（HTTP 走标准库）；无打包改动。

## 七、已知限制与后续

> *〔2026-10-07 终审修复对齐（`9d922d6`）：新增两条（15s 预算属软上限 / 存量被改坏的城市名
> 不自动修复），详见 §9.3〕*

1. **行数预算**：`modern_settings_dialog.py` 只加 2 行（import + 保存委托，与
   `settings_file_interpret` / `settings_music` 形态一致；页面本体全在 `settings_weather.py`），
   2415 超到 **2417**，按该文件既有规矩在 `tests/test_architecture.py` 带日期注释校准
   （并写明「再省只能压行/合并语句，是注释明令禁止的反向优化」）。本分支并入 integration
   时实测预算 **2421**；当晚全部批次并入后最终实测 **2426**（见各自的合并提交）。
2. **城市列表的 per-slot 语义**：legacy 多进程槽位下写的是该槽自己的配置；overlay 与主窗
   路径都是主配置。属已知边界，未专门处理。
3. **默认值可一行改**：若产品希望开箱即有数据，把 `weather_city` / `weather_city_list`
   默认改成 `"北京"` / `["北京"]` 即可（`config.py` 三处 + snapshot 用例）。
4. **未做**：README 功能条目、`CONTEXT.md` 词条（无可加）、`docs/NETWORK-PROXY-AND-VPN-2026-09-22.md`
   的实测表更新（本次不填推断）。
5. **未做视觉验收**：`WeatherCityDialog` 亮/暗主题观感（见第五节）；如需与设置页统一风格，
   需要另开一刀加 QSS。

## 八、风险与回滚

- **影响面**：三个全新配置键，默认值下用户不点菜单就零变化。新增两条菜单项（两个模板都接）
  与设置页一个页内标签；`modern_settings_dialog.py` +2 行接线。取数只在用户主动点击时发生，
  **不引入任何后台轮询或常驻线程**。
- **配置迁移**：`weather_enabled`（默认 `True`）、`weather_city`（默认 `""`）、
  `weather_city_list`（默认 `[]`）；老配置无此键 → 取默认；手改脏值由
  `_normalize_pet_settings` 收口（`"false"` 不误开、列表去空去重、超上限截断）。
  无落盘数据迁移。
- **隐私/网络面**：城市检索与实况请求会把城市名与出口 IP 交给数据源；这是取数的固有代价，
  已在实现中**把国内源设为默认路径**（够用时不把数据多给一家海外服务）。
- **回滚**：`git revert 34bdce1` 即可，无残留状态（config 里多出的三个键退化为无害未知键；
  服务单例随进程退出消失；城市列表落盘数据保留但不再被读取）。
- **合并冲突面**：`pet/menu_templates/modern-default-v1.json` 与 `tests/test_menu_layout.py`
  （默认节点表/渲染表）、`tests/test_desktop_pet_features.py`（标签清单）、
  `tests/test_settings_interaction_tabs.py`（标签契约）——当晚与 #172 / #228 在同几处撞车，
  按合并提交里的并序结论为准。**免打扰（#208）与本改动无共享代码**：天气气泡是用户主动
  查询的应答，走既有 `show_bubble` **直发**；免打扰刻意不拦直发气泡（与自言自语、联动状态
  气泡同一口径，见 `window_alerts.quiet_blocked` 的 docstring），被拦的只有普通提醒。
  **天气气泡不受免打扰影响，这是设计意图。**
- **分支状态**：本提交经 `bc34ac5` 并入 `integration/2026-10-07-night-batch`；
  分支未 push、PR 未开。


## 九、终审修复对齐（2026-10-07 追加）

> 按 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) 的「后续轮次在同一文档追加新章节、
> 保留新旧对照，不要重写覆盖」约定**追加**：上文记录的是各提交当时的树，本节只记终审修复
> 带来的增量。上文对应位置已就地加注「2026-10-07 终审修复对齐（提交 `<sha>`）」。

### 9.1 §2 修改文件说明的增量（`9d922d6`）

| 文件 | 本批增量 | 要点 |
|---|---|---|
| `pet/weather.py` | +253 / −67 | ① `normalize_city_name` **改为只做可逆清洗**（NFKC / 空白 / 长度），**不再剥行政区后缀**；② 新增查询侧 `strip_city_suffix` / `city_name_variants`（**变体必须精确命中**，且不回写存储）；③ 新增 `read_bounded`（见 9.3）；④ 地区码直取路径 |
| `pet/weather_menu.py` | +88 / −22 | 添加城市时把候选**地区码**连同显示名一起存进 `weather_city_codes`；同名候选才附「朝阳 · 辽宁」式地区后缀；对话框监听 `textEdited`，一改输入就作废旧候选与旧选择；删城市时同步收敛地区码 |
| `pet/weather_service.py` | +30 / −17 | **请求结算与结果呈现解耦**：bridge 槽固定走 `WeatherService._settle`，成功 / 失败 / 宿主已死 / 起线程失败**四条结束路径都释放忙门**并断开旧 bridge；宿主不在时只结算不冒泡 |
| `pet/config.py` | +17 / −4 | **新增第四键 `weather_city_codes`**（默认值 + reload 白名单 + `set()` 归一化 + 快照四处登记） |
| `pet/settings_weather.py` | +20 / −5 | 三键子宠页置灰（见 9.4） |

**由此推翻的两处上文口径**：

1. **§3.2 真值表「城市名带后缀（鹿城区）」一行**：上文写「源 A 原名搜不到 → 用**归一化名**
   重搜；取数侧也对存量值试两个变体」。现行口径是**存储层不再改写城市名**（上文那套
   归一化每次整表跑都会再剥一层：`景德镇市 → 景德镇 → 景德`，于是"改一个跟天气无关的设置"
   也会继续改坏城市名，`新乡`/`景德镇` 这类真名还被当「乡」「镇」后缀裁掉）；后缀容错只
   发生在**查询侧**，且变体**必须精确命中**（否则「新乡」搜不到时会用「新」把「新余」顶上来）。
2. **§3.2 真值表「宿主窗口已销毁」一行**：上文写「丢弃，不崩」。现行口径是**结算与呈现解耦**
   ——宿主不在时只结算不冒泡，但**忙门必须解开**（否则换新宿主再点会一直没反应，属
   「忙门永锁」）。

### 9.2 §3.2 失败口径真值表的增量

| 场景 | 现行代码路径 | 用户看到 |
|---|---|---|
| 城市名带后缀 / 是真名（`鹿城区` / `新乡` / `景德镇`） | **存储不变**；查询侧先按原名、再试剥后缀变体，**变体必须精确命中** | 正常出「鹿城 …」；`新乡` 不会被裁成「新」 |
| 同名城市（`朝阳` 北京 / 辽宁） | 添加时存**地区码**（`weather_city_codes`），取数**按码直取**（一跳，不进检索接口），码失效才回落检索 | "选哪项中哪项"，候选重名时显示「朝阳 · 辽宁」 |
| 输入改动后旧候选 | 对话框监听 `textEdited`，一改输入即清旧候选与旧选择 | 不再出现"搜北京后改成上海、却把北京加进去" |
| 宿主窗口已销毁 | bridge 槽走 `_settle`：**结算（释放忙门 + 断开旧 bridge）但不冒泡** | 不崩、不静默卡死；换新宿主后再点照常响应 |
| 预算耗尽 / 响应体过大 | `read_bounded`：**分块读，每块前复查截止时间 + 2MB 体积上限** | 按超时失败（原因带「请求超时」）；超大响应体被截断为失败而不是读爆内存 |

### 9.3 §7 已知限制与后续的增量

- **新增**：**「15s 预算是软上限」**——`read_bounded` 把体积封在 2MB、每块前复查截止，
  但**墙钟 = 预算 + 至多一次 recv 阻塞**（已在 `weather.py` 模块头如实写明）。上文 §4 只写
  「单请求超时 6s + 总预算 15s」，没有这层口径。
- **新增**：城市名的**存储值不再被归一化改写**（后缀剥除只在查询侧）；存量配置里被旧实现
  改坏过的城市名**不会被自动修复**，需要用户重选一次城市。
- §7 第 2 条（legacy 槽位下城市列表写该槽自己的配置）与第 3 条（两个默认值可一行改）**未变**。

### 9.4 §2 设置行的增量（`ddbea79`）

`pet/settings_weather.py` 另有 **+20 / −5**：天气三键（启用开关 / 当前城市 / 城市列表）
在**子宠页置灰** + tooltip「仅主桌宠可设置」。理由与免打扰同族——这些键不在
`PER_SLOT_SETTING_KEYS` 里（是进程级/全局语义，不是逐宠偏好），子宠设置进程写的是
`config-slot-N.json` 而运行期读主配置，原先"能保存、运行时不消费"是静默死开关。
收口函数是新增的 `settings_widgets.mark_main_pet_only()`（主宠页一个不动、幂等）。

### 9.5 §6 测试与验证的增量

`9d922d6` 共 **+646 / −139**，其中四个既有测试文件净增约 **+369 / −42**
（`test_weather.py` +181/−16、`test_weather_menu.py` +86/−15、`test_weather_service.py` +68/−4、
`test_weather_settings.py` +34/−2、`test_config_schema.py` +62/−7）。新增/改写约 30 条：
幂等与真名保护、变体精确命中、地区码身份、删城市清码、编辑输入作废候选、宿主销毁后仍能
再发起、起线程失败结算、有界读取的体积与截止。上文 §6 的红→绿切片与聚焦计数（285/4532）
**因此过期**。
