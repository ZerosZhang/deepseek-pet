# PR 报告：产品级审查确认的 8 项缺陷修复 + 残留文案收尾

> **基线**：`dce895f`（分支 `release/2026-10-08-candidate`，本地分支不推送）
> **分支**：`release/2026-10-08-candidate`　**日期**：2026-10-08
> **范围**：23 个文件（实现 13、测试 7、文档 3），`+967 / −80`
> **关联**：[`PR-REPORT-RELEASE-CANDIDATE-DEPLOY-2026-10-08.md`](PR-REPORT-RELEASE-CANDIDATE-DEPLOY-2026-10-08.md)（同一分支的上一次部署快照）

## 一、核心特性

把一轮产品级审查**已确认**的 8 项缺陷逐条修掉，并收尾一批与现行实现不符的
文案/注释/文档。8 项按危害排序：

| # | 现象 | 根因一句话 |
|---|---|---|
| B1 | 直播捕获 / legacy 路径下「恢复默认设置」被静默撤销 | 设置进程「先写默认值、再写对齐指令」，主进程**先消费指令**（当场 `cfg.save()` 整表落盘）、**后**才按 300ms 去抖 reload；对齐那一刻运行期 Config 还是旧值，整表落盘把刚写的默认值覆盖回去 |
| B2 | 硬失败回合灵动岛仍亮绿点 + 卡片「刚完成」 | 桥接失败后先写 `execution/failed`、随后**仍无条件**转发同一条 `turn/end`，收敛器一律收敛 success，而 `dsh_state_changed.emit` 原样把 success 送给岛 |
| B3 | 硬失败提醒被免打扰压进暂存队列 | `_on_execution_failed` 调 `show_alert()` 没传 `alert_type`，落进默认的 `watchdog`（普通提醒档） |
| B4 | 首首歌 12s 内零帧歌词 | `_on_lyrics_ready` 先 `_bubble_blocked()` 早退（那条引导自己就占着 `_alert_current`），resolve 引导的代码排在它后面 ⇒ **不可达死代码** |
| B5 | 取词失败后同一首歌永不重试 | 冷却判定只在 `_start_track`（切歌路径），同曲轮询曲目 key 不变、永远走不到 |
| B6 | 保存失败时按 Esc 静默关窗丢草稿 | `reject()` 忽略 `_write_config()` 的返回值照常 `super().reject()`（X 路径一直有 `event.ignore()`） |
| B7 | 关掉天气开关后旧版菜单仍能加城市 | 停用门只在新版注册表；共享天气建造器自身无门，legacy 直调它 |
| B8 | 旧版音乐菜单缺「歌词对齐」入口 | 引导文案与设置页都指向「音乐 → 歌词对齐」，新注册表有、legacy 建造器没装 |

**红线 / 不变量**：不动 DSH 收敛器语义（八态是它的契约，只在**呈现侧**翻译）；
不动正常成功回合的岛绿点与完成提醒；不动免打扰的「只压普通提醒」口径（透传集的
分类器一字未改，只把调用点补上正确的类型）；不动菜单结构（Runtime Disabled =
位置保留 + 置灰 + 写明原因，**不是**整条消失）。

## 二、修改文件说明

`git diff --numstat dce895f..HEAD`：

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/settings_reset_defaults.py` | +39 / −1 | 新增 `reload_runtime_config(*configs)`（B1）：对齐前按磁盘拉齐运行期配置。复用既有的 `Config.reload`（外部变更合并口），同对象只重载一次，无 `reload` 接口的替身跳过。模块 docstring 的运行态对齐条目补上这条前置。
| `pet/app.py` | +9 / −0 | `AppShell.apply_settings_reset` 在调 `win.go_default_corner()` **之前** `reload_runtime_config(win.cfg, self.config)`（B1）。`go_default_corner` 一次做完落位 + `cfg.save()` 整表落盘，不先拉齐就是"整表覆盖回旧值"。 |
| `pet/overlay_shell.py` | +8 / −0 | `OverlayShell.apply_settings_reset` 同口径（B1）：这一只的几何由退出收口的 `save_position()` → `self._config.save()` 整表落盘，缺陷同源。 |
| `pet/agent_link.py` | +45 / −2 | ① 新增 `_island_state_for(to_state)`，`dsh_state_changed.emit` 改走它（B2）：`to_state == success` 且 `"dsh" in _saw_error` 时改发 `error`，**只翻译 success 一个值**；② 新增 `_FAIL_ALERT_TYPE = "execution/failed"` / `_FAIL_ALERT_PRIORITY = 1` 两个类常量，`_on_execution_failed` 经 `_show_alert_compat` 带上它们（B3）。 |
| `pet/music_lyric_controller.py` | +41 / −14 | ① `_on_lyrics_ready` 里 resolve `music-lyric-estimated` 的块移到 `_bubble_blocked()` 早退**之前**（B4，只精确收起那一条）；② 抽 `_request_lyrics(key, title, artist, playback, now)` 承载「在途去重 + 失败冷却」（B5），切歌与同曲轮询两处共用；③ 统一 `_no_lyric_until` / `_on_lyrics_ready` / `_primed` 三处与修复后行为冲突的注释。 |
| `pet/modern_settings_dialog.py` | +23 / −23 | ① `reject()` 与 `closeEvent` 的"关闭前落盘"抽成 `_save_before_close()`——两条路径共用一份判定，`reject()` 改为"没写成功就不关窗"（B6）。这个抽法是**行数预算逼出来的正解**：该文件有 2497 行的架构绊线（`test_architecture.py::test_modern_settings_dialog_py_line_budget`），直接给 `reject()` 加 7 行会顶破；抽成共用后净增 0 行，契约也从两处变一处。② Agent 联动折叠框注释改为"只装提示音效，消费统计已独立成一级分组"。
| `pet/weather_menu.py` | +37 / −2 | 新增 `WEATHER_DISABLED_REASON` / `weather_menu_enabled(pet)` / `_mark_disabled`（B7）：两个建造器自己落地 Runtime Disabled（`add_show_weather` 置灰 action、`add_weather_cities` 置灰子菜单的 `menuAction` ⇒ 展不开 ⇒ 添加城市不可达）。 |
| `pet/context_menus/registry.py` | +18 / −22 | 天气与歌词对齐的判据/原因改为**转发**共享模块的那一份（B7/B8）：`_WEATHER_DISABLED_REASON = WEATHER_DISABLED_REASON`、`_weather_enabled = weather_menu_enabled`、`_music_align_ready` 转发 `shared.music_align_ready`、`disabled_reason=MUSIC_ALIGN_DISABLED_REASON`；import 收拢成模块级 from。 |
| `pet/context_menus/shared.py` | +29 / −0 | 新增 `MUSIC_ALIGN_DISABLED_REASON` + `music_align_ready(pet)`，`add_music_lyric_align` 内部按它置灰（B8）；`isinstance` 校验搬到共享函数里（原先在注册表）。 |
| `pet/context_menus/legacy.py` | +6 / −0 | 音乐子菜单在 `add_music_quit` 之后、分隔线之前接入 `add_music_lyric_align`（B8），位置与新版默认布局一致。 |
| `pet/config.py` | +2 / −1 | `music_player_paths` 注释改为"也能在「设置 → 桌宠 → 播放器路径（高级）」里改"（原写"暂无设置页控件"）。 |
| `pet/settings_network.py` | +1 / −1 | 菜单入口文案由「关掉后菜单里不再出现该入口」改为实际的 Runtime Disabled 契约（保留 + 置灰 + 悬停说明）。 |
| `pet/settings_weather.py` | +2 / −1 | 同上：补上「关掉后菜单里保留这两个入口并置灰」。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_settings_reset_defaults.py` | +69 / −0 | B1 两条：两个独立 `Config` 实例（运行期 vs 设置进程）+ 真实 `consume_command` + 真实 `go_default_corner`/`save_position` + 真实写盘，legacy 与 overlay 各一条。 |
| `tests/test_agent_link.py` | +73 / −1 | B2 三条（真实失败记录序列 → 岛收 error；正常序列 → 仍收 success；无 `turn/end` → 岛通道不变）；B3 的硬失败窗口替身补齐 `show_alert` 真实签名并断言 `alert_type`/`priority`。 |
| `tests/test_quiet_mode.py` | +26 / −1 | B3：真 `AgentLinkManager` → 真 `window_alerts.show_alert`，开免打扰后失败提醒照常弹出、暂存队列为空。 |
| `tests/test_music_lyric.py` | +153 / −0 | B4 两条（真 PetWindow + 真提醒队列 + 真气泡：引导被收起且歌词立即上屏；审批占位时歌词仍让路、别人的提醒不被顺手收掉）；B5 两条（冷却到期同曲自动重试；在途不叠加第二路请求）；`_HintWin` 替身补真实占用态。 |
| `tests/test_requested_regressions.py` | +70 / −0 | B6 两条：真对话框 + 真 Esc 键事件 + 置败的磁盘 seam → 窗口存活、草稿在；保存正常时 Esc 照旧关窗并落盘。 |
| `tests/test_weather_menu.py` | +65 / −0 | B7 三条：共享建造器关闭态两个入口置灰 + 原因（修复前红）；真 PetWindow + 真 legacy 建造器关闭态不可点（修复前红）；开启态照旧可用。 |
| `tests/test_sprite_menu_parity.py` | +51 / −0 | B8：legacy 音乐子菜单含「歌词对齐」+ 五个子项顺序；可用性语义与注册表 `enabled_ids` 逐点一致（无控制器 → 置灰；位置靠本地时钟估算 → 可用）；`MUSIC_LABELS` 收编该入口（overlay legacy 树一并覆盖）。 |

### 文档

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `README.md` | +9 / −10 | 设置侧栏结构更新为现行 10 域；待办提醒指向「自动化与联动」；省电模式指向「桌宠 → 动作与碰撞 → 动画与移动」；删掉已退役的「单进程多开」开关说法（多宠恒为进程内多开），设置作用域段落按现行口径重写。 |
| `docs/INDEX.md` | +1 / −1 | 部署报告条目标注为**初次部署快照**（部署点 `9e026e4`，分支此后又落了审查修复）。 |
| `docs/PR-REPORT-REVIEW-FIXES-2026-10-08.md` | 新增 | 本文。 |

### 未改动（故意）

- `pet/dsh_state.py`：收敛器语义**不动**（B2 的翻译只发生在呈现侧的 emit 处）。
- `pet/window_alerts.py`：`alert_survives_suppression` 的透传集**一字未改**——
  `execution/failed` 本来就在里面，缺的是调用点没传类型（B3）。
- `pet/window_placement.py`：`go_default_corner` 也被右键菜单/托盘复用，不在那里
  加 reload（那会让一次普通「回到右下角」顺带采用外部配置），B1 的 reload 落在
  两个 `apply_settings_reset` 里。

## 三、实现要点

**B1 为什么是 reload 而不是"别整表写"**。`cfg.save()` 整表落盘是既有契约（多处
依赖），改它要动写盘语义的面；而对齐前先 `reload()` 用的是**已有的**外部变更合并口
（`Config.reload` 的键白名单与 watcher 那一拍同源），与"主进程 watcher 稍后本来就会
reload"这一事实一致——只是把那一刻提前到落盘之前。同对象只重载一次（生产路径
`win.cfg is self.config`），一处实现两个拓扑共用。

**B2 为什么在 emit 处翻译而不是改收敛器**。收敛器输出的是"桥接事件流的客观态"，
`turn/end` 就是 success；"这一轮对用户是失败"是呈现判断，属于 GUI 侧已有的
`_saw_error` 标记（`_on_execution_failed` 在同一批记录里先于 `turn/end` 落盘）。
只翻译 `success` 一个值，其它态（含真 error）原样转发；下一个回合一进 busy 就清标，
不需要额外复位。

**B3 优先级取值**。分类器是**按类型**判穿透的，所以只有 `alert_type` 是必需的；
`priority=1` 取既有错误类提醒（`model_access` / `llm_error`）同档——高于普通状态
气泡与默认 `watchdog` 档，正在展示的低优先提醒会被它顶掉，审批/提问的 `0` 仍可抢占。
走既有的 `_show_alert_compat` 以兼容签名较窄的旧窗口。

**B4 的次序**是本次最便宜也最关键的修复：resolve 必须在 `_bubble_blocked()` 早退
之前（那一条引导自己就是"占用位"），否则它永远不可达；收起后再走一次同样的门禁
自然放行。

**B5 的抽取**把"要不要发请求"收成一个函数，两条调用点共用同一份冷却/在途判定；
同曲分支只在真正到点且不在途时派发。

**B7/B8 的共同形状**：停用门与原因文案**下沉到共享建造器模块**（`weather_menu` /
`shared`），注册表只转发同一份判据。这条形状在仓库里已有先例（`network_info` 的
`add_network_info` + `NETWORK_INFO_DISABLED_REASON` 就在 shared），本次把天气与
歌词对齐补齐到同一口径。

## 四、性能分析

实测环境：本机 Windows / Python 3.13 / PySide6 6.11.2，`QT_QPA_PLATFORM=offscreen`。
命令即下方各条 `python - <<PY` 内联脚本（`timeit` 取 200000 次、配置重载取 200 次
取均值）。

| 项 | 测量 | 结论 |
|---|---|---|
| B5 新增守卫（同曲轮询每拍一次：`dict.get` + `set` 成员） | **0.073 µs/次** | 1Hz 轮询下每天约 6.3 ms，可忽略 |
| B2 新增翻译（每状态变化一次：字符串比较 + `set` 成员） | **0.040 µs/次** | 状态边沿是事件级（一回合几次），可忽略 |
| B1 `Config.reload()` | **1.340 ms/次**（config.json 7518 字节） | 只在用户按下「恢复默认设置」那一刻执行一次（事件驱动，非稳态路径），且**替代**了随后 300ms 去抖里本来就会发生的那一次 reload |
| B3 | 两个关键字参数 | 零成本 |
| B7/B8 | 菜单建造期各多一次 `cfg.get` / `isinstance` 判断 | 菜单建造本就要扫 `music_player_paths` 缓存、构造几十个 action，可忽略（菜单是点击时构建，非常驻热路径） |

- **稳态开销**：全部改动在稳态路径上新增的只有上面的 0.073 µs/拍（B5）与
  0.040 µs/边沿（B2）。
- **新增路径成本与触发频率**：B1 的 `reload()` 是唯一新增的 I/O，1.34 ms/次且
  仅在重置时。
- **有无新的系统调用 / 网络 / 磁盘 / 线程**：**无**。没有新增线程、定时器、
  网络请求；磁盘读只多 B1 那一次 `reload()`（原本 300ms 后也会读）。
- **内存有无增长**：无。没有新增常驻容器或缓存；B2/B5 只多两个类常量与一个
  现有集合的成员判定。

## 五、实机运行记录

本机（不是 CI、不是 mock）真实执行，命令与真实输出如下。

**1. 真 PetWindow + 真 legacy 建造器：关闭态菜单项的置灰与原因（B7/B8）**

```
$ QT_QPA_PLATFORM=offscreen python - <<'PY'   # weather_enabled=False / music_lyric_enabled=True
查看天气: enabled=False tooltip='天气功能已在设置中关闭'
天气城市: enabled=False tooltip='天气功能已在设置中关闭'
歌词对齐: enabled=False tooltip='当前不需要手动对齐（播放器会上报进度，或还没有歌词）'
  子项=['回到开头（现在这句算开头）', '上一句', '下一句', '后退 5 秒', '前进 5 秒']
```

（「歌词对齐」置灰是因为该探针窗口还没装歌词控制器 → `music_align_ready` 为假，
与新版注册表的判定一致；同一脚本里装上控制器后即转可用，见测试用例。）

**2. B1 的两 Config 复现（设置进程写默认 + 写指令 → 主进程消费 + 退出收口写盘）**

```
$ QT_QPA_PLATFORM=offscreen python - <<'PY'
盘上 pet_opacity = 100 (默认 100)
盘上 no_move = False  stream_capture_mode = False
盘上 rx = 0.93
```

修复前同一条命令的输出是 `pet_opacity = 40 / no_move = True / stream_capture_mode = True`
（即重置被整表覆盖回旧值），这就是 B1 的现场证据。

**3. B3 的分类器真值（真实 `window_alerts` + 真免打扰开启）**

```
$ QT_QPA_PLATFORM=offscreen python - <<'PY'
alert_type='watchdog'           priority=3 → 免打扰下穿透=False
alert_type='execution/failed'   priority=1 → 免打扰下穿透=True
quiet_active = True
```

**4. 全量套件（本地真机）**：`QT_QPA_PLATFORM=offscreen python -m pytest -q tests`
→ `5468 passed, 11 skipped, 328 warnings in 1115.55s (0:18:35)`，exit 0。

**不能自动验证的部分（如实登记）**：

- 桌面 GUI 的肉眼确认本批**未做**：本轮修复的可视结果（岛绿点 vs 红点、失败气泡
  在免打扰下真的冒出来、第一首歌 12 秒内看到歌词）在 offscreen 下用真实 Qt 对象与
  真实提醒队列断言到了"状态与投递"这一层，但没有做真机截图/录屏复核。
- B8 的「引导文案所指入口真实存在」用"文案字符串 → 菜单树逐项存在"的机器比对锁定
  （`MUSIC_LABELS` + 子项顺序断言），没有做"点到菜单项后画面变化"的人工复核。
- 桌宠实机（`D:/dsh-pet` 那份部署包）**未重新构建/替换**：本批只在源码分支上完成，
  部署点仍是上一次的 `9e026e4`（见 `docs/INDEX.md` 的初次部署快照标注）。

## 六、验证结果

- 各条修复的 focused 套件全绿（详见 §二 测试表的对应用例）。
- `python -m ruff check pet/ tests/` → `All checks passed!`
- 全量：`QT_QPA_PLATFORM=offscreen python -m pytest -q tests` →
  **`5468 passed, 11 skipped, 328 warnings in 1115.55s (0:18:35)`**，exit 0（本机单跑，
  没有与其它进程并发）。
- 第一轮全量曾红一条 `test_architecture.py::test_modern_settings_dialog_py_line_budget`
  （B6 给该文件净加 7 行，顶破 2497 行绊线）：改为把「关闭前落盘」抽成
  `_save_before_close()` 由 `reject` / `closeEvent` 共用（净增 0 行，契约从两处变一处），
  现已与该绊线一致且本提交序列里每个 commit 都处在预算内。
