"""Live history route paging: bounded pages, cursors, and store reuse.

The dashboard loads live creature history through
``GET /{sid}/creatures/{cid}/history`` after every attach, tab switch, and
turn; before paging that request built the ENTIRE event log synchronously
on the event loop (the 331MB problem session measured a ~7s build for a
123MB response). These tests pin the store-read paging contract: bounded
by default, ``before`` walks backwards, ``since_event_id`` composes,
``max_event_id`` stays the full-log truth, and the engine-held store is
never reopened.
"""

import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kohakuterrarium.api.deps import get_service
from kohakuterrarium.api.routes.sessions_v2 import creatures_chat as chat_mod
from kohakuterrarium.session.store import SessionStore
from kohakuterrarium.terrarium.creature_history import chat_history_for
from kohakuterrarium.terrarium.service import CreatureInfo

GRAPH_ID = "graph_live1"


def _info(cid="cid", name="alice"):
    return CreatureInfo(
        creature_id=cid,
        name=name,
        graph_id=GRAPH_ID,
        is_running=True,
        is_privileged=False,
        parent_creature_id=None,
        listen_channels=(),
        send_channels=(),
    )


class _FakeAgent:
    def __init__(self, name, store=None):
        self.name = name
        self.session_store = store
        self.conversation_history = [{"role": "user", "content": "snapshot"}]
        self.is_processing = False
        self._direct_job_meta = {}


class _FakeCreature:
    def __init__(self, agent, name="alice"):
        self.agent = agent
        self.name = name
        self.graph_id = GRAPH_ID
        self.is_privileged = False


class _FakeEngine:
    """Minimal engine surface ``chat_history_for`` touches."""

    def __init__(self, creature, store=None):
        self._creature = creature
        self._session_stores = {GRAPH_ID: store} if store is not None else {}

    def get_creature(self, cid):
        return self._creature


class _DelegatingService:
    """Routes ``chat_history`` through the REAL ``chat_history_for`` so the
    paging contract is exercised end to end from the HTTP layer."""

    def __init__(self, engine):
        self._engine = engine
        # ``live_store_entry`` reads this for the ``ch:`` branch.
        self._session_stores = engine._session_stores

    async def list_creatures(self):
        return (_info(),)

    async def chat_history(self, creature_id, **kwargs):
        return chat_history_for(self._engine, creature_id, **kwargs)


def _make_store(
    tmp_path: Path,
    *,
    agent: str = "alice",
    events: int = 0,
    channel_messages: int = 0,
    channel: str = "ops",
) -> SessionStore:
    path = tmp_path / "alice_3f2a9c11.kohakutr"
    store = SessionStore(str(path))
    store.init_meta(
        agent,
        "agent",
        "/p",
        "/w",
        [agent],
        terrarium_channels=[{"name": channel}] if channel_messages else None,
    )
    for i in range(events):
        store.append_event(agent, "user_message", {"content": f"m{i}"})
    for i in range(channel_messages):
        store.save_channel_message(channel, {"sender": "a", "content": f"c{i}"})
    store.flush()
    return store


def _client(engine):
    app = FastAPI()
    app.dependency_overrides[get_service] = lambda: _DelegatingService(engine)
    app.include_router(chat_mod.router, prefix="/sessions")
    return TestClient(app)


# ── agent-target paging ────────────────────────────────────────


class TestLiveAgentPaging:
    def test_default_response_is_bounded(self, tmp_path):
        store = _make_store(tmp_path, events=450)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        try:
            body = (
                _client(engine)
                .get(f"/sessions/{GRAPH_ID}/creatures/alice/history")
                .json()
            )
            assert len(body["events"]) == 400
            assert body["has_more"] is True
            assert body["total"] == 450
            assert body["oldest_event_id"] == body["events"][0]["event_id"]
            assert body["events"][-1]["event_id"] == 450
            # Newest page carries the live conversation snapshot.
            assert body["messages"] == [{"role": "user", "content": "snapshot"}]
            assert body["is_processing"] is False
            # Full-log truth, NOT the page maximum — a client advancing its
            # incremental cursor from a page-bounded max would re-fetch.
            assert body["max_event_id"] == 450
        finally:
            store.close()

    def test_before_cursor_walks_older_pages(self, tmp_path):
        store = _make_store(tmp_path, events=10)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        client = _client(engine)
        try:
            page1 = client.get(
                f"/sessions/{GRAPH_ID}/creatures/alice/history",
                params={"limit": 4},
            ).json()
            assert [e["event_id"] for e in page1["events"]] == [7, 8, 9, 10]
            page2 = client.get(
                f"/sessions/{GRAPH_ID}/creatures/alice/history",
                params={"limit": 4, "before": page1["oldest_event_id"]},
            ).json()
            assert [e["event_id"] for e in page2["events"]] == [3, 4, 5, 6]
            # Older pages omit the snapshot — it belongs to the newest
            # window and would duplicate megabytes per request.
            assert page2["messages"] == []
            assert page2["has_more"] is True
            assert page2["total"] == 10
            # max_event_id stays the full-log maximum on cursor pages.
            assert page2["max_event_id"] == 10
        finally:
            store.close()

    def test_limit_zero_returns_full_log(self, tmp_path):
        store = _make_store(tmp_path, events=450)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        try:
            body = (
                _client(engine)
                .get(
                    f"/sessions/{GRAPH_ID}/creatures/alice/history",
                    params={"limit": 0},
                )
                .json()
            )
            assert len(body["events"]) == 450
            assert body["has_more"] is False
            assert body["total"] == 450
            assert body["max_event_id"] == 450
        finally:
            store.close()

    def test_since_event_id_composes_with_the_default_bound(self, tmp_path):
        store = _make_store(tmp_path, events=450)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        try:
            body = (
                _client(engine)
                .get(
                    f"/sessions/{GRAPH_ID}/creatures/alice/history",
                    params={"since_event_id": 100},
                )
                .json()
            )
            ids = [e["event_id"] for e in body["events"]]
            # Newest page of the log minus the already-applied prefix.
            assert ids == list(range(101, 451))
            # Incremental payloads omit the snapshot.
            assert "messages" not in body
            assert body["max_event_id"] == 450
        finally:
            store.close()

    def test_negative_limit_is_rejected(self, tmp_path):
        store = _make_store(tmp_path, events=5)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        try:
            resp = _client(engine).get(
                f"/sessions/{GRAPH_ID}/creatures/alice/history",
                params={"limit": -1},
            )
            assert resp.status_code == 422
        finally:
            store.close()

    def test_live_history_never_reopens_the_store_file(self, tmp_path):
        store = _make_store(tmp_path, events=10)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)

        original_init = SessionStore.__init__

        def _bomb(self, *a, **k):
            raise AssertionError("live history must not open the session file")

        SessionStore.__init__ = _bomb
        try:
            client = _client(engine)
            body = client.get(
                f"/sessions/{GRAPH_ID}/creatures/alice/history",
                params={"limit": 3},
            ).json()
            assert [e["event_id"] for e in body["events"]] == [8, 9, 10]
            older = client.get(
                f"/sessions/{GRAPH_ID}/creatures/alice/history",
                params={"limit": 3, "before": body["oldest_event_id"]},
            ).json()
            assert [e["event_id"] for e in older["events"]] == [5, 6, 7]
        finally:
            SessionStore.__init__ = original_init
            store.close()


class TestLivePageBoundaryInterrupt:
    """A live ``before`` page must not fabricate interrupt terminals.

    The page boundary can end on a ``tool_call`` whose real result lives
    in a NEWER page the client already rendered; synthesizing an
    "Interrupted by session resume" bubble there would leave a fake
    terminal coexisting with the genuine result (P1 review). The newest
    window keeps the synthesis — a dangling call at the log tail with no
    live job IS dead.
    """

    def _tool_store(self, tmp_path: Path) -> SessionStore:
        store = _make_store(tmp_path)
        store.append_event("alice", "user_message", {"content": "u1"})  # id 1
        store.append_event(
            "alice", "tool_call", {"call_id": "j1", "name": "bash", "args": {}}
        )  # id 2
        store.append_event(
            "alice", "tool_result", {"call_id": "j1", "output": "ok"}
        )  # id 3
        store.append_event("alice", "user_message", {"content": "u2"})  # id 4
        store.append_event(
            "alice", "tool_call", {"call_id": "j2", "name": "bash", "args": {}}
        )  # id 5 — dangling, no live job
        store.flush()
        return store

    def test_older_page_does_not_synthesize_interrupt(self, tmp_path):
        store = self._tool_store(tmp_path)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        try:
            body = (
                _client(engine)
                .get(
                    f"/sessions/{GRAPH_ID}/creatures/alice/history",
                    params={"limit": 10, "before": 3},
                )
                .json()
            )
            ids = [e.get("event_id") for e in body["events"]]
            assert 2 in ids and 3 not in ids  # boundary split the pair
            assert not any(
                e.get("_synthetic_resume") or e.get("final_state") == "interrupted"
                for e in body["events"]
            )
        finally:
            store.close()

    def test_newest_window_still_synthesizes_for_dead_jobs(self, tmp_path):
        store = self._tool_store(tmp_path)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        try:
            body = (
                _client(engine)
                .get(
                    f"/sessions/{GRAPH_ID}/creatures/alice/history",
                    params={"limit": 2},
                )
                .json()
            )
            synthetic = [
                e
                for e in body["events"]
                if e.get("_synthetic_resume") and e.get("call_id") == "j2"
            ]
            assert len(synthetic) == 1
            assert synthetic[0]["final_state"] == "interrupted"
        finally:
            store.close()


# ── channel-target paging ──────────────────────────────────────


class TestLiveChannelPaging:
    def test_channel_pages_use_sequence_cursor(self, tmp_path):
        store = _make_store(tmp_path, channel_messages=30)
        engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
        client = _client(engine)
        try:
            page1 = client.get(
                f"/sessions/{GRAPH_ID}/creatures/ch:ops/history",
                params={"limit": 10},
            ).json()
            assert [e["content"] for e in page1["events"]] == [
                f"c{i}" for i in range(20, 30)
            ]
            assert page1["has_more"] is True
            assert page1["total"] == 30
            assert page1["max_event_id"] == 0
            page2 = client.get(
                f"/sessions/{GRAPH_ID}/creatures/ch:ops/history",
                params={"limit": 10, "before": page1["oldest_event_id"]},
            ).json()
            assert [e["content"] for e in page2["events"]] == [
                f"c{i}" for i in range(10, 20)
            ]
            assert page2["has_more"] is True
        finally:
            store.close()

    def test_channel_without_local_store_keeps_full_merge(self):
        # No host-local store surface on the service: the legacy full
        # cross-node merge answers, with has_more explicitly false because
        # the merged log has no sequence cursor.
        class _RemoteService:
            async def list_creatures(self):
                return (_info(),)

            async def channel_history(self, gid, name):
                assert (gid, name) == (GRAPH_ID, "ops")
                return [{"sender": "a", "content": "x", "timestamp": 1.0}]

        app = FastAPI()
        app.dependency_overrides[get_service] = lambda: _RemoteService()
        app.include_router(chat_mod.router, prefix="/sessions")
        body = (
            TestClient(app).get(f"/sessions/{GRAPH_ID}/creatures/ch:ops/history").json()
        )
        assert [e["content"] for e in body["events"]] == ["x"]
        assert body["has_more"] is False
        assert body["total"] == 1


# ── chat_history_for paging units ──────────────────────────────


class TestChatHistoryForPaging:
    def test_paged_read_without_store_yields_empty_page(self):
        # Neither an agent-attached store nor a lifecycle store: the paged
        # payload degrades to an empty page instead of raising.
        agent = _FakeAgent("alice", None)
        engine = _FakeEngine(_FakeCreature(agent))
        out = chat_history_for(engine, "cid", limit=5, before=None)
        assert out["events"] == []
        assert out["total"] == 0
        assert out["has_more"] is False
        assert out["messages"] == agent.conversation_history
        assert out["max_event_id"] == 0

    def test_unreadable_store_counter_falls_back_to_event_scan(self, tmp_path):
        store = _make_store(tmp_path, events=6)
        # Simulate a store without the O(1) counter: the payload max must
        # still be derived rather than reported as 0.
        counterless = types.SimpleNamespace(
            flush=store.flush,
            events=store.events,
            load_conversation=store.load_conversation,
        )
        agent = _FakeAgent("alice", counterless)
        engine = _FakeEngine(_FakeCreature(agent), store)
        try:
            out = chat_history_for(engine, "cid", limit=3, before=None)
            assert out["max_event_id"] == 6
        finally:
            store.close()


@pytest.mark.parametrize("event_count,limit,expected", [(2, 5, 2), (0, 5, 0)])
def test_small_logs_page_without_has_more(tmp_path, event_count, limit, expected):
    store = _make_store(tmp_path, events=event_count)
    engine = _FakeEngine(_FakeCreature(_FakeAgent("alice", store)), store)
    try:
        out = chat_history_for(engine, "cid", limit=limit, before=None)
        assert len(out["events"]) == expected
        assert out["has_more"] is False
    finally:
        store.close()
