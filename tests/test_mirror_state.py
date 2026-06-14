import bilihud  # noqa: F401
import blivedm.models.web as web_models

from bilihud.mirror_state import MirrorState, message_to_mirror_entry


def test_message_to_mirror_entry_converts_text_danmaku():
    message = web_models.DanmakuMessage(
        uname="Locez",
        msg="<hello>",
        privilege_type=0,
        vip=0,
        svip=0,
        admin=0,
    )

    entry = message_to_mirror_entry(1, message)

    assert entry == {
        "seq": 1,
        "kind": "danmaku",
        "user": "Locez",
        "userColor": "#66CCFF",
        "segments": [{"type": "text", "text": "<hello>"}],
    }


def test_message_to_mirror_entry_converts_pure_emoticon_danmaku():
    message = web_models.DanmakuMessage(
        uname="Locez",
        msg="[妙啊]",
        dm_type=1,
        emoticon_options={
            "url": "https://i0.hdslb.com/bfs/live/emote.png",
            "width": 183,
            "height": 60,
        },
    )

    entry = message_to_mirror_entry(2, message)

    assert entry["segments"] == [
        {
            "type": "image",
            "text": "[妙啊]",
            "url": "https://i0.hdslb.com/bfs/live/emote.png",
            "width": 104,
            "height": 34,
        }
    ]


def test_message_to_mirror_entry_converts_inline_emoticons():
    message = web_models.DanmakuMessage(
        uname="Locez",
        msg="[汤圆] ok [汤圆]",
        mode_info={
            "extra": {
                "emots": {
                    "[汤圆]": {
                        "url": "https://i0.hdslb.com/bfs/live/tangyuan.png",
                        "width": 60,
                        "height": 60,
                    }
                }
            }
        },
    )

    entry = message_to_mirror_entry(3, message)

    assert entry["segments"] == [
        {
            "type": "image",
            "text": "[汤圆]",
            "url": "https://i0.hdslb.com/bfs/live/tangyuan.png",
            "width": 34,
            "height": 34,
        },
        {"type": "text", "text": " ok "},
        {
            "type": "image",
            "text": "[汤圆]",
            "url": "https://i0.hdslb.com/bfs/live/tangyuan.png",
            "width": 34,
            "height": 34,
        },
    ]


def test_message_to_mirror_entry_converts_gift_message():
    message = web_models.GiftMessage(uname="Locez", action="赠送", gift_name="辣条", num=3)

    entry = message_to_mirror_entry(4, message)

    assert entry == {
        "seq": 4,
        "kind": "gift",
        "user": "Locez",
        "userColor": "#FFD700",
        "segments": [{"type": "text", "text": "赠送 辣条 x3"}],
    }


def test_message_to_mirror_entry_converts_interact_message():
    message = web_models.InteractWordV2Message(username="观众", msg_type=2)

    entry = message_to_mirror_entry(5, message)

    assert entry == {
        "seq": 5,
        "kind": "interact",
        "user": "观众",
        "userColor": "#AAAAAA",
        "segments": [{"type": "text", "text": "关注了主播"}],
    }


def test_mirror_state_caps_messages_and_assigns_sequences():
    state = MirrorState(max_messages=2)

    first = state.add_message(web_models.DanmakuMessage(uname="A", msg="1"))
    second = state.add_message(web_models.DanmakuMessage(uname="B", msg="2"))
    third = state.add_message(web_models.DanmakuMessage(uname="C", msg="3"))

    assert first["seq"] == 1
    assert second["seq"] == 2
    assert third["seq"] == 3
    assert [entry["user"] for entry in state.snapshot()] == ["B", "C"]
