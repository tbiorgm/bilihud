import os
from pathlib import Path

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QFont, QImage
from PyQt6.QtWidgets import QApplication, QLabel

from bilihud import danmaku_widget
from bilihud.live_emoticons import LiveEmoticon, LiveEmoticonPackage

_QT_APP = None


def _app():
    global _QT_APP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


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


def test_danmaku_delegate_renders_local_system_messages():
    class SystemMessage:
        uname = " [系统]"
        msg = "BiliHUD Mirror 已启动: <url>"
        is_system_info = True
        is_system_error = False
        privilege_type = 0
        vip = False
        svip = False
        admin = False

    html = danmaku_widget.DanmakuDelegate().get_html_for_message(SystemMessage())

    assert "BiliHUD Mirror 已启动" in html
    assert "&lt;url&gt;" in html
    assert html.strip()


def test_danmaku_delegate_does_not_reuse_document_for_reused_message_id(monkeypatch):
    _app()

    class Message:
        privilege_type = 0
        vip = False
        svip = False
        admin = False

        def __init__(self, text: str):
            self.uname = "Locez"
            self.msg = text

    delegate = danmaku_widget.DanmakuDelegate()
    monkeypatch.setattr(danmaku_widget, "id", lambda _message: 7450109, raising=False)

    first_doc = delegate._get_document(Message("旧消息"), 320, QFont())
    second_doc = delegate._get_document(Message("新消息"), 320, QFont())

    assert "旧消息" in first_doc.toPlainText()
    assert "新消息" in second_doc.toPlainText()
    assert "旧消息" not in second_doc.toPlainText()


def test_danmaku_widget_prunes_history_before_scrolling_to_bottom():
    class Message:
        uname = "Locez"
        msg = "新弹幕"
        privilege_type = 0
        vip = False
        svip = False
        admin = False

    class RemovedItem:
        def data(self, _role):
            return Message()

    class FakeDelegate:
        def forget_message(self, _message):
            calls.append("forget")

    class FakeList:
        def __init__(self):
            self._count = 200

        def addItem(self, _item):
            calls.append("add")
            self._count += 1

        def count(self):
            return self._count

        def takeItem(self, _row):
            calls.append("take")
            self._count -= 1
            return RemovedItem()

        def itemDelegate(self):
            return FakeDelegate()

        def scrollToBottom(self):
            calls.append("scroll")

    class MirrorState:
        def add_message(self, _message):
            return {"seq": 1}

    calls = []
    class Widget:
        pass

    widget = Widget()
    widget.danmaku_list = FakeList()
    widget.mirror_state = MirrorState()
    widget.mirror_server = None

    danmaku_widget.DanmakuWidget.add_message(widget, Message())

    assert calls.index("take") < calls.index("scroll")


def test_modern_input_widget_exposes_emoticon_button_signal():
    _app()
    widget = danmaku_widget.ModernInputWidget()

    seen = []
    widget.emoticon_requested.connect(lambda: seen.append(True))
    widget.emoticon_btn.click()

    assert seen == [True]


def test_modern_input_widget_can_hide_emoticon_button():
    _app()
    widget = danmaku_widget.ModernInputWidget(show_emoticon_button=False)

    assert widget.emoticon_btn.isHidden()


def test_emoticon_picker_does_not_emit_locked_emoticons():
    _app()
    picker = danmaku_widget.EmoticonPickerPopup()
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
    assert "#FF6699" in cell.styleSheet()
    assert not cell.isEnabled()


def test_emoticon_picker_hides_after_available_emoticon_click():
    app = _app()
    picker = danmaku_widget.EmoticonPickerPopup()
    emoticon = LiveEmoticon(
        emoji="啊",
        url="http://i0.hdslb.com/bfs/live/a.png",
        width=200,
        height=60,
        perm=1,
        unique="official_331",
        emoticon_id=331,
    )
    package = LiveEmoticonPackage(1, "通用表情", 1, 1, (emoticon,))
    emitted = []
    picker.emoticon_selected.connect(emitted.append)
    picker.set_packages([package])
    picker.show()
    app.processEvents()

    picker._emoticon_buttons[0].click()

    assert emitted == [emoticon]
    assert not picker.isVisible()


def test_emoticon_picker_deletes_old_tab_pages_when_refreshing():
    app = _app()
    picker = danmaku_widget.EmoticonPickerPopup()

    for _ in range(5):
        picker.set_loading()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    labels = [label.text() for label in picker.findChildren(QLabel)]

    assert labels == ["加载中..."]


def test_emoticon_picker_keeps_one_tab_per_package():
    _app()
    picker = danmaku_widget.EmoticonPickerPopup()
    emoticon = LiveEmoticon(
        emoji="啊",
        url="http://i0.hdslb.com/bfs/live/a.png",
        width=200,
        height=60,
        perm=1,
        unique="official_331",
        emoticon_id=331,
    )
    packages = [
        LiveEmoticonPackage(1, "通用表情", 1, 1, (emoticon,)),
        LiveEmoticonPackage(2, "UP主大表情", 2, 1, (emoticon,)),
    ]

    picker.set_packages(packages)

    assert picker.tabs.count() == 2
    assert [picker.tabs.tabText(index) for index in range(picker.tabs.count())] == ["通用表情", "UP主大表情"]


def test_danmaku_widget_source_wires_emoticon_picker_to_client_methods():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "self.input_area.emoticon_requested.connect(self.open_emoticon_picker)" in source
    assert "await self.danmaku_client.fetch_live_emoticons()" in source
    assert "await self.danmaku_client.send_live_emoticon(emoticon)" in source
