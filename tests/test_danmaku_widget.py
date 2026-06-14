from pathlib import Path

from PyQt6.QtGui import QImage

from bilihud import danmaku_widget


def test_danmaku_widget_does_not_manually_process_qt_events():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "QApplication.processEvents()" not in source


def test_danmaku_widget_imports_qimage_for_emoticon_loader():
    assert danmaku_widget.QImage is QImage
