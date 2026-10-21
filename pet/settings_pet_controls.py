"""Pet-page control builders for the modern settings dialog (host-based).

ModernSettingsDialog retains a thin delegation method of the same name, so
existing callers and test patches keep working unchanged.
"""

from __future__ import annotations

import json
import sys

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import autostart as autostart_mod
from . import catalog
from .config import (
    DEFAULT_CONTEXT_MENU_APPEARANCE,
    DEFAULT_SELF_TALK_BUBBLE_STYLE,
    DEFAULT_SELF_TALK_DURATION_SECONDS,
    DEFAULT_SELF_TALK_IMAGE_CHANCE,
    DEFAULT_SELF_TALK_MAX_INTERVAL,
    DEFAULT_SELF_TALK_MIN_INTERVAL,
    DEFAULT_SELF_TALK_TEXTS,
    _float_or_default,
)
from .context_menus.icons import vector_widget_icon
from .persona_phrases import PUBLIC_DIALOGUE_EVENTS, phrase_keys
from .persona_template import build_persona_template
from .settings_widgets import (
    BrowserDoubleSpinBox,
    BrowserSpinBox,
    ClickSoundPackPicker,
    ColorPicker,
    ModernSelect,
    ResourcePathPicker,
    SettingRow,
    ToggleSwitch,
)
from .speech_bubble import BUBBLE_STYLE_PRESETS


#: 全局键的作用域声明（措辞与设置门禁 2026-10-10 条目同源，规范 §五的原文也是「影响所有桌宠」）。
#:
#: 与 ``ALL_PETS_SCOPE_NOTE`` 分开：那条是**窗口级键**在子宠页的补充说明
#: （"这一行在一窗多宠里作用于整窗"），这条是**全局键**的作用域声明
#: （"改了影响所有桌宠"）。两句话的适用对象不同，不合并成一句。
GLOBAL_SCOPE_NOTE = "（影响所有桌宠）"

#: 子宠设置页对这些键的补充说明（窗口级键：一窗多宠里作用于整窗）。
ALL_PETS_SCOPE_NOTE = "（对所有桌宠生效）"

#: 全局键行里逐字写着的那句范围声明（原本拼在说明末尾）。拆成独立标注时**逐字保留**：
#: 措辞与规范 §五同源，改字就是改语义。
ALL_PETS_SCOPE_SENTENCE = "此设置影响所有桌宠。"

#: 「允许桌宠跨屏」基础文案。全局键、重启级（进程快照）——本行随时可改，但下一次
#: 启动才按新值建窗；关闭态下**屏归属与归属那块屏上的位置**都原样保留（临时承载在
#: 启动那块屏上的几何一个键都不写），所以关掉再开回来，各宠仍回到各自那块屏的
#: 原位置（见 ``overlay_shell._save_child_geometry`` 的分流）。
#:
#: 窗口数按**屏缩放**分流（v4.3.4）：多屏且任一屏 DPR ≠ 1 → 每屏一张合成窗（一张窗
#: 只能有一个 DPR，混合缩放下必有一侧被按错倍率画，issue #307 / #310）；多屏全是
#: 100% → 仍是一张窗铺满整个桌面。所以文案不能写成"永远每屏一张"。
CROSS_SCREEN_HINT = (
    "开启后，桌宠可以被直接拖到任意一块显示器上；默认关闭，重启后生效。"
    "有多块屏且任一块屏的缩放不是 100% 时，每块屏各自有一张合成窗，"
    "桌宠按它所在那块屏的缩放呈现；多块屏的缩放全是 100% 时，仍是一张合成窗铺满整个桌面。"
    "关闭时所有桌宠只留在启动时那块屏，拖不过去；"
    "各宠原来记着的屏与位置不会被清掉，重新开启后仍回到各自那块屏的原位置。"
    + GLOBAL_SCOPE_NOTE
)

#: 作用域标注的接线表：``(行键, 说明末尾那句原文)``——同一句既是"从说明里削掉什么"，
#: 也是"标注显示什么"。行本身照着这张表补标注（见 ``_apply_window_scope_rows``），
#: 因此文案仍然只有说明表一份来源，这里一个字的文案都不新写。
#:
#: - 全部行的说明末尾都逐字带着这句原文（主文件里「开机自启」那一行），
#:   所以削得掉、不用另抄。
GLOBAL_SCOPE_ROWS: tuple[tuple[str, str], ...] = (
    ("autostart", GLOBAL_SCOPE_NOTE),
    ("cross_screen", GLOBAL_SCOPE_NOTE),
)

#: 「省电模式」（idle_low_fps_enabled）文案，按拓扑分流：
#: overlay 下该键唯一作用是关掉后台动画预热（``app.py`` 建库与
#: ``_sync_animation_prewarm``）；可见帧率由素材 clip 自持定时器按素材 fps
#: 驱动，与开关无关；legacy 的 PetWindow 仍按半帧率呈现。
IDLE_LOW_FPS_OVERLAY_HINT = (
    "开启后停止后台动画预热（降低待机占用，首次切换动画可能略慢）。"
    "动画帧率不受影响：闲置时的系统降载自动进行，与本开关无关。"
)
IDLE_LOW_FPS_LEGACY_HINT = (
    "一段时间不操作桌宠时，动画按半帧率呈现（24fps 素材 → 12fps 效果）"
    "并停止后台动画预热，任何交互立即恢复全帧率。"
)


#: overlay 单合成窗下物理上只能整窗生效的窗口级键（一窗多宠）：一套窗旗标
#: （置顶 / 鼠标穿透 / 光标隐藏穿透 / 全屏隐藏）、一个窗口透明度、一份锁位与
#: 拖拽修饰钳制。
OVERLAY_WINDOW_SCOPE_IDS = (
    "on_top",
    "mouse_through",
    "pet_opacity",
    "lock_position",
    "shift_drag",
    "cursor_hidden_passthrough",
    "auto_hide_fullscreen",
)


def _is_overlay_topology() -> bool:
    """拓扑判定（懒 import：设置进程禁止导入重量级模块，见模块 docstring）。"""
    from . import overlay_settings_command

    return overlay_settings_command.is_overlay_topology()


def idle_low_fps_hint() -> str:
    """「省电模式」说明文案（按渲染拓扑分流，同 ``stream_capture_hint``）。"""
    if _is_overlay_topology():
        return IDLE_LOW_FPS_OVERLAY_HINT
    return IDLE_LOW_FPS_LEGACY_HINT


def _apply_window_scope_rows(host) -> None:
    """overlay 一窗多宠：slot 页给窗口级键补「对所有桌宠生效」。

    slot 页写的是自己的 ``config-slot-N.json``，但这些键在单合成窗里作用于整窗
    ——不提示的话用户会以为改的只是那一只。每个 slot 页都加（#271 起主宠页也是
    slot0 页，同口径标注），legacy 不加（每宠独立窗口，键确实只作用于自己）。

    行分散在多个模块构建（互动域的「鼠标穿透」在 ``settings_interaction``），
    故在所有行就位后按 objectName 统一补，与 ``_apply_dialogue_scope_rows`` 同
    一形态；行尚未构建时静默跳过。标注走 ``SettingRow.set_scope_note``：挂在标签那一行的
    右边（不再粘在灰说明末尾，也不独占一行），``accessibleDescription`` 仍是"说明 + 标注"全文。

    同时把**全局键**（``GLOBAL_SCOPE_ROWS``）的同类声明一并拆出来——两者都是
    "改了谁受影响"，同一处置、同一处调用，故合成一个 pass（主文件的行数预算不
    允许再接线一次）。
    """
    for setting_id, note in GLOBAL_SCOPE_ROWS:
        row = host.findChild(SettingRow, f"settingRow_{setting_id}")
        if row is None:
            continue
        if row.scope_note.text() != note:
            row.set_scope_note(note)
    if not getattr(getattr(host, "config", None), "instance_id", None):
        return
    if not _is_overlay_topology():
        return
    for setting_id in OVERLAY_WINDOW_SCOPE_IDS:
        row = host.findChild(SettingRow, f"settingRow_{setting_id}")
        if row is None or row.scope_note.text() == ALL_PETS_SCOPE_NOTE:
            continue
        row.set_scope_note(ALL_PETS_SCOPE_NOTE)


def build_pet_controls(host) -> None:
    from .modern_settings_dialog import dialogue_params_hint
    host.scale_combo = ModernSelect(host, width=132)
    current_scale = float(host.config.get("scale", catalog.DEFAULT_SCALE))
    scales = list(catalog.SCALE_STEPS)
    if not any(abs(current_scale - value) < 0.001 for value in scales):
        scales.append(current_scale)
        scales.sort()
    for scale in scales:
        host.scale_combo.addItem(f"{int(round(catalog.CANVAS_W * scale))} px", scale)
    host.scale_combo.setCurrentIndex(host.scale_combo.findData(current_scale))

    host.on_top_check = ToggleSwitch(host)
    host.on_top_check.setChecked(bool(host.config.get("on_top", True)))
    # 允许桌宠跨屏（全局键、重启级）：唯一消费者是 overlay 壳的宿主化路径
    # （overlay_shell 的屏宿主分配/跨屏路由）。legacy 单窗 PetWindow 自己就是一个
    # 真窗口，本来就能跨显示器拖动，本开关对它没有第二个读点 ⇒ 非 overlay 拓扑下
    # 如实置灰 + 说明，不留"改了没反应"的活开关。
    host.cross_screen_check = ToggleSwitch(host)
    host.cross_screen_check.setChecked(bool(host.config.get("allow_cross_screen", False)))
    if not _is_overlay_topology():
        host.cross_screen_check.setEnabled(False)
        host.cross_screen_check.setToolTip("仅单合成窗（overlay）拓扑生效")
    host.no_move_check = ToggleSwitch(host)
    host.no_move_check.setChecked(bool(host.config.get("no_move", False)))
    host.mouse_through_check = ToggleSwitch(host)
    host.mouse_through_check.setChecked(bool(host.config.get("mouse_through", False)))
    # Windows 专属的光标隐藏穿透仅在 Windows 创建，避免非 Windows 未入布局时游离到窗口左上角。
    host.cursor_hidden_passthrough_check = None
    if sys.platform == "win32":
        host.cursor_hidden_passthrough_check = ToggleSwitch(host)
        host.cursor_hidden_passthrough_check.setChecked(bool(host.config.get("cursor_hidden_passthrough", True)))
    # 静止放手下落（#219）：低速松手零初速受重力落地。独立于「拖动物理」——
    # 拖动物理关时低速松手同样是「原地放下」，用户要的下落不该被那个开关挡住。
    host.drop_gravity_check = ToggleSwitch(host)
    host.drop_gravity_check.setChecked(bool(host.config.get("drop_gravity", False)))
    if not _is_overlay_topology():
        # 静止放手下落只被 sprite 路径消费（pet_sprite；legacy 的 PetWindow 没有
        # 对应行为）。捕获模式接通后 legacy 已是真实用户路径，开关摆在那里改了
        # 没反应 ⇒ 如实置灰 + 说明（同节其它行 legacy 真的消费，保持可用）。
        host.drop_gravity_check.setEnabled(False)
        host.drop_gravity_check.setToolTip("仅单合成窗（overlay）拓扑生效")
    # 「单进程多开」开关不再创建（拓扑收口 Phase A：设置页隐藏；
    # 游离 ToggleSwitch 会被孤儿开关测试拦截）。

    # 甩出力度四档：gentle (轻柔) / standard (标准) / strong (强力) / crazy (疯狂)
    host.throw_strength_select = ModernSelect(host, width=132)
    host.throw_strength_select.addItem("轻柔", "gentle")
    host.throw_strength_select.addItem("标准", "standard")
    host.throw_strength_select.addItem("强力", "strong")
    host.throw_strength_select.addItem("疯狂", "crazy")
    current_strength = str(host.config.get("throw_strength", "standard") or "standard")
    host.throw_strength_select.setCurrentData(current_strength if current_strength in {"gentle", "standard", "strong", "crazy"} else "standard")

    # 弹弓弹射开关
    host.slingshot_check = ToggleSwitch(host)
    host.slingshot_check.setChecked(bool(host.config.get("slingshot_enabled", True)))

    # 多开碰撞设置
    host.lock_position_check = ToggleSwitch(host)
    host.lock_position_check.setChecked(bool(host.config.get("lock_position", False)))
    host.shift_drag_check = ToggleSwitch(host)
    host.shift_drag_check.setChecked(bool(host.config.get("shift_drag", False)))
    host.pet_opacity_spin = BrowserSpinBox(host)
    host.pet_opacity_spin.setRange(10, 100)
    host.pet_opacity_spin.setSuffix(" %")
    host.pet_opacity_spin.setValue(int(_float_or_default(host.config.get("pet_opacity", 100), 100, 10, 100)))
    host.autostart_check = ToggleSwitch(host)
    host._autostart_initial = autostart_mod.is_enabled()
    host.autostart_check.setChecked(host._autostart_initial)
    # 开机自启是**全局**键（`autostart_wanted` 写在主配置，系统登录项只有一份），
    # 但**任意宠**都能改它——界面必须自己说清影响范围，而不是把自己置灰。旧判据
    # `if instance_id` 在 slot0 拿到显式身份后把主宠页也一起禁掉了，tooltip 却让人
    # "去主桌宠设置"，指向一个用户正站着的地方（2026-10-10 终审 A04-b）。
    host.autostart_check.setToolTip("影响所有桌宠：系统登录项只有一份。")
    host.dock_icon_check = None
    if sys.platform == "darwin":
        host.dock_icon_check = ToggleSwitch(host)
        host.dock_icon_check.setChecked(bool(host.config.get("show_dock_icon", True)))

    # 点击音效控件群
    host.click_sound_check = ToggleSwitch(host)
    host.click_sound_check.setChecked(bool(host.config.get("click_sound_enabled", True)))
    host.click_sound_picker = ClickSoundPackPicker(
        host.config.get("click_sound_pack"),
        parent=host,
    )
    host.click_sound_volume_spin = BrowserSpinBox(host)
    host.click_sound_volume_spin.setRange(0, 100)
    host.click_sound_volume_spin.setSuffix(" %")
    click_vol = float(host.config.get("click_sound_volume", 0.70))
    host.click_sound_volume_spin.setValue(int(round(click_vol * 100)))

    host.click_sound_preview_btn = QPushButton("试听", host)
    host.click_sound_preview_btn.setIcon(vector_widget_icon(host.click_sound_preview_btn, "sound", 14))
    host.click_sound_preview_btn.setFixedWidth(72)
    host.click_sound_preview_btn.clicked.connect(host._preview_click_sound)

    host.click_sound_check.toggled.connect(host._update_click_sound_controls)
    # 音效开关即时生效：对话框的批量写回发生在关闭时，但声音开关是即时
    # 听觉反馈——用户关掉后期望立刻静音，而不是等关对话框。
    host.click_sound_check.toggled.connect(host._apply_click_sound_enabled_now)
    host.click_balance_check = ToggleSwitch(host)
    host.click_balance_check.setChecked(bool(host.config.get("click_show_balance", False)))
    host.click_self_talk_check = ToggleSwitch(host)
    host.click_self_talk_check.setChecked(bool(host.config.get("click_show_self_talk", False)))
    host.golden_spin_click_check = ToggleSwitch(host)
    host.golden_spin_click_check.setChecked(bool(host.config.get("golden_spin_on_click", False)))
    host.golden_spin_direct_check = ToggleSwitch(host)
    host.golden_spin_direct_check.setChecked(bool(host.config.get("golden_spin_direct", False)))
    host.edge_probe_check = ToggleSwitch(host)
    host.edge_probe_check.setChecked(bool(host.config.get("edge_probe_enabled", False)))
    host.balance_refresh_spin = BrowserSpinBox(host)
    host.balance_refresh_spin.setRange(0, 1440)
    host.balance_refresh_spin.setSuffix(" 分钟")
    host.balance_refresh_spin.setValue(int(host.config.get("balance_refresh_minutes", 0) or 0))
    host.balance_tier_mode_select = ModernSelect(host, width=180)
    host.balance_tier_mode_select.addItem("空闲 / 高峰（默认）", "default")
    host.balance_tier_mode_select.addItem("梁文谷 / 梁文峰", "liangwen")
    host.balance_tier_mode_select.addItem("自定义", "custom")
    host.balance_tier_mode_select.setCurrentData(
        str(host.config.get("balance_tier_labels_mode", "default") or "default")
    )
    host.balance_tier_peak_edit = QLineEdit(host)
    host.balance_tier_peak_edit.setPlaceholderText("高峰文本，例如：梁文峰")
    host.balance_tier_peak_edit.setText(str(host.config.get("balance_tier_label_peak", "") or ""))
    host.balance_tier_idle_edit = QLineEdit(host)
    host.balance_tier_idle_edit.setPlaceholderText("空闲文本，例如：梁文谷")
    host.balance_tier_idle_edit.setText(str(host.config.get("balance_tier_label_idle", "") or ""))
    host.balance_tier_color_check = ToggleSwitch(host)
    host.balance_tier_color_check.setChecked(bool(host.config.get("balance_tier_color_enabled", True)))
    host.auto_hide_fullscreen_check = None
    if sys.platform == "win32":
        host.auto_hide_fullscreen_check = ToggleSwitch(host)
        host.auto_hide_fullscreen_check.setChecked(bool(host.config.get("auto_hide_fullscreen", True)))

    host.speed_select = ModernSelect(host, width=112)
    current_speed = float(host.config.get("playback_speed", 1.0))
    speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]
    if not any(abs(current_speed - value) < 0.001 for value in speeds):
        speeds.append(current_speed)
        speeds.sort()
    for speed in speeds:
        host.speed_select.addItem(f"{speed:g}x", speed)
    host.speed_select.setCurrentData(current_speed)
    host.gap_spin = BrowserDoubleSpinBox(host)
    host.gap_spin.setRange(0.0, 3600.0)
    host.gap_spin.setSingleStep(0.5)
    host.gap_spin.setDecimals(1)
    host.gap_spin.setSuffix(" 秒")
    host.gap_spin.setValue(float(host.config.get("animation_gap_seconds", 0.0)))

    host.self_talk_check = ToggleSwitch(host)
    host.self_talk_check.setChecked(bool(host.config.get("self_talk_enabled", False)))
    host.idle_low_fps_check = ToggleSwitch(host)
    host.idle_low_fps_check.setChecked(bool(host.config.get("idle_low_fps_enabled", False)))
    host.self_talk_duration_spin = BrowserDoubleSpinBox(host)
    host.self_talk_duration_spin.setRange(1.0, 300.0)
    host.self_talk_duration_spin.setSingleStep(0.5)
    host.self_talk_duration_spin.setDecimals(1)
    host.self_talk_duration_spin.setSuffix(" 秒")
    host.self_talk_duration_spin.setValue(float(host.config.get(
        "self_talk_duration_seconds", DEFAULT_SELF_TALK_DURATION_SECONDS
    )))
    host.bubble_style_select = ModernSelect(host, width=172)
    for value, preset in BUBBLE_STYLE_PRESETS.items():
        host.bubble_style_select.addItem(str(preset["label"]), value)
    host.bubble_style_select.setCurrentData(
        str(host.config.get("self_talk_bubble_style", DEFAULT_SELF_TALK_BUBBLE_STYLE))
    )
    host.min_spin = BrowserDoubleSpinBox(host)
    host.max_spin = BrowserDoubleSpinBox(host)
    for spin, value in (
        (host.min_spin, host.config.get("self_talk_min_interval", DEFAULT_SELF_TALK_MIN_INTERVAL)),
        (host.max_spin, host.config.get("self_talk_max_interval", DEFAULT_SELF_TALK_MAX_INTERVAL)),
    ):
        spin.setRange(5.0, 3600.0)
        spin.setDecimals(0)
        spin.setSuffix(" 秒")
        spin.setValue(float(value))
    host.texts_edit = QPlainTextEdit(host)
    host.texts_edit.setMinimumSize(240, 82)
    host.texts_edit.setMaximumHeight(170)
    texts = host.config.get("self_talk_texts", DEFAULT_SELF_TALK_TEXTS)
    host.texts_edit.setPlainText("\n".join(str(item) for item in texts))
    host.self_talk_image_dir_picker = ResourcePathPicker(
        str(host.config.get("self_talk_image_dir", "") or ""),
        directory=True,
        image_preview=True,
        parent=host,
    )
    host.self_talk_image_scale_spin = BrowserSpinBox(host)
    host.self_talk_image_scale_spin.setRange(50, 300)
    host.self_talk_image_scale_spin.setSuffix(" %")
    host.self_talk_image_scale_spin.setValue(int(host.config.get("self_talk_image_scale", 100)))
    host.self_talk_image_chance_spin = BrowserSpinBox(host)
    host.self_talk_image_chance_spin.setRange(0, 100)
    host.self_talk_image_chance_spin.setSuffix(" %")
    host.self_talk_image_chance_spin.setValue(
        int(host.config.get("self_talk_image_chance", DEFAULT_SELF_TALK_IMAGE_CHANCE))
    )
    # 气泡文字大小：与配图大小并列的独立系数（气泡与字号一起等比放大）
    host.bubble_text_scale_spin = BrowserSpinBox(host)
    host.bubble_text_scale_spin.setRange(50, 300)
    host.bubble_text_scale_spin.setSuffix(" %")
    host.bubble_text_scale_spin.setValue(int(host.config.get("bubble_text_scale", 100)))
    host.click_talk_bindings_btn = QPushButton("编辑…", host)
    host.click_talk_bindings_btn.setObjectName("clickTalkBindingsButton")
    host.click_talk_bindings_btn.clicked.connect(host._open_click_talk_bindings)

    host.dialogue_mode_select = ModernSelect(host, width=190)
    for label, value in (("默认模式", "legacy"), ("鲸鱼娘女仆模式", "whale_maid"), ("自定义台词", "custom")):
        host.dialogue_mode_select.addItem(label, value)
    host.dialogue_mode_select.setCurrentData(str(host.config.get("dialogue_mode", "legacy") or "legacy"))
    # 统一预设：global 层是编辑区默认面（flat 旧结构 = global；双层取 global）
    configured_phrases = host.config.get("dialogue_phrases", {})
    if isinstance(configured_phrases, dict) and ("global" in configured_phrases or "agents" in configured_phrases):
        preset_global = configured_phrases.get("global")
        if not isinstance(preset_global, dict):
            preset_global = {}
        preset_agents = configured_phrases.get("agents")
        if not isinstance(preset_agents, dict):
            preset_agents = {}
    else:
        preset_global = configured_phrases if isinstance(configured_phrases, dict) else {}
        preset_agents = {}

    # 编辑层（delta）编辑缓冲：scope（""=global）→ {事件: 文本}
    host.dialogue_scope_select = ModernSelect(host, width=190)
    host.dialogue_scope_select.addItem("默认（全局文案）", "")
    # 记住并恢复上次编辑层（设置页保存时写 dialogue_last_scope；未知值回落全局）
    initial_scope = str(host.config.get("dialogue_last_scope", "") or "")
    if host.dialogue_scope_select.findData(initial_scope) < 0:
        initial_scope = ""
    host.dialogue_scope_select.setCurrentData(initial_scope)
    host._dialogue_scope = initial_scope  # 当前编辑层（""=global）

    host.dialogue_phrase_edits: dict[str, QPlainTextEdit] = {}
    for key in phrase_keys():
        edit = QPlainTextEdit(host)
        raw_value = preset_global.get(key, "")
        if isinstance(raw_value, list):
            edit.setPlainText("\n".join(str(item) for item in raw_value if isinstance(item, str)))
        else:
            edit.setPlainText(str(raw_value or ""))
        edit.setMinimumHeight(48)
        edit.setMaximumHeight(120)
        hint = dialogue_params_hint(key)
        if hint:
            placeholder = "留空使用基础模式台词；本事件支持：" + hint
        else:
            placeholder = "留空使用基础模式台词；本事件无可替换参数"
        edit.setPlaceholderText(placeholder)
        host.dialogue_phrase_edits[key] = edit

    # 每个 scope 的编辑缓冲快照（切换时 flush/load）
    host._dialogue_scope_buffer: dict[str, dict[str, str]] = {}
    host._dialogue_scope_buffer[""] = {
        key: edit.toPlainText() for key, edit in host.dialogue_phrase_edits.items()
    }
    for agent_key, agent_events in preset_agents.items():
        if not isinstance(agent_events, dict):
            continue
        host._dialogue_scope_buffer[str(agent_key)] = {
            key: ("\n".join(str(i) for i in value) if isinstance(value, list) else str(value or ""))
            for key, value in agent_events.items()
        }
    if host._dialogue_scope:
        # 恢复上次编辑层：把该层缓冲载入编辑框（行可见性等对话框建完行后再收敛）
        _load_dialogue_scope_into_editors(host, host._dialogue_scope)
    host.dialogue_scope_select.currentIndexChanged.connect(host._on_dialogue_scope_changed)

    host.dialogue_template_import_edit = QPlainTextEdit(host)
    host.dialogue_template_import_edit.setObjectName("dialogueTemplateImportEdit")
    host.dialogue_template_import_edit.setPlaceholderText(
        "粘贴 persona-phrases/v1 JSON 模板到这里，然后点击“导入模板”"
    )
    host.dialogue_template_import_edit.setMinimumHeight(92)
    host.dialogue_template_import_edit.setMaximumHeight(180)
    host.dialogue_template_export_btn = QPushButton("一键复制模板", host)
    host.dialogue_template_export_btn.setObjectName("dialogueTemplateExportButton")
    host.dialogue_template_export_btn.clicked.connect(host._export_dialogue_template)
    host.dialogue_template_import_btn = QPushButton("导入模板", host)
    host.dialogue_template_import_btn.setObjectName("dialogueTemplateImportButton")
    host.dialogue_template_import_btn.clicked.connect(host._import_dialogue_template_json)
    host.dialogue_template_actions = QWidget(host)
    dialogue_template_actions_layout = QVBoxLayout(host.dialogue_template_actions)
    dialogue_template_actions_layout.setContentsMargins(0, 0, 0, 0)
    dialogue_template_actions_layout.setSpacing(6)
    dialogue_template_actions_layout.addWidget(host.dialogue_template_import_edit)
    dialogue_template_buttons = QHBoxLayout()
    dialogue_template_buttons.setContentsMargins(0, 0, 0, 0)
    dialogue_template_buttons.addWidget(host.dialogue_template_export_btn)
    dialogue_template_buttons.addWidget(host.dialogue_template_import_btn)
    dialogue_template_actions_layout.addLayout(dialogue_template_buttons)
    appearance = host.config.get("context_menu_appearance", DEFAULT_CONTEXT_MENU_APPEARANCE)
    host.menu_theme_select = ModernSelect(host, width=132)
    for label, value in (("跟随系统", "system"), ("浅色", "light"), ("深色", "dark")):
        host.menu_theme_select.addItem(label, value)
    host.menu_theme_select.setCurrentData(appearance.get("theme", "system"))
    host.menu_density_select = ModernSelect(host, width=132)
    for label, value in (("紧凑", "compact"), ("标准", "standard"), ("宽松", "spacious")):
        host.menu_density_select.addItem(label, value)
    host.menu_density_select.setCurrentData(appearance.get("density", "standard"))
    host.menu_radius_select = ModernSelect(host, width=112)
    for radius in (8, 12, 16, 18):
        host.menu_radius_select.addItem(f"{radius} px", radius)
    host.menu_radius_select.setCurrentData(int(appearance.get("corner_radius", 12)))
    host.menu_font_select = ModernSelect(host, width=172)
    host.menu_font_select.addItem("系统默认", "system")
    host._menu_fonts_populated = False
    current_font = str(appearance.get("ui_font") or "system")
    if current_font != "system":
        # 保留当前配置值无需枚举字体库，确保用户未展开选择器直接保存时
        # 不会把自定义字体静默重置为 system。
        host.menu_font_select.addItem(current_font, current_font)
    host.menu_font_select.setCurrentData(current_font)
    # Windows 字体较多时首次枚举可阻塞数秒。零延迟定时器仍会在
    # 设置窗口首帧绘制前运行，因此改为仅在用户真正展开字体选择器时加载。
    host.menu_font_select.aboutToShowPopup.connect(host._populate_menu_fonts)
    host.menu_font_size_select = ModernSelect(host, width=112)
    for size in range(10, 19):
        host.menu_font_size_select.addItem(f"{size} px", size)
    host.menu_font_size_select.setCurrentData(int(appearance.get("ui_font_size", 13)))
    host.menu_translucent_check = ToggleSwitch(host)
    host.menu_translucent_check.setChecked(bool(appearance.get("translucent", True)))
    host.menu_opacity_spin = BrowserDoubleSpinBox(host)
    host.menu_opacity_spin.setRange(0.72, 1.0)
    host.menu_opacity_spin.setSingleStep(0.02)
    host.menu_opacity_spin.setDecimals(2)
    host.menu_opacity_spin.setValue(float(appearance.get("opacity", 0.94)))

    def color_picker(key: str) -> ColorPicker:
        return ColorPicker(str(appearance.get(key) or DEFAULT_CONTEXT_MENU_APPEARANCE[key]), host)

    host.light_background_picker = color_picker("light_background")
    host.light_foreground_picker = color_picker("light_foreground")
    host.light_hover_picker = color_picker("light_hover")
    host.dark_background_picker = color_picker("dark_background")
    host.dark_foreground_picker = color_picker("dark_foreground")
    host.dark_hover_picker = color_picker("dark_hover")


# ------------------------------------------------------------ 台词模板控制器
# 从 ModernSettingsDialog 外迁（host-based）：逻辑以 host 为参数驻留本模块，
# 对话框保留同名薄委托方法，兼容既有调用与测试 patch（tests 直接调
# dialog._import_dialogue_template_json / _current_dialogue_template 等）。


def _dialogue_flush_scope(host, scope: str | None = None) -> None:
    """把当前编辑区的文本快照写回 scope buffer（切换/保存前调用）。

    scope 缺省取内部追踪的当前层（host._dialogue_scope），而不是
    select.currentData()——切换信号触发时下拉已是新值，用它 flush 会把
    编辑内容误写进目标层。
    """
    if not hasattr(host, "dialogue_scope_select") or not hasattr(host, "dialogue_phrase_edits"):
        return
    scope = host._dialogue_scope if scope is None else scope
    host._dialogue_scope_buffer[str(scope)] = {
        key: edit.toPlainText() for key, edit in host.dialogue_phrase_edits.items()
    }


def _load_dialogue_scope_into_editors(host, scope: str) -> None:
    """把某层缓冲载入全部编辑框（未配置的事件留空 = 沿用 global/内置）。"""
    buf = host._dialogue_scope_buffer.get(scope) or {}
    for key, edit in host.dialogue_phrase_edits.items():
        edit.setPlainText(str(buf.get(key, "") or ""))


def _apply_dialogue_scope_rows(host) -> None:
    """非 global 编辑层只显示该层可定制事件，公共事件行隐藏。

    global 层（""）显示全部事件。行尚未构建（对话框 __init__ 中途）时静默跳过。
    """
    scope = str(getattr(host, "_dialogue_scope", "") or "")
    if not hasattr(host, "dialogue_phrase_edits"):
        return
    show_all = scope == ""
    for key in host.dialogue_phrase_edits:
        row = host.findChild(SettingRow, f"settingRow_dialogue_{key}")
        if row is None:
            continue
        if show_all:
            row.setVisible(True)
            continue
        if key in PUBLIC_DIALOGUE_EVENTS:
            row.setVisible(False)


def _on_dialogue_scope_changed(host, index: int) -> None:
    """切换文案编辑层：flush 当前层后载入目标层内容。"""
    if not hasattr(host, "dialogue_scope_select"):
        return
    _dialogue_flush_scope(host)
    target = str(host.dialogue_scope_select.currentData() or "")
    host._dialogue_scope = target
    _load_dialogue_scope_into_editors(host, target)
    _apply_dialogue_scope_rows(host)


def _dialogue_scope_values(host, scope: str) -> dict[str, list[str]]:
    """scope buffer 某层的非空事件 → list[str]（供保存/导出）。"""
    buf = host._dialogue_scope_buffer.get(scope) or {}
    return {
        key: [line.strip() for line in str(text).splitlines() if line.strip()]
        for key, text in buf.items()
        if str(text or "").strip()
    }


def _dialogue_phrase_values(host) -> dict[str, list[str]]:
    return _dialogue_scope_values(host, "")


def _current_dialogue_template(host) -> dict:
    # 导出 = 纯字段参考模板：phrases 一律留空（不携带当前已配置的台词），
    # 供 AI 依角色卡从零撰写；当前台词如需备份请直接复制编辑框内容。
    # agents：为每个可编辑层各生成一层事件脚手架（值空 = 沿用 global/内置）。
    agent_keys = [
        str(host.dialogue_scope_select.itemData(index) or "")
        for index in range(host.dialogue_scope_select.count())
    ]
    agent_keys = [key for key in agent_keys if key]
    return build_persona_template({
        "dialogue_mode": host.dialogue_mode_select.currentData() or "legacy",
        "dialogue_phrases": {},
    }, agent_keys=agent_keys or None)


def _export_dialogue_template(host) -> None:
    """Export the complete current template to the clipboard (no file dialog)."""
    try:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            raise RuntimeError("系统剪贴板不可用")
        clipboard.setText(json.dumps(_current_dialogue_template(host), ensure_ascii=False, indent=2) + "\n")
    except Exception as exc:
        QMessageBox.warning(host, "导出失败", f"无法写入系统剪贴板：{exc}")
        return
    QMessageBox.information(
        host, "导出成功",
        "模板已复制到剪贴板：可直接粘贴给 AI 依角色卡改写，"
        "或粘贴回「导入模板」输入框一键导回。",
    )


def _import_dialogue_template_json(host) -> None:
    """Import a complete persona template from the inline JSON editor."""
    raw = host.dialogue_template_import_edit.toPlainText().strip()
    if not raw:
        QMessageBox.warning(host, "导入失败", "请先粘贴 JSON 模板。")
        return
    try:
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("模板根节点必须是 JSON 对象")
        template_name = str(document.get("template", "") or "")
        if template_name and not template_name.startswith("persona-phrases/"):
            raise ValueError("不是兼容的 persona-phrases 模板")
        phrases = document.get("phrases")
        if not isinstance(phrases, dict):
            phrases = document.get("dialogue_phrases")
        if not isinstance(phrases, dict):
            raise ValueError("模板缺少 phrases 对象")
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        QMessageBox.warning(host, "导入失败", f"JSON 模板无效：{exc}")
        return
    for key, edit in host.dialogue_phrase_edits.items():
        value = phrases.get(key, "")
        if isinstance(value, list):
            edit.setPlainText("\n".join(str(item) for item in value if isinstance(item, str)))
        elif value is not None:
            edit.setPlainText(str(value))
    # entries[].phrases 兜底：顶层 phrases 缺失/为空的 key 用 entries 补齐
    #（顶层有内容时以顶层为准，不被 entries 覆盖）。
    entries = document.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            edit = host.dialogue_phrase_edits.get(str(entry.get("key") or "").strip())
            if edit is None:
                continue
            current = phrases.get(entry["key"])
            has_top = (
                (isinstance(current, list) and any(isinstance(i, str) and i.strip() for i in current))
                or (isinstance(current, str) and current.strip())
            )
            if has_top or edit.toPlainText().strip():
                continue
            value = entry.get("phrases")
            if isinstance(value, list):
                text = "\n".join(str(item) for item in value if isinstance(item, str) and item.strip())
                if text:
                    edit.setPlainText(text)
    host.dialogue_mode_select.setCurrentData("custom")
    # agents delta（整体导入）：写入 scope buffer，供切换专属层编辑
    _dialogue_flush_scope(host)
    raw_agents = document.get("agents")
    if isinstance(raw_agents, dict):
        for agent_key, agent_events in raw_agents.items():
            if not isinstance(agent_events, dict):
                continue
            host._dialogue_scope_buffer[str(agent_key)] = {
                str(k): ("\n".join(str(i) for i in v) if isinstance(v, list) else str(v or ""))
                for k, v in agent_events.items()
            }
    host.dialogue_template_import_edit.clear()
    QMessageBox.information(host, "导入成功", "已导入全部弹窗内容模板；点击“保存并退出”后生效。")
