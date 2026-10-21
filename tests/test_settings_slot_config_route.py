# -*- coding: utf-8 -*-
"""子宠设置页的配置读写路由（架构级死开关修复）。

问题：overlay 拓扑下右键子宠 → 桌宠设置拉起的是**独立设置进程**
（``--instance slot-N`` → ``Config(instance_id="slot-N")`` → 读写
``config-slot-N.json``），而运行期只有 ``PER_SLOT_SETTING_KEYS`` 里的键逐宠取源
（``overlay_shell._SpriteConfig.get``），其余键一律读主配置。于是子宠页上「语音
报时 / 节日 / 待办 / 灵动岛 / 菜单外观 / 窗口级 7 键 …」保存成功、回显正确、
运行期零效果——窗口级 7 行还写着「（对所有桌宠生效）」，实际对所有桌宠都不生效。

本文件钉住修法的四件事（走真实 ``ModernSettingsDialog`` 这个公开 seam，不碰私有
调用顺序）：

1. 保存路由：非 per-slot 键落进**主** ``config.json``，per-slot 键落 slot 文件；
2. 初值路由：子宠页非 per-slot 行显示主配置的真实值（不再是 slot 文件里的无效快照）；
3. 恢复默认：子宠页只重置 slot 文件，主配置一个键都不碰；
4. 并发纪律：主配置在设置窗打开后被外部改写 → 保存不盖回该键（reload-merge）。

分流只在 overlay 拓扑下的 slot 身份生效：legacy 单窗（含捕获模式）里那只桌宠读的
就是自己那份 ``config-slot-N.json`` 的**全部**键，分流反而会让它的设置失效。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pet import overlay_spawn_state as spawn_state
from pet import settings_slot_config
from pet.catalog import DEFAULT_SCALE
from pet.config import DEFAULT_SELF_TALK_TEXTS, Config


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _dialog(config, *, include_ai: bool = False, standalone: bool = False):
    from pet.modern_settings_dialog import ModernSettingsDialog

    return ModernSettingsDialog(config, include_ai=include_ai,
                                standalone=standalone)


def _read_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _slot_path(config_dir, slot: int = 1) -> Path:
    return spawn_state.slot_config_path(config_dir, slot)


# ------------------------------------------------------------ 1. 保存路由




# ------------------------------------------------------------ 2. 初值路由


# ------------------------------------------------------------ 3. 恢复默认收口




# ------------------------------------------------------------ 4. 并发纪律
def test_routed_save_reloads_main_before_writing(tmp_path):
    """路由视图自己的落盘纪律：``reload`` → 重放 pending → ``save``。

    ``Config.save`` 是**整表**写：不先重读，设置窗打开期间主进程/托盘改过的键就
    被陈旧内存快照盖回去。这一条钉在路由视图上（不依赖调用方是否记得先 reload），
    ``_write_config`` 那条端到端路径见下一条。
    """
    main = Config(base=tmp_path)
    main.set("mem_min_size_mb", 50.0)
    assert main.save() is True
    cfg = Config(base=tmp_path, instance_id="slot-1")
    routed = settings_slot_config.route_settings_config(cfg)
    assert routed is not cfg

    routed.set("pet_opacity", 30)
    external = Config(base=tmp_path)
    external.set("mem_min_size_mb", 123.0)
    assert external.save() is True

    assert routed.save() is True
    on_disk = _read_json(main.path)
    assert on_disk["pet_opacity"] == 30, "本次要改的键要落盘"
    assert on_disk["mem_min_size_mb"] == 123.0, "外部并发改动被陈旧内存快照盖回去了"




# ------------------------------------------------------------ 5. 分流键的清洗口径




# ------------------------------------------------------------ 6. 点击台词绑定保存
def _save_click_talk_binding(config, action_id: str, text: str) -> str:
    """走真实对话框保存一条绑定（`编辑…` 按钮那条路），返回实际角色 id。"""
    from pet.click_talk_dialog import ClickTalkBindingsDialog

    dialog = ClickTalkBindingsDialog(config, click_names=[action_id])
    try:
        dialog.text_edit.setPlainText(text)
        dialog._save()
        return dialog.character_id
    finally:
        dialog.deleteLater()




def test_click_talk_binding_save_writes_main_config_even_without_page_save(tmp_path, app):
    """绑定对话框自己的「保存」即落盘：设置页没再点保存（或直接关窗）也不丢。

    路由把落盘收口在 ``save`` 的 reload → 重放 pending → save 上，但
    ``Config.set_click_talk_bindings`` 的既契约是"保存即落盘"；两者都要满足。
    """
    main = Config(base=tmp_path)
    assert main.save() is True
    cfg = Config(base=tmp_path, instance_id="slot-1")
    routed = settings_slot_config.route_settings_config(cfg)

    character_id = _save_click_talk_binding(routed, "click2", "在的")

    on_disk = _read_json(main.path)
    assert on_disk["character_profiles"][character_id]["click_talk_bindings"] == {
        "click2": ["在的"]}


# ------------------------------------------------------------ 7. 置灰摘除（路由接通后真生效）


# ------------------------------------------------------------ 8. 分流范围（空身份与 slot 身份都分流）
def test_main_pet_config_is_routed_to_slot0(tmp_path):
    """主宠设置会话（无 --instance 的空身份）也按 slot0 分流（#271 契约变更）。

    旧契约是"空身份原样返回、行为逐位不变"，实机口径已推翻：运行期每宠键只从
    ``config-slot-0.json`` 取源（``_SpriteConfig.get`` 的第一条分支），空身份直写的
    每宠键在 ``Config.save()`` 出闸时被当退役键 pop 掉——写入凭空蒸发、``save()``
    还报成功，用户重开设置看到的是出厂默认（#271：主宠改尺寸/气泡不生效）。
    故空身份与显式 ``slot-0`` 同规：每宠键落 slot0 档案、全局键落主 ``config.json``。
    """
    from pet import pet_profiles

    main = Config(base=tmp_path, instance_id="")
    assert main.save() is True

    routed = settings_slot_config.route_settings_config(main)
    assert isinstance(routed, settings_slot_config.SlotRoutedConfig)
    assert routed.path == spawn_state.slot_config_path(main.dir, 0), \
        "空身份会话的配置面指向 slot0 档案（身份与报错路径都以它为准）"

    routed.set("scale", 0.77)        # 每宠键
    routed.set("pet_opacity", 55)    # 全局键
    assert routed.save() is True

    assert pet_profiles.read_slot_profile(main.dir, 0).value("scale") == pytest.approx(0.77)
    assert "scale" not in _read_json(main.path), "每宠键不许落进主 config.json"
    assert _read_json(main.path)["pet_opacity"] == 55, "全局键照旧落主 config.json"


def test_legacy_topology_slot_config_is_not_routed(tmp_path, monkeypatch):
    """legacy 单窗：那只宠读的就是自己那份 slot 文件的全部键，不许分流。"""
    from pet import overlay_settings_command as cmd_mod

    monkeypatch.setenv(cmd_mod.ENV_TOPOLOGY, "legacy")
    cfg = Config(base=tmp_path, instance_id="slot-1")
    assert isinstance(settings_slot_config.route_settings_config(cfg), settings_slot_config.SlotRoutedConfig)


def test_non_slot_instance_is_not_routed(tmp_path):
    """非 slot-N 的实例身份（测试/诊断用法）：没有可写的 slot 文件，不分流。"""
    cfg = Config(base=tmp_path, instance_id="probe-a")
    assert settings_slot_config.route_settings_config(cfg) is cfg


# ------------------------------------------------------------ 9. 主配置身份（F2 定论）
def test_slot_compat_launch_main_config_is_that_process_main(tmp_path, monkeypatch):
    """F2 定论：``--slot N`` 兼容启动下，路由的"主配置"= 该进程的 config-slot-N.json。

    ``--slot N`` 启动把 ``DSH_PET_INSTANCE=slot-N`` 写进进程环境，设置子进程继承它，
    于是 ``route_settings_config`` 里的主配置构造（``Config(base=...)``，不传
    ``instance_id``）解析出 ``config-slot-N.json``。那就是**该进程**的主配置：运行期
    壳的非 per-slot 键读源是 ``shell._config``（``_SpriteConfig.get`` 的兜底分支），
    而 ``shell._config`` 正是 ``Config(instance_id="slot-N")``。故这不是"读错了主配置"，
    写进去立刻生效（详见模块 docstring 的「主配置身份」一节）。
    """
    from pet import overlay_settings_command as cmd_mod

    monkeypatch.setenv("DSH_PET_INSTANCE", "slot-2")
    monkeypatch.setenv(cmd_mod.ENV_TOPOLOGY, "overlay")

    cfg = Config(base=tmp_path, instance_id="slot-2")
    assert cfg.path == spawn_state.slot_config_path(cfg.dir, 2)
    assert Config(base=tmp_path).path == cfg.path, "env 身份让主配置构造落到同一份文件"

    routed = settings_slot_config.route_settings_config(cfg)
    assert routed is not cfg, "该进程仍是 overlay 拓扑下的 slot 身份，照常分流"
    routed.set("pet_opacity", 42)
    assert routed.save() is True
    assert _read_json(routed._main.path)["pet_opacity"] == 42
    assert routed._main.path.name == "config.json"
    assert not cfg.path.exists()




# ------------------------------------------------------------ 10. 分流按父进程运行中拓扑（R01）
def test_parent_overlay_topology_routes_child_page_despite_disk_capture_mode(
        tmp_path, monkeypatch):
    """磁盘 ``stream_capture_mode=True``（勾了没重启）+ 父进程正跑 overlay → 照旧分流。

    R01：默认 overlay 运行中，用户在主宠设置勾选「直播捕获兼容」并保存（文案明说
    重启后生效，用户没重启）→ 磁盘上捕获开关为 True。此后打开子宠设置：设置子进程
    按磁盘快照判成 legacy，``route_settings_config`` 原样返回不分流，子宠页把全部
    设置写进 ``config-slot-N.json``——而仍在运行的 overlay 主进程对这些键只读主配置，
    于是"保存成功、实际无效"，还会污染下一次重启的配置身份。

    正解：设置进程按**拉起它的那个主进程的运行中拓扑**分流。
    """
    from pet import overlay_settings_command as cmd_mod

    main = Config(base=tmp_path)
    main.set("stream_capture_mode", True)
    assert main.save() is True
    monkeypatch.delenv(cmd_mod.ENV_TOPOLOGY, raising=False)
    monkeypatch.delenv(cmd_mod.ENV_PARENT_TOPOLOGY, raising=False)
    cmd_mod.reset_topology_snapshot()

    # 主进程拉起设置子进程时把**运行中拓扑**显式传下去（子进程快照是冷的：只按
    # 磁盘读就是 legacy，正是 R01 的错判）。
    monkeypatch.setenv(cmd_mod.ENV_PARENT_TOPOLOGY, "overlay")
    cfg = Config(base=tmp_path, instance_id="slot-1")

    routed = settings_slot_config.route_settings_config(cfg)
    assert routed is not cfg, "父进程还在 overlay 跑：子宠页必须分流"

    routed.set("pet_opacity", 33)
    assert routed.save() is True
    assert _read_json(main.path)["pet_opacity"] == 33, "非 per-slot 键落主配置（真生效）"
    assert not _slot_path(main.dir).exists(), "全局保存不创建宠档案"


def test_parent_legacy_topology_does_not_route_even_when_disk_says_overlay(
        tmp_path, monkeypatch):
    """父进程正跑 legacy（捕获模式/dev 逃生门）→ 即使磁盘捕获开关关着也不分流。

    那只宠读的就是自己那份 ``config-slot-N.json`` 的全部键，分流会让它的设置失效。
    父进程的陈述与磁盘互相矛盾时以**父进程运行中拓扑**为准：那才是这个设置页正在
    编辑的那个进程。
    """
    from pet import overlay_settings_command as cmd_mod

    main = Config(base=tmp_path)
    assert main.save() is True
    cmd_mod.reset_topology_snapshot()
    monkeypatch.delenv(cmd_mod.ENV_TOPOLOGY, raising=False)
    monkeypatch.setenv(cmd_mod.ENV_PARENT_TOPOLOGY, "legacy")

    cfg = Config(base=tmp_path, instance_id="slot-1")
    assert settings_slot_config.route_settings_config(cfg) is not cfg

    # 父进程陈述与 dev 逃生门同时在场且互相矛盾：父进程运行中拓扑优先
    monkeypatch.setenv(cmd_mod.ENV_TOPOLOGY, "overlay")
    assert settings_slot_config.route_settings_config(cfg) is not cfg


def test_missing_parent_topology_env_falls_back_to_existing_verdict(
        tmp_path, monkeypatch):
    """父进程没发话（手工单开设置页/旧主进程）→ 判定逐位回到原有链路。"""
    from pet import overlay_settings_command as cmd_mod

    main = Config(base=tmp_path)
    main.set("stream_capture_mode", True)
    assert main.save() is True
    cmd_mod.reset_topology_snapshot()
    monkeypatch.delenv(cmd_mod.ENV_TOPOLOGY, raising=False)
    monkeypatch.delenv(cmd_mod.ENV_PARENT_TOPOLOGY, raising=False)

    cfg = Config(base=tmp_path, instance_id="slot-1")
    assert settings_slot_config.route_settings_config(cfg) is not cfg, \
        "缺父进程陈述时照旧按磁盘快照判（勾了没重启 = 那个进程就是 legacy）"

    monkeypatch.setenv(cmd_mod.ENV_PARENT_TOPOLOGY, "overlay")
    assert settings_slot_config.route_settings_config(cfg) is not cfg, \
        "同一份磁盘配置，父进程陈述 overlay 就分流"


# ------------------------------------------------------------ 11. 坏档案（G1b 接线后）


# ------------------------------------------------------------ 12. 表单编辑代次（防回归契约）


