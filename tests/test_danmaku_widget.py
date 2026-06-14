from pathlib import Path

from PyQt6.QtGui import QImage

from bilihud import danmaku_widget
from bilihud.danmaku_widget import (
    danmaku_emoticon_scaled_size,
    danmaku_emoticon_url,
    danmaku_message_content_html,
)


def test_danmaku_widget_does_not_manually_process_qt_events():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "QApplication.processEvents()" not in source


def test_danmaku_widget_imports_qimage_for_emoticon_loader():
    assert danmaku_widget.QImage is QImage


def test_danmaku_emoticon_url_only_uses_pure_emoticon_messages():
    emoticon = danmaku_widget.web_models.DanmakuMessage(
        dm_type=1,
        msg="[妙啊]",
        emoticon_options={
            "url": "https://i0.hdslb.com/bfs/live/emote.png",
            "width": 183,
            "height": 60,
        },
    )
    text = danmaku_widget.web_models.DanmakuMessage(
        dm_type=0,
        msg="[妙啊]",
        emoticon_options={
            "url": "https://i0.hdslb.com/bfs/live/emote.png",
            "width": 183,
            "height": 60,
        },
    )

    assert danmaku_emoticon_url(emoticon) == "https://i0.hdslb.com/bfs/live/emote.png"
    assert danmaku_emoticon_url(text) == ""


def test_danmaku_emoticon_scaled_size_preserves_aspect_ratio():
    options = {
        "url": "https://i0.hdslb.com/bfs/live/emote.png",
        "width": 183,
        "height": 60,
    }

    assert danmaku_emoticon_scaled_size(options) == (104, 34)


def test_danmaku_message_content_html_renders_emoticon_image_and_escapes_text():
    emoticon = danmaku_widget.web_models.DanmakuMessage(
        dm_type=1,
        msg='[<妙啊>"]',
        emoticon_options={
            "url": "https://i0.hdslb.com/bfs/live/emote.png?x=1&y=2",
            "width": 60,
            "height": 60,
        },
    )
    text = danmaku_widget.web_models.DanmakuMessage(dm_type=0, msg="<b>普通弹幕</b>")

    assert danmaku_message_content_html(emoticon) == (
        '<img class="emoticon" src="https://i0.hdslb.com/bfs/live/emote.png?x=1&amp;y=2" '
        'width="34" height="34" alt="[&lt;妙啊&gt;&quot;]" />'
    )
    assert danmaku_message_content_html(text) == "&lt;b&gt;普通弹幕&lt;/b&gt;"
