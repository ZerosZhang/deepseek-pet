# -*- coding: utf-8 -*-
"""设置页第四刀（2026-10-08）搜索增强的行为验收：折叠组标题入索引 + 口语别名表。

背景（第一刀遗留）：搜索索引原本只有「行 label + hint + objectName」，所以

- 搜**折叠组标题**（「启动项（高级）」「碰撞参数（高级）」「网络延迟检测（高级）」…）
  0 命中——组的名字在索引之外；
- 搜**用户口语**（「网速」「开机启动」「密钥」「壁纸」…）0 命中——行文案用的是另一套词。

口径（主代理裁决）：

1. 组标题命中 ⇒ 该组**全部行**进候选（回车逐行可达），并沿用既有「自动展开折叠 /
   切页内标签」机制——不许只高亮组标题却不给行；
2. 口语别名 = 人工策展的小表（不做拼音引擎、不引入依赖），每条别名都要有「真实用户
   会这么说」的理由；
3. 搜索状态行/计数语义不变；多源命中的同一行只算一次；空查询行为不变；
4. 配置键 / 默认值 / 归属 / 依赖语义零改动。

纪律同 ``tests/test_settings_ia_first_cut.py``：断言走真实 ``ModernSettingsDialog``
这个公开 seam（真实搜索框输入 + 真实回车遍历 + 真实折叠态检查），不调私有方法拼结果。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import pet.modern_settings_dialog as settings_mod
from pet.config import Config
from pet.modern_settings_dialog import SettingRow, SettingsSection
from pet.settings_widgets import SettingsTabContainer

app = QApplication.instance() or QApplication([])

#: 桌宠域两个页内标签（第二刀）的键；「碰撞参数（高级）」属于第 2 个标签。
_TAB_MOTION = "motion_collision"

#: 「碰撞参数（高级）」组内的 5 行（第三刀的口径：音量随物理参数进这一组）。
_COLLISION_ADVANCED_ROWS = (
    "settingRow_collision_restitution",
    "settingRow_collision_friction",
    "settingRow_collision_mass_scale",
    "settingRow_collision_impulse_cap",
    "settingRow_collision_sound_volume",
)


def _dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    return settings_mod.ModernSettingsDialog(Config(tmp_path), include_ai=True)


def _row(dialog, key) -> SettingRow:
    row = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert row is not None, f"缺少设置行 {key}"
    return row


def _section_of(dialog, key) -> SettingsSection:
    """行所属的 ``SettingsSection``（走 widget 祖先链，不用陈旧的 findChildren）。"""
    parent = _row(dialog, key).parentWidget()
    while parent is not None and not isinstance(parent, SettingsSection):
        parent = parent.parentWidget()
    assert parent is not None, f"{key} 必须落在某个 SettingsSection 内"
    return parent


def _page_of(dialog, domain: str):
    index = next(i for i in range(dialog.sidebar.count())
                 if dialog.sidebar.item(i).text() == domain)
    return dialog.pages.widget(index)


def _tabs_of(page):
    return page if isinstance(page, SettingsTabContainer) else page.findChild(
        SettingsTabContainer, "settingsTaskTabs")


def _current_page(dialog):
    return dialog.pages.widget(dialog.sidebar.currentRow())


def _current_match(dialog) -> SettingRow:
    matches = dialog._search_matches
    assert matches, "搜索没有命中任何行"
    return matches[dialog._search_index]


def _matches(dialog, query) -> list:
    """真实搜索框输入（textChanged），返回**全部**候选行。"""
    dialog.search_edit.setText("")
    app.processEvents()
    dialog.search_edit.setText(query)
    app.processEvents()
    return list(dialog._search_matches)


def _search(dialog, query, *, presses: int = 0) -> SettingRow:
    """真实搜索框输入 + 可选回车遍历（eventFilter），返回当前命中行。"""
    _matches(dialog, query)
    for _ in range(presses):
        QTest.keyClick(dialog.search_edit, Qt.Key.Key_Return)
        app.processEvents()
    return _current_match(dialog)


def _keys(rows) -> list:
    return [row.objectName() for row in rows]


# --------------------------------------------------------------- ① 折叠组标题命中






# ------------------------------------------------------------------- ② 口语别名








# --------------------------------------------- ②b 用户视角实测的 0 命中词（2026-10-18）
















# ------------------------------------------------------------------ ③ 去重与计数




# ------------------------------------------------------------- ④ 空/无义查询不回归


# ------------------------------------------------------------------ ⑤ 既有搜索回归


# ---------------------------------------------------------------- Ctrl+F 与索引口径




# ---------------------------------------------------------------- 方向键翻命中




