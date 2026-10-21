# 文档索引

本目录只剩与**当前精简版**相关的开发文档。上游 183 篇文档中，描述已删功能（AI 对话、识屏、语音、音乐、天气、联动、灵动岛、插件体系等）的 160 余篇与全部 PR 报告、截图已在精简时删除；需要查历史时去上游仓库或本仓库首个提交。

## 条目

| 文档 | 内容 | 何时读 |
|---|---|---|
| [ONEDIR_PACKAGING.md](ONEDIR_PACKAGING.md) | onedir 打包流程、随包分发内容、Qt runtime 补全与瘦身 | 改 `scripts/build_onedir.ps1`、`slim_bundle.py`、打包相关资源时 |
| [SETTINGS-CHANGE-GATES.md](SETTINGS-CHANGE-GATES.md) | 设置项的增删改闸门：配置键、行、域、默认值标记的连带改动 | 新增/移动/删除任何持久设置时 |
| [SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md](SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md) | 设置页域布局的决策记录 | 重排设置页结构时 |
| [WINDOW_PY_SPLIT_GUIDE.md](WINDOW_PY_SPLIT_GUIDE.md) | `window.py` 的拆分约定：新功能优先拆控制器 | 往 `window.py` 加内容之前 |
| [ASSET-PIPELINE.md](ASSET-PIPELINE.md) | 素材管线：WebM → 帧序列、编码档、目录契约 | 改素材、编码档、`tools/convert_frameseq.py` 时 |
| [PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md](PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md) | 动作状态机与防重复规则 | 改动画链/状态机时 |
| [PERSONA-PHRASES-PRESET-STORAGE-2026-09-08.md](PERSONA-PHRASES-PRESET-STORAGE-2026-09-08.md) | 台词预设的存储与语义 | 改 `pet/persona_presets/`、`persona_phrases.py` 时 |
| [PERSONA-TEMPLATE-FIELD-ALIGNMENT-2026-09-05.md](PERSONA-TEMPLATE-FIELD-ALIGNMENT-2026-09-05.md) | 台词模板字段对齐 | 同上 |
| [CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md) | 右键菜单的结构、样式与平台行为 | 改菜单结构/样式时 |
| [ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md](ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md) | Windows 关机/注销时的 ffmpeg 与 warm 调度 | 改 `webm_clip`、`session_watcher` 时 |
| [OPTIMIZATION_CHECKLIST.md](OPTIMIZATION_CHECKLIST.md) | 性能检查清单（历史快照） | 做性能优化前扫一遍 |
| [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) | 验收测试口径 | 补验收测试时 |
| [QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md](QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md) | Qt 对象生命周期导致的全套件崩溃族处置 | 全量测试崩溃/事件循环测试时 |
| [PR-MERGE-LESSONS-2026-09-12.md](PR-MERGE-LESSONS-2026-09-12.md) | 合并与冲突教训、时序测试纪律 | 合并 PR 前 |
| [PR-REPORT-TEMPLATE.md](PR-REPORT-TEMPLATE.md) | 交付证据三件套模板 | 写 PR 报告时 |
| [DEV-HANDOVER.md](DEV-HANDOVER.md) | 交接规范与证据细则 | 交接/长期接手时 |
| [NETWORK-PROXY-AND-VPN-2026-09-22.md](NETWORK-PROXY-AND-VPN-2026-09-22.md) | Windows 系统代理与网络功能排障 | 网络相关功能"昨天还能用"时 |
| [CHANGELOG-ARCHIVE-2026-10.md](CHANGELOG-ARCHIVE-2026-10.md) | 上游变更归档（历史快照，含已删功能） | 追溯历史用途时 |
| [agents/](agents/) | 本地 issue / 分诊 / 领域文档的使用说明 | 用 `.scratch/` 流程时 |
