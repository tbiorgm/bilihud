# BiliHUD Live Control State Semantics Design

## Context

BiliHUD live control coordinates two different systems:

- Bilibili live room state, exposed through Bilibili live APIs such as `get_room_info`, `start_live`, and `stop_live`.
- Local OBS output state, exposed through OBS WebSocket.

These states can diverge. Examples:

- BiliHUD starts live, then exits. OBS keeps pushing because process exit must not stop OBS.
- User manually stops OBS after BiliHUD exits. Bilibili may still report the room as live for some time or until `stop_live` is called.
- User starts OBS manually and pushes to an unknown target while Bilibili is not live.
- BiliHUD restarts while Bilibili is live and OBS is still pushing. In-memory flags such as `_obs_streaming_started` are lost.

The current implementation uses Bilibili `live_status` for the primary start/stop buttons, but OBS side effects partly depend on memory-only flags (`_obs_streaming_started` and `_obs_connected`). After restart, those flags no longer describe the real OBS state.

## Goal

Define a clear, durable state contract for live control:

- Bilibili `live_status` is the source of truth for whether the room is live.
- OBS state never overrides Bilibili `live_status`.
- OBS state is checked at action time when a start/stop action may affect local OBS output.
- BiliHUD process exit does not stop OBS push.
- Restarting BiliHUD should not make OBS side-effect decisions depend on stale or missing in-memory flags.

## Non-Goals

- Do not infer Bilibili live state from OBS output state.
- Do not disable "开始直播" only because OBS is already pushing.
- Do not disable "停止直播" only because OBS is not pushing.
- Do not automatically stop OBS when BiliHUD exits or when the live control dialog closes.
- Do not add persistent storage for stream credentials or "BiliHUD owns this OBS stream" state in this change.
- Do not require OBS WebSocket to be available before users can start or stop the Bilibili live room.

## State Model

### Primary State: Bilibili Live Status

`LiveControlDialog.is_live_active` represents Bilibili room live status only.

It is set from:

- `get_room_info(...).is_live` on dialog load or room refresh.
- Successful `start_live` response code `0`.
- Successful `stop_live`.

It is not set from:

- OBS process running state.
- OBS WebSocket connection state.
- OBS `GetStreamStatus`.
- BiliHUD's previous in-memory `_obs_streaming_started` flag.

Button enablement follows this rule:

- `开始直播` is enabled only when the form is valid, CSRF is available, and `is_live_active` is false.
- `停止直播` is enabled only when room ID and CSRF are available and `is_live_active` is true.

### Secondary State: OBS Local Output Status

OBS state describes local output only. It may be:

- unavailable because OBS is closed;
- unavailable because OBS WebSocket is disabled, unreachable, or unauthenticated;
- available and not currently streaming;
- available and currently streaming.

OBS state is queried just in time for actions that may affect OBS:

- before starting live, to avoid silently overwriting or interrupting an existing OBS push;
- after successfully stopping Bilibili live, to clean up local OBS push if OBS is currently streaming.

OBS state may be displayed as an informational status, but it must not change Bilibili start/stop button semantics.

## UX Semantics

### Dialog Open

When live control opens:

1. Load saved form values.
2. Create an authenticated Bilibili session.
3. Load area list.
4. Load Bilibili room info.
5. Set `is_live_active` from Bilibili `live_status`.

The dialog may optionally check OBS connectivity or output state for display, but that result must not override `is_live_active`.

### Start Live When OBS Is Not Streaming

If Bilibili reports not live and OBS is not streaming, the user can click "开始直播".

Flow:

1. Validate room, title, area, and CSRF.
2. Save form config.
3. Sync title and area if needed.
4. Call Bilibili `start_live`.
5. On success, parse stream credentials.
6. Write selected Bilibili stream settings into OBS and start OBS streaming if OBS is available.
7. If OBS is unavailable or write/start fails, keep Bilibili state live and show manual credential copy UI.

### Start Live When OBS Is Already Streaming

If Bilibili reports not live but OBS is already streaming, "开始直播" remains enabled.

Before calling Bilibili `start_live`, BiliHUD shows a confirmation dialog because continuing can interrupt or retarget a local OBS push.

Confirmation choices:

- Continue: proceed with Bilibili start-live flow.
- Cancel: do not call Bilibili `start_live` and do not change OBS.

On Continue:

1. Call Bilibili `start_live`.
2. If Bilibili start fails, leave OBS unchanged.
3. If Bilibili start succeeds, parse new stream credentials.
4. Stop the current OBS stream if OBS still reports streaming.
5. Write the new Bilibili stream settings into OBS.
6. Start OBS streaming to the new target.

If the OBS switch fails after Bilibili start succeeds, BiliHUD keeps `is_live_active = true`, shows stream credentials, and reports that OBS switching failed. The user can manually fix OBS using the displayed credentials.

### Stop Live

If Bilibili reports live, "停止直播" is enabled.

Clicking "停止直播" expresses an intent to stop the live session. No confirmation dialog is required for OBS cleanup because, after Bilibili is stopped, continuing to push from OBS no longer helps the Bilibili live room.

Flow:

1. Call Bilibili `stop_live`.
2. If Bilibili stop fails, do not change OBS and keep the UI live state unchanged.
3. If Bilibili stop succeeds, clear credentials and set `is_live_active = false`.
4. Query OBS current stream status.
5. If OBS WebSocket is available and OBS is currently streaming, call OBS `StopStream`.
6. If OBS is unavailable, not streaming, or stop fails, do not revert Bilibili stopped state.

Status messaging:

- Bilibili stopped and OBS stopped: "直播已停止，OBS 推流已停止。"
- Bilibili stopped and OBS was not streaming: "直播已停止。"
- Bilibili stopped but OBS status could not be checked or OBS stop failed: "直播已停止；OBS 推流未能自动确认/停止，请在 OBS 中手动确认。"

This flow fixes the restart case: even though `_obs_streaming_started` is false after restart, BiliHUD still checks the current OBS state after successful Bilibili stop.

### BiliHUD Exit

BiliHUD process exit or live control dialog close must not stop OBS streaming.

Allowed cleanup:

- cancel pending BiliHUD tasks;
- close BiliHUD-owned aiohttp sessions;
- close dialogs.

Disallowed cleanup:

- OBS `StopStream`;
- OBS process termination;
- Bilibili `stop_live`.

## Architecture

### `obs_api.py`

Add OBS WebSocket support for reading stream output status:

- Build a `GetStreamStatus` request.
- Parse the response into a small data type or boolean.
- Expose an async method such as `get_stream_status()` or `is_streaming()`.

The method should return only OBS output state. It should not know about Bilibili state.

Errors should use existing `ObsApiError` conventions.

### `live_control_dialog.py`

Keep the existing Bilibili-driven action state:

- `_update_action_state()` continues to call `room_action_enabled_state(..., self.is_live_active)`.
- Do not add OBS state into `room_action_enabled_state`.

Add action-time OBS checks:

- `handle_start_live()` checks OBS stream status before calling Bilibili `start_live`.
- `handle_stop_live()` checks OBS stream status after successful Bilibili `stop_live`.

Avoid relying on `_obs_streaming_started` for restart-sensitive decisions. It can remain as an in-session hint for messages, but live start/stop side effects should use current OBS status where possible.

### Confirmation Dialog

Only the "start while OBS is already streaming" path needs confirmation.

The confirmation must happen before Bilibili `start_live`, so canceling leaves both Bilibili and OBS unchanged.

The confirmation text should make the side effect clear:

- OBS is already streaming.
- Continuing may stop or retarget the current OBS stream.
- Cancel leaves OBS and Bilibili unchanged.

Use non-blocking/qasync-safe dialog handling if this path is called from an async slot. Avoid adding nested event-loop calls such as `QApplication.processEvents()` or modal `exec()` in qasync task paths.

## Data Flow

### Restart, Bilibili Live, OBS Streaming

1. User restarts BiliHUD.
2. User opens live control.
3. BiliHUD loads Bilibili room info and sees `live_status = true`.
4. "停止直播" is enabled.
5. User clicks "停止直播".
6. BiliHUD calls Bilibili `stop_live`.
7. BiliHUD queries OBS current stream status.
8. If OBS is streaming, BiliHUD stops OBS streaming.

### Restart, Bilibili Not Live, OBS Streaming Unknown Target

1. User restarts BiliHUD.
2. User opens live control.
3. BiliHUD loads Bilibili room info and sees `live_status = false`.
4. "开始直播" is enabled.
5. User clicks "开始直播".
6. BiliHUD queries OBS current stream status.
7. If OBS is streaming, BiliHUD asks for confirmation.
8. Cancel leaves both systems unchanged.
9. Continue starts Bilibili live and then switches OBS to the new Bilibili target.

### Bilibili Stop Succeeds, OBS Cleanup Fails

1. User clicks "停止直播".
2. Bilibili `stop_live` succeeds.
3. BiliHUD marks Bilibili state stopped.
4. OBS status check or `StopStream` fails.
5. BiliHUD reports that OBS could not be automatically confirmed/stopped.
6. BiliHUD does not roll back the Bilibili stopped state.

## Error Handling

- OBS status check failure before start should not block Bilibili start unless OBS positively reports that it is streaming and the user cancels.
- If OBS status is unknown before start, proceed with existing start flow and surface any OBS write/start error normally.
- If Bilibili start fails after the user confirmed an OBS switch, do not touch OBS.
- If Bilibili start succeeds but OBS switch fails, keep Bilibili live state true and show credentials for manual recovery.
- If Bilibili stop fails, do not stop OBS automatically.
- If Bilibili stop succeeds, OBS cleanup failure is a warning, not a reason to restore live state.

## Testing

Add tests that avoid real Bilibili or OBS network access:

- OBS request builder for `GetStreamStatus` uses the expected request type.
- OBS status parser treats active output as streaming and inactive output as not streaming.
- `room_action_enabled_state` remains driven only by Bilibili live state.
- Start-flow helper, if extracted, requires confirmation only when OBS status is known streaming.
- Stop-flow helper, if extracted, attempts OBS cleanup after Bilibili stop when OBS status is known streaming.
- Restart-sensitive behavior is covered by tests that do not set `_obs_streaming_started` but still provide current OBS streaming status.

Existing tests should continue to pass:

```sh
uv run --extra test pytest -q
```

## Manual Verification

### Start While OBS Already Streams

1. Start OBS and begin streaming to any target.
2. Ensure Bilibili room is not live.
3. Open BiliHUD live control.
4. Click "开始直播".
5. Confirm the dialog appears before Bilibili start.
6. Click Cancel and verify OBS keeps streaming and Bilibili does not start.
7. Repeat and click Continue.
8. Verify Bilibili starts and OBS switches to the Bilibili target.

### Restart Then Stop Live

1. Use BiliHUD to start Bilibili live and OBS push.
2. Exit BiliHUD.
3. Confirm OBS keeps pushing.
4. Restart BiliHUD.
5. Open live control.
6. Confirm "停止直播" is enabled because Bilibili is live.
7. Click "停止直播".
8. Confirm Bilibili stops and OBS push stops automatically.

### Exit Does Not Stop OBS

1. Start OBS push.
2. Exit BiliHUD without clicking "停止直播".
3. Confirm OBS keeps pushing.

## Implementation Notes

- Keep Bilibili state and OBS state named distinctly in code.
- Avoid names that imply OBS controls room live state.
- Do not persist stream credentials or OBS ownership state.
- Keep OBS WebSocket request/parse logic in `obs_api.py` so tests do not need PyQt.
- If confirmation UI needs async integration, prefer a small helper that returns a boolean without nested event-loop pumping.
