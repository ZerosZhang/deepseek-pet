# -*- coding: utf-8 -*-
"""「允许桌宠跨屏」设置行：全局键、默认关、重启级、保存 round trip。

行本身是常规域「窗口与系统」的一行（位置与分组由 ``test_settings_ia_first_cut``
与 ``test_settings_compat_layering`` 钉住），本文件只管这一行的**行为契约**：

1. 默认关（出厂默认 = 单显示器口径）；
2. 保存 round trip：勾选 → ``_write_config`` 落盘 → 重开对话框仍是勾上的；
3. 作用域是**全局键**：行内带「（影响所有桌宠）」标注，且说明里那句被削到标注里
   （文案只有一份来源，见 ``settings_pet_controls.GLOBAL_SCOPE_ROWS``）；
4. 重启级：勾选只改磁盘，运行中的壳不重读（进程快照，见
   ``tests/test_overlay_cross_screen_switch.py``）；
5. 非 overlay 拓扑（legacy 单窗）下如实置灰 + 说明，不留"改了没反应"的活开关；
6. 默认值标记：它登记在 ``settings_default_marks`` 的映射表里（出厂默认 False）。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import pet.modern_settings_dialog as settings_mod  # noqa: E402
import pet.settings_pet_controls as pet_controls  # noqa: E402
from pet import settings_default_marks  # noqa: E402
from pet.config import Config  # noqa: E402
from pet.modern_settings_dialog import SettingRow  # noqa: E402
from pet.settings_pet_controls import GLOBAL_SCOPE_NOTE  # noqa: E402

app = QApplication.instance() or QApplication([])

ROW_KEY = "cross_screen"
CONFIG_KEY = "allow_cross_screen"


def _dialog(tmp_path, monkeypatch, *, overlay=True):
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(pet_controls, "_is_overlay_topology", lambda: overlay)
    return settings_mod.ModernSettingsDialog(Config(base=tmp_path), include_ai=True)


def _row(dialog) -> SettingRow:
    row = dialog.findChild(SettingRow, f"settingRow_{ROW_KEY}")
    assert row is not None, "常规域「窗口与系统」必须有这一行"
    return row












def test_hint_describes_the_window_count_split_by_scaling():
    """说明文案必须写 v4.3.4 的窗口数分流：混合缩放每屏一窗，全 100% 仍是单窗。

    旧文案（v4.3.3）是「一张合成窗铺满所有显示器组成的桌面」——那是单窗模型：一张窗
    只能有一个 DPR，混合缩放下必有一侧被按错倍率画（#307），两块屏缩放相同但不是
    100% 时又会把 Qt 报错的负原点屏坐标当真（#310）。反向也不能写成"永远每屏一张"：
    多块屏缩放全是 100% 时仍是单窗。
    """
    from pet.settings_pet_controls import CROSS_SCREEN_HINT

    assert "一张合成窗铺满所有显示器组成的桌面" not in CROSS_SCREEN_HINT
    assert "每块屏各自有一张合成窗" in CROSS_SCREEN_HINT
    assert "缩放不是 100%" in CROSS_SCREEN_HINT, (
        "条件必须写出来，否则会被读成「永远每屏一窗」")
    assert "全是 100% 时，仍是一张合成窗" in CROSS_SCREEN_HINT, (
        "全 100% 的多屏还是单窗，这句不能省")
    assert "默认关闭" in CROSS_SCREEN_HINT and "重启后生效" in CROSS_SCREEN_HINT, (
        "默认态与生效时机都是用户第一眼要问的两件事")
    assert CROSS_SCREEN_HINT.endswith(GLOBAL_SCOPE_NOTE), (
        "末句仍是作用域声明原文（由 GLOBAL_SCOPE_ROWS 削进行内标注）")
