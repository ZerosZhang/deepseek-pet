# -*- coding: utf-8 -*-
"""打包面：收费 TTS 凭据要能真的存住，第三方许可要真的随包走。

两条都是**发布阻断级**的缺陷，共同点是「产品界面看不出来」：

1. **keyring 被 no-chat 变体排除**（``build_onedir.ps1`` 与两个 shell 脚本原本把
   ``keyring`` 和 ``pet.chat`` 一起排除）。可语音报时设置页在 chat / no-chat 两条链路上
   都注册（它刻意不依赖 ``pet.chat``），MiMo / 豆包这两个收费后端照旧出现、照旧收
   API Key——只是那个 Key 永远只能落进**写它的进程**的内存里。设置页默认跑在独立
   进程（``settings_process_isolation``），真正合成的 ``VoiceChimeService`` 在主宠
   进程，于是用户填完 Key、界面报「已保存」，而收费后端永远自报「没配 Key」。
   跨进程读不到这件事本身的行为回归在 ``tests/test_tts_secrets.py``，本文件只钉
   **构建参数清单**：四个变体一个都不能少 keyring，且不许再排除它。
2. **LICENSE / THIRD_PARTY_NOTICES.md 不随包**。内置点击音
   （``assets/sounds/duck/Ya1.mp3`` + ``Ya2.mp3``，MIT，MeteorNOX）的许可正文只写在
   仓根 ``THIRD_PARTY_NOTICES.md`` 里，而三端构建只打 ``assets/sounds``、``--add-data``
   里没有那份声明；APK 侧同样只把 ``android/NOTICE.txt`` 拷进资产，MIT 正文靠一句
   「见源码仓库的 THIRD_PARTY_NOTICES.md」交代——那不是随包分发，是给用户一个
   他手里没有的链接。MIT 要求许可正文随复制件一起走。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PS1 = REPO / "scripts" / "build_onedir.ps1"
SHELLS = {
    "linux": REPO / "scripts" / "build_linux.sh",
    "macos": REPO / "scripts" / "build_macos.sh",
}
BUILD_SCRIPTS = [PS1, *SHELLS.values()]
ANDROID_EXPORT = REPO / "scripts" / "export_android_assets.py"
ANDROID_GRADLE = REPO / "android" / "app" / "build.gradle.kts"
ANDROID_NOTICE = REPO / "android" / "NOTICE.txt"
NOTICES = REPO / "THIRD_PARTY_NOTICES.md"

#: 随包分发的两份声明（仓根）：项目自身的 MIT 许可 + 第三方素材/组件声明。
BUNDLED_NOTICES = ("LICENSE", "THIRD_PARTY_NOTICES.md")
#: 收费 TTS 后端（自带 API Key 字段）——它们的存在就是「keyring 必须随每个变体」的理由。
PAID_PROVIDERS = ("doubao", "mimo")
MIT_GRANT = "Permission is hereby granted, free of charge"
METEORNOX_COPYRIGHT = "Copyright (c) 2025 MeteorNOX"


def _args_block(text: str) -> str:
    """shell 脚本里的 PyInstaller 参数数组（``args=(`` … ``)``）。"""
    start = text.index("args=(")
    return text[start : text.index(")\n", start)]


def _pyinstaller_command(text: str) -> str:
    """Windows 脚本里真正交给 PyInstaller 的那段命令（不认注释里的字样）。"""
    return text[text.index("python -m PyInstaller") : text.index("$entry\n")]


# ==================================================== 一、keyring 必须随每个变体走




def test_windows_build_collects_keyring_for_every_variant():
    text = PS1.read_text(encoding="utf-8")

    assert "'--collect-all', 'keyring'" in text, "keyring 的收集参数不见了"
    assert "'--exclude-module', 'keyring'" not in text, (
        "keyring 一旦被排除，no-chat 变体的收费后端凭据就只能留在设置进程内存里"
    )
    assert "$keyringCollect = if ($noChat)" not in text, (
        "keyring 不许再按变体分叉：no-chat 变体同样有收费后端"
    )
    assert "@keyringCollect" in _pyinstaller_command(text), "收集参数没真的交给 PyInstaller"


def test_windows_build_excludes_only_the_chat_subsystem():
    """no-chat 变体该排的是 chat 子系统本体，不是它的存储依赖。"""
    text = PS1.read_text(encoding="utf-8")

    assert "'--exclude-module', 'pet.chat'" in text


# ==================================================== 二、许可与声明必须随包


@pytest.mark.parametrize("script", BUILD_SCRIPTS, ids=lambda p: p.name)
def test_desktop_builds_carry_the_license_and_the_notices(script):
    """三端构建都要把仓根的 LICENSE 与 THIRD_PARTY_NOTICES.md 打进包。

    目标目录是包的数据根（onedir 的 ``_internal``）——内置点击音的 MIT 正文就在
    THIRD_PARTY_NOTICES.md 里，只打 ``assets/sounds`` 等于只分发素材、不分发许可。
    """
    text = script.read_text(encoding="utf-8")
    separator = ";" if script == PS1 else ":"
    command = _pyinstaller_command(text) if script == PS1 else _args_block(text)

    for name in BUNDLED_NOTICES:
        target = f"{name}{separator}."
        assert target in text, f"{script.name} 没有把 {name} 打进包（声明必须随产物分发）"
        wired = [
            line for line in command.splitlines()
            if "add-data" in line and target in line
        ]
        assert wired, (
            f"{script.name} 里的 {name} 没挂在 --add-data 上（写进源码但不交给 "
            f"PyInstaller 等于没写）"
        )


def test_notices_carry_the_full_mit_text_for_the_click_sounds():
    """声明文件里必须有内置点击音的完整 MIT 正文（不是只有一行署名）。"""
    text = NOTICES.read_text(encoding="utf-8")
    section = text.split("## 1. DeepSeek Balance Whale Widget Sound Assets", 1)[1].split(
        "\n---\n", 1
    )[0]
    assert "assets/sounds/duck/Ya1.mp3" in section and "assets/sounds/duck/Ya2.mp3" in section
    assert METEORNOX_COPYRIGHT in text
    assert MIT_GRANT in text


def _load_android_exporter():
    """按文件路径加载导出脚本（``scripts/`` 不是包，import 不进来）。"""
    spec = importlib.util.spec_from_file_location("export_android_assets", ANDROID_EXPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_android_assets"] = module
    spec.loader.exec_module(module)
    return module


def test_android_export_carries_the_notices_into_the_apk_assets(tmp_path):
    """APK 资产里要有声明文件本体，且 MIT 正文真的在资产里（不是一句链接）。"""
    module = _load_android_exporter()
    output = tmp_path / "assets"
    output.mkdir()

    written = module.copy_notices(output)

    names = sorted(path.name for path in written)
    assert names == ["LICENSE-APACHE-2.0.txt", "NOTICE.txt", "THIRD_PARTY_NOTICES.md"]
    for name in names:
        assert (output / name).is_file(), f"{name} 没有真的落进资产"

    exported = (output / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert METEORNOX_COPYRIGHT in exported
    assert MIT_GRANT in exported
    assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in exported, "MIT 正文不完整"


def test_android_notice_points_at_a_file_that_ships_inside_the_apk():
    """NOTICE.txt 里那段 MIT 说明不许再指向"源码仓库"（用户手里只有 APK）。"""
    text = ANDROID_NOTICE.read_text(encoding="utf-8")
    paragraph = text.split("Click sound pair bundled", 1)[1].split("\n\n", 1)[0]

    assert METEORNOX_COPYRIGHT in paragraph
    assert "THIRD_PARTY_NOTICES.md" in paragraph
    assert "source repository" not in paragraph, (
        "声明不能把用户指向他手里没有的源码仓库——那份文件现在就在 APK 资产里"
    )


def test_android_gradle_tracks_the_notice_input():
    """Gradle 的输入清单要含声明文件，否则改了声明不会触发资产重导出。"""
    text = ANDROID_GRADLE.read_text(encoding="utf-8")
    assert 'inputs.file(repository.resolve("THIRD_PARTY_NOTICES.md"))' in text


def test_packaging_doc_registers_the_keyring_rule_and_the_notices():
    """文档面：这两条都是"漏了也不报错"的静默失效，必须写进打包文档。"""
    doc = (REPO / "docs" / "ONEDIR_PACKAGING.md").read_text(encoding="utf-8")
    assert "keyring" in doc
    assert "THIRD_PARTY_NOTICES.md" in doc
    assert "LICENSE" in doc


# ==================================================== 三、构建脚本的编码契约


def test_windows_build_script_keeps_its_utf8_bom():
    """`build_onedir.ps1` 必须带 UTF-8 BOM。

    PowerShell 5.1 **没有** BOM 时按系统 ANSI 码页读 `.ps1`，而这份脚本里全是中文
    注释与中文报错——GBK 环境下会被解成乱码，重则破坏引号配对（脚本里那段"可执行
    字符串保持纯 ASCII"的警告讲的就是这件事）。本轮改这个文件时就踩过一次：BOM 在
    编辑器往返里丢了，而 `Parser::ParseFile` 在本机（中文系统 + UTF-8 环境）**照样
    通过**，diff 里只表现为"首行变了"——只有当构建真在别的中文机器上跑才会暴露。
    """
    assert PS1.read_bytes().startswith(b"\xef\xbb\xbf"), (
        "build_onedir.ps1 的 UTF-8 BOM 丢了；PowerShell 5.1 会按 ANSI 码页读它"
    )


# ==================================================== 四、keyring 的 Windows 后端依赖
def test_build_scripts_collect_keyring_windows_backend_dependency():
    """`--collect-all keyring` 收的是 keyring 自己，不带它的 Windows 后端依赖。

    归因纠正（2026-10-19 实测 PYZ）：4.3.3 的包**并不缺** `win32ctypes`——`_internal`
    目录里没有，但 exe 内嵌 PYZ 里有 27 个 `win32ctypes.*` 模块（PyInstaller 自带的
    hook 收的），冻结包里可以正常导入。所以"缺这个模块"不是那次 401 的根因。
    显式收集仍然要留：隐式 hook 一旦与 keyring 版本失配就会静默丢，症状是钥匙串后端
    不可用（凭据只活在写它的进程内存里）。
    """

    repo = Path(__file__).resolve().parents[1]
    script = (repo / "scripts" / "build_onedir.ps1").read_text(encoding="utf-8")
    assert "win32ctypes" in script, "构建脚本必须显式收集 win32ctypes"
    assert "--collect-all', 'win32ctypes'" in script, (
        "要以 --collect-all 收集（它自己的子模块也要带）")

    requires = (repo / "requirements.txt").read_text(encoding="utf-8")
    assert "pywin32-ctypes" in requires, "运行时依赖要显式声明（不靠 keyring 带）"
