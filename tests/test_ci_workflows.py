# -*- coding: utf-8 -*-
"""CI 工作流接线（精简版）：Windows 单平台，测试 + ruff。

上游的三端矩阵、node bridge 门禁、Linux 崩溃前缀诊断随对应代码一起删除，
本文件只钉住现在真实存在的那条门：Windows runner、ruff、分片主套件、
三个隔离族步骤、失败时的面包屑回读。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PR_TEST = WORKFLOWS / "pr-test.yml"
BUILD_WINDOWS = WORKFLOWS / "build-windows.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_only_windows_workflows_remain():
    names = sorted(p.name for p in WORKFLOWS.glob("*.yml"))
    assert names == ["build-windows.yml", "pr-test.yml"], names


def test_pr_gate_triggers_on_pr_and_main_push():
    text = _text(PR_TEST)
    assert "pull_request:" in text
    assert "branches: [main]" in text
    assert "workflow_dispatch:" in text


def test_pr_gate_runs_only_on_windows():
    text = _text(PR_TEST)
    assert "runs-on: windows-latest" in text
    for gone in ("ubuntu-latest", "macos-latest", "matrix:"):
        assert gone not in text, f"精简版不再跑 {gone}"


def test_pr_gate_lints_and_shards_the_main_suite():
    text = _text(PR_TEST)
    assert "ruff check pet/ tests/" in text
    assert "python scripts/ci_shards.py" in text


def test_pr_gate_keeps_the_isolated_flaky_families():
    text = _text(PR_TEST)
    for family in (
        "tests/test_webm_reader_lifecycle.py",
        "tests/test_webm_clip_lifecycle.py",
        "tests/test_webm_first_frame_lock.py",
        "tests/test_low_priority_warm_interaction_yield.py",
        "tests/test_frameseq_prefetch_watchdog.py",
        "tests/test_frameseq_clip.py",
    ):
        assert family in text, family


def test_pr_gate_reads_crash_breadcrumbs_on_failure():
    text = _text(PR_TEST)
    assert "if: failure()" in text
    assert "pytest-breadcrumb.txt" in text


def test_pr_gate_has_no_reference_to_removed_features():
    text = _text(PR_TEST)
    for gone in ("integrations/dsh-pet-bridge", "node --test", "verify_import.mjs",
                 "capture=tee-sys", "dspet-pytest-diag-linux-prefix"):
        assert gone not in text, f"已删功能仍在工作流里：{gone}"


def test_build_workflow_calls_the_windows_build_script():
    text = _text(BUILD_WINDOWS)
    assert "scripts\\build_onedir.ps1" in text or "scripts/build_onedir.ps1" in text
