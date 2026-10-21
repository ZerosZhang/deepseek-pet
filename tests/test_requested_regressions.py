import os
import types

import pytest
from datetime import datetime, timezone


def _slot0_config(tmp_path):
    """生产形态的配置面：slot0 身份经 ``SlotRoutedConfig`` 分流。

    每宠键（气泡文字大小、气泡方案…）的真值在 ``config-slot-0.json``：裸全局
    ``Config.set/save`` 出闸时会过滤掉它们，改不动任何一只宠。
    """
    from pet.config import Config
    from pet.settings_slot_config import route_settings_config

    return route_settings_config(Config(base=tmp_path, instance_id="slot-0"))












def test_readme_harness_autostart_paragraph_matches_the_launch_gates():
    """README 的「随桌宠启动 dsh 服务」段落与代码同口径（自启门 + 收口例外）。

    同一事实的双处守卫：设置页 hint 由上面那条用例看着，README 段落此前无人看管，
    于是同一句话在 README 里停在旧口径（缺联动门、缺启动窗口例外）。代码依据同上
    （``pet/app.py`` :2161-2165 与 :2136-2138）。
    """
    from pathlib import Path

    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    para = next((line for line in readme.splitlines() if "随桌宠启动 dsh 服务" in line), None)
    assert para is not None, "README 里找不到「随桌宠启动 dsh 服务」段落"
    assert "DSH 联动" in para
    assert "不会拉起" in para, "必须写明联动关着时不自启（联动没开时 dsh web 无人消费）"
    assert "例外" in para and "探测期间" in para, (
        "必须写明「拉起探测期间关掉开关会立刻收掉刚拉起的实例」这一例外"
    )


def _readme_text():
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_documents_the_new_global_hotkey_section():
    """README 必须登记 v4.3.4 的「互动 → 快捷键」（做了就要说）。

    依据：`pet/settings_interaction.py` 的第五个页内标签 `hotkeys` →
    `pet/settings_hotkeys.build_hotkey_rows`（三个动作、默认空、必须有修饰键、
    非 Windows 只存不注册）。此前 `grep 快捷键 README.md` 一条都搜不到。
    """
    readme = _readme_text()
    assert "设置 → 互动 → 快捷键" in readme, "入口要按真实路径写（域 + 页内标签）"
    lines = readme.splitlines()
    start = next(
        (index for index, line in enumerate(lines)
         if line.startswith("#") and "全局快捷键" in line), None)
    assert start is not None, "README 缺少「全局快捷键」小节"
    end = next(
        (index for index in range(start + 1, len(lines))
         if lines[index].startswith("# ") or lines[index].startswith("## ")),
        len(lines))
    body = "\n".join(lines[start:end])
    for phrase, why in (
        ("默认全空", "默认不绑是这一版的行为基线（不绑 = 与旧版逐位相同）"),
        ("修饰键", "单个字母的全局键会抢走系统级打字，录入时就被拒"),
        ("只有 Windows", "其它平台能存不注册，用户必须知道"),
        ("AI 对话", "三个动作要逐一点名"),
        ("看看屏幕", "三个动作要逐一点名"),
        ("截图提问", "三个动作要逐一点名"),
    ):
        assert phrase in body, f"快捷键小节必须写「{phrase}」：{why}"


def test_readme_ai_config_path_matches_the_real_ui():
    """README 的 AI 配置路径要能真的走通（用户第一步就撞墙的那条）。

    依据：右键菜单模板 `pet/menu_templates/modern-default-v1.json` 里**没有**
    `ai_settings` 节点（只有 `chat`=AI 对话、`modern_settings`=桌宠设置）；「AI 设置」
    只存在于**托盘**菜单（`pet/app.py` 的 `add_tray_action(menu, 'AI 设置', ...)`）。
    设置窗里那一页叫「AI 与对话」，保存按钮是侧栏的「保存并退出」（AI 页没有存档
    按钮，`pet/settings_widgets.sidebar_save_button`）。
    """
    readme = _readme_text()
    assert "设置 → AI 与对话" in readme, "零基础配置必须写真实路径"
    assert "保存并退出" in readme, "AI 页没有「保存」按钮，存档只有侧栏这一个入口"
    for line in readme.splitlines():
        if "AI 设置" in line:
            assert "托盘" in line, (
                f"「AI 设置」只存在于托盘菜单，提到它必须写明托盘，否则用户会去右键菜单找：{line}"
            )


def test_readme_lists_the_settings_that_are_not_effective_immediately():
    """「关闭即自动保存并立即生效」必须带例外清单，且与代码同口径。

    三个例外各有出处：`settings_pet_controls.CROSS_SCREEN_HINT`（重启级）、
    `STREAM_CAPTURE_RESTART_HINT`（重启级）、`settings_network` 的「帧率采集权限」行
    （加入 `Performance Log Users` 后要重新登录，令牌才换）。
    """
    readme = _readme_text()
    assert "少数几项要重启或重新登录才生效" in readme, "快速开始里要指向例外清单"
    exceptions = next(
        (line for line in readme.splitlines() if "三个例外" in line), None)
    assert exceptions is not None, "「立即生效」旁边必须有例外清单"
    for name in ("允许桌宠跨屏", "直播捕获兼容", "帧率采集权限"):
        assert f"`{name}`" in exceptions, f"例外清单缺「{name}」"
    assert "重启" in exceptions and ("注销" in exceptions or "重新登录" in exceptions)
































@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows 无 time.tzset()，无法在测试进程内切换时区（CI runner 为 UTC）",
)
def test_new_session_title_converts_utc_creation_time_to_local(monkeypatch):
    import os
    import time

    from pet.chat.models import ChatSession
    from pet.chat.widgets import _short_title

    previous_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        created = datetime(2026, 8, 27, 1, 5, tzinfo=timezone.utc).isoformat()
        session = ChatSession("id", "shenshen", "provider", "", created_at=created)
        assert _short_title(session) == "新会话 · 09:05"
    finally:
        if previous_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", previous_tz)
        if hasattr(time, "tzset"):
            time.tzset()












def test_macos_hide_pet_respects_dock_icon_hidden_preference(tmp_path, monkeypatch):
    """macOS 关闭「显示 Dock 图标」后，隐藏桌宠不得再临时唤回 Dock 图标。

    issue #74：托盘（菜单栏）菜单已承担恢复入口（显示/隐藏、鼠标穿透、
    桌宠设置），因此隐藏桌宠应尊重用户关闭 Dock 图标的偏好，不再把
    activation policy 临时改回 Regular，也不写回配置。
    """
    import sys

    from unittest import mock

    from PySide6.QtWidgets import QWidget

    import pet.app
    from pet.config import Config
    from pet.window import PetWindow

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(pet.app, "_mac_set_dock_icon_visible", mock.Mock())

    for pref in (False, True):
        with mock.patch.object(QWidget, "hide") as mock_hide:
            win = PetWindow.__new__(PetWindow)
            win.cfg = Config(tmp_path)
            win.cfg.set("show_dock_icon", pref)
            PetWindow.hide(win, notify=False)
            mock_hide.assert_called_once()
            assert win.cfg.get("show_dock_icon") is pref
            pet.app._mac_set_dock_icon_visible.assert_not_called()




# Linux 回归：Windows 专属开关不得在非 Windows 平台创建后游离到设置窗左上角。


def test_hide_pet_notifies_and_dock_click_restores(tmp_path, monkeypatch):
    """用户主动隐藏：弹托盘提示 + macOS 点击 Dock 图标恢复桌宠。"""
    import sys

    from unittest import mock

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    import pet.window as window_mod
    from pet.config import Config

    monkeypatch.setattr(sys, "platform", "darwin")
    app = QApplication.instance() or QApplication([])
    win = window_mod.PetWindow.__new__(window_mod.PetWindow)
    win.cfg = Config(tmp_path)
    notified = []
    win.on_hidden = lambda: notified.append(True)

    with mock.patch.object(QWidget, "hide"), mock.patch.object(
        window_mod.PetWindow, "show"
    ) as mock_show, mock.patch.object(app, "applicationStateChanged") as m_sig:
        window_mod.PetWindow.hide(win)
        assert notified, "用户主动隐藏应触发托盘提示回调"
        # 隐藏后 arm Dock 点击恢复监听
        m_sig.connect.assert_called_once()
        # 点击 Dock 图标 → 应用激活 → 自动恢复桌宠
        window_mod.PetWindow._restore_on_dock_reactivate(
            win, Qt.ApplicationState.ApplicationActive
        )
        mock_show.assert_called_once()
        # 一次性监听：再次激活不再恢复
        mock_show.reset_mock()
        window_mod.PetWindow._restore_on_dock_reactivate(
            win, Qt.ApplicationState.ApplicationActive
        )
        mock_show.assert_not_called()


def test_hide_pet_internal_replacement_skips_notify(tmp_path, monkeypatch):
    """角色切换等内部替换隐藏：不弹提示、不 arm Dock 恢复监听。"""
    import sys

    from unittest import mock

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    import pet.window as window_mod
    from pet.config import Config

    monkeypatch.setattr(sys, "platform", "darwin")
    app = QApplication.instance() or QApplication([])
    win = window_mod.PetWindow.__new__(window_mod.PetWindow)
    win.cfg = Config(tmp_path)
    win.on_hidden = lambda: pytest.fail("内部替换不应弹提示")

    with mock.patch.object(QWidget, "hide"), mock.patch.object(
        window_mod.PetWindow, "show"
    ) as mock_show, mock.patch.object(app, "applicationStateChanged") as m_sig:
        window_mod.PetWindow.hide(win, notify=False)
        m_sig.connect.assert_not_called()
        window_mod.PetWindow._restore_on_dock_reactivate(
            win, Qt.ApplicationState.ApplicationActive
        )
        mock_show.assert_not_called()


def test_animation_icon_applier_updates_action_and_cleans_worker():
    """图标解码完成回调须经 GUI 线程槽更新 QAction，并清理 worker 记录。

    回归背景：ready 信号此前直连普通闭包，setIcon/update 在 QThreadPool
    工作线程执行（Qt 未定义行为）；现经 _AnimationIconApplier（挂在
    submenu 下、随菜单生命周期）队列投递回 GUI 线程。
    """
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.shared import _AnimationIconApplier

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    submenu = QMenu(menu)
    submenu._animation_icon_workers = []
    action = submenu.addAction("测试动画")
    pump_calls = []
    worker = object()

    # 无图（解码失败/空帧）：不 setIcon，但必须移除 worker 并继续泵任务
    applier = _AnimationIconApplier(
        submenu, action, worker, lambda: pump_calls.append(1), parent=submenu
    )
    applier.on_ready(None)
    assert submenu._animation_icon_workers == []
    assert pump_calls == [1]

    # 有效图：菜单不可见（offscreen）时更新图标
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(0xFF3366FF)
    submenu._animation_icon_workers.append(worker)
    applier2 = _AnimationIconApplier(
        submenu, action, worker, lambda: pump_calls.append(2), parent=submenu
    )
    applier2.on_ready(image)
    assert submenu._animation_icon_workers == []
    assert pump_calls == [1, 2]
    assert not action.icon().isNull()

    # 菜单已销毁：槽必须静默返回，不访问已删 C++ 对象
    menu.deleteLater()
    app.processEvents()




def test_store_fun_asset_keeps_bundled_paths_relative(tmp_path):
    """内置 assets 内的路径必须持久化为相对值（portable），外部文件保留绝对路径。

    回归背景：设置对话框把默认相对路径固化成安装目录绝对路径，目录移动/
    自更新后彩蛋弹窗失效。
    """
    from pet.fun_image_popup import bundled_assets_root, store_fun_asset

    default = bundled_assets_root() / "big_blue_fat_fish" / "ojingjing.jpg"
    # 绝对路径指向内置 assets → 归一化为相对值
    stored = store_fun_asset(str(default), default)
    assert stored == "assets/big_blue_fat_fish/ojingjing.jpg"
    # 相对值原样保留
    assert store_fun_asset("assets/big_blue_fat_fish", default) == "assets/big_blue_fat_fish"
    # 空值回退默认
    assert store_fun_asset("", default) == str(default)
    # 外部文件 → 绝对路径保留
    external = tmp_path / "custom" / "egg.jpg"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"x")
    assert store_fun_asset(str(external), default) == str(external)


def test_menu_autostart_persists_wanted_flag(tmp_path, monkeypatch):
    """右键菜单的「开机自启」必须记录 autostart_wanted（启动自检提醒依赖它）。

    注册表（registry 的 autostart 项）、设置页与托盘都写这个键；共享建造器被
    直调时漏传 pet 就会只写系统登录项、不写配置——``pet/app.py`` 的自检
    （``autostart_wanted`` 为真但系统项被安全软件清掉 → 提醒用户重新启用）
    因此永远看不到用户勾过。

    真 QMenu + 真 Config + 真 PetWindow 建菜单，只把系统登录项边界（autostart
    模块）打桩；断言配置落盘，而不只是内存里的 Config 对象。
    """
    import json

    from PySide6.QtWidgets import QApplication, QMenu

    import pet.context_menus.shared as shared_mod
    import tests.test_context_menu_lifecycle as lc
    from pet.config import Config
    from pet.context_menu import populate_context_menu

    app = QApplication.instance() or QApplication([])
    applied: list[bool] = []
    monkeypatch.setattr(shared_mod.autostart_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(shared_mod.autostart_mod, "set_enabled",
                        lambda enabled: applied.append(bool(enabled)) or True)
    config = Config(base=tmp_path)
    config.save()
    assert config.get("autostart_wanted") is False
    win = lc.PetWindow(lc.FakeLibrary(), config)
    menu = QMenu()
    try:
        populate_context_menu(menu, win)
        action = next(a for action in menu.actions()
                      if action.menu() is not None
                      for a in action.menu().actions() if a.text() == "开机自启")
        action.setChecked(True)
        assert applied == [True], "系统登录项照常写入"
        assert config.get("autostart_wanted") is True
        persisted = json.loads((config.dir / "config.json").read_text(encoding="utf-8"))
        assert persisted["autostart_wanted"] is True, "必须落盘（自检读的是盘上的值）"
    finally:
        menu.close()
        win.close()
        app.processEvents()




def _answer_save_failure(monkeypatch, seen: list, *, discard: bool = False) -> None:
    """替掉保存失败框的 ``exec``，但框本体走**产品真实构造**（文案/按钮都是真的）。

    只有"用户点了哪个按钮"这一处可注入：``settings_close_flow.confirm_discard_unsaved``
    （conftest 里默认桩成"继续编辑"，这里换成取真框并读回文案的替身）。

    ``seen`` 里也收了一份标题，但**断言不许只看标题**：macOS 的 QMessageBox 走系统原生
    对话框，``windowTitle()`` 在那边恒为空（仓库既有结论与同族修法见
    ``tests/test_harness_lifecycle.py::test_confirm_dialog_text_names_pid_and_port``）。
    承载"用户看得见什么"的是 ``text`` / ``info``——标题只在 Windows/Linux 上读得到。
    """
    from pet import settings_close_flow

    def answer(parent, failure):
        box, _keep, discard_button = settings_close_flow.build_save_failure_box(parent, failure)
        try:
            seen.append({"failure": failure, "title": box.windowTitle(),
                         "text": box.text(), "info": box.informativeText(),
                         "discard": discard_button})
        finally:
            box.deleteLater()
        return discard

    monkeypatch.setattr(settings_close_flow, "confirm_discard_unsaved", answer)








def test_settings_stylesheet_has_dark_overrides(monkeypatch):
    """深色系统下新版设置必须追加深色覆盖段（白底白字不可读问题）。"""
    from pet.modern_settings_dialog import _settings_stylesheet

    monkeypatch.setattr("pet.settings_theme_qss._system_dark", lambda: True)
    qss = _settings_stylesheet()
    assert "background: #202024" in qss
    assert "color: #e4e4e9" in qss
    monkeypatch.setattr("pet.settings_theme_qss._system_dark", lambda: False)
    qss_light = _settings_stylesheet()
    assert "background: #202024" not in qss_light
    # 浅色也必须显式给按钮补文字色（防深色 palette 白字）
    assert "QPushButton { color: #202020; }" in qss_light






def test_modern_settings_finished_refreshes_even_on_rejected(tmp_path, monkeypatch):
    """新版设置直接关闭（Rejected）也必须把改动应用到桌宠。

    回归背景：只有 Accepted（保存并退出）才刷新；X 关闭时 closeEvent 已
    自动保存，但桌宠 scale/拖动物理等不生效。
    """
    from PySide6.QtWidgets import QApplication

    import pet.app as app_mod
    from pet.app import AppShell, PetInstance
    from pet.config import Config

    app = QApplication.instance() or QApplication([])
    owner = PetInstance.__new__(PetInstance)
    owner.shell = AppShell.__new__(AppShell)
    owner.modern_settings_dialog = object()
    refreshed = []

    class FakeWin:
        def refresh_pet_settings(self):
            refreshed.append(1)

        def set_bubble_suppressed(self, _suppressed):
            pass

    owner.win = FakeWin()
    owner.config = Config(tmp_path)
    # 真实壳恒有 config（应用链末尾无条件走一次台词预缓存，入口自己按开关收敛）
    owner.shell.config = owner.config
    owner.shell._apply_balance_timer = lambda: None
    owner.shell._sync_dynamic_island = lambda: None
    # Phase 1 门控后 todo 服务走 _sync_todo_service（懒启停）；测试只测桌宠刷新
    owner.shell._sync_todo_service = lambda: None
    owner.shell._sync_chime_service = lambda: None  # 语音报时同样懒启停，本用例只测桌宠刷新
    owner.shell._sync_festival_service = lambda: None  # 节日提醒同样懒启停（其内部会连带同步报时通道）
    owner.shell._sync_divination_service = lambda: None  # 每日一签同属懒启停族（无定时器，仍按开关建/释放）
    owner._refresh_chat_windows = lambda: None
    owner._sync_animation_prewarm = lambda: None
    monkeypatch.setattr(app_mod, "_mac_set_dock_icon_visible", lambda *a, **k: None)
    PetInstance._modern_settings_finished(owner, 0)  # QDialog.Rejected（X 关闭）
    assert refreshed == [1], "Rejected 关闭也必须刷新桌宠"








# --- macOS Dock recovery menu regression (2026-09-03) ---




# --- 评审回归：碰撞分离累计写回 / 隐藏宠退出碰撞世界（2026-10-03）---


def _make_pet_sprite(pos, scale=0.5):
    """真 PetSprite（offscreen）：假 clip 无 ffmpeg 依赖，几何 = 640x360 画布 × scale。"""
    from PySide6.QtCore import QPointF

    from pet.pet_sprite import PetSprite
    from tests.test_sprite_collision_id import FakeLibrary

    return PetSprite(FakeLibrary(), pos=QPointF(*pos), scale=scale)


def _world_members(world, sprites):
    return [world._member_from_sprite(s) for s in sprites]


def test_real_pets_separate_by_solver_cumulative_in_one_tick():
    """真 PetSprite 静止重叠：一轮 tick 的终位 = 求解器累计分离量（D9 回归）。

    旧口径按 ImpulseResult 的**末轮** dx 逐 pair 写回：本场景 40px 重叠四轮迭代
    累计每只 18.51px，实际只写回 1.86px——90% 的分离量留到下一 tick，与连续
    重叠记账 / 去抖互相打架。
    """
    from PySide6.QtWidgets import QApplication

    from pet import collision
    from pet.sprite_collision import SpriteCollisionWorld

    app = QApplication.instance() or QApplication([])
    a = _make_pet_sprite((600, 300))
    b = _make_pet_sprite((880, 300))          # 320 宽 → 重叠 40px
    id_a, id_b = a.collision_id, b.collision_id
    world = SpriteCollisionWorld()
    members = _world_members(world, (a, b))
    impulses, combined, _history = collision.solve_multi_body_collision(
        members, tick=1)

    assert abs(combined[id_a][2]) > 5 * abs(impulses[0].dx_a), \
        "前提：累计分离量远大于末轮增量（旧写回口径）"

    world.tick([a, b], 0.016)

    assert a.pos.x() == pytest.approx(600.0 + combined[id_a][2], abs=1e-6)
    assert b.pos.x() == pytest.approx(880.0 + combined[id_b][2], abs=1e-6)
    # 一轮之后只剩求解器自己的迭代残差，而不是 90% 的重叠留待下一 tick
    residual = collision.check_collision_members(
        *_world_members(world, (a, b)))[3]
    assert residual <= 0.1 * 40.0
    app.processEvents()


def test_real_hidden_pet_is_not_an_invisible_obstacle():
    """逐只隐藏的真 PetSprite 退出碰撞世界：不推可见宠、不触发碰撞反馈（D10）。"""
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from pet.sprite_collision import (
        INTERACTION_NORMAL,
        INTERACTION_THROWN,
        SpriteCollisionWorld,
    )

    app = QApplication.instance() or QApplication([])
    world = SpriteCollisionWorld()
    victim = _make_pet_sprite((600, 300))
    ghost = _make_pet_sprite((880, 300))
    ghost.set_velocity(QPointF(-800, 0))      # 高速撞向可见宠
    ghost.set_visible(False)

    assert world.tick([victim, ghost], 0.016) == []
    assert victim.pos.x() == 600.0 and victim.pos.y() == 300.0
    assert victim.velocity.x() == 0.0
    assert victim.interaction_state == INTERACTION_NORMAL

    ghost.set_visible(True)                   # 恢复可见：碰撞干净回归
    results = world.tick([victim, ghost], 0.016)
    assert [r.pair for r in results] == [
        "|".join(sorted((victim.collision_id, ghost.collision_id)))]
    assert victim.velocity.x() < 0.0          # 被撞飞
    assert victim.interaction_state == INTERACTION_THROWN
    app.processEvents()
