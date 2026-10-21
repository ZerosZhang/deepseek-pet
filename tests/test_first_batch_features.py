# -*- coding: utf-8 -*-
"""第一批功能：灵动岛配置/点击台词绑定/聊天窗置顶的基础测试。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from pet.config import Config


def _config(tmp_path: Path) -> Config:
    return Config(tmp_path)


def test_config_click_talk_bindings_roundtrip(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.set_click_talk_bindings("shenshen", {
        "点击回应 - 开心跃动": ["好耶！", "今天也要开心～"],
        "点击回应 - 傲娇生气": ["哼！"],
    })

    reloaded = Config(tmp_path)
    assert reloaded.click_talk_texts_for("shenshen", "点击回应 - 开心跃动") == ["好耶！", "今天也要开心～"]
    assert reloaded.click_talk_texts_for("shenshen", "点击回应 - 傲娇生气") == ["哼！"]
    assert reloaded.click_talk_texts_for("shenshen", "未绑定动画") == []










