# -*- coding: utf-8 -*-
"""配置读取与持久化；兼容旧版平铺 chat_* 字段的迁移。"""

from __future__ import annotations

import copy
import errno
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from . import catalog


DEFAULT_ANIMATION_GAP_SECONDS = 0.0
DEFAULT_SELF_TALK_MIN_INTERVAL = 20.0
DEFAULT_SELF_TALK_MAX_INTERVAL = 60.0
DEFAULT_SELF_TALK_DURATION_SECONDS = 3.2
DEFAULT_SELF_TALK_TEXTS = [
    "\u597d\u5973\u5b69\u2026\u2026",
    "\u597d\u6a21\u578b\u2026\u2026",
    "\u6b27\u9cb8\u9cb8\u2026\u2026",
    "\u4eca\u5929\u4e5f\u8981\u8ba4\u771f\u5de5\u4f5c\u5440\u3002",
    "\u518d\u966a\u4f60\u4e00\u4f1a\u513f\u3002",
]
DEFAULT_SELF_TALK_BUBBLE_STYLE = "classic_top"
# 自言自语出图概率（百分比 0~100）：先决定"这次出图还是出文本"，再在对应池里等权
# 抽一条。默认 30%——图片目录常有几十张图，若与文本等权随机会让图片彻底压过文本
# （实测某配置 24 图 + 5 句 → 出图 82.8%，点击几乎总是弹图）。
DEFAULT_SELF_TALK_IMAGE_CHANCE = 30
# 免打扰（issue #208）时长档位（分钟）：右键菜单四档与设置页「默认时长」共用这
# 一份列表——**唯一来源**，两处各抄一份迟早漂移。
QUIET_MINUTE_CHOICES = (15, 30, 60, 120)
DEFAULT_QUIET_MINUTES = 30
DEFAULT_QUIET_ALSO_ON_FULLSCREEN = True
# 免打扰暂存队列上限：溢出丢最旧（规格硬要求）。
QUIET_QUEUE_LIMIT = 20


def normalize_quiet_minutes(value) -> int:
    """把任意输入归一到一个合法档位（手改 config / 陈旧值都不至于让菜单空掉）。

    非法值回落默认档；合法整数取**最近的档**（60 → 60，45 → 30/60 取近者），
    保证消费方（菜单/设置页/倒计时）永远拿到 ``QUIET_MINUTE_CHOICES`` 里的值。
    OverflowError 与 ``_float_or_default`` 同规：json 里 400 位数字串会解析成
    Python 大整数，``float()`` 直接抛——不接住就是 Config() 构造失败、启动崩。
    """
    try:
        minutes = float(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_QUIET_MINUTES
    if minutes != minutes or minutes <= 0:  # NaN / 非正数
        return DEFAULT_QUIET_MINUTES
    return int(min(QUIET_MINUTE_CHOICES, key=lambda choice: (abs(choice - minutes), choice)))


DEFAULT_DIALOGUE_PHRASES = {}
DEFAULT_COLLISION_SETTINGS = {
}
SELF_TALK_BUBBLE_STYLES = {
    "classic_top",
    "paper_left",
    "glass_right",
    "soft_blue_top",
    "breath_bubble",
}
DEFAULT_CONTEXT_MENU_APPEARANCE = {
    "theme": "system",
    "density": "standard",
    "corner_radius": 12,
    "ui_font": "system",
    "ui_font_size": 13,
    "translucent": True,
    "opacity": 0.94,
    "light_background": "#ffffff",
    "light_foreground": "#171717",
    "light_hover": "#eeeeee",
    "dark_background": "#252525",
    "dark_foreground": "#f3f3f3",
    "dark_hover": "#3a3a3a",
}



# 2026-09-23：右键菜单去掉「鼠标穿透」（该开关的唯一入口收敛到桌宠设置 + 托盘菜单），
# 用户旧布局里残留的该节点在此一次性剔除——否则菜单编辑器会把它一直回存成「此平台
# 不可用」，旧入口就没有干净去向（docs/SETTINGS-CHANGE-GATES.md「旧 key/旧入口有去向」）。
# 同名 action id 若将来重新引入，删掉这里即可。
_MENU_LAYOUT_DROPPED_ACTIONS = frozenset({
    "mouse_through",
    # 2026-10-21：精简版移除的功能入口。用户旧布局里残留的节点在此一次性剔除。
    "chat", "look_screen", "screen_capture", "character",
    "music", "music_pause", "music_next", "music_prev", "music_quit",
    "music_lyric_align", "music_open_netease", "music_open_qqmusic",
    "music_open_kugou", "music_open_soda",
    "quick_launch", "agent_link", "proactive_screen", "todo_panel",
    "weather", "weather_cities", "divination_draw",
    "harness", "deepseek_web", "check_update", "network_info",
    "github_project", "quark_download",
    "spawn_pet", "clear_spawned_pets", "drag_physics",
    # 仅从右键菜单移除；功能保留在设置页（播放速率 / 桌宠大小）。
    "playback_speed", "size",
    "ojingjing",
})


def _drop_removed_menu_actions(nodes):
    kept = []
    for node in nodes:
        if not isinstance(node, dict):
            kept.append(node)
            continue
        if str(node.get("id") or "") in _MENU_LAYOUT_DROPPED_ACTIONS:
            continue
        children = node.get("children")
        if isinstance(children, list):
            node["children"] = _drop_removed_menu_actions(children)
        kept.append(node)
    return kept


def _clean_menu_layout_override(value):
    if not isinstance(value, dict):
        return None
    cleaned = copy.deepcopy(value)
    nodes = cleaned.get("nodes")
    if isinstance(nodes, list):
        cleaned["nodes"] = _drop_removed_menu_actions(nodes)
    return cleaned


def _clean_color(value, default):
    value = str(value or "").strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value.lower()
        except ValueError:
            pass
    return default


def _clean_menu_appearance(value):
    value = value if isinstance(value, dict) else {}
    defaults = DEFAULT_CONTEXT_MENU_APPEARANCE
    theme = str(value.get("theme", "system"))
    density = str(value.get("density", "standard"))
    # 整数键统一走 _float_or_default 再取整：手写 int() 只接 TypeError/ValueError，
    # 而 Infinity/NaN 撞 int() 抛 OverflowError（一整个启动路径就此断掉）。
    radius = int(_float_or_default(value.get("corner_radius"), 12.0, 6.0, 18.0))
    font_size = int(_float_or_default(value.get("ui_font_size"), 13.0, 10.0, 18.0))
    result = {
        "theme": theme if theme in {"system", "light", "dark"} else "system",
        "density": density if density in {"compact", "standard", "spacious"} else "standard",
        "corner_radius": radius,
        "ui_font": str(value.get("ui_font") or "system")[:80],
        "ui_font_size": font_size,
        "translucent": bool(value.get("translucent", True)),
        "opacity": _float_or_default(value.get("opacity"), 0.94, 0.72, 1.0),
    }
    for key in (
        "light_background",
        "light_foreground",
        "light_hover",
        "dark_background",
        "dark_foreground",
        "dark_hover",
    ):
        result[key] = _clean_color(value.get(key), defaults[key])
    return result


def _normalize_fun_asset_path(candidate: str, default: str) -> str:
    """绝对路径若指向应用内置 assets 目录，归一化为相对路径。

    旧版设置对话框会把默认相对路径固化成安装目录绝对路径；portable
    目录一移动/自更新即失效。此处在加载时统一还原为 assets/... 相对值。
    """
    candidate = str(candidate or "").strip()
    if not candidate:
        return default
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        return candidate
    assets_root = Path(__file__).resolve().parents[1] / "assets"
    try:
        rel = path.resolve().relative_to(assets_root.resolve())
        # 统一正斜杠：配置值与 legacy 迁移比较、跨平台一致
        return str(Path("assets") / rel).replace("\\", "/")
    except ValueError:
        return candidate


def _default_click_sound_pack() -> dict:
    return {"kind": "builtin", "id": "default", "path": ""}


def _clean_click_sound_pack(value: Any) -> dict:
    defaults = _default_click_sound_pack()
    if not isinstance(value, dict):
        return dict(defaults)
    kind = str(value.get("kind") or "builtin").strip().lower()
    if kind not in {"builtin", "file", "folder"}:
        return dict(defaults)
    pack_id = str(value.get("id") or ("default" if kind == "builtin" else "custom")).strip()
    if kind == "builtin" and pack_id not in {"default", "duck"}:
        pack_id = "default"
    path = str(value.get("path") or "").strip()[:500]
    return {
        "kind": kind,
        "id": pack_id,
        "path": path,
    }

def _default_chat_data():
    return {
        "enabled": True,
        "active_provider": "openai-main",
        "default_system_prompt": "\u4f60\u662f\u4e00\u53ea\u53ef\u7231\u7684\u684c\u9762\u5ba0\u7269\uff0c\u8bf7\u7528\u81ea\u7136\u3001\u53cb\u5584\u7684\u4e2d\u6587\u548c\u7528\u6237\u4ea4\u6d41\u3002",
        "history_message_limit": 40,
        "history_char_limit": 24000,
        "providers": {
            "openai-main": {
                "name": "DeepSeek",
                "base_url": "https://api.deepseek.com",
                "chat_path": "/v1/chat/completions",
                "model": "deepseek-v4-flash",
                "api_key_ref": "provider/openai-main",
                "api_key": "",
                "timeout": 60.0,
                "temperature": 0.7,
                "max_tokens": 2048,
            }
        },
        # 联网搜索全局默认值（与 pet/chat/models.py 的 WebSearchSettings 数据类保持一致；
        # 默认值快照比对按这里的字面量走，不要再抄进 settings_default_marks）。
        # 不写 api_key：保存路径会做密钥卫生（pop 掉 api_key），写了反而让
        # 「重置→保存→重载」与出厂初始数据产生结构性差异。
        "web_search": {
            "enabled": False,
            "engine": "baidu",
            "api_key_ref": "websearch/api",
            "max_results": 5,
            "fetch_pages": True,
        },
    }


def _merge_chat_data(raw):
    result = _default_chat_data()
    raw = raw if isinstance(raw, dict) else {}
    result.update({k: v for k, v in raw.items() if k != "providers"})
    incoming = raw.get("providers")
    if isinstance(incoming, dict) and incoming:
        providers = {}
        for provider_id, provider in incoming.items():
            if isinstance(provider, dict):
                base = dict(_default_chat_data()["providers"].get("openai-main", {}))
                base.update(provider)
                # 非 openai-main provider 未显式写 api_key_ref 时按自身归位，
                # 避免沿用 openai-main 的钥匙串条目（密钥串用/查错 key）。
                # 必须看用户原始输入：base 已被 openai-main 默认值预填，判 base 永远非空。
                if not str(provider.get("api_key_ref") or "").strip():
                    base["api_key_ref"] = f"provider/{provider_id}"
                # 历史 bug 迁移：旧版本曾把 openai-main 的钥匙串引用继承给自定义 provider，
                # UI 从不暴露该字段，非主 provider 挂着主引用一定是继承错的。
                if provider_id != "openai-main" and base.get("api_key_ref") == "provider/openai-main":
                    base["api_key_ref"] = f"provider/{provider_id}"
                providers[str(provider_id)] = base
    else:
        providers = dict(result["providers"])
    result["providers"] = providers or _default_chat_data()["providers"]
    active = str(result.get("active_provider") or "")
    result["active_provider"] = active if active in result["providers"] else next(iter(result["providers"]))
    return result


#: chat 域里的密钥类字段（provider 级）——「恢复默认设置」唯一保留的项。
#:
#: 为什么保留：API Key 是用户最难重配的一项（要回服务商后台重新申请/翻记录），
#: 且 keyring 不可用时 ``_redacted_data`` 不落盘、明文只存在内存里，重置一并清掉
#: 会让用户当场失去凭据。``api_key_ref``/``vision_api_key_ref`` 是指向系统钥匙串
#: 的引用，属于同一份凭据的一半，必须与明文一起保留，否则钥匙串里有 key 也取不回来。
#: 其余 chat 键（服务商地址/模型/提示词/历史长度）与其它域一律回默认。
CHAT_SECRET_FIELDS = ("api_key", "api_key_ref", "vision_api_key", "vision_api_key_ref")


def chat_secret_carryover(chat: Any) -> dict[str, dict]:
    """提取 chat.providers 下各 provider 的密钥类字段 + 识别用的显示名。

    返回 ``{provider_id: {字段: 值}}``（凭据字段 + 可选的 ``name``），只收集非空值；
    返回空 dict = 没有凭据要保留。只读，不改传入数据（重置换掉 ``self.data`` 时旧值
    已不在原处，必须先取出来）。

    ``name`` 不是凭据，但重置后要给非默认 provider 重建一个凭据容器，光有 provider_id
    用户认不出那是哪个服务商（id 多为 ``api-2`` 这类自动名）；它只在重建时用来当骨架名，
    已存在的 provider 只回填凭据、不覆盖名字（名字属于"其余配置"，按重置口径回默认）。
    """
    providers = chat.get("providers") if isinstance(chat, dict) else None
    if not isinstance(providers, dict):
        return {}
    carried: dict[str, dict] = {}
    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        kept = {
            field: provider[field]
            for field in CHAT_SECRET_FIELDS
            if str(provider.get(field) or "").strip()
        }
        if not kept:
            continue
        name = str(provider.get("name") or "").strip()
        if name:
            kept["name"] = name[:60]
        carried[str(provider_id)] = kept
    return carried


def _default_base():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home())
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path.home() / ".config"


def _app_dir_name() -> str:
    """打包变体的独立数据目录名；源码运行时回退到共享目录。

    构建脚本（scripts/build_onedir.ps1）会在打包前生成
    packaging/build_variant.py（VARIANT = "webm-chat" 等），
    使 Chat / 无 Chat 等变体各自使用独立的配置目录、会话与自启项。
    """
    try:
        from build_variant import VARIANT  # 仅打包产物中存在

        name = str(VARIANT).strip()
        if name:
            return f"dsh-pet-standalone-{name}"
    except Exception:
        pass
    return "dsh-pet-standalone"


APP_DIR_NAME = _app_dir_name()


def _float_or_default(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        # OverflowError：json.loads 会把超长整数字面量解析成 Python int，
        # float(10**400) 直接抛——不接住就是 Config() 构造失败、启动崩。
        return default
    if number != number:  # NaN
        # NaN 与任何数比较都为假，max/min 的结果取决于参数顺序（实测回落到区间
        # **上限**），是夹取夹不出来的脏值——与 net_monitor.clamp_interval /
        # speech_bubble_text.clamp_bubble_text_scale 同规：回默认。
        return default
    return max(minimum, min(maximum, number))


def _bool_or_default(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(default)


def _clean_self_talk_texts(value):
    if not isinstance(value, list):
        return list(DEFAULT_SELF_TALK_TEXTS)
    texts = []
    for item in value:
        text = str(item).strip()
        if text and text not in texts:
            texts.append(text[:120])
    return texts or list(DEFAULT_SELF_TALK_TEXTS)


def _clean_character_profiles(value) -> dict:
    """角色档案：当前先承载 click_talk_bindings，后续可扩展头像/人设字段。"""
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for character_id, profile in value.items():
        if not isinstance(profile, dict):
            continue
        bindings_raw = profile.get("click_talk_bindings")
        bindings = {}
        if isinstance(bindings_raw, dict):
            for action_id, texts in bindings_raw.items():
                if not isinstance(texts, list):
                    continue
                items = []
                for item in texts:
                    text = str(item).strip()
                    if text and text not in items:
                        items.append(text[:120])
                if items:
                    bindings[str(action_id)] = items
        entry = dict(profile)
        entry["click_talk_bindings"] = bindings
        cleaned[str(character_id)] = entry
    return cleaned


#: os.replace 的瞬时共享冲突判定用 WinError：ERROR_ACCESS_DENIED(5) 与
#: ERROR_SHARING_VIOLATION(32)。
_REPLACE_CONFLICT_WINERRORS = (5, 32)
_REPLACE_RETRY_BASE_DELAY = 0.02   # 20ms 起步
_REPLACE_RETRY_MAX_DELAY = 0.2     # 封顶 200ms


def _is_replace_conflict(exc: OSError) -> bool:
    """该 OSError 是否属"马上重试就能过"的瞬时共享冲突。"""
    if isinstance(exc, PermissionError):
        return True
    return (getattr(exc, "winerror", None) in _REPLACE_CONFLICT_WINERRORS
            or exc.errno in (errno.EACCES, errno.EPERM))


def atomic_replace_with_retry(temp, target, attempts: int = 5) -> None:
    """``os.replace(temp, target)``，遇瞬时共享冲突时有界退避重试。

    实机背景（Windows，独立设置进程的「保存并退出」报"配置未能写入磁盘"）：
    主进程 3s 轮询 / 目录 watcher 触发的瞬时 ``read_text()`` 与设置进程
    ``os.replace(temp, config.json)`` 撞在同一配置文件上 → PermissionError
    (WinError 5) → ``Config.save`` 返回 False → 用户"什么都没调也关不了设置"。

    只重试共享冲突（PermissionError / WinError 5、32 / EACCES、EPERM）：这类
    失败重试代价仅秒级且会自愈；其它 OSError（ENOENT、ENOSPC、跨设备……）是
    真实错误，立即上抛交给调用方诚实上报，不做无谓等待。重试耗尽后最后一次
    异常照常上抛（调用方的失败分支不变）。
    """
    delay = _REPLACE_RETRY_BASE_DELAY
    limit = max(1, int(attempts))
    for attempt in range(1, limit + 1):
        try:
            os.replace(temp, target)
            return
        except OSError as exc:
            if attempt >= limit or not _is_replace_conflict(exc):
                raise
            time.sleep(delay)
            delay = min(delay * 2, _REPLACE_RETRY_MAX_DELAY)


#: ``reload()`` 里**采纳盘上显式 null** 的键白名单（缺陷 15）。
#:
#: 背景：设置页「恢复默认」是靠写 ``null`` 表达"撤掉覆写"（modern_settings_dialog
#: 保存菜单编排时，用户布局等于内置默认就写 None）。旧实现把显式 null 与"键缺失"
#: 一视同仁（``raw[key] is not None``），主进程 reload 拿不到 None，之后任何一次
#: ``save()``（整体写内存视图）又把旧覆写写回磁盘——"恢复默认"静默回滚。
#:
#: 只把**把 None 当合法取值（= 用内置默认）**的键放进来：``context_menu_layout``
#: 的消费者是 ``_clean_menu_layout_override`` 与菜单渲染层，None 就是"没有覆写"。
#: 白名单外的键维持旧口径（null 视为"未提供"，保留内存现值）——它们大多是数值/
#: 字符串键，消费者直接 ``float()``/``int()``/``str()`` 强转或区间夹取，采纳 None
#: 会在运行期抛异常（"修一个键顺手炸一片"）。新增键前先确认其全部消费者吃 None。
#:
#: 2026-10-07 加入位置三键（issue #220 M10）：``reset_to_defaults`` 把 rx/ry/
#: screen_name 写成 null 表达"没有位置记忆"（新装/重置后应落默认角落）。消费者本来
#: 就是这个口径：``window_placement.restore_position`` 见 None 即 ``_default_corner_
#: pos``，``overlay_shell._restore_position``/``_spawn_sprite_pos`` 同样按 None 分支，
#: ``window_placement.screen_available(host, None)`` 回落当前屏。不采纳则运行期内存里
#: 一直留着**重置前**的位置：之后任何一次 ``restore_position``（换屏/副屏上线）都会
#: 把桌宠送回旧位置，与刚写下的默认值自相矛盾。
_NULL_ACCEPTING_KEYS = frozenset({"context_menu_layout", "rx", "ry", "screen_name"})


_MISSING = object()


def _keep_config_deletions(baseline: dict, local: dict, normalized: dict) -> None:
    for key in baseline.keys() | normalized.keys():
        if key not in local:
            normalized.pop(key, None)
        elif (isinstance(baseline.get(key), dict) and isinstance(local[key], dict)
              and isinstance(normalized.get(key), dict)):
            _keep_config_deletions(baseline[key], local[key], normalized[key])


def _merge_config_changes(baseline: dict, local: dict, latest: dict) -> dict:
    result = copy.deepcopy(latest)
    for key in baseline.keys() | local.keys():
        before = baseline.get(key, _MISSING)
        after = local.get(key, _MISSING)
        if after is _MISSING:
            result.pop(key, None)
        elif before == after:
            continue
        elif isinstance(after, dict) and (isinstance(before, dict) or before is _MISSING):
            disk = result.get(key)
            result[key] = _merge_config_changes(
                before if isinstance(before, dict) else {}, after,
                disk if isinstance(disk, dict) else {})
        else:
            result[key] = copy.deepcopy(after)
    return result


def _pet_profile_version(raw: dict) -> int:
    try:
        return int(raw.get("version", 1) or 1)
    except (TypeError, ValueError, OverflowError):
        return 1


def _has_click_sound_pack(raw: dict) -> bool:
    pack = raw.get("click_sound_pack")
    return (isinstance(pack, dict)
            and str(pack.get("kind") or "").strip().lower() in {"builtin", "file", "folder"})


def _migrate_pet_profile_values(data: dict, raw: dict) -> None:
    if _pet_profile_version(raw) < 2:
        data["scale"] = catalog.DEFAULT_SCALE
    if not _has_click_sound_pack(raw):
        old_path = str(raw.get("click_sound_path") or "").strip()
        data["click_sound_pack"] = (
            {"kind": "file", "id": "custom", "path": old_path}
            if old_path else _default_click_sound_pack())


def _normalize_pet_profile_values(data: dict) -> None:
    from . import physics as physics_mod

    data["scale"] = _float_or_default(data.get("scale"), catalog.DEFAULT_SCALE, 0.1, 4.0)
    data["playback_speed"] = _float_or_default(data.get("playback_speed"), 1.0, 0.1, 8.0)
    minimum = _float_or_default(data.get("self_talk_min_interval"), DEFAULT_SELF_TALK_MIN_INTERVAL, 5.0, 3600.0)
    maximum = _float_or_default(data.get("self_talk_max_interval"), DEFAULT_SELF_TALK_MAX_INTERVAL, 5.0, 3600.0)
    data["self_talk_min_interval"] = min(minimum, maximum)
    data["self_talk_max_interval"] = max(minimum, maximum)
    data["self_talk_duration_seconds"] = _float_or_default(
        data.get("self_talk_duration_seconds"), DEFAULT_SELF_TALK_DURATION_SECONDS, 1.0, 300.0)
    data["self_talk_image_dir"] = str(data.get("self_talk_image_dir") or "").strip()[:500]
    data["self_talk_image_scale"] = int(_float_or_default(data.get("self_talk_image_scale"), 100.0, 50.0, 300.0))
    data["self_talk_image_chance"] = int(_float_or_default(data.get("self_talk_image_chance"), float(DEFAULT_SELF_TALK_IMAGE_CHANCE), 0.0, 100.0))
    data["bubble_text_scale"] = int(_float_or_default(data.get("bubble_text_scale"), 100.0, 50.0, 300.0))
    data["self_talk_enabled"] = bool(data.get("self_talk_enabled", False))
    data["self_talk_texts"] = _clean_self_talk_texts(data.get("self_talk_texts"))
    bubble_style = str(data.get("self_talk_bubble_style") or "")
    data["self_talk_bubble_style"] = bubble_style if bubble_style in SELF_TALK_BUBBLE_STYLES else DEFAULT_SELF_TALK_BUBBLE_STYLE
    data["click_sound_enabled"] = bool(data.get("click_sound_enabled", True))
    data["click_sound_pack"] = _clean_click_sound_pack(data.get("click_sound_pack"))
    data["click_sound_volume"] = _float_or_default(data.get("click_sound_volume"), 0.70, 0.0, 1.0)
    data["throw_strength"] = physics_mod.normalize_throw_strength(str(data.get("throw_strength") or "standard"))
    data["drop_gravity"] = _bool_or_default(data.get("drop_gravity"), False)
    recycle = _float_or_default(data.get("ffmpeg_recycle_minutes"), 10, 0, 120)
    data["ffmpeg_recycle_minutes"] = 0 if recycle <= 0 else int(max(2.0, recycle))


def normalize_pet_profile_snapshot(raw: Any) -> dict:
    """纯每宠快照迁移与清洗；返回独立数据，不读盘、不构造 Config。"""
    from .pet_profiles import PER_PET_KEYS

    raw = raw if isinstance(raw, dict) else {}
    defaults = Config._initial_data()
    data = {key: defaults[key] for key in PER_PET_KEYS}
    data.update({key: copy.deepcopy(value) for key, value in raw.items()
                 if key in PER_PET_KEYS and (value is not None or key in _NULL_ACCEPTING_KEYS)})
    _migrate_pet_profile_values(data, raw)
    _normalize_pet_profile_values(data)
    return data


class Config:
    def __init__(self, base=None, instance_id: str | None = None):
        base = Path(base) if isinstance(base, str) else (base or _default_base())
        self.dir = base / APP_DIR_NAME
        # 多开隔离：--instance <id> 或 DSH_PET_INSTANCE 时使用独立配置文件，
        # 位置/大小/朝向等不再互相覆盖；不传时完全保持原行为。
        self.instance_id = (os.environ.get("DSH_PET_INSTANCE", "") if instance_id is None else instance_id).strip()
        self.path = self.dir / f"config-{self.instance_id}.json" if self.instance_id else self.dir / "config.json"
        self._migrate_legacy_config(base)
        # 副槽"整表落种"（把主配置整份复制成 config-slot-N.json）已随规范 §五 退役：
        # 每宠键的真值只经 ``pet_profiles.write_profile_settings`` 落进档案，生成子宠
        # 时的落种在 ``overlay_shell._build_slot_sprite`` / ``app.py`` 的 spawn 路径上
        # （``tests/test_single_process_spawn.py`` 锁"整表落种入口不再使用"）。
        self.data = self._initial_data()
        self._save_baseline = copy.deepcopy(self.data)
        self._reset_generation = None
        self._full_reset = False
        self.reload()
        self._normalize_pet_settings()

    @staticmethod
    def _initial_data() -> dict:
        """构造出厂默认配置数据（唯一来源）。

        ``__init__`` 与 :meth:`reset_to_defaults` 共用本方法：默认值只此一份，
        重置设置必须与首次启动落在同一组值上（两份字面量迟早会漂移）。
        """
        return {
            "version": 4,
            "rx": None,
            "ry": None,
            "screen_name": None,
            "facing": "left",
            "scale": catalog.DEFAULT_SCALE,
            "user_customized": False,  # 批 C：仅当用户在该子肥鱼自己的设置界面保存过才置真
            "on_top": True,
            "show_dock_icon": True,
            "no_move": False,
            "character": catalog.DEFAULT_CHARACTER,
            "playback_speed": 1.0,
            "animation_gap_seconds": DEFAULT_ANIMATION_GAP_SECONDS,
            "self_talk_enabled": False,
            "self_talk_min_interval": DEFAULT_SELF_TALK_MIN_INTERVAL,
            "self_talk_max_interval": DEFAULT_SELF_TALK_MAX_INTERVAL,
            "self_talk_duration_seconds": DEFAULT_SELF_TALK_DURATION_SECONDS,
            "self_talk_image_scale": 100,  # 气泡配图显示尺寸百分比（50~300，100 = 默认）
            "self_talk_image_chance": DEFAULT_SELF_TALK_IMAGE_CHANCE,  # 出图概率百分比（0~100）
            "bubble_text_scale": 100,  # 气泡文字显示尺寸百分比（50~300，100 = 默认；气泡与字号一起放大）
            "self_talk_texts": list(DEFAULT_SELF_TALK_TEXTS),
            "self_talk_image_dir": "assets/big_blue_fat_fish",
            "self_talk_bubble_style": DEFAULT_SELF_TALK_BUBBLE_STYLE,
            # Existing event wording: legacy is deliberately the default.
            "dialogue_mode": "legacy",
            "dialogue_phrases": dict(DEFAULT_DIALOGUE_PHRASES),
            "dialogue_last_scope": "",  # 台词编辑上次打开的层（""=全局；设置页专属文案入口记忆）
            "mouse_through": False,
            "cursor_hidden_passthrough": True,
            "drop_gravity": False,  # 静止放手下落：低速松手零初速受重力落地（#219，默认关=旧行为）
            "lock_position": False,  # 锁定位置：桌宠不可拖动（点击仍有效）
            "shift_drag": False,  # 按住 SHIFT+左键才能拖动
            "pet_opacity": 100,  # 桌宠窗口不透明度 10-100
            "context_menu_layout": None,
            "context_menu_appearance": dict(DEFAULT_CONTEXT_MENU_APPEARANCE),
            # 动画菜单连播（#221）：默认 False = 点一个动作就把整条菜单链收起，
            # 菜单不再挡住桌宠。想连点多个动作连播的用户手改成 true（菜单行为类
            # 偏好，与 mem_* 同口径：不进设置页，config.json 里改）。
            "anim_menu_stay_open": False,
            "auto_hide_fullscreen": True,  # 全屏应用自动隐藏（Windows）
            # 允许桌宠跨屏（全局键、重启级）：开启后每块有桌宠的屏各一张合成窗，
            # 拖动可以跨显示器；关闭时全部桌宠只留在启动时那块屏。默认关 =
            # 单显示器用户与旧行为逐位相同（见 overlay_shell._cross_screen_allowed）。
            "allow_cross_screen": False,
            # 免打扰（issue #208）：右键菜单四档时长的默认档 + 全屏应用时自动等效
            # 免打扰。二者只描述**偏好**，当前是否在免打扰是运行态、不落盘。
            "quiet_minutes_default": DEFAULT_QUIET_MINUTES,
            "quiet_also_on_fullscreen": DEFAULT_QUIET_ALSO_ON_FULLSCREEN,
            "click_sound_enabled": True,  # 点击 Q 弹音效
            "click_sound_pack": _default_click_sound_pack(),
            "click_sound_volume": 0.70,
            "slingshot_enabled": True,  # 弹弓弹射
            "throw_strength": "standard",  # gentle / standard / strong / crazy
            "idle_low_fps_enabled": False,  # 闲置降帧（灰度默认关）：长时间无交互时动画隔帧呈现
            "idle_low_fps_threshold": 30.0,  # 闲置阈值（秒）：超过该时长无交互且窗口可见才降帧
            "click_show_balance": False,  # 点击显示 DeepSeek 余额
            "click_show_self_talk": False,  # 点击随机显示自定义自言自语
            "balance_refresh_minutes": 0,  # DeepSeek 余额自动刷新间隔（分钟，0=关闭）
            "balance_tier_labels_mode": "default",  # 峰谷提示文案：default / liangwen / custom
            "balance_tier_label_peak": "",  # 自定义“高峰”文本（custom 模式）
            "balance_tier_label_idle": "",  # 自定义“空闲”文本（custom 模式）
            "balance_tier_color_enabled": True,  # 峰谷提示颜色：高峰红/低谷绿
            "golden_spin_on_click": False,  # 点击回应动画结束后自动接一段黄金回旋
            "golden_spin_direct": False,  # 点击触发黄金回旋时跳过点击动画，直接回旋并逐圈加速
            "edge_probe_enabled": False,  # 拖到屏幕左右边缘后自动进入探头姿态
            # 「回收内存」菜单动作（#210）：只作用于**别的**进程（自己/前台/自己
            # 的子进程/系统关键进程一律不碰，见 pet/memory_trim.py）。菜单动作类
            # 功能不进设置页，这两个键只存在于 config.json。
            "mem_skip_foreground": True,  # 跳过当前前台进程（不抖用户正在用的窗口）
            "mem_min_size_mb": 50.0,  # 工作集小于该值(MB)的进程不折腾
            "autostart_wanted": False,  # 用户曾开启过开机自启（用于启动自检：被安全软件清理时提醒）
            "chat_background": "",  # 肥鱼牌小手机背景：空=纯色；builtin:* = 内置主题；否则为图片路径
            "modern_chat_background": "",  # 肥鱼版 DeepSeek 背景：空=纯色；否则为自定义图片路径
            "chat_background_opacity": 100,
            "chat_background_fill": "cover",
            "modern_chat_background_opacity": 100,
            "modern_chat_background_fill": "cover",
            "modern_chat_card_opacity": 84,
            "chat_bg_crops": {},  # 每个背景的用户自定义取景框 {背景标识: [x,y,w,h] 归一化}
            "character_aliases": {},  # 角色显示名别名 {角色id: 自定义名}，空名=恢复默认
            "character_profiles": {},  # 角色档案：{角色id: {click_talk_bindings: {动画id: [台词]}}}
            "system_notifications_enabled": True,  # 提醒/通知类事件是否弹桌面系统通知
            # 节日提醒（农历/24 节气/西方节日；命中当日用气泡告知并附氛围匹配文案）。
            # 总开关默认关闭：属"主动打扰"型功能，升级后不应突然冒出来，由用户显式开启。
            "festival_reminder_enabled": False,  # 节日提醒总开关
            "festival_reminder_cn": True,  # 中国节日
            "festival_reminder_solar_terms": True,  # 24 节气
            "festival_reminder_west": True,  # 西方节日
            "festival_reminder_mode": "times",  # times（按次数）/ custom（自定义时间点）
            "festival_reminder_count": 2,  # times 模式提醒次数（1~6，均匀铺在 09:00–21:00）
            "festival_reminder_times": "09:00",  # custom 模式时间点（HH:MM 逗号分隔）
            "festival_reminder_show_quote": True,  # 是否附诗词/引文
            "festival_reminder_animation": True,  # 节日提醒是否播匹配动画
            # 生日进「动态节日」：命中当天排最前，不进 FESTIVALS 静态表（见 festival_animations）。
            # 默认空串＝没填，非法/不存在的日期静默落空（clean_birthday 整串 fullmatch 校验）。
            "festival_birthday": "",
            "festival_custom_quotes_cn": "",  # 自定义中文文案（一行一条，追加到内置库）
            "festival_custom_quotes_west": "",  # 自定义西文文案（一行一条，追加到内置库）
            **DEFAULT_COLLISION_SETTINGS,
            "media_prewarm": "balanced",  # full / balanced / minimal 素材首帧预热力度
            # 批10-A3：默认 32→8MB。预测式预热（批10-A1）落地后，首帧 LRU 只需
            # 装「瞬时交互核 pinned（click/turn/drag）+ 1-2 个预测位」；idle/move
            # 由预测机制与 LRU 热度自然覆盖，不再常驻。
            "first_frame_cache_max_mb": 8,  # 首帧缓存全局预算（MB），低配机可调小
            # 批10-A1 预测式接力预热：当前动画墙钟剩余 ≤ 该提前量（毫秒）时，
            # 帧驱动提前掷骰决定下一动画并在后台预解码其首帧进 LRU（Phase 1）。
            "predict_prewarm_lead_ms": 350,  # 提前量（ms），范围 200-600
            # 批11-B1：ffmpeg 圈边界定期回收阈值（分钟）。长寿循环 reader 在圈
            # 边界驻留时按进程存活时长评估回收：达到该值 → 不 park/re-arm，正常
            # 退出杀进程、下一次 start() 自然 fresh spawn（把 47→64MB 的 ffmpeg
            # 内部累积周期性清零）。0 = 关闭回收（回退保险）；否则范围 [2, 120]。
            "ffmpeg_recycle_minutes": 10,
            # 批5.3：同角色共享解码链（进程内帧扇出）开关，默认开。多宠恒为
            # 进程内多窗/多 sprite（`experimental_single_process_spawn` 键已随
            # 4.4b 退役删除），关掉即回每窗独立解码。
            "experimental_shared_decode": True,
            # 设置页进程隔离：默认开 = 设置页拉到独立进程（--settings），关窗即
            # 进程退出，OS 连锅端走首开留下的字体/样式/模块高水位（无卸载 API）；
            # False = 完全回退进程内对话框旧路径（排障/回退保险，不新增控件）。
            "settings_process_isolation": True,
            "chat": _default_chat_data(),
        }

    def _migrate_legacy_config(self, base) -> None:
        """旧版各变体共用 %APPDATA%/dsh-pet-standalone；升级后首次运行时
        把该目录的 config.json 与 sessions/ 一次性复制到变体独立目录，
        避免用户设置与聊天会话“消失”。仅在新目录尚不存在时执行。"""
        if self.instance_id:
            return  # 多开实例不参与旧版迁移，避免把单开配置复制给每个实例
        if APP_DIR_NAME == "dsh-pet-standalone" or self.path.exists():
            return
        legacy = base / "dsh-pet-standalone"
        if not (legacy / "config.json").is_file():
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy / "config.json", self.path)
            src_sessions = legacy / "sessions"
            if src_sessions.is_dir():
                shutil.copytree(src_sessions, self.dir / "sessions", dirs_exist_ok=True)
        except OSError:
            pass

    def reload(self) -> bool:
        """从磁盘重读一份可信快照进内存；返回**这次有没有真的拿到**（既有调用方一律忽略）。

        ``False`` = 没拿到（目录锁抢不到 / 文件读不到 / 内容不可信 / 明确不是对象），
        内存保持原样——这条返回值只有 :meth:`discard_unsaved_drafts` 用：它需要知道
        "退回基线之后有没有与磁盘核对过"，好在拿不到的时候如实告诉用户。
        """
        if not self.path.is_file():
            # 盘上还没有这份配置：没有可核对的快照，内存里那份就是基线（不是失败）。
            return True
        from . import config_write_lock as cwl

        try:
            with cwl.config_write_lock(self.dir):
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                generation = self._read_reset_generation()
                if (self._reset_generation is not None
                        and generation != self._reset_generation
                        and self.data != self._save_baseline):
                    raise cwl.JsonStateError("reset 前的未保存草稿不能绑定到新代次")
        except cwl.ConfigWriteError as exc:
            logging.warning("重读配置未取得可信快照: %s (%s)", self.path, exc)
            return False
        except (OSError, ValueError):
            from . import slot_manager as slot_manager_mod

            slot_manager_mod.backup_corrupt_config(self.path)
            return False
        if not isinstance(raw, dict):
            from . import slot_manager as slot_manager_mod

            slot_manager_mod.backup_corrupt_config(self.path)
            return False
        old_version = _pet_profile_version(raw)
        chat = raw.get("chat") if isinstance(raw.get("chat"), dict) else {}
        legacy = {}
        if "chat_enabled" in raw:
            legacy["enabled"] = raw["chat_enabled"]
        if "chat_system_prompt" in raw:
            legacy["default_system_prompt"] = raw["chat_system_prompt"]
        legacy_provider = {}
        if raw.get("chat_api_url"):
            legacy_provider["base_url"] = raw["chat_api_url"]
        if raw.get("chat_model"):
            legacy_provider["model"] = raw["chat_model"]
        if raw.get("chat_api_key"):
            legacy_provider["api_key"] = raw["chat_api_key"]
        if legacy_provider:
            legacy["providers"] = {"openai-main": legacy_provider}
        merged = dict(legacy)
        merged.update(chat)
        # secret 只进不出：磁盘重载不得冲掉内存中的 key。
        # _redacted_data() 写盘时会剔除 chat.providers 下的明文 api_key /
        # vision_api_key（keyring 不可用时 key 只存内存 self.data），因此磁盘文件
        # 里没有这两项。这里若某 provider 在磁盘数据里缺 api_key/vision_api_key
        # 但合入前的内存里有，则保留内存值，避免设置对话框重开（自 config.reload()
        # 从磁盘重载）把用户未重启就丢掉的 key 覆盖成空。新旧两套设置对话框都走
        # 这条 reload() 路径，一处修复全覆盖。
        previous_chat = self.data.get("chat")
        previous_providers = previous_chat.get("providers") if isinstance(previous_chat, dict) else None
        merged_chat = _merge_chat_data(merged)
        self.data["chat"] = merged_chat
        if isinstance(previous_providers, dict):
            raw_providers = merged.get("providers")
            raw_providers = raw_providers if isinstance(raw_providers, dict) else {}
            merged_providers = merged_chat.get("providers")
            if isinstance(merged_providers, dict):
                for provider_id, merged_provider in merged_providers.items():
                    if not isinstance(merged_provider, dict):
                        continue
                    previous_provider = previous_providers.get(provider_id)
                    if not isinstance(previous_provider, dict):
                        continue
                    raw_provider = raw_providers.get(provider_id)
                    raw_provider = raw_provider if isinstance(raw_provider, dict) else {}
                    if "api_key" not in raw_provider and previous_provider.get("api_key"):
                        merged_provider["api_key"] = previous_provider["api_key"]
                    if "vision_api_key" not in raw_provider and previous_provider.get("vision_api_key"):
                        merged_provider["vision_api_key"] = previous_provider["vision_api_key"]
        for key in (
            "rx",
            "ry",
            "screen_name",
            "facing",
            "scale",
            "on_top",
            "show_dock_icon",
            "no_move",
            "character",
            "user_customized",
            "playback_speed",
            "animation_gap_seconds",
            "self_talk_enabled",
            "self_talk_min_interval",
            "self_talk_max_interval",
            "self_talk_texts",
            "self_talk_duration_seconds",
            "self_talk_image_dir",
            "self_talk_image_scale",
            "self_talk_image_chance",
            "bubble_text_scale",
            "self_talk_bubble_style",
            "mouse_through",
            "cursor_hidden_passthrough",
            "drop_gravity",
            "dialogue_mode",
            "dialogue_phrases",
            "dialogue_last_scope",
            "context_menu_layout",
            "lock_position",
            "shift_drag",
            "pet_opacity",
            "context_menu_appearance",
            "anim_menu_stay_open",
            "auto_hide_fullscreen",
            "quiet_minutes_default",
            "quiet_also_on_fullscreen",
            "click_sound_enabled",
            "click_sound_pack",
            "click_sound_volume",
            "slingshot_enabled",
            "throw_strength",
            "idle_low_fps_enabled",
            "idle_low_fps_threshold",
            "click_show_balance",
            "click_show_self_talk",
            "balance_refresh_minutes",
            "autostart_wanted",
            "allow_cross_screen",
            "golden_spin_on_click",
            "golden_spin_direct",
            "edge_probe_enabled",
            "mem_skip_foreground",
            "mem_min_size_mb",
            "balance_tier_labels_mode",
            "balance_tier_label_peak",
            "balance_tier_label_idle",
            "balance_tier_color_enabled",
            "chat_background",
            "modern_chat_background",
            "chat_background_opacity",
            "chat_background_fill",
            "modern_chat_background_opacity",
            "modern_chat_background_fill",
            "modern_chat_card_opacity",
            "chat_bg_crops",
            "system_notifications_enabled",
            "festival_reminder_enabled",
            "festival_reminder_cn",
            "festival_reminder_solar_terms",
            "festival_reminder_west",
            "festival_reminder_mode",
            "festival_reminder_count",
            "festival_reminder_times",
            "festival_reminder_show_quote",
            "festival_reminder_animation",
            "festival_birthday",
            "festival_custom_quotes_cn",
            "festival_custom_quotes_west",
            "character_aliases",
            "character_profiles",
            "media_prewarm",
            "first_frame_cache_max_mb",
            "predict_prewarm_lead_ms",
            "ffmpeg_recycle_minutes",
            "experimental_shared_decode",
            "settings_process_isolation",
        ):
            if key not in raw:
                continue
            value = raw[key]
            if value is None and key not in _NULL_ACCEPTING_KEYS:
                # 「键缺失」= 磁盘没提供（保留内存现值）；「显式 null」= 该键被撤成
                # 默认（只对 _NULL_ACCEPTING_KEYS 生效，口径见该常量）。
                continue
            self.data[key] = value
        self._migrate_click_sound_config(raw)
        self._migrate_decode_broker_config(raw)
        self._migrate_menu_template_config(raw)
        self.data["version"] = 4
        self._migrate_plaintext_keys_to_keyring()
        self._save_baseline = copy.deepcopy(self.data)
        if legacy:
            self._save_baseline["chat"] = copy.deepcopy(chat)
        else:
            raw_providers = chat.get("providers")
            if isinstance(raw_providers, dict):
                for provider_id, provider in raw_providers.items():
                    base_provider = self._save_baseline["chat"]["providers"].get(provider_id)
                    if not isinstance(provider, dict) or not isinstance(base_provider, dict):
                        continue
                    for ref in ("api_key_ref", "vision_api_key_ref"):
                        if base_provider.get(ref) != provider.get(ref):
                            if ref in provider:
                                base_provider[ref] = provider[ref]
                            else:
                                base_provider.pop(ref, None)
        if old_version < 2:
            self._save_baseline.pop("scale", None)
        if raw.get("click_sound_path") and not _has_click_sound_pack(raw):
            self._save_baseline.pop("click_sound_pack", None)
        self._reset_generation = generation
        return True

    @property
    def has_local_changes(self) -> bool:
        """内存是否偏离"最后一次成功保存/读取"的基线 = 这份内存里有本视图自己的未写差异。

        只给"要不要动这份内存"的只读判断用（``SlotRoutedConfig.absorb_persisted_globals``）：
        脏的时候任何 reload / 整值重放都会破坏编辑基线——reload 会把基线换成盘上那份，
        于是本地差异只能靠"整值重放"恢复，而整值重放会把**没碰过的同字典兄弟叶**按旧快照
        盖回内存，下一次 ``save()`` 的递归合并就把兄弟叶当成"本地差异"提交，另一份视图刚
        写成功的那个叶被静默覆盖。判据与 ``reload`` / ``save`` 内部那句
        ``self.data != self._save_baseline`` 同源，不另立第二份脏判据。
        """
        return self.data != self._save_baseline

    def discard_unsaved_drafts(self) -> tuple[bool, str]:
        """放弃内存里还没成功落盘的草稿：退回最后一次成功保存/读取的那一份，**不写盘**。

        只有一处调用方：设置窗里用户明确选了「放弃未保存的改动并关闭」。为什么不能
        只清调用方的待写区——``set()`` 改的就是**这份内存**（``data``），而 ``save()``
        失败时只保证"磁盘没被改坏"（它把 ``data`` 还原成进入本次保存前的那一份，而
        那一份已经带着用户的草稿）。草稿留在 ``data`` 里，下一次**无关**的保存就会把它
        当成"本地差异"按叶键合并落盘（实机审查 CF01：明确放弃过的尺寸改动被后续速度
        保存重新提交）。

        四件不做的事：不写盘、不推进/回滚代次侧车、不回滚磁盘上已经写成功的值、不新增
        keyring 写入（``reload()`` 里那条既有的"磁盘明文 key 迁进 keyring"是它自己的老
        行为，不是这里新加的）。做法是先退回 ``_save_baseline``（"最后一次成功"的那份，失败
        时它就是唯一可信的落点），再按磁盘重读核对一次：读到就用磁盘上那份（外部写者的
        新值顺带吸收进来），读不到就停在基线上——两条路上"被放弃的值不会再被写回"都
        成立（基线与草稿的差异已经归零）。

        返回 ``(是否与磁盘核对过, 没能核对时的配置文件路径)``：``False`` 时调用方必须
        把"草稿作废了、但没能核对磁盘"如实告诉用户，不许假称放弃完全成功。
        """
        self.data = copy.deepcopy(self._save_baseline)
        if self.reload():
            return True, ""
        return False, str(self.path)

    def reset_to_defaults(self) -> bool:
        """把全部设置恢复出厂默认，仅保留 chat 域密钥类字段（见 ``CHAT_SECRET_FIELDS``）。

        铁律：
        - 默认值走 ``_initial_data``（与首次启动同一份字面量），不另建第二份默认；
        - 落盘走 :meth:`save` 的既有原子写路径（临时文件 + ``atomic_replace_with_retry``，
          脱敏也在同一处），因此与设置页「批量改配置 + 一次性落盘」范式一致：主进程的
          config watcher 看到的要么是重置前、要么是重置后的完整文件，没有中间态；
        - 落盘失败整体回滚内存（返回 False），不留"内存已是默认、磁盘还是旧值"的错位。

        保留集的落点（缺一即"文案承诺保留密钥、行为却丢密钥"）：
        - 默认集里已有的 provider（``openai-main``）：只回填凭据字段，名字/地址/模型等
          其余字段按重置口径回默认；
        - 默认集里没有的 provider（用户自建/中转站）：重建一个**只装凭据**的最小条目
          （显示名 + 凭据），否则凭据无处安放——keyring 不可用时明文只存在内存里，
          条目一没了明文就永久丢失。骨架之外一律不留（地址/模型回默认模板），所以它
          不是"看起来配好了"的服务商，只是钥匙的容器，也不会被自动选中
          （``active_provider`` 回默认那个）。
        本方法从不触碰 ``SecretStore``：keyring 条目是外部状态，删它才是数据丢失。
        """
        carried = chat_secret_carryover(self.data.get("chat"))
        previous = self.data
        self.data = self._initial_data()
        providers = self.data["chat"]["providers"]
        for provider_id, kept in carried.items():
            kept = dict(kept)
            name = kept.pop("name", None)
            provider = providers.get(provider_id)
            if not isinstance(provider, dict):
                provider = {"name": name or provider_id}
                providers[provider_id] = provider
            provider.update(kept)
        self._full_reset = True
        try:
            if not self.save():
                self.data = previous
                return False
            return True
        finally:
            self._full_reset = False

    def _migrate_plaintext_keys_to_keyring(self) -> None:
        """加载时把磁盘遗留的明文 API Key 迁移进 keyring。

        v4.0.4/4.0.5 起 _redacted_data() 写盘时剔除 chat.providers 下的明文
        api_key/vision_api_key，但 SecretStore.set 只在设置对话框保存时调用——
        老版本（≤v4.0.0）磁盘上的明文 key 从未进过 keyring，升级后首次写盘即被剔除，
        重启后 resolve_api_key 拿不到任何值，聊天/视觉 401 静默失效。
        此处补迁移：keyring 已有值不覆盖（与 resolve_api_key 的 keyring 优先序一致），
        仅丢弃明文；set 失败（keyring 不可用）保留内存明文，维持原兜底行为。
        幂等：迁移成功后内存/磁盘均无明文，重复 reload 无副作用；不主动 save()，
        写盘剔除交给下次正常保存。
        """
        chat = self.data.get("chat")
        providers = chat.get("providers") if isinstance(chat, dict) else None
        if not isinstance(providers, dict):
            return
        try:
            from .chat.models import SecretStore  # 惰性导入，且只实例化一次
        except ModuleNotFoundError as exc:
            # 无聊天功能的独立打包会明确排除 pet.chat；配置仍可被
            # 通用入口加载，因此不能让一次迁移检查阻止桌宠启动。
            if exc.name == "pet.chat" or str(exc.name or "").startswith("pet.chat."):
                return
            raise
        store = SecretStore()
        for provider_id, provider in providers.items():
            if not isinstance(provider, dict):
                continue
            for key_field, ref_field, default_ref in (
                ("api_key", "api_key_ref", f"provider/{provider_id}"),
                ("vision_api_key", "vision_api_key_ref", f"provider/{provider_id}/vision"),
            ):
                plaintext = str(provider.get(key_field) or "")
                if not plaintext.strip():
                    continue
                ref = str(provider.get(ref_field) or "").strip()
                if not ref:
                    ref = default_ref
                    provider[ref_field] = ref
                if store.get(ref) or store.set(ref, plaintext):
                    provider.pop(key_field, None)

    def _migrate_click_sound_config(self, raw: dict) -> None:
        """旧版 click_sound_path 迁移为 click_sound_pack。"""
        _migrate_pet_profile_values(self.data, raw)

    def _migrate_decode_broker_config(self, raw: dict) -> None:
        """批5.3：decode_broker_enabled 退役（shm broker 下线，共享解码改由
        进程内 DecodeFanoutHub 承担）。迁移语义（SETTINGS-CHANGE-GATES）：读旧值
        → 记一次 info → 忽略（键从 defaults/白名单移除，不再归一/进入 self.data）。"""
        if getattr(self, "_decode_broker_migrated", False):
            return
        if "decode_broker_enabled" in raw:
            old = raw.get("decode_broker_enabled")
            logging.getLogger(__name__).info("配置键 decode_broker_enabled 已退役（批5.3 共享解码改为进程内 fan-out），忽略旧值 %r", old)
            raw.pop("decode_broker_enabled", None)
        self._decode_broker_migrated = True

    def _migrate_menu_template_config(self, raw: dict) -> None:
        """2026-10-08：右键菜单模板键退役（旧版扁平菜单全量删除，只剩现代树）。

        迁移语义（SETTINGS-CHANGE-GATES「旧 key 有明确去向」）：读旧值 → 记一次
        info → 丢弃。**不报错、不回退、不写回**——旧存档里不论写着 ``legacy``、
        ``modern`` 还是脏值，表现都是"什么都没发生"：菜单永远是现代树，键在下一次
        save()（落盘的是 ``self.data``，键已不在其中）时从文件里消失。

        主配置与每个 slot 配置各走一次本方法（所有实例都是同一条构造路径），因此
        子肥鱼那份 ``config-slot-N.json`` 同样被清。

        幂等且可重复调用：``save`` 落盘前对**盘上那份**再跑一次同一实现（合并以盘
        上内容为底，不清就写回）。日志只记一次（``_menu_template_migrated``）。
        """
        if "context_menu_template" in raw:
            if not getattr(self, "_menu_template_migrated", False):
                logging.getLogger(__name__).info(
                    "配置键 context_menu_template 已退役（旧版右键菜单全量删除，"
                    "菜单恒为现代树），忽略旧值 %r", raw.get("context_menu_template"))
            raw.pop("context_menu_template", None)
        self._menu_template_migrated = True

    @staticmethod
    def _clean_phrase_events(events) -> dict:
        """清洗单层 dialogue 事件映射 {event: list[str] | str}（值上限 8 条/240 字符）。"""
        if not isinstance(events, dict):
            return {}
        cleaned = {}
        for key, value in events.items():
            if not str(key).strip():
                continue
            if isinstance(value, list):
                items = [item.strip()[:240] for item in value if isinstance(item, str) and item.strip()]
                if not items:
                    continue
                cleaned[str(key)] = items[:8]
            elif isinstance(value, str) and value.strip():
                cleaned[str(key)] = value.strip()[:240]
        return cleaned

    # dialogue 文案占位符迁移表：旧字段名（链路语义曾错位/曾与协议保留字段撞名）
    # → 新字段名。加载时幂等替换（新文案不含旧占位符即 no-op），只在用户
    # 自定义 dialogue_phrases 上执行；内置 preset JSON 直接改源文件。
    _DIALOGUE_PLACEHOLDER_MIGRATIONS = (
        ("{source}", "{failureType}"),
        ("{errorText}", "{errorMessage}"),
    )

    # 事件键改名表：旧事件键（曾按状态码命名）→ 新语义键。内置 preset JSON 直接
    # 改源文件；用户自定义 dialogue_phrases 里的旧键在加载时迁移一次（幂等）。
    # 新键已存在时以新配置为准，丢弃旧键（不合并、不留别名）。
    _DIALOGUE_EVENT_KEY_MIGRATIONS = (
        ("rate_limit.one", "model_access.one"),
        ("rate_limit.many", "model_access.many"),
    )

    @classmethod
    def _migrate_dialogue_phrase_fields(cls, phrases) -> None:
        """迁移 dialogue_phrases（global/agents 各层文案）里的旧事件键与旧占位符。

        先按 ``_DIALOGUE_EVENT_KEY_MIGRATIONS`` 改键，再把 list/str 值里的旧占位符
        替换为新名（``_DIALOGUE_PLACEHOLDER_MIGRATIONS``）。原地修改；对新配置
        （无旧键、无旧占位符）幂等无副作用。
        """
        if not isinstance(phrases, dict):
            return
        stack = [phrases]
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            for old_key, new_key in cls._DIALOGUE_EVENT_KEY_MIGRATIONS:
                if old_key not in node:
                    continue
                if new_key in node:
                    node.pop(old_key)  # 新配置优先：同名新键已在，丢弃旧键
                else:
                    node[new_key] = node.pop(old_key)
            for key, value in node.items():
                if isinstance(value, str):
                    replaced = value
                    for old, new in cls._DIALOGUE_PLACEHOLDER_MIGRATIONS:
                        replaced = replaced.replace(old, new)
                    if replaced != value:
                        node[key] = replaced
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if not isinstance(item, str):
                            continue
                        replaced = item
                        for old, new in cls._DIALOGUE_PLACEHOLDER_MIGRATIONS:
                            replaced = replaced.replace(old, new)
                        if replaced != item:
                            value[i] = replaced
                elif isinstance(value, dict):
                    stack.append(value)

    def _normalize_pet_settings(self):
        self.data.pop("drag_physics", None)  # 拖动物理功能已移除，清掉旧配置键
        dialogue_mode = str(self.data.get("dialogue_mode") or "legacy").lower()
        self.data["dialogue_mode"] = dialogue_mode if dialogue_mode in {"legacy", "whale_maid", "custom"} else "legacy"
        raw_phrases = self.data.get("dialogue_phrases")
        if isinstance(raw_phrases, dict) and ("global" in raw_phrases or "agents" in raw_phrases):
            # 统一预设双层 {global: events, agents: {agent_key: events}}
            preset = {}
            global_events = raw_phrases.get("global")
            preset["global"] = self._clean_phrase_events(global_events)
            agents = {}
            raw_agents = raw_phrases.get("agents")
            if isinstance(raw_agents, dict):
                for agent_key, events in raw_agents.items():
                    agent_cleaned = self._clean_phrase_events(events)
                    if str(agent_key).strip() and agent_cleaned:
                        agents[str(agent_key)] = agent_cleaned
            preset["agents"] = agents
            self.data["dialogue_phrases"] = preset
        else:
            # 旧单层 {event: [...]}：视为 global
            self.data["dialogue_phrases"] = self._clean_phrase_events(raw_phrases)
        # 旧占位符迁移（{source}→{failureType} 等；新配置幂等 no-op）
        self._migrate_dialogue_phrase_fields(self.data.get("dialogue_phrases"))
        _normalize_pet_profile_values(self.data)
        self.data["animation_gap_seconds"] = _float_or_default(self.data.get("animation_gap_seconds"), DEFAULT_ANIMATION_GAP_SECONDS, 0.0, 3600.0)
        self.data["cursor_hidden_passthrough"] = _bool_or_default(self.data.get("cursor_hidden_passthrough"), True)
        self.data["allow_cross_screen"] = _bool_or_default(self.data.get("allow_cross_screen"), False)
        self.data["show_dock_icon"] = bool(self.data.get("show_dock_icon", True))
        self.data["context_menu_layout"] = _clean_menu_layout_override(self.data.get("context_menu_layout"))
        self.data["context_menu_appearance"] = _clean_menu_appearance(self.data.get("context_menu_appearance"))
        # 动画菜单连播（#221）：布尔走 _bool_or_default（防手写 "false" 被当开）
        self.data["anim_menu_stay_open"] = _bool_or_default(
            self.data.get("anim_menu_stay_open"), False)
        self.data["character_profiles"] = _clean_character_profiles(self.data.get("character_profiles"))
        for prefix in ("chat_background", "modern_chat_background"):
            opacity_key = f"{prefix}_opacity"
            fill_key = f"{prefix}_fill"
            # 不透明度 [10,100]：整数键统一走 _float_or_default 再取整——手写
            # int() 只接 TypeError/ValueError，Infinity/NaN 抛 OverflowError（启动崩）。
            self.data[opacity_key] = int(_float_or_default(
                self.data.get(opacity_key), 100.0, 10.0, 100.0))
            fill = str(self.data.get(fill_key, "cover") or "cover")
            self.data[fill_key] = fill if fill in {"cover", "contain", "stretch"} else "cover"
        self.data["modern_chat_card_opacity"] = int(_float_or_default(
            self.data.get("modern_chat_card_opacity"), 84.0, 10.0, 100.0))

        self.data["slingshot_enabled"] = bool(self.data.get("slingshot_enabled", True))
        # 闲置降帧（性能调研 §4.3）：开关默认关（灰度）；阈值夹到 [1, 3600] 秒
        # 终审 P1-3：必须用 _bool_or_default——bool("false") is True，字符串
        # 布尔（外部手改配置/旧版导出）会被误开；与其它布尔键同规。
        self.data["idle_low_fps_enabled"] = _bool_or_default(self.data.get("idle_low_fps_enabled"), False)
        self.data["idle_low_fps_threshold"] = _float_or_default(self.data.get("idle_low_fps_threshold"), 30.0, 1.0, 3600.0)
        # 上游 #60 系统通知开关：同规防字符串布尔误开（bool("false") is True）。
        self.data["system_notifications_enabled"] = _bool_or_default(self.data.get("system_notifications_enabled"), True)
        # 免打扰（issue #208）：默认时长归一到一个合法档位（手改成 7 分钟不该让
        # 菜单里一个勾选项都对不上）；布尔键同族同规，防手改字符串布尔误开。
        self.data["quiet_minutes_default"] = normalize_quiet_minutes(
            self.data.get("quiet_minutes_default", DEFAULT_QUIET_MINUTES)
        )
        self.data["quiet_also_on_fullscreen"] = _bool_or_default(
            self.data.get("quiet_also_on_fullscreen"), DEFAULT_QUIET_ALSO_ON_FULLSCREEN
        )
        # 黄金回旋 / 边缘探头：与其它布尔键同规，防手改字符串布尔误开。
        self.data["golden_spin_on_click"] = _bool_or_default(self.data.get("golden_spin_on_click"), False)
        self.data["golden_spin_direct"] = _bool_or_default(self.data.get("golden_spin_direct"), False)
        self.data["edge_probe_enabled"] = _bool_or_default(self.data.get("edge_probe_enabled"), False)
        # 「回收内存」(#210)：布尔走 _bool_or_default 防字符串布尔误开；阈值夹到
        # [0, 8192]（上限与 pet/memory_trim.py::MIN_SIZE_MB_MAX 同值，由
        # test_memory_trim 的漂移断言钉住）——脏值直接打死 worker 线程不可接受，
        # 负值则会退化成"连 0 字节进程都要折腾"。
        self.data["mem_skip_foreground"] = _bool_or_default(self.data.get("mem_skip_foreground"), True)
        self.data["mem_min_size_mb"] = _float_or_default(self.data.get("mem_min_size_mb"), 50.0, 0.0, 8192.0)
        prewarm = str(self.data.get("media_prewarm", "balanced") or "balanced").strip().lower()
        self.data["media_prewarm"] = prewarm if prewarm in {"full", "balanced", "minimal"} else "balanced"
        # 批10-A3：默认 32→8（预测式预热使能）；32 是批9 引入仅一天的旧默认，
        # 视为遗留值一并迁移（想调大可设 16/64 等非 32 值，32 本身被保留为迁移哨兵）。
        _ffb = _float_or_default(self.data.get("first_frame_cache_max_mb"), 8, 4, 64)
        self.data["first_frame_cache_max_mb"] = 8 if int(_ffb) == 32 else int(_ffb)
        # 批10-A1 预测式预热提前量：夹到 [200, 600] 毫秒（默认 350）。
        self.data["predict_prewarm_lead_ms"] = int(_float_or_default(self.data.get("predict_prewarm_lead_ms"), 350, 200, 600))
        # 批5.3 共享解码链开关：同规防字符串布尔误开（默认开）。
        self.data["experimental_shared_decode"] = _bool_or_default(self.data.get("experimental_shared_decode"), True)
        # 设置页进程隔离：同规防字符串布尔误开；默认开（关掉 = 回退进程内设置页）。
        self.data["settings_process_isolation"] = _bool_or_default(self.data.get("settings_process_isolation"), True)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def character_alias(self, character_id: str) -> str:
        """用户自定义的角色显示名；未设置返回空串。"""
        aliases = self.data.get("character_aliases")
        if isinstance(aliases, dict):
            return str(aliases.get(character_id, "") or "").strip()
        return ""

    def set_character_alias(self, character_id: str, name: str) -> None:
        """设置角色显示名别名（最长 24 字符）；空名表示恢复默认。"""
        aliases = self.data.setdefault("character_aliases", {})
        if not isinstance(aliases, dict):
            aliases = {}
            self.data["character_aliases"] = aliases
        name = (name or "").strip()[:24]
        if name:
            aliases[character_id] = name
        else:
            aliases.pop(character_id, None)
        self.save()

    def character_display_name(self, character_id: str) -> str:
        """角色显示名：用户别名优先，未设置回退目录显示名（manifest name/角色 id）。

        展示给用户或注入 AI 提示（如识屏自我识别）的场合一律走本方法，
        不要直取 catalog.character_display_name 而绕过用户重命名。
        """
        return self.character_alias(character_id) or catalog.character_display_name(character_id)

    def character_profile(self, character_id: str) -> dict:
        """返回角色档案；不存在时返回空档案。"""
        profiles = self.data.get("character_profiles")
        if isinstance(profiles, dict):
            profile = profiles.get(str(character_id))
            if isinstance(profile, dict):
                return profile
        return {}

    def click_talk_bindings(self, character_id: str) -> dict:
        """返回某角色的点击动画台词绑定：{动画id: [台词, ...]}。"""
        profile = self.character_profile(character_id)
        bindings = profile.get("click_talk_bindings")
        return bindings if isinstance(bindings, dict) else {}

    def click_talk_texts_for(self, character_id: str, action_id: str) -> list[str]:
        """返回某点击动画绑定的台词；未绑定返回空列表。"""
        bindings = self.click_talk_bindings(character_id)
        texts = bindings.get(str(action_id))
        return texts if isinstance(texts, list) else []

    def set_click_talk_bindings(self, character_id: str, bindings: dict) -> None:
        """保存某角色的点击动画台词绑定并立即落盘。"""
        profiles = self.data.setdefault("character_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
            self.data["character_profiles"] = profiles
        profile = profiles.setdefault(str(character_id), {})
        if not isinstance(profile, dict):
            profile = {}
            profiles[str(character_id)] = profile
        profile["click_talk_bindings"] = bindings
        self.data["character_profiles"] = _clean_character_profiles(profiles)
        self.save()

    def set(self, key, value):
        self.data[key] = value
        before_normalize = copy.deepcopy(self.data)
        if key in {
            "playback_speed",
            "animation_gap_seconds",
            "self_talk_enabled",
            "self_talk_min_interval",
            "self_talk_max_interval",
            "self_talk_texts",
            "self_talk_duration_seconds",
            "self_talk_image_dir",
            "self_talk_image_scale",
            "self_talk_image_chance",
            "bubble_text_scale",
            "self_talk_bubble_style",
            "context_menu_appearance",
            "context_menu_layout",
            "anim_menu_stay_open",
            "click_sound_enabled",
            "click_sound_pack",
            "click_sound_volume",
            "slingshot_enabled",
            "throw_strength",
            "drop_gravity",
            "idle_low_fps_enabled",
            "idle_low_fps_threshold",
            "media_prewarm",
            "first_frame_cache_max_mb",
            "predict_prewarm_lead_ms",
            "ffmpeg_recycle_minutes",
            "quiet_minutes_default",
            "quiet_also_on_fullscreen",
            "mem_skip_foreground",
            "mem_min_size_mb",
            "character_profiles",
        }:
            self._normalize_pet_settings()
            # 本次显式赋的键是**整值替换**，不是"用户删了里面的子键"：把它的规范化
            # 结果放回 local 再比对，否则嵌套键的部分更新会被当成删键。
            # 这类部分 dict 会被当成删键，规范化刚补上的默认子键被整片摘掉（内存态
            # 丢 title/hint…，写盘即固化）。其它键的删除语义照旧保留。
            staged = dict(before_normalize)
            staged[key] = self.data.get(key)
            _keep_config_deletions(self._save_baseline, staged, self.data)

    def chat_settings(self):
        from .chat.models import ChatSettings

        return ChatSettings.from_dict(self.data.get("chat", {}))

    def set_chat_settings(self, settings):
        self.data["chat"] = settings.to_dict(include_secrets=True)

    def resolve_api_key(self, provider):
        from .chat.models import SecretStore

        return SecretStore().get(provider.api_key_ref) or provider.api_key

    def _redacted_data(self) -> dict:
        """深拷贝待写盘数据，并剔除 chat.providers 下的明文 API Key。

        keyring 不可用时（SecretStore.set 返回 False）设置对话框会把 key 放进
        provider.api_key / vision_api_key 供本次运行使用；写盘时必须剔除，
        避免明文落盘——key 只保留在内存（self.data），重启需重输。
        """
        write_data = copy.deepcopy(self.data)
        chat = write_data.get("chat")
        if isinstance(chat, dict):
            providers = chat.get("providers")
            if isinstance(providers, dict):
                for provider in providers.values():
                    if isinstance(provider, dict):
                        provider.pop("api_key", None)
                        provider.pop("vision_api_key", None)
            web_search = chat.get("web_search")
            if isinstance(web_search, dict):
                web_search.pop("api_key", None)
        return write_data

    def _read_reset_generations(self) -> dict:
        from . import config_write_lock as cwl

        path = self.dir / ".config-reset-generations.json"
        data, status = cwl.read_json_dict(path)
        if status == "missing":
            return {}
        if (status != "ok" or type(data.get("version")) is not int
                or data["version"] not in (1, 2)
                or not isinstance(data.get("generations"), dict)):
            raise cwl.JsonStateError(f"配置 reset 代次不可信: {path}")
        result = {}
        for name, value in data["generations"].items():
            if (not isinstance(name, str) or not name.startswith("config")
                    or not name.endswith(".json") or "/" in name or "\\" in name):
                raise cwl.JsonStateError(f"配置 reset 文件名不可信: {path}")
            if data["version"] == 1:
                if not (isinstance(value, str) or type(value) is int and value >= 0):
                    raise cwl.JsonStateError(f"配置 reset 旧代次不可信: {path}")
                result[name] = {"token": str(value), "pending": False}
            elif (isinstance(value, dict) and set(value) == {"token", "pending"}
                  and isinstance(value["token"], str) and value["token"]
                  and type(value["pending"]) is bool):
                result[name] = dict(value)
            else:
                raise cwl.JsonStateError(f"配置 reset 状态不可信: {path}")
        return result

    def _read_reset_generation(self) -> str:
        from . import config_write_lock as cwl

        state = self._read_reset_generations().get(self.path.name)
        if state and state["pending"]:
            raise cwl.JsonStateError("配置 reset 尚未完成，拒绝普通读取/保存")
        return state["token"] if state else ""

    def _write_save_payload(self, path: Path, payload: dict) -> None:
        temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            atomic_replace_with_retry(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def save(self) -> bool:
        """目录锁内重读并递归合并真实变更；失败保留草稿与成功基线。

        dict 按叶键合并，list/标量整值提交，同键最后成功提交者优先。
        reset 是显式全量写，先推进小型代次侧车阻挡旧快照；第二步失败
        返回 False（可能已推进代次），重试 reset 可收敛，不声称跨文件事务。
        """
        from . import config_write_lock as cwl

        if self.instance_id.startswith("slot-"):
            logging.warning("raw slot Config 禁止整表写；使用 SlotRoutedConfig: %s", self.path)
            return False
        original = copy.deepcopy(self.data)
        try:
            self._normalize_pet_settings()
            if not self._full_reset:
                _keep_config_deletions(self._save_baseline, original, self.data)
            with cwl.config_write_lock(self.dir):
                latest, status = cwl.read_json_dict(self.path)
                if status not in ("ok", "missing"):
                    raise cwl.JsonStateError(f"拒绝覆盖不可信配置（{status}）: {self.path}")
                # 盘上还残留的退役键在这里按**同一条**读入即弃规则清掉（迁移实现只有
                # 一份，避免"又一个消费方读它"）：合并会以盘上那份为底，不清就写回。
                if isinstance(latest, dict):
                    self._migrate_menu_template_config(latest)
                generation = self._reset_generation
                if not self._full_reset:
                    generation = self._read_reset_generation()
                    if generation != (self._reset_generation or ""):
                        raise cwl.JsonStateError("配置快照早于 reset，需 reload 后重新编辑")
                local = self._redacted_data()
                if self._full_reset or status == "missing":
                    payload = local
                else:
                    previous = self.data
                    self.data = self._save_baseline
                    try:
                        baseline = self._redacted_data()
                    finally:
                        self.data = previous
                    payload = _merge_config_changes(baseline, local, latest)
                if not self.instance_id:
                    from . import pet_profiles

                    target = pet_profiles.slot_profile_path(self.dir, 0)
                    if not target.exists() and not self._full_reset:
                        migration = pet_profiles.migrate_slot0_profile(self.dir)
                        if not migration.ok:
                            raise cwl.JsonStateError(str(migration))
                        if not target.exists():
                            values = normalize_pet_profile_snapshot(original)
                            result = pet_profiles.write_profile_settings(
                                self.dir, 0, {key: values[key] for key in pet_profiles.PER_PET_KEYS})
                            if not result.ok:
                                raise cwl.JsonStateError(str(result))
                    for key in pet_profiles.PER_PET_KEYS | pet_profiles.SLOT_LOCAL_KEYS:
                        payload.pop(key, None)
                payload["version"] = 4
                for retired in ("chat_api_key", "chat_enabled", "chat_system_prompt",
                                "chat_api_url", "chat_model", "click_sound_path",
                                "decode_broker_enabled"):
                    payload.pop(retired, None)
                previous = self.data
                self.data = payload
                try:
                    payload = self._redacted_data()
                finally:
                    self.data = previous
                if self._full_reset:
                    import uuid

                    generations = self._read_reset_generations()
                    generation = uuid.uuid4().hex
                    generations[self.path.name] = {"token": generation, "pending": True}
                    cwl.atomic_write_json(
                        self.dir / ".config-reset-generations.json",
                        {"version": 2, "generations": generations})
                self._write_save_payload(self.path, payload)
                if self._full_reset:
                    generations[self.path.name]["pending"] = False
                    cwl.atomic_write_json(
                        self.dir / ".config-reset-generations.json",
                        {"version": 2, "generations": generations})
                self._save_baseline = copy.deepcopy(self.data)
                self._reset_generation = generation
        except (OSError, ValueError, TypeError, cwl.ConfigWriteError) as exc:
            self.data = original
            logging.warning("保存配置失败: %s (%s)", self.path, exc)
            return False
        return True
