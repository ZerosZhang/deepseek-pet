# -*- coding: utf-8 -*-
"""档案代次被外部推进后，设置窗必须**关得掉**（2026-10-10 实机报告 §4 的收口）。

复现链（真实持久副本，代次不用 mock）：打开子宠设置窗（表单首读钉住当时的档案代次）→
这只宠被退出又重新生成（``pet_profiles.begin_slot_generation``，正是壳在生成新住客时
写的那一步）→ 旧窗口点「保存并退出」/ X / Esc：代次防覆盖门拒绝旧表单落盘。旧实现到
这里就是死路——窗口关不掉、提示还把"代次落后"说成"配置未能写入磁盘"，用户只能杀进程。

产品口径（父级决定，逐条钉在下面的用例里）：

1. 旧代次**不许**覆盖新档案（这道门不动，它是保护不是故障）；
2. 默认保留草稿——不自动覆盖、不自动刷新、不把窗口刷成新值；
3. 但必须有**明确可达**的出口「放弃未保存的改动并关闭」；
4. 代次冲突的说明是"这只桌宠已重新生成 / 设置在别处更新过，请重新打开"，**不是**磁盘失败；
5. 普通写失败（锁/写盘）同样可安全放弃；X / Esc 与「保存并退出」同契约、同出口；
6. 放弃只放弃**还没写成功**的部分：档案被代次门挡住时全局那一半可能已经落盘，文案必须
   如实说出来（不许说"已回滚"）；
7. Qt 只 finalize 一次：同一件事不弹两个框，X 关闭不把整表写回两遍。

测试用真对话框 + 真槽档案文件 + 真 ``settings.lock``；只有"用户在消息框里点了哪个按钮"
这一处是可注入的 seam（``settings_close_flow.confirm_discard_unsaved``），且替身里用的是
**产品真实构造**的框（文案/按钮/默认钮都是真的）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pet import pet_profiles
from pet import settings_close_flow
from pet import settings_slot_config
from pet.config import Config

SLOT = 1
KEEP_LABEL = "继续编辑"
DISCARD_LABEL = "放弃未保存的改动并关闭"
#: 产品那份 `confirm_discard_unsaved`（conftest 的 autouse 挡板会在用例里把它换成
#: "继续编辑"；需要跑真 exec 的用例把它装回去）。
_REAL_CONFIRM_DISCARD = settings_close_flow.confirm_discard_unsaved
#: 产品那份 `QMessageBox.warning`（同样在 conftest 的防卡挡板之前取下来——在用例里
#: 现取会拿到挡板那个 no-op，见 ``test_discard_unverified_notice_is_a_real_visible_box``）。
_REAL_WARNING = settings_close_flow.QMessageBox.warning


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------ 夹具 / 工具
def _config_dir(tmp_path) -> Path:
    """真实配置目录（``Config.dir`` = base / APP_DIR_NAME；槽档案与代次都住这里）。"""
    return Config(base=tmp_path).dir


def _main_config(tmp_path) -> Config:
    """主配置（全局键那份），并落一个非默认的全局值当基线。"""
    main = Config(base=tmp_path)
    main.set("pet_opacity", 55)
    assert main.save() is True
    return main


def _slot_path(tmp_path) -> Path:
    return pet_profiles.slot_profile_path(_config_dir(tmp_path), SLOT)


def _profile_exists(tmp_path, values: dict) -> None:
    assert pet_profiles.write_profile_settings(
        _config_dir(tmp_path), SLOT, values, user_customized=True).status == "ok"


def _dialog(tmp_path, *, standalone: bool = True):
    from pet.modern_settings_dialog import ModernSettingsDialog

    return ModernSettingsDialog(
        Config(base=tmp_path, instance_id=f"slot-{SLOT}"),
        include_ai=False, standalone=standalone)


def _rebuild_pet(tmp_path) -> int:
    """真实持久副本：这只宠被退出又重新生成（壳在生成新住客时做的就是这一步）。"""
    result = pet_profiles.begin_slot_generation(_config_dir(tmp_path), SLOT)
    assert result.ok, result
    return result.generation


def _answer_with(monkeypatch, *, discard: bool, seen: list, note=None):
    """替掉 exec：框本体走**产品真实构造**（文案/按钮/默认钮都是真的）。

    与 ``test_settings_reset_defaults`` 的 ``answer_yes`` 同规——只替换"用户点了哪个
    按钮"这一处，任何文案/按钮语义的错配都会在断言里露出来。
    """
    def answer(parent, failure):
        box, keep, discard_button = settings_close_flow.build_save_failure_box(parent, failure)
        try:
            seen.append({
                "failure": failure,
                "title": box.windowTitle(),
                "text": box.text(),
                "info": box.informativeText(),
                "default": box.defaultButton(),
                "escape": box.escapeButton(),
                "keep": keep,
                "discard": discard_button,
            })
        finally:
            box.deleteLater()
        if note is not None:
            note()
        return discard

    monkeypatch.setattr(settings_close_flow, "confirm_discard_unsaved", answer)


def _copy_of(entry: dict) -> str:
    return "\n".join((entry["title"], entry["text"], entry["info"]))


def _drop(dialog) -> None:
    """收尾：对话框带 WA_DeleteOnClose，被真关掉时 C++ 对象当场销毁（判活着再删）。"""
    import shiboken6

    if shiboken6.isValid(dialog):
        dialog.deleteLater()


def _close_with_escape(dialog, app) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    app.processEvents()


def _run_realmodal_driver(tmp_path, mode: str) -> dict:
    """在干净子进程里跑真模态框流程（驱动器：tests/settings_realmodal_driver.py）。

    主套件共享进程里的 quitNow 残留会让真模态 exec 进入即 -1 秒退（qtbase 6.9
    qeventloop.cpp / qcoreapplication.cpp:1512），进程内清旗又必须泵全局事件队列
    （conftest 明令禁止的全局冲刷）——所以真框验证走进程边界（AGENTS.md：Qt 回归
    用真实事件循环和进程边界），子进程里 Qt 状态干净、防卡桩为零，框全是产品原件。
    """
    import os
    import subprocess
    import sys

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(
        [sys.executable,
         str(Path(__file__).parent / "settings_realmodal_driver.py"),
         mode, str(tmp_path), str(SLOT)],
        capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == 0, f"驱动器异常退出 {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
    lines = [line[len("RESULT "):] for line in proc.stdout.splitlines()
             if line.startswith("RESULT ")]
    assert len(lines) == 1, f"驱动器必须恰好打一行 RESULT:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(lines[0])


# ------------------------------------------------------------ 1. 死路消失


# ------------------------------------------------------------ 2. 放弃出口真的能出去












# ------------------------------------------------------------ 3. 放弃的边界（诚实）


# ------------------------------------------------------------ 4. 普通失败也能安全出去








# ------------------------------------------------------------ 5. 分类与文案的对照
@pytest.mark.parametrize("status,kind", [
    ("stale-generation", settings_slot_config.SAVE_FAILURE_STALE),
    ("refused-corrupt", settings_slot_config.SAVE_FAILURE_PROFILE),
    ("corrupt", settings_slot_config.SAVE_FAILURE_PROFILE),
    ("refused-unsupported-version", settings_slot_config.SAVE_FAILURE_PROFILE),
    ("write-failed", settings_slot_config.SAVE_FAILURE_DISK),
    ("lock-timeout", settings_slot_config.SAVE_FAILURE_DISK),
    ("lock-unavailable", settings_slot_config.SAVE_FAILURE_DISK),
])
def test_slot_status_classification_matches_the_pet_profiles_vocabulary(status, kind):
    """``pet_profiles`` 的失败词 → 界面类别：只有真的写盘/锁失败才算磁盘失败。"""
    assert settings_slot_config.classify_slot_status(status) == kind


@pytest.mark.parametrize("kind", [
    settings_slot_config.SAVE_FAILURE_STALE,
    settings_slot_config.SAVE_FAILURE_PROFILE,
    settings_slot_config.SAVE_FAILURE_LAYOUT,
    settings_slot_config.SAVE_FAILURE_AUTOSTART,
    settings_slot_config.SAVE_FAILURE_DISK,
    settings_slot_config.SAVE_FAILURE_UNKNOWN,
])
def test_only_a_real_write_failure_is_described_as_a_disk_failure(app, kind):
    """文案对照：**只有** ``SAVE_FAILURE_DISK`` 那一支可以说"配置未能写入磁盘"。

    这就是实机 §4 里说错的那句话：代次冲突被说成写盘失败，把排查方向指到磁盘与锁上。
    """
    box, keep, discard = settings_close_flow.build_save_failure_box(
        None, settings_slot_config.SaveFailure(kind=kind, status=kind, path="C:/x/config-slot-1.json"))
    try:
        copy = "\n".join((box.windowTitle(), box.text(), box.informativeText()))
        assert ("配置未能写入磁盘" in copy) is (kind == settings_slot_config.SAVE_FAILURE_DISK)
        assert keep.text() == KEEP_LABEL and discard.text() == DISCARD_LABEL
        assert box.defaultButton() is keep and box.escapeButton() is keep
    finally:
        box.deleteLater()


# ------------------------------------------------------------ 6. finalize 纪律


# ------------------------------------------------------------ 7. 独立设置进程形态
def test_discard_in_the_settings_process_releases_the_lock_for_the_next_open(
        tmp_path, app, monkeypatch):
    """真进程形态（``pet/__main__._exec_settings``）：放弃关窗 → 事件循环退出 → 锁释放。

    "能重新打开设置页"的判据是这把锁真的放开了（主进程按它判断是否已有设置页在跑），
    而不是"对话框对象还在不在"。
    """
    from PySide6.QtCore import QLockFile, Qt, QTimer
    from PySide6.QtTest import QTest

    from pet import __main__ as entry
    from pet.modern_settings_dialog import ModernSettingsDialog

    _main_config(tmp_path)
    _profile_exists(tmp_path, {"scale": 0.8})
    config = Config(base=tmp_path, instance_id=f"slot-{SLOT}")
    seen: list = []
    _answer_with(monkeypatch, discard=True, seen=seen)
    problems: list = []

    def drive():
        for widget in app.topLevelWidgets():
            if not isinstance(widget, ModernSettingsDialog):
                continue
            if getattr(widget.config, "dir", None) != config.dir:
                continue
            widget.scale_combo.setCurrentIndex(widget.scale_combo.findData(1.0))
            _rebuild_pet(tmp_path)
            QTest.keyClick(widget, Qt.Key.Key_Escape)
            return
        problems.append("设置对话框没出现")

    QTimer.singleShot(0, drive)
    watchdog = QTimer(app)
    watchdog.setSingleShot(True)
    watchdog.setInterval(10000)
    watchdog.timeout.connect(app.quit)   # 兜底：绝不挂死在事件循环里（真挂住会在断言处红）
    watchdog.start()
    try:
        assert entry._exec_settings(app, config) == 0
    finally:
        # app 是进程级单例：正常跑完必须拆雷，否则 10s 后这一发 quit 会落在后面
        # 用例的模态 exec 里（曾把 test_discard_unverified_notice 的通知框打没）。
        watchdog.stop()
    assert problems == []
    assert len(seen) == 1
    assert pet_profiles.read_slot_profile(_config_dir(tmp_path), SLOT).value("scale") == pytest.approx(0.8)
    lock = QLockFile(str(config.dir / "settings.lock"))
    assert lock.tryLock(0), "放弃关窗后 settings.lock 必须已释放（否则设置页再也打不开）"
    lock.unlock()


# ------------------------------------------------------------ 8. 放弃 = 真的作废草稿（进程内表单视图）
#: astra 增量审查 CF01（``.scratch/product-final-review-astra-20261010/REVIEW-CLOSE-FLOW.md``）：
#: 上面那些用例都用**新建**的 Config 构造路由、且 ``standalone=True``，所以关窗之后没有
#: 任何人还持有那份路由——草稿跟着对象一起消失，缺口因此躲过了 27 项用例。产品真实支持的
#: 进程内 fallback（``settings_process_isolation=False``，或 ``startDetached`` 失败回退）不是
#: 这样：``app.py:1369``/``:3740`` 把 ``SlotRoutedConfig`` 直接挂在 ``PetInstance`` 上，
#: 而设置窗拿到的是它自己那份**表单视图**（``SlotRoutedConfig.new_form_view``，同一 ``_instance``
#: / ``_main``，草稿与编辑基线各自一份）：关窗只是关窗，草稿还活在这份视图里，下一次
#: **无关**保存（例如宠物菜单里改播放速度）会把它一起 flush 落盘。
#:
#: 下面这一组钉住的就是这条真实 seam：真 ``Config`` + 真 ``SlotRoutedConfig`` + 真关闭闸门
#: （``standalone=False``、运行期那份视图与表单视图**同时存在**），只有"这一次写盘失败"与
#: "用户点了哪个按钮"两处是注入的。


def _shared_route(tmp_path):
    """运行期那只手 + 主配置：进程内 fallback 的形态（设置窗关掉之后它仍然活着）。"""
    main = _main_config(tmp_path)
    identity = Config(base=tmp_path, instance_id=f"slot-{SLOT}")
    return settings_slot_config.SlotRoutedConfig(identity, main, SLOT), main


def _shared_dialog(shared):
    """开一张设置表单：**独立编辑视图 + 独立全局内存视图**，只有持久真值共用。

    对象 identity 不作为"隔离了"的判据（astra CF01-GLOBAL 的教训：登记表独立 ≠ 草稿独立）；
    这里只用它排除"又是同一个对象"，真正的隔离由第 8 节的行为交错用例钉住。
    """
    from pet.modern_settings_dialog import ModernSettingsDialog

    dialog = ModernSettingsDialog(shared, include_ai=False, standalone=False)
    form = dialog.config
    assert form is not shared, "表单必须是**独立**的编辑视图（草稿与编辑基线各自一份）"
    assert form._main is not shared._main, (
        "全局草稿真正的存放处是 Config.data：独立视图必须有自己的那一份（astra CF01-GLOBAL）")
    assert (str(form._main.path), form._main.instance_id) == (
        str(shared._main.path), shared._main.instance_id), "持久真值只有一处：同一个 config.json"
    assert (form.dir, form.instance_id) == (shared.dir, shared.instance_id)
    return dialog


def _notices(monkeypatch) -> list:
    """捕获"放弃没能与磁盘核对"那条可见诊断（``QMessageBox.warning``：通知型，无返回分支）。"""
    from PySide6.QtWidgets import QMessageBox

    seen: list = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *args, **kwargs: seen.append((args, kwargs))))
    return seen




















# ------------------------------------------------------------ 9. 设置窗挡住不可逆收口（ops P3-c）
#: 顺序纪律：设置页闸门必须在**任何**不可逆收口之前（存位置 / 停预热 / 关 Agent / 关会话
#: 写盘 worker / 摘 runtime 标记 / 关父窗 / 丢 instance）。用户选「继续编辑」→ 整次收口
#: **取消**，一个资源都不动；选「放弃」→ 收口照常走完。放在收口中途 return 只会留下半死的
#: 宠物，所以闸门在方法第一行（``_on_window_exit_requested`` 顶部）与用户退出应用入口
#: （``AppShell.request_app_quit``）。
#:
#: 这里用 ``AppShell.__new__`` 的最小桩（仓库既有测试桩做法）+ **真** ModernSettingsDialog +
#: 真关闭闸门 + 真配置目录，只有"用户点了哪个按钮"是注入的。


def _exit_host(tmp_path, app, monkeypatch, *, keep_editing: bool):
    """一只可被「退出这只」的窗 + 真设置页 + 只记调用序列的收口桩。

    返回 ``(shell, inst, dialog, calls, seen)``；``calls`` 里出现的每个名字都代表一次
    **不可逆**收口动作，闸门没拦住就会留下痕迹。
    """
    from types import SimpleNamespace

    from pet.app import AppShell

    shared, _main = _shared_route(tmp_path)
    _profile_exists(tmp_path, {"scale": 0.8})
    dialog = _shared_dialog(shared)
    dialog.show()
    seen: list = []
    _answer_with(monkeypatch, discard=not keep_editing, seen=seen)
    calls: list = []

    shell = AppShell.__new__(AppShell)
    shell.app = SimpleNamespace(quit=lambda: calls.append("quit"))
    shell.instance = SimpleNamespace()                 # slot0 占位（被退的不是它）
    shell._instances = []
    shell._refresh_tray_menu = lambda: calls.append("refresh_tray")
    shell._close_instance_session_writer = lambda inst: calls.append("close_session_writer")
    shell._enqueue_heavy_teardown = lambda inst, jobs: calls.append("heavy_teardown")
    win = SimpleNamespace(
        save_position=lambda: calls.append("save_position"),
        lib=None, agent_link_manager=None, remove_runtime_marker=lambda: calls.append("remove_marker"),
        close=lambda: calls.append("win_close"),
    )
    inst = type("FakeInstance", (), {})()      # 支持 weakref（clear_spawned_pets 要）
    inst.win = win
    inst.slot_id = SLOT
    inst.modern_settings_dialog = dialog
    inst.config = shared
    inst.legacy_chat_window = None
    inst.modern_chat_window = None
    inst.quick_chat = None
    inst.chat_settings_dialog = None
    inst.chat_window = None
    inst.broker_facade = SimpleNamespace(shutdown=lambda: calls.append("broker_shutdown"))
    shell._instances.append(inst)
    # 让设置页这次保存必然失败（外部推进了这只宠的档案代次），失败框才有出口可点
    dialog.scale_combo.setCurrentIndex(dialog.scale_combo.findData(1.0))
    _rebuild_pet(tmp_path)
    app.processEvents()
    return shell, inst, dialog, calls, seen










def test_session_end_paths_keep_the_no_dialog_semantics():
    """OS 强制会话结束那条路径**不弹**任何阻塞对话框：闸门只接用户显式的退出入口。

    机器可检：``_on_session_end`` / ``_on_about_to_quit`` 的源码里不许出现设置页闸门
    （``_settings_window_releasable`` / ``_release_settings_windows`` / ``request_app_quit``）
    ——Windows 注销/关机时弹模态框会把关机流程卡住，这是既有语义，不许被本次修复改变。
    """
    import ast

    source = Path("pet/app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    checked = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name in (
                    "_on_session_end", "_on_about_to_quit"):
                segment = ast.get_source_segment(source, item) or ""
                checked.append(item.name)
                assert "_settings_window_releasable" not in segment, (
                    f"{item.name} 不许接设置页闸门（强制会话结束不弹阻塞框）")
                assert "request_app_quit" not in segment
    assert checked == ["_on_session_end", "_on_about_to_quit"] or set(checked) == {
        "_on_session_end", "_on_about_to_quit"}, f"这两个落点必须都找到，实际 {checked}"


# ------------------------------------------------------------ 8d. 全局草稿隔离（astra CF01-GLOBAL）
#: `new_form_view` 只隔离登记表不够：全局草稿真正的存放处是 ``Config.data``。下面两条是
#: astra 最后那轮点名的**行为交错**（不靠对象 identity 宣称独立）。








# ------------------------------------------------------------ 10. 会话结束（注销/关机）的关闭路径
#: ops P2：Qt 在 aboutToQuit 之后还会 closeAllWindows，设置窗照样进 closeEvent。会话结束
#: 标记用现成的进程级闸门 ``pet.webm_clip.session_ending``（issue #111 同一个标记，conftest
#: 每个用例后自动复位），这里用真标记置位/复位，不用 monkeypatch 假函数。








# ------------------------------------------------------------ 8e. absorb 不许重引 nested 丢更新
#: 2026-10-11 父级复核：上一版 ``absorb_persisted_globals`` 用 reload + 整值 ``_pending_main``
#: 重放，恰好把 astra 早先修过的"同字典异叶丢更新"重新引了一遍（换函数名不换错）。现在的口径
#: 是：本视图**有未写差异时什么都不做**（保住自己的 baseline，由 ``Config.save`` 的递归合并
#: 提交它自己的相对差异）；干净才 reload。下面三条钉住这件事，全走真实链路
#: （``new_form_view`` → ``set``/``save`` → 自动 absorb）。


def _island(shared) -> dict:
    value = shared.get("dynamic_island")
    return dict(value) if isinstance(value, dict) else {}






