"""聊天窗口时间线：打开即落在最新一条回复，下方不留大片空白（#191）。

修复前：对话越多，最新消息下方空白越大——气泡纵向策略 Minimum 把 sizeHint（按非实际
宽度折行估出的偏高值）当成最小高度，QScrollArea 用整条时间线的最小高度撑大内容；
窗口关闭只是隐藏，重新打开停在上次位置。
"""
from __future__ import annotations

import random
import time
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

# 布局边距（message_host_layout 上下各 24~30px）+ 余量；修复前实测为数千像素
_MAX_BOTTOM_GAP = 80


def _app():
    return QApplication.instance() or QApplication([])


def _pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def _window_with_long_history(tmp_path: Path):
    from pet.chat.models import ChatMessage
    from pet.chat.session_store import SessionStore
    from pet.chat.widgets import ChatWindow
    from pet.config import Config

    cfg = Config(tmp_path)
    store = SessionStore(cfg.dir)
    session = store.create("shenshen", "openai-main", "sys")
    rng = random.Random(1)
    for i in range(20):
        session.messages.append(ChatMessage("user", f"问题 {i} " + "这是一个问题。" * rng.randint(1, 30)))
        body = ("这是一段比较长的回答内容，用来撑开气泡高度。" * rng.randint(2, 60) + "\n") * rng.randint(1, 4)
        session.messages.append(ChatMessage("assistant", f"回答 {i}\n" + body))
    store.save(session)
    if hasattr(store, "flush"):
        store.flush()
    return ChatWindow(cfg, "shenshen")


def _last_bubble_geometry(win):
    from pet.chat.widgets import MessageBubble

    viewport = win.scroll.viewport()
    last = [b for b in win.findChildren(MessageBubble) if b.isVisible()][-1]
    top = last.mapTo(viewport, QPoint(0, 0)).y()
    return top, top + last.height(), viewport.height()




