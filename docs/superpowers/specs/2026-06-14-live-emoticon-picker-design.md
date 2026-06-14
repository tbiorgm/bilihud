# Live Emoticon Picker Design

## Goal

Add a compact emoticon picker beside the BiliHUD danmaku input so users can send Bilibili live-room emoticons without opening the browser chat panel.

The picker must prioritize room-specific emoticons, preserve Bilibili permission semantics, and avoid sending locked emoticons.

## Scope

In scope:

- Add an emoticon button between the existing input field and send button.
- Fetch room emoticons from Bilibili live v2 API:
  `https://api.live.bilibili.com/xlive/web-ucenter/v2/emoticon/GetEmoticons?platform=pc&room_id=<room_id>`.
- Show each returned package as a separate tab/pane, similar to chat applications.
- Sort package panes with room-specific packages first:
  1. `房间专属表情`
  2. `UP主大表情`
  3. `通用表情`
  4. any other returned packages in API order
- Render each emoticon image in a grid.
- Show locked emoticons with a disabled visual style and do not send them.
- Send available live emoticons from the picker.

Out of scope for the first version:

- The broader Bilibili web reply emoticon catalog from `api.bilibili.com/x/emote/user/panel/web?business=reply`.
- Recent/favorite emoticons.
- Search.
- Persisting selected package tab.
- Recreating the exact Bilibili browser panel styling.

## API Semantics

The v2 API requires login. Without login it returns `code=-101`.

The relevant response shape is:

```json
{
  "code": 0,
  "data": {
    "data": [
      {
        "pkg_id": 428,
        "pkg_name": "UP主大表情",
        "pkg_type": 2,
        "pkg_perm": 1,
        "emoticons": [
          {
            "emoji": "打call",
            "url": "http://i0.hdslb.com/bfs/garb/example.png",
            "width": 162,
            "height": 162,
            "perm": 1,
            "identity": 4,
            "unlock_show_text": "粉丝团",
            "unlock_show_color": "#FF6699",
            "emoticon_unique": "room_870691_1149",
            "emoticon_id": 1149
          }
        ]
      }
    ]
  }
}
```

Permission rules:

- `perm == 1`: the emoticon is available and may be sent.
- `perm != 1`: the emoticon is locked and must not be sent.
- `unlock_show_text` is the user-facing lock label, such as `粉丝团`, `lv.3`, `舰长`, `提督`, or `总督`.
- `unlock_show_color` should be used for the lock label when present.
- `unlock_need_level`, `unlock_need_gift`, and `identity` are preserved in the parsed model for diagnostics and tooltips, but the UI sendability decision is based on `perm`.

Observed `870691` behavior:

- `房间专属表情`: all available.
- `UP主大表情`: mixed available and locked entries.
- `通用表情`: all available.

## UI Behavior

The local HUD input row becomes:

```text
[ input field                  ] [emoticon button] [发送]
```

Clicking the emoticon button opens a small frameless popup anchored near the button. The popup contains:

- A horizontal package tab bar.
- A scrollable grid for the selected package.
- A loading state while fetching.
- An empty/error state if the room has no returned emoticons or the request fails.

Tab labels should be short and stable. Use the package name when it fits; otherwise truncate visually.

Available emoticon cells:

- show the image at a consistent thumbnail size;
- show a tooltip with the `emoji` name;
- send on click.

Locked emoticon cells:

- show the image with reduced opacity;
- show the `unlock_show_text` label when present;
- use the `unlock_show_color` for the label when present;
- show a tooltip with the unlock label;
- ignore click/send.

The popup should reuse BiliHUD's existing dark glass visual language and must stay readable over arbitrary page backgrounds.

## Data Flow

`DanmakuClient` owns the authenticated `aiohttp.ClientSession`, so it should also expose room emoticon fetching and sending.

Proposed modules and responsibilities:

- `live_emoticons.py`
  - dataclasses for `LiveEmoticon` and `LiveEmoticonPackage`;
  - parser for v2 response payload;
  - package sorting helper.
- `DanmakuClient.fetch_live_emoticons()`
  - fetches v2 API using the existing session;
  - caches successful package results for 60 seconds per client instance;
  - returns parsed packages;
  - reports Bilibili API errors as user-readable failures.
- `DanmakuClient.send_live_emoticon(emoticon)`
  - sends a pure live emoticon using `/msg/send`;
  - sends through the WBI-signed `/msg/send?web_location=444.8&w_rid=...&wts=...` URL;
  - starts with `dm_type=1`, `emoticonOptions=[object Object]`, `data_extend={"trackid":"-99998"}`, and `msg=<emoticon_unique>`;
  - returns the same `(success, message)` shape as `send_danmaku`.
- `EmoticonPickerPopup`
  - Qt popup for package tabs and image grid;
  - loads thumbnail images with Bilibili referer/user-agent headers;
  - emits selected available emoticons.
- `ModernInputWidget`
  - adds the emoticon button and signal;
  - keeps text sending behavior unchanged.
- `DanmakuWidget`
  - connects the button to the popup;
  - fetches packages through the active `DanmakuClient`;
  - displays send failures as existing system messages.

## Sending Semantics

The picker sends only available v2 live emoticons.

Package named `emoji` uses Bilibili's text escape path. The clicked name is sent through the normal text danmaku endpoint as `[name]`, preserving already-bracketed values like `[dog]`.

Other v2 live emoticon packages use the pure emoticon path. Initial request body extends the existing text danmaku request:

```text
bubble=0
msg=<emoticon_unique>
color=16777215
mode=1
fontsize=25
rnd=<timestamp>
roomid=<room_id>
csrf=<bili_jct>
csrf_token=<bili_jct>
dm_type=1
emoticonOptions=[object Object]
data_extend={"trackid":"-99998"}
```

If Bilibili rejects this shape during manual verification, the implementation should keep the fetch/picker work and update only the send payload once the correct field names are observed.

Locked emoticons are not sent, even if the user clicks repeatedly.

## Error Handling

- If the user is not connected to a room, opening the picker shows a system message or disabled/empty popup state.
- If login is missing or expired, the fetch error should tell the user to reconnect or log in.
- Failed fetches are not cached, so a later retry can recover immediately.
- If the v2 API returns no packages, show an empty state.
- If an image fails to load, keep the cell present with its text tooltip/name.
- If sending fails, use the existing `发送失败: ...` system message path.

## Tests

Unit tests:

- Parse v2 payload into packages and emoticons.
- Sort `房间专属表情`, `UP主大表情`, and `通用表情` before other packages.
- Treat `perm == 1` as available and `perm != 1` as locked.
- Preserve lock labels and colors.
- Build the live emoticon send payload with `dm_type=1`, `emoticonOptions=[object Object]`, and `data_extend={"trackid":"-99998"}`.
- Send live emoticons as `multipart/form-data` through the WBI-signed `/msg/send?web_location=444.8&w_rid=...&wts=...` URL.
- Ensure locked emoticons do not emit/send from the picker.

Manual verification:

- Connect to room `870691`.
- Open the picker.
- Confirm tabs appear in order: `房间专属表情`, `UP主大表情`, `通用表情`.
- Confirm locked `UP主大表情` entries are dimmed and cannot send.
- Send an available room-specific emoticon and confirm it appears in BiliHUD and Bilibili chat.
- Confirm text danmaku sending still works.

## Non-Goals And Constraints

- Do not change mirror behavior as part of this feature.
- Do not change quit/live-control semantics.
- Do not read browser cookies directly for this feature; use the existing BiliHUD authenticated session.
- Keep the UI compact because it lives inside a small HUD.
