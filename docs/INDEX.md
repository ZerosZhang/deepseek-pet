# 文档索引

本目录只保留与**当前精简版**对应的开发约定；上游 180 余篇设计与 PR 报告已在精简时删除（需要时查上游仓库或本仓库首个提交）。

| 文档 | 内容 | 何时读 |
|---|---|---|
| [ONEDIR_PACKAGING.md](ONEDIR_PACKAGING.md) | onedir 打包流程、随包内容、Qt runtime 补全与瘦身 | 改 `scripts/build_onedir.ps1`、`slim_bundle.py` 时 |
| [SETTINGS-CHANGE-GATES.md](SETTINGS-CHANGE-GATES.md) | 设置项增删改的闸门：配置键、行、域、默认值标记的连带改动 | 新增/移动/删除任何持久设置时 |
| [WINDOW_PY_SPLIT_GUIDE.md](WINDOW_PY_SPLIT_GUIDE.md) | `window.py` 的拆分约定：新功能优先拆控制器 | 往 `window.py` 加内容之前 |
| [ASSET-PIPELINE.md](ASSET-PIPELINE.md) | 素材管线：WebM → 帧序列、编码档、目录契约 | 改素材、编码档、`tools/convert_frameseq.py` 时 |
| [CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md) | 右键菜单的结构、样式与平台行为 | 改菜单结构/样式时 |
| [PR-REPORT-TEMPLATE.md](PR-REPORT-TEMPLATE.md) | 交付证据三件套模板 | 写 PR 报告时 |
| [DEV-HANDOVER.md](DEV-HANDOVER.md) | 交接规范与证据细则 | 交接/长期接手时 |
