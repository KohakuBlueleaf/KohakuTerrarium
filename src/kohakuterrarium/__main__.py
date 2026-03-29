"""
KohakuTerrarium CLI entry point.

Run agents from the command line:
    python -m kohakuterrarium run agents/my_agent
    python -m kohakuterrarium run agents/swe-agent --log-level DEBUG

List available agents:
    python -m kohakuterrarium list

Show agent info:
    python -m kohakuterrarium info agents/my_agent
"""

import argparse
import asyncio
import sys
from pathlib import Path

from kohakuterrarium.terrarium.cli import (
    add_terrarium_subparser,
    handle_terrarium_command,
)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="kohakuterrarium",
        description="KohakuTerrarium - Universal Agent Framework",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run an agent")
    run_parser.add_argument(
        "agent_path",
        help="Path to agent config folder (e.g., agents/swe-agent)",
    )
    run_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List available agents")
    list_parser.add_argument(
        "--path",
        default="agents",
        help="Path to agents directory",
    )

    # Info command
    info_parser = subparsers.add_parser("info", help="Show agent info")
    info_parser.add_argument(
        "agent_path",
        help="Path to agent config folder",
    )

    # Terrarium command group
    add_terrarium_subparser(subparsers)

    args = parser.parse_args()

    if args.command == "run":
        return run_agent_cli(args.agent_path, args.log_level)
    elif args.command == "list":
        return list_agents_cli(args.path)
    elif args.command == "info":
        return show_agent_info_cli(args.agent_path)
    elif args.command == "terrarium":
        return handle_terrarium_command(args)
    else:
        parser.print_help()
        return 0


def run_agent_cli(agent_path: str, log_level: str) -> int:
    """Run an agent from CLI."""
    from kohakuterrarium.core.agent import Agent
    from kohakuterrarium.utils.logging import set_level

    # Setup logging
    set_level(log_level)

    # Check path exists
    path = Path(agent_path)
    if not path.exists():
        print(f"Error: Agent path not found: {agent_path}")
        return 1

    config_file = path / "config.yaml"
    if not config_file.exists():
        config_file = path / "config.yml"
        if not config_file.exists():
            print(f"Error: No config.yaml found in {agent_path}")
            return 1

    try:
        # Create and run agent
        agent = Agent.from_path(str(path))
        asyncio.run(agent.run())
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def list_agents_cli(agents_path: str) -> int:
    """List available agents."""
    path = Path(agents_path)
    if not path.exists():
        print(f"Agents directory not found: {agents_path}")
        return 1

    print(f"Available agents in {agents_path}:")
    print("-" * 40)

    found = False
    for agent_dir in sorted(path.iterdir()):
        if not agent_dir.is_dir():
            continue

        config_file = agent_dir / "config.yaml"
        if not config_file.exists():
            config_file = agent_dir / "config.yml"

        if config_file.exists():
            found = True
            # Try to read name from config
            try:
                import yaml

                with open(config_file) as f:
                    config = yaml.safe_load(f)
                name = config.get("name", agent_dir.name)
                desc = config.get("description", "")
                print(f"  {agent_dir.name}")
                if desc:
                    print(f"    {desc[:60]}...")
            except Exception:
                print(f"  {agent_dir.name}")

    if not found:
        print("  No agents found")

    return 0


def show_agent_info_cli(agent_path: str) -> int:
    """Show agent information."""
    path = Path(agent_path)
    if not path.exists():
        print(f"Error: Agent path not found: {agent_path}")
        return 1

    config_file = path / "config.yaml"
    if not config_file.exists():
        config_file = path / "config.yml"
        if not config_file.exists():
            print(f"Error: No config.yaml found in {agent_path}")
            return 1

    try:
        import yaml

        with open(config_file) as f:
            config = yaml.safe_load(f)

        print(f"Agent: {config.get('name', path.name)}")
        print("-" * 40)

        if config.get("description"):
            print(f"Description: {config['description']}")

        if config.get("model"):
            print(f"Model: {config['model']}")

        # Tools
        tools = config.get("tools", [])
        if tools:
            print(f"\nTools ({len(tools)}):")
            for tool in tools:
                if isinstance(tool, dict):
                    print(f"  - {tool.get('name', 'unknown')}")
                else:
                    print(f"  - {tool}")

        # Sub-agents
        subagents = config.get("subagents", [])
        if subagents:
            print(f"\nSub-agents ({len(subagents)}):")
            for sa in subagents:
                if isinstance(sa, dict):
                    print(f"  - {sa.get('name', 'unknown')}")
                else:
                    print(f"  - {sa}")

        # Files
        print(f"\nFiles:")
        for f in sorted(path.iterdir()):
            if f.is_file():
                print(f"  - {f.name}")

        return 0

    except Exception as e:
        print(f"Error reading config: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
