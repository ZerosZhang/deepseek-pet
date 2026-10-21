# -*- coding: utf-8 -*-
"""Modern-inspired sidebar settings panel used by the modern context menu.

拆分后的主对话框模块：ModernSettingsDialog 及对话框装配/配置写回逻辑留守本文件。
控件库 / 菜单布局编辑器 / AI 设置页 / 主题 QSS 已按结构线拆至
settings_widgets / settings_menu_layout_editor / chat/ai_settings_page / settings_theme_qss。
本文件保留这些符号的 re-export，供 tests 与 pet/ 既有调用向后兼容。
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

import shiboken6


from PySide6.QtCore import QEvent, QFileInfo, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QClipboard,
    QFontDatabase,
    QKeySequence,
    QShortcut,
    QIcon,
    QImageReader,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QDialog,
    QColorDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QLayout,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import autostart as autostart_mod
from . import catalog
from .click_sound import warm_click_sound_effects
from .config import (
    DEFAULT_CONTEXT_MENU_APPEARANCE,
    DEFAULT_SELF_TALK_BUBBLE_STYLE,
    DEFAULT_SELF_TALK_DURATION_SECONDS,
    DEFAULT_SELF_TALK_MAX_INTERVAL,
    DEFAULT_SELF_TALK_MIN_INTERVAL,
    DEFAULT_SELF_TALK_TEXTS,
    _float_or_default,
)
from .context_menus.icons import (
    CUSTOM_ICON_SUFFIXES,
    custom_icon_file_error,
    vector_widget_icon,
)
from .context_menus.registry import CUSTOM_ICON_CHOICES, MENU_ACTIONS
from .menu_layout import (
    load_default_menu_layout,
    materialize_implicit_separators,
    merge_default_menu_actions,
    resolve_menu_layout,
)
from . import settings_close_flow
from .application_icon import load_application_icon
from .settings_slot_config import route_settings_config
from .speech_bubble import BUBBLE_STYLE_PRESETS


from .settings_widgets import (
    _system_font_families,
    BROWSER_CONTROL_SPEC,
    SETTINGS_DOMAIN_NAV,
    BROWSER_CONTROL_STYLESHEET,
    _widget_dark,
    reveal_settings_row,
    ToggleSwitch,
    IMAGE_NAME_FILTER,
    AUDIO_NAME_FILTER,
    ClickSoundPackPicker,
    MasonryLayout,
    MasonryImageCard,
    MasonryFlow,
    ImagePreviewDrawer,
    ResourcePathPicker,
    ColorSwatchButton,
    ColorPicker,
    _draw_chevron,
    SETTINGS_POPUP_OBJECT_NAME,
    SETTINGS_POPUP_STYLESHEET,
    _DARK_POPUP_OVERRIDE,
    settings_popup_stylesheet,
    configure_settings_action_popup,
    SettingsPopupAction,
    SettingsPopupMenu,
    SettingsMenuButton,
    ModernSelect,
    BrowserSpinBox,
    BrowserDoubleSpinBox,
    CONTENT_READING_MAX_WIDTH,
    CollapsibleGroup,
    SettingRow,
    ResponsiveActionRow,
    ResponsiveToggleActionRow,
    SettingsCard,
    SettingsDisclosureHeader,
    SettingsSection,
    SettingsSidebarPane,
    refresh_settings_icons,
    settings_save_exit_button,
    settings_sidebar_item,
    _CurrentPageStack,
    SettingsTabContainer,
    _SettingsPageShell,
    _line_edit,
    _system_dark,
)
from .settings_theme_qss import _settings_stylesheet
from .settings_menu_layout_editor import MenuLayoutEditor
from .persona_template import (
    CONDITIONAL_PARAMETERS,
    PARAMETERS,
)
from . import settings_default_marks
from . import settings_interaction
from . import settings_page_guide
from . import settings_pet_controls
from . import settings_quiet
from . import settings_reset_defaults
from . import settings_search


# 语言配置页只展示用户能理解的事件名称；内部 key 仍用于保存和渲染。
DIALOGUE_LABELS = {
    "start": "开始工作",
    "thinking": "思考",
    "activity.read": "读取文件",
    "activity.search": "搜索或查找",
    "activity.edit": "编辑代码",
    "activity.run": "运行或测试",
    "activity.default": "其他工具操作",
    "agent.attention": "需要用户处理",
    "agent.error": "Agent 出错",
    "agent.missing": "未找到 Agent",
    "bridge.install.pending": "安装桥接中",
    "bridge.install.success": "桥接安装成功",
    "bridge.install.failed": "桥接安装失败",
    "bridge.uninstall.failed": "桥接卸载失败",
    "approval.tool": "审批工具",
    "approval.generic": "审批提示",
    "question.empty": "等待选择",
    "question.one": "单个用户问题",
    "question.many": "多个用户问题",
    "model_access.one": "模型访问失败（单次）",
    "model_access.many": "模型访问失败（连续）",
    "llm_error.api": "AI 服务错误",
    "done.success": "任务完成",
    "done.attention": "任务暂停待确认",
    "failure.retry": "重试后失败",
    "failure.tool": "工具执行失败",
    "failure.generic": "执行失败",
    "balance.loading": "查询余额中",
    "balance.result": "余额结果",
}

DIALOGUE_PARAMS = {
    "name": "Agent 名称",
    "command": "命令文本（已退役：恒隐藏）",
    "label": "标签（工具标签/会话标签随事件而定）",
    "body": "问题内容",
    "count": "数量",
    "reasons": "判断原因（已退役：恒隐藏）",
    "detail": "错误详情",
    "text": "显示文本",
    "event": "未知事件名（bridge.unknown）",
    "tool": "原始工具名",
    "callId": "工具调用 ID",
    "step": "步骤序号",
    "toolName": "审批原始工具名",
    "argsKey": "工具参数摘要键（已退役：恒隐藏）",
    "sessionName": "会话显示名",
    "projectName": "项目名",
    "errorCode": "错误码（llm_error 为上游真实码，如 bad_response_status_code）",
    "errorMessage": "错误信息原文",
    "errorKind": "错误分类（api=AI API 请求失败）",
    "consecutiveRetryCount": "连续模型访问失败次数",
    "retry": "重试序号",
    "retries": "已重试次数",
    "retryExhausted": "是否重试耗尽",
    "failureType": "失败类型",
}

# 与 persona_template.PARAMETERS 保持同一真相源：调用点注入什么，这里就宣称什么。
DIALOGUE_KEY_PARAMS = dict(PARAMETERS)

def dialogue_params_hint(key: str) -> str:
    """「可用参数」提示文案：区分保证注入与条件注入（仅上游记录提供时可用）。"""
    params = DIALOGUE_KEY_PARAMS.get(key, ())
    if not params:
        return ""
    text = "、".join("{" + item + "}（" + DIALOGUE_PARAMS[item] + "）" for item in params)
    conditional = [item for item in params if item in CONDITIONAL_PARAMETERS.get(key, ())]
    if conditional:
        text += "；其中 " + "、".join("{" + item + "}" for item in conditional) + " 仅在上游记录提供时可用"
    return text


class ModernSettingsDialog(QDialog):
    """Settings window matching Modern's sidebar and rounded-card hierarchy."""

    def __init__(self, config, parent=None, *,
                 standalone: bool = False, initial_page: str | None = None):
        super().__init__(parent)
        # slot 设置页（含 #271 起的主宠页 = slot0 页）：非 per-slot 键直读**主**配置
        #（而不是 slot 文件里的无效快照），保存时按同一分流写回。
        # 见 pet/settings_slot_config.py 的模块 docstring。
        config = route_settings_config(config)
        # 每张表单一份**独立编辑视图**（草稿 + 编辑代次基线各自一份，运行期那份保持只读）：
        # 复用运行期那份会让"旧表单钉住的代次"跨窗存活，重开设置永远存不进去。
        opener = getattr(config, "new_form_view", None)
        self.config = config = opener() if callable(opener) else config
        # standalone=True：本对话框跑在独立设置进程（python -m pet --settings）里，
        # 没有桌宠窗口/AppShell 可依附。只影响下面几处显式分支，默认 False 时
        # 全部行为与改动前逐位一致。
        self.standalone = bool(standalone)
        self.initial_page = str(initial_page or "").strip()
        self.setProperty("modernStyle", True)
        self.setProperty("menuStyle", "modern")
        self.setWindowTitle("桌宠设置")
        # 原生标题栏的图标：不设的话 Windows 摆的是系统给的通用图标（--icon 只写进
        # 可执行文件/应用包的文件图标资源，与窗口属性是两回事）。拿不到时是空图标。
        self.setWindowIcon(load_application_icon())
        self.resize(800, 560)
        self.setMinimumSize(720, 500)
        self._positioned_away = False
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(13)
        self.setFont(font)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar_pane = SettingsSidebarPane(self)
        sidebar_layout = QVBoxLayout(sidebar_pane)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        # 间距 3px + 导航行距 1px：slot 页有两个重置按钮时，默认窗口 800×560 下 10 个
        # 能力域要全落在视口里；3px 把本机余量 4 → 19px（CI 280：Ubuntu 上 6px 不够）。
        sidebar_layout.setSpacing(3)
        # 「保存并退出」的图标 / 保存时机 tooltip / 焦点旗标都在控件库里（本文件有行数预算）。
        self.save_exit_button = settings_save_exit_button(sidebar_pane, self._save)
        sidebar_layout.addWidget(self.save_exit_button)
        self.search_edit = QLineEdit(sidebar_pane)
        self.search_edit.setObjectName("settingsSearch")
        self.search_edit.setPlaceholderText("搜索设置…")
        self.search_edit.addAction(
            # 宿主就是搜索框自己：记在它身上的请求换主题后重画（QLineEdit 无 setIcon）。
            vector_widget_icon(self.search_edit, "search", 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search_edit.installEventFilter(self)
        sidebar_layout.addWidget(self.search_edit)
        self.search_status = QLabel("", sidebar_pane)
        self.search_status.setObjectName("searchStatus")
        self.search_status.setWordWrap(True)
        self.search_status.hide()
        sidebar_layout.addWidget(self.search_status)
        self.sidebar = QListWidget(sidebar_pane)
        self.sidebar.setObjectName("settingsSidebar")
        self.sidebar.setIconSize(QSize(18, 18))
        # 导航行距 1px：与上面的侧栏间距一起把 10 个能力域收进默认窗口高度。
        self.sidebar.setSpacing(1)
        sidebar_layout.addWidget(self.sidebar, 1)
        # 全局兜底入口（命令而非偏好项，故放侧栏底部；实现在 settings_reset_defaults.py）。
        settings_reset_defaults.create_reset_button(self, sidebar_layout)
        self.version_footer = QLabel(f"版本 v{__version__}", sidebar_pane)
        self.version_footer.setObjectName("settingsVersion")
        self.version_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_footer.setToolTip("当前运行版本")
        sidebar_layout.addWidget(self.version_footer)

        self.pages = QStackedWidget(self)
        body.addWidget(sidebar_pane)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

        self._build_pet_controls()
        general_content = QWidget()
        general_layout = QVBoxLayout(general_content)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(18)
        # 「开机自启」的作用域声明由 settings_pet_controls 的作用域 pass 拆成行内标注
        # （挂在标签那一行，不占额外一行），说明与拆分机制同一处（GLOBAL_SCOPE_ROWS）。
        launch_rows = [
            SettingRow("autostart", "开机自启", "登录系统后自动启动桌宠。", self.autostart_check),
        ]
        if sys.platform == "darwin":
            launch_rows.append(
                SettingRow(
                    "dock_icon",
                    "显示 Dock 图标",
                    "在 macOS Dock 中显示桌宠应用；关闭后仍可通过桌宠和托盘操作。",
                    self.dock_icon_check,
                )
            )
        general_layout.addWidget(SettingsSection("应用启动", launch_rows, general_content))
        window_rows = [
            SettingRow("on_top", "窗口置顶", "始终将桌宠保持在其他窗口上方。", self.on_top_check),
        ]
        if sys.platform == "win32":
            window_rows.extend(
                [
                    SettingRow("auto_hide_fullscreen", "全屏时自动隐藏", "全屏游戏或视频期间自动隐藏桌宠。", self.auto_hide_fullscreen_check),
                    SettingRow(
                        "cursor_hidden_passthrough",
                        "光标隐藏时自动穿透",
                        "Windows 光标隐藏后，桌宠自动穿透点击；光标出现立即恢复。适用于游戏，也可能影响自动隐藏光标的视频播放器。",
                        self.cursor_hidden_passthrough_check,
                    ),
                ]
            )
        # 「允许桌宠跨屏」不分平台（三端都有多显示器），排在窗口旗标类之后：前面几条
        # 讲"窗口怎么摆"，它讲"桌宠能不能到别的显示器去"（行序见常规域装配的 claim 表）。
        window_rows.append(
            SettingRow(
                "cross_screen",
                "允许桌宠跨屏",
                settings_pet_controls.CROSS_SCREEN_HINT,
                self.cross_screen_check,
            )
        )
        general_layout.addWidget(SettingsSection("窗口与系统", window_rows, general_content))
        # 拓扑收口：「单进程多开」实验开关已从设置页移除，4.4b 起配置键
        # `experimental_single_process_spawn` 本身也随多进程多宠退役层删除
        # （进程内多窗是唯一多宠形态，不再是可切换的实验开关）。
        if self.balance_refresh_spin is not None:
            general_layout.addWidget(
                SettingsSection(
                    "后台服务",
                    [
                        SettingRow("balance_refresh", "余额自动刷新", "设置后台刷新间隔；0 分钟表示关闭。", self.balance_refresh_spin),
                        SettingRow("balance_tier_mode", "高峰 / 空闲时段提示", "选择 DeepSeek 高峰/空闲提示的显示风格。", self.balance_tier_mode_select),
                        SettingRow(
                            "balance_tier_peak", "高峰自定义文本", "仅“自定义”模式生效；留空回退默认“高峰”。", self.balance_tier_peak_edit, stacked=True
                        ),
                        SettingRow(
                            "balance_tier_idle", "空闲自定义文本", "仅“自定义”模式生效；留空回退默认“空闲”。", self.balance_tier_idle_edit, stacked=True
                        ),
                        SettingRow(
                            "balance_tier_color",
                            "峰谷提示颜色",
                            "开启后高峰显示红色、低谷显示绿色；关闭则使用普通气泡文字颜色。",
                            self.balance_tier_color_check,
                        ),
                    ],
                    general_content,
                )
            )
        general_layout.addStretch(1)
        self._add_page("常规", "settings", self._page_shell("常规", general_content))

        behavior_content = QWidget()
        behavior_layout = QVBoxLayout(behavior_content)
        behavior_layout.setContentsMargins(0, 0, 0, 0)
        behavior_layout.setSpacing(16)
        behavior_layout.addWidget(
            SettingsSection(
                "动画",
                [
                    # F06：``playback_speed`` 是**每宠**键（``PER_PET_KEYS``，B7b 起
                    # 右键菜单的速率也只改被点的那一只），文案不许再说"所有桌宠"。
                    SettingRow("playback_speed", "播放速率", "控制这只桌宠动画的播放速度。", self.speed_select),
                    SettingRow("animation_gap", "动作等待间隔", "非待机动作之间的休息时间；0 秒表示连续播放。", self.gap_spin),
                    SettingRow(
                        "idle_low_fps",
                        "省电模式",
                        settings_pet_controls.idle_low_fps_hint(),
                        self.idle_low_fps_check,
                    ),
                    SettingRow("no_move", "不移动", "暂停桌宠在桌面上的自动移动。", self.no_move_check),
                    # 鼠标穿透行归「互动 · 输入」（settings_interaction 构建）。
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsSection(
                "拖拽与弹射",
                [
                    SettingRow("drop_gravity", "静止放手下落", "松开鼠标时如果宠物几乎没移动，它不再停在半空，而是自然落下、落地静止；贴地松手不会弹起。与「拖动物理」无关：关掉拖动物理后甩出惯性依然不生效。", self.drop_gravity_check),
                    SettingRow("throw_strength", "甩出力度", "控制桌宠被甩出或弹射发射时的最大速度限制。", self.throw_strength_select),
                    SettingRow("slingshot_enabled", "弹弓弹射", "拖拽桌宠时点击右键进入蓄力瞄准，松开左键弹射飞出（Esc或右键取消）。", self.slingshot_check),
                    SettingRow("lock_position", "锁定位置", "桌宠固定不动，无法拖动（点击互动仍有效）。", self.lock_position_check),
                    SettingRow("shift_drag", "SHIFT+左键拖动", "开启后必须按住 SHIFT 再左键才能拖动桌宠。", self.shift_drag_check),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsSection(
                "边缘探头",
                [
                    SettingRow(
                        "edge_probe", "边缘探头", "拖到屏幕左/右边缘后自动以 45° 探头姿态窥视；点击真实角色会拉直约 5 秒后自动退回。", self.edge_probe_check
                    ),
                ],
                behavior_content,
            )
        )
        # 「点击反馈」与「自言自语」两组归「互动」域（settings_interaction 构建，
        # 行数预算原因；组名与顺序的既有契约见 tests/test_menu_layout.py）。
        labels = DIALOGUE_LABELS
        behavior_layout.addWidget(
            SettingsSection(
                "表达风格",
                [
                    SettingRow(
                        "dialogue_mode",
                        "表达风格",
                        "控制桌宠自言自语、候选内容和主动气泡的说话方式；同时覆盖 Agent 状态、审批、提问、错误、模型访问失败等所有气泡。内置「默认模式」与「鲸鱼娘女仆模式」不可编辑；选择「自定义台词」后，可粘贴下方 JSON 一键导入全部弹窗文案。",
                        self.dialogue_mode_select,
                    ),
                    SettingRow(
                        "dialogue_scope",
                        "专属文案对象(仅在自定义模式生效)",
                        "下方逐事件编辑针对的对象：默认（全局文案）或某 Agent 的专属文案。留空的事件自动沿用全局（或默认模式）文案。",
                        self.dialogue_scope_select,
                        stacked=True,
                    ),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsCard(
                [
                    SettingRow(
                        "dialogue_template_actions",
                        "弹窗文案模板（JSON）",
                        "一键复制当前全部弹窗内容模板到剪贴板；把复制的 JSON 粘贴回「导入模板」可一次覆盖所有「自定义台词」，也可以直接发给 AI 依角色卡改写。事件留空时自动沿用默认模式文案；模板占位符会自动读取上游事件字段。",
                        self.dialogue_template_actions,
                        stacked=True,
                    ),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsCard(
                [
                    SettingRow(
                        f"dialogue_{key}",
                        labels.get(key, key),
                        "留空则使用基础模式台词。可用参数：" + (dialogue_params_hint(key) or "无"),
                        edit,
                        stacked=True,
                    )
                    for key, edit in self.dialogue_phrase_edits.items()
                ],
                behavior_content,
            )
        )
        behavior_layout.addStretch(1)
        self._add_page("桌宠行为", "play", self._page_shell("桌宠行为", behavior_content))

        appearance_content = QWidget()
        appearance_layout = QVBoxLayout(appearance_content)
        appearance_layout.setContentsMargins(0, 0, 0, 0)
        appearance_layout.setSpacing(16)
        appearance_layout.addWidget(
            SettingsSection(
                "桌宠显示",
                [
                    SettingRow("scale", "桌宠大小", "调整桌宠在桌面上的显示尺寸。", self.scale_combo),
                    SettingRow(
                        "bubble_text_scale",
                        "气泡文字大小",
                        "气泡里文字的显示尺寸：气泡与字号一起等比放大（100% 为默认）。"
                        "大屏上嫌气泡字小时调大；审批/提问气泡为固定布局，不随本项变化。",
                        self.bubble_text_scale_spin,
                    ),
                    SettingRow("pet_opacity", "不透明度", "调整桌宠窗口的整体透明度；100% 为完全不透明。", self.pet_opacity_spin),
                    # 「气泡方案」行归「互动 · 自言自语」（settings_interaction 构建）。
                ],
                appearance_content,
            )
        )
        appearance_layout.addWidget(
            SettingsSection(
                "菜单外观",
                [
                    SettingRow("menu_theme", "颜色主题", "可跟随系统，或固定使用浅色/深色菜单。", self.menu_theme_select),
                    SettingRow("menu_density", "菜单密度", "调整新版右键菜单的菜单项高度和分组留白。", self.menu_density_select),
                    SettingRow("menu_radius", "圆角大小", "调整新版右键菜单和子菜单的外轮廓圆角。", self.menu_radius_select),
                    SettingRow("menu_font", "UI 字体", "设置新版菜单使用的界面字体。", self.menu_font_select),
                    SettingRow("menu_font_size", "UI 字号", "同步调整主菜单与多级菜单的字号。", self.menu_font_size_select),
                    SettingRow("menu_translucent", "半透明菜单", "使用接近 Modern 的半透明浮层表面。", self.menu_translucent_check),
                    SettingRow("menu_opacity", "表面不透明度", "调整菜单背景透出桌面内容的程度。", self.menu_opacity_spin),
                ],
                appearance_content,
            )
        )
        appearance_layout.addWidget(
            SettingsSection(
                "浅色主题",
                [
                    SettingRow("light_background", "背景色", "浅色菜单的浮层背景。", self.light_background_picker),
                    SettingRow("light_foreground", "文字色", "浅色菜单的主要文字与图标颜色。", self.light_foreground_picker),
                    SettingRow("light_hover", "悬停色", "鼠标悬停菜单项时的背景。", self.light_hover_picker),
                ],
                appearance_content,
            )
        )
        appearance_layout.addWidget(
            SettingsSection(
                "深色主题",
                [
                    SettingRow("dark_background", "背景色", "深色菜单的浮层背景。", self.dark_background_picker),
                    SettingRow("dark_foreground", "文字色", "深色菜单的主要文字与图标颜色。", self.dark_foreground_picker),
                    SettingRow("dark_hover", "悬停色", "鼠标悬停菜单项时的背景。", self.dark_hover_picker),
                ],
                appearance_content,
            )
        )
        appearance_layout.addStretch(1)
        self._add_page("外观", "appearance", self._page_shell("外观", appearance_content))

        menu_content = QWidget()
        menu_page_layout = QVBoxLayout(menu_content)
        menu_page_layout.setContentsMargins(0, 0, 0, 0)
        menu_page_layout.setSpacing(18)
        menu_available_actions = set(MENU_ACTIONS.ids)
        self.menu_available_actions = frozenset(menu_available_actions)
        menu_enabled_actions = set(menu_available_actions)
        self.menu_layout_editor = MenuLayoutEditor(
            self.config.get("context_menu_layout"),
            menu_content,
            available_actions=menu_available_actions,
            enabled_actions=menu_enabled_actions,
        )
        menu_page_layout.addWidget(
            SettingsSection(
                "内容与布局",
                [
                    SettingRow("context_menu_layout", "菜单编排", "调整显示、顺序和层级；左侧编辑，右侧同步预览。", self.menu_layout_editor, stacked=True),
                ],
                menu_content,
            )
        )
        menu_page_layout.addStretch(1)
        self._add_page("菜单", "application", self._page_shell("菜单", menu_content))

        # AI rows are composed directly into the final capability domain by
        # _rebuild_domain_navigation. Do not temporarily hand the controller
        # widget to a QScrollArea: that creates a second Qt ownership path when
        # its rows are reparented into the shared card system.

        # 节日提醒设置页（行在 _rebuild_domain_navigation 中拾入「自动化与联动」域）
        from .festival_settings import FestivalSettingsPage

        self.festival_page = FestivalSettingsPage(self.config, self)

        # 更新页是命令/状态面板，不写入 Config；它与常规域同级，便于从菜单
        # 和设置窗口进入同一套检查、下载、校验、安装流程。
        self._rebuild_domain_navigation()
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(0)
        if self.initial_page:
            self.select_page(self.initial_page)
        # 索引口径：标准设置行 + 「更新」页的作者账号行（后者不是 SettingRow，
        # 但暴露同名的 label/hint_label，故同一套匹配函数就能覆盖；侧栏命令类
        # 控件仍不进索引——那是 docs/SETTINGS-CHANGE-GATES.md 里的既有决定）。
        self._search_rows = self.findChildren(SettingRow)
        self._search_matches: list[SettingRow] = []
        self._search_index = -1
        self.search_edit.textChanged.connect(self._search_settings)
        # Ctrl+F：设置窗内任意位置把光标送进搜索框（浏览器/编辑器的一致习惯）。
        # 不抢输入框自己的按键：焦点已经在搜索框时 Qt 不会再触发这条快捷方式。
        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find_shortcut.activated.connect(self._focus_search_box)

        self.self_talk_check.toggled.connect(self._update_self_talk_controls)
        self.menu_translucent_check.toggled.connect(self._update_translucency_controls)
        self.golden_spin_click_check.toggled.connect(self._update_golden_spin_controls)
        self.click_self_talk_check.toggled.connect(self._update_click_self_talk_controls)
        self._update_self_talk_controls(self.self_talk_check.isChecked())
        self._update_click_self_talk_controls(self.click_self_talk_check.isChecked())
        self._update_translucency_controls(self.menu_translucent_check.isChecked())
        self._sync_menu_action_states()
        # 初始同步须在全部 SettingRow 构建完成后执行，否则 findChild 找不到行
        self._update_click_sound_controls(self.click_sound_check.isChecked())
        self._update_golden_spin_controls(self.golden_spin_click_check.isChecked())

        self.menu_theme_select.currentIndexChanged.connect(self._apply_selected_theme)
        self._apply_selected_theme()
        # 行全部就位后收敛台词编辑可见性：初始层若为某 Agent 专属则隐藏公共事件行
        settings_pet_controls._apply_dialogue_scope_rows(self)
        # 行全部就位后标注窗口级键的生效范围（overlay 一窗多宠：只有子宠页需要）
        settings_pet_controls._apply_window_scope_rows(self)
        if self.standalone:
            # 独立进程本地宿主：试听改本地播放、节日试听本地演示、无 parent 时
            # 读 runtime 状态文件避让桌宠。逻辑全在 pet/settings_standalone.py，
            # 这里只做接线（本文件有行数预算）。
            from .settings_standalone import install_standalone_hooks

            install_standalone_hooks(self)
        # 全部行（含域导航重建时才造出来的文件识别行）就位后再装「已修改」标记
        settings_default_marks.install(self)

    def _sync_menu_action_states(self, *_args) -> None:
        enabled = set(self.menu_available_actions)
        self.menu_layout_editor.set_enabled_actions(enabled)

    def _build_pet_controls(self) -> None:
        """Compatibility delegation (settings_pet_controls.build_pet_controls)."""
        settings_pet_controls.build_pet_controls(self)

    def _update_self_talk_controls(self, enabled: bool) -> None:
        """周期气泡（``self_talk``）的细项显隐。

        点击侧（``click_self_talk*`` / ``click_talk_bindings``）**不在这里**：它们是
        独立开关的后续项，见 :meth:`_update_click_self_talk_controls`。绑在一起会让
        「只想点击听声」的用户在设置页里连开关都看不到。

        节奏项（最短/最长间隔、配图大小）只属于周期链路，仍只跟本开关；内容项
        （显示时间/候选内容/图片目录/配图概率）两条链路**共读同一份配置**——点击
        自言自语落地的 ``window_alerts.show_click_self_talk`` 读的正是这批键——所以
        它们跟 :meth:`_update_self_talk_content_controls` 走「任一开启」。
        """
        self._set_setting_rows_visible(
            ("self_talk_min", "self_talk_max", "self_talk_image_scale"),
            enabled,
            dependency="self_talk",
        )
        self._update_self_talk_content_controls(enabled)

    def _update_self_talk_content_controls(self, self_talk_enabled: bool) -> None:
        """内容项显隐：周期气泡与点击自言自语**任一**开启就显示。

        这些键是两条链路共用的内容源（候选文本 / 图片目录 / 配图概率 / 显示时长）。
        旧模型把显隐整组挂在周期开关上，只开点击的用户必须先打开一个他不用的周期
        功能才能编辑候选文本——消费侧早已解耦（``show_click_self_talk`` 不看
        ``self_talk_enabled``），显隐跟着解耦。
        """
        self._set_setting_rows_visible(
            (
                "self_talk_duration",
                "self_talk_texts",
                "self_talk_images",
                "self_talk_image_chance",
            ),
            self_talk_enabled or self.click_self_talk_check.isChecked(),
            dependency="self_talk_content",
        )

    def _update_click_self_talk_controls(self, enabled: bool) -> None:
        """点击自言自语（``click_self_talk``）的后续项显隐。

        台词绑定只属于点击链路，点击开关关着时没有意义。内容项与周期气泡共用，
        见 :meth:`_update_self_talk_content_controls`（任一开启即显示）。
        """
        keys = (
            "click_talk_bindings",
        )
        self._set_setting_rows_visible(keys, enabled, dependency="click_self_talk")
        self._update_self_talk_content_controls(self.self_talk_check.isChecked())

    def _set_setting_rows_visible(
        self,
        keys: tuple[str, ...],
        visible: bool,
        *,
        dependency: str = "parent",
    ) -> None:
        """Show dependent settings as a complete group and repair card dividers."""
        cards: set[SettingsCard] = set()
        sections: set[SettingsSection] = set()
        for key in keys:
            row = self.findChild(SettingRow, f"settingRow_{key}")
            if row is None:
                continue
            dependencies = getattr(row, "_visibility_dependencies", {})
            dependencies[dependency] = bool(visible)
            row._visibility_dependencies = dependencies
            row.setVisible(all(dependencies.values()))
            card = row.parentWidget()
            if isinstance(card, SettingsCard):
                cards.add(card)
                section = card.parentWidget()
                if isinstance(section, SettingsSection):
                    sections.add(section)
        for section in sections:
            section.refresh_dependency_visibility()
        for card in cards:
            card.refresh_separators()

    def _populate_menu_fonts(self) -> None:
        if shiboken6.isValid(self) is False or self._menu_fonts_populated:
            return
        self._menu_fonts_populated = True
        appearance = self.config.get("context_menu_appearance", DEFAULT_CONTEXT_MENU_APPEARANCE)
        for family in _system_font_families():
            if self.menu_font_select.findData(family) < 0:
                self.menu_font_select.addItem(family, family)
        current_font = str(appearance.get("ui_font") or "system")
        if self.menu_font_select.findData(current_font) < 0:
            self.menu_font_select.addItem(current_font, current_font)
        self.menu_font_select.setCurrentData(current_font)

    def _open_click_talk_bindings(self) -> None:
        from .click_talk_dialog import ClickTalkBindingsDialog

        click_names = None
        parent = self.parent()
        if parent is not None and hasattr(parent, "clicks") and parent.clicks:
            click_names = list(parent.clicks)
        dialog = ClickTalkBindingsDialog(self.config, click_names=click_names, parent=self)
        dialog.exec()

    def _preview_click_sound(self) -> None:
        """试听当前选择的点击音效配置（不保存配置）。"""
        from .click_sound import choose_sound, play_sound, resolve_click_sound_candidates

        pack = self.click_sound_picker.value()
        candidates = resolve_click_sound_candidates(pack, self.config.dir)
        sound_file = choose_sound(candidates)
        if sound_file:
            vol = float(self.click_sound_volume_spin.value()) / 100.0
            play_sound(sound_file, volume=vol)

    def _import_dialogue_template_json(self) -> None:
        """Import a complete persona template from the inline JSON editor."""
        settings_pet_controls._import_dialogue_template_json(self)

    def _dialogue_flush_scope(self, scope: str | None = None) -> None:
        """把当前编辑区的文本快照写回 scope buffer（切换/保存前调用）。"""
        settings_pet_controls._dialogue_flush_scope(self, scope)

    def _on_dialogue_scope_changed(self, index: int) -> None:
        """切换 global/某 Agent 专属文案编辑层：flush 当前层后载入目标层内容。"""
        settings_pet_controls._on_dialogue_scope_changed(self, index)

    def _dialogue_scope_values(self, scope: str) -> dict[str, list[str]]:
        """scope buffer 某层的非空事件 → list[str]（供保存/导出）。"""
        return settings_pet_controls._dialogue_scope_values(self, scope)

    def _dialogue_phrase_values(self) -> dict[str, list[str]]:
        return settings_pet_controls._dialogue_phrase_values(self)

    def _current_dialogue_template(self) -> dict:
        return settings_pet_controls._current_dialogue_template(self)

    def _export_dialogue_template(self) -> None:
        """Export the complete current template to the clipboard (no file dialog)."""
        settings_pet_controls._export_dialogue_template(self)

    def _update_click_sound_controls(self, enabled: bool) -> None:
        for row_key in ("click_sound_pack", "click_sound_volume", "click_sound_preview"):
            row = self.findChild(SettingRow, f"settingRow_{row_key}")
            if row is not None:
                row.setVisible(bool(enabled))
                card = row.parentWidget()
                if isinstance(card, SettingsCard):
                    card.refresh_separators()

    def _update_golden_spin_controls(self, enabled: bool) -> None:
        """“点击触发黄金回旋”总开关控制“跳过动画”子开关可见性。"""
        row = self.findChild(SettingRow, "settingRow_golden_spin_direct")
        if row is not None:
            row.setVisible(bool(enabled))
            card = row.parentWidget()
            if isinstance(card, SettingsCard):
                card.refresh_separators()

    def _update_translucency_controls(self, enabled: bool) -> None:
        self._set_setting_rows_visible(("menu_opacity",), enabled)

    def _apply_click_sound_enabled_now(self, checked: bool) -> None:
        """点击音效开关即时生效，不等对话框关闭（写盘前 reload，理由同上）。"""
        self.config.reload()
        self.config.set("click_sound_enabled", bool(checked))
        self.config.save()
        if bool(checked):
            # 开启后立即预热，保证不关闭对话框直接试听/点击也有声音。
            warm_click_sound_effects(
                self.config.get("click_sound_pack"),
                data_dir=self.config.dir,
            )

    def move_away_from_pet(self) -> None:
        """把窗口定位到不与桌宠相交的位置。

        在 show() 之前调用（_present_dialog 的 before_present），窗口首帧
        即落在最终位置，避免 Windows 上"先显示默认位置再跳走"的两段式。
        """
        if self._positioned_away:
            return
        self._positioned_away = True
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            self._move_away_from(parent.geometry())
            return
        if self.standalone:
            # 独立进程没有桌宠窗口：改读配置目录 runtime 状态文件取桌宠位置；
            # 读不到返回 None，保持默认位置（不许崩、也不许静默乱跳）。
            from .settings_standalone import standalone_pet_geometry

            pet_geo = standalone_pet_geometry(self.config)
            if pet_geo is not None:
                self._move_away_from(pet_geo)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().showEvent(event)
        # 兜底：未经 _present_dialog 直接 show 的路径仍要避让桌宠
        self.move_away_from_pet()
        if not getattr(self, "_initial_focus_assigned", False):
            self._initial_focus_assigned = True
            self.sidebar.setFocus(Qt.FocusReason.OtherFocusReason)

    def _move_away_from(self, pet_geo: QRect) -> None:
        """首次显示时把窗口移到不与桌宠相交的位置（右侧优先，再左侧/下方/上方）"""
        size = self.size()
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else QRect()
        for rect in (
            QRect(pet_geo.right() + 12, pet_geo.top(), size.width(), size.height()),
            QRect(pet_geo.left() - 12 - size.width(), pet_geo.top(), size.width(), size.height()),
            QRect(pet_geo.left(), pet_geo.bottom() + 12, size.width(), size.height()),
            QRect(pet_geo.left(), pet_geo.top() - 12 - size.height(), size.width(), size.height()),
        ):
            if avail.contains(rect):
                self.move(rect.topLeft())
                return

    def _page_shell(self, title: str, content: QWidget) -> QWidget:
        # 默认最大阅读宽度见 CONTENT_READING_MAX_WIDTH；「菜单」域的内容自己声明更宽的值。
        content_max_width = int(content.property("contentMaxWidth") or CONTENT_READING_MAX_WIDTH)
        page = _SettingsPageShell(content_max_width, self.pages)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 28, 20)
        layout.setSpacing(12)
        heading_host = QWidget(page)
        heading_host.setObjectName("pageHeader")
        heading_host.setMaximumWidth(content_max_width)
        heading_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        heading_layout = QVBoxLayout(heading_host)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(0)
        heading = QLabel(title, heading_host)
        heading.setObjectName("pageTitle")
        heading_layout.addWidget(heading)
        page.heading_host = heading_host
        layout.addWidget(heading_host, 0, Qt.AlignmentFlag.AlignHCenter)
        scroll = QScrollArea(page)
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        content.setMaximumWidth(content_max_width)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def select_page(self, label: str) -> bool:
        """按侧栏标题选中页面，供右键菜单/更新通知做深链接。"""
        target = str(label or "").strip()
        for index in range(self.sidebar.count()):
            if self.sidebar.item(index).text() == target:
                self.sidebar.setCurrentRow(index)
                return True
        return False

    def _add_page(self, label: str, icon_name: str, page: QWidget) -> None:
        self.sidebar.addItem(settings_sidebar_item(self, label, icon_name))
        self.pages.addWidget(page)

    def _rebuild_domain_navigation(self) -> None:
        """Move existing rows into stable capability domains without cloning state."""
        old_pages = {self.sidebar.item(index).text(): self.pages.widget(index) for index in range(self.pages.count())}
        all_rows = list(self.findChildren(SettingRow))
        claimed: set[SettingRow] = set()

        def claim(*setting_ids: str) -> list[SettingRow]:
            rows = []
            for setting_id in setting_ids:
                row = self.findChild(SettingRow, f"settingRow_{setting_id}")
                if row is not None and row not in claimed:
                    claimed.add(row)
                    rows.append(row)
            return rows

        def claim_prefix(prefix: str) -> list[SettingRow]:
            rows = [row for row in all_rows if row.objectName().startswith(f"settingRow_{prefix}") and row not in claimed]
            claimed.update(rows)
            return rows

        def page_content(sections) -> QWidget:
            content = QWidget(self)
            layout = QVBoxLayout(content)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(18)
            for section in sections:
                if isinstance(section, QWidget):  # 已构造好的块（折叠框等）原样进布局
                    layout.addWidget(section)
                    continue
                title, rows, *options = section
                rows = [row for row in rows if row is not None]
                if rows:
                    layout.addWidget(
                        SettingsSection(
                            title,
                            rows,
                            content,
                            advanced=bool(options and options[0]),
                        )
                    )
            layout.addStretch(1)
            return content

        general = page_content(
            [
                ("应用启动", claim("autostart")),
                # 「光标隐藏时自动穿透」回主组：它也是窗口旗标类偏好（与置顶/全屏隐藏同族），
                # 用户找它会先看这一组；原先跟「直播捕获」一起塞进"Windows 兼容"是埋掉了它。
                ("窗口与系统", claim("dock_icon", "on_top", "auto_hide_fullscreen", "cursor_hidden_passthrough", "cross_screen")),
                        # 「多开」分组已随拓扑收口 Phase A 隐藏（见上方注释）
            ]
        )
        # 「桌宠」域：单页（不再切成「显示 / 动作与碰撞」两个页内标签）。
        pet = page_content(
            [
                ("显示", claim("scale", "bubble_text_scale", "pet_opacity")),
                ("动画与移动", claim("playback_speed", "animation_gap", "idle_low_fps", "no_move")),
                ("拖拽与弹射", claim("drop_gravity", "throw_strength", "slingshot_enabled", "lock_position", "shift_drag")),
                ("边缘探头", claim("edge_probe")),
            ]
        )
        # 「互动」域（2026-09-22 分页）：整页在本模块构建（settings_interaction，
        # 行数预算原因），页内用任务标签分成「点击与音效 / 自言自语」两个同级任务；
        # 行不进 all_rows 快照，因此不需要 claim，也不会掉进「待分类（开发期）」。
        interaction = settings_interaction.build_interaction_domain(self)
        # 点击音效 4 行与 click_self_talk / click_balance / click_talk_bindings
        # 同享 click_ 前缀，按 2026-09-17 定稿口径整组留在 interaction 域。
        menu = SettingsTabContainer(self)
        menu.addTab(
            "layout",
            "菜单编排",
            page_content(
                [
                    ("内容与布局", claim("context_menu_layout")),
                ]
            ),
        )
        menu.addTab(
            "appearance",
            "外观",
            page_content(
                [
                    ("菜单外观", claim("menu_theme", "menu_density", "menu_radius", "menu_font", "menu_font_size", "menu_translucent", "menu_opacity")),
                    (
                        "高级配色",
                        claim(
                            "light_background",
                            "light_foreground",
                            "light_hover",
                            "dark_background",
                            "dark_foreground",
                            "dark_hover",
                        ),
                        True,
                    ),
                ]
            ),
        )
        menu.setProperty("contentMaxWidth", 1240)

        # 节日提醒的行在这里登记：本页的行从构造起就挂在自己的持有容器里
        # （无父的 SettingRow 一旦 setVisible 就是个顶层窗口，用户会看到无标题小窗闪
        # ——上游 #261 修的就是这个），因此 findChildren 现在取得到它们。不登记就会
        # 掉进「待分类（开发期）」——它们稍后由 build_domain_page 现造卡片收进
        # 「自动化与联动」域。
        festival_rows = list(self.festival_page.findChildren(SettingRow))
        claimed.update(festival_rows)
        dialogue_rows = claim_prefix("dialogue_")
        # 「自定义台词」＝一个可折叠框（默认折叠）：逐事件文案行全部收进去，
        # 不用自定义台词的用户不该翻过整页文案框；搜索命中时会自动展开
        # （见 _search_settings）。全局风格控件（表达风格/专属文案对象/模板 JSON）
        # 不是事件文案，单独放「文案风格与模板」小节。
        phrases_box = CollapsibleGroup("自定义台词（逐事件文案）", self)
        phrase_edit_keys = set(self.dialogue_phrase_edits)
        phrase_rows = [row for row in dialogue_rows
                       if row.objectName()[len("settingRow_dialogue_"):] in phrase_edit_keys]
        ungated_dialogue_rows = [row for row in dialogue_rows
                                 if row.objectName()[len("settingRow_dialogue_"):] not in phrase_edit_keys]
        if phrase_rows:
            phrases_box.add_group("事件气泡文案", phrase_rows)
        phrases_box.set_expanded(False)
        self.dialogue_phrases_box = phrases_box
        # dialogue_* 里的全局风格控件（表达风格、专属文案对象、弹窗文案模板 JSON）
        # 不是某个事件的气泡文案，已被 claim_prefix("dialogue_") 认领（不再进
        # leftovers），若不显式放回本域就会从设置页里彻底消失。
        # 顶层顺序就是下表顺序（没有倒插）；折叠框是已构造好的 QWidget，直接作为表元素进布局。
        automation = page_content(
            [
                # 「免打扰」两行在本模块构建（settings_quiet，行数预算原因）。
                ("免打扰", settings_quiet.build_quiet_rows(self)),
                ("文案风格与模板", ungated_dialogue_rows),
                phrases_box,
            ]
        )

        # 节日提醒整组（分组标题 + 折叠编排）由 festival_settings 自己建卡交给
        # 「自动化与联动」域：本域不能按「一组行」收它——页面容器会散架、四段
        # 分组标题会跟着丢（见 docs/SETTINGS-CHANGE-GATES.md 节日提醒准入记录）。
        # 故这里不用 page_content，自己起一层容器，排在免打扰/消费统计之后。
        festival = QWidget(self)
        festival_layout = QVBoxLayout(festival)
        festival_layout.setContentsMargins(0, 0, 0, 0)
        festival_layout.setSpacing(18)
        festival_layout.addWidget(self.festival_page.build_domain_page(festival))
        festival_layout.addStretch(1)
        automation.layout().insertWidget(
            max(0, automation.layout().count() - 1), festival)
        # 节日提醒的行刚被搬进这张平卡：摆正「常用项在前 + 少用项折叠」的行序。
        self.festival_page.refresh_backend_rows()

        # Preserve any newly added row until it receives an explicit domain decision.
        leftovers = [row for row in all_rows if row not in claimed]
        if leftovers:
            layout = automation.layout()
            layout.insertWidget(max(0, layout.count() - 1), SettingsSection("待分类（开发期）", leftovers, automation))

        while self.pages.count():
            self.pages.removeWidget(self.pages.widget(0))
        self.sidebar.clear()
        domain_content = {
            "常规": general,
            "桌宠": pet,
            "互动": interaction,
            "菜单": menu,
            "自动化与联动": automation,
        }
        for label, icon in SETTINGS_DOMAIN_NAV:
            content = domain_content.get(label)
            if content is None:
                continue
            self._add_page(label, icon, self._page_shell(label, content))
        for page in old_pages.values():
            page.deleteLater()
        # 域页全部装好之后再装「按区直找」：页头跳转条 + 每个分区的组描述。
        settings_page_guide.install(self)

    def _clear_search_matches(self) -> None:
        for row in self._search_rows:
            if row.property("searchMatch"):
                row.setProperty("searchMatch", False)
                row.style().unpolish(row)
                row.style().polish(row)

    def _focus_search_box(self) -> None:
        """把焦点送进侧栏搜索框并全选（Ctrl+F；不改变已输入的内容之外的状态）。"""
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()

    def _search_settings(self, query: str, *, advance: int = 0) -> None:
        """执行搜索；``advance`` 是**步长**（回车/↓ = +1、↑ = -1、0 = 不主动翻页）。

        用步长而不是"要不要前进"的布尔：↑ 需要反方向，取模天然支持回绕
        （第一条上按 ↑ 落到最后一条），不必为回绕写特判。

        ``advance=0`` 是"不主动翻页"，**不是"重新开始"**：命中集合没变时保持当前
        索引，只有集合变了（`:2166` 那支）才归零。
        """
        query = query.strip().lower()
        self._clear_search_matches()
        if not query:
            self._search_matches = []
            self._search_index = -1
            self.search_status.hide()
            return
        matches = settings_search.find_matches(self._search_rows, query)
        if not matches:
            self._search_matches = []
            self._search_index = -1
            self.search_status.setText("未找到匹配的设置")
            self.search_status.show()
            return
        if matches != self._search_matches:
            self._search_matches = matches
            self._search_index = 0
        elif advance:
            self._search_index = (self._search_index + advance) % len(matches)
        row = matches[self._search_index]
        row.setProperty("searchMatch", True)
        row.style().unpolish(row)
        row.style().polish(row)
        page_index = 0
        for index in range(self.pages.count()):
            if self.pages.widget(index).isAncestorOf(row):
                page_index = index
                break
        self.sidebar.setCurrentRow(page_index)
        page = self.pages.widget(page_index)
        # 命中折叠里的行要先把它露出来，否则「搜索结果存在但看不见」。
        # 折叠有两种形态，交给 settings_widgets.reveal_settings_row 一处管：
        # ① CollapsibleGroup / 高级组 / 页内标签是 QWidget 嵌套（判祖先即可）；
        # ② 节日提醒的少用项行是**行级**折叠（那批行会被搬进一张平卡，容器活不
        #    下来，所以折叠状态落在行上的 _reveal_fold 回调里）。
        # 只判祖先会漏掉 ②：搜索命中折叠里的自定义文案行时它仍藏着。
        reveal_settings_row(row, page)
        scroll = page.findChild(QScrollArea, "settingsScroll")
        if scroll is not None:
            scroll.ensureWidgetVisible(row, 0, 24)
        # 依赖不满足的行：只给可见说明，绝不替用户改配置（R2 §一-3）。
        note = "" if row.isVisibleTo(page) else f"（{self._hidden_prerequisite_note(row)}）"
        self.search_status.setText(
            f"{self._search_index + 1}/{len(matches)} · {row.label.text()}{note}")
        self.search_status.show()

    def _hidden_prerequisite_note(self, row: SettingRow) -> str:
        """命中行被前置开关隐藏时给出说明（依赖不满足绝不自动改配置）。"""
        return "当前被前置开关隐藏"

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.search_edit and event.type() == QEvent.Type.KeyPress:
            # 回车 / ↓ 前进、↑ 后退。只在**裸键**（或小键盘键）时拦：带 Ctrl/Alt/Shift
            # 的 ↑/↓ 一律透传——输入法候选导航、以及将来可能加的组合键，不该被搜索抢走。
            # 单行 QLineEdit 里裸 ↑/↓ 本来没有默认行为，拦掉不损失任何既有操作。
            if event.modifiers() in (Qt.KeyboardModifier.NoModifier,
                                     Qt.KeyboardModifier.KeypadModifier):
                step = {
                    Qt.Key.Key_Return: 1,
                    Qt.Key.Key_Enter: 1,
                    Qt.Key.Key_Down: 1,
                    Qt.Key.Key_Up: -1,
                }.get(event.key())
                if step is not None:
                    self._search_settings(self.search_edit.text(), advance=step)
                    return True
        return super().eventFilter(watched, event)

    def _apply_selected_theme(self, *_args) -> None:
        theme = str(self.menu_theme_select.currentData() or "system")
        dark = theme == "dark" or (theme == "system" and _system_dark())
        self.setProperty("settingsDark", dark)
        self.setStyleSheet(_settings_stylesheet(theme))
        # 图标是位图：QSS 换了它不会自己换色，按记录的名字重画（见 settings_widgets）。
        refresh_settings_icons(self)
        for control in self.findChildren(ModernSelect):
            if control._popup is not None:
                control._popup.setStyleSheet(control.popupStyleSheet())
            control.update()
        for popup in self.findChildren(QMenu):
            if popup.property("settingsPopup"):
                configure_settings_action_popup(popup)
        for control in self.findChildren(ToggleSwitch):
            control.update()

    def _apply_autostart(self) -> None:
        """应用「开机自启」开关：仅在实际改动时写入系统登录项。

        保存按钮与直接关闭（X / Esc）共用，保证三条路径行为一致。
        """
        if self.autostart_check.isChecked() != self._autostart_initial:
            # set_enabled 返回 bool（enable()/disable()）；仅在明确失败时提示。
            ok = autostart_mod.set_enabled(self.autostart_check.isChecked())
            if ok is False:
                QMessageBox.warning(
                    self,
                    "开机自启设置失败",
                    "写入开机自启失败：可能被安全软件拦截。\n可稍后在托盘菜单重试，或检查安全软件/系统优化工具的拦截记录。",
                )

    def _save(self) -> None:
        """「保存并退出」：写入配置并关闭对话框（失败走同一条关闭闸门）。"""
        if not self._save_before_close():
            return
        # 闸门这次关闭已经做过决定（落盘成功，或用户明确选择放弃）：这里只负责关窗，
        # 并闸住关闭路径再写一遍整表（放弃时尤其不能写——那正是要放弃的东西）。
        self._saved_via_button = True
        self.accept()

    def _write_config(self) -> bool:
        """把当前控件值写入 config 并落盘（按钮与直接关闭共用）。

        保存前从磁盘重读：吸收外部对本对话框未暴露字段的改动。
        standalone 下这条尤其关键——主进程在设置开着期间会自己写 config
        （托盘菜单开关等），不 reload 就把别人的改动回滚了。
        已知限制：已暴露字段仍是 last-writer-wins（对话框获胜）。
        返回是否成功落盘；失败**不在这里弹**——把类别记进 ``self._write_failure``，
        由关闭闸门（``pet/settings_close_flow``）统一给文案与「放弃未保存的改动并关闭」
        出口（自己再弹一次就是同一件事弹两遍，且那两个出口只有闸门知道）。
        """
        self._write_failure = None
        menu_layout_value = self.menu_layout_editor.value()
        menu_validation = resolve_menu_layout(
            menu_layout_value,
            registered_actions=MENU_ACTIONS.ids,
            available_actions=MENU_ACTIONS.ids,
        )
        if menu_validation.source == "fallback":
            self._write_failure = settings_close_flow.layout_failure(
                menu_validation.diagnostics)
            return False
        self.config.reload()
        minimum = min(self.min_spin.value(), self.max_spin.value())
        maximum = max(self.min_spin.value(), self.max_spin.value())
        texts = [line.strip()[:120] for line in self.texts_edit.toPlainText().splitlines() if line.strip()]
        self.config.set("scale", float(self.scale_combo.currentData()))
        self.config.set("on_top", self.on_top_check.isChecked())
        if self.dock_icon_check is not None:
            self.config.set("show_dock_icon", self.dock_icon_check.isChecked())
        self.config.set("no_move", self.no_move_check.isChecked())
        self.config.set("mouse_through", self.mouse_through_check.isChecked())
        self.config.set("drop_gravity", self.drop_gravity_check.isChecked())
        self.config.set("throw_strength", str(self.throw_strength_select.currentData() or "standard"))
        self.config.set("slingshot_enabled", self.slingshot_check.isChecked())
        self.config.set("lock_position", self.lock_position_check.isChecked())
        self.config.set("shift_drag", self.shift_drag_check.isChecked())
        self.config.set("pet_opacity", int(self.pet_opacity_spin.value()))
        click_sound_enabled = self.click_sound_check.isChecked()
        click_sound_pack = self.click_sound_picker.value()
        click_sound_volume = float(self.click_sound_volume_spin.value()) / 100.0
        click_sound_pack_changed = self.config.get("click_sound_pack") != click_sound_pack
        click_sound_enabled_changed = self.config.get("click_sound_enabled") != click_sound_enabled
        self.config.set("click_sound_enabled", click_sound_enabled)
        self.config.set("click_sound_pack", click_sound_pack)
        self.config.set("click_sound_volume", click_sound_volume)
        # 只在真正需要时预热：点击音效处于启用状态，且本次写回改变了启用开关或音效包。
        # 音量变化/未改动不需要重建 QSoundEffect；开关从关到开已由勾选回调即时预热，
        # 因此普通“打开设置再关闭”不应在每次落盘都创建 QtMultimedia 音频对象。
        if click_sound_enabled and (click_sound_enabled_changed or click_sound_pack_changed):
            warm_click_sound_effects(
                click_sound_pack,
                data_dir=self.config.dir,
            )
        if self.click_balance_check is not None:
            self.config.set("click_show_balance", self.click_balance_check.isChecked())
        self.config.set("click_show_self_talk", self.click_self_talk_check.isChecked())
        self.config.set("golden_spin_on_click", self.golden_spin_click_check.isChecked())
        self.config.set("golden_spin_direct", self.golden_spin_direct_check.isChecked())
        self.config.set("edge_probe_enabled", self.edge_probe_check.isChecked())
        if self.balance_refresh_spin is not None:
            self.config.set("balance_refresh_minutes", int(self.balance_refresh_spin.value()))
            self.config.set(
                "balance_tier_labels_mode",
                str(self.balance_tier_mode_select.currentData() or "default"),
            )
            self.config.set("balance_tier_label_peak", self.balance_tier_peak_edit.text().strip())
            self.config.set("balance_tier_label_idle", self.balance_tier_idle_edit.text().strip())
            self.config.set("balance_tier_color_enabled", self.balance_tier_color_check.isChecked())
        if self.auto_hide_fullscreen_check is not None:
            self.config.set("auto_hide_fullscreen", self.auto_hide_fullscreen_check.isChecked())
        if getattr(self, "cross_screen_check", None) is not None:
            self.config.set("allow_cross_screen", self.cross_screen_check.isChecked())
        # 「单进程多开」键不落盘控件值：开关已隐藏（拓扑收口 Phase A），
        # 配置字典里加载的原值随 config.save() 原样回写（兼容保留）。
        if self.cursor_hidden_passthrough_check is not None:
            self.config.set("cursor_hidden_passthrough", self.cursor_hidden_passthrough_check.isChecked())
        self.config.set("playback_speed", float(self.speed_select.currentData()))
        self.config.set("animation_gap_seconds", self.gap_spin.value())
        self.config.set("idle_low_fps_enabled", self.idle_low_fps_check.isChecked())
        self.config.set("self_talk_enabled", self.self_talk_check.isChecked())
        self.config.set("self_talk_bubble_style", self.bubble_style_select.currentData())
        self.config.set("self_talk_min_interval", minimum)
        self.config.set("self_talk_max_interval", maximum)
        self.config.set("self_talk_duration_seconds", self.self_talk_duration_spin.value())
        self.config.set("self_talk_texts", texts or list(DEFAULT_SELF_TALK_TEXTS))
        self.config.set("self_talk_image_dir", self.self_talk_image_dir_picker.text())
        self.config.set("self_talk_image_scale", self.self_talk_image_scale_spin.value())
        self.config.set("self_talk_image_chance", self.self_talk_image_chance_spin.value())
        self.config.set("bubble_text_scale", self.bubble_text_scale_spin.value())
        # Agent 联动：自定义 thinking 文案与音效（合并写回，不覆盖 agent_link 其他开关）
        self.config.set("dialogue_mode", str(self.dialogue_mode_select.currentData() or "legacy"))
        # 统一预设：编辑区当前层 flush 后，global 层 + agents delta 分层写回
        self._dialogue_flush_scope()
        new_global = self._dialogue_scope_values("")
        agents_delta: dict[str, dict[str, list[str]]] = {}
        for scope in self._dialogue_scope_buffer:
            if scope == "":
                continue
            values = self._dialogue_scope_values(str(scope))
            if values:
                agents_delta[str(scope)] = values
        # 兼容旧扁平存储：双层仅当存在 agents delta 或原配置已是双层时启用
        current_phrases = self.config.get("dialogue_phrases", {})
        was_preset = isinstance(current_phrases, dict) and ("global" in current_phrases or "agents" in current_phrases)
        if agents_delta or was_preset:
            self.config.set("dialogue_phrases", {"global": new_global, "agents": agents_delta})
        else:
            self.config.set("dialogue_phrases", new_global)
        # 记住上次编辑层：下次打开设置直接回到该 Agent 专属层（未知值回落全局）
        self.config.set("dialogue_last_scope", str(getattr(self, "_dialogue_scope", "") or ""))
        # 节日提醒设置页写回（仅写 festival_reminder_* / festival_custom_* 10 键）
        if self.festival_page is not None:
            self.festival_page.apply_to_config()
        self.config.set(
            "context_menu_appearance",
            {
                "theme": self.menu_theme_select.currentData(),
                "density": self.menu_density_select.currentData(),
                "corner_radius": self.menu_radius_select.currentData(),
                "ui_font": self.menu_font_select.currentData(),
                "ui_font_size": self.menu_font_size_select.currentData(),
                "translucent": self.menu_translucent_check.isChecked(),
                "opacity": self.menu_opacity_spin.value(),
                "light_background": self.light_background_picker.text(),
                "light_foreground": self.light_foreground_picker.text(),
                "light_hover": self.light_hover_picker.text(),
                "dark_background": self.dark_background_picker.text(),
                "dark_foreground": self.dark_foreground_picker.text(),
                "dark_hover": self.dark_hover_picker.text(),
            },
        )
        default_menu_nodes = load_default_menu_layout().get("nodes", [])
        self.config.set(
            "context_menu_layout",
            None if menu_layout_value.get("nodes") == default_menu_nodes else menu_layout_value,
        )
        settings_quiet.save_quiet_settings(self)
        self.config.set("autostart_wanted", self.autostart_check.isChecked())
        # 批 C：落种占位语义——仅当用户在该子肥鱼自己的设置界面保存过才置真；
        # 位置自动保存等一切后台写盘不得置位。主配置（slot 0/主肥鱼）保存不置位。
        if self.config.instance_id:
            self.config.set("user_customized", True)
        ok = self.config.save()
        if not ok:
            self._write_failure = settings_close_flow.failure_of(self)
        # 写回之后再对齐一次标记：落盘后的配置值才是「已改过没」的现行答案
        settings_default_marks.refresh(self)
        return ok

    def _close_after_external_write(self) -> None:
        """关窗，但跳过关闭路径的整表写回（``_write_config``）。

        供"已在窗口外完成落盘"的入口使用（当前是「恢复默认设置」）：此时控件里
        持有的仍是落盘前的旧值，关闭路径照常写回就会把刚写下的配置静默覆盖回去。
        """
        self._saved_via_button = True
        self.accept()

    def _save_before_close(self) -> bool:
        """关闭前落盘（X / Esc / 关闭按钮 /「保存并退出」共用）；False = 要留在窗口里继续改。

        落盘、失败文案与出口全在 ``pet/settings_close_flow``：保存成功或用户明确选择
        「放弃未保存的改动并关闭」→ True（调用方照常 accept/reject），用户选「继续编辑」
        → False（不关窗，草稿留在控件里）。这里只回答"这次关闭能不能真的关"。
        """
        outcome = settings_close_flow.save_before_close(self)
        return outcome != settings_close_flow.CLOSE_KEEP_EDITING

    def reject(self) -> None:  # noqa: N802 - Qt API
        """Esc / 关闭按钮与 X 同契约：保存失败不关窗，除非用户明确选择放弃改动。"""
        if self._save_before_close():
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self._save_before_close():
            event.ignore()
            return
        super().closeEvent(event)
