from bilihud.live_api import app_sign, format_face_auth_url, parse_stream_credentials


def test_app_sign_sorts_params_adds_appkey_and_signs():
    params = {"ts": "1700000000000", "system_version": "2"}

    signed = app_sign(params)

    assert (
        signed
        == "appkey=aae92bc66f3edfab&system_version=2&ts=1700000000000"
        "&sign=0145560363728c74c6e3f829a34d8991"
    )
    assert params == {"ts": "1700000000000", "system_version": "2"}


def test_parse_stream_credentials_extracts_primary_and_protocol_streams():
    payload = {
        "rtmp": {"addr": "rtmp://primary", "code": "primary-key"},
        "protocols": [
            {"protocol": "rtmp", "addr": "rtmp://backup", "code": "backup-key"},
            {"protocol": "srt", "addr": "srt://primary", "code": "srt-key"},
        ],
    }

    credentials = parse_stream_credentials(payload)

    assert [(item.label, item.address, item.key) for item in credentials] == [
        ("rtmp-1", "rtmp://primary", "primary-key"),
        ("rtmp-2", "rtmp://backup", "backup-key"),
        ("srt-1", "srt://primary", "srt-key"),
    ]


def test_parse_stream_credentials_skips_invalid_or_unknown_protocols():
    payload = {
        "rtmp": {"addr": "", "code": "missing-address"},
        "protocols": [
            {"protocol": "rtmp", "addr": "rtmp://valid", "code": "valid-key"},
            {"protocol": "rtmp", "addr": "rtmp://missing-key", "code": ""},
            {"protocol": "srt", "addr": "", "code": "missing-address"},
            {"protocol": "hls", "addr": "https://ignored", "code": "ignored"},
        ],
    }

    credentials = parse_stream_credentials(payload)

    assert [(item.label, item.address, item.key) for item in credentials] == [
        ("rtmp-1", "rtmp://valid", "valid-key"),
    ]


def test_format_face_auth_url_uses_uid():
    assert (
        format_face_auth_url("12345")
        == "https://www.bilibili.com/blackboard/live/face-auth-middle.html?source_event=400&mid=12345"
    )
