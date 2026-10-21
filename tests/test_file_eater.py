# -*- coding: utf-8 -*-
"""“吃垃圾文件”拖放模拟功能测试：只记录，绝不真删/移动文件。"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QWidget

from pet.file_eater import FileEaterDropHandler, format_bytes
from pet.window_optional_services import WindowFeatureGateMixin


class _FakePet(QWidget):
    def __init__(self, config_dir):
        super().__init__()
        self.cfg_dir = config_dir
        self.acts = ["待机", "吃Token", "吃西瓜"]
        self.anim_requests = []
        self.bubbles = []

    @property
    def cfg(self):
        class _Cfg:
            pass

        obj = _Cfg()
        obj.dir = self.cfg_dir
        return obj

    def request_link_anim(self, name):
        self.anim_requests.append(name)

    def show_bubble(self, text, duration_ms=3200, subtitle=None):
        self.bubbles.append((text, subtitle))


def _qapp():
    return QApplication.instance() or QApplication([])


def _make_pet(tmp_path):
    _qapp()
    return _FakePet(tmp_path)


class _FakePetWindow(QWidget, WindowFeatureGateMixin):
    def __init__(self, config_dir):
        super().__init__()
        self.acts = ["待机", "吃Token"]
        self.cfg = type("Cfg", (), {"dir": config_dir})()


def test_install_file_eater_is_idempotent_and_accepts_drops(tmp_path):
    _qapp()
    pet = _FakePetWindow(tmp_path)
    assert pet._file_eater is None

    first = pet.install_file_eater()
    assert pet.acceptDrops() is True
    assert first is pet._file_eater
    assert pet.install_file_eater() is first


def test_eat_paths_records_stats_plays_eat_animation_and_keeps_files(tmp_path):
    pet = _make_pet(tmp_path)
    first = tmp_path / "junk-a.log"
    first.write_text("0123456789", encoding="utf-8")
    second = tmp_path / "junk-b.bin"
    second.write_text("x" * 2048, encoding="utf-8")
    folder = tmp_path / "junk-dir"
    folder.mkdir()
    inner = folder / "inner.tmp"
    inner.write_text("y" * 512, encoding="utf-8")

    handler = FileEaterDropHandler(pet)
    result = handler.eat_paths([str(first), str(second), str(folder)])

    # 文件只是“被吃”，真实内容不能动。
    assert first.read_text(encoding="utf-8") == "0123456789"
    assert second.stat().st_size == 2048
    assert inner.read_text(encoding="utf-8") == "y" * 512

    # 动画优先选更贴近“吃数字垃圾”的吃Token。
    assert pet.anim_requests == ["吃Token"]
    assert len(pet.bubbles) == 1
    assert "文件没有删除或移动" in pet.bubbles[0][1]

    stats_path = tmp_path / "file_eaten_stats.json"
    assert stats_path.is_file()
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    assert stats["feed_count"] == 1
    assert stats["file_count"] == 2
    assert stats["folder_count"] == 1
    assert stats["item_count"] == 3
    assert stats["total_bytes"] == 10 + 2048 + 512

    # 再吃一个文件，累计统计继续增加。
    third = tmp_path / "junk-c.tmp"
    third.write_text("z" * 100, encoding="utf-8")
    handler.eat_paths([str(third)])
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    assert stats["feed_count"] == 2
    assert stats["file_count"] == 3
    assert stats["total_bytes"] == 10 + 2048 + 512 + 100
    assert result["stats"]["total_bytes"] == 10 + 2048 + 512


def test_drag_and_drop_events_are_accepted_and_fed(tmp_path):
    pet = _make_pet(tmp_path)
    target = tmp_path / "drop.txt"
    target.write_text("drop", encoding="utf-8")

    handler = FileEaterDropHandler(pet)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(target))])

    drag = QDragEnterEvent(
        QPoint(0, 0),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert handler.eventFilter(pet, drag) is True
    assert drag.isAccepted()

    pet.anim_requests.clear()
    drop = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert handler.eventFilter(pet, drop) is True
    assert drop.isAccepted()
    assert pet.anim_requests == ["吃Token"]
    assert (tmp_path / "file_eaten_stats.json").is_file()


def test_format_bytes_has_human_readable_units():
    assert format_bytes(0) == "0 B"
    assert format_bytes(1023) == "1023 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_bytes(3 * 1024 * 1024) == "3.0 MB"
    assert format_bytes(4 * 1024 * 1024 * 1024) == "4.0 GB"




class _InterpretPet(_FakePet):
    """投喂链 + **真实**解读控制器接线所需的窗口面（cfg 既要 ``.dir`` 也要 ``.get``）。"""

    def __init__(self, config_dir):
        super().__init__(config_dir)
        self.alerts: list[tuple[str, dict]] = []

    @property
    def cfg(self):
        class _Cfg:
            dir = None

            @staticmethod
            def get(key, default=None):
                return {"enabled": True} if key == "file_interpret" else default

        obj = _Cfg()
        obj.dir = self.cfg_dir
        return obj

    def show_alert(self, text, **kwargs):
        self.alerts.append((text, kwargs))


# ---------------------------------------------------------------- B03：扫描预算
def _big_dir(tmp_path, name, count):
    folder = tmp_path / name
    folder.mkdir()
    for i in range(count):
        (folder / f"f{i:05d}.bin").write_text("x" * 10, encoding="utf-8")
    return folder


def test_small_drop_reports_no_truncation(tmp_path):
    """小目录/散文件不触预算：旧口径（文件数/文件夹数/字节数）一个不少。"""
    pet = _make_pet(tmp_path)
    folder = tmp_path / "small-dir"
    folder.mkdir()
    (folder / "inner.bin").write_text("x" * 7, encoding="utf-8")
    loose = tmp_path / "loose.bin"
    loose.write_text("y" * 3, encoding="utf-8")

    result = FileEaterDropHandler(pet).eat_paths([str(folder), str(loose)])

    assert result["files"] == 1
    assert result["folders"] == 1
    assert result["bytes"] == 10
    assert result["truncated"] is False
    assert result["scanned"] == 2
    assert "只统计了前" not in pet.bubbles[0][0]


def test_eat_paths_stops_at_file_budget(tmp_path, monkeypatch):
    """B03：文件数预算——触上限即停扫，统计/气泡用真实口径（不是全量数）。"""
    import pet.file_eater as file_eater

    monkeypatch.setattr(file_eater, "SCAN_FILE_LIMIT", 3)
    pet = _make_pet(tmp_path)
    folder = _big_dir(tmp_path, "big-dir", 6)

    result = FileEaterDropHandler(pet).eat_paths([str(folder)])

    assert result["truncated"] is True
    assert result["scanned"] == 3, "计数停在预算内"
    assert result["folders"] == 1
    assert result["bytes"] == 30, "只累计已统计的 3 个文件（每个 10 字节）"
    assert "只统计了前 3 项" in pet.bubbles[0][0], "气泡如实提示截断"
    stats = json.loads((tmp_path / "file_eaten_stats.json").read_text(encoding="utf-8"))
    assert stats["total_bytes"] == 30


def test_eat_paths_checks_clock_for_every_item(tmp_path, monkeypatch):
    """astra F2：查钟粒度 = **逐项**（不再是「每 256 项查一次」）。

    单层目录只进一次目录，若查钟还带"每 N 项"的粒度，单层少量慢文件就整段不受控；
    这里用假钟记调用次数：30 个文件必须查到 ≥ 32 次（建预算 1 + 进目录 1 + 每文件 1）。
    """
    import pet.file_eater as file_eater

    folder = _big_dir(tmp_path, "item-clock-dir", 30)
    calls = {"n": 0}

    def counting_clock():
        calls["n"] += 1
        return 0.0  # 时间永远不动：只数查了几次，不触发截断

    monkeypatch.setattr(file_eater, "_SCAN_CLOCK", counting_clock)
    pet = _make_pet(tmp_path)

    result = FileEaterDropHandler(pet).eat_paths([str(folder)])

    assert result["truncated"] is False
    assert result["scanned"] == 30
    assert calls["n"] >= 32, f"每记一项都要查钟，实际只查了 {calls['n']} 次"


def test_eat_paths_stops_at_time_budget_in_one_slow_directory(tmp_path, monkeypatch):
    """astra F2：单层**少量**慢文件也必须封顶（逐项查钟的反例场景）。

    旧实现每 256 项才查一次钟：一个目录 30 个文件、每个 ``stat()`` 0.3s（合计 9s）
    既不到 256 项、也不会再进新目录 → 全程一次钟都不查 → 9 秒不截断，GUI 线程就
    这么冻着。逐项查钟之后，第 7 次 stat 之后（2.1s）进第 8 个文件即越 2s 预算。
    """
    import pet.file_eater as file_eater

    folder = _big_dir(tmp_path, "slow-single-layer", 30)
    ticks = {"t": 0.0}
    monkeypatch.setattr(file_eater, "_SCAN_CLOCK", lambda: ticks["t"])

    real_stat = Path.stat

    def slow_stat(self, *args, **kwargs):
        # 只让**被统计的文件**慢（``is_file``/``is_dir`` 内部同样走 ``Path.stat``，
        # 一并计耗会把"还没开始统计就超预算"变成被测行为之外的事）。
        if self.name.endswith(".bin"):
            ticks["t"] += 0.3  # 每个文件 stat 花 0.3 秒（预算 2 秒）
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", slow_stat)
    pet = _make_pet(tmp_path)

    result = FileEaterDropHandler(pet).eat_paths([str(folder)])

    assert result["truncated"] is True, "单层 30 个慢文件不到任何'每 N 项'阈值也必须封顶"
    assert result["scanned"] == 7, "7 次 stat 累计 2.1s，第 8 个文件记账前即越预算"
    assert result["bytes"] == 7 * 10
    assert "只统计了前 7 项" in pet.bubbles[0][0]


def test_eat_paths_stops_at_time_budget_for_slow_loose_files(tmp_path, monkeypatch):
    """astra F2：批量散文件同缺口——没有目录层、每项都慢的批同样按墙钟截断。"""
    import pet.file_eater as file_eater

    pet = _make_pet(tmp_path)
    paths = []
    for i in range(30):
        path = tmp_path / f"loose{i:02d}.bin"
        path.write_text("x" * 10, encoding="utf-8")
        paths.append(str(path))

    ticks = {"t": 0.0}

    def slow_clock():
        ticks["t"] += 0.3  # 每次查钟推进 0.3 秒（预算 2 秒）
        return ticks["t"]

    monkeypatch.setattr(file_eater, "_SCAN_CLOCK", slow_clock)

    result = FileEaterDropHandler(pet).eat_paths(paths)

    assert result["truncated"] is True, "散文件批也必须有墙钟封顶"
    assert (result["files"], result["scanned"]) == (6, 6), "第 7 个文件记账时已越预算"
    assert result["bytes"] == 60
    assert "只统计了前 6 项" in pet.bubbles[0][0]


def test_eat_paths_stops_in_empty_directory_tree(tmp_path, monkeypatch):
    """复审#4：纯空目录树也必须被墙钟封顶。

    旧实现只在 ``os.walk`` 的 files 循环里记账：一个文件都不统计的空目录树既不耗
    文件预算、也永远走不到耗时检查——几万层空目录照样把 GUI 线程冻住，结果里连
    "截断"都不标（用户看到"吃了空气"）。
    """
    import pet.file_eater as file_eater

    root = tmp_path / "empty-tree"
    cursor = root
    for depth in range(3):
        cursor = cursor / f"lvl{depth}"
    cursor.mkdir(parents=True)  # 三层空目录，一个文件都没有

    calls = {"n": 0}

    def slow_clock():
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else 1e6  # 建预算时正常，之后时间已越过预算

    monkeypatch.setattr(file_eater, "_SCAN_CLOCK", slow_clock)
    pet = _make_pet(tmp_path)

    result = FileEaterDropHandler(pet).eat_paths([str(root)])

    assert result["truncated"] is True, "空目录树也必须有墙钟封顶"
    assert (result["files"], result["scanned"]) == (0, 0)
    assert result["folders"] == 1
    assert "只统计了前 0 项" in pet.bubbles[0][0]


def test_eat_paths_stops_when_each_stat_is_slow(tmp_path, monkeypatch):
    """复审#4：文件少但 stat 巨慢的树同样封顶。

    旧实现的耗时检查要求已处理 ≥512 个文件：慢盘/杀软扫描下"只有几十个文件、每个
    ``stat()`` 都要几百毫秒"的目录在两次检查之间完全不受控。进目录就查一次钟以后，
    任何形态的树都有墙钟封顶。
    """
    import pet.file_eater as file_eater

    root = tmp_path / "slow-stat-tree"
    for name in ("a", "b", "c"):
        leaf = root / name
        leaf.mkdir(parents=True)
        (leaf / "f.bin").write_text("x" * 10, encoding="utf-8")

    ticks = {"t": 0.0}
    monkeypatch.setattr(file_eater, "_SCAN_CLOCK", lambda: ticks["t"])

    real_stat = Path.stat

    def slow_stat(self, *args, **kwargs):
        # 只让**被统计的文件**慢：``is_file``/``is_dir`` 内部同样走 ``Path.stat``，
        # 一并计耗会把"还没开始统计就超预算"变成被测行为之外的事。
        if self.name.endswith(".bin"):
            ticks["t"] += 1.0  # 每个文件 stat 花 1 秒（预算 2 秒）
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", slow_stat)
    pet = _make_pet(tmp_path)

    result = FileEaterDropHandler(pet).eat_paths([str(root)])

    assert result["truncated"] is True, "少于 N 个文件的慢目录也必须封顶"
    assert result["scanned"] == 2, "前两个 stat 之后进第三个目录即越预算"
    assert result["bytes"] == 20
    assert "只统计了前 2 项" in pet.bubbles[0][0]


def test_eat_paths_budget_covers_dropped_file_list(tmp_path, monkeypatch):
    """预算按整批记账：拖进来的一串散文件同样在预算内截断。"""
    import pet.file_eater as file_eater

    monkeypatch.setattr(file_eater, "SCAN_FILE_LIMIT", 2)
    pet = _make_pet(tmp_path)
    paths = []
    for i in range(4):
        p = tmp_path / f"loose{i}.bin"
        p.write_text("x" * 5, encoding="utf-8")
        paths.append(str(p))

    result = FileEaterDropHandler(pet).eat_paths(paths)

    assert (result["files"], result["bytes"]) == (2, 10)
    assert result["truncated"] is True
    assert result["scanned"] == 2
