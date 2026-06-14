import inspect
import json

from bilihud.mirror_server import MirrorServer, mirror_event_payload, mirror_html
from bilihud.mirror_state import MIRROR_EVENTS_ROUTE, MIRROR_ROUTE


def test_mirror_routes_are_bilihud_named():
    assert MIRROR_ROUTE == "/bilihud-mirror"
    assert MIRROR_EVENTS_ROUTE == "/bilihud-mirror/events"
    assert "obs" not in MIRROR_ROUTE.lower()
    assert "obs" not in MIRROR_EVENTS_ROUTE.lower()


def test_mirror_html_uses_transparent_page_and_event_source():
    page = mirror_html(MIRROR_EVENTS_ROUTE)

    assert "background: transparent" in page
    assert f'new EventSource("{MIRROR_EVENTS_ROUTE}")' in page
    assert "/obs" not in page.lower()
    assert "textContent" in page
    assert 'createElement("img")' in page


def test_mirror_event_payload_serializes_named_event():
    payload = mirror_event_payload("append", {"seq": 1, "segments": []})

    assert payload.startswith("event: append\n")
    assert payload.endswith("\n\n")
    data_line = next(line for line in payload.splitlines() if line.startswith("data: "))
    assert json.loads(data_line.removeprefix("data: ")) == {"seq": 1, "segments": []}


def test_mirror_server_registers_sse_client_before_snapshot_write():
    source = inspect.getsource(MirrorServer._handle_events)

    assert source.index("self._clients.add(queue)") < source.index('mirror_event_payload("snapshot"')
