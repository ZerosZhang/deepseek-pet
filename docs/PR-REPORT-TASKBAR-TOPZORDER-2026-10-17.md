# PR 报告：overlay 合成窗让任务栏掉出置顶层（issue #296）

> **基线**：`a8593a8`（v4.3.1 正式发布）
> **分支**：`fix/issue-296-non-rude-hwnd`　**日期**：2026-10-17
> **范围**：代码 3 个文件（实现 2、测试 1）+ 文档 2 个文件（本报告、`docs/INDEX.md` 登记）
> **关联**：<https://github.com/MerZlin/dsh-pet-indesktop/issues/296>

## 一、核心特性

4.3.0 起默认渲染拓扑是 overlay：每块屏一张**铺满 `screen.geometry()`（含任务栏）**
的透明置顶合成窗（`pet/overlay_window.py:89`）。Windows Shell 的 "rude window
manager" 按窗口几何判定全屏应用——铺满整块显示器的窗口会让任务栏被移到 z 序
底部。用户观感就是 issue #296 的「启动桌宠后，任务栏被所有悬浮窗口挡住；退出
桌宠即恢复」。4.2.1 默认 legacy 小窗，从不满足「铺满整屏」，所以没有该问题。

修法：在窗口**显示之前**调用官方豁免
`SetProp(hwnd, L"NonRudeHWND", HANDLE(TRUE))`（MS 文档
`ITaskbarList2::MarkFullscreenWindow` Remarks：自 Windows 7 起支持；与
`MarkFullscreenWindow(FALSE)` 的差别是 Shell **不会**回落到自动检测）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | Windows overlay 窗登记「非全屏应用」 | 每次 `showEvent` 给当前 HWND 设 `NonRudeHWND`；任务栏不再被压到 z 序底部 |
| 2 | 原生窗重建后自动重放 | `on_top` 的 `setWindowFlag` 会重建 HWND；属性随旧 HWND 消失，下一次 `showEvent` 重设 |

**红线 / 不变量**：

- overlay 仍铺满 `screen.geometry()`——坐标模型、跨屏迁移、`_local_bounds`
  全部不变；
- 宠物移动边界仍是 `availableGeometry`（[`overlay_shell.py:1586`](../pet/overlay_shell.py#L1586)），
  并且不因为本改动跑到任务栏上；
- 仅 Windows 生效；非 Windows 连 import 都不发生（`sys.platform == "win32"` 分支）。

## 二、修改文件说明

`git diff --numstat`：

| 文件 | 增删 | 说明 |
|---|---|---|
| `pet/platform_win.py` | +30 / −0 | 新增 `_NON_RUDE_PROP` 与 `_set_windows_non_rude_hwnd(hwnd, user32=None)`：`SetPropW` + argtypes（64 位 HWND/HANDLE 指针不被 int32 截断，口径同 `_set_windows_topmost`）；`user32` 可注入，便于跨平台单测 |
| `pet/overlay_window.py` | +13 / −1 | `showEvent` 顶部（原生窗显示之前）在 win32 下调用新原语；win32 导入清单增加该函数。注释写明「属性随 HWND 销毁，靠下一次 `showEvent` 重放」 |
| `tests/test_platform_non_rude.py` | +122 / −0 | 新增：① 原语调用形状（属性名 / `HANDLE(TRUE)` / 返回值 / 失败返回 False）；② `OverlayWindow.showEvent` 真的接线；③ `hide → setWindowFlag → show` 重放（Windows 门控） |
| `docs/PR-REPORT-TASKBAR-TOPZORDER-2026-10-17.md` | +170 / −0 | 本报告：根因、实现要点、性能实测、实机记录（含本机未复现的如实说明） |
| `docs/INDEX.md` | +1 / −0 | 按新文档入场规则在「PR 报告存档」表登记本报告 |

### 未改动（明确不做）

- `pet/screen_capture/overlay.py:275`：截图选区层也是全屏置顶 Tool 窗，机制相同，
  但只在截图期间存在、关闭即恢复。本 PR 控制范围，另开 issue 跟踪。
- `pet/window.py`（legacy 捕获模式）：小窗，不构成「铺满整屏」，无需标记。

## 三、实现要点

1. **为什么放在 `showEvent`**：MS 文档要求「before showing a window」。本机对
   真实 `OverlayWindow` 的探针（见第五节）确认调用点处 `IsWindowVisible=False`，
   显示后才是 `True`，满足前置条件。
2. **为什么不改几何**：把 overlay 缩到 `availableGeometry` 会连带改坏跨屏坐标、
   位置迁移和屏原点缓存（`_sync_host_geometry` 用 `screen.geometry()` 同步）。
   `NonRudeHWND` 是零几何改动的正解。
3. **为什么不用 `MarkFullscreenWindow(FALSE)`**：文档明说它会回落到自动检测，
   "possibly still flagging the window as full-screen"；`NonRudeHWND` 才是
   关掉检测。
4. **重建路径**：`setWindowFlag` 在可见窗上会重建原生窗（
   [`overlay_shell.py:4421`](../pet/overlay_shell.py#L4421) 同一处已注释），随后
   `overlay.show()` 会再次进入 `showEvent`，属性自动重设——与既有
   `_set_windows_no_activate` 是同一条先例。
5. **失败不致命**：`SetPropW` 返回 bool，调用点不检查（与 `_set_windows_no_activate`
   一致）；失败退化为旧行为，不抛异常。

## 四、性能分析

**方法（可复现）**：单次原语微基准，`SetPropW` 在桌面窗句柄上调用 20000 次后
`RemovePropW` 清理；Python 3.11.9，Windows 10.0.22631-SP0。

| 指标 | 实测 | 归属 |
|---|---|---|
| `SetPropW` 单次调用 | **2.28 µs/call**（20000 次共 45.6 ms） | 新增路径 |
| 每次 overlay 显示的新增调用数 | 1 次 | 新增路径 |
| 稳态（tick）开销 | **0**（不在 tick/绘制/输入轮询路径上） | 稳态 |
| 新增线程 / 定时器 / 网络 / 磁盘 | **0 / 0 / 0 / 0** | 稳态 |
| 常驻内存增长 | **0**（临时 `c_void_p`，不持有引用） | 稳态 |

**结论**：① 稳态开销没有变化；② 新增路径绝对成本约 2.3 µs，触发频率 =
每次 overlay 显示一次（启动每屏一次、全屏避让恢复、托盘恢复、`on_top` 切换后
重建），与 10/50 ms 的输入轮询和 90 Hz tick 相比低 4-5 个数量级；③ 没有引入
新的系统调用类别以外的资源（仅一次 `SetPropW`）；④ 内存与缓存无增长。

## 五、实机运行记录

**本机环境**：Windows 11 家庭中文版 10.0.22631，1707×1067 逻辑 / dpr 1.5，
Python 3.11.9，PySide6 6.11.2，源码运行（非 CI、非 mock）。

### 5.1 属性是否真的落在真实 overlay 窗上

启动真实应用（`.venv/Scripts/pythonw.exe -m pet`），从**外部进程**枚举该进程
顶层窗并读 `GetPropW`：

```
# 修复后（本分支）
hwnd=2885140 class='Qt6112QWindowToolSaveBits' rect=(0, 0, 1707, 1067)
            size=1707x1067 visible=1 NonRudeHWND=1

# 基线 a8593a8（独立 worktree，同一探针）
hwnd=722390  class='Qt6112QWindowToolSaveBits' rect=(0, 0, 1707, 1067)
            size=1707x1067 visible=1 NonRudeHWND=None
```

同一探针还确认：灵动岛小窗（192×44）没有该属性（符合预期，只标记全屏窗）。

### 5.2 「必须在显示之前」的前置条件

对真实 `OverlayWindow` 插桩（包装原语）后 `show()`：

```
call site: hwnd=67862 IsWindowVisible=False
after show: hwnd=67862 IsWindowVisible=True
prop: 1
```

### 5.3 用户可见行为（**本机未复现，如实记录**）

用普通 Qt 窗口压到任务栏区域（逻辑坐标 1180,860，520×300），分别对基线
`a8593a8` 与修复分支截图：**两版的 Windows 任务栏都完整压在普通窗口之上**，
本机没有复现「任务栏被普通窗口遮住」。

- 报告者环境是 **Windows 11 22H2 Build 22621**，本机是 **22631**；
- 报告者描述为「很大概率」，且触发前有 `Weixin.exe` 被全屏判定命中的日志；
- 结论：本机属性差异是客观的（`None` → `1`），但**用户可见行为需要报告者
  在自己的 22621 上复测确认**。未确认前不得写成「已修复」。

### 5.4 为什么不能自动验证

rude window manager 在 `explorer.exe` 内部，没有公开 API 查询它的判定结果；
唯一可观测量是任务栏的 z 序/遮挡行为，而该行为受激活与几何启发式影响（本机
即未复现）。可自动化的部分（属性是否设置、是否在显示前设置）已在上两节用真实
窗口验证。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check .` | All checks passed |
| 聚焦（新增 + 相关） | `pytest -q tests/test_platform_non_rude.py tests/test_island_topmost.py tests/test_input_controller_poll_tiers.py tests/test_input_controller_drag.py tests/test_overlay_hardening.py` | 44 passed |
| 全量（第一轮） | `python -m pytest -q` | 8126 passed, 29 skipped, 1 failed——失败项 `test_screen_capture_ocr.py::test_self_built_sessions_are_injected_into_the_engine_cfg` 报 `ModuleNotFoundError: omegaconf`（`requirements.txt:85` 已声明、本机 venv 未装，与本次改动无关） |
| 补装声明依赖后复跑该文件 | `pytest -q tests/test_screen_capture_ocr.py` | 56 passed, 6 skipped |
| 全量（第二轮，干净环境） | `python -m pytest -q` | **8134 passed, 24 skipped, 0 failed**（864.92s） |
| 全量（推送前复跑，机器重启后） | `python -m pytest -q` | **8134 passed, 24 skipped, 0 failed**（870.53s） |
| 架构红线 | 含在全量内 `tests/test_architecture.py` | 通过 |
| 交付纪律 | `pytest -q tests/test_pr_report_discipline.py` | 183 passed（本报告已登记 INDEX） |

> **环境说明**：本机 venv 初始缺 `numpy`（`requirements.txt:84`）与 `omegaconf`
> （`:85`）两个**已声明**依赖，首轮全量在收集阶段/单条用例上各红过一次；两者
> 均按项目声明补装，未改动任何版本约束。这不是产品缺陷，也不属于本 PR 范围。

## 七、已知限制与后续

- **22H2 / 22621 未经本机验证**：需要报告者复测（这也是本报告不写「已修复」的原因）。
- 截图选区层（`pet/screen_capture/overlay.py`）同样的全屏置顶窗未标记；
  它只在选区期间存在，影响面小，建议另开 issue。
- 属性是 Shell 的文档化行为，但不同 Windows 版本的判定时机有差异；若未来
  Win11 新版本改变行为，本修复的观测点（属性存在性）不变，仍可回退。

## 八、风险与回滚

- **影响面**：仅 Windows、仅 overlay 全屏合成窗；legacy/捕获模式与非 Windows
  完全不受影响。
- **失败模式**：`SetPropW` 失败时静默退化为旧行为（任务栏问题仍在），不会
  引入新的崩溃路径。
- **配置/落盘**：无新增配置键、无迁移、无持久化状态。
- **回滚**：`git revert` 即可；无需清理任何落盘数据。
