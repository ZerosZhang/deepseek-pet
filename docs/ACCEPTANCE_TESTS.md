# 验收测试文件清单

仓库中不存在 `tests/test_modern_settings_dialog.py` 和 `tests/test_dsh_pet_bridge.py`。检查 Git 历史（包括所有本地及远程引用）后，未发现这两个路径曾被提交、重命名或拆分后保留原文件名。因此验收不创建同名空文件，而按实际测试边界执行下列文件。

## 设置窗口验收

现代设置窗口的测试已按功能拆分：

- `tests/test_settings_and_resources.py`：现代设置窗口基本控件与配置 round-trip；
- `tests/test_overlay_collision_toggle.py`：宠-宠碰撞开关的真实接线（真配置落盘 →
  reload → `refresh_settings` → 世界结算行为、per-slot 归属；设置窗口里那个勾选框
  本身在 `tests/test_desktop_pet_features.py`）；
- `tests/test_settings_subslot_autostart.py`：子槽位下现代设置窗口的开机自启行为；
- `tests/test_desktop_pet_features.py`：现代设置侧栏、页面归属、表达风格及依赖控件；
- `tests/test_settings_event_gating.py`：设置窗口打开时的事件/提醒拦截边界。

验收命令（每个路径都由 pytest 收集并执行）：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q `
  tests/test_settings_and_resources.py `
  tests/test_overlay_collision_toggle.py `
  tests/test_settings_subslot_autostart.py `
  tests/test_desktop_pet_features.py `
  tests/test_settings_event_gating.py
```

## DSH Bridge 验收

Bridge 验收采用真实插件源码上的 Node contract 测试，并结合桌宠端真实事件解析/状态处理测试：

- `tests/test_bridge_instance_scope.js`：写者归属（`inst` 信封字段）不得被事件内容顶掉、不进嵌套载荷、真的随写入行落队（多 DSH 实例隔离的身份来源）；
- `tests/test_bridge_root_control.js`：已删机制（控制队列/mux 中继）不得复活的静态闸 + 退役测试出口不再导出；
- `tests/test_bridge_interaction_dedup.js`：问题写盘去重键的会话隔离（callId 复合键）；
- `tests/test_bridge_question_callid.js`：question 写盘的 callId 身份管理（会话隔离复合键、register/forget 幂等）；
- `tests/test_bridge_user_action_guard.js`：tool/result 兜底只走 resolveQuestion，不再写恒不可达的 user_action；
- `tests/test_bridge_manifest.js`：插件可独立加载（inject 契约）+ 清单零依赖红线；
- `integrations/dsh-pet-bridge/verify_import.mjs`：hermetic 零依赖冒烟（无 node_modules 隔离目录 import + 已删机制/明文字符串静态禁令）；
- `tests/test_agent_link.py`：真实 `AgentLinkManager`、tailer、事件映射、请求生命周期和交互队列；
- `tests/test_dsh_state.py`：真实 DSH JSONL 状态读取与状态转换。

验收命令：

```powershell
node --check integrations/dsh-pet-bridge/index.js
node --test tests/test_bridge_hardfailure.js tests/test_bridge_instance_scope.js tests/test_bridge_interaction_dedup.js tests/test_bridge_manifest.js tests/test_bridge_question_callid.js tests/test_bridge_retry.js tests/test_bridge_root_control.js tests/test_bridge_user_action_guard.js
node integrations/dsh-pet-bridge/verify_import.mjs
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_agent_link.py tests/test_dsh_state.py
```

## Qt 生命周期与最终全量验收

Windows/offscreen 的最终验证必须分两步执行，避免高并发跨进程压力测试掩盖普通
Qt 生命周期问题：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q --ignore=tests/test_decode_fanout.py --ignore=tests/test_decode_fanout_integration.py
python -m pytest -q tests/test_decode_fanout.py tests/test_decode_fanout_integration.py
```

第一步必须先完整结束且无 native abort；第二步只能在第一步通过后运行。

**为什么不用 `-k "not decode_fanout"`**：`-k` 按父模块名匹配，除两个扇出文件外还会顺带摘掉
`tests/test_architecture.py::test_decode_fanout_does_not_depend_on_window_or_player`；第二步只跑两个扇出文件，
补不回这一条 —— 两段都不覆盖它。收集口径实测（`--collect-only`，**只收集、不执行用例**）：

| 命令 | 收集结果 |
|---|---|
| `python -m pytest -q --collect-only` | `5713 tests collected` |
| `… --collect-only -k "not decode_fanout"` | `5682/5713 tests collected (31 deselected)` |
| `… --collect-only --ignore=tests/test_decode_fanout.py --ignore=tests/test_decode_fanout_integration.py` | `5683 tests collected` |
| `… --collect-only tests/test_architecture.py` | `15 tests collected` |
| `… --collect-only -k "not decode_fanout" tests/test_architecture.py` | `14/15 tests collected (1 deselected)` |

对照即缺口：新形式比旧形式多收集 **1** 条，少的正是 `test_architecture.py` 里那条扇出守卫。

**最近一次完整口径（WP13 + G0 独立验收，2026-10-09；三段真实退出码均为 0）** —— 三段相加才是全量。
**这是本轮新增测试文件（`tests/test_gpu_monitor.py` 等）落盘之前的树口径**（收集实测时裸收集 `5713`，与 G0 基线自洽）；每新增一个测试文件总数都会变，
**不要把它当成永久门禁值**，改动测试边界后按本节规则重新取数：

| 段 | 命令 | 结果 |
|---|---|---|
| 主套件 | 第一步（`--ignore` 形式） | 收集 `5683`，即 **5672 passed / 11 skipped** |
| 扇出族 | 第二步 | **30 passed** |
| 合计 | — | **5702 passed / 11 skipped / 0 failed** |

**G0 那轮的实际跑法**（如实登记，**不得读成"新命令已经整段跑过"**）：G0 用的是**旧命令**
`-k "not decode_fanout"` → `5671 passed / 11 skipped / 31 deselected`，再**单独实跑**补漏那一条 → `1 passed`
（5671 + 1 = 5672；31 deselected = 30 条扇出 + 补漏的这 1 条）。**`--ignore` 形式本身尚未整段跑过**：
上表第一段的 `5683 collected` 来自本轮的收集实测，`5672 passed` 由 `5671 + 1` 换算；11 skips 全部落在第一段
（两个扇出文件在旧命令下为 0 skipped）。证据：`.scratch/product-g0-20261009/logs/`（`20-full-nondecode.txt`、
`21-full-decode-fanout.txt`、`22-deselect-gap.txt`、`11-ruff.txt`）；本轮收集实测见
`.scratch/product-release-continuation-20261009/logs/10-collect-ignore.txt`…`14-arch-bare.txt`。

**历史基线（旧命令口径，不是当前标准）**：主套件 `1895 passed, 8 skipped, 2 deselected`（2 deselected = 当时
本机两个已知环境假红：高刷屏 drag 节流钟差、collision 真时钟竞态）；解码扇出族（原跨进程 shm broker 已被
进程内 fan-out 取代）：`29 passed`。这两个数字来自更早的基线，**数量级已与现状差两倍以上，不得当作当前门禁值**。

生命周期重点覆盖 `PetWindow.closeEvent()` 的幂等关闭、外置
`PetSpeechBubble` 的 owner 清理、右键菜单执行 seam、AgentLink/WebM/session
后台资源 teardown。详细说明见
[`QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md`](QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md).
