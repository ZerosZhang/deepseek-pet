# -*- coding: utf-8 -*-
"""右键菜单作用对象 = 被点的那一只（批 B2）。

旧版一窗一宠，菜单以 ``pet=self`` 建造，条目天然作用在本窗那一只。overlay 单窗
多宠后 facade 的写操作却硬编码 ``shell.sprite``（主宠），读勾选态/素材清单却用
被点 sprite → 右击子肥鱼改的是主肥鱼、菜单勾选态还停在子宠的旧档。

本文件锁六处缺口（审计 raw.txt F1/F2/F3/A/G）：

1. ``switch_clip`` / ``trigger_move`` / ``set_playback_speed`` / ``change_scale`` /
   ``set_drag_physics`` / ``go_default_corner`` 作用于被点 sprite，素材清单读它的库；
   子宠设置写它自己的 ``config-slot-N.json``（B7b；主配置一字不动）；
2. ``trigger_golden_spin(sprite=...)`` 转被点的那只；
3. ``hide`` 只隐藏被点的那只（主宠 = 宿主窗，维持整窗隐藏语义）；
4. ``look_at_screen(sprite=...)`` 记住发起者；
5. ``DeepSeek 余额`` 的父窗传**发起的那一只**的代次呈现器（手动结果归发起者），
   永久自锁 ``_update_checking``。

装配：真 ``OverlayShell`` + 真 ``PetSprite`` + 真 ``Config``；子宠走真
``shell.spawn_pet()``；余额/更新复用 ``pet.app`` 的真实展示实现（只桩网络边界）。
纪律：offscreen；同步直调 + 事件同步轮询（不赌固定 sleep）。
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import pet.app as app_mod
import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
import tests.test_sprite_menu_parity as parity
from pet.app import AppShell
from pet.config import Config
from pet.overlay_shell import OverlayShell
from pet.pet_sprite import PetSprite
from pet.sprite_menu_facade import SpriteMenuFacade, build_sprite_full_menu

app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- 装配
class _MiniAppShell:
    """最小真实 AppShell 面：余额复用 ``pet.app`` 的真实实现。

    ``show_balance`` 调真实 ``_show_balance_payload``（网络/缓存路径与本缺口无关）。
    """

    def __init__(self, instance=None) -> None:
        self.instance = instance

    def show_balance(self, parent=None) -> None:
        app_mod._show_balance_payload(
            parent, {"text": "余额 12.34", "info": {"total": 12.34}})


class _TargetInstance(parity._StubInstance):
    """PetInstance 面：子宠库带可辨识动作池（判定菜单读的是哪只的库）。"""

    def __init__(self, config, *, chat=True, app_shell=None) -> None:
        super().__init__(config, chat=chat)
        if app_shell is not None:
            self.shell = app_shell
        self.library_calls = 0

    def _create_library(self, character_id):
        self.library_calls += 1
        lib = fac.RichLibrary()
        if self.library_calls > 1:          # 第 2 次起 = 子宠库
            lib.acts = ["child_act"]
            lib._clips["child_act"] = fac.FakeClip("child_act", 24)
        return lib


def _make_shell(tmp_path, *, chat=True, values=None, app_shell=None):
    config = Config(base=tmp_path)
    for key, value in (values or {}).items():
        config.set(key, value)
    instance = _TargetInstance(config, chat=chat, app_shell=app_shell)
    screen = cap.FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    shell = OverlayShell(
        app, instance, screen=screen,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    return shell, instance, config


def _spawn_child(shell):
    """真壳 spawn 出一只子宠（前置不成立就直接红，不放行）。"""
    shell.spawn_pet()
    assert shell._spawned, "spawn_pet 未产出子宠（用例前置不成立）"
    return shell._spawned[0]


def _find_deep(container, label: str):
    """递归找条目（modern 模板把条目录在分组子菜单里）。"""
    for action in container.actions():
        if action.isSeparator():
            continue
        if action.text() == label:
            return action
        submenu = action.menu()
        if submenu is not None:
            found = _find_deep(submenu, label)
            if found is not None:
                return found
    return None


def _require(container, label: str):
    action = _find_deep(container, label)
    assert action is not None, f"菜单缺项 {label}"
    return action


def _wait_until(predicate, timeout=5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


# ---------------------------------------------------------------- F1 六类条目






# ---------------------------------------------------------------- F2 黄金回旋
def test_golden_spin_targets_clicked_sprite(tmp_path):
    """「黄金回旋」转被点的那只（旧版一窗一宠，天然只有被点那只）。"""
    shell, _instance, _config = _make_shell(tmp_path)
    try:
        child = _spawn_child(shell)
        menu = build_sprite_full_menu(shell, child)

        _require(menu, "黄金回旋").trigger()
        assert shell._golden_spin_target is child
        assert shell._golden_spin_timer is not None
        assert shell._golden_spin_timer.isActive()
        assert shell.sprite.throw_rotation == 0.0

        # 控制器角度只写目标 sprite
        shell._golden_spin_started = time.monotonic() - 0.2
        shell._advance_golden_spin()
        assert -360.0 < child.throw_rotation < 0.0
        assert shell.sprite.throw_rotation == 0.0
        # 转满一圈：停表 + 目标 sprite 回正（也顺手收掉在跑的定时器）
        shell._golden_spin_started = time.monotonic() - 1.0
        shell._advance_golden_spin()
        assert not shell._golden_spin_timer.isActive()
        assert child.throw_rotation == 0.0
        assert shell.sprite.throw_rotation == 0.0
    finally:
        shell.clear_spawned_pets()
        shell._delete_runtime_marker()


def test_golden_spin_defaults_to_main_sprite(tmp_path):
    """无参调用（旧调用点）仍转主宠。"""
    shell, _instance, _config = _make_shell(tmp_path)
    try:
        shell.trigger_golden_spin()
        assert shell._golden_spin_target is shell.sprite
        assert shell._golden_spin_timer.isActive()
        shell._golden_spin_started = time.monotonic() - 1.0
        shell._advance_golden_spin()
        assert not shell._golden_spin_timer.isActive()
        assert shell.sprite.throw_rotation == 0.0
    finally:
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- F3 隐藏桌宠
def test_hide_child_keeps_window_and_other_pets(tmp_path):
    """右击子肥鱼「隐藏桌宠」只藏这一只（窗口与主宠照旧）。"""
    shell, _instance, _config = _make_shell(tmp_path)
    try:
        child = _spawn_child(shell)
        shell.overlay.show()
        app.processEvents()
        assert shell.overlay.isVisible()
        facade = SpriteMenuFacade(shell, child)
        facade.hide()
        assert child.visible is False
        assert shell.sprite.visible is True
        assert shell.overlay.isVisible(), "隐藏子宠不得隐藏整窗（其它宠还在）"
    finally:
        shell.clear_spawned_pets()
        shell._delete_runtime_marker()


def test_hide_main_keeps_whole_window_semantics(tmp_path):
    """主宠 = 宿主窗：维持整窗隐藏语义（托盘顶层「显示 / 隐藏」可恢复）。

    主宠逐只隐藏会留下空的可交互合成窗，且无子宠时托盘没有逐只菜单可恢复，
    故主宠保持 ``set_pet_visible(False)``。
    """
    shell, _instance, _config = _make_shell(tmp_path)
    try:
        shell.overlay.show()
        app.processEvents()
        SpriteMenuFacade(shell).hide()
        assert not shell.overlay.isVisible()
    finally:
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- G 看看屏幕


# ---------------------------------------------------------------- A 余额/更新
