# 旧版右键菜单全量退役 + 清理（2026-10-08）

> **基线**：`6021fc4`（分支 `release/2026-10-08-candidate`）
> **分支**：`release/2026-10-08-candidate`　**日期**：2026-10-08
> **范围**：45 个文件（实现 20、脚本 1、测试 16、文档 8；净 `+1048 / −1042`，含删除 4 个文件、新增 1 个文档）
> **关联**：[`SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md`](SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md)（菜单迁移决定）、
> [`PR-REPORT-OVERLAY-MENU-PARITY-2026-09-24.md`](PR-REPORT-OVERLAY-MENU-PARITY-2026-09-24.md)（模板分发与 facade parity 的上游报告）、
> [`CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md`](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md)（双模板的来源）

## 发布说明（可直接引用）

> **旧版右键菜单已移除**；原选择旧版的用户将自动使用新版菜单，功能为旧版超集。

不弹窗、不报错、不需要用户重新设置：旧存档里的菜单模板键会被静默丢弃，下一次保存后
从 `config.json` 中消失。

## 一、核心特性

右键菜单过去有两套实现：现代树（动作注册表 + 用户编排 + 图标分组）与旧版扁平树
（`legacy.py` 手写布局），由配置键 `context_menu_template` 决定走哪一套，菜单里还有
一条「切换菜单模板」项。本次把旧版整层删除：**菜单只剩现代树**，两套建造器的分发、
模板装载、模板切换、配置键全部退役；`overlay` 侧（多宠合成窗）与窗口侧共用同一个
建造器。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 旧版菜单实现删除 | `pet/context_menus/legacy.py`（117 行）、`menu_styles/legacy.py`（13 行）、`menu_templates/{legacy,modern}.json`（各 15 行）整文件删除 |
| 2 | 模板分发机制删除 | `context_menu.py` 的 `TEMPLATE_IDS` / `_FALLBACK_TEMPLATES` / `load_menu_template` / `normalize_template_id` 与 legacy 分支；`build_modern_menu` 去掉无人使用的 `template` 参数 |
| 3 | 配置键退役 + 静默迁移 | `context_menu_template` 从 defaults / reload 白名单 / 脏值归一化 / 设置页 / 默认值标记 / 搜索别名全部删除；`Config._migrate_menu_template_config()` 在读盘路径丢弃旧值 |
| 4 | 死槽清理 | `on_open_legacy_settings`（恒为 None 的槽位）与 `on_open_modern_chat`（全仓 0 赋值）整条删除 |
| 5 | 防复活守卫 | `tests/test_architecture.py` 三层机器化守卫：退役文件不存在 / pet/ 树零退役符号 / 退役键只许出现在迁移函数里 |
| 6 | 样式继承修正 | `inherit_menu_style` 默认值原指向已删的旧版样式——父菜单属性没设上时子菜单会**静默掉样式**，改为恒落现代分支 |

**红线 / 不变量**：

- 菜单条目**一项都不能少**（除两条有记录的去向）：退役后现代树覆盖退役前旧版树的
  全部标签，见第五节「超集核对」；
- 旧配置**不许报错**：任何模板值（`legacy` / `modern` / 脏值）都只是被丢弃；
- 「AI 设置」**不许复活成独立菜单项**：它按
  [`SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md`](SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md)
  402/428 行的既定决定并入「桌宠设置 → AI 与对话」，机器化钉在
  `tests/test_sprite_menu_parity.py::test_ai_settings_stays_merged_into_pet_settings_entry`；
- 用户自己编排过的 `context_menu_layout` **不动**（退役的是模板，不是编排）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/context_menus/legacy.py` | +0 / −117 | **整文件删除**。旧版扁平建造器，唯一调用方是 `context_menu.populate_context_menu` 的 legacy 分支与 facade 的同款分支（两者都已删） |
| `pet/context_menus/menu_styles/legacy.py` | +0 / −13 | **整文件删除**。旧版菜单外观（原生系统样式），消费者 `apply_legacy_menu_style` 只剩 `inherit_menu_style` 的 else 分支 |
| `pet/menu_templates/legacy.json` | +0 / −15 | **整文件删除**。旧版模板数据，没有读者 |
| `pet/menu_templates/modern.json` | +0 / −15 | **整文件删除**。它的 `groups` 早就是死数据——`build_modern_menu` 第一行就是 `del template`，真正生效的布局是 `modern-default-v1.json`（`pet/menu_layout.py`）。留着等于"看起来有两套模板，其实只有一套" |
| `pet/context_menu.py` | +7 / −81 | 分发器收成单路：删 `TEMPLATE_IDS` / `_FALLBACK_TEMPLATES` / `load_menu_template` / `normalize_template_id` / legacy 分支与模板键读取；`populate_context_menu` 只剩「现代外观 → 建树 → 勾选指示/响应式/停留交互」固定流水线 |
| `pet/context_menus/__init__.py` | +2 / −3 | 去掉 `build_legacy_menu` 导出，模块 docstring 更正（不再有"两套独立实现"） |
| `pet/context_menus/menu_styles/__init__.py` | +1 / −2 | 去掉 `apply_legacy_menu_style` 导出 |
| `pet/context_menus/modern.py` | +1 / −2 | `build_modern_menu(menu, pet, template)` → `build_modern_menu(menu, pet)`；参数本来就是 `del template` 的死参数 |
| `pet/context_menus/shared.py` | +1 / −11 | 删 `add_template_switch`（唯一调用方是已删的 legacy 建造器，全仓无消费者）；`add_proactive_menu` 里"回退 `on_open_legacy_settings`"的 `or` 链裁掉一半 |
| `pet/context_menus/menu_styles/common.py` | +15 / −15 | **本次最易漏的一处**：`inherit_menu_style` 原按父菜单 `menuStyle` 属性分支，取不到时默认值指向 `"legacy"`。旧版样式删除后这个默认值仍会把**所有继承失败的子菜单**送进已删模块（掉样式 + 原生外观）；改为恒落现代分支，并补一条"父菜单没设属性"的用例 |
| `pet/sprite_menu_facade.py` | +27 / −80 | overlay 侧单分支化：删 `set_context_menu_template`、`on_open_legacy_settings` 属性、模板分发与旧布局的「隐藏桌宠」补位（现代树里该入口由注册表 `hide_pet` 落在「桌宠控制」，再补就是同名重项）；docstring 按现状重写 |
| `pet/config.py` | +24 / −7 | 退役键收支：`_initial_data` 默认值、reload 白名单、`_normalize_pet_settings` 归一化各删一处；新增 `_migrate_menu_template_config()`（`reload()` 内调用，读旧值 → 记一次 info → `raw.pop`，口径同既有 `decode_broker_enabled` 先例）。`_normalize_pet_settings` 里那条"枚举键先 `str()` 再判成员"的防御注释保留并挪到仍在用的 `chat_ui_style` 上 |
| `pet/modern_settings_dialog.py` | +0 / −6 | 删设置页「菜单」域的「菜单版本（新版 / 旧版）」下拉（构造 4 行 + 行定义 1 行 + 保存回写 1 行）；该域只剩「菜单编排」 |
| `pet/settings_default_marks.py` | +0 / −1 | 删行键 `menu_template` → 配置键的默认值映射（行没了，映射留着会在覆盖率守卫里变成孤儿） |
| `pet/settings_search.py` | +2 / −2 | 删搜索别名「菜单模式」→ `menu_template`：设置行已不存在，别名只会空转。搜「菜单模式 / 旧版菜单 / 切换菜单」自此 0 候选（不是没搜到） |
| `pet/window.py` | +1 / −9 | 删 `set_context_menu_template`（模板切换第三个入口）与 `context_menu` 的 `normalize_template_id` 导入；`__init__` 删 `on_open_legacy_settings`、`on_open_modern_chat` 两个槽位 |
| `pet/app.py` | +0 / −4 | `_wire_window` 删"旧版设置槽位恒 None"的赋值与解释注释（旧版建造器是它唯一读方） |
| `pet/weather_menu.py` | +3 / −3 | 函数内 import 的解释注释仍指向已删的 `context_menus.legacy`，按现状改正（循环导入的理由不变） |
| `pet/context_menus/registry.py` | +6 / −6 | 仅注释：停用门"为什么落在建造器里"的理由原写成"legacy 建造器直调"，改按现状表述（理由成立、参照物已删） |
| `pet/overlay_shell.py` | +1 / −1 | 仅注释：`reopen_context_menu` 的"模板切换立即生效"改为"菜单树重建后立即生效" |
| `scripts/capture_settings_pages.py` | +0 / −12 | 截图脚本的「菜单模式下拉」截图块删除（控件已不存在，跑起来必抛 `AttributeError`） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_architecture.py` | +109 / −3 | 三层防复活守卫：① 退役文件必须不存在；② pet/ 树零退役符号（函数体/字符串/注释一律算）；③ 退役键只许出现在 `config.py::_migrate_menu_template_config` 里（含 `_function_block` 辅助） |
| `tests/test_sprite_menu_parity.py` | +202 / −229 | 收成单树 parity：与真实 `PetWindow` 的现代树逐项比对、显式条目清单、聊天门/音乐门/Windows 门、点击路由、动画分组与收起；新增 `test_ai_settings_stays_merged_into_pet_settings_entry`（钉死"AI 设置不复活"） |
| `tests/test_desktop_pet_features.py` | +160 / −253 | 旧版分发/样式/回退三例改为单模板用例；`test_context_menu_runtime_only_dispatches_modern_layout`（源码断言旧版建造器存在）改由架构守卫统一承担；新增子菜单样式继承用例；设置入口用例收成单模板 |
| `tests/test_config_schema.py` | +38 / −6 | 白名单快照去掉退役键；枚举脏值用例只留 `chat_ui_style`；新增 3 例迁移（主配置静默丢弃 / 不写回 / slot 配置丢弃） |
| `tests/test_menu_layout.py` | +14 / −7 | 删「切到旧版并落盘」用例，改为"设置页不再有菜单版本控件 + 保存不写回该键"；`build_modern_menu` 调用点去掉空模板参数 |
| `tests/test_quiet_mode.py` | +8 / −10 | 「两种模板都有免打扰入口」参数化用例收成单树，并删旧版专属的子菜单用例 |
| `tests/test_weather_menu.py` | +11 / −14 | 旧版建造器两例改写为现代树两例（置灰门必须落在共享建造器的证据保留） |
| `tests/test_memory_trim.py` | +6 / −8 | 旧版菜单的平台门用例改写为**共享建造器**直调用例（平台门不只在注册表） |
| `tests/test_effects_integration.py` | +2 / −19 | 删旧版菜单的黄金回旋/边缘探头用例（现代树同款用例已在同文件）；测试替身去掉 `template` 参数与退役键 |
| `tests/test_requested_regressions.py` | +13 / −12 | 「旧版菜单开机自启落盘」改写为现代树用例；打包脚本用例的兜底断言从 `load_menu_template` 改为 `load_menu_layout.load_default_menu_layout()` |
| `tests/test_harness_lifecycle.py` | +17 / −10 | 「轻量构建隐藏 Harness」的源码断言（`inspect.getsource(build_legacy_menu)`）改为注册表可用性断言 + 共享建造器形状断言 |
| `tests/test_animation_menu_close_and_group.py` | +10 / −15 | 「legacy 与 modern 分组一致」改为现代树单树分组断言 |
| `tests/test_chat_subsystem.py` | +2 / −7 | 菜单路由用例去掉退役键与 `on_open_modern_chat` 探针、`on_open_legacy_settings` 替身 |
| `tests/test_sprite_menu_facade.py` | +9 / −11 | 能力条目用例收成单树 |
| `tests/test_sprite_menu_target.py` | +3 / −7 | `_make_shell` 去掉 `template` 参数与配置写入 |
| `tests/test_menu_tree_release.py` | +1 / −2 | 壳装配去掉退役键写入 |
| `tests/test_settings_page_guide.py` | +2 / −2 | 「定稿措辞」表与「旧词可搜」表去掉菜单版本行（行被删除而非改名，旧词别名同步从 `settings_search` 移除） |

### 文档

| 文件 | 改动意图 |
|---|---|
| `README.md` | 三处「一键回到旧版 / 可切换新旧模板」表述失实（现代树本就没有切换项，是 Q6/Q7 有意设计）改为如实描述；目录树注释与「旧版菜单也同步提供」旧句更正 |
| `docs/PR-REPORT-LEGACY-MENU-RETIREMENT-2026-10-08.md` | 本报告（新增） |
| `docs/INDEX.md` | 登记本报告；给菜单调研文档与 overlay parity 报告行加后继变更指针 |
| `docs/SETTINGS-CHANGE-GATES.md` | 按门禁要求补本条**设置删除**的变更记录（准入复核/键去向/旧入口/搜索别名/恢复路径，准出逐项对应） |
| `docs/SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md` | 两条 legacy 迁移条目标记为**已执行（2026-10-08）**；补一段说明「搜旧称 0 候选是正确行为」 |
| `docs/CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md` | 文首加「双模板已是历史」警示（正文保持 2026-08-25 快照不改写） |
| `docs/DEV-HANDOVER.md` | 目录树注释同步；`test_architecture.py` 行数/用例数按实测校准（213/7 → 577/13，原数字本就滞后） |

### 未改动（故意）

- `pet/menu_layout.py` / `pet/menu_templates/modern-default-v1.json`：**用户编排**的
  布局与版本化 id 一律不动——本次退役的是"模板"，不是"编排"。
- `pet/settings_menu_layout_editor.py`：编排编辑器的可用动作集合来自
  `MENU_ACTIONS.ids`，删除动作会让它自动失去该项，无需改代码。
- `pet/chat/settings_dialog.py`（经典 AI 设置对话框）：**保留**，理由见第三节第 0 步裁决。
- `window.py::reopen_context_menu` / `overlay_shell.py::reopen_context_menu`：作为通用
  "菜单重建后原位重开"能力保留（有测试），见第七节。

## 三、实现要点

### 第 0 步：AI 设置入口的裁决（带证据）

任务前提是"经典 `ChatSettingsDialog` 全仓唯一入口是旧版菜单的「AI 设置」项"。
**该前提不成立**，逐条证据：

| 入口 | 位置 | 现状 |
|---|---|---|
| 旧版右键菜单「AI 设置」 | `pet/context_menus/legacy.py:60` | 随本次退役删除 |
| 托盘菜单「AI 设置」 | `pet/app.py:3790`（`add_tray_action(menu, 'AI 设置', …)`） | **活的**，不受本次改动影响 |
| 聊天授权回调 | `pet/app.py:791, 811`（`auth_callback=self.open_chat_settings`） | **活的**：聊天缺凭据时由 ChatService 唤起 |
| 窗口槽位 | `pet/app.py:517` → `sprite_menu_facade.on_open_chat_settings` | 活（现代树 `chat`/`chat_settings` 动作面） |

因此"删掉对话框 = 顺手删掉唯一入口"这条不再成立：退役对话框必须连带改托盘与授权
回调两条非菜单入口（另一条 workstream，超出"右键菜单退役"的范围）。

配置键维度的对比（真实构造两个对话框读出来的，脚本
`.scratch/legacy-menu-retirement/step0_ai_coverage.py`）：

| 经典 `ChatSettingsDialog` 覆盖 | 现代 `_AiSettingsPage`（AI 与对话域） | 结论 |
|---|---|---|
| API 列表增删切换、Provider 名称 / API 地址 / 模型 / API Key | `provider_list` / `provider_name` / `api_url` / `model` / `api_key` | 全面覆盖 |
| 视觉模型复用开关 / 视觉模型 / 视觉 API 地址 / 视觉 API Key | `vision_same` / `vision_model` / `vision_url` / `vision_key` | 全面覆盖 |
| System Prompt、超时 / Temperature / Max Tokens、跳过 SSL | `system_prompt` / `timeout` / `temperature` / `max_tokens` / `skip_ssl` | 全面覆盖 |
| 系统通知开关（`system_notifications_enabled`） | 同键同名行 | 全面覆盖 |
| 聊天背景（`chat_background`）+ 裁切取景（`chat_bg_crops`） | `chat_background` / `chat_background_file` / `chat_background_opacity` / `chat_background_fill` / `chat_bg_crops` | 覆盖且**多出**不透明度与填充方式 |
| （无） | `chat_ui_style` / `modern_chat_card_opacity` | 现代页独有 |
| 「已保存 API Key」动态状态提示（`key_hint`） | （无对应控件） | **经典对话框独有**的一块 UI affordance |

裁决：**不退役 `ChatSettingsDialog`，也不在现代树里加「AI 设置」项**。

1. 「严格超集」在功能维度不成立（缺 `key_hint` 那一条动态提示），在键维度成立——
   单纯按键判会把"可以删对话框"当成结论，而删它需要另外两条入口一起改；
2. 更重要的是本仓**已有记录在案的产品决定**：
   [`SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md`](SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md)
   402 行把「AI 设置」的去向写成"合并到『桌宠设置 → AI 与对话』｜是，**移除重复快捷入口**"，
   428 行写明"根菜单保留一个『桌宠设置』"。把 `chat_settings` 重新注册进现代树，
   等于把当年有意移除的重复入口装回来；
3. 因此现代树对旧版「AI 设置」的能力覆盖由「桌宠设置 → AI 与对话」承担（同一入口
   里就是上表的现代页），并由
   `tests/test_sprite_menu_parity.py::test_ai_settings_stays_merged_into_pet_settings_entry`
   机器化钉住（既断言现代树没有 `chat_settings` 项，也断言 `桌宠设置` 在）。

### 退役的边界：模板 ≠ 编排

`context_menu_template`（选哪一套模板）与 `context_menu_layout`（用户自己编排的树）
是两件事。本次只删前者：`pet/menu_layout.py`、`modern-default-v1.json`、
`resolve_menu_layout` / `merge_default_menu_actions` 一字未动，所以用户的自定义编排、
以及"新增动作自动补进老用户布局"的机制照旧工作。

### 配置迁移的落点

顶层配置键的退役本仓已有先例（`_migrate_decode_broker_config`，批 5.3 的
`decode_broker_enabled`）。本次照抄同一形状：在 `reload()` 解析出 `raw` 之后、
合并进 `self.data` 之前调用 `_migrate_menu_template_config(raw)`——
读旧值 → 记一次 info → `raw.pop`。

这样做的三个后果，正是验收要的东西：

- **读入即弃**：键从不进入 `self.data`，消费方（已全部删除）读不到任何旧值；
- **不报错**：不论值是 `legacy` / `modern` / `[1,2]` / `{"a":1}` 都只是被 pop 掉；
- **不写回**：`save()` 落盘的是 `self.data`，键已不在其中 ⇒ 旧键在下一次保存时
  从 `config.json` / `config-slot-N.json` 里消失（无需额外的"清理"动作）。

主配置与每个 slot 配置走的是同一条构造路径，因此子肥鱼那份配置文件同样被清
（实测见第五节）。

## 四、性能分析

**方法（可复现）**：`.scratch/legacy-menu-retirement/bench_menu.py`（同一脚本在退役前
基线 worktree `D:/dsh-pet-baseline`（`6021fc4`）与退役后分支各跑 **4 轮**，每轮：
冷导入取 5 次中位、菜单实建 300 次取中位、配置加载 300 次取中位；`import` 的 RSS
增量由子进程内 psutil 前后差取中位。下表是 4 轮的中位与全距）
环境：`Windows 11 / Python 3.13.7 / PySide6（本仓 requirements）/ QT_QPA_PLATFORM=offscreen`

| 指标 | 退役前（`6021fc4`） | 退役后 | 差异 | 归属 |
|---|---|---|---|---|
| `import pet.context_menu` 冷导入（4 轮中位，全距） | **310.9 ms**（303.8–332.5） | **300.4 ms**（295.9–304.5） | −10.5 ms（−3.4%），**全距重叠** | 导入图少 3 个模块 |
| 同上，RSS 增量 | **31040 KB**（30912–31228） | **31032 KB**（30928–31348） | ≈0（噪声内） | 少加载 2 个 JSON + 3 个模块（相对 PySide6 可忽略） |
| `populate_context_menu` 建树（300 次中位） | **20.6 ms**（20.35–21.01） | **20.15 ms**（19.92–20.72） | −0.45 ms（−2.2%） | 热路径：去掉模板分发与一次文件读取 |
| 同上，p90 | **23.5 ms**（23.29–23.79） | **23.0 ms**（22.78–23.40） | −0.5 ms | 同上 |
| `Config(base)` 加载（300 次中位） | **0.1645 ms**（0.155–0.215） | **0.1585 ms**（0.154–0.162） | −0.006 ms（−3.7%） | 少一次归一化分支；新增迁移只在旧键存在时多一次 `dict` 成员判断 |

**结构性测量（不依赖计时，去噪声）**：`.scratch/legacy-menu-retirement/probe_menu_io.py`
用 `sys.addaudithook` 统计一次右键建菜单读取 `pet/menu_templates/*.json` 的次数：

| | 首次建树打开次数 / 文件 | 稳态 5 次建树打开次数 / 文件 |
|---|---|---|
| 退役前 | 3（`modern.json` + `modern-default-v1.json` + `__init__.pyc`） | **10**（`modern.json` + `modern-default-v1.json`） |
| 退役后 | 2（`modern-default-v1.json` + `__init__.pyc`） | **5**（`modern-default-v1.json`） |

即每次右键（窗口侧与 overlay 侧同一条建造器）**少一次模板文件读取**——旧实现
每开一次菜单就把 `modern.json` 读一遍（`load_menu_template`），而那份数据
`build_modern_menu` 根本不用。

**结论**：逐条回答——① **稳态开销没有可测变化**：四个指标的差异都落在运行间波动内
（导入全距重叠、建树 −0.45 ms 而两树全距相邻、配置加载 −0.006 ms 属噪声级）；这是
删除类改动的预期结果，不宣称"更快"。② **新增路径成本**：唯一新增逻辑是
`reload()` 里一次 `"context_menu_template" in raw` 判断（键不存在时一次 `dict` 成员
检查，纳秒级；配置加载中位反而略低）。③ **没有新的系统调用 / 网络 / 磁盘 / 线程**：
磁盘**减少**一次/次右键（上表），无网络、无新线程。④ **内存与缓存**：无增长
（导入 RSS 增量 31040 → 31032 KB，噪声内）；反而少驻留 `legacy.py` 等 3 个模块对象
与 2 份模板 JSON（体量小到测不出来，如实记为"无可测收益"）。

## 五、实机运行记录

本机 Windows 真实环境，`QT_QPA_PLATFORM=offscreen` 下的真实 Qt 菜单树（不是 mock）。

1. **功能超集核对（退役前 / 退役后两棵树各实建一次菜单）**

   脚本 `.scratch/legacy-menu-retirement/dump_menu_tree.py` 用**同一个**装配
   （真实 `PetWindow` + 真 `Config` + `app._wire_window` 同款回调面）在两侧各导出一棵
   树的完整标签路径；`compare.py` 逐标签比对（"动画 · X" 是旧版扁平布局的分类标题
   前缀，现代树把同一批分类收进「播放动画」子菜单且不带前缀，比对时归一）：

   ```text
   退役前 legacy 标签数      : 83
   退役前 modern 标签数      : 94
   退役后 modern 标签数      : 94
   退役前后 modern 标签集一致 : True
   legacy 有、退役后 modern 没有的标签：
     - AI 设置: 并入「桌宠设置 → AI 与对话」（SETTINGS-REDESIGN-Q6-Q7…:402/428）
     - 切换到新版菜单: 模板切换入口随旧版菜单一起删除（本 PR 的目的）
   判定：退役后 modern 是退役前 legacy 的功能超集（差异仅上面两条有记录的条目）： True
   ```

   另：退役后即使**仍然请求 legacy**（配置里写 `context_menu_template=legacy`），实建
   出来的树与 `modern` 逐字节相同（`after-legacy-requested.json == after-modern.json`
   ⇒ `True`），即旧值已完全失去分流能力。

2. **迁移实测（真写文件 → 真加载 → 真建菜单 → 真落盘）**

   脚本 `.scratch/legacy-menu-retirement/migration_check.py`，原始输出：

   ```text
   [log] INFO 配置键 context_menu_template 已退役（旧版右键菜单全量删除，菜单恒为现代树），忽略旧值 'legacy'
   1) 主配置写入 context_menu_template=legacy，开始加载…
      cfg.data 里还有这个键吗: False
      cfg.get(...) 返回        : None
      菜单根层               : ['厉害了我的鲸', '播放动画', '切换角色', '播放速率', '大小', '音乐', '桌宠控制', '快捷启动', '工具与帮助', 'Agent 联动', '免打扰', '回收内存', '退出']
      保存后磁盘上还有这个键吗  : False
   2) slot 配置（config-slot-3.json）写入 context_menu_template=modern，开始加载…
      slot data 里还有这个键吗 : False
      slot 保存后磁盘还有吗     : False
   3) 脏值（list / dict）同样静默丢弃，未抛异常
   ```

   另外，`1)` 里的菜单是**真实弹出路径**建的：`menu.objectName() == "modernContextMenu"`
   在脚本里是硬断言（不回退旧版）。

3. **第 0 步的 AI 覆盖对比**（`step0_ai_coverage.py`，真实构造两个对话框）：
   经典对话框 17 行逐条映射到现代页行键，全部命中；现代页额外多出
   `chat_ui_style` / `chat_background_file` / `chat_background_opacity` /
   `chat_background_fill` / `modern_chat_card_opacity` 五个键。

4. **边界与失败路径**：
   - 值脏到 `[1,2]` / `{"a":1}` 也不构造失败（`Config(base)` 不抛）；
   - `pet/context_menus/legacy.py` 等四个文件删除后，`import pet.context_menu` /
     `pet.sprite_menu_facade` / `pet.context_menus` / `pet.window` 全部成功（不是靠
     try/except 兜住的静默降级）；
   - 「设置里找不到菜单模式」不再有候选：`settings_search` 的别名表已删该项。

5. **未能自动验证 / 未做**（如实登记）：
   - **真实 GUI 截图未产出**：本次是删除类改动，视觉面唯一变化是「菜单」域少一行
     下拉；没有用肉眼在真机桌面点开菜单确认（本会话无图像复核手段）。程序化断言
     覆盖了树结构与样式属性，但"看起来对不对"没有人工确认；
   - **托盘「AI 设置」入口未实机点验**：本次没有改它（保留 `ChatSettingsDialog`），
     也没有在真机点开核对；它由既有用例覆盖；
   - macOS / Linux 真机未跑（不推断平台结果）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/ scripts/` | **All checks passed!** |
| 聚焦（菜单族 15 文件） | `pytest -q tests/test_sprite_menu_parity.py tests/test_menu_layout.py tests/test_desktop_pet_features.py tests/test_quiet_mode.py tests/test_weather_menu.py tests/test_memory_trim.py tests/test_effects_integration.py tests/test_requested_regressions.py tests/test_config_schema.py tests/test_harness_lifecycle.py tests/test_chat_subsystem.py tests/test_animation_menu_close_and_group.py tests/test_sprite_menu_facade.py tests/test_sprite_menu_target.py tests/test_architecture.py` | 基线 **672 passed / 2 skipped**；退役后同 15 文件 **674 passed / 2 skipped**（92.9s） |
| 全量（第一次，含尚未修的措辞表） | `QT_QPA_PLATFORM=offscreen python -m pytest -q tests` | **2 failed, 5506 passed, 11 skipped**（1032s）——两条失败恰是本轮后修的 `test_settings_page_guide.py` 措辞/旧词表（菜单版本行删除后表未同步），修复后该文件 118 passed |
| 全量（冻结树复跑，`1f1d66a`） | 同上 | **5510 passed / 11 skipped / 0 failed**（1028.89s，17:08） |
| 架构红线 | `pytest -q tests/test_architecture.py` | 见全量 |
| 迁移实测 | `python .scratch/legacy-menu-retirement/migration_check.py` | **通过**（第五节 2） |
| 超集核对 | `python .scratch/legacy-menu-retirement/compare.py` | **通过**（第五节 1） |
| 文件读取探针 | `python .scratch/legacy-menu-retirement/probe_menu_io.py` | 实测每 5 次建树少 5 次模板文件读取（第四节） |

### 红 → 绿证据（先改测试到红，再删实现到绿）

| 组 | 先红的用例 | 红时的输出 | 绿 |
|---|---|---|---|
| 1 旧版菜单退役 | `test_architecture.py::test_retired_legacy_menu_files_are_gone`、`::test_pet_tree_has_zero_retired_legacy_menu_references`、`test_desktop_pet_features.py::test_context_menu_has_no_template_switch_entry` | `3 failed`（文件仍在、符号仍在、`populate_context_menu` 仍按模板键出旧树：`assert '' == 'modernContextMenu'`） | 实现删除后同 3 例通过 |
| 2 配置键退役 | `test_architecture.py::test_retired_menu_template_key_confined_to_migration`、`test_config_schema.py::test_retired_menu_template_key_*`（3 例） | `5 failed`；守卫**准确指出** `modern_settings_dialog.py:916` / `:2367`、`settings_default_marks.py:89` 三处残留消费点 | 实现删除后 77 passed（`test_architecture.py` + `test_config_schema.py`） |
| 3 死槽清理 | 删除的是"无害赋值"，无独立红相位：由组 1/2 的守卫覆盖（`on_open_legacy_settings` 的读方在组 1 已删，本组删的是写方） | — | 聚焦族 371 passed |

### commit 清单

| # | commit | 主题 |
|---|---|---|
| 1 | `339292e` | `refactor(menu): 旧版右键菜单全量退役` |
| 2 | `e23f6e6` | `refactor(config): 右键菜单模板键退役 + 旧存档静默迁移` |
| 3 | `aad317d` | `refactor(menu): 清理随旧版菜单退役的死槽` |
| 4 | `5480cd7` | `chore(menu): 同步随菜单版本行失效的残留引用`（措辞表 / 截图脚本 / 域归属声明 / 注释） |
| 5 | `02e84dd` | `docs(menu): 旧版菜单退役的用户可见说明与文档同步` |
| 6 | `8ddb901` | `docs(menu): 修正仍按"两套建造器"写的历史注释（无行为改动）` |
| 7 | `1f1d66a` | `docs(handover): test_architecture 的行数与用例数按实测校准` |

**本次未 push**（用户明令）。第 7 个提交之后工作区只有本报告的实测数字回填（纯文档）。
全量套件是在 `1f1d66a` 这棵树上跑的（0 failed）；此后仅本报告与纯注释/文档有改动。

## 七、已知限制与后续

1. **`context_menu_template` 仍能出现在 `config.json` 里**——直到用户下一次保存。
   这是"不写回"的必然结果（我们不做主动清理整盘的动作）。迁移函数每次启动都会
   再丢一次，代价是一次 `dict.pop`。
2. **`reopen_context_menu` 在 `pet/` 内已无产品调用方**：它原本服务「切换模板后原位
   重开」，模板切换删除后只剩测试在调。它本身是通用的"菜单重建后原位重开"，且
   `window.py` / `overlay_shell.py` 各一份实现、都有测试，故本次保留；若 owner 认为
   该一并退役，可另开一刀（涉及 2 个实现 + 3 处测试引用）。
3. **托盘「AI 设置」与聊天授权回调仍指向经典 `ChatSettingsDialog`**：退役该对话框
   需要把这两条入口改接到现代设置页（`open_modern_settings` 已支持 `initial_page`
   深链，`open_settings_process(instance, page=…)` 也透传），建议单独立项；顺带可把
   现代页缺的「已保存 API Key」提示补上，那才是真正的严格超集。
4. **未做真机 GUI 截图**（第五节 5）。

## 八、风险与回滚

- **影响面**：右键菜单（窗口侧 + overlay 侧）、配置加载路径、设置页「菜单」域、
  测试套件。不涉及网络 / 线程 / IO 新增。
- **开关**：没有新增开关。旧版菜单不再可选（这正是本刀的目的）。
- **配置迁移**：删除一个键（`context_menu_template`），无新增键；旧值静默丢弃，
  无回滚到"旧版菜单"的路径（回滚只能回滚代码）。
- **回滚步骤**：`git revert` 三个提交即可；注意点是 `tests/test_architecture.py`
  的防复活守卫会随 revert 一起消失，届时旧版菜单即为当前实现。**残留状态**：
  revert 后用户的 `config.json` 里已没有该键，`Config` 的默认值会补回 `"modern"`
  ——即回滚后用户看到的是现代菜单，而不是他退役前选的旧版（该信息在退役时已被有意
  丢弃，无法恢复）。
