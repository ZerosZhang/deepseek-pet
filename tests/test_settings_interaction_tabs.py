# -*- coding: utf-8 -*-
"""「互动」域页内分标签（点击与音效 / 自言自语 / 天气 / 趣味）的聚焦回归。

背景：主人反馈「设置界面有点乱，单页面太多东西」。互动域原先 18 行 / 3 组**平铺、
零折叠**，是本仓库最长的"无折叠"域之一；「菜单」域已用 ``SettingsTabContainer``
把同域的多个同级任务分成页内标签（见 test_menu_layout 里的菜单域用例）。

本文件钉住四件事：
1. 互动域确实用页内标签组织，且**侧栏 10 个域不变**（域数量/顺序是外部契约）；
2. 每个设置行都能通过它的标签**到达**（切到对应标签后可见）——"整理后功能仍可用"；
3. 设置搜索命中非默认标签里的行时，**自动切到那个标签**（否则结果不可见）；
4. 全局不变量：所有 ``settingRow_*`` 仍落在某个域页里，不出现「待分类（开发期）」。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

EXPECTED_SIDEBAR = [
    "常规", "桌宠", "互动", "菜单", "桌面组件", "AI 与对话", "自动化与联动", "语音", "文件识别", "更新",
]
# 标签键/名：键给代码（稳定），名给用户（可读）。顺序 = 使用顺序。
# 「天气」（issue #209，2026-10-07）与「点击显示余额」同族——都是"桌宠替你看一眼
# 外部数据"的互动面，故挂在同一个域里当第三个同级任务，而不是新开侧栏域；
# 「抽签」（每日一签，2026-10-15）同族（用户主动拉一次、桌宠给一个结果），是第四个。
# 「快捷键」（2026-10-18）是第五个：用户怎么唤出这三个动作，同属"人宠交互"面。
EXPECTED_TABS = (("click", "点击与音效"), ("self_talk", "自言自语"), ("weather", "天气"),
                 ("divination", "趣味"), ("hotkeys", "快捷键"))

# 每组行各自应该落在哪个标签
ROWS_BY_TAB = {
    "hotkeys": ("hotkey_open_chat", "hotkey_look_screen", "hotkey_screen_capture"),
    "click": (
        "mouse_through", "click_sound", "click_sound_pack", "click_sound_volume",
        "click_sound_preview", "click_balance", "click_self_talk", "click_self_talk_speak",
        "click_self_talk_precache", "click_talk_bindings", "golden_spin_click",
        "golden_spin_direct",
    ),
    "self_talk": (
        "self_talk_bubble_style", "self_talk", "self_talk_duration", "self_talk_min",
        "self_talk_max", "self_talk_texts", "self_talk_images", "self_talk_image_scale",
        "self_talk_image_chance",
    ),
    "weather": ("weather_enabled", "weather_city", "weather_city_list"),
    "divination": ("divination_enabled", "divination_speak", "divination_preview",
                   "divination_hint"),
}


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = _qapp()
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dlg = settings_mod.ModernSettingsDialog(Config(tmp_path), include_ai=True)
    yield dlg
    dlg.close()
    app.processEvents()


def _interaction_page(dialog):
    index = next(
        i for i in range(dialog.sidebar.count()) if dialog.sidebar.item(i).text() == "互动"
    )
    return dialog.pages.widget(index)


def _row(dialog, key: str):
    from pet.modern_settings_dialog import SettingRow

    found = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert found is not None, f"缺少设置行 {key}"
    return found
















# —— 每日一签（「互动 · 抽签」）归位后的四条聚焦口径 ——————————————————
# 它 2026-10-15 曾以一个只有一组「抽签」的**一级域【趣味】**进设置页，靠把侧栏
# 布局间距 3→0 / 导航行距 1→0 挤进 800×560。2026-10-17 按
# docs/SETTINGS-CHANGE-GATES.md 的准入（新一级域须"预计包含至少两个稳定设置组"）
# 判不合格：域撤回、行归位到「互动」页内第四个标签，侧栏间距与行高一个都不动。







