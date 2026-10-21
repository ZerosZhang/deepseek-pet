# -*- coding: utf-8 -*-
"""卸载清理（--uninstall-cleanup）各步骤的可 mock 单元测试。

覆盖：
- run_uninstall_cleanup 依次执行自启删除 / Claude hooks 卸载 / DSH 桥接插件卸载；
- 其他实例仍使用 DSH 联动时桥接插件保留（skipped）；
- other_instances_use_agent 的逐类判定：本变体自己的 slot 档案不算“别的实例”，
  旧式独立实例配置 / peer 变体 / 旧共享目录照旧保护；
- __main__ 把 --uninstall-cleanup 派发给共享入口 pet.uninstall_cleanup.main。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pet.config import Config
from pet import uninstall_cleanup

ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path) -> Config:
    return Config(base=tmp_path)


def _variant_config(tmp_path, variant: str) -> Config:
    """把“当前被卸载的变体”指到合成目录。

    源码树里 ``APP_DIR_NAME`` 没有变体后缀，真机上它由打包变体决定
    （``pet.config._app_dir_name``）；这里直接指过去——判定的消费面只有
    ``config.dir`` / ``config.path`` 两个属性。
    """
    config = _config(tmp_path)
    config.dir = tmp_path / variant
    config.path = config.dir / "config.json"
    config.dir.mkdir(parents=True, exist_ok=True)
    return config


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
















# ------------------------------------- other_instances_use_agent：逐类判定

















# ------------------------------------------- __main__：--uninstall-cleanup 派发

_DISPATCH_RUNNER = r"""
import json, runpy, sys, types

sys.path.insert(0, sys.argv[1])  # 仓库根：runpy 要能 import pet（子进程 cwd 不进 sys.path）
record = {"legacy": [], "main": [], "app": []}

uninstall = types.ModuleType("pet.uninstall_cleanup")


def run_uninstall_cleanup(*args, **kwargs):
    # 旧接线：入口自己复刻的清理调用（本次要替掉的那条路）
    record["legacy"].append([list(args), kwargs])
    return {"autostart": True, "claude_hooks": True, "dsh_bridge": True}


def main(*args, **kwargs):
    record["main"].append([list(args), kwargs])
    return 7


uninstall.run_uninstall_cleanup = run_uninstall_cleanup
uninstall.main = main

app = types.ModuleType("pet.app")


def app_main(*args, **kwargs):
    record["app"].append(list(sys.argv))
    return 99


app.main = app_main

import pet
pet.uninstall_cleanup = uninstall
pet.app = app
sys.modules["pet.uninstall_cleanup"] = uninstall
sys.modules["pet.app"] = app

sys.argv = ["dsh-pet-standalone", "--uninstall-cleanup"]
exit_code = 0
try:
    runpy.run_module("pet.__main__", run_name="__main__")
except SystemExit as exc:
    exit_code = exc.code if isinstance(exc.code, int) else 1

qt_loaded = sorted(n for n in sys.modules if n == "PySide6" or n.startswith("PySide6."))
print(json.dumps({
    "exit": exit_code,
    "legacy": record["legacy"],
    "main": record["main"],
    "app": record["app"],
    "qt": qt_loaded,
}))
"""


def test_main_entry_delegates_uninstall_cleanup_without_qt_or_desktop_main(tmp_path):
    """真实入口进程里跑 `--uninstall-cleanup`：走共享 main，不建 Qt、不跑桌宠 main。

    spy 经 ``sys.modules`` 注入（清理实现与 ``pet.app``）：即使入口漏了分流也只会
    调到 spy——不卸真实自启/hooks/桥接插件、不碰真实用户配置、不启动桌宠。
    """
    runner = tmp_path / "_pet_main_runner.py"
    runner.write_text(_DISPATCH_RUNNER, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(runner), str(ROOT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert payload["main"] == [[[], {}]], "必须调用共享入口 main（无参）"
    assert payload["legacy"] == [], "入口不许自己复刻清理调用：逐步诊断/退出码只有一处实现"
    assert payload["exit"] == 7, "共享入口的退出码原样返回"
    assert payload["app"] == [], "分流后不许再跑正常桌宠 main"
    assert payload["qt"] == [], f"卸载清理路径不该加载 Qt：{payload['qt']}"


def test_main_entry_dispatches_before_importing_app():
    """静态顺序：分流必须早于 ``from .app import main``（漏了就变成普通桌宠启动）。

    锚在**真正那一行代码**上（行首缩进的 ``from .app import main as app_main``），
    不是"文件里任何地方出现过这串字"：上面几个 ``_run_*`` 的 docstring 里也会提到
    这个导入（2026-10-14 切片 5 的 ``_run_ocr_worker`` 就是这么写红的），照字符串
    取位置的话，一句注释就能让这条顺序断言失效。
    """
    source = (ROOT / "pet" / "__main__.py").read_text(encoding="utf-8")

    dispatch_at = source.index('"--uninstall-cleanup" in sys.argv')
    app_import_at = source.index("\n    from .app import main as app_main")
    assert dispatch_at < app_import_at
    assert "from .uninstall_cleanup import main as uninstall_cleanup_main" in source


def test_main_dispatches_uninstall_cleanup_to_shared_entry(monkeypatch):
    """``--uninstall-cleanup`` 派发给共享入口，并把它自己的退出码原样返回。"""
    import pet.__main__ as m

    calls = []
    legacy = []
    monkeypatch.setattr(sys, "argv", ["pet", "--uninstall-cleanup"])
    monkeypatch.setattr(uninstall_cleanup, "main", lambda *a, **k: calls.append((a, k)) or 7)
    # 旧路径换成 spy：这条用例在任何实现下都不会碰真实自启/hooks/注册表
    monkeypatch.setattr(
        uninstall_cleanup,
        "run_uninstall_cleanup",
        lambda *a, **k: legacy.append((a, k)) or {"autostart": True},
    )

    assert m._main() == 7
    assert calls == [((), {})]
    assert legacy == []


def test_main_returns_shared_entry_failure_code(monkeypatch):
    """共享入口返回非零（有步骤失败）时，入口原样透传。"""
    import pet.__main__ as m

    monkeypatch.setattr(sys, "argv", ["pet", "--uninstall-cleanup"])
    monkeypatch.setattr(uninstall_cleanup, "main", lambda *a, **k: 1)
    monkeypatch.setattr(uninstall_cleanup, "run_uninstall_cleanup", lambda *a, **k: {})

    assert m._main() != 0
