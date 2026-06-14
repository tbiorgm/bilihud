# Live Emoticon Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact Bilibili live-room emoticon picker to the BiliHUD input row, backed by the live v2 emoticon API and respecting locked emoticon permissions.

**Architecture:** Keep API parsing and payload building in a focused `live_emoticons.py` module, expose fetch/send methods through `DanmakuClient`, and add a Qt popup connected from `ModernInputWidget` and `DanmakuWidget`. The picker is a UI layer over parsed `LiveEmoticonPackage` data and never sends locked emoticons.

**Tech Stack:** Python 3.10+, PyQt6, aiohttp, qasync, pytest.

---

## File Structure

- Create `src/bilihud/live_emoticons.py`: dataclasses, v2 parser, package sorting, send payload builder.
- Modify `src/bilihud/danmaku_client.py`: fetch live emoticons and send selected live emoticon via the existing authenticated session.
- Modify `src/bilihud/danmaku_widget.py`: input-row emoticon button, picker popup, image thumbnails, locked styles, send wiring.
- Create `tests/test_live_emoticons.py`: parser, sorting, permission, payload tests.
- Modify `tests/test_danmaku_client.py`: client fetch/send behavior using fake sessions.
- Modify `tests/test_danmaku_widget.py`: source-level/UI signal tests for button/popup locked behavior where practical.

---

### Task 1: Live Emoticon Model, Parser, Sorting, Payload

**Files:**
- Create: `src/bilihud/live_emoticons.py`
- Test: `tests/test_live_emoticons.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_live_emoticons.py`:

```python
from bilihud.live_emoticons import (
    LiveEmoticon,
    build_live_emoticon_payload,
    parse_live_emoticon_packages,
)


def test_parse_live_emoticon_packages_sorts_room_packages_first_and_preserves_lock_state():
    payload = {
        "code": 0,
        "message": "0",
        "data": {
            "data": [
                {
                    "pkg_id": 1,
                    "pkg_name": "通用表情",
                    "pkg_type": 1,
                    "pkg_perm": 1,
                    "emoticons": [
                        {
                            "emoji": "啊",
                            "url": "http://i0.hdslb.com/bfs/live/a.png",
                            "width": 200,
                            "height": 60,
                            "perm": 1,
                            "identity": 99,
                            "unlock_show_text": "",
                            "unlock_show_color": "",
                            "emoticon_unique": "official_331",
                            "emoticon_id": 331,
                        }
                    ],
                },
                {
                    "pkg_id": 428,
                    "pkg_name": "UP主大表情",
                    "pkg_type": 2,
                    "pkg_perm": 1,
                    "emoticons": [
                        {
                            "emoji": "疑惑",
                            "url": "http://i0.hdslb.com/bfs/garb/locked.png",
                            "width": 162,
                            "height": 162,
                            "perm": 0,
                            "identity": 3,
                            "unlock_need_level": 1,
                            "unlock_need_gift": 0,
                            "unlock_show_text": "舰长",
                            "unlock_show_color": "#FF6699",
                            "emoticon_unique": "room_870691_1154",
                            "emoticon_id": 1154,
                        }
                    ],
                },
                {
                    "pkg_id": 100428,
                    "pkg_name": "房间专属表情",
                    "pkg_type": 2,
                    "pkg_perm": 1,
                    "emoticons": [
                        {
                            "emoji": "AKIE的A",
                            "url": "http://i0.hdslb.com/bfs/live/room.png",
                            "width": 162,
                            "height": 162,
                            "perm": 1,
                            "identity": 99,
                            "unlock_show_text": "",
                            "unlock_show_color": "",
                            "emoticon_unique": "room_870691_84455",
                            "emoticon_id": 0,
                        }
                    ],
                },
            ]
        },
    }

    packages = parse_live_emoticon_packages(payload)

    assert [package.name for package in packages] == ["房间专属表情", "UP主大表情", "通用表情"]
    locked = packages[1].emoticons[0]
    assert locked.is_available is False
    assert locked.unlock_label == "舰长"
    assert locked.unlock_color == "#FF6699"
    assert locked.unique == "room_870691_1154"


def test_parse_live_emoticon_packages_raises_on_api_error():
    payload = {"code": -101, "message": "账号未登录", "data": None}

    try:
        parse_live_emoticon_packages(payload)
    except ValueError as exc:
        assert "账号未登录" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_live_emoticon_payload_uses_dm_type_and_unique_id():
    emoticon = LiveEmoticon(
        emoji="AKIE的A",
        url="http://i0.hdslb.com/bfs/live/room.png",
        width=162,
        height=162,
        perm=1,
        unique="room_870691_84455",
        emoticon_id=0,
    )

    payload = build_live_emoticon_payload(
        room_id=870691,
        csrf_token="csrf-token",
        rnd="12345",
        emoticon=emoticon,
    )

    assert payload["msg"] == "AKIE的A"
    assert payload["roomid"] == 870691
    assert payload["csrf"] == "csrf-token"
    assert payload["csrf_token"] == "csrf-token"
    assert payload["dm_type"] == "1"
    assert payload["emoticonOptions"] == "[object Object]"
    assert payload["data_extend"] == '{"trackid":"-99998"}'
    assert "emoticon_unique" not in payload
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_live_emoticons.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bilihud.live_emoticons'`.

- [ ] **Step 3: Implement module**

Create `src/bilihud/live_emoticons.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ROOM_PACKAGE_ORDER = {
    "房间专属表情": 0,
    "UP主大表情": 1,
    "通用表情": 2,
}


@dataclass(frozen=True)
class LiveEmoticon:
    emoji: str
    url: str
    width: int
    height: int
    perm: int
    unique: str
    emoticon_id: int
    identity: int = 0
    unlock_label: str = ""
    unlock_color: str = ""
    unlock_need_level: int = 0
    unlock_need_gift: int = 0

    @property
    def is_available(self) -> bool:
        return self.perm == 1


@dataclass(frozen=True)
class LiveEmoticonPackage:
    package_id: int
    name: str
    package_type: int
    package_perm: int
    emoticons: tuple[LiveEmoticon, ...]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_emoticon(raw: dict[str, Any]) -> LiveEmoticon | None:
    emoji = str(raw.get("emoji") or raw.get("descript") or "").strip()
    url = str(raw.get("url") or "").strip()
    unique = str(raw.get("emoticon_unique") or "").strip()
    if not emoji or not url or not unique:
        return None

    return LiveEmoticon(
        emoji=emoji,
        url=url,
        width=_as_int(raw.get("width")),
        height=_as_int(raw.get("height")),
        perm=_as_int(raw.get("perm")),
        unique=unique,
        emoticon_id=_as_int(raw.get("emoticon_id")),
        identity=_as_int(raw.get("identity")),
        unlock_label=str(raw.get("unlock_show_text") or ""),
        unlock_color=str(raw.get("unlock_show_color") or ""),
        unlock_need_level=_as_int(raw.get("unlock_need_level")),
        unlock_need_gift=_as_int(raw.get("unlock_need_gift")),
    )


def parse_live_emoticon_packages(payload: dict[str, Any]) -> list[LiveEmoticonPackage]:
    if payload.get("code") != 0:
        message = str(payload.get("message") or "获取直播间表情失败")
        raise ValueError(message)

    data = payload.get("data")
    groups = data.get("data") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return []

    packages: list[tuple[int, LiveEmoticonPackage]] = []
    for index, raw_package in enumerate(groups):
        if not isinstance(raw_package, dict):
            continue
        name = str(raw_package.get("pkg_name") or "").strip()
        if not name:
            continue

        raw_emoticons = raw_package.get("emoticons")
        if not isinstance(raw_emoticons, list):
            raw_emoticons = []
        emoticons = tuple(
            emoticon
            for emoticon in (_parse_emoticon(raw) for raw in raw_emoticons if isinstance(raw, dict))
            if emoticon is not None
        )

        package = LiveEmoticonPackage(
            package_id=_as_int(raw_package.get("pkg_id")),
            name=name,
            package_type=_as_int(raw_package.get("pkg_type")),
            package_perm=_as_int(raw_package.get("pkg_perm")),
            emoticons=emoticons,
        )
        packages.append((index, package))

    packages.sort(key=lambda item: (ROOM_PACKAGE_ORDER.get(item[1].name, 100), item[0]))
    return [package for _, package in packages]


def build_live_emoticon_payload(
    *,
    room_id: int,
    csrf_token: str,
    rnd: str,
    emoticon: LiveEmoticon,
) -> dict[str, str | int]:
    return {
        "bubble": "0",
        "msg": emoticon.unique,
        "color": "16777215",
        "mode": "1",
        "fontsize": "25",
        "rnd": rnd,
        "roomid": room_id,
        "csrf": csrf_token,
        "csrf_token": csrf_token,
        "dm_type": "1",
        "emoticonOptions": "[object Object]",
        "data_extend": '{"trackid":"-99998"}',
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_live_emoticons.py -q
```

Expected: PASS.

---

### Task 2: DanmakuClient Fetch And Send Methods

**Files:**
- Modify: `src/bilihud/danmaku_client.py`
- Test: `tests/test_danmaku_client.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_danmaku_client.py`:

```python
import json

from bilihud.live_emoticons import LiveEmoticon


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self.payload


class _FakeCookie:
    def __init__(self, key, value):
        self.key = key
        self.value = value


class _FakeSession:
    def __init__(self, get_payload=None, post_payload=None):
        self.get_payload = get_payload or {"code": 0, "data": {"data": []}}
        self.post_payload = post_payload or {"code": 0, "message": "0"}
        self.posted_data = None
        self.get_params = None
        self.get_headers = None
        self.cookie_jar = [_FakeCookie("bili_jct", "csrf-token")]

    def get(self, url, params=None, headers=None):
        self.get_url = url
        self.get_params = params
        self.get_headers = headers
        return _FakeResponse(self.get_payload)

    def post(self, url, data=None):
        self.post_url = url
        self.posted_data = data
        return _FakeResponse(self.post_payload)


async def test_fetch_live_emoticons_uses_v2_api_and_existing_session():
    client = DanmakuClient(870691)
    client.session = _FakeSession(
        get_payload={
            "code": 0,
            "message": "0",
            "data": {
                "data": [
                    {
                        "pkg_id": 100428,
                        "pkg_name": "房间专属表情",
                        "pkg_type": 2,
                        "pkg_perm": 1,
                        "emoticons": [
                            {
                                "emoji": "AKIE的A",
                                "url": "http://i0.hdslb.com/bfs/live/room.png",
                                "width": 162,
                                "height": 162,
                                "perm": 1,
                                "emoticon_unique": "room_870691_84455",
                                "emoticon_id": 0,
                            }
                        ],
                    }
                ]
            },
        }
    )

    packages = await client.fetch_live_emoticons()

    assert packages[0].name == "房间专属表情"
    assert client.session.get_url.endswith("/xlive/web-ucenter/v2/emoticon/GetEmoticons")
    assert client.session.get_params == {"platform": "pc", "room_id": 870691}
    assert client.session.get_headers["Referer"] == "https://live.bilibili.com/870691"


async def test_send_live_emoticon_posts_dm_type_payload():
    client = DanmakuClient(870691)
    client.session = _FakeSession(post_payload={"code": 0, "message": "0"})
    emoticon = LiveEmoticon(
        emoji="AKIE的A",
        url="http://i0.hdslb.com/bfs/live/room.png",
        width=162,
        height=162,
        perm=1,
        unique="room_870691_84455",
        emoticon_id=0,
    )

    success, message = await client.send_live_emoticon(emoticon)

    assert success is True
    assert message == "发送成功"
    assert client.session.post_url.startswith("https://api.live.bilibili.com/msg/send?")
    assert client.session.posted_data.is_multipart is True
    posted_fields = _form_data_fields(client.session.posted_data)
    assert posted_fields["dm_type"] == "1"
    assert posted_fields["emoticonOptions"] == "[object Object]"
    assert posted_fields["data_extend"] == '{"trackid":"-99998"}'
    assert "emoticon_unique" not in posted_fields
    assert posted_fields["msg"] == "AKIE的A"


async def test_send_live_emoticon_rejects_locked_emoticon_without_posting():
    client = DanmakuClient(870691)
    client.session = _FakeSession()
    emoticon = LiveEmoticon(
        emoji="疑惑",
        url="http://i0.hdslb.com/bfs/live/locked.png",
        width=162,
        height=162,
        perm=0,
        unique="room_870691_1154",
        emoticon_id=1154,
        unlock_label="舰长",
    )

    success, message = await client.send_live_emoticon(emoticon)

    assert success is False
    assert "未解锁" in message
    assert client.session.posted_data is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_danmaku_client.py::test_fetch_live_emoticons_uses_v2_api_and_existing_session tests/test_danmaku_client.py::test_send_live_emoticon_posts_dm_type_payload tests/test_danmaku_client.py::test_send_live_emoticon_rejects_locked_emoticon_without_posting -q
```

Expected: FAIL because `DanmakuClient` has no `fetch_live_emoticons` or `send_live_emoticon`.

- [ ] **Step 3: Implement methods**

Modify imports in `src/bilihud/danmaku_client.py`:

```python
from .live_emoticons import LiveEmoticon, build_live_emoticon_payload, parse_live_emoticon_packages
```

Add methods inside `DanmakuClient` after `send_danmaku`:

```python
    async def fetch_live_emoticons(self):
        """Fetch room-specific live emoticon packages."""
        if not self.session:
            raise RuntimeError("弹幕会话未初始化")

        url = "https://api.live.bilibili.com/xlive/web-ucenter/v2/emoticon/GetEmoticons"
        params = {"platform": "pc", "room_id": self.room_id}
        headers = {"Referer": f"https://live.bilibili.com/{self.room_id}"}
        async with self.session.get(url, params=params, headers=headers) as res:
            if res.status != 200:
                raise RuntimeError(f"HTTP错误: {res.status}")
            payload = await res.json(content_type=None)
        return parse_live_emoticon_packages(payload)

    async def send_live_emoticon(self, emoticon: LiveEmoticon) -> tuple[bool, str]:
        """Send a pure live emoticon."""
        if not self.session:
            return False, "会话未初始化"
        if not emoticon.is_available:
            label = emoticon.unlock_label or "当前账号"
            return False, f"表情未解锁: {label}"

        csrf_token = ""
        for cookie in self.session.cookie_jar:
            if cookie.key == "bili_jct":
                csrf_token = cookie.value
                break
        if not csrf_token:
            return False, "未找到CSRF Token，请重新连接或检查Cookie"

        data = build_live_emoticon_payload(
            room_id=self.room_id,
            csrf_token=csrf_token,
            rnd=str(int(time.time())),
            emoticon=emoticon,
        )

        try:
            send_url = await self._signed_live_msg_send_url()
            async with self.session.post(send_url, data=_multipart_form_data(data)) as res:
                if res.status != 200:
                    return False, f"HTTP错误: {res.status}"
                json_data = await res.json()
                if json_data["code"] == 0:
                    return True, "发送成功"
                return False, f"发送失败: {json_data['message']}"
        except Exception as exc:
            return False, f"发送异常: {str(exc)}"
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_danmaku_client.py::test_fetch_live_emoticons_uses_v2_api_and_existing_session tests/test_danmaku_client.py::test_send_live_emoticon_posts_dm_type_payload tests/test_danmaku_client.py::test_send_live_emoticon_rejects_locked_emoticon_without_posting -q
```

Expected: PASS.

---

### Task 3: Input Button And Picker Popup

**Files:**
- Modify: `src/bilihud/danmaku_widget.py`
- Test: `tests/test_danmaku_widget.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_danmaku_widget.py`:

```python
from bilihud.live_emoticons import LiveEmoticon, LiveEmoticonPackage


def test_modern_input_widget_exposes_emoticon_button_signal(qtbot):
    widget = danmaku_widget.ModernInputWidget()
    qtbot.addWidget(widget)

    seen = []
    widget.emoticon_requested.connect(lambda: seen.append(True))
    widget.emoticon_btn.click()

    assert seen == [True]


def test_emoticon_picker_does_not_emit_locked_emoticons(qtbot):
    picker = danmaku_widget.EmoticonPickerPopup()
    qtbot.addWidget(picker)
    locked = LiveEmoticon(
        emoji="疑惑",
        url="http://i0.hdslb.com/bfs/live/locked.png",
        width=162,
        height=162,
        perm=0,
        unique="room_870691_1154",
        emoticon_id=1154,
        unlock_label="舰长",
        unlock_color="#FF6699",
    )
    package = LiveEmoticonPackage(
        package_id=428,
        name="UP主大表情",
        package_type=2,
        package_perm=1,
        emoticons=(locked,),
    )
    emitted = []
    picker.emoticon_selected.connect(emitted.append)

    picker.set_packages([package])
    cell = picker._emoticon_buttons[0]
    cell.click()

    assert emitted == []
    assert "舰长" in cell.toolTip()
    assert not cell.isEnabled()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_danmaku_widget.py::test_modern_input_widget_exposes_emoticon_button_signal tests/test_danmaku_widget.py::test_emoticon_picker_does_not_emit_locked_emoticons -q
```

Expected: FAIL because `emoticon_requested`, `emoticon_btn`, and `EmoticonPickerPopup` do not exist.

- [ ] **Step 3: Implement UI classes**

Modify `src/bilihud/danmaku_widget.py` imports:

```python
    QDialog, QSizePolicy, QAbstractItemView, QListView, QScrollArea,
    QGridLayout, QToolButton, QTabWidget
```

Add to `PyQt6.QtGui` imports:

```python
    QPixmap
```

Add to local imports:

```python
from .live_emoticons import LiveEmoticon, LiveEmoticonPackage
```

Modify `ModernInputWidget`:

```python
    emoticon_requested = pyqtSignal()
```

Create `self.emoticon_btn` before `send_btn` and add it between input and send:

```python
        self.emoticon_btn = QPushButton("☻")
        self.emoticon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.emoticon_btn.setFixedSize(28, 26)
        self.emoticon_btn.setToolTip("发送表情")
        self.emoticon_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 35);
                color: white;
                border: 1px solid rgba(255, 255, 255, 60);
                border-radius: 13px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 60);
            }
        """)
        self.emoticon_btn.clicked.connect(self.emoticon_requested.emit)
```

Then:

```python
        self.layout.addWidget(self.input_edit)
        self.layout.addWidget(self.emoticon_btn)
        self.layout.addWidget(self.send_btn)
```

Add `EmoticonPickerPopup` above `DanmakuWidget`:

```python
class EmoticonPickerPopup(QDialog):
    emoticon_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(330, 260)
        self._network_manager = QNetworkAccessManager(self)
        self._image_cache: dict[str, QPixmap] = {}
        self._button_by_url: dict[str, list[QToolButton]] = {}
        self._emoticon_buttons: list[QToolButton] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(22, 24, 28, 235);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 8px;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 24);
                color: white;
                padding: 5px 9px;
                margin-right: 4px;
                border-radius: 5px;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: rgba(79, 172, 254, 150);
            }
            QToolButton {
                background: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 6px;
                color: white;
                padding: 2px;
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 40);
            }
            QToolButton:disabled {
                background: rgba(255, 255, 255, 10);
                color: rgba(255, 255, 255, 110);
            }
        """)
        outer.addWidget(self.container)
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(8, 8, 8, 8)
        self.tabs = QTabWidget(self.container)
        layout.addWidget(self.tabs)

    def set_loading(self):
        self.tabs.clear()
        self._emoticon_buttons.clear()
        label = QLabel("加载中...", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: rgba(255, 255, 255, 180);")
        self.tabs.addTab(label, "表情")

    def set_error(self, message: str):
        self.tabs.clear()
        self._emoticon_buttons.clear()
        label = QLabel(message, self)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: rgba(255, 255, 255, 180);")
        self.tabs.addTab(label, "表情")

    def set_packages(self, packages: list[LiveEmoticonPackage]):
        self.tabs.clear()
        self._emoticon_buttons.clear()
        if not packages:
            self.set_error("没有可显示的直播间表情")
            return

        for package in packages:
            page = QWidget(self)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 4, 0, 0)
            scroll = QScrollArea(page)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            grid_host = QWidget(scroll)
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)

            for index, emoticon in enumerate(package.emoticons):
                button = self._create_emoticon_button(emoticon)
                row, col = divmod(index, 5)
                grid.addWidget(button, row, col)
                self._emoticon_buttons.append(button)

            scroll.setWidget(grid_host)
            page_layout.addWidget(scroll)
            self.tabs.addTab(page, package.name)

    def _create_emoticon_button(self, emoticon: LiveEmoticon) -> QToolButton:
        button = QToolButton(self)
        button.setFixedSize(52, 52)
        button.setIconSize(QSize(42, 42))
        label = emoticon.unlock_label
        button.setToolTip(emoticon.emoji if not label else f"{emoticon.emoji} - {label}")
        if not emoticon.is_available:
            button.setEnabled(False)
            if label:
                button.setText(label)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        else:
            button.clicked.connect(lambda _checked=False, emoticon=emoticon: self.emoticon_selected.emit(emoticon))

        self._load_icon(button, emoticon.url)
        return button

    def _load_icon(self, button: QToolButton, url: str):
        cached = self._image_cache.get(url)
        if cached:
            button.setIcon(QIcon(cached))
            return

        self._button_by_url.setdefault(url, []).append(button)
        if len(self._button_by_url[url]) > 1:
            return

        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"Referer", b"https://live.bilibili.com/")
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0 BiliHUD")
        reply = self._network_manager.get(request)
        reply.finished.connect(lambda reply=reply, url=url: self._on_icon_loaded(reply, url))

    def _on_icon_loaded(self, reply, url: str):
        pixmap = QPixmap()
        pixmap.loadFromData(reply.readAll())
        reply.deleteLater()
        buttons = self._button_by_url.pop(url, [])
        if pixmap.isNull():
            return
        self._image_cache[url] = pixmap
        icon = QIcon(pixmap)
        for button in buttons:
            button.setIcon(icon)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_danmaku_widget.py::test_modern_input_widget_exposes_emoticon_button_signal tests/test_danmaku_widget.py::test_emoticon_picker_does_not_emit_locked_emoticons -q
```

Expected: PASS.

---

### Task 4: Wire Picker Into DanmakuWidget

**Files:**
- Modify: `src/bilihud/danmaku_widget.py`
- Test: `tests/test_danmaku_widget.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_danmaku_widget.py`:

```python
def test_danmaku_widget_source_wires_emoticon_picker_to_client_methods():
    source = Path(danmaku_widget.__file__).read_text(encoding="utf-8")

    assert "self.input_area.emoticon_requested.connect(self.open_emoticon_picker)" in source
    assert "await self.danmaku_client.fetch_live_emoticons()" in source
    assert "await self.danmaku_client.send_live_emoticon(emoticon)" in source
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_danmaku_widget.py::test_danmaku_widget_source_wires_emoticon_picker_to_client_methods -q
```

Expected: FAIL because wiring does not exist.

- [ ] **Step 3: Implement wiring**

In `DanmakuWidget.init_ui`, after `self.input_area.send_requested.connect(self.trigger_send)`, add:

```python
        self.input_area.emoticon_requested.connect(self.open_emoticon_picker)
        self.emoticon_picker = EmoticonPickerPopup(self)
        self.emoticon_picker.emoticon_selected.connect(self.trigger_send_live_emoticon)
```

Add methods near send methods:

```python
    @qasync.asyncSlot()
    async def open_emoticon_picker(self):
        if not self.danmaku_client or not self.danmaku_client.session:
            self.add_system_message("未连接直播间，无法加载表情", "error")
            return

        self.emoticon_picker.set_loading()
        button_pos = self.input_area.emoticon_btn.mapToGlobal(QPoint(0, 0))
        self.emoticon_picker.move(button_pos.x() - self.emoticon_picker.width() + 28, button_pos.y() - self.emoticon_picker.height() - 8)
        self.emoticon_picker.show()
        try:
            packages = await self.danmaku_client.fetch_live_emoticons()
        except Exception as exc:
            self.emoticon_picker.set_error(str(exc))
            return
        self.emoticon_picker.set_packages(packages)

    def trigger_send_live_emoticon(self, emoticon: LiveEmoticon):
        asyncio.create_task(self._send_live_emoticon_task(emoticon))

    async def _send_live_emoticon_task(self, emoticon: LiveEmoticon):
        if not self.danmaku_client:
            self.add_system_message("未连接直播间，无法发送", "error")
            return
        success, msg = await self.danmaku_client.send_live_emoticon(emoticon)
        if not success:
            self.add_system_message(f"发送失败: {msg}", "error")
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
pytest tests/test_danmaku_widget.py::test_danmaku_widget_source_wires_emoticon_picker_to_client_methods -q
```

Expected: PASS.

---

### Task 5: Verification And Manual Smoke

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_live_emoticons.py tests/test_danmaku_client.py tests/test_danmaku_widget.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run lint/format if available**

Run:

```bash
uv run ruff check src tests
```

Expected: PASS.

- [ ] **Step 4: Manual smoke with room 870691**

Run:

```bash
uv run bilihud
```

Manual checks:

- Connect to `870691`.
- Click the new emoticon button.
- Confirm tabs appear in order: `房间专属表情`, `UP主大表情`, `通用表情`.
- Confirm locked `UP主大表情` entries are disabled and show labels like `舰长`.
- Send an available room emoticon.
- Send a normal text danmaku.

Expected: picker opens, locked entries cannot send, available send either succeeds or returns a Bilibili error message that identifies the send payload adjustment needed.

---

## Plan Self-Review

- Spec coverage: covers v2 fetch, package ordering, per-package panes, locked styling, send blocking, send API extension, and tests.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency: `LiveEmoticon`, `LiveEmoticonPackage`, `fetch_live_emoticons`, and `send_live_emoticon` signatures are used consistently across tasks.
