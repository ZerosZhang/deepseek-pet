# -*- coding: utf-8 -*-
"""issue #219：静止放手下落开关（``drop_gravity``）的三重登记与运行期接线。

issue 原声指旧路径（``pet/window.py`` 的 mouseReleaseEvent），但当前默认拓扑是
overlay/sprite 世界（``PET_RENDER_TOPOLOGY`` 缺省 = overlay，legacy 只是 dev
逃生门）——同样的「低速松手 = 原地放下」判定在 ``PetSprite.on_release``
（新路径，探针实测：半空低速松手 pos.y 不动、velocity 归零）。本文件锁新路径
的 ①配置键三重登记（默认值 / reload 白名单 / 快照，另加布尔归一化）
②config → sprite 同步（启动 / 热改 / 子宠 spawn）③设置页往返。

行为面（开关开→零初速进抛掷链落地、开关关→停半空、贴地不弹跳）在
``tests/test_sprite_physics.py``（复用那边的 sprite/物理装配）。
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
from pet import config as config_mod
from pet.config import Config
from pet.overlay_shell import OverlayShell
from pet.pet_sprite import PetSprite

app = QApplication.instance() or QApplication([])


def _slot0_config(tmp_path):
    """生产形态的配置面：slot0 身份经 ``SlotRoutedConfig`` 分流。

    每宠键（``drop_gravity`` 在内）的真值在 ``config-slot-0.json``：裸全局
    ``Config.set/save`` 只碰全局那份，每宠键出闸即被过滤，改不动任何一只宠。
    """
    from pet.settings_slot_config import route_settings_config

    return route_settings_config(Config(base=tmp_path, instance_id="slot-0"))


def _make_shell(tmp_path, values=None):
    """真实 PetSprite + 真 overlay 的壳（复用既有测试装配，风格同
    tests/test_overlay_sprite_settings.py）。"""
    config = cap.CapConfig(tmp_path, values or {})
    instance = cap.CapInstance(config)
    screen = cap.FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    shell = OverlayShell(
        app, instance, screen=screen,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    lib = fac.RichLibrary()
    shell.lib = lib
    shell.sprite.library = lib
    return shell, config


def _write_config(tmp_path, payload: dict) -> None:
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------- ① 配置键契约
def test_default_is_off_and_survives_round_trip(tmp_path):
    """默认关闭（现状语义）；set → save → 重载仍为开（reload 白名单覆盖）。"""
    cfg = _slot0_config(tmp_path)
    assert cfg.get("drop_gravity") is False          # 默认关 = 现状

    cfg.set("drop_gravity", True)
    assert cfg.save() is True

    assert _slot0_config(tmp_path).get("drop_gravity") is True
    assert _slot0_config(tmp_path).data["drop_gravity"] is True


def test_string_false_is_not_truthy(tmp_path):
    """手改配置的字符串布尔不得被 bool() 误开（同族 #129 规约）。"""
    _write_config(tmp_path, {"version": 4, "drop_gravity": "false"})
    cfg = Config(base=tmp_path)
    assert cfg.data["drop_gravity"] is False

    cfg = Config(base=tmp_path)
    cfg.set("drop_gravity", "false")
    assert cfg.data["drop_gravity"] is False

    _write_config(tmp_path, {"version": 4, "drop_gravity": "yes"})
    assert Config(base=tmp_path).data["drop_gravity"] is True


# ---------------------------------------------------------------- ② config → sprite
def test_sprite_gets_drop_gravity_from_config(tmp_path):
    """启动即按 config 下发；refresh_settings 热改生效（不重启、不换 sprite）。"""
    shell, config = _make_shell(tmp_path, {"drop_gravity": True})
    try:
        assert shell.sprite.drop_gravity is True

        config.set("drop_gravity", False)
        shell.refresh_settings()
        assert shell.sprite.drop_gravity is False
    finally:
        shell._delete_runtime_marker()


def test_spawned_sprite_inherits_drop_gravity(tmp_path):
    """spawn 的子肥鱼同样吃这份配置（缺自己的 slot 键回退主配置）。"""
    shell, _config = _make_shell(tmp_path, {"drop_gravity": True})
    try:
        shell._spawn_slot(7)
        spawned = shell._spawned[-1]
        assert spawned.drop_gravity is True
        lib = shell._spawned_libs.pop(spawned)
        shutdown = getattr(lib, "shutdown", None)
        if callable(shutdown):
            shutdown()
    finally:
        shell._delete_runtime_marker()


def test_per_slot_value_applies_to_that_pet_only(tmp_path):
    """per-slot 语义：只有被改的那只子宠按自己那份走（`PER_SLOT_SETTING_KEYS` 登记）。

    旧架构每只桌宠各读自己的 ``config-slot-N.json``；新壳里这张名单就是
    「逐只设置」的物质基础（审计 C1/B7b）。本用例用真落盘 config + 真壳验证
    ``drop_gravity`` 在名单里：改子宠 slot 只影响它自己，主宠一个键都不动。
    """
    import tests.test_overlay_collision_toggle as toggle
    import tests.test_overlay_per_slot_settings as per_slot

    shell, cfg = toggle._make_slot_shell(tmp_path, drop_gravity=False)
    try:
        shell.spawn_pet()
        main, child = list(shell.overlay.sprites)
        assert main.drop_gravity is False and child.drop_gravity is False

        per_slot._write_slot(cfg, 1, drop_gravity=True)
        per_slot._notify(shell)

        assert main.drop_gravity is False     # 主宠不被子宠的设置带跑
        assert child.drop_gravity is True     # 子宠按自己那份 slot 配置
    finally:
        toggle._teardown(shell)


# ---------------------------------------------------------------- ③ 设置页




# ---------------------------------------------------------------- ④ 拓扑作用域
def _dialog_for(cfg):
    from pet.modern_settings_dialog import ModernSettingsDialog

    return ModernSettingsDialog(cfg, include_ai=False)






