"""Unit tests for the persistence fork + history routes."""

import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kohakuterrarium.api.deps import get_service
from kohakuterrarium.api.routes.persistence import fork as fork_mod
from kohakuterrarium.api.routes.persistence import history as history_mod
from kohakuterrarium.session.store import SessionStore


def _app(router) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


class _FakeAgent:
    def __init__(self, job_ids):
        self._direct_job_meta = {jid: {} for jid in job_ids}


class _FakeCreature:
    def __init__(self, agent):
        self.agent = agent


class _FakeGraph:
    def __init__(self, creature_ids):
        self.creature_ids = list(creature_ids)


class _FakeEngine:
    """Minimal host engine: not a ``TerrariumService`` Protocol instance,
    so ``host_engine_or_none`` treats it as the engine directly."""

    def __init__(self, graph, creatures):
        self._graph = graph
        self._creatures = creatures

    def get_graph(self, session_name):
        return self._graph

    def get_creature(self, creature_id):
        return self._creatures[creature_id]


# ── fork ────────────────────────────────────────────────────────


class TestForkRoute:
    def test_session_missing(self, monkeypatch):
        monkeypatch.setattr(fork_mod, "resolve_session_path_default", lambda n: None)
        client = TestClient(_app(fork_mod.router))
        resp = client.post(
            "/api/ghost/fork",
            json={"at_event_id": 5},
        )
        assert resp.status_code == 404

    def test_success(self, monkeypatch):
        monkeypatch.setattr(
            fork_mod,
            "resolve_session_path_default",
            lambda n: Path("/x/s.kohakutr"),
        )

        async def fake_fork(path, **kwargs):
            return {
                "session_id": "s-fork-1",
                "fork_point": kwargs["at_event_id"],
                "path": "/x/s-fork-1.kohakutr.v2",
            }

        monkeypatch.setattr(fork_mod, "fork_session_handler", fake_fork)
        client = TestClient(_app(fork_mod.router))
        resp = client.post(
            "/api/sess/fork",
            json={"at_event_id": 5, "name": "branch-x"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["session_id"] == "s-fork-1"
        assert body["fork_point"] == 5

    def test_live_fork_reuses_the_attached_store(self, monkeypatch, tmp_path):
        # Forking a LIVE session (by graph_id or file stem) must go
        # through the engine's open store — a second open of the
        # actively-written source IOERRs on POSIX. Both source-open
        # entry points are bombed; the REAL fork runs.
        from kohakuterrarium.studio.persistence import fork as fork_handler_mod

        store_path = tmp_path / "alice_3f2a9c11.kohakutr"
        store = SessionStore(str(store_path))
        store.init_meta("alice", "agent", "/p", "/w", ["alice"])
        store.append_event("alice", "user_message", {"content": "hi"})
        store.checkpoint()
        engine = _FakeEngine(graph=_FakeGraph([]), creatures={})
        engine._session_stores = {"graph_live1": store}

        def _bomb(*a, **k):
            raise AssertionError("live fork must not open the source session file")

        monkeypatch.setattr(fork_mod, "resolve_session_path_default", _bomb)
        monkeypatch.setattr(fork_handler_mod, "SessionStore", _bomb)

        app = _app(fork_mod.router)
        app.dependency_overrides[get_service] = lambda: engine
        client = TestClient(app)
        try:
            resp = client.post(
                "/api/alice_3f2a9c11/fork",
                json={"at_event_id": 1, "name": "pin-fork"},
            )
            assert resp.status_code == 201, resp.text
            assert resp.json()["fork_point"] == 1
            # The child landed on disk as a REAL fork of the live source.
            assert Path(resp.json()["path"]).exists()
        finally:
            store.close()


# ── history ─────────────────────────────────────────────────────


class TestHistoryRoutes:
    def test_index_missing(self, monkeypatch):
        monkeypatch.setattr(history_mod, "resolve_session_path_default", lambda n: None)
        client = TestClient(_app(history_mod.router))
        resp = client.get("/api/ghost/history")
        assert resp.status_code == 404

    def test_index_success(self, monkeypatch):
        monkeypatch.setattr(
            history_mod,
            "resolve_session_path_default",
            lambda n: Path("/x/s.kohakutr"),
        )
        monkeypatch.setattr(
            history_mod,
            "history_index_payload",
            lambda p: {"session_name": "s", "targets": ["a", "b"]},
        )
        client = TestClient(_app(history_mod.router))
        resp = client.get("/api/sess/history")
        assert resp.status_code == 200
        assert resp.json()["targets"] == ["a", "b"]

    def test_target_missing(self, monkeypatch):
        monkeypatch.setattr(history_mod, "resolve_session_path_default", lambda n: None)
        client = TestClient(_app(history_mod.router))
        resp = client.get("/api/ghost/history/alice")
        assert resp.status_code == 404

    def test_target_success(self, monkeypatch):
        monkeypatch.setattr(
            history_mod,
            "resolve_session_path_default",
            lambda n: Path("/x/s.kohakutr"),
        )
        monkeypatch.setattr(
            history_mod,
            "history_payload",
            lambda p, t, j=None, **k: {"target": t, "events": []},
        )
        client = TestClient(_app(history_mod.router))
        resp = client.get("/api/sess/history/alice")
        assert resp.status_code == 200
        assert resp.json()["target"] == "alice"

    def test_target_unquoted(self, monkeypatch):
        monkeypatch.setattr(
            history_mod,
            "resolve_session_path_default",
            lambda n: Path("/x/s.kohakutr"),
        )

        def fake_payload(p, t, j=None, **kwargs):
            return {"target": t, "events": []}

        monkeypatch.setattr(history_mod, "history_payload", fake_payload)
        client = TestClient(_app(history_mod.router))
        # URL-encoded "a:b" → "a%3Ab"
        resp = client.get("/api/sess/history/a%3Ab")
        assert resp.status_code == 200
        assert resp.json()["target"] == "a:b"

    def test_saved_target_passes_no_live_job_ids(self, monkeypatch):
        # A genuinely saved session (no live store) threads ``None`` so
        # the read-only interrupted-synthesis semantics are unchanged.
        monkeypatch.setattr(history_mod, "live_store_entry", lambda svc, n: None)
        monkeypatch.setattr(
            history_mod,
            "resolve_session_path_default",
            lambda n: Path("/x/s.kohakutr"),
        )
        captured = {}

        def fake_payload(p, t, j=None, **kwargs):
            captured["live"] = j
            return {"target": t, "events": []}

        monkeypatch.setattr(history_mod, "history_payload", fake_payload)
        client = TestClient(_app(history_mod.router))
        resp = client.get("/api/sess/history/root")
        assert resp.status_code == 200
        assert captured["live"] is None

    def test_live_target_threads_running_job_ids(self, monkeypatch):
        # A live-resolved session gathers the still-running job ids from
        # the host engine's live agents and threads them into the payload
        # so an in-flight sub-agent isn't synthesised as interrupted
        # (Bug 2). Uses the REAL ``_live_job_ids_for_graph`` gather and
        # must build from the ENGINE'S store, named by its file stem.
        fake_store = types.SimpleNamespace(_path="/x/live.kohakutr")
        monkeypatch.setattr(
            history_mod, "live_store_entry", lambda svc, n: ("live_g", fake_store)
        )
        engine = _FakeEngine(
            graph=_FakeGraph(["root"]),
            creatures={"root": _FakeCreature(_FakeAgent(["job_abc"]))},
        )
        captured = {}

        def fake_from_store(store, name, target, j=None, **kwargs):
            captured["store"] = store
            captured["name"] = name
            captured["live"] = j
            return {"target": target, "events": []}

        monkeypatch.setattr(history_mod, "history_from_store", fake_from_store)
        app = _app(history_mod.router)
        app.dependency_overrides[get_service] = lambda: engine
        resp = TestClient(app).get("/api/live_g/history/root")
        assert resp.status_code == 200
        assert captured["live"] == {"job_abc"}
        assert captured["store"] is fake_store
        assert captured["name"] == "live"

    def test_live_history_never_reopens_the_store_file(self, monkeypatch, tmp_path):
        # THE CI bug (POSIX): a second SessionStore open of the live,
        # actively-written file fails with SQLITE_IOERR. While the
        # session is live, history — addressed by graph_id OR by the
        # store's file stem — must reuse the engine's open store, so
        # every disk-open entry point is bombed.
        store_path = tmp_path / "alice_3f2a9c11.kohakutr"
        store = SessionStore(str(store_path))
        store.init_meta("alice", "agent", "/p", "/w", ["alice"])
        store.checkpoint()
        engine = _FakeEngine(graph=_FakeGraph([]), creatures={})
        engine._session_stores = {"graph_live1": store}

        def _bomb(*a, **k):
            raise AssertionError("live history must not open the session file")

        monkeypatch.setattr(history_mod, "resolve_session_path_default", _bomb)
        monkeypatch.setattr(history_mod, "history_index_payload", _bomb)
        monkeypatch.setattr(history_mod, "history_payload", _bomb)

        app = _app(history_mod.router)
        app.dependency_overrides[get_service] = lambda: engine
        client = TestClient(app)
        try:
            for name in ("graph_live1", "alice_3f2a9c11"):
                index = client.get(f"/api/{name}/history")
                assert index.status_code == 200, (name, index.text)
                assert index.json()["session_name"] == "alice_3f2a9c11"
                target = client.get(f"/api/{name}/history/alice")
                assert target.status_code == 200, (name, target.text)
        finally:
            store.close()


# ── history pagination ──────────────────────────────────────────


def _make_store(
    tmp_path: Path,
    *,
    agent: str = "alice",
    events: int = 0,
    channel_messages: int = 0,
    channel: str = "ops",
    content_size: int = 8,
) -> SessionStore:
    """Build a real store with numbered events and/or channel messages."""
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
        store.append_event(agent, "user_message", {"content": f"m{i}" * content_size})
    for i in range(channel_messages):
        store.save_channel_message(channel, {"sender": "a", "content": f"c{i}"})
    store.flush()
    return store


def _saved_client(monkeypatch, store: SessionStore):
    """Client that resolves the saved session to ``store``'s file."""
    monkeypatch.setattr(history_mod, "live_store_entry", lambda svc, n: None)
    monkeypatch.setattr(
        history_mod, "resolve_session_path_default", lambda n: Path(store.path)
    )
    app = _app(history_mod.router)
    return TestClient(app)


class TestHistoryPagination:
    def test_default_response_is_bounded(self, monkeypatch, tmp_path):
        # Without query params the route returns the MOST RECENT page
        # (≤ DEFAULT_HISTORY_PAGE_LIMIT events), never the full log.
        store = _make_store(tmp_path, events=450)
        try:
            client = _saved_client(monkeypatch, store)
            resp = client.get("/api/sess/history/alice")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["events"]) == 400
            assert body["has_more"] is True
            assert body["total"] == 450
            assert body["oldest_event_id"] == body["events"][0]["event_id"]
            # Chronological order preserved and the newest event is last.
            assert body["events"][-1]["content"].startswith("m449")
            assert body["events"][0]["content"].startswith("m50")
        finally:
            store.close()

    def test_limit_zero_returns_full_log(self, monkeypatch, tmp_path):
        store = _make_store(tmp_path, events=450)
        try:
            client = _saved_client(monkeypatch, store)
            resp = client.get("/api/sess/history/alice", params={"limit": 0})
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["events"]) == 450
            assert body["has_more"] is False
            assert body["total"] == 450
        finally:
            store.close()

    def test_cursor_walk_has_no_gaps_or_duplicates(self, monkeypatch, tmp_path):
        store = _make_store(tmp_path, events=250)
        try:
            client = _saved_client(monkeypatch, store)
            before = None
            seen: list[int] = []
            for _ in range(10):
                params = {"limit": 100}
                if before is not None:
                    params["before"] = before
                body = client.get("/api/sess/history/alice", params=params).json()
                ids = [e["event_id"] for e in body["events"]]
                assert len(ids) <= 100
                assert ids == sorted(ids)
                seen = ids + seen
                if not body["has_more"]:
                    break
                before = body["oldest_event_id"]
            assert seen == list(range(1, 251))
        finally:
            store.close()

    def test_byte_budget_caps_page_below_limit(self, monkeypatch, tmp_path):
        from kohakuterrarium.session import history_paging as paging_mod

        store = _make_store(tmp_path, events=50, content_size=100)
        try:
            monkeypatch.setattr(paging_mod, "DEFAULT_HISTORY_PAGE_BYTES", 10_000)
            client = _saved_client(monkeypatch, store)
            body = client.get("/api/sess/history/alice", params={"limit": 400}).json()
            assert 1 <= len(body["events"]) < 50
            assert body["has_more"] is True
            # The cursor stays consistent even on a byte-truncated page.
            before = body["oldest_event_id"]
            body2 = client.get(
                "/api/sess/history/alice", params={"limit": 400, "before": before}
            ).json()
            ids1 = [e["event_id"] for e in body["events"]]
            ids2 = [e["event_id"] for e in body2["events"]]
            assert not set(ids1) & set(ids2)
            assert max(ids2) < min(ids1)
        finally:
            store.close()

    def test_before_older_than_everything_returns_empty_page(
        self, monkeypatch, tmp_path
    ):
        store = _make_store(tmp_path, events=5)
        try:
            client = _saved_client(monkeypatch, store)
            body = client.get(
                "/api/sess/history/alice", params={"limit": 10, "before": 1}
            ).json()
            assert body["events"] == []
            assert body["has_more"] is False
            assert body["oldest_event_id"] is None
            assert body["total"] == 5
        finally:
            store.close()

    def test_negative_limit_is_rejected(self, monkeypatch, tmp_path):
        store = _make_store(tmp_path, events=5)
        try:
            client = _saved_client(monkeypatch, store)
            resp = client.get("/api/sess/history/alice", params={"limit": -1})
            assert resp.status_code == 422
        finally:
            store.close()

    def test_live_path_paginates_without_reopening_store(self, monkeypatch, tmp_path):
        # The live path keeps using the engine-owned store (SQLITE_IOERR)
        # and pages from it directly — disk-open entry points stay bombed.
        store = _make_store(tmp_path, events=10)
        engine = _FakeEngine(graph=_FakeGraph([]), creatures={})
        engine._session_stores = {"graph_live1": store}

        def _bomb(*a, **k):
            raise AssertionError("live history must not open the session file")

        monkeypatch.setattr(history_mod, "resolve_session_path_default", _bomb)
        monkeypatch.setattr(history_mod, "history_payload", _bomb)
        app = _app(history_mod.router)
        app.dependency_overrides[get_service] = lambda: engine
        client = TestClient(app)
        try:
            page1 = client.get(
                "/api/graph_live1/history/alice", params={"limit": 3}
            ).json()
            assert [e["event_id"] for e in page1["events"]] == [8, 9, 10]
            assert page1["has_more"] is True
            assert page1["total"] == 10
            page2 = client.get(
                "/api/graph_live1/history/alice",
                params={"limit": 3, "before": page1["oldest_event_id"]},
            ).json()
            assert [e["event_id"] for e in page2["events"]] == [5, 6, 7]
        finally:
            store.close()

    def test_channel_target_pagination(self, monkeypatch, tmp_path):
        store = _make_store(tmp_path, channel_messages=30)
        try:
            client = _saved_client(monkeypatch, store)
            page1 = client.get("/api/sess/history/ch:ops", params={"limit": 10}).json()
            assert len(page1["events"]) == 10
            assert page1["has_more"] is True
            assert page1["total"] == 30
            assert page1["events"][-1]["content"] == "c29"
            page2 = client.get(
                "/api/sess/history/ch:ops",
                params={"limit": 10, "before": page1["oldest_event_id"]},
            ).json()
            assert [e["content"] for e in page2["events"]] == [
                f"c{i}" for i in range(10, 20)
            ]
            assert page2["has_more"] is True
        finally:
            store.close()

    def test_older_pages_omit_conversation_snapshot(self, monkeypatch, tmp_path):
        # The conversation snapshot belongs to the newest window; carrying
        # it on every older page would duplicate megabytes per request.
        store = _make_store(tmp_path, events=5)
        try:
            store.save_conversation("alice", [{"role": "user", "content": "hi"}])
            store.flush()
            client = _saved_client(monkeypatch, store)
            page1 = client.get("/api/sess/history/alice", params={"limit": 2}).json()
            assert page1["messages"] == [{"role": "user", "content": "hi"}]
            page2 = client.get(
                "/api/sess/history/alice",
                params={"limit": 2, "before": page1["oldest_event_id"]},
            ).json()
            assert page2["messages"] == []
            assert len(page2["events"]) == 2
        finally:
            store.close()

    def test_studio_layer_default_stays_full(self, tmp_path):
        # Programmatic callers (studio facade) rely on the studio-layer
        # default: full payload, no page bound. Only the HTTP route
        # defaults to a page.
        store = _make_store(tmp_path, events=450)
        try:
            payload = history_mod.history_payload(Path(store.path), "alice")
            assert len(payload["events"]) == 450
            assert payload["has_more"] is False
            assert payload["total"] == 450
        finally:
            store.close()


class TestPageBoundaryInterruptSynthesis:
    """A page boundary must not fabricate "Interrupted by session resume".

    A ``before`` page can end on a ``tool_call`` whose real ``tool_result``
    lives in a NEWER page; synthesizing an interrupt there would fabricate
    a terminal that then coexists with the genuine result after the client
    accumulates both pages (P1). Older pages therefore skip the synthesis;
    the newest window keeps it (an unfinished call at the log tail IS dead
    for a saved session).
    """

    def _tool_store(self, tmp_path: Path) -> SessionStore:
        path = tmp_path / "alice_3f2a9c11.kohakutr"
        store = SessionStore(str(path))
        store.init_meta("alice", "agent", "/p", "/w", ["alice"])
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
        )  # id 5 — never finished (genuinely dead)
        store.flush()
        return store

    def test_older_page_does_not_synthesize_interrupt(self, monkeypatch, tmp_path):
        store = self._tool_store(tmp_path)
        try:
            monkeypatch.setattr(history_mod, "live_store_entry", lambda svc, n: None)
            monkeypatch.setattr(
                history_mod, "resolve_session_path_default", lambda n: Path(store.path)
            )
            client = TestClient(_app(history_mod.router))
            # Page ending exactly between tool_call j1 (id 2) and its
            # result (id 3): the boundary splits the pair.
            body = client.get(
                "/api/sess/history/alice",
                params={"limit": 10, "before": 3},
            ).json()
            ids = [e.get("event_id") for e in body["events"]]
            assert 2 in ids and 3 not in ids
            # Announcement repair may inject id-less assistant rows, but no
            # synthetic interrupt terminal may appear.
            assert not any(
                e.get("_synthetic_resume") or e.get("final_state") == "interrupted"
                for e in body["events"]
            )
        finally:
            store.close()

    def test_newest_page_still_synthesizes_for_dead_jobs(self, monkeypatch, tmp_path):
        store = self._tool_store(tmp_path)
        try:
            monkeypatch.setattr(history_mod, "live_store_entry", lambda svc, n: None)
            monkeypatch.setattr(
                history_mod, "resolve_session_path_default", lambda n: Path(store.path)
            )
            client = TestClient(_app(history_mod.router))
            body = client.get("/api/sess/history/alice", params={"limit": 2}).json()
            # The tail holds tool_call j2 with no result anywhere: the
            # interrupt synthesis must still fire on the newest window.
            synthetic = [
                e
                for e in body["events"]
                if e.get("_synthetic_resume") and e.get("call_id") == "j2"
            ]
            assert len(synthetic) == 1
            assert synthetic[0]["final_state"] == "interrupted"
        finally:
            store.close()
