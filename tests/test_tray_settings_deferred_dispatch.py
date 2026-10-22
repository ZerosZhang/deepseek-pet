# -*- coding: utf-8 -*-
"""托盘「AI 设置 / 桌宠设置」入口：菜单先关、回调延到菜单跟踪会话之后。

背景：托盘菜单此前是裸 ``menu.addAction(text, callback)``——回调在原生菜单跟踪
会话里**内联执行**。macOS 的托盘菜单是 AppKit 原生 NSMenu，跟踪会话中新建/激活
窗口会被 AppKit 抑制（issue #4 家族：点了没反应，再点一次才对；右键菜单路径早已
用 ``close_on_trigger`` + ``exec()`` 返回后派发解决，托盘菜单没有 ``exec()``
收口点，故走 ``shared.run_after_menu_closed``：菜单先关、等它真的不在了再执行）。

同一口径覆盖托盘菜单里**会改窗面**的其余条目（显示/隐藏、回到右下角、切换角色、
鼠标穿透、开机自启、灵动岛）：它们的旧接法是裸 ``menu.addAction``(回调) 或
``toggled``(回调)，都在菜单跟踪会话里内联执行——显示/隐藏要 ``show()`` 桌宠窗、
切换角色要重建角色窗面（与 issue #4 同病），其余条目改的是窗面/冒泡/系统登录项，
统一到「菜单先关、回调延后」这一条契约上。

验收口径：菜单可见期内回调不得执行；点击后菜单先关；菜单关闭后执行一次。
时序纪律：事件同步 + 宽预算轮询（``app.processEvents()``），不赌固定 sleep。
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from pet.app import AppShell
from pet.config import Config

app = QApplication.instance() or QApplication([])


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def _entry(menu, label: str):
    for action in menu.actions():
        if action.text() == label:
            return action
    raise AssertionError(
        f"托盘菜单缺项 {label}；实际: {[a.text() for a in menu.actions()]}")


class _TrayWin:
    """建托盘所需的最小窗口桩（刻意非 QWidget：_build_tray 的调用方可能是替身）。

    显隐 / 归位 / 穿透都记账：这几条托盘条目本批从「菜单会话内联执行」改为
    「菜单关闭后执行」，回归要能先后点数——先证明没内联，再证明执行了**一次**。
    """

    def __init__(self, config):
        self.config = config
        self._speech_bubble = QWidget()
        self.hidden_bubbles = 0
        self.visible = True
        self.show_calls = 0
        self.hide_calls = 0
        self.corner_calls = 0
        self.mouse_through_calls: list[bool] = []

    def icon_pixmap(self, _size: int = 64) -> QPixmap:
        return QPixmap(2, 2)

    def hide_speech_bubble(self) -> None:
        self.hidden_bubbles += 1

    def go_default_corner(self) -> None:
        self.corner_calls += 1

    def set_mouse_through(self, on: bool) -> None:
        self.mouse_through_calls.append(bool(on))
        self.config.set("mouse_through", bool(on))

    def isVisible(self) -> bool:  # noqa: N802 (Qt 命名)
        return self.visible

    def show(self) -> None:
        self.show_calls += 1
        self.visible = True

    def hide(self) -> None:
        self.hide_calls += 1
        self.visible = False


def _tray_shell(tmp_path):
    """新壳 + 记账窗口桩 + 已建好的托盘菜单（本文件条目级回归共用）。

    窗口桩共用壳自己的 config：显示/穿透这些条目的勾选态与副作用都读同一份配置，
    替身窗口另持一份会让断言看着对、实际接错线。
    """
    shell = AppShell(app, Config(tmp_path), enable_chat=True)
    win = _TrayWin(shell.config)
    tray = shell._build_tray(win)
    menu = tray.contextMenu()
    assert menu is not None
    return shell, win, tray, menu


def _open_menu(menu) -> None:
    menu.show()
    app.processEvents()
    assert menu.isVisible(), "前提：菜单在显示态"


def _submenu(menu, label: str):
    for action in menu.actions():
        if action.text() == label and action.menu() is not None:
            return action.menu()
    raise AssertionError(
        f"托盘菜单缺子菜单 {label}；实际: {[a.text() for a in menu.actions()]}")


def _close_tray(tray, *menus) -> None:
    tray.hide()
    for menu in menus:
        menu.close()
    app.processEvents()


def _legacy_tray(tmp_path, calls):
    shell = AppShell(app, Config(tmp_path), enable_chat=True)
    shell.instance.open_chat_settings = lambda: calls.append("ai")
    shell.instance.open_modern_settings = lambda: calls.append("pet")
    win = _TrayWin(Config(tmp_path))
    tray = shell._build_tray(win)
    menu = tray.contextMenu()
    assert menu is not None
    return shell, tray, menu








def test_overlay_tray_settings_entry_waits_for_menu_close(tmp_path):
    """overlay 拓扑的同一个入口（``OverlayShell._refresh_tray_menu``）同口径。"""
    from tests.test_overlay_spawn import _make_persistent_shell

    shell, _made = _make_persistent_shell(tmp_path)
    opened: list = []
    try:
        shell._instance.shell = SimpleNamespace(
            open_settings_process=lambda inst: (opened.append(inst), True)[1])
        menu = shell.tray.contextMenu()
        assert menu is not None
        menu.show()
        app.processEvents()
        assert menu.isVisible(), "前提：菜单在显示态"

        _entry(menu, "桌宠设置").trigger()
        assert opened == [], "菜单还开着，设置入口不许内联执行"
        assert not menu.isVisible(), "点击后菜单必须先关"
        assert _wait_until(lambda: len(opened) == 1), "菜单关闭后必须打开设置"
    finally:
        menu = shell.tray.contextMenu()
        if menu is not None:
            menu.close()
        shell._teardown_settings_command_watch()
        app.processEvents()


# ------------------------------------------------ 其余改窗面条目：同一契约












# ------------------------------------------------ overlay 托盘全条目：同一契约
def _overlay_tray(tmp_path):
    """overlay 拓扑的托盘 + 菜单（overlay 下用户**实际看到**的那一份）。

    overlay 不构造 PetWindow，托盘挂在 ``OverlayShell`` 上：先前这批修复只覆盖了
    legacy 的 ``AppShell._build_tray``，本文件的其余用例也都打在 legacy 托盘上——
    于是 overlay 拓扑下的裸 ``addAction`` / ``toggled`` 一直没被回归覆盖。
    """
    from tests.test_overlay_spawn import _make_persistent_shell

    shell, _made = _make_persistent_shell(tmp_path)
    menu = shell.tray.contextMenu()
    assert menu is not None
    return shell, menu


def _close_overlay_tray(shell) -> None:
    """收口：菜单（生灭后可能已重建，故从托盘重取）+ 指令 watcher + 运行标记。"""
    if getattr(shell, "tray", None) is not None:
        menu = shell.tray.contextMenu()
        if menu is not None:
            try:
                menu.close()
            except RuntimeError:
                pass  # 菜单已随生灭重建销毁：跳过
        shell.tray.hide()
    shell._teardown_settings_command_watch()
    shell._delete_runtime_marker()
    app.processEvents()


def test_overlay_tray_show_hide_waits_for_menu_close(tmp_path):
    """overlay 托盘「显示 / 隐藏」：动的是合成窗，同样菜单先关再切。"""
    shell, menu = _overlay_tray(tmp_path)
    try:
        shell.overlay.show()
        app.processEvents()
        assert shell.overlay.isVisible(), "前提：合成窗可见"
        _open_menu(menu)

        _entry(menu, "显示 / 隐藏").trigger()
        assert shell.overlay.isVisible(), "菜单还开着，显隐动作不许内联执行"
        assert not menu.isVisible(), "点击后菜单必须先关"

        assert _wait_until(lambda: not shell.overlay.isVisible()), \
            "菜单关闭后必须切换一次显隐"
    finally:
        _close_overlay_tray(shell)


def test_overlay_tray_quit_entry_stays_inline(tmp_path):
    """「退出」刻意不延迟派发：它不是窗面动作，legacy 托盘同为裸 addAction。

    这条把"有意不改"钉住：将来若有人顺手把它也改成延迟派发，本用例会提醒先想清楚
    ——退出发生在原生菜单跟踪会话里不需要 AppKit 放行（会话随进程一起结束）。
    """
    shell, menu = _overlay_tray(tmp_path)
    quit_calls: list = []
    try:
        shell.app = SimpleNamespace(quit=lambda: quit_calls.append(1))
        shell._refresh_tray_menu()
        menu = shell.tray.contextMenu()
        _entry(menu, "退出").trigger()
        assert quit_calls == [1], "「退出」触发即生效（无延迟派发）"
    finally:
        _close_overlay_tray(shell)
