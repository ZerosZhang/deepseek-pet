# PR 报告：帧序列首跑供给派生 ffmpeg 弹出命令行窗口

> **基线**：`ee699c7`（Merge PR #233 feature/agent-link-subtraction）
> **分支**：`fix/frameseq-ffmpeg-no-console`　**日期**：`2026-10-12`
> **范围**：3 个文件（实现 1、测试 1、文档 1 + INDEX 登记）
> **关联**：[`PR-REPORT-FRAMESEQ-V3-PIPELINE-2026-09-29.md`](PR-REPORT-FRAMESEQ-V3-PIPELINE-2026-09-29.md)（首跑供给的来源）

## 一、核心特性

Windows 打包版（`--windowed`，GUI 子系统、无控制台）启动后约 2 分钟内，屏幕上会**反复闪出命令行窗口**，
到达供给预算后停止，下次启动又会再闪，直到 106 段 clip 全部转换完。根因：
`pet/frameseq_provision.py::_creation_flags()` 只给 ffmpeg 设了 `BELOW_NORMAL_PRIORITY_CLASS`，
没有 `CREATE_NO_WINDOW`；GUI 进程派生控制台程序（ffmpeg.exe）时，Windows 会为子进程**新建一个可见控制台**。
本机实测：同一条 ffmpeg 命令在无控制台的父进程里以旧标志启动 → 新增 **2 个**可见控制台窗口；
加上 `CREATE_NO_WINDOW` → **0 个**（见第五节）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 首跑供给不再闪窗 | `_creation_flags()` 在 Windows 上返回 `BELOW_NORMAL_PRIORITY_CLASS \| CREATE_NO_WINDOW` |

**红线 / 不变量**：ffmpeg 仍以「低于正常」优先级运行（一次性重编码的 CPU 让给交互）；POSIX 分支仍返回 0；
派生、取消、`communicate()` 收集 stderr 的路径一律不动（`CREATE_NO_WINDOW` 不影响管道重定向）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/frameseq_provision.py` | +7 / −2 | `_creation_flags()`：Windows 分支在原优先级标志上 OR `CREATE_NO_WINDOW`；docstring 写明为什么需要（`--windowed` 父进程派生控制台程序会新建可见控制台）。该函数唯一调用点是 `_encode_one` 的 `_popen(..., creationflags=_creation_flags())`。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_frameseq_no_console.py` | +26 / −0（新增） | Windows：标志同时含 `CREATE_NO_WINDOW` 与 `BELOW_NORMAL_PRIORITY_CLASS`；POSIX：返回 0。基线代码上 Windows 用例**红**、本分支**绿**（第六节）。 |

### 未改动（故意）

- `probe_fps()`：走 `imageio_ffmpeg.read_frames`，imageio_ffmpeg 内部已用 `STARTUPINFO` 隐藏窗口（`pet/webm_clip.py` 头注释同一结论），本机实测运行期未见它弹窗。
- `pet/webm_clip.py` 播放解码、`pet/agent_link.py` / `pet/harness_launcher.py` / `pet/updater.py`：已带 `CREATE_NO_WINDOW` 或等效处理，逐个 grep 过 `subprocess.Popen/run`。
- `pet/click_sound.py::_play_with_system_player`：只在非 Windows 平台使用（afplay/paplay/aplay）。

## 三、实现要点

`CREATE_NO_WINDOW`（0x08000000）只对控制台程序生效：子进程仍有一个**隐藏的**控制台，stdin/stdout/stderr 管道照常工作，
与 `harness_launcher.py` 的既有用法一致。没有改用 `DETACHED_PROCESS`：那会让子进程完全没有控制台，
部分控制台程序在无控制台时行为不同，且与本模块「取消时 terminate + communicate 收尾」的模型无关，没必要扩大改动面。

## 四、性能分析

**方法（可复现）**：`pythonw.exe console_probe.py`（无控制台父进程，与打包版一致；脚本见第五节）
环境：Windows 11 Pro 22631.6199 / AMD Ryzen 7 7800X3D / Python 3.11.5 / imageio-ffmpeg 0.6.0（ffmpeg v7.1）

| 指标 | 实测 | 归属 |
|---|---|---|
| 新标志下 `ffmpeg -version` 启动+退出耗时 | 中位 **203.9 ms**，p90 209.8 ms，最小 200.3 ms（n=30） | 既有路径（每段 clip 转换派生一次） |
| 触发频率 | 每次启动在 120 s 起手预算内转换约 **5 段**（本机日志：`新转 5 / 预算搁置 96~101`），全部 106 段转完后为 0 | 既有路径 |
| 旧标志下的同项耗时 | **未测**：旧标志每次都会在桌面弹出可见窗口，30 次采样等于在用户桌面连闪 30 个窗口，故只做了下面一次复现 | — |

**结论**：① 稳态开销不变（供给结束后不再派生）；② 新增成本为零——只是 `CreateProcess` 的一个标志位，
不新建进程/线程；省掉的是每次派生一个可见控制台窗口（conhost/终端宿主）的创建与绘制；③ 无新的系统调用、网络、磁盘或线程；
④ 内存无增长。

## 五、实机运行记录

**根因复现（本机，2026-10-12）**：无控制台父进程（`pythonw.exe`，`GetConsoleWindow()==0`）派生
`ffmpeg -re -f lavfi -i color=... -t 1.5 -f null -`，运行期间每 50 ms 枚举可见顶层窗口，统计新增的
`ConsoleWindowClass` / `CASCADIA_HOSTING_WINDOW_CLASS` / `PseudoConsoleWindow`：

```json
"old_BELOW_NORMAL":                   {"new_visible_console_windows": 2, "exit": 0},
"new_BELOW_NORMAL|CREATE_NO_WINDOW":  {"new_visible_console_windows": 0, "exit": 0}
```

**用户可见行为**：本机打包版（`scripts/build_onedir.ps1` 构建的 webm-chat 变体）启动后，用户报告「隔一段时间就跳出命令符对话框，跳了几次后又不跳了」；
同一时段日志 `帧序列首跑供给收尾：新转 5 / … / 预算搁置 96`，与「供给预算内逐段转换、到点收手」吻合。

**修复后**：重新打包安装，启动后 150 s 内（覆盖整个供给窗口）每 500 ms 枚举可见控制台窗口：
**观察到 ffmpeg 进程 136 个（含播放解码），新增可见控制台窗口 0 个**；日志 `新转 5 / 失败 0`，转换照常完成。

**边界**：POSIX 分支未在 macOS/Linux 真机验证（本改动不触及该分支，用例只断言返回 0）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | All checks passed |
| 断言有效性 | 基线 `ee699c7` 的 `frameseq_provision.py` 上跑新用例 | **1 failed**（缺 `CREATE_NO_WINDOW`） |
| 聚焦 | `pytest -q tests/test_frameseq*.py tests/test_architecture.py tests/test_pr_report_discipline.py` | 273 passed, 1 skipped（Python 3.11.5，Windows） |
| 全量 | `python -m pytest -q` | 见 PR 描述（Python 3.11.5，Windows） |

## 七、已知限制与后续

无。

## 八、风险与回滚

影响面仅限 Windows 上帧序列首跑供给派生的 ffmpeg；无新增配置键、无落盘格式变化。回滚 = `git revert`，无残留状态。
