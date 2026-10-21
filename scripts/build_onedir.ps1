# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    dsh-pet-standalone onedir build + portable zip packaging.

.DESCRIPTION
    Builds a PyInstaller --onedir variant (no runtime extraction, no _MEI cache),
    output at dist-onedir\<name>\ plus a <name>-portable.zip green package.

    Variants:
      webm-chat   - WebM assets + AI chat (default)
      webm        - WebM assets, no chat
      gif-chat    - GIF assets + AI chat (run with -Gif to generate GIFs first)
      gif         - GIF assets, no chat

    Encoding isolation (issue #26):
      The whole build runs with PYTHONUTF8=1 + PYTHONIOENCODING=utf-8 so neither
      PyInstaller nor the helper scripts can decode UTF-8 sources/resources with
      a legacy codepage (GBK/cp1252). After PyInstaller, an encoding self-check
      (scripts\check_bundle_encoding.py) scans the bundle's bytecode/resources/
      filenames for known Chinese literals and fails the build if any are garbled.

    Bundle slimming (2026-09):
      After PyInstaller + the Qt runtime copy, scripts\slim_bundle.py removes
      statically-unreferenced modules/resources from the bundle (Qt Quick/QML/
      VirtualKeyboard stack, QtPdf, Mesa opengl32sw, non zh/en Qt translations,
      Pillow AVIF plugin, OpenCV's FFMPEG video backend). The script aborts if
      any kept binary still imports a removal candidate, and re-checks a
      required-file manifest right after the removal, so an incomplete runtime
      can never be shipped. -SkipSlim keeps the bundle untouched.

    Credential store + bundled notices (2026-10-17):
      Every variant collects keyring: the settings page runs in its own process, so
      a bundle without keyring can only keep a key in the memory of the process that
      wrote it, and the main pet process never sees it while the UI says "saved".
      The repo-root LICENSE and THIRD_PARTY_NOTICES.md are bundled too: the click
      sounds under assets\sounds\duck are MIT assets whose license text only lives in
      the notices file, so shipping the assets without it ships the material without
      the license.

    Examples:
      powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1
      powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1 -Variant webm -SkipZip
      powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1 -SkipSlim
#>
param(
    [string]$Variant = 'webm-chat',
    [switch]$SkipBuild,
    [switch]$SkipZip,
    [switch]$SkipCheck,
    [switch]$SkipSlim,
    [switch]$SkipFrameseq,
    [switch]$Gif
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$buildStamp = (Get-Date).ToUniversalTime().ToString('o')
Write-Host "[build] pet-runtime-2026-09-01.1 build_started=$buildStamp source=$root" -ForegroundColor DarkCyan

# 编码隔离（issue #26）：整个构建过程强制 UTF-8。
# - PYTHONIOENCODING 只解决控制台 print 中文；PYTHONUTF8=1 让 Python 的
#   locale.getpreferredencoding() 恒为 utf-8，杜绝 PyInstaller/辅助脚本按
#   GBK/cp1252 二次解码源码或资源（乱码包根因）。
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$variants = @{
    'webm-chat' = @{ Name = 'dsh-pet-standalone-webm-chat'; Entry = 'packaging\pet_entry.py' }
    'webm'      = @{ Name = 'dsh-pet-standalone-webm';      Entry = 'packaging\pet_entry_no_chat.py'; NoChat = $true }
    'gif-chat'  = @{ Name = 'dsh-pet-standalone-gif-chat';  Entry = 'packaging\pet_entry.py'; Gif = $true }
    'gif'       = @{ Name = 'dsh-pet-standalone-gif';       Entry = 'packaging\pet_entry_no_chat.py'; Gif = $true; NoChat = $true }
}

if (-not $variants.ContainsKey($Variant)) {
    throw "Unknown variant: $Variant (available: $($variants.Keys -join ', '))"
}
$name  = $variants[$Variant].Name
$entry = $variants[$Variant].Entry
$isGif = $variants[$Variant].Gif
$noChat = $variants[$Variant].NoChat

# GIF builds ship assets/characters_gif (webm dir must NOT be bundled, else runtime prefers webm)
$datas = if ($isGif) { 'assets/characters_gif;assets/characters_gif' } else { 'assets/characters;assets/characters' }
# no-chat 变体只排 chat 子系统本体（2026-10-17 起不再排 keyring）：
# 语音报时设置页与它的收费 TTS 后端（MiMo / 豆包都要 API Key）在四个变体里都在，
# 少了 keyring 的变体只能把 Key 留在**写它的那个进程**的内存里——而设置页跑在独立
# 进程（--settings），主程序读不到，界面却报「已保存」。四个变体三个平台都由
# tests/test_packaging_keyring_notices.py 钉住。
$excludes = if ($noChat) { @('--exclude-module', 'pet.chat') } else { @() }
# PyOpenGL 与本应用无关（Qt 用自带 OpenGL），但其 freeglut_README.txt 是
# CP1252 编码，会触发 check_bundle_encoding 的 UTF-8 严格校验（该自检针对
# 中文资源，第三方 README 属误伤）；排除后包体也更小。
$excludes += @('--exclude-module', 'OpenGL')
# 本机 Python 环境里的 ML/数据科学全家桶（torch/transformers/datasets/
# langchain/pandas/spacy/playwright 等）会被 PyInstaller 模块图连带收集，
# 包体从 ~350M 膨胀到 5G+。全仓 grep 确认应用代码零引用，一律排除。
# 注意：这份排除清单是「打包机 Python 环境」的函数——换机/重装环境/新装库后
# 必须复查（新装的大库会再被连带收集）。
foreach ($m in @('torch','transformers','datasets','langchain','langchain_core',
                 'langchain_openai','langsmith','langgraph','wandb','sentry_sdk',
                 'pandas','numba','llvmlite','pyarrow','polars','_polars_runtime_32',
                 'spacy','playwright','narwhals','sympy','fsspec')) {
    $excludes += @('--exclude-module', $m)
}
# Qt 绑定互斥（2026-09-22 实测：构建被直接中止）。
# 打包机上装了 PyQt5 时，上面那批库（连同 matplotlib 这类经笔记本/绘图栈被连带
# 收集的模块）里的 `qt_compat` 会**条件导入任意 Qt 绑定**，于是 hook-PyQt5 与
# 先运行的 hook-PySide6 冲突，PyInstaller 直接终止：
#   ERROR: Aborting build process due to attempt to collect multiple Qt bindings
#   packages: attempting to run hook for 'PyQt5', while hook for 'PySide6' has
#   already been run!
# 本应用只用 PySide6。按 PyInstaller 报错里给出的处置方式排除其余绑定，构建就
# 不再取决于打包机上恰好装了哪些 Qt 绑定（这正是「排除清单是打包机环境的函数」
# 那条例外的镜像情形：环境多装一个包就能让构建红）。
foreach ($m in @('PyQt5','PyQt6','PySide2')) {
    $excludes += @('--exclude-module', $m)
}
# 再把「把 Qt 绑定拖进来的那条上游链」一并排除（全仓 grep 确认应用零引用；同时
# 省下笔记本/绘图栈的几十 MB）。清单来自 2026-09-22 构建日志里实际出现的 hook。
foreach ($m in @('matplotlib','matplotlib_inline','seaborn','IPython','ipykernel',
                 'jupyter_client','jupyter_core','nbformat','zmq')) {
    $excludes += @('--exclude-module', $m)
}
# 构建机环境污染（2026-10-01 实测部署包 _internal：django 30MB + numpy 27MB）：
# 产品全仓（.py/.spec/.ps1/.json/.toml/.yaml）零 import，requirements.txt 也未声明；
# scripts\slim_bundle.py 的 FORBIDDEN_GLOBS 会对这批做构建期硬闸，这里先让
# PyInstaller 根本不收集。
foreach ($m in @('django','hypothesis')) {
    $excludes += @('--exclude-module', $m)
}
# keyring 必须显式收集，且**四个变体都要**（API Key 的系统安全存储）：no-chat 变体把
# pet.chat 排掉了，静态分析因此摸不到 keyring（chat 的 SecretStore 是它原来的唯一入口），
# 而语音报时的收费后端（pet/tts/mimo、pet/tts/doubao）照旧收 API Key。少了它，凭据只能
# 留在写它的进程内存里，主程序永远读不到（见上面 $excludes 那段）。
$keyringCollect = @('--collect-all', 'keyring')
# **keyring 的 Windows 后端要 win32ctypes**（pywin32-ctypes 包，import 名 `win32ctypes`）。
#
# 注意归因（2026-10-19 核验，纠正先前的说法）：4.3.3 的包**并不缺它**。两项证据要分开看：
# ① 产物层：`CArchiveReader` 读 4.3.3 部署 exe 的内嵌 PYZ，里面有 27 个 `win32ctypes.*`
#    模块（PyInstaller 自带 hook-win32ctypes 收的；`_internal` 目录里看不到它只是"纯 Python
#    模块进 PYZ"的正常表现）。
# ② 模块层（**不是**冻结进程）：以产物 `_internal` 作 sys.path、`python -S` 隔离系统
#    site-packages，`import win32ctypes.pywin32.win32cred` 成功——这只说明包内那份源码能被
#    同版本解释器加载，不能当成"冻结运行时已验证"（keyring 本体会因 jaraco 只在 PYZ 里而
#    在这条路径下 ImportError）。
# 所以"缺这个模块"不是那次 401 的根因。
#
# 仍然显式收集，理由换成加固：那条收集是**隐式**的，依赖 PyInstaller hook 与 keyring
# 版本恰好的配合；hook 消失或依赖布局变化就静默丢，症状是钥匙串后端不可用（凭据只活在
# 写它的进程内存里：界面显示"已保存"、重启后读到空）。显式收集让这件事在构建期可见，
# 并进 `scripts/verify_bundle_tts.py` 的 **Windows** 兜底清单（缺了退出码 4；Linux/macOS
# 不装这个依赖，门禁不许要求它）。
$keyringCollect += @('--collect-all', 'win32ctypes')
# 随包分发的许可与声明：assets\sounds\duck 下的内置点击音是 MeteorNOX 的 MIT 素材，
# 许可正文写在仓根 THIRD_PARTY_NOTICES.md 第 1 节——只打 assets\sounds 等于只分发素材、
# 不分发许可。两份都落在 _internal（onedir 的数据根），安装包整目录拷贝即随分发。
# 这两行刻意写成内联的 --add-data（同 assets\icon.ico 那行）：漏掉不报错，只在产物里
# 静默少一份声明，所以它要待在参数段里一眼看得见（守卫：tests/test_packaging_keyring_notices.py）。
$chatData = @()
# GIF variants: generate GIF assets from webm first (auto when missing, -Gif forces regen)
if ($isGif -and -not $Gif -and -not (Test-Path 'assets\characters_gif')) {
    $Gif = $true
}
if ($Gif -and -not $SkipBuild) {
    Write-Host "[1/3] Generating GIF assets..." -ForegroundColor Cyan
    python scripts\convert_to_gif.py --force --clean
    if ($LASTEXITCODE -ne 0) { throw "convert_to_gif failed: $LASTEXITCODE" }
}

# 停掉正在运行的旧 exe：无论是否重跑 PyInstaller，产物都可能被活进程占用
# （进程加载的 Qt 插件会锁住 PySide6\*.dll / translations，导致瘦身删除报
#  WinError 5 拒绝访问）。属构建期自愈，不触碰用户数据。
$running = Get-Process -Name $name -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "[build] stopping running $name before build/post-processing..." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Milliseconds 800
}

if (-not $SkipBuild) {
    Write-Host "[0/3] Generating app icon..." -ForegroundColor Cyan
    python scripts\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw "make_icon failed: $LASTEXITCODE" }

    # 素材硬门（2026-10-08）：帧序列产物 assets\characters\<角色>\frameseq\ 是刻意
    # 不入库的派生产物（.gitignore），只在构建机的素材源里存在。worktree / 新克隆
    # 天然没有它，而上面 $datas 对非 GIF 变体**整树拷贝** assets\characters——素材
    # 在就进包、缺了也不报错，于是缺帧序列的包会被静默打出来，用户长期看到未转换
    # 素材（白边）。这里在 PyInstaller 起跑前验证每个 clip 都有当前世代的帧序列
    # 产物，非零即中止（脚本自己的中文报错已打到 stderr，含怎么补）。
    # GIF 变体跳过本门：它打包的是 assets\characters_gif（由 convert_to_gif.py
    # 从 webm 直出 GIF），素材树里没有也没有 frameseq 这一层，本门不适用。
    if (-not $isGif -and -not $SkipFrameseq) {
        Write-Host "[frameseq] verifying frame-sequence material completeness..." -ForegroundColor Cyan
        python scripts\check_frameseq_bundle.py
        if ($LASTEXITCODE -ne 0) { throw "check_frameseq_bundle failed: $LASTEXITCODE" }
        Write-Host "[frameseq] frame-sequence material OK" -ForegroundColor Green
    }

    # DLL 冲突隔离（issue: Qt6Core "procedure not found" / 找不到指定的程序）：
    # conda 的 Library\bin 与 MiKTeX 的 bin\x64 各自携带一套 Qt6/ICU DLL（版本与
    # PySide6 6.11 不匹配）。PyInstaller 的 bindepend 会按 PATH 解析 Qt6Core.dll 的
    # icuuc.dll 依赖并把 conda 的 ICU 75 打进包内，运行时 QtCore 加载即报
    # "DLL load failed ... 找不到指定的程序"。这里在构建期间把这两类目录从 PATH
    # 剔除，让 bindepend 只看到 PySide6 自带 DLL 与系统 System32 的兼容 ICU。
    # 注意：若 PySide6 是 conda 包（DLL 在 Library\bin），此剔除会导致 DLL 缺失，
    # 此时应改用 pip 版 PySide6 构建（DLL 在 site-packages\PySide6）。
    $env:PATH = ($env:PATH -split ';' | Where-Object {
    $_ -and $_ -notmatch '(?i)(conda|miniconda)[\\/].*[\\/]Library[\\/]bin$' -and
        $_ -notmatch '(?i)[\\/]envs[\\/].*[\\/]Library[\\/]bin$' -and
            $_ -notmatch '(?i)MiKTeX[\\/]miktex[\\/]bin'
    }) -join ';'

    # 注：运行中的旧 exe 已在进入本块之前统一停掉（见上面的 $running 段），
    # 否则 PyInstaller 无法覆盖 exe，后续瘦身也会因 DLL 被活进程锁定而失败。
    Write-Host "[1/3] PyInstaller --onedir building $name ..." -ForegroundColor Cyan
    # 注入变体标识：配置目录/会话/开机自启按变体隔离（pet/config.py 读取）。
    # 必须写 BOM-free UTF-8：PowerShell 5.1 的 Set-Content -Encoding UTF8 会带
    # BOM，且内容若含中文再被旧编辑器按 GBK 另存就会污染产物（issue #26）。
    $variantPy = Join-Path $root 'packaging\build_variant.py'
    [System.IO.File]::WriteAllText(
        $variantPy,
        "VARIANT = '$Variant'`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    # 运行期图标（窗口/标题栏）也要进包：上面的 --icon 只把图标写进 exe 的**文件图标**
    # 资源，窗口图标由 pet/application_icon.py 从 <_MEIPASS>\assets\icon.ico 读。
    # 漏掉这一行不会有任何报错（只有源文件不存在时 PyInstaller 才会挡下），因此由
    # tests/test_application_icon.py 的打包契约测试守着。见 docs\ONEDIR_PACKAGING.md
    # 「运行期应用图标」。
    python -m PyInstaller --noconfirm --clean --onedir --windowed --noupx `
        --name $name `
        --distpath dist-onedir `
        --workpath build-onedir `
        --icon assets\icon.ico `
        --collect-all imageio_ffmpeg `
        --collect-all certifi `
        --collect-all PySide6.QtMultimedia `
        --collect-all tzdata `
        @keyringCollect `
        --add-data $datas `
        --add-data "assets\big_blue_fat_fish\ojingjing.jpg;assets\big_blue_fat_fish" `
        --add-data "pet\persona_presets;pet\persona_presets" `
        --add-data "pet\menu_templates;pet\menu_templates" `
        @chatData `
        --add-data "assets\sounds;assets\sounds" `
        --add-data "assets\icon.ico;assets" `
        --add-data "LICENSE;." `
        --add-data "THIRD_PARTY_NOTICES.md;." `
        @excludes `
        $entry
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
}

$appDir = Join-Path $root "dist-onedir\$name"
if (-not (Test-Path $appDir)) { throw "Build output missing: $appDir" }

# =====================================================================
# Qt runtime post-build (issue: shiboken6 "找不到指定的模块")
# =====================================================================
# conda 版 PySide6 的 Qt6 runtime DLL 位于 <env>\Library\bin（不在
# site-packages\PySide6），PyInstaller 只收集了 .pyd 绑定，导致运行时
# QtCore.pyd 加载失败。这里用 sys.prefix 定位 conda 环境（不猜目录层数），
# 独立成 post-build 阶段：把 Qt6*.dll 与已验证的非系统依赖复制进 bundle
# 的 PySide6 runtime 目录，并兜底补齐 platform plugin。
# 注意：本段 Write-Host 消息保持纯 ASCII——PowerShell 5.1 按系统 ANSI
# 码页解析 .ps1，可执行字符串里的中文在 GBK 环境下会破坏引号配对。
$pythonPrefix = (& python -c "import sys; print(sys.prefix)").Trim()
$condaBin = Join-Path $pythonPrefix "Library\bin"
$condaQtPlugins = Join-Path $pythonPrefix "Library\lib\qt6\plugins"
$bundlePySide = Join-Path $appDir "_internal\PySide6"
$bundleShiboken = Join-Path $appDir "_internal\shiboken6"

# 此前已用 pefile 解析出的 conda Qt6 非系统依赖（Q6 运行必需）
$qtNonSystemDeps = @(
    'MSVCP140.dll','MSVCP140_1.dll','MSVCP140_2.dll',
    'VCRUNTIME140.dll','VCRUNTIME140_1.dll',
    'double-conversion.dll','freetype.dll','libcrypto-3-x64.dll',
    'libpng16.dll','pcre2-16.dll','zlib.dll','zstd.dll',
    'icudt75.dll','icuin75.dll','icuuc75.dll'
)

Write-Host "[Qt] Python prefix: $pythonPrefix"

if (Test-Path (Join-Path $condaBin 'Qt6Core.dll')) {
    # ---------- conda 版 PySide6：补充 Qt runtime ----------
    Write-Host "[Qt] Runtime source: $condaBin"
    Write-Host "[Qt] Copying runtime..."
    if (-not (Test-Path $bundlePySide)) { throw "[Qt] bundle PySide6 dir missing: $bundlePySide" }
    Get-ChildItem $condaBin -Filter 'Qt6*.dll' -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item $_.FullName $bundlePySide -Force
    }
    foreach ($dep in $qtNonSystemDeps) {
        $depSrc = Join-Path $condaBin $dep
        if (Test-Path $depSrc) { Copy-Item $depSrc $bundlePySide -Force }
    }
    # conda PySide6/Shiboken 共享 DLL 在 Library\bin，不在 site-packages\shiboken6
    # Shiboken.pyd 直接依赖 shiboken6.cp310-win_amd64.dll（conda 命名），
    # QtCore.pyd 直接依赖 pyside6.cp310-win_amd64.dll（conda 命名）——
    # 缺任何一个都会报 "DLL load failed while importing ..."。
    $shibokenDll = Join-Path $condaBin 'shiboken6.cp310-win_amd64.dll'
    if (Test-Path $shibokenDll) {
        Copy-Item $shibokenDll $bundleShiboken -Force
        Write-Host "[Qt] copied shiboken6.cp310-win_amd64.dll to shiboken6/"
    }
    $pyside6Dll = Join-Path $condaBin 'pyside6.cp310-win_amd64.dll'
    if (Test-Path $pyside6Dll) {
        Copy-Item $pyside6Dll $bundlePySide -Force
        Write-Host "[Qt] copied pyside6.cp310-win_amd64.dll to PySide6/"
    }
    Write-Host "[Qt] Copying plugins..."
    $dstPlatforms = Join-Path $bundlePySide 'plugins\platforms'
    if (-not (Test-Path (Join-Path $dstPlatforms 'qwindows.dll'))) {
        if (Test-Path (Join-Path $condaQtPlugins 'platforms')) {
            if (-not (Test-Path $dstPlatforms)) { New-Item -ItemType Directory -Path $dstPlatforms -Force | Out-Null }
            Copy-Item (Join-Path $condaQtPlugins 'platforms\*') $dstPlatforms -Force
            Write-Host "[Qt] copied platform plugins from $condaQtPlugins"
        } else {
            throw "[Qt] qwindows.dll missing and conda plugin dir not found: $condaQtPlugins"
        }
    }
    Write-Host "[Qt] Runtime validation OK" -ForegroundColor Green

    # ---------- Fix Python SSL DLL missing for conda builds ----------
    # Copy Python SSL dependencies (libcrypto/libssl) from conda Library/bin to bundle _internal root
    # Required because _ssl.pyd (Python's SSL module) depends on these DLLs, they aren't always collected automatically
    foreach ($dep in @('libcrypto-3-x64.dll', 'libssl-3-x64.dll')) {
        $depSrc = Join-Path $condaBin $dep
        $depDst = Join-Path $appDir "_internal\$dep"
        if (Test-Path $depSrc) {
            Copy-Item $depSrc $depDst -Force
            Write-Host "[SSL] copied $dep to bundle _internal/ (fixes import ssl DLL load error)"
        }
    }
} else {
    Write-Host "[Qt] pip PySide6 (Qt6 DLL bundled), runtime copy skipped" -ForegroundColor Yellow
}

# ---------- Qt runtime 硬性验证（无论 conda/pip 都执行） ----------
$qtRequired = @(
    'Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','plugins\platforms\qwindows.dll'
)
foreach ($rel in $qtRequired) {
    $full = Join-Path $bundlePySide $rel
    if (-not (Test-Path $full)) { throw "[Qt] required file missing in bundle: $rel" }
}
if (Test-Path (Join-Path $condaBin 'Qt6Core.dll')) {
    foreach ($dep in $qtNonSystemDeps) {
        if (-not (Test-Path (Join-Path $bundlePySide $dep))) {
            throw "[Qt] conda Qt dependency missing in bundle: $dep"
        }
    }
    # 验证 shiboken6.cp310-win_amd64.dll 与 pyside6.cp310-win_amd64.dll 已进 bundle
    if (-not (Test-Path (Join-Path $bundleShiboken 'shiboken6.cp310-win_amd64.dll'))) {
        throw "[Qt] shiboken6.cp310-win_amd64.dll missing in bundle shiboken6/"
    }
    if (-not (Test-Path (Join-Path $bundlePySide 'pyside6.cp310-win_amd64.dll'))) {
        throw "[Qt] pyside6.cp310-win_amd64.dll missing in bundle PySide6/"
    }
}
Write-Host "[Qt] Runtime validation OK" -ForegroundColor Green

# DLL 冲突自检（issue: Qt6Core "procedure not found"）：若构建环境 PATH 里混入
# conda/MiKTeX 的 Qt6 或 ICU DLL，PyInstaller 会错误打包进 onedir 目录，运行时
# QtCore 加载报 "找不到指定的程序"。此处扫描产物，发现即中止并给出明确指引。
# 注：我们主动补进 _internal\PySide6 的 Qt6/ICU DLL（conda Qt 自身运行所需的
# icu*.dll）属预期，自检白名单排除该 runtime 目录；其他位置出现的意外
# ICU/Qt6 DLL 仍按原规则报告冲突。
# pip PySide6 6.11.2 and the bundled Poppler runtime both use ICU 78.3.
# PyInstaller resolves Poppler's ICU dependencies into _internal root, so
# location alone is not enough to classify these files as a conflict. Keep
# rejecting stale/foreign ICU versions, while allowing this known-compatible
# pair only after checking the file version.
$allowedIcu = @('icuuc.dll', 'icudt78.dll')
$badIcu = Get-ChildItem -Recurse -Path $appDir -Filter 'icu*.dll' -ErrorAction SilentlyContinue |
    Where-Object {
        if ($_.DirectoryName -like '*\_internal\PySide6') { return $false }
        $version = $_.VersionInfo.FileVersion
        -not ($allowedIcu -contains $_.Name -and $version -like '78, 3, 0, 0*')
    }
$badQt = Get-ChildItem -Recurse -Path $appDir -Filter 'Qt6*.dll' -ErrorAction SilentlyContinue |
    Where-Object {
        # pip PySide6 wheels are collected by PyInstaller into _internal root;
        # conda builds and manually copied runtimes use PySide6/.  Both are
        # valid locations, while nested foreign runtime directories remain
        # rejected.
        $_.DirectoryName -notlike '*\_internal' -and
            $_.DirectoryName -notlike '*\PySide6*' -and
            $_.DirectoryName -notlike '*\shiboken6*'
    }
if ($badIcu -or $badQt) {
    $names = @($badIcu.Name) + @($badQt.Name)
    throw "Bundle contains incompatible Qt/ICU DLLs ($($names -join ', ')). " +
        "This causes 'DLL load failed ... 找不到指定的程序'. Build with a PATH " +
        "that excludes conda Library\bin and MiKTeX miktex\bin."
}

# ---------- onedir 瘦身（scripts\slim_bundle.py，2026-09） ----------
# 移除静态零引用 + 代码零使用的模块与冗余资源：Qt Quick/QML/VirtualKeyboard
# 栈、QtPdf、Mesa 软件 OpenGL 后备（opengl32sw.dll）、非 zh/en 的 Qt 翻译、
# Pillow AVIF 插件。slim_bundle.py 先做依赖闭包校验（任一保留二进制仍 import
# 待删文件即中止），删除后再校验必需清单（Qt 核心/平台插件/ffmpeg 多媒体插件/
# Python 绑定），任何一步失败都 throw，绝不静默产出残缺包。
# 位置约束：必须在上面 Qt runtime 复制之后——否则复制会把刚删掉的 DLL 带回来。
# 输出消息保持纯 ASCII——PowerShell 5.1 按 ANSI 码页解析可执行字符串。
if (-not $SkipSlim) {
    Write-Host "[1.5/3] Slimming bundle (unused Qt modules / redundant resources)..." -ForegroundColor Cyan
    python scripts\slim_bundle.py --app-dir $appDir
    if ($LASTEXITCODE -ne 0) { throw "Bundle slimming failed: $LASTEXITCODE" }
    Write-Host "[slim] bundle slimmed" -ForegroundColor Green
}

# 中文编码自检（issue #26）：字节码字面量/文本资源/中文文件名任一项被
# 编码污染即中止，绝不把乱码包发出去。
if (-not $SkipCheck) {
    Write-Host "[1.6/3] Chinese-encoding self-check on bundle..." -ForegroundColor Cyan
    python scripts\check_bundle_encoding.py --dir $appDir
    if ($LASTEXITCODE -ne 0) {
        throw "Bundle encoding check failed - refusing to package garbled output (issue #26)"
    }
}

# 窗口出现等待：轮询 + 宽预算，禁止「固定 sleep 后只判一次」。
# 依据（2026-09-23 v4.2.1 同版本重构建实踩）：Windows runner 冷启动 ~10 s 才出窗，
# 旧写法 sleep 10 s 后只判一次，上一次侥幸 10.05 s 过、这一次 >10 s 直接假红。
# 本机更极端：从未跑过的 bundle 首启主窗实测 44.4 s（杀毒软件首扫 330 MB 目录），
# 热盘时同一步只要 1.9 s。窗口出现是异步事件，只能轮询等；超时才判死。
# 预算 90 s = 已观测最坏值的 2 倍，且每次都打印实测耗时，便于日后判假红。
function Wait-SmokeWindow {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][string]$Label,
        [string]$EarlyExitHint = 'runtime dependency broken',
        [string]$NoWindowHint = "startup failed (likely 'Failed to execute script')",
        [int]$TimeoutSec = 90
    )
    $t0 = Get-Date
    $deadline = $t0.AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        if ($Process.HasExited) {
            throw "[smoke] $Label exited early (code $($Process.ExitCode)) - $EarlyExitHint"
        }
        $Process.Refresh()
        if ($Process.MainWindowHandle -ne 0) {
            $elapsed = ((Get-Date) - $t0).TotalSeconds
            Write-Host ("[smoke] $Label window appeared after {0:N1}s" -f $elapsed) -ForegroundColor DarkGray
            return
        }
    }
    throw "[smoke] $Label running but no window appeared within ${TimeoutSec}s - $NoWindowHint"
}

# ---------- exe smoke test（启动成功才继续打包） ----------
# 注意：PyInstaller --windowed 在 import 失败时会弹错误对话框且进程存活，
# 只看"进程 8 秒没退出"是假阳性。这里先做确定性加载链验证（从 bundle 布局
# 真实加载 Shiboken/QtCore/QtGui/QtWidgets），再启动 exe 检查主窗口出现。
$exePath = Join-Path $appDir "$name.exe"
if (-not (Test-Path $exePath)) { throw "Build exe missing: $exePath" }

$verifyScript = Join-Path $root 'scripts\verify_bundle_qt.py'
if (-not (Test-Path $verifyScript)) { throw "missing verify script: $verifyScript" }
Write-Host "[smoke] verifying bundle DLL chain (Shiboken/QtCore/QtGui/QtWidgets)..." -ForegroundColor Cyan
python $verifyScript --internal (Join-Path $appDir '_internal')
if ($LASTEXITCODE -ne 0) { throw "[smoke] bundle DLL chain verification failed" }
Write-Host "[smoke] bundle DLL chain OK" -ForegroundColor Green

Write-Host "[smoke] Launching $exePath ..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $exePath -PassThru
try {
    Wait-SmokeWindow -Process $proc -Label 'exe'
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}
Write-Host "[smoke] exe started OK" -ForegroundColor Green

# ---------- --settings 分流冒烟（设置页进程隔离） ----------
# exe 必须能按参数分流到独立设置进程：起的是一个设置窗口（不是又一只桌宠），
# 并且持有 settings.lock。用隔离的 APPDATA，避免冒烟配置写进用户目录。
Write-Host "[smoke] Launching $exePath --settings ..." -ForegroundColor Cyan
$smokeBase = Join-Path $env:TEMP ("dsh-settings-smoke-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $smokeBase -Force | Out-Null
$oldAppData = $env:APPDATA
$env:APPDATA = $smokeBase
$settingsProc = $null
try {
    $settingsProc = Start-Process -FilePath $exePath -ArgumentList '--settings' -PassThru
    Wait-SmokeWindow -Process $settingsProc -Label '--settings' `
        -EarlyExitHint 'arg routing broken' `
        -NoWindowHint 'no settings window appeared'
    # 配置目录名随打包变体走（= $name，如 dsh-pet-standalone-webm-chat），
    # 写死基础名会让 webm-chat 等变体误报"没拿到锁"（实机踩过）
    $settingsLock = Join-Path (Join-Path $smokeBase $name) 'settings.lock'
    if (-not (Test-Path $settingsLock)) {
        throw "[smoke] --settings did not acquire settings.lock"
    }
} finally {
    if ($settingsProc -and -not $settingsProc.HasExited) {
        Stop-Process -Id $settingsProc.Id -Force -ErrorAction SilentlyContinue
    }
    $env:APPDATA = $oldAppData
    Remove-Item $smokeBase -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "[smoke] --settings started OK" -ForegroundColor Green

if (-not $SkipZip) {
    Write-Host "[2/3] Packing portable zip..." -ForegroundColor Cyan
    $zip = Join-Path $root "dist-onedir\$name-portable.zip"
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path "$appDir\*" -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "      $zip ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)" -ForegroundColor Green
}

Write-Host "[3/3] Done. onedir dir: $appDir" -ForegroundColor Green
Write-Host "      Installer: compile packaging\dsh-pet-$Variant.iss with ISCC.exe"
