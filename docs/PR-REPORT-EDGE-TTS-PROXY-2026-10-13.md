# PR 报告：edge-tts 跟随系统代理（issue #252，2026-10-13）

> **基线**：`1ab73fe`（Merge PR #258）
> **分支**：`fix/edge-tts-proxy`　**日期**：2026-10-13
> **范围**：3 个文件（实现 1、测试 2），`+76/−2`
> **关联**：issue #252（语音合成失败 edge-tts 403，CLI 加 --proxy 可成功但桌宠内部不走代理）

## 一、核心特性

开启系统代理（如 Clash）且直连被拦的用户，语音合成/在线音色表此前必然 403
失败。修复后 edge-tts 的合成与音色列表请求显式跟随系统代理；无代理环境
行为不变（直连）。

根因：edge-tts 走 aiohttp 的 WSS/HTTPS，而 aiohttp 默认 `trust_env=False`
——不读环境变量与系统代理，必须显式传 `proxy=` 参数。CLI 的 `--proxy`
生效正是因为它显式传了这个参数。

**红线 / 不变量**：无系统代理时传 `None`（与现状逐位一致）；代理探测失败
不阻断合成；歌词等特意绕过代理的功能不受影响（`pet/music_lyric.py` 的
绕过设计不变）。

## 二、修改文件说明

`git diff --numstat`：

```
46	0	pet/voice_chime_service.py
2	2	tests/test_voice_chime_edge_voice.py
28	0	tests/test_voice_chime_service.py
```

### 实现

- `pet/voice_chime_service.py`
  - 新增 `_resolve_edge_tts_proxy()`：经 `urllib.request.getproxies()` 读系统
    代理（Windows 注册表 / 环境变量），https 键优先、http 兜底，读不到/异常
    返回 None。注释写明 aiohttp `trust_env=False` 的根因。
  - `refresh_voice_list()` 的 `edge_tts.list_voices()` 与 `_TTSWorker._synthesize`
    的 `edge_tts.Communicate()` 均显式传 `proxy=`（两个 API 都原生支持该参数，
    已核签名）。

### 测试

- `tests/test_voice_chime_service.py` 新增 2 条（红→绿）：
  - `_resolve_edge_tts_proxy` 三态（https 优先 / 仅 http / 无代理）
  - 合成路径把代理传进 `Communicate`（fake edge_tts 捕获 kwargs）+ 无代理时传 None
- `tests/test_voice_chime_edge_voice.py`（+2/−2）：测试替身接口同步——
  `_FakeCommunicate.__init__` 收 `**_kwargs`、`list_voices` 收 `proxy=None`，
  与真实 edge_tts 签名对齐（接口变更的测试侧适配，无行为断言改动）。

## 三、性能分析

| 路径 | 实测（本机 Windows 11，Python 3.13） | 触发频率 |
|---|---|---|
| `getproxies()` | 0.11 ms/次（1000 次均值 113.4 ms/1000） | 每次合成/音色表刷新各一次 |
| 稳态开销 | 零（无新增线程/定时器/轮询） | — |
| 内存 | 无新增驻留对象 | — |

## 四、实机运行记录

```
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_voice_chime_service.py
    tests/test_voice_chime.py tests/test_voice_chime_edge_voice.py
    tests/test_self_talk_voice_precache.py -q
  → 298 passed in 8.20s（含 2 条新用例，改动前红、改动后绿）
ruff check pet/voice_chime_service.py tests/test_voice_chime_service.py
    tests/test_voice_chime_edge_voice.py → All checks passed!
本机 getproxies() 实测：{'http': 'http://127.0.0.1:7890', ...}（本机有系统代理）
```

全量未跑的理由（AGENTS.md 风险门）：本改动是网络参数接线，接口/持久化/
生命周期/平台分发均未变；语音族 298 项全覆盖。

**未验（如实登记）**：真实 403 网络环境下的端到端合成（本机直连可达微软，
无法复现 #252 的拦截环境）；macOS/Linux 系统代理读取（getproxies 各平台
实现不同，CI 三端会覆盖逻辑路径但无法模拟代理拦截）。
