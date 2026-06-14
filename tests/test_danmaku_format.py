import importlib

from bilihud.danmaku_format import (
    danmaku_author_badges_html,
    danmaku_emoticon_scaled_size,
    danmaku_emoticon_url,
    danmaku_message_content_html,
    danmaku_message_emoticon_urls,
)

web_models = importlib.import_module("blivedm.models.web")


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


def test_danmaku_author_badges_html_renders_compact_metadata_badges():
    message = web_models.DanmakuMessage(
        medal_name="<狐>",
        medal_level=26,
        mcolor=0x2FB6E8,
        wealth_level=8,
        privilege_type=3,
    )

    badges = danmaku_author_badges_html(message)

    assert "meta-badge medal-badge" in badges
    assert "&lt;狐&gt;" in badges
    assert "26" in badges
    assert "#FF79C6" in badges
    assert "&lt;狐&gt; 26</span>&nbsp;<span" in badges
    assert "meta-badge wealth-badge" in badges
    assert "✦" in badges
    assert "8" in badges
    assert "✦ 8</span>&nbsp;<span" in badges
    assert "meta-badge privilege-badge" in badges
    assert "⚓︎" in badges
    assert "舰长" not in badges
    assert "荣耀" not in badges
    assert "荣" not in badges


def test_danmaku_author_badges_html_omits_empty_metadata():
    message = web_models.DanmakuMessage()

    assert danmaku_author_badges_html(message) == ""


def test_danmaku_author_badges_html_maps_guard_levels_to_blue_purple_gold():
    assert "🛳︎" in danmaku_author_badges_html(web_models.DanmakuMessage(privilege_type=1))
    assert "#FFD700" in danmaku_author_badges_html(web_models.DanmakuMessage(privilege_type=1))
    assert "⛴︎" in danmaku_author_badges_html(web_models.DanmakuMessage(privilege_type=2))
    assert "#C9B6FF" in danmaku_author_badges_html(web_models.DanmakuMessage(privilege_type=2))
    assert "⚓︎" in danmaku_author_badges_html(web_models.DanmakuMessage(privilege_type=3))
    assert "#86C8FF" in danmaku_author_badges_html(web_models.DanmakuMessage(privilege_type=3))
