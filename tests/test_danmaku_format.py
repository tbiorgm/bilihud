import bilihud  # noqa: F401
import blivedm.models.web as web_models

from bilihud.danmaku_format import (
    danmaku_emoticon_scaled_size,
    danmaku_emoticon_url,
    danmaku_message_content_html,
    danmaku_message_emoticon_urls,
)


def test_danmaku_emoticon_url_only_uses_pure_emoticon_messages():
    emoticon = web_models.DanmakuMessage(
        dm_type=1,
        msg="[妙啊]",
        emoticon_options={
            "url": "https://i0.hdslb.com/bfs/live/emote.png",
            "width": 183,
            "height": 60,
        },
    )
    text = web_models.DanmakuMessage(
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
    emoticon = web_models.DanmakuMessage(
        dm_type=1,
        msg='[<妙啊>"]',
        emoticon_options={
            "url": "https://i0.hdslb.com/bfs/live/emote.png?x=1&y=2",
            "width": 60,
            "height": 60,
        },
    )
    text = web_models.DanmakuMessage(dm_type=0, msg="<b>普通弹幕</b>")

    assert danmaku_message_content_html(emoticon) == (
        '<img class="emoticon" src="https://i0.hdslb.com/bfs/live/emote.png?x=1&amp;y=2" '
        'width="34" height="34" alt="[&lt;妙啊&gt;&quot;]" />'
    )
    assert danmaku_message_content_html(text) == "&lt;b&gt;普通弹幕&lt;/b&gt;"


def test_danmaku_message_content_html_renders_inline_emoticons_from_extra_emots():
    message = web_models.DanmakuMessage(
        dm_type=0,
        msg="[汤圆][汤圆] <ok>",
        mode_info={
            "extra": {
                "emots": {
                    "[汤圆]": {
                        "url": "https://i0.hdslb.com/bfs/live/tangyuan.png?x=1&y=2",
                        "width": 60,
                        "height": 60,
                    }
                }
            }
        },
    )

    assert danmaku_message_content_html(message) == (
        '<img class="emoticon" src="https://i0.hdslb.com/bfs/live/tangyuan.png?x=1&amp;y=2" '
        'width="34" height="34" alt="[汤圆]" />'
        '<img class="emoticon" src="https://i0.hdslb.com/bfs/live/tangyuan.png?x=1&amp;y=2" '
        'width="34" height="34" alt="[汤圆]" />'
        " &lt;ok&gt;"
    )


def test_danmaku_message_emoticon_urls_include_inline_emots_once():
    message = web_models.DanmakuMessage(
        dm_type=0,
        msg="[汤圆][汤圆] [无图]",
        mode_info={
            "extra": {
                "emots": {
                    "[汤圆]": {
                        "url": "https://i0.hdslb.com/bfs/live/tangyuan.png",
                        "width": 60,
                        "height": 60,
                    },
                    "[无图]": {
                        "url": "",
                        "width": 60,
                        "height": 60,
                    },
                }
            }
        },
    )

    assert danmaku_message_emoticon_urls(message) == [
        "https://i0.hdslb.com/bfs/live/tangyuan.png"
    ]
