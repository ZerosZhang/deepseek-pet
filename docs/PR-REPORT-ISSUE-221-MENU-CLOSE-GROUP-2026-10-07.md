# issue #221：动画菜单点完收起与随机动作前缀分组

> **基线**：`aa72d75`（merge 托盘延迟派发 + 设置可见反馈）；本提交经 `e65e65f` 并入 integration
> **分支**：`feature/issue-221-menu-close-and-group`　**提交**：`2eadc76`　**日期**：2026-10-07
> **范围**：6 个文件（实现 2、测试 3、文档 1），净 `+737 / −10`，含 1 个新测试文件
> **关联**：issue #221
> **互链**：术语 **Animation Menu Dismissal** 已按
> [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) §5 写入 [`../CONTEXT.md`](../CONTEXT.md)；
> 菜单结构与交互的研究档案见
> [`CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md`](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md)
> （本批**未**向其追加新一轮，见第七节）；必备证据章节见
> [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md)；本文已登记在 [`INDEX.md`](INDEX.md) 的
> 「PR 报告存档」。

## 一、核心特性

两条菜单体验修复：

1. **点完动画动作后整条菜单不收起**——右键 →「播放动画」→「随机动作」→ 某个动作，点完
   三级菜单（含根菜单）仍然留在屏幕上，用户得手动点空白处关掉。
2. **随机动作 95 项平铺一列**——`随机动作` 子菜单是一张单列长清单，实机高度 1439px
   **顶满整屏**，找动作要滚很久。

修法：① 给动画叶子加 `closeOnTrigger` 属性，接进仓库**既有的**菜单收口机制（`connect_action`
见属性且父菜单可见 → `defer_menu_callback`；`StayOpenMenuFilter` 见属性则让 Qt 走原生关闭
路径，**整条链一起收**）；② 给随机动作清单按**名字前缀**做家族分组（7 组），家族子菜单在
**构建期**就建好，动作仍延迟到各自 `aboutToShow` 才填充（缩略图解码量不增加）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 点动作整条菜单收起 | 三级/四级链全部消失；动作正常播放 |
| 2 | 设置类不受影响 | 播放速率 / 大小 / 拖动物理开关点完**菜单留在屏上** |
| 3 | 随机动作分 7 组 | `吃 / 余额 / 原地 / 工作状态 / 放 / 碎碎念 / 更多`，按成员数降序，`更多` 恒定最后 |
| 4 | 连播开关 | `anim_menu_stay_open`（默认 `False`）：置 `true` 回到旧行为（不收起），家族子菜单内同样不收起 |
| 5 | 两条菜单模板 parity | legacy + modern 都分组、都收起（共用同一建造器，parity 测试逐项比对） |

**红线 / 不变量**：
- **设置类**（速率/大小）、**开关类**（拖动物理等）、**子菜单项**一律不碰——它们走
  `add_action` / `addMenu`，代码路径没动；点完必须留在屏上。
- 不分组时（清单 < 24 项、或整份清单挤在同一家族）**逐位保持旧行为**（平铺 + 单一
  `aboutToShow`）。
- **不增加缩略图解码量**：家族子菜单构建期只建**壳**，动作仍延迟填充。
- 不硬编码字符表：分组规则完全数据驱动（含 `-` 用首个 `-` 前那段；否则按首字取最长公共前缀）。
- 不遮挡位置算法：`menu_layout` / `pick_context_menu_position` **一行未动**。

## 二、修改文件说明

`git log --numstat 2eadc76`：

```
11	0	CONTEXT.md
9	0	pet/config.py
140	9	pet/context_menus/shared.py
453	0	tests/test_animation_menu_close_and_group.py
43	0	tests/test_config_schema.py
81	1	tests/test_sprite_menu_parity.py
```

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/context_menus/shared.py` | +140 / −9 | **①** 新增 `animation_menu_stay_open(pet)`：读 `anim_menu_stay_open`，默认 `False`；`cfg` 按面探测（`getattr(cfg, "get")` 可调用）——菜单建造器的宿主常是 `__getattr__` 兜底返回函数的替身，直接 `cfg.get` 会 `AttributeError`（全量套件里先在 `test_effects_integration` / `test_desktop_pet_features` 撞出来的，已收口）。**②** `_populate_animation_category(...)` 增加 `close_on_trigger` 形参，给每个动画叶子 `setProperty("closeOnTrigger", bool(...))`——这就是仓库既有的收口机制：`connect_action` 见属性且父菜单可见 → `defer_menu_callback`（关根菜单 + 回调延后到 `menu.exec()` 返回后由 `window.py` / `overlay_shell._dispatch_deferred_menu_callbacks` 派发）；`StayOpenMenuFilter` 见属性则 `return False` 让 Qt 走原生关闭路径（整条链一起收）。**③** 新增分组纯函数 `group_animation_entries(entries)` + `_dash_family_key` + `_prefix_family_key`，常量 `ANIMATION_GROUP_RESIDUAL_LABEL="更多"`、`ANIMATION_FAMILY_MIN_MEMBERS=3`、`ANIMATION_FAMILY_MAX_KEY_LEN=4`、`ANIMATION_GROUP_MIN_ENTRIES=24`。**④** `build_animation_categories`：分类表加第 4 列 `groupable`（只有随机动作 `True`）；随机动作清单分组时**家族子菜单在构建期就建好**（这样后面的 `install_responsive_menu_style` / `install_stay_open_interaction` 递归能覆盖到它们），动作仍延迟到各自 `aboutToShow` 才填充，**缩略图解码量不增加**；不分组时逐位保持旧行为；宿主返回非序列时 `isinstance` 守卫跳过分组。 |
| `pet/config.py` | +9 / −0 | `anim_menu_stay_open: False` 进默认值 dict；进入 reload 白名单元组；`_normalize_pet_settings` 用 `_bool_or_default`（防手写 `"false"` 被当开）；`set()` 归一调度元组。**设置页不加行**（同 `mem_*` 口径，用户手改 `config.json`）。 |
| `CONTEXT.md` | +11 / −0 | 新增术语 **Animation Menu Dismissal**（[`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) §5 要求改 Menu Action Model / 共享交互契约时更新术语表）。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_animation_menu_close_and_group.py`（新） | +453 / −0 | 12 项，**不 mock 菜单**：收起真值表走**真实 Qt 管理的子菜单链**（hover 让 Qt 自己弹子菜单）+ **真实鼠标按下/抬起**；分组断言走真实 `populate_context_menu` 产物 + 本仓 shenshen 素材包**真实清单**。 |
| `tests/test_config_schema.py` | +43 / −0 | `RELOAD_WHITELIST_SNAPSHOT` 加键；新增默认值 / 字符串布尔归一 / `set` + 落盘 round trip 三个用例。 |
| `tests/test_sprite_menu_parity.py` | +81 / −1 | 新增长清单 parity（legacy + modern 两模板，overlay facade 树 vs 真实 `PetWindow` 基准树逐项包含 + 家族结构相等 + 族内叶子带 `closeOnTrigger`）。 |

### 未改动（看起来相关但故意没动）

- `menu_layout` / `pick_context_menu_position`：**一行未动**——本批不做位置算法，靠
  ① 收起 + ② 分组自然缓解遮挡。
- `pet/context_menus/legacy.py`：分组与收起都在共用建造器里，legacy 路径自动生效。
- 设置页：新键不进设置页（按本次口径，属「命令/偏好型」手改 config.json）。
- 菜单研究档案 `CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md`：未追加新一轮（见第七节）。

## 三、实现要点

### 3.1 分组清单与规则（真实清单，非拍脑袋）

`D:\dsh-pet\_internal\assets\characters\shenshen` 全量 dump（**95 项**，顺序与
`MovieLibrary._load_all` 的 `sorted(rglob)` + `build_categories` 一致）：

| 组 | 项数 | 成员（示例） |
|---|---|---|
| 吃 | 17 | 吃Token / 吃冰淇淋融化 / 吃饺子 / 吃西瓜 … |
| 余额 | 6 | 余额-分文不剩 … 余额-钱袋满溢（`events/balance/`，前缀含 `-`） |
| 原地 | 6 | 原地专心玩魔方 / 原地敲击桌面互动 / 原地重力下蹲压缩 … |
| 工作状态 | 6 | 工作状态-原地踱步张望 … 工作状态-雀跃庆祝 |
| 放 | 4 | 放孔明灯 / 放河灯 / 放烟花 / 放风筝 |
| 碎碎念 | 3 | 碎碎念-发呆/对屏/擦桌碎碎念 |
| 更多 | 53 | 其余零散长尾（三球抛接、写代码、撸猫、蓝鲸现世 …） |

**规则（纯数据驱动，不硬编码字符表）**：

1. 名字含 `-` → 家族键 = **首个 `-` 之前**那段（`余额` / `工作状态` / `碎碎念`；角色包日后
   加 `乐器-*` 会自动成族）；
2. 否则家族由**首字**划定，键取该族全体成员的**最长公共前缀**（吃西瓜/吃饺子/吃Token 的
   公共前缀只有「吃」，原地系列是「原地」，放系列是「放」）——这个写法避免把 `吃10号`
   拆成独立的「吃1」族；
3. 家族成员 **< 3** 的退回「更多」；
4. 清单 **< 24 项**、或整份清单挤在同一家族（无收益）→ **不分组**，保持平铺；
5. 排序：家族按成员数降序（同数按首次出现序），「更多」**恒定最后**。

**边界诚实说明**：`大口吃零食` / `偷吃零食被抓住` / `是啊，吃什么` / `中秋赏月吃月饼` 只是
**含**「吃」而非前缀，按拍板口径留在「更多」。任务里提到的 `乐器*` 在本机素材包中**不存在**
（首字族只有 吃 17 / 原地 6 / 放 4 三个）——规则对它是自动生效的，但**本次无法实机确认**。

### 3.2 收起机制（复用既有链路，不发明第二套）

`closeOnTrigger` 属性是仓库既有 `defer_menu_callback` 机制的开关：`connect_action` 见属性
且父菜单可见 → 关根菜单 + 把回调**延后**到 `menu.exec()` 返回后由
`window.py` / `overlay_shell._dispatch_deferred_menu_callbacks` 派发；
`StayOpenMenuFilter` 见属性则 `return False` 让 Qt 走**原生关闭路径**（这样 Qt 自己把整条
子菜单链一起收，不需要逐级手工关）。两条模板、两条拓扑共用同一建造器，故 natural parity。

**为什么家族子菜单必须在构建期建好**：`install_responsive_menu_style` /
`install_stay_open_interaction` 是**递归**安装的，若家族子菜单延迟创建，递归就覆盖不到它们，
族内叶子点了会被 Qt 原生路径收起（连播开关打开时行为不一致）。这条已用
`test_stay_open_holds_inside_family_submenus` 锁死（判别力抽查见第六节）。

### 3.3 一处替身面过度假设（首轮全量踩到的坑）

首轮全量 5 failed：`test_effects_integration` 与 `test_desktop_pet_features` 的三个动画菜单
测试用的替身 `__getattr__` **返回函数**，`pet.cfg` / `pet.acts` 因此不是配置和序列，
新读取点直接抛 `AttributeError` / `TypeError`。已在 `animation_menu_stay_open` 与
`build_animation_categories` 两处按面守卫（`getattr(cfg, "get")` 可调用、`isinstance` 序列
守卫）收口，5 项转绿。**归类**：这属「新代码对既有替身面过度假设」，不是替身的错。

## 四、性能分析

**方法（可复现）**：卸载/加载两组对照在本机**离屏**（`QT_QPA_PLATFORM=offscreen`）用真实
`populate_context_menu` 产物测量菜单尺寸；样本是 `D:\dsh-pet\_internal\assets\characters\shenshen`
的真实素材清单（95 项）。
环境：Windows / Python 3.13.7 / PySide6 6.11.2。

| 指标 | 实测 | 归属 |
|---|---|---|
| 随机动作未分组时子菜单尺寸 | **236 × 1439px**（单列，**顶满整屏高度**）——实机与离屏同口径复核 | 既有（被修） |
| 分组后同风格离屏对照 | 未分组总高 **2294px**；最大一级（`更多`）**1286px → 约 800px**，即 **56%** | 新增 |
| 分组后实机一级菜单 | 7 个子菜单，高度明显低于屏幕高度、可滚动（主代理真机记录另见第五节） | 新增 |
| 分组计算成本 | 纯字符串前缀统计，一次菜单构建一次（**离散事件**，非每帧、非每拍）；常数阈值均写死（`FAMILY_MIN_MEMBERS=3` / `MAX_KEY_LEN=4` / `GROUP_MIN_ENTRIES=24`） | 新增 |
| 缩略图解码量 | **不变** —— 家族子菜单构建期只建壳，动作仍延迟到各自 `aboutToShow` | 既有路径不变 |
| 收起机制成本 | 复用既有 `defer_menu_callback` + `StayOpenMenuFilter`，**未新增定时器/线程/轮询**；只是给叶子多设一个 Qt 动态属性 | 新增（可忽略） |
| 稳态开销（不开菜单） | **零** —— 分组只在菜单构建时求值；不建菜单则一行不跑 | 既有路径不变 |
| 新增线程 / 网络 / 磁盘 / 系统调用 | **0 / 0 / 0 / 0** | — |
| 内存 | 新增一个家族结构（7 组、95 个名字的引用），随菜单生命周期释放；无缓存 | 新增（有界、随菜单释放） |

**结论**：① **稳态开销零变化**——分组与收起只在菜单构建/点击这两个离散事件上发生，不开
菜单则一行不跑；② **新增路径成本**是一次纯字符串前缀统计（95 个短名字），相对菜单构建
本身可忽略；③ **未引入任何定时器/线程/网络/磁盘/系统调用**——收起复用既有链路，只多设一个
Qt 动态属性；④ **内存有界**且随菜单释放；**缩略图解码量不变**是本批刻意保住的性质。

## 五、实机运行记录

**主代理本机真机验收（真实桌面、真实进程、真实鼠标输入驱动的产品实例）**：

- **分组（逐条照用）**：**随机动作分 7 组（吃 / 余额 / 原地 / 工作状态 / 放 / 碎碎念 /
  更多，182px 不再顶满屏）**——即在真实进程中，原先平铺 1439px 顶满屏的清单已变成 7 个
  家族子菜单，不再顶满屏幕。
- **收起（逐条照用）**：**点动作整条菜单消失**——点击家族子菜单里的动作后，**整条菜单链
  （含根菜单）消失**，动作正常播放。

**口径诚实说明（不强行合并两个数字）**：真机这条记录给的是 **182px**，而第四节的离屏
自动化对照给的是**高度口径**（未分组总高 2294px、最大一级 1286px→约 800px）。两者**不是
同一口径**（前者是真实渲染下的一级菜单尺寸记录，后者是离屏对照的逐级总高），故**并列
如实登记**，本报告不把二者互相解释成同一个数。

**隔离实例的实机验证步骤（本次交付的清单，供复查）**：

```text
cd /d/dsh-pet-src-wt-221
set DSH_PET_INSTANCE=dev221 && python -m pet
```

用 `%APPDATA%/dsh-pet-standalone/config-dev221.json`（首次运行从主配置落种，因此继承
modern 模板 / shenshen / 菜单外观），**主配置不被改**。展开路径：右键 → 播放动画 →
随机动作 → 应见 7 个子菜单（顺序按成员数降序）；点 `吃 → 吃西瓜` → 三级（含根）菜单必须
整条消失。

**现场复核（本机，改动前）**：离屏复现同一现象——真实链 + 真实鼠标事件后
root / 播放动画 / 随机动作 的 `isVisible()` **全为 True**，回调同步跑（即「点完不收」确实
存在于当前代码路径）。改动后三级/四级链**全部 False**，动作正常播放；连播开关打开则维持
全 True。

**前提复核**：部署构建 `D:\dsh-pet\_internal` 与本 worktree 素材包一致
（`random/` 89 + `events/balance/` 6 = **95 项**，`build_categories` 同口径复核）。
**部署构建（`D:\dsh-pet`，运行中的 PID 33084）不含本次改动**，实机验证必须跑 worktree 源码。

**边界与失败路径（实机/自动已验证）**：

- **设置类不受影响**：播放速率点 1.5x、大小点一档、拖动物理勾选开关——菜单**留在屏上**
  （真值表走真实 Qt 子菜单链 + 真实鼠标事件）。
- **连播开关**：`anim_menu_stay_open: true` 时点动作菜单**不收起**（旧行为），且**家族子菜单
  里同样不收起**（`test_stay_open_holds_inside_family_submenus` 锁死）。
- **不分组短路**：清单 < 24 项或全挤在同一家族 → 逐位回到旧的平铺 + 单一 `aboutToShow`。
- **宿主返回非序列** → `isinstance` 守卫跳过分组，不抛异常。

**无法自动验证的能力（如实登记）**：

- **macOS 真机未验证**：收起逻辑复用的是仓库既有的 macOS 原生菜单跟踪收口机制，本批**只在
  Windows 本机离屏 + 真机验证**。「四级链 + 挂起回调」这一组合建议在 macOS 上按同一清单
  再走一遍（该机制本身是 macOS 实机踩出来的）。
- **`乐器*` 家族无法实机确认**（本机素材包没有这类名字），规则对它是自动生效的。
- **未做对照截图**：清单第 9 条建议「做 4（收起）与 6（连播）的对照截图，两张即是最有力的
  验收证据」，本次**未拍**。

## 六、测试与验证

**红 → 绿（先写测试、后写实现）**

```text
git stash push pet/context_menus/shared.py pet/config.py
$ QT_QPA_PLATFORM=offscreen python -m pytest -q <新测试文件 + test_config_schema>
20 failed        # 失败原因逐条是行为断言
                 #   `_close 后 root 仍可见`
                 #   `closeOnTrigger is None`
                 #   `随机动作层没有家族子菜单`
                 #   `列里没有默认值键`
$ git stash pop
60 passed
```

**判别力抽查（证明测试不是摆设）**：把 `install_stay_open_interaction` 换成**非递归**版本
（只装根菜单）后重跑，`test_stay_open_holds_inside_family_submenus` **立刻红**（家族子菜单被
Qt 原生关闭路径收起）——这条测试确实锁住了「家族子菜单是构建期建的、样式/交互必须递归跟上」。

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | All checks passed |
| 聚焦 | 新增 12 项 + parity 21 项 | **33 passed** |
| 时序敏感族高负载复跑 | 同上 **× 3 轮**（每轮 5.6–5.7s） | **33 passed × 3**，无 flake |
| 空白检查 | `git diff --check` | 通过 |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4815 passed, 11 skipped**（11:12；这是修掉首轮 5 项旧套件失败后的复跑结果） |
| 集成全量（当晚最终树） | 同上（integration/2026-10-07-night-batch） | **4828 passed, 11 skipped** |

**首轮全量的 5 failed 已如实记录**：见第三节 3.3（替身面过度假设），收口后转绿。
**一次僵尸进程事件**：执行层把首轮全量后台任务设了 300s 超时，被截断时留下一个僵尸 pytest
（PID 35008，自己起的），按仓库的僵尸排查流程 kill 后重跑；**用户桌宠进程全程未碰**。

## 七、已知限制与后续

1. **「更多」53 项仍是最大的一级**（约 800px）：满足「每级不超过一屏」，但没有更短。两个
   可选后续：家族最少成员数 `3 → 2`（能再收窄约 10 项，代价是多几个 2 项小家族），或给长尾
   加一张语义关键词表（需人工维护、且是「拍脑袋」口径，**本次没做**）。这是主动留的取舍点，
   不是遗漏。
2. **macOS 真机未验证**（见第五节）。
3. **`乐器*` 类家族无法实机确认**（规则自动生效）。
4. **未做对照截图**。
5. **未向菜单研究档案追加新一轮**：该仓菜单类改动的惯例是往
   [`CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md`](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md)
   追加「TDD 过程 + 实测数字」，本批**未追加**（按当时的执行口径）；`docs/INDEX.md` 因本报告
   入场而更新。
6. **新键不进设置页**：`anim_menu_stay_open` 只在 `config.py` 四处登记 + `CONTEXT.md` 术语；
   与其它菜单类键一致，跟随 sprite 的 config 视图（子肥鱼缺键时回退主配置）。

## 八、风险与回滚

- **影响面**：`anim_menu_stay_open` 默认 `False` → 默认行为是**新行为**（点动作收起）——
  这是本批唯一「改了默认观感」的地方，属 issue 诉求本身。分组只在随机动作清单 ≥ 24 项且
  家族 ≥ 3 时才发生，其余清单逐位保持旧行为。菜单布局位置算法未动。
- **配置迁移**：全新键；老配置无此键 → 取默认 `False`。手改脏值（字符串布尔）由
  `_bool_or_default` 收口。无落盘数据迁移。
- **回滚**：`closeOnTrigger` 与分组都在 `build_animation_categories` **一条通道**上；要回退
  只需删新键默认值/守卫，两模板**同时**回到旧行为（不会出现「一条模板新、一条旧」的半吊子
  状态）。`git revert 2eadc76` 后无残留状态。
- **合并冲突面**：`pet/context_menus/shared.py`（当晚多条批次都改这个文件：菜单节点插入、
  分组函数、网络置灰、托盘延迟派发）；`tests/test_config_schema.py` 两份字面量快照；
  `tests/test_sprite_menu_parity.py`（legacy + modern 树比对）。
- **分支状态**：本提交经 `e65e65f` 并入 `integration/2026-10-07-night-batch`；
  分支未 push、PR 未开。
