# -*- coding: utf-8 -*-
"""
应用入口 —— QApplication + 桌宠窗口 + 系统托盘。

支持运行时切换角色：
- 右键桌宠 →「切换角色」
- 托盘菜单 →「切换角色」
切换后会热加载对应形象的 webm，并保留位置/朝向等配置。

批5.1（纯重构）把原 PetApp 按「进程级 / 每窗」拆成两块，行为逐位不变；
批5.2 spike 扩成多窗集合（AppShell 持有 ``_instances`` 列表，``self.instance``
指主窗 = 列表头，兼容既有调用面）：
- ``AppShell``：进程级服务（托盘、dock 菜单、更新、余额、系统通知、
  broker、aboutToQuit 收口），持有 ``PetInstance`` 集合。
- ``PetInstance``：每窗容器（config/lib/win/聊天窗/设置窗/气泡），持 backref
  到 ``AppShell``，窗口级操作都从这里路由，``self.win`` 主窗单窗假设据此收敛。
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
import weakref
from logging.handlers import RotatingFileHandler
from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from . import autostart as autostart_mod
from . import catalog
from . import click_sound
from . import overlay_instance_gate as overlay_gate_mod
from . import slot_manager as slot_manager_mod
from . import webm_clip as webm_clip_mod
from .config import APP_DIR_NAME, Config, _default_base
from .context_menus.icons import vector_menu_icon
from .context_menus.shared import add_tray_action
from .desktop_notify import DesktopNotification, position_stack
from .library import MovieLibrary
from .window import PetWindow
from .runtime_cleanup import cleanup_stale_runtime_dirs
from .session_watcher import install_session_watcher
from .decode_fanout import DecodeFanoutHub
from .persona_phrases import PhrasePicker


_persona_pickers = weakref.WeakKeyDictionary()

# 存活 AppShell 注册表（测试收口用）。多窗共享子系统与待办服务
# 持有无主 QTimer（`QTimer()` + timeout.connect），其连接从 Qt C++ 侧强引用
# 住整个 shell 对象图，Python 的 gc.collect() 回收不掉；解释器退出时的 GC
# 才最终化这些 Qt 对象 → 原生访问违规（Windows 0xC0000005，崩溃点落在
# "Garbage-collecting / <no Python frame>"）。WeakSet 只弱引用 shell 本身，
# 测试收口时逐对象停表并释放反向引用。
_LIVE_SHELLS: "weakref.WeakSet" = weakref.WeakSet()


class _BackgroundResult(QObject):
    done = Signal(bool, object)


def _presentation_available(host) -> bool:
    """这个宿主现在还能不能承载一次**呈现**（迟到的服务结果用）。

    ``_SpriteServicePresenter``（overlay 菜单的手动余额/天气落点）自带"发起的那一只
    还在吗"的判据；普通宿主（PetWindow / 壳 / 测试替身）没有这一面，一律按可用——
    它们本来就是"这一份就是唯一落点"的形态。判据是对象身份（同一槽重建出来的是另一只
    宠），比槽号 + 代次更强：旧结果绝不投给新住客（规范 §一「关闭后的迟到结果」）。
    """
    check = getattr(host, "presentation_available", None)
    if not callable(check):
        return True
    try:
        return bool(check())
    except RuntimeError:
        # 已销毁的原生窗口/壳：按不可用处理（不冒险触碰）
        return False


class _BalanceBridge(_BackgroundResult):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.done.connect(self._show)

    def _show(self, ok: bool, payload) -> None:
        # 异步回调可能晚于窗口销毁（切角色/退出），先探活再触碰 Qt 对象
        if self.win is None or not shiboken6.isValid(self.win):
            return
        if not _presentation_available(self.win):
            # 发起的那一只已经不在了（或换成了另一只）：**只取消这次呈现**。
            # 数据侧不受影响——内存/文件缓存由 worker 落好，用户问的余额信息
            # 下次查询仍会命中缓存（规范 §一「只取消宠物呈现」）。
            logging.info("余额结果到达时发起桌宠已不在，取消本次呈现（缓存仍更新）")
            return
        if not ok:
            self.win.show_bubble(str(payload), duration_ms=6000)
            return
        _show_balance_payload(self.win, payload)


def _persona_picker(win):
    """Return an application-owned picker without extending PetWindow state."""
    try:
        picker = _persona_pickers.get(win)
    except (TypeError, RuntimeError):
        picker = None
    if picker is None:
        picker = PhrasePicker()
        try:
            _persona_pickers[win] = picker
        except (TypeError, RuntimeError):
            pass
    return picker


def _persona_text(win, key: str, fallback: str, **values) -> str:
    """Render a configured persona phrase for application-level messages."""
    cfg = getattr(win, "cfg", None)
    if cfg is None:
        return fallback.format(**values)
    mode = str(cfg.get("dialogue_mode", "legacy") or "legacy")
    picker = _persona_picker(win)
    if mode == "custom":
        text = picker.custom(cfg.get("dialogue_phrases", {}), key, fallback, **values)
        # 与内置模式同语义：未命中自定义文案时回退并填充占位符（含 {text} 等）。
        # 此前直接 return 会把未格式化的 fallback 露出字面量 {…}。
        return fallback.format(**values) if text is fallback else text
    # legacy / whale_maid：命中内置 JSON 预设即渲染，未命中回退调用方原文案
    text = picker.get(mode, key, fallback, **values)
    return fallback.format(**values) if text is fallback else text


def _show_balance_payload(win, payload) -> None:
    """展示余额气泡（含峰谷副标题）并按余额档位触发余额动画。

    网络查询、内存缓存、文件缓存三条路径统一走这里，避免缓存命中时
    没有副标题/不播动画导致的行为不一致。

    pet.balance 按需导入（内存瘦身第二刀）：该模块自带整套档位文案/价格提示
    表，实测独占 4.75MB Python 堆（tools/import_cost.py），而余额查询在
    默认配置下从不发生（balance_refresh_minutes=0 且用户没点"看余额"）——
    启动就不该为它付这份常驻。函数内 import 只在真正要显示余额时才付。
    """
    from . import balance as balance_mod

    if win is None or not shiboken6.isValid(win):
        return
    if isinstance(payload, dict):
        text = str(payload.get("text") or "余额信息为空")
        info = payload.get("info") or {}
    else:
        text = str(payload)
        info = {}
    cfg = getattr(win, "cfg", None)
    if cfg is not None:
        text = _persona_text(win, "balance.result", "余额情况：{text}", text=text)
    cfg = getattr(win, "cfg", None)
    mode = str(cfg.get("balance_tier_labels_mode", "default") or "default") if cfg is not None else "default"
    custom_peak = str(cfg.get("balance_tier_label_peak", "") or "") if cfg is not None else ""
    custom_idle = str(cfg.get("balance_tier_label_idle", "") or "") if cfg is not None else ""
    peak_label, idle_label = balance_mod.resolve_tier_labels(mode, custom_peak, custom_idle)
    color_enabled = bool(cfg.get("balance_tier_color_enabled", True)) if cfg is not None else True
    if color_enabled:
        subtitle = balance_mod.deepseek_pricing_hint_html(
            peak_label=peak_label, idle_label=idle_label,
        )
    else:
        subtitle = balance_mod.deepseek_pricing_hint(
            peak_label=peak_label, idle_label=idle_label,
        )
    win.show_bubble(
        text, duration_ms=6000,
        subtitle=subtitle,
    )
    # 按余额档位播放上游余额动画（仅当素材存在时静默跳过）
    p = balance_mod.balance_percent(info.get("total"))
    if p is not None:
        idx = balance_mod.balance_event_index(p)
        name = balance_mod.BALANCE_EVENT_NAMES[idx]
        if name and hasattr(win, "request_link_anim"):
            win.request_link_anim(name)


def _instance_config_identity(instance) -> str:
    """实例的配置身份（"" = 主身份，``slot-N`` = 子宠；slot_manager 同口径）。

    独立设置进程按这个身份选 ``config.json`` / ``config-slot-N.json``，进程内多窗
    下也是"这个设置页属于哪只宠"的判据（``_launch_settings_process`` 与设置页占用
    提示共用一处实现）。
    """
    return str(getattr(getattr(instance, "config", None), "instance_id", "") or "")


class _EmptyPetHost:
    def __init__(self, shell):
        self.cfg = shell.config
        self.scale = 1.0
        self._speech_bubble = None
        self._bubble_suppressed = False
        self._alert_current = None
        self._sticky_bubble_active = False
        self._physics_mode = None
        self._dragging = False

    def isVisible(self):  # noqa: N802
        return False

    def visible_content_rect(self):
        return QRect()

    def show_bubble(self, *args, **kwargs):
        return False

    def show_alert(self, *args, **kwargs):
        return False

    def resolve_alert(self, *args, **kwargs):
        return None

    def hold_bubble(self, *args):
        return None

    def set_bubble_suppressed(self, suppressed):
        self._bubble_suppressed = bool(suppressed)


# 批5.2 §③.7：多窗日志用 [slot-N] 前缀区分。单进程多窗共享一份日志文件，
# 故用线程本地记录「当前执行的窗」由日志 Filter 加前缀；flag 关（单进程单窗）
# 时前缀为 None，日志格式与现状逐位一致。
_pet_log_slot = threading.local()


class _SlotLogFilter(logging.Filter):
    """按线程本地槽位给日志记录加 [slot-N] 前缀（flag 开/多窗时）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        slot = getattr(_pet_log_slot, "slot", None)
        if slot:
            record.msg = f"[{slot}] {record.msg}"
        return True


def _setup_logging(config: Config) -> None:
    config.dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        str(config.dir / f'pet-{os.getpid()}.log'),  # 多开实例日志按 PID 隔离，避免互相覆盖
        maxBytes=1_000_000, backupCount=2, encoding='utf-8',
    )  # 滚动日志：1MB×2，不再无限增长
    handler.addFilter(_SlotLogFilter())
    logging.basicConfig(
        handlers=[handler],
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        encoding='utf-8',
    )
    _cleanup_old_pet_logs(config.dir)


def _cleanup_old_pet_logs(log_dir, *, max_age_days: float = 7.0) -> int:
    """启动时清理过期的 pet-<pid>.log（含滚动备份 .log.1/.2）。

    每实例每次启动都产生新文件，不清理会无界累积（审查 GLM-M2）。
    只删本变体命名空间下超龄文件；失败静默（清理不影响启动）。
    """
    removed = 0
    try:
        cutoff = time.time() - max_age_days * 86400
        for path in Path(log_dir).glob('pet-*.log*'):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed


def _show_startup_error(title: str, message: str) -> None:
    QMessageBox.critical(None, title, message)


def _cleanup_stale_runtime_dirs() -> None:
    """清理 PyInstaller onefile 遗留的 ``_MEI*`` 临时目录。

    只扫描系统临时目录中超过 24 小时的目录，并始终跳过当前进程的
    ``sys._MEIPASS``。删除失败只记录日志，不接管 ACL，也不影响启动。
    """
    if not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return

    current = Path(meipass).resolve(strict=False)
    result = cleanup_stale_runtime_dirs(current_dir=current)
    for directory in result.removed:
        logging.info("已清理遗留 PyInstaller 缓存目录: %s", directory)
    for directory, error in result.failed.items():
        logging.warning("清理 PyInstaller 缓存目录失败: %s (%s)", directory, error)


def _read_spawn_offset_env() -> int:
    """P0-1：读取 spawn 子进程路径写入的 DSH_PET_SPAWN_OFFSET_INDEX，显式传给
    主窗 PetInstance.spawn_offset（进程 spawn 路径依赖它错开落位）。

    该 env 是历史多进程 spawn 的落点错峰通道，4.4b 后不再有进程 spawn，但
    **兼容解析保留**（T5）：存量快捷方式/外壳脚本仍可能带它，读到就照旧接到
    主窗的 spawn_offset 构造参数。
    """
    try:
        return max(0, int(os.environ.get('DSH_PET_SPAWN_OFFSET_INDEX', '0') or '0'))
    except (TypeError, ValueError):
        return 0


class PetInstance:
    """每窗容器 —— config/lib/win/聊天窗/设置窗/气泡与全部窗口级操作。

    批5.1（纯重构）拆自原 PetApp 的「每窗」半边，行为逐位不变，运行时仍
    一进程一窗。持 backref 到所属 ``AppShell``；窗口级逻辑集中于本类后，
    ``self.win`` 单窗假设只有一个归属点，便于批5.2 扩成多窗集合。
    """

    def __init__(self, shell: "AppShell", config: Config,
                 slot_id: int | None = None,
                 spawn_offset: int = 0) -> None:
        self.shell: AppShell = shell
        self.config = config
        self.slot_id = slot_id
        self._spawn_offset = max(0, int(spawn_offset if spawn_offset is not None else 0))
        self.win: PetWindow | None = None
        self.modern_settings_dialog = None
        self._pending_dialog_opens: set[str] = set()
        # 4.4a 停用多进程多宠退役层：本窗不再自持碰撞 IPC 会话——多宠碰撞由
        # overlay 拓扑的 SpriteCollisionWorld（进程内统一世界）承载；legacy
        # 拓扑退化为单宠/进程内多窗渲染面，不再跨进程交换冲量。
        # 批5.3：进程级共享解码 hub（AppShell 持有，各窗共用同一份）。此前
        # broker 是每窗一个 shm facade；现换成进程级 DecodeFanoutHub（fan-out
        # 与碰撞角色解耦，不骑 QLocal），窗口调用点/参数名零改。
        self.broker_facade = getattr(self.shell, '_decode_hub', None)

    # ------------------------------------------------------------ 窗口构建
    def _create_library(self, character_id: str) -> MovieLibrary:
        # 预热策略：默认 balanced（瞬时交互核 pinned 预热首帧，随机动作池
        # 按需解码）。预热开关已并入省电模式：省电开启 = 闲置降帧 + 关闭
        # 后台预热（此处经 prewarm_enabled 传入，设置保存后由
        # _sync_animation_prewarm 同步）。media_prewarm 键保留给高级用户。
        prewarm = str(self.config.get("media_prewarm", "balanced") or "balanced")
        # 首帧缓存全局预算（高级用户可在 config.json 调小，省电/低配机用）；
        # 进程级设置，幂等，切角色重复调用无害。
        webm_clip_mod.set_first_frame_budget(
            int(self.config.get("first_frame_cache_max_mb", 8)) * 1024 * 1024
        )
        lib = MovieLibrary(
            character_id=character_id,
            prewarm_policy=prewarm,
            prewarm_enabled=not bool(self.config.get("idle_low_fps_enabled", False)),
        )
        # UI 就绪后统一调度预热：高优先级立即后台跑（带 0~0.05s 错峰），
        # 随机动作池延迟 2s 补全，避免多开启动时 ffmpeg 进程洪峰。
        lib.schedule_high_priority_warm()
        lib.schedule_low_priority_warm()
        # 首跑帧序列自动供给（B 档）：延迟 5s 后台低优转热集，静默 no-op 兜底
        getattr(lib, 'maybe_provision_frameseq', lambda: None)()
        logging.info('素材加载完成：%s %d 段动画', character_id, len(lib.names()))
        return lib

    def _slot_wrap(self, fn):
        """包一层：多窗时把线程本地日志槽位设为本窗 slot（批5.2 §③.7）。

        4.4b：进程内多窗常开化后不再有 flag 快照——按**活窗数**判定：单窗
        （含 legacy 默认形态）槽位为 None，日志格式与历史逐位一致；≥2 窗时
        槽位为 'slot-N'，由 _SlotLogFilter 加 [slot-N] 前缀。
        """
        if fn is None:
            return None
        slot = f"slot-{self.slot_id}" if self.slot_id is not None else "slot-0"

        def wrapper(*args, **kwargs):
            prev = getattr(_pet_log_slot, "slot", None)
            if len(getattr(self.shell, "_instances", ())) > 1:
                _pet_log_slot.slot = slot
            else:
                _pet_log_slot.slot = None
            try:
                return fn(*args, **kwargs)
            finally:
                _pet_log_slot.slot = prev

        wrapper.__name__ = getattr(fn, "__name__", "wrapper")
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        return wrapper

    def _wire_window(self, win: PetWindow) -> None:
        """绑定新窗口的回调接线（创建与角色切换共用，两处历史逐行重复）。

        两段原始代码逐行一致（并集 = 该段本身，未发现任一方多设回调），
        后续新增回调只改这一处即可保证两个入口同步。
        进程级操作（余额/更新/生小肥鱼/系统通知）经 ``self.shell`` 路由，
        其余均为本窗操作。批5.2 用 ``_slot_wrap`` 给每窗回调加日志槽位。
        """
        win.on_show_balance = self._slot_wrap(self.shell.show_balance)
        win.on_open_modern_settings = self._slot_wrap(self.open_modern_settings)
        # 「恢复默认设置」后的重置级运行态对齐：进程内设置页直接调这里（独立设置
        # 进程没有窗可依附，走 D12 指令通道 → AppShell._consume_settings_command）。
        win.on_settings_reset = self._slot_wrap(
            lambda: self.shell.apply_settings_reset(self))
        win.on_festival_now = self._slot_wrap(self.shell.trigger_festival_now)
        win.on_toggle_festival = self._slot_wrap(self.shell.toggle_festival_reminder)
        win.on_hidden = self._slot_wrap(self._notify_pet_hidden)
        # 4.4b：窗级「退出这只」恒注入（多窗常开化；最后一窗退出即全进程退出，
        # 与旧 flag 关时的 app.quit 分支语义等价）。
        win.on_exit_window = self._slot_wrap(self._request_exit_window)

    def _build_window(self, character_id: str, lib: MovieLibrary | None = None,
                      build_tray: bool = True) -> PetWindow:
        """创建新窗口并完成接线、音效预热与旧对象延迟销毁（创建与切换共用）。

        从 _create_ui 与 switch_character 两处历史逐行重复的公共序列（约 25 行）
        抽出：步骤顺序与 deleteLater / QTimer.singleShot 时序与原实现完全一致。
        lib 可预传入（switch_character 先预创建、失败则保留当前角色），
        缺省时按 character_id 创建（_create_ui 启动路径）。
        托盘为进程级（AppShell 持有），经 ``self.shell`` 路由。
        build_tray=False 供批5.2 进程内多窗使用：非主窗不再新建/替换托盘
        （复用 `shell._refresh_tray_menu` 聚合各窗菜单）。
        """
        if lib is None:
            lib = self._create_library(character_id)
        # 4.4b：进程级共享子系统（全屏 watcher）常建；窗口全屏监视交由共享
        # watcher（本窗不再自建线程）。
        shared = getattr(self.shell, "_shared", None)
        # 批5.2a §③.5：**子窗**构造期日志加 [slot-N] 前缀（主窗 slot 0 保持
        # 历史格式不变）；运行时动画/物理等 GUI 线程日志不动 window.py。
        _prev_slot = getattr(_pet_log_slot, "slot", None)
        if self.slot_id:
            _pet_log_slot.slot = f"slot-{self.slot_id}"
        try:
            win = PetWindow(lib, self.config,
                            broker_facade=self.broker_facade)
        finally:
            _pet_log_slot.slot = _prev_slot
        token = getattr(self.config, "profile_generation", None)
        win.set_profile_identity(character_id, token() if callable(token) else None)
        win.shared_fullscreen_watcher_active = shared is not None
        self._wire_window(win)
        # 文件投喂（拖文件模拟吃掉）：PR73 引入的接线在批5.2 重构时被丢，
        # 必须随每只窗的创建（启动/切角色/多窗）挂载，缺失则拖放无效。
        win.install_file_eater()
        # 预热点击音效：首次创建 QSoundEffect/QMediaPlayer 池并等待加载完成，
        # 在显示窗口前完成，避免窗口出现后主线程被音频初始化阻塞、
        # 首次点击 Q 弹卡顿。音效关闭时不预热，避免无谓拉起 QtMultimedia 池。
        if self.config.get("click_sound_enabled", True):
            click_sound.warm_click_sound_effects(
                self.config.get("click_sound_pack"),
                data_dir=self.config.dir,
            )
        win.show()

        tray = self.shell._build_tray(win) if build_tray else None

        # 清理旧对象（热切换时使用）
        old_win = self.win
        old_tray = self.shell.tray
        self.win = win
        if build_tray:
            self.shell.tray = tray

        if old_win is not None:
            old_win.hide(notify=False)
            QTimer.singleShot(0, old_win.deleteLater)
            # 仅主窗（build_tray=True）换托盘；非主窗绝不 hide/deleteLater 共享托盘。

            if build_tray and old_tray is not None:
                old_tray.hide()
                QTimer.singleShot(0, old_tray.deleteLater)
        return win

    def _create_ui(self, character_id: str) -> None:
        self._build_window(character_id)

    def _apply_spawn_offset(self) -> None:
        """让新孵化的桌宠与母桌宠错开，避免两个窗口完全重叠。

        批5.2：偏移量改为实例属性（显式传递），不再读进程级
        DSH_PET_SPAWN_OFFSET_INDEX 环境变量——单进程多窗下环境变量是
        进程级的，无法区分各窗（§1.2）。
        """
        if self.win is None:
            return
        index = self._spawn_offset
        if index <= 0:
            return
        scr = self.win.screen_available()
        if scr is None:
            return
        available = scr.availableGeometry()
        horizontal = -1 if self.win.geometry().center().x() > available.center().x() else 1
        vertical = -1 if self.win.geometry().center().y() > available.center().y() else 1
        # 虚拟窗口坐标：贴边状态下实际窗口位置不含绘制偏移，错开要按
        # 角色自然位置算；未支持统一出口的窗口回退实际位置（= 改造前）。
        vp_fn = getattr(self.win, '_virtual_pos', None)
        base = vp_fn() if callable(vp_fn) else QPoint(self.win.x(), self.win.y())
        x = base.x() + horizontal * 48 * index
        y = base.y() + vertical * 32 * index
        mover = getattr(self.win, '_move_window_towards', None)
        if callable(mover):
            mover(x, y)  # 统一出口自带工作区钳位（含小屏兜底）
            return
        # 小屏（可用区比窗口还窄/矮）时上界 < 下界，min/max 会互相打架把
        # 窗口推出屏幕外；先判边界再钳制。
        max_x = available.right() - self.win.width() + 1
        max_y = available.bottom() - self.win.height() + 1
        x = available.left() if max_x < available.left() else min(max(x, available.left()), max_x)
        y = available.top() if max_y < available.top() else min(max(y, available.top()), max_y)
        self.win.move(x, y)

    def _defer_while_popup_active(self, key: str, callback) -> bool:
        """Avoid constructing a heavy dialog inside QMenu.exec()."""
        if QApplication.activePopupWidget() is None:
            self._pending_dialog_opens.discard(key)
            return False
        if key in self._pending_dialog_opens:
            return True
        self._pending_dialog_opens.add(key)

        def retry() -> None:
            if QApplication.activePopupWidget() is not None:
                QTimer.singleShot(50, retry)
                return
            self._pending_dialog_opens.discard(key)
            callback()

        QTimer.singleShot(50, retry)
        return True

    def _present_dialog(self, dialog, before_present=None, attempt: int = 0) -> None:
        """延迟呈现非模态窗口，直到任何弹出菜单关闭。

        macOS 的右键/托盘菜单是原生 NSMenu 跟踪会话（menu.exec 阻塞期间），
        菜单项动作触发时会话尚未结束，此时新建窗口的 show/raise/activate
        会被 AppKit 抑制——表现为首次点击「AI 设置 / 桌宠设置」无反应，
        需要再点一次（此时窗口实例已存在，直接 show 成功）。
        延迟到菜单关闭后再呈现即可稳定弹出；Qt 自绘菜单（Windows）同样
        覆盖：弹窗仍显示时重试等待。重试 60 次（约 3.6 秒）后放弃，
        防止弹窗长期不消失时无限空转。
        """
        if attempt > 60:
            return
        if QApplication.activePopupWidget() is not None:
            QTimer.singleShot(60, lambda: self._present_dialog(dialog, before_present, attempt + 1))
            return
        if before_present is not None:
            before_present()
        if dialog.isMinimized():
            dialog.showNormal()
        else:
            dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    # ------------------------------------------------------------ 设置
    def _update_bubble_suppression_for_settings(self) -> None:
        """任一设置窗口打开/独立设置进程存活时暂停桌宠气泡，避免气泡盖住设置界面。"""
        if getattr(self, "win", None) is None:
            return
        shell = getattr(self, "shell", None)
        # 独立设置进程在跑时主进程没有对话框对象，只能看 shell 上的存活标记：
        # 锁文件存在期由 AppShell 维护（watcher 立即 + 3s 轮询兜底清除）。
        external_settings = bool(getattr(shell, "_settings_child_active", False)) if shell is not None else False
        any_open = (
            getattr(self, "modern_settings_dialog", None) is not None
            or external_settings
        )
        self.win.set_bubble_suppressed(any_open)

    def open_modern_settings(self, initial_page: str | None = None) -> None:
        # 默认路径：设置页拉到独立进程（关窗即进程退出，OS 回收首开留下的
        # 字体/样式/模块高水位）。只有开关关闭或 startDetached 失败时才回退
        # 下面的进程内路径——功能绝不丢。
        if self._try_open_settings_process(initial_page):
            return
        from .modern_settings_dialog import ModernSettingsDialog
        if self.modern_settings_dialog is None:
            self._dock_icon_before_settings = bool(self.config.get("show_dock_icon", True))
            dialog = ModernSettingsDialog(
                self.config,
                self.win,
                initial_page=initial_page,
            )
            dialog.finished.connect(self._modern_settings_finished)
            self.modern_settings_dialog = dialog
        elif initial_page:
            selector = getattr(self.modern_settings_dialog, "select_page", None)
            if callable(selector):
                selector(initial_page)
        self._update_bubble_suppression_for_settings()
        # 在 show 之前定位，避免 Windows 上窗口先显示默认位置再跳走（闪现小窗）
        self._present_dialog(
            self.modern_settings_dialog,
            before_present=self.modern_settings_dialog.move_away_from_pet,
        )

    def _try_open_settings_process(self, initial_page: str | None = None) -> bool:
        """尝试走独立设置进程；True = 已交给独立进程（不要再开进程内对话框）。"""
        shell = getattr(self, "shell", None)
        opener = getattr(shell, "open_settings_process", None)
        if not callable(opener):
            return False
        try:
            try:
                return bool(opener(self, page=initial_page))
            except TypeError:
                # 兼容旧测试桩/宿主：老 opener 只接受 instance。
                return bool(opener(self))
        except Exception:
            logging.exception("独立设置进程链路异常，回退进程内设置页")
            return False

    def _modern_settings_finished(self, result: int) -> None:
        self.modern_settings_dialog = None
        self._update_bubble_suppression_for_settings()
        # 新版设置在关闭时一律落盘（closeEvent 自动保存，「保存并退出」同样走
        # _write_config），因此无论 Accepted/Rejected 都把改动应用到桌宠。
        # 此前只有 Accepted 才刷新：直接 X 关闭时保存生效但桌宠不更新。
        #
        # 表单用独立编辑视图（SlotRoutedConfig.new_form_view），但它每次**成功落盘**都会
        # 作废运行期这份视图的只读快照（SlotRoutedConfig._refresh_runtime_view），所以
        # 这里不必再补一次刷新。
        #
        # 应用链与 watcher 路径共用 AppShell._apply_external_config_change；但
        # 旧测试桩（AppShell.__new__ + 只打桩原内联 seam，没有 _instances）仍走
        # 原内联序列，保证进程内路径的既有测试/时序逐位不变。
        shell = self.shell
        apply_change = getattr(shell, "_apply_external_config_change", None)
        if callable(apply_change) and getattr(shell, "_instances", None) is not None:
            apply_change()
        else:
            if self.win is not None:
                self.win.refresh_pet_settings()
            shell._apply_balance_timer()
            # Phase 1/2：设置保存后按配置同步可选服务（festival 懒启停）与动画预热
            shell._sync_festival_service()
            self._sync_animation_prewarm()
            _mac_set_dock_icon_visible(bool(self.config.get("show_dock_icon", True)))
        if (
            getattr(self, "_dock_icon_before_settings", None) is True
            and not bool(self.config.get("show_dock_icon", True))
        ):
            self._hint_dock_hidden_recovery()


    def _dock_hidden_recovery_message(self) -> str:
        return (
            "已隐藏 Dock 图标，桌宠仍会常驻。需要恢复时：点菜单栏托盘图标 → "
            "「桌宠设置」→ 重新勾选「显示 Dock 图标」；找不到桌宠也从托盘菜单「显示 / 隐藏」恢复。"
        )

    def _hint_dock_hidden_recovery(self) -> None:
        if sys.platform != "darwin":
            return
        win = self.win
        if win is not None and callable(getattr(win, "show_bubble", None)) and win.isVisible():
            win.show_bubble(self._dock_hidden_recovery_message(), duration_ms=7000)
            return
        tray = getattr(self.shell, "tray", None)
        if tray is not None and callable(getattr(tray, "showMessage", None)):
            tray.showMessage(
                "桌宠设置",
                self._dock_hidden_recovery_message(),
                QSystemTrayIcon.MessageIcon.Information,
                7000,
            )

    def _sync_animation_prewarm(self) -> None:
        """设置保存后把预热状态同步到当前素材库（幂等）。

        预热开关已并入省电模式（省电 = 闲置降帧 + 不预热）：省电模式开启时
        关闭后台预热，关闭时恢复。上游 PR73 的独立 animation_prewarm_enabled
        键已移除（8MB 首帧预算下其省内存的价值主张不成立）。

        overlay 拓扑没有 PetWindow（``self.win`` 恒 None），素材库挂在 sprite 壳上
        ——漏掉这条回退，设置页保存省电模式后要等下次启动/切角色才生效。
        """
        win = self.win
        if win is not None:
            libs = [getattr(win, "lib", None)]
            visible = None
            is_visible = getattr(win, "isVisible", None)
            if callable(is_visible):
                visible = bool(is_visible())
        else:
            shell = getattr(self.shell, "_overlay_shell", None)
            if shell is None:
                return
            # 主宠 + 已生子宠各自的库（口径同 overlay_shell 的退出收口遍历）
            libs = [getattr(shell, "lib", None)]
            libs.extend(lib for lib in getattr(shell, "_spawned_libs", {}).values())
            visible = None
            is_visible = getattr(shell, "isVisible", None)
            if callable(is_visible):
                visible = bool(is_visible())
        enabled = not bool(self.config.get("idle_low_fps_enabled", False))
        for lib in libs:
            setter = getattr(lib, "set_prewarm_enabled", None)
            if callable(setter):
                setter(enabled, visible=visible)

    # ------------------------------------------------------------ 其它窗口级
    def _set_autostart(self, enabled: bool, win=None) -> bool:
        ok = autostart_mod.set_enabled(bool(enabled))
        self.config.set("autostart_wanted", bool(enabled))
        self.config.save()
        target = win or self.win
        if target is not None and not ok:
            target.show_bubble("开机自启写入失败，请检查系统登录项或安全软件设置。", duration_ms=6000)
        return ok

    def _check_autostart_wanted(self) -> None:
        if self.config.get("autostart_wanted", False) and not autostart_mod.is_enabled() and self.win is not None:
            self.win.show_bubble("检测到开机自启已被系统或安全软件关闭，可在设置中重新启用。", duration_ms=7000)

    def _notify_pet_hidden(self) -> None:
        """用户主动隐藏桌宠后弹托盘提示，指明恢复入口。

        非主窗（多窗）的提示文案指向托盘菜单里的「显示 / 隐藏 [slot-N]」
        （P2-5 消除误导）。
        """
        if self.shell.tray is None:
            return
        if self is not self.shell.instance:
            message = "点击托盘菜单中该窗口的「显示 / 隐藏」即可恢复。"
        else:
            if sys.platform == "darwin" and not bool(self.config.get("show_dock_icon", True)):
                message = "点击托盘菜单「显示 / 隐藏」即可恢复。"
            else:
                message = "点击托盘图标或 Dock 图标即可恢复。"
        self.shell.tray.showMessage(
            "桌宠已隐藏",
            message,
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _request_exit_window(self) -> None:
        """窗级「退出这只」：委托 AppShell 收口本窗资源（批5.2）。"""
        if self.win is None:
            return
        self.shell._on_window_exit_requested(self)


class AppShell:
    """进程级外壳 —— 托盘、dock 菜单、更新、余额、系统通知、碰撞会话、broker。

    批5.1（纯重构）拆自原 PetApp 的「进程级」半边，行为逐位不变；批5.2
    spike 扩成多窗集合（``self.instances``），``self.instance`` 仍是主窗
    （列表头）。aboutToQuit 收口在 ``_on_about_to_quit``，含窗级/进程级
    资源的分段释放（窗级字段与进程级 broker/碰撞/permanent writer 分开，
    见 §2.2-E2 / R5）。
    """

    def __init__(self, app: QApplication, config: Config,
                 slot_id: int | None = None,
                 spawn_offset: int = 0, overlay_gate=None) -> None:
        self.app = app
        self.config = config
        self._slot_id = slot_id
        # 托盘本体（属性访问器在下方：overlay 拓扑回退到壳持有的托盘）
        self._tray: QSystemTrayIcon | None = None
        # 托盘上下文菜单所有权（F5）：_build_tray 每次构建的 QMenu 必须由进程侧
        # 强引用保活——PySide6 下仅靠 tray.setContextMenu 持有 C++ 指针时，Python
        # wrapper 一旦被回收，之后的 act.menu()/contextMenu() 会命中 shiboken 缓存里
        # 已失效的 wrapper（RuntimeError: Internal C++ object already deleted）。
        # 除菜单本体外还必须保活其 QAction wrapper：子菜单的 menuAction 挂在父菜单的
        # actions 列表里，这些 QAction wrapper 被回收会让仍存活且被强引用的 QMenu
        # wrapper 连带失效（_install_tray_menu 会一并快照保活）。
        # 新菜单接管后旧菜单经 _install_tray_menu 显式 deleteLater 释放，不累积泄漏。
        self._tray_menu: QMenu | None = None
        self._tray_submenus: list[QMenu] = []
        self._tray_actions: list = []
        self.dock_menu: QMenu | None = None
        self._notification_click_callback = None
        self._toast_windows: list[DesktopNotification] = []
        self._spawned_pet_count = 0
        self._balance_busy = False
        self._balance_cache = None
        self._balance_bridge = None
        # 天气服务（「查看天气」）：懒创建，进程级单例（多窗共用一份忙门与客户端）
        self._on_about_to_quit_connected = False
        # overlay 拓扑产品壳（4.1a）：仅 overlay 拓扑构造；捕获模式与显式
        # PET_RENDER_TOPOLOGY=legacy 都走 legacy 单窗，恒为 None
        self._overlay_shell = None
        # D4：桌宠单实例进程门（由 main() 抢到后传入；两个拓扑都有，只有直接
        # 构造 AppShell 的测试路径才会拿到 None）。释放挂在会话结束路径
        # （_on_session_end）与 main() 的 finally。
        self._overlay_gate = overlay_gate
        self._balance_timer = QTimer()
        self._balance_timer.timeout.connect(self.show_balance)
        self._balance_cache_path = config.dir / 'balance_cache.json'  # 跨实例共享余额缓存（按 provider 绑定）
        # 网络信息弹窗（issue #172）：进程级单例、非模态。数据只在打开时取一次
        # （后台线程），故不需要常驻服务；窗口销毁即置空。
        # 节日提醒：进程级单例（多窗共用调度器）。**默认关闭** → 不创建服务；
        # 由用户在设置里开启后 _sync_festival_service 才创建并跑 30s tick。
        self.festival_service = None
        if self._festival_wanted():
            self._ensure_festival_service()
        # 4.4b：`experimental_single_process_spawn` 键删除——进程内多窗从
        # "实验开关"升格为**唯一**多宠形态（多进程多宠退役层已删除），
        # 原先依赖该 flag 快照的窗级逻辑（runtime 标记版本化、日志前缀、
        # 退出分派、共享子系统）一律常开/按活窗数派生。
        # D0 门控解绑（PHASE4_DESIGN T3）：overlay 拓扑下 hub 必须**常开**——
        # 多 sprite 同角色若各自建链会退化成 N 路独立 ffmpeg（硬指标③回退）。
        # 拓扑判定唯一入口收口在 overlay_shell.is_overlay_topology（T5 的 dev
        # 环境变量，不进 Config/设置页/schema）。
        # 批5.3：进程级共享解码 hub（同角色帧扇出）——使能门收敛为
        # `experimental_shared_decode` 这一个用户级总闸（flag 快照已删；
        # overlay 拓扑不再需要额外门控，legacy 多窗同样受益）。
        self._decode_hub = DecodeFanoutHub(
            enabled=bool(config.get('experimental_shared_decode', True)))
        # 4.4b（T6「multi_window_shared 不删，常开化」）：进程级共享子系统
        # （全屏 watcher / 免打扰轮询）**恒建**，崩溃/换角色不重建。sprite
        # 拓扑里共享子系统缺位即静默缺失（全屏 watcher 无人承载）。
        #（位置在 _instances 就绪之后，共享 manager 构造期即遍历窗集合）。
        self._shared = None
        # 每窗容器：批5.1 单进程单窗仅一个；批5.2 spike 扩成多窗集合
        #（self.instance 指主窗 = instances[0]，兼容既有调用面）。
        self._instances: list[PetInstance] = []
        # 批 E：清除子肥鱼链式关闭进行中标记（重复点击忽略，保持幂等）。
        self._clear_spawned_pending = False
        # 设置进程隔离：独立设置进程存活标记 + config 目录 watcher/定时器
        #（懒安装，见 _install_config_watcher）。默认关的键下完全不用它们。
        self._settings_child_active = False
        self._settings_launch_at = 0.0
        # 本进程最近一次拉起的设置页归属实例身份（"" = 主身份 / "slot-N"）：
        # 设置页已开着时据此说清"是哪只宠的设置"，None = 归属未知（外部拉起）。
        self._settings_owner_instance_id = None
        self._config_watcher = None
        self._config_reload_timer = None
        self._settings_watch_timer = None
        self._last_config_signature = None
        from . import pet_profiles
        from .settings_slot_config import SlotRoutedConfig
        from types import SimpleNamespace

        migration = pet_profiles.migrate_slot0_profile(config.dir)
        # slot0 档案不可用（``target-corrupt``）只牵连这一份档案 → **降级该槽**，
        # 不拖死整个应用；其余非 ok 状态涉及全局面/迁移基础设施，照旧硬失败并说清楚
        # （'一份坏档案'与'全局配置坏了'是两种事故，处置也不同：前者保留原文件、
        # 把槽空着等用户显式动作，后者必须停下）。2026-10-10 ops D2。
        self._slot0_profile_unusable = False
        self._slot0_profile_diagnosis = ""
        if not migration.ok:
            if not migration.slot_only_problem:
                raise RuntimeError(str(migration))
            self._mark_slot0_profile_unusable(migration)
        pet_profiles.migrate_active_set(config.dir)
        active_slots = list(pet_profiles.load_active_set(config.dir).slots)
        if self._slot0_profile_unusable:
            # 只在**内存**里摘掉 0：持久化活跃集合只由用户显式生成/关闭触发，
            # 启动期不替用户改盘（也不"自动修复"坏档案）。
            active_slots = [n for n in active_slots if n != 0]
        self._active_pet_slots = active_slots
        identity = SimpleNamespace(dir=config.dir, path=config.dir / "config-slot-0.json",
                                   instance_id="slot-0", data={})
        self.instance = PetInstance(
            self, SlotRoutedConfig(identity, config, 0), slot_id=0, spawn_offset=0,
        )
        self._instances.append(self.instance)
        from .multi_window_shared import SharedSubsystems

        self._shared = SharedSubsystems(self)  # 4.4b：常开化（T6）
        _LIVE_SHELLS.add(self)

    def _mark_slot0_profile_unusable(self, migration) -> None:
        """slot0 档案不可用（单槽损坏）：**降级该槽**，不拖死整个应用（ops D2）。

        一份 ``config-slot-0.json`` 手改坏/断电半写，此前的处置是
        ``raise RuntimeError`` → 启动失败对话框 → 全局配置、其它槽、提醒、托盘全不可用，
        而对话框里连文件路径都没有。同一类事故在活跃集合上走的是"降级为空继续跑"，
        两条真值策略不一致。

        这里的口径（与规范"不覆盖、不自动修复"并存）：

        - **原文件一个字节不动**：损坏内容可能是用户手改的一手数据，任何"自动修复"都是猜；
        - 该槽在**内存**里退出活跃集合（不落盘），恢复正常后照常复活；
        - 其余槽、全局配置、托盘/恢复入口全部照常；
        - 诊断（**含文件路径**）进日志并留给可见提示，用户不必翻日志才知道出了什么事；
        - **恢复方式按当前拓扑如实说**（见下），不许两种拓扑共用一句"重启"。
        """
        self._slot0_profile_unusable = True
        path = getattr(migration, "profile_path", None)
        # 恢复方式两个拓扑不同，不许一锅端：
        # - overlay 壳的「生成 / 恢复 slot0」会把该槽档案**重新读一遍**，修好文件后
        #   免重启即可原地恢复（实机验证：.scratch/product-close-approved-gui-
        #   20261011/REPORT.md §4.4；同链路的失败气泡早就写着"再试一次"）；
        # - legacy 单窗形态在本进程内不再重读该档案（``spawn_pet`` 被
        #   ``_slot0_profile_unusable`` 拒掉，见 ``app.spawn_pet`` 的拒写分支），
        #   所以那条路只能是重启后按修好的档案回来。
        # 旧文案两边都写"重启即可恢复"，对 overlay 用户是错的口径（实测发现）。
        from .overlay_shell import is_overlay_topology

        recovery = ("修好后点托盘 / 恢复窗的「生成 / 恢复 slot0」即可恢复（重启同样有效）。"
                    if is_overlay_topology() else
                    "修好该文件后重启即可恢复。")
        self._slot0_profile_diagnosis = (
            f"slot0 档案不可信（{migration.status}），已跳过这只桌宠；"
            f"原文件保留未改：{path}。" + recovery)
        logging.error("启动：%s（%s）", self._slot0_profile_diagnosis, migration.reason)

    def slot0_profile_diagnosis(self) -> str:
        """slot0 降级诊断（空串 = 正常）。可见恢复入口/托盘提示用。"""
        return str(getattr(self, "_slot0_profile_diagnosis", "") or "")

    def _save_active_set(self, *, action: str) -> bool:
        """把活跃集合落盘（**用户显式动作**路径：生成 / 恢复 / 关闭）。

        坏文件在这里先备份再覆盖（``on_broken="backup-overwrite"``）：文件已经不可信，
        而"用户显式关闭/生成"是规范里唯一允许改活跃集合的动作——继续 ``refuse`` 会让
        「生成了 → 重启又没了」「关掉了 → 重启还在」永远修不好，UI 里却没有任何解释
        （2026-10-10 ops D1）。失败必须**可见**：日志 + 气泡点名路径，不许继续假成功。
        """
        from . import pet_profiles

        result = pet_profiles.save_active_set(
            self.config.dir, self._active_pet_slots, on_broken="backup-overwrite")
        if result.status != "ok":
            logging.error("%s：活跃集合落盘失败（%s）：%s → %s",
                          action, result.status, result.reason, result.path)
            self._notify_active_set_write_failed(action, result)
            return False
        if result.backup_path is not None:
            logging.warning("%s：原活跃集合文件不可信，已备份到 %s 后重建",
                            action, result.backup_path)
        return True

    def _notify_active_set_write_failed(self, action: str, result) -> None:
        """活跃集合落盘失败的可见反馈（气泡；无宠可冒泡时只剩日志，如实不撒谎）。"""
        text = (f"{action}没能记住：活跃状态文件写入失败，重启后这次改动会丢失。\n"
                f"文件：{result.path}")
        for target in (getattr(self, "_overlay_shell", None),
                       getattr(getattr(self, "instance", None), "win", None)):
            shower = getattr(target, "show_bubble", None)
            if callable(shower):
                try:
                    if shower(text, 9000):
                        return
                except Exception:
                    logging.exception("提示活跃集合落盘失败时冒泡失败")

    def _notify_slot0_profile_unusable(self, action: str) -> bool:
        """slot0 档案不可用时"恢复/生成"被拒的可见反馈（含路径）。返回是否上了屏。

        通道按"谁能真上屏"降级：overlay 壳 / 本窗气泡 → 右下角自绘通知（沿用「系统通知」
        总开关，与 ``_notify_settings_process_busy`` 同口径）。全程只有日志 = 用户点了
        没反应，正是本轮要消灭的那类失败；系统通知被关掉时如实记一条 warning，不假称
        已经提示过。
        """
        text = f"{action} 失败：{self.slot0_profile_diagnosis()}"
        for target in (getattr(self, "_overlay_shell", None),
                       getattr(getattr(self, "instance", None), "win", None)):
            shower = getattr(target, "show_bubble", None)
            if callable(shower):
                try:
                    if shower(text, 9000):
                        return True
                except Exception:
                    logging.exception("提示 slot0 档案不可用时冒泡失败")
        if not bool(self.config.get("system_notifications_enabled", True)):
            logging.warning("slot0 档案不可用，且系统通知已关闭，无法可见提示：%s", text)
            return False
        notify = getattr(self, "system_notify", None)
        if callable(notify):
            try:
                notify("无法恢复桌宠", text)
                return True
            except Exception:
                logging.exception("提示 slot0 档案不可用时发通知失败")
        logging.warning("slot0 档案不可用：%s", text)
        return False

    @property
    def slot_id(self) -> int | None:
        """主窗 slot（E2：主窗实例 slot_id 为权威，本属性只读转发）。"""
        inst = getattr(self, 'instance', None)
        if inst is not None and getattr(inst, 'slot_id', None) is not None:
            return inst.slot_id
        return self._slot_id

    @property
    def instances(self) -> list[PetInstance]:
        return self._instances

    # --- 进程级功能（todo 提醒等）的鸭式访问器：转发到主窗实例 ---
    @property
    def win(self):
        """主窗窗口；overlay 拓扑下退回 sprite 壳（PetWindow 形的呈现宿主）。

        两个进程级提醒服务（TodoReminderService /
        FestivalReminderService）经 ``app.win`` 取气泡锚点，只读
        ``show_bubble`` / ``isVisible`` / ``cfg`` / ``_speech_bubble`` /
        ``visible_content_rect`` / ``scale``——OverlayShell 逐条提供同契约
        （见 overlay_shell「PetWindow 形宿主面」段），故 overlay 拓扑
        （``instance.win`` 恒 None）下退回壳；不退回则两条提醒全部落到系统通知
        （节日还不过 system_notifications_enabled 门）。

        legacy 拓扑 ``_overlay_shell`` 为 None → 恒返回 PetWindow，逐位不变。
        """
        inst = getattr(self, 'instance', None)
        win = inst.win if inst is not None else None
        if win is not None:
            return win
        overlay = getattr(self, '_overlay_shell', None)
        if overlay is not None:
            return overlay
        if not hasattr(self, '_empty_pet_host'):
            self._empty_pet_host = _EmptyPetHost(self)
        return self._empty_pet_host

    @win.setter
    def win(self, value) -> None:
        """Legacy compatibility setter routed to the primary instance."""
        inst = getattr(self, 'instance', None)
        if inst is not None:
            inst.win = value

    @property
    def tray(self):
        """托盘对象：legacy = 本进程建的 QSystemTrayIcon；overlay = 壳的托盘。

        overlay 拓扑进程级托盘由 OverlayShell 持有（``self.tray`` 恒 None），
        不看向壳则「隐藏桌宠 → 点托盘恢复」提示与 Dock 隐藏指路都读不到托盘。
        """
        tray = getattr(self, '_tray', None)
        if tray is not None:
            return tray
        return getattr(getattr(self, '_overlay_shell', None), 'tray', None)

    @tray.setter
    def tray(self, value) -> None:
        self._tray = value

    @property
    def modern_settings_dialog(self):
        """转发主窗实例的设置对话框引用（TodoReminderService 气泡抑制判定用）。"""
        inst = getattr(self, 'instance', None)
        return getattr(inst, 'modern_settings_dialog', None) if inst is not None else None

    # ------------------------------------------------------------ 功能门控（节日提醒）
    def _festival_wanted(self) -> bool:
        # 总开关默认关闭：主动打扰型功能，升级后不应突然冒出来。
        return bool(self.config.get("festival_reminder_enabled", False))

    def _ensure_festival_service(self):
        """懒创建节日提醒服务（仅在开启提醒/手动触发时创建）。

        pet.festival_service 连带 festival/festival_calendar/festival_data 与
        五份节日文案表，实测 2.95MB Python 堆（tools/import_cost.py）。总开关
        默认关闭（主动打扰型功能），关闭时整套文案表都不该常驻——import 收到
        构造点，开启/试听时按需付一次。
        """
        if getattr(self, "festival_service", None) is None:
            from .festival_service import FestivalReminderService

            self.festival_service = FestivalReminderService(self)
        return self.festival_service

    def _sync_festival_service(self) -> None:
        """按配置启停节日提醒服务；关闭时释放服务对象。"""
        if self._festival_wanted():
            service = self._ensure_festival_service()
            if service.is_running():
                # 已在运行：设置保存只刷新配置，不重置 tick。
                service.apply_config()
            else:
                service.start()
        elif getattr(self, "festival_service", None) is not None:
            try:
                self.festival_service.stop()
            except Exception:
                logging.exception("停止节日提醒服务失败")
            self.festival_service = None

    # ------------------------------------------------------------ 设置进程隔离
    def _apply_external_config_change(self) -> None:
        """把「配置已在别处落盘」同步到运行期（独立设置进程 / watcher 路径）。

        全局快捷键也在这里重注册：关掉进程隔离时设置页就在本进程里保存、**没有**
        watcher，改键要立刻生效就只能挂在这条共用入口上（watcher 路径同样走这里）。

        与进程内对话框 finished 的应用链同源（PetInstance._modern_settings_finished
        在真实壳上委托到这里）；多实例时扇出到每个 PetInstance 的窗口，而不是
        只看主窗——外部改配置的那个实例不一定是主窗。
        """
        for inst in getattr(self, "_instances", []):
            win = getattr(inst, "win", None)
            if win is not None:
                win.refresh_pet_settings()
        overlay_shell = getattr(self, "_overlay_shell", None)
        if overlay_shell is not None:
            refresh = getattr(overlay_shell, "refresh_settings", None)
            if callable(refresh):
                refresh()  # overlay 拓扑的窗口能力重应用（4.1b）
        self._apply_balance_timer()
        self._sync_festival_service()
        for inst in getattr(self, "_instances", []):
            prewarm = getattr(inst, "_sync_animation_prewarm", None)
            if callable(prewarm):
                prewarm()
        _mac_set_dock_icon_visible(bool(self.config.get("show_dock_icon", True)))

    def open_settings_process(self, instance=None, page: str | None = None) -> bool:
        """拉起独立设置进程；True = 已交给独立进程（不得再开进程内对话框）。

        False = 开关关闭或 startDetached 失败，由调用方回退进程内设置页。
        """
        if not bool(self.config.get("settings_process_isolation", True)):
            return False
        self._install_config_watcher()
        if self._settings_process_running():
            # 单实例：已有设置进程在跑（可能不是本主进程拉起的）→ 不再拉起，
            # 但仍按"设置开着"抑制气泡并盯住它的锁文件。
            logging.info("独立设置进程已在运行，不重复拉起")
            self._mark_settings_child(True)
            if not self._settings_launch_pending():
                # 拉起窗口之外 = 用户再次点了「桌宠设置」（可能是另一只宠的）：
                # 静默 return True 会让这次点击表现为"什么都没发生"。
                self._notify_settings_already_open(instance)
            return True
        if self._settings_launch_pending():
            # 刚拉起、子进程还没来得及建锁：连点场景视为已在启动，避免双开。
            self._mark_settings_child(True)
            return True
        if not self._launch_settings_process(instance, page=page):
            return False
        self._settings_launch_at = time.monotonic()
        self._settings_owner_instance_id = _instance_config_identity(instance)
        self._mark_settings_child(True)
        return True

    def _notify_settings_already_open(self, instance) -> None:
        """设置页已开着时的可见反馈（此前是静默 no-op，右击另一只宠像没反应）。

        独立设置进程是**单实例**：进程内多窗共用同一份 Config，所有宠的设置页
        走的都是那一个设置进程，无法再开第二扇窗，也无法从主进程把它前置——
        能做的只有说清现状。文案按归属分三种：同一只（"已经打开"）、另一只
        （"先关闭"）、归属未知（外部拉起的设置进程）。

        走 self-drawn 右下角通知而不是桌宠气泡：设置页开着时气泡本来就被抑制
        （_update_bubble_suppression_for_settings），冒泡必被丢弃；通知沿用
        「系统通知」总开关（与待办提醒的 notify 分支同口径）。
        """
        if not bool(self.config.get("system_notifications_enabled", True)):
            return
        owner = getattr(self, "_settings_owner_instance_id", None)
        requested = _instance_config_identity(instance)
        if owner is not None and owner == requested:
            message = "桌宠设置已经打开（独立设置窗口不会重复打开）：请切换到已打开的窗口。"
        elif owner is not None:
            message = "已有一只桌宠的设置窗口开着：请先关闭它，再打开这只的设置。"
        else:
            message = "桌宠设置已经打开：请先关闭已打开的设置窗口再试。"
        logging.info("设置页已在运行，提示用户：%s", message)
        notify = getattr(self, "system_notify", None)
        if callable(notify):
            try:
                notify("桌宠设置", message)
            except Exception:
                logging.exception("设置页占用提示失败")

    def _settings_process_running(self) -> bool:
        """settings.lock 是否被活着的设置进程持有。

        QLockFile 会把「pid 已死」的残留锁判为陈旧并接管，因此设置进程崩溃
        残留的锁文件不会永久堵住设置入口。
        """
        from PySide6.QtCore import QLockFile

        lock_path = self.config.dir / "settings.lock"
        lock = QLockFile(str(lock_path))
        lock.setStaleLockTime(30000)
        try:
            if lock.tryLock(0):
                lock.unlock()
                return False
        except Exception:
            logging.exception("探测设置进程锁失败")
            return True  # 探测异常按"已在运行"保守处理，宁可不开第二份
        if not lock_path.exists():
            # 拿不到锁但锁文件并不存在 = 目录不可写之类的环境错误，不是"已有设置
            # 进程"；否则用户会彻底打不开设置页。
            logging.warning("设置进程锁探测失败且锁文件不存在：%s", lock_path)
            return False
        return True

    def _settings_launch_pending(self) -> bool:
        """刚拉起独立设置进程的启动窗口（子进程建锁前的连点保护）。"""
        started = float(getattr(self, "_settings_launch_at", 0.0) or 0.0)
        return bool(started) and (time.monotonic() - started) <= 5.0

    @staticmethod
    def _spawn_settings_process(program, arguments, working_dir, environment) -> bool:
        """startDetached 独立设置进程，带着**只给子进程**的那份环境。

        单独一层是为了让"注入的环境到底有没有交给子进程"能被点到（Qt 的实例方法
        在测试侧替换不掉，真起一个设置窗又不合适），实现本身是 Qt 的标准 detach
        路径：实例 ``QProcess`` + ``startDetached()``，与静态重载同语义（子进程与
        父进程生命周期解耦；父进程的环境一个字节都不改）。
        """
        from PySide6.QtCore import QProcess

        process = QProcess()
        process.setProgram(program)
        process.setArguments(list(arguments))
        process.setWorkingDirectory(working_dir)
        process.setProcessEnvironment(environment)
        return bool(process.startDetached())

    def _launch_settings_process(self, instance=None, *, page: str | None = None) -> bool:
        """startDetached 独立设置进程；冻结包与源码运行分流。

        源码运行要走 `-m pet`（工作目录取仓库根），冻结包直接复用 exe 的参数
        分流入口（--settings）——与 --uninstall-cleanup 同一范式。

        子进程还带着一条 ``DSH_PET_PARENT_TOPOLOGY``：**本进程运行中的拓扑**
        （``overlay`` / ``legacy``）。设置页要按拓扑分流（子宠页的非 per-slot 键该
        写主配置还是 slot 文件），而它自己只能看到磁盘——磁盘上的捕获开关是**重启级**
        输入，用户勾了没重启时那个值描述的是"下一次启动"，不是那个正在跑的主进程。
        传运行中拓扑 = 让"保存成功、实际无效"重新变回"保存即生效"（见
        ``overlay_settings_command`` 的 ``ENV_PARENT_TOPOLOGY``）。
        """
        from PySide6.QtCore import QProcessEnvironment

        from . import overlay_settings_command as settings_command_mod

        if getattr(sys, "frozen", False):
            program = sys.executable
            arguments = ["--settings"]
            workdir = str(Path(sys.executable).parent)
        else:
            program = sys.executable
            arguments = ["-m", "pet", "--settings"]
            workdir = str(Path(__file__).resolve().parent.parent)
        if not program:
            logging.warning("sys.executable 为空，无法拉起独立设置进程")
            return False
        instance_id = _instance_config_identity(instance)
        if page:
            arguments += ["--settings-page", str(page)]
        if instance_id:
            arguments += ["--instance", instance_id]
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("DSH_PET_INSTANCE", "")
        environment.insert(settings_command_mod.ENV_PARENT_TOPOLOGY,
                           settings_command_mod.runtime_topology_env_value())
        try:
            started = self._spawn_settings_process(program, arguments, workdir,
                                                  environment)
        except Exception:
            logging.exception("拉起独立设置进程异常")
            return False
        if not started:
            logging.warning("startDetached 未启动独立设置进程，回退进程内设置页")
        return bool(started)

    def _mark_settings_child(self, active: bool) -> None:
        """记录独立设置进程存活态，并同步各窗气泡抑制与存活轮询。"""
        self._settings_child_active = bool(active)
        timer = getattr(self, "_settings_watch_timer", None)
        if timer is not None:
            if active:
                if not timer.isActive():
                    timer.start()
            else:
                self._settings_launch_at = 0.0
                # 设置页已关闭：归属身份作废（下次占用提示按"外部拉起"口径说）
                self._settings_owner_instance_id = None
                timer.stop()
        for inst in getattr(self, "_instances", []):
            update = getattr(inst, "_update_bubble_suppression_for_settings", None)
            if not callable(update):
                continue
            try:
                update()
            except Exception:
                logging.exception("同步设置期气泡抑制状态失败")

    def _poll_settings_process(self) -> None:
        """设置进程存活轮询：崩溃/漏事件时兜底解除气泡抑制；顺带消费指令。"""
        # 4.4a：D12 指令消费的轮询兜底（目录 watcher 漏事件/网络盘等场景）。
        self._consume_settings_command()
        self._refresh_legacy_profile_if_changed()
        if not bool(getattr(self, "_settings_child_active", False)):
            return
        if self._settings_process_running():
            # 子进程已建锁 = 启动窗口结束：此后锁一消失就可立即解除抑制。
            self._settings_launch_at = 0.0
            return
        if self._settings_launch_pending():
            return
        self._mark_settings_child(False)

    def _consume_settings_command(self) -> None:
        """消费独立设置进程写下的指令（D12；4.4a 起 legacy 拓扑也走这条通道）。

        退役前 legacy 的「一键退出子肥鱼」由设置进程直接 ``child_pet_cleanup``
        （runtime 标记 + taskkill）杀子进程；多进程多宠退役层停用后不存在跨进程
        子宠，统一改「写指令文件 → 主进程消费」。target 为空 = 退出全部子肥鱼；
        否则只退那个 slot 身份（身份已不在登记表 = 空操作，只留日志）。

        **overlay 拓扑下让路**：壳（``OverlayShell._consume_settings_command``）
        独占这条通道。两份消费者盯同一个配置目录、都走 ``consume_command``
        （消费即删），谁先跑谁把指令摘走——而本类的 ``clear_spawned_pets`` /
        slot 身份在 overlay 下都没有目标（子宠是 sprite，不在 ``_instances``
        里），抢到就是静默丢一次用户点击。
        """
        if getattr(self, "_overlay_shell", None) is not None:
            return
        config_dir = getattr(self.config, "dir", None)
        if config_dir is None:
            return
        from . import overlay_settings_command

        command = overlay_settings_command.consume_command(config_dir)
        if command is None:
            return
        if command.get("command") == overlay_settings_command.CMD_PROFILE_RESET:
            if command.get("target") == 0:
                self._apply_legacy_profile(0)
            return
        if command.get("command") == overlay_settings_command.CMD_APPLY_SETTINGS_RESET:
            target = command.get("target")
            if target is None:
                logging.info("收到设置进程指令 → 按默认值对齐主桌宠运行态")
                self.apply_settings_reset(self.instance)
                return
            for inst in list(self._instances):
                slot = overlay_settings_command.slot_from_instance_id(
                    str(getattr(inst.config, "instance_id", "") or ""))
                if slot == int(target):
                    logging.info("收到设置进程指令 → 按默认值对齐 slot-%s 运行态", target)
                    self.apply_settings_reset(inst)
                    return
            logging.info("收到设置进程指令 → slot-%s 已不在活跃清单，跳过", target)
            return
    def _refresh_legacy_profile_if_changed(self):
        if getattr(self, "_overlay_shell", None) is not None:
            return
        signatures = []
        for name in ("config-slot-0.json", "overlay-slot-generations.json"):
            try:
                stat = (self.config.dir / name).stat()
                signatures.append((stat.st_mtime_ns, stat.st_size))
            except OSError:
                signatures.append(None)
        signature = tuple(signatures)
        previous = getattr(self, "_legacy_profile_signature", signature)
        self._legacy_profile_signature = signature
        if signature != previous and not self._apply_legacy_profile(0):
            self._legacy_profile_signature = previous

    def _apply_legacy_profile(self, slot=0) -> bool:
        if slot != 0:
            return True
        from . import window_placement, pet_profiles

        snapshot = pet_profiles.read_slot_snapshot(self.config.dir, 0)
        if snapshot.status != "ok" or pet_profiles._slot_reset_pending(self.config.dir, 0):
            return False
        inst = self.instance
        win = inst.win
        center = None
        if win is not None:
            center = window_placement.virtual_pos(win) + win.stable_body_local_rect().center()
        inst.config.reload()
        character = str(inst.config.get("character", catalog.DEFAULT_CHARACTER))
        if win is not None:
            if character != (win.profile_character or character):
                try:
                    lib = inst._create_library(character)
                    old = win
                    old.close()
                    inst._build_window(character, lib=lib)
                    win = inst.win
                except Exception:
                    logging.exception("slot0 档案角色资源应用失败")
                    return False
            else:
                win.refresh_pet_settings()
            if center is not None:
                new_center = window_placement.virtual_pos(win) + win.stable_body_local_rect().center()
                win.move(win.pos() + center - new_center)
            win.set_profile_identity(character, inst.config.profile_generation())
        refresh_view = getattr(inst.config, "refresh_profile_view", None)
        if callable(refresh_view):
            refresh_view()
        return True

    def apply_settings_reset(self, instance=None) -> None:
        """刷新全局reset结果；宠物档案、位置与active不属于此动作。"""
        self.config.reload()
        self._apply_external_config_change()

    def _install_config_watcher(self) -> None:
        """盯 config.json 所在目录 + 文件，把外部写盘合并进运行期（幂等）。

        盯目录而不是只盯文件：config.save() 用 os.replace 落盘会换 inode，
        QFileSystemWatcher 对消失的路径会停止监视，只盯文件必丢后续事件。
        目录信号不带文件名，故 basename 过滤交给 fileChanged（带路径），
        目录信号负责换 inode 后重新 addPath、以及 settings.lock 出现/消失。
        300ms 去抖：一次保存可能伴随目录多次变动。进程内保存同样触发——
        去抖窗口内合并即可；finished 路径不改成走 watcher，保持原时序语义。
        """
        if getattr(self, "_config_watcher", None) is not None:
            return
        if not bool(self.config.get("settings_process_isolation", True)):
            return
        from PySide6.QtCore import QFileSystemWatcher, QTimer

        try:
            self.config.dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logging.warning("配置目录不可创建，跳过 config 变更监视：%s", self.config.dir)
            return
        watcher = QFileSystemWatcher()
        watcher.directoryChanged.connect(self._on_config_dir_changed)
        watcher.fileChanged.connect(self._on_config_file_changed)
        if not watcher.addPath(str(self.config.dir)):
            logging.warning("无法监视配置目录：%s", self.config.dir)
            return
        self._config_watcher = watcher
        self._last_config_signature = self._config_signature()
        self._config_reload_timer = QTimer()
        self._config_reload_timer.setSingleShot(True)
        self._config_reload_timer.setInterval(300)
        self._config_reload_timer.timeout.connect(self._on_config_change_debounced)
        self._settings_watch_timer = QTimer()
        self._settings_watch_timer.setInterval(3000)
        self._settings_watch_timer.timeout.connect(self._poll_settings_process)
        self._watch_config_file()

    def _watch_config_file(self) -> None:
        """确保 config.json 在监视列表里（os.replace 换 inode 后被 Qt 自动移除）。"""
        watcher = getattr(self, "_config_watcher", None)
        if watcher is None:
            return
        try:
            path = str(self.config.path)
            if self.config.path.exists() and path not in watcher.files():
                watcher.addPath(path)
        except OSError:
            pass

    def _config_signature(self):
        """(st_ino, mtime_ns, size) 签名：判断 config 是否真的变了（目录信号不带文件名）。

        ``st_ino`` 让原子 ``os.replace`` 落盘换到的新 inode 与上一份区分开——同字节
        数、同时间戳刻度（FAT/exFAT 2s）的改动不再被判重。**非绝对保证**：原位改写、
        inode 号复用、或取不到 inode（部分网络/FUSE 挂载返回 0）时退化为
        ``(mtime_ns, size)``（与改造前同口径，不会更严），故去重门只许偏保守
        （宁可多应用一次，见 ``_on_config_change_debounced``）。
        """
        try:
            stat = self.config.path.stat()
        except OSError:
            return None
        return (stat.st_ino, stat.st_mtime_ns, stat.st_size)

    def _arm_config_reload(self) -> None:
        """重启去抖窗口：窗口内的多次变动合并成一次 reload+应用。"""
        timer = getattr(self, "_config_reload_timer", None)
        if timer is not None:
            timer.start()

    def _on_config_file_changed(self, path: str) -> None:
        if Path(path).name != self.config.path.name:
            return  # 只认本配置文件的 basename（同目录还有 settings.lock 等）
        self._watch_config_file()
        # 盘上内容没变就不重启去抖窗口：同一次 os.replace 的重复通知可能迟到于
        # 首轮应用之后（mac 实测一次保存两次应用链），无门就会再应用一次。
        # 签名口径与目录侧（_on_config_dir_changed）同源；新内容照常进窗口。
        if self._config_signature() != getattr(self, "_last_config_signature", None):
            self._arm_config_reload()

    def _on_config_dir_changed(self, path: str) -> None:
        self._watch_config_file()
        self._refresh_legacy_profile_if_changed()
        # 4.4a：D12 指令通道的目录侧消费（原子 os.replace 会在目录里产生事件）。
        self._consume_settings_command()
        if self._config_signature() != getattr(self, "_last_config_signature", None):
            self._arm_config_reload()
        # 锁文件出现 = 设置进程已起来（启动窗口结束）；锁文件消失 = 设置进程
        # 退出（QLockFile 解锁即删文件）→ 立即解除气泡抑制。
        lock_path = self.config.dir / "settings.lock"
        if lock_path.exists():
            self._settings_launch_at = 0.0
        elif (bool(getattr(self, "_settings_child_active", False))
                and not self._settings_launch_pending()):
            self._mark_settings_child(False)

    def _on_config_change_debounced(self) -> None:
        # 先采样再 reload，finally 记**采样值**：应用期间外部落盘的第二次保存不能
        # 被算成"已应用"（那会让它随后的通知全被去重门吞掉）。采样只会偏旧 →
        # 失效方向只可能是多应用一次，不可能是漏。
        sampled = self._config_signature()
        self.config.reload()
        try:
            self._apply_external_config_change()
        except Exception:
            logging.exception("应用外部配置变更失败")
        finally:
            self._last_config_signature = sampled

    def _teardown_config_watcher(self) -> None:
        """释放 watcher 与两个定时器（退出/测试收口共用）。"""
        watcher = getattr(self, "_config_watcher", None)
        if watcher is not None:
            for signal, slot in (
                (watcher.directoryChanged, self._on_config_dir_changed),
                (watcher.fileChanged, self._on_config_file_changed),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            self._config_watcher = None
        for name in ("_config_reload_timer", "_settings_watch_timer"):
            timer = getattr(self, name, None)
            if timer is None:
                continue
            try:
                timer.stop()
            except RuntimeError:
                pass

    # ------------------------------------------------------------ 启动
    def start(self) -> None:
        # aboutToQuit 只在控制器层绑定一次：角色热切换会重建窗口，逐个
        # connect win.save_position 会在旧窗口延迟销毁后残留失效引用。
        # 统一走 _on_about_to_quit，在信号触发时读取当前有效窗口。
        if not self._on_about_to_quit_connected:
            self.app.aboutToQuit.connect(self._on_about_to_quit)
            self._on_about_to_quit_connected = True
        character_id = str(self.config.get('character', catalog.DEFAULT_CHARACTER))
        logging.info('当前形象: %s', character_id)
        # 拓扑分流（T5/4.1a + T4 Phase A）：唯一读取点是
        # overlay_shell.is_overlay_topology（显式 PET_RENDER_TOPOLOGY 优先，其次
        # 主配置 stream_capture_mode，启动时快照定死）。overlay → 单合成窗产品壳
        # 接管渲染，不建 PetWindow；**捕获模式（stream_capture_mode=true）→ 这里
        # 走 legacy 单窗 PetWindow 路径**（OBS 只能枚举真窗口），OverlayShell
        # 根本不构造 ⇒ 活跃宠清单里的多只桌宠不会自动复活（T4「重启时收拢为主
        # 宠物」），但清单本身不删（关掉捕获模式重启即回来）。
        from .overlay_shell import is_overlay_topology
        overlay_topology = is_overlay_topology()
        # 拓扑落一行日志：捕获模式"勾了但没重启"与"重启后确实切了"在用户侧
        # 只表现为窗口标题/任务栏，支持排查需要一行可 grep 的证据。
        logging.info('渲染拓扑: %s',
                     'overlay(单合成窗)' if overlay_topology else 'legacy(单窗 PetWindow)')
        if overlay_topology:
            from .overlay_shell import OverlayShell
            self._overlay_shell = OverlayShell(self.app, self.instance)
            self._overlay_shell.start()
            selector = getattr(self._overlay_shell, "select_slot", None)
            if self._slot_id is not None and callable(selector):
                selector(self._slot_id)
        else:
            if 0 in self._active_pet_slots:
                self._create_ui_with_character_fallback(str(self.instance.config.get(
                    'character', catalog.DEFAULT_CHARACTER)))
            else:
                self._build_empty_pet_tray()
            self._refresh_legacy_profile_if_changed()
        # 批5.2a：进程级共享全屏 watcher 在主窗就绪后启动（自省任一窗是否需要，
        # 无需窗——环则空转）；flag 关时 _shared 为 None，no-op。
        if self._shared is not None:
            self._shared.start()
        self._install_macos_dock_menu()
        self.instance._apply_spawn_offset()
        self._apply_balance_timer()
        self._sync_festival_service()
        # 设置页进程隔离：启动即装 config 目录 watcher，独立设置进程落盘后由它
        # 合并进运行期（开关关闭时不装，完全走旧路径）。
        self._install_config_watcher()
        QTimer.singleShot(3500, self.instance._check_autostart_wanted)
        # issue #111：会话结束（Windows 关机/注销）探测器。必须在窗口就绪后安装
        # ——它要在关机窗口期到来**之前**就位，才能抢在会话拆除前关掉 ffmpeg
        # 派生（否则系统会弹 0xc0000142 阻塞关机）。
        self._install_session_watcher()
        # 全局快捷键：壳已就绪才装（分发目标是壳的三个既有入口），默认全不绑。
        self._announce_slot0_profile_problem()

    def _announce_slot0_profile_problem(self) -> None:
        """slot0 档案降级后的**可见**告知（含文件路径与恢复动作）。

        静默降级比硬失败更危险：用户看到的是"我的主桌宠不见了"，只会以为坏了或丢了设置。
        这里在窗口/托盘就绪之后把诊断说出来，并点名"生成 / 恢复 slot0"这条显式入口
        （托盘与无托盘恢复窗都有）——恢复动作仍然只由用户自己做，程序不代劳、不覆盖。
        """
        diagnosis = self.slot0_profile_diagnosis()
        if not diagnosis:
            return
        overlay = getattr(self, "_overlay_shell", None)
        if overlay is not None:
            teller = getattr(overlay, "announce_slot0_profile_problem", None)
        else:
            teller = None
        if callable(teller):
            try:
                if teller(diagnosis):
                    return
            except Exception:
                logging.exception("提示 slot0 档案降级失败（overlay）")
        win = getattr(getattr(self, "instance", None), "win", None)
        shower = getattr(win, "show_bubble", None)
        if callable(shower):
            try:
                shower(f"{diagnosis}\n可用托盘/恢复窗的「生成 / 恢复 slot0」再试。",
                       9000)
                return
            except Exception:
                logging.exception("提示 slot0 档案降级失败（窗口）")
        logging.warning("slot0 档案降级提示无法上屏（无可见桌宠/托盘）：%s", diagnosis)

    def _install_session_watcher(self) -> None:
        """安装会话结束探测器（幂等；实例属性强引用保活，不跨实例共享）。"""
        if getattr(self, "_session_watcher", None) is not None:
            return
        try:
            self._session_watcher = install_session_watcher(
                app=self.app, on_session_end=self._on_session_end,
            )
        except Exception:
            logging.exception("安装会话结束探测器失败")

    def _on_session_end(self) -> None:
        """会话结束（关机/注销）：冻结各窗并停止全部 ffmpeg reader（issue #111）。

        幂等：重复的会话结束信号（WM_QUERYENDSESSION 之后又有 WM_ENDSESSION、
        Qt 的 commitDataRequest/aboutToQuit）只收口一次。

        只做正常退出路径（``_on_about_to_quit``）不做、且关机场景必需的三件事：
        关 ffmpeg spawn 闸门、冻结窗口动画（``match_shutdown``）、把各窗素材库
        里**已建的全部 clip** 一起停掉（不只是各窗当前在播的那个：圈末软停驻留
        的 clip 仍持有一个存活但空闲的 ffmpeg 进程，关机时一并收口）、留一行日志。

        刻意**不**做会话保存/写盘/槽位解锁：关机时登录会话已在拆除，那些收尾
        既非必需（多开文件锁由操作系统在进程退出时释放）又会拉长清理窗口，
        与「静默、快速、不再派生任何进程」的目标相反。
        """
        if getattr(self, "_session_end_done", False):
            return
        # 「真会话结束」才置位（ops5.5 终审 C2）：SessionWatcher 把 aboutToQuit 也
        # 汇进同一条 arm 回调——那只是正常退出的兜底，不是关机/注销。靠
        # ``_on_about_to_quit`` 先行置下的标记区分（Qt 按连接序调槽，主退出先到）。
        # 不区分的话，:2137/:2185/:2369 三处会把「正常退出」误当「会话结束」跳过。
        if not getattr(self, "_plain_about_to_quit", False):
            self._session_end_done = True
        self._mark_session_ending()
        # D4：会话结束（关机/注销）路径释放桌宠单实例进程门。与下面的
        # 「不做会话保存/写盘/槽位解锁」不冲突——本模块的释放是一次 unlink +
        # 关句柄，O(1)、不派生进程、不写盘；不显式释放则只剩"进程被拆掉后由
        # OS 回收句柄 + 下次启动按 QLockFile pid 陈旧判定接管"这条兜底链。
        self._release_overlay_gate()
        stopped = 0
        for inst in self._instances:
            win = getattr(inst, "win", None)
            match_shutdown = getattr(win, "match_shutdown", None)
            if callable(match_shutdown):
                try:
                    match_shutdown()
                except Exception:
                    logging.exception("会话结束时冻结窗口失败")
            lib = getattr(win, "lib", None)
            stop_all = getattr(lib, "stop_all_clips", None)
            if callable(stop_all):
                try:
                    stop_all()
                    stopped += 1
                except Exception:
                    logging.exception("会话结束时停止素材库 clip 失败")
        logging.info(
            "会话结束：已停止全部 ffmpeg reader（%d 个素材库收口），进入静默退出", stopped,
        )

    def _release_overlay_gate(self) -> None:
        """释放桌宠单实例进程门（D4；幂等，未注入门时 no-op）。"""
        gate = getattr(self, "_overlay_gate", None)
        if gate is None:
            return
        try:
            gate.release()
        except Exception:
            logging.exception("释放桌宠单实例进程门失败")

    def _mark_session_ending(self) -> None:
        """置位进程级 ffmpeg spawn 闸门（webm_clip.set_session_ending）。

        覆盖「已进入退出流程、但原生 WM_QUERYENDSESSION 未被观测到」的路径
        （如托盘退出、Qt aboutToQuit、测试直接调收口）。
        """
        # 退出标记与闸门同源（R3-gemini P1）：只走 aboutToQuit 置位会漏掉
        # 会话结束观察路径（:2042），在途 autostart worker 会无视退出继续拉起。
        self._quitting = True
        try:
            webm_clip_mod.set_session_ending(True)
        except Exception:
            logging.exception("置位会话结束闸门失败")


    def _create_ui_with_character_fallback(self, character_id: str) -> None:
        """启动路径创建主窗；配置记住的角色素材目录已被删/搬走（如 DLC 卸载）
        时回退默认角色重试一次，而不是直接弹错退出。默认角色也缺素材则照常
        抛出，由上层弹启动错误。"""
        try:
            self.instance._create_ui(character_id)
        except FileNotFoundError:
            if character_id == catalog.DEFAULT_CHARACTER:
                raise
            logging.warning('角色 %s 素材缺失，回退默认角色 %s', character_id, catalog.DEFAULT_CHARACTER)
            character_id = catalog.DEFAULT_CHARACTER
            self.config.set('character', character_id)
            self.instance._create_ui(character_id)

    # ------------------------------------------------------------ 退出收口
    def _on_about_to_quit(self) -> None:
        """退出前保存各窗位置并释放资源（全进程「全部退出」语义，R5 切分）。

        aboutToQuit 只绑定一次自本控制器；切换角色会重建桌宠窗口，信号
        触发时读取当前窗口（经 ``self.instance.win``），避免调用已延迟销毁
        的旧窗口。

        R5 切分：**窗级**项（位置/预热/Agent/各窗会话保存/slot 锁/每窗自持的
        碰撞会话）逐窗收口；批5.3 起共享解码 hub 为进程级（shutdown 为 no-op），
        **进程级**收口仅剩 hub ``stop_all()`` 与 ``close_all_writers(permanent=True)``
        各停一次——多窗下任一窗退出不许停进程级资源，只有「全部退出」才收口
        （这也是「退出这只」与「全部退出」的核心差异）。
        """
        # 纯桌宠版（打包排除 ``pet.chat``）里这个模块根本不存在：模块级无条件 import
        # 会让正常退出在**第一步**就 ModuleNotFoundError，而它发生在 ``_mark_session_ending``
        # / ``_quitting`` 等收口之前——位置回写、共享子系统停表、ffmpeg reader 收尾全部
        # 被跳过（2026-10-10 终审「no-chat 变体 normal quit 提前异常」）。改成能力守卫内
        # 的按需 import：没有 chat 就没有会话写盘 worker 要收，跳过是正确答案。
        # issue #111：先关 ffmpeg spawn 闸门，再走正常退出收口——正常退出路径
        # （托盘退出/最后窗口关闭）同样落在关机前后，绝不能在里面再派生 reader。
        # 「正常退出兜底」标记（ops5.5 终审 C2）：本槽先于 SessionWatcher 的
        # aboutToQuit→arm 执行（Qt 按连接序调槽），``_on_session_end`` 凭它区分
        # 「真会话结束」与「正常退出兜底」，只有前者才置 ``_session_end_done``。
        self._plain_about_to_quit = True
        self._mark_session_ending()
        # 退出标记（R2 第五缺口）：在途自动拉起 worker 凭它中止或补偿收口——
        # 否则「退出时登记表为空 → worker 随后 spawn 登记」会留下永远无人收的进程。
        self._quitting = True
        # 窗级收口：逐窗保存位置、停本窗预热与 Agent、提交本窗会话
        for inst in self._instances:
            win = inst.win
            if win is not None:
                try:
                    win.save_position()
                except Exception:
                    logging.exception("退出时保存位置失败")
                try:
                    if getattr(win, 'lib', None) is not None:
                        win.lib.pause_warm()
                except Exception:
                    logging.exception("退出时暂停预热失败")
                # issue #111：供给线程不是预热线程——``pause_warm`` 管不到它，而它
                # 自己派生转换 ffmpeg。退出同样是"再派生进程"的坏时机（与 overlay 的
                # ``_on_about_to_quit`` 同一收口位置），库随窗口销毁时活线程还会被
                # 一起析构（Qt fatal）。库侧自带幂等 + 有界等待 + 超时孤儿兜底。
                try:
                    if getattr(win, 'lib', None) is not None:
                        win.lib.cancel_frameseq_provision()
                except Exception:
                    logging.exception("退出时取消帧序列供给线程失败")
            # 批5.2 P1-1：每窗自持 broker，逐窗收口（「全部退出」逐窗停）
            try:
                inst.broker_facade.shutdown()
            except Exception:
                logging.exception("退出时关闭 broker facade 失败")
        # 会话异步写盘（B8）：全部会话已保存，再永久关闭写盘 worker
        #（关掉后迟到的 queued 回调提交会被明确拒绝）。
        # 节日提醒是进程级懒服务，退出必须一并停：其无主 QTimer 的 timeout
        # 连接从 Qt C++ 侧强引用住整个对象图（理由同 todo_service，见
        # _shutdown_live_for_tests 注释）；不停则退出期仍在跑 30s tick。
        if self.festival_service is not None:
            self.festival_service.stop()
        try:
            from .chat import session_store as _session_store

            if not _session_store.close_all_writers(permanent=True):
                logging.warning("退出时会话写盘 worker 未干净关闭")
        except ImportError:
            logging.info("退出收口：本构建没有 chat 模块，跳过会话写盘收口")
        except Exception:
            logging.exception("退出时关闭会话写盘 worker 失败")
        # 批5.2a：进程级共享子系统收口（全屏 watcher / 免打扰轮询）。
        # 单窗关闭（退出这只）不触发——只有「全部退出」才停共享子系统。
        if self._shared is not None:
            try:
                self._shared.stop_all()
            except Exception:
                logging.exception("退出时关闭共享子系统失败")
        # 批5.3：进程级共享解码 hub 收口（全部退出时才停；各窗的源/订阅早已
        # 由窗 closeEvent/_switch 的 shareable_end 逐素材收敛）。
        try:
            self._decode_hub.stop_all()
        except Exception:
            logging.exception("退出时关闭共享解码 hub 失败")
        # 设置页进程隔离：释放 config 目录 watcher 与两个定时器（无主 QTimer 的
        # timeout 连接会从 Qt C++ 侧强引用住本对象图，不停则阻碍回收）。
        self._teardown_config_watcher()

    @classmethod
    def _shutdown_live_for_tests(cls) -> None:
        """收口测试直接创建、未走 aboutToQuit 的 AppShell。

        只做 Qt 生命周期释放，不改业务状态：
        - 停待办提醒服务定时器（其 ``_app`` 反向强引用 shell，且无主 QTimer 的
          timeout 连接从 Qt C++ 侧强引用住整个对象图，Python gc 回收不掉）；
        - 共享子系统经 ``SharedSubsystems._shutdown_live_for_tests`` 收口；
        - 断开 shell → app 的 aboutToQuit 连接并释放反向引用；
        - 注销全局聊天订阅（同生产收口口径）。

        不做 ``_on_about_to_quit`` 的退出语义（保存位置/永久关闭写盘 worker）：
        那是「全部退出」，测试收口不得触发。
        """
        for shell in tuple(_LIVE_SHELLS):
            try:
                if getattr(shell, "_shared", None) is not None:
                    shell._shared.stop_all()
                service = getattr(shell, "festival_service", None)
                if service is not None:
                    try:
                        service.stop()
                    except Exception:
                        logging.debug("测试收口节日提醒服务失败", exc_info=True)
                    shell.festival_service = None
                if getattr(shell, "instance", None) is not None:
                    win = getattr(shell.instance, "win", None)
                    lib = getattr(win, "lib", None)
                    if lib is not None:
                        lib.pause_warm()
                if getattr(shell, "_on_about_to_quit_connected", False):
                    try:
                        shell.app.aboutToQuit.disconnect(shell._on_about_to_quit)
                    except (RuntimeError, TypeError):
                        pass
                    shell._on_about_to_quit_connected = False
                # 设置页进程隔离：watcher/定时器同属"无主 Qt 对象"一族，收口
                #（不停会让后续测试凭空多一条 3s 轮询，并阻碍对象图回收）。
                teardown_watcher = getattr(shell, "_teardown_config_watcher", None)
                if callable(teardown_watcher):
                    try:
                        teardown_watcher()
                    except Exception:
                        logging.debug("测试收口 config watcher 失败", exc_info=True)
                shell._settings_child_active = False
                shell._instances = []
            except Exception:
                logging.debug("测试收口 AppShell 失败", exc_info=True)

    def _on_shared_fullscreen(self, hit: bool) -> None:
        """批5.2a：共享全屏 watcher 广播 → 扇出到各窗的 _on_fullscreen_changed。

        逐窗动态遍历（读 _instances 而非绑定某窗），任一窗退出/重建后自动忽略它。
        经窗的公开信号全屏状态回传（避开 window 私有面冻结，见 test_architecture 红线2）。
        """
        if getattr(self, "_shared", None) is None:
            return
        # 免打扰（issue #208）：全屏 = 等效免打扰的唯一来源（不另起探测）。
        # **入场先立闸、退场后结算**，两个落点都不能挪：
        # - 入场（hit=True）在隐藏各窗之前立闸，隐藏动作自身带出的呈现不会漏过门控；
        # - 退场（hit=False）必须等各窗**恢复显示之后**再结算——结束汇报经
        #   ``MultiWindowProxy`` 只投向可见窗，窗口还没回来就结算等于把攒下的
        #   提醒汇报给空气（交付确认兜底会让它下一拍重试，但正序才是常态路径）。
        # 也刻意不走下面那个按 auto_hide_fullscreen 的逐窗过滤：那是自动隐藏的
        # 开关，与 quiet_also_on_fullscreen 是两个独立偏好。
        from . import quiet_mode

        if hit:
            quiet_mode.note_fullscreen(True)
        for inst in self._instances:
            win = inst.win
            if win is None or not shiboken6.isValid(win):
                continue
            # 复审 P1-2：全屏广播按每窗配置过滤——关掉「全屏自动隐藏」的窗
            # 不得被无关广播隐藏/恢复（光标路径的每窗 gate 在窗内已有，
            # 该窗的 _on_cursor_visibility_changed 首行自过滤，无需重复）。
            if not getattr(win, "auto_hide_fullscreen", False):
                continue
            try:
                win.fullscreen_changed.emit(hit)
            except (AttributeError, RuntimeError):
                logging.exception("扇出全屏状态到窗口失败")
        if not hit:
            quiet_mode.note_fullscreen(False)

    def _on_shared_cursor(self, visibility: str) -> None:
        """批5.2a：共享光标可见性广播 → 扇出到各窗的 _on_cursor_visibility_changed。"""
        if getattr(self, "_shared", None) is None:
            return
        for inst in self._instances:
            win = inst.win
            if win is None or not shiboken6.isValid(win):
                continue
            try:
                win.cursor_visibility_changed.emit(visibility)
            except (AttributeError, RuntimeError):
                logging.exception("扇出光标状态到窗口失败")

    def _identity_config(self):
        """进程级服务的**角色身份**取源：当前呈现身份的每宠视图。

        ``character`` 属 ``PER_PET_KEYS``，真值在 ``config-slot-N.json``；全局面那个
        ``character`` 是出厂默认的残留（slot0 迁移与 ``Config.save`` 都会把每宠键从
        ``config.json`` 清掉）。所以托盘「切换角色」勾选、主动识屏的 ``pet_name``
        等进程级读点一律经这里取当前身份——不是「没有值」，是**稳定读到错的默认值**。

        两条拓扑各自的"该宠此刻真正在用的那份视图"，不另造读取口径：

        - overlay：主宠是 sprite，取壳的 ``_sprite_config(主 sprite)``（配置同步边界
          会作废它的快照，换角色后立刻是新值）；
        - legacy：``PetInstance.config`` 那条 slot0 路由视图。

        overlay 壳还没有主 sprite（启动期、slot0 档案被降级、退出收口后）时退回同一条
        slot0 视图：两者读的都是 slot0 档案，不会给出第二个真值。
        """
        overlay = getattr(self, "_overlay_shell", None)
        sprite = getattr(overlay, "sprite", None)
        sprite_config = getattr(overlay, "_sprite_config", None)
        if sprite is not None and callable(sprite_config):
            return sprite_config(sprite)
        config = getattr(getattr(self, "instance", None), "config", None)
        return config if config is not None else self.config

    def _apply_balance_timer(self) -> None:
        self._balance_timer.stop()
        minutes = max(0, int(self.config.get("balance_refresh_minutes", 0) or 0))
        if minutes:
            self._balance_timer.start(minutes * 60000)

    # ------------------------------------------------------------ 余额
    def show_balance(self, parent=None) -> None:
        # 宿主判定：必须是能冒泡的 pet 形宿主。overlay 菜单把合成窗
        # （OverlayWindow，无 show_bubble）当 parent 传下来，直接用它会在
        # _show_balance_payload 里 AttributeError；overlay 拓扑下 ``instance.win``
        # 又恒为 None——两条都收敛到 ``self.win``（原生 Win 或 sprite 壳）。
        win = parent
        if win is None or not callable(getattr(win, "show_bubble", None)):
            win = self.win
        if win is None or self._balance_busy or not win.isVisible():
            return
        now = time.monotonic()
        # 余额缓存绑定 provider 身份（id + base_url + key 摘要）：同地址不同账号也不串号；
        # 摘要不可逆推原 key，不落敏感信息。
        import hashlib
        settings = self.config.chat_settings()
        provider = settings.active_config
        provider.api_key = self.config.resolve_api_key(provider)
        key_digest = hashlib.sha256(str(provider.api_key or '').encode()).hexdigest()[:12]
        provider_key = '|'.join([
            str(getattr(provider, 'id', '') or ''),
            str(provider.base_url or ''),
            key_digest,
        ])
        if self._balance_cache is not None and now - self._balance_cache[0] < 30.0 \
                and self._balance_cache[2] == provider_key:
            _show_balance_payload(win, self._balance_cache[1])
            return
        file_payload = self._read_balance_file_cache(provider_key)
        if file_payload is not None:
            self._balance_cache = (now, file_payload, provider_key)
            _show_balance_payload(win, file_payload)
            return
        self._balance_busy = True
        # 延迟到事件循环空闲再冒泡：macOS 菜单跟踪会话内新建/显示窗口会被
        # AppKit 抑制（与设置对话框首次点击无反应同源），singleShot 在 macOS
        # 上要等菜单关闭后才派发，Windows 上立即派发也无害。
        QTimer.singleShot(0, lambda: win.show_bubble('让我看看余额…', duration_ms=6000))
        bridge = _BalanceBridge(win, owner=self)
        self._balance_bridge = bridge
        try:
            threading.Thread(
                target=self._balance_worker,
                args=(bridge, provider.base_url, provider.api_key, provider.verify_ssl, provider_key),
                daemon=True, name='pet-balance',
            ).start()
        except Exception as exc:  # noqa: BLE001 - 启动失败也必须释放忙状态
            self._balance_busy = False
            error_message = f'余额查询失败：{exc}'
            QTimer.singleShot(0, lambda message=error_message: bridge.done.emit(False, message))

    def _balance_worker(self, bridge, base_url: str, api_key: str, verify_ssl: bool, provider_key: str = '') -> None:
        from . import balance as balance_mod  # 按需导入（见 _show_balance_payload）
        try:
            info = balance_mod.fetch_balance(base_url, api_key, verify_ssl=verify_ssl)
            text = balance_mod.format_balance(info)
            payload = {"text": text, "info": info}
            self._balance_cache = (time.monotonic(), payload, provider_key)
            self._write_balance_file_cache(payload, provider_key)
            bridge.done.emit(True, payload)
        except Exception as exc:  # noqa: BLE001 - 任何失败走气泡提示
            bridge.done.emit(False, f'余额查询失败：{exc}')
        finally:
            self._balance_busy = False

    def _read_balance_file_cache(self, provider_key: str = '') -> dict | None:
        """读取跨实例共享的余额缓存（30s 内有效，且必须是同一 provider 的缓存）。

        返回 {"text": ..., "info": {...}}；兼容旧版只存 text 字符串的缓存。
        """
        try:
            data = json.loads(self._balance_cache_path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return None
            if str(data.get('provider', '') or '') != provider_key:
                return None
            if time.time() - float(data.get('ts', 0) or 0) >= 30.0:
                return None
            text = str(data.get('text', '') or '')
            if not text:
                return None
            info = data.get('info')
            return {
                'text': text,
                'info': info if isinstance(info, dict) else {},
            }
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _write_balance_file_cache(self, payload: dict, provider_key: str = '') -> None:
        """写入跨实例共享的余额缓存（原子替换，绑定 provider）。

        同时保存 text 和 info，使缓存命中时也能显示峰谷副标题并播放余额动画。
        """
        try:
            self._balance_cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._balance_cache_path.with_suffix(f'.{os.getpid()}.tmp')
            tmp.write_text(
                json.dumps({
                    'ts': time.time(),
                    'text': str(payload.get('text') or ''),
                    'info': payload.get('info') or {},
                    'provider': provider_key,
                }, ensure_ascii=False),
                encoding='utf-8',
            )
            tmp.replace(self._balance_cache_path)
        except OSError:
            pass

    # ------------------------------------------------------------ 多窗
    def spawn_in_process_window(self, offset_index: int = 1) -> PetInstance:
        """进程内创建第二个 PetInstance（不共享库/Config/SessionStore）。

        - 新 slot 身份：4.4a 起走 **D6 无锁分配器**（``overlay_spawn_state.
          allocate_slot``，与 overlay 拓扑同一套口径），不再抢 slot-N.lock
          ——多进程多宠退役层的文件锁不再被任何路径使用；
        - 独立 Config(instance_id=slot-N)，显式传 instance_id（不再依赖进程级
          DSH_PET_INSTANCE），独立 MovieLibrary / PetWindow / SessionStore 目录；
        - 碰撞不再经 QLocal 回环：多宠碰撞归 overlay 拓扑的 sprite 世界；
          legacy 的多窗是渲染面（捕获模式收窄），窗间不做跨进程冲量交换。
        """
        overlay = getattr(self, "_overlay_shell", None)
        if overlay is not None:
            overlay.spawn_pet()
            return self.instance
        from .overlay_shell import is_overlay_topology

        if not is_overlay_topology():
            raise RuntimeError("捕获模式仅允许恢复slot0，不创建额外多宠窗口")
        config_dir = self.config.dir
        from . import overlay_spawn_state as overlay_spawn_state_mod

        # 进程内 slot 语义 = 窗身份分配：已占用 = 目录内既有 config-slot-N.json
        # 身份 ∪ 本进程活跃窗身份；分配单调增长，永不与保留身份相撞。
        used = {inst.slot_id for inst in self._instances if inst.slot_id is not None}
        slot_id = overlay_spawn_state_mod.allocate_slot(config_dir, active_slots=used)
        instance_id = slot_manager_mod.slot_to_instance_id(slot_id)
        # 新 slot 落种：走共享落种函数。无存档 slot 按主设置落种；存在但未在该
        # 子肥鱼设置界面自定义过的 slot 按主设置刷新；已自定义（user_customized）
        # 的 slot 一个键都不碰。落种/刷新永不写位置键。
        from . import pet_profiles
        from .settings_slot_config import route_settings_config

        if not pet_profiles.slot_profile_exists(config_dir, slot_id):
            from .config import normalize_pet_profile_snapshot

            source = normalize_pet_profile_snapshot(pet_profiles.read_slot_profile(config_dir, 0).data)
            seeded = pet_profiles.write_profile_settings(config_dir, slot_id,
                {key: source[key] for key in pet_profiles.PER_PET_SETTING_KEYS})
            if not seeded.ok:
                raise RuntimeError(str(seeded))
        # 复用主窗同一配置根目录（AppShell.config.dir 的父目录），使所有窗的
        # config-slot-N.json / sessions-slot-N 落在同一 APP_DIR_NAME 下，仅按
        # instance_id 区分；显式传 instance_id，不再依赖进程级 DSH_PET_INSTANCE。
        new_config = route_settings_config(Config(base=self.config.dir.parent, instance_id=instance_id))
        character_id = str(new_config.get('character', catalog.DEFAULT_CHARACTER))
        inst = PetInstance(
            self, new_config, slot_id=slot_id, spawn_offset=offset_index,
        )
        # 批5.3：P1-6 移除——进程内多窗不再停用任何窗的共享解码；新窗与主窗
        # 共用同一进程级 DecodeFanoutHub（同素材首窗发布、同速窗进食）。
        # build_tray=False：非主窗不再新建/替换进程级托盘，改由 _refresh_tray_menu 聚合。
        inst._build_window(character_id, build_tray=False)
        self._instances.append(inst)
        inst._apply_spawn_offset()
        self._refresh_tray_menu()
        # 批5.2a §③.4：_check_autostart_wanted 逐窗（读各自 config），新窗入列后补一次。
        QTimer.singleShot(3500, inst._check_autostart_wanted)
        # N-5：msg 不手写 [slot-N] 前缀——_slot_wrap/_SlotLogFilter 会加调用方
        # 槽位前缀，叠加成双前缀纯噪音；新窗身份保留在正文里。
        logging.info("进程内新窗已创建 (slot=%s, instance=%s)", slot_id, instance_id)
        return inst

    def _on_window_exit_requested(self, instance: PetInstance,
                                  *, defer_heavy_teardown: bool = False) -> None:
        """窗级「退出这只」（R5 切分）：只收口本窗，不碰其它窗的进程级资源。

        顺序：存本窗位置 → 停本窗预热 → 保存本窗三聊天窗 live session
        （P0-2，对齐 aboutToQuit 安全网）→ 关闭/断开本窗从属窗（P1-5，防 writer
        复活）→ 删本窗 runtime 标记 → 关本窗 sessions writer（非 permanent，
        2s 超时）→ 释放本窗 slot 锁 → 停本窗碰撞会话（P1-1；共享解码 hub 为
        进程级，其 shutdown 是 no-op，不在此停）→ 关本窗 →
        子窗从呈现集合移除；slot0关闭只释放呈现，固定控制instance与共享会话保留。
        不提升、不quit，进程级writer仅在显式退出应用收口。

        ``defer_heavy_teardown=True``（批 G，仅「退出子肥鱼」链式路径使用）：
        把有界但秒级的重资源回收——本窗 sessions writer 关闭（最多 2s join）、
        碰撞会话停止（最多 3s+1s wait）——挪到进程级后台 reaper 线程串行执行；
        UI 线程只保留关窗、摘 runtime 标记、释放 slot 锁、从登记表移除等毫秒级
        必做步骤，N 只连清时主桌宠不再冻结。默认 False = 「退出这只」单窗路径保持
        既有同步语义逐位不变。重回收只做线程 join / queued 调用 / 纯 Python
        注册表操作，不触碰 Qt 对象，后台执行安全。

        **第一步是设置页闸门**（2026-10-11 ops P3-c）：进程内设置页开着时先过一遍
        它的关闭闸门（保存/放弃/继续编辑）。用户选「继续编辑」→ **整次收口取消**，
        位置、预热、会话、引用、活跃集合一个都不动；否则才往下走。放在这里
        而不是收口中途，是因为中途 return 只会留下半死的宠物（见
        ``_settings_window_releasable``）。
        """
        if not self._settings_window_releasable(instance):
            logging.info("退出这只：用户留在设置页里继续改，本次收口取消（一个资源都没动）")
            return
        win = instance.win
        if instance is self.instance:
            if win is None:
                return
            win.save_position()
            win.close()
            instance.win = None
            self._active_pet_slots = [n for n in self._active_pet_slots if n != 0]
            self._save_active_set(action="关闭 slot0")
            self._build_empty_pet_tray()
            return
        heavy_jobs: list[tuple[str, object]] = []  # defer 模式的重回收任务
        if win is not None:
            try:
                win.save_position()
            except Exception:
                logging.exception("退出这只：保存位置失败")
            try:
                if getattr(win, 'lib', None) is not None:
                    win.lib.pause_warm()
            except Exception:
                logging.exception("退出这只：暂停预热失败")
        # 批5.2 P1-5：关闭/隐藏本窗的设置窗并断开引用，防止孤儿顶层窗
        # 在 writer 关闭后经 store 提交、复活写盘 worker（常驻到进程结束）。
        self._close_instance_subwindows(instance)
        if win is not None:
            marker_remover = getattr(win, 'remove_runtime_marker', None)
            if callable(marker_remover):
                try:
                    marker_remover()
                except Exception:
                    logging.exception("退出这只：删除 runtime 标记失败")
        # 批5.2 P1-7：运行期关窗不许冻 GUI 10s——只关本窗 writer，timeout 降到 2s。
        # 批 G：defer 模式下这 2s 有界 join 也挪到 reaper 线程（会话保存已在
        # 上方同步完成，顺序由 reaper 串行保证）。
        if defer_heavy_teardown:
            heavy_jobs.append(
                ("关闭会话写盘 worker",
                 lambda: self._close_instance_session_writer(instance)))
        else:
            self._close_instance_session_writer(instance)
        # 4.4a：本窗不再持有 slot 文件锁与碰撞 IPC 会话（退役层停用）。
        try:
            instance.broker_facade.shutdown()
        except Exception:
            logging.exception("退出这只：关闭 broker 失败")
        try:
            if win is not None:
                win.close()
        except Exception:
            logging.exception("退出这只：关闭窗口失败")
        if instance in self._instances:
            self._instances.remove(instance)
        self._refresh_tray_menu()
        if heavy_jobs:
            self._enqueue_heavy_teardown(instance, heavy_jobs)

    def _teardown_reaper_queue(self) -> "queue.Queue":
        """懒创建的进程级重资源回收队列（批 G）：单条 daemon 线程串行执行
        各窗退出时的 writer 关闭 / agent shutdown / 碰撞停止（都是有界但
        秒级的线程 join/wait），UI 线程因此不被阻塞。daemon：进程退出不强等
        （aboutToQuit 的进程级收口另有兜底），队列任务失败只记录不中断。"""
        q = getattr(self, "_teardown_queue", None)
        if q is None:
            q = queue.Queue()

            def reap() -> None:
                while True:
                    jobs = q.get()
                    for label, fn in jobs:
                        try:
                            fn()
                        except Exception:
                            logging.exception("退出子肥鱼：后台重回收失败 (%s)", label)

            threading.Thread(
                target=reap, daemon=True, name="pet-teardown-reaper").start()
            self._teardown_queue = q
        return q

    def _enqueue_heavy_teardown(self, instance: PetInstance, jobs: list) -> None:
        """把一窗的重回收任务排进 reaper（幂等：同一实例只排一次）。"""
        if getattr(instance, "_heavy_teardown_enqueued", False):
            return
        instance._heavy_teardown_enqueued = True
        self._teardown_reaper_queue().put(jobs)

    def _settings_window_releasable(self, instance: PetInstance) -> bool:
        """不可逆收口**之前**：把这张窗的进程内设置页过一遍关闭闸门。

        True = 可以继续收口（没有设置页，或它已经关掉）；False = 用户在失败框里选了
        「继续编辑」，调用方必须**整次取消**这次关闭请求，一个资源都不许动。

        为什么必须在收口之前做（ops P3-c）：设置页的关闭闸门在保存失败时会弹框，用户选
        「继续编辑」时 ``close()`` 被 ignore。等收口流程走到 ``_close_instance_subwindows``
        才发现就晚了——那时位置已存、预热已停、Agent 已关、会话写盘 worker 已关，父窗随即
        销毁，草稿窗成孤儿跟着消失（那里也**没法**在中途安全退出：留下的是半死的宠物）。

        只认 ``modern_settings_dialog``（有保存闸门的那一个）；ChatSettingsDialog 的
        closeEvent 没有闸门，仍由 ``_close_instance_subwindows`` 收。
        """
        dialog = getattr(instance, "modern_settings_dialog", None)
        if dialog is None:
            return True
        try:
            closed = dialog.close()
        except Exception:
            # C++ 对象已经没了（WA_DeleteOnClose 之后又被回收）：没有草稿可保护。
            logging.exception("退出前关闭进程内设置页失败")
            return True
        if isinstance(closed, bool):
            return closed
        # 老替身/桩：close() 没有返回值，退回可见性判据（隐藏的窗口不可能有用户草稿）。
        visible = getattr(dialog, "isVisible", None)
        return not (callable(visible) and bool(visible()))

    def _release_settings_windows(self) -> bool:
        """所有窗的进程内设置页过一遍关闭闸门；False = 调用方必须取消这次退出。"""
        for instance in list(getattr(self, "_instances", None) or ()):
            if not self._settings_window_releasable(instance):
                return False
        return True

    def request_app_quit(self) -> None:
        """托盘/恢复窗的「退出应用」：进程内设置页先过关闭闸门，用户要留在设置里就取消整次退出。

        只接**用户显式**的退出入口（托盘「退出」/「退出应用」、恢复窗按钮）。OS 强制会话
        结束与程序内其它 ``app.quit()`` 不走这里：``aboutToQuit`` → ``_on_session_end`` 那条
        路径保持既有语义——**不弹任何阻塞对话框**、照旧收口（见 docs/ISSUE-111-*）。
        """
        if not self._release_settings_windows():
            logging.info("退出应用：用户留在设置页里继续改，本次退出取消")
            return
        self.app.quit()

    def _close_instance_subwindows(self, instance: PetInstance) -> None:
        """批5.2 P1-5：关闭本窗拥有的设置窗并断开引用。

        设置页（``modern_settings_dialog``）正常情况下已经在收口**之前**由
        ``_settings_window_releasable`` 过完闸门并断开引用；这里再列一次是防御
        （那条闸门只覆盖用户显式退出入口，不覆盖程序内直接调用本方法的老路径）。
        """
        for attr in ('modern_settings_dialog',):
            dialog = getattr(instance, attr, None)
            if dialog is None:
                continue
            try:
                dialog.close()
            except Exception:
                logging.exception("退出这只：关闭子窗失败 (%s)", attr)
            try:
                # N-4：WA_DeleteOnClose 的对话框 close() 已调度销毁，再排
                # deleteLater 会对已删 C++ 对象抛 RuntimeError（噪音）。
                if not dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose):
                    QTimer.singleShot(0, dialog.deleteLater)
            except Exception:
                pass
            setattr(instance, attr, None)

    def _close_instance_session_writer(self, instance: PetInstance) -> None:
        """只关本窗（sessions-slot-N）的会话写盘 writer，不置永久屏障。

        R5/E2：多窗下绝不能 close_all_writers(permanent=True)——那会永久关掉
        其它窗的写盘 worker。此处只 flush + 关闭本窗根目录对应的 writer。
        """
        try:
            from .chat import session_store as _session_store
            root = _session_store.SessionStore(
                instance.config.dir, instance.config.instance_id).root
            # P1-7：运行期关窗 writer 的 timeout 降到 2s（不许冻 GUI 10s）；
            # 退出路径的 close_all_writers 仍保持默认 10s 不变。
            if not _session_store.close_writer_for_root(root, timeout=2.0):
                logging.warning("退出这只：会话写盘 worker 未干净关闭 (%s)", root)
        except Exception:
            logging.exception("退出这只：关闭会话写盘 worker 失败")

    def _build_empty_pet_tray(self) -> None:
        """零宠物的可见兜底：托盘（无托盘时另开恢复窗）。

        **必须留一条 WARN**：legacy 拓扑下走这条路径意味着"进程活着、但桌面上没有
        任何顶层窗口"，而调用方不区分它与正常启动——没有日志时用户侧只能报出
        「启动后什么都没有」，连是不是启动失败都无从自查（issue #286）。
        """
        logging.warning(
            "legacy: slot0 未活跃，没有捕获窗（活跃集合=%s，配置目录=%s）："
            "托盘/恢复窗的「生成 / 恢复 slot0」可重建",
            sorted(getattr(self, "_active_pet_slots", None) or ()),
            getattr(self.instance.config, "dir", None))
        tray = self.tray
        if tray is None:
            tray = QSystemTrayIcon(self._tray_placeholder_icon())
            self.tray = tray
        menu = QMenu()
        menu.addAction("slot0 未活跃：没有捕获窗").setEnabled(False)
        menu.addAction("slot0 设置", self.instance.open_modern_settings)
        menu.addAction("退出应用", self.request_app_quit)
        self._install_tray_menu(menu, [menu])
        tray.setContextMenu(menu)
        # 托盘提示同样说实话：默认的通用 tooltip 会让"桌面上什么都没有"看起来像
        # 悬停没反应，而不是"这只宠物当前没有捕获窗"。
        tray.setToolTip("dsh-pet：没有可显示的桌宠（slot0 未活跃）")
        tray.show()
        if not QSystemTrayIcon.isSystemTrayAvailable():
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton

            recovery = getattr(self, "_pet_recovery_window", None)
            if recovery is None:
                recovery = QWidget()
                recovery.setWindowTitle("桌宠恢复")
                layout = QVBoxLayout(recovery)
                for label, callback in (("slot0 设置", self.instance.open_modern_settings),
                                        ("退出应用", self.request_app_quit)):
                    button = QPushButton(label)
                    button.clicked.connect(callback)
                    layout.addWidget(button)
                self._pet_recovery_window = recovery
            recovery.show()

    def _refresh_tray_menu(self) -> None:
        """重建单托盘的菜单，逐窗列出「显示/隐藏」「退出这只」（批5.2 spike 聚合）。

        多窗时不新建托盘，只复用主窗托盘并刷新菜单；聚合美化留到 5.2a。
        """
        if self.tray is None:
            return
        primary = self._instances[0] if self._instances else None
        win = primary.win if primary is not None else None
        if win is None:
            return
        self._build_tray(win, tray=self.tray)

    def _toggle_primary_pet_visible(self) -> None:
        """双击托盘图标：切换主窗（instances[0]）可见性（按当前主窗）。"""
        primary = self._instances[0] if self._instances else None
        win = primary.win if primary is not None else None
        if win is None:
            return
        if win.isVisible():
            win.hide()
        else:
            win.show()

    def _install_macos_dock_menu(self) -> QMenu | None:
        """Install the native Dock context menu as an independent recovery path."""
        if sys.platform != "darwin":
            self.dock_menu = None
            return None
        menu = QMenu()

        def show_pet() -> None:
            if self.instance is None:
                return
            win = self.instance.win
            if win is None:
                return
            win.show()
            win.raise_()

        # N-2：Dock 菜单只装一次，动作必须动态解析当前主窗实例——
        # 主窗经「退出这只」退掉并提升新主窗后，绑旧实例会把死窗复活。
        menu.addAction("显示桌宠", show_pet)
        menu.addAction("桌宠设置", lambda: self.instance is not None and self.instance.open_modern_settings())
        menu.addSeparator()
        quit_callback = getattr(self.app, "quit", None)
        if callable(quit_callback):
            menu.addAction("退出", quit_callback)
        install_dock_menu = getattr(menu, "setAsDockMenu", None)
        dock_menu_installed = callable(install_dock_menu)
        if dock_menu_installed:
            install_dock_menu()
        menu.setProperty("dockMenuInstalled", dock_menu_installed)
        self.dock_menu = menu
        return menu

    def _toggle_flag(self, key: str, sync) -> None:
        """布尔开关的统一实现：翻转配置 → 落盘 → 同步服务启停（读旧值取反，
        再调对应的 `_sync_*_service`）。
        """
        self.config.set(key, not bool(self.config.get(key, False)))
        self.config.save()
        sync()

    def trigger_festival_now(self) -> None:
        """手动提醒「今日节日」：设置页「立即试听」与菜单编排加回的「今日节日」共用（该菜单项默认隐藏）。

        **无视总开关**，服务懒创建；当天没有节日/节气时给出明确文案，不做静默无反应。
        """
        service = self._ensure_festival_service()
        service.remind_now()

    def toggle_festival_reminder(self) -> None:
        """「启用/关闭节日提醒」开关（默认隐藏、菜单编辑器可加回）：翻转配置并同步服务启停。"""
        self._toggle_flag("festival_reminder_enabled", self._sync_festival_service)

    def system_notify(self, title: str, message: str, *, on_click=None, duration_ms: int = 5000) -> None:
        """Show a bottom-right desktop notification (self-drawn, tray-independent)."""
        self._prune_toasts()
        toast = DesktopNotification(
            str(title),
            str(message),
            on_click=on_click,
            duration_ms=int(duration_ms),
        )
        self._toast_windows.append(toast)
        toast.destroyed.connect(lambda _obj=None: self._prune_toasts())
        toast.show()
        position_stack(self._toast_windows)

    def _prune_toasts(self) -> None:
        self._toast_windows = [
            w for w in self._toast_windows
            if not (hasattr(w, "is_closed") and w.is_closed())
        ]
        position_stack(self._toast_windows)

    def _tray_placeholder_icon(self) -> QIcon:
        """首帧还没解码时的托盘占位图标：复用既有矢量图标语言，不用新素材。

        刻意不把桌宠窗口传进去取主题色——_build_tray 的调用方可能是非 QWidget
        的替身窗口（测试），而托盘观感本来就该跟窗口 QSS 无关。
        """
        return vector_menu_icon(QWidget(), "pet", 64)

    def _build_tray(self, win: PetWindow, tray: QSystemTrayIcon | None = None) -> QSystemTrayIcon:
        # 批5.2：可复用已有托盘（_refresh_tray_menu 传 self.tray），避免多窗各自
        # 建托盘图标；新建时绑定双击切换，复用时不重复连接（activated 只接一次）。
        if tray is None:
            icon = QIcon(win.icon_pixmap())
            pending = icon.isNull()
            if pending:
                # 首帧还没解码时 icon_pixmap() 是空图：直接拿去建托盘会得到一个
                # 没有图标的条目（用户反馈「托盘图标消失了」，且此后永不刷新）。
                # 先用占位图标顶上，首帧就绪后再换角色头像。
                icon = self._tray_placeholder_icon()
            tray = QSystemTrayIcon(icon)
            tray.activated.connect(
                lambda reason: self._toggle_primary_pet_visible()
                if reason == QSystemTrayIcon.ActivationReason.DoubleClick
                else None
            )
            if pending:
                ready = getattr(win, "frame_ready", None)
                if ready is not None:
                    ready.connect(lambda: tray.setIcon(QIcon(win.icon_pixmap())))

        def toggle_visible() -> None:
            if win.isVisible():
                win.hide()
            else:
                win.show()

        menu = QMenu()
        # F5：本 build 创建的全部 QMenu（含子菜单）先收集起来，安装时由
        # _install_tray_menu 显式接管所有权（进程侧强引用保活 + 旧菜单
        # 在新菜单接管后才释放），防止 wrapper 被回收导致菜单/子菜单被误判删除。
        tray_submenus: list[QMenu] = [menu]

        def track_menu(child: QMenu) -> QMenu:
            tray_submenus.append(child)
            return child

        # 气泡是置顶 Tool 窗口（层级高于原生菜单 popup），托盘菜单弹出前
        # 先隐藏气泡，避免气泡盖住菜单
        menu.aboutToShow.connect(lambda: win.hide_speech_bubble())

        def add_tray_toggle(target: QMenu, label: str, checked, apply):
            """可勾选托盘条目：勾选态照旧即时翻转，副作用延到菜单关闭后。

            ``add_tray_action`` 的回调在菜单关闭后执行，此时 ``isChecked()`` 已是
            用户点出来的最终值——故 apply 收勾选态，而不是在连接时把它绑死。
            勾选态的接线保持原样（``setCheckable`` + 初始 ``setChecked`` + 弹出前
            ``sync_tray_checks`` 同步）；旧接线挂 ``toggled`` 连副作用，弹出前的那次
            程序化 ``setChecked`` 也会把它触发一遍（开一次菜单就把配置/系统登录项
            重写一遍），挂 ``triggered`` 没有这个副作用。
            """
            action = add_tray_action(target, label, lambda: apply(bool(action.isChecked())))
            action.setCheckable(True)
            action.setChecked(bool(checked))
            return action

        # 本段全部条目都会动窗口面（显示/激活桌宠窗、重建角色窗面）或冒泡/系统
        # 登录项：托盘菜单是原生弹出（macOS 上是 NSMenu 跟踪会话），会话中做这些
        # 会被 AppKit 抑制（首次点击无反应，issue #4 家族），故一律走
        # add_tray_action——菜单先关，回调延到菜单真的不在之后再执行。
        add_tray_action(menu, '显示 / 隐藏', toggle_visible)
        add_tray_action(menu, '回到右下角', lambda: win.go_default_corner())

        add_tray_action(menu, '桌宠设置', self.instance.open_modern_settings)

        mouse_through = add_tray_toggle(
            menu, '鼠标穿透', bool(self.config.get('mouse_through', False)),
            win.set_mouse_through)

        menu.addSeparator()

        auto = add_tray_toggle(
            menu, '开机自启', autostart_mod.is_enabled(),
            lambda enabled: self.instance._set_autostart(enabled, win))

        def sync_tray_checks() -> None:
            # 设置对话框/右键菜单里改过的开关，弹出托盘菜单前同步复选状态
            #（托盘菜单在 _build_tray 时一次性构建，不复用则不刷新会过期）。
            # 只改看相、不触发副作用：副作用挂 triggered，程序化 setChecked 不发它。
            mouse_through.setChecked(bool(self.config.get('mouse_through', False)))
            auto.setChecked(autostart_mod.is_enabled())

        menu.aboutToShow.connect(sync_tray_checks)

        menu.addSeparator()
        menu.addAction('DeepSeek 余额', lambda: self.show_balance(win))

        menu.addAction('退出', self.request_app_quit)

        tray.setContextMenu(menu)
        tray.setToolTip('dsh-pet 独立桌宠')
        tray.show()
        # F5：菜单已由新菜单接管后，显式记录所有权并释放被替换的旧菜单
        #（owner 生命周期：强引用保活到替换，旧菜单延迟销毁防泄漏）。
        self._install_tray_menu(menu, tray_submenus)
        return tray

    def _install_tray_menu(self, menu: QMenu, submenus: list[QMenu]) -> None:
        """显式接管托盘上下文菜单所有权（F5：owner 与替换/销毁顺序）。

        旧菜单必须先等新菜单 ``tray.setContextMenu(menu)`` 接管完成才释放：
        先 ``deleteLater`` 旧菜单、再记录新菜单的强引用集合，保证任何时刻
        托盘引用的菜单都有一份进程侧 Python 引用（PySide6 wrapper 不被回收），
        且被替换的旧菜单经事件循环延迟销毁，不会永久泄漏。

        除菜单本体外，还必须保活每个菜单的 QAction wrapper：子菜单的 menuAction
        挂在父菜单的 actions 列表里；这些 QAction wrapper 一旦被 GC 终结，对应
        QMenu 的 wrapper 即使仍被强引用也会被 PySide6 连带标记为已删除（读取
        sub.actions() 抛 Internal C++ object already deleted）。因此这里一并
        快照保活全部菜单的 actions，外部临时持有/丢弃 actions 列表不再造成失效。
        """
        old = self._tray_menu
        if old is not None:
            old.deleteLater()
        self._tray_menu = menu
        self._tray_submenus = list(submenus)
        snapshot: list = []
        for m in (menu, *submenus):
            try:
                snapshot.extend(m.actions())
            except RuntimeError:
                # 菜单刚被接管，正常不会走到；防御性跳过避免拖垮托盘刷新
                continue
        self._tray_actions = snapshot


def _mac_set_dock_icon_visible(visible: bool) -> None:
    """Switch the macOS application policy without restarting the pet.

    The speech bubble itself owns the non-activating window flags; application
    activation policy must not be used as a focus workaround because Accessory
    Regular (0) displays a Dock item; Accessory (1) keeps the application out
    of the Dock. Pet tool windows own their independent visibility/focus flags.
    """
    if sys.platform != 'darwin':
        return
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc') or '/usr/lib/libobjc.A.dylib')
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.objc_getClass.restype = ctypes.c_void_p
        msg = objc.objc_msgSend
        msg.restype = ctypes.c_void_p
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        shared = msg(
            objc.objc_getClass(b'NSApplication'),
            objc.sel_registerName(b'sharedApplication'),
        )
        # NSApplicationActivationPolicyRegular = 0; Accessory = 1
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        msg(shared, objc.sel_registerName(b'setActivationPolicy:'), 0 if visible else 1)
    except Exception:
        pass


def _default_xcb_platform_on_wayland() -> None:
    """Linux Wayland 会话下把 Qt 平台插件默认设为 xcb（XWayland）。

    Wayland 协议不允许客户端自行移动顶层窗口，桌宠拖动依赖的
    QWidget.move() 会被合成器静默忽略（表现为无法拖动）；透明无边框
    窗口在原生 wayland 插件下还存在重绘残留（拖影）。须在创建
    QApplication 之前调用。用户显式设置 QT_QPA_PLATFORM 时尊重其选择。
    """
    if not sys.platform.startswith("linux"):
        return
    if "QT_QPA_PLATFORM" in os.environ:
        return
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def _configure_linux_fcitx_input_method() -> None:
    """为 PySide6 冻结版选择与内置 Qt ABI 兼容的 Fcitx 输入法前端。"""
    # Linux 成品随包携带按 PySide6 Qt ABI 编译的 Fcitx 插件；未指定时默认选中 fcitx 上下文。
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("XMODIFIERS", "").strip() != "@im=fcitx":
        return
    if not os.environ.get("QT_IM_MODULE", "").strip():
        os.environ["QT_IM_MODULE"] = "fcitx"


# Historical public name retained for integrations and older tests.
PetApp = AppShell


def main(argv: list[str] | None = None, enable_chat: bool = True) -> int:
    # ``enable_chat`` 只为旧打包入口（packaging/pet_entry_no_chat.py）保留形参，
    # AI 对话 UI 已整体移除，两个入口行为一致。
    _ = enable_chat
    _default_xcb_platform_on_wayland()
    # 必须在 QApplication 构造前设置，Qt 才会按随包 Fcitx 插件创建输入法上下文。
    _configure_linux_fcitx_input_method()
    argv = list(argv if argv is not None else sys.argv)
    preferred_slot = None

    if "--slot" in argv:
        index = argv.index("--slot")
        if index + 1 < len(argv):
            try:
                preferred_slot = int(argv[index + 1])
                if preferred_slot < 0 or preferred_slot > 128:
                    logging.error("无效的 --slot 参数 (必须在 0~128 范围内): %s", argv[index + 1])
                    return 1
            except ValueError:
                logging.error("无效的 --slot 参数: %s", argv[index + 1])
                return 1
        else:
            logging.error("缺少 --slot 参数值")
            return 1

    app = QApplication(argv)
    app.setApplicationName(APP_DIR_NAME)
    app.setQuitOnLastWindowClosed(False)
    # 图片解码上限（像素级别的一处设定）：Qt 默认 256 MB/张（本机 Qt 6.11.2 实测），
    # 用户给的超大图会**直接读不出来**而不是慢一点——聊天附件预览、设置页头像、
    # 趣味图片弹窗都吃这条上限。踩点放在这里而不是各调用点：它是静态设置，
    # 一处设定覆盖全进程（与本文件里其它 Qt 全局设定同一位置纪律）。
    from .qt_image_limits import apply_image_allocation_limit
    apply_image_allocation_limit()

    # 确定配置根目录
    config_dir = _default_base() / APP_DIR_NAME

    # D4（PHASE4_DESIGN §4）桌宠单实例进程门：**先于** slot 竞争。两个拓扑都抢
    # （T4 Phase A）：overlay 双开 = 两个进程各自恢复全部 sprite、位置回写互踩；
    # 捕获模式的 legacy 单窗拓扑同样是完整实例（建窗、存位置、落盘配置），双开
    # 与「重启时多只桌宠先收拢为主宠物」的单窗口径冲突。第二实例必须在产生任何
    # 配置目录副作用（抢 slot-1、落种 config-slot-N.json）之前退场。
    overlay_gate = overlay_gate_mod.acquire_overlay_instance_gate(config_dir)
    if not overlay_gate.acquired:
        # 双击桌面宠物场景：不弹窗、不阻塞，只留痕 + 退出。退出码对齐
        # pet/__main__.py 的 settings.lock 惯例（「已有实例，本次退出」= 0），
        # 免得外壳把"第二实例"当启动失败报错。
        logging.warning(
            "已有实例在运行（门 %s，持有者 pid=%s）：本次启动退出",
            overlay_gate.path, overlay_gate.holder_pid(),
        )
        return overlay_gate_mod.DUPLICATE_EXIT_CODE

    # 4.4a 停用多进程多宠退役层的**槽位文件锁**：main() 不再抢 slot-N.lock
    #（原语义 = 跨进程竞争「我是第几只」，退役层删除后不复存在）。`--slot`
    # 兼容解析保留（T5）：旧快捷方式/自启项仍按它选择 config-slot-N.json
    # 身份；缺省或 D4 门保证的单实例即主身份（slot 0）。
    slot_id = preferred_slot if preferred_slot is not None else 0

    try:
        instance_id = ""
        os.environ["DSH_PET_INSTANCE"] = ""
        slot_manager_mod.migrate_legacy_spawns(config_dir)
        config = Config(instance_id="")
        _mac_set_dock_icon_visible(bool(config.get("show_dock_icon", True)))
        _setup_logging(config)

        logging.info("dsh-pet-standalone 启动 (slot: %s, instance: %s)", slot_id, instance_id)
        _cleanup_stale_runtime_dirs()
        stale_removed = autostart_mod.cleanup_stale_entries()
        if stale_removed:
            logging.info("已清理 %d 个指向不存在路径的开机自启项", stale_removed)

        controller = AppShell(app, config, slot_id=slot_id,
                              spawn_offset=_read_spawn_offset_env(), overlay_gate=overlay_gate)
        try:
            controller.start()
        except Exception as exc:
            logging.exception("启动失败")
            _show_startup_error("dsh-pet-standalone", str(exc))
            return 1

        logging.info("进入事件循环")
        return app.exec()
    finally:
        # D4：正常退出（app.exec() 返回前 aboutToQuit 已跑完，各窗位置已落盘）
        # 才释放进程门——比 _on_about_to_quit 内更晚，避免"本地还在收尾、第二
        # 实例已能起来"的位置回写竞态。会话结束路径另见 _on_session_end。
        if overlay_gate is not None:
            try:
                overlay_gate.release()
            except Exception:
                logging.exception("释放桌宠单实例进程门失败")


if __name__ == '__main__':
    sys.exit(main())
