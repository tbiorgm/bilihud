from dataclasses import dataclass

from bilihud.auth import AuthManager


@dataclass
class FakeCookie:
    name: str
    value: str


def test_load_auth_cookies_prefers_keyring(monkeypatch):
    manager = AuthManager()
    monkeypatch.setattr(manager, "load_cookies", lambda: {"SESSDATA": "keyring-sess", "bili_jct": "csrf"})

    cookies, from_keyring = manager.load_auth_cookies()

    assert cookies == {"SESSDATA": "keyring-sess", "bili_jct": "csrf"}
    assert from_keyring is True


def test_load_auth_cookies_uses_browser_when_keyring_is_empty(monkeypatch):
    manager = AuthManager()
    monkeypatch.setattr(manager, "load_cookies", lambda: None)
    monkeypatch.setattr(
        "bilihud.auth.load_bilibili_cookies",
        lambda: [FakeCookie("SESSDATA", "browser-sess"), FakeCookie("bili_jct", "browser-csrf")],
    )

    cookies, from_keyring = manager.load_auth_cookies()

    assert cookies == {"SESSDATA": "browser-sess", "bili_jct": "browser-csrf"}
    assert from_keyring is False


def test_load_auth_cookies_returns_empty_state_when_sources_fail(monkeypatch):
    manager = AuthManager()
    monkeypatch.setattr(manager, "load_cookies", lambda: None)

    def raise_browser_error():
        raise RuntimeError("browser unavailable")

    monkeypatch.setattr("bilihud.auth.load_bilibili_cookies", raise_browser_error)

    cookies, from_keyring = manager.load_auth_cookies()

    assert cookies == {}
    assert from_keyring is False
