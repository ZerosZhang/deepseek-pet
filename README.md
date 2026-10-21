# DeepSeek 桌宠（精简版）

> **本项目参考 [MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop)（MIT）**，是它的**精简版本**：只保留桌宠本体，移除了大量功能（完整清单见文末「已移除的功能」）。上游的原创代码与素材版权归原作者所有，见 [LICENSE](LICENSE) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

一个基于 **Python + PySide6** 的透明桌面宠物：无边框、置顶、可拖拽、会自己走动和播放动画，带右键菜单、系统托盘与设置页。

## 运行

需要 Python 3.13（3.11+ 亦可）与 Windows。

```bat
pip install -r requirements.txt
python -m pet
```

双击 `run.bat` 等价于 `pythonw -m pet`（无控制台窗口）。

配置、日志与缓存写在 `%APPDATA%\dsh-pet-standalone\`，卸载/清理直接删这个目录即可。

命令行参数：

| 参数 | 作用 |
|---|---|
| `--settings` | 只打开设置窗口（独立进程，不加载素材库/托盘） |
| `--slot N` | 指定宠物身份 0..128（内部实现，一般无需使用） |
| `--uninstall-cleanup` | 卸载清理 |

## 功能

- **动画播放**：640×360 透明 WebM / 无损帧序列（frameseq），逐帧 alpha 合成，播放速率可调
- **动画链**：一段播完按概率接下一段（待机/转向/随机动作/移动），不会停住
- **屏幕漫游**：朝面向方向走动，不走出屏幕；转向动画后翻转朝向
- **点击回应**：点击播放回应动画 + Q 弹挤压反馈，连点可打断
- **拖拽**：按住拖动跟手，松手停住；可选边缘探头
- **碰撞**：多宠同屏时互相弹开（单宠下无效果）
- **气泡台词**：自言自语、节日提醒、点击台词；位置与配色可换
- **右键菜单**：播放动画 / 桌宠控制（不移动、窗口置顶、开机自启、回到右下角、隐藏桌宠、黄金回旋、边缘探头）/ 免打扰 / 回收内存 / 节日提醒 / 桌宠设置 / 退出
- **系统托盘**：显示隐藏、开机自启、退出；位置与大小自动持久化
- **设置页**：常规 / 桌宠 / 互动 / 菜单 / 自动化与联动，支持 `Ctrl+F` 搜索
- **免打扰**：全屏应用运行时自动隐身
- **回收内存**：把空闲的工作集还给系统

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_onedir.ps1
```

产物在 `dist-onedir/dsh-pet-standalone-webm-chat/`（onedir，双击 exe 即用）。
可选开关：`-SkipZip`（不出便携 zip）、`-SkipSlim`（不瘦身）、`-SkipFrameseq`（跳过帧序列素材完整性门）。

> 素材门默认要求每个 clip 都有当前世代的 frameseq 产物。补齐缺失的段落：
> `python tools/convert_frameseq.py --character shenshen --include random,events`
> 未补齐时用 `-SkipFrameseq` 打包，缺失段落运行时会回落到 WebM（额外拉起 ffmpeg 子进程）。

## 测试

```bat
python -m pytest -q
```

## 素材

- `assets/characters/<id>/videos/`：源 WebM 动画，随仓库分发
- `assets/characters/<id>/frameseq/`：帧序列派生产物，**不入库**，由 `tools/convert_frameseq.py` 生成
- `assets/sounds/`：内置点击音效（MeteorNOX，MIT，正文见 THIRD_PARTY_NOTICES.md）

## 与上游的差异（只保留核心）

在 `MerZlin/dsh-pet-indesktop` 基础上删除了：

**功能**：AI 对话与余额对话链、看看屏幕 / 截图提问 / 主动识屏、Agent 联动与桥接插件、音乐与歌词、天气、抽签、待办、快捷启动、切换角色与角色包、灵动岛、多实例、直播捕获、彩蛋入口、语音报时 / TTS、文件识别、更新检查。对应的配置键、设置页分组、菜单项一并删除。

**工程面**：Android 版、macOS / Linux 构建脚本与工作流、平台评测脚本、`docs/` 里描述已删功能的 160 余篇设计与 PR 报告、只被已删功能使用的依赖（rapidocr、onnxruntime、winrt、pycaw、psutil 等）与随包资源（OCR 模型 31MB、PresentMon、聊天背景图、彩蛋图池）。

保留的是跑起来和构建必需的部分：`pet/`（产品代码）、`assets/characters/*/videos`（动画素材）、`packaging/`、`scripts/`（Windows 打包与素材门）、`tools/convert_frameseq.py`、`tests/`、`docs/`（8 篇现行约定）。

## 已知限制

- 渲染有 overlay（默认）与 legacy（`PET_RENDER_TOPOLOGY=legacy`）两条拓扑，legacy 是开发逃生门
- 只在 Windows 上验证；macOS / Linux 的构建链已随精简删除
- 帧序列素材当前只有 22/106 段，未转换的段落运行时会回落到 WebM（多出 ffmpeg 子进程）
