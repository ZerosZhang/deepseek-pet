"""Action registration and tree rendering for the shared Menu Action Model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QWidgetAction

from .icons import custom_file_menu_icon, vector_menu_icon
from .shared import (
    add_action,
    add_autostart,
    add_balance,
    add_edge_probe,
    add_golden_spin,
    add_hide_pet,
    add_memory_trim,
    add_no_move,
    add_on_top,
    add_quiet_mode_menu,
    add_quit,
    add_return_corner,
    add_submenu,
    build_animation_categories,
    build_size_menu,
    build_speed_menu,
)


ACTION_LABELS = {
    "animations_hub": "播放动画", "playback_speed": "播放速率",
    "size": "大小", "no_move": "不移动",
    "on_top": "窗口置顶", "autostart": "开机自启",
    "return_corner": "回到右下角", "hide_pet": "隐藏桌宠",
    "golden_spin": "黄金回旋", "edge_probe": "边缘探头",
    "balance": "DeepSeek 余额",
    "memory_trim": "回收内存",
    "quiet_mode": "免打扰",
    "modern_settings": "桌宠设置", "quit": "退出",
}


Builder = Callable[[QMenu, object], object]
Availability = Callable[[object], bool]
Enablement = Callable[[object], bool]


ACTION_ICONS = {
    "animations_hub": "play", "playback_speed": "speed",
    "size": "size", "no_move": "pause",
    "on_top": "pin", "autostart": "autostart",
    "return_corner": "corner", "hide_pet": "hide",
    "golden_spin": "play", "edge_probe": "corner",
    "balance": "balance",
    "memory_trim": "clear",
    "quiet_mode": "pause",
    "modern_settings": "settings", "quit": "quit",
    "festival_now": "todo", "festival_toggle": "todo",
}

CUSTOM_ICON_CHOICES = (
    ("默认图标", "default"), ("无图标", "none"),
    ("对话", "chat"), ("屏幕", "screen"), ("播放", "play"),
    ("角色", "character"), ("速度", "speed"), ("尺寸", "size"),
    ("桌宠", "pet"), ("交互", "interaction"), ("置顶", "pin"),
    ("隐藏", "hide"), ("应用", "application"), ("余额", "balance"),
    ("清除", "clear"), ("网页", "web"), ("下载", "download"), ("更新", "update"),
    ("自动化", "automation"), ("设置", "settings"), ("待办", "todo"),
)


@dataclass(frozen=True)
class MenuActionSpec:
    build: Builder
    available: Availability = lambda _pet: True
    enabled: Enablement = lambda _pet: True
    disabled_reason: str = "当前功能未启用"


def _callback_available(name: str) -> Availability:
    return lambda pet: callable(getattr(pet, name, None))


def _memory_trim_available(_pet) -> bool:
    """「回收内存」只对 Windows 显示：其它平台没有 EmptyWorkingSet。

    判定走 ``pet/memory_trim.py::is_supported``（与执行层同一判据），不另写一份
    ``sys.platform`` 比较——菜单给不给看和执行能不能跑必须是同一个真相。
    """
    from .. import memory_trim

    return memory_trim.is_supported()


def _build_animations(menu, pet):
    submenu = add_submenu(menu, "播放动画", "play")
    build_animation_categories(submenu, pet, icons=False, leaf_role_icons=True)
    return submenu


def _build_settings(menu, pet):
    return add_action(menu, "桌宠设置", "settings", pet.on_open_modern_settings, close_on_trigger=True)


def _flag_toggle_spec(key: str, on_label: str, off_label: str, icon: str,
                      callback: str):
    """布尔开关菜单项的规约工厂：按配置当前值翻转标签，点击回回调。

    「读配置 → 选标签 → add_action」收成一处；标签翻转、图标、回调与
    close_on_trigger 语义逐点不变。注意 `enabled` 只影响展示标签，不影响回调
    可用性（可用性仍由 `MenuActionSpec.available` 的 `_callback_available` 判定）。
    """
    def _build(menu, pet):
        cfg = getattr(pet, "cfg", None)
        enabled = bool(cfg.get(key, False)) if cfg is not None else False
        return add_action(
            menu, on_label if enabled else off_label, icon,
            getattr(pet, callback), close_on_trigger=True,
        )

    return _build


_build_festival_toggle = _flag_toggle_spec(
    "festival_reminder_enabled", "关闭节日提醒", "启用节日提醒", "todo",
    "on_toggle_festival",
)


def _build_festival_now(menu, pet):
    return add_action(menu, "今日节日", "todo", pet.on_festival_now, close_on_trigger=True)


class MenuActionRegistry:
    """Resolve capability-aware action IDs and render a resolved menu tree."""

    def __init__(self) -> None:
        self._specs = {
            "animations_hub": MenuActionSpec(_build_animations),
            "playback_speed": MenuActionSpec(lambda menu, pet: build_speed_menu(menu, pet)),
            "size": MenuActionSpec(lambda menu, pet: build_size_menu(menu, pet)),
            "no_move": MenuActionSpec(add_no_move),
            "on_top": MenuActionSpec(add_on_top),
            "autostart": MenuActionSpec(lambda menu, pet: add_autostart(menu, pet)),
            "return_corner": MenuActionSpec(add_return_corner),
            "hide_pet": MenuActionSpec(add_hide_pet),
            # 始终可用：消费统计与歌词无关，不该被歌词开关卡住。
            # 平台门在 menu_layout 的 available_actions 过滤里生效（非 Windows
            # 整条不出现）；builder 自身也有同一道门，legacy 扁平布局直接调它。
            "memory_trim": MenuActionSpec(add_memory_trim, _memory_trim_available),
            "golden_spin": MenuActionSpec(
                add_golden_spin,
                _callback_available("trigger_golden_spin"),
            ),
            "edge_probe": MenuActionSpec(add_edge_probe),
            "balance": MenuActionSpec(add_balance, _callback_available("on_show_balance")),
            # 免打扰：进程级状态，任何宿主（PetWindow / SpriteMenuFacade）都可用，
            # 不做能力判定——菜单里永远给得出入口，用户不必先找开关。
            "quiet_mode": MenuActionSpec(add_quiet_mode_menu),
            "modern_settings": MenuActionSpec(
                _build_settings, _callback_available("on_open_modern_settings")
            ),
            "festival_now": MenuActionSpec(
                _build_festival_now, _callback_available("on_festival_now")
            ),
            "festival_toggle": MenuActionSpec(
                _build_festival_toggle, _callback_available("on_toggle_festival")
            ),
            "quit": MenuActionSpec(add_quit),
        }

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self._specs)

    def available_ids(self, pet) -> frozenset[str]:
        return frozenset(
            action_id
            for action_id, spec in self._specs.items()
            if spec.available(pet)
        )

    def enabled_ids(self, pet) -> frozenset[str]:
        return frozenset(
            action_id
            for action_id, spec in self._specs.items()
            if spec.available(pet) and spec.enabled(pet)
        )

    def disabled_reason(self, action_id: str) -> str:
        spec = self._specs.get(action_id)
        return spec.disabled_reason if spec is not None else "当前不可用"

    def default_icon(self, action_id: str) -> str:
        return ACTION_ICONS.get(action_id, "")

    def label(self, action_id: str) -> str:
        return ACTION_LABELS.get(action_id, action_id)

    def icon(self, widget, action_id: str, override=None) -> QIcon:
        """Resolve semantic or local-file presentation with a safe fallback."""
        if isinstance(override, dict) and override.get("kind") == "file":
            custom = custom_file_menu_icon(widget, override)
            if not custom.isNull():
                return custom
            override = None
        if override == "none":
            return QIcon()
        name = str(override or self.default_icon(action_id) or "")
        return vector_menu_icon(widget, name) if name else QIcon()

    def populate(self, menu: QMenu, pet, nodes, *, enabled_actions=None) -> None:
        enabled = frozenset(enabled_actions) if enabled_actions is not None else self.enabled_ids(pet)
        explicit_separators = any(node.get("type") == "separator" for node in nodes)
        previous_section = None
        rendered = 0
        for node in nodes:
            if node.get("type") == "separator":
                if rendered and menu.actions() and not menu.actions()[-1].isSeparator():
                    menu.addSeparator()
                previous_section = None
                continue
            section = node.get("section")
            if (
                not explicit_separators
                and rendered and section and previous_section and section != previous_section
            ):
                menu.addSeparator()
            built = None
            if node.get("type") == "submenu":
                submenu = add_submenu(
                    menu,
                    str(node.get("alias") or node.get("label") or ""),
                )
                self.populate(
                    submenu, pet, node.get("children", ()), enabled_actions=enabled,
                )
                built = submenu
                if "icon" in node:
                    submenu.menuAction().setIcon(
                        self.icon(menu, str(node.get("id") or ""), node.get("icon"))
                    )
            else:
                action_id = str(node.get("id") or "")
                spec = self._specs.get(action_id)
                if spec is not None:
                    built = spec.build(menu, pet)
                    action = built.menuAction() if isinstance(built, QMenu) else built
                    alias = str(node.get("alias") or "").strip()
                    if alias and action is not None:
                        action.setText(alias)
                        if isinstance(action, QWidgetAction):
                            widget = action.defaultWidget()
                            setter = getattr(widget, "set_title", None)
                            if callable(setter):
                                setter(alias)
                    if action is not None and "icon" in node:
                        action.setIcon(self.icon(menu, action_id, node.get("icon")))
                    if action is not None and action_id not in enabled:
                        action.setEnabled(False)
                        action.setToolTip(self.disabled_reason(action_id))
                        if isinstance(action, QWidgetAction) and action.defaultWidget() is not None:
                            action.defaultWidget().setEnabled(False)
            rendered += 1
            if section:
                previous_section = section


MENU_ACTIONS = MenuActionRegistry()
