# -*- coding: utf-8 -*-
"""无源视频角色包（只有 ``character.json`` + 帧序列）的建库回归。

回归背景：``_load_all`` 扫不到 ``*.webm``/``*.gif`` 就抛 ``FileNotFoundError``，
``rescan_frameseq`` 又要求「源 webm 的 sha256」当采纳身份 —— 于是**不带源视频的
角色包根本起不来**。契约见 ``.scratch/asset-arch/RESOURCE-CONTRACT.md``。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from pet import character_pack as cp
from pet import frameseq_provision
from pet.frameseq_clip import FrameSeqClip
from pet.library import MovieLibrary

SHA = "b" * 64


def _make_frames(dir_path: Path, count: int = 4, size: tuple[int, int] = (32, 24)) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    w, h = size
    for i in range(count):
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        img.setPixel(0, 0, (0xFF << 24) | ((i * 40) << 8) | 0x33)
        assert img.save(str(dir_path / f"f_{i + 1:04d}.webp"), "webp", 100)
    from pet import pack_download as _pd
    (dir_path / "meta.json").write_text(
        json.dumps({"fps": 24.0, "frames": count,
                    "encoder": frameseq_provision.ENCODER_DESC,
                    # 采纳闸门要求内容摘要（失败关闭）；口径与安装器写进来的一致
                    "content_sha": _pd.frame_digest(dir_path)}),
        encoding="utf-8")


def _sourceless_pack(tmp_path: Path, *, frames: int = 4) -> Path:
    """``<char>/character.json`` + ``<char>/anim/idle/待机/``，**没有 videos 目录**。"""
    root = tmp_path / "chars" / "shenshen"
    clip_dir = root / "anim" / "idle" / "待机"
    _make_frames(clip_dir, count=frames)
    index = {
        "schema": 1, "id": "shenshen", "name": "深深",
        "canvas": [640, 360], "fps": 24.0,
        "pipeline": "unblend-white-v6", "format": "lossless-frame-v1",
        "parts": ["core", "extra"],
        "clips": [{
            "name": "待机", "category": "idle", "dir": "anim/idle/待机",
            "frames": frames, "key_every": 12, "part": "core",
            "content_sha": __import__("pet.pack_download", fromlist=["x"]).frame_digest(clip_dir),
            "bytes": 100,
        }],
    }
    (root / cp.INDEX_NAME).write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return root


def _close_all(lib: MovieLibrary) -> None:
    for m in lib.movies().values():
        for name in ("close", "cleanup", "stop"):
            fn = getattr(m, name, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
                break








def test_index_not_picked_up_from_shared_parent(tmp_path):
    """素材目录不叫 videos 时，不得到父目录里捡别人的索引（防串角色）。"""
    shared = tmp_path / "assets"
    shared.mkdir()
    (shared / cp.INDEX_NAME).write_text(json.dumps({
        "schema": 1, "id": "other", "name": "x", "canvas": [1, 1], "fps": 24,
        "pipeline": "p", "format": "f", "parts": ["core"],
        "clips": [{"name": "c", "category": "idle", "dir": "anim/c",
                   "frames": 1, "key_every": 12, "part": "core", "content_sha": SHA}],
    }), encoding="utf-8")
    mine = shared / "mine"
    (mine / "idle").mkdir(parents=True)
    (mine / "idle" / "x.webm").write_bytes(b"placeholder")
    lib = MovieLibrary(character_id="mine", asset_dir=mine, prewarm_enabled=False)
    try:
        assert lib._pack_index is None       # 没被别人的索引污染
    finally:
        _close_all(lib)











