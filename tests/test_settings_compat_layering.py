# -*- coding: utf-8 -*-
"""常规域的两层收敛：光标穿透回主组、直播捕获单独折叠且只留一句摘要。

原先把「光标隐藏时自动穿透」和「直播捕获兼容」一起塞进一个「Windows 兼容（高级）」——
两者的性质其实不同：前者是普通窗口旗标偏好（跟置顶 / 全屏自动隐藏同族，说明只有两行），
后者才是"要不要现在读"的那种长说明（四段：重启级切换、OBS 捕获方式、平台限制、作用域）。
于是现在：

1. **光标穿透回「窗口与系统」主组**（不再被折叠埋着）；
2. **直播捕获单独进一层高级折叠**，组描述只留**一句摘要**（"这一项做什么"），
   重启 / 平台限制 / 作用域全部留在行内（展开即见全文，分层不等于删说明）。
3. **作用域是行内独立标注**，不再粘在灰说明末尾；但可访问说明与搜索索引仍然拿得到
   这句（同一句话只是换了呈现位置，见 ``SettingRow.set_scope_note``）。

非 Windows 上「直播捕获兼容」与「光标隐藏时自动穿透」这两行都不构造（能力是 Windows
专属），用例一律按**实际构造结果**驱动：缺行就跳过，行在却摆错位置照样红。平台闸门本身
另有 ``test_desktop_pet_features`` 与 ``test_menu_layout`` 盯着。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea  # noqa: E402

import pet.modern_settings_dialog as settings_mod  # noqa: E402
from pet import settings_page_guide  # noqa: E402
from pet.config import Config  # noqa: E402
from pet.modern_settings_dialog import SettingRow, SettingsSection  # noqa: E402
from pet.settings_pet_controls import GLOBAL_SCOPE_NOTE  # noqa: E402

app = QApplication.instance() or QApplication([])

CAPTURE_TITLE = "直播捕获（高级）"
WINDOW_GROUP = "窗口与系统"


def _dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    return settings_mod.ModernSettingsDialog(Config(base=tmp_path), include_ai=True)


def _row(dialog, key: str) -> SettingRow:
    row = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert row is not None, f"缺少设置行 {key}"
    return row


def _section_of(row: SettingRow) -> SettingsSection:
    parent = row.parentWidget()
    while parent is not None and not isinstance(parent, SettingsSection):
        parent = parent.parentWidget()
    assert parent is not None, "行必须落在某个 SettingsSection 内"
    return parent


def _section_by_title(dialog, title: str) -> SettingsSection | None:
    for section in dialog.findChildren(SettingsSection):
        label = section.findChild(QLabel, "sectionTitle")
        name = section.toggle.text() if section.toggle is not None else (
            label.text() if label is not None else "")
        if name == title:
            return section
    return None


def _current_page(dialog):
    return dialog.pages.currentWidget()


def _search(dialog, query: str):
    dialog.search_edit.setText("")
    app.processEvents()
    dialog.search_edit.setText(query)
    app.processEvents()
    return dialog._search_matches[0] if dialog._search_matches else None


def _capture_section(dialog) -> SettingsSection:
    """直播捕获那个高级组。

    **不能静默跳过**：本平台没有这一行（非 Windows）才是合法缺席；一旦行还在、组没了
    （改名/挪回主组/又跟别的开关合组），这里必须红——否则分层结构被改坏时整组用例
    集体"跳过"，等于没人盯着。
    """
    section = _section_by_title(dialog, CAPTURE_TITLE)
    if section is not None:
        return section
    if _optional_row(dialog, "stream_capture") is None:
        pytest.skip("本平台不构造 Windows 专属的直播捕获行（平台闸门另有专用用例）")
    pytest.fail(f"有直播捕获行，却没有「{CAPTURE_TITLE}」这一组：分层结构被改坏了")


def _optional_row(dialog, key: str) -> SettingRow | None:
    return dialog.findChild(SettingRow, f"settingRow_{key}")














def test_section_guide_documents_the_capture_group(tmp_path, monkeypatch):
    """组描述表里有这一组、且没有留下旧组名的残迹（覆盖率守卫的同一口径）。"""
    assert CAPTURE_TITLE in settings_page_guide.SECTION_GUIDE
    assert "Windows 兼容（高级）" not in settings_page_guide.SECTION_GUIDE
    if sys.platform != "win32":  # pragma: no cover - 只在非 Windows 上走到
        dialog = settings_mod.ModernSettingsDialog(Config(base=tmp_path), include_ai=True)
        try:
            assert _section_by_title(dialog, CAPTURE_TITLE) is None
        finally:
            dialog.close()


