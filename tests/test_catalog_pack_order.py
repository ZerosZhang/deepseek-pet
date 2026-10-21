# -*- coding: utf-8 -*-
"""角色包版本目录排序（`catalog._pack_version_key`）的类型安全回归。"""
from __future__ import annotations

from pathlib import Path

from pet import catalog


def test_version_key_is_type_stable_across_segments():
    """`1.0` 与 `1.0.0` 段数不同：键必须类型统一，不能把 str 与 int 拿去比较。"""
    a = catalog._pack_version_key(Path("1.0-base-640x360"))
    b = catalog._pack_version_key(Path("1.0.0-base-640x360"))
    assert isinstance(a[0], tuple) and isinstance(b[0], tuple)
    assert sorted([a, b])          # 不抛 TypeError


def test_version_key_orders_numerically():
    folders = [Path(n) for n in ("1.0.0-a-1x1", "1.10.0-a-1x1", "1.2.0-a-1x1")]
    ordered = sorted(folders, key=catalog._pack_version_key, reverse=True)
    assert [f.name for f in ordered] == ["1.10.0-a-1x1", "1.2.0-a-1x1", "1.0.0-a-1x1"]


def test_version_key_handles_garbage_prefix():
    assert catalog._pack_version_key(Path("weird-name"))




def test_body_box_scales_hd_pack_to_logical_canvas(tmp_path):
    """720p 包的 body_box（1280×720 包像素）必须换算到逻辑 640×360（720p 几何雷）。

    旧实现按 640×360 校验包像素坐标——合法高清框全被判非法 → 回退"窗口即身体"，
    碰撞/探头几何全错。现在校验按包画布做、坐标按画布比换算。
    """
    import json as _json

    from pet import catalog as _catalog

    root = tmp_path / "hd-pack"
    root.mkdir()
    (root / "character.json").write_text(_json.dumps({
        "schema": 1, "id": "shenshen", "name": "深深", "canvas": [1280, 720],
        "fps": 24.0, "pipeline": "unblend-white-v6", "format": "lossless-frame-v1",
        "parts": ["core"],
        "clips": [{"name": "待机", "category": "idle", "dir": "anim/idle/待机",
                   "frames": 1, "key_every": 12, "part": "core",
                   "content_sha": "a" * 64, "bytes": 1}]}), encoding="utf-8")
    (root / "manifest.json").write_text(_json.dumps({
        "name": "深深", "body_box": [200, 100, 1080, 700],
        "head_box": [300, 100, 980, 420]}), encoding="utf-8")

    body = _catalog.character_body_box("shenshen", root)
    assert body == (100, 50, 540, 350), f"720p 框应按 0.5 换算: {body}"
    head = _catalog.character_head_box("shenshen", root)
    assert head == (150, 50, 490, 210), f"head_box 同样换算: {head}"
    # 超包画布的框仍判非法
    (root / "manifest.json").write_text(_json.dumps({"body_box": [0, 0, 9999, 9999]}),
                                        encoding="utf-8")
    _catalog._body_box_scaled.cache_clear()
    assert _catalog.character_body_box("shenshen", root) is None


def test_geometry_is_bound_to_pack_root_not_active_pointer(tmp_path):
    """几何绑定素材根（root_str, canvas），不绑磁盘上的 active 指针。

    契约（终审 P1 后的修正）：「使用这套」只改下次启动的指针；在播库的
    素材根不变、几何也不变。根级缓存按 (root, canvas) 隔离，两个包根
    各有各的框，不需要 set_active 清任何缓存。
    """
    import json as _json

    from pet import catalog as _catalog

    _catalog.clear_geometry_caches()
    root_a = tmp_path / "pack-a"
    root_b = tmp_path / "pack-b"
    for root, box in ((root_a, [10, 10, 100, 100]), (root_b, [20, 20, 200, 200])):
        root.mkdir()
        (root / "manifest.json").write_text(_json.dumps({"body_box": box}),
                                            encoding="utf-8")
    assert _catalog.character_body_box("shenshen", root_a) == (10, 10, 100, 100)
    assert _catalog.character_body_box("shenshen", root_b) == (20, 20, 200, 200)
    # 再读一次（走缓存）：两根仍然各自正确，互不串
    assert _catalog.character_body_box("shenshen", root_a) == (10, 10, 100, 100)
