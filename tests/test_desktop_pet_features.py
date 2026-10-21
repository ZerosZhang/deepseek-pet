from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _slot0_config(tmp_path):
    """生产形态的配置面：slot0 身份经 ``SlotRoutedConfig`` 分流。

    每宠键（自言自语族、气泡样式、尺寸…）的真值在 ``config-slot-0.json``：
    裸全局 ``Config.set/save`` 出闸时会过滤掉它们，改不动任何一只宠。
    """
    from pet.config import Config
    from pet.settings_slot_config import route_settings_config

    return route_settings_config(Config(base=tmp_path, instance_id="slot-0"))


def test_speech_bubble_never_accepts_focus():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    bubble = PetSpeechBubble()
    assert bubble.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert bubble.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert bubble.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    bubble.close()
    app.processEvents()


def test_self_talk_bubble_presets_have_distinct_visuals_and_safe_positions():
    from PySide6.QtCore import QRect, QSize

    from pet.speech_bubble import (
        BUBBLE_STYLE_PRESETS,
        bubble_rect_for_anchor,
    )

    assert list(BUBBLE_STYLE_PRESETS) == [
        "classic_top", "paper_left", "glass_right", "soft_blue_top", "breath_bubble",
    ]
    assert len({preset["background"] for preset in BUBBLE_STYLE_PRESETS.values()}) == 5
    assert {preset["placement"] for preset in BUBBLE_STYLE_PRESETS.values()} == {
        "top", "top_left", "top_right",
    }
    available = QRect(0, 0, 1440, 900)
    pet = QRect(620, 420, 220, 260)
    for preset in BUBBLE_STYLE_PRESETS.values():
        bubble = bubble_rect_for_anchor(pet, QSize(240, 92), available, preset["placement"])
        assert available.contains(bubble)
        assert not bubble.intersects(pet)


def test_breath_bubble_uses_organic_water_shape_and_detached_trailing_bubbles():
    import math

    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    bubble = PetSpeechBubble(style_id="breath_bubble")
    bubble.show_text("今天也要认真工作呀。", QRect(420, 460, 180, 240), 5000)
    app.processEvents()
    assert bubble._preset["shape"] == "breath_bubble"
    assert not bubble._main_bubble_path.isEmpty()
    assert len(bubble._breath_paths) == 2
    assert all(not path.isEmpty() for path in bubble._breath_paths)
    assert bubble._water_fill == "#d9f2fb"
    assert bubble._shadow_alpha == 0
    main = bubble._main_bubble_path.boundingRect()
    assert 1.17 <= main.width() / main.height() <= 1.27
    assert bubble._water_start_ratio <= 0.50
    assert bubble._highlight_width_ratios[0] <= 0.16
    assert bubble._highlight_width_ratios[1] <= 0.05

    def edge_distance(first, second):
        first_points = [first.pointAtPercent(index / 160) for index in range(161)]
        second_points = [second.pointAtPercent(index / 160) for index in range(161)]
        return min(
            math.hypot(left.x() - right.x(), left.y() - right.y())
            for left in first_points for right in second_points
        )

    first_gap = edge_distance(bubble._main_bubble_path, bubble._breath_paths[0])
    second_gap = edge_distance(bubble._breath_paths[0], bubble._breath_paths[1])
    assert 2.0 <= first_gap <= 7.0
    assert 2.0 <= second_gap <= 7.0
    assert abs(first_gap - second_gap) <= 2.0
    assert all(path.elementCount() >= 10 for path in bubble._breath_paths)
    bubble.close()
    app.processEvents()


def test_breath_bubble_size_tracks_the_visible_pet_without_dominating_it():
    from PySide6.QtCore import QRect, QSize
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import (
        PetSpeechBubble,
        breath_bubble_size_for_anchor,
        breath_bubble_size_for_scale,
    )

    app = QApplication.instance() or QApplication([])
    small_pet = QRect(420, 460, 180, 240)
    large_pet = QRect(420, 460, 360, 480)

    assert breath_bubble_size_for_anchor(small_pet) == QSize(168, 137)
    assert breath_bubble_size_for_anchor(large_pet) == QSize(216, 176)
    scale_sizes = [breath_bubble_size_for_scale(value) for value in (0.5, 0.72, 0.85, 1.0)]
    assert [size.width() for size in scale_sizes] == sorted({size.width() for size in scale_sizes})

    bubble = PetSpeechBubble(style_id="breath_bubble")
    bubble.show_text("今天也要认真工作呀。", small_pet, 5000)
    app.processEvents()
    assert bubble.size() == QSize(168, 137)
    assert bubble.width() <= small_pet.width()
    # offscreen QPA shifts windows on show(); assert the placement logic
    # directly so the visual gap contract (7px design) is platform-stable.
    bubble._place(small_pet)
    visible_bubble_bottom = bubble.y() + bubble._surface_path.boundingRect().bottom()
    visual_gap = small_pet.top() - visible_bubble_bottom
    assert 5 <= visual_gap <= 9
    visible_surface = bubble._surface_path.translated(bubble.x(), bubble.y())
    pet_path = bubble._surface_path.__class__()
    pet_path.addRect(small_pet)
    assert visible_surface.intersected(pet_path).isEmpty()
    assert 1.17 <= bubble._main_bubble_path.boundingRect().width() / bubble._main_bubble_path.boundingRect().height() <= 1.27
    bubble.close()
    app.processEvents()


def test_breath_bubble_reflows_on_pet_scale_change_and_summarizes_markdown():
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    pet = QRect(420, 460, 220, 260)
    bubble = PetSpeechBubble(style_id="breath_bubble")
    bubble.show_text(
        "## 小狐狸的星空故事\n森林边有一棵老树，树洞里住着一只小狐狸。"
        "每天傍晚它都会抬头看星星，并把看到的故事记在叶片上。"
        "它把叶片一片片夹进树洞深处的旧书里，等月亮升起来的时候，"
        "就坐在树根上给路过的旅人讲这些星星的故事，讲着讲着自己也睡着了。" * 2,
        pet,
        5000,
        pet_scale=0.5,
    )
    app.processEvents()
    small_width = bubble.width()
    assert "##" not in bubble.label.text()
    assert bubble.label.text().count("\n") <= 5  # 长文本放宽到 6 行
    assert bubble.label.text().endswith("…")  # 超出 6 行仍省略收尾

    bubble.reflow(pet, pet_scale=1.0)
    app.processEvents()
    assert bubble.width() > small_width
    assert bubble.label.pixmap().isNull()
    bubble.close()
    app.processEvents()


def test_breath_bubble_keeps_its_shape_but_adapts_to_text_and_image_content(tmp_path):
    from PIL import Image
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    pet = QRect(420, 460, 220, 260)
    bubble = PetSpeechBubble(style_id="breath_bubble")
    bubble.show_text("好女孩……", pet, 5000, pet_scale=0.72)
    app.processEvents()
    short_size = bubble.size()

    bubble.show_text(
        "今天也要认真工作，完成任务后一起去看看星星和蓝色的大海吧。",
        pet, 5000, pet_scale=0.72,
    )
    app.processEvents()
    assert bubble.width() > short_size.width()
    assert abs(bubble.width() / bubble.height() - 240 / 195) < 0.03

    image = tmp_path / "square.png"
    Image.new("RGB", (240, 240), "white").save(image)
    assert bubble.show_image(image, pet, 5000, pet_scale=0.72)
    app.processEvents()
    assert bubble.width() > short_size.width()
    assert bubble._breath_image_rect.height() >= 104
    assert abs(bubble.width() / bubble.height() - 240 / 195) < 0.03
    bubble.close()
    app.processEvents()


def test_breath_bubble_image_is_clipped_and_painted_below_water_details(tmp_path):
    from PIL import Image
    from PySide6.QtCore import QPointF, QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    image = tmp_path / "square-content.png"
    Image.new("RGB", (300, 300), "red").save(image)
    bubble = PetSpeechBubble(style_id="breath_bubble")
    assert bubble.show_image(
        image, QRect(420, 460, 220, 260), 5000, pet_scale=0.72
    )
    app.processEvents()

    # A child QLabel paints after the parent and used to cover the water,
    # outline and highlight with an un-clipped rectangular image.
    assert bubble.label.pixmap().isNull()
    assert not bubble._breath_image_rect.isEmpty()
    assert not bubble._breath_image_clip_path.isEmpty()
    assert bubble._breath_image_clip_path.contains(
        QPointF(bubble._breath_image_rect.center())
    )
    assert not bubble._breath_image_clip_path.contains(
        QPointF(bubble._breath_image_rect.topLeft())
    )
    bubble.close()
    app.processEvents()


def test_breath_image_position_uses_actual_window_size_not_hidden_label_hint(tmp_path):
    from PIL import Image
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble, bubble_rect_for_anchor

    app = QApplication.instance() or QApplication([])
    image = tmp_path / "position.png"
    Image.new("RGB", (300, 300), "blue").save(image)
    anchor = QRect(420, 460, 220, 260)
    bubble = PetSpeechBubble(style_id="breath_bubble")
    assert bubble.show_image(image, anchor, 5000, pet_scale=0.72)
    app.processEvents()
    available = app.primaryScreen().availableGeometry()
    expected = bubble_rect_for_anchor(
        anchor, bubble.size(), available, bubble._preset["placement"]
    )
    assert bubble.sizeHint() != bubble.size()
    assert bubble.x() == expected.x()
    bubble.close()
    app.processEvents()


def test_standard_bubble_images_keep_retina_device_pixel_density(tmp_path, monkeypatch):
    from PIL import Image
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    image = tmp_path / "retina.png"
    Image.new("RGB", (600, 600), "blue").save(image)
    bubble = PetSpeechBubble(style_id="paper_left")
    # 打在**类**上，不打在实例上：monkeypatch 对实例属性记下的旧值是本类的
    # bound method，undo() 会把它写回 ``bubble.__dict__``，形成
    # ``bubble -> __dict__ -> bound method -> bubble`` 的自环 ⇒ 引用计数永远归不了
    # 零，Python 包装只能等周期性 GC 回收，C++ 侧 QWidget 也就落到任意时点销毁
    # （实测落在别的用例的 import 里，属于 conftest 记的「Garbage-collecting /
    # no Python frame」原生崩溃家族；本用例的顶层窗口清扫因此看不到它，收口失效）。
    # ``devicePixelRatioF`` 来自 QWidget、不在 ``PetSpeechBubble.__dict__`` 里，
    # 类级补丁的旧值是 NOTSET，undo() 走 delattr，不留自环。
    monkeypatch.setattr(PetSpeechBubble, "devicePixelRatioF", lambda self: 2.0)
    assert bubble.show_image(image, QRect(420, 460, 220, 260), 5000)
    app.processEvents()
    bubble.grab()
    assert bubble.label.pixmap().isNull()
    assert bubble._source_pixmap.width() >= bubble.label.width() * 2
    assert bubble._standard_image_rect.toRect() == bubble.label.geometry()
    bubble.close()
    app.processEvents()
    # 类级补丁不应给实例留下方法覆盖，避免 undo 恢复 bound method 形成自环。
    assert "devicePixelRatioF" not in bubble.__dict__


def test_all_bubble_presets_use_soft_layered_shadows():
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import BUBBLE_STYLE_PRESETS, PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    for style_id in BUBBLE_STYLE_PRESETS:
        bubble = PetSpeechBubble(style_id=style_id)
        bubble.show_text("阴影测试", QRect(420, 460, 220, 260), 5000)
        app.processEvents()
        assert len(bubble._shadow_layers) >= 3
        widths = [layer[0] for layer in bubble._shadow_layers]
        alphas = [layer[1] for layer in bubble._shadow_layers]
        assert widths == sorted(widths, reverse=True)
        assert alphas == sorted(alphas)
        assert alphas[0] > 0
        bubble.close()
    app.processEvents()


def test_pet_scale_change_reflows_visible_bubble_after_rebuilding_mask():
    from PySide6.QtCore import QRect

    from pet.window import PetWindow

    events = []

    class Bubble:
        def isVisible(self):
            return True

        def reflow(self, anchor, *, pet_scale):
            events.append(("reflow", anchor, pet_scale))

    class FakePet:
        scale = 0.5
        _h = 100
        _speech_bubble = Bubble()
        _collision_bounds_cache = {}

        def geometry(self):
            return QRect(20, 30, 100, self._h)

        def x(self):
            return 20

        def _apply_scale(self):
            self._h = 200
            events.append("scale")

        def move(self, x, y):
            events.append(("move", x, y))

        def _rebuild_frame(self):
            events.append("rebuild")

        def visible_content_rect(self):
            assert events[-1] == "rebuild"
            return QRect(25, 35, 160, 210)

        def update(self):
            events.append("update")

        def _save_position(self):
            events.append("save")

    pet = FakePet()
    PetWindow.change_scale(pet, 1.0)
    assert events[2] == "rebuild"
    assert events[3] == ("reflow", QRect(25, 35, 160, 210), 1.0)


def test_change_scale_with_destroyed_bubble_is_noop():
    """N7：closeEvent 置 _speech_bubble=None 后，迟到的 change_scale 不得 AttributeError。"""
    from PySide6.QtCore import QRect

    from pet.window import PetWindow

    class FakePet:
        scale = 1.0
        _h = 100
        _speech_bubble = None
        _collision_bounds_cache = {}

        def geometry(self):
            return QRect(0, 0, 100, self._h)

        def x(self):
            return 0

        def _apply_scale(self):
            self._h = 200

        def move(self, x, y):
            pass

        def _rebuild_frame(self):
            pass

        def visible_content_rect(self):
            return QRect(0, 0, 100, 200)

        def update(self):
            pass

        def _save_position(self):
            pass

    PetWindow.change_scale(FakePet(), 1.5)


def test_self_talk_images_and_duration_are_normalized_and_scheduled_after_hide(tmp_path, monkeypatch):
    from PIL import Image

    from pet.config import Config, DEFAULT_SELF_TALK_DURATION_SECONDS
    from pet.speech_bubble import list_self_talk_images
    from pet.window import PetWindow

    image_dir = tmp_path / "talk-images"
    image_dir.mkdir()
    Image.new("RGB", (20, 10), "blue").save(image_dir / "one.png")
    (image_dir / "ignore.txt").write_text("not an image", encoding="utf-8")

    config = _slot0_config(tmp_path)
    assert config.get("self_talk_duration_seconds") == DEFAULT_SELF_TALK_DURATION_SECONDS
    config.set("self_talk_duration_seconds", 7.5)
    config.set("self_talk_image_dir", str(image_dir))
    assert config.save() is True
    loaded = _slot0_config(tmp_path)
    assert loaded.get("self_talk_duration_seconds") == 7.5
    assert loaded.get("self_talk_image_dir") == str(image_dir)
    assert list_self_talk_images(str(image_dir)) == [image_dir / "one.png"]

    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    bubble = PetSpeechBubble(style_id="breath_bubble")
    assert bubble.show_image(
        image_dir / "one.png", QRect(420, 460, 220, 260),
        5000, pet_scale=0.72,
    )
    app.processEvents()
    assert not bubble._source_pixmap.isNull()
    assert not bubble._breath_image_rect.isEmpty()


def test_self_talk_image_scale_config_and_bubble_size(tmp_path):
    """气泡配图尺寸：配置 50~300 钳位 + 气泡按 image_scale 放大（双气泡形态都验证）。"""
    from PIL import Image

    from pet.config import Config

    image_dir = tmp_path / "talk-images"
    image_dir.mkdir()
    Image.new("RGB", (20, 10), "blue").save(image_dir / "one.png")

    config = _slot0_config(tmp_path)
    assert config.get("self_talk_image_scale") == 100  # 默认
    config.set("self_talk_image_scale", 250)
    assert config.save() is True
    loaded = _slot0_config(tmp_path)
    assert loaded.get("self_talk_image_scale") == 250
    # 钳位：越界/非数值
    config.set("self_talk_image_scale", 9999)
    assert config.save() is True
    assert _slot0_config(tmp_path).get("self_talk_image_scale") == 300
    config.set("self_talk_image_scale", "abc")
    assert config.save() is True
    assert _slot0_config(tmp_path).get("self_talk_image_scale") == 100

    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    anchor = QRect(420, 460, 220, 260)
    normal = PetSpeechBubble()
    big = PetSpeechBubble()
    assert normal.show_image(image_dir / "one.png", anchor, 5000, image_scale=1.0)
    assert big.show_image(image_dir / "one.png", anchor, 5000, image_scale=2.5)
    assert big.label.width() > normal.label.width() * 2
    # 呼吸气泡形态同样吃缩放
    breath_normal = PetSpeechBubble(style_id="breath_bubble")
    breath_big = PetSpeechBubble(style_id="breath_bubble")
    assert breath_normal.show_image(image_dir / "one.png", anchor, 5000, pet_scale=0.72, image_scale=1.0)
    assert breath_big.show_image(image_dir / "one.png", anchor, 5000, pet_scale=0.72, image_scale=2.5)
    assert breath_big.width() > breath_normal.width()
    # 超界缩放被弹窗侧钳住（双保险）
    huge = PetSpeechBubble()
    capped = PetSpeechBubble()
    assert huge.show_image(image_dir / "one.png", anchor, 5000, image_scale=99.0)
    assert capped.show_image(image_dir / "one.png", anchor, 5000, image_scale=3.0)
    assert huge._image_scale == 3.0
    assert huge.label.width() == capped.label.width()
    app.processEvents()
    for w in (normal, big, breath_normal, breath_big, huge, capped):
        w.close()
    app.processEvents()




def test_speech_bubble_tail_is_one_surface_and_shadow_has_no_graphics_effect():
    from PySide6.QtCore import QPointF, QRect
    from PySide6.QtWidgets import QApplication

    from pet.speech_bubble import PetSpeechBubble

    app = QApplication.instance() or QApplication([])
    bubble = PetSpeechBubble(style_id="classic_top")
    bubble.show_text("今天也要认真工作呀。", QRect(320, 420, 180, 240), 5000)
    app.processEvents()
    assert bubble.graphicsEffect() is None
    assert not bubble._surface_path.isEmpty()
    base_center = QPointF(
        (bubble._tail_base[0].x() + bubble._tail_base[1].x()) / 2,
        (bubble._tail_base[0].y() + bubble._tail_base[1].y()) / 2,
    )
    inside_tail = QPointF(
        bubble._tail_tip.x() * 0.8 + base_center.x() * 0.2,
        bubble._tail_tip.y() * 0.8 + base_center.y() * 0.2,
    )
    assert bubble._surface_path.contains(inside_tail)
    assert bubble._surface_path.contains(base_center)
    assert bubble._shadow_offset_y <= 2
    bubble.close()
    app.processEvents()


def test_self_talk_bubble_style_is_normalized_and_persisted(tmp_path):
    from pet.config import Config

    config = _slot0_config(tmp_path)
    assert config.get("self_talk_bubble_style") == "classic_top"
    config.set("self_talk_bubble_style", "glass_right")
    assert config.save() is True
    assert _slot0_config(tmp_path).get("self_talk_bubble_style") == "glass_right"
    config.set("self_talk_bubble_style", "unknown")
    # 脏值在**落盘后的读端**被归一（路由视图对未保存的草稿按原样回显，清洗发生在
    # 同源默认那条读规则上——唯一清洗实现仍是 Config 的每宠快照规范化）。
    assert config.save() is True
    assert _slot0_config(tmp_path).get("self_talk_bubble_style") == "classic_top"


def test_icon_composition_ignores_low_alpha_noise_and_fills_canvas():
    from PIL import Image, ImageDraw

    script = Path("scripts/make_icon.py")
    spec = importlib.util.spec_from_file_location("make_icon_for_test", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    source = Image.new("RGBA", (640, 360), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.rectangle((290, 120, 349, 239), fill=(40, 100, 180, 255))
    draw.point((1, 1), fill=(255, 255, 255, 1))

    icon = module.prepare_icon_image(source, side=256)
    bbox = icon.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    assert icon.size == (256, 256)
    assert bbox is not None
    assert max(bbox[2] - bbox[0], bbox[3] - bbox[1]) >= 248










def test_pet_avatar_menu_icon_fills_native_slot_and_stays_centered(monkeypatch):
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication, QMenu, QStyle

    from pet.context_menus.icons import pet_avatar_menu_icon

    class FakePet:
        @staticmethod
        def icon_pixmap(size=64):
            # Reproduce a Retina source: physical dimensions are twice the
            # logical dimensions. The old painter path rendered this at 1/2 size.
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            from PySide6.QtGui import QPainter

            painter = QPainter(pixmap)
            painter.fillRect(QRect(size // 4, 0, size // 2, size), Qt.GlobalColor.blue)
            painter.end()
            pixmap.setDevicePixelRatio(2.0)
            return pixmap

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    native_size = menu.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, menu)
    icon = pet_avatar_menu_icon(menu, FakePet())
    pixmap = icon.pixmap(native_size, native_size)
    # Retina menu (dpr=2) yields physical 32px backing for the same 16 logical slot.
    dpr = pixmap.devicePixelRatio() or 1.0
    assert pixmap.width() / dpr == native_size
    assert pixmap.height() / dpr == native_size
    assert icon.availableSizes()[0].width() / dpr == native_size
    # Inspect actual non-transparent pixels, not merely the QImage canvas.
    points = [
        (x, y)
        for y in range(pixmap.height())
        for x in range(pixmap.width())
        if pixmap.toImage().pixelColor(x, y).alpha() > 0
    ]
    left, right = min(x for x, _ in points), max(x for x, _ in points)
    top, bottom = min(y for _, y in points), max(y for _, y in points)
    assert (bottom - top + 1) / dpr >= native_size * 0.8
    assert abs(((left + right) / 2.0) / dpr - ((native_size - 1) / 2.0)) <= 1.0
    menu.close()
    app.processEvents()








def test_context_menu_always_applies_the_modern_style():
    from PySide6.QtWidgets import QApplication, QMenu, QStyle, QWidget

    from pet.context_menu import populate_context_menu

    class Config:
        def get(self, key, default=None):
            return {
                "character": "shenshen",
                # 固定浅色主题，避免断言随系统深色模式翻转
                "context_menu_appearance": {"theme": "light"},
            }.get(key, default)

    class Pet:
        on_open_chat = on_open_chat_settings = None
        on_open_modern_settings = None
        on_spawn_pet = None
        idles = turns = moves = clicks = acts = []
        playback_speed = scale = 1.0
        drag_physics = no_move = False

        def __init__(self):
            self.cfg = Config()

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    populate_context_menu(menu, Pet())
    assert menu.objectName() == "modernContextMenu"
    # The modern menu follows the compact macOS project-menu reference: a
    # white hairline surface, small system text, outline icons and subtle rules
    # between semantic groups.
    assert "background-color: rgba(255, 255, 255, 240)" in menu.styleSheet()
    assert "border: none" in menu.styleSheet()
    hairline = menu.findChild(QWidget, "modernHairlineBorder")
    assert hairline is not None
    assert hairline.property("physicalPixelWidth") == 1
    assert "border-radius: 12px" in menu.styleSheet()
    assert "font-size: 13px" in menu.styleSheet()
    assert "icon-size: 18px" in menu.styleSheet()
    assert "background-color: #eeeeee" in menu.styleSheet()
    assert "min-height: 18px" in menu.styleSheet()
    assert "padding: 3px 29px 3px 13px" in menu.styleSheet()
    assert "margin-right: 10px" in menu.styleSheet()
    assert "QMenu::separator" in menu.styleSheet()
    separator_rule = menu.styleSheet().split("QMenu::separator", 1)[1]
    assert "height: 1px" in separator_rule
    assert "background: #e5e5e5" in separator_rule
    assert Path("pet/context_menus/menu_styles/common.py").is_file()
    assert Path("pet/context_menus/menu_styles/modern.py").is_file()
    assert menu.style().styleHint(QStyle.StyleHint.SH_Menu_SubMenuPopupDelay, None, menu) == 60
    assert menu.style().styleHint(QStyle.StyleHint.SH_Menu_SubMenuSloppyCloseTimeout, None, menu) == 120
    assert menu.style().styleHint(QStyle.StyleHint.SH_Menu_SubMenuSloppySelectOtherActions, None, menu) == 1
    assert menu.style().styleHint(QStyle.StyleHint.SH_Menu_SubMenuUniDirection, None, menu) == 0
    menu.close()
    app.processEvents()


def test_submenu_inherits_the_modern_style_from_its_parent():
    """子菜单样式继承：父菜单没打上 ``menuStyle`` 属性时也必须落现代样式。

    回归背景：``inherit_menu_style`` 原先按 ``menuStyle`` 分支，取不到属性时
    默认值指向已退役的旧版样式——任何"父菜单属性还没设上"的子菜单会静默掉
    样式，露出原生外观（旧版样式已删除，默认值只能指向现代）。
    """
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.menu_styles.common import inherit_menu_style

    app = QApplication.instance() or QApplication([])
    parent = QMenu()          # 刻意不设 menuStyle 属性（默认值路径）
    submenu = QMenu(parent)
    inherit_menu_style(parent, submenu)
    assert submenu.property("menuStyle") == "modern"
    assert submenu.objectName() == "modernContextMenu"
    assert submenu.styleSheet() != "", "子菜单必须套上现代样式（不能露原生外观）"
    parent.close()
    app.processEvents()


def test_modern_menu_icons_are_crisp_outline_glyphs(monkeypatch):
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.icons import vector_menu_icon
    from pet.context_menus.menu_styles.modern import apply_modern_menu_style

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    # 固定浅色主题：深色系统下菜单图标为浅灰（深色菜单设计），
    # 该断言验证的是浅色菜单的深色轮廓图标
    apply_modern_menu_style(menu, {"theme": "light"})
    names = ("chat", "play", "character", "speed", "spawn", "settings", "web", "exit")
    cache_keys = []
    for name in names:
        icon = vector_menu_icon(menu, name)
        pixmap = icon.pixmap(18, 18)
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        cache_keys.append(icon.cacheKey())
        opaque_pixels = 0
        dark_pixels = 0
        for y in range(image.height()):
            for x in range(image.width()):
                color = QColor(image.pixelColor(x, y))
                if color.alpha() > 24:
                    opaque_pixels += 1
                    if max(color.red(), color.green(), color.blue()) < 150:
                        dark_pixels += 1
        assert opaque_pixels >= 12
        assert dark_pixels >= 8
    assert len(set(cache_keys)) == len(names)
    menu.close()
    app.processEvents()


def test_modern_checked_action_is_painted_in_reserved_right_slot():
    from PySide6.QtWidgets import QApplication, QMenu, QWidget

    from pet.context_menus.menu_styles.modern import (
        apply_modern_menu_style,
        install_modern_check_indicators,
    )

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    apply_modern_menu_style(menu)
    action = menu.addAction("窗口置顶")
    action.setCheckable(True)
    action.setChecked(True)
    install_modern_check_indicators(menu)
    assert menu.property("paintChecksOnRight") is True
    assert menu.findChild(QWidget, "modernEnabledIndicator") is None
    assert menu.findChild(QWidget, "modernCheckLayer") is not None
    assert "padding:" in menu.styleSheet()
    action.setChecked(False)
    app.processEvents()
    assert action.isChecked() is False
    action.setChecked(True)
    app.processEvents()
    assert action.isChecked() is True
    menu.close()
    app.processEvents()




def test_macos_tool_window_stays_visible_when_application_deactivates(monkeypatch):
    from PySide6.QtCore import Qt

    import pet.window as window_mod

    attributes = []

    class FakeWindow:
        def setAttribute(self, attribute, enabled=True):
            attributes.append((attribute, enabled))

    monkeypatch.setattr(window_mod.sys, "platform", "darwin")
    window_mod._keep_macos_tool_window_visible(FakeWindow())
    assert attributes == [(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)]
    source = Path("pet/window.py").read_text(encoding="utf-8")
    set_on_top_source = source.split("def set_on_top", 1)[1].split("def showEvent", 1)[0]
    assert "WA_MacAlwaysShowToolWindow, on" not in set_on_top_source








def test_wired_petwindow_offers_settings_entry(tmp_path):
    """正式装配：真实 PetWindow + 真实 ``_wire_window`` 的「桌宠设置」入口可触发。

    真实装配：真实 ``PetWindow``（素材库用既有测试替身）+ **真实**
    ``pet.app.PetInstance._wire_window``（宿主只补该方法读到的面）；建菜单后触发
    设置项，断言落到 ``_wire_window`` 注入的那条现代设置回调。
    """
    from PySide6.QtWidgets import QApplication, QMenu

    import pet.app as app_mod
    from pet.context_menu import populate_context_menu
    from pet.config import Config

    import tests.test_context_menu_lifecycle as lc

    class _Shell:  # AppShell 经 self.shell 路由的进程级方法（本用例不触发）
        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    class _Host:  # _wire_window 的最小宿主：只补它读到的属性
        enable_chat = True

        def __init__(self, config):
            self.config = config
            self.shell = _Shell()
            self.opened: list[str] = []

        def _slot_wrap(self, fn):
            return fn

        def open_modern_settings(self):
            self.opened.append("modern")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    app = QApplication.instance() or QApplication([])
    config = Config(base=tmp_path)
    config.save()
    win = lc.PetWindow(lc.FakeLibrary(), config)
    host = _Host(config)
    app_mod.PetInstance._wire_window(host, win)
    try:
        menu = QMenu()
        populate_context_menu(menu, win)
        entries = [a for a in menu.actions() if a.text() == "桌宠设置"]
        assert len(entries) == 1, (
            f"「桌宠设置」入口应恰有一条，实际 {len(entries)} 条")
        assert entries[0].isEnabled()
        entries[0].trigger()
        assert host.opened == ["modern"], "设置入口未落到窗口的现代设置回调"
        menu.close()
        app.processEvents()
    finally:
        win.close()
        app.processEvents()


def test_runtime_pet_icon_crops_transparent_canvas_before_scaling():
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from pet.window import PetWindow

    class FakePet:
        idle = None
        lib = None

    app = QApplication.instance() or QApplication([])
    source = QPixmap(100, 100)
    source.fill(Qt.GlobalColor.transparent)
    painter = QPainter(source)
    painter.fillRect(QRect(45, 40, 10, 20), Qt.GlobalColor.blue)
    painter.end()
    fake = FakePet()
    fake._frame_pixmap = source

    icon = PetWindow.icon_pixmap(fake, 32)
    assert max(icon.width(), icon.height()) >= 30
    app.processEvents()


def test_windows_build_regenerates_the_icon_before_pyinstaller():
    build_script = Path("scripts/build_onedir.ps1").read_text(encoding="utf-8")
    make_icon = build_script.index("scripts\\make_icon.py")
    pyinstaller = build_script.index("python -m PyInstaller")
    assert make_icon < pyinstaller
    assert "assets\\big_blue_fat_fish\\ojingjing.jpg;assets\\big_blue_fat_fish" in build_script
    assert "pet\\menu_templates;pet\\menu_templates" in build_script
    mac_build_script = Path("scripts/build_macos.sh").read_text(encoding="utf-8")
    assert 'assets/big_blue_fat_fish:assets/big_blue_fat_fish' in mac_build_script
    assert "pet/menu_templates:pet/menu_templates" in mac_build_script


def test_modern_animation_leaf_icons_are_loaded_only_when_category_opens(monkeypatch):
    import time

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menu import populate_context_menu

    class Config(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    class Pet:
        cfg = Config(character="shenshen", on_top=False)
        on_open_chat = on_open_modern_settings = on_spawn_pet = None
        idles = ["idle-a"]
        turns = ["turn-a"]
        moves = ["move-a"]
        clicks = ["click-a"]
        acts = ["act-a"]
        playback_speed = scale = 1.0
        drag_physics = no_move = False

        def __init__(self):
            self.icon_requests = 0

        def animation_icon_image(self, name):
            self.icon_requests += 1
            image = QImage(64, 64, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.blue if name.endswith("a") else Qt.GlobalColor.red)
            return image

        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: None

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    pet = Pet()
    populate_context_menu(menu, pet)
    # Opening the root menu must not synchronously decode every animation.
    assert pet.icon_requests == 0
    animations = next(submenu for submenu in menu._owned_submenus if submenu.title() == "播放动画")
    idle = next(submenu for submenu in animations._owned_submenus if submenu.title() == "待机")
    assert idle.actions() == [], "根菜单构建不应同步填充动画分类动作"
    idle.aboutToShow.emit()
    placeholder_key = idle.actions()[0].icon().cacheKey()
    assert not idle.actions()[0].icon().isNull()
    deadline = time.monotonic() + 1.0
    while (
        (pet.icon_requests < 1 or idle.actions()[0].icon().cacheKey() == placeholder_key)
        and time.monotonic() < deadline
    ):
        app.processEvents()
        time.sleep(0.01)
    assert pet.icon_requests == 1
    assert not idle.actions()[0].icon().isNull()
    assert idle.actions()[0].icon().cacheKey() != placeholder_key
    menu.close()
    app.processEvents()


def test_animation_leaf_icon_crops_transparent_frame_before_filling_slot():
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QBitmap, QPainter, QPixmap, QRegion
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.icons import fitted_pet_pixmap_icon
    from pet.context_menus.menu_styles.modern import apply_modern_menu_style

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    apply_modern_menu_style(menu)
    source = QPixmap(640, 360)
    source.fill(Qt.GlobalColor.transparent)
    painter = QPainter(source)
    painter.fillRect(QRect(295, 120, 50, 120), Qt.GlobalColor.blue)
    painter.end()

    rendered = fitted_pet_pixmap_icon(menu, source).pixmap(18, 18)
    bounds = QRegion(QBitmap.fromImage(rendered.toImage().createAlphaMask())).boundingRect()
    assert max(bounds.width(), bounds.height()) >= 16
    app.processEvents()


def test_reopened_animation_menu_reuses_cached_images_immediately():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.shared import build_animation_categories
    from pet.context_menus.menu_styles.modern import apply_modern_menu_style

    class Pet:
        idles = ["idle-a"]
        turns = moves = clicks = acts = []

        def animation_icon_cached_image(self, name):
            assert name == "idle-a"
            image = QImage(64, 64, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.blue)
            return image

        def animation_icon_image(self, _name):
            raise AssertionError("cached thumbnail must not be decoded again")

        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: None

    app = QApplication.instance() or QApplication([])
    root = QMenu()
    apply_modern_menu_style(root)
    build_animation_categories(root, Pet(), icons=False, leaf_role_icons=True)
    idle = root._owned_submenus[0]
    assert idle.actions() == [], "根菜单构建不应同步填充动画分类动作"
    idle.aboutToShow.emit()
    assert idle.actions(), "首次展开分类子菜单时应填充动作"
    assert not idle.actions()[0].icon().isNull()
    app.processEvents()


def test_representative_animation_image_is_cached_on_pet(monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    import pet.window as window_mod
    from pet.window import PetWindow

    calls = []

    def decode(path):
        calls.append(path)
        image = QImage(64, 64, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.blue)
        return image

    class Clip:
        path = "/tmp/cached-animation.webm"

    class Library:
        def movie(self, _name, **_kw):
            return Clip()

        def clip_path(self, _name):
            return Clip.path

    class Pet:
        lib = Library()

    monkeypatch.setattr(window_mod, "decode_representative_frame", decode)
    pet = Pet()
    first = PetWindow.animation_icon_image(pet, "idle-a")
    second = PetWindow.animation_icon_image(pet, "idle-a")
    assert not first.isNull() and not second.isNull()
    assert calls == ["/tmp/cached-animation.webm"]


def test_representative_animation_decode_is_shared_across_pets(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from PySide6.QtGui import QImage

    import pet.animation_thumbnail as thumbnail

    path = tmp_path / "shared.webm"
    path.write_bytes(b"fixture")
    thumbnail._image_cache.clear()
    thumbnail._inflight.clear()
    calls = []

    def decode(_path):
        calls.append(1)
        return QImage(8, 8, QImage.Format.Format_ARGB32)

    monkeypatch.setattr(thumbnail, "_decode_representative_frame", decode)
    with ThreadPoolExecutor(max_workers=4) as pool:
        images = list(pool.map(thumbnail.decode_representative_frame, [path] * 4))

    assert len(calls) == 1
    assert all(not image.isNull() for image in images)
    assert thumbnail.decode_representative_frame(tmp_path / "missing.webm").isNull()


def test_long_submenus_enable_qt_scrolling():
    from PySide6.QtWidgets import QApplication, QMenu, QStyle

    from pet.context_menus.menu_styles.common import install_responsive_menu_style

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    for index in range(100):
        menu.addAction(f"动作 {index}")
    install_responsive_menu_style(menu)
    assert menu.style().styleHint(QStyle.StyleHint.SH_Menu_Scrollable, None, menu) == 1
    app.processEvents()


def test_visible_animation_submenu_does_not_relayout_when_thumbnail_finishes():
    import time

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.shared import build_animation_categories
    from pet.context_menus.menu_styles.modern import apply_modern_menu_style

    class Pet:
        idles = ["idle-a"]
        turns = moves = clicks = acts = []

        def __init__(self):
            self.cached = {}

        def animation_icon_cached_image(self, name):
            return self.cached.get(name, QImage())

        def animation_icon_image(self, name):
            image = QImage(64, 64, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.blue)
            self.cached[name] = image
            return image

        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: None

    app = QApplication.instance() or QApplication([])
    root = QMenu()
    apply_modern_menu_style(root)
    pet = Pet()
    build_animation_categories(root, pet, icons=False, leaf_role_icons=True)
    submenu = root._owned_submenus[0]
    assert submenu.actions() == [], "根菜单构建不应同步填充动画分类动作"
    submenu.aboutToShow.emit()
    placeholder_key = submenu.actions()[0].icon().cacheKey()
    # popup() 在无交互桌面的测试环境中可能不会进入可见状态，
    # 改用 show() 稳定模拟“菜单已展开”，从而覆盖可见时不重排图标的保护逻辑。
    submenu.show()
    deadline = time.monotonic() + 1.0
    while not pet.cached and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert pet.cached
    assert submenu.actions()[0].icon().cacheKey() == placeholder_key
    submenu.hide()
    submenu.aboutToShow.emit()
    assert submenu.actions()[0].icon().cacheKey() != placeholder_key


def test_animation_hover_only_dispatches_bounded_background_work():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.shared import build_animation_categories
    from pet.context_menus.menu_styles.modern import apply_modern_menu_style

    class Pet:
        idles = turns = moves = clicks = []
        acts = [f"act-{index}" for index in range(80)]

        def animation_icon_cached_image(self, _name):
            return QImage()

        def animation_icon_image(self, _name):
            return QImage()

        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: None

    app = QApplication.instance() or QApplication([])
    root = QMenu()
    apply_modern_menu_style(root)
    build_animation_categories(root, Pet(), icons=False, leaf_role_icons=True)
    submenu = root._owned_submenus[0]
    submenu.aboutToShow.emit()
    assert len(submenu._animation_icon_workers) <= 2
    app.processEvents()


def test_on_top_pet_reasserts_native_level_after_context_menu_hides():
    from PySide6.QtWidgets import QApplication

    from pet.window import PetWindow

    class Config(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    class Pet:
        cfg = Config(on_top=True)

        def __init__(self):
            self.levels = []

        def _schedule_macos_window_level(self, enabled):
            self.levels.append(enabled)

        def setAttribute(self, *_args):
            pass

    QApplication.instance() or QApplication([])
    pet = Pet()
    PetWindow._restore_on_top_after_context_menu(pet)
    assert pet.levels == [True]


def test_disabled_on_top_does_not_raise_after_context_menu_hides():
    from PySide6.QtWidgets import QApplication

    from pet.window import PetWindow

    class Pet:
        cfg = {"on_top": False}

        def __init__(self):
            self.levels = []

        def _schedule_macos_window_level(self, enabled):
            self.levels.append(enabled)

    QApplication.instance() or QApplication([])
    pet = Pet()
    PetWindow._restore_on_top_after_context_menu(pet)
    assert pet.levels == []


def test_representative_animation_frame_uses_the_later_middle():
    from pet.animation_thumbnail import representative_frame_index

    assert representative_frame_index(1) == 0
    assert representative_frame_index(50) == 30
    assert representative_frame_index(100) == 61


def test_template_reopen_reuses_original_visible_menu_position(monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QMenu

    import pet.window as window_mod
    from pet.window import PetWindow

    class FakePet:
        _context_menu_anchor = QPoint(320, 240)

        def __init__(self):
            self.shown_at = None

        def _show_context_menu(self, point):
            self.shown_at = QPoint(point)

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(window_mod.QTimer, "singleShot", lambda *args: args[-1]())
    menu = QMenu()
    menu.move(410, 260)
    fake = FakePet()
    PetWindow.reopen_context_menu(fake, menu)
    assert fake.shown_at == QPoint(410, 260)
    menu.close()
    app.processEvents()




def test_easter_egg_config_preserves_custom_paths(tmp_path):
    from pet.config import Config

    config = Config(tmp_path)
    config.set("menu_easter_egg", {
        "avatar": "/custom/avatar.png",
        "image_dir": "/custom/images",
    })
    custom = config.get("menu_easter_egg")
    assert custom["avatar"] == "/custom/avatar.png"
    assert custom["image_dir"] == "/custom/images"












def test_modern_menu_exposes_no_template_switch_action():
    """旧版菜单与它的「切换到…菜单」入口一起退役：注册表里不再有该动作。

    原位重开的通用能力（`reopen_context_menu`）由
    ``tests/test_sprite_menu_parity.py::test_open_full_menu_at_rebuilds_menu_at_position``
    覆盖，这里只钉"模板切换项不得复活"。
    """
    from pet.context_menus.registry import ACTION_LABELS, MENU_ACTIONS

    assert "switch_template" not in MENU_ACTIONS.ids
    assert "switch_template" not in ACTION_LABELS
    assert "切换到新版菜单" not in ACTION_LABELS.values()
    assert "切换回旧版菜单" not in ACTION_LABELS.values()


def test_color_picker_uses_stable_painted_swatch_instead_of_border_hack():
    from PySide6.QtWidgets import QApplication

    from pet.modern_settings_dialog import ColorPicker, ColorSwatchButton

    app = QApplication.instance() or QApplication([])
    picker = ColorPicker("#171717")
    assert isinstance(picker.button, ColorSwatchButton)
    assert picker.button.color().name() == "#171717"
    assert "border-left" not in picker.button.styleSheet()
    picker.edit.setText("#eeeeee")
    assert picker.button.color().name() == "#eeeeee"
    picker.close()
    app.processEvents()




def test_product_copy_has_no_external_brand_reference():
    forbidden = ("co" + "dex").lower()
    roots = [Path("pet"), Path("tests"), Path("docs"), Path("README.md")]
    hits = []
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in {".py", ".qss", ".md", ".json"}:
                continue
            # Competitive research records source names by design; they are
            # evidence, not user-facing product copy.
            if (
                path.name in {"agent_link.py", "test_agent_link.py"}
                or path.name.endswith("-RESEARCH.md")
                # Contributor/change reports are repository evidence, not
                # user-facing product copy and may mention external brands.
                or path.name.startswith("README-CHANGE-")
            ):
                continue
            if forbidden in path.read_text(encoding="utf-8", errors="ignore").lower():
                hits.append(str(path))
    assert hits == []


def test_return_corner_cancels_all_position_writers_before_move():
    from PySide6.QtCore import QRect

    from pet.window import PetWindow

    calls = []

    class Screen:
        @staticmethod
        def availableGeometry():
            return QRect(0, 0, 1000, 700)

        @staticmethod
        def name():
            return "test"

        @staticmethod
        def devicePixelRatio():
            return 1.0

    class FakePet:
        _w = 120
        _h = 180
        _dragging = False
        _press_global = None
        _grab_offset = None

        def _cancel_move(self): calls.append("move")
        def _stop_physics(self): calls.append("physics")
        def _screen_available(self): return Screen()
        def move(self, x, y): calls.append((x, y))
        def _save_position(self): calls.append("save")

    PetWindow._go_default_corner(FakePet())
    assert calls[:2] == ["move", "physics"]
    assert calls[-1] == "save"
    assert (855, 519) in calls


def test_macos_on_top_reapplies_native_level_without_stale_window_id():
    source = Path("pet/window.py").read_text(encoding="utf-8")
    method = source.split("def set_on_top", 1)[1].split("def showEvent", 1)[0]
    assert "_schedule_macos_window_level" in method
    assert "int(self.winId())" not in method
    helper = source.split("def _schedule_macos_window_level", 1)[1].split("def set_on_top", 1)[0]
    assert "self.winId()" in helper
    assert "40" in helper


def test_context_menu_leaf_actions_stay_open_until_focus_is_lost():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.menu_styles.common import install_stay_open_interaction

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    action = menu.addAction("拖动物理")
    action.setCheckable(True)
    install_stay_open_interaction(menu)
    menu.popup(QPoint(30, 30))
    app.processEvents()
    rect = menu.actionGeometry(action)
    pos = rect.center()
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, pos, menu.mapToGlobal(pos),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(menu, event)
    app.processEvents()
    assert action.isChecked() is True
    assert menu.isVisible() is True
    menu.close()
    app.processEvents()


def test_window_opening_menu_action_uses_native_close_path():
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.shared import add_action

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    action = add_action(menu, "桌宠设置", None, lambda: None, close_on_trigger=True)
    assert action.property("closeOnTrigger") is True
    menu.close()
    app.processEvents()


def test_macos_dock_icon_policy_tracks_the_saved_visibility_setting():
    source = Path("pet/app.py").read_text(encoding="utf-8")
    helper = source.split("def _mac_set_dock_icon_visible", 1)[1].split("def main", 1)[0]
    assert "NSApplicationActivationPolicyRegular = 0" in helper
    assert "Accessory = 1" in helper
    assert "setActivationPolicy:" in helper
    main = source.split("def main", 1)[1]
    assert '_mac_set_dock_icon_visible(bool(config.get("show_dock_icon", True)))' in main


def test_pet_app_binds_about_to_quit_once_to_current_window(tmp_path, monkeypatch):
    """aboutToQuit 只绑定一次，且触发时保存「当前」有效窗口位置（非已销毁的旧窗口）。"""
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "legacy")  # PetWindow 路径测试
    from PySide6.QtWidgets import QApplication

    import pet.app as app_mod
    from pet.app import AppShell
    from pet.config import Config

    QApplication.instance() or QApplication([])

    class FakeApp:
        def __init__(self):
            self.connections = []

        @property
        def aboutToQuit(self):
            # 模拟信号对象：self.app.aboutToQuit.connect(slot) 追加到 connections
            return self

        def connect(self, slot):
            self.connections.append(slot)

    class FakeWin:
        def __init__(self):
            self.saved = 0

        def save_position(self):
            self.saved += 1

    monkeypatch.setattr(app_mod.QTimer, "singleShot", lambda *a, **k: None)
    owner = AppShell(FakeApp(), Config(tmp_path))
    owner.instance._create_ui = lambda cid: None
    owner.instance._apply_spawn_offset = lambda: None
    owner._apply_balance_timer = lambda: None

    old = FakeWin()
    owner.instance.win = old
    owner.start()
    owner.start()  # 重复 start 不得叠加 connect
    # 本用例的被测对象是 AppShell 的**自有**接线：只统计它自己的槽——start()
    # 还会让会话结束探测器（issue #111）接一条 aboutToQuit 兜底，那是另一个
    # 组件的一次性接线（由 pet/session_watcher 自测覆盖），不参与本计数。
    shell_connections = [c for c in owner.app.connections
                         if c == owner._on_about_to_quit]
    assert len(shell_connections) == 1, "AppShell 重复 start 不得叠加 aboutToQuit 接线"

    current = FakeWin()
    owner.instance.win = current
    owner._on_about_to_quit()  # 触发 aboutToQuit（直接调用同样的槽）
    assert current.saved == 1
    assert old.saved == 0  # 旧窗口不再被保存





def test_external_character_dirs_uses_variant_then_legacy_fallback(tmp_path, monkeypatch):
    """外部角色目录应优先变体目录，并保留旧 dsh-pet-standalone 目录兜底。"""
    import sys

    import pet.catalog as catalog_mod
    from pet import config as config_mod

    monkeypatch.setattr(config_mod, "APP_DIR_NAME", "dsh-pet-standalone-webm-chat")
    # 数据目录按平台走 APPDATA / Library/Application Support / XDG_CONFIG_HOME
    if sys.platform == "win32":
        root = tmp_path
        monkeypatch.setenv("APPDATA", str(tmp_path))
    elif sys.platform == "darwin":
        root = tmp_path / "Library" / "Application Support"
        monkeypatch.setenv("HOME", str(tmp_path))
    else:
        root = tmp_path
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    dirs = catalog_mod.external_character_dirs()
    variant = root / "dsh-pet-standalone-webm-chat" / "characters"
    legacy = root / "dsh-pet-standalone" / "characters"
    assert variant in dirs
    assert legacy in dirs
    assert dirs.index(variant) < dirs.index(legacy)  # 新目录优先


def test_external_character_dirs_dedupes_base_dir(tmp_path, monkeypatch):
    """非变体（APP_DIR_NAME == 默认）时旧目录不被重复追加。"""
    import sys

    import pet.catalog as catalog_mod
    from pet import config as config_mod

    monkeypatch.setattr(config_mod, "APP_DIR_NAME", "dsh-pet-standalone")
    if sys.platform == "win32":
        root = tmp_path
        monkeypatch.setenv("APPDATA", str(tmp_path))
    elif sys.platform == "darwin":
        root = tmp_path / "Library" / "Application Support"
        monkeypatch.setenv("HOME", str(tmp_path))
    else:
        root = tmp_path
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    dirs = catalog_mod.external_character_dirs()
    base = root / "dsh-pet-standalone" / "characters"
    assert dirs.count(base) == 1
def test_self_talk_deleted_external_dir_falls_back_to_text_not_bundled(tmp_path):
    """回归：用户显式配置的外部图片目录被删后，不再回退内置彩蛋池
    （用户删目录的意图就是不要再看图）。"""
    from pet.window import _resolve_self_talk_image_dir

    gone = tmp_path / "deleted_dir"
    assert _resolve_self_talk_image_dir(str(gone)) == ""

    existing = tmp_path / "pics"
    existing.mkdir()
    assert _resolve_self_talk_image_dir(str(existing)) == str(existing)

    # 相对路径（内置 assets）仍走既有回退解析
    assert _resolve_self_talk_image_dir("") == ""
# --- Custom image-directory gallery regression (2026-09-03) ---


def test_image_directory_picker_opens_right_drawer_with_three_column_masonry(tmp_path):
    from PIL import Image
    from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout

    from pet.modern_settings_dialog import ImagePreviewDrawer, ResourcePathPicker

    short = tmp_path / "01-one.png"
    # 名字要够长（卡片文本按宽度截断显示、tooltip 显示全名），但不能长到触发
    # Windows MAX_PATH：tmp_path 本身已有 ~90 字符，*8 的重复拼出 262 字符的
    # 绝对路径，在未开启长路径支持（LongPathsEnabled=0）的 Windows 上
    # Image.save() 直接 FileNotFoundError。*3 仍是长名字，够验证截断与 tooltip。
    long = tmp_path / ("02-" + "very-long-image-name-" * 3 + ".jpg")
    Image.new("RGB", (40, 80), "red").save(short)
    Image.new("RGB", (100, 40), "blue").save(long)
    Image.new("RGB", (80, 80), "green").save(tmp_path / "03-square.png")
    Image.new("RGB", (120, 50), "yellow").save(tmp_path / "04-fourth.png")
    (tmp_path / "ignore.txt").write_text("ignore", encoding="utf-8")
    app = QApplication.instance() or QApplication([])
    host = QDialog()
    host.resize(1000, 680)
    layout = QVBoxLayout(host)
    picker = ResourcePathPicker(str(tmp_path), directory=True, image_preview=True, parent=host)
    layout.addWidget(picker)
    host.show()
    app.processEvents()

    assert picker.preview_button.text() == "预览"
    assert host.findChild(ImagePreviewDrawer, "imagePreviewDrawer") is None
    picker.preview_button.click()
    app.processEvents()
    drawer = host.findChild(ImagePreviewDrawer, "imagePreviewDrawer")
    assert drawer is not None and not drawer.isHidden()
    assert drawer.geometry().right() == host.rect().right()
    assert drawer.flow.layout.column_count == 3
    assert drawer.count_label.text() == "4 张图片"
    assert len(drawer.flow.cards) == 4
    assert drawer.flow.cards[1].toolTip() == long.name
    assert drawer.flow.cards[3].y() < drawer.flow.cards[0].geometry().bottom()
    assert drawer.flow.cards[3].x() == drawer.flow.cards[1].x()
    host.close()
    app.processEvents()


def test_cleanup_old_pet_logs(tmp_path):
    """审查 GLM-M2 回归：启动时清理超龄 pet-*.log，不动新日志与其他文件。"""
    import os
    import time

    from pet.app import _cleanup_old_pet_logs

    old = tmp_path / "pet-111.log"
    old.write_text("x", encoding="utf-8")
    old_ts = time.time() - 8 * 86400
    os.utime(old, (old_ts, old_ts))
    old_backup = tmp_path / "pet-111.log.1"
    old_backup.write_text("x", encoding="utf-8")
    os.utime(old_backup, (old_ts, old_ts))
    fresh = tmp_path / "pet-222.log"
    fresh.write_text("y", encoding="utf-8")
    other = tmp_path / "config.json"
    other.write_text("z", encoding="utf-8")
    os.utime(other, (time.time() - 30 * 86400,) * 2)  # 老但非 pet 日志

    assert _cleanup_old_pet_logs(tmp_path) == 2
    assert not old.exists() and not old_backup.exists()
    assert fresh.exists() and other.exists()












