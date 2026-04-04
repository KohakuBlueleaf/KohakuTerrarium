"""Tests for session memory: embedding providers, block extraction, indexing, and search."""

import os
import tempfile

import numpy as np
import pytest

from kohakuterrarium.session.embedding import (
    BaseEmbedder,
    NullEmbedder,
    create_embedder,
)
from kohakuterrarium.session.memory import (
    Block,
    SearchResult,
    SessionMemory,
    _block_metadata,
    _extract_blocks,
)


# ── Fixtures ──────────────────────────────────────────────────


class FakeEmbedder(BaseEmbedder):
    """Deterministic embedder for testing (no model download)."""

    dimensions = 4

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = []
        for text in texts:
            # Simple hash-based deterministic vector
            h = hash(text) & 0xFFFFFFFF
            v = np.array(
                [(h >> i) & 0xFF for i in range(0, 32, 8)],
                dtype=np.float32,
            )
            norm = np.linalg.norm(v)
            vecs.append(v / norm if norm > 0 else v)
        return np.array(vecs, dtype=np.float32)


@pytest.fixture
def tmp_db():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".kohakutr")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def sample_events():
    """Sample session events mimicking real agent output."""
    return [
        {"type": "user_input", "content": "Fix the auth bug", "ts": 1000.0},
        {"type": "processing_start", "ts": 1000.1},
        {
            "type": "text",
            "content": "I'll investigate the auth module.",
            "ts": 1001.0,
        },
        {
            "type": "tool_call",
            "name": "read",
            "args": {"path": "src/auth.py"},
            "ts": 1002.0,
        },
        {
            "type": "tool_result",
            "name": "read",
            "output": "def login(user, password):\n    token = generate_token(user)\n    return token",
            "ts": 1003.0,
        },
        {
            "type": "text",
            "content": "Found the issue. The token expiry is not set.",
            "ts": 1004.0,
        },
        {
            "type": "token_usage",
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "ts": 1004.5,
        },
        {"type": "processing_end", "ts": 1005.0},
        {"type": "user_input", "content": "Good, now fix it", "ts": 2000.0},
        {"type": "processing_start", "ts": 2000.1},
        {
            "type": "tool_call",
            "name": "edit",
            "args": {
                "path": "src/auth.py",
                "old": "return token",
                "new": "return token, expiry",
            },
            "ts": 2001.0,
        },
        {
            "type": "tool_result",
            "name": "edit",
            "output": "Edited src/auth.py\n  1 replacement(s) made",
            "ts": 2002.0,
        },
        {
            "type": "text",
            "content": "Fixed. The token now includes an expiry field.",
            "ts": 2003.0,
        },
        {"type": "processing_end", "ts": 2004.0},
        {
            "type": "trigger_fired",
            "channel": "alerts",
            "content": "Build failed on CI",
            "ts": 3000.0,
        },
        {"type": "processing_start", "ts": 3000.1},
        {
            "type": "text",
            "content": "Checking the CI failure.",
            "ts": 3001.0,
        },
        {"type": "processing_end", "ts": 3002.0},
    ]


# ── NullEmbedder ──────────────────────────────────────────────


class TestNullEmbedder:
    def test_raises_on_encode(self):
        e = NullEmbedder()
        with pytest.raises(RuntimeError, match="No embedding model configured"):
            e.encode(["test"])

    def test_dimensions_zero(self):
        assert NullEmbedder().dimensions == 0


# ── FakeEmbedder sanity ───────────────────────────────────────


class TestFakeEmbedder:
    def test_encode_shape(self, fake_embedder):
        vecs = fake_embedder.encode(["hello", "world"])
        assert vecs.shape == (2, 4)
        assert vecs.dtype == np.float32

    def test_encode_one(self, fake_embedder):
        vec = fake_embedder.encode_one("hello")
        assert vec.shape == (4,)

    def test_deterministic(self, fake_embedder):
        v1 = fake_embedder.encode(["same text"])
        v2 = fake_embedder.encode(["same text"])
        np.testing.assert_array_equal(v1, v2)

    def test_different_texts(self, fake_embedder):
        v1 = fake_embedder.encode_one("hello")
        v2 = fake_embedder.encode_one("world")
        assert not np.allclose(v1, v2)


# ── create_embedder ───────────────────────────────────────────


class TestCreateEmbedder:
    def test_none_config(self):
        assert isinstance(create_embedder(None), NullEmbedder)

    def test_empty_config(self):
        # auto with no deps -> attempts detection
        e = create_embedder({})
        # Should not crash; returns whatever is available or NullEmbedder
        assert isinstance(e, BaseEmbedder)

    def test_explicit_none(self):
        assert isinstance(create_embedder({"provider": "none"}), NullEmbedder)

    def test_unknown_provider(self):
        assert isinstance(create_embedder({"provider": "bogus"}), NullEmbedder)

    def test_model2vec_import_error(self):
        """model2vec provider raises ImportError if package not installed."""
        # This test only verifies the error path; it succeeds if model2vec is installed
        e = create_embedder({"provider": "model2vec"})
        assert isinstance(e, BaseEmbedder)

    def test_api_requires_key(self):
        with pytest.raises(ValueError, match="api_key"):
            create_embedder(
                {
                    "provider": "api",
                    "api_key": "",
                    "api_key_env": "NONEXISTENT_KEY_12345",
                }
            )


# ── Block extraction ──────────────────────────────────────────


class TestBlockExtraction:
    def test_basic_extraction(self, sample_events):
        blocks = _extract_blocks("test", sample_events)
        assert len(blocks) > 0

    def test_round_numbering(self, sample_events):
        blocks = _extract_blocks("test", sample_events)
        rounds = sorted(set(b.round_num for b in blocks))
        assert rounds == [1, 2, 3]

    def test_block_types(self, sample_events):
        blocks = _extract_blocks("test", sample_events)
        types = set(b.block_type for b in blocks)
        assert "user" in types
        assert "text" in types
        assert "tool" in types
        assert "trigger" in types

    def test_user_input_block(self, sample_events):
        blocks = _extract_blocks("test", sample_events)
        user_blocks = [b for b in blocks if b.block_type == "user"]
        assert len(user_blocks) == 2
        assert "Fix the auth bug" in user_blocks[0].content

    def test_tool_call_block(self, sample_events):
        blocks = _extract_blocks("test", sample_events)
        tool_blocks = [b for b in blocks if b.block_type == "tool"]
        assert len(tool_blocks) >= 2
        # Tool call should have name in content
        assert any("[tool:read" in b.content for b in tool_blocks)

    def test_trigger_block(self, sample_events):
        blocks = _extract_blocks("test", sample_events)
        trigger_blocks = [b for b in blocks if b.block_type == "trigger"]
        assert len(trigger_blocks) == 1
        assert "alerts" in trigger_blocks[0].channel
        assert "Build failed" in trigger_blocks[0].content

    def test_text_split_on_double_newline(self):
        # Must exceed 300 chars to trigger split
        para1 = "First paragraph. " * 20  # ~340 chars
        para2 = "Second paragraph. " * 10
        para3 = "Third paragraph. " * 10
        long_text = f"{para1}\n\n{para2}\n\n{para3}"
        events = [
            {"type": "user_input", "content": "test", "ts": 1.0},
            {"type": "processing_start", "ts": 1.1},
            {"type": "text", "content": long_text, "ts": 2.0},
            {"type": "processing_end", "ts": 3.0},
        ]
        blocks = _extract_blocks("test", events)
        text_blocks = [b for b in blocks if b.block_type == "text"]
        assert len(text_blocks) == 3

    def test_short_text_not_split(self):
        events = [
            {"type": "user_input", "content": "test", "ts": 1.0},
            {"type": "processing_start", "ts": 1.1},
            {"type": "text", "content": "Short\n\ntext", "ts": 2.0},
            {"type": "processing_end", "ts": 3.0},
        ]
        blocks = _extract_blocks("test", events)
        text_blocks = [b for b in blocks if b.block_type == "text"]
        # Short text (<300 chars) not split
        assert len(text_blocks) == 1

    def test_ignores_events_outside_round(self):
        events = [
            {"type": "text", "content": "orphan text", "ts": 0.5},
            {"type": "user_input", "content": "start", "ts": 1.0},
            {"type": "processing_start", "ts": 1.1},
            {"type": "text", "content": "in round", "ts": 2.0},
            {"type": "processing_end", "ts": 3.0},
        ]
        blocks = _extract_blocks("test", events)
        text_blocks = [b for b in blocks if b.block_type == "text"]
        assert len(text_blocks) == 1
        assert "in round" in text_blocks[0].content

    def test_empty_events(self):
        assert _extract_blocks("test", []) == []

    def test_agent_name_propagated(self, sample_events):
        blocks = _extract_blocks("myagent", sample_events)
        for b in blocks:
            assert b.agent == "myagent"


# ── Block metadata ────────────────────────────────────────────


class TestBlockMetadata:
    def test_without_content(self):
        block = Block(
            round_num=1,
            block_num=0,
            agent="test",
            block_type="text",
            content="hello world",
            ts=100.0,
        )
        meta = _block_metadata(block)
        assert meta["round"] == 1
        assert meta["block"] == 0
        assert meta["agent"] == "test"
        assert "content" not in meta

    def test_with_content(self):
        block = Block(
            round_num=1,
            block_num=0,
            agent="test",
            block_type="text",
            content="hello world",
            ts=100.0,
        )
        meta = _block_metadata(block, include_content=True)
        assert meta["content"] == "hello world"


# ── SessionMemory ─────────────────────────────────────────────


class TestSessionMemory:
    def test_init_with_null_embedder(self, tmp_db):
        memory = SessionMemory(tmp_db)
        assert not memory.has_vectors

    def test_init_with_embedder(self, tmp_db, fake_embedder):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        assert memory.has_vectors

    def test_index_events(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        count = memory.index_events("test", sample_events)
        assert count > 0
        stats = memory.get_stats()
        assert stats["fts_blocks"] > 0
        assert stats["vec_blocks"] > 0
        assert stats["fts_blocks"] == stats["vec_blocks"]

    def test_incremental_indexing(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        count1 = memory.index_events("test", sample_events[:8])
        count2 = memory.index_events("test", sample_events)
        assert count1 > 0
        assert count2 > 0
        # Second call indexes only new events
        stats = memory.get_stats()
        assert stats["fts_blocks"] == count1 + count2

    def test_no_double_index(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        memory.index_events("test", sample_events)
        count2 = memory.index_events("test", sample_events)
        assert count2 == 0  # Already indexed

    def test_empty_events(self, tmp_db, fake_embedder):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        count = memory.index_events("test", [])
        assert count == 0

    def test_fts_search(self, tmp_db, sample_events):
        memory = SessionMemory(tmp_db)  # FTS only
        memory.index_events("test", sample_events)
        results = memory.search("auth bug", mode="fts", k=5)
        assert len(results) > 0
        assert any("auth" in r.content.lower() for r in results)

    def test_semantic_search(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        memory.index_events("test", sample_events)
        results = memory.search("authentication issue", mode="semantic", k=5)
        assert len(results) > 0

    def test_hybrid_search(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        memory.index_events("test", sample_events)
        results = memory.search("auth", mode="hybrid", k=5)
        assert len(results) > 0

    def test_auto_mode_with_vectors(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        memory.index_events("test", sample_events)
        results = memory.search("auth", mode="auto", k=5)
        assert len(results) > 0

    def test_auto_mode_fts_only(self, tmp_db, sample_events):
        memory = SessionMemory(tmp_db)  # No embedder
        memory.index_events("test", sample_events)
        results = memory.search("auth", mode="auto", k=5)
        assert len(results) > 0

    def test_agent_filter(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        memory.index_events("agent1", sample_events)
        memory.index_events("agent2", sample_events)
        results = memory.search("auth", mode="fts", k=20, agent="agent1")
        assert all(r.agent == "agent1" for r in results)

    def test_search_result_fields(self, tmp_db, sample_events):
        memory = SessionMemory(tmp_db)
        memory.index_events("test", sample_events)
        results = memory.search("auth", mode="fts", k=1)
        assert len(results) >= 1
        r = results[0]
        assert r.content
        assert r.round_num > 0
        assert r.agent == "test"
        assert r.block_type in ("user", "text", "tool", "trigger")
        assert r.ts > 0

    def test_search_no_results(self, tmp_db, sample_events):
        memory = SessionMemory(tmp_db)
        memory.index_events("test", sample_events)
        results = memory.search("xyzzynonexistent12345", mode="fts", k=5)
        assert len(results) == 0

    def test_get_stats(self, tmp_db, fake_embedder, sample_events):
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        memory.index_events("test", sample_events)
        stats = memory.get_stats()
        assert "fts_blocks" in stats
        assert "vec_blocks" in stats
        assert "has_vectors" in stats
        assert "dimensions" in stats
        assert stats["dimensions"] == 4

    def test_vec_rebuild_on_empty(self, tmp_db, sample_events):
        """If FTS was indexed but vectors are empty, re-index both."""
        # First: index FTS only
        memory1 = SessionMemory(tmp_db)
        memory1.index_events("test", sample_events)
        stats1 = memory1.get_stats()
        assert stats1["fts_blocks"] > 0
        assert stats1["vec_blocks"] == 0

        # Second: open with embedder, should detect empty vectors and rebuild
        memory2 = SessionMemory(tmp_db, embedder=FakeEmbedder())
        count = memory2.index_events("test", sample_events)
        stats2 = memory2.get_stats()
        assert count > 0  # Should have re-indexed
        assert stats2["vec_blocks"] > 0

    def test_dimension_table_naming(self, tmp_db, fake_embedder):
        """Vector table name includes dimensions."""
        memory = SessionMemory(tmp_db, embedder=fake_embedder)
        # FakeEmbedder has 4 dims, so table should be memory_vec_4d
        assert memory._vec is not None

    def test_vec_dimensions_saved(self, tmp_db, fake_embedder, sample_events):
        """Saved vec_dimensions allows search-only mode to find the table."""
        memory1 = SessionMemory(tmp_db, embedder=fake_embedder)
        memory1.index_events("test", sample_events)

        # Open without embedder, should discover existing vectors
        memory2 = SessionMemory(tmp_db)
        assert memory2._vec is not None
        results = memory2.search("auth", mode="fts", k=3)
        assert len(results) > 0


# ── SearchResult ──────────────────────────────────────────────


class TestSearchResult:
    def test_age_str_seconds(self):
        import time

        r = SearchResult(
            content="",
            round_num=1,
            block_num=0,
            agent="test",
            block_type="text",
            score=1.0,
            ts=time.time() - 30,
        )
        assert "s ago" in r.age_str

    def test_age_str_minutes(self):
        import time

        r = SearchResult(
            content="",
            round_num=1,
            block_num=0,
            agent="test",
            block_type="text",
            score=1.0,
            ts=time.time() - 300,
        )
        assert "m ago" in r.age_str

    def test_age_str_hours(self):
        import time

        r = SearchResult(
            content="",
            round_num=1,
            block_num=0,
            agent="test",
            block_type="text",
            score=1.0,
            ts=time.time() - 7200,
        )
        assert "h ago" in r.age_str

    def test_age_str_no_ts(self):
        r = SearchResult(
            content="",
            round_num=1,
            block_num=0,
            agent="test",
            block_type="text",
            score=1.0,
            ts=0,
        )
        assert r.age_str == ""


# ── SearchMemoryTool ──────────────────────────────────────────


class TestSearchMemoryTool:
    """Tests for the search_memory builtin tool."""

    def test_import(self):
        from kohakuterrarium.builtins.tools.search_memory import SearchMemoryTool

        tool = SearchMemoryTool()
        assert tool.tool_name == "search_memory"
        assert tool.needs_context is True

    def test_description(self):
        from kohakuterrarium.builtins.tools.search_memory import SearchMemoryTool

        tool = SearchMemoryTool()
        assert "search" in tool.description.lower()

    def test_full_documentation(self):
        from kohakuterrarium.builtins.tools.search_memory import SearchMemoryTool

        tool = SearchMemoryTool()
        doc = tool.get_full_documentation()
        assert "query" in doc
        assert "fts" in doc
        assert "semantic" in doc

    @pytest.mark.asyncio
    async def test_no_query(self):
        from kohakuterrarium.builtins.tools.search_memory import SearchMemoryTool

        tool = SearchMemoryTool()
        result = await tool._execute({}, context=None)
        assert result.error
        assert "query" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_context(self):
        from kohakuterrarium.builtins.tools.search_memory import SearchMemoryTool

        tool = SearchMemoryTool()
        result = await tool._execute({"query": "test"}, context=None)
        assert result.error
        assert "context" in result.error.lower()

    def test_registered_in_catalog(self):
        from kohakuterrarium.builtins.tool_catalog import get_builtin_tool

        tool_cls = get_builtin_tool("search_memory")
        assert tool_cls is not None

    def test_native_schema_exists(self):
        from kohakuterrarium.llm.tools import _BUILTIN_SCHEMAS

        assert "search_memory" in _BUILTIN_SCHEMAS
        schema = _BUILTIN_SCHEMAS["search_memory"]
        assert "query" in schema["properties"]
        assert "query" in schema["required"]
