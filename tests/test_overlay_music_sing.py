# -*- coding: utf-8 -*-
"""音乐自动唱歌（``music_sing_enabled``）overlay 接线回归（DS 审查 M5f）。

旧架构落点：``window.py:485-489/745-746`` 建 1s 轮询 + 显隐对称启停；
``window_alerts.py:495-550`` 的 host 形实现（检测/唱歌态/静音宽限期）。
overlay 拓扑下 PetWindow 不构造，该键此前零消费（死开关）。

接法对齐 self_talk：壳提供 host 形转发（``_check_music_sing`` /
``_switch`` / ``_is_one_shot_playing``）+ 定时器 + 配置热改/显隐对称。

纪律：offscreen；monkeypatch 音乐检测函数，同步直调 handler，不 sleep。
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import tests.test_sprite_menu_facade as fac
from tests.test_overlay_dead_switches import _make_shell

app = QApplication.instance() or QApplication([])


class _MusicSingHarness:
    """把 shell 与假音乐检测拼起来（不依赖真实音频 COM/素材）。"""

    def __init__(self, shell, playing=True):
        self.shell = shell
        self.playing = playing

    def check(self):
        from pet import music_detect
        original = music_detect.is_music_playing
        try:
            music_detect.is_music_playing = lambda: self.playing
            self.shell._check_music_sing()
        finally:
            music_detect.is_music_playing = original










def _sing_scene():
    """BehaviorController 直连现场：唱歌素材当一次性动画播（无壳/无 extras 链）。"""
    from pet.sprite_behavior import BehaviorController
    from tests.test_sprite_behavior import (
        BOUNDS,
        ScriptedRng,
        _make_library,
        _make_sprite,
    )
    from pet.window import SING_ANIM

    lib = _make_library(idles=["idle1", SING_ANIM])
    sprite = _make_sprite(lib, facing="right")
    c = BehaviorController(BOUNDS, rng=ScriptedRng(rolls=[0.85], ints=(100, 0)))
    c.predict_enabled = False
    assert c.play_once(sprite, SING_ANIM) is True
    return c, sprite, lib, SING_ANIM


def _sing_expire(c, sprite, lib, sing):
    from pet.sprite_behavior import STATE_ACTS
    assert c.state_of(sprite) == STATE_ACTS
    c.tick([sprite], lib.duration(sing) + 0.1)








