# v4.3.4 成体系修复：两个模型盲审 + 逐条红绿

> 分支 `release/v4.3.3`（发布前改版本号为 4.3.4），基线 v4.3.3 = `a4c8b7f`。
> 触发原因：v4.3.3 发布数小时内两位用户报告仍无声（#307 及另一位），用户明确要求
> 「从 4.3.0 到这次任务的修复都过一遍，不想再出一点小问题修一点」。

## 一、方法：先归纳模式，再找全部实例

盲审由两个独立模型执行（`gpt-6-astra` 全面审查 + `Agents-A1` 复核），均为**只读**、
基于 `git log v4.3.0..HEAD` 与代码取证。第二轮的任务不是复述第一轮，而是核对
「每条是否真修好」并**继续找同一模式的漏网实例**。

最终归纳出七类模式：

| 模式 | 本批修复的实例 |
|---|---|
| **读写作用域分裂**（每宠键用主配置读） | 点击朗读判据、音频通道生命周期、主宠 `cfg`、chat 会话角色、灵动岛名、主动识屏 `pet_name`、托盘角色勾选 |
| **运行态与持久态两套身份** | 拖到副屏后 `home_screen` 更新但 `screen_name`／待写归属没更新 |
| **输入范围扩张、通知范围没扩张** | 刷新率取数枚举全部屏，但只订阅窗口自己那块屏 |
| **「调用成功」冒充「交付成功」** | 待办/报时/节日的气泡返回 False 却被当成已送达 |
| **缓存键不是实际计算输入的指纹** | 台词纯文本键（换音色永不更新）、报时键用配置原音色而非 resolved 音色 |
| **单飞防重变丢更新、开启门没有运行期撤销** | 预缓存合成期间保存被丢弃、关开关不停止后续句子 |
| **测试按内部捷径验证** | 跨屏持久化绕过鼠标拖拽；缓存 expected 复用错误配置；作用域测试抹平 slot/global |

## 二、修改文件说明

产品代码（净改动）：

逐文件增删（`git diff --numstat origin/main..HEAD`，产品代码 21 个文件 +1370/−250，
测试 18 个文件 +1514/−51，合计 +3142/−301 含文档）：

| 文件 | +/− | 一句话 |
|---|---|---|
| `pet/overlay_shell.py` | +582/−58 | 每屏一窗、跨屏投影与会话、逐宿主几何/DPR/岛/弹弓、缩放翻转重排宿主 |
| `pet/self_talk_voice.py` | +144/−35 | 缓存键改 flavor 指纹、预缓存补跑与取消 |
| `pet/app.py` | +120/−42 | 每宠视图（点击朗读判据 / chat 角色 / 身份）、音频通道生命周期 |
| `pet/overlay_window.py` | +98/−7 | 投影绘制与旧矩形记账、刷新率/几何、气泡跟随换窗 |
| `pet/fps_monitor.py` | +56/−1 | 残留 ETW 会话清理（进程内一次） |
| `pet/todo_reminder.py` | +50/−22 | 气泡未送达改道通知、每日跨午夜宽限 |
| `pet/island_bridge.py` | +45/−1 | 墙按岛所在屏绑定/重绑 |
| `pet/voice_chime_service.py` | +42/−21 | 缓存键 resolved attempt、气泡被占不静默 |
| `pet/festival_service.py` | +35/−19 | 与报时同型修复 |
| `pet/game_fps.py` | +34/−0 | `parse_session_names` / `stale_session_names` / `stop_session_args`（纯函数） |
| `pet/modern_settings_dialog.py` | +32/−10 | 点击内容设置显隐解耦 |
| `pet/proactive.py` | +25/−5 | 角色身份走 provider |
| `pet/sprite_slingshot.py` | +25/−3 | 会话记 owner，只有 owner 画/Esc 路由 |
| `pet/dynamic_island.py` | +21/−2 | 岛名走身份视图 |
| `pet/sprite_menu_facade.py` | +20/−6 | 右键菜单按宿主取控制器、图标取帧 |
| `pet/voice_chime.py` | +11/−4 | `cache_key` 接受 `values=` |
| `pet/window.py` | +10/−5 | legacy `show_bubble` 返回布尔 |
| `pet/settings_interaction.py` | +8/−3 | 同上显隐解耦的设置面 |
| `pet/multi_window_shared.py` | +6/−3 | 扇出目标取壳 |
| `pet/sprite_sound.py` | +5/−2 | 点击音效多文件现挑（#308） |
| `pet/__init__.py` | +1/−1 | 版本号 4.3.4 |

测试：18 个文件 +1514/−51，新增回归约 60 条（`test_overlay_hosts_multiscreen.py`
新增 8 条含缩放翻转与物理拖拽域、`test_island_multiscreen_hosts.py` 新增拔屏重绑、
`test_fps_monitor.py` 新增 6 条清理闸门/前缀/失败路径），另有两条旧断言按新契约改写
（空洞钳制点移到松手、拖动中的钳制域改为整窗）。


| 文件 | 改了什么 + 为什么 |
|---|---|
| `pet/overlay_shell.py` | `cfg` 改回**主宠每宠视图**（点击朗读/台词池/角色都读它）；新增 `_mixed_dpr()` / `_multi_window()`：混合缩放 + 允许跨屏时**每块屏一张窗**（一窗只能一个 DPR），跨屏 = **拖拽期间不换窗**（这只仍在源窗积分），邻窗挂带缩放的只读投影补另一半、松手才按物理位置提交归属（局部坐标经全局中转）；关闭跨屏时仍单窗并退化为家屏；`_activity_rects` 多窗下按宿主；拖拽收尾补记屏幕归属并**松手即落盘**（且只在原归属屏仍在线时算有意换屏，拔屏的临时承载不动归属）；`move_sprite_to_screen` 改按活动区判定；全屏订阅 `refreshRateChanged` 并接/摘一致 |
| `pet/app.py` | `_self_talk_speak_wanted` 改读每宠视图；`_self_talk_voice_configs` 修正底层表名（`_instances`）与测试桩容错；`_sync_chat_sessions` 的角色走 `_identity_config()`；`_identity_config()` 新增，供灵动岛/托盘/识屏取当前呈现身份 |
| `pet/todo_reminder.py` | 气泡返回 False 时改道系统通知（不再吞掉）；`_daily_due` 枚举昨天/今天/明天，跨午夜宽限窗生效 |
| `pet/window.py` | legacy `show_bubble` 返回布尔，与 overlay 同契约 |
| `pet/voice_chime_service.py` | 气泡被占时不再静默；缓存键改用 attempt 的 resolved `provider+values`；设置页抑制期的直写抽成 `_bubble_in_slot` |
| `pet/festival_service.py` | 与报时同型修复 |
| `pet/self_talk_voice.py` | 缓存键加 `provider.flavor(values)`；经典文本 wav 降为兼容来源；`_pending_run` 支持补跑与取消 |
| `pet/voice_chime.py` | `cache_key` 接受 `values=`（三处调用共用同一份 resolved attempt） |
| `pet/dynamic_island.py` / `pet/proactive.py` / `pet/multi_window_shared.py` | 角色身份经 provider 取，不再读全局 `character` |
| `pet/modern_settings_dialog.py` / `pet/settings_interaction.py` | 点击内容设置（文本/配图目录/概率/时长）改为「周期或点击任一开启」即显示；节奏项仍只跟周期 |
| `pet/game_fps.py` | 新增 `parse_session_names` / `stale_session_names` / `stop_session_args`（纯函数）：按 `dsh-pet-fps-` 前缀列出本应用自己的 ETW 会话、排除本次会话名、生成精确停止命令 |
| `pet/fps_monitor.py` | 新增模块级 `sweep_stale_sessions(session_name)`，由会话工厂 `default_session()` 在**建会话之前**调用：清掉异常退出遗留的残留 ETW 会话（Windows trace 会话有上限，攒满后新会话报 `error 1450`）。放在工厂而不是 `FpsSession.start()`：清残留是「准备新采集」的前置动作，且它要再起两个 `logman` 子进程，不该被会话自己的进程替身记账。**一个进程只扫一次**（查询实测 970 ms，残留只来自上一个被强杀的进程） |

测试：新增 `tests/test_process_service_identity.py`；改写两条把 bug 写成契约的断言
（`test_precache_worker_uses_resolved_voice` 用旧 `_cfg` 造 expected；
`test_click_self_talk_rows_follow_their_own_toggle` 断言「只开点击时内容项隐藏」）；
新增约 25 条回归，全部先红后绿。

## 三、性能分析

| 路径 | 开销 | 触发频率 |
|---|---|---|
| 拖拽收尾多一次几何自存 | 中位 3.4 ms（一次性原子写） | 用户每次拖拽结束 |
| `_mixed_dpr()` | 每屏一次 `devicePixelRatio()` 比较（屏集合通常在个位数） | 建壳、几何同步，**以及每拍**：`_advance_screen_sync` → `_screen_of_sprite` → `_multi_window()` 这条链每 tick 判一次 |
| 台词点击查找 | 0.071 → 0.265 ms（flavor 解析 0.038 ms，且不再读钥匙串；磁盘侧由整目录 glob 变按 flavor 键的精确查找，每次查找内含 `stat` + 打开文件读 12 字节头校验） | 每次点击 |
| `_attempts` 每轮解析 | 0.7–1.6 ms | 每次预缓存批次（一次，非每句） |
| `refreshRateChanged` 接线 | 每块屏一条信号连接 | 改刷新率/插拔屏 |
| 残留 ETW 会话清理 | `logman query -ets` 实测 **970 ms** 中位（Windows 11 + Python 3.13 + `subprocess.run` 采样 5 次，本机空闲态；首末次 965–978 ms），每个残留会话 1 次 `logman stop <name> -ets` **56 ms**（均不需管理员）；**一个进程只跑一次** | 进程内第一次开采集会话时（历史现场 N=11，约 1.6 s 一次性，跑在 `FpsMonitor._run` 工作线程上） |

无新增线程、定时器、网络请求；常驻内存无增长路径（`deque` 上限均在模块常量里，清理只读命令输出）。

## 四、实机运行记录

- 本机双屏（主屏 2560×1440 avail 1392 @170Hz + 左侧副屏 1920×1080 avail 1032 @60Hz，
  DPR 均为 1.0）：部署 v4.3.3 后实测合成窗 `(-1920,0,4480,1392)`、tick 6ms、帧序列
  106 段，跨屏拖拽/探头/设置说明均正常（用户当场确认「用起来正常了」）。
- 混合缩放部署后核验（125% 副屏）：枚举进程全部可见顶层窗，得到
  `(-1920,0,1920×1020)` 与 `(0,0,2560×1392)` —— 每块屏一张、各自物理尺寸正确；
  整屏截图（虚拟桌面 `-1920,0 4480×1440`）确认三只桌宠分别画在对应屏上、
  无裁切、无错位；工作集 215 MB。
- 台词语音：用用户真实配置（slot0 档案 22 句）跑预缓存 → **22 句全成、0 失败**，
  26.5 s；`cached_audio` 命中验证通过。
- SAPI 线程 COM：修复前后台线程 `WinError -2147221008`，修复后同线程取到 3 个音色、
  真合成 60 872 字节 wav。
- 混合缩放（#307 问题一、#286 的相邻症状）：把左侧副屏调到 **125%**（物理 1920×1020、
  逻辑 1536×816）后实机验证——跨屏拖拽连续过缝、到副屏后能继续拖、跨窗投影位置跟随
  光标、副屏子宠动画正常。验证期间暴露并修掉的一批多窗缺口见发布稿 `docs/RELEASE-v4.3.4.md` §六点五。
- 混合 DPI 坐标探针（`.scratch/probe-screens.py`，本机实测）：Win32 原生 `\.\DISPLAY2`
  为 `(-1920,0,1920,1080)`，Qt 报 `geometry=(-1920,0,1536,864)` —— 原点是原生、宽高是
  逻辑，`native/dpr` 应为 `(-1536,0,1536,864)`。即 Qt 6.12 在 Windows 上对负原点屏
  返回混合坐标系（issue #310 的根因在**本机就真实存在**），只是每屏一窗让那个坐标
  不参与运算；单窗路径（多屏同 DPR≠1）会复现。已按「多屏且任意屏 DPR≠1 → 每屏一窗」
  修掉。
- issue #311 附带的第二个崩溃路径已本机复现：`island_collision._wall_active` 对
  `None` 调 `isVisible()`，行号（273）与报告完全一致；护栏加在判空处与「没岛不建
  碰撞体」两处。
- FPS 不出数的现场证据：`logman query -ets` 实抓到 **11 个** `Running` 的
  `dsh-pet-fps-*` 残留会话（`-15520-37-b4e46ca9`、`-17840-14`、`-33764-85`、
  `-31060-20`、`-33980-7`、`-9956-16`、`-33764-62`、`-24896-1`、`-30960-12`、
  `-38784-1`、`-22572-1`），而 `logman stop <名字> -ets` **不需要管理员**即成功。
  这解释了新会话 `error 1450`（`ERROR_NO_SYSTEM_RESOURCES`）：不是权限不够。
  修复已随包部署，**用户开游戏复核尚未回**——本条按「代码级 + 现场证据」记录，
  不声称已实测出数。

## 五、测试与验证

全部命令都在本机（Windows 11 / Python 3.13 / `QT_QPA_PLATFORM=offscreen`）执行，
`-p no:randomly` 固定顺序以便复现：

| 命令 | 结果 |
|---|---|
| `python -m pytest -q -p no:randomly`（全量） | `8264 passed, 14 skipped`（28 分 01 秒，日志 `.scratch/full-final4.log`；该轮之后又落了两条改动，见下） |
| 交付前收尾两轮的聚焦族（`test_fps_monitor.py` `test_game_fps.py`） | 126 passed |
| 多屏族（`test_overlay_hosts_multiscreen` `test_island_multiscreen_hosts` `test_sprite_bubble` `test_overlay_seam_passage` `test_overlay_cross_screen_switch` `test_overlay_virtual_desktop` `test_overlay_independent_screens`） | 159 passed |
| `docs/test_pr_report_discipline` 系 | 197 passed |
| `ruff check pet/ tests/` | All checks passed |

**先红后绿**：本轮收尾新增的 5 条用例（主宠气泡换窗重绑、主宠 runtime 监听换窗、
运行中改缩放翻转拓扑后重排宿主、拖拽域覆盖高 DPI 屏物理范围、拔屏后岛墙重绑）
在还原 `pet/overlay_shell.py` / `pet/sprite_bubble.py` 到修复前状态时全部失败，
恢复修复后全部通过。

**没跑到的那一轮要说清**：最后两条改动（多窗日志文案按真实路径分流、残留清理改一个
进程一次）之后没有再跑全量——按用户指示直接进入交付审查。它们的影响面是
`overlay_shell._create_host` 的一条日志与 `fps_monitor` 的清理时机，
相关族已单跑通过（多屏族 159 条、FPS 族 126 条）。

## 六、风险与回滚

- **回滚方式**：整版回退到 `v4.3.3` 即可（无配置格式变更、无键改名、无迁移，
  新旧版本读同一份配置与素材）。
- **多窗是行为级改动**：混合缩放下从一张窗变成每屏一窗。API 未变，但窗口数量与
  枚举形态变了——OBS 等按窗口捕获的工具在 overlay 拓扑下本来就只能看到「一个有标题
  的窗口」（捕获模式另算），本版未改这条语义。
- **最坏情况**：多窗在某些三方 DPI 工具（如非整数缩放的强制覆盖）下几何取不到，
  代码回退到逻辑原点并在日志留 warning；此时跨屏投影会偏。留了
  `_window_physical_origin` 的 fallback 分支与日志，便于现场定位。

## 七、已知未修（如实）

- **#286**（150% DPI 下点不到、legacy 拖不动）需要该缩放环境 + 现场探针；报告者的
  「活跃清单启动不注册」经核为代码注释写明的有意设计（启动期不替用户改盘）。
- `VoiceChimeService.apply_config()` 不中止**已起飞**的合成：已提交的句子用旧音色
  播完属可接受契约，未改。
- 待办 fire 的「每档一次」戳语义未改：气泡+通知双不通时只留 warning，不无限重试。
- 跨窗拖拽期间没有碰撞（拖到另一块屏、仍按着鼠标时能与那只屏上的宠重叠，松手归窗后才分离）；
  岛横跨两屏缝上时墙只建在岛所在那块屏的世界里。两条都由用户明确同意留到下一版。

## 八、10-19 补充：快捷键 / Ctrl+F / 打包与凭据（astra 第 13–14 轮）

首轮报告封稿之后又落了三个功能提交与一轮审查修正，这里补齐它们的修改文件与证据。
前七节结论不受影响。

### 8.1 修改文件

| 提交 | 文件 | +/− | 一句话 |
|---|---|---|---|
| `69d5dfe` | `pet/hotkey_spec.py`（新） | +162 | 键位口径：解析/规范化/VK 表，零 Qt、零 Win32，可纯函数测 |
| | `pet/hotkeys.py`（新） | +225 | `GlobalHotkeyService`：`RegisterHotKey` + 原生 `WM_HOTKEY` 过滤，被占用/失败可见 |
| | `pet/settings_hotkeys.py`（新） | +168 | 互动域第五个页内标签「快捷键」，三行录入 |
| | `pet/platform_win.py` | +33 | 注册/注销两个 ctypes 封装 |
| | `pet/app.py` | +80 | 三处接线：安装 / 外部配置变更后重装 / 退出注销 |
| | `pet/config.py` | +15 | `hotkey_open_chat`、`hotkey_look_screen`、`hotkey_screen_capture`（默认 `""`） |
| | `pet/settings_interaction.py`、`pet/settings_page_guide.py`、`pet/modern_settings_dialog.py` | +15 | 标签注册与搜索索引 |
| `aeb9854` | `pet/modern_settings_dialog.py` | +19 | `Ctrl+F` → 聚焦搜索框（Qt6 里 `QShortcut` 在 QtGui） |
| | `pet/settings_about.py` | +21 | 作者行按 `SettingRow` 同形暴露 `label`/`hint_label`，进搜索索引（排版不变） |
| `c4f2e43` | `pet/chat/models.py` | +51 | 凭据存储不可用/读写失败不再静默；后端判据从「能 import」升级为「后端可用」 |
| | `scripts/build_onedir.ps1` | +7 | Windows 构建期 `--collect-all win32ctypes` |
| | `scripts/verify_bundle_tts.py` | +4 | 产物门禁加 keyring 的 Windows 后端依赖 |
| | `requirements.txt` | +6 | 显式声明 `pywin32-ctypes`（不靠 keyring 带） |
| 本轮 | `scripts/verify_bundle_tts.py` | +23/−8 | `WINDOWS_ONLY_MODULES` + `platform_modules()`：Windows-only 依赖只在该平台目标上要求 |
| | `pet/chat/models.py` | +22/−6 | `_is_placeholder_backend()`：只认 `keyring.backends.fail` / `.null` 两个占位类 |
| | `tests/test_verify_bundle_tts.py` | +47 | 三条门禁用例：linux/darwin 不要求、win32 必须要求、`platform_modules` 归零 |
| | `tests/test_chat_subsystem.py` | +53 | 七条：第三方 `failover` 后端保留、`null` 后端拒绝、五个真实平台后端保留 |
| `1e89d9f` | `pet/modern_settings_dialog.py` | +17/−4 | 设置页搜索：`_search_settings` 改成 `advance: int` 步长，eventFilter 加 ↑/↓（首条按 ↑ 回绕） |
| | `tests/test_settings_search_aliases.py` | +41 | 两条方向键用例（↓ 前进两条再 ↑ 退回；第一条 ↑ 回绕到最后） |

### 8.2 红绿（本轮，先红后绿实测）

把 `pet/chat/models.py` 与 `scripts/verify_bundle_tts.py` 暂退回 HEAD 再跑：

```
FAILED test_verify_bundle_tts.py::test_platform_modules_is_empty_off_windows
FAILED test_verify_bundle_tts.py::test_windows_only_modules_are_not_required_on_other_targets[linux]
FAILED test_verify_bundle_tts.py::test_windows_only_modules_are_not_required_on_other_targets[darwin]
FAILED test_verify_bundle_tts.py::test_windows_target_still_requires_its_backend_dependency
FAILED test_chat_subsystem.py::test_secret_store_keeps_a_third_party_backend_whose_name_mentions_fail
   （旧判据下 `assert False is True`：`company.failover.Keyring` 被判成"没有钥匙串"）
6 failed
```

恢复产品代码后：`test_verify_bundle_tts.py + test_packaging_keyring_notices.py` 33 passed；
`test_chat_subsystem.py + test_config_key_migration.py + test_settings_reset_defaults.py`
186 passed, 1 skipped；`ruff check` 全过。

### 8.3 产物与真机证据（本轮补，只读/可逆；每条标明执行宿主与命令）

**证据分三层，层次不可互相代替**——`a` 是"包里有什么"，`b` 是"同版本解释器能加载包内文件"，
`c` 是"这台机器的 OS 凭据库能跨进程持久"。**没有一条是在冻结 exe 进程里跑的**。

**a. 旧部署 exe 的内嵌 PYZ 清单**（执行宿主：打包机 CPython 3.13，脚本见下）

```python
from PyInstaller.archive.readers import CArchiveReader
r = CArchiveReader(r"D:\dsh-pet\dsh-pet-standalone-webm-chat.exe")
mods = set()
for name, entry in r.toc.items():
    if entry[-1] == "z":
        mods |= set(r.open_embedded_archive(name).toc.keys())
```

原始输出：

```
== D:\dsh-pet\dsh-pet-standalone-webm-chat.exe  (PYZ modules: 2902)
   keyring                            OK 28
   keyring.backends.Windows           OK 1
   win32ctypes                        OK 27
   win32ctypes.pywin32.win32cred      OK 1
   win32ctypes.core                   OK 21
== dist-onedir\...\dsh-pet-standalone-webm-chat.exe  (PYZ modules: 2912)
   win32ctypes                        OK 34
```

→ **4.3.3 与 4.3.4 的包都带着这个依赖**，"缺模块导致 401"不成立。

**b. 包内文件的外部解释器导入**（执行宿主：打包机 CPython 3.13，cwd 为产物目录）

```
python -S -c "import sys; sys.path.insert(0,'_internal'); import win32ctypes.pywin32.win32cred as m; print(m.__file__)"
→ frozen pyd import OK: \win32ctypes\pywin32\win32cred.py
```

`-S` 屏蔽系统 site-packages，所以加载的是包内那份源码。**边界**：这是"同版本解释器
能加载包内文件"，`keyring` 本体在此路径下会因 `jaraco` 只在 PYZ 里而 ImportError——
这正说明这条路径**不等于冻结运行时**，不要拿它当"冻结进程已验证"。

**c. 跨进程凭据往返**（执行宿主：打包机 CPython 3.13，三个独立 `python -c` 进程；
用的是 `probe-<uuid>` 探针串，**未触碰任何真实 API Key**）

```
BACKEND = keyring.backends.Windows.WinVaultKeyring
write -> ok (pid differs next call)
read back in a NEW process: 'secret-probe-097025eb...'
MATCH = True
cleaned: True
```

这证明"本机 Windows 凭据库 + keyring 25.7.0 的 WinVault 后端"跨进程持久正常。
**尚未做**：在冻结 exe 进程内完成写→读→删。冻结 exe 没有可注入代码的通用入口
（只有 `--settings` / `--settings-page` / `--ocr-worker` / `--uninstall-cleanup`），
不加调试入口就自动化不了。这一条转由实机验收覆盖：填一次 Key → 重启 → 设置页仍显示
已保存、日志无「凭据存储不可用」。是**未覆盖**，不是"已验证"。

**d. 三端门禁不再互相污染**：`platform_modules("linux") == platform_modules("darwin") == ()`，
`platform_modules("win32")` 仍要求 `win32ctypes.pywin32.win32cred`，反向用例保证
Windows 少带它仍以退出码 4 中止。**能力边界**：门禁校验的是模块名在不在，不校验父包
完整性与实际可导入性（这是既有清单校验的边界，不是本轮条件化引入的）。

### 8.4 结论修正

`c4f2e43` 的**提交标题写错了因果**（"没打进包"）。它做的事仍然要留——显式收集把一条
隐式的 PyInstaller hook 行为变成构建期可知的一件事，凭据读写失败不再静默也是对的——
但它**不是那次 401 的根因修复**。发布稿第七节已按实测重写这一段，读者以那里为准。

### 8.5 一次全量 segfault 的调查与收口（2026-10-19）

第一次最终全量（`572bb44`，**与 PyInstaller 构建并行**跑）在 64% 处
`Windows fatal exception: access violation`，崩点是
`tests/test_quiet_mode.py::test_ticker_keeps_retrying_until_delivery_is_confirmed`
里的 `qapp.processEvents()`（`_spin`）。

| 步骤 | 结果 |
|---|---|
| 崩点单文件复跑 | `tests/test_quiet_mode.py` 60 passed（8.6 s），单独跑复现不出 |
| 崩溃线程快照 | `mem_debug._tick_loop`（`while True: sleep`）与 `_self_talk_loader_loop`（`queue.get` 阻塞）都不碰 Qt；`tests/conftest.py` 的 autouse fixture 每例复位 `mem_debug`/quiet/webm session latch |
| 干净环境全量（无并行构建） | **8377 passed, 14 skipped, 0 failed**（24:18），64% 那个点干净越过 |
| 高负载复跑（本机 CPU 打满，`test_quiet_mode.py` × 3） | 60 / 60 / 60 passed（40.8 s / 13.5 s / 13.8 s，首遍即满负载） |

**结论与边界**：**未复现，也没定性**。现有证据指向"全量 + 构建并行把 CPU 打满 →
`processEvents()` 里撞上偶发竞态"，但 access violation 不带 Python 帧，没有能定性的
栈。按仓库纪律已做高负载复跑，仍记为**已知偶发风险**，不写成"已修"。后续若再现，
排查入口是 `test_quiet_mode` 的 `_spin` / `_pump`（两者都是 `processEvents()` +
`sleep(0.005)` 的宽预算轮询），以及同一进程里残留的 `mem_debug` ticker 线程。
