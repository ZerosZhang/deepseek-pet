# -*- coding: utf-8 -*-
"""测试设置界面控件状态、保存/读取 round-trip 以及内置 Agent 音效资源存在与格式有效性。"""
from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from pet.click_sound import resolve_builtin_sound
from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_builtin_agent_sounds_exist_and_valid_wav():
    """验证三个内置 Agent 音效文件存在，且是合法 16-bit 22050Hz 单声道 WAV。"""
    for sound_id, key in [
        ("builtin:agent-start", "agent-start"),
        ("builtin:agent-done", "agent-done"),
        ("builtin:agent-error", "agent-error"),
    ]:
        sound_path = resolve_builtin_sound(sound_id)
        assert sound_path is not None, f"无法解析内置音效: {sound_id}"
        assert sound_path.is_file(), f"音效文件不存在: {sound_path}"
        assert sound_path.suffix.lower() == ".wav"
        assert sound_path.stat().st_size > 1000

        with wave.open(str(sound_path), "rb") as wf:
            assert wf.getnchannels() == 1  # 单声道
            assert wf.getsampwidth() == 2  # 16-bit = 2 bytes
            assert wf.getframerate() == 22050
            num_frames = wf.getnframes()
            assert num_frames > 0
            duration = num_frames / wf.getframerate()
            assert 0.1 <= duration <= 1.0









def test_dialogue_key_params_match_runtime_call_sites():
    """设置页每 key 的“可用参数”提示直接派生自 PARAMETERS（单一真相源）。

    上游重构曾让设置页提示与运行时注入漂移；现在 DIALOGUE_KEY_PARAMS 由
    persona_template.PARAMETERS 派生，这里验证派生关系与代表性条目。"""
    from pet.modern_settings_dialog import DIALOGUE_KEY_PARAMS, DIALOGUE_PARAMS
    from pet.persona_template import PARAMETERS

    assert DIALOGUE_KEY_PARAMS == dict(PARAMETERS)
    # 展示名必须覆盖全部宣称的参数（对话框 hint 渲染用 DIALOGUE_PARAMS[item]）
    advertised = {f for fields in PARAMETERS.values() for f in fields}
    assert advertised <= set(DIALOGUE_PARAMS), sorted(advertised - set(DIALOGUE_PARAMS))
    # activity 组字段以桥接 tool/call 真实记录为准：target/ok 不在 tool/call 里，
    # 不得宣称（活动气泡渲染时拿不到，写了就是永不替换的占位符）
    assert "callId" in DIALOGUE_KEY_PARAMS["activity.read"]
    assert "target" not in DIALOGUE_KEY_PARAMS["activity.read"]
    assert "ok" not in DIALOGUE_KEY_PARAMS["activity.read"]
    assert {"errorCode", "errorMessage", "consecutiveRetryCount", "retry"} <= set(
        DIALOGUE_KEY_PARAMS["model_access.one"])
    assert "dsh.writeback.failed" not in DIALOGUE_KEY_PARAMS, "回写链已删，其文案键不得残留"




def _nav_item_indexes(dialog) -> dict[str, int]:
    """返回 sidebar 标签 → pages 栈索引 的映射。"""
    return {
        dialog.sidebar.item(i).text(): i
        for i in range(dialog.sidebar.count())
    }




















def test_position_autosave_does_not_set_user_customized(tmp_path):
    """批 C：位置自动保存等后台写盘不得置位 user_customized（保留默认假）。"""
    cfg_root = tmp_path / "appdata"
    cfg = Config(cfg_root, instance_id="slot-2")
    # 模拟窗口 _save_position：写位置键 + save()，不经过设置界面。
    cfg.set("rx", 0.5)
    cfg.set("ry", 0.5)
    cfg.set("screen_name", "X")
    cfg.set("facing", "right")
    cfg.save()
    assert cfg.get("user_customized") is False
    reloaded = Config(cfg_root, instance_id="slot-2")
    assert reloaded.get("user_customized") is False














