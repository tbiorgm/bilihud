import asyncio
from pathlib import Path

import pytest

from bilihud.danmaku_client import DanmakuClient, DanmakuShutdownError


def test_stop_catches_asyncio_timeout_error_for_python_310_compatibility():
    source = Path("src/bilihud/danmaku_client.py").read_text(encoding="utf-8")

    assert "except asyncio.TimeoutError" in source
    assert "except TimeoutError" not in source


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


class RaisingJoinBLiveClient(FakeBLiveClient):
    async def join(self):
        raise RuntimeError("join failed")


def test_stop_waits_for_blivedm_and_closes_session():
    async def run_test():
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

    asyncio.run(run_test())


def test_stop_closes_resources_but_keeps_references_when_join_raises():
    async def run_test():
        fake_blive = RaisingJoinBLiveClient(finish_on_stop=False)
        fake_session = FakeSession()
        client = DanmakuClient(1)
        client.client = fake_blive
        client.session = fake_session

        with pytest.raises(RuntimeError, match="join failed"):
            await client.stop(normal_timeout=0.05, forced_timeout=0.05)

        assert fake_blive.stop_calls == 1
        assert fake_blive.close_calls == 1
        assert fake_session.close_calls == 1
        assert fake_session.closed is True
        assert client.client is fake_blive
        assert client.session is fake_session

    asyncio.run(run_test())


def test_stop_closes_session_to_force_blivedm_completion_after_timeout():
    async def run_test():
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

    asyncio.run(run_test())


def test_stop_raises_if_blivedm_task_survives_forced_session_close():
    async def run_test():
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

    asyncio.run(run_test())
