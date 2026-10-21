# -*- coding: utf-8 -*-
"""Phase 1 开关式加载门控测试。

验证目标：可选功能关闭时不构造/启动对应服务对象；启用时才懒装配。
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.window import PetWindow


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _disabled_config(tmp_path):
    cfg = Config(base=tmp_path)
    cfg.set("collision_enabled", False)
    cfg.set("decode_broker_enabled", True)  # 依赖碰撞通道，碰撞关时仍不应创建 broker
    cfg.set("todo_reminder_enabled", False)
    cfg.set("click_sound_enabled", False)
    island = dict(cfg.get("dynamic_island", {}))
    island["enabled"] = False
    cfg.set("dynamic_island", island)
    cfg.set("auto_hide_fullscreen", False)
    return cfg


















