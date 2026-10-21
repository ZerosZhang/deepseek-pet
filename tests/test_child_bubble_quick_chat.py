"""G2-R1：子宠自己的气泡也必须可点，点击后快速对话归于发起槽（锚定子宠）。

回归：``_apply_bubble_interactive`` 只在主宠冒泡路径被调用，子宠自己冒泡
（``_show_bubble_text_for``）时气泡保持鼠标穿透；槽重建后新住客同样不可点。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from pet.sprite_bubble import sprite_anchor_rect_global  # noqa: E402
from tests.test_overlay_collision_toggle import _make_slot_shell  # noqa: E402

_TRANSPARENT = Qt.WidgetAttribute.WA_TransparentForMouseEvents


def _child(shell):
    children = [s for s in shell._all_sprites() if s is not shell.sprite]
    assert len(children) == 1
    return children[0]


def _assert_child_bubble_opens_quick_chat(shell, child):
    assert shell._show_bubble_text_for(child, "子宠说话", 3000) is True
    bubble = shell._bubble_followers[child].bubble
    assert not bubble.testAttribute(_TRANSPARENT), "子宠气泡必须可点"
    bubble.clicked.emit()
    quick = shell._quick_chat
    assert quick is not None and quick.isVisible()
    assert quick.pet_window.visible_content_rect() == sprite_anchor_rect_global(
        child, shell.overlay.geometry().topLeft())
    shell._close_quick_chat()




def _real_click_and_assert(shell, child):
    """真 Qt 鼠标事件点这只宠的气泡（不是直接 emit clicked），必须打开快速对话。"""
    from PySide6.QtTest import QTest

    assert shell._show_bubble_text_for(child, "子宠说话", 3000) is True
    bubble = shell._bubble_followers[child].bubble
    assert not bubble.testAttribute(_TRANSPARENT), "前提：可点态已生效"
    QTest.mouseClick(bubble, Qt.MouseButton.LeftButton, pos=bubble.rect().center())
    quick = shell._quick_chat
    assert quick is not None and quick.isVisible(), "真鼠标点击必须打开快速对话"
    assert quick.pet_window.visible_content_rect() == sprite_anchor_rect_global(
        child, shell.overlay.geometry().topLeft()), "快速对话必须锚定被点的那一只"
    shell._close_quick_chat()



