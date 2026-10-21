# -*- coding: utf-8 -*-
"""「开机自启」在任意宠的设置页都可编辑，且界面明示影响范围（终审 A04-b）。

开机自启是**全局**键（``autostart_wanted`` 写在主配置、系统登录项只有一份），规范 §五
要求"任意宠可以编辑全局设置，但界面必须明确说明影响所有桌宠"。旧判据
``if config.instance_id`` 在 slot0 拿到显式身份（``slot-0``）之后把**主宠自己的页面**
也一起禁掉了，tooltip 还写着"仅主桌宠可设置"——用户正站在主桌宠设置里，按提示找不到
任何可设之处。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog
from pet.settings_slot_config import route_settings_config


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])






