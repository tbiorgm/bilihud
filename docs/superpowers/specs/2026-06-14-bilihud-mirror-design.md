# BiliHUD Mirror Design

## Context

BiliHUD currently renders danmaku for the local streamer HUD. The same content can be useful outside the local overlay, especially when a broadcaster wants viewers to see the danmaku layer in a streaming or recording scene.

The first consumer is expected to be an OBS Browser Source, but the feature should not be named or modeled as OBS-specific. A browser, projection tool, or recording pipeline should be able to consume the same mirror page.

## Goal

Expose a local browser-rendered mirror of BiliHUD's danmaku content:

- URL: `http://127.0.0.1:<port>/bilihud-mirror`
- Default port: `2233`.
- Sync local HUD danmaku content and visual style semantics.
- Let external tools place, scale, crop, and capture the mirror page themselves.
- Keep mirror naming and core implementation free of OBS-specific semantics.

## Non-Goals

- Do not capture the Qt HUD window.
- Do not mirror the local HUD window position or size.
- Do not mirror top bar controls, room ID controls, lock-through state, or the danmaku input box.
- Do not require OBS to use the mirror.
- Do not make the mirror the source of truth for local HUD rendering.
- Do not add a global Bilibili emoticon catalog or extra Bilibili API fetches as part of this feature.

## Product Semantics

The mirror represents the local HUD's danmaku content area, not the full application chrome.

Synchronized:

- Recent danmaku list and ordering.
- Existing local retention behavior, such as keeping only the newest messages.
- User names and color semantics.
- Danmaku text style semantics.
- Pure emoticons from `emoticon_options`.
- Inline emoticons from `mode_info.extra.emots`.
- System messages that are shown in the local danmaku list, if they are part of the same list.
- Visual settings that affect the danmaku content area, such as font family, font sizes, content colors, background opacity, and border radius.

Not synchronized:

- Local HUD screen position.
- Local HUD width or height.
- OBS/source width, height, position, crop, or transform.
- Header buttons, room ID text field, connect button, lock-through button, close button.
- Bottom input field and send button.
- Whether the local HUD is in click-through mode.

External tools own their own layout. For OBS specifically, the user can resize and position the Browser Source in the OBS scene without BiliHUD changing those dimensions.

## Architecture

### Mirror Server

Add a small local server owned by BiliHUD. It binds to loopback only.

Default URL shape:

```text
http://127.0.0.1:<port>/bilihud-mirror
```

The default concrete URL is:

```text
http://127.0.0.1:2233/bilihud-mirror
```

Suggested endpoints:

- `GET /bilihud-mirror`: transparent HTML page.
- `GET /bilihud-mirror/events`: event stream for initial state and live updates.
- `GET /bilihud-mirror/assets/...`: optional static assets, if needed later.

The initial version can use Server-Sent Events because traffic is one-way from BiliHUD to the mirror page. WebSocket is acceptable if the implementation already has a cleaner async path for it, but the page should not need to send commands back to BiliHUD.

The server should start only when the mirror feature is enabled. It should stop on BiliHUD exit.

### Mirror State

Keep a lightweight mirror state model separate from Qt widgets:

- message ID or sequence number;
- message kind, such as danmaku, gift, interaction, or system;
- user display name;
- user color/style class;
- content as structured segments, not raw Qt HTML;
- emoticon URLs and display sizes;
- timestamp if useful for animations or pruning.

The local Qt HUD and the mirror page should be fed from the same incoming danmaku events where practical, but neither should scrape rendered output from the other.

The mirror state should cap memory using the same message count policy as the local HUD, or a configurable mirror-specific count if local behavior later becomes unsuitable for streaming.

### Mirror Page

The page renders a transparent background by default.

It should:

- render the current snapshot on load;
- append new events in order;
- prune old messages according to the state limit;
- render pure and inline emoticons using `<img>`;
- escape text content by construction;
- handle event stream disconnects by showing stale content rather than clearing immediately;
- reconnect automatically when the stream returns.

The page should not contain OBS-specific labels, names, or assumptions.

### Style Sync

Mirror style should follow the local HUD content style semantically, not by copying Qt pixels.

The first implementation should encode the current HUD visual constants into CSS:

- content font family and size;
- username color semantics;
- text color;
- line height;
- background opacity and rounded rectangle style;
- emoticon max height and max width.

If BiliHUD later exposes user-configurable visual settings, those settings should update both local HUD and mirror CSS through the same config model.

## OBS Integration Boundary

OBS integration is optional and sits outside the mirror core.

If a later UI action creates or updates an OBS Browser Source, it should point to:

```text
http://127.0.0.1:<port>/bilihud-mirror
```

With the default port:

```text
http://127.0.0.1:2233/bilihud-mirror
```

Names in OBS can use `BiliHUD Mirror`, but the mirror server and page should not use OBS-specific route names such as `/obs-mirror` or `/obs-danmaku`.

Failure to connect to OBS must not disable the mirror page. The user can still add the URL manually.

## Configuration

Suggested config keys:

- `mirror_enabled`: boolean.
- `mirror_port`: integer, default `2233`.

The server should bind only to `127.0.0.1` by default. Exposing the mirror to LAN is out of scope for the first version because danmaku content and user names are being re-served from the local machine.

If the configured port is unavailable, BiliHUD should either:

- choose another available loopback port and show the active URL; or
- fail clearly and keep the local HUD usable.

The first implementation should prefer `2233` if available, with clear fallback messaging if it is occupied.

## Data Flow

1. BiliHUD starts and loads config.
2. If mirror is enabled, BiliHUD starts the Mirror Server on loopback.
3. User or external tool opens `/bilihud-mirror`.
4. The page receives an initial snapshot from `/bilihud-mirror/events`.
5. BiliHUD receives a danmaku event from the live WebSocket.
6. BiliHUD updates the local HUD.
7. BiliHUD converts the same event into mirror state and publishes it to connected mirror pages.
8. Mirror pages append the message and prune old messages.

## Error Handling

- If Mirror Server fails to start, show a local status message and keep local HUD behavior unchanged.
- If a mirror page disconnects, keep local HUD behavior unchanged.
- If an emoticon image fails to load in the browser, preserve the message text/alt content where possible.
- If an event cannot be serialized, log it and skip only that mirror event.
- If no mirror clients are connected, keep only the capped mirror snapshot and do not buffer unbounded events.

## Testing

Unit tests should cover:

- conversion from `DanmakuMessage` to mirror state;
- pure emoticon segment conversion;
- inline emoticon segment conversion;
- HTML/text escaping requirements in the serialized state;
- message cap/pruning behavior;
- route naming uses `/bilihud-mirror` and not OBS-specific paths.

Integration-level tests can cover:

- starting the server on loopback;
- serving the mirror HTML;
- event stream initial snapshot shape;
- publishing a new message to connected clients.

Manual verification should cover:

- opening the mirror URL in a browser;
- adding the URL as an OBS Browser Source;
- transparent background rendering;
- local HUD and mirror receiving the same danmaku sequence;
- OBS source resizing without BiliHUD overriding width or height.
