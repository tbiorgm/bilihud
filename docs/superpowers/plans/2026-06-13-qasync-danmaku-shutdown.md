# QAsync Danmaku Shutdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix qasync event-loop reentrancy and make BiliHUD danmaku shutdown return only after the underlying connection is actually stopped.

**Architecture:** Remove the known nested Qt event-loop pump from the HUD UI path. Introduce a strict `DanmakuClient.stop()` shutdown contract with normal stop, forced session-close escalation, and explicit failure if the blivedm network task cannot complete.

**Tech Stack:** Python 3.14, PyQt6, qasync, aiohttp, pytest, vendored blivedm.

---

## File Structure

- Modify `src/bilihud/danmaku_client.py`
  - Add `DanmakuShutdownError`.
  - Add strict `stop()` shutdown phases.
  - Add small private helpers only if needed to avoid duplicating timeout/session-close logic.
- Modify `src/bilihud/danmaku_widget.py`
  - Remove `QApplication.processEvents()` from the LayerShell/game-mode visual update path.
  - Keep existing UI update calls and allow the Qt event loop to process them naturally.
  - Report disconnect failures without pretending the client stopped.
- Create `tests/test_danmaku_client.py`
  - Cover normal stop, forced session-close stop, and failure after escalation.
- Modify or create `tests/test_danmaku_widget.py`
  - Add a static regression test proving `QApplication.processEvents()` is not called from `DanmakuWidget`.

## Task 1: Strict Danmaku Stop Contract

**Files:**
- Modify: `src/bilihud/danmaku_client.py`
- Create: `tests/test_danmaku_client.py`

- [ ] **Step 1: Write failing stop-contract tests**

Create `tests/test_danmaku_client.py` with:

```python
import asyncio

import pytest

from bilihud.danmaku_client import DanmakuClient, DanmakuShutdownError


class FakeSession:
    def __init__(self, on_close=None):
        self.closed = False
        self.close_calls = 0
        self._on_close = on_close

    async def close(self):
        self.close_calls += 1
        self.closed = True
        if self._on_close is not None:
            self._on_close()


class FakeBLiveClient:
    def __init__(self, *, finish_on_stop=True):
        self.stop_calls = 0
        self.close_calls = 0
        self._done = asyncio.Event()
        self._finish_on_stop = finish_on_stop

    @property
    def is_running(self):
        return not self._done.is_set()

    def stop(self):
        self.stop_calls += 1
        if self._finish_on_stop:
            self._done.set()

    async def join(self):
        await self._done.wait()

    async def close(self):
        self.close_calls += 1

    def finish(self):
        self._done.set()


@pytest.mark.asyncio
async def test_stop_waits_for_blivedm_and_closes_session():
    client = DanmakuClient(1)
    fake_blive = FakeBLiveClient(finish_on_stop=True)
    fake_session = FakeSession()
    client.client = fake_blive
    client.session = fake_session

    await client.stop(normal_timeout=0.05, forced_timeout=0.05)

    assert fake_blive.stop_calls == 1
    assert fake_blive.close_calls == 1
    assert fake_session.close_calls == 1
    assert fake_session.closed is True
    assert fake_blive.is_running is False


@pytest.mark.asyncio
async def test_stop_closes_session_to_force_blivedm_completion_after_timeout():
    fake_blive = FakeBLiveClient(finish_on_stop=False)
    fake_session = FakeSession(on_close=fake_blive.finish)
    client = DanmakuClient(1)
    client.client = fake_blive
    client.session = fake_session

    await client.stop(normal_timeout=0.01, forced_timeout=0.05)

    assert fake_blive.stop_calls == 1
    assert fake_session.close_calls == 1
    assert fake_session.closed is True
    assert fake_blive.close_calls == 1
    assert fake_blive.is_running is False


@pytest.mark.asyncio
async def test_stop_raises_if_blivedm_task_survives_forced_session_close():
    fake_blive = FakeBLiveClient(finish_on_stop=False)
    fake_session = FakeSession()
    client = DanmakuClient(1)
    client.client = fake_blive
    client.session = fake_session

    with pytest.raises(DanmakuShutdownError):
        await client.stop(normal_timeout=0.01, forced_timeout=0.01)

    assert fake_blive.stop_calls == 1
    assert fake_session.close_calls == 1
    assert fake_session.closed is True
    assert fake_blive.close_calls == 1
    assert fake_blive.is_running is True
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```sh
uv run --extra test pytest tests/test_danmaku_client.py -q
```

Expected: FAIL because `DanmakuShutdownError` is not defined and/or `DanmakuClient.stop()` does not accept timeout arguments.

- [ ] **Step 3: Implement strict stop contract**

Update `src/bilihud/danmaku_client.py`:

```python
class DanmakuShutdownError(RuntimeError):
    pass
```

Replace `DanmakuClient.stop()` with a strict phased shutdown:

```python
    async def stop(self, normal_timeout: float = 3.0, forced_timeout: float = 3.0):
        """Stop the danmaku client and wait until network resources are closed."""
        client = self.client
        session = self.session

        try:
            if client:
                if getattr(client, "is_running", False):
                    client.stop()
                    try:
                        await asyncio.wait_for(client.join(), timeout=normal_timeout)
                    except TimeoutError:
                        if session and not session.closed:
                            await session.close()
                        try:
                            await asyncio.wait_for(client.join(), timeout=forced_timeout)
                        except TimeoutError as exc:
                            raise DanmakuShutdownError(
                                f"弹幕连接未能在强制关闭后停止，room_id={self.room_id}"
                            ) from exc
                await client.close()
        finally:
            if session and not session.closed:
                await session.close()
```

- [ ] **Step 4: Run stop tests and verify GREEN**

Run:

```sh
uv run --extra test pytest tests/test_danmaku_client.py -q
```

Expected: PASS.

## Task 2: HUD Disconnect Failure State

**Files:**
- Modify: `src/bilihud/danmaku_widget.py`

- [ ] **Step 1: Write failing HUD disconnect test if practical**

If a focused Qt widget test is practical in the existing suite, create `tests/test_danmaku_widget.py` with a fake client that raises `DanmakuShutdownError` and assert the button remains checked. If importing `DanmakuWidget` requires a real display/layer-shell environment and is unstable in CI, document that this behavior is manually verified and keep this task implementation-only.

- [ ] **Step 2: Update disconnect branch to keep state honest**

In `DanmakuWidget.toggle_connection()`, wrap only the disconnect stop call:

```python
            try:
                if self.danmaku_client is not None:
                    await self.danmaku_client.stop()
            except Exception as e:
                self.connect_button.setText("断开")
                self.connect_button.setChecked(True)
                self.connect_button.setEnabled(True)
                self.add_system_message(f"断开失败: {e}", "error")
                print(f"Disconnect failed: {e}")
                return
```

Then keep the existing success path that clears `self.danmaku_client` and changes the button to "连接".

- [ ] **Step 3: Run focused tests**

Run:

```sh
uv run --extra test pytest tests/test_danmaku_client.py tests/test_main.py -q
```

Expected: PASS.

## Task 3: Remove QAsync Reentrancy Source

**Files:**
- Modify: `src/bilihud/danmaku_widget.py`
- Create or modify: `tests/test_danmaku_widget.py`

- [ ] **Step 1: Write failing regression test for `processEvents` removal**

Create `tests/test_danmaku_widget.py` if it does not exist:

```python
from pathlib import Path


def test_danmaku_widget_does_not_manually_process_qt_events():
    source = Path("src/bilihud/danmaku_widget.py").read_text(encoding="utf-8")

    assert "QApplication.processEvents()" not in source
```

- [ ] **Step 2: Run regression test and verify RED**

Run:

```sh
uv run --extra test pytest tests/test_danmaku_widget.py -q
```

Expected: FAIL because `QApplication.processEvents()` is currently present.

- [ ] **Step 3: Remove manual event-loop pumping**

In `src/bilihud/danmaku_widget.py`, remove:

```python
                QApplication.processEvents()
```

Keep the preceding calls:

```python
                self.layout().activate()
                self.danmaku_list.update()
                self.update()
```

- [ ] **Step 4: Run regression test and verify GREEN**

Run:

```sh
uv run --extra test pytest tests/test_danmaku_widget.py -q
```

Expected: PASS.

## Task 4: Full Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run full test suite**

Run:

```sh
uv run --extra test pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Inspect diff**

Run:

```sh
git diff -- src/bilihud/danmaku_client.py src/bilihud/danmaku_widget.py tests/test_danmaku_client.py tests/test_danmaku_widget.py
```

Expected: diff only implements the qasync reentrancy removal and strict shutdown contract.

- [ ] **Step 3: Commit implementation**

Run:

```sh
git add src/bilihud/danmaku_client.py src/bilihud/danmaku_widget.py tests/test_danmaku_client.py tests/test_danmaku_widget.py docs/superpowers/plans/2026-06-13-qasync-danmaku-shutdown.md
git commit -m "fix: harden danmaku shutdown under qasync"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: Tasks cover removing the proven `QApplication.processEvents()` reentrancy source, strict `DanmakuClient.stop()` success contract, forced session-close escalation, explicit failure on incomplete shutdown, and verification.
- Placeholder scan: No TBD/TODO/fill-in-later steps remain.
- Type consistency: `DanmakuShutdownError`, `normal_timeout`, and `forced_timeout` are defined before use.

## Execution Notes

- `tests/test_danmaku_client.py` uses `asyncio.run()` instead of `pytest.mark.asyncio` because the project test extra does not include `pytest-asyncio`.
- `DanmakuClient.stop()` uses a single shielded `join()` task across normal and forced timeouts. This avoids canceling or abandoning the first wait when escalating to session close.
- If shutdown still does not complete after forced session close, `stop()` closes available resources, keeps `self.client`/`self.session` references for honest failure state, and raises `DanmakuShutdownError`.
- Full verification passed with `uv run --extra test pytest -q`: 36 tests passed.
