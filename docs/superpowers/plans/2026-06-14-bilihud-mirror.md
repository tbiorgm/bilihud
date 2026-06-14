# BiliHUD Mirror Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local `http://127.0.0.1:2233/bilihud-mirror` browser page that mirrors BiliHUD's danmaku content and style semantics without syncing local HUD position or size.

**Architecture:** First extract existing danmaku formatting helpers out of the Qt widget into a small Qt-free module, then build a Qt-free mirror state model on top of those helpers. Serve the mirror with `aiohttp.web` on loopback using Server-Sent Events. Wire `DanmakuWidget.add_message()` to publish to the mirror because it is already the convergence point for danmaku, gifts, interactions, and system messages.

**Tech Stack:** Python 3.10+, `aiohttp.web`, PyQt6/qasync integration, existing `blivedm.models.web` message models, pytest.

---

## File Structure

- Create `src/bilihud/danmaku_format.py`
  - Owns Qt-free danmaku formatting helpers currently living in `danmaku_widget.py`.
  - Avoids circular imports between `danmaku_widget.py` and the mirror modules.

- Create `src/bilihud/mirror_state.py`
  - Converts BiliHUD message objects into serializable mirror messages.
  - Owns message cap/pruning and sequence numbers.
  - Has no Qt imports and no HTTP/server code.

- Create `src/bilihud/mirror_server.py`
  - Owns the loopback `aiohttp.web` app.
  - Serves `/bilihud-mirror`.
  - Serves `/bilihud-mirror/events` as Server-Sent Events.
  - Publishes snapshots and append events from `MirrorState`.

- Modify `src/bilihud/danmaku_widget.py`
  - Imports formatting helpers from `danmaku_format.py`.
  - Creates and starts/stops `MirrorServer`.
  - Publishes every `add_message()` message into the mirror state.
  - Adds tray actions to start/stop the mirror and show the URL.

- Create `tests/test_danmaku_format.py`
  - Moves existing danmaku formatting tests away from `tests/test_danmaku_widget.py`.

- Create `tests/test_mirror_state.py`
  - Unit tests for conversion, emoticons, escaping-safe state shape, pruning, and path-independent semantics.

- Create `tests/test_mirror_server.py`
  - Unit/integration-style tests for route constants, HTML content, and event serialization helpers.

---

### Task 1: Extract Qt-Free Danmaku Formatting

**Files:**
- Create: `src/bilihud/danmaku_format.py`
- Modify: `src/bilihud/danmaku_widget.py`
- Create: `tests/test_danmaku_format.py`
- Modify: `tests/test_danmaku_widget.py`

- [ ] **Step 1: Create failing tests for the new formatting module**

Create `tests/test_danmaku_format.py`:

```python
from bilihud import danmaku_widget
from bilihud.danmaku_format import (
    danmaku_emoticon_scaled_size,
    danmaku_emoticon_url,
    danmaku_message_content_html,
    danmaku_message_emoticon_urls,
)


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


def test_danmaku_message_content_html_renders_inline_emoticons_from_extra_emots():
    message = danmaku_widget.web_models.DanmakuMessage(
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
    message = danmaku_widget.web_models.DanmakuMessage(
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run --extra test pytest tests/test_danmaku_format.py -q
```

Expected: FAIL because `bilihud.danmaku_format` does not exist.

- [ ] **Step 3: Create `danmaku_format.py`**

Create `src/bilihud/danmaku_format.py` by moving these existing helpers from `src/bilihud/danmaku_widget.py`:

```python
import html
import re

import blivedm.models.web as web_models


DANMAKU_EMOTICON_MAX_HEIGHT = 34
DANMAKU_EMOTICON_MAX_WIDTH = 140


def _emoticon_option_url(options: dict) -> str:
    url = str(options.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    return url


def danmaku_emoticon_url(message: web_models.DanmakuMessage) -> str:
    if message.dm_type != 1:
        return ""
    return _emoticon_option_url(message.emoticon_options_dict)


def danmaku_inline_emoticons(message: web_models.DanmakuMessage) -> dict[str, dict]:
    emots = message.extra_dict.get("emots")
    if not isinstance(emots, dict):
        return {}

    inline_emoticons = {}
    for token, options in emots.items():
        if not token or not isinstance(options, dict):
            continue
        if not _emoticon_option_url(options):
            continue
        inline_emoticons[str(token)] = options
    return inline_emoticons


def danmaku_emoticon_scaled_size(options: dict) -> tuple[int, int]:
    try:
        source_width = int(options.get("width") or 0)
        source_height = int(options.get("height") or 0)
    except (TypeError, ValueError):
        source_width = 0
        source_height = 0

    if source_width <= 0 or source_height <= 0:
        return DANMAKU_EMOTICON_MAX_HEIGHT, DANMAKU_EMOTICON_MAX_HEIGHT

    scale = DANMAKU_EMOTICON_MAX_HEIGHT / source_height
    width = max(1, round(source_width * scale))
    height = DANMAKU_EMOTICON_MAX_HEIGHT
    if width > DANMAKU_EMOTICON_MAX_WIDTH:
        width = DANMAKU_EMOTICON_MAX_WIDTH
        height = max(1, round(source_height * (DANMAKU_EMOTICON_MAX_WIDTH / source_width)))
    return width, height


def _danmaku_emoticon_image_html(token: str, options: dict) -> str:
    width, height = danmaku_emoticon_scaled_size(options)
    alt = html.escape(token.strip() or "表情", quote=True)
    src = html.escape(_emoticon_option_url(options), quote=True)
    return f'<img class="emoticon" src="{src}" width="{width}" height="{height}" alt="{alt}" />'


def danmaku_inline_emoticon_content_html(message: web_models.DanmakuMessage) -> str:
    text = message.msg.strip()
    inline_emoticons = {
        token: options
        for token, options in danmaku_inline_emoticons(message).items()
        if token in text
    }
    if not inline_emoticons:
        return html.escape(text, quote=True)

    tokens = sorted(inline_emoticons, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(token) for token in tokens))
    parts = []
    last_end = 0
    for match in pattern.finditer(text):
        parts.append(html.escape(text[last_end:match.start()], quote=True))
        token = match.group(0)
        parts.append(_danmaku_emoticon_image_html(token, inline_emoticons[token]))
        last_end = match.end()
    parts.append(html.escape(text[last_end:], quote=True))
    return "".join(parts)


def danmaku_message_content_html(message: web_models.DanmakuMessage) -> str:
    emoticon_url = danmaku_emoticon_url(message)
    if emoticon_url:
        return _danmaku_emoticon_image_html(message.msg, message.emoticon_options_dict)
    return danmaku_inline_emoticon_content_html(message)


def danmaku_message_emoticon_urls(message: web_models.DanmakuMessage) -> list[str]:
    urls = []
    seen = set()

    pure_emoticon_url = danmaku_emoticon_url(message)
    if pure_emoticon_url:
        urls.append(pure_emoticon_url)
        seen.add(pure_emoticon_url)

    for token, options in danmaku_inline_emoticons(message).items():
        if token not in message.msg.strip():
            continue
        url = _emoticon_option_url(options)
        if url and url not in seen:
            urls.append(url)
            seen.add(url)

    return urls
```

- [ ] **Step 4: Update `danmaku_widget.py` imports and remove moved helpers**

In `src/bilihud/danmaku_widget.py`:

1. Remove `import html` and `import re` if no longer used directly.
2. Remove the moved constants and helper functions from the top of the file.
3. Add:

```python
from .danmaku_format import (
    danmaku_message_content_html,
    danmaku_message_emoticon_urls,
)
```

Leave the existing `html.escape(...)` calls in `DanmakuDelegate.get_html_for_message()` intact. If `html` is still used there, keep `import html`.

- [ ] **Step 5: Trim duplicated tests from `tests/test_danmaku_widget.py`**

Remove these imports from `tests/test_danmaku_widget.py`:

```python
from bilihud.danmaku_widget import (
    danmaku_emoticon_scaled_size,
    danmaku_emoticon_url,
    danmaku_message_content_html,
)
```

Remove these tests from `tests/test_danmaku_widget.py` because they now live in `tests/test_danmaku_format.py`:

- `test_danmaku_emoticon_url_only_uses_pure_emoticon_messages`
- `test_danmaku_emoticon_scaled_size_preserves_aspect_ratio`
- `test_danmaku_message_content_html_renders_emoticon_image_and_escapes_text`
- `test_danmaku_message_content_html_renders_inline_emoticons_from_extra_emots`
- `test_danmaku_message_emoticon_urls_include_inline_emots_once`

Keep these widget tests:

- `test_danmaku_widget_does_not_manually_process_qt_events`
- `test_danmaku_widget_imports_qimage_for_emoticon_loader`

- [ ] **Step 6: Run formatting and widget tests**

Run:

```bash
uv run --extra test pytest tests/test_danmaku_format.py tests/test_danmaku_widget.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/bilihud/danmaku_format.py src/bilihud/danmaku_widget.py tests/test_danmaku_format.py tests/test_danmaku_widget.py
git commit -m "refactor: extract danmaku formatting helpers"
```

---

### Task 2: Mirror State Model

**Files:**
- Create: `src/bilihud/mirror_state.py`
- Test: `tests/test_mirror_state.py`

- [ ] **Step 1: Write failing tests for mirror conversion and pruning**

Create `tests/test_mirror_state.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run --extra test pytest tests/test_mirror_state.py -q
```

Expected: FAIL because `bilihud.mirror_state` does not exist.

- [ ] **Step 3: Implement mirror state**

Create `src/bilihud/mirror_state.py`:

```python
from __future__ import annotations

import re
from typing import Any

import blivedm.models.web as web_models

from .danmaku_format import (
    danmaku_emoticon_scaled_size,
    danmaku_emoticon_url,
    danmaku_inline_emoticons,
)


MIRROR_DEFAULT_PORT = 2233
MIRROR_ROUTE = "/bilihud-mirror"
MIRROR_EVENTS_ROUTE = "/bilihud-mirror/events"
MIRROR_MAX_MESSAGES = 200


def user_color_for_message(message: Any) -> str:
    if getattr(message, "is_system_error", False):
        return "#FF5555"
    if getattr(message, "is_system_info", False):
        return "#AAAAAA"
    if getattr(message, "privilege_type", 0) > 0:
        return "#FFD700"
    if isinstance(message, web_models.GiftMessage):
        return "#FFD700"
    if isinstance(message, web_models.InteractWordV2Message):
        return "#AAAAAA"
    if getattr(message, "vip", False) or getattr(message, "svip", False):
        return "#FF69B4"
    if getattr(message, "admin", False):
        return "#FF4500"
    return "#66CCFF"


def _image_segment(text: str, url: str, options: dict[str, Any]) -> dict[str, Any]:
    width, height = danmaku_emoticon_scaled_size(options)
    return {
        "type": "image",
        "text": text,
        "url": url,
        "width": width,
        "height": height,
    }


def danmaku_segments(message: web_models.DanmakuMessage) -> list[dict[str, Any]]:
    pure_url = danmaku_emoticon_url(message)
    if pure_url:
        return [_image_segment(message.msg.strip() or "表情", pure_url, message.emoticon_options_dict)]

    text = message.msg.strip()
    inline = {
        token: options
        for token, options in danmaku_inline_emoticons(message).items()
        if token in text
    }
    if not inline:
        return [{"type": "text", "text": text}]

    pattern = re.compile("|".join(re.escape(token) for token in sorted(inline, key=len, reverse=True)))
    segments: list[dict[str, Any]] = []
    last_end = 0
    for match in pattern.finditer(text):
        if match.start() > last_end:
            segments.append({"type": "text", "text": text[last_end:match.start()]})
        token = match.group(0)
        options = inline[token]
        segments.append(_image_segment(token, str(options.get("url") or ""), options))
        last_end = match.end()
    if last_end < len(text):
        segments.append({"type": "text", "text": text[last_end:]})
    return segments


def _interact_text(msg_type: int) -> str:
    return {
        1: "进入直播间",
        2: "关注了主播",
        3: "分享了直播间",
        4: "特别关注了主播",
        5: "互粉了主播",
        6: "为主播点赞了",
    }.get(msg_type, "进入直播间")


def message_to_mirror_entry(seq: int, message: Any) -> dict[str, Any]:
    if isinstance(message, web_models.DanmakuMessage):
        return {
            "seq": seq,
            "kind": "danmaku",
            "user": message.uname,
            "userColor": user_color_for_message(message),
            "segments": danmaku_segments(message),
        }

    if isinstance(message, web_models.GiftMessage):
        return {
            "seq": seq,
            "kind": "gift",
            "user": message.uname,
            "userColor": user_color_for_message(message),
            "segments": [{"type": "text", "text": f"{message.action} {message.gift_name} x{message.num}"}],
        }

    if isinstance(message, web_models.InteractWordV2Message):
        return {
            "seq": seq,
            "kind": "interact",
            "user": message.username,
            "userColor": user_color_for_message(message),
            "segments": [{"type": "text", "text": _interact_text(message.msg_type)}],
        }

    return {
        "seq": seq,
        "kind": "system",
        "user": str(getattr(message, "uname", "")),
        "userColor": user_color_for_message(message),
        "segments": [{"type": "text", "text": str(getattr(message, "msg", ""))}],
    }


class MirrorState:
    def __init__(self, max_messages: int = MIRROR_MAX_MESSAGES):
        self.max_messages = max_messages
        self._next_seq = 1
        self._messages: list[dict[str, Any]] = []

    def add_message(self, message: Any) -> dict[str, Any]:
        entry = message_to_mirror_entry(self._next_seq, message)
        self._next_seq += 1
        self._messages.append(entry)
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]
        return entry

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._messages)
```

- [ ] **Step 4: Run mirror state tests**

Run:

```bash
uv run --extra test pytest tests/test_mirror_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Run formatting and state tests together**

Run:

```bash
uv run --extra test pytest tests/test_danmaku_format.py tests/test_mirror_state.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/bilihud/mirror_state.py tests/test_mirror_state.py
git commit -m "feat: add bilihud mirror state"
```

---

### Task 3: Mirror Server

**Files:**
- Create: `src/bilihud/mirror_server.py`
- Test: `tests/test_mirror_server.py`

- [ ] **Step 1: Write failing tests for routes, HTML, and event formatting**

Create `tests/test_mirror_server.py`:

```python
import json

from bilihud.mirror_server import mirror_event_payload, mirror_html
from bilihud.mirror_state import MIRROR_EVENTS_ROUTE, MIRROR_ROUTE


def test_mirror_routes_are_bilihud_named():
    assert MIRROR_ROUTE == "/bilihud-mirror"
    assert MIRROR_EVENTS_ROUTE == "/bilihud-mirror/events"
    assert "obs" not in MIRROR_ROUTE.lower()
    assert "obs" not in MIRROR_EVENTS_ROUTE.lower()


def test_mirror_html_uses_transparent_page_and_event_source():
    page = mirror_html(MIRROR_EVENTS_ROUTE)

    assert "background: transparent" in page
    assert f'new EventSource("{MIRROR_EVENTS_ROUTE}")' in page
    assert "/obs" not in page.lower()
    assert "textContent" in page
    assert "createElement(\"img\")" in page


def test_mirror_event_payload_serializes_named_event():
    payload = mirror_event_payload("append", {"seq": 1, "segments": []})

    assert payload.startswith("event: append\n")
    assert payload.endswith("\n\n")
    data_line = next(line for line in payload.splitlines() if line.startswith("data: "))
    assert json.loads(data_line.removeprefix("data: ")) == {"seq": 1, "segments": []}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run --extra test pytest tests/test_mirror_server.py -q
```

Expected: FAIL because `bilihud.mirror_server` does not exist.

- [ ] **Step 3: Implement mirror server helpers and lifecycle**

Create `src/bilihud/mirror_server.py`:

```python
from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from .mirror_state import MIRROR_DEFAULT_PORT, MIRROR_EVENTS_ROUTE, MIRROR_ROUTE, MirrorState


def mirror_event_payload(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def mirror_html(events_route: str = MIRROR_EVENTS_ROUTE) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: transparent;
      overflow: hidden;
      font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    }}
    #panel {{
      box-sizing: border-box;
      width: 100vw;
      min-height: 100vh;
      padding: 10px;
      background: rgba(0, 0, 0, 0.47);
      border-radius: 8px;
      color: white;
    }}
    .message {{
      line-height: 1.2;
      margin: 0 0 4px;
      font-size: 13px;
      font-weight: 500;
    }}
    .user {{
      font-size: 12px;
      font-weight: 700;
    }}
    .colon {{
      color: white;
      font-size: 12px;
    }}
    .emoticon {{
      vertical-align: middle;
      max-height: 34px;
      max-width: 140px;
    }}
  </style>
</head>
<body>
  <div id="panel"></div>
  <script>
    const panel = document.getElementById("panel");
    const maxMessages = 200;

    function appendText(parent, text) {{
      parent.appendChild(document.createTextNode(text));
    }}

    function renderEntry(entry) {{
      const row = document.createElement("div");
      row.className = "message";
      row.dataset.seq = String(entry.seq);

      const user = document.createElement("span");
      user.className = "user";
      user.style.color = entry.userColor || "#66CCFF";
      user.textContent = entry.user || "";
      row.appendChild(user);

      const colon = document.createElement("span");
      colon.className = "colon";
      colon.textContent = " : ";
      row.appendChild(colon);

      for (const segment of entry.segments || []) {{
        if (segment.type === "image") {{
          const img = document.createElement("img");
          img.className = "emoticon";
          img.src = segment.url;
          img.alt = segment.text || "";
          img.width = segment.width || 34;
          img.height = segment.height || 34;
          row.appendChild(img);
        }} else {{
          appendText(row, segment.text || "");
        }}
      }}

      panel.appendChild(row);
      while (panel.children.length > maxMessages) {{
        panel.removeChild(panel.firstElementChild);
      }}
      window.scrollTo(0, document.body.scrollHeight);
    }}

    function renderSnapshot(entries) {{
      panel.replaceChildren();
      for (const entry of entries || []) {{
        renderEntry(entry);
      }}
    }}

    const events = new EventSource("{events_route}");
    events.addEventListener("snapshot", event => renderSnapshot(JSON.parse(event.data)));
    events.addEventListener("append", event => renderEntry(JSON.parse(event.data)));
  </script>
</body>
</html>"""


class MirrorServer:
    def __init__(self, state: MirrorState, host: str = "127.0.0.1", port: int = MIRROR_DEFAULT_PORT):
        self.state = state
        self.host = host
        self.port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._clients: set[asyncio.Queue[str]] = set()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{MIRROR_ROUTE}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get(MIRROR_ROUTE, self._handle_page)
        app.router.add_get(MIRROR_EVENTS_ROUTE, self._handle_events)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

    async def stop(self) -> None:
        for queue in list(self._clients):
            queue.put_nowait("")
        self._clients.clear()
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def _handle_page(self, _request: web.Request) -> web.Response:
        return web.Response(text=mirror_html(), content_type="text/html")

    async def _handle_events(self, _request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(_request)
        await response.write(mirror_event_payload("snapshot", self.state.snapshot()).encode("utf-8"))

        queue: asyncio.Queue[str] = asyncio.Queue()
        self._clients.add(queue)
        try:
            while True:
                payload = await queue.get()
                if not payload:
                    break
                await response.write(payload.encode("utf-8"))
        except (asyncio.CancelledError, ConnectionResetError, RuntimeError):
            pass
        finally:
            self._clients.discard(queue)
        return response

    def publish_append(self, entry: dict[str, Any]) -> None:
        payload = mirror_event_payload("append", entry)
        for queue in list(self._clients):
            queue.put_nowait(payload)
```

- [ ] **Step 4: Run mirror server tests**

Run:

```bash
uv run --extra test pytest tests/test_mirror_server.py -q
```

Expected: PASS.

- [ ] **Step 5: Run mirror tests together**

Run:

```bash
uv run --extra test pytest tests/test_mirror_state.py tests/test_mirror_server.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/bilihud/mirror_server.py tests/test_mirror_server.py
git commit -m "feat: serve bilihud mirror page"
```

---

### Task 4: Wire Mirror Into DanmakuWidget

**Files:**
- Modify: `src/bilihud/danmaku_widget.py`
- Test: `tests/test_danmaku_widget.py`

- [ ] **Step 1: Write failing tests for widget integration hooks**

Append to `tests/test_danmaku_widget.py`:

```python
def test_danmaku_widget_imports_mirror_components():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "from .mirror_state import MIRROR_DEFAULT_PORT, MIRROR_ROUTE, MirrorState" in source
    assert "from .mirror_server import MirrorServer" in source


def test_danmaku_widget_add_message_publishes_to_mirror():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "entry = self.mirror_state.add_message(message)" in source
    assert "self.mirror_server.publish_append(entry)" in source


def test_danmaku_widget_exposes_bilihud_mirror_tray_action():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "BiliHUD Mirror" in source
    assert "MIRROR_ROUTE" in source
    assert "obs-mirror" not in source
    assert "obs-danmaku" not in source
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run --extra test pytest tests/test_danmaku_widget.py -q
```

Expected: FAIL because the widget does not import or publish mirror state yet.

- [ ] **Step 3: Add imports**

In `src/bilihud/danmaku_widget.py`, add:

```python
from .mirror_state import MIRROR_DEFAULT_PORT, MIRROR_ROUTE, MirrorState
from .mirror_server import MirrorServer
```

- [ ] **Step 4: Initialize mirror state and config once**

In `DanmakuWidget.__init__`, after `self.layer_shell_disabled_reason = ""`, add:

```python
        config = load_config()
        self.mirror_state = MirrorState()
        self.mirror_server: MirrorServer | None = None
        self.mirror_enabled = bool(config.get("mirror_enabled", False))
        self.mirror_port = int(config.get("mirror_port", MIRROR_DEFAULT_PORT))
```

Then remove the later duplicate `config = load_config()` line and reuse the existing `config` variable for `room_id`.

- [ ] **Step 5: Start mirror after tray setup when enabled**

In `DanmakuWidget.__init__`, after `self.setup_danmaku_client()`, add:

```python
        if self.mirror_enabled:
            asyncio.create_task(self.start_mirror_server())
```

- [ ] **Step 6: Add mirror tray actions**

In `setup_tray_icon()`, after the live control action is added, insert:

```python
        self.tray_mirror_action = QAction("启动 BiliHUD Mirror", self)
        self.tray_mirror_action.triggered.connect(self.toggle_mirror_server)
        tray_menu.addAction(self.tray_mirror_action)

        self.tray_mirror_url_action = QAction("显示 Mirror URL", self)
        self.tray_mirror_url_action.triggered.connect(self.show_mirror_url)
        tray_menu.addAction(self.tray_mirror_url_action)
```

- [ ] **Step 7: Add mirror lifecycle methods**

Add these methods to `DanmakuWidget` near `open_live_control()`:

```python
    @property
    def mirror_url(self) -> str:
        return f"http://127.0.0.1:{self.mirror_port}{MIRROR_ROUTE}"

    @qasync.asyncSlot()
    async def toggle_mirror_server(self):
        if self.mirror_server is None:
            await self.start_mirror_server()
        else:
            await self.stop_mirror_server()

    async def start_mirror_server(self):
        if self.mirror_server is not None:
            self.show_mirror_url()
            return
        server = MirrorServer(self.mirror_state, port=self.mirror_port)
        try:
            await server.start()
        except OSError as exc:
            self.add_system_message(f"BiliHUD Mirror 启动失败: {exc}", "error")
            return
        self.mirror_server = server
        self.mirror_enabled = True
        save_config({"mirror_enabled": True, "mirror_port": self.mirror_port})
        self.tray_mirror_action.setText("停止 BiliHUD Mirror")
        self.add_system_message(f"BiliHUD Mirror 已启动: {server.url}")

    async def stop_mirror_server(self):
        if self.mirror_server is None:
            return
        server = self.mirror_server
        self.mirror_server = None
        await server.stop()
        self.mirror_enabled = False
        save_config({"mirror_enabled": False, "mirror_port": self.mirror_port})
        self.tray_mirror_action.setText("启动 BiliHUD Mirror")
        self.add_system_message("BiliHUD Mirror 已停止。")

    def show_mirror_url(self):
        self.tray_icon.showMessage(
            "BiliHUD Mirror",
            self.mirror_server.url if self.mirror_server else self.mirror_url,
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )
```

- [ ] **Step 8: Publish messages from `add_message()`**

In `add_message()`, after pruning the local list, add:

```python
        entry = self.mirror_state.add_message(message)
        if self.mirror_server is not None:
            self.mirror_server.publish_append(entry)
```

- [ ] **Step 9: Stop mirror on application quit**

Change `quit_app()` to:

```python
    @qasync.asyncSlot()
    async def quit_app(self):
        if self.mirror_server is not None:
            await self.stop_mirror_server()
        QApplication.quit()
```

- [ ] **Step 10: Run widget tests**

Run:

```bash
uv run --extra test pytest tests/test_danmaku_widget.py -q
```

Expected: PASS.

- [ ] **Step 11: Run all mirror-related tests**

Run:

```bash
uv run --extra test pytest tests/test_danmaku_format.py tests/test_danmaku_widget.py tests/test_mirror_state.py tests/test_mirror_server.py -q
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add src/bilihud/danmaku_widget.py tests/test_danmaku_widget.py
git commit -m "feat: connect bilihud mirror to hud messages"
```

---

### Task 5: Verification And Manual Smoke Test

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run full test suite**

Run:

```bash
uv run --extra test pytest -q
```

Expected: PASS.

- [ ] **Step 2: Check diff cleanliness**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Start BiliHUD**

Run:

```bash
uv run bilihud
```

Expected: BiliHUD starts without traceback.

- [ ] **Step 4: Start BiliHUD Mirror from the tray menu**

Use the tray action `启动 BiliHUD Mirror`.

Expected:

- A system message appears in the local HUD with `http://127.0.0.1:2233/bilihud-mirror`.
- The tray action changes to `停止 BiliHUD Mirror`.

- [ ] **Step 5: Open mirror URL manually**

Open:

```text
http://127.0.0.1:2233/bilihud-mirror
```

Expected:

- Browser page is transparent where supported.
- Existing mirror snapshot appears if messages were already added.
- New danmaku added to local HUD also appears on the page.
- Pure and inline emoticons render as images.

- [ ] **Step 6: Add URL as OBS Browser Source**

In OBS, add a Browser Source manually with:

```text
http://127.0.0.1:2233/bilihud-mirror
```

Expected:

- OBS source shows the same danmaku content sequence as the local HUD.
- Resizing the OBS source changes only OBS layout; BiliHUD does not try to sync local HUD size or position.

- [ ] **Step 7: Final commit if verification fixes were needed**

If Task 5 required code changes:

```bash
git add <changed-files>
git commit -m "fix: polish bilihud mirror verification issues"
```

If no code changes were needed, do not create an empty commit.

---

## Self-Review

- Spec coverage: The plan covers `/bilihud-mirror`, default port `2233`, loopback binding, content/style semantic mirror, no position/size sync, no OBS route naming, pure and inline emoticons, capped state, transparent browser page, and manual OBS Browser Source usage.
- Intentional gap: automatic OBS Browser Source creation is not in the first implementation because the spec keeps OBS outside the mirror core and the user asked for a simple plan.
- Dependency boundary: `danmaku_format.py` prevents circular imports by keeping shared formatting helpers free of Qt, mirror server, and widget dependencies.
- Type consistency: `MirrorState`, `MirrorServer`, `MIRROR_DEFAULT_PORT`, `MIRROR_ROUTE`, and `MIRROR_EVENTS_ROUTE` are defined before use.
- Scope guardrail: the plan does not refactor `danmaku_widget.py` broadly and does not introduce a settings window.
