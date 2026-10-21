# -*- coding: utf-8 -*-
"""A3 回归：布尔开关菜单项「标签翻转 + 回调」模板的行为契约。

`_flag_toggle_spec` 把语音报时开关与节日提醒开关的同构实现收成一处
（`pet/context_menus/registry.py`）。本用例钉住提炼后的对外行为：

1. 配置开 → 显示「关闭 X」（点了就关）；配置关 → 显示「启用 X」；
2. `cfg` 缺失时按关处理（历史 `getattr(pet, "cfg", None)` 兜底语义）；
3. 点击落到 pet 上对应的 toggle 回调，且 close_on_trigger 语义不变。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMenu

from pet.context_menus import registry as registry_mod


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    def __init__(self, values: dict):
        self._values = dict(values)

    def get(self, key, default=None):
        return self._values.get(key, default)


class _Pet:
    def __init__(self, values: dict | None = None, with_cfg: bool = True):
        if with_cfg:
            self.cfg = _Cfg(values or {})
        self.voice_calls = 0
        self.festival_calls = 0

    def on_toggle_voice_chime(self):
        self.voice_calls += 1

    def on_toggle_festival(self):
        self.festival_calls += 1






