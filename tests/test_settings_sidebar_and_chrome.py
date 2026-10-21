# -*- coding: utf-8 -*-
"""设置窗「外框」三件事：侧栏宽度跟着内容走、导航可达、窗口挂正式桌宠图标。

为什么单独一个文件：这三条都是**壳层几何/窗口属性**（侧栏、标题栏），与设置项、
持久化、搜索候选集无关；本仓库的设置测试按主题分文件（``test_settings_page_guide``
管页内布局、``test_settings_reset_defaults`` 管重置链路），壳层单独立一份便于定位。

口径（都落在真实 ``ModernSettingsDialog`` 这个公开 seam 上）：

1. **侧栏宽度 = ``max(200, 内容所需)``**：200px 是设计令牌，但放大字体下按钮文案会
   长过它——本机实测 1.5 倍字体（20px）时侧栏按钮（「重置本宠设置…」）的 ``sizeHint``
   要 186px，而 200px 的侧栏内宽只有 175px，文字会被省略号吃掉。宽度按**最宽的
   非撑满子控件**算，默认字体下恒为 200（逐像素不变），放大字体下跟着长；**构造之后
   字体才变大也要跟上**（系统放大字体 / 无障碍放大 / 截图脚本的 ``--font-scale`` 都是
   这条路，所以不能只在构造时算一次）。
2. **导航可达**：默认窗口 800×560 下 10 个能力域必须全部落在视口里（默认尺寸就把
   「更新」截掉一半＝用户看不到还有这一页）；720×500 下允许滚动，但每一行都要能选中
   并切到对应页。
3. **窗口图标**：``setWindowTitle`` 之后挂正式桌宠图标（``load_application_icon``），
   原生标题栏不再摆系统给的那一个；图标拿不到时照旧能建窗（空图标，不抛异常）。
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import pet.application_icon as application_icon  # noqa: E402
import pet.modern_settings_dialog as settings_mod  # noqa: E402
from pet.config import Config  # noqa: E402
from pet.settings_widgets import (  # noqa: E402
    CONTENT_READING_MAX_WIDTH,
    SIDEBAR_MIN_WIDTH,
    SettingsSection,
    SettingsTabContainer,
    sidebar_content_width,
)

app = QApplication.instance() or QApplication([])

#: 1.5 倍字体（与 ``scripts/capture_settings_pages.py --font-scale 1.5`` 同一口径）：
#: 无障碍/系统放大字体下按钮文案最容易撑破侧栏。
FONT_SCALE = 1.5


def _scale_fonts(root: QWidget, scale: float) -> None:
    """按截图脚本同一做法逐控件放大像素字号（构造之后再放大）。"""
    for widget in [root, *root.findChildren(QWidget)]:
        font = widget.font()
        pixels = font.pixelSize()
        if pixels > 0:
            font.setPixelSize(max(1, round(pixels * scale)))
            widget.setFont(font)


def _dialog(tmp_path: Path, monkeypatch, *, width: int = 800, height: int = 560,
            font_scale: float = 1.0):
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dialog = settings_mod.ModernSettingsDialog(Config(base=tmp_path), include_ai=True)
    dialog.resize(width, height)
    dialog.show()
    app.processEvents()
    if font_scale != 1.0:
        _scale_fonts(dialog, font_scale)
        # 与截图脚本同一收尾：改完字体各 resize 一拍，让布局按新字号落定。
        dialog.resize(width + 1, height)
        app.processEvents()
        dialog.resize(width, height)
        app.processEvents()
    return dialog


def _pane(dialog):
    pane = dialog.findChild(QFrame, "sidebarPane")
    assert pane is not None, "侧栏容器不见了（sidebarPane）"
    return pane


# ------------------------------------------------------------------ 1. 侧栏宽度


def test_sidebar_width_ignores_widgets_that_fill_the_column():
    """撑满列的控件不参与宽度需求——判据是**策略**，不是宽度。

    这条钉的是"为什么不能直接用 ``layout.minimumSize()``"：搜索框这类控件的
    ``sizeHint`` 是 Qt 默认的「十七个字符宽」（本机默认字体下实测 210px），照它算会把
    侧栏顶到 290px 这种与内容无关的宽度。

    **前提不许写成绝对阈值**：注册过应用字体之后 Qt 对默认家族的解析会变（``tests/
    test_screen_capture_ocr.py`` 的 ``addApplicationFont`` 一跑，'x' 的 advance 实测
    12 → 6，同一个 ``QLineEdit.sizeHint`` 从 210 掉到 108），于是"更宽"这个前提会随字体库
    状态漂。这里改成自己造一个**确定很宽**的撑满控件来立前提。
    """
    host = QWidget()
    layout = QVBoxLayout(host)
    try:
        filler = QLineEdit(host)
        assert filler.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        layout.addWidget(filler)
        assert sidebar_content_width(layout) == 0, "撑满列的控件不该产生宽度需求"

        # 再宽也一样：宽度超过令牌、策略是撑满 → 仍然不参与（判据是策略）。
        wide = QLabel("跨平台同步与自动恢复策略的超长本地化标题示例", host)
        wide.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(wide)
        assert wide.sizeHint().width() > SIDEBAR_MIN_WIDTH, "前提：这个撑满控件自己确实很宽"
        assert sidebar_content_width(layout) == 0, "再宽也不参与：判据是策略不是宽度"

        button = QPushButton("保存并退出", host)
        layout.addWidget(button)
        assert sidebar_content_width(layout) == button.sizeHint().width()
    finally:
        host.deleteLater()
        app.processEvents()






# ------------------------------------------------------------------ 2. 导航可达






# ------------------------------------------------------------------ 3. 窗口图标




# ------------------------------------------------------------------ 4. 表单阅读宽度
def _settle(turns: int = 3) -> None:
    """把布局推平：切页/视口尺寸变化都会再排一拍（页头宽度跟着视口走，见
    ``_SettingsPageShell._sync_heading_width``）。"""
    for _turn in range(turns):
        app.processEvents()


def _content_of(dialog, domain: str):
    """域页的可滚动内容与视口（页内标签域取当前标签页）。"""
    index = next(i for i in range(dialog.sidebar.count())
                 if dialog.sidebar.item(i).text() == domain)
    page = dialog.pages.widget(index)
    scroll = page.findChild(QScrollArea, "settingsScroll")
    content = scroll.widget()
    tabs = content.findChild(SettingsTabContainer, "settingsTaskTabs")
    root = tabs.stack.currentWidget() if tabs is not None else content
    return page, scroll, root


#: 表单最大阅读宽度的**定稿值**：宽过它的一律按这一列排（设计令牌，见
#: ``settings_widgets.CONTENT_READING_MAX_WIDTH``）。写死在这里是有意的——改这个数
#: 必须同时改这条用例，等于把"表单看着多宽"变成一次显式决定。
READING_WIDTH = 800








# ------------------------------------------------------------------ 5. 保存并退出


#: 一级能力域的准入判据（`docs/SETTINGS-CHANGE-GATES.md`「准入记录」末段）：新增一级域须
#: "代表长期独立用户目标、预计包含**至少两个**稳定设置组"。下面这两个域是该判据落地之前
#: 就在的既成事实，作为快照豁免；它们现在是 1 组就写 1 组——将来变多，这条断言会逼你更新
#: 快照，免得豁免名单悄悄扩大成垃圾桶。
DOMAINS_WITH_ONE_GROUP = {"文件识别", "更新"}


