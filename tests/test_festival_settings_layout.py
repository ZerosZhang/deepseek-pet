# -*- coding: utf-8 -*-
"""节日提醒设置页的呈现回归：常用项平铺、少用项折叠、分组与文案。

机主 2026-10-13 原话（同日先验收语音页整理）：「节日提醒页面也修整一下」——
照语音页那套口径做：常用项平铺在最上面，少用/高级项折成一行（可展开、默认收起），
文案一句话 ≤20 字，界面不出现配置键名/内部机制/文件名/接口实现细节。

这一组用例锁五件事：

1. 「少用项」折叠＝**折叠头行 + 成员行 setVisible**：默认收起、点得开；常见项
   （总开关 / 何时提醒 / 提醒哪些日子 / 怎么提醒 / 生日）全留在平铺区；
2. 分组按心智分（何时提醒 → 提醒哪些日子 → 怎么提醒 → 生日 → 少用项），且行序
   在**真实设置对话框的域卡片**里成立——本页的行会被「语音」域整块收走，那一步只
   搬 ``SettingRow``、不搬容器，所以折叠与分组标题都只能落在行/卡片上；
3. 搜索命中折叠里的行必须自动展开（否则「搜到了却看不见」）；
4. 整页文案黑名单：任何行的标题 + 提示都不许出现配置键名 / 接口与实现细节；
5. 反向断言：从界面删掉的技术细节仍在模块 docstring 里（换地方存档，不是丢失）。

生日是**个人信息**：用例只用合成值（如 10-24），仓库里不得出现任何真实个人日期。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pet.festival_settings import FestivalSettingsPage  # noqa: E402
from pet.festival_settings_panel import (  # noqa: E402
    COLLAPSE_TEXT,
    EXPAND_TEXT,
    FOLD_KEY,
    FestivalFoldPanel,
)
from pet.settings_widgets import SettingRow, SettingsCard  # noqa: E402

#: 设置页上不许出现的技术细节（与 2026-10-13 语音页同一口径）：那些只留在模块
#: docstring/注释里，界面不讲课。
TECHNICAL_MARKERS = (
    "http",
    ".com",
    "www.",
    "edge-tts",
    "edge_tts",
    "ffmpeg",
    "keyring",
    "config.json",
    "festival_",
    "接口",
    "错误码",
    "资源号",
    "uuid",
    "配置文件",
    "模块",
)

#: 折叠的成员行（少用/高级项）：自定义文案与试听
FOLDED_KEYS = (
    "festival_custom_quotes_cn",
    "festival_custom_quotes_west",
    "festival_preview",
)

#: 平铺在最上面的常用行，按预期先后顺序排列（含分组边界）
FLAT_KEYS = (
    # 何时提醒
    "festival_reminder_enabled",
    "festival_reminder_mode",
    "festival_reminder_count",
    "festival_reminder_times",
    # 提醒哪些日子
    "festival_reminder_cn",
    "festival_reminder_solar_terms",
    "festival_reminder_west",
    # 怎么提醒
    "festival_reminder_speak",
    "festival_reminder_animation",
    "festival_reminder_show_quote",
    # 生日
    "festival_birthday",
)

#: 分组标题（域卡片里的 ``sectionTitle``，按呈现顺序）
SECTION_TITLES = ("何时提醒", "提醒哪些日子", "怎么提醒", "你的生日", "少用项")

#: 行标题里不许出现的配置键名痕迹
KEY_LIKE = ("festival_", "_reminder", "settingRow")


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _rows_by_name(widget) -> dict[str, SettingRow]:
    """行按 key 索引。

    域构建前这些行还没有 parent（页面自身不挂它们，整块要被「语音」域收走），
    所以不能只靠 ``findChildren``；域构建后两者一致。
    """
    page = getattr(widget, "festival_page", None) or widget
    panel = getattr(page, "_festival_panel", None)
    if panel is not None:
        return panel.row_map()
    return {
        row.objectName().replace("settingRow_", ""): row
        for row in widget.findChildren(SettingRow)
    }


def _domain(tmp_path, monkeypatch):
    """真实设置对话框里「语音」域的节日提醒卡片（域构建后的真实形态）。"""
    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog

    _qapp()
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dialog = ModernSettingsDialog(Config(tmp_path), include_ai=True)
    labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
    voice_page = dialog.pages.widget(labels.index("语音"))
    page = dialog.festival_page
    return dialog, voice_page, page, FestivalFoldPanel.card_of(voice_page)


def _keys(card: SettingsCard) -> list[str]:
    return [row.objectName().replace("settingRow_", "") for row in card.rows]


def _section_card_keys(page) -> list[list[str]]:
    """域页里各分段卡片的行 key，按分段顺序（每个 ``SettingsSection`` 一张卡）。"""
    from PySide6.QtWidgets import QLabel

    from pet.settings_widgets import SettingsSection

    ordered: list[list[str]] = []
    for section in page.findChildren(SettingsSection):
        ordered.append(_keys(section.card))
    titles = [label.text() for label in page.findChildren(QLabel, "sectionTitle")]
    assert len(ordered) == len(titles), "每个分段标题都该配一张卡片"
    return ordered


def _flat_keys_of(page, wanted) -> list[str]:
    """域页里属于 ``wanted`` 的行 key，按分段卡片顺序拉平（保留呈现顺序）。"""
    wanted = set(wanted)
    return [key for keys in _section_card_keys(page) for key in keys if key in wanted]


def _section_titles(widget) -> list[str]:
    """域里出现的分段标题（按 QObject 树深度优先顺序）。"""
    from PySide6.QtWidgets import QLabel

    return [label.text() for label in widget.findChildren(QLabel, "sectionTitle")]


# ============================================================ 折叠








# ============================================================ 行序与分组








# ============================================================ 文案




def test_page_never_teaches_technical_details(tmp_path):
    """接口地址 / 配置键名 / 实现库名这类细节一个字都不许出现在界面上。"""
    from pet.config import Config

    _qapp()
    page = FestivalSettingsPage(Config(base=tmp_path))
    for row in page._festival_panel.rows():
        text = f"{row.label.text()} {row.hint_label.text()}".lower()
        for marker in TECHNICAL_MARKERS:
            assert marker.lower() not in text, (
                f"{row.objectName()} 又把技术细节摆上界面了：{text}"
            )




# ============================================================ 功能面不变


def test_controls_and_round_trip_are_unchanged(tmp_path):
    """折叠只改呈现：控件仍在、写回与刷新仍按原语义（生日用合成值）。"""
    from pet.config import Config

    _qapp()
    page = FestivalSettingsPage(Config(base=tmp_path))
    page.enabled_check.setChecked(True)
    page.mode_select.setCurrentData("custom")
    page.times_edit.setText("09:00, 20:00")
    page.birthday_edit.setText("10-24")
    page.custom_cn_edit.setPlainText("今宵剩把银釭照，犹恐相逢是梦中。")
    page.apply_to_config()

    assert page.config.get("festival_reminder_enabled") is True
    assert page.config.get("festival_reminder_mode") == "custom"
    assert page.config.get("festival_reminder_times") == "09:00, 20:00"
    assert page.config.get("festival_birthday") == "10-24"

    page.birthday_edit.setText("99-99")
    page.custom_cn_edit.setPlainText("改脏")
    page.refresh_from_config()
    assert page.birthday_edit.text() == "10-24"
    assert page.custom_cn_edit.toPlainText() == "今宵剩把银釭照，犹恐相逢是梦中。"


def test_fold_members_stay_reachable_when_expanded(tmp_path):
    """折叠成员行展开后仍是可用控件（收起不是禁用）。"""
    from pet.config import Config

    _qapp()
    page = FestivalSettingsPage(Config(base=tmp_path))
    page._festival_panel.set_open(True)
    rows = _rows_by_name(page)
    for key in FOLDED_KEYS:
        assert rows[key].control.isEnabled(), f"{key} 展开后必须是可用控件"
    assert rows["festival_preview"].control.text() == "立即试听"


#: 本页唯一该写进 config 的键（整理不得新增/改名/少写）
CONFIG_KEYS = (
    "festival_reminder_enabled",
    "festival_reminder_cn",
    "festival_reminder_solar_terms",
    "festival_reminder_west",
    "festival_reminder_mode",
    "festival_reminder_count",
    "festival_reminder_times",
    "festival_reminder_show_quote",
    "festival_reminder_speak",
    "festival_reminder_animation",
    "festival_birthday",
    "festival_custom_quotes_cn",
    "festival_custom_quotes_west",
)


class _Recorder:
    """只记录写入的 config 替身（不落盘、不碰 schema）。"""

    def __init__(self):
        self.writes: list[tuple[str, object]] = []

    def get(self, key, default=None):
        return default

    def set(self, key, value) -> None:
        self.writes.append((key, value))




def test_fold_header_is_a_presentation_row_only(tmp_path):
    """折叠头是纯展示行：不是配置键，控件就是那颗展开/收起按钮。"""
    from pet.config import Config

    _qapp()
    page = FestivalSettingsPage(Config(base=tmp_path))
    header = page._festival_panel.row_map()[FOLD_KEY]
    assert header.control is page.fold_toggle, "折叠头的控件就是那颗展开/收起按钮"
    assert header.objectName().replace("settingRow_", "") not in CONFIG_KEYS


def test_mode_switch_keeps_enabling_the_right_time_control(tmp_path):
    """提醒方式的启停逻辑原样保留：次数与自定义时间互斥生效。"""
    from pet.config import Config

    _qapp()
    page = FestivalSettingsPage(Config(base=tmp_path))
    page.mode_select.setCurrentData("times")
    assert page.count_spin.isEnabled() and not page.times_edit.isEnabled()
    page.mode_select.setCurrentData("custom")
    assert not page.count_spin.isEnabled() and page.times_edit.isEnabled()
