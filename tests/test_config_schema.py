# -*- coding: utf-8 -*-
"""Config 键白名单收口测试（批3 子项3）。

pet/config.py 里 __init__ 的默认值 dict（约 498-566 行）与 reload() 的白名单
元组（约 656-691 行）是两份独立维护的键列表。本测试把现状文档化并加护栏：

实测两集合**不一致**（现状文档化，不修产品代码）：
- 默认值 dict 共 80 键；reload 白名单共 75 键。
- 差异 = 默认值多出 4 键：{version, proactive_screen, agent_link, chat}。
  这 4 键在 reload() 里走专门路径（version 末尾强制回写 4；
  proactive_screen / agent_link / chat 分别经 _merge_*_data 合并），
  不属于普通白名单键，故不并入白名单元组。

护栏语义（新增键漏登记立即红）：
- 默认值键 - 特例键 ⊆ 真实白名单（默认值加键而白名单漏登记 → 失败）；
- 真实白名单 ⊆ 默认值键（白名单出现孤儿键 → 失败）；
- 两集合与显式快照一致（现状文档化，改键必须同步改快照）。
"""

from __future__ import annotations

import inspect
import json
import re

import pytest

from pet import config as config_mod
from pet.config import Config

# reload() 白名单键集合现状快照（与 pet/config.py reload() 的
# "for key in (...)" 元组一致；任何增删必须同步更新本快照）。
RELOAD_WHITELIST_SNAPSHOT = frozenset(
    {
        "agent_cost_enabled",
        "allow_cross_screen",
        "anim_menu_stay_open",
        "animation_gap_seconds",
        "auto_hide_fullscreen",
        "autostart_wanted",
        "balance_refresh_minutes",
        "balance_tier_color_enabled",
        "balance_tier_label_idle",
        "balance_tier_label_peak",
        "balance_tier_labels_mode",
        "character",
        "character_aliases",
        "character_profiles",
        "chat_always_on_top",
        "chat_background",
        "chat_background_fill",
        "chat_background_opacity",
        "chat_bg_crops",
        "chat_follow_pet",
        "chat_reply_voice_enabled",
        "chat_ui_style",
        "click_show_balance",
        "click_show_self_talk",
        "click_sound_enabled",
        "click_sound_pack",
        "click_sound_volume",
        "collision_enabled",
        "collision_friction",
        "collision_impulse_cap",
        "collision_mass_scale",
        "collision_restitution",
        "collision_sound_enabled",
        "collision_sound_volume",
        "context_menu_appearance",
        "context_menu_layout",
        "cursor_hidden_passthrough",
        "dialogue_last_scope",
        "dialogue_mode",
        "dialogue_phrases",
        "divination_enabled",
        "divination_hint",
        "divination_speak",
        "divination_state",
        "drag_physics",
        "drop_gravity",
        "edge_probe_enabled",
        "experimental_shared_decode",
        "facing",
        "ffmpeg_recycle_minutes",
        "first_frame_cache_max_mb",
        "game_fps_process",
        "game_fps_target_mode",
        "golden_spin_direct",
        "golden_spin_on_click",
        # 全局快捷键（进程级；空串 = 不绑）
        "hotkey_open_chat",
        "hotkey_look_screen",
        "hotkey_screen_capture",
        "harness_autostart",
        "harness_launch_target",
        "idle_low_fps_enabled",
        "idle_low_fps_threshold",
        "lock_position",
        "media_prewarm",
        "mem_min_size_mb",
        "mem_skip_foreground",
        "menu_easter_egg",
        "modern_chat_background",
        "modern_chat_background_fill",
        "modern_chat_background_opacity",
        "modern_chat_card_opacity",
        "mouse_through",
        "music_browser_media_enabled",
        "foobar_lyrics_enabled",
        "foobar_title_format",
        "music_lyric_cache_limit",
        "music_lyric_enabled",
        "music_lyric_lead_seconds",
        "music_player_paths",
        "music_sing_enabled",
        "music_sing_grace_seconds",
        "network_info_menu_enabled",
        "network_probe_interval_seconds",
        "no_move",
        "on_top",
        "pet_opacity",
        "playback_speed",
        "pnpm_bin",
        "predict_prewarm_lead_ms",
        "quick_launch_apps",
        "quiet_also_on_fullscreen",
        "quiet_minutes_default",
        "bubble_text_scale",
        "rx",
        "ry",
        "scale",
        "screen_name",
        "self_talk_bubble_style",
        "self_talk_duration_seconds",
        "self_talk_enabled",
        "self_talk_image_chance",
        "self_talk_image_dir",
        "self_talk_image_scale",
        "self_talk_max_interval",
        "self_talk_min_interval",
        "self_talk_speak_enabled",
        "self_talk_texts",
        "self_talk_voice_precache_enabled",
        "settings_process_isolation",
        "shift_drag",
        "show_dock_icon",
        "slingshot_enabled",
        "spawn_inherit_size",
        "spawn_scale",
        "stream_capture_mode",
        "system_notifications_enabled",
        "throw_strength",
        "todo_reminder_enabled",
        "todo_reminder_lead_minutes",
        "todo_reminder_speak",
        "user_customized",
        "voice_chime_custom_quotes_en",
        "voice_chime_custom_quotes_zh",
        "voice_chime_custom_times",
        "voice_chime_doubao_pitch",
        "voice_chime_doubao_speaker",
        "voice_chime_enabled",
        "voice_chime_mimo_model",
        "voice_chime_mimo_style",
        "voice_chime_mimo_voice",
        "voice_chime_pitch",
        "voice_chime_rate",
        "voice_chime_sapi_rate",
        "voice_chime_sapi_voice",
        "voice_chime_schedule",
        "voice_chime_show_bubble",
        "voice_chime_show_quote",
        "voice_chime_tts_backend",
        "voice_chime_tts_fallback",
        "festival_birthday",
        "festival_custom_quotes_cn",
        "festival_custom_quotes_west",
        "festival_reminder_animation",
        "festival_reminder_cn",
        "festival_reminder_count",
        "festival_reminder_enabled",
        "festival_reminder_mode",
        "festival_reminder_show_quote",
        "festival_reminder_solar_terms",
        "festival_reminder_speak",
        "festival_reminder_times",
        "festival_reminder_west",
        "voice_chime_custom_quotes_en",
        "voice_chime_custom_quotes_zh",
        "voice_chime_voice",
        "voice_chime_volume",
        "weather_city",
        "weather_city_codes",
        "weather_city_list",
        "weather_enabled",
    }
)

# 默认值 dict 里不走普通白名单、由 reload() 专门路径处理的键（现状文档化）。
# 2026-09-19 加入 file_interpret（拖文件解读，嵌套 dict 走 _merge_ 专门路径）。
SPECIAL_CASED_KEYS = frozenset({"version", "proactive_screen", "agent_link", "chat", "file_interpret"})

# 默认值 dict 键集合现状快照 = 白名单 ∪ 特例键。
# 2026-09-17 加入 music_player_paths（交付前审查 P1-3 登记）。
# 2026-09-22 加入点击台词朗读 / 台词本地语音预缓存 / 自言自语配图概率 3 键
# （self_talk_speak_enabled、self_talk_voice_precache_enabled、self_talk_image_chance）。
# 2026-10-07 加入音乐播放器来源 2 键（foobar_lyrics_enabled / foobar_title_format）。
# 2026-10-07 深夜批次再加：天气 3（weather_enabled/weather_city/weather_city_list）、
# 网络 3（island_network_enabled/network_probe_interval_seconds/network_info_menu_enabled）、
# 免打扰 2（quiet_minutes_default/quiet_also_on_fullscreen）、回收内存 2
# （mem_skip_foreground/mem_min_size_mb）、动画菜单 1（anim_menu_stay_open）。
# 后实测（2026-10-07 夜间整合后复测）：白名单字面量 139 + 特例 5 = 144。
# 2026-10-07 P1 Slice C 加灵动岛指标 1（island_metrics，列表序=优先级），白名单 140。
# 2026-10-11 加游戏帧率 2（game_fps_target_mode 枚举 / game_fps_process 纯 exe 名，
# 都是**全局**键：岛与采集链路读主配置），白名单 142。
# 2026-10-13 加语音报时合成后端 9 键（tts_backend / tts_fallback / mimo_model /
# mimo_voice / mimo_style / sapi_voice / sapi_rate / doubao_speaker / doubao_pitch，
# 随 provider 注册表一起进来），白名单 151。
# 2026-10-14 补登记节日提醒 2 键（festival_reminder_animation / festival_birthday）：
# 它们随「节日动画 + 我的生日」一起进来时**漏登在 config.py 的默认 dict 与白名单里**
# （设置页有行、config 没键），于是本轮把它们渲染出来后被
# `test_settings_default_marks` 的「冻结集」抓到——补齐后白名单 153。
# 2026-10-18 加待办语音播报 1 键（todo_reminder_speak，默认 False：复用语音报时的
# 音频通道，不新增语速/音色/音量键），白名单 154。
# 2026-10-20 加助手回复朗读 1 键（chat_reply_voice_enabled，默认 False：同样复用
# 语音报时的音频通道，只念对话不念歌词），白名单 155。
DEFAULTS_SNAPSHOT = RELOAD_WHITELIST_SNAPSHOT | SPECIAL_CASED_KEYS


def _actual_reload_whitelist() -> frozenset:
    """测试探针：从 config.py 源码提取 reload() 白名单元组的真实键集合。

    白名单是 reload() 方法内的字面量，运行期无法经实例访问，故用
    inspect.getsource + 正则提取。格式变更导致提取失败时以明确信息
    失败（提示同步更新本探针），而不是静默放行。
    """
    reload_src = inspect.getsource(config_mod.Config.reload)
    m = re.search(r"for key in \((.*?)\):\n", reload_src, re.S)
    assert m, "从 reload() 源码找不到白名单元组，请检查 config.py 的白名单格式"
    return frozenset(re.findall(r'"([a-zA-Z0-9_]+)"', m.group(1)))


def _actual_defaults_keys(tmp_path) -> frozenset:
    """运行期默认值键集合：无配置文件时 Config.data 即默认值 dict 的键。"""
    cfg = Config(base=tmp_path)
    return frozenset(cfg.data)






def test_every_defaults_key_is_whitelisted_or_special_cased(tmp_path):
    """核心护栏：默认值 dict 新增键必须登记白名单（或列入特例集），否则立即红。"""
    defaults = _actual_defaults_keys(tmp_path)
    whitelist = _actual_reload_whitelist()
    assert defaults - SPECIAL_CASED_KEYS <= whitelist


def test_whitelist_has_no_orphan_keys(tmp_path):
    """白名单键都必须存在于默认值 dict（无孤儿白名单键）。"""
    defaults = _actual_defaults_keys(tmp_path)
    assert _actual_reload_whitelist() <= defaults




# ---------------------------------------------------------------- #129 脏值归一化
# 音乐关联 / 消费统计这 5 个键此前只在默认值 dict 与 reload 白名单里登记，
# 没进 _normalize_pet_settings：数值键的脏值会让设置页构造直接抛
# ValueError（float('abc') 打死整个设置页），字符串布尔被 bool() 误开
# （bool('false') is True，歌词功能自己打开）。下面固定这两条修复。

def _dirty_music_cost_config(tmp_path):
    """把 5 个键写成脏值落盘，再走真实加载路径（reload + _normalize_pet_settings）。"""
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 4,
                "music_lyric_enabled": "false",
                "music_lyric_lead_seconds": "abc",
                "music_lyric_cache_limit": -5,
                "music_sing_grace_seconds": "oops",
                "agent_cost_enabled": "yes",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return Config(base=tmp_path)






# ------------------------------------------------- 「回收内存」(#210) 两个键
def _memory_trim_config(tmp_path, raw: dict) -> Config:
    """把 mem_* 键写成脏值落盘，再走真实加载路径（reload + _normalize_pet_settings）。"""
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"version": 4, **raw}, ensure_ascii=False), encoding="utf-8",
    )
    return Config(base=tmp_path)


# ------------------------------------------------- 动画菜单连播（#221）
def _anim_menu_config(tmp_path, raw) -> Config:
    """把 ``anim_menu_stay_open`` 写成脏值落盘，再走真实加载路径。"""
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"version": 4, "anim_menu_stay_open": raw}, ensure_ascii=False),
        encoding="utf-8",
    )
    return Config(base=tmp_path)


def test_anim_menu_stay_open_defaults_to_closing_after_action(tmp_path):
    """默认 False = 点一个动作就收起菜单（#221 的产品决策）。

    该键是**菜单行为类**偏好：不进设置页（与 mem_* 同口径），用户手改
    config.json 才切到连播。
    """
    assert Config(base=tmp_path).data["anim_menu_stay_open"] is False


@pytest.mark.parametrize("raw,expected", [
    ("false", False), ("no", False), ("off", False),
    ("true", True), ("yes", True), ("on", True),
    # 非字符串布尔不参与解析（同族布尔键同规）：回落默认 False
    (1, False), (0, False), (None, False), ("随便", False),
])
def test_dirty_anim_menu_stay_open_is_not_truthy_by_string(tmp_path, raw, expected):
    """bool("false") is True——字符串布尔必须按字面语义归一。"""
    cfg = _anim_menu_config(tmp_path / f"raw-{raw}", raw)
    assert cfg.data["anim_menu_stay_open"] is expected


def test_set_and_reload_keep_anim_menu_stay_open(tmp_path):
    """set() 路径归一，且落盘 → 重启加载不被默认值冲掉。"""
    cfg = Config(base=tmp_path)
    cfg.set("anim_menu_stay_open", "on")
    assert cfg.data["anim_menu_stay_open"] is True
    assert cfg.save() is True
    assert Config(base=tmp_path).data["anim_menu_stay_open"] is True


# ------------------------------------------------- 天气四键（issue #209）
def _dirty_weather_config(tmp_path):
    """把天气键写成脏值落盘，再走真实加载路径（reload + _normalize_pet_settings）。"""
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 4,
                "weather_enabled": "false",
                "weather_city": "  鹿城区  ",
                "weather_city_list": ["北京", "北京", " 鹿城区 ", "", 42, "上海"],
                "weather_city_codes": {"鹿城区": " 101210710 ", "北京": "", "": "x"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return Config(base=tmp_path)


def test_memory_trim_keys_have_documented_defaults(tmp_path):
    """默认值：跳过前台（保护用户正在用的窗口）、阈值 50MB。

    两个键都是"菜单动作类功能"的配置面，**不进设置页**——只能手改 config.json
    或由菜单路径读取，默认值即推荐值。
    """
    cfg = Config(base=tmp_path)

    assert cfg.data["mem_skip_foreground"] is True
    assert cfg.data["mem_min_size_mb"] == 50.0


def test_dirty_memory_trim_keys_are_normalized(tmp_path):
    """脏值不得打死 worker 线程：字符串布尔不许被 bool() 误开，阈值必须落区间。

    阈值下限 0 有语义（0 = 连 0 字节进程都纳入），上限与
    ``pet/memory_trim.py::MIN_SIZE_MB_MAX`` 同值（漂移由 test_memory_trim 钉住）。
    """
    from pet import memory_trim

    assert _memory_trim_config(
        tmp_path / "str-bool", {"mem_skip_foreground": "false"},
    ).data["mem_skip_foreground"] is False
    assert _memory_trim_config(
        tmp_path / "bad-num", {"mem_min_size_mb": "abc"},
    ).data["mem_min_size_mb"] == memory_trim.DEFAULT_MIN_SIZE_MB
    assert _memory_trim_config(
        tmp_path / "negative", {"mem_min_size_mb": -5},
    ).data["mem_min_size_mb"] == 0.0
    assert _memory_trim_config(
        tmp_path / "huge", {"mem_min_size_mb": 10 ** 9},
    ).data["mem_min_size_mb"] == memory_trim.MIN_SIZE_MB_MAX


def test_set_normalizes_memory_trim_keys(tmp_path):
    cfg = Config(base=tmp_path)

    cfg.set("mem_min_size_mb", "abc")
    assert cfg.data["mem_min_size_mb"] == 50.0
    cfg.set("mem_skip_foreground", "false")
    assert cfg.data["mem_skip_foreground"] is False




# ------------------------------------------- 网络信息 / 灵动岛指标（#172 + Slice C）
def _dirty_network_config(tmp_path, raw: dict) -> Config:
    """把网络信息诸键写成脏值落盘，再走真实加载路径（reload + 归一化）。"""
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": 4}
    payload.update(raw)
    (cfg_dir / "config.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return Config(base=tmp_path)












# --------------------------------------- M1：城市名归一化幂等、不被别的设置改坏
def test_repeated_normalization_never_erodes_the_city_name(tmp_path):
    """保存任何设置都会跑整表归一化：城市名必须一次定形，之后一直不变。

    回归的正是终审 M1 的实测：``景德镇市`` → ``景德镇`` → ``景德``（每次保存
    别的设置都继续剥一层），以及「新乡」「景德镇」被当后缀裁掉。
    """
    cfg = Config(base=tmp_path)
    cfg.set("weather_city", "景德镇市")
    cfg.set("weather_city_list", ["新乡", "景德镇", "鹿城区"])
    assert cfg.data["weather_city"] == "景德镇市"
    assert cfg.data["weather_city_list"] == ["新乡", "景德镇", "鹿城区"]

    for _ in range(5):
        cfg._normalize_pet_settings()
        assert cfg.data["weather_city"] == "景德镇市"
        assert cfg.data["weather_city_list"] == ["新乡", "景德镇", "鹿城区"]


def test_setting_an_unrelated_key_leaves_the_weather_city_alone(tmp_path):
    """改一个跟天气无关的设置（会触发整表归一化）不得动城市名。"""
    cfg = Config(base=tmp_path)
    cfg.set("weather_city", "景德镇市")
    cfg.set("weather_city_codes", {"景德镇市": "101240801"})

    cfg.set("pet_opacity", 90)
    cfg.set("bubble_text_scale", 120)

    assert cfg.data["weather_city"] == "景德镇市"
    assert cfg.data["weather_city_codes"] == {"景德镇市": "101240801"}



# ------------------------------------------------- 自启目标（harness_launch_target）
def _launch_target_config(tmp_path, raw: str) -> Config:
    """把 ``harness_launch_target`` 写成指定原始值落盘，再走真实加载路径。"""
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"version": 4, "harness_launch_target": raw}, ensure_ascii=False),
        encoding="utf-8",
    )
    return Config(base=tmp_path)




def test_set_harness_launch_target_keeps_service(tmp_path):
    """set() 路径同样不吞 service（设置页保存走 set → save）。"""
    cfg = Config(base=tmp_path)
    cfg.set("harness_launch_target", "service")
    assert cfg.data["harness_launch_target"] == "service"




# ---------------------------------------------------------------- 交付前审查 P1-3 / P2-a / P2-b


def _write_config(tmp_path, payload: dict) -> None:
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
























# ------------------------------------------- 退役键的静默迁移（2026-10-08）
def test_retired_menu_template_key_is_discarded_silently(tmp_path):
    """旧版菜单退役后，配置里的菜单模板键必须静默丢弃：读入即弃 + 不再写回。

    旧存档（含用户手改的 `"legacy"`）只能表现为"什么都没发生"：不抛异常、
    不回退旧布局、不影响启动；下一次落盘时键从文件里消失。
    """
    cfg = _load_with(tmp_path, context_menu_template="legacy")
    assert "context_menu_template" not in cfg.data
    assert cfg.get("context_menu_template") is None
    assert cfg.get("context_menu_template", "modern") == "modern"


def test_retired_menu_template_key_is_not_written_back(tmp_path):
    """丢弃必须落到盘上：save() 之后 config.json 里不再有这个键。"""
    import json

    cfg = _load_with(tmp_path, context_menu_template="modern")
    assert cfg.save() is True
    payload = json.loads((cfg.dir / "config.json").read_text(encoding="utf-8"))
    assert "context_menu_template" not in payload


def test_retired_menu_template_key_is_dropped_in_slot_config(tmp_path):
    """每个 slot 配置同样丢弃（子肥鱼各有自己那份 config-slot-N.json）。"""
    import json

    slot_dir = tmp_path / "slot"
    (slot_dir / config_mod.APP_DIR_NAME).mkdir(parents=True, exist_ok=True)
    _write_config(slot_dir, {"version": 4, "context_menu_template": "legacy"})
    slot_path = slot_dir / config_mod.APP_DIR_NAME / "config.json"
    slot_path.rename(slot_path.with_name("config-slot-3.json"))
    cfg = Config(base=slot_dir, instance_id="slot-3")
    assert "context_menu_template" not in cfg.data
    assert cfg.get("context_menu_template") is None


# ------------------------------------------------- 脏值家族：合法 JSON 不得阻断启动
#
# 全产品审查 C3（2026-10-08）：三族脏值都能让 ``Config()`` 构造直接抛异常，
# 而启动路径（``pet/app.py`` 的 Config()）与自救入口（``pet/__main__.py`` 的
# 独立设置页同样先构造 Config()）都没有 try —— 一个手改出来的 config.json
# 就能让程序连设置恢复都进不去：
#
# - list / dict 撞 ``x not in {"..."}`` 成员判断 → TypeError: unhashable；
# - ``10**400``（json 合法数字字面量 → Python 大整数）撞 ``float()`` /
#   ``math.isfinite()`` → OverflowError；
# - ``Infinity`` / ``NaN``（Python json.loads 默认接受）撞 ``int()`` → OverflowError。
#
# 下面把这一族**逐键**钉住：构造成功 + 回默认值。探针口径见本文件末尾的
# ``test_dirty_value_scan_covers_every_config_key``（穷举全键 × 全脏值）。

_HUGE = int("9" * 400)


def _load_with(tmp_path, **payload):
    """按真实加载路径读一份脏配置（reload + _normalize_pet_settings）。"""
    payload.setdefault("version", 4)
    _write_config(tmp_path, payload)
    return Config(base=tmp_path)












def test_huge_quiet_minutes_falls_back_to_default(tmp_path):
    """免打扰默认时长：超大整数回默认档（float() 溢出不得冒泡）。"""
    cfg = _load_with(tmp_path, quiet_minutes_default=_HUGE)
    assert cfg.data["quiet_minutes_default"] == config_mod.DEFAULT_QUIET_MINUTES


def test_nonfinite_int_keys_fall_back_to_default(tmp_path):
    """int() 型数值键遇 Infinity/NaN：不得 OverflowError，落在可用区间内。"""
    cases = ((float("inf"), 100, 100), (float("-inf"), 10, 10), (float("nan"), 100, 84))
    for i, (dirty, background, card) in enumerate(cases):
        cfg = _load_with(
            tmp_path / f"opacity{i}",
            chat_background_opacity=dirty,
            modern_chat_background_opacity=dirty,
            modern_chat_card_opacity=dirty,
        )
        assert cfg.data["chat_background_opacity"] == background, f"{dirty!r}"
        assert cfg.data["modern_chat_background_opacity"] == background, f"{dirty!r}"
        assert cfg.data["modern_chat_card_opacity"] == card, f"{dirty!r}"


def test_nonfinite_menu_appearance_int_keys_fall_back(tmp_path):
    """菜单外观的圆角/字号：Infinity/NaN 回可用值（不抛），合法值照常夹取。"""
    cases = (
        (float("inf"), 18, 18),
        (float("-inf"), 6, 10),
        (float("nan"), 12, 13),      # NaN → 默认
        (999, 18, 18),               # 越界数值 → 夹取
    )
    for i, (dirty, radius, font_size) in enumerate(cases):
        cfg = _load_with(
            tmp_path / f"appearance{i}",
            context_menu_appearance={"corner_radius": dirty, "ui_font_size": dirty},
        )
        assert cfg.data["context_menu_appearance"]["corner_radius"] == radius, f"{dirty!r}"
        assert cfg.data["context_menu_appearance"]["ui_font_size"] == font_size, f"{dirty!r}"


def test_nonfinite_version_does_not_break_reload(tmp_path):
    """顶层 version 非有限：reload 的迁移判定不得抛（回 1 = 老配置路径）。"""
    for i, dirty in enumerate((float("inf"), float("-inf"), float("nan"))):
        cfg = _load_with(tmp_path / f"version{i}", version=dirty)
        assert cfg.data["version"] == 4, "归一化后 version 仍必须回写当前版本"


def test_dirty_value_scan_covers_every_config_key(tmp_path):
    """穷举探针：每个配置键 × 每种脏值都必须能构造出 Config（家族护栏）。

    这是"同族残留"的机器判据——新增键只要又走裸 ``x in {...}`` / ``int()`` /
    ``float()`` / ``math.isfinite()``，这里立刻红，并指出是哪个键哪种脏值。
    """
    dirty_values = {
        "list": [1, 2],
        "dict": {"a": 1},
        "huge": _HUGE,
        "nan": float("nan"),
        "inf": float("inf"),
        "neginf": float("-inf"),
        "str": "abc",
        "none": None,
    }
    keys = sorted(Config(base=tmp_path / "seed").data)
    failures: list[str] = []
    for key in keys:
        for label, dirty in dirty_values.items():
            case = tmp_path / f"{key[:40]}-{label}"
            try:
                _load_with(case, **{key: dirty})
            except Exception as exc:  # noqa: BLE001 - 探针要把任何异常都记下来
                failures.append(f"{key}={label}: {type(exc).__name__}: {exc}")
    assert failures == [], "脏值不得阻断 Config() 构造：\n" + "\n".join(failures)
