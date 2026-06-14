from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from .mirror_state import MIRROR_DEFAULT_PORT, MIRROR_EVENTS_ROUTE, MIRROR_ROUTE, MirrorState


def mirror_event_payload(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def mirror_html(events_route: str = MIRROR_EVENTS_ROUTE) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: transparent;
      overflow: hidden;
      font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    }}
    #panel {{
      box-sizing: border-box;
      width: 100vw;
      min-height: 100vh;
      padding: 10px;
      background: rgba(0, 0, 0, 0.47);
      border-radius: 8px;
      color: white;
    }}
    .message {{
      line-height: 1.2;
      margin: 0 0 4px;
      font-size: 13px;
      font-weight: 500;
    }}
    .user {{
      font-size: 12px;
      font-weight: 700;
    }}
    .colon {{
      color: white;
      font-size: 12px;
    }}
    .emoticon {{
      vertical-align: middle;
      max-height: 34px;
      max-width: 140px;
    }}
  </style>
</head>
<body>
  <div id="panel"></div>
  <script>
    const panel = document.getElementById("panel");
    const maxMessages = 200;

    function appendText(parent, text) {{
      parent.appendChild(document.createTextNode(text));
    }}

    function renderEntry(entry) {{
      const row = document.createElement("div");
      row.className = "message";
      row.dataset.seq = String(entry.seq);

      const user = document.createElement("span");
      user.className = "user";
      user.style.color = entry.userColor || "#66CCFF";
      user.textContent = entry.user || "";
      row.appendChild(user);

      const colon = document.createElement("span");
      colon.className = "colon";
      colon.textContent = " : ";
      row.appendChild(colon);

      for (const segment of entry.segments || []) {{
        if (segment.type === "image") {{
          const img = document.createElement("img");
          img.className = "emoticon";
          img.src = segment.url;
          img.alt = segment.text || "";
          img.width = segment.width || 34;
          img.height = segment.height || 34;
          row.appendChild(img);
        }} else {{
          appendText(row, segment.text || "");
        }}
      }}

      panel.appendChild(row);
      while (panel.children.length > maxMessages) {{
        panel.removeChild(panel.firstElementChild);
      }}
      window.scrollTo(0, document.body.scrollHeight);
    }}

    function renderSnapshot(entries) {{
      panel.replaceChildren();
      for (const entry of entries || []) {{
        renderEntry(entry);
      }}
    }}

    const events = new EventSource("{events_route}");
    events.addEventListener("snapshot", event => renderSnapshot(JSON.parse(event.data)));
    events.addEventListener("append", event => renderEntry(JSON.parse(event.data)));
  </script>
</body>
</html>"""


class MirrorServer:
    def __init__(self, state: MirrorState, host: str = "127.0.0.1", port: int = MIRROR_DEFAULT_PORT):
        self.state = state
        self.host = host
        self.port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._clients: set[asyncio.Queue[str]] = set()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{MIRROR_ROUTE}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get(MIRROR_ROUTE, self._handle_page)
        app.router.add_get(MIRROR_EVENTS_ROUTE, self._handle_events)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

    async def stop(self) -> None:
        for queue in list(self._clients):
            queue.put_nowait("")
        self._clients.clear()
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def _handle_page(self, _request: web.Request) -> web.Response:
        return web.Response(text=mirror_html(), content_type="text/html")

    async def _handle_events(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._clients.add(queue)
        await response.write(mirror_event_payload("snapshot", self.state.snapshot()).encode("utf-8"))

        try:
            while True:
                payload = await queue.get()
                if not payload:
                    break
                await response.write(payload.encode("utf-8"))
        except (asyncio.CancelledError, ConnectionResetError, RuntimeError):
            pass
        finally:
            self._clients.discard(queue)
        return response

    def publish_append(self, entry: dict[str, Any]) -> None:
        payload = mirror_event_payload("append", entry)
        for queue in list(self._clients):
            queue.put_nowait(payload)
