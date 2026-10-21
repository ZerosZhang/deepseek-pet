# issue #220：设置页「恢复默认设置」入口（整体重置）

> **基线**：`ee699c7`（Merge PR #233 from MerZlin/feature/agent-link-subtraction）
> **分支**：`feature/issue-220-reset-defaults`（已并入 `integration/2026-10-07-night-batch`）
> **提交**：`b9c0b31`　**日期**：2026-10-07
> **范围**：6 个文件（实现 3、测试 2、文档 1），`+523 / −3`（含两个新文件）
> **状态**：分支未 push、PR 未开；本批六分支整合终全量 **4413 passed, 11 skipped**
> （`integration/2026-10-07-night-batch`，2026-10-07）
> **关联**：issue #220（设置页一键恢复出厂）；
> 设置变更准入/准出见 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)；
> 报告体裁与必备章节见 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；
> 本文已登记在 [`INDEX.md`](INDEX.md) 的「PR 报告存档」。

## 一、核心特性

设置被改坏（宠物跑到屏幕外、透明度调成看不见、误开鼠标穿透/锁位）之后，用户此前
**没有任何回到出厂状态的手段**——只能卸载重装或手改 `config.json`。本批在设置页
侧栏底部加一个常驻命令「恢复默认设置」：二次确认后把**全部持久化偏好**一次性恢复
出厂默认，并关窗让运行中的桌宠立即应用。

唯一例外的保留集是 **AI 对话密钥**：`api_key` / `vision_api_key` 是明文凭据
（keyring 不可用时**只存在于内存**，重置清掉 = 当场失凭据），两个 `*_ref` 是指向
系统钥匙串的引用（丢了钥匙串里有 key 也取不回）。依据是读 `pet/chat/models.py`
的 `ProviderConfig`（唯一 provider 字段表）确认 chat 域里带凭据语义的只有这四个。

**"恢复默认"必须是可测量的，不能是"看起来生效了"**：本批实现的一条铁律是
**默认值只有一份**（`Config._initial_data()`，与首次启动同一个字面量），因此
"重置后"与"全新安装"逐字节等价——这一点用机器验证过：改动前的 156 行字面量块与
新函数体逐行 `identical: True`，且改动前后空目录 `Config().data` 的 JSON（129 键）
**完全相同**。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 侧栏常驻入口「恢复默认设置」 | 与既有「一键退出子肥鱼」同层级（**命令而非 `SettingRow`**，故不进设置页搜索索引；按钮常驻可见，可发现性不受影响） |
| 2 | 二次确认框逐项写明 | 「保留：AI 对话密钥——各服务商的 API Key 与视觉模型 Key（系统钥匙串里的条目不会删除）」+「其余设置……都会恢复出厂默认」+「设置窗口将随即关闭，桌宠立即应用默认设置」+ 标「不可撤销」；**默认按钮 = 取消** |
| 3 | `Config.reset_to_defaults()` | 快照密钥 → `self.data = self._initial_data()` → 按 provider 归位回填保留集 → `save()` 原子写**一次**落盘；写失败整体回滚内存并返回 `False` |
| 4 | 关窗不再回写旧值 | 新增 `_close_after_external_write()`：置 `_saved_via_button` 后 `accept()`，跳过关闭路径的整表写回 |
| 5 | 运行中桌宠即时反映 | 不另造刷新：重置只做一次 `save()`，主进程走既有 config watcher → `reload()` + `_apply_external_config_change()`；子宠 slot 走既有 slot 签名 watcher |

**红线 / 不变量**：
- **默认值只有一份**：`_initial_data()` 是唯一字面量来源，`__init__` 与
  `reset_to_defaults()` 共用它——任何"再抄一份默认值"的改法都会让两者漂移；
- **从不触碰 `SecretStore`**：重置不删钥匙串条目（有测试用**抛异常的
  `SecretStore.set` 探针**证明它一次都没被调用）；
- **落盘用既有原子写路径**：临时文件 + `atomic_replace_with_retry`，主进程
  config watcher 看到的要么是重置前、要么是重置后的完整文件，**没有中间态**；
- **写失败不留错位**：内存整体回滚（`self.data = previous`），不会出现"内存已是
  默认、磁盘还是旧值"；
- **不新增任何配置键**：键集合仍是 129 + 白名单不变（`test_config_schema.py`
  的 `RELOAD_WHITELIST_SNAPSHOT` 无需同步）。

## 二、修改文件说明

`git diff --numstat ee699c7 b9c0b31`：6 个文件，`+523 / −3`，其中两个是**新增文件**。

### 实现

> *〔2026-10-07 终审修复对齐（`4ae35de`）：本表 **2 行**已被修订——`pet/settings_reset_defaults.py`
> （105 → 175 行）与 `pet/config.py`（`chat_secret_carryover` 语义 + 位置三键 null 采纳），
> 并新增 `app.py` / `overlay_shell.py` / `overlay_settings_command.py` / `window.py` 的接线，
> 见 §9.1〕*

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/config.py` | +71 / −3 | ① `__init__` 里的 `self.data = {…}` 默认值字面量**提为** `Config._initial_data()`（**逐字节纯搬运**：改动前的 156 行块与新函数体逐行 `identical: True`），`__init__` 改为 `self.data = self._initial_data(); self.reload(); self._normalize_pet_settings()`——重置必须与首次启动共用同一份默认值，否则两份字面量迟早漂移；② 新增 `CHAT_SECRET_FIELDS` + 模块级纯函数 `chat_secret_carryover(chat)`（提取密钥类字段，含空值过滤，只回填**重置后仍存在的 provider id**）；③ 新增 `Config.reset_to_defaults()`（与 `reload()` 并排）：快照密钥 → `self.data = self._initial_data()` → 归位回填 → `save()`；`save()` 返回假时 `self.data = previous` 整体回滚并返回 `False` |
| `pet/settings_reset_defaults.py`（**新**，105 行） | +105 / −0 | 按钮 / 确认框 / 重置执行全在这里（与 `settings_music`、`settings_file_interpret` 同规：主对话框只留接线，**因为它有行数预算**）。对外四个入口：`create_reset_button(host, layout)`、`build_reset_confirm_box(parent)`（**不 exec**，供文案断言）、`confirm_reset(parent)`、`on_reset_clicked(host)` |
| `pet/modern_settings_dialog.py` | +13 / −0 | 只加接线：import 1 行、侧栏按钮构造 3 行（在 `sidebar_layout.addWidget(self.sidebar, 1)` 之后、版本号 footer 之前）、`_close_after_external_write()` 方法 7 行——flag 语义留在对话框内，新模块**不直接戳字段** |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_settings_reset_defaults.py`（**新**，321 行） | +321 / −0 | 10 条聚焦测试：`test_reset_restores_every_non_secret_key_to_defaults`（逐键比对全部非密钥键）、`test_reset_does_not_touch_keyring_and_drops_extra_providers`（**抛异常的 `SecretStore.set` 探针** + 自定义 provider 条目被重置）、`test_reset_result_survives_reload`（round trip）、`test_reset_writes_through_atomic_replace`（落盘路径探针）、`test_reset_write_failure_rolls_back_memory`、`test_reset_button_confirm_applies_defaults_and_skips_stale_writeback`（关窗闸门）、`test_reset_button_cancel_has_zero_side_effect`、`test_reset_button_reports_write_failure_instead_of_closing`、`test_reset_confirm_box_copy_states_kept_items_and_irreversibility`、`test_reset_button_is_reachable_and_unclipped_at_minimum_window_size` |
| `tests/test_architecture.py` | +5 / −0 | 行数预算变动日志：本文件净 +13，**实测恰为上限 2407**（**未上调预算**，按该文件"只随实测校准"的约定；并注明"若与其它在飞分支叠加越线，按先例带日期注释校准"）。该注释块在整合分支由 `28005ba` 按实测校准为 **2415**（#220 +13、#219、service 三分支叠加的实测值） |

### 文档

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `CONTEXT.md` | +8 / −0 | 收录 **Settings Reset** 术语（`SETTINGS-CHANGE-GATES` §5 要求改 Settings System 时同步；沿用该文件 glossary 体例），并写明 `_Avoid_`: Per-page reset, credential reset |

### 未改动（看起来相关但故意没动）

| 文件 | 为什么不动 |
|---|---|
| `pet/settings_music.py`、`pet/settings_file_interpret.py` | 同族的"设置页子模块"先例，本批照它们的形态新建 `settings_reset_defaults.py`，不改它们 |
| 设置页各分页 / `SettingRow` 注册表 | 「恢复默认」是**命令**（侧栏按钮）而不是偏好项，不进域页、不进搜索索引；**不做按分页重置**（issue 范围是整体重置） |
| `pet/chat/models.py`、`SecretStore` | 只**读**它的字段表来定保留集，不新增/删除凭据接口；重置路径明确不触碰钥匙串 |
| QSS / 主题文件 | 按钮复用既有 `QPushButton` token 与 `retry` 语义图标，**未改任何颜色 / 容器 / QSS** |

## 三、实现要点

1. **默认值只有一份，且这一条是"机器可验证的"**。重置最容易出的错是"又抄一份
   默认值"——两份字面量今天相同、三个月后必然漂移。做法是把字面量提成
   `_initial_data()`，`__init__` 与 `reset_to_defaults()` 共用。验证是两条：
   `git show HEAD~1:pet/config.py` 的原块与新函数体**逐行 identical**；
   改动前后空目录 `Config().data` 的 JSON（129 键）**完全相同**。
2. **保留集按 provider 归位，而不是整块保留 chat 域**。只回填**重置后仍存在的
   provider id**（默认集里就是 `openai-main`）：自定义 provider 的条目会被重置掉，
   而它的 keyring 条目是外部状态、本方法从不触碰——**密钥没丢，只是配置不再引用
   它**。这条语义由「抛异常的 `SecretStore.set` 探针」钉死（探针一旦被调用即失败）。
3. **落盘复用既有原子写，不另造一条写路径**。`reset_to_defaults()` 只调一次
   `save()`，因此脱敏、临时文件命名、`atomic_replace_with_retry`、重试全部走既有
   代码。探针（"包一层仍调真实实现"）断言：重置只触发 **1 次**
   `atomic_replace_with_retry`、target == `config.json`、temp 名 ==
   `config.json.<pid>.tmp`、temp 已删（#194 口径）。
4. **关窗闸门是本批最容易被漏掉的一处**——它不是防御性代码，是**功能成立的前提**。
   设置对话框的关闭路径（`reject()`/关闭按钮）默认会把控件里的值**整表写回**；重置
   已经在窗口外落盘，而控件里持有的仍是重置前的旧值 —— 照常写回就会**静默覆盖掉
   刚写下的默认值**，用户看到"点了重置、重启后又变回来了"。做法是
   `_close_after_external_write()` 置 `_saved_via_button` + `accept()`，flag 语义
   留在对话框内（新模块不直接戳字段）。**这一条有消融证据**（见第六节）。
5. **不做按分页重置是有意的**：整体重置的失败模式可控（一次原子写、可回滚），
   而"每页各自重置"会让"我到底重置了哪些页"变成用户心智负担，也把保留集的判定
   拆散到多个入口。issue 只要整体重置。
6. **需产品 owner 确认的两个语义决策**（按 issue 原文实现，改法都很小）：
   - 只保留密钥字段、**自定义服务商条目会重置**（中转站用户重置后要重填
     `base_url`/模型；钥匙串里的 key 不会删，重建 provider 仍可能自动取回）。
     若要连服务商条目一起保留，改 `chat_secret_carryover` 的返回内容即可；
   - **用户自撰内容一并重置**：自定义台词（`dialogue_phrases`）、角色别名
     （`character_aliases`）、点击绑定台词（`character_profiles`）、快捷启动列表、
     形象（`character`）、位置 `rx/ry`（对"桌宠跑到屏幕外"正好是救济）。确认文案已
     逐项写明并标"不可撤销"。
   - 附带语义：子宠 `user_customized` 回 `False` → 该 slot 之后跟随主配置刷新
     （默认行为），已在代码注释与本节注明。

## 四、性能分析

**方法（可复现）**：探针脚本（一次性，跑完删除，未入库）以
`QT_QPA_PLATFORM=offscreen python <probe>.py` 在本机运行，`APPDATA` 指向 scratch
目录（不碰用户真实配置目录）；落盘路径断言"包一层仍调真实实现"，
`atomic_replace_with_retry` 调用次数由包层计数。
环境：Windows 10 x64 / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属 |
|---|---|---|
| 重置落盘次数 | **1 次** `atomic_replace_with_retry`，target = `config.json`，temp = `config.json.<pid>.tmp`，temp 已删 | 新增（复用既有原子写） |
| `Config._initial_data()` 单次成本 | 构造一个 129 键的嵌套 dict 字面量（纯 Python 常量，无 IO）；**首次启动本来就付这份成本**，重置只是第二次调用 | 既有（纯搬运） |
| `reset_to_defaults()` 额外成本 | 一次 `chat_secret_carryover()`（遍历 ≤ provider 数 × 4 个字段名）+ 一次 `save()` | 新增 |
| 稳态开销（桌宠运行期） | **零变化**：本改动只在用户点击「恢复默认设置」时执行；没有新增定时器、轮询、线程或缓存 | 零 |
| 设置对话框构造 +13 行接线 | 一个 `QPushButton` 创建（与既有侧栏按钮同构），相对同一次对话框构造可忽略 | 新增（一次性） |
| 内存 | 无增长：无新增缓存或长驻容器；`_initial_data()` 每次调用**新建**一份 dict（不复用 `self.data`，避免别名污染），随即用即弃 | 新增 |
| 系统调用 / 网络 / 磁盘 / 线程 | **新增：0**。唯一的磁盘动作是重置时的 1 次原子写（用户手动触发的离散动作） | 零 |

**结论**（逐条回答）：

1. **稳态开销有没有变化**：没有。改动全部落在"用户点按钮"这一条路径上；桌宠待机
   / 移动 / 播放的任意热路径上一行代码都没变（本提交不触及任何 tick / 渲染 / 物理
   路径）。
2. **新增路径的绝对成本与触发频率**：绝对成本 = 一次 dict 字面量构造 + 一次原子写
   （毫秒级，取决于磁盘）；触发频率 = **用户手动点击**（低频、离散）。
3. **有没有引入新的系统调用 / 网络 / 磁盘 / 线程**：磁盘 = 重置时 1 次原子写
   （既有的 `atomic_replace_with_retry` 路径）；系统调用 = 该写的固有配套；**网络 0、
   新线程 0、定时器 0**。
4. **内存与缓存有没有增长**：无长驻增长；`_initial_data()` 新建的 dict 在 `save()`
   后被 `self.data` 持有（这就是配置本身，不是额外缓存），失败路径下被 `previous`
   替换后由 GC 回收。

## 五、实机运行记录

> *〔2026-10-07 终审修复对齐（`4ae35de`）：本节引用的二次确认文案**原文已过期**
> （「自定义服务商条目…都会恢复出厂默认」不再准确），现行文案见 §9.2〕*

本机：Windows 10 x64，真实开发机（非 CI、非 mock）。用一次性探针（跑完已删，
未进仓库）在本机 `APPDATA` 指向 scratch 目录下执行：

1. **真实入口起得来**：`python -m pet --settings`（真实设置进程入口）→
   `settings.lock` 出现，进程带新模块构建成功；随后收掉自己起的进程
   （确认无残留进程）。
2. **真实控件 + "改坏"的存档**：真实 `ModernSettingsDialog(standalone=True)` 加载
   一份改坏的存档（`rx/ry=-4000`、`pet_opacity=10`、
   `mouse_through/lock_position/self_talk_enabled=True`、自定义提示词、已配置 key）
   后点击侧栏按钮，原始输出：

   ```text
   用户看到的二次确认文案：
    | 将重置全部设置为默认值（不可撤销）。
    | 保留：AI 对话密钥——各服务商的 API Key 与视觉模型 Key（系统钥匙串里的条目不会删除）。
    | 其余设置（自定义服务商条目、形象、系统提示词、自定义台词与角色别名、外观与功能开关等）都会恢复出厂默认。
    | 设置窗口将随即关闭，桌宠立即应用默认设置。
    | 按钮：[恢复默认设置] / [取消]   默认按钮=取消
   对话框 result=1（Accepted），已关窗
   磁盘 diff：rx: -4000 -> None / pet_opacity: 10 -> 100 / mouse_through: True -> False
             lock_position: True -> False / self_talk_enabled: True -> False
   chat.default_system_prompt: '被改坏的提示词' -> '你是一只可爱的桌面宠物，'
   保留项：内存 api_key='sk-real-probe'（明文不落盘）× 磁盘 api_key_ref='provider/openai-main'
   主进程 reload 后：pet_opacity=100 mouse_through=False rx=None   ← 「运行中 UI 即时反映默认值」
   ```

3. **生效链路未自造刷新**（可核查的设计事实）：重置只做一次 `save()`，主进程走既有
   config watcher → `reload()` + `_apply_external_config_change()`；子宠 slot 走既有
   slot 签名 watcher（与普通保存同一条）。窗口关闭后由 `_modern_settings_finished`
   触发同一条应用链（`accept()` 路径已被既有代码覆盖）。
4. **边界与失败路径**：
   - **取消 = 零副作用**（`test_reset_button_cancel_has_zero_side_effect`）；
   - **写失败不关窗、不撒谎**：落盘失败时按钮入口**报错并且不关闭对话框**
     （`test_reset_button_reports_write_failure_instead_of_closing`），内存回滚到
     重置前（`test_reset_write_failure_rolls_back_memory`）；
   - **最小窗口尺寸下按钮可达且不被裁**（`test_reset_button_is_reachable_and_unclipped_at_minimum_window_size`）。
5. **无法自动验证的能力（如实登记）**：
   - **未做真实 GUI 截图验收**（只跑了 offscreen）。`desktop-pet-ui-style` SKILL 的
     截图证据需要真实 GUI 会话，`scripts/capture_settings_pages.py` 本轮未跑；
     同时**未改任何颜色/容器/QSS**（按钮复用既有 token），故"明暗双态截图"这条按
     不适用处理。
   - 未在真机上验证"重置后立刻重启桌宠，位置与透明度确实回到出厂"这条端到端链路
     ——已验的是"重置 → 磁盘 → 主进程 reload 后内存值正确"（第 2 条最后一行）。

## 六、测试与验证

> *〔2026-10-07 终审修复对齐（`4ae35de`）：聚焦 21 条新增/改写（含两条消融可复现的回归）；
> 另本表一处数字过期——快照键集合现为 **139 + 5 = 144**（非 129），详见 §9.3〕*

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | `All checks passed!` |
| 空白检查 | `git diff --check` | clean |
| 聚焦（相关族 8 文件） | `pytest -q tests/test_settings_reset_defaults.py tests/test_config_schema.py tests/test_config_reload_null.py tests/test_config_domains.py tests/test_architecture.py tests/test_settings_and_resources.py tests/test_settings_interaction_tabs.py tests/test_menu_layout.py` | **179 passed** |
| 全量（源 worktree，跑过两次） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4317 passed, 11 skipped**（9 分 53 秒；两轮均绿。注：跑测期间机器上还有另外两个 agent 的 pytest 在跑，属环境噪声，不影响结果) |
| 本批整合终全量 | `integration/2026-10-07-night-batch` | **4413 passed, 11 skipped** |
| 已有护栏 | `test_config_schema.py` 快照 | **无需同步**（未新增配置键，键集合仍是 129 + 白名单不变） |
| 已有护栏 | `test_modern_settings_dialog_py_line_budget` | 分支内 2407 ≤ 2407（零余量）；整合分支由 `28005ba` 按实测校准为 2415 |
| 已有护栏 | `test_every_setting_row_still_lives_in_a_domain_page` | 通过（该入口是侧栏命令、不是 `SettingRow`，与既有「一键退出子肥鱼」同侧栏层级） |
| 交付纪律 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr_report_discipline.py -q` | 见本文末（登记后全绿） |

**红 → 绿证据（test-first）**

- **红 1（功能不存在）**：`python -m pytest tests/test_settings_reset_defaults.py -q`
  → `ImportError: cannot import name 'settings_reset_defaults' from 'pet'`
  （**收集期报错**）。
- **红 2（消融，证明最关键那条回归不是空转）**：把 `on_reset_clicked` 里的
  `host._saved_via_button = True` 闸门临时删掉后，
  `test_reset_button_confirm_applies_defaults_and_skips_stale_writeback` 失败并给出
  **真实差异**：

  ```text
  self_talk_texts: ['自定义台词'] != [...默认 5 句]
  mouse_through: True != False
  lock_position: True != False
  context_menu_appearance: dark/compact != system/standard
  ```

  即**关窗路径确实会把旧控件值整表写回、静默回滚重置**（第三节第 4 条的实锤）；
  恢复闸门后全绿。
- **绿**：10 条测试通过（逐条见第二节测试表的测试名清单）。

**断言有效性**：红 2 就是断言有效性的证明——它用"撤掉实现后仍给出真实差异"说明
这条断言能区分"重置生效"与"被关窗写回覆盖"。落盘路径探针断言"只 1 次原子写 +
temp 已删"能区分"另造写路径"与"复用既有路径"。`SecretStore.set` 抛异常探针能区分
"不碰钥匙串"与"顺手清了钥匙串"。

## 七、已知限制与后续

1. **行数预算零余量**（分支内）：`pet/modern_settings_dialog.py` 实测**恰好 2407 =
   当轮预算**，同文件若与其它在飞分支叠加任何一行即红
   （[`PR-MERGE-LESSONS-2026-09-12.md`](PR-MERGE-LESSONS-2026-09-12.md) 教训 2 的
   组合效应）。整合分支已按先例带日期注释校准为 **2415**（`28005ba`，实测
   #220 +13 / #219 / service 三分支叠加），但**拆分仍是待办**：下一次改这个文件
   应走"继续抽模块"而不是"再抬预算"。
2. **`pet/config.py` 的 `__init__` 结构变了**（默认值字面量改由 `_initial_data()`
   提供）。字面量内容逐行未动，但任何同时改 `__init__` 默认值区的分支都会冲突——
   解冲突时**务必保住"默认值只有一份"**这条约束（`reset_to_defaults` 依赖它）。
3. **设置页搜索索引只覆盖 `SettingRow`**：搜"恢复默认"会显示"未找到匹配的设置"。
   按钮本身常驻侧栏可见，不影响可发现性；若要把命令也纳入搜索，属设置系统层面的
   另一件事（非本批）。
4. **暗色 QSS 的通用 `QPushButton` 没有 `:focus` 规则**：键盘焦点依赖 Qt 默认提示。
   同对话框里其它普通按钮（如「一键退出…」）情况相同，属既有缺口；要统一修应在
   QSS 层单独一批做（**不是本改动引入**）。
5. **两个语义决策仍待产品 owner 确认**（第三节第 6 条）：自定义服务商条目会重置、
   用户自撰内容（台词/别名/形象/位置）一并重置。
   *〔2026-10-07 终审修复对齐（`4ae35de`）：**前半已解**——自定义服务商的**密钥现在保留**
   （骨架回默认模板、不自动选中）；后半仍待确认。详见 §9.4〕*
6. **分支未 push、PR 未开**（见文末状态）。

## 八、风险与回滚

- **影响面**：设置页侧栏多一个按钮 + 新增一个模块 + `Config` 多一个公开方法。桌宠
  运行期的任何热路径未变；不点这个按钮的用户**零感知**。
- **用户可见变化**：设置页侧栏底部出现「恢复默认设置」；点它 → 确认框（默认取消）
  → 全量恢复出厂（保留 AI 密钥）→ 窗口关闭 → 运行中的桌宠立即应用。
- **配置迁移**：**无新键、无格式变更**（键集合 129 + 白名单不变，`test_config_schema`
  快照无需同步）。唯一的行为语义是新增的"重置"动作本身。
- **回滚**：`git revert b9c0b31` 即可，**无落盘残留**——重置写出的仍是既有 schema 的
  合法配置（只是值等于默认），回滚后这些值照常被读取；无缓存格式变化、无迁移代码、
  无外部状态（钥匙串条目从未被本改动触碰）。
- **落盘失败路径**：内存回滚 + 按钮报错不关窗，不产生"内存/磁盘错位"的半状态。


## 九、终审修复对齐（2026-10-07 追加）

> 按 [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) 的「后续轮次在同一文档追加新章节、
> 保留新旧对照，不要重写覆盖」约定**追加**：上文记录的是各提交当时的树，本节只记终审修复
> 带来的增量。上文对应位置已就地加注「2026-10-07 终审修复对齐（提交 `<sha>`）」。
> （本文属更早一批交付；本节由后续的口径对齐批补写。）

### 9.1 §2 修改文件说明的增量（`4ae35de`）

| 文件 | 增量 | 要点 |
|---|---|---|
| `pet/settings_reset_defaults.py` | +79 / −9（105 → **175** 行） | 重置执行链补两条：**运行态对齐**（`_request_runtime_alignment`）与**系统登录项收敛**（`sync_system_autostart`） |
| `pet/config.py` | +40 / −13 | `chat_secret_carryover` 增加 `name` 采集（供非默认 provider 重建骨架名）；位置三键加入 reload 的 **null 采纳白名单** |
| `pet/app.py` | +46 / −0 | 进程内路径的重置级运行态对齐 + `CMD_APPLY_SETTINGS_RESET` 的消费 |
| `pet/overlay_shell.py` | +29 / −2 | overlay 拓扑的同款消费 |
| `pet/overlay_settings_command.py` | +10 / −2 | 新增 `CMD_APPLY_SETTINGS_RESET` 指令 |
| `pet/window.py` | +2 / −0 | 传给设置页的窗回调 |
| `CONTEXT.md` | +7 / −3 | 术语补充（重置的保留集与运行态口径） |
| `tests/test_settings_reset_defaults.py` | +365 / −14 | 含两条**消融可复现**的回归（见 §9.3） |

**两处「承诺与行为不符」的收口**（都推翻上文口径）：

1. **自定义服务商的密钥原本会在重置后丢失**。上文 §3 第 2 条写「保留集按 provider 归位，只
   回填**重置后仍存在的** provider id」——非默认 provider 的条目于是被整个重置掉，而 keyring
   不可用时明文**只存在内存里**：条目一没了，密钥**永久丢失**，可确认文案却承诺「保留 AI 对话
   密钥」。现行：默认集里的 provider 只回填**凭据字段**；**非默认 provider 重建一个
   「只装凭据」的最小条目**（显示名 + 密钥字段），地址/模型等骨架按重置口径回默认模板，且
   **不会被自动选中**（`active_provider` 回默认那个）；**keyring 条目始终不动**。
2. **重置后的运行态不完整**（上文未覆盖）。位置键写成 `null` 表达「没有位置记忆」，但
   **运行中的窗口不会自己动**，正常退出时 `save_position()` 把重置前的旧位置**写回磁盘**
   ⇒ 重置被**静默抵消**；系统登录项也没跟着收敛。现行：重置成功后走一次**「重置级运行态
   对齐」**——用既有的「回到右下角」把这一只落回默认位置并落盘（顺带取消在途移动/物理），
   再按新值收敛系统登录项。落点**刻意不读配置里的 `rx`/`ry`**：本方法可能由跨进程指令驱动，
   指令与主进程去抖中的外部 reload 是**两条时序**。触发与「一键退出子肥鱼」同规：进程内
   设置页直接调窗回调，独立设置进程走 **D12 指令通道**（新增 `CMD_APPLY_SETTINGS_RESET`，
   两个拓扑各消费一次）。

### 9.2 §5 实机运行记录的增量（确认文案已改）

上文 §5 引用的二次确认文案原文**已过期**（:170-172）。现行文案：

```text
保留：AI 对话密钥——各服务商的 API Key 与视觉模型 Key；自定义服务商只留一个
      只装密钥的条目，密钥不会丢（系统钥匙串里的条目也不会删除）。
位置立即回默认落位、开机自启按默认关闭；形象与素材类设置需重启后生效。
```

即「其余设置（**自定义服务商条目**、形象、…）都会恢复出厂默认」这句里的**自定义服务商条目**
已不再准确——它改为「骨架回默认模板、密钥条目保留、且不自动选中」。

### 9.3 §6 测试与验证的增量

- 聚焦 **21 条**新增/改写（`tests/test_settings_reset_defaults.py` +365/−14）。两条**消融可
  复现**的回归：① 去掉凭据容器 → 自定义 provider 凭据丢失；② 去掉运行态对齐 → **磁盘写回
  重置前的旧位置 `0.42`** 而不是默认落位 **`0.93`**。第 ② 条正是 §9.1 第 2 点的实锤。
- **一处数字修正**（非 `4ae35de` 引入，属本批顺手对齐）：§6 表内「`test_config_schema.py`
  快照 → 键集合仍是 **129** + 白名单不变」是当轮旧值；集成分支当前实测
  **白名单 139 + 特例 5 = 144**。结论（**无需同步快照**）不变——`4ae35de` 本身**未新增
  配置键**，只把**既有**位置三键加进 null 采纳白名单——要改的只有那个数字。

### 9.4 §7 已知限制与后续的增量

- **第 5 条应读作「一个已解、一个待确认」**：前半「**自定义服务商条目会重置**」已被
  `4ae35de` 改掉——自定义服务商的**密钥现在保留**（骨架回默认模板、不自动选中）；后半
  「用户自撰内容（台词/别名/形象/位置）一并重置」**仍待产品 owner 确认**。
- **新增**：**重置会立即改运行态**（位置落回默认、系统登录项按新值收敛），不再是"只改配置、
  重启才见效"；代价是重置会**取消在途的移动/物理**（同「回到右下角」的既有语义）。
- 第 1 条（行数预算）与第 2 条（`_initial_data()` 结构的合并注意点）**未变**。
