# -*- coding: utf-8 -*-
"""批5.2a：单进程多窗的进程级共享子系统（全屏 watcher / 免打扰轮询）。

4.4b：多进程多宠退役层删除后本模块**常开化**（T6）——``AppShell`` 恒持有一个
共享实例，把呈现/探测事件**扇出**到全部窗，同时只运行一份监视器/探测线程
（省 (N-1) 份重复的后台轮询）。历史上由 ``experimental_single_process_spawn``
feature flag 门控（flag 关 = 每窗各自创建）；该键已随退役层删除。

设计要点（对应 BATCH5_SINGLE_PROCESS_DESIGN §4.7 / §4.8 / §8）：
- **全屏 watcher**：一份探测线程（1Hz 全屏 + 20Hz 光标轮询）→ 广播到各窗；
  ``MultiWindowProxy`` 只在「任一窗仍需要」时才继续轮询（G1 守卫保留）。
"""

from __future__ import annotations

import logging
import threading
import time
import weakref

from PySide6.QtCore import QObject, Signal

from . import platform_win
from . import quiet_mode
from . import window_alerts
from .overlay_settings_command import is_overlay_topology

log = logging.getLogger("dsh-pet-standalone")

# 存活共享子系统注册表（测试收口用）。共享子系统的 QTimer / bridge 在多窗代理
# 下 parent 为 None，其 timeout/frame 连接从 Qt C++ 侧强引用住 shell 对象图，
# Python gc 回收不掉，解释器退出 GC 才最终化 → 原生访问违规。WeakSet 只弱引用
# 子系统本身。
_LIVE_SHARED_SUBSYSTEMS: "weakref.WeakSet[SharedSubsystems]" = weakref.WeakSet()


def presentation_targets(shell) -> list:
    """共享子系统的呈现扇出目标集合（T1 的 ``instances[].win`` 位置 + D0 另一半）。

    legacy 拓扑 = 各窗 ``instances[].win``（PetWindow），逐行不变；overlay
    拓扑下 ``instances[].win`` **恒为 None**（单合成窗里没有 PetWindow），
    共享 manager 的扇出集合因此为空 = 提醒/气泡静默缺失。sprite 世界的
    等价物是 ``OverlayShell``：它提供 PetWindow 的呈现面（气泡/提醒/动作/聚合状态），
    落点就是主 sprite 的头顶气泡与行为控制器。

    ``_overlay_shell`` 在 ``AppShell.start()`` 才构造（晚于 SharedSubsystems
    的 ``__init__``），故本函数必须在每次扇出时动态读取，绝不缓存。
    兼容无该属性的替身 shell（测试 ``_ProxyShell``）。
    """
    overlay_shell = getattr(shell, "_overlay_shell", None)
    if overlay_shell is not None:
        return [overlay_shell]
    return [inst.win for inst in shell.instances if inst.win is not None]


class MultiWindowProxy:
    """单进程多窗的「窗集合替身」：把单窗接口扇出到全部窗。

    生命周期：作为进程级共享呈现面的 ``win`` 替身（提醒/气泡落点）。只读 ``shell`` 的
    呈现目标集合（``presentation_targets``：legacy = ``instances[].win``，
    overlay = sprite 世界的壳），不持有窗对象引用；任一窗退出/重建后自动忽略它（逐窗探活读取）。

    呈现类方法只扇出到**可见**窗（隐藏窗不跳舞/不弹泡，与多进程各窗独立显隐
    等价）；状态类属性做成聚合值（任一可见 / 任一生效），供 Reducer 读取。

    **状态类提醒是唯一例外**（``_STATEFUL_ALERT_TYPES``）：审批/问题这类请求的
    真值在提醒队列里，请求到达时没有可见窗也**不能当场丢掉**
    ——要交给应用级 owner（``OverlayShell`` 的提醒队列与岛反馈面能在无可见宠期间
    持有/改道它），恢复可见时按同一 alert_id 补投。
    """

    #: 不可见期间也**不能丢**的状态类提醒（阻塞型交互 + 硬失败）：这些事件的本地
    #: 真值在提醒队列里，owner 拿到后可以持有/改道，恢复可见时按同一
    #: id 补投。其余（过程汇报、模型访问、余额等瞬时提醒）保持"没有可见目标就不投"
    #: 的既有语义，避免隐藏期凭空多出正文落点。
    _STATEFUL_ALERT_TYPES = frozenset({
        "approval", "question", "interaction", "cordis", "execution/failed",
    })

    def __init__(self, shell) -> None:
        self._shell = shell
        self.cfg = shell.config

    def _windows(self) -> list:
        # overlay 拓扑 = sprite 世界的壳（presentation_targets 的注释）
        return presentation_targets(self._shell)

    def _visible_windows(self) -> list:
        return [w for w in self._windows() if getattr(w, "isVisible", lambda: True)()]

    def has_presentation_target(self) -> bool:
        """是否有可交付的呈现目标（至少一个可见窗）。

        免打扰的结束汇报据此**确认交付**：没有目标就不排空暂存、下一拍重试，
        否则（退出全屏的那一拍窗口还没回来）汇报会被静默丢掉且不可恢复。
        """
        return bool(self._visible_windows())

    # ---- 呈现扇出（只发给可见窗）----
    def show_bubble(self, text: str, duration_ms: int = 4500) -> None:
        # 气泡只发首个可见窗（与 show_alert 同策）：多窗同弹一条过程汇报
        # 既吵又重复，单窗展示即可；隐藏窗不弹的语义保持不变。
        for w in self._visible_windows():
            if hasattr(w, "show_bubble"):
                w.show_bubble(text, duration_ms=duration_ms)
                return

    # ---- 提醒扇出（交互式提醒：审批/问题/控制级 Watchdog）----
    def show_alert(self, text: str, *, subtitle: str = "", duration_ms: int = 0,
                   buttons: list | None = None, sticky: bool = True,
                   alert_id: str = "", priority: int = 3,
                   alert_type: str = "watchdog", metadata: dict | None = None) -> bool:
        """把交互式提醒入队到**首个可见窗**（多窗只弹一处，避免每只桌宠重复轰炸）。

        ``hasattr(win, "show_alert")`` 决定是否走队列提醒；本方法
        确保共享宿主是 proxy 时仍走交互式提醒（审批/控制按钮不丢失）。
        首个可见窗缺失 ``show_alert`` 时回退 ``show_bubble``（绝不因签名差异崩溃）。
        收起仍由 ``resolve_alert`` 全窗扇出兜底。

        返回是否**确实交付出去了**（至少要有一个可见窗接手）：免打扰的结束汇报
        据此确认交付，没有目标时保留暂存重试，而不是先排空再丢。

        免打扰分流放在可见性筛选**之前**：先按可见窗筛的话，隐藏宿主（全屏避让、
        手动隐藏）的普通提醒会在到达 ``window_alerts.show_alert`` 的门控之前就被
        丢掉——既不上屏也不进暂存队列。普通提醒被暂存同样算"接手"。
        """
        if window_alerts.quiet_blocked(self) and not window_alerts.alert_survives_suppression(
                alert_type, sticky=sticky, buttons=buttons, priority=priority):
            window_alerts.defer_quiet(text)
            return True
        visible = self._visible_windows()
        for w in visible:
            method = getattr(w, "show_alert", None)
            if callable(method):
                method(text, subtitle=subtitle, duration_ms=duration_ms,
                       buttons=buttons, sticky=sticky, alert_id=alert_id,
                       priority=priority, alert_type=alert_type, metadata=metadata)
                return True
        # 可见窗都不支持 show_alert：退化到首个可见窗的 show_bubble
        for w in visible:
            if hasattr(w, "show_bubble"):
                try:
                    w.show_bubble(text, sticky=sticky, buttons=buttons,
                                  duration_ms=duration_ms if not sticky else 0)
                except TypeError:
                    w.show_bubble(text, duration_ms=max(duration_ms, 4500))
                return True
        # 没有可见窗：状态类请求仍交给应用级 owner（它的提醒队列/岛反馈面能在
        # 无可见宠期间持有这条请求；恢复可见时 manager 按同一 alert_id 补投）。
        # 其余提醒保持"没有可见目标就不投"（多窗只弹一处、隐藏不冒泡的既有语义）。
        if str(alert_type or "").strip().lower() in self._STATEFUL_ALERT_TYPES:
            for w in self._windows():
                method = getattr(w, "show_alert", None)
                if callable(method):
                    method(text, subtitle=subtitle, duration_ms=duration_ms,
                           buttons=buttons, sticky=sticky, alert_id=alert_id,
                           priority=priority, alert_type=alert_type, metadata=metadata)
                    return True
        return False

    def resolve_alert(self, alert_id: str) -> None:
        """按 alert_id 在所有窗收起该提醒（含隐藏窗）：任意窗点按钮即全局收起。

        ``window_alerts`` 的按钮回调/审批回写都经 ``self.win.resolve_alert`` 关闭气泡；
        扇出到全部窗，保证一个窗上点按钮/忽略后，其它窗上的同款气泡一并收起。
        """
        if not alert_id:
            return
        for w in self._windows():
            method = getattr(w, "resolve_alert", None)
            if callable(method):
                method(alert_id)
            elif hasattr(w, "hide_bubble"):
                w.hide_bubble()

    def clear_alerts(self) -> None:
        """清空所有窗的提醒队列并关闭当前提醒（离线/重启收口）。"""
        for w in self._windows():
            method = getattr(w, "clear_alerts", None)
            if callable(method):
                method()

    def hide_bubble(self) -> None:
        """主动收起所有窗当前气泡（审批结束/离线兜底）。"""
        for w in self._windows():
            method = getattr(w, "hide_bubble", None)
            if callable(method):
                method()

    @property
    def _bubble_suppressed(self) -> bool:
        # 设置窗抑制的聚合视图：任一窗打开设置窗即视为全局抑制。提醒节流门禁
        # ``getattr(self.win, "_bubble_suppressed", False)`` 据此读到
        # True，避免单窗设置期间共享宿主继续弹提醒/白占节流槽。
        return any(getattr(w, "_bubble_suppressed", False) for w in self._windows())

    @property
    def _sticky_bubble_active(self) -> bool:
        # 任一窗仍有常驻粘滞气泡（审批/控制提醒）时记为 True，供
        # ``dismiss_all_interactions`` 的提前返回判定使用（避免漏清理）。
        return any(getattr(w, "_sticky_bubble_active", False) for w in self._windows())

    @property
    def _alert_current(self):
        # 任一见窗当前正在展示提醒时返回该提醒，否则 None（普通气泡据此让路，
        # 避免在提醒/审批展示期间被覆盖）。
        for w in self._windows():
            cur = getattr(w, "_alert_current", None)
            if cur is not None:
                return cur
        return None

    @property
    def _alert_queue(self) -> bool:
        # 聚合视图：任一窗提醒队列非空即视为激活（普通气泡据此让路）。
        return any(getattr(w, "_alert_queue", None) for w in self._windows())

    def request_link_anim(self, name: str) -> None:
        for w in self._visible_windows():
            if hasattr(w, "request_link_anim"):
                w.request_link_anim(name)

    def request_link_idle(self) -> None:
        for w in self._visible_windows():
            if hasattr(w, "request_link_idle"):
                w.request_link_idle()

    def mark_activity(self) -> None:
        for w in self._windows():
            if hasattr(w, "mark_activity"):
                w.mark_activity()

    def clear_pending_link_anim(self) -> None:
        for w in self._windows():
            if hasattr(w, "clear_pending_link_anim"):
                w.clear_pending_link_anim()

    def hold_bubble(self, seconds: float) -> None:
        for w in self._windows():
            if hasattr(w, "hold_bubble"):
                w.hold_bubble(seconds)

    def on_look_synced(self, user_text: str, reply: str) -> None:
        # 主动识屏答复同步进**各窗**的 AI 会话（各窗独立会话目录）
        for w in self._windows():
            cb = getattr(w, "on_look_synced", None)
            if callable(cb):
                try:
                    cb(user_text, reply)
                except Exception:
                    log.exception("主动识屏回复同步进会话失败")

    @property
    def cats(self) -> dict:
        # 动作池按「首个含动作包的窗」归类（角色不同动作名不同，缺失名 no-op）
        for w in self._windows():
            c = getattr(w, "cats", None)
            if c:
                return c
        return {}

    # ---- 聚合状态（Reducer）----
    def isVisible(self) -> bool:
        return any(getattr(w, "isVisible", lambda: True)() for w in self._windows())

    @property
    def _bubble_busy_until(self) -> float:
        vals = [getattr(w, "_bubble_busy_until", 0.0) for w in self._windows()]
        return max(vals) if vals else 0.0

    @property
    def _dragging(self) -> bool:
        return any(getattr(w, "_dragging", False) for w in self._windows())

    @property
    def _physics_mode(self):
        # 聚合视图：任一窗处于物理模式（'drag'/'throw'）即返回该模式，否则 None。
        #
        # 这里必须保持单窗 PetWindow._physics_mode 的**哨兵语义**（None 表示
        # 「不在物理模式」），不能返回 ``any(...)`` 的 bool：消费方按
        # `getattr(win, "_physics_mode", None) is not None` 判定，而
        # ``False is not None`` 恒为 True，共享模式下 interacting 会恒真。
        for w in self._windows():
            mode = getattr(w, "_physics_mode", None)
            if mode is not None:
                return mode
        return None

    @property
    def _click_effect_phase(self) -> int:
        vals = [getattr(w, "_click_effect_phase", 0) or 0 for w in self._windows()]
        return max(vals) if vals else 0

    @property
    def mouse_through(self) -> bool:
        return any(getattr(w, "mouse_through", False) for w in self._windows())


class SharedFullscreenWatcher(QObject):
    """进程级共享的全屏/光标 watcher：一份探测线程 → 广播到各窗。

    Windows 下启动单个后台线程，以 1Hz 探测前台窗口全屏、20Hz 轮询系统光标
    可见性；通过 Qt 信号（queued→GUI 线程）扇出到全部注册窗。任一窗的
    ``_on_fullscreen_changed`` / ``_on_cursor_visibility_changed`` 照常处理。
    仅当「任一窗需要」时才真正探测（``_any_wants`` 自省），否则线程空转。

    线程由 ``SharedSubsystems.start()`` 起，**overlay 拓扑不起**（sprite 世界的
    壳自持 ``FullscreenCursorWatcher``，且不暴露本类自省所需的面 → 本线程只会
    空转）；legacy 拓扑下各窗 ``_watch_required`` 自省决定是否真探测。
    """

    fullscreen_changed = Signal(bool)
    cursor_visibility_changed = Signal(str)

    def __init__(self, shell) -> None:
        super().__init__()
        self._shell = shell
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fs_last = False
        self._fs_polls = 0
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="pet-shared-fs-watch")
        self._thread.start()
        log.info("共享全屏监视线程已启动")

    def stop(self) -> None:
        self._stop.set()

    def _windows(self) -> list:
        # overlay 拓扑下返回 sprite 世界的壳（presentation_targets 的注释）；
        # 该壳**刻意不暴露** ``auto_hide_fullscreen`` / ``_watch_required`` /
        # ``_cursor_hidden_passthrough_enabled``——overlay 壳自持一个
        # ``FullscreenCursorWatcher``（4.1b），共享 watcher 若同时探测就是
        # 双倍轮询（硬指标③回退）。三个 getattr 缺省为假 → ``_any_wants()``
        # 恒 False → 探测线程保持 1s 空转，与 overlay 壳构造前（instances
        # 为空）逐位等价。
        return presentation_targets(self._shell)

    def _any_wants(self) -> bool:
        # 任一窗需要全屏自动隐藏或光标穿透（_watch_required 已含 Windows 平台判定）
        return any(
            getattr(w, "_watch_required", lambda: False)()
            for w in self._windows())

    def _any_fullscreen_wants(self) -> bool:
        return any(
            getattr(w, "auto_hide_fullscreen", False) for w in self._windows())

    def _any_cursor_wants(self) -> bool:
        return any(
            getattr(w, "_cursor_hidden_passthrough_enabled", lambda: False)()
            for w in self._windows())

    def _probe_fullscreen(self) -> bool:
        try:
            hit, detail = platform_win._fg_fullscreen_probe()
            if hit != self._fs_last:
                self._fs_last = hit
                log.info("共享全屏检测变化 hit=%s (%s)", hit, detail)
                self.fullscreen_changed.emit(hit)
            elif self._fs_polls % 15 == 0:
                log.info("共享全屏检测心跳 hit=%s %s", hit, detail)
            self._fs_polls += 1
            return hit
        except Exception:
            log.exception("共享全屏检测异常")
            return False

    def _poll_cursor(self) -> None:
        try:
            visibility = platform_win.get_cursor_visibility()
            self.cursor_visibility_changed.emit(visibility)
        except (RuntimeError, AttributeError) as exc:
            log.debug("共享光标状态检测瞬时异常 (%s)", exc)
        except Exception:
            try:
                self.cursor_visibility_changed.emit('UNKNOWN')
            except (RuntimeError, AttributeError) as exc:
                log.debug("共享光标状态降级发射瞬时异常 (%s)", exc)

    def _loop(self) -> None:
        next_fullscreen = time.monotonic() + 1.0
        while not self._stop.wait(0.05):
            if not self._any_wants():
                # 无人需要则低频空转（1s 一醒），避免 20Hz 空转
                self._stop.wait(1.0)
                continue
            # 光标可见性：20Hz（每循环一次）
            if self._any_cursor_wants():
                self._poll_cursor()
            # 全屏探测：1Hz 节拍
            now = time.monotonic()
            if now < next_fullscreen:
                continue
            next_fullscreen = now + 1.0
            if self._any_fullscreen_wants():
                self._probe_fullscreen()


class SharedSubsystems:
    """批5.2a：单个进程的一整套共享子系统（全屏 watcher / 免打扰轮询）。

    ``AppShell`` 恒实例化它一次；各窗订阅 ``fs`` 的广播信号，
    呈现扇出经 ``proxy`` 落到首个可见窗。
    """

    def __init__(self, shell) -> None:
        self.proxy = MultiWindowProxy(shell)
        self.fs = SharedFullscreenWatcher(shell)
        self.fs.fullscreen_changed.connect(shell._on_shared_fullscreen)
        self.fs.cursor_visibility_changed.connect(shell._on_shared_cursor)
        # 免打扰（issue #208）：进程级一份轮询表，只在免打扰生效期间跑；结束时
        # 经共享 proxy 把"攒了几条提醒"汇报到首个可见窗（多窗只报一处）。
        self.quiet = quiet_mode.QuietTicker(
            also_on_fullscreen=lambda: bool(
                shell.config.get("quiet_also_on_fullscreen", True)
            )
        )
        self.quiet.ended.connect(self._on_quiet_ended)
        _LIVE_SHARED_SUBSYSTEMS.add(self)

    def _on_quiet_ended(self, items) -> None:
        """免打扰结束（到点 / 退出全屏）：一条气泡汇报暂存提醒。

        ``MultiWindowProxy`` 直接当呈现宿主：它的 ``show_alert`` 会落到首个可见
        窗（与其它提醒同策），多宠不会重复播报。

        **交付确认制**：只有确有交付目标时才 ``ack_report``（排空暂存）。没有目标
        （退出全屏的同一拍里窗口还没恢复显示）就原样返回——轮询表会保持重试，
        提示只会晚一点到，不会消失。
        """
        state = quiet_mode.shared_quiet_state()
        if not items:
            state.ack_report()   # 一轮下来无事可报：结算掉，别让轮询表空转
            return
        if not self.proxy.has_presentation_target():
            return
        try:
            delivered = window_alerts.report_quiet_summary(self.proxy, items)
        except Exception:
            log.exception("免打扰结束汇报失败")
            return
        if delivered:
            state.ack_report()

    def start(self) -> None:
        # overlay 拓扑不启共享全屏 watcher：sprite 世界的壳自持
        # ``FullscreenCursorWatcher``（4.1b），且刻意不暴露 ``_watch_required``
        # / ``_cursor_hidden_passthrough_enabled`` / ``auto_hide_fullscreen``
        # → 本线程的 ``_any_wants()`` 恒 False，只会 1s 一醒地空转到进程退出；
        # 广播目标 ``instances[].win`` 在 overlay 下也恒为 None（扇出无接收方）。
        # legacy 拓扑逐位不变（各窗 ``_watch_required`` 自省决定是否真探测）。
        if not is_overlay_topology():
            self.fs.start()

    def stop_all(self) -> None:
        """进程级收口：停共享定时器/探测线程 + 释放 Qt 生命周期引用。

        生产路径由 ``AppShell._on_about_to_quit`` 在「全部退出」时调用；测试
        （conftest ``_close_qt_top_level_widgets`` → ``_shutdown_live_for_tests``）
        亦经本方法收口。除停表外还必须把 parent 为 None 的 Qt 对象过继给
        QApplication：否则 Qt C++ 侧连接强引用住整个对象图，Python gc 回收
        不掉，解释器退出 GC 才最终化 → 原生访问违规（见 _LIVE_SHARED_SUBSYSTEMS
        注释）。
        """
        self.fs.stop()
        self.quiet.stop()
        _release_qt_lifetimes(self)

    @classmethod
    def _shutdown_live_for_tests(cls) -> None:
        """收口未由测试显式 stop 的共享子系统。"""
        for subs in tuple(_LIVE_SHARED_SUBSYSTEMS):
            try:
                subs.stop_all()
            except Exception:
                log.debug("测试收口共享子系统失败", exc_info=True)


def _release_qt_lifetimes(subs: "SharedSubsystems") -> None:
    """把共享子系统里 parent 为 None 的 Qt 对象过继给 QApplication。

    仅接管 Python/C++ 生命周期，不改变业务状态。多窗代理下这些对象的
    parent 是伪装成窗口的 ``MultiWindowProxy``（无 ``winId``），构造时退化为
    None；其 ``timeout`` / ``frame_ready`` 连接从 Qt C++ 侧强引用住 shell
    对象图，Python gc 回收不掉。过继给与进程同寿的 QApplication 后，wrapper
    在任何线程被回收都只是空壳析构，不会跨线程删除带 QTimer/信号连接的
    QObject（interpreter 退出 access violation 根因）。
    """
    try:
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance()
        if app is None:
            return
        for obj in (subs.fs, subs.quiet):
            try:
                if obj.parent() is None and obj.thread() is app.thread():
                    obj.setParent(app)
            except RuntimeError:
                pass
    except Exception:
        log.debug("共享子系统 Qt 生命周期过继失败", exc_info=True)
