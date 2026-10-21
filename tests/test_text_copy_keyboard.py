# -*- coding: utf-8 -*-
"""只读文本要能用键盘复制（Ctrl+C），不只是鼠标选中 + 右键菜单。

2026-10-19 实机反馈：截图翻译结果里用鼠标选出一段文字，按 Ctrl+C 没反应，只能右键
菜单「复制」。两处成因：

1. **窗口层**：结果面板带 ``WindowDoesNotAcceptFocus``（``WS_EX_NOACTIVATE``），
   连"用户点击后激活"也一并禁掉 → 键盘事件永远进不来。现在只保留
   ``WA_ShowWithoutActivating``（打开时不激活），点击可以让面板获得焦点。
2. **控件层**：一批 QLabel 只设了 ``TextSelectableByMouse``，没有
   ``TextSelectableByKeyboard``，也没有可聚焦策略 → 选中了也没有 Ctrl+C 的落点。
   现在统一补上，并给 ``ClickFocus``（点击才聚焦，不抢 Tab 焦点流）。

这里钉两件事：控件层真按 Ctrl+C 能进剪贴板；那些 QLabel 的 flags/焦点策略没退回去。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

app = QApplication.instance() or QApplication([])






