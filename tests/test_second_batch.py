# -*- coding: utf-8 -*-
"""第二批功能：快速对话气泡基础测试。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from pet.config import Config


def _config(tmp_path: Path) -> Config:
    return Config(tmp_path)














def test_quick_chat_survives_initial_cocoa_activation_handoff(tmp_path: Path):
    """已有活动窗口时，首次激活不能被 Cocoa 的过渡失活事件立即关闭。"""
    import pytest
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog

    app = QApplication.instance() or QApplication([])
    if app.platformName() != "cocoa":
        pytest.skip("requires the real Cocoa Qt platform plugin")

    from pet.quick_chat import QuickChatBubble

    settings = QDialog()
    bubble = QuickChatBubble(_config(tmp_path))
    try:
        settings.show()
        settings.raise_()
        settings.activateWindow()
        QTest.qWait(100)

        bubble.show_for_pet()
        QTest.qWait(100)

        assert bubble.isVisible(), "首次激活过渡不能留下空白的已关闭原生窗口"
        assert bubble.isActiveWindow()
    finally:
        bubble.close()
        settings.close()
        app.processEvents()
