# -*- coding: utf-8 -*-
"""G4 宠物间总碰撞开关：settings → OverlayShell → SpriteCollisionWorld（offscreen）。

分层纪律：每 pair 的过滤语义在 ``tests/test_sprite_collision.py``（纯逻辑）；
本文件只验真实接线一层——真 ``OverlayShell`` + 真 ``SpriteCollisionWorld`` +
真 ``PetSprite``（含真实 ``spawn_pet`` 生出的两只子宠），断言「现成 settings 值经
``refresh_settings`` 落到每只 sprite 的资格位，并改变世界的实际结算行为」。

岛（静态成员）与宠物开关彼此独立：岛-宠碰撞由 ``dynamic_island.collision_enabled``
（壳侧挂/摘岛桥）单独负责，本开关只过滤宠-宠 pair。

纪律：同步直调 tick / refresh_settings，不 sleep、不起真实 QTimer 赌时序、不写
真实配置目录（config.dir 全部落在 tmp_path）。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

import tests.test_sprite_menu_facade as fac
from pet import collision as collision_mod
from pet.sprite_collision import SpriteCollisionWorld

app = QApplication.instance() or QApplication([])

# 真 PetSprite 的矩形不小（整画布），摆放重叠量按 rect().width() 实测取一个常量
OVERLAP = 20.0


def _spawn_three_pets(tmp_path):
    """真壳 + 主宠 + 两只子宠（**真实落盘 Config**：子宠身份配置可被 per-slot 读点读到）。

    子宠 spawn 时按旧语义从主配置落种 → 各自 ``config-slot-N.json`` 自带当时那份
    ``collision_enabled``；此后每只按自己的文件走（本文件后面的 per-slot 段专门测）。
    """
    shell, _cfg = _make_slot_shell(tmp_path, collision_enabled=True)
    shell.spawn_pet()
    shell.spawn_pet()
    sprites = list(shell.overlay.sprites)
    assert len(sprites) == 3
    return shell, sprites


def _park(sprite, x):
    sprite.set_pos(QPointF(x, 0.0))
    sprite.set_velocity(QPointF(0.0, 0.0))
    sprite.interaction_state = "normal"


def _setup(world, sprites, *, vx=500.0):
    """a/b 水平重叠 OVERLAP、迎面速度 ±vx；c 停在远处互不接触。

    位置是测试直接摆放的瞬移，故清空帧间扫掠快照（``_prev_circles``）——否则
    把"瞬移跨过对方"当成高速掠过（该语义另在纯逻辑层覆盖）。**注意**：因此本
    文件这条用例不构成"无幽灵残留"的证据；那条结论由
    ``test_pet_collision_toggle_hot_switch_across_ticks`` 承担（全程不清私有簿记）。
    """
    a, b, c = sprites
    a.set_pos(QPointF(0.0, 0.0))
    a.set_velocity(QPointF(vx, 0.0))
    a.interaction_state = "normal"
    b.set_pos(QPointF(float(a.rect().width()) - OVERLAP, 0.0))
    b.set_velocity(QPointF(-vx, 0.0))
    b.interaction_state = "normal"
    _park(c, 3000.0)
    world._prev_circles = {}


def _teardown(shell):
    timer = getattr(shell, "_self_talk_timer", None)
    if timer is not None:
        timer.stop()
    shell._teardown_settings_command_watch()
    overlay = getattr(shell, "overlay", None)
    if overlay is not None:
        overlay.close()
    # 排空延迟音效回调：sprite_sound._submit 用 QTimer.singleShot(0, ...) 把播放
    # 推迟到下一轮事件循环，不排空会漏进下一条用例的 play_sound 打桩里（音量 0.7
    # 的碰撞音被记成别人的点击音）。调两次：回调执行本身也可能再投递事件。
    QApplication.processEvents()
    QApplication.processEvents()






# ---------------------------------------------------------------- G4 残留：per-slot 配置
class _SlotInstance:
    """真壳最小宿主（per-slot 用例用真实 Config）：只提供 per-pet 库工厂。"""

    def __init__(self, config):
        self.config = config

    def _create_library(self, _character_id):
        return fac.RichLibrary()


def _make_slot_shell(tmp_path, **config_values):
    """**真实落盘 Config**（``tmp_path`` 下）的真壳 + 真 PetSprite。

    与上面 ``fac._make_shell``（dict 假 config）不同：per-slot 用例必须走真配置
    文件——``_spawn_slot`` 会用 ``slot_manager.seed_slot_config_from_main`` 把主
    配置落种成 ``config-slot-N.json``，这正是旧架构"每个桌宠各自 config"的物质
    基础。所有写盘都在 tmp_path 内。
    """
    from pet.config import Config
    from pet.overlay_shell import OverlayShell
    from pet.pet_sprite import PetSprite
    from tests.test_overlay_window_capabilities import FakeScreen

    cfg = Config(base=tmp_path)
    for key, value in config_values.items():
        cfg.set(key, value)
    cfg.save()
    shell = OverlayShell(
        app, _SlotInstance(cfg),
        screen=FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)),
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))
    lib = fac.RichLibrary()
    shell.lib = lib
    shell.sprite.library = lib
    return shell, cfg


def _write_slot(parent, slot, **values):
    """按设置进程的写法改 ``config-slot-N.json``（真 Config + 真落盘）。"""
    from pet.config import Config

    from pet.settings_slot_config import route_settings_config

    cfg = route_settings_config(Config(base=parent, instance_id=f"slot-{slot}"))
    for key, value in values.items():
        cfg.set(key, value)
    assert cfg.save()


def _notify_slot_saved(shell):
    """走壳体既有的"配置目录有变动"入口（D12 watcher 的目录事件回调）。"""
    shell._on_settings_command_dir_changed(str(shell._config.dir))


def _save_main(parent, shell, **values):
    """模拟主配置被外部（设置进程/主进程保存）改写：落盘 → reload → 应用。"""
    from pet.config import Config

    from pet.settings_slot_config import route_settings_config

    other = route_settings_config(Config(base=parent, instance_id="slot-0"))
    for key, value in values.items():
        other.set(key, value)
    assert other.save()
    shell._config.reload()
    shell.refresh_settings()


def _flags(shell):
    """当前三只的资格位（主 + 两只子宠，按 overlay 顺序）。"""
    return [bool(getattr(s, "collision_enabled", True))
            for s in shell.overlay.sprites]












