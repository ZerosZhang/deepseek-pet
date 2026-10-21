# -*- coding: utf-8 -*-
"""「桌宠」域页内标签（显示与音乐 / 动作与碰撞）的聚焦回归（第二刀，2026-10-08）。

口径来源：``.scratch/SETTINGS-UI-DESIGN-K3-20261007.md`` §二（页内标签的判定规则）
与第二刀裁决——桌宠域是**两个互斥任务**：「它长什么样 / 唱不唱歌」（显示与音乐）
与「它怎么动 / 怎么撞」（动作与碰撞）；高级组永远垫底其所属标签页；侧栏 10 域、
深链与搜索跳域语义不变。

本文件钉住五件事：

1. 桌宠域确实用页内标签组织、默认激活标签 1、侧栏 10 个域不变（域是外部契约）；
2. 标签内组序：主视线组在前、高级组垫底；每行的 ``SettingsSection`` 归属唯一；
3. 每一行都能由标签键路由到，切到所属标签后可见（分页没丢功能）；
4. 搜索命中另一标签的行时自动切标签 + 展开高级组，命中行**实际可见**
   （标签 1：标题格式 / 自动检测播放器；标签 2：碰撞开关 / 碰撞音量）；
5. 保存 round trip 不变——分页是纯呈现层改动，不碰配置键、默认值与保存链。
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6")

EXPECTED_SIDEBAR = [
    "常规", "桌宠", "互动", "菜单", "桌面组件", "AI 与对话", "自动化与联动", "语音", "文件识别", "更新",
]
#: 标签键给代码（稳定），标签名给用户（可读）；顺序 = 使用顺序。
EXPECTED_TABS = (("display_music", "显示与音乐"), ("motion_collision", "动作与碰撞"),
                 ("character_packs", "角色与素材"))

#: 标签 1 的主视线组序；高级组标题按平台上有没有「标题格式」行动态取
#: （``settings_music.advanced_group_title``），用例里拼。
TAB1_PRIMARY = ("显示", "音乐关联")
#: 标签 2 的组序：主视线 5 组 + 垫底的「碰撞参数（高级）」。
TAB2_SECTIONS = ("动画与移动", "拖拽与弹射", "边缘探头", "生小肥鱼", "多开碰撞", "碰撞参数（高级）")

TAB1_ROWS = (
    "scale", "bubble_text_scale", "pet_opacity",
    "music_sing", "music_lyric", "music_lyric_lead",
)
TAB1_ADVANCED_ROWS = (
    "music_player_netease", "music_player_qqmusic", "music_player_kugou",
    "music_player_soda", "music_player_detect",
)
TAB2_ROWS = (
    "playback_speed", "animation_gap", "idle_low_fps", "no_move",
    "drag_physics", "drop_gravity", "throw_strength", "slingshot_enabled",
    "lock_position", "shift_drag", "edge_probe",
    "spawn_inherit_size", "spawn_scale", "clear_spawned_pets",
    "collision_enabled", "collision_sound_enabled",
)
TAB2_ADVANCED_ROWS = (
    "collision_restitution", "collision_friction", "collision_mass_scale",
    "collision_impulse_cap", "collision_sound_volume",
)
#: 浏览器媒体会话开关与 foobar 两行同样只在 Windows 建（SMTC / 窗口标题源是
#: Windows 专属能力，非 Windows 建行也没效果）——平台闸门，不是被整理掉了。
if sys.platform == "win32":
    TAB1_ROWS = TAB1_ROWS + ("music_browser_media", "foobar_lyrics")
    TAB1_ADVANCED_ROWS = ("foobar_title_format",) + TAB1_ADVANCED_ROWS


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.settings_slot_config import route_settings_config

    app = _qapp()
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    # 生产形态：当前宠的设置页拿 slot0 的路由视图（每宠键写进 config-slot-0.json）
    dlg = settings_mod.ModernSettingsDialog(
        route_settings_config(Config(base=tmp_path, instance_id="slot-0")),
        include_ai=True)
    yield dlg
    dlg.close()
    app.processEvents()


def _pet_page(dialog):
    index = next(
        i for i in range(dialog.sidebar.count()) if dialog.sidebar.item(i).text() == "桌宠"
    )
    return dialog.pages.widget(index)


def _pet_tabs(dialog):
    from pet.settings_widgets import SettingsTabContainer

    tabs = _pet_page(dialog).findChild(SettingsTabContainer, "settingsTaskTabs")
    assert tabs is not None, "桌宠域没有用页内标签组织"
    return tabs


def _row(dialog, key):
    from pet.modern_settings_dialog import SettingRow

    found = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert found is not None, f"缺少设置行 {key}"
    return found


def _row_key(row) -> str:
    return row.objectName()[len("settingRow_"):]


def _sections_of_tab(tabs, tab_key):
    """标签页里按真实布局顺序排列的 ``SettingsSection``（不是 child 顺序）。"""
    from pet.settings_widgets import SettingsSection

    tabs.setCurrentKey(tab_key)
    content = tabs.stack.currentWidget()
    sections = []
    for position in range(content.layout().count()):
        widget = content.layout().itemAt(position).widget()
        if isinstance(widget, SettingsSection):
            sections.append(widget)
    return sections


def _section_title(section) -> str:
    from PySide6.QtWidgets import QLabel

    if section.toggle is not None:  # 高级组：标题在 disclosure 按钮上
        return section.toggle.text()
    label = section.findChild(QLabel, "sectionTitle")
    return label.text() if label is not None else ""


def _section_of(row):
    """行所属的 ``SettingsSection``（走 widget 祖先链）。"""
    from pet.modern_settings_dialog import SettingsSection

    parent = row.parentWidget()
    while parent is not None and not isinstance(parent, SettingsSection):
        parent = parent.parentWidget()
    assert parent is not None, f"{row.objectName()} 必须落在某个 SettingsSection 内"
    return parent










def _search(dialog, query: str):
    """真实搜索框输入（textChanged）+ 事件循环，取当前命中行。"""
    dialog.search_edit.setText("")
    _qapp().processEvents()
    dialog.search_edit.setText(query)
    for _ in range(3):
        _qapp().processEvents()
    matches = dialog._search_matches
    assert matches, f"搜索「{query}」没有命中任何行"
    return matches[dialog._search_index]








