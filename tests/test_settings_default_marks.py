# -*- coding: utf-8 -*-
"""设置页第三刀「已修改标记 + 默认值小字 + 单项重置」的行为验收（2026-10-08）。

口径来源：主代理裁决（本刀 §③）+ ``docs/SETTINGS-CHANGE-GATES.md`` +
``.scratch/SETTINGS-UI-DESIGN-K3-20261007.md`` §五（第三刀：默认值呈现 + 单项重置）。

本文件钉住七件事：

1. 全默认配置下**整窗没有任何标记**（默认态与改动前一致）；
2. 改不同类型控件的值 → 恰好对应数量的标记出现，且默认值文本正确；
3. 单项重置只改控件值：延迟写回行**保存前 Config 与磁盘都没被动过**，即时生效行
   （``click_sound_enabled``）重置后**立即**写盘——落盘时机跟着该行自己的保存语义，
   重置不新增写回路径；
4. 重置后保存并退出 → 新开的 Config 读回默认值（round trip 不绕开既有写回）；
5. 子宠页的**全局**行（开机自启，写 OS 登录项）可编辑且行内写明"影响所有桌宠"——
   判据是"能不能改"，不是"是哪只宠的页面"；同页的 per-slot 行不受影响；
6. 被依赖开关隐藏的行不显示标记；前置开关重新打开后标记回来（不做可见性记账）；
7. 没有可比配置默认值的行（逐服务商字段 / 列表成员 / UI 记忆）不显示标记也不报错，
   四类之外的控件类型同样不参与。

纪律：断言全部走真实 ``ModernSettingsDialog`` 这个公开 seam；「可见」用真实的域切换 +
页内标签 + 折叠展开（``_reveal``）后取 ``isVisible()``，不假定隐藏控件上的标记算数。
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox

import pet.modern_settings_dialog as settings_mod
from pet import settings_default_marks
from pet.config import Config
from pet.modern_settings_dialog import SettingRow
from pet.settings_widgets import (
    BrowserSpinBox,
    ModernSelect,
    SettingsTabContainer,
    ToggleSwitch,
)

app = QApplication.instance() or QApplication([])

#: 四类受支持控件（本刀只认这四类，其余控件类型整行不参与）；
#: ``QDoubleSpinBox`` / ``QComboBox`` / 自绘选择器 / 路径选择器都不在此列。
_SUPPORTED_TYPES = (ToggleSwitch, ModernSelect, BrowserSpinBox, QLineEdit)

#: 「四类控件 + 没有可比默认值」的行快照（逐服务商字段 / 列表成员 / UI 记忆）。
#: 现状文档化：新增这类行会让覆盖率用例变红，逼一次显式归类（不是静默漏掉）。
NO_DEFAULT_ROWS = frozenset({
    # AI 服务商逐条目字段：每个服务商一套值，没有单一默认值可比
    "provider_name", "api_url", "model", "api_key", "timeout", "max_tokens", "skip_ssl",
    "vision_same", "vision_model", "vision_url", "vision_key",
    # 深度思考开关/强度也是逐服务商字段（ProviderConfig.thinking/reasoning_effort）
    "thinking_mode", "reasoning_effort",
    # 搜索 API Key 是凭据字段（优先系统钥匙串），没有可比默认值
    "web_search_key",
    # 岛指标行是 island_metrics **列表**的成员，不是标量键
    "island_network", "island_cpu", "island_mem", "island_gpu", "island_fps",
    # 台词编辑器的「上次打开的层」是 UI 记忆，不是偏好
    "dialogue_scope",
})


def _is_supported(control) -> bool:
    return isinstance(control, _SUPPORTED_TYPES)


def _row_key(row) -> str:
    return row.objectName()[len("settingRow_"):]


def _row(dialog, key) -> SettingRow:
    row = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert row is not None, f"缺少设置行 {key}"
    return row


def _reveal(dialog, row) -> None:
    """把行真正呈现出来：选中所属域 → 切到所属页内标签 → 展开折叠它的组。

    分页 / 标签 / 折叠都是既有呈现层机制，测试走它们（而不是假定行在屏幕外也算
    "可见"），才能证明标记对用户真的看得见。
    """
    page = row.parentWidget()
    while page is not None and dialog.pages.indexOf(page) < 0:
        page = page.parentWidget()
    assert page is not None, f"{row.objectName()} 不在任何设置域页里"
    dialog.sidebar.setCurrentRow(dialog.pages.indexOf(page))
    parent = row.parentWidget()
    while parent is not None:
        if isinstance(parent, SettingsTabContainer):
            parent.activate_for_descendant(row)
        toggle = getattr(parent, "toggle", None)
        if toggle is not None and not toggle.isChecked():
            toggle.setChecked(True)
        parent = parent.parentWidget()
    app.processEvents()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """真实设置窗（主宠页）+ 它的 Config 与配置目录。

    配置面按生产形态给：slot0 身份经 ``SlotRoutedConfig`` 分流，每宠键（点击音效、
    气泡方案…）写进 ``config-slot-0.json``，全局键仍进 ``config.json``。
    """
    from pet.settings_slot_config import route_settings_config

    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    cfg = route_settings_config(Config(base=tmp_path, instance_id="slot-0"))
    dialog = settings_mod.ModernSettingsDialog(cfg, include_ai=True)
    dialog.show()
    app.processEvents()
    yield dialog, cfg, tmp_path
    dialog.close()
    app.processEvents()


def _marked(dialog) -> list[str]:
    """当前处于「已修改」态的行键（按控件自带状态，不受所属页面是否在前台影响）。"""
    return sorted(
        _row_key(row) for row, _control, _default in dialog._default_mark_rows
        if not row.modified_mark.isHidden()
    )


# —— ① 默认态整窗无标记 ——————————————————————————————————————————



# —— 布局与可访问性（GATES §3）：标记/按钮不压控件、都在行内、读屏说得清 ———



# —— ② 改过就出现，默认值文本正确 ————————————————————————————————





# —— ③ 单项重置：只改控件；落盘时机跟着该行自己的保存语义 ————————





# —— ④ 保存并退出后读回默认 ————————————————————————————————————





# —— ⑤ 子宠页：主宠专属行置灰且不提供重置 ————————————————————————



# —— ⑥ 依赖隐藏行不出标记，前置开关回来标记也回来 ——————————————



# —— ⑦ 没有默认值可比的键不显示标记，也不报错 ————————————————







# —— 默认值来源护栏 ——————————————————————————————————————————

def test_mapping_table_registers_paths_not_default_values(tmp_path):
    """映射表里只能有「路径（+ 量纲倍数）」，且每条路径都真能在 Config 默认数据里走通。"""
    for row_key, entry in settings_default_marks._ROW_DEFAULT_PATHS.items():
        path, factor = entry if isinstance(entry, tuple) else (entry, None)
        assert isinstance(path, str) and path, row_key
        assert factor is None or isinstance(factor, (int, float)), row_key
        assert settings_default_marks._row_default_value(None, row_key)[0], (
            f"{row_key} 登记了在 Config 默认数据里走不通的路径：{path}"
        )


def test_default_values_come_from_config_itself(tmp_path):
    """默认值只有 Config 一份：本刀的表只登记路径，不抄默认值。"""
    empty = Config(base=tmp_path / "empty")
    assert settings_default_marks._config_default_data() == empty._initial_data()
