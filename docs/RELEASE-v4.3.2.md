# v4.3.2

> 从 **v4.3.1 到 v4.3.2** 的**紧急补丁版**（**已于 2026-10-17 发布**：[`releases/tag/v4.3.2`](https://github.com/MerZlin/dsh-pet-indesktop/releases/tag/v4.3.2)，tag `v4.3.2` = `322d73c`；8 个附件的 size 与 sha256 已对账进 `update.json`，发布正文由本文件的「下载 → 致谢」两段生成）。
> **唯一产品改动**：截图翻译把整句拆成逐词译文。
> **本版不新增功能、不新增/改名配置键、不换安装形态**（仍是 onedir 四变体）、应用标识与配置目录都不变。
> 报告与红绿证据见 PR [#297](https://github.com/MerZlin/dsh-pet-indesktop/pull/297)（合并提交 `a8d30df`）。
>
> **本文件分两段用**：`## 📦 下载` 到 `## 🙏 致谢`（含）是**发布正文**；`RELEASE-BODY-END` 注释之后的维护者清单（含人工验收清单与「本版明确不含」）**只在仓库内使用，不随 Release 发布**。
>
> 生成发布正文 = **从 `## 📦 下载` 标题开始**取到 `RELEASE-BODY-END` 注释行之前（末尾 `---` 一并去掉；**不要从文件头取**）：
> `python -c "import pathlib;L=pathlib.Path('docs/RELEASE-v4.3.2.md').read_text(encoding='utf-8').splitlines();j=next(k for k,l in enumerate(L) if l.startswith('## 📦 下载'));i=next(k for k,l in enumerate(L) if l.strip().startswith('<!--') and 'RELEASE-BODY-END' in l);pathlib.Path('body.md').write_text('\n'.join(L[j:i]).rstrip().rstrip('-').rstrip()+'\n',encoding='utf-8')"` → `gh release edit v4.3.2 --notes-file body.md`。

---

## 📦 下载

| 平台 | 变体 | 安装版 / 绿色版 |
|---|---|---|
| Windows x64 | WebM + Chat（AI 对话） | `dsh-pet-standalone-webm-chat-setup.exe` / `dsh-pet-standalone-webm-chat-portable.zip` |
| Windows x64 | WebM 无 Chat（纯桌宠） | `dsh-pet-standalone-webm-setup.exe` / `dsh-pet-standalone-webm-portable.zip` |
| macOS arm64 | WebM + Chat | `dsh-pet-standalone-webm-chat-macos-arm64.zip` |
| macOS arm64 | WebM 无 Chat | `dsh-pet-standalone-webm-macos-arm64.zip` |
| Linux x86_64 | WebM + Chat | `dsh-pet-standalone-webm-chat-linux-x86_64.zip` |
| Linux x86_64 | WebM 无 Chat | `dsh-pet-standalone-webm-linux-x86_64.zip` |

均为 **onedir** 形态：安装版与绿色版运行期都不解压、不产生临时缓存，启动快、卸载干净。

## ⚠️ 升级说明

直接覆盖安装、或换掉绿色包即可。配置与会话都在用户配置目录（Windows 为 `%APPDATA%\dsh-pet`），**不受换包影响**。

- **无新增配置键、无键搬迁、无数据迁移**。
- 从 v4.3.1 升级不需要任何额外操作；从更早版本升级请照常读对应版本的发布说明。

## 🐛 修复

### 截图翻译：整句不再被拆成逐词译文

**现象**：截图翻译把一行 `Working on two of these` 翻成「正在 / 处理 / 这些 / 中的 / 两个」——语序和语义一起丢。同一模型在白底大字（整段被识别成一个块）的截图上翻译完全正常，所以这不是模型能力问题。

**根因（两处叠加）**：

1. OCR 的文本视图按**块**拼换行。检测器给出的块是**词/片段级**的：`reading_order()` 虽然按竖向重叠把同一视觉行的块聚成一组，输出时又把分组拍平了——行结构在那一步丢掉，于是同一行的每个词各占一行。
2. 翻译指令写着「保留原有的换行结构」。模型老实照做，把硬换行当成句子边界，逐行对译。

**修复**：

- 文本视图改成**行内接成一句**（中文相邻不插空格、其余用单个空格），行间才换行；
- 翻译指令改为「换行只是排版断行、不是句子边界，先按语义把被断开的句子接回完整句子再翻译，按自然段落输出」。原文仍逐字照发，不改写你在结果里看到的 OCR 原文。

**不受影响的部分**：整段被识别成一个块的场景（白底大字段落）行为完全不变——单块原样返回、原有换行保留。

**明确不包含**：OCR 检测/识别本身的分块误差（例如某个词块的边界多带了一个字母）不在本次范围，它仍会跟着进译文。

## 🙏 致谢

本版为维护者自查的单一修复，问题由维护者在日常使用中复现并定位（两张对照截图：深色小字推文句被逐词拆译、白底大字整段正常）。贡献者与修复记录见 [README 的贡献段](https://github.com/MerZlin/dsh-pet-indesktop#贡献) 与 PR [#297](https://github.com/MerZlin/dsh-pet-indesktop/pull/297)。

<!-- RELEASE-BODY-END -->

## 维护者清单（不随 Release 发布）

### 本版范围

| 项 | 说明 |
|---|---|
| 唯一产品改动 | `pet/screen_capture/ocr.py`（文本视图按行成句）+ `pet/screen_capture/translate.py`（指令口径） |
| 测试 | `tests/test_screen_capture_ocr.py` +4 条、`tests/test_screen_capture_translate.py` +1 条，另更新 1 条锁旧「一块一行」口径的既有用例 |
| 版本号 | `pet/__init__.py` 4.3.1 → 4.3.2 |
| 配置键 | 净增 **0**、删除 0、搬迁 0 |
| 安装形态 | onedir 四变体，与 v4.3.1 相同 |

### 人工验收清单（发布前）

- [ ] Windows 安装版：装、启动、卸载（配置保留）；绿色版解压即用
- [ ] 深色小字截图 → 翻译：**原文框成整句、译文成整句**
- [ ] 白底大字截图 → 翻译：与 v4.3.1 表现一致（回归）
- [ ] 中文截图 → 译英文方向同样按行成句
- [ ] 截图问答 / 提取文字两条链路未被带坏（同一 OCR 文本视图的消费者）
- [ ] 升级覆盖后配置与会话仍在

### 本版明确不含

- **DLC / 插件化线的一切**（在 `dlc/mod-center-port` 分支，不进 main）
- OCR 分块与识别精度的改进（属检测/识别层，不在本版）
- v4.3.1 之后新提的任何功能请求

### 构建与发布口径

- 正式构建出在合并提交 `a8d30df` 之上、含版本号与本文档的提交
- 三端构建由 `.github/workflows/build-windows.yml` / `build-linux.yml` / `build-macos.yml` 在 tag 推送时产出并挂到本 Release
- `update.json` 在附件核对通过后单独升版（size 与 sha256 取自本 Release 的真实资产）
