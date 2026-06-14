from pathlib import Path

from bilihud.mirror_settings_dialog import MirrorSettingsDialog


def test_mirror_settings_dialog_exposes_url_and_persistent_enable_controls():
    source = Path("src/bilihud/mirror_settings_dialog.py").read_text(encoding="utf-8")

    assert MirrorSettingsDialog.__name__ == "MirrorSettingsDialog"
    assert "启用 BiliHUD Mirror" in source
    assert "复制 URL" in source
    assert "self.url_input.setReadOnly(True)" in source
    assert "set_mirror_state" in source
    assert "mirror_url" in source
    assert "set_mirror_enabled" in source
    assert "mirror_status_text" in source
