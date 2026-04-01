"""Tests for session resume functionality."""

import json
from pathlib import Path

import pytest

from kohakuterrarium.core.conversation import Conversation
from kohakuterrarium.session.resume import detect_session_type
from kohakuterrarium.session.store import SessionStore


@pytest.fixture
def agent_session(tmp_path):
    """Create a populated agent session .kt file."""
    kt_path = tmp_path / "agent_session.kt"
    store = SessionStore(kt_path)

    store.init_meta(
        session_id="sess_test",
        config_type="agent",
        config_path="examples/agent-apps/swe_agent",
        pwd=str(tmp_path),
        agents=["swe_agent"],
    )

    # Simulate a conversation
    store.append_event(
        "swe_agent", "user_input", {"content": "Hello, summarize this project"}
    )
    store.append_event("swe_agent", "processing_start", {})
    store.append_event(
        "swe_agent", "text", {"content": "This is a Python agent framework."}
    )
    store.append_event(
        "swe_agent",
        "token_usage",
        {
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "total_tokens": 550,
        },
    )
    store.append_event("swe_agent", "processing_end", {})

    # Save conversation snapshot
    conv = Conversation()
    conv.append("system", "You are a helpful agent.")
    conv.append("user", "Hello, summarize this project")
    conv.append("assistant", "This is a Python agent framework.")
    store.save_conversation("swe_agent", conv.to_messages())

    # Save scratchpad
    store.save_state(
        "swe_agent", scratchpad={"plan": "step 1: read code", "status": "in_progress"}
    )

    store.close()
    return kt_path


@pytest.fixture
def terrarium_session(tmp_path):
    """Create a populated terrarium session .kt file."""
    kt_path = tmp_path / "terrarium_session.kt"
    store = SessionStore(kt_path)

    store.init_meta(
        session_id="sess_terr",
        config_type="terrarium",
        config_path="terrariums/swe_team",
        pwd=str(tmp_path),
        agents=["root", "swe", "reviewer"],
        terrarium_name="swe_team",
        terrarium_channels=[{"name": "tasks", "type": "queue"}],
        terrarium_creatures=[
            {"name": "swe", "listen": ["tasks"], "send": ["review"]},
        ],
    )

    # Root conversation
    root_conv = Conversation()
    root_conv.append("system", "You manage the terrarium.")
    root_conv.append("user", "Fix the auth bug")
    root_conv.append("assistant", "Dispatching to SWE.")
    store.save_conversation("root", root_conv.to_messages())
    store.save_state("root", scratchpad={"task": "auth bug fix"})

    # SWE conversation
    swe_conv = Conversation()
    swe_conv.append("system", "You are a software engineer.")
    swe_conv.append("user", "Fix auth bug in middleware.py")
    swe_conv.append("assistant", "Analyzing the auth module.")
    store.save_conversation("swe", swe_conv.to_messages())
    store.save_state("swe", scratchpad={"bug": "line 42"})

    # Channel messages
    store.save_channel_message("tasks", {"sender": "root", "content": "Fix auth bug"})

    store.close()
    return kt_path


class TestDetectSessionType:
    def test_detect_agent(self, agent_session):
        assert detect_session_type(agent_session) == "agent"

    def test_detect_terrarium(self, terrarium_session):
        assert detect_session_type(terrarium_session) == "terrarium"


class TestSessionStoreRoundTrip:
    """Test that data survives a store close + reopen cycle."""

    def test_conversation_roundtrip(self, agent_session):
        store = SessionStore(agent_session)
        messages = store.load_conversation("swe_agent")
        assert messages is not None
        assert isinstance(messages, list)
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello, summarize this project"
        assert messages[2]["role"] == "assistant"
        assert "Python agent framework" in messages[2]["content"]
        store.close()

    def test_scratchpad_roundtrip(self, agent_session):
        store = SessionStore(agent_session)
        pad = store.load_scratchpad("swe_agent")
        assert pad == {"plan": "step 1: read code", "status": "in_progress"}
        store.close()

    def test_events_roundtrip(self, agent_session):
        store = SessionStore(agent_session)
        events = store.get_events("swe_agent")
        assert len(events) == 5
        assert events[0]["type"] == "user_input"
        assert events[0]["content"] == "Hello, summarize this project"
        assert events[4]["type"] == "processing_end"
        store.close()

    def test_terrarium_multi_agent_roundtrip(self, terrarium_session):
        store = SessionStore(terrarium_session)

        # Root conversation
        root_msgs = store.load_conversation("root")
        assert root_msgs is not None
        assert len(root_msgs) == 3
        assert root_msgs[1]["content"] == "Fix the auth bug"

        # SWE conversation
        swe_msgs = store.load_conversation("swe")
        assert swe_msgs is not None
        assert len(swe_msgs) == 3
        assert "auth module" in swe_msgs[2]["content"]

        # Scratchpads
        assert store.load_scratchpad("root") == {"task": "auth bug fix"}
        assert store.load_scratchpad("swe") == {"bug": "line 42"}

        # Channel messages
        tasks_msgs = store.get_channel_messages("tasks")
        assert len(tasks_msgs) == 1
        assert tasks_msgs[0]["sender"] == "root"

        store.close()

    def test_meta_roundtrip(self, terrarium_session):
        store = SessionStore(terrarium_session)
        meta = store.load_meta()
        assert meta["config_type"] == "terrarium"
        assert meta["terrarium_name"] == "swe_team"
        assert "root" in meta["agents"]
        assert "swe" in meta["agents"]
        store.close()


class TestConversationInjection:
    """Test that we can inject a loaded conversation into a controller."""

    def test_conversation_from_json_and_inject(self):
        """Simulate the resume flow: create conv, serialize, deserialize, verify."""
        # Create original conversation
        original = Conversation()
        original.append("system", "You are helpful.")
        original.append("user", "What is 2+2?")
        original.append("assistant", "4")
        original.append("user", "And 3+3?")
        original.append("assistant", "6")

        # Serialize
        json_str = original.to_json()

        # Deserialize (this is what resume does)
        restored = Conversation.from_json(json_str)

        # Verify
        original_msgs = original.to_messages()
        restored_msgs = restored.to_messages()
        assert len(restored_msgs) == len(original_msgs)
        for orig, rest in zip(original_msgs, restored_msgs):
            assert orig["role"] == rest["role"]
            assert orig["content"] == rest["content"]

    def test_conversation_with_tool_calls_roundtrip(self):
        """Verify tool_calls survive msgpack roundtrip via to_messages."""
        conv = Conversation()
        conv.append("system", "You have tools.")
        conv.append("user", "List files")
        conv.append(
            "assistant",
            "",
            tool_calls=[
                {
                    "id": "tc_001",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command": "ls"}'},
                }
            ],
        )
        conv.append("tool", "file1.py\nfile2.py", tool_call_id="tc_001", name="bash")
        conv.append("assistant", "There are 2 files.")

        # Simulate save/load via SessionStore (msgpack roundtrip)
        messages = conv.to_messages()
        assert messages[2].get("tool_calls") is not None
        assert messages[2]["tool_calls"][0]["function"]["name"] == "bash"
        assert messages[3]["role"] == "tool"
        assert messages[3]["tool_call_id"] == "tc_001"

        # Rebuild conversation from messages (resume path)
        from kohakuterrarium.session.resume import _build_conversation

        restored = _build_conversation(messages)
        restored_msgs = restored.to_messages()
        assert len(restored_msgs) == 5
        assert restored_msgs[2].get("tool_calls") is not None
        assert restored_msgs[2]["tool_calls"][0]["function"]["name"] == "bash"
        assert restored_msgs[3]["tool_call_id"] == "tc_001"


class TestResumeEdgeCases:
    def test_resume_empty_conversation(self, tmp_path):
        """Resume with no saved conversation should work (fresh start)."""
        kt_path = tmp_path / "empty.kt"
        store = SessionStore(kt_path)
        store.init_meta(
            session_id="empty",
            config_type="agent",
            config_path="examples/agent-apps/swe_agent",
            pwd=str(tmp_path),
            agents=["swe_agent"],
        )
        store.close()

        # Reopen and verify no conversation
        store2 = SessionStore(kt_path)
        assert store2.load_conversation("swe_agent") is None
        assert store2.load_scratchpad("swe_agent") == {}
        store2.close()

    def test_resume_empty_scratchpad(self, agent_session):
        """Resume with empty scratchpad should not error."""
        store = SessionStore(agent_session)
        # Overwrite scratchpad with empty
        store.save_state("swe_agent", scratchpad={})
        pad = store.load_scratchpad("swe_agent")
        assert pad == {}
        store.close()

    def test_multiple_resume_cycles(self, tmp_path):
        """Simulate multiple save/resume cycles."""
        kt_path = tmp_path / "multi.kt"

        # Cycle 1: create and save
        store = SessionStore(kt_path)
        store.init_meta(
            session_id="multi",
            config_type="agent",
            config_path="test",
            pwd=str(tmp_path),
            agents=["agent"],
        )
        conv1 = Conversation()
        conv1.append("system", "You are helpful.")
        conv1.append("user", "Hello")
        conv1.append("assistant", "Hi!")
        store.save_conversation("agent", conv1.to_messages())
        store.save_state("agent", scratchpad={"cycle": "1"})
        store.append_event("agent", "user_input", {"content": "Hello"})
        store.close()

        # Cycle 2: resume, add more, save
        store = SessionStore(kt_path)
        messages = store.load_conversation("agent")
        assert len(messages) == 3

        # Simulate adding more turns
        messages.append({"role": "user", "content": "How are you?"})
        messages.append({"role": "assistant", "content": "I'm fine!"})
        store.save_conversation("agent", messages)
        store.save_state("agent", scratchpad={"cycle": "2"})
        store.append_event("agent", "user_input", {"content": "How are you?"})
        store.close()

        # Cycle 3: verify accumulated state
        store = SessionStore(kt_path)
        messages = store.load_conversation("agent")
        assert len(messages) == 5
        assert messages[3]["content"] == "How are you?"

        pad = store.load_scratchpad("agent")
        assert pad["cycle"] == "2"

        events = store.get_events("agent")
        assert len(events) == 2
        assert events[0]["content"] == "Hello"
        assert events[1]["content"] == "How are you?"
        store.close()
