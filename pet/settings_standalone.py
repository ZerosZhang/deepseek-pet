# -*- coding: utf-8 -*-
"""独立设置进程（``python -m pet --settings``）的本地宿主。

设置进程刻意不导入 ``pet.app``（不载素材库/ffmpeg/托盘），因此进程内设置页
依赖的外部能力在这里用最小宿主补齐：

1. **节日试听**：复用 ``FestivalReminderService.remind_now``（文案组装与调度逻辑
   同源），文本走宿主 ``system_notify``（进程内瞬时提示）。产品不含音频管线，
   试听只出文字。

2. **避让桌宠位置**：没有 parent 窗口可读几何，改读配置目录里的 runtime 状态文件
   （桌宠启动/移动时写的 ``pet-runtime-v2-*.json`` / ``runtime-*.json``）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def show_transient_notice(text: str) -> None:
    """独立设置进程内的可见反馈：瞬时 tooltip（非模态、不阻塞、无需点确认）。

    设置进程没有桌宠气泡可挂，模态 QMessageBox 又会卡住试听期间的界面，
    tooltip 是这里最轻的"一定看得见"通道。
    """
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QToolTip

    try:
        QToolTip.showText(QCursor.pos(), str(text))
    except Exception:
        logger.debug("独立设置进程提示展示失败", exc_info=True)


class _StandaloneHost:
    """FestivalReminderService 的最小宿主。

    服务只依赖 ``config`` / ``win`` / ``system_notify`` 这组鸭子面，不需要真正的
    AppShell。
    """

    def __init__(self, config, parent=None) -> None:
        self.config = config
        # 独立进程没有桌宠窗口：win 保持 None，气泡路径自然落到 system_notify。
        self.win = None
        self._parent = parent
        self._festival = None

    def system_notify(self, title: str, message: str, **_kwargs) -> None:
        show_transient_notice(message)

    def festival_service(self):
        if self._festival is None:
            from .festival_service import FestivalReminderService

            self._festival = FestivalReminderService(self)
        return self._festival

    def shutdown(self) -> None:
        """设置窗关闭/进程退出：停掉在跑的节日服务定时器。"""
        service = self._festival
        if service is None:
            return
        try:
            service.stop()
        except Exception:
            logger.debug("独立设置进程停止服务失败", exc_info=True)


def preview_festival(dialog) -> None:
    """节日设置页「立即试听」：本地演示今日节日（纯文字）。"""
    host = getattr(dialog, "_standalone_host", None)
    if host is None:
        return
    host.festival_service().remind_now()


def standalone_pet_geometry(config):
    """读配置目录 runtime 状态文件，返回一只活桌宠窗口的几何矩形。

    设置进程没有 parent 窗口可读几何，只能取桌宠自己留下的运行时标记。
    ``slot_manager.read_live_instances`` 同时认 ``pet-runtime-v2-*.json``（多窗）
    与旧 ``runtime-*.json``，并顺手清掉死进程/损坏的标记。读不到返回 None，
    调用方保持默认位置（不许因为读文件失败而崩）。
    """
    from PySide6.QtCore import QRect

    from . import slot_manager as slot_manager_mod

    try:
        instances = slot_manager_mod.read_live_instances(config.dir)
    except Exception:
        logger.debug("读取桌宠运行时标记失败", exc_info=True)
        return None
    for _pid, x, y, w, h in instances:
        if w > 0 and h > 0:
            return QRect(int(x), int(y), int(w), int(h))
    return None


def install_standalone_hooks(dialog) -> None:
    """给独立进程的设置对话框接上本地宿主（幂等）。

    只挂独立进程需要的东西，进程内（standalone=False）实例完全不走这里。
    """
    if getattr(dialog, "_standalone_host", None) is not None:
        return
    host = _StandaloneHost(dialog.config, parent=dialog)
    dialog._standalone_host = host  # 强引用保活
    # 节日试听：FestivalSettingsPage 沿 parent 链向上找 on_festival_now（进程内由
    # PetWindow 提供）。独立进程只在对话框这一层挂同名属性；进程内实例不设该属性，
    # 因此查找仍会穿过对话框落到 PetWindow，行为逐位不变。
    dialog.on_festival_now = lambda: preview_festival(dialog)
    dialog.finished.connect(lambda _result: host.shutdown())
