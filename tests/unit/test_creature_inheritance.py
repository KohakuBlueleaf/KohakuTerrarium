"""
Creature Hierarchy and Agent Inheritance Tests

Tests for:
- base_config loading and merging
- Child overrides parent values
- System prompt comes from child if specified, parent otherwise
- Tools list from child if specified, parent otherwise
- Recursive inheritance (grandparent -> parent -> child)

These tests run offline without API keys.
"""

from pathlib import Path

import pytest
import yaml

from kohakuterrarium.core.config import (
    _merge_configs,
    _resolve_base_config_path,
    load_agent_config,
)


@pytest.fixture
def tmp_creatures(tmp_path):
    """Create a temporary creature hierarchy for testing."""
    # Base creature: general
    general = tmp_path / "creatures" / "general"
    general.mkdir(parents=True)
    (general / "prompts").mkdir()

    (general / "config.yaml").write_text(
        yaml.dump(
            {
                "name": "general",
                "version": "1.0",
                "controller": {
                    "model": "base-model",
                    "reasoning_effort": "medium",
                    "tool_format": "native",
                },
                "system_prompt_file": "prompts/system.md",
                "skill_mode": "dynamic",
                "tools": [
                    {"name": "bash", "type": "builtin"},
                    {"name": "read", "type": "builtin"},
                    {"name": "write", "type": "builtin"},
                    {"name": "think", "type": "builtin"},
                ],
                "subagents": [
                    {"name": "explore", "type": "builtin"},
                    {"name": "plan", "type": "builtin"},
                ],
            }
        )
    )
    (general / "prompts" / "system.md").write_text(
        "# General Agent\n\nYou are a general-purpose assistant.\n"
    )

    # SWE creature inheriting from general
    swe = tmp_path / "creatures" / "swe"
    swe.mkdir(parents=True)
    (swe / "prompts").mkdir()

    (swe / "config.yaml").write_text(
        yaml.dump(
            {
                "name": "swe",
                "version": "1.0",
                "base_config": "../general",
                "controller": {"reasoning_effort": "high"},
                "system_prompt_file": "prompts/system.md",
            }
        )
    )
    (swe / "prompts" / "system.md").write_text(
        "# SWE Agent\n\nYou are a software engineering agent.\n"
    )

    # Agent inheriting from swe (two-level inheritance via creatures/ path)
    agent = tmp_path / "agents" / "my_agent"
    agent.mkdir(parents=True)

    (agent / "config.yaml").write_text(
        yaml.dump(
            {
                "name": "my_agent",
                "version": "2.0",
                "base_config": "creatures/swe",
                "controller": {
                    "model": "agent-model",
                    "api_key_env": "MY_KEY",
                    "base_url": "https://example.com/v1",
                },
                "input": {"type": "cli", "prompt": "> "},
                "output": {"type": "stdout", "controller_direct": True},
            }
        )
    )

    return tmp_path


class TestMergeConfigs:
    """Tests for the _merge_configs function."""

    def test_child_overrides_scalars(self):
        base = {"name": "base", "version": "1.0", "skill_mode": "dynamic"}
        child = {"name": "child", "version": "2.0"}
        result = _merge_configs(base, child)
        assert result["name"] == "child"
        assert result["version"] == "2.0"
        assert result["skill_mode"] == "dynamic"  # inherited

    def test_child_extends_tool_lists(self):
        base = {
            "tools": [{"name": "bash"}, {"name": "read"}],
            "subagents": [{"name": "explore"}],
        }
        child = {"tools": [{"name": "grep"}]}
        result = _merge_configs(base, child)
        # Child tools extend base tools (not replace)
        assert len(result["tools"]) == 3
        tool_names = [t["name"] for t in result["tools"]]
        assert tool_names == ["bash", "read", "grep"]
        assert result["subagents"] == [{"name": "explore"}]  # inherited

    def test_child_extends_deduplicates(self):
        base = {
            "tools": [{"name": "bash"}, {"name": "read"}],
        }
        child = {"tools": [{"name": "bash"}, {"name": "grep"}]}
        result = _merge_configs(base, child)
        # bash already in base, so only grep is added
        assert len(result["tools"]) == 3
        tool_names = [t["name"] for t in result["tools"]]
        assert tool_names == ["bash", "read", "grep"]

    def test_dicts_are_shallow_merged(self):
        base = {"controller": {"model": "base-model", "temperature": 0.7}}
        child = {"controller": {"model": "child-model"}}
        result = _merge_configs(base, child)
        assert result["controller"]["model"] == "child-model"
        assert result["controller"]["temperature"] == 0.7

    def test_none_values_not_applied(self):
        base = {"name": "base", "model": "base-model"}
        child = {"name": "child", "model": None}
        result = _merge_configs(base, child)
        assert result["model"] == "base-model"

    def test_base_config_key_excluded(self):
        base = {"name": "base"}
        child = {"name": "child", "base_config": "../base"}
        result = _merge_configs(base, child)
        assert "base_config" not in result


class TestResolveBaseConfigPath:
    """Tests for base_config path resolution."""

    def test_relative_path(self, tmp_path):
        child = tmp_path / "creatures" / "swe"
        child.mkdir(parents=True)
        base = tmp_path / "creatures" / "general"
        base.mkdir(parents=True)

        result = _resolve_base_config_path("../general", child)
        assert result is not None
        assert result.name == "general"

    def test_creatures_prefix_path(self, tmp_path):
        creatures = tmp_path / "creatures" / "swe"
        creatures.mkdir(parents=True)
        general = tmp_path / "creatures" / "general"
        general.mkdir(parents=True)

        agent = tmp_path / "agents" / "my_agent"
        agent.mkdir(parents=True)

        result = _resolve_base_config_path("creatures/swe", agent)
        assert result is not None
        assert result.name == "swe"

    def test_nonexistent_path_returns_none(self, tmp_path):
        child = tmp_path / "creatures" / "swe"
        child.mkdir(parents=True)

        result = _resolve_base_config_path("../nonexistent", child)
        assert result is None


class TestLoadAgentConfigInheritance:
    """Tests for config inheritance via load_agent_config."""

    def test_basic_inheritance(self, tmp_creatures):
        """Child inherits tools and subagents from parent."""
        swe = tmp_creatures / "creatures" / "swe"
        config = load_agent_config(swe)

        assert config.name == "swe"
        # Inherits tools from general (swe doesn't define tools)
        assert len(config.tools) == 4
        tool_names = [t.name for t in config.tools]
        assert "bash" in tool_names
        assert "think" in tool_names

        # Inherits subagents from general
        assert len(config.subagents) == 2
        agent_names = [s.name for s in config.subagents]
        assert "explore" in agent_names

    def test_child_overrides_controller(self, tmp_creatures):
        """Child controller values override parent."""
        swe = tmp_creatures / "creatures" / "swe"
        config = load_agent_config(swe)

        # SWE overrides reasoning_effort but inherits model from general
        assert config.reasoning_effort == "high"
        assert config.model == "base-model"
        assert config.tool_format == "native"  # inherited

    def test_child_system_prompt_appended(self, tmp_creatures):
        """Child system prompt is appended to base, not replaced."""
        swe = tmp_creatures / "creatures" / "swe"
        config = load_agent_config(swe)

        # Base prompt is included (from general)
        assert "General Agent" in config.system_prompt
        assert "general-purpose assistant" in config.system_prompt
        # Child prompt is appended (from swe)
        assert "SWE Agent" in config.system_prompt
        assert "software engineering" in config.system_prompt

    def test_inherited_system_prompt(self, tmp_creatures):
        """Parent system prompt is used when child doesn't have the file."""
        # Create a creature that specifies parent's prompt file but has no
        # local prompt file -- should fall back to base path
        bare = tmp_creatures / "creatures" / "bare"
        bare.mkdir(parents=True)
        (bare / "config.yaml").write_text(
            yaml.dump(
                {
                    "name": "bare",
                    "base_config": "../general",
                    # system_prompt_file inherited from general
                }
            )
        )

        config = load_agent_config(bare)
        assert "General Agent" in config.system_prompt

    def test_two_level_inheritance(self, tmp_creatures):
        """Agent inheriting from swe which inherits from general."""
        agent = tmp_creatures / "agents" / "my_agent"
        config = load_agent_config(agent)

        assert config.name == "my_agent"
        assert config.version == "2.0"
        # Model overridden by agent
        assert config.model == "agent-model"
        # reasoning_effort from swe (not general)
        assert config.reasoning_effort == "high"
        # tool_format from general (via swe)
        assert config.tool_format == "native"
        # Tools inherited from general (neither swe nor agent define tools)
        assert len(config.tools) == 4
        # Input from agent
        assert config.input.type == "cli"

    def test_child_tools_extend_parent(self, tmp_creatures):
        """When child defines tools, they extend parent tools."""
        custom = tmp_creatures / "creatures" / "custom"
        custom.mkdir(parents=True)
        (custom / "config.yaml").write_text(
            yaml.dump(
                {
                    "name": "custom",
                    "base_config": "../general",
                    "tools": [{"name": "grep", "type": "builtin"}],
                }
            )
        )

        config = load_agent_config(custom)
        # grep extends general's 4 tools (bash, read, write, think)
        assert len(config.tools) == 5
        tool_names = [t.name for t in config.tools]
        assert "grep" in tool_names
        assert "bash" in tool_names

    def test_no_base_config(self, tmp_creatures):
        """Config without base_config loads normally."""
        general = tmp_creatures / "creatures" / "general"
        config = load_agent_config(general)

        assert config.name == "general"
        assert len(config.tools) == 4
        assert config.model == "base-model"

    def test_missing_base_config_warns(self, tmp_creatures):
        """Missing base_config path logs warning and continues."""
        broken = tmp_creatures / "creatures" / "broken"
        broken.mkdir(parents=True)
        (broken / "config.yaml").write_text(
            yaml.dump(
                {
                    "name": "broken",
                    "base_config": "../nonexistent",
                }
            )
        )

        # Should not raise -- just loads child-only config
        config = load_agent_config(broken)
        assert config.name == "broken"
        assert len(config.tools) == 0


class TestRealCreatures:
    """Tests that verify the actual creatures/ configs load correctly."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).resolve().parent.parent.parent

    def test_general_creature_loads(self, project_root):
        general = project_root / "creatures" / "general"
        if not general.exists():
            pytest.skip("creatures/general not found")
        config = load_agent_config(general)
        assert config.name == "general"
        assert len(config.tools) > 0
        assert "KohakuTerrarium" in config.system_prompt

    def test_swe_creature_loads(self, project_root):
        swe = project_root / "creatures" / "swe"
        if not swe.exists():
            pytest.skip("creatures/swe not found")
        config = load_agent_config(swe)
        assert config.name == "swe"
        # Should inherit tools from general
        assert len(config.tools) > 0
        # General prompt is included (inherited)
        assert "KohakuTerrarium" in config.system_prompt
        # SWE prompt is appended
        assert "Software Engineering" in config.system_prompt

    def test_researcher_creature_loads(self, project_root):
        researcher = project_root / "creatures" / "researcher"
        if not researcher.exists():
            pytest.skip("creatures/researcher not found")
        config = load_agent_config(researcher)
        assert config.name == "researcher"
        # Researcher inherits all tools from general
        tool_names = [t.name for t in config.tools]
        assert "bash" in tool_names
        assert "http" in tool_names
        # General prompt is included (inherited)
        assert "KohakuTerrarium" in config.system_prompt
        # Researcher prompt is appended
        assert "Research Methodology" in config.system_prompt

    def test_root_creature_loads(self, project_root):
        root = project_root / "creatures" / "root"
        if not root.exists():
            pytest.skip("creatures/root not found")
        config = load_agent_config(root)
        assert config.name == "root"
        # Root extends general tools with terrarium management
        tool_names = [t.name for t in config.tools]
        assert "bash" in tool_names  # inherited from general
        assert "send_message" in tool_names  # inherited from general
        assert "terrarium_status" in tool_names  # root-specific
        assert "creature_start" in tool_names  # root-specific
        # General prompt is included (inherited)
        assert "KohakuTerrarium" in config.system_prompt
        # Root prompt is appended
        assert "Terrarium Management" in config.system_prompt
