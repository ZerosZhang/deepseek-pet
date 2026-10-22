import json
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication
from pet.config import APP_DIR_NAME
from pet import pet_profiles as profiles
from tests.test_overlay_spawn import _make_persistent_shell

app = QApplication.instance() or QApplication([])


def test_close_zero_preserves_children_and_restores_identity(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    shell.spawn_pet()
    shell.spawn_pet()
    children = list(shell._spawned)
    directory = tmp_path / APP_DIR_NAME
    before = {n: profiles.slot_profile_path(directory, n).read_bytes() for n in (1, 2)}
    try:
        assert shell.exit_pet(shell.sprite)
        assert shell.sprite is None
        assert shell._spawned == children
        assert shell._active_slots() == [1, 2]
        shell.overlay.show()
        assert shell.alert_target_sprite() is children[0]
        shell.handle_geometry_changed()
        assert all(profiles.slot_profile_path(directory, n).read_bytes() == before[n] for n in before)
        shell.spawn_pet()
        assert shell.sprite is not None
        assert shell._active_slots() == [0, 1, 2]
        shell.spawn_pet()
        assert shell._spawned_slots[shell._spawned[-1]] == 3
    finally:
        shell.stop()


def test_v2_empty_builds_no_pet(tmp_path):

    directory = tmp_path / APP_DIR_NAME
    directory.mkdir()
    (directory / profiles.ACTIVE_SET_FILENAME).write_text(json.dumps({'version': 2, 'slots': []}), encoding='utf8')
    from tests.test_overlay_window_capabilities import CapInstance, FakeScreen
    from pet.config import Config
    from pet.overlay_shell import OverlayShell
    shell = OverlayShell(app, CapInstance(Config(base=tmp_path, instance_id='')),
                         screen=FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)))
    try:
        assert shell.sprite is None
        assert shell.overlay.sprites == []
        assert profiles.load_active_set(directory).slots == ()
        assert not shell.driver._timer.isActive()
    finally:
        shell.stop()


def test_spawn_failure_leaves_no_partial_sprite(tmp_path, monkeypatch):
    shell, _ = _make_persistent_shell(tmp_path)
    before = list(shell.overlay.sprites)
    def fail(*args):
        raise RuntimeError('apply failed')
    monkeypatch.setattr(shell, '_apply_sprite_settings_to', fail)
    shell.spawn_pet()
    assert shell.overlay.sprites == before
    assert shell._active_slots() == [0]
    assert shell._spawned == []




def test_slot_focus_does_not_activate_inactive_profile(tmp_path):
    shell, _ = _make_persistent_shell(tmp_path)
    shell.spawn_pet()
    child = shell._spawned[0]
    shell.set_sprite_visible(child, False)
    assert shell.select_slot(1)
    assert child.visible and shell.overlay.isVisible()
    before = shell._active_slots()
    assert not shell.select_slot(128)
    assert shell._active_slots() == before






def test_three_distinct_profiles_close_restore_generate_restart(tmp_path):
    directory = tmp_path / APP_DIR_NAME
    for slot, role, rx, speed in ((0, 'shenshen', 0.3, 0.5), (1, 'nova', 0.5, 1.5), (2, 'cat', 0.7, 2.0)):
        profiles.write_profile_settings(directory, slot, {'character': role, 'rx': rx, 'ry': 0.4,
            'scale': 0.4, 'playback_speed': speed})
    profiles.save_active_set(directory, [0, 1, 2])
    shell, _ = _make_persistent_shell(tmp_path)
    before = {n: profiles.slot_profile_path(directory, n).read_bytes() for n in (1, 2)}
    assert shell.exit_pet(shell.sprite)
    assert all(profiles.slot_profile_path(directory, n).read_bytes() == before[n] for n in before)
    shell.spawn_pet()
    assert shell._sprite_config(shell.sprite).get('character') == 'shenshen'
    shell.spawn_pet()
    assert shell._spawned_slots[shell._spawned[-1]] == 3
    shell.save_position()
    shell.save_spawned_positions()
    restarted, _ = _make_persistent_shell(tmp_path)
    assert restarted._active_slots() == [0, 1, 2, 3]
    for n, role, speed in ((0, 'shenshen', 0.5), (1, 'nova', 1.5), (2, 'cat', 2.0)):
        sprite = restarted._sprite_for_slot(n)
        assert restarted._sprite_config(sprite).get('character') == role
        assert sprite.playback_speed == speed


def test_no_tray_recovery_button_is_visible_and_restores(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon, QPushButton
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', lambda: False)
    directory = tmp_path / APP_DIR_NAME
    profiles.save_active_set(directory, [])
    from pet.config import Config
    from pet.overlay_shell import OverlayShell
    from tests.test_overlay_window_capabilities import CapInstance, FakeScreen
    shell = OverlayShell(app, CapInstance(Config(base=tmp_path, instance_id='')),
        screen=FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)))
    assert shell._recovery_window.isVisible()
    button = next(b for b in shell._recovery_window.findChildren(QPushButton) if '生成' in b.text())
    button.click()
    assert shell.sprite is not None
    assert shell._active_slots() == [0]
    shell._recovery_window.close()






# ---------------------------------------------------------------- ops D1/D2（2026-10-10 终审）

def test_migration_statuses_separate_slot_only_from_global(tmp_path):
    """ops D2：迁移失败按**结果类型**处置——单槽损坏可降级，其它一律不许吞。

    "一份 slot0 档案坏了"与"全局配置读不出来 / 备份失败 / 锁超时"是两种事故：
    前者只牵连那一个槽（保留原文件、该槽空着，用户显式动作再恢复），后者涉及全局面
    或迁移基础设施，必须照旧硬失败。把两者都当"异常"一起吞掉，等于用不可信的全局配置
    继续跑。
    """
    slot_only = profiles.Slot0Migration(status="target-corrupt")
    assert slot_only.ok is False and slot_only.slot_only_problem is True
    for status in ("source-corrupt", "source-unreadable", "refused-slot-source",
                   "backup-invalid", "backup-failed", "write-failed", "lock-timeout"):
        migration = profiles.Slot0Migration(status=status)
        assert migration.ok is False
        assert migration.slot_only_problem is False, status


def test_corrupt_slot0_profile_is_reported_as_target_corrupt(tmp_path):
    """真生产者：坏 slot0 档案 → ``target-corrupt``（带路径），不覆盖、不清源。"""
    from pet.config import Config

    cfg = Config(base=tmp_path, instance_id='')
    cfg.dir.mkdir(parents=True, exist_ok=True)
    (cfg.dir / 'config.json').write_text(json.dumps({"version": 4, "scale": 0.8}), encoding='utf8')
    broken = cfg.dir / profiles.slot_profile_path(cfg.dir, 0).name
    broken.write_bytes(b'{ "scale": 0.8, broken')
    before = broken.read_bytes()

    migration = profiles.migrate_slot0_profile(cfg.dir)

    assert migration.status == 'target-corrupt'
    assert migration.slot_only_problem is True
    assert migration.profile_path == broken
    assert broken.read_bytes() == before


def test_corrupt_slot0_profile_does_not_break_the_overlay_shell(tmp_path):
    """ops D2（真壳）：坏 slot0 档案不许让整个 overlay 壳起不来。

    旧处置是 ``raise RuntimeError`` → 启动失败对话框 → 全局配置、其它槽、提醒、托盘
    全不可用，对话框里连文件路径都没有。现在只降级那一个槽：主 sprite 不复活、
    其它 active 子照常、原文件一个字节不动、活跃集合也不被启动期改写。
    """
    from pet.config import Config
    from pet.overlay_shell import OverlayShell
    from tests.test_overlay_window_capabilities import CapInstance, FakeScreen

    directory = tmp_path / APP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'config.json').write_text(json.dumps({"version": 4}), encoding='utf8')
    profiles.save_active_set(directory, [0, 1])
    assert profiles.write_profile_settings(directory, 1, {'character': 'nova'}).status == 'ok'
    broken = directory / profiles.slot_profile_path(directory, 0).name
    broken.write_bytes(b'{broken')
    before_broken = broken.read_bytes()
    active_path = directory / profiles.ACTIVE_SET_FILENAME
    before_active = active_path.read_bytes()

    shell = OverlayShell(
        app, CapInstance(Config(base=tmp_path, instance_id='')),
        screen=FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)))
    try:
        assert shell.sprite is None, '坏档案的那个槽先空着'
        assert shell._remembered_active == [1], '只摘掉坏掉的那个槽'
        assert [shell._spawned_slots[s] for s in shell._spawned] == [1], '其它 active 子照常复活'
    finally:
        shell.stop()

    assert broken.read_bytes() == before_broken, '坏档案一个字节都不许动（不自动修复）'
    assert active_path.read_bytes() == before_active, '启动不替用户改活跃集合'




def _corrupt_slot0_app(tmp_path):
    """真 AppShell + 坏 slot0 档案（只断言诊断口径时用）。"""
    from pet.config import Config

    cfg = Config(base=tmp_path, instance_id='')
    directory = cfg.dir
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'config.json').write_text(json.dumps({"version": 4}), encoding='utf8')
    profiles.save_active_set(directory, [0])
    broken = profiles.slot_profile_path(directory, 0)
    broken.write_bytes(b'{broken')
    return cfg, broken






def test_explicit_spawn_over_a_corrupt_active_set_backs_up_and_writes(tmp_path):
    """ops D1：坏活跃集合 + 用户显式生成 → 先备份再覆盖，不许"永远落不进盘"。

    旧行为：默认 ``refuse`` 让每次 save 都 ``refused-corrupt``，只有一条 warning——
    用户看到的是「生成了 → 重启又没了」，UI 里没有任何解释，也永远修不好。
    """
    shell, _ = _make_persistent_shell(tmp_path)
    directory = tmp_path / APP_DIR_NAME
    active_path = directory / profiles.ACTIVE_SET_FILENAME
    active_path.write_text('{not json', encoding='utf8')
    try:
        shell.spawn_pet()

        result = profiles.load_active_set(directory)
        assert result.status == 'ok', '显式生成必须真的把活跃集合写成可信状态'
        assert set(result.slots) == {0, 1}
        backups = list(directory.glob(
            f'{profiles.ACTIVE_SET_FILENAME}{profiles.CORRUPT_BACKUP_MARKER}*'))
        assert backups, '坏文件必须先备份再覆盖（不静默销毁）'
        assert backups[0].read_text(encoding='utf8') == '{not json'
    finally:
        shell.stop()


def test_active_set_write_failure_is_visible_and_not_faked(tmp_path, monkeypatch):
    """ops D1：写不进去必须**可见**（气泡点名路径）+ 返回值如实 False，不许假成功。"""
    from pet import pet_profiles as profiles_mod

    shell, _ = _make_persistent_shell(tmp_path)
    feedback: list = []
    shell.show_bubble = lambda text, **kw: feedback.append(text) or True
    seen_kwargs: list = []
    target = shell._spawn_config_dir() / profiles_mod.ACTIVE_SET_FILENAME

    def fake_save(config_dir, slots, **kwargs):
        seen_kwargs.append(kwargs)
        return profiles_mod.ProfileResult(status='lock-timeout', path=target,
                                          reason='controlled contention')

    monkeypatch.setattr(profiles_mod, 'save_active_set', fake_save)
    try:
        assert shell._persist_active_slots() is False, '失败不许假报成功'
        assert seen_kwargs and seen_kwargs[0].get('on_broken') == 'backup-overwrite', (
            '显式生成/关闭这条路必须走先备份再覆盖的既有 API')
        assert feedback and str(target) in feedback[0], '失败必须可见并点名文件路径'
    finally:
        shell.stop()


# ---------------------------------------------------------------- ops D2-新（2026-10-10 终审复核）
def _broken_slot0_shell(base, *, active):
    """真 OverlayShell + 坏 ``config-slot-0.json``（原文件保留、其它槽照常）。"""
    from pet.config import Config
    from pet.overlay_shell import OverlayShell
    from tests.test_overlay_window_capabilities import CapInstance, FakeScreen

    directory = base / APP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'config.json').write_text(json.dumps({"version": 4}), encoding='utf8')
    profiles.save_active_set(directory, list(active))
    broken = profiles.slot_profile_path(directory, 0)
    broken.write_bytes(b'{broken')
    shell = OverlayShell(
        app, CapInstance(Config(base=base, instance_id='')),
        screen=FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)))
    return shell, directory, broken


def test_spawn_over_a_corrupt_slot0_is_visible_and_keeps_children(tmp_path):
    """ops D2-新：坏 slot0 期间生成**不许静默失败**，健康子照常活。

    终审链条：启动降级后 ``_remembered_active`` 不含 0 → 分配器仍按**最小非活跃槽**
    回到 0（这是用户的明确取舍：不静默跳号、不改分配语义）→ ``_build_slot_sprite(0)``
    读坏档案抛错 → 旧实现只有一条 ``logging.exception``。用户眼里就是"点了没反应"，
    而且**每次点都一样**（正是 B01 要消灭的那类失败）。

    本用例钉住：失败必须带**路径**可见、健康子不受牵连、活跃集合不被改写、坏档案
    一个字节不动；档案修好后再生成照常恢复 slot0。
    """
    shell, directory, broken = _broken_slot0_shell(tmp_path, active=[0, 1])
    assert profiles.write_profile_settings(directory, 1, {'character': 'nova'}).status == 'ok'
    before = broken.read_bytes()
    spoken: list = []
    try:
        (child,) = shell._spawned
        assert shell._spawned_slots[child] == 1
        shell.overlay.show()
        shell._show_bubble_text = lambda text, duration_ms=0, **kw: (
            spoken.append(str(text)), True)[1]

        shell.spawn_pet()                       # 目标仍是 slot0（不跳号）

        assert spoken, '生成失败必须可见（旧实现只 logging.exception）'
        assert str(broken) in spoken[0], '可见反馈必须点名坏档案路径'
        assert 'slot-0' in spoken[0]
        assert shell.sprite is None, '失败的 slot0 不许留下半只'
        assert shell._spawned == [child] and shell._spawned_slots[child] == 1, '健康子继续活'
        assert shell._active_slots() == [1], '失败不改活跃集合'
        assert broken.read_bytes() == before, '坏档案一个字节都不许动（不自动修复）'

        # 修好档案 → 同一进程里再次生成恢复 slot0（失败是可恢复的，不是死状态）
        broken.write_text(json.dumps({"version": 4, "character": "nova"}), encoding='utf8')
        shell.spawn_pet()
        assert shell.sprite is not None, '档案修好后生成必须恢复 slot0'
        assert shell._active_slots() == [0, 1]
    finally:
        shell.stop()


def test_spawn_failure_reaches_the_recovery_window_when_no_pet_is_visible(tmp_path):
    """无宠时冒不出泡：同一份带路径的说明必须落到**可见恢复窗**，并留修复入口。

    无宠期（刚关掉最后一只 / 全隐藏）气泡没有落点，反馈只剩日志就等于又回到静默。
    恢复窗此时是唯一的可见入口，故失败说明要写进它，并且「打开配置目录」这条
    "去修档案"的入口必须在（本批次不做自动修复，只给路）。
    """
    from PySide6.QtWidgets import QPushButton

    shell, directory, broken = _broken_slot0_shell(tmp_path, active=[])
    try:
        assert shell.sprite is None and not shell._spawned

        shell.spawn_pet()

        window = getattr(shell, '_recovery_window', None)
        assert window is not None, '无宠失败必须给出可见恢复窗'
        assert window.isVisible(), '恢复窗必须真的显示出来（不是建了不 show）'
        label = getattr(shell, '_recovery_diagnosis_label', None)
        assert label is not None and str(broken) in label.text(), '说明必须带档案路径'
        buttons = [b.text() for b in window.findChildren(QPushButton)]
        assert any('配置目录' in text for text in buttons), (
            '必须给出"去打开配置目录修档案"的入口：%s' % buttons)
        assert any('设置' in text for text in buttons), '保留该槽设置入口'
    finally:
        window = getattr(shell, '_recovery_window', None)
        if window is not None:
            window.close()
        shell.stop()



