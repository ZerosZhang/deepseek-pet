# -*- coding: utf-8 -*-
"""4.2c 后段 offscreen 单测：托盘聚合 + D12 指令消费 + D13 逐 sprite 设置路由。

覆盖验收口径：

- **托盘聚合**（对齐 legacy 单托盘 + 每窗子菜单的聚合语义）：**≥1 只**就有逐只
  子菜单（主肥鱼 / 小肥鱼 [slot-N]）各含「回到右下角」「退出这只」，动作路由到
  被点的那一只而不是主宠；0 只时不建（没有"这只"可指）；spawn/退出后菜单自动
  重建（旧条目不得残留）；单宠的关闭入口闭环见
  `tests/test_single_pet_close_entry.py`；托盘不可用时壳照常活；
- **D12 指令消费**：主进程按 config 目录 watcher + QTimer 轮询消费「退出子肥鱼」
  指令（含 target slot 只退一只、未知 slot 空操作、消费即删、无 config 目录不装
  watcher、stop/退出收口）；
- **D13 路由**：右键命中的 sprite 透传给菜单建造器；菜单「桌宠设置」按被点
  sprite 的 config 身份（主身份 / slot-N）传入独立设置进程；「退出这只」接
  exit_pet(被点 sprite)。

时序纪律：事件同步 + 宽预算轮询（app.processEvents()），不赌固定 sleep。
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtWidgets import QApplication, QMenu

import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_menu_facade as fac
from pet import overlay_settings_command as cmd
from pet import overlay_spawn_state as ovs
from pet.config import APP_DIR_NAME
from pet.overlay_shell import OverlayShell
from pet.pet_sprite import PetSprite
from pet.sprite_menu_facade import build_sprite_full_menu
from tests.test_overlay_spawn import _make_persistent_shell

app = QApplication.instance() or QApplication([])

MAIN_LABEL = "主肥鱼 [slot-0]"


# ---------------------------------------------------------------- 探测工具
class _NoDirConfig:
    """无 ``dir`` 的假配置（overlay_shell 约定：拿不到目录就不装指令 watcher）。"""

    def __init__(self):
        self._values: dict = {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


def _make_nodir_shell():
    instance = cap.CapInstance(_NoDirConfig())
    screen = cap.FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    return OverlayShell(
        app, instance, screen=screen,
        sprite_factory=lambda lib, pos, scale: PetSprite(lib, pos=pos, scale=scale))


def _tray_menu(shell):
    assert shell.tray is not None, "测试环境应能建出托盘对象"
    menu = shell.tray.contextMenu()
    assert menu is not None
    return menu


def _labels(menu) -> list[str]:
    return [a.text() for a in menu.actions()]


def _submenus(menu) -> dict:
    return {a.text(): a.menu() for a in menu.actions() if a.menu() is not None}


def _action(menu, label: str):
    for act in menu.actions():
        if act.text() == label:
            return act
    raise AssertionError(f"菜单缺项 {label}；实际: {_labels(menu)}")


def _child_label(shell, sprite) -> str:
    return f"小肥鱼 [slot-{shell._spawned_slots[sprite]}]"


def _spawn_two(shell):
    shell.spawn_pet()
    shell.spawn_pet()
    return shell._spawned[0], shell._spawned[1]


def _teardown(shell) -> None:
    shell._teardown_settings_command_watch()
    shell._delete_runtime_marker()
    if getattr(shell, "tray", None) is not None:
        shell.tray.hide()


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    """宽预算轮询等托盘命令落地（``shared.run_after_menu_closed`` 的延迟派发）。

    托盘条目一律「菜单先关、回调延到菜单关闭后执行」：触发后必须先证明**没有**
    内联执行，再用本函数等它真的执行——不赌固定 sleep。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class _FakeContextEvent:
    def __init__(self, pos):
        self._pos = QPoint(pos)
        self.accepted = False
        self.ignored = False

    def pos(self):
        return QPoint(self._pos)

    def globalPos(self):
        return QPoint(10, 20)

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


# ================================================================ 托盘聚合
def test_tray_aggregate_entries_and_quit(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    quit_calls: list = []
    try:
        _spawn_two(shell)
        shell.overlay.show()
        labels = [a.text() for a in _tray_menu(shell).actions() if a.text()]
        assert labels == ["显示 / 隐藏", "桌宠设置", "退出"], labels

        toggle = _action(_tray_menu(shell), "显示 / 隐藏")
        toggle.trigger()
        assert shell.overlay.isVisible(), "菜单还开着，显隐不许内联执行"
        assert _wait_until(lambda: not shell.overlay.isVisible()), "菜单关闭后隐藏"
        toggle = _action(_tray_menu(shell), "显示 / 隐藏")
        toggle.trigger()
        assert _wait_until(lambda: shell.overlay.isVisible()), "菜单关闭后显示"

        # 「退出」必须走当前 app（F5：菜单持有的回调不能是旧对象）；它刻意不延迟
        # 派发（不是窗面动作，legacy 托盘同为裸 addAction），故触发即生效。
        shell.app = SimpleNamespace(quit=lambda: quit_calls.append(1))
        shell._refresh_tray_menu()
        _action(_tray_menu(shell), "退出").trigger()
        assert quit_calls == [1]
    finally:
        shell.overlay.close()
        _teardown(shell)


def test_tray_unavailable_keeps_shell_alive(tmp_path, monkeypatch):
    """托盘构造失败（无托盘环境）：壳照常建，刷新/收口全走空转不抛。"""
    from pet import overlay_shell as overlay_shell_mod

    def boom(*_args, **_kwargs):
        raise RuntimeError("no tray here")

    monkeypatch.setattr(overlay_shell_mod, "QSystemTrayIcon", boom)
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        assert shell.tray is None
        shell.spawn_pet()                  # 生灭触发的菜单刷新不得抛
        shell.clear_spawned_pets()
        shell._refresh_tray_menu()
        shell._teardown_settings_command_watch()
    finally:
        shell._delete_runtime_marker()


def test_tray_survives_menu_build_failure(tmp_path, monkeypatch):
    """缺口 C：建菜单异常不得连带把已建好的托盘判死。

    旧实现把「建托盘 + 建菜单」包在同一个 try 里，菜单阶段任何异常都会
    ``self.tray = None``，而 ``start()`` 判 None 永不 show → 用户看到的是
    「托盘里完全没有桌宠条目」，只留一行 log（正是用户报的现象）。
    """
    from pet import overlay_shell as overlay_shell_mod

    class _BoomMenu:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("menu boom")

    monkeypatch.setattr(overlay_shell_mod, "QMenu", _BoomMenu)
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        assert shell.tray is not None, "菜单异常不得连带丢弃托盘"
        shell.start()
        assert shell.tray.isVisible() is True, "托盘照常 show（用户至少能看到条目）"
    finally:
        if shell.tray is not None:
            shell.tray.hide()
        shell.stop()
        shell._delete_runtime_marker()


# ================================================================ D12 指令消费
def test_command_watch_installed_with_config_dir(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        assert shell._command_watcher is not None
        assert str(shell._config.dir) in shell._command_watcher.directories()
        assert shell._command_timer.isActive()
    finally:
        _teardown(shell)


def test_command_watch_absent_without_config_dir():
    """假配置对象没有 dir：不装 watcher/定时器（也不许抛）。"""
    shell = _make_nodir_shell()
    try:
        assert getattr(shell._config, "dir", None) is None
        assert shell._command_watcher is None
        assert not shell._command_timer.isActive()
        shell._consume_settings_command()          # 空转不抛
    finally:
        _teardown(shell)


def test_command_consume_clears_all_spawned_pets(tmp_path):
    config_dir = tmp_path / APP_DIR_NAME
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        _spawn_two(shell)
        assert cmd.write_command(config_dir, cmd.CMD_EXIT_SPAWNED_PETS) is True
        shell._consume_settings_command()
        assert shell._spawned == []
        assert shell.overlay.sprites == [shell.sprite]
        assert not cmd.command_path(config_dir).exists()   # 消费即删
        assert ovs.load_active_slots(config_dir) == [0]
    finally:
        _teardown(shell)


def test_command_consume_target_slot_exits_only_that_pet(tmp_path):
    config_dir = tmp_path / APP_DIR_NAME
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        first, second = _spawn_two(shell)
        cmd.write_command(config_dir, cmd.CMD_EXIT_SPAWNED_PETS,
                          target=shell._spawned_slots[first])
        shell._consume_settings_command()
        assert shell._spawned == [second]
        assert ovs.load_active_slots(config_dir) == [0, shell._spawned_slots[second]]
    finally:
        _teardown(shell)


def test_command_consume_unknown_target_is_noop(tmp_path):
    config_dir = tmp_path / APP_DIR_NAME
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        _spawn_two(shell)
        cmd.write_command(config_dir, cmd.CMD_EXIT_SPAWNED_PETS, target=99)
        shell._consume_settings_command()
        assert len(shell._spawned) == 2
        assert not cmd.command_path(config_dir).exists()
    finally:
        _teardown(shell)


def test_command_consumed_by_poll_timer(tmp_path):
    """真事件循环：轮询兜底路径（watcher 在换 inode/网络盘下可能漏事件）。"""
    config_dir = tmp_path / APP_DIR_NAME
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        shell.spawn_pet()
        shell._command_timer.setInterval(50)
        assert cmd.write_command(config_dir, cmd.CMD_EXIT_SPAWNED_PETS) is True
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and shell._spawned:
            app.processEvents()
            time.sleep(0.02)
        assert shell._spawned == [], "轮询兜底未消费指令"
    finally:
        _teardown(shell)


def test_command_watch_torn_down_on_stop_and_quit(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        shell.start()
        assert shell._command_timer.isActive()
        shell.stop()
        assert shell._command_watcher is None
        assert not shell._command_timer.isActive()
        # 退出收口（aboutToQuit）同样停表
        shell._install_settings_command_watch()
        shell._on_about_to_quit()
        assert not shell._command_timer.isActive()
    finally:
        _teardown(shell)


# ================================================================ 右键菜单：目标透传
def test_context_menu_builder_receives_clicked_sprite(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        _spawn_two(shell)
        child = shell._spawned[1]
        child.bind_clip("idle1")               # 命中图就绪（alpha_at 需要）
        child._rebuild_pixmap()                # 命中图惰性重建：绘制前手工触发
        child.set_pos(QPointF(300, 300))
        seen: list = []
        exec_calls: list = []
        # 真 QMenu + 实例级 exec 桩：菜单建造器/收口都按真实契约（QMenu）走，
        # offscreen 下真 exec 会进模态嵌套事件循环（挂死），只能桩掉。
        fake_menu = QMenu()
        fake_menu.exec = lambda *args: exec_calls.append(args) or 0
        shell.overlay._full_menu_builder = (
            lambda target: (seen.append(target), fake_menu)[1])
        event = _FakeContextEvent(child.rect().center())
        shell.overlay.contextMenuEvent(event)
        assert seen == [child], "菜单建造器必须拿到被点 sprite"
        assert event.accepted is True and exec_calls
    finally:
        _teardown(shell)


def test_context_menu_ignores_empty_area(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        called: list = []
        shell.overlay._full_menu_builder = lambda target: called.append(target)
        event = _FakeContextEvent(QPoint(5, 5))
        shell.overlay.contextMenuEvent(event)
        assert called == []
        assert event.ignored is True
    finally:
        _teardown(shell)


def test_full_menu_builder_targets_clicked_sprite(tmp_path):
    """壳层装的建造器是「传目标」形态：菜单 facade 的目标 = 被点 sprite。"""
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        first, _second = _spawn_two(shell)
        menu = shell.overlay._full_menu_builder(first)
        assert menu._facade._sprite is first
    finally:
        _teardown(shell)


# ================================================================ 菜单：退出这只 / D13 路由
def test_menu_exit_this_routes_to_exit_pet(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        first, second = _spawn_two(shell)
        menu = build_sprite_full_menu(shell, first)
        _action(menu, "退出这只").trigger()
        assert shell._spawned == [second]
        assert first not in shell.overlay.sprites
    finally:
        _teardown(shell)


def test_menu_exit_this_absent_for_single_pet(tmp_path):
    """legacy parity：单窗（flag 关）不注入「退出这只」，只有「退出」。"""
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        labels = _labels(build_sprite_full_menu(shell))
        assert "退出这只" not in labels
        assert "退出" in labels
    finally:
        _teardown(shell)


def test_menu_settings_routes_child_identity(tmp_path):
    """D13：被点子肥鱼的「桌宠设置」必须带该 sprite 的 slot 身份。"""
    shell, _ = _make_persistent_shell(tmp_path)
    opened: list = []
    try:
        shell._instance.shell = SimpleNamespace(
            open_settings_process=lambda inst: (opened.append(inst), True)[1])
        first, _second = _spawn_two(shell)
        menu = build_sprite_full_menu(shell, first)
        _action(menu, "桌宠设置").trigger()
        assert [inst.config.instance_id for inst in opened] == [
            f"slot-{shell._spawned_slots[first]}"]
    finally:
        _teardown(shell)


def test_menu_settings_keeps_main_identity(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    opened: list = []
    try:
        shell._instance.shell = SimpleNamespace(
            open_settings_process=lambda inst: (opened.append(inst), True)[1])
        _spawn_two(shell)
        menu = build_sprite_full_menu(shell, shell.sprite)
        _action(menu, "桌宠设置").trigger()
        assert [inst.config.instance_id for inst in opened] == [
            "slot-0"]
    finally:
        _teardown(shell)


def test_tray_settings_entry_uses_main_identity(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    opened: list = []
    try:
        shell._instance.shell = SimpleNamespace(
            open_settings_process=lambda inst: (opened.append(inst), True)[1])
        _spawn_two(shell)
        _action(_tray_menu(shell), "桌宠设置").trigger()
        # 托盘入口是「菜单先关、回调延后」（shared.run_after_menu_closed）：
        # 本用例只管身份路由，时序按宽预算轮询等命令落到 open_settings_process。
        deadline = time.monotonic() + 3
        while not opened and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert [inst.config.instance_id for inst in opened] == ["slot-0"]
    finally:
        _teardown(shell)


def test_open_settings_for_returns_false_without_app_shell(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        shell._instance.shell = None
        assert shell.open_settings_for(shell.sprite) is False
    finally:
        _teardown(shell)


def test_sprite_instance_id_maps_slot_identity(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    try:
        first, second = _spawn_two(shell)
        main_id = "slot-0"
        assert shell.sprite_instance_id(shell.sprite) == main_id
        assert shell.sprite_instance_id(first) == f"slot-{shell._spawned_slots[first]}"
        assert shell.sprite_instance_id(second) != shell.sprite_instance_id(first)
        # 陌生 sprite（不在登记表）→ 回退主身份，绝不瞎猜 slot
        strange = PetSprite(fac.RichLibrary(), pos=QPointF(0, 0), scale=1.0)
        assert shell.sprite_instance_id(strange) == main_id
    finally:
        _teardown(shell)
