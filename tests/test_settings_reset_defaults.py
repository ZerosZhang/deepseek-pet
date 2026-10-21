# -*- coding: utf-8 -*-
"""「恢复默认设置」聚焦测试（issue #220）。

语义契约（整体重置，不做按分页重置）：
1. 除保留集外的全部键回到出厂默认（口径 = 全新安装的 ``Config.data``）；
2. 保留集 = chat 域密钥类字段（``api_key``/``vision_api_key`` 及其 keyring 引用），
   因为 API Key 是用户最难重配的一项，且 keyring 不可用时明文只存在内存里。
   **自定义 provider 也一样**：条目按重置口径只剩「名字 + 凭据」骨架，凭据必须
   在任何情况下仍可读出（否则确认文案的「保留 AI 对话密钥」就是空话）；
3. 落盘走既有 ``save()`` 原子写路径（``atomic_replace_with_retry``，#194 教训）；
4. 用户取消 / 落盘失败 = 零副作用（内存与磁盘都不变）；
5. 重置后关窗不得把旧控件值整表写回（设置窗关闭时会保存全部控件，控件持有的是
   重置前的旧值，不闸住就把刚写的默认值覆盖回去）；
6. 重置级运行态对齐分**两个作用域**（G1b）：
   - **全局作用域**：位置（rx/ry=None）要立即回默认落位，否则本次退出
     ``save_position()`` 会把重置前的旧位置写回磁盘、重置被静默抵消。触发它的
     宿主配置是**整份**配置（进程内全局页 / legacy 的 ``--slot N`` 进程，都不是
     SlotRoutedConfig）；#271 起空身份**设置窗**按 slot0 分流，那种窗口里全局
     口径挂在侧栏副按钮的显式 ``RESET_SCOPE_GLOBAL`` 上；
   - **slot 口径（含 #271 后的主宠页 = slot0 页）**：本宠 reset **保留位置**
     （"回到默认落位"是独立操作，见
     ``docs/PRODUCT-NEXT-STEPS-SPEC-2026-10-09.md`` §五），所以它写的是
     ``CMD_PROFILE_RESET``（偏好/尺寸/角色的运行态同步），**绝不**写会重定位的
     ``CMD_APPLY_SETTINGS_RESET``；系统登录项单独按新值收敛。
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget

from pet import config as config_mod
from pet import overlay_settings_command as cmd_mod
from pet import settings_reset_defaults
from pet import window_placement
from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _no_real_autostart_writes(monkeypatch):
    """本文件一律不碰真实系统登录项：autostart 通道默认打桩成"没开"。

    重置链路会按新值收敛 OS 登录项（``sync_system_autostart``）——测试机上真的开了
    开机自启时，跑一次用例就会把它关掉。需要断言该行为的用例在用例体内自行覆盖
    （test_reset_syncs_system_autostart_login_item 等已如此）。
    """
    from pet import autostart as autostart_mod

    monkeypatch.setattr(autostart_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(autostart_mod, "set_enabled", lambda _on: True)


def _fresh_config(base: Path) -> Config:
    """一份全新安装口径的 Config（目录里没有任何配置文件）。"""
    return Config(base=base)


def _settings_only(data: dict, fresh: dict) -> dict:
    """只留"设置面"的深拷贝（摘掉保留集，供"其余全等于默认"的比较）。

    - 默认集里的 provider：只摘掉凭据字段；
    - 非默认 provider 的条目整个摘掉——重置后它是"只装凭据的容器"（内存里刚重置
      完只有名字+凭据，重新加载后由 ``_merge_chat_data`` 按默认模板补齐骨架），
      容器自身的形状与内容另有专项测试（rebuilds_credential_only_entry）。
    """
    data = copy.deepcopy(data)
    providers = data.get("chat", {}).get("providers")
    default_ids = set((fresh.get("chat") or {}).get("providers") or {})
    if isinstance(providers, dict):
        for provider_id in list(providers):
            if provider_id not in default_ids:
                providers.pop(provider_id)
                continue
            provider = providers[provider_id]
            if isinstance(provider, dict):
                for field in config_mod.CHAT_SECRET_FIELDS:
                    provider.pop(field, None)
    return data


def _dirty_config(base: Path) -> Config:
    """把一份配置改成"被用户改坏"的样子（含自定义密钥与非默认值）。"""
    cfg = Config(base)
    cfg.data.update(
        {
            "playback_speed": 3.5,
            "pet_opacity": 40,
            "mouse_through": True,
            "lock_position": True,
            "self_talk_enabled": True,
            "self_talk_texts": ["自定义台词"],
            "click_sound_volume": 0.2,
            "collision_restitution": 0.1,
            "todo_reminder_lead_minutes": 30,
            "voice_chime_enabled": True,
            "character_aliases": {"default": "小名"},
            "context_menu_appearance": {"theme": "dark", "density": "compact"},
            "chat": {
                "enabled": False,
                "active_provider": "relay",
                "default_system_prompt": "自定义提示词",
                "history_message_limit": 5,
                "providers": {
                    "openai-main": {
                        "name": "DeepSeek",
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-v4-flash",
                        # 明文 key（keyring 不可用时的兜底）与自定义钥匙串引用：
                        # 两者都是保留集，重置后必须原样还在。
                        "api_key": "sk-live-secret",
                        "api_key_ref": "provider/legacy-main",
                        "vision_api_key": "sk-live-vision",
                        "vision_api_key_ref": "provider/legacy-main/vision",
                    },
                    "relay": {
                        "name": "中转",
                        "base_url": "https://relay.example.com",
                        "model": "gpt-4o",
                        "api_key": "sk-relay",
                    },
                },
            },
        }
    )
    assert cfg.save() is True, "前置条件：脏配置必须能落盘"
    return cfg


def _spy_atomic_replace(monkeypatch) -> list[tuple[Path, Path]]:
    """记录 save() 的原子替换调用（探针，不是打桩：仍调真实实现）。"""
    calls: list[tuple[Path, Path]] = []
    real = config_mod.atomic_replace_with_retry

    def spy(temp, target, *args, **kwargs):
        calls.append((Path(temp), Path(target)))
        return real(temp, target, *args, **kwargs)

    monkeypatch.setattr(config_mod, "atomic_replace_with_retry", spy)
    return calls


# ---------------------------------------------------------------- 1. 重置语义

def test_reset_restores_every_non_secret_key_to_defaults(tmp_path: Path):
    """重置后：所有非保留键 == 全新安装默认值，保留键原样。"""
    cfg = _dirty_config(tmp_path / "appdata")
    fresh = _fresh_config(tmp_path / "fresh")
    assert _settings_only(cfg.data, fresh.data) != _settings_only(fresh.data, fresh.data), "前置条件：脏配置必须偏离默认值"

    assert cfg.reset_to_defaults() is True

    assert _settings_only(cfg.data, fresh.data) == _settings_only(fresh.data, fresh.data)
    provider = cfg.data["chat"]["providers"]["openai-main"]
    assert provider["api_key"] == "sk-live-secret", "明文 Key 必须原样保留"
    assert provider["vision_api_key"] == "sk-live-vision"
    assert provider["api_key_ref"] == "provider/legacy-main", "keyring 引用必须原样保留"
    assert provider["vision_api_key_ref"] == "provider/legacy-main/vision"


def test_reset_keeps_custom_provider_credentials_when_keyring_unavailable(
        tmp_path: Path, monkeypatch):
    """B1：keyring 不可用时，自定义 provider 的明文密钥必须活过重置。

    旧行为只回填"默认集里仍存在的 provider"（openai-main），自定义 provider 的
    条目被重置掉 → 内存明文密钥永久丢失，而确认文案承诺「保留 AI 对话密钥」。
    断言落在**生产读密钥口径**上（``Config.resolve_api_key`` = keyring 优先、
    取不到回落明文），而不是只看配置里的字段。
    """
    from pet.chat.models import SecretStore

    monkeypatch.setattr(SecretStore, "get", lambda self, ref: "")  # keyring 不可用

    cfg = _dirty_config(tmp_path / "appdata")
    assert cfg.reset_to_defaults() is True

    settings = cfg.chat_settings()
    relay = settings.providers["relay"]
    assert cfg.resolve_api_key(relay) == "sk-relay", "自定义服务商的密钥必须仍可读出"


def test_reset_rebuilds_credential_only_entry_for_custom_providers(tmp_path: Path):
    """自定义 provider 只留「名字 + 凭据」骨架；其余字段按重置口径回默认模板。"""
    cfg = _dirty_config(tmp_path / "appdata")
    assert cfg.reset_to_defaults() is True

    entry = cfg.data["chat"]["providers"]["relay"]
    assert set(entry) <= {"name", *config_mod.CHAT_SECRET_FIELDS}
    assert "base_url" not in entry and "model" not in entry, "中转站地址/模型不得被当凭据保留"
    assert entry["api_key"] == "sk-relay"

    reloaded = Config(base=tmp_path / "appdata")  # 加载路径按默认模板补齐骨架
    relay = reloaded.data["chat"]["providers"]["relay"]
    assert relay["base_url"] == "https://api.deepseek.com"
    assert relay["model"] == "deepseek-v4-flash"
    assert relay["api_key_ref"] == "provider/relay", "凭据引用必须留下（钥匙串里的 key 靠它取回）"
    # 重置后活跃 provider 仍是默认那一个：被保留的凭据容器不会被自动选中。
    assert reloaded.data["chat"]["active_provider"] == "openai-main"


def test_reset_does_not_touch_keyring_and_drops_non_credential_fields(tmp_path: Path, monkeypatch):
    """保留集之外什么都不保：自定义服务商的地址/模型/提示词回默认（钥匙串条目不删除）。

    重置只写配置文件，**从不**调用 SecretStore：自定义服务商的 keyring 条目原样
    留在系统钥匙串里（删掉才是数据丢失）。
    """
    from pet.chat.models import SecretStore

    def boom(*_args, **_kwargs):  # pragma: no cover - 只在被调用时触发
        raise AssertionError("重置设置不得触碰系统钥匙串")

    monkeypatch.setattr(SecretStore, "set", boom)

    cfg = _dirty_config(tmp_path / "appdata")
    assert cfg.reset_to_defaults() is True

    providers = cfg.data["chat"]["providers"]
    assert providers["relay"]["api_key"] == "sk-relay"          # 只有凭据活着
    assert providers["relay"]["name"] == "中转"                  # 骨架名（便于认出是哪个服务商）
    assert cfg.data["chat"]["active_provider"] == "openai-main"
    assert cfg.data["chat"]["default_system_prompt"] != "自定义提示词"


def test_reset_result_survives_reload(tmp_path: Path):
    """重置结果必须在重新加载后依然成立（主进程 watcher 走的就是这条路径）。"""
    cfg = _dirty_config(tmp_path / "appdata")
    fresh = _fresh_config(tmp_path / "fresh")
    assert cfg.reset_to_defaults() is True

    reloaded = Config(base=tmp_path / "appdata")

    assert _settings_only(reloaded.data, fresh.data) == _settings_only(fresh.data, fresh.data)
    # 明文 Key 不落盘（_redacted_data 脱敏），但 keyring 引用必须落盘。
    assert reloaded.data["chat"]["providers"]["openai-main"]["api_key_ref"] == "provider/legacy-main"
    assert reloaded.data["chat"]["providers"]["openai-main"]["api_key"] == ""
    assert reloaded.data["pet_opacity"] == fresh.data["pet_opacity"]


# ---------------------------------------------------------------- 2. 落盘路径

def test_reset_writes_through_atomic_replace(tmp_path: Path, monkeypatch):
    """重置走 save() 同一条原子写路径，且临时文件被清干净。"""
    cfg = _dirty_config(tmp_path / "appdata")
    calls = _spy_atomic_replace(monkeypatch)
    calls.clear()

    assert cfg.reset_to_defaults() is True

    assert len(calls) == 1, "重置应当只落盘一次（批量改配置 + 一次性落盘）"
    temp, target = calls[0]
    assert target == cfg.path
    assert temp.name == f"{cfg.path.name}.{os.getpid()}.tmp"
    assert not temp.exists(), "临时文件必须被清掉（失败残留会污染配置目录）"
    on_disk = json.loads(cfg.path.read_text(encoding="utf-8"))
    assert on_disk["pet_opacity"] == 100


def test_reset_write_failure_rolls_back_memory(tmp_path: Path, monkeypatch):
    """落盘失败：返回 False、内存回滚、磁盘不变（不许出现"内存默认/磁盘旧值"）。"""
    cfg = _dirty_config(tmp_path / "appdata")
    before_memory = copy.deepcopy(cfg.data)
    before_disk = cfg.path.read_text(encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(config_mod, "atomic_replace_with_retry", fail)

    assert cfg.reset_to_defaults() is False

    assert cfg.data == before_memory
    assert cfg.path.read_text(encoding="utf-8") == before_disk


# ---------------------------------------------------------------- 3. 设置页接线







def test_reset_confirm_box_copy_states_kept_items_and_irreversibility(qapp, tmp_path: Path):
    """二次确认文案：写清"重置全部"、保留项、不可撤销，且默认按钮是取消。"""
    box, confirm = settings_reset_defaults.build_reset_confirm_box(None)
    try:
        text = box.text() + "\n" + box.informativeText()
        assert "将重置全局设置为默认值" in text
        assert "活跃状态及会话历史" in text
        assert "API Key" in text, "保留项必须逐项写明"
        assert "钥匙串" in text, "保留的 keyring 引用要说清楚"
        # 2026-10-07 第一刀：「只装密钥的条目」拗口句改顺，语义不变——
        # 各服务商的密钥仍保留，自定义服务商只保留密钥本身（地址/模型回默认）。
        assert "每个自定义服务商只保留密钥本身" in text, "各服务商密钥仍保留，其余设置回默认"
        assert "地址、模型等其它设置会恢复默认" in text
        assert "角色、尺寸、位置" in text
        assert "开机自启按默认关闭" in text
        assert confirm.text() == "恢复默认设置"
        assert box.defaultButton() is not confirm, "破坏性操作的默认按钮不得是确认"
    finally:
        box.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------- 作用域文案（R08）












def test_global_only_page_does_not_call_itself_this_pet(qapp, tmp_path: Path):
    """没有每宠划分的那一面（全局页）不自称"本宠"：单动作按钮沿用原文案。

    那一面没有"每宠档案 / 全局"的区分，按钮写成"本宠"会指向一个不存在的划分——用户会
    以为"本宠之外的设置没被重置"。产品入口（``--instance slot-N`` 与空身份会话）都按
    slot0 分流、给的是两个带作用域的按钮；这一支是 legacy 整表身份/诊断身份才会走到的
    路径，判据仍是 ``reset_scope_is_slot``（配置面，不是实例名）。
    """

    class _Host(QWidget):
        def __init__(self, config):
            super().__init__()
            self.config = config

    host = _Host(Config(base=tmp_path / "appdata"))
    settings_reset_defaults.create_reset_button(host, QVBoxLayout(host))
    try:
        assert settings_reset_defaults.reset_scope_is_slot(host) is False
        assert host.reset_defaults_btn.text() == settings_reset_defaults.RESET_BUTTON_TEXT
        assert "本宠" not in host.reset_defaults_btn.text()
        assert getattr(host, "reset_global_defaults_btn", None) is None, (
            "全局页只有一个作用域，不该多出一个全局按钮")
    finally:
        host.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------- 4. 重置级运行态对齐
# 重置只落盘 + 走普通刷新是不够的：位置（rx/ry=None）不重定位，用户看不到任何变化，
# 而本次进程正常退出时 save_position() 会把运行态几何写回磁盘——重置前的旧位置
# 因此被"合法地"写回去，重置被静默抵消。下面固定「重置级对齐」这条链。

class _Host:
    """设置窗最小替身：只提供重置链路需要的鸭子面（config / parent / 关窗）。"""

    def __init__(self, config, parent=None):
        self.config = config
        self._parent = parent
        self.closed = 0

    def parentWidget(self):
        return self._parent

    def _close_after_external_write(self):
        self.closed += 1


class _StubScreen:
    def __init__(self, name, geometry):
        self._name = name
        self._geometry = geometry

    def name(self):
        return self._name

    def availableGeometry(self):
        return self._geometry

    def devicePixelRatio(self):
        return 1.0


class _StubPet:
    """window_placement 的轻量宿主桩（与 tests/test_window_position.py 同型）。

    真实的 ``save_position`` / ``go_default_corner`` 实现照跑——两者都显式支持
    轻量桩（``move()`` 回退分支），所以这里量到的是真实落位与真实写盘。
    """

    cfg = None
    facing = "left"
    scale = 1.0
    _w = 220
    _h = 260
    _capture_headroom = 0

    def __init__(self, cfg, screen, pos):
        self.cfg = cfg
        self._screen = screen
        self._pos = QPointF(*pos)
        self._awaiting_saved_screen = None
        self._saved = 0

    def _screen_available(self, screen_name=None):
        return self._screen

    def move(self, x, y):
        self._pos = QPointF(float(x), float(y))

    def x(self):
        return int(self._pos.x())

    def y(self):
        return int(self._pos.y())

    def _cancel_move(self):
        pass

    def _stop_physics(self):
        pass

    def _save_position(self):
        self._saved += 1
        return window_placement.save_position(self)

    def go_default_corner(self):
        # 与 PetWindow 同型：公开转发到 window_placement（真实落位 + 真实落盘）
        return window_placement.go_default_corner(self)


def _stub_instance(cfg, screen, pos):
    class _Instance:
        def __init__(self):
            self.win = _StubPet(cfg, screen, pos)
    return _Instance()


def _stub_shell(instance):
    from pet.app import AppShell

    shell = AppShell.__new__(AppShell)
    shell.instance = instance
    shell._instances = [instance]
    shell.config = instance.win.cfg
    shell._apply_external_config_change = lambda: None
    return shell


def test_reload_adopts_reset_position_nulls(tmp_path: Path):
    """rx/ry/screen_name 的显式 null 必须被采纳，否则运行期永远留着重置前的位置。

    这三个键的消费者（window_placement.restore_position / overlay 落位）本来就把
    None 当"没有位置记忆"，所以它们进 _NULL_ACCEPTING_KEYS 是同一个口径的延伸。
    """
    from pet import pet_profiles
    from pet.settings_slot_config import route_settings_config

    cfg = _dirty_config(tmp_path / "appdata")
    pet_profiles.write_profile_settings(cfg.dir, 0, {"rx": 0.42, "ry": 0.42, "screen_name": "primary"})
    routed = route_settings_config(Config(base=tmp_path / "appdata", instance_id="slot-0"))
    assert cfg.reset_to_defaults()
    assert routed.get("rx") == 0.42
    pet_profiles.write_profile_settings(cfg.dir, 0, {"rx": None, "ry": None, "screen_name": None})
    routed.reload()
    assert routed.get("rx") is None
    assert routed.get("screen_name") is None


def test_reset_asks_parent_window_to_align_runtime(tmp_path: Path, monkeypatch):
    """进程内设置页：重置后直接调窗口上已接线的回调（不走指令通道），并同步系统项。"""
    from pet import autostart as autostart_mod

    monkeypatch.setattr(settings_reset_defaults, "confirm_reset", lambda _parent, _scope=None: True)
    calls: list[str] = []
    parent = type("_Win", (), {})()
    parent.on_settings_reset = lambda: calls.append("window")
    os_calls: list[bool] = []
    monkeypatch.setattr(autostart_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(autostart_mod, "set_enabled", lambda on: (os_calls.append(bool(on)), True)[1])
    cfg = _dirty_config(tmp_path / "appdata")
    host = _Host(cfg, parent)

    assert settings_reset_defaults.on_reset_clicked(host) is True

    assert calls == ["window"], "有桌宠窗口时必须直接请求它对齐运行态"
    assert os_calls == [False], "重置链路必须把系统登录项一起收敛"
    assert not cmd_mod.command_path(cfg.dir).exists(), "进程内不必写指令文件"


def test_reset_writes_alignment_command_without_parent_window(tmp_path: Path, monkeypatch):
    """**全局口径**的独立设置进程：没有窗口可依附 → 写 D12 指令，由主进程消费后重定位。

    这里的宿主配置不是 ``SlotRoutedConfig``（``_Host`` 直接拿一份 ``slot-2`` 的 Config，
    即 legacy ``--slot N`` 进程的形态）：那种进程重置的就是该文件**全部**键（含位置），
    "回默认落位"仍然成立，故指令与 target 逐位不变。子宠页（overlay 路由）那一支见下一条。
    """
    monkeypatch.setattr(settings_reset_defaults, "confirm_reset", lambda _parent, _scope=None: True)
    cfg = Config(tmp_path / "appdata", instance_id="")
    host = _Host(cfg)

    assert settings_reset_defaults.on_reset_clicked(host) is True

    command = cmd_mod.read_command(cfg.dir)
    assert command is not None, "独立设置进程必须写下运行态对齐指令"
    assert command["command"] == cmd_mod.CMD_APPLY_SETTINGS_RESET
    assert command["target"] is None, "全局刷新无逐宠搬家目标"


def test_slot_scope_reset_writes_profile_reset_not_a_reposition_command(
        tmp_path: Path, monkeypatch):
    """**子宠页（slot 作用域）**：reset 保留位置 ⇒ 写 ``CMD_PROFILE_RESET``，不写重定位指令。

    旧行为给子宠页也写 ``CMD_APPLY_SETTINGS_RESET``，而那个指令的语义就是"位置回默认
    落位"——与"本宠 reset 保留位置"（规范 §五）直接冲突。这里两端一起钉住：档案里的位置
    原样保留，发出的指令是新的 ``profile_reset``。
    """
    from pet import pet_profiles, settings_slot_config

    monkeypatch.setattr(settings_reset_defaults, "confirm_reset", lambda _parent, _scope=None: True)
    monkeypatch.setenv(cmd_mod.ENV_TOPOLOGY, "overlay")
    cmd_mod.reset_topology_snapshot()
    base = tmp_path / "appdata"
    main = Config(base=base)
    assert main.save() is True
    cfg = Config(base=base, instance_id="slot-2")
    routed = settings_slot_config.route_settings_config(cfg)
    assert isinstance(routed, settings_slot_config.SlotRoutedConfig), "前提：子宠页走路由"
    assert pet_profiles.write_profile_settings(
        cfg.dir, 2, {"scale": 1.5}, user_customized=True).status == "ok"
    assert pet_profiles.write_profile_geometry(
        cfg.dir, 2, {"rx": 0.3, "ry": 0.35, "screen_name": "primary"}).status == "ok"
    host = _Host(routed)

    assert settings_reset_defaults.on_reset_clicked(host) is True

    command = cmd_mod.read_command(cfg.dir)
    assert command is not None
    assert command["command"] == cmd_mod.CMD_PROFILE_RESET, (
        "子宠页不得再发会重定位的 apply_settings_reset")
    assert command["command"] != cmd_mod.CMD_APPLY_SETTINGS_RESET
    assert command["target"] == 2
    profile = pet_profiles.read_slot_profile(cfg.dir, 2)
    assert (profile.data["rx"], profile.data["ry"]) == (0.3, 0.35), "位置必须保留"
    assert profile.data["screen_name"] == "primary"


def test_profile_reset_command_does_not_reposition_on_the_current_consumer(tmp_path: Path):
    """过渡期安全：当前消费端**不识别** ``profile_reset`` → 安全地什么都不做。

    这一批不改 ``overlay_shell`` / ``AppShell`` 的指令消费（下一批一起改），而新指令的
    语义（偏好/尺寸/角色同步、保位置）必须等到消费端就位才生效。在它被识别之前，行为
    必须是"消费掉、不动作"，**绝不能**被当成旧的 reset 指令去做重定位。
    """
    cfg = _dirty_config(tmp_path / "appdata")
    instance = _stub_instance(
        cfg, _StubScreen("primary", QRect(0, 0, 1920, 1040)), (400, 400))
    shell = _stub_shell(instance)
    calls: list = []
    shell.apply_settings_reset = lambda instance=None: calls.append(instance)
    before = (instance.win.x(), instance.win.y())
    assert cmd_mod.write_command(cfg.dir, cmd_mod.CMD_PROFILE_RESET, target=2) is True

    shell._consume_settings_command()

    assert calls == [], "过渡期不得把新指令当成重置对齐执行"
    assert (instance.win.x(), instance.win.y()) == before, "桌宠位置不许被动过"
    assert not cmd_mod.command_path(cfg.dir).exists(), "消费即删（不留给下一轮重放）"


def test_apply_settings_reset_repositions_window_without_position_memory(tmp_path: Path):
    """AppShell 侧：重置级对齐把这一只送回默认落位（不依赖配置里的 rx/ry 读数）。"""
    screen = _StubScreen("primary", QRect(0, 0, 1920, 1040))
    cfg = _dirty_config(tmp_path / "appdata")
    cfg.data.update({"rx": 0.42, "ry": 0.42, "screen_name": "primary"})
    assert cfg.save() is True
    instance = _stub_instance(cfg, screen, (int(0.42 * 1920) - 110, int(0.42 * 1040) - 130))
    shell = _stub_shell(instance)
    before = (instance.win.x(), instance.win.y())

    assert cfg.reset_to_defaults() is True
    shell.apply_settings_reset(instance)

    assert (instance.win.x(), instance.win.y()) == before
    assert "rx" not in json.loads(cfg.path.read_text(encoding="utf8"))


def test_exit_position_save_after_reset_keeps_default_placement(tmp_path: Path):
    """required 回归：重置后退出进程，盘上位置不得是重置前的旧值。

    退出收口就是 ``win.save_position()``（app.py:2240 / app.py:3159）→
    ``window_placement.save_position`` 写**运行态几何**。所以只要重置级对齐把运行态
    摆到默认落位，磁盘拿到的就是新位置而不是旧位置（旧行为下这里会写回 0.42）。
    """
    screen = _StubScreen("primary", QRect(0, 0, 1920, 1040))
    cfg = _dirty_config(tmp_path / "appdata")
    cfg.data.update({"rx": 0.42, "ry": 0.42, "screen_name": "primary"})
    assert cfg.save() is True
    instance = _stub_instance(cfg, screen, (int(0.42 * 1920) - 110, int(0.42 * 1040) - 130))
    shell = _stub_shell(instance)

    assert cfg.reset_to_defaults() is True
    shell.apply_settings_reset(instance)      # ← 重置级对齐（生产路径）
    window_placement.save_position(instance.win)   # ← 退出收口（生产路径）

    reloaded = Config(base=tmp_path / "appdata")
    from pet import pet_profiles

    assert "rx" not in json.loads(reloaded.path.read_text(encoding="utf8"))
    assert pet_profiles.read_slot_profile(cfg.dir, 0).value("rx") is None
    assert (instance.win.x(), instance.win.y()) == (int(0.42 * 1920) - 110, int(0.42 * 1040) - 130)


def test_settings_reset_command_is_consumed_and_aligns_legacy_window(
        tmp_path: Path, monkeypatch):
    """D12 指令 → AppShell 消费 → 只对齐指令点名的那一只。"""
    cfg = _dirty_config(tmp_path / "appdata")
    main = _stub_instance(cfg, _StubScreen("primary", QRect(0, 0, 1920, 1040)), (100, 100))
    aligned: list = []

    shell = _stub_shell(main)
    shell.apply_settings_reset = lambda instance=None: aligned.append(instance)
    assert cmd_mod.write_command(cfg.dir, cmd_mod.CMD_APPLY_SETTINGS_RESET) is True

    shell._consume_settings_command()

    assert aligned == [main]
    assert not cmd_mod.command_path(cfg.dir).exists(), "消费即删"


def test_reset_syncs_system_autostart_login_item(tmp_path: Path, monkeypatch):
    """系统登录项按重置后的值收敛（默认关）；已是目标值时不重复写注册表。"""
    from pet import autostart as autostart_mod

    calls: list[bool] = []
    monkeypatch.setattr(autostart_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(
        autostart_mod, "set_enabled",
        lambda on: (calls.append(bool(on)), True)[1])

    host = _Host(_dirty_config(tmp_path / "appdata"))
    settings_reset_defaults.sync_system_autostart(host)
    assert calls == [False], "重置把 autostart_wanted 清成 False → 系统登录项必须关掉"

    calls.clear()
    monkeypatch.setattr(autostart_mod, "is_enabled", lambda: False)
    settings_reset_defaults.sync_system_autostart(host)
    assert calls == [], "系统侧已是目标值 → 不重复写"


def test_reset_leaves_system_autostart_alone_for_child_pet(tmp_path: Path, monkeypatch):
    """**本宠**作用域的重置不碰系统登录项：它一个全局键都没重置。

    判据是"重置落在哪个配置面"（``reset_scope_is_slot``），不是实例名——旧用例用一份
    未装箱的 ``Config(instance_id="slot-1")`` 当子宠页，那其实是 legacy ``--slot N``
    进程的"整表身份"，重置它确实会改到 ``autostart_wanted``。产品形态的子宠设置页是
    **装箱后**的路由视图，这里按它来钉。
    """
    from pet import autostart as autostart_mod
    from pet.settings_slot_config import route_settings_config

    calls: list[bool] = []
    monkeypatch.setattr(autostart_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(
        autostart_mod, "set_enabled",
        lambda on: (calls.append(bool(on)), True)[1])

    main = Config(tmp_path / "appdata")
    assert main.save() is True
    routed = route_settings_config(Config(base=tmp_path / "appdata", instance_id="slot-1"))
    assert settings_reset_defaults.reset_scope_is_slot(_Host(routed)) is True, "前提：本宠作用域"
    settings_reset_defaults.sync_system_autostart(_Host(routed))

    assert calls == []


def test_global_reset_from_a_slot_page_syncs_system_autostart(tmp_path: Path, monkeypatch):
    """**全局**作用域从任意宠的页发起都要收敛系统登录项（开机自启是全局键）。

    2026-10-10 终审 A04-b：开机自启控件在 slot0/子宠页都可用（标"影响所有桌宠"），
    所以从子宠页点的全局 reset 必须把 OS 侧一起收敛——旧代码按"实例名非空"直接 return，
    那种页面上系统登录项与配置就会长期不一致（配置说关、注册表还开着）。
    """
    from pet import autostart as autostart_mod
    from pet.settings_slot_config import route_settings_config

    calls: list[bool] = []
    monkeypatch.setattr(autostart_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(
        autostart_mod, "set_enabled",
        lambda on: (calls.append(bool(on)), True)[1])

    main = Config(tmp_path / "appdata")
    main.set("autostart_wanted", True)
    assert main.save() is True
    routed = route_settings_config(Config(base=tmp_path / "appdata", instance_id="slot-2"))
    global_config = settings_reset_defaults.reset_config_for(
        _Host(routed), settings_reset_defaults.RESET_SCOPE_GLOBAL)
    assert global_config is not None and global_config.path == main.path
    assert global_config.reset_to_defaults() is True

    settings_reset_defaults.sync_system_autostart(_Host(routed), config=global_config)

    assert calls == [False], "重置把 autostart_wanted 清成 False → 系统登录项必须关掉"


def test_settings_reset_command_aligns_overlay_sprite(tmp_path: Path):
    """overlay 侧：指令消费后主 sprite 按默认落位重摆（rx/ry=None 的落位语义）。"""
    from tests.test_overlay_spawn import _make_persistent_shell

    shell, _ = _make_persistent_shell(tmp_path)
    try:
        shell.sprite.set_pos(QPointF(50, 60))
        moved = QPointF(shell.sprite.pos)
        assert cmd_mod.write_command(
            shell._config.dir, cmd_mod.CMD_APPLY_SETTINGS_RESET) is True

        shell._consume_settings_command()

        assert QPointF(shell.sprite.pos) == moved, "全局reset不搬宠"
        assert not cmd_mod.command_path(shell._config.dir).exists()
    finally:
        shell._teardown_settings_command_watch()
        shell._delete_runtime_marker()
        if getattr(shell, "tray", None) is not None:
            shell.tray.hide()


# ------------------------------------- 4. 指令先到、reload 后到：不得整表回写旧值
#
# 真实时序（B1）：独立设置进程是"先写默认值、再写对齐指令"两步目录事件，而主进程
# 的目录事件处理顺序是「先消费指令（立刻对齐并落盘）、后按 300ms 去抖排 reload」。
# 于是对齐那一刻运行期那份 Config 还停在重置前的旧值，而它的落盘是**整表**写——
# 刚落盘的默认值被整表覆盖回旧值，重置被静默抵消。



def test_overlay_reset_command_reloads_runtime_config_before_alignment(tmp_path: Path):
    """overlay 同一条指令：对齐前同样把运行期配置拉齐（否则退出写盘覆盖回旧值）。"""
    from tests.test_overlay_spawn import _make_persistent_shell

    base = tmp_path / "appdata"
    shell, _ = _make_persistent_shell(base, {
        "no_move": True, "pet_opacity": 40,
        "mouse_through": True, "self_talk_enabled": True,
    })
    try:
        stale = shell._config.data["pet_opacity"]
        assert stale == 40, "前置条件：运行期那份 Config 必须还停在旧值"

        settings = Config(str(base))                # 设置进程：独立实例
        assert settings.reset_to_defaults() is True
        assert cmd_mod.write_command(
            settings.dir, cmd_mod.CMD_APPLY_SETTINGS_RESET) is True

        shell._consume_settings_command()           # ← 指令先到（reload 还没跑）
        shell.save_position()                       # ← 退出收口：真实整表写盘

        on_disk = Config(str(base))
        assert on_disk.get("pet_opacity") == 100, "overlay 退出写盘把默认值覆盖回旧值"
        assert on_disk.get("no_move") is False
        assert on_disk.get("mouse_through") is False
        assert on_disk.get("self_talk_enabled") is False
        from pet import pet_profiles

        assert "rx" not in json.loads(on_disk.path.read_text(encoding="utf8"))
        assert pet_profiles.read_slot_profile(on_disk.dir, 0).value("rx") is not None
    finally:
        shell._teardown_settings_command_watch()
        shell._delete_runtime_marker()
        if getattr(shell, "tray", None) is not None:
            shell.tray.hide()


# ------------------------------------- 5. 两个作用域两个动作（终审 A04-a）
# 设置页的所有产品入口都带 `--instance slot-N`（含 slot0）。只留一个"本宠"按钮时，
# 已经在实现里活着的**全局** reset 在产品 UI 上完全不可达——用户只能手工命令行
# `--settings` 才够得着。两个动作复用两个既有实现与两份既有文案，不新增设置项。

def _slot_page_dialog(tmp_path: Path):
    """真设置窗：slot0 页（路由视图），全局侧带脏值。"""
    from pet import pet_profiles
    from pet.settings_slot_config import route_settings_config

    base = tmp_path / "appdata"
    main = Config(base=base)
    main.set("pet_opacity", 55)
    main.set("autostart_wanted", True)
    main.set("self_talk_texts", ["全局台词"])
    main.set("chat", {
        "active_provider": "relay",
        "providers": {"relay": {"name": "中转", "api_key": "sk-live", "base_url": "x"}},
    })
    assert main.save() is True
    assert pet_profiles.write_profile_settings(
        main.dir, 0, {"scale": 0.8, "playback_speed": 1.5}, user_customized=True).status == "ok"
    routed = route_settings_config(Config(base=base, instance_id="slot-0"))
    return ModernSettingsDialog(routed, include_ai=False), main






