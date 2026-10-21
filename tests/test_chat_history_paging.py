# -*- coding: utf-8 -*-
"""聊天窗口历史分页 + 批量加载性能守卫测试。

背景（本机 PySide6 6.11.2 offscreen 实测）：870 条消息的会话让
``ChatWindow._load()`` 一次性建约 8700 个 QWidget（同步 ~3s + 事件排空
5-9s），``_add`` 每条都 ``_update_bubble_widths()`` 全量循环（O(n²)，76 万次
setMin/MaxWidth），且每条消息排 4 个零延时 singleShot 回调 → 打开聊天窗 /
删除会话 / 新建会话整体卡死 6-12 秒，实测一次 AppHang 被系统终止。

本文件钉住修复契约：
- 分页：首屏只渲染最新 50 条，顶部「加载更早消息」行逐页 prepend，
  全部加载后该行消失，prepend 不拽视口回底部；
- 批量守卫：``_load()`` 期间 ``_update_bubble_widths`` 只跑一次（O(1)），
  不排逐条 singleShot；
- 流式路径：``_started`` / ``_typewriter_tick`` 新消息始终追加在底部，
  不重置已加载的更早消息；
- 泄漏：``_refresh_sessions`` 旧行控件随刷新销毁，viewport 子控件不单调增长；
- 悬挂引用：``_remove_bubble`` 后 ``self._bubble`` 置 None。
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

_PAGE = 50
_TOTAL = 200


def _app():
    return QApplication.instance() or QApplication([])


def _pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def _exec_pump(app, ms: int = 150):
    """真正进事件循环的泵：本机 PySide6 6.11.2 实测 DeferredDelete（deleteLater）
    只在 exec() 循环里投递，processEvents 不投递——销毁类断言必须用它。"""
    from PySide6.QtCore import QTimer

    QTimer.singleShot(ms, app.quit)
    app.exec()


def _make_session(tmp_path: Path, count: int = _TOTAL):
    from pet.chat.models import ChatMessage
    from pet.chat.session_store import SessionStore
    from pet.config import Config

    cfg = Config(tmp_path)
    store = SessionStore(cfg.dir)
    session = store.create("shenshen", "openai-main", "sys")
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        reasoning = f"思考过程 {i}" if role == "assistant" and i % 4 == 1 else ""
        activity = [f"联网检索 {i}"] if role == "assistant" and i % 4 == 3 else []
        session.messages.append(
            ChatMessage(role, f"消息 {i:04d}", reasoning=reasoning, activity=activity)
        )
    store.save(session)
    if hasattr(store, "flush"):
        store.flush()
    return cfg, session


def _modern_window(tmp_path: Path, count: int = _TOTAL):
    from pet.chat.widgets import ChatWindow

    cfg, session = _make_session(tmp_path, count)
    return ChatWindow(cfg, "shenshen"), session


def _legacy_window(tmp_path: Path, count: int = _TOTAL):
    from pet.chat.legacy_widgets import ChatWindow

    cfg, session = _make_session(tmp_path, count)
    return ChatWindow(cfg, "shenshen"), session


# ---------- 分页（modern） ----------












# ---------- 分页（legacy 镜像） ----------




# ---------- O(n²) 守卫 ----------








# ---------- 控件泄漏 ----------








# ---------- 悬挂引用 ----------


