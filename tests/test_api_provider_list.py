# -*- coding: utf-8 -*-
"""API/Provider 列表：设置页可添加、切换、删除多套 API 配置。"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from pet.config import Config


def _app():
    return QApplication.instance() or QApplication([])










