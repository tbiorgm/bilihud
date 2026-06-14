from pathlib import Path

from PyQt6.QtGui import QImage

from bilihud import danmaku_widget


def test_danmaku_widget_does_not_manually_process_qt_events():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "QApplication.processEvents()" not in source


def test_danmaku_widget_imports_qimage_for_emoticon_loader():
    assert danmaku_widget.QImage is QImage


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


def test_danmaku_widget_emoticon_requests_include_bilibili_headers():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert 'request.setRawHeader(b"Referer", b"https://live.bilibili.com/")' in source
    assert "https://live.bilibili.com/" in source
    assert "QNetworkRequest.KnownHeaders.UserAgentHeader" in source
