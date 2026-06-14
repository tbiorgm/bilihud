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
    assert "from .mirror_settings_dialog import MirrorSettingsDialog" in source


def test_danmaku_widget_add_message_publishes_to_mirror():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "entry = self.mirror_state.add_message(message)" in source
    assert "self.mirror_server.publish_append(entry)" in source


def test_danmaku_widget_exposes_bilihud_mirror_tray_action():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert 'QAction("BiliHUD Mirror", self)' in source
    assert source.count('QAction("BiliHUD Mirror", self)') == 1
    assert "open_mirror_settings" in source
    assert "MIRROR_ROUTE" in source
    assert "显示 Mirror URL" not in source
    assert "启动 BiliHUD Mirror" not in source
    assert "停止 BiliHUD Mirror" not in source
    assert "obs-mirror" not in source
    assert "obs-danmaku" not in source


def test_danmaku_widget_opens_single_mirror_settings_dialog():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "def open_mirror_settings(self):" in source
    assert "MirrorSettingsDialog(self)" in source
    assert "_mirror_settings_dialog" in source


def test_danmaku_widget_keeps_mirror_enabled_config_when_quitting():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "await self.shutdown_mirror_server()" in source
    assert "def mirror_status_text(self)" in source
    assert "self.mirror_error" in source
    assert 'return f"启动失败: {self.mirror_error}"' in source
    assert "async def set_mirror_enabled(self, enabled: bool)" in source
    assert source.index("async def shutdown_mirror_server") > source.index("async def stop_mirror_server")
    shutdown_body = source.split("async def shutdown_mirror_server", 1)[1]
    assert 'save_config({"mirror_enabled": False' not in shutdown_body


def test_danmaku_widget_emoticon_requests_include_bilibili_headers():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert 'request.setRawHeader(b"Referer", b"https://live.bilibili.com/")' in source
    assert "https://live.bilibili.com/" in source
    assert "QNetworkRequest.KnownHeaders.UserAgentHeader" in source
