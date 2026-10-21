# PR 报告：打包两个静默失效（keyring 被 no-chat 排除 / 许可声明不随包）

> **基线**：`origin/main` `e08c7fb`（PR #289 之后）
> **分支**：`fix/packaging-tts-keyring-notices`　**日期**：2026-10-17
> **范围**：见 §二（实现 3、构建/资产 6、测试 3、文档 5 含本报告；共 17 个文件，产品改动最小）
> **关联**：发布阻断项（4.3.1 发布前收尾）；打包链路见
> [`ONEDIR_PACKAGING.md`](ONEDIR_PACKAGING.md) 第一、四节与 [`ANDROID.md`](ANDROID.md)

## 一、核心特性

两条都是「**构建不报错、界面看不出来**」的静默失效，本轮把它们变成可见、可拦、有守卫：

| # | 现象（用户视角） | 根因 | 修法 |
|---|---|---|---|
| 1 | 打包版（尤其 no-chat 变体）填了 MiMo / 豆包的 API Key，设置页说「已保存」，报时却永远不出声——收费后端一直自报「没配 Key」 | 三个构建脚本把 `keyring` 与 `pet.chat` **一起**排除在 no-chat 变体之外，而语音报时设置页与它的收费后端在四个变体里都在；凭据只能落进**写它的那个进程**的内存，设置页又是独立进程（`settings_process_isolation`），主宠进程读不到 | 四个变体 × 三端无条件 `--collect-all keyring`，`keyring` 不再出现在任何排除清单里；产物侧清单 `verify_bundle_tts.MINIMUM_MODULES` 加 `keyring`（三端构建期硬门）；界面对写失败如实说「没能保存上（只在本进程内存，重启就没了）」并弹一次提示，删掉「已保存 / 仅本次运行」这类承诺 |
| 2 | 产物里找不到 `LICENSE` / `THIRD_PARTY_NOTICES.md`；内置点击音（MeteorNOX，MIT）的许可正文只在源码仓库里 | 三端 `--add-data` 里没有那两份声明；APK 侧只拷 `android/NOTICE.txt`，MIT 正文靠一句「见源码仓库的 THIRD_PARTY_NOTICES.md」交代 | 三端各加两行 `--add-data`（落包的数据根）；`scripts/export_android_assets.py::copy_notices()` 把声明本体拷进 APK 资产根，`android/NOTICE.txt` 的指向改到 APK 内那份文件 |

**红线 / 不变量**：

- 凭据**只**走系统钥匙串（`pet/tts_secrets`）：不落盘明文、不经 IPC 传 Key、不新增凭据框架；
- `pet.chat` 仍然是 no-chat 变体唯一被排除的产品模块；四个变体、三端脚本的差异只在「排 `pet.chat`」这一点上；
- 设置页在 chat / no-chat 两条链路上都要能打开（不引入对 `pet.chat` 的依赖）；
- **不写任何真实凭据**：本轮全部验证都是只读或指向不存在的 ref。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/tts_secrets.py` | +16 / −5 | `available()`（只判「keyring 模块在不在」）换成 `persisted()`：**回读钥匙串**判断这条凭据是不是真的存住了。前者在「模块在、系统拒绝写」时返回 True，正是界面敢说「已保存」的来源；后者是唯一能区分「钥匙串里有」与「只在本进程内存」的判据。模块文档同步写明内存兜底**跨进程不可见**，以及这是所有变体都要带 keyring 的原因 |
| `pet/voice_chime_settings.py` | +21 / −5 | ① `_apply_secret()` 不再丢掉 `tts_secrets.set()` 的返回值：写失败弹一次 `QMessageBox.warning`（「系统钥匙串不可用：这个 Key 没能保存上，只留在本进程的内存里——重启就没了，其他进程读不到它。」）；② `_secret_state()` 改用 `persisted()`，三态：还没设置 / 已保存 / **没能保存上（只在本进程内存，重启就没了）**，删掉「已保存（仅本次运行）」；③ 模块文档同步 |
| `scripts/verify_bundle_tts.py` | +6 / −0 | 产物侧兜底清单 `MINIMUM_MODULES` 加 `keyring`（含一条为什么在列的注释）：三端在 PyInstaller **之后**都跑这份清单，任何变体少带 keyring 即以退出码 4 中止。只钉脚本里的 `--collect-all keyring` 不够——`--collect-all` 在收集不到时只打一行 WARNING 就继续，这正是这个脚本存在的理由 |
| `scripts/build_onedir.ps1` | +29 / −5 | `$excludes` 的 no-chat 分支只剩 `pet.chat`；`$keyringCollect` 去掉 `if ($noChat)` 分叉（四变体无条件收集）；PyInstaller 参数里新增 `--add-data "LICENSE;."` 与 `--add-data "THIRD_PARTY_NOTICES.md;."`（内联，便于一眼看见）；头部 DESCRIPTION 补一段 |
| `scripts/build_linux.sh` | +14 / −3 | no-chat 变体 `excludes` 由 `pet.chat,keyring` 改成 `pet.chat`；`--collect-all keyring` 从 `*-chat` 条件分支移进无条件的 `args` 数组；新增 `--add-data "LICENSE:."` / `"THIRD_PARTY_NOTICES.md:."` |
| `scripts/build_macos.sh` | +14 / −3 | 同 Linux |
| `scripts/export_android_assets.py` | +22 / −2 | 新增 `NOTICE_FILES` 与 `copy_notices()`：把 `android/NOTICE.txt`、`android/LICENSE-APACHE-2.0.txt` 与**仓根 `THIRD_PARTY_NOTICES.md`** 一起拷进资产根（缺任一份即 `FileNotFoundError` 中止导出）；`main()` 里原来那个两文件循环换成它 |
| `android/app/build.gradle.kts` | +1 / −0 | `exportPetAssets` 的输入清单加 `inputs.file(repository.resolve("THIRD_PARTY_NOTICES.md"))`——否则改了声明不会触发资产重导出（Gradle 增量） |
| `android/NOTICE.txt` | +4 / −4 | 点击音那段不再指向「源码仓库」，改为指向 APK 资产内那份完整正文；角色素材那句同样改指 APK 内的 `THIRD_PARTY_NOTICES.md` 第 2 节 |
| `THIRD_PARTY_NOTICES.md` | +18 / −11 | 第 1 节补「分发方式」并**把 MIT 正文从第 2 节标题下挪回第 1 节**（原先正文挂在"角色素材"那节里，读者会以为那是角色素材的许可）；第 9 节写明 APK 资产里同时分发本文件 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_packaging_keyring_notices.py`（新增） | +264 / −0 | 15 例：① 前提——收费后端（mimo/doubao）的凭据字段对所有变体可见、设置页不依赖 `pet.chat`；② 三端脚本都无条件收集 keyring 且**不再排除**它（Windows 还钉 `$keyringCollect` 真的进 PyInstaller 命令、shell 钉它必须在无条件 `args` 数组里且不在 `*-chat` 分支里）；③ **产物侧清单要求 keyring** 且三端脚本真的在 PyInstaller 之后跑那份清单；④ 三端脚本都带 `LICENSE` / `THIRD_PARTY_NOTICES.md` 的 `--add-data`（并钉那一行真的挂在 `--add-data` 上）；⑤ 声明里是**完整** MIT 正文；⑥ `copy_notices()` 真的把三份文件落进资产根且 MIT 正文在里面；⑦ `android/NOTICE.txt` 不再指向源码仓库；⑧ Gradle 输入清单含该文件；⑨ 打包文档写明这些规则；⑩（本轮自己踩坑后补）`build_onedir.ps1` 的 UTF-8 BOM 不许丢 |
| `tests/test_tts_secrets.py` | +77 / −5 | 原有 6 例按新契约改（`available()` → `persisted()`），新增 2 例：`persisted()` 在「写失败、内存里有值」时必须 False；**跨进程**回归——子进程用 meta_path 钩子挡住 `keyring` 的 import（= 冻结包没有该模块的真实形态），写一次凭据后另一个进程读到空串 |
| `tests/test_voice_chime_settings_layout.py` | +51 / −4 | 重写凭据行状态例（三态 + 断言不再出现「已保存」/「仅本次运行」），新增写失败例：`set()` 返回 False 时必须有弹窗、行状态必须说「没能保存上」、输入框照旧清空 |

### 文档

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `docs/ONEDIR_PACKAGING.md` | +72 / −1 | 第四节改成「no-chat 只排 `pet.chat`」并新增子节「`keyring` 四个变体都带」（现象、根因、为什么与 chat 无关、产物侧清单）；新增子节「随包的许可与声明：`LICENSE` + `THIRD_PARTY_NOTICES.md`」（三端那两个 `--add-data`、为什么不能只靠源码仓库、漏了不报错、本机实测落点、Android 侧同一件事）；冒烟清单补第 10、11 条；「语音依赖门禁」标注清单里多了 `keyring` |
| `docs/ANDROID.md` | +8 / −1 | 资源契约里写清 `copy_notices()` 拷哪三份文件与为什么（含"指向源码仓库不构成随复制件分发许可正文"）；末尾那句「APK 内包含 NOTICE.txt 和 Apache-2.0 全文，并附 MIT 署名」改成「资产内含 NOTICE.txt、Apache-2.0 全文与第三方声明本体」 |
| `docs/INDEX.md` | +3 / −2 | 登记本报告；`ONEDIR_PACKAGING` 行的「何时必读」补 `--exclude-module`/`--collect-all`/`--add-data` 与"no-chat 到底排掉了什么以该文第四节为准"；`THIRD_PARTY_NOTICES.md` 行写明它本身随三端产物与 APK 分发 |
| `docs/PR-REPORT-PACKAGING-KEYRING-NOTICES-2026-10-17.md`（新增） | 本文件 | 三份交付证据 + 未验项 |

**红 → 绿取证**：产品改动前，`tests/test_packaging_keyring_notices.py` 13 例全红、`tests/test_tts_secrets.py` 4 例红、`tests/test_voice_chime_settings_layout.py` 2 例红、产物侧清单那条也红（`keyring` 不在 `MINIMUM_MODULES` 里），共 **20 例**：`persisted` 不存在、构建脚本里仍是旧清单、产物清单不要求 keyring、`copy_notices` 不存在、`android/NOTICE.txt` 仍指向源码仓库、写失败时无弹窗且行状态说「已保存」。改后全绿。第 14 例（BOM 守卫）是本轮自己踩坑后补的，见 §五第 4 条。

### 未改动（刻意）

| 文件/行为 | 为什么不动 |
|---|---|
| `pet/chat/*`、`Config.resolve_api_key`、`SecretStore`、`_migrate_plaintext_keys_to_keyring` | chat 侧「keyring 写失败 → 明文留内存 + 弹窗」是既有哲学（`tests/test_requested_regressions.py::test_ai_page_warns_when_keyring_unavailable`），本轮**不改 settings 哲学**：只把 TTS 凭据那条链路的**谎话**改成实话 |
| `scripts/build_*.sh|ps1` 里 `--collect-all keyring` 的**收集方式** | 保持与 chat 变体一致（那是已发布配置）；`--collect-all` 会把 keyring 自己的 dev 模块一起收进来（本机实测 +约 58 MB，见 §四），最小改法见 §七的后续项 |
| `packaging/dsh-pet.iss` | 安装器整目录拷贝 onedir，`--add-data` 落进 `_internal` 即随安装包分发，无需新条目 |
| `pet/voice_chime_service.py` | 服务侧读凭据的路径（`_secret_values`）本来就走 `tts_secrets.get`，本轮不需要改；收费后端「没配 Key」的提示文案也照旧 |
| `README.md` | 里面的凭据口径都是 chat 的（「API Key 优先使用系统钥匙串」），与本轮无关；第 58 行「无 Chat 版完全不携带 AI 对话依赖」说的是**不加载聊天子系统**，keyring 是凭据存储依赖（chat 与语音报时的收费后端都用它），本轮让它随四个变体走不改变那句话的语义。README 没有文档化收费 TTS 后端，用户可见差异只有包体 |
| `pet/config.py`、`pet/voice_chime.py` | 配置键、清洗、默认值一个字都没动——本轮改的是"凭据能不能存住"和"打包带不带它"，不是配置模型 |

## 三、实现要点

**1. 判据从「模块在不在」换成「回读一次」。** 旧代码：

```python
return "已保存" if tts_secrets.available() else "已保存（仅本次运行）"
```

`available()` 只回答「`import keyring` 成不成功」。系统钥匙串被策略禁用 / keyring 无可用后端时，模块照样 import 成功、`set_password` 抛异常 → `set()` 返回 False，而界面报「已保存」。新的 `persisted(ref)` 直接回读 `keyring.get_password(SERVICE_NAME, ref)`（**只读，且不回落到内存**），所以「内存里有值」不等于「已保存」。这个函数顺带成了设置页三态判据，不再需要任何"猜"。

**2. 写失败必须有一条可见的提示，而不是只在行里换个措辞。** 设置页默认跑在独立进程（`settings_process_isolation`，`pet/config.py`），关窗即退：进程内存里的 Key 对主宠进程**等于不存在**。所以写失败时弹一次 `QMessageBox.warning`（复用 chat 侧同款形态：标题「凭据没能保存上」+ 一句人话），行状态同步为「没能保存上（只在本进程内存，重启就没了）」。文案刻意不写「本次运行有效」——那是独立设置进程下的假话。

**3. 打包侧只留一个差异点，并加一道产物侧的门。** no-chat 变体与 chat 变体的区别应当只有「有没有 chat 子系统」：`pet.chat` 排除、`keyring` 保留（它是凭据存储，与 chat 无关）。四个变体 × 三个平台的清单因此只有一处不同。光靠参数清单还不够——`--collect-all keyring` 在收集不到时只打一行 WARNING 就继续构建（`verify_bundle_tts.py` 的模块文档里记着这个 2026-09-22 的实测），所以同一份清单（`MINIMUM_MODULES`）也要求 `keyring`：三端构建在 PyInstaller 之后都会从**产物 exe 的内嵌 PYZ + `_internal`** 里读真实模块集，缺了就以退出码 4 中止。

**4. 声明随产物走。** 桌面侧用 `--add-data "LICENSE;."`（Windows）/`"LICENSE:."`（POSIX）落包的数据根；APK 侧把仓根那份声明**本体**拷进资产根，并把 `NOTICE.txt` 里「见源码仓库」的说法改掉——用户手里只有产物，指向源码仓库等于没给。

**取舍**：没有为 TTS 凭据另造存储层、没有把 Key 塞进 config.json、没有引入进程间传 Key 的通道（都被显式排除）。也没有把「收费后端在 no-chat 变体里不可用」做成功能开关——产品里它本来就在，缺陷只是它存不住凭据。

## 四、性能分析

**方法（可复现）**：本机 `D:/dsh-pet-wt-packaging-final`（Windows 11 / Python 3.13.7 / PyInstaller 6.22.2 / PySide6 6.11.2 / keyring 25.7.0，后端 `WinVaultKeyring`）。
命令：`python - <<'EOF' … persisted() 计时 n=2000 … EOF`（脚本正文见 §五第 3 条）、
`python -m PyInstaller …`（同一探针 × 四组参数）、`du -sk dist/<probe>`。

| 指标 | 实测 | 归属 |
|---|---|---|
| `import keyring` 冷启动（首次 `_keyring_module()`） | **271.8 ms** | 既有（惰性 import 未改；不发生在启动路径上，只在设置页刷新/服务读凭据时） |
| `persisted()`：一次钥匙串回读（不存在的 ref） | 中位 **185.1 µs** / 均值 293.3 µs（n=2000） | 新增路径 |
| 设置页刷新一行**未设置**的凭据（`get()` 命中空 → 短路，不再回读） | 中位 **181.4 µs** | 与改前同量级（改前这一支只调 `get()`） |
| 设置页刷新一行**已保存**的凭据 | ≈ `get()` + `persisted()` ≈ 2 次钥匙串回读（本机 ≈ 0.4 ms） | 新增（每次刷新 ≤ 2 次系统调用） |
| `_refresh_secret_hints()` 触发频率 | 换后端 / 保存设置 / 清除凭据时各一次；**不在**报时、扫屏、逐帧路径上 | 既有触发点，未新增 |
| 探针产物体积（同一探针、只差参数） | `--collect-all keyring`：**79 612 KB**；只去掉 `--exclude-module keyring`：**21 479 KB**；含 `--exclude-module keyring`：15 736 KB | 打包期 |
| 其中 keyring 本体的落点 | `_internal/keyring` 133 KB + `keyring-25.7.0.dist-info` 44 KB | 打包期 |
| 两份声明随包 | `_internal/LICENSE` **1 085 B** + `_internal/THIRD_PARTY_NOTICES.md` **19 397 B**（≈ 20 KB / 变体） | 新增 |

**结论**：

1. **稳态开销**：运行期新增的只有「凭据行刷新时多一次钥匙串回读」（本机中位 185 µs）。它不参与报时合成、不参与逐帧渲染，进程启动路径一个字节都没多（`pet/tts_secrets` 仍然惰性 import keyring）。**未设置凭据时是 0 次新增调用**（`get()` 为空即短路）。
2. **新增路径的绝对成本与触发频率**：≤ 2 次只读系统调用 / 行 / 刷新；每次刷新由用户动作（换后端、保存、清除）触发，不存在周期性轮询。
3. **有没有新的系统调用 / 网络 / 磁盘 / 线程**：多的是**一次只读的 Windows 凭据管理器访问**（`CredRead`，本就是 `get()` 已经在做的事）；没有新线程、没有网络、没有磁盘写。打包期多两行 `--add-data`（拷贝 20 KB）。
4. **内存与缓存有没有增长**：运行期无新增缓存（`_memory` 语义未变，仍只在写失败时暂存当次输入）；打包体积 **+20 KB（声明）+ keyring 及其后端**——后者在 no-chat 变体上是新增，本机实测「`--collect-all keyring` 相对"只不排除 keyring"多出 **+58 MB**」，来源是 `--collect-all` 把 keyring 自己的开发模块（`keyring.devpi_client`、`keyring.testing` 等）也收进图，连带 `twisted` / `cryptography` / `pywin32` / `zope` / `numpy`（取决于打包机上装了什么）。**两个 chat 变体本来就是这个代价**，本轮把它带到两个 no-chat 变体；要不要收紧见 §七。

## 五、实机运行记录

**环境**：Windows，Python 3.13.7，PyInstaller 6.22.2，worktree `D:/dsh-pet-wt-packaging-final`。
所有原始输出归档在 `.scratch/packaging-final-20261017/`（`evidence.txt`、`build_keyring_*.log`、`full_pytest.log`）。

### 1. 根因现场复现（源码态，跨进程）

把 `_keyring_module` 置空模拟 no-chat 包，同一个进程里写、另一个进程读：

```
设置进程 set() 返回: False | 本进程读回: 'sk-from-settings-process'
主进程（另一进程）读回: ''
```

→ 设置页那份「已保存」对主程序**不成立**。同一次输出还复现了第二种假话：
「后端写失败 set() 返回: False | available(): True | get(): 'k'」——模块在、写失败，旧判据照样说可用。

### 2. 界面现场（offscreen，修前 HEAD）

```
chat 变体：keyring 模块在、系统拒绝写 -> 行提示: '去小米开放平台生成。 · 已保存'      （无弹窗，set() = False）
no-chat 变体：包里没有 keyring       -> 行提示: '去小米开放平台生成。 · 已保存（仅本次运行）'（无弹窗，set() = False）
```

修后同一路径：弹窗「凭据没能保存上 / 系统钥匙串不可用：这个 Key 没能保存上，只留在本进程的内存里——重启就没了，其他进程读不到它。」，行提示「… · 没能保存上（只在本进程内存，重启就没了）」。

### 3. 真实冻结产物（最小 onedir 探针，**不是产品变体**）

探针 `probe_frozen.py` 打印 `sys._MEIPASS`、两份声明在不在、`keyring.get_keyring()` 的类型、以及经 `pet.tts_secrets` 的一次**只读**取凭据（ref 刻意取不存在的名字，绝不写用户凭据）。

修复后的参数（= 现在 no-chat 变体的口径）：

```
{"meipass": "...\\probe-keyring-on\\_internal", "license": true, "notices": true,
 "keyring_backend": "keyring.backends.Windows.WinVaultKeyring",
 "seam_read": "", "seam_persisted": false, "mit_verbatim": true, "licenses_mentions_project_mit": true}
```

消融对照（修复前的参数 `--exclude-module keyring`，无 `--collect-all`）——**构建 exit=0，不报任何错**，运行才炸：

```
  File "probe_frozen.py", line 23, in <module>
ModuleNotFoundError: No module named 'keyring'
```

第三组（只去掉排除、不带 `--collect-all`）：`keyring_backend` 同样是 `WinVaultKeyring`，体积 21 479 KB（证明「静态收集在 Windows 上够用」，但这只在 Windows 上验过，故正式改法仍用 `--collect-all`，见 §七）。

**产物侧清单上膛的实测**（用**同一个门的代码**读上面三个探针的真实模块清单，等价于构建期的 `verify_bundle_tts.py --app-dir`）：

```
probe-keyring-on       frozen_modules= 1653  按新清单缺=[...aiohttp/edge_tts/tabulate...]      ← keyring 不在缺失里
probe-keyring-static   frozen_modules=  635  按新清单缺=[...aiohttp/edge_tts/tabulate...]      ← keyring 不在缺失里
probe-keyring-off      frozen_modules=  121  按新清单缺=[..., 'keyring', 'tabulate']           ← keyring 判缺 ⇒ 退出码 4
```

（探针不带 edge-tts，所以那几项本来就"缺"；关键看 `keyring`：修复后的参数不缺、修复前的参数缺。）

声明落点：`_internal/LICENSE`（1 085 B）与 `_internal/THIRD_PARTY_NOTICES.md`（19 397 B），后者 `MIT_GRANT` / `Copyright (c) 2025 MeteorNOX` / `AS IS` 三段逐字命中。

### 4. 三端脚本的语法与编码（本轮自己踩的坑，如实登记）

- `bash -n scripts/build_linux.sh && bash -n scripts/build_macos.sh` → **shell syntax OK**；
  `powershell.exe -NoProfile -Command "[Parser]::ParseFile(...)"` → **ps1 syntax OK**。
- **踩坑**：本轮改 `build_onedir.ps1` 时，编辑器往返把首行的 **UTF-8 BOM 弄丢了**。PowerShell 5.1
  在没有 BOM 时按**系统 ANSI 码页**读 `.ps1`，而这份脚本里全是中文注释与中文报错——GBK
  环境下会被解成乱码，重则破坏引号配对（脚本里那段"可执行字符串保持纯 ASCII"的警告讲的
  就是这件事）。更隐蔽的是：BOM 丢了之后 **`Parser::ParseFile` 在本机照样通过**，diff 里
  只表现为"首行变了"，只有构建真在中文码页的机器上跑才会暴露。已恢复 BOM，并补一条字节级
  守卫（`tests/test_packaging_keyring_notices.py::test_windows_build_script_keeps_its_utf8_bom`）。

### 5. 没能实机验证的（如实登记）

- **产品变体没有构建**（本轮明确不构建整个包，最终累计候选未定）：上面是等参数的最小探针，验证的是打包参数与冻结布局，不是产品包体与启动。
- **Linux / macOS 的构建与冻结行为未验证**（本机是 Windows）：两个 shell 脚本的改动与 Windows 同构，且由 `tests/test_packaging_keyring_notices.py` 钉住清单；但「Linux 上 keyring 有没有可用后端」取决于 `secretstorage` 之类的后端依赖，**未测**。若某个平台确实没有可用后端，现在会**如实报错**（弹窗 + 行状态「没能保存上」），不再谎称已保存——这正是本轮要达到的行为。
- **Android APK 未构建**：`copy_notices()` 用真实仓库文件跑过（测试里真拷真读，断言 MIT 正文在资产里）；Gradle 只做了输入清单的静态断言，未跑 `assembleDebug`。
- **真实凭据写入未测**（红线：不改用户凭据）：所有路径都用 monkeypatch 的替身 keyring 或只读访问。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed!**（exit 0） |
| 新增守卫（打包清单 + 声明） | `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_packaging_keyring_notices.py` | **15 passed**（产品改动前 13 failed；BOM 守卫为事后新增） |
| 凭据存储 | `pytest -q tests/test_tts_secrets.py` | **10 passed**（改动前 4 failed：`persisted` 不存在） |
| 设置页 | `pytest -q tests/test_voice_chime_settings_layout.py` | **12 passed**（改动前 2 failed：`persisted` 不存在 / 无弹窗） |
| 相关族（语音报时全链） | `pytest -q tests/test_voice_chime_mimo.py tests/test_voice_chime_service.py tests/test_voice_chime.py tests/test_menu_layout.py` | **376 passed** |
| 产物侧门（TTS 清单） | `pytest -q tests/test_verify_bundle_tts.py` | **13 passed**（清单加 `keyring` 后未破既有断言）＋ 上表那条新守卫 |
| 声明/素材既有守卫 | `pytest -q tests/test_presentmon_packaging.py tests/test_verify_rapidocr_models.py tests/test_festival.py` | **149 passed**（含新增那 15 例） |
| 打包/平台/进程隔离族 | `pytest -q tests/test_android_assets.py tests/test_android_acceptance.py tests/test_settings_process_isolation.py tests/test_ci_workflows.py tests/test_application_icon.py tests/test_bundle_slim.py tests/test_config_key_migration.py tests/test_architecture.py` | **175 passed** |
| 交付纪律与登记 | `pytest -q tests/test_pr_report_discipline.py tests/test_packaging_keyring_notices.py` | **193 passed**（报告三节 + INDEX 登记由机器校验） |
| 真实冻结探针（非产品包） | 三组 `python -m PyInstaller …` + 运行产物 + 用门的代码读三份模块清单 | 见 §五第 3 条（修复参数可用 / 旧参数 `ModuleNotFoundError`；旧参数按新清单判缺 `keyring`，两次构建均 exit 0） |
| 三端脚本语法/编码 | `bash -n …` ×2 + PowerShell `Parser::ParseFile` | 见 §五第 4 条 |
| 全量（本机顺序跑） | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | **8065 passed / 16 skipped / 0 failed**（0:23:46；日志 `.scratch/packaging-final-20261017/full_pytest.log`） |
| 三平台 CI（PR [#294](https://github.com/MerZlin/dsh-pet-indesktop/pull/294)） | `gh pr checks 294` | 首轮：macOS **pass**（20m13s）、Ubuntu **pass**（18m52s）、Windows **fail**——失败是 `tests/test_music_lyric.py::test_lyric_request_bypasses_system_proxy` 的浮点相等断言（`7.999999999999886 == 8.0`，`tests/test_music_lyric.py:1485`），与本轮改动无关、本机全量为绿；见下方「CI 状态」 |

**全量状态**：本机顺序全量 **8065 passed / 16 skipped / 0 failed**（23:46；`.scratch/packaging-final-20261017/full_pytest.log`）。首次尝试被会话侧的后台任务时限截断在 49%（日志 `full_pytest_first_try.log` 保留），随后以无时限方式重跑得到上面的结果。

**CI 状态**：PR #294 两轮三平台 CI ——

- 首轮（head `695e8ba`）：macOS **pass** / Ubuntu **pass** / Windows **fail**，失败是
  `tests/test_music_lyric.py::test_lyric_request_bypasses_system_proxy` 的浮点相等断言
  （`assert opener.calls[0][1] == music_lyric.HTTP_TIMEOUT` 实测左边 `7.999999999999886`，
  `tests/test_music_lyric.py:1485`；超时预算是 `deadline - monotonic()` 相减得来的）。
  这条用例在本轮**未触碰**的歌词链路里，本机全量为绿。
- 第二轮（head `9a9387a`，本报告补数那一提交）：**macOS pass 19m26s / Ubuntu pass 13m43s /
  Windows pass 21m56s**——首轮那条 Windows 红确认为既有的时序/浮点假红，未在本 PR 修
  （改它属于另一条线的行为变更）。

CI 只跑测试与门禁工作流，**不跑三端构建**（`build-*.yml` 只在 tag / 手动分发时触发），
所以本轮构建脚本的改动没有 CI 侧产物证据——产物证据是 §五第 3 条的最小 onedir 探针。

**断言有效性（红 → 绿）**：19 例在产品代码改动前全部红（`persisted` 不存在、构建脚本仍排除 keyring、`copy_notices` 不存在、`android/NOTICE.txt` 仍指向源码仓库、Gradle 无该输入、写失败无弹窗），改后全绿——不是"一直绿"的装饰断言。

## 七、已知限制与后续

1. **`--collect-all keyring` 会连带 keyring 自己的开发模块**（`keyring.devpi_client`、`keyring.testing` 等 → `twisted` / `cryptography` / `pywin32` / `zope` / `numpy` 视打包机环境而定）。本机实测相对"只不排除 keyring"多出约 **58 MB**。收紧办法（下一轮，需三端各跑一次真实构建）：把 `--collect-all keyring` 换成 `--hidden-import keyring --collect-submodules keyring.backends --collect-submodules keyring.util` + 保留 `keyring-*.dist-info`（后端是靠 entry points 发现的，dist-info 必须在），并核对冻结包里 `keyring.get_keyring()` 仍解析出真实后端。**本轮不做**：两个 chat 变体已经是这个代价，改它属于另一次行为变更，且本机只能验 Windows。
2. **Linux/macOS 上 keyring 是否真有可用后端未验证**（见 §五第 4 条）。
3. **APK 未构建**；Gradle 侧只验了输入清单与拷贝函数。
4. **收费后端在 no-chat 变体里的可用性**仍取决于用户是否申请到 Key（与变体无关）；本轮只保证「填进去能存住、存不住会说实话」。
5. **`pet.tts_secrets` 的 `persisted()` 每次回读钥匙串**：行状态刷新时 ≤2 次只读调用（本机中位 185 µs）。若日后设置页刷新变频繁，应改成"进程内缓存 + 写/清后失效"，本轮不预先优化。

## 八、风险与回滚

- **影响面**：① 打包参数（三端 × 四变体：no-chat 变体的 `--exclude-module` 少一项、`--collect-all keyring` 变无条件、多两行 `--add-data`，包体 +20 KB 起）；② 设置页凭据行的文案与一次失败弹窗（只在新输入非空且 `set()` 返回 False 时出现）；③ `pet/tts_secrets` 的公共谓词 `available()` → `persisted()`（调用点只有设置页与测试，全仓 grep 确认）。
- **配置迁移**：**没有**新增/删除/改名任何配置键；`config.json` 格式未变；已有钥匙串条目（服务名 `dsh-pet-standalone`、ref `tts/mimo`、`tts/doubao_api_key`）不受影响——`persisted()` 只读不写。
- **失败模式变化**：keyring 不可用时**从「谎称已保存」变成「报没能保存上」**，用户第一次会看到一次弹窗；这是本轮的目的，不是回归。
- **回滚**：`git revert` 后回到旧参数（no-chat 不排 keyring 之前的状态）与旧文案；没有任何落盘状态需要清理（没有新文件落到用户目录，`_memory` 只在进程内）。回滚不会影响已存的钥匙串条目。
