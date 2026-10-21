# PR 报告：Harness 自启目标 `auto` 改为「仅服务」（新增 `service` 目标）（2026-10-06）

> **基线**：`ee699c7`（Merge PR #233 from MerZlin/feature/agent-link-subtraction）
> **分支**：`feature/harness-service-autostart`　**提交**：`b0e28f2`　**日期**：2026-10-06
> **范围**：9 个文件（实现 5、测试 4、文档 0），`+321 / −69`
> **状态**：**分支未 push、PR 未开**——提交只在本地，等待用户决策后再对外提交
> **关联**：前作 [`PR-REPORT-HARNESS-DUAL-TARGET-2026-10-06.md`](PR-REPORT-HARNESS-DUAL-TARGET-2026-10-06.md)
> （本报告改的正是它引入的 `auto` 语义）、[`PR-REPORT-HARNESS-OWNERSHIP-2026-09-29.md`](PR-REPORT-HARNESS-OWNERSHIP-2026-09-29.md)
> （自启门控与退出收口）、[`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)（设置页准入准出）

## 一、核心特性

**问题**：自启（`harness_autostart`）的本意是「把 dsh 服务准备好」，但 `harness_launch_target`
的 `auto` 被实现成「检测到桌面端安装就走桌面端」，于是**装了桌面端的机器每次桌宠启动都把
整个桌面端 GUI 拉起来**。产品口径（2026-10）：自启只应拉起 dsh 服务（headless web 服务，
不开浏览器、不开界面），web / 桌面端界面必须是**显式选择**才有的行为。

本机就是会中招的机器，前提有现场证据（§五第 1 条）：桌面端安装位命中
`C:\Users\me\AppData\Local\Programs\DeepSeek Harness\DeepSeek Harness.exe`，且旧版本启动
桌宠 9 秒后拉起桌面端 GUI **五个进程**。

| # | 能力 | 说明 |
|---|---|---|
| 1 | `auto` 语义改为「仅服务」 | `resolve_launch_target("auto")` 恒返回 `"service"`，**不再做任何桌面端探测**（安装位 / 注册表 / 进程一律不看）。旧实现 `return "desktop" if desktop_install_path() is not None else "web"` |
| 2 | 新增 `service` 目标 | `LAUNCH_TARGETS = ("auto", "service", "web", "desktop")`：显式表达「只起服务」。`service`/`web`/`desktop` 三者直通，非法值仍回落 `auto`（= `service`） |
| 3 | `service` 强制 headless | 走原有 web 启动路径，但 `open_browser` 一律按 `False` 处理：即使调用方传 `True`，也不开浏览器、不派生「等就绪再开页面」的线程 |
| 4 | 设置页如实 | 「自启目标」新增「仅 dsh 服务（不开界面）」；`auto` 文案由「自动（桌面端优先）」改为「自动（仅服务，不开界面）」；Windows / 非 Windows 两段目标说明同步改写 |
| 5 | 下拉文案不被裁字 | 控件宽度改按**最长项文案**计算（`ModernSelect.suggestedWidth()`）。自绘文本区没有省略号，原写死的 190px 会把新文案尾部裁掉（§四实测） |

**红线 / 不变量**：

1. **`desktop` 目标语义一行未改**：显式 `desktop` 仍拉起桌面端 exe；非 Windows 仍如实报
   `unsupported`（不静默回落、不 Popen `.app` 目录）；桌面端仍**只登记不杀**（退出/联动
   关闭绝不终止用户主力 GUI 应用）。
2. **`web` 目标行为逐字未变**：复用已有实例时开浏览器、新起实例（`--no-open`）由桌宠等
   就绪后开页面 —— 由既有用例 `test_launch_harness_browser_ownership` 看住。
3. **自启路径的「不开浏览器」性质不变**：`pet/app.py` 自启调用点本来就传
   `open_browser=False`（`pet/app.py:2120-2124`），所以本次变化是「不再开界面 / 不拉 GUI」，
   不是「不弹浏览器才开始」。
4. **菜单入口不受自启目标影响**：右键子菜单与托盘两个入口都显式传 `target`
   （`pet/context_menus/shared.py:561` 的 `_launch(action, target)`；`pet/app.py:3558-3559`
   传 `web` / `desktop`），点哪项起哪项。
5. 配置默认值仍是 `auto`，**无新键、无格式迁移**；老配置里的 `desktop` / `web` 照旧生效。

## 二、修改文件说明

`git diff --numstat ee699c7..b0e28f2`：9 个文件，`+321 / −69`。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/harness_launcher.py` | +52 / −24 | `LAUNCH_TARGETS` 加 `"service"`（:79）；`resolve_launch_target` 的 `auto` 分支由「探测后二选一」改成常量 `return "service"`（:214-227），随之删掉这里对 `desktop_install_path()` 的唯一调用；`launch_harness` 在 desktop 分支之后加 `if resolved == "service": open_browser = False`（:618-624），落在 web 路径之前；五处旧语义描述同步改写（模块 docstring、`desktop_install_path` 里「auto 因此仍解析成 web」这句已失效的注释、`launch_harness` / `launch_harness_gui` / `resolve_launch_target` 的 docstring）。**desktop 分支与 web 路径本体一行未动** |
| `pet/app.py` | +7 / −4 | `_maybe_autostart_harness` docstring 改为「auto/service 都是只拉起 dsh 服务」并写明 auto 不再解析成 desktop。调用点（`launch_harness(open_browser=False, target=配置值)`）未改 |
| `pet/modern_settings_dialog.py` | +17 / −11 | 下拉新增第 2 项「仅 dsh 服务（不开界面）」data=`service`；`auto` 项文案改「自动（仅服务，不开界面）」（原来按平台二选一的三元表达式取消——`auto` 现已与平台无关）；`web` / `desktop` 项与 desktop 置灰 + 回落 + 保存边界未动；Windows / 非 Windows 的 `harness_target_hint` 按新语义改写（保留「暂不支持」字样）；控件宽度改为 `setFixedWidth(max(190, suggestedWidth()))`（:345-353）。净 +6 行（2394 → 2400） |
| `pet/config.py` | +4 / −3 | 归一化白名单加 `"service"`（:1279）；默认值仍 `"auto"`；两句注释里的旧 `auto` 语义改掉 |
| `pet/settings_widgets.py` | +12 / −0 | `ModernSelect.suggestedWidth()`（:849-857）：按最长项文案 + 文本区内缩（34px）求控件所需宽度，把「paintEvent 的文本区是 `width()-34`」这一口径收在画它的控件自己身上。**未调用它的既有下拉行为不变**（新增方法，无副作用） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_harness_launcher.py` | +102 / −25 | **新增 4 条**：① `auto` 解析为 `service` 且把 `desktop_install_path` / `desktop_process_running` 换成**会抛的替身**（auto 只要碰它们一次就红），同时钉住 `""` / `"  AUTO  "` / `"bogus"` / 三个显式值 ② `auto` 启动走 web 路径但不开浏览器、不派生线程（`open_browser` 取默认 `True`） ③ 显式 `service` + `open_browser=True` 仍不开 ④ 已有实例复用（`already`）也不开。**改**：删掉两条旧 `auto → desktop/web` 语义用例；3 条原依赖裸 `launch_harness()`（默认 `auto`）开浏览器的旧用例显式改传 `target="web"`；`test_desktop_unsupported_platform_keeps_web_default` 的 `auto` 期望改为 `service` |
| `tests/test_harness_ownership.py` | +31 / −2 | **新增 1 条端到端**：真线程 + 真 `launch_harness` + 真 `_maybe_autostart_harness`（只打桩 OS 边界），在「装了桌面端」的桩环境下走产品自启入口，断言 dsh 服务被拉起、`_spawn_desktop` **零调用**、`webbrowser.open` **零调用**。**改**：一条既有用例的 docstring 里「`desktop/auto`」改为「`desktop`」（`auto` 已不是界面目标） |
| `tests/test_requested_regressions.py` | +64 / −0 | **新增 2 条**：① 设置页新项与文案（`itemText(0)` 逐字、`service` 排第 2、`web`/`desktop` 项未变、能落盘、说明里写明 auto = 只起服务不开浏览器）② 控件宽度 ≥ `suggestedWidth()`（裁字回归的机器守卫） |
| `tests/test_config_schema.py` | +32 / −0 | **新增 2 条**：① 加载路径归一化认 `service`、`auto` 保持、4 个非法值（`desktop-gui` / `SERVICE2` / 空串 / `0`）回退 `auto` ② `set()` 路径不吞 `service` |

### 文档

本批**没有改任何文档**，理由见下节「未改动」——登记本报告的 `docs/INDEX.md` 一行随本报告一起提交。

### 未改动（故意）

| 文件 | 为什么不动 |
|---|---|
| [`PR-REPORT-HARNESS-DUAL-TARGET-2026-10-06.md`](PR-REPORT-HARNESS-DUAL-TARGET-2026-10-06.md) | 它是 PR #233 的**归档交付证据**（含基于旧 `auto` 语义的调用次数与耗时实测）。就地改写等于事后篡改证据链，按 `AGENTS.md` 的「历史报告豁免」保留原样；语义变更由**本报告**承接 |
| `docs/INDEX.md:136`（DUAL-TARGET 的索引行） | 同一条理由：该行描述的是那份归档报告的结论 |
| `README.md` | 逐句核对：那段「随桌宠启动 dsh 服务」文字**没有**写 `auto` 解析成谁（只说「目标是 dsh web 时后台静默起服务」），对 `auto` = `service` 仍然成立，无需改动 |
| `CONTEXT.md`、`docs/SETTINGS-CHANGE-GATES.md` | 前者无 harness/自启目标内容；后者是准入准出标准，没有逐设置的登记表 |
| `pet/context_menus/shared.py`、`pet/app.py` 菜单入口 | 菜单是显式目标，本批语义变更不触及它们 |
| `restart_harness` | 本来就钉 `target="web"`（重启的是服务，不跟随自启目标），无需改 |

## 三、实现要点

1. **`auto` 变成纯字符串归一**。旧实现里 `auto` 是唯一会调用 `desktop_install_path()` 的分支
   （因此 `resolve_launch_target` 不是纯函数，会做文件系统/注册表 IO）。改成常量返回后，
   它与显式值走同一条路径，`auto` 不再携带平台/安装状态依赖 —— 「非 Windows 上 auto 不会
   拐到 desktop」这条旧保证升级成「**任何平台上 auto 都不看桌面端**」。
2. **强制 headless 只有一行布尔，而不是另起一条分支**。`service` 与 `web` 共用同一段启动
   代码（命令构造、端口复用、`already/started/not-found/aborted/error` 五态、`_spawn`），
   唯一差异是「开不开浏览器」。放在 desktop 分支之后、端口循环之前，语义上「先定目标、再定
   行为、最后跑路径」，读起来不会误以为 `service` 是第三种启动方式。
3. **`_wait_and_open` 在 `service` 下结构性不可达**，不是靠 `if` 绕开：命令带 `--no-open`
   时，`if not open_browser: return "started", url` 先于线程创建代码返回（`launch_harness`
   尾部）。所以 `service` 既不会开浏览器，也不会留下一个最长活 90 秒的等待线程。
4. **遗留限制照写不回避**：旧版 dsh 不支持 `--no-open` 时由 dsh 自己开浏览器，`service`
   目标无法阻止——这与既有 `open_browser=False` 的限制同源（启动前无法可靠探测：探测本身
   就是 `dsh web --help`，而旧版传参会启动失败）。§五第 3 条给出本机的实测判定（本机
   dsh **支持** `--no-open`，真实命令行确实带该参数）。
5. **设置页文案与行为必须同口径**。`auto` 的文案由「自动（桌面端优先）」改为
   「自动（仅服务，不开界面）」——旧措辞描述的是被撤掉的语义，留着就是骗用户；原按平台
   二选一的三元表达式一并取消（`auto` 不再与平台相关），新增项插在 `auto` 之后，顺序
   「默认 → 显式要服务 → 显式要界面」。
6. **裁字是量出来的，不是猜的**。`ModernSelect.paintEvent` 直接 `drawText` 到
   `QRectF(10, 0, width()-34, height())`，没有 elide，超宽即裁。规格给定的文案在对话框
   字体下最长项需 182px，而 190px 控件的文本区只有 156px。取舍：
   - 不用 `elidedText` 改 `paintEvent`：那会改变**所有** `ModernSelect` 的观感（越界）；
   - 不改短文案：文案是产品规格给定的；
   - 采用 `suggestedWidth()` + `setFixedWidth(max(190, …))`：只影响这一个控件，且把内缩口径
     收在画它的控件里，别的调用方加长文案时不必再手算固定宽度。

## 四、性能分析

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen python .scratch/harness-service/probe_service_target.py`
（脚本：`.scratch/harness-service/probe_service_target.py`，原始输出：
`.scratch/harness-service/PROBE-20261006.log`；`.scratch/` 在 `.gitignore` 内，未进提交）
环境：Windows 10 x64 / Python 3.13 / 本机**已安装 DeepSeek Harness 桌面端**（默认安装位
命中，探针运行时有 5 个桌面端进程在跑）。`suggestedWidth()` 那行先做一次预热调用再计时。

| 指标 | 实测（中位 / 最坏，n） | 归属 |
|---|---|---|
| `resolve_launch_target("auto")` | **0.20µs** / 2.30µs（n=200） | 既有指标，**成本下降**：改动前该分支内含一次 `desktop_install_path()`（下表 2 行） |
| `resolve_launch_target("service"/"web"/"desktop")` | 0.30µs / 0.40µs（n=200） | 只做字符串归一（与改动前一致） |
| `resolve_launch_target("bogus")` / `("")` | 0.30µs / 8.50µs、0.20µs / 0.40µs（n=200） | 非法/空值回落 `auto`，同样不做探测 |
| `desktop_install_path()`（默认安装位命中，不读注册表） | 51.2µs / 78.4µs（n=20） | 既有；**旧 `auto` 每次自启付一次，现在 0 次** |
| `desktop_process_running()`（全表 PID 枚举 + 逐 pid 取镜像名） | 11.66ms / 12.12ms（n=10） | 既有；**旧 `auto`→desktop 每次自启付一次，现在 0 次** |
| 新增代码：`ModernSelect.suggestedWidth()` | **20.20µs** / 151.00µs（n=1000，预热后） | 新增；**每次设置对话框构造调用一次** |
| 设置对话框构造（含上面那一次调用） | 730ms | 既有；新增占比 **20.2µs / 730ms ≈ 0.0028%** |
| 下拉多一项的分配量（tracemalloc，200 次重复） | **+1665 B / 控件** | 新增；一个常驻控件的「字符串 + 元组槽位」 |
| 真实设置对话框上下文（字体由对话框给） | 控件 **216px**／文本区 **182px**／最长项 **182px**；四项 156 / 182 / 130 / 65px **全部完整** | 新增（改动前控件 190px／文本区 156px ⇒ 最长项被裁 26px） |

**结论**（逐条回答）：

1. **稳态开销无变化**。没有新增线程、定时器、轮询、网络或磁盘写；唯一新增的常驻物是一个
   下拉项的字符串（1665 B/控件，控件本来就常驻）。自启是一次性动作，改动后每次自启**少付**
   约 **11.7ms**（51.2µs 安装探测 + 11.66ms 进程枚举）外加**不再派生一个 Electron GUI 进程**。
2. **新增路径的绝对成本与触发频率**：`suggestedWidth()` 20.2µs（最坏 151µs），触发点是
   **设置对话框构造**（不是每次绘制、不是每次切页），相对同一次构造 730ms 可忽略
   （0.0028%）。`service` 分支本身的成本是一次布尔赋值（实测低于探针分辨率，取
   `resolve_launch_target` 的 0.2–0.3µs 量级为上限）。
3. **有没有引入新的系统调用 / 网络 / 磁盘 / 线程：零**。方向是**减少**：`auto` 不再做
   文件系统 `is_file` 探测、不再走注册表兜底、不再做全表 PID 枚举、不再 `Popen` 桌面端；
   `service` 路径**不派生**等待线程（新用例用 `threading.Thread` 替身计数断言 `threads == []`）。
   注意 `service` 仍走 web 路径，因此原有的端口探测与 `_spawn` 开销不变（这是「起服务」本身
   的成本，不是本批引入）。
4. **内存与缓存无增长**：没有新增缓存或长驻容器；`ModernSelect._items` 多一个
   `(str, str)` 元组，实测 +1665 B/控件；`_NO_OPEN_CACHE`、`_SELF_LAUNCHED_*` 等既有容器
   本批一行未改。

## 五、实机运行记录

本机：Windows 10 x64，真实开发机（非 CI、非 mock）。

1. **前提现场复现（旧行为真实存在）**：
   - 本机桌面端安装位命中，且探针运行时有 5 个桌面端进程在跑（原始输出）：

     ```text
     DESKTOP_SUPPORTED = True
     desktop_install_path() = C:\Users\me\AppData\Local\Programs\DeepSeek Harness\DeepSeek Harness.exe
     desktop 进程数 = 5
     ```
   - **旧版对照**（2026-10-06 22:06，旧构建部署在 `D:/dsh-pet`）：桌宠启动 **9 秒后**拉起
     DeepSeek Harness 桌面端，桌面端 **5 个进程**。
2. **用户可见行为确认（新构建，2026-10-06 23:36，同一部署树 `D:/dsh-pet`）**——本节由
   用户/主代理在真机部署后采集，照录：
   - 新构建 **545.7MB** portable zip 部署到 `D:/dsh-pet`；
   - **23:36:46** 桌宠启动；
   - **23:36:54**（启动后 8 秒）拉起
     `node .../dsh/lib/bin.js web --host 127.0.0.1 --port 38080 --no-open`（PID **16364**），
     随后 **38080 LISTENING**；
   - **全程无新的 DeepSeek Harness 桌面端进程、无浏览器被打开**。

   即：同一条自启路径，旧构建拉起的是桌面端 GUI，新构建拉起的是 headless 服务 —— 本批的
   用户可见差异就是这两条。
3. **本机真实探测（命令 + 原始输出）**：
   - `resolve_launch_target` 全表（改动后，真实解释器）：

     ```text
     'auto'     -> 'service'
     'service'  -> 'service'
     'web'      -> 'web'
     'desktop'  -> 'desktop'
     'AUTO'     -> 'service'
     'bogus'    -> 'service'
     ''         -> 'service'
     ```
   - 真实启动命令解析（走产品函数，非替身）：
     `_find_launch_command(38080)` → `['cmd.exe', '/c', 'C:\\Users\\me\\AppData\\Roaming\\npm\\dsh.CMD', 'web', '--host', '127.0.0.1', '--port', '38080', '--no-open']`（耗时 5.35s）；
     缓存 `_NO_OPEN_CACHE = {('C:\\Users\\me\\AppData\\Roaming\\npm\\dsh.CMD',): True}` ——
     即**本机 dsh 支持 `--no-open`**，§三第 4 条那条遗留限制在本机不成立。
   - 诚实附注（不是本次引入、也不在本次 diff 内）：用裸名 `_supports_no_open(["dsh"])` 查询
     得到 `False`（13.8ms 返回，命中按基础命令为键的一条缓存）；产品实际使用的是解析后的
     `dsh.CMD` 路径为键，结果 `True`。两把键不同，本批未触及该缓存逻辑。
4. **边界与失败路径（真实观察）**：非法值 `"bogus"` / 空串 → `service`（既不是 `desktop`，
   也不会「什么都不做」）；旧配置里的 `desktop` 仍解析为 `desktop`（现仍由既有用例与设置页
   置灰逻辑守住）。
5. **无法在真机验证的能力（如实登记）**：
   - **非 Windows**：本批语义在非 Windows 上由 `DESKTOP_SUPPORTED=False` 的能力位与既有
     用例（桌面端项置灰、回落、保存边界拒写）覆盖；**没有 mac/Linux 真机**，未做实机验收；
   - **设置页 GUI 截图**：本次**未做**。本环境只能起 offscreen 渲染，无法起真实显示会话去
     截图；替代探针是同一对话框在 offscreen 下的字体度量（§四末行：控件 216px / 文本区
     182px / 四项 156·182·130·65px 全部完整），它能**直接判定有无裁字**，但不能判定真实
     主题、DPI 与窄宽度下的观感 —— 这一格留给有显示会话的人。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests` | `All checks passed!` |
| 空白检查 | `git diff --check` | 干净 |
| 聚焦（本轮改动域） | `pytest -q tests/test_harness_launcher.py tests/test_harness_ownership.py tests/test_requested_regressions.py tests/test_config_schema.py` | **138 passed, 1 skipped** |
| 聚焦（扩到设置/托盘域） | 上列 + `test_settings_and_resources` / `test_settings_overlay_copy` / `test_settings_event_gating` / `test_settings_process_isolation` / `test_settings_subslot_autostart` / `test_menu_layout` / `test_config_*` | **266 passed, 1 skipped**（66s） |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **4314 passed, 11 skipped**，594.23s，exit 0 |
| 验收对象一致性 | `git diff \| sha256sum`（运行前）与 `git diff HEAD~1 HEAD \| sha256sum` 同值 | 两者均为 `a76e367f…`，即**全量跑的就是提交 `b0e28f2` 的内容** |
| 架构红线 | `pytest -q tests/test_architecture.py` | **10 passed**（含 `modern_settings_dialog.py` 行数 2400 ≤ 预算 2407，只剩 7 行余量） |
| 断言有效性（消融） | 见下表 | 6 条新用例能区分新旧实现 |
| 交付纪律 | `pytest -q tests/test_pr_report_discipline.py` | 本报告写入后、未登记时 **1 failed**（`test_report_is_registered_in_index[PR-REPORT-HARNESS-SERVICE-TARGET-2026-10-06.md]`，报错原文：「未在 docs/INDEX.md 登记（新文档入场规则第 1 条）」）；在 `docs/INDEX.md` 登记后 **73 passed**（0.95s） |

**红 → 绿证据（test-first）**：实现前先写/改用例，四条独立红：

```text
tests/test_harness_launcher.py                              5 failed, 27 passed
tests/test_config_schema.py -k harness_launch_target        1 failed, 1 passed
tests/test_requested_regressions.py -k harness_target_offers_service   1 failed
tests/test_harness_ownership.py -k autostart_default_target_starts_service   1 failed
```

实现后：`launcher + config` 49 passed；`requested_regressions` 48 passed / 1 skipped；
`ownership` 40 passed。红的原因是语义本身（`'web' == 'service'`、`'自动（桌面端优先）' ==
'自动（仅服务，不开界面）'`、自启时服务根本没被拉起），不是测试写错。

**消融表（临时注入缺陷后重跑，逐个复原）**：

| 注入的缺陷（= 退回旧实现） | 结果 |
|---|---|
| `resolve_launch_target` 的 `auto` 改回 `desktop if desktop_install_path() else "service"` | **2 failed**：`test_auto_resolves_to_service_without_probing_desktop`（auto 碰了桌面端探测替身）、`test_autostart_default_target_starts_service_without_gui_or_browser`（服务没被拉起、`_spawn_desktop` 反被调用） |
| 去掉 `if resolved == "service": open_browser = False` | **3 failed**：`test_auto_launch_is_headless_service`、`test_service_target_stays_headless_even_with_open_browser_true`、`test_service_target_does_not_open_browser_on_reused_instance`。自启端到端用例**仍绿**——因为 `pet/app.py` 自启路径本来就传 `open_browser=False`，这一格的判别只能由 launcher 层用例承担（这正是同时保留两层用例的理由） |
| 控件宽度退回写死 190px | **1 failed**：`test_harness_target_select_width_fits_its_longest_item`；复原后即绿 |

## 七、已知限制与后续

1. **分支未 push、PR 未开**：提交 `b0e28f2` 只在本地 `feature/harness-service-autostart`；
   对外提交（push / 开 PR）需用户明确点头。
2. **`launch_harness_gui` 的 started 冒泡文案未按目标分叉**（`pet/harness_launcher.py:1222`
   附近）：它对 `started` 固定说「就绪后会自动打开浏览器……」，若调用方不传 `target`
   （默认 `auto` → `service`）这句就是假的。当前产品内所有菜单入口都显式传 `web` / `desktop`
   （`pet/context_menus/shared.py:561`、`pet/app.py:3558-3559`），所以**不可达**；是否顺手
   分叉文案留给决策。
3. **`launch_harness()` 的签名默认 `target="auto"` 现在语义上是 headless**：三条依赖裸调用
   开浏览器的既有用例已显式改传 `target="web"`。若希望裸调用仍开浏览器，需改默认值
   （本批未改，规格未要求）。
4. **旧版 dsh（不支持 `--no-open`）在 `service` 目标下仍会自己开浏览器**：启动前无法可靠
   判定（探测即 `dsh web --help`，旧版传参会启动失败），与既有 `open_browser=False` 同源。
   本机 dsh 支持该参数（§五第 3 条），故本机不受影响。
5. **`pet/modern_settings_dialog.py` 只剩 7 行余量**（2400 / 预算 2407，本批 +6）：下一次改
   这个文件前建议先按结构线拆分，而不是再抬预算。
6. **非 Windows 真机未验、设置页 GUI 截图未做**（§五第 5 条给出理由与替代探针）。
7. **本报告的归档性质**：本报告承接 DUAL-TARGET 报告里的 `auto` 语义，但**没有**回改那份
   归档（见 §二「未改动」）；两份报告并存时，`auto` 的现行语义以本报告为准。

## 八、风险与回滚

- **影响面**：仅「随桌宠启动」这一条路（`pet/app.py::_maybe_autostart_harness` →
   `launch_harness(target=配置值)`）+ 设置页「自启目标」一行。菜单 / 托盘 / 重启 / 停止全部
   显式传 `target`，不受影响；`desktop` 目标与桌面端的「只登记不杀」归属收口一行未动。
- **用户可见变化**：装了桌面端且开着自启的用户，启动桌宠后看到的是**服务常驻**而不是桌面端
   窗口弹出来 —— 这正是本批目标；设置页多一项、`auto` 文案变化。
- **配置迁移**：无新键、无格式变更、默认值仍 `auto`。老配置里写死的 `web` / `desktop` 照旧
   生效；写 `auto`（默认）或非法值的机器，自启行为由「可能拉 GUI」变为「只起服务」——
   这是**有意的行为变更**，不是迁移事故。所有 `auto` 用户在自启路径上都不开浏览器（改动前
   也是），所以浏览器侧零差异。
- **回滚**：`git revert b0e28f2` 或直接丢弃分支即可；无落盘数据残留（无新键、无缓存格式
  变化、无迁移代码），回滚后 `auto` 恢复「装了就拉 GUI」。已构建并部署到 `D:/dsh-pet` 的
   545.7MB portable zip 需重新构建才算回滚到旧行为，**部署树本身没有本次改动写入的任何状态**。
