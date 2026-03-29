"""Integration tests for agent pipeline using test infrastructure."""

import pytest

from kohakuterrarium.testing import (
    OutputRecorder,
    ScriptedLLM,
    ScriptEntry,
    TestAgentBuilder,
)


class TestBasicPipeline:
    """Test basic agent pipeline with scripted LLM."""

    async def test_simple_text_response(self):
        """LLM text response reaches output."""
        env = (
            TestAgentBuilder()
            .with_llm_script(["Hello! How can I help?"])
            .build()
        )

        await env.inject("Hi there")

        assert env.output.has_output
        assert "Hello" in env.output.all_text
        assert env.llm.call_count == 1

    async def test_multiple_turns(self):
        """Multiple inject calls create multiple turns."""
        env = (
            TestAgentBuilder()
            .with_llm_script(["First response", "Second response"])
            .build()
        )

        await env.inject("Turn 1")
        assert "First" in env.output.all_text

        env.output.clear_all()

        await env.inject("Turn 2")
        assert "Second" in env.output.all_text
        assert env.llm.call_count == 2

    async def test_system_prompt_reaches_llm(self):
        """Custom system prompt is included in LLM messages."""
        env = (
            TestAgentBuilder()
            .with_system_prompt("You are a pirate assistant.")
            .with_llm_script(["Arrr!"])
            .build()
        )

        await env.inject("Hello")

        messages = env.llm.call_log[0]
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert "pirate" in system_msg["content"]

    async def test_ephemeral_mode_configured(self):
        """Ephemeral mode is set on the controller."""
        env = (
            TestAgentBuilder()
            .with_llm_script(["Response 1", "Response 2"])
            .with_ephemeral()
            .build()
        )

        assert env.controller.is_ephemeral
        # Note: env.inject doesn't call controller.flush() directly.
        # Ephemeral flushing happens in Agent._process_event_with_controller
        # which is not used in TestAgentEnv. This test documents that gap.


class TestLLMScriptMatching:
    """Test ScriptedLLM entry matching."""

    async def test_sequential_responses(self):
        """Entries used in order."""
        env = (
            TestAgentBuilder()
            .with_llm_script(["First", "Second", "Third"])
            .build()
        )

        await env.inject("a")
        assert "First" in env.output.all_text

        env.output.clear_all()
        await env.inject("b")
        assert "Second" in env.output.all_text

    async def test_match_based_response(self):
        """Match-based entries respond to specific input."""
        env = (
            TestAgentBuilder()
            .with_llm(ScriptedLLM([
                ScriptEntry("I'll search for it.", match="find"),
                ScriptEntry("I don't understand."),
            ]))
            .build()
        )

        await env.inject("Please find the bug")
        assert "search" in env.output.all_text


class TestNamedOutputs:
    """Test named output routing through pipeline."""

    async def test_output_block_routes_to_named(self):
        """Output blocks in LLM response route to named modules."""
        discord_rec = OutputRecorder()

        env = (
            TestAgentBuilder()
            .with_llm_script(["[/output_discord]Hello Discord![output_discord/]"])
            .with_named_output("discord", discord_rec)
            .build()
        )

        await env.inject("Send a message to discord")

        # Discord recorder got the content
        assert "Hello Discord!" in discord_rec.all_text

    async def test_mixed_text_and_output(self):
        """LLM can produce both regular text and named output."""
        api_rec = OutputRecorder()

        env = (
            TestAgentBuilder()
            .with_llm_script([
                "Thinking about it...\n[/output_api]API response here[output_api/]",
            ])
            .with_named_output("api", api_rec)
            .build()
        )

        await env.inject("Process this")

        # Main output got the thinking text
        assert "Thinking" in env.output.stream_text
        # API output got the API response
        assert "API response" in api_rec.all_text
