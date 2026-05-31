# -*- coding: utf-8 -*-
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import urlencode

import aiohttp

BASE_URL = "https://api.live.bilibili.com"
APP_KEY = "aae92bc66f3edfab"
APP_SECRET = "af125a0d5279fd576c1b4418a3e8276d"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
)


@dataclass(frozen=True)
class StreamCredential:
    label: str
    address: str
    key: str


@dataclass(frozen=True)
class LiveVersion:
    curr_version: str
    build: int


@dataclass(frozen=True)
class StartLiveResult:
    code: int
    message: str
    data: dict[str, Any]


class LiveApiError(RuntimeError):
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


def app_sign(params: Mapping[str, str]) -> str:
    signed_params = {str(key): str(value) for key, value in params.items()}
    signed_params["appkey"] = APP_KEY
    query = urlencode(sorted(signed_params.items()))
    sign = hashlib.md5((query + APP_SECRET).encode("utf-8")).hexdigest()
    return f"{query}&sign={sign}"


def format_face_auth_url(uid: str | int) -> str:
    return (
        "https://www.bilibili.com/blackboard/live/face-auth-middle.html"
        f"?source_event=400&mid={uid}"
    )


def get_cookie_value(session: aiohttp.ClientSession, name: str) -> Optional[str]:
    for cookie in session.cookie_jar:
        if cookie.key == name:
            return cookie.value
    return None


def parse_stream_credentials(start_live_data: Mapping[str, Any]) -> list[StreamCredential]:
    credentials: list[StreamCredential] = []
    counters = {"rtmp": 0, "srt": 0}

    rtmp = start_live_data.get("rtmp")
    if isinstance(rtmp, Mapping):
        addr = str(rtmp.get("addr") or "")
        code = str(rtmp.get("code") or "")
        if addr and code:
            counters["rtmp"] += 1
            credentials.append(StreamCredential("rtmp-1", addr, code))

    protocols = start_live_data.get("protocols") or []
    if not isinstance(protocols, list):
        protocols = []

    for protocol_data in protocols:
        if not isinstance(protocol_data, Mapping):
            continue
        protocol = str(protocol_data.get("protocol") or "").lower()
        if protocol not in counters:
            continue
        addr = str(protocol_data.get("addr") or "")
        code = str(protocol_data.get("code") or "")
        if not addr or not code:
            continue
        counters[protocol] += 1
        credentials.append(StreamCredential(f"{protocol}-{counters[protocol]}", addr, code))

    return sorted(credentials, key=lambda item: item.label)


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    endpoint: str,
    *,
    data: Optional[Mapping[str, str]] = None,
    headers: Optional[Mapping[str, str]] = None,
    require_sign: bool = False,
    raw: bool = False,
) -> Any:
    url = f"{BASE_URL}{endpoint}"
    request_headers = {
        "Accept": "*/*",
        "User-Agent": USER_AGENT,
        **dict(headers or {}),
    }
    body = None

    if method.upper() != "GET" and data is not None:
        request_headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        body = app_sign(data) if require_sign else urlencode(data)

    async with session.request(method.upper(), url, headers=request_headers, data=body) as response:
        if response.status != 200:
            raise LiveApiError(f"HTTP错误: {response.status}")
        payload = await response.json()

    if raw:
        return payload

    if payload.get("code") != 0 or payload.get("data") is None:
        raise LiveApiError(
            f"API错误: {payload.get('message') or 'Unknown Error'} ({payload.get('code')})",
            payload.get("code"),
        )

    return payload["data"]


async def get_area_list(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    data = await _request_json(
        session,
        "GET",
        "/room/v1/Area/getList?show_pinyin=1",
        headers={"Origin": BASE_URL},
    )
    return list(data)


async def get_live_version(session: aiohttp.ClientSession, now_ms: Optional[int] = None) -> LiveVersion:
    timestamp = str(now_ms if now_ms is not None else int(time.time() * 1000))
    query = app_sign({"system_version": "2", "ts": timestamp})
    data = await _request_json(
        session,
        "GET",
        f"/xlive/app-blink/v1/liveVersionInfo/getHomePageLiveVersion?{query}",
        headers={"Origin": BASE_URL},
    )
    return LiveVersion(curr_version=str(data["curr_version"]), build=int(data["build"]))


def require_csrf(session: aiohttp.ClientSession) -> str:
    csrf = get_cookie_value(session, "bili_jct")
    if not csrf:
        raise LiveApiError("未找到CSRF Token，请先扫码登录")
    return csrf


async def update_room_title(session: aiohttp.ClientSession, room_id: int, title: str) -> None:
    csrf = require_csrf(session)
    await _request_json(
        session,
        "POST",
        "/room/v1/Room/update",
        headers={"Origin": BASE_URL},
        data={
            "room_id": str(room_id),
            "csrf": csrf,
            "csrf_token": csrf,
            "title": title,
            "platform": "pc_link",
        },
    )


async def update_room_area(session: aiohttp.ClientSession, room_id: int, area_id: str) -> None:
    csrf = require_csrf(session)
    await _request_json(
        session,
        "POST",
        "/room/v1/Room/update",
        headers={"Origin": BASE_URL},
        data={
            "room_id": str(room_id),
            "csrf": csrf,
            "csrf_token": csrf,
            "area_id": area_id,
            "platform": "pc_link",
        },
    )


async def start_live(
    session: aiohttp.ClientSession,
    room_id: int,
    area_id: str,
    version: str,
    build: str,
    now_ms: Optional[int] = None,
) -> StartLiveResult:
    csrf = require_csrf(session)
    timestamp = str(now_ms if now_ms is not None else int(time.time() * 1000))
    payload = await _request_json(
        session,
        "POST",
        "/room/v1/Room/startLive",
        headers={"Origin": BASE_URL},
        data={
            "room_id": str(room_id),
            "platform": "pc_link",
            "backup_stream": "0",
            "csrf": csrf,
            "csrf_token": csrf,
            "area_v2": area_id,
            "version": version,
            "build": build,
            "ts": timestamp,
        },
        require_sign=True,
        raw=True,
    )
    return StartLiveResult(
        code=int(payload.get("code", -1)),
        message=str(payload.get("message") or ""),
        data=dict(payload.get("data") or {}),
    )


async def stop_live(session: aiohttp.ClientSession, room_id: int) -> None:
    csrf = require_csrf(session)
    await _request_json(
        session,
        "POST",
        "/room/v1/Room/stopLive",
        headers={"Origin": BASE_URL},
        data={
            "room_id": str(room_id),
            "csrf": csrf,
            "platform": "pc_link",
            "csrf_token": csrf,
        },
    )
