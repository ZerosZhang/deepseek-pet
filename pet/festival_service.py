# -*- coding: utf-8 -*-
"""节日提醒服务：调度 + 气泡落地（服务层）。

分层约定：
  - **模块顶层不 import Qt**：QTimer 在 ``__init__`` 内惰性导入，使本模块
    可被无 GUI 环境导入（也便于纯逻辑测试引用常量）。
  - 服务不继承 QObject，由 AppShell 持有引用保证生命周期。
  - 全部逻辑跑在 GUI 线程（只有一个 QTimer），无跨线程对象，也不合成音频：
    提醒只出气泡（产品已无 TTS / 音频管线）。

为什么 tick 是 30s 而不是 60s：提醒时间点是精确到分钟的，60s 间隔在边界
抖动下可能整分钟跳过；30s 保证任意分钟至少被采样两次，且开销可忽略。
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from .festival import (
    NO_FESTIVAL_TEXT,
    build_festival_text,
    normalize_festival_config,
    reminder_slot,
    startup_slot,
)
logger = logging.getLogger(__name__)


class FestivalReminderService:
    """节日提醒服务（AppShell 持有，GUI 线程）。"""

    TICK_INTERVAL_MS = 30_000
    BUBBLE_DURATION_MS = 12_000

    def __init__(self, app) -> None:
        from PySide6.QtCore import QTimer

        self._app = app
        # 契约形状由纯逻辑层定义（enabled/cn/solar_terms/west/mode/count/times/...）
        self._cfg: dict = normalize_festival_config(None)
        # 当天已触发的槽位；跨天自动清空（槽位本身含日期，这里只是防集合无界增长）
        self._slot_day: date | None = None
        self._fired: set[str] = set()
        self._timer = QTimer()
        self._timer.setInterval(self.TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        self.apply_config()
        self._catch_up()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def is_running(self) -> bool:
        """调度 tick 是否在跑（AppShell 的懒启停门控据此决定重启还是只刷配置）。"""
        return bool(self._timer.isActive())

    def apply_config(self) -> None:
        """重读配置。

        统一走纯逻辑层 normalize_festival_config：清洗/钳制只有一处实现，
        且 config.json 被手改成非法值时回落默认而不是抛异常（本方法在
        start() 路径上执行，抛异常等于功能在启动期直接失败）。
        """
        config = getattr(self._app, "config", None)
        self._cfg = normalize_festival_config(config if config is not None else {})

    # ------------------------------------------------------------ 对外入口
    def remind_now(self) -> None:
        """手动提醒「今日节日」（右键菜单入口）。

        **无视总开关**，由用户主动发起即执行；当天没有任何节日/节气时给出明确
        文案而不是静默无反应。
        """
        self.apply_config()
        now = datetime.now()
        text = build_festival_text(now.date(), self._cfg, 0) or NO_FESTIVAL_TEXT
        self._bubble(text)

    # ------------------------------------------------------------ 调度
    def _catch_up(self, now: datetime | None = None) -> None:
        """启动补提醒：当天有节日且已过首个提醒点时，立即补报一次。

        桌宠不保证常驻，用户可能中午才开机；没有这一步，当天的提醒点
        全部错过后就再也收不到，功能体感等于失效。

        ``now`` 可注入（同 ``_on_tick``）：调用方传 ``None`` 即取当前时刻，
        便于用例覆盖"恰好在提醒分钟内启动"这条只有真机重启才会踩到的路径。
        """
        now = now or datetime.now()
        slot = startup_slot(now, self._cfg)
        if not slot or slot in self._fired:
            return
        self._roll_day(now.date())
        self._fired.add(slot)
        text = build_festival_text(now.date(), self._cfg, 0)
        if text:
            self._bubble(text)
            # 启动时刻恰好落在当天的某个提醒分钟内：把本分钟的正式槽位一并
            # 盖戳。否则紧接着的 _on_tick 会命中同一分钟再弹一次气泡，与
            # reminder_slot 承诺的"同一提醒时间只播报一次"矛盾。
            # 只压这一分钟——晚些时候的提醒点仍走各自的正式槽位照常播报。
            due = reminder_slot(now, self._cfg)
            if due:
                self._fired.add(due)

    def _on_tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        if not self._cfg.get("enabled"):
            return
        self._roll_day(now.date())
        slot = reminder_slot(now, self._cfg)
        if not slot or slot in self._fired:
            return
        self._fired.add(slot)
        # 当天第几次提醒：作为文案索引，使同一天多次提醒轮到不同句子。
        index = len(self._fired) - 1
        text = build_festival_text(now.date(), self._cfg, index)
        if text:
            self._bubble(text)

    def _roll_day(self, today: date) -> None:
        if self._slot_day != today:
            self._slot_day = today
            self._fired = set()

    # ------------------------------------------------------------ 提示
    def _bubble(self, text: str) -> None:
        """桌宠气泡展示节日提醒。

        设置窗口打开等场景下 ``win.show_bubble`` 会被抑制，
        而节日提醒是用户主动关注的事件（一天只有一两次），此时退到桌宠气泡位
        直接展示，避免"弹一下就没了"；两者都不可用时再退到系统通知。

        气泡**没上屏**是另一回事：``show_bubble`` 返回 False，最常见的原因是审批/
        问题提醒正占着气泡位（普通气泡让路）。那类弹窗是用户要回答的东西，绝不
        抢占——改道系统通知并留一条 warning。旧写法只看"调用没抛异常"就 return，
        于是气泡没出、通知没发、日志也没有，这一天的节日问候整条消失。

        飞行期是唯一的例外：这是**瞬时**状态（鱼被撞飞几秒），此时连直写也
        禁掉（鱼飞行过程中不弹气泡），也不排队、不改道系统通知——一次性播报
        丢弃即可，落地后正常。判据统一走 ``window_alerts`` 的门禁助手（惰性
        import：本模块顶层不 import Qt，见文件头）。
        """
        if not text:
            return
        from . import window_alerts
        app = self._app
        win = getattr(app, "win", None)
        # 免打扰（含全屏等效）判定必须在**可见性判断之前**：宿主隐藏时（全屏避让
        # 走的正是这条）若先看 isVisible，提醒会直接落到系统通知——免打扰既压不住
        # 也不进暂存队列（实测节日通知照发、queued=0）。
        if win is not None and window_alerts.quiet_blocked(win):
            window_alerts.defer_quiet(text)
            return
        if win is not None and win.isVisible():
            if window_alerts.sprite_in_flight(win):
                return
            if window_alerts.bubble_blocked(win):
                if self._bubble_in_slot(win, text):
                    return
            else:
                try:
                    if win.show_bubble(text, duration_ms=self.BUBBLE_DURATION_MS):
                        return
                except Exception:
                    logger.exception("节日提醒气泡展示失败")
                logger.warning("节日提醒气泡未上屏（多半是提醒占着气泡位），改道桌面通知：%s", text)
        notify = getattr(app, "system_notify", None)
        if callable(notify):
            try:
                notify("节日提醒", text)
            except Exception:
                logger.exception("节日提醒桌面通知失败")

    def _bubble_in_slot(self, win, text: str) -> bool:
        """设置页抑制期直写桌宠气泡位（绕过 show_bubble 的抑制门禁）。

        抑制期是"设置页开着、普通气泡一律让路"的长时用户意图，而节日提醒是用户
        主动关注的事件，故照旧直写；写不进去返回 False，由调用方改道桌面通知。
        """
        try:
            bubble = getattr(win, "_speech_bubble", None)
            rect = win.visible_content_rect()
            scale = getattr(win, "scale", 1.0)
            if bubble is not None and rect is not None:
                bubble.show_text(
                    text,
                    rect,
                    self.BUBBLE_DURATION_MS,
                    pet_scale=scale,
                    subtitle="",
                )
                return True
        except Exception:
            logger.exception("节日提醒气泡降级展示失败")
        return False
