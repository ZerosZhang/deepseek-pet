# -*- coding: utf-8 -*-
"""Frameless, stackable image windows for the playful menu entry."""
from __future__ import annotations

import os
from pathlib import Path



def oijingjing_image_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "big_blue_fat_fish" / "ojingjing.jpg"


def bundled_assets_root() -> Path:
    """应用内置资产根目录（源码树或 PyInstaller _internal）。"""
    return Path(__file__).resolve().parents[1] / "assets"


def resolve_fun_asset(path: str | Path | None, fallback: Path) -> Path:
    fallback = Path(fallback).expanduser()
    if path is None or not str(path).strip():
        return fallback
    candidate = Path(str(path or "")).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.exists() else fallback
    bundled = Path(__file__).resolve().parents[1] / candidate
    return bundled if bundled.exists() else fallback


def store_fun_asset(value, default: Path | str) -> str:
    """把路径转成适合持久化的形式（保持 portable）。

    - 应用内置 assets 内的路径（含用户曾保存的绝对路径）→ 存相对值
      assets/...，目录移动/自更新后仍可解析；
    - 用户自选的外部文件 → 存绝对路径原样保留。
    """
    default = Path(default)
    candidate = str(value or "").strip()
    if not candidate:
        return str(default)
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        # Windows 上统一正斜杠，避免配置里混入反斜杠（跨平台一致）
        return candidate.replace("\\", "/") if os.name == "nt" else candidate
    try:
        rel = path.resolve().relative_to(bundled_assets_root().resolve())
        # 统一正斜杠：配置值与 legacy 迁移比较、跨平台一致
        return str(Path("assets") / rel).replace("\\", "/")
    except ValueError:
        return str(path)
