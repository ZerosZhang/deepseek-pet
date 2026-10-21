# PR 报告：气泡置顶跟随桌宠「桌面置顶」开关（2026-10-13）

> **基线**：`3ab1048`（Merge PR #254）
> **分支**：`fix/bubble-on-top-follows-pet`　**日期**：2026-10-13
> **范围**：3 个文件（实现 2、测试 1），`+79/−18`
> **关联**：4.2.1 发布视频评论区反馈（用户「風の夢一」：关了桌面置顶，气泡仍是桌面置顶，宠物被页面挡住时气泡浮在最上）

## 一、核心特性

「桌面置顶」（`on_top`）关闭后，气泡（自言自语/通知/歌词等 `PetSpeechBubble`）
不再浮在最上层，跟随宠物一起被其他窗口遮挡；开启则恢复置顶。

根因是可定位的硬编码：`PetSpeechBubble.__init__` 无条件拼入
`WindowStaysOnTopHint`，`PetWindow.set_on_top()` 只调 `setWindowFlag` 管主窗，
从未触碰气泡——两个窗口的置顶状态从诞生起就没有关联。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 气泡置顶跟随宿主 | `set_host_on_top(on)`：关置顶 → 气泡落回普通层级；开置顶 → 恢复 |
| 2 | 初始值一致 | 气泡构造时按配置 `on_top` 应用，出生即正确 |
| 3 | 可见性保持 | `setWindowFlags` 会隐窗，旗标重建后自动恢复显示 |

**红线 / 不变量**：capture 兼容模式（气泡作为主窗子控件渲染，直播捕获用）
无独立窗口旗标，行为不变；overlay 拓扑不变（OverlayWindow 恒置顶，
气泡置顶与之自洽）；气泡不抢焦点的 `WindowDoesNotAcceptFocus` 硬约束不变。

## 二、修改文件说明

`git diff --numstat 3ab1048...HEAD`：

```
32	17	pet/speech_bubble.py
4	0	pet/window.py
43	1	tests/test_speech_bubble.py
```

### 实现

- `pet/speech_bubble.py`（+32/−17）
  - `__init__`：硬编码旗标块改为 `self._host_on_top = True` + `self._apply_window_flags()`——
    置顶旗标从"永远焊死"改为"读状态装配"。
  - 新增 `_apply_window_flags()`：旗标重建唯一收口，`_host_on_top` 为 True 才拼
    `WindowStaysOnTopHint`；重建前记可见性、重建后补 `show()`（`setWindowFlags` 隐窗）。
  - 新增 `set_host_on_top(on)`：公开 seam。同值早退；capture 兼容子控件模式跳过
    （那时气泡是 Widget 子控件，没有顶层窗口旗标可改）。
  - `set_capture_compat` 关闭分支：原来的硬编码旗标块改调 `_apply_window_flags()`，
    行为相同（默认 `_host_on_top=True` 时旗标逐位一致）且不再分叉。
- `pet/window.py`（+4/−0）
  - `__init__` 气泡构造后：`set_host_on_top(bool(config.get('on_top', True)))`——初始值一致。
  - `set_on_top()` 尾部：`self._speech_bubble.set_host_on_top(on)`——运行时切换同步。
    `getattr` 防御：构造早期 `_speech_bubble` 尚未创建时不炸。

### 测试

- `tests/test_speech_bubble.py`（+43/−1）
  - `test_bubble_follows_host_on_top_flag`：默认置顶 → 关闭后旗标消失且仍可见 →
    重开恢复——可见性断言钉住「setWindowFlags 隐窗」这个坑。
  - `test_pet_window_on_top_propagates_to_bubble`：真 `PetWindow`（`pet_window_fakes`
    替身素材库基建）验证 `set_on_top` 传播 + `on_top=False` 配置出生时气泡即不置顶。
  - 两条均先红（`AttributeError: set_host_on_top` / 传播缺失）后绿。

## 三、性能分析

本改动不加线程、不加定时器、不加系统调用/网络/磁盘、不加常驻内存；
只在两个用户动作点各多一次方法调用。

实测（本机 Windows 11，Python 3.13，QT_QPA_PLATFORM=offscreen，真 Qt 事件循环）：

| 路径 | 实测 | 触发频率 |
|---|---|---|
| `set_host_on_top` 隐藏态 | 6.43 µs/次（1000 次均值） | 用户切开关，一次会话≤数次 |
| `set_host_on_top` 可见态（含窗口重建+show） | 244 µs/次（100 次均值） | 同上 |
| `PetWindow.__init__` 新增调用 | 同值早退，≈0 | 每只宠一次 |

稳态开销：**零**（无新增轮询/监听/驻留对象）。新增路径成本：单次切换
≤0.25 ms，人不可感知。内存：新增一个布尔实例字段。

## 四、实机运行记录

本机真实环境（非 CI、非 mock 窗口系统之外的替身）执行：

```
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_speech_bubble.py -q
  → 43 passed in 2.81s（含 2 条新用例，改动前红、改动后绿）
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_sprite_bubble.py
    tests/test_overlay_bubble_wiring.py tests/test_child_bubble_quick_chat.py
    tests/test_flight_bubble_suppression.py tests/test_bubble_text_scale.py
    tests/test_bubble_subtitle_budget.py -q
  → 68 passed in 5.82s（气泡全族回归）
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_effects_integration.py
    tests/test_feature_gating.py tests/test_agent_link_threads.py
    tests/test_throw_egg.py tests/test_single_process_spawn.py -q
  → 89 passed in 16.20s（PetWindow 构造族——新 init 调用在所有窗口级测试里过一遍）
ruff check pet/speech_bubble.py pet/window.py tests/test_speech_bubble.py
  → All checks passed!
```

全量未跑的理由（AGENTS.md 风险门）：本改动是孤立 widget 表现层旗标，
接口/持久化数据/生命周期/平台分发均未变；窗口构造路径已由 89 项窗口级
测试覆盖。

**未验（如实登记）**：桌面 GUI 肉眼确认（「宠被浏览器挡住时气泡也被挡住」的
真实观感）未做——需要真桌面会话切换窗口层级验证；macOS 窗口层级
（`WA_MacAlwaysShowToolWindow` 路径）未验；overlay 拓扑行为不变故未验。
