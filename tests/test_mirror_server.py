import asyncio
import inspect
import json

from aiohttp import ClientSession, web

from bilihud.mirror_server import IMAGE_PROXY_HEADERS, MirrorServer, mirror_event_payload, mirror_html
from bilihud.mirror_state import MIRROR_EVENTS_ROUTE, MIRROR_IMAGE_ROUTE, MIRROR_ROUTE, MirrorState


def _site_port(site: web.TCPSite) -> int:
    sockets = site._server.sockets
    assert sockets is not None
    return sockets[0].getsockname()[1]


def test_mirror_routes_are_bilihud_named():
    assert MIRROR_ROUTE == "/bilihud-mirror"
    assert MIRROR_EVENTS_ROUTE == "/bilihud-mirror/events"
    assert MIRROR_IMAGE_ROUTE == "/bilihud-mirror/image"
    assert "obs" not in MIRROR_ROUTE.lower()
    assert "obs" not in MIRROR_EVENTS_ROUTE.lower()
    assert "obs" not in MIRROR_IMAGE_ROUTE.lower()


def test_mirror_html_uses_transparent_page_and_event_source():
    page = mirror_html(MIRROR_EVENTS_ROUTE)

    assert "background: transparent" in page
    assert f'new EventSource("{MIRROR_EVENTS_ROUTE}")' in page
    assert "/obs" not in page.lower()
    assert "textContent" in page
    assert 'createElement("img")' in page
    assert "proxyImageUrl(segment.url)" in page
    assert f'"{MIRROR_IMAGE_ROUTE}?url="' in page


def test_mirror_event_payload_serializes_named_event():
    payload = mirror_event_payload("append", {"seq": 1, "segments": []})

    assert payload.startswith("event: append\n")
    assert payload.endswith("\n\n")
    data_line = next(line for line in payload.splitlines() if line.startswith("data: "))
    assert json.loads(data_line.removeprefix("data: ")) == {"seq": 1, "segments": []}


def test_mirror_server_registers_sse_client_before_snapshot_write():
    source = inspect.getsource(MirrorServer._handle_events)

    assert source.index("self._clients.add(queue)") < source.index('mirror_event_payload("snapshot"')


def test_mirror_server_registers_image_proxy_route():
    source = inspect.getsource(MirrorServer.start)

    assert "self._handle_image" in source
    assert "MIRROR_IMAGE_ROUTE" in source


def test_mirror_image_proxy_fetches_image_with_bilibili_headers():
    async def run_test():
        seen_headers = {}

        async def handle_source_image(request: web.Request) -> web.Response:
            seen_headers["Referer"] = request.headers.get("Referer")
            seen_headers["User-Agent"] = request.headers.get("User-Agent")
            return web.Response(body=b"image-bytes", headers={"Content-Type": "image/png"})

        source_app = web.Application()
        source_app.router.add_get("/emote.png", handle_source_image)
        source_runner = web.AppRunner(source_app)
        await source_runner.setup()
        source_site = web.TCPSite(source_runner, "127.0.0.1", 0)
        await source_site.start()

        mirror_server = MirrorServer(MirrorState(), port=0)
        await mirror_server.start()

        try:
            source_url = f"http://127.0.0.1:{_site_port(source_site)}/emote.png"
            mirror_url = f"http://127.0.0.1:{_site_port(mirror_server._site)}{MIRROR_IMAGE_ROUTE}"

            async with ClientSession() as session:
                async with session.get(mirror_url, params={"url": source_url}) as response:
                    assert response.status == 200
                    assert await response.read() == b"image-bytes"
                    assert response.headers["Content-Type"] == "image/png"

            assert seen_headers == IMAGE_PROXY_HEADERS
        finally:
            await mirror_server.stop()
            await source_runner.cleanup()

    asyncio.run(run_test())
