# -*- coding: utf-8 -*-
"""Phase 3b/3c offscreen 单测（QT_QPA_PLATFORM=offscreen 可跑）。

覆盖：
- OverlayWindow 位置监听（add/remove_position_listener）：rect 变化触发 /
  视觉无变化（advance 返回 None）不触发 / 仅帧变化（rect 未动）不触发 /
  remove 后不再触发 / remove_sprite 连带清理；
- 气泡锚点换算纯函数 sprite_anchor_rect_global（overlay 局部 → 全局）；
- 真实 PetSpeechBubble 经 SpriteBubbleFollower 跟随 sprite 位移；
- 可见性闸门 OverlayVisibilityGate（O2）：光标探测表只在有可见 overlay 时跑，
  全屏探测表不受影响（隐藏后它是恢复显示的唯一路径）。

纪律：同步直调 _on_tick(dt=...) / 事件处理器，不启动真实 QTimer、不固定
sleep 赌时序（AGENTS.md 时序测试纪律）。
"""
from __future__ import annotations

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from pet import collision as collision_mod
from pet import overlay_peripherals
from pet.config import Config
from pet.overlay_peripherals import FullscreenCursorWatcher, OverlayVisibilityGate
from pet.overlay_window import OverlayWindow
from pet.sprite_bubble import SpriteBubbleFollower, sprite_anchor_rect_global
from pet.sprite_collision import CollisionEvent, SpriteCollisionWorld

app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- 假件
class FakeSprite:
    """纯 QImage 假 sprite：与 PetSprite 同一组协议方法（同 test_overlay_window）。"""

    def __init__(self, pos, size=(40, 30), *, movable=False):
        self.pos = QPointF(*pos)
        self._size = size
        self.image = QImage(size[0], size[1], QImage.Format.Format_ARGB32)
        self.image.fill(0xFF336699)
        self.velocity = QPointF(0, 0)
        self.movable = movable
        self.frame_dirty = False
        self.scale = 1.0

    def rect(self):
        return QRect(int(self.pos.x()), int(self.pos.y()), self._size[0], self._size[1])

    def alpha_at(self, local):
        return 255

    def advance(self, dt):
        old = self.rect()
        if self.movable:
            self.pos += self.velocity * dt
        new = self.rect()
        if new != old or self.frame_dirty:
            self.frame_dirty = False
            return (old, new)
        return None

    def paint(self, painter):
        pass


class FakeIsland(QWidget):
    """几何/显隐可控的假岛：QWidget 提供 geometry/isVisible，bump 记录调用。"""

    def __init__(self):
        super().__init__()
        self.on_geometry_changed = None
        self.bump_calls: list[tuple[float, float, float]] = []

    def bump(self, strength=1.0, dir_x=0.0, dir_y=0.0):
        self.bump_calls.append((strength, dir_x, dir_y))

    def emit_geometry_changed(self):
        """模拟 DynamicIsland._emit_geometry_changed 的无参回调。"""
        if callable(self.on_geometry_changed):
            self.on_geometry_changed()


class StubSound:
    def __init__(self):
        self.events = []

    def on_collision(self, event):
        self.events.append(event)


def _overlay() -> OverlayWindow:
    return OverlayWindow()


# ---------------------------------------------------------------- 位置监听
def test_position_listener_fires_on_rect_change():
    overlay = _overlay()
    sprite = FakeSprite((10, 10), movable=True)
    sprite.velocity = QPointF(100, 0)
    overlay.add_sprite(sprite)
    seen = []
    overlay.add_position_listener(sprite, seen.append)
    overlay._on_tick(dt=0.1)
    assert seen == [sprite]


def test_position_listener_not_fired_without_visual_change():
    overlay = _overlay()
    sprite = FakeSprite((10, 10), movable=True)  # velocity 为 0 → advance 返回 None
    overlay.add_sprite(sprite)
    seen = []
    overlay.add_position_listener(sprite, seen.append)
    overlay._on_tick(dt=0.1)
    assert seen == []


def test_position_listener_not_fired_when_only_frame_changes():
    overlay = _overlay()
    sprite = FakeSprite((10, 10), movable=False)
    sprite.frame_dirty = True  # advance 返回 (old, new) 但 old == new
    overlay.add_sprite(sprite)
    seen = []
    overlay.add_position_listener(sprite, seen.append)
    overlay._on_tick(dt=0.1)
    assert seen == []


def test_remove_position_listener_stops_callbacks():
    overlay = _overlay()
    sprite = FakeSprite((10, 10), movable=True)
    sprite.velocity = QPointF(100, 0)
    overlay.add_sprite(sprite)
    seen = []
    overlay.add_position_listener(sprite, seen.append)
    overlay.remove_position_listener(sprite, seen.append)
    overlay.remove_position_listener(sprite, seen.append)  # 重复注销是 no-op
    overlay._on_tick(dt=0.1)
    assert seen == []


def test_remove_sprite_drops_position_listeners():
    overlay = _overlay()
    sprite = FakeSprite((10, 10), movable=True)
    overlay.add_sprite(sprite)
    overlay.add_position_listener(sprite, lambda s: None)
    overlay.remove_sprite(sprite)
    assert sprite not in overlay._position_listeners


# ---------------------------------------------------------------- 气泡锚点换算（纯函数）
def test_sprite_anchor_rect_global_converts_origin():
    sprite = FakeSprite((100, 50), size=(80, 60))
    anchor = sprite_anchor_rect_global(sprite, QPoint(10, 20))
    assert anchor == QRect(110, 70, 80, 60)


def test_sprite_anchor_rect_global_zero_origin():
    sprite = FakeSprite((7, 9), size=(40, 30))
    anchor = sprite_anchor_rect_global(sprite, QPoint(0, 0))
    assert anchor == QRect(7, 9, 40, 30)


# ---------------------------------------------------------------- 真实气泡跟随
def test_bubble_follower_real_bubble_follows_sprite():
    overlay = _overlay()
    sprite = FakeSprite((100, 200), movable=True)
    overlay.add_sprite(sprite)
    follower = SpriteBubbleFollower(overlay, sprite)
    try:
        assert follower.bubble is not None
        assert follower.say("测试一句") is True
        assert follower.bubble.isVisible()
        before = follower.bubble.pos()
        sprite.velocity = QPointF(100, 0)
        overlay._on_tick(dt=0.2)  # sprite 右移 20px → 位置监听 → 气泡直移跟随
        after = follower.bubble.pos()
        assert after.x() - before.x() == 20
        assert after.y() == before.y()
        assert follower.say("") is False  # 空文案静默降级
    finally:
        follower.close()
    assert sprite not in overlay._position_listeners


# ---------------------------------------------------------------- 岛静态成员注册/注销/几何更新


# ---------------------------------------------------------------- 撞岛反馈




# ---------------------------------------------------------------- 真实灵动岛构造接线


# ---------------------------------------------------------------- 可见性闸门（O2）
def _watcher(gate, probes: list) -> FullscreenCursorWatcher:
    return FullscreenCursorWatcher(
        fullscreen_probe=lambda: False,
        cursor_probe=lambda: probes.append(1) or "UNKNOWN",
        overlay_visibility=gate)


def test_cursor_timer_follows_overlay_visibility():
    """没有可见 overlay 就不跑光标探测；有则跑；全屏表始终不受影响。"""
    gate = OverlayVisibilityGate()
    probes: list = []
    w = _watcher(gate, probes)
    widget = QWidget()
    try:
        w.set_fullscreen_enabled(True)
        w.set_cursor_enabled(True)
        assert not w._cursor_timer.isActive(), "无可见 overlay：不空转"
        assert w._fs_timer.isActive()

        gate.note(widget, True)
        assert w._cursor_timer.isActive()
        probes.clear()
        gate.note(widget, False)
        assert not w._cursor_timer.isActive()
        assert probes == [], "隐藏后不得再探测光标"
        assert w._fs_timer.isActive(), "全屏探测表不受显隐影响"

        gate.note(widget, True)
        assert w._cursor_timer.isActive()
        assert probes, "恢复显示必须立即补一次探测（停表对去抖状态机透明）"
    finally:
        w.stop()
        widget.close()


def test_cursor_gate_off_wins_over_visibility():
    """配置门关：即使有可见 overlay 也不跑；再开时按当前可见性决定。"""
    gate = OverlayVisibilityGate()
    probes: list = []
    w = _watcher(gate, probes)
    widget = QWidget()
    w.set_cursor_enabled(True)
    try:
        gate.note(widget, True)
        assert w._cursor_timer.isActive()
        w.set_cursor_enabled(False)
        assert not w._cursor_timer.isActive()
        gate.note(widget, False)
        w.set_cursor_enabled(True)
        assert not w._cursor_timer.isActive(), "门开了但窗口仍隐藏：不跑"
        gate.note(widget, True)
        assert w._cursor_timer.isActive()
    finally:
        w.stop()
        widget.close()


def test_gate_drops_destroyed_widgets():
    """弱引用登记：窗口被回收即自动摘除，不会把闸门永久顶开。"""
    gate = OverlayVisibilityGate()
    widget = QWidget()
    gate.note(widget, True)
    assert gate.any_visible() is True
    assert gate.count() == 1
    widget.close()
    del widget
    gc.collect()
    assert gate.any_visible() is False


def test_module_gate_reports_real_overlay_visibility():
    """真 OverlayWindow 的 show/hide 走模块级闸门（生产路径）。"""
    overlay = OverlayWindow()
    base = overlay_peripherals.visible_overlay_count()
    try:
        overlay.show()
        assert overlay_peripherals.visible_overlay_count() == base + 1
        overlay.hide()
        assert overlay_peripherals.visible_overlay_count() == base
    finally:
        overlay.close()
    assert overlay_peripherals.visible_overlay_count() == base
