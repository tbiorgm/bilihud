# BiliHUD QAsync Danmaku Shutdown Design

## Context

BiliHUD runs PyQt6 UI code and asyncio network code in the same qasync event loop. The main HUD danmaku client uses blivedm WebSocket tasks for incoming danmaku and uses HTTP requests for sending danmaku. The live control dialog uses async qasync slots to call Bilibili live APIs and optionally trigger OBS WebSocket actions.

Observed failure:

- Start BiliHUD.
- Connect the HUD to a live room from the upper-right button.
- Open the tray live control dialog.
- Start live and push stream through OBS.
- The HUD no longer refreshes incoming danmaku.
- Sending danmaku still works.
- Clicking the HUD disconnect button leaves the button stuck as "断开".

User-provided runtime log:

```text
RuntimeError: Cannot enter into task <Task pending ... WebSocketClientBase._network_coroutine_wrapper() ...>
while another task <Task pending ... LiveControlDialog.handle_start_live() ...> is being executed.
```

A local qasync reproduction confirmed that calling `QApplication.processEvents()` inside a running qasync task can trigger the same asyncio reentrancy error when another task wakes up before the current task returns.

## Goal

Fix the qasync reentrancy failure and make danmaku shutdown deterministic:

- No BiliHUD code should manually pump the Qt event loop while qasync tasks are active.
- Danmaku WebSocket receive tasks must not be broken by nested Qt event processing.
- `DanmakuClient.stop()` must return only after the underlying blivedm network task has ended and the aiohttp session is closed.
- Timeout handling must escalate shutdown, not silently leave a pending task behind.
- HUD UI state should only switch back to disconnected after the danmaku client has actually stopped.

## Non-Goals

- Do not change Bilibili danmaku protocol handling.
- Do not assume that starting live requires reconnecting the danmaku WebSocket.
- Do not modify vendored blivedm unless evidence shows its stop contract cannot be satisfied from BiliHUD.
- Do not redesign the live control dialog or main overlay UI.
- Do not add automatic reconnect on successful start-live as part of this fix.

## Root Cause

The root cause is local event-loop reentrancy, not a proven Bilibili WebSocket state transition.

`QApplication.processEvents()` can run pending Qt events immediately. Under qasync, those Qt events can include qasync timer callbacks that resume asyncio tasks. If this happens while another asyncio task is still executing, Python 3.14 raises `RuntimeError: Cannot enter into task ... while another task ... is being executed`.

In the observed failure, the live control `handle_start_live()` task was executing while the blivedm network task tried to resume. The WebSocket task then failed to continue processing incoming messages. The HUD still had a valid HTTP session, so sending danmaku could continue even though WebSocket receive stopped.

## Architecture

### Event Loop Rule

BiliHUD must not call APIs that run a nested Qt event loop from normal qasync task paths.

Disallowed in qasync task paths:

- `QApplication.processEvents()`
- `QDialog.exec()`
- `QMessageBox.exec()`
- qasync `asyncClose()` style loops that repeatedly call `processEvents()`

The immediate implementation targets the proven `QApplication.processEvents()` reentrancy source. Existing modal dialogs are not on the reported successful start-live path; they are documented here as the same class of risk and should not be introduced into new qasync task paths. Convert existing modal `exec()` calls only if implementation work touches those paths or future logs implicate them.

### UI Refresh Strategy

Layer shell or game-mode UI updates should request painting/layout work and then return control to the main event loop naturally.

Allowed approaches:

- `layout().activate()`
- `widget.update()`
- `widget.repaint()` only if synchronous repaint is proven safe and needed
- `QTimer.singleShot(0, callable)` for deferring UI work until the current callback returns

`QTimer.singleShot(0, ...)` must not be used to start long async work. It should only schedule small UI updates.

### Danmaku Client Stop Contract

`DanmakuClient.stop()` owns the shutdown contract for BiliHUD's danmaku connection.

When `stop()` returns successfully:

- blivedm is no longer running;
- the blivedm network future has completed;
- the WebSocket is closed;
- the aiohttp session is closed;
- the client object no longer exposes a usable active connection.

If normal shutdown does not complete within a bounded timeout, timeout escalates the shutdown:

1. Request normal blivedm stop.
2. Await blivedm completion for a short timeout.
3. If still running, close the aiohttp session to force the WebSocket receive loop to exit.
4. Await blivedm completion again.
5. If the network task still has not completed, raise a shutdown error instead of pretending the client stopped.

The UI should surface a concise disconnect failure message and keep the connection state honest if this error occurs.

## Data Flow

### Normal Disconnect

1. User clicks "断开".
2. `DanmakuWidget.toggle_connection()` calls `DanmakuClient.stop()`.
3. `DanmakuClient.stop()` asks blivedm to stop.
4. blivedm cancels and joins its network coroutine.
5. BiliHUD closes its aiohttp session.
6. `DanmakuWidget` clears the client reference and changes the button to "连接".

### Escalated Disconnect

1. User clicks "断开".
2. `DanmakuClient.stop()` asks blivedm to stop.
3. blivedm does not finish within the normal timeout.
4. `DanmakuClient.stop()` closes the aiohttp session to break WebSocket IO.
5. `DanmakuClient.stop()` waits for the blivedm network task to finish.
6. If it finishes, the HUD enters disconnected state.
7. If it still does not finish, `DanmakuClient.stop()` raises a shutdown error and the HUD reports the failure.

### Live Start

1. User starts live in `LiveControlDialog`.
2. The dialog updates live control UI without manually processing Qt events.
3. The blivedm WebSocket task can resume only when the current qasync callback yields or returns normally.
4. Incoming danmaku should continue without forced reconnect.

## Error Handling

- qasync reentrancy errors should be treated as bugs. The fix removes the known nested event processing path instead of catching the exception.
- Disconnect failure should not silently reset the UI.
- If forced session close cannot make the blivedm task complete, raise a specific `DanmakuShutdownError`.
- Logs should include shutdown phase and room ID but must not include cookies or stream credentials.

## Testing

Add unit tests that do not require real Bilibili network access:

- A qasync/offscreen regression test proving the replacement UI update path does not call `QApplication.processEvents()`.
- A `DanmakuClient.stop()` test where a fake blivedm client stops normally and the session close path runs.
- A `DanmakuClient.stop()` test where a fake blivedm client does not finish at first, session close is invoked, and then the network task completes.
- A `DanmakuClient.stop()` test where the fake client still does not finish after forced close and `DanmakuShutdownError` is raised.
- A HUD disconnect test, if practical without full GUI automation, verifying the button state changes only after successful client shutdown.

Existing tests should continue to pass with:

```sh
uv run --extra test pytest -q
```

## Manual Verification

Manual verification should cover the reported path:

1. Start `bilihud`.
2. Connect the HUD to the room.
3. Open live control from the tray.
4. Start live and trigger OBS push.
5. Confirm the terminal no longer logs `Cannot enter into task`.
6. Confirm incoming danmaku keeps refreshing.
7. Click "断开".
8. Confirm the button returns to "连接" only after the connection has actually stopped.
9. Reconnect and confirm incoming danmaku works again.

Also verify game-mode/layer-shell behavior:

- Toggle locked click-through mode.
- Confirm the visual state updates without calling `QApplication.processEvents()`.
- Confirm click-through still behaves as before.

## Implementation Notes

- Keep the primary fix in BiliHUD code, not vendored blivedm.
- Avoid relying on private blivedm fields unless no public API can satisfy the stop contract. If private fields are needed for verification, isolate access in small helper methods.
- Prefer explicit shutdown phases over broad cancellation handling.
- Do not add automatic danmaku reconnect in this change unless post-fix manual verification proves the WebSocket still fails while the event-loop reentrancy error is gone.
