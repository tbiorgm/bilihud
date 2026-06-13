# Live Control State Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make live-control start/stop actions always use Bilibili live status as the primary state while checking current OBS output state only for action-time side effects.

**Architecture:** Keep `room_action_enabled_state()` and `LiveControlDialog.is_live_active` Bilibili-only. Add OBS `GetStreamStatus` support in `obs_api.py`, then use it inside `LiveControlDialog` before start and after successful stop. Start while OBS is already streaming asks for confirmation; stop after Bilibili success automatically stops OBS if OBS is currently streaming.

**Tech Stack:** Python 3.14, PyQt6, qasync, aiohttp, OBS WebSocket v5, pytest.

---

## File Structure

- Modify `src/bilihud/obs_api.py`
  - Add `build_get_stream_status_request()`.
  - Add `parse_stream_status_response()`.
  - Add `ObsWebSocketClient.is_streaming()`.
- Modify `tests/test_obs_api.py`
  - Cover `GetStreamStatus` request building and response parsing.
- Modify `src/bilihud/live_control_dialog.py`
  - Check OBS stream state before `start_live`.
  - Add qasync-safe confirmation helper for start while OBS is already streaming.
  - After successful Bilibili stop, query current OBS stream state and stop OBS if active.
  - Keep Bilibili button enablement driven only by `is_live_active`.
- Create `tests/test_live_control_state_semantics.py`
  - Cover helper logic that can be tested without launching Qt widgets or real OBS/Bilibili.

## Task 1: OBS Stream Status API

**Files:**
- Modify: `src/bilihud/obs_api.py`
- Modify: `tests/test_obs_api.py`

- [ ] **Step 1: Write failing OBS status tests**

Add these imports to `tests/test_obs_api.py`:

```python
from bilihud.obs_api import (
    build_get_stream_status_request,
    parse_stream_status_response,
)
```

Add tests:

```python
def test_build_get_stream_status_request_reads_obs_output_state():
    assert build_get_stream_status_request() == {
        "requestType": "GetStreamStatus",
        "requestId": "get-bilihud-stream-status",
    }


def test_parse_stream_status_response_reads_active_output():
    assert parse_stream_status_response({"responseData": {"outputActive": True}}) is True
    assert parse_stream_status_response({"responseData": {"outputActive": False}}) is False
    assert parse_stream_status_response({"responseData": {}}) is False
```

- [ ] **Step 2: Run OBS tests and verify RED**

Run:

```sh
uv run --extra test pytest tests/test_obs_api.py -q
```

Expected: FAIL because the new functions do not exist.

- [ ] **Step 3: Implement OBS status helpers**

In `src/bilihud/obs_api.py`, add:

```python
def build_get_stream_status_request() -> dict[str, Any]:
    return {
        "requestType": "GetStreamStatus",
        "requestId": "get-bilihud-stream-status",
    }


def parse_stream_status_response(response: Mapping[str, Any]) -> bool:
    data = dict(response.get("responseData") or {})
    return bool(data.get("outputActive"))
```

Add `Mapping` to the imports:

```python
from collections.abc import Mapping, Sequence
```

Add this method to `ObsWebSocketClient`:

```python
    async def is_streaming(self) -> bool:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(self.url, timeout=self.timeout) as ws:
                    await self._identify(ws)
                    response = await self._send_request(ws, build_get_stream_status_request())
                    return parse_stream_status_response(response)
            except TimeoutError as exc:
                raise ObsApiError("连接 OBS WebSocket 超时。") from exc
            except aiohttp.ClientError as exc:
                raise ObsApiError(f"无法连接 OBS WebSocket: {exc}") from exc
```

- [ ] **Step 4: Run OBS tests and verify GREEN**

Run:

```sh
uv run --extra test pytest tests/test_obs_api.py -q
```

Expected: PASS.

## Task 2: Testable Live-Control State Helpers

**Files:**
- Modify: `src/bilihud/live_control_dialog.py`
- Create: `tests/test_live_control_state_semantics.py`

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_live_control_state_semantics.py`:

```python
from bilihud.live_control_dialog import (
    obs_cleanup_after_stop_state,
    start_live_confirmation_needed,
)


def test_start_live_confirmation_needed_only_when_obs_is_known_streaming():
    assert start_live_confirmation_needed(obs_streaming=True) is True
    assert start_live_confirmation_needed(obs_streaming=False) is False
    assert start_live_confirmation_needed(obs_streaming=None) is False


def test_obs_cleanup_after_stop_only_when_obs_is_known_streaming():
    assert obs_cleanup_after_stop_state(obs_streaming=True) == (True, "streaming")
    assert obs_cleanup_after_stop_state(obs_streaming=False) == (False, "not_streaming")
    assert obs_cleanup_after_stop_state(obs_streaming=None) == (False, "unknown")
```

- [ ] **Step 2: Run helper tests and verify RED**

Run:

```sh
uv run --extra test pytest tests/test_live_control_state_semantics.py -q
```

Expected: FAIL because helper functions do not exist.

- [ ] **Step 3: Implement helper functions**

In `src/bilihud/live_control_dialog.py`, near module-level constants after `logger`, add:

```python
def start_live_confirmation_needed(obs_streaming: bool | None) -> bool:
    return obs_streaming is True


def obs_cleanup_after_stop_state(obs_streaming: bool | None) -> tuple[bool, str]:
    if obs_streaming is True:
        return True, "streaming"
    if obs_streaming is False:
        return False, "not_streaming"
    return False, "unknown"
```

- [ ] **Step 4: Run helper tests and verify GREEN**

Run:

```sh
uv run --extra test pytest tests/test_live_control_state_semantics.py -q
```

Expected: PASS.

## Task 3: Start Live Confirmation And OBS Switch

**Files:**
- Modify: `src/bilihud/live_control_dialog.py`

- [ ] **Step 1: Add OBS status query helper**

Add this method to `LiveControlDialog`:

```python
    async def _current_obs_streaming(self) -> bool | None:
        client = self._obs_client()
        if client is None:
            return None
        try:
            streaming = await client.is_streaming()
        except ObsApiError as exc:
            logger.info("Failed to query OBS stream status: %s", exc)
            return None
        except Exception:
            logger.exception("Unexpected OBS stream status failure")
            return None
        self._obs_connected = True
        return streaming
```

- [ ] **Step 2: Add qasync-safe confirmation helper**

Add this method to `LiveControlDialog`:

```python
    async def _confirm_switch_obs_stream(self) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        box = QMessageBox(self)
        box.setWindowTitle("OBS 正在推流")
        box.setText("OBS 当前正在推流。继续开播会停止当前 OBS 推流，并切换到新的 B 站推流地址。")
        box.setInformativeText("取消将不会开播，也不会修改 OBS。")
        continue_btn = box.addButton("继续开播", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

        def finish() -> None:
            if not future.done():
                future.set_result(box.clickedButton() == continue_btn)
            box.deleteLater()

        box.finished.connect(lambda _result: finish())
        box.open()
        return await future
```

- [ ] **Step 3: Check OBS before Bilibili start**

In `handle_start_live()`, after `_set_busy(True, "正在开始直播...")` and before `_save_form_config()`, insert:

```python
            obs_streaming = await self._current_obs_streaming()
            if start_live_confirmation_needed(obs_streaming):
                self._set_busy(False)
                if not await self._confirm_switch_obs_stream():
                    self.set_status("已取消开播，OBS 推流保持不变。")
                    return
                self._set_busy(True, "正在开始直播...")
```

Keep this check before `start_live()` so canceling leaves Bilibili and OBS unchanged.

- [ ] **Step 4: Switch OBS after successful Bilibili start**

In `_handle_start_live_result`, no change is needed beyond existing `self._obs_write_task = asyncio.create_task(self._write_obs_after_start())`. `start_obs_stream()` will handle stopping active OBS output before writing new credentials in the next step.

- [ ] **Step 5: Stop current OBS stream before writing new credentials**

In `start_obs_stream()`, after obtaining `client` and before `await client.set_stream_service_settings_and_start(credential)`, query streaming status and stop if active:

```python
            try:
                if await client.is_streaming():
                    await client.stop_stream()
            except ObsApiError as exc:
                logger.info("Failed to stop existing OBS stream before switch: %s", exc)
                raise
```

This happens only after Bilibili `start_live` has succeeded and credentials exist.

## Task 4: Stop Live OBS Cleanup After Restart

**Files:**
- Modify: `src/bilihud/live_control_dialog.py`

- [ ] **Step 1: Replace memory-only OBS stop decision**

In `handle_stop_live()`, replace:

```python
            should_stop_obs = self._obs_streaming_started or self._obs_connected
            obs_stopped = True
            if should_stop_obs:
                obs_stopped = await self.stop_obs_stream(auto=True)
```

with:

```python
            obs_streaming = await self._current_obs_streaming()
            should_stop_obs, obs_state = obs_cleanup_after_stop_state(obs_streaming)
            obs_stopped = True
            if should_stop_obs:
                obs_stopped = await self.stop_obs_stream(auto=True)
                if not self._is_current_action(action_generation, session):
                    return
```

- [ ] **Step 2: Update stop status messaging**

Replace the final status block with:

```python
            self._obs_streaming_started = False
            if should_stop_obs and obs_stopped:
                self.set_status("直播已停止，OBS 推流已停止。")
            elif obs_state == "unknown" or (should_stop_obs and not obs_stopped):
                self.set_status("直播已停止；OBS 推流未能自动确认/停止，请在 OBS 中手动确认。", error=True)
            else:
                self.set_status("直播已停止。")
```

## Task 5: Verification And Commit

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run focused tests**

Run:

```sh
uv run --extra test pytest tests/test_obs_api.py tests/test_live_api.py tests/test_live_control_state_semantics.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full tests**

Run:

```sh
uv run --extra test pytest -q
```

Expected: PASS.

- [ ] **Step 3: Inspect diff**

Run:

```sh
git diff -- src/bilihud/obs_api.py src/bilihud/live_control_dialog.py tests/test_obs_api.py tests/test_live_control_state_semantics.py docs/superpowers/plans/2026-06-13-live-control-state-semantics.md
```

Expected: diff only implements OBS stream status, start confirmation/switch, stop cleanup, and plan documentation.

- [ ] **Step 4: Commit implementation**

Run:

```sh
git add src/bilihud/obs_api.py src/bilihud/live_control_dialog.py tests/test_obs_api.py tests/test_live_control_state_semantics.py docs/superpowers/plans/2026-06-13-live-control-state-semantics.md
git commit -m "fix: align live control obs side effects with room state"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: OBS `GetStreamStatus`, Bilibili-only `live_status`, start confirmation before Bilibili start, stop cleanup after Bilibili stop, and exit non-cleanup are all covered.
- Placeholder scan: No TBD/TODO/fill-in-later steps remain.
- Type consistency: Helpers use `bool | None` for known/unknown OBS state; `obs_cleanup_after_stop_state()` returns `(bool, str)` for decision and messaging.

## Execution Notes

- `start_obs_stream()` distinguishes OBS status-query failure from known active streaming. If querying status fails, it preserves the previous behavior and still attempts to write/start OBS. If OBS is known streaming and `StopStream` fails, the OBS switch fails and the existing error path tells the user to handle OBS manually.
- `handle_stop_live()` no longer uses `_obs_streaming_started` or `_obs_connected` to decide whether OBS should be stopped after Bilibili stop. It queries current OBS status, which covers BiliHUD restart cases.
- Verification passed with `uv run --extra test pytest tests/test_obs_api.py tests/test_live_api.py tests/test_live_control_state_semantics.py -q`: 21 tests passed.
- Verification passed with `uv run --extra test pytest -q`: 40 tests passed.
