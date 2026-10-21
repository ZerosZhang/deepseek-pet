# -*- coding: utf-8 -*-
"""设置页进程隔离（PostMerge P1）聚焦测试。

覆盖规格里的六件事：
1. --settings 入口分流（免 pet.app、standalone 标志、单实例锁）；
2. standalone 保存前 reload 合并（不覆盖主进程中途改的盘；即存型开关同此契约）；
3. config 目录 watcher 触发应用链；
4. 主进程单实例锁（已持有不再拉起）与 startDetached 失败回退进程内；
5. 独立设置进程存活期气泡抑制；
6. standalone 试听接线 / 无 parent 时的 runtime 避让。

时序纪律：watcher 测试用「有界轮询 + processEvents」而不是固定 sleep 猜时序
（CI runner 是本地数倍慢，见 AGENTS.md 的 CI cost discipline）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QLockFile, QRect, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from pet import config as config_mod
from pet import slot_manager as slot_manager_mod
from pet.app import AppShell, PetInstance
from pet.config import Config


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _bare_shell(config: Config) -> AppShell:
    """最小 AppShell 桩（__new__ 绕过完整初始化，只接设置进程/监视链路）。"""
    shell = AppShell.__new__(AppShell)
    shell.config = config
    shell._instances = []
    shell._settings_child_active = False
    shell._settings_launch_at = 0.0
    shell._config_watcher = None
    shell._config_reload_timer = None
    shell._settings_watch_timer = None
    shell._last_config_signature = None
    return shell


# ---------------------------------------------------------------- 1. 入口分流

def test_main_routes_settings_flag_to_settings_process(monkeypatch):
    """`python -m pet --settings` 走独立设置进程分支。"""
    import pet.__main__ as entry

    calls = []
    monkeypatch.setattr(entry, "_run_settings", lambda: calls.append(1) or 0)
    monkeypatch.setattr(sys, "argv", ["pet", "--settings"])
    assert entry._main() == 0
    assert calls == [1]


def test_settings_instance_id_parsing():
    """--instance 解析（多窗场景主进程显式传参用）。"""
    import pet.__main__ as entry

    assert entry._settings_instance_id(["pet", "--settings"]) == ""
    assert entry._settings_instance_id(["pet", "--settings", "--instance", "slot-2"]) == "slot-2"
    assert entry._settings_instance_id(["pet", "--settings", "--instance"]) == ""


class _AutoCloseDialog(QDialog):
    """假对话框：show() 后立刻让事件循环退出（避免测试真阻塞）。"""

    captured: dict = {}

    def __init__(self, config, parent=None, *, include_ai=True, standalone=False):
        super().__init__(parent)
        type(self).captured = {
            "config": config,
            "parent": parent,
            "include_ai": include_ai,
            "standalone": standalone,
        }

    def show(self) -> None:  # noqa: N802 - Qt API
        super().show()
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)


def test_exec_settings_builds_standalone_dialog(tmp_path, monkeypatch):
    """--settings 主体：parent=None + standalone=True，退出时释放 settings.lock。"""
    import pet.__main__ as entry
    import pet.modern_settings_dialog as settings_mod

    app = _qapp()
    monkeypatch.setattr(settings_mod, "ModernSettingsDialog", _AutoCloseDialog)
    _AutoCloseDialog.captured = {}
    config = Config(base=tmp_path)
    previous = app.quitOnLastWindowClosed()
    try:
        assert entry._run_settings(config) == 0
    finally:
        app.setQuitOnLastWindowClosed(previous)
    assert _AutoCloseDialog.captured["standalone"] is True
    assert _AutoCloseDialog.captured["parent"] is None
    assert _AutoCloseDialog.captured["include_ai"] is True
    # 锁文件用完即释放（QLockFile 解锁会删文件），主进程据此判定设置页已关闭
    assert not (config.dir / "settings.lock").exists()


def test_exec_settings_exits_when_another_settings_process_holds_lock(tmp_path, monkeypatch):
    """单实例：锁已被持有（另一个设置进程在跑）时不再开第二个对话框。"""
    import pet.__main__ as entry
    import pet.modern_settings_dialog as settings_mod

    config = Config(base=tmp_path)
    config.dir.mkdir(parents=True, exist_ok=True)
    held = QLockFile(str(config.dir / "settings.lock"))
    assert held.tryLock(0)
    created = []
    monkeypatch.setattr(settings_mod, "ModernSettingsDialog", lambda *a, **k: created.append(1))
    try:
        assert entry._exec_settings(_qapp(), config) == 0
    finally:
        held.unlock()
    assert created == []




def test_packaging_entries_route_settings_before_importing_app():
    """打包入口必须在 import pet.app 之前分流 --settings，否则子进程跑成桌宠。"""
    root = Path(__file__).resolve().parents[1]
    for name in ("packaging/pet_entry.py", "packaging/pet_entry_no_chat.py"):
        source = (root / name).read_text(encoding="utf-8")
        settings_at = source.index('"--settings" in sys.argv')
        app_import_at = source.index("from pet.app import main")
        assert settings_at < app_import_at, f"{name}: --settings 分流必须在 import pet.app 之前"
        assert "from pet.__main__ import _run_settings" in source


# ------------------------------------------------- 2. standalone 保存前 reload





# ------------------------------------------------------------ 3. config watcher



def test_config_watcher_ignores_unrelated_directory_churn(tmp_path):
    """目录里非 config.json 的变动不得触发应用链（basename 过滤）。"""
    app = _qapp()
    config = Config(base=tmp_path)
    config.dir.mkdir(parents=True, exist_ok=True)
    assert config.save()
    shell = _bare_shell(config)
    shell._install_config_watcher()
    applied = []
    try:
        shell._apply_external_config_change = lambda: applied.append(1)
        # 触发目录变动但不是 config.json：例如设置页锁文件的出现
        (config.dir / "settings.lock").write_text("x", encoding="utf-8")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert applied == []
    finally:
        shell._teardown_config_watcher()




# ------------------------------------------------------- 4. 单实例 / 降级回退

def test_open_settings_process_skips_when_lock_already_held(tmp_path):
    """主进程单实例：settings.lock 已被持有 → 不再拉起（日志路径）。"""
    config = Config(base=tmp_path)
    config.dir.mkdir(parents=True, exist_ok=True)
    shell = _bare_shell(config)
    launched = []
    shell._launch_settings_process = lambda instance=None: launched.append(1) or True
    held = QLockFile(str(config.dir / "settings.lock"))
    assert held.tryLock(0)
    try:
        assert shell.open_settings_process(object()) is True
    finally:
        held.unlock()
        shell._teardown_config_watcher()
    assert launched == []
    assert shell._settings_child_active is True


def test_open_settings_process_disabled_by_config(tmp_path):
    """settings_process_isolation=False → 完全走旧路径（不拉起、不装 watcher）。"""
    config = Config(base=tmp_path)
    config.set("settings_process_isolation", False)
    shell = _bare_shell(config)
    launched = []
    shell._launch_settings_process = lambda instance=None: launched.append(1) or True
    assert shell.open_settings_process(object()) is False
    assert launched == []
    assert shell._config_watcher is None




def test_open_modern_settings_does_not_build_inprocess_dialog_when_launched(tmp_path, monkeypatch):
    """拉起成功 → 不再构造进程内对话框。"""
    import pet.modern_settings_dialog as settings_mod

    _qapp()
    owner = PetInstance.__new__(PetInstance)
    owner.config = Config(base=tmp_path)
    owner.shell = AppShell.__new__(AppShell)
    owner.shell.enable_chat = True
    owner.shell.open_settings_process = lambda instance: True
    owner.win = mock.Mock()
    owner.modern_settings_dialog = None
    owner.chat_settings_dialog = None
    created = []
    monkeypatch.setattr(settings_mod, "ModernSettingsDialog", lambda *a, **k: created.append(1))
    owner.open_modern_settings()
    assert created == []
    assert owner.modern_settings_dialog is None


def test_launch_settings_process_uses_source_command(tmp_path, monkeypatch):
    """源码运行：python -m pet --settings（工作目录取仓库根）。"""
    import pet.app as app_mod

    shell = _bare_shell(Config(base=tmp_path))
    calls = []
    monkeypatch.setattr(app_mod.sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        AppShell, "_spawn_settings_process",
        staticmethod(lambda program, arguments, workdir, environment:
                     calls.append((program, arguments, workdir)) or True),
    )
    assert shell._launch_settings_process() is True
    program, arguments, workdir = calls[0]
    assert program == sys.executable
    assert arguments == ["-m", "pet", "--settings"]
    assert Path(workdir) == Path(app_mod.__file__).resolve().parent.parent


def test_launch_settings_process_failure_is_reported(tmp_path, monkeypatch):
    """detach 启动失败 → _launch_settings_process 返回 False（触发回退）。"""
    import pet.app as app_mod

    shell = _bare_shell(Config(base=tmp_path))
    monkeypatch.setattr(app_mod.sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        AppShell, "_spawn_settings_process",
        staticmethod(lambda program, arguments, workdir, environment: False),
    )
    assert shell._launch_settings_process() is False


def test_launch_settings_process_tells_child_the_running_topology(tmp_path, monkeypatch):
    """R01：子进程拿到的是**拉起它的主进程运行中拓扑**，不是磁盘上下一次启动的配置。

    主进程启动时读一次拓扑并快照定死（app.start()）；此后用户在设置页勾上「直播
    捕获兼容」只改磁盘，正在跑的这个进程仍是 overlay。设置子进程若只按磁盘判就是
    legacy，子宠页会把全部设置写进 ``config-slot-N.json``，而运行中的 overlay 主进程
    对非 per-slot 键只读主配置——"保存成功、实际无效"。
    """
    import pet.app as app_mod
    from pet import overlay_settings_command as cmd_mod

    config = Config(base=tmp_path)
    assert config.save() is True
    cmd_mod.reset_topology_snapshot()
    monkeypatch.delenv(cmd_mod.ENV_TOPOLOGY, raising=False)
    monkeypatch.delenv(cmd_mod.ENV_PARENT_TOPOLOGY, raising=False)
    assert cmd_mod.is_overlay_topology() is True, "用例前置：启动时判成 overlay 并快照"

    # 用户勾选「直播捕获兼容」并保存（重启后生效，本进程没重启）
    external = Config(base=tmp_path)
    external.set("stream_capture_mode", True)
    assert external.save() is True
    on_disk = json.loads(config.path.read_text(encoding="utf-8"))
    assert on_disk["stream_capture_mode"] is True, "用例前置：磁盘已开启捕获模式"

    shell = _bare_shell(config)
    calls = []
    monkeypatch.setattr(app_mod.sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        AppShell, "_spawn_settings_process",
        staticmethod(lambda program, arguments, workdir, environment:
                     calls.append(environment) or True),
    )
    assert shell._launch_settings_process() is True

    environment = calls[0]
    assert environment.value(cmd_mod.ENV_PARENT_TOPOLOGY) == "overlay", \
        "磁盘捕获开关不得改写父进程运行中拓扑的陈述"


def test_spawn_settings_process_hands_environment_to_the_detached_child(
        tmp_path, monkeypatch):
    """真起一个 detach 子进程：注入的 env 必须到得了子进程（不是只写进对象）。

    这条是真机机制验证（不 mock Qt）：``QProcess`` 实例 + ``startDetached()`` +
    ``setProcessEnvironment``。设置子进程侧读到的就是这条 env（见
    ``overlay_settings_command.is_overlay_topology`` 的判定链）。
    """
    from PySide6.QtCore import QProcessEnvironment

    out = tmp_path / "child-env.txt"
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("DSH_PET_PARENT_TOPOLOGY", "overlay")

    script = (
        "import os, pathlib, sys;"
        "pathlib.Path(sys.argv[1]).write_text("
        "os.environ.get('DSH_PET_PARENT_TOPOLOGY', 'MISSING'), encoding='utf-8')"
    )
    started = AppShell._spawn_settings_process(
        sys.executable, ["-c", script, str(out)], str(tmp_path), environment)

    assert started is True
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline and not out.exists():
        time.sleep(0.05)
    assert out.exists(), "子进程没跑起来（detach 机制坏了）"
    assert out.read_text(encoding="utf-8") == "overlay"


# ------------------------------------------------------------- 5. 气泡抑制

def test_bubble_suppressed_while_external_settings_process_runs(tmp_path):
    """独立设置进程存活期抑制气泡；锁释放后恢复。"""
    owner = PetInstance.__new__(PetInstance)
    owner.config = Config(base=tmp_path)
    owner.shell = AppShell.__new__(AppShell)
    owner.shell._settings_child_active = True
    owner.modern_settings_dialog = None
    owner.chat_settings_dialog = None
    calls = []
    owner.win = mock.Mock()
    owner.win.set_bubble_suppressed = lambda value: calls.append(value)
    owner._update_bubble_suppression_for_settings()
    assert calls == [True]
    owner.shell._settings_child_active = False
    owner._update_bubble_suppression_for_settings()
    assert calls == [True, False]


def test_poll_settings_process_clears_suppression_after_child_exit(tmp_path):
    """轮询兜底：锁文件消失（设置进程退出）→ 解除存活标记与抑制。"""
    config = Config(base=tmp_path)
    shell = _bare_shell(config)
    owner = PetInstance.__new__(PetInstance)
    owner.config = config
    owner.shell = shell
    owner.modern_settings_dialog = None
    owner.chat_settings_dialog = None
    suppressed = []
    owner.win = mock.Mock()
    owner.win.set_bubble_suppressed = lambda value: suppressed.append(value)
    shell._instances = [owner]
    shell._install_config_watcher()
    try:
        shell._mark_settings_child(True)
        assert shell._settings_child_active is True
        assert suppressed == [True]
        # 子进程"刚启动"窗口内不误判（锁还没建好）
        shell._settings_launch_at = time.monotonic()
        shell._poll_settings_process()
        assert shell._settings_child_active is True
        # 启动窗口过后锁仍不存在 → 判定子进程已退出，解除抑制
        shell._settings_launch_at = time.monotonic() - 10.0
        shell._poll_settings_process()
        assert shell._settings_child_active is False
        assert suppressed == [True, False]
    finally:
        shell._teardown_config_watcher()


def test_modern_settings_finished_delegates_to_shell_apply_chain(tmp_path):
    """真实壳形状（有 _instances）时 finished 走 AppShell._apply_external_config_change。"""
    _qapp()
    owner = PetInstance.__new__(PetInstance)
    owner.shell = AppShell.__new__(AppShell)
    owner.shell._instances = []
    # 真实壳恒有 config（_modern_settings_finished 末尾无条件走一次台词预缓存，
    # 那条入口自己按开关收敛，壳上没有 config 只可能是测试桩少给了）
    owner.shell.config = Config(base=tmp_path)
    calls = []
    owner.shell._apply_external_config_change = lambda: calls.append(1)
    owner.modern_settings_dialog = object()
    owner.config = Config(base=tmp_path)
    owner.win = None
    PetInstance._modern_settings_finished(owner, 0)
    assert calls == [1]
    assert owner.modern_settings_dialog is None


# ------------------------------------------- 6. standalone 试听 / runtime 避让











def test_standalone_geometry_ignores_dead_process_markers(tmp_path):
    """死者留下的 runtime 标记不算桌宠位置（返回 None）。"""
    import pet.settings_standalone as standalone_mod

    config = Config(base=tmp_path)
    config.dir.mkdir(parents=True, exist_ok=True)
    marker = config.dir / "pet-runtime-v2-999999-slot-0.json"
    marker.write_text(
        json.dumps({"pid": 999999, "x": 1, "y": 2, "w": 30, "h": 40}),
        encoding="utf-8",
    )
    # pid 999999 必然不存活（Windows 上上限远低于该值；POSIX 同理）
    assert standalone_mod.standalone_pet_geometry(config) is None


# ------------------------------------------------------------ 配置键契约

def test_settings_process_isolation_default_true_and_normalized(tmp_path):
    """默认 True；脏值字符串 "false" 必须归一为 False（bool("false") 陷阱）。"""
    assert Config(base=tmp_path / "fresh").get("settings_process_isolation") is True
    cfg_dir = tmp_path / config_mod.APP_DIR_NAME
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"version": 4, "settings_process_isolation": "false"}),
        encoding="utf-8",
    )
    assert Config(base=tmp_path).get("settings_process_isolation") is False


def test_settings_process_isolation_survives_reload(tmp_path):
    """reload 白名单必须认这个键（否则外部写盘会被内存旧值盖回去）。"""
    config = Config(base=tmp_path)
    external = Config(base=tmp_path)
    external.set("settings_process_isolation", False)
    assert external.save()
    config.reload()
    assert config.get("settings_process_isolation") is False


def test_settings_standalone_module_does_not_import_heavy_modules():
    """pet.settings_standalone 顶层不得 import voice_chime_service / pet.app。

    试听/节日服务必须留给点击时惰性 import，否则独立设置进程启动就白付
    edge-tts/QtMultimedia 的导入成本（违反"standalone 启动只许懒加载"）。
    """
    path = Path(__file__).resolve().parents[1] / "pet" / "settings_standalone.py"
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if line[:1].isspace():
            continue  # 函数内惰性 import 合法（这正是本用例要守的形态）
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            continue
        assert "voice_chime_service" not in stripped, f"settings_standalone.py:{lineno} 顶层 import 回潮"
        assert "pet.app" not in stripped, f"settings_standalone.py:{lineno} 顶层 import 回潮"


# ------------------------------------------------- 7. D12「退出子肥鱼」指令分流

def _clear_dialog(config):
    """standalone 设置页（无 parent、无 PetWindow 回调面）= 独立设置进程形态。"""
    from pet.modern_settings_dialog import ModernSettingsDialog

    _qapp()
    return ModernSettingsDialog(config, include_ai=False, standalone=True)














