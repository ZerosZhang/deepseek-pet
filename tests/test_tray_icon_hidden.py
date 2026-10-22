# -*- coding: utf-8 -*-
"""隐藏托盘图标 + 「再次启动打开设置页」的回归。

两条需求是同一个逃生口的正反面：托盘可以藏，但藏起来之后用户必须还能回到设置与
退出——所以第二次启动桌宠要打开设置页，而不是无声退出。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tests.test_overlay_dead_switches import _make_shell

app = QApplication.instance() or QApplication([])


class _FakeTray:
    """最小托盘替身：只记账显隐（QSystemTrayIcon 在 offscreen 下不一定可用）。"""

    def __init__(self, visible: bool = False):
        self.visible = visible
        self.calls: list[str] = []

    def show(self) -> None:
        self.calls.append("show")
        self.visible = True

    def hide(self) -> None:
        self.calls.append("hide")
        self.visible = False

    def isVisible(self) -> bool:  # noqa: N802 (Qt 命名)
        return self.visible


def _shell_with_fake_tray(tmp_path, values):
    shell, _lib = _make_shell(tmp_path, values)
    shell.tray = _FakeTray(visible=True)
    return shell


# ------------------------------------------------------------------ 配置与设置页
def test_config_defaults_to_visible_tray(tmp_path):
    from pet.config import Config

    assert Config(tmp_path)._initial_data()["tray_icon_hidden"] is False


def test_settings_row_persists_the_hidden_flag(tmp_path):
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog

    config = Config(tmp_path)
    dialog = ModernSettingsDialog(config)
    try:
        row = dialog.findChild(object, "settingRow_tray_icon")
        assert row is not None, "常规域缺「隐藏托盘图标」行"
        assert dialog.tray_icon_check.isChecked() is False
        dialog.tray_icon_check.setChecked(True)
        assert dialog._write_config() is True
        assert Config(tmp_path).get("tray_icon_hidden") is True
    finally:
        dialog.deleteLater()
        app.processEvents()


# ------------------------------------------------------------------ 运行期应用
def test_overlay_shell_hides_and_restores_tray_icon(tmp_path):
    shell = _shell_with_fake_tray(tmp_path, {"tray_icon_hidden": True})
    tray = shell.tray

    shell._apply_tray_icon_visibility()
    assert tray.visible is False, "配置为隐藏时托盘必须收起来"

    shell._config.set("tray_icon_hidden", False)
    shell._apply_tray_icon_visibility()
    assert tray.visible is True, "关掉开关后托盘要重新出现"


# ------------------------------------------------------------------ 再次启动
def test_duplicate_launch_spawns_the_settings_process(monkeypatch):
    import pet.app as app_mod

    seen: list = []

    class _Popen:
        def __init__(self, argv, **kwargs):
            seen.append((argv, kwargs))

    monkeypatch.setattr("subprocess.Popen", _Popen)

    assert app_mod._launch_settings_process() is True
    argv, kwargs = seen[0]
    assert argv[-2:] == ["-m", "pet"] or argv[-2:] == ["--settings"] or "--settings" in argv
    assert "--settings" in argv
    assert kwargs.get("close_fds") is True
    assert kwargs.get("stdin") is not None
    if os.name == "nt":
        assert kwargs["creationflags"] & 0x00000008  # DETACHED_PROCESS


def test_duplicate_launch_uses_the_frozen_exe(monkeypatch):
    import sys

    import pet.app as app_mod

    seen: list = []

    class _Popen:
        def __init__(self, argv, **kwargs):
            seen.append(argv)

    monkeypatch.setattr("subprocess.Popen", _Popen)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert app_mod._launch_settings_process() is True
    assert seen[0] == [sys.executable, "--settings"], seen[0]


def test_duplicate_launch_failure_is_swallowed(monkeypatch):
    import pet.app as app_mod

    def _boom(*_args, **_kwargs):
        raise OSError("no process")

    monkeypatch.setattr("subprocess.Popen", _boom)
    assert app_mod._launch_settings_process() is False


def test_settings_process_flag_routes_without_importing_app():
    """入口侧契约：--settings 必须在 import pet.app 之前分流（省内存的前提）。"""
    from pathlib import Path

    source = Path("packaging/pet_entry.py").read_text(encoding="utf-8")
    assert 'if "--settings" in sys.argv:' in source
    assert source.index('if "--settings" in sys.argv:') < source.index("from pet.app import main")
    # 托盘可用性守卫不应把这条路径写死成"必须有托盘"
    assert QSystemTrayIcon is not None
