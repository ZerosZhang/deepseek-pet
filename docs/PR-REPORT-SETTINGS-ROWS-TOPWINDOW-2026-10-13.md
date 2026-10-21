# 点设置时闪一堆无标题小窗（SettingRow 游离顶层窗口）修复

> **基线**：`47b6bfe`（Merge PR #259 `fix/edge-tts-proxy`，origin/main）
> **分支**：`fix/settings-rows-topwindow-flicker`　**日期**：2026-10-13
> **范围**：3 个实现/测试文件 + 2 个文档（实现 `+37/−18`、测试 `+118`、文档 2）
> **关联**：设置页信息架构（`docs/SETTINGS-CHANGE-GATES.md`）、`pet/chat/settings_dialog.py:115`
> 的同款坑注释（旧聊天设置窗靠显式父对象修过）

## 一、核心特性

**用户可见症状**：从灵动岛 / 右键菜单 / 托盘任一入口点「设置」，加载过程中反复弹出、
消失一批无标题小窗口，约 2 秒后主设置窗才出现。

**根因（已插桩实证）**：`SettingRow` 行壳在**还没有父对象**时被 `setVisible(True)`。
没有父对象的 QWidget 就是顶层窗口（`isWindow()` 为真），`setVisible(True)` 于是当场在
桌面上开出一个**真原生窗口**（`windowHandle()` 非空），约 0.25s 后被 `SettingsCard` 的
布局 reparent 才消失。两个触发点：

| # | 触发链 | 行数（本次复现配置） |
|---|---|---|
| 1 | `pet/settings_network.py::build_island_network_rows` → `_install_visibility.apply` 的「父对象尚未设置 → 对本体补一次 setVisible」分支（行壳刚建出来、还没进卡片） | 指标 5 + 间隔 1 + 帧率 3（含授权行）= 9 |
| 2 | `pet/chat/ai_settings_page.py::appearance_rows` → `_update_background_visibility`（构造期按当前背景值决定详情行显隐） | 5 |

**红线 / 不变量**：行的**依赖显隐语义一位不变**——`_visibility_dependencies` 仍是
「多通道 AND 合成、与调用顺序无关」；高级组「全行被依赖隐藏则整组收起」
（`tests/test_settings_ia_first_cut.py:348-349`）、「依赖满足后该组重新出现」
（同文件 `:548`）继续成立。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/settings_network.py` | +19 / −9 | ① `build_island_network_rows` 的指标行（推导式内）、间隔行，`build_game_fps_rows` 的目标模式行 / 程序名行，`_fps_permission_rows` 的授权行，全部改为 `SettingRow(..., parent=dialog)`——行从诞生起就不是顶层控件；② `_install_visibility(dialog, rows)` → `_install_visibility(dialog)`：删掉「父对象尚未设置 → 对本体补一次 `setVisible`」分支与它专用的 `by_key` 表（行现在建在宿主上，`_set_setting_rows_visible` 的 `findChild` 一次就命中，该分支已成死代码）；③ 两处 builder docstring 写明「行建在宿主上」的理由。 |
| `pet/chat/ai_settings_page.py` | +18 / −9 | ① `appearance_rows()` 的 7 行、`__init__` 里 `vision_rows` 的 4 行改为 `parent=self`（行壳挂 `_AiSettingsPage` 上，与同文件既有 `SettingsSection(..., self)` 的口径一致）；② `appearance_rows` docstring 写明为什么不能无父——函数返回**之前**那句 `_update_background_visibility` 就要显隐详情行。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_modern_settings_rows_topwindow.py` | +118（新） | 监视构造期**真实到达的 `QEvent.Show`**（Qt 只在真把控件显示出来时派发它）——「一个 `SettingRow` 以顶层窗口身份收到 Show」逐字等于用户看到的那个闪烁窗口。两条用例：默认配置、以及「岛指标 + 间隔 + 帧率 + 背景详情行全可见」的真实用户配置形态；另附构造后不变量（全部行有父对象、`SettingRow` 总数 ≥ 100 防空跑）。探针只读取事件、不改行为。 |
| `tests/test_settings_stale_form_exit.py` | +62 / −76 | 两条真模态 exec 用例（`test_product_confirm_discard_reads_the_real_button_click`、`test_discard_unverified_notice_is_a_real_visible_box`）改为**子进程驱动**（原因与机制见 §六之一）；另拆掉 `test_discard_in_the_settings_process_releases_the_lock_for_the_next_open` 的 10 秒兜底 `app.quit` 定时器泄漏（跑完即 `stop()`，原为静态 `singleShot` 跑完不拆，会落在后面用例的循环里）。 |
| `tests/settings_realmodal_driver.py` | 新增 | 子进程驱动器：干净 Qt 进程里跑「编辑 → 关窗 → 真确认框点放弃 →（通知框读文本点掉）」，框全是产品原件，结果以 `RESULT {json}` 交父进程断言；音频按 conftest 同规打桩；`os._exit` 避开退出期 Qt 拆除。 |

### 未改动（明确写出来，避免评审误以为漏了）

- `pet/modern_settings_dialog.py`：本次不新增行、不动 `_set_setting_rows_visible`（`findChild` 语义**因本次改动变好**：行壳建在宿主上，构造期那一次 `apply` 现在就能命中并记下依赖位，不再依赖「进卡片后再补」）。
- `pet/chat/ai_settings_page.py::_update_vision_visibility` 与 `pet/chat/settings_dialog.py:126-130`：同坑残留，按任务约定不在本最小修复范围内（前者由本次的行父对象顺带覆盖，逻辑未动）。
- **懒加载/预热**：不属本 PR 范围（见 §四「结论 ②」与 §七）。

## 三、实现要点

1. **为什么是「传父对象」而不是「别调用 setVisible」**：行的显隐必须照样生效（它由
   `_visibility_dependencies` 与多通道 AND 决定），所以只能在**调用之前**让行从诞生起
   就有父对象。传父对象后 `setVisible(True)` 只是置标志（父窗未显示），不会再开窗口；
   行的语义与「进卡片后」完全一致。
2. **删掉补丁分支的连带清理**：`_install_visibility(dialog, rows)` 的 `rows` 参数在删除
   补丁后不再被使用，一并去掉（唯一调用点在 `build_island_network_rows`，无测试直调该
   私有函数）。
3. **`_set_setting_rows_visible` 的 `findChild` 不回退**：该函数用
   `self.findChild(SettingRow, f"settingRow_{key}")` 取行——行建在宿主上后，构造期那次
   调用从「找不到 → 落空」变成「找到 → 记依赖位 + 置显隐」，语义是**加强**而非回退；
   `SettingsSection` 装配时 `layout.addWidget` 会把行 reparent 到卡片，`parentWidget()`
   仍指卡片，`:376`/`:400` 的 `isinstance(card, SettingsCard)` 判断不受影响。
4. **`_fps_permission_rows`（仅 Windows）也在 `_FPS_FOLLOW_KEYS` 里**跟着帧率开关显隐，
   所以同样必须传父对象——否则真机上它不跟着帧率开关走。

## 四、性能分析

**方法（可复现）**：`PET_REPO_ROOT=$(pwd) python .scratch/settings-topwindow-flicker/bench_rows.py`
（脚本：每轮新建 `Config` + `ModernSettingsDialog(include_ai=True)`，安装 app 级事件过滤器统计
「`SettingRow` 以顶层窗口身份收到 `QEvent.Show` 的条数」及其 `windowHandle()` 是否非空；
配置为「岛开、信息槽开、指标 cpu/mem/network/gpu/fps 全勾、背景选自定义图」）。
环境：Windows（本机真实桌面，非 CI）／Python 3.13.7／PySide6 6.11.2／**样本量 n=5 轮**。

| 指标 | 基线 `47b6bfe` | 本分支 | 归属 |
|---|---|---|---|
| 构造中位耗时（**真 `windows` 平台插件**） | **2238.5 ms**（1993.1 / 2540.9） | **1026.0 ms**（984.6 / 1590.5） | 既有路径（打开设置时的构造段） |
| 构造中位耗时（`offscreen`） | 781.7 ms | 761.1 ms | 同上（离屏平台不真实创窗，故差额小） |
| 构造期游离顶层 Show 事件 | **14.0 条/轮**（70/5 轮） | **0 条/轮** | 新增缺陷面，已归零 |
| 其中真有原生窗口（`windowHandle()` 非空） | **14.0 条/轮** | 0 条/轮 | 用户看到的就是这些 |
| 构造出的 `SettingRow` 总数 | 230 | 230 | 回归对照（不多不少） |

**结论**（逐条）：

1. **稳态开销**：零变化——本改动只删掉构造期的 14 次 `setVisible(True)`「无父窗口」路径，
   不新增任何常驻分支、定时器或信号连接；`_install_visibility` 反而少了一次字典查表分支。
2. **新增路径的绝对成本与触发频率**：没有新增路径。构造期成本**下降**：真机上中位
   **−1212.5 ms（−54%）**，因为 14 次「创建原生窗口 + 显示 + 隐藏」本身就是这段耗时的
   大头；离屏平台只有 −20.6 ms（−2.6%），说明这部分成本几乎全部来自真窗口。
3. **系统调用 / 网络 / 磁盘 / 线程**：**减少**——每次打开设置少 14 次原生窗口创建与销毁
   （`CreateWindowEx`/`DestroyWindow` 级）。无新增网络、磁盘、线程、定时器。
4. **内存与缓存**：无增长——控件对象数与行数逐位不变（230 行）；少掉的只是 14 个瞬时
   顶层窗口的平台侧资源，构造结束后它们的生命周期本来也结束。

**用户报的「约 2 秒」**：在本机真桌面实测基线的构造段中位 2238.5 ms，与用户描述的时间
量级吻合；修复后同一段降到 1026.0 ms。**设置页「慢」的另一个成因**（独立设置进程冷启动 +
一次性构造 10 个域页面）不在本 PR 范围：本 PR 不做懒加载、不做预热，报告只如实记录该段
之外的耗时仍存在。

## 五、实机运行记录

**本机真实环境（Windows 桌面，非 CI、非 mock）**，三条记录：

1. **根因现场复现（真 `windows` 平台插件，n=5 轮）**——基线树上同一条命令：

   ```
   $ cd .scratch/prefix-baseline && python bench_rows.py      # 47b6bfe
   平台插件=windows　Python=3.13.7　轮数=5
     #1: 构造   2540.9 ms　游离顶层 Show  14　其中真原生窗口  14　SettingRow 总数 230
     ...
   构造中位 2238.5 ms　游离顶层 Show 合计 70（14.0/轮）　原生窗口合计 70
   ```

   本分支同一条命令：`构造中位 1026.0 ms　游离顶层 Show 合计 0（0.0/轮）`。14 个
   `SettingRow` 在真桌面上各开一个原生窗口，就是用户看到的那串无标题小窗。

2. **用户可见行为的确认**：本机跑上述探针时，基线树每轮**肉眼可见 14 个小窗口连闪**
   （探针本身不打桩、不隐藏窗口）；本分支同一条命令下桌面**没有任何窗口闪出**，只有
   探针自身的控制台输出。这串闪烁即用户报告的现象，属于本次修复的现场复现与消除。

3. **边界与失败路径**：`tests/test_modern_settings_rows_topwindow.py` 的「全开配置」用例
   覆盖「依赖全满足 → 行都该可见」这条路径；构造后不变量断言行全部有父对象、行数 ≥ 100
   （防探针空跑）。依赖隐藏路径仍由既有用例把关：`tests/test_settings_ia_first_cut.py:348`
   「间隔行默认隐藏 + 高级组整组收起」、`:548`「依赖满足后该组重新出现」——本分支上均通过。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `ruff check pet/settings_network.py pet/chat/ai_settings_page.py tests/test_modern_settings_rows_topwindow.py` | All checks passed（仓库配置 `select=["F"]`） |
| 新增回归（**修前**） | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_modern_settings_rows_topwindow.py -q` | **2 failed**（默认配置 6 条游离窗口；全开配置 14 条，逐条 objectName 与 sizeHint 吻合） |
| 新增回归（**修后**） | 同上 | **2 passed** |
| 聚焦族 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_settings_{network,game_fps,fps_permission,ia_first_cut,pet_tabs,interaction_tabs,search_aliases,default_marks,page_guide,reset_defaults,process_isolation,and_resources}.py tests/test_api_provider_list.py tests/test_modern_settings_rows_topwindow.py -q` | **295 passed / 0 failed**（147.15s） |
| 既有「放弃未保存改动」族 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_settings_stale_form_exit.py -q` | **1 failed / 49 passed** —— 唯一那条红见 §六之一（既有计时脆弱，非本改动的语义后果）；放进 14 文件批次里是 **2 failed / 341 passed**（同 §六之一 的 A/B 表） |
| 交付证据纪律 | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pr_report_discipline.py` | 通过 |

### 六之一、既有时序脆弱用例：已根治（进程边界化，本 PR 内闭环）

> 本节前半是当时的诊断登记，后半是最终修法。两条真模态 exec 用例
> （`test_discard_unverified_notice_is_a_real_visible_box` 与
> `test_product_confirm_discard_reads_the_real_button_click`）在本分支上曾**必红**——
> 这是 CI 三端连红的直接原因。

**根因（Qt 6.9 源码级钉死）**：套件共享进程里，任何一次「事件循环在跑时兑现
`QCoreApplication.quit()`」都会把 `quitNow` 旗标留在线程数据上
（`qcoreapplication.cpp:1512` `data->quitNow = true` 并退出所有在跑循环）；此后
`QEventLoop::exec` 在入口见到旗标**直接返回 -1 且不清旗**（`qeventloop.cpp` exec 入口
检查）——真模态框"弹了即死"。本 PR 的构造提速（14 个闪窗消失、事件泵时机变化）
改变了旗标落点：基线上它落在无害时刻，本分支上恰好落进这两条用例的真框 exec。
对照证据：基线代码 + 一句 `time.sleep(0.03)` 到构造函数（语义零改动）同样红；
干净进程逐字复刻同一流程通过 → 产品行为本身正常。

**为什么不走进程内清旗**：唯一能复位 `quitNow` 的公开路径是 `QCoreApplication.exec`
进出（`qcoreapplication.cpp:1445/1450`），但它会泵全局事件队列——实测在全套件语境下
引爆别用例遗留的排队事件/重复触发 `aboutToQuit`（全量套件 28 挂），conftest 也明令
禁止全局冲刷。两条进程内修法（单拍探针改事件同步轮询、fixture 级清旗）都被这套
机制否决后，按 AGENTS.md「Qt 回归用真实事件循环和进程边界」改为**子进程方案**：

- `tests/settings_realmodal_driver.py` 在干净子进程里跑完整真框流程（确认框点放弃
  → 通知框读文本点掉），`RESULT {json}` 交父进程断言；两条用例的断言语义一字未降。
- 验证：文件 50/50、settings 族组合 422/422（此前必红的组合）、子进程单条约 2.7s。
- 顺带真修了一个泄漏：`test_discard_in_the_settings_process_…` 的 10 秒兜底
  `app.quit` 定时器原为静态 `singleShot`，正常跑完不拆，会落在后面用例的循环里——
  改为句柄式 `QTimer`，`finally` 里 `stop()`。

## 七、已知限制与后续

- 设置页「慢」的剩余成因（独立设置进程冷启动、一次性构造 10 个域页面）未动：本 PR 只
  消除闪烁与那 14 个窗口的构造成本。若仍嫌慢，另开工单做懒加载/预热。
- 同坑残留未清：`pet/chat/ai_settings_page.py::_update_vision_visibility` 的调用形态、
  `pet/chat/settings_dialog.py:126-130`（按任务约定不在最小修复范围）。
- 本 PR 未做消融式开关审计（不涉开关增删），未做全量套件（见 §六 聚焦族）。

## 八、风险与回滚

- **影响面**：只在设置窗**构造期**改变行的父对象归属；行最终仍归 `SettingsCard`（装配时
  `addWidget` reparent），运行期信号与保存路径不变。
- **配置迁移**：无新增/删除配置键，无迁移。
- **回滚**：`git revert` 即回到旧行为（闪烁与 2.2 s 构造段一并回来），无落盘残留、无状态
  需要清理。
- **已知副作用**：无。§六之一登记的既有时序脆弱已在本次以进程边界化根治（断言语义
  不降），CI 三端曾因此连红的阻塞解除。
