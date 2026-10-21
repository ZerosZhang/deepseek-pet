# -*- coding: utf-8 -*-
"""python -m pet 入口。"""

import sys


def _exec_settings(app, config, *, initial_page: str = "") -> int:
    """独立设置进程主体：锁 + 独立对话框 + 事件循环。

    单独拆一层是为了让测试能注入最小 QApplication/临时 Config，不必真的跑
    一个阻塞的 app.exec() 或用真实用户配置目录。
    """
    import logging

    from PySide6.QtCore import QLockFile

    # 单实例：设置进程自己持有 settings.lock 直到退出（QLockFile 在解锁/析构时
    # 删除锁文件；崩溃残留的锁由 QLockFile 按 pid 存活判定为陈旧后接管）。
    # 主进程经同一把锁判断"是否已有设置页开着"，已持有则不再拉起。
    lock = QLockFile(str(config.dir / "settings.lock"))
    lock.setStaleLockTime(30000)
    if not lock.tryLock(0):
        logging.getLogger(__name__).info("已有设置进程持有 settings.lock，本次退出")
        return 0
    from .modern_settings_dialog import ModernSettingsDialog

    # parent=None + standalone=True：没有桌宠窗口可依附，试听/避让由
    # pet.settings_standalone 提供进程内最小宿主。
    dialog_kwargs = {"standalone": True}
    if initial_page:
        dialog_kwargs["initial_page"] = initial_page
    dialog = ModernSettingsDialog(config, parent=None, **dialog_kwargs)
    dialog.finished.connect(lambda _result: app.quit())
    dialog.show()
    try:
        return app.exec()
    finally:
        lock.unlock()


def _settings_instance_id(argv) -> str:
    """从 --settings 附加参数里取 instance_id（缺省空 = 主宠，按 slot0 分流，#271）。

    进程内多窗时第二窗的 config 是
    config-slot-N.json，而进程级 DSH_PET_INSTANCE 仍是主窗的；主进程会显式
    追加 --instance slot-N 把子进程指到正确的那份配置。
    """
    try:
        index = argv.index("--instance")
    except ValueError:
        return ""
    if index + 1 >= len(argv):
        return ""
    return str(argv[index + 1] or "").strip()


def _settings_page(argv) -> str:
    try:
        index = argv.index("--settings-page")
    except ValueError:
        return ""
    if index + 1 >= len(argv):
        return ""
    return str(argv[index + 1] or "").strip()


def _run_settings(config=None) -> int:
    """--settings：设置页独立进程（不导入 pet.app）。

    参照 --uninstall-cleanup 的免 GUI 分流范式，但设置页自身要 GUI：只拉起最小
    QApplication + Config + ModernSettingsDialog。**严禁**导入 pet.app——那会连带
    载入素材库/ffmpeg/托盘，独立进程省内存的前提（也省启动时间）就没了。
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    # 设置进程只有设置窗一个窗口：关窗即退出，OS 立刻回收全部内存
    #（进程内设置页首开留下的字体/样式/模块高水位没有卸载 API，只能靠进程退出）。
    app.setQuitOnLastWindowClosed(True)
    # 图片解码上限：设置页要用 QImageReader 读用户挑的头像/图片文件，超大图在
    # Qt 默认上限（256 MB/张，本机实测）下读不出来。与 pet/app.py::main 同一处设定
    # （这里的 QApplication 是本进程自己建的，静态设置不跨进程继承）。
    from .qt_image_limits import apply_image_allocation_limit
    apply_image_allocation_limit()
    if config is None:
        from .config import Config

        # DSH_PET_INSTANCE 由主进程经环境继承下来：子肥鱼的设置进程编辑的是
        # 它自己的 config-slot-N.json，与主进程同一份文件；多窗场景由主进程
        # 追加 --instance 显式指明。
        config = Config(instance_id=_settings_instance_id(sys.argv))
    try:
        config.dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return _exec_settings(app, config, initial_page=_settings_page(sys.argv))


def _main() -> int:
    # 卸载清理走无 GUI 路径：不导入 pet.app（避免拉起 QApplication/事件循环），
    # 并与两个冻结入口共用 pet.uninstall_cleanup.main——逐步诊断输出、配置目录留痕、
    # 退出码语义只有那一处实现，入口侧不再自己复刻一份。
    if "--uninstall-cleanup" in sys.argv:
        from .uninstall_cleanup import main as uninstall_cleanup_main
        return uninstall_cleanup_main()
    # 设置页独立进程同样不导入 pet.app（模块集合是主进程的子集，见模块 docstring）。
    if "--settings" in sys.argv:
        return _run_settings()
    from .app import main as app_main
    return app_main()


if __name__ == "__main__":
    sys.exit(_main())
