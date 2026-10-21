from pet.menu_layout import (
    load_default_menu_layout,
    materialize_implicit_separators,
    resolve_menu_layout,
)




def test_legacy_section_boundaries_become_editable_separator_nodes():
    upgraded = materialize_implicit_separators({
        "schema_version": 1,
        "layout_id": "user",
        "nodes": [
            {"type": "action", "id": "chat", "visible": True, "section": "one"},
            {"type": "action", "id": "look_screen", "visible": True, "section": "two"},
        ],
    })

    assert [node["type"] for node in upgraded["nodes"]] == [
        "action", "separator", "action"
    ]
    assert upgraded["nodes"][1]["id"] == "user.separator-1"


def test_invalid_layout_falls_back_to_minimum_safe_menu():
    result = resolve_menu_layout(
        {
            "schema_version": 1,
            "layout_id": "user",
            "nodes": [
                {"type": "action", "id": "quit", "visible": True},
                {"type": "action", "id": "quit", "visible": True},
            ],
        },
        registered_actions={"modern_settings", "quit"},
        available_actions={"modern_settings", "quit"},
    )

    assert result.source == "fallback"
    assert result.diagnostics == ("duplicate-action:quit",)
    assert result.nodes == (
        {"type": "action", "id": "modern_settings", "visible": True},
        {"type": "action", "id": "quit", "visible": True},
    )


def test_user_layout_filters_hidden_unavailable_and_empty_submenus():
    result = resolve_menu_layout(
        {
            "schema_version": 1,
            "layout_id": "user",
            "nodes": [
                {"type": "action", "id": "chat", "visible": False},
                {"type": "action", "id": "look_screen", "visible": True},
                {
                    "type": "submenu",
                    "id": "pet_controls",
                    "label": "桌宠控制",
                    "visible": True,
                    "children": [
                        {"type": "action", "id": "no_move", "visible": True},
                        {"type": "action", "id": "mouse_through", "visible": True},
                    ],
                },
                {
                    "type": "submenu",
                    "id": "empty_tools",
                    "label": "空工具",
                    "visible": True,
                    "children": [
                        {"type": "action", "id": "balance", "visible": False}
                    ],
                },
                {"type": "action", "id": "modern_settings", "visible": True},
                {"type": "action", "id": "quit", "visible": True},
            ],
        },
        registered_actions={
            "chat",
            "look_screen",
            "no_move",
            "mouse_through",
            "balance",
            "modern_settings",
            "quit",
        },
        available_actions={"no_move", "modern_settings", "quit"},
    )

    assert result.source == "user"
    assert result.diagnostics == ()
    assert result.nodes == (
        {
            "type": "submenu",
            "id": "pet_controls",
            "label": "桌宠控制",
            "visible": True,
            "children": (
                {"type": "action", "id": "no_move", "visible": True},
            ),
        },
        {"type": "action", "id": "modern_settings", "visible": True},
        {"type": "action", "id": "quit", "visible": True},
    )


def test_layout_preserves_alias_icon_and_explicit_separator_nodes():
    result = resolve_menu_layout(
        {
            "schema_version": 1,
            "layout_id": "user",
            "nodes": [
                {
                    "type": "action",
                    "id": "chat",
                    "visible": True,
                    "alias": "和鲸鱼聊聊",
                    "icon": "screen",
                },
                {"type": "separator", "id": "user.separator-1", "visible": True},
                {"type": "action", "id": "modern_settings", "visible": True},
                {"type": "action", "id": "quit", "visible": True},
            ],
        },
        registered_actions={"chat", "modern_settings", "quit"},
        available_actions={"chat", "modern_settings", "quit"},
    )

    assert result.nodes[0] == {
        "type": "action",
        "id": "chat",
        "visible": True,
        "alias": "和鲸鱼聊聊",
        "icon": "screen",
    }
    assert result.nodes[1] == {
        "type": "separator",
        "id": "user.separator-1",
        "visible": True,
    }








def test_layout_restores_required_settings_and_exit_actions():
    result = resolve_menu_layout(
        {
            "schema_version": 1,
            "layout_id": "user",
            "nodes": [
                {"type": "action", "id": "chat", "visible": True},
                {"type": "action", "id": "modern_settings", "visible": False},
            ],
        },
        registered_actions={"chat", "modern_settings", "quit"},
        available_actions={"chat", "modern_settings", "quit"},
    )

    assert result.source == "normalized"
    assert result.diagnostics == (
        "required-action-restored:modern_settings",
        "required-action-restored:quit",
    )
    assert [node["id"] for node in result.nodes if node["type"] != "separator"] == [
        "chat",
        "modern_settings",
        "quit",
    ]




def test_config_persists_menu_layout_override_without_copying_default(tmp_path):
    from pet.config import Config

    config = Config(tmp_path)
    assert config.get("context_menu_layout") is None

    override = {
        "schema_version": 1,
        "layout_id": "user",
        "nodes": [
            {"type": "action", "id": "modern_settings", "visible": True},
            {"type": "action", "id": "quit", "visible": True},
        ],
    }
    config.set("context_menu_layout", override)
    config.save()

    restored = Config(tmp_path)
    assert restored.get("context_menu_layout") == override


def test_saved_layout_drops_removed_mouse_through_action(tmp_path):
    """2026-09-23：右键菜单去掉「鼠标穿透」，旧布局里的残留节点载入时就地清掉。

    渲染层本来就会丢弃未注册 id（只影响当次显示），但菜单编辑器没有「删除菜单项」
    操作，会把残留节点按「此平台不可用」一直回存下去；入口收敛必须在配置层收口，
    否则旧布局里会永久留着一条幽灵菜单项。
    """
    from pet.config import Config

    config = Config(tmp_path)
    config.set("context_menu_layout", {
        "schema_version": 1,
        "layout_id": "user",
        "nodes": [
            {"type": "action", "id": "modern_settings", "visible": True},
            {
                "type": "submenu", "id": "pet_controls", "label": "桌宠控制", "visible": True,
                "children": [
                    {"type": "action", "id": "no_move", "visible": True},
                    {"type": "action", "id": "mouse_through", "visible": True},
                ],
            },
            {"type": "action", "id": "quit", "visible": True},
        ],
    })
    config.save()

    nodes = Config(tmp_path).get("context_menu_layout")["nodes"]
    assert [node["id"] for node in nodes] == ["modern_settings", "pet_controls", "quit"]
    assert [child["id"] for child in nodes[1]["children"]] == ["no_move"]


def test_menu_registry_no_longer_registers_mouse_through():
    """入口收敛：右键菜单注册表里不再有「鼠标穿透」，开关只留在设置页与托盘菜单。"""
    from pet.context_menus.registry import MENU_ACTIONS, ACTION_ICONS, ACTION_LABELS

    assert "mouse_through" not in MENU_ACTIONS.ids
    assert "mouse_through" not in ACTION_LABELS
    assert "mouse_through" not in ACTION_ICONS


def test_unknown_schema_uses_safe_fallback_with_migration_diagnostic():
    result = resolve_menu_layout(
        {
            "schema_version": 99,
            "layout_id": "future",
            "nodes": [{"type": "action", "id": "chat", "visible": True}],
        },
        registered_actions={"chat", "modern_settings", "quit"},
        available_actions={"chat", "modern_settings", "quit"},
    )

    assert result.source == "fallback"
    assert result.diagnostics == ("unsupported-schema:99",)
    assert [node["id"] for node in result.nodes] == ["modern_settings", "quit"]




















def test_user_layout_rejects_nested_submenus_beyond_one_level():
    result = resolve_menu_layout(
        {
            "schema_version": 1,
            "layout_id": "user",
            "nodes": [{
                "type": "submenu",
                "id": "user.outer",
                "label": "外层",
                "visible": True,
                "children": [{
                    "type": "submenu",
                    "id": "user.inner",
                    "label": "内层",
                    "visible": True,
                    "children": [
                        {"type": "action", "id": "chat", "visible": True}
                    ],
                }],
            }],
        },
        registered_actions={"chat", "modern_settings", "quit"},
        available_actions={"chat", "modern_settings", "quit"},
    )

    assert result.source == "fallback"
    assert result.diagnostics == ("submenu-depth-exceeded:user.inner",)
    assert [node["id"] for node in result.nodes] == ["modern_settings", "quit"]








def _section_of(dialog, settings_mod, setting_id):
    """返回某个设置行所属的 SettingsSection（域重构后行会被 reparent 进共享卡片）。"""
    from pet.modern_settings_dialog import SettingRow

    row = dialog.findChild(SettingRow, f"settingRow_{setting_id}")
    assert row is not None, f"{setting_id} 行必须存在"
    parent = row.parentWidget()
    while parent is not None and not isinstance(parent, settings_mod.SettingsSection):
        parent = parent.parentWidget()
    assert parent is not None, f"{setting_id} 必须落在某个 SettingsSection 内"
    return parent


def _section_title(section) -> str:
    if section.toggle is not None:  # 高级组（默认收起）标题在 disclosure 按钮上
        return section.toggle.text()
    from pet import modern_settings_dialog as settings_mod

    label = section.findChild(settings_mod.QLabel, "sectionTitle")
    assert label is not None
    return label.text()




























def test_setting_row_stacks_a_wide_control_before_copy_becomes_unreadable():
    from PySide6.QtWidgets import QApplication, QPushButton

    from pet.modern_settings_dialog import SettingRow

    app = QApplication.instance() or QApplication([])
    control = QPushButton("宽控件")
    control.setFixedWidth(340)
    row = SettingRow(
        "responsive",
        "跨平台同步与自动恢复策略的超长本地化标题示例",
        "说明文字必须保持可读。",
        control,
    )
    row.resize(500, 180)
    row.show()
    app.processEvents()

    assert control.y() > row.label.y() + row.label.height()
    assert row.property("responsiveStacked") is True

    row.resize(900, 180)
    app.processEvents()

    assert control.x() > row.label.x()
    assert row.property("responsiveStacked") is False
    row.close()
    app.processEvents()




def test_responsive_action_row_can_stack_wide_actions_vertically():
    from PySide6.QtWidgets import QApplication, QPushButton

    from pet.modern_settings_dialog import ModernSelect, ResponsiveActionRow

    app = QApplication.instance() or QApplication([])
    primary = ModernSelect(width=230)
    first = QPushButton("第一个很长的本地化操作")
    second = QPushButton("第二个很长的本地化操作")
    first.setMinimumWidth(260)
    second.setMinimumWidth(260)
    row = ResponsiveActionRow(primary, [first, second])
    row.setFixedWidth(454)
    row.resize(454, 180)
    row.show()
    app.processEvents()

    assert row.minimumSizeHint().width() <= 260
    assert row.property("responsiveMode") == "compact"
    assert first.y() < second.y()
    assert first.geometry().right() <= row.rect().right()
    assert second.geometry().right() <= row.rect().right()
    row.close()
    app.processEvents()


def test_responsive_action_row_inline_mode_does_not_reserve_compact_height():
    from PySide6.QtWidgets import QApplication, QPushButton

    from pet.modern_settings_dialog import ModernSelect, ResponsiveActionRow

    app = QApplication.instance() or QApplication([])
    primary = ModernSelect(width=230)
    first = QPushButton("新增")
    second = QPushButton("删除")
    row = ResponsiveActionRow(primary, [first, second])
    row.setFixedWidth(800)
    row.show()
    app.processEvents()

    expected_height = max(
        widget.minimumHeight() or widget.minimumSizeHint().height()
        for widget in (primary, first, second)
    )
    assert row.property("responsiveMode") == "inline"
    assert row.minimumSizeHint().height() == expected_height
    row.close()
    app.processEvents()










def test_missing_default_resource_returns_minimum_safe_menu(monkeypatch):
    import pet.menu_layout as layout_mod

    monkeypatch.setattr(
        layout_mod,
        "load_default_menu_layout",
        lambda: (_ for _ in ()).throw(OSError("missing resource")),
    )

    result = layout_mod.resolve_menu_layout(
        None,
        registered_actions={"modern_settings", "quit"},
        available_actions={"modern_settings", "quit"},
    )

    assert result.source == "fallback"
    assert result.diagnostics == ("default-layout-unavailable",)
    assert [node["id"] for node in result.nodes] == ["modern_settings", "quit"]




def test_menu_preview_refreshes_after_tree_shape_changes():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from pet.modern_settings_dialog import MenuLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(None)
    controls = next(
        editor.tree.topLevelItem(index)
        for index in range(editor.tree.topLevelItemCount())
        if (
            editor.tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole) or {}
        ).get("id")
        == "pet_controls"
    )
    action = controls.child(0)
    action_label = action.text(0)

    controls.removeChild(action)
    editor.tree.addTopLevelItem(action)
    app.processEvents()

    preview_roots = [
        editor.preview.topLevelItem(index)
        for index in range(editor.preview.topLevelItemCount())
    ]
    preview_controls = next(item for item in preview_roots if item.text(0) == "桌宠控制")
    assert action_label in [item.text(0) for item in preview_roots]
    assert action_label not in [
        preview_controls.child(index).text(0)
        for index in range(preview_controls.childCount())
    ]
    editor.close()
    app.processEvents()


def test_menu_preview_and_runtime_qmenu_share_the_same_layout_structure():
    from copy import deepcopy

    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.modern import build_modern_menu
    from pet.context_menus.registry import MENU_ACTIONS
    from pet.modern_settings_dialog import MenuLayoutEditor

    layout = deepcopy(load_default_menu_layout())
    layout["layout_id"] = "user"
    visible_root_ids = {"chat", "pet_controls", "modern_settings", "quit"}
    for node in layout["nodes"]:
        node["visible"] = node["id"] in visible_root_ids
        if node["id"] == "pet_controls":
            node["label"] = "常用桌宠操作"
            for child in node["children"]:
                child["visible"] = child["id"] == "drag_physics"

    class FakeConfig:
        def get(self, key, default=None):
            values = {
                "context_menu_layout": layout,
                "menu_easter_egg": {"enabled": False},
                "quick_launch_apps": [],
            }
            return values.get(key, default)

    class FakePet:
        cfg = FakeConfig()
        drag_physics = False
        on_open_chat = lambda self: None
        on_open_modern_settings = lambda self: None
        set_drag_physics = lambda self, _enabled: None
        request_quit = lambda self: None

    def preview_shape(parent):
        return [
            (
                parent.child(index).text(0),
                preview_shape(parent.child(index)),
            )
            for index in range(parent.childCount())
            if parent.child(index).text(0) != "────────"
        ]

    def runtime_shape(menu, nodes):
        actions = [action for action in menu.actions() if not action.isSeparator()]
        assert len(actions) == len(nodes)
        return [
            (
                action.text(),
                runtime_shape(action.menu(), node["children"])
                if node.get("type") == "submenu"
                else [],
            )
            for action, node in zip(actions, nodes)
        ]

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(layout, available_actions=MENU_ACTIONS.ids)
    runtime_menu = QMenu()
    build_modern_menu(runtime_menu, FakePet())
    resolved = resolve_menu_layout(
        layout,
        registered_actions=MENU_ACTIONS.ids,
        available_actions=MENU_ACTIONS.available_ids(FakePet()),
    )

    assert preview_shape(editor.preview.invisibleRootItem()) == runtime_shape(
        runtime_menu, resolved.nodes
    )
    runtime_menu.close()
    editor.close()
    app.processEvents()


def test_menu_editor_switches_between_stacked_and_split_layouts():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from pet.modern_settings_dialog import MenuLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(None)
    editor.resize(560, 420)
    editor.show()
    app.processEvents()
    assert editor.findChild(type(editor.split), "menuEditorSplit").orientation() == Qt.Orientation.Vertical
    assert editor.tree.isColumnHidden(2)

    editor.resize(900, 420)
    app.processEvents()
    assert editor.split.orientation() == Qt.Orientation.Horizontal
    assert not editor.tree.isColumnHidden(2)
    editor.close()
    app.processEvents()


def test_menu_editor_uses_settings_cards_instead_of_native_table_chrome():
    from PySide6.QtWidgets import QApplication, QHeaderView

    from pet.modern_settings_dialog import MenuLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(None)
    editor.resize(900, 520)
    editor.show()
    app.processEvents()

    assert editor.tree.objectName() == "menuLayoutTree"
    assert editor.tree.uniformRowHeights()
    assert editor.tree.indentation() == 18
    assert all(
        editor.tree.header().sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
        for column in range(3)
    )
    assert not editor.tree.header().stretchLastSection()
    assert editor.tree.columnWidth(2) == 92
    assert editor.preview.header().isHidden()
    assert editor.preview.uniformRowHeights()
    assert editor.preview.indentation() == 18
    assert editor.findChild(
        type(editor.preview_label), "menuLayoutPreviewLabel"
    ).text() == "实时菜单预览"

    editor.close()
    app.processEvents()




def test_menu_editor_compact_action_bar_keeps_every_button_reachable():
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication

    from pet.modern_settings_dialog import MenuLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(None)
    editor.resize(420, 620)
    editor.show()
    app.processEvents()
    assert editor.width() <= 420

    buttons = (
        editor.order_button,
        editor.move_button,
        editor.submenu_button,
        editor.customize_button,
        editor.more_button,
    )
    assert all(button.isVisible() for button in buttons)
    assert all(
        button.mapTo(editor, QPoint(0, 0)).x() + button.width() <= editor.width()
        for button in buttons
    )
    assert len({button.mapTo(editor, QPoint(0, 0)).y() for button in buttons}) == 3
    editor.close()
    app.processEvents()


def test_non_windows_settings_does_not_create_orphan_windows_control(tmp_path, monkeypatch):
    import sys

    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog

    if sys.platform == "win32":
        return
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dialog = ModernSettingsDialog(Config(tmp_path), include_ai=True)

    assert dialog.cursor_hidden_passthrough_check is None
    dialog.reject()
    app.processEvents()




def test_menu_editor_retains_but_marks_platform_unavailable_action(tmp_path, monkeypatch):
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog

    if sys.platform == "win32":
        return
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dialog = ModernSettingsDialog(Config(tmp_path), include_ai=True)
    item = dialog.menu_layout_editor.item_for_action("proactive_screen")

    assert item is not None
    assert item.text(1) == "此平台不可用"
    assert not item.flags() & Qt.ItemFlag.ItemIsEnabled
    assert "主动识屏" not in [
        dialog.menu_layout_editor.preview.topLevelItem(i).text(0)
        for i in range(dialog.menu_layout_editor.preview.topLevelItemCount())
    ]
    dialog.reject()
    app.processEvents()








def test_removed_action_is_ignored_with_migration_diagnostic():
    result = resolve_menu_layout(
        {
            "schema_version": 1,
            "layout_id": "user",
            "nodes": [
                {"type": "action", "id": "retired_action", "visible": True},
                {"type": "action", "id": "chat", "visible": True},
                {"type": "action", "id": "modern_settings", "visible": True},
                {"type": "action", "id": "quit", "visible": True},
            ],
        },
        registered_actions={"chat", "modern_settings", "quit"},
        available_actions={"chat", "modern_settings", "quit"},
    )

    assert result.source == "normalized"
    assert result.diagnostics == ("unknown-action:retired_action",)
    assert [node["id"] for node in result.nodes] == ["chat", "modern_settings", "quit"]


def test_user_layout_gains_future_default_action_without_losing_custom_order(
    monkeypatch,
):
    import pet.menu_layout as layout_mod

    monkeypatch.setattr(
        layout_mod,
        "load_default_menu_layout",
        lambda: {
            "schema_version": 1,
            "layout_id": "modern-default-v1",
            "nodes": [
                {
                    "type": "submenu",
                    "id": "pet_controls",
                    "label": "桌宠控制",
                    "visible": True,
                    "children": [
                        {"type": "action", "id": "drag_physics", "visible": True},
                        {"type": "action", "id": "future_action", "visible": True},
                        {"type": "action", "id": "no_move", "visible": True},
                    ],
                },
                {"type": "action", "id": "modern_settings", "visible": True},
                {"type": "action", "id": "quit", "visible": True},
            ],
        },
    )
    result = resolve_menu_layout(
        {
            "schema_version": 1,
            "layout_id": "user",
            "nodes": [
                {
                    "type": "submenu",
                    "id": "pet_controls",
                    "label": "我的桌宠操作",
                    "visible": True,
                    "children": [
                        {"type": "action", "id": "no_move", "visible": True},
                        {"type": "action", "id": "drag_physics", "visible": False},
                    ],
                },
                {"type": "action", "id": "modern_settings", "visible": True},
                {"type": "action", "id": "quit", "visible": True},
            ],
        },
        registered_actions={
            "drag_physics",
            "future_action",
            "no_move",
            "modern_settings",
            "quit",
        },
        available_actions={
            "drag_physics",
            "future_action",
            "no_move",
            "modern_settings",
            "quit",
        },
    )

    assert result.source == "normalized"
    assert result.diagnostics == ("default-action-added:future_action",)
    controls = result.nodes[0]
    assert controls["label"] == "我的桌宠操作"
    assert [child["id"] for child in controls["children"]] == [
        "no_move",
        "future_action",
    ]




# --- Settings menu customization regressions (2026-09-03) ---






def test_menu_editor_header_columns_are_user_resizable():
    from PySide6.QtWidgets import QApplication, QHeaderView

    from pet.modern_settings_dialog import MenuLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(None)
    editor.resize(1000, 560)
    editor.show()
    app.processEvents()

    header = editor.tree.header()
    assert all(
        header.sectionResizeMode(index) == QHeaderView.ResizeMode.Interactive
        for index in range(3)
    )
    assert not header.sectionsMovable()
    original = editor.tree.columnWidth(0)
    header.resizeSection(0, original + 48)
    app.processEvents()
    assert editor.tree.columnWidth(0) == original + 48
    assert "拖动表头" in editor.editor_hint.text()
    editor.close()
    app.processEvents()


def test_settings_tabs_are_compact_left_aligned_plugin_style_navigation():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

    from pet.modern_settings_dialog import SettingsTabContainer

    app = QApplication.instance() or QApplication([])
    tabs = SettingsTabContainer()
    for key, label in (("layout", "菜单编排"), ("launcher", "快捷启动"), ("appearance", "外观")):
        tabs.addTab(key, label, QWidget())
    tabs.resize(900, 420)
    tabs.show()
    app.processEvents()

    assert tabs.tab_bar.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Maximum
    assert tabs.tab_layout.alignment() & Qt.AlignmentFlag.AlignLeft
    assert tabs.tab_bar.width() < tabs.width() * 0.7
    assert all(button.property("navigationStyle") == "plugin" for button in tabs._buttons)
    tabs.close()
    app.processEvents()


def test_action_menu_button_matches_selector_popup_geometry_and_anchor():
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QWidgetAction

    from pet.modern_settings_dialog import MenuLayoutEditor, ModernSelect, SettingsMenuButton

    app = QApplication.instance() or QApplication([])
    select = ModernSelect(width=240)
    select.addItem("新版菜单", "modern")
    select.addItem("旧版兼容菜单", "legacy")
    select.move(40, 40)
    select.show()
    select.showPopup()
    app.processEvents()
    selector_popup = select._popup
    assert selector_popup is not None

    editor = MenuLayoutEditor(None)
    editor.resize(1000, 560)
    editor.show()
    app.processEvents()
    button = editor.order_button
    assert isinstance(button, SettingsMenuButton)
    assert button.menu() is None  # no native indicator/anchoring path
    button.showPopup()
    app.processEvents()
    popup = button.popupMenu()

    assert popup.width() >= button.width()
    assert popup.pos() == button.mapToGlobal(QPoint(0, button.height() + 4))
    assert popup.property("settingsPopup") == selector_popup.property("settingsPopup")
    assert not any(isinstance(action, QWidgetAction) for action in selector_popup.actions())
    assert popup.actionGeometry(popup.actions()[0]).height() == selector_popup.actionGeometry(
        selector_popup.actions()[0]
    ).height()
    popup.close()
    selector_popup.close()
    editor.close()
    select.close()
    app.processEvents()


def test_menu_editor_uses_three_responsive_toolbar_and_panel_modes():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from pet.modern_settings_dialog import MenuLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(None)
    editor.show()

    editor.resize(1000, 600)
    app.processEvents()
    assert editor.property("layoutMode") == "wide"
    assert editor.split.orientation() == Qt.Orientation.Horizontal
    assert max(button.width() for button in editor.toolbar_buttons) <= 132
    assert editor.toolbar_layout.itemAtPosition(0, 4) is not None

    editor.resize(680, 700)
    app.processEvents()
    assert editor.property("layoutMode") == "medium"
    assert editor.split.orientation() == Qt.Orientation.Vertical
    assert editor.toolbar_layout.itemAtPosition(1, 1) is not None
    assert editor.toolbar_layout.itemAtPosition(1, 2) is None

    editor.resize(430, 760)
    app.processEvents()
    assert editor.property("layoutMode") == "compact"
    assert editor.tree.isColumnHidden(2)
    assert editor.toolbar_layout.itemAtPosition(2, 0) is not None
    assert editor.editor_hint.isHidden()
    editor.close()
    app.processEvents()






def test_pending_preview_refresh_is_cancelled_when_editor_destroyed():
    """回归：编辑器 C++ 对象销毁后，遗留的预览刷新不得再触碰已销毁的子控件。

    原实现用静态 ``QTimer.singleShot(0, self._flush_preview_refresh)``：它无法
    取消、也不随编辑器一起销毁；窗口关闭（C++ 对象已删除）后回调仍会执行
    ``_on_changed``，并在 ``self.tree.blockSignals(True)`` 抛
    ``RuntimeError: Internal C++ object (QTreeWidget) already deleted``。
    全量套件里这个残留回调由后续无关测试的 ``processEvents()`` 引爆
    （test_agent_link_threads / test_webm_clip_broker_feed 观测到）。

    owner 侧修法：改成父对象为自身的成员单次 timer（随对象销毁）+ 有效性闸门。
    """
    import shiboken6
    from PySide6.QtWidgets import QApplication

    from pet.modern_settings_dialog import MenuLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = MenuLayoutEditor(None)
    editor._schedule_preview_refresh()
    assert editor._preview_refresh_pending is True
    shiboken6.delete(editor)  # 同步销毁：等价于窗口关闭后 C++ 对象消失
    app.processEvents()  # 不得抛 RuntimeError（旧实现此处必红）




def _stylesheet_font_family(sheet: str) -> str:
    for line in sheet.splitlines():
        stripped = line.strip()
        if stripped.startswith("font-family:"):
            return stripped[len("font-family:"):].rstrip(";").strip()
    raise AssertionError("modern 菜单样式表里没有 font-family")


def test_system_font_stack_matches_platform():
    """右键菜单 font-family 必须是**单族**，且该族要覆盖菜单里的中文。

    2026-09-28 真 Qt(Windows 6.11) 分步实测：`QFontDatabase` 的族枚举本身只要 ~16MB，
    但只要拿一个「请求族覆盖不了待测文本」或「多族列表」的 QFont 去测量中文文本，
    Qt 就会为缺失字形做回退搜索而枚举整个字体库，把 C:\\Windows\\Fonts 的 528 个字体
    文件（~831MB）映射进进程——菜单弹出一次后 msyh.ttc 37.6MB、StaticCache.dat 19.2MB、
    simhei/arial 等常驻，RSS +70~150MB 不回。旧 macOS 栈、新 Windows 三族栈、
    单族但不存在（或覆盖不了中文）三种写法都会触发，所以这里只允许单族。
    """
    import sys
    from pet.context_menus.menu_styles.common import SYSTEM_FONT_STACK
    from pet.context_menus.menu_styles.modern import modern_menu_stylesheet

    sheet = modern_menu_stylesheet({"theme": "light"})
    assert SYSTEM_FONT_STACK in sheet
    family = _stylesheet_font_family(sheet)
    if sys.platform == "win32":
        # 单族 + 覆盖中文，两个条件缺一都会触发枚举（实测）
        assert "," not in family, f"多族 font-family 会触发全字体库枚举: {family}"
        assert "Microsoft YaHei" in family
    elif sys.platform == "darwin":
        # macOS 未实机验证，多族栈按原样保留，这里只锁住「没被顺手改掉」
        assert "SF Pro Text" in family

    # 用户自选字体也必须收敛成单族，否则挑了自定义字体的人重新踩同一个坑
    custom = _stylesheet_font_family(
        modern_menu_stylesheet({"theme": "light", "ui_font": "Consolas"})
    )
    assert "," not in custom, f"自选字体被拼成多族: {custom}"
    assert "Consolas" in custom




# --------------------------------------------------- 音乐：四播放器启动入口
# 2026-10-16：原先菜单里只有「打开网易云 / QQ音乐并播放」两个入口，酷狗与汽水
# 缺失（用户点名的缺口）。四个入口必须**同源**：同一个 ``_music_player_builder``
# 建造器 + 同一个 ``_launch_player_and_play`` worker，只有 player_key 不同；
# 因此路径解析、冷缓存乐观启用、后台预热、负缓存置灰、手填路径失效提示这几条语义
# 由共享代码一次性给出，新键不该各写一遍。

_PLAYER_KEYS = ("netease", "qqmusic", "kugou", "soda")


def _player_entry_labels() -> dict[str, str]:
    """播放器键 → 菜单项文案（文案取自 ``music_players`` 注册表的显示名）。"""
    from pet import music_players

    return {
        key: f"打开{music_players.player_label(key)}给主人放歌"
        for key in _PLAYER_KEYS
    }


def _full_menu_pet(values=None):
    """构建整棵真实菜单用的最小宿主替身（口径同 test_default_layout_...）。"""
    from PySide6.QtGui import QPixmap

    class _Cfg:
        def __init__(self, seed):
            self.values = dict(seed)

        def get(self, key, default=None):
            return self.values.get(key, default)

        def set(self, key, value):
            self.values[key] = value

        def save(self):
            return None

    class _Pet:
        cfg = _Cfg({
            "context_menu_layout": None,
            "character": "shenshen",
            "on_top": True,
            "agent_link": {},
            "music_lyric_enabled": True,
            **(values or {}),
        })
        idles = ["待机"]
        turns = moves = clicks = acts = []
        playback_speed = scale = 1.0
        drag_physics = no_move = mouse_through = False

        def icon_pixmap(self, size=64):
            pixmap = QPixmap(size, size)
            pixmap.fill()
            return pixmap

        def __getattr__(self, _name):
            return lambda *args, **kwargs: None

    return _Pet()


def _build_full_menu(monkeypatch, pet):
    """按默认布局建一棵真实菜单（窗口侧与 overlay 侧共用这一条路径）。"""
    from PySide6.QtWidgets import QApplication, QMenu

    from pet import catalog
    from pet.context_menu import populate_context_menu
    from pet.context_menus import shared

    monkeypatch.setattr(shared.autostart_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(catalog, "list_available_characters", lambda: ["shenshen"])
    QApplication.instance() or QApplication([])
    menu = QMenu()
    populate_context_menu(menu, pet)
    return menu


def _music_entries(menu) -> dict:
    """音乐子菜单：文案 → QAction。"""
    submenu = next(a.menu() for a in menu.actions() if a.text() == "音乐")
    return {a.text(): a for a in submenu.actions() if not a.isSeparator()}


def _wait_until(predicate, *, timeout: float = 15.0) -> bool:
    """轮询等待（事件同步 + 宽预算，不赌固定 sleep 时序）。"""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def _save_player_cache():
    from pet import music_players

    saved = dict(music_players._cache)
    with music_players._warm_lock:
        inflight = set(music_players._warm_inflight)
    music_players.clear_cache()
    return saved, inflight


def _restore_player_cache(saved) -> None:
    from pet import music_players

    cache, inflight = saved
    music_players.clear_cache()
    music_players._cache.update(cache)
    with music_players._warm_lock:
        music_players._warm_inflight.clear()
        music_players._warm_inflight.update(inflight)
















