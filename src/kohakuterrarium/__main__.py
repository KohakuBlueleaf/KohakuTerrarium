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

import yaml

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.llm.codex_auth import CodexTokens, oauth_login
from kohakuterrarium.session.resume import (
    detect_session_type,
    resume_agent,
    resume_terrarium,
)
from kohakuterrarium.session.store import SessionStore
from kohakuterrarium.terrarium.cli import (
    add_terrarium_subparser,
    handle_terrarium_command,
)
from kohakuterrarium.utils.logging import set_level


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="kt",
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
    run_parser.add_argument(
        "--session",
        nargs="?",
        const="__auto__",
        default=None,
        help="Enable session persistence (optionally specify .kt file path)",
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

    # Resume command
    resume_parser = subparsers.add_parser(
        "resume", help="Resume from a .kt session file"
    )
    resume_parser.add_argument("session_path", help="Path to .kt session file")
    resume_parser.add_argument("--pwd", help="Override working directory")
    resume_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )

    # Login command
    login_parser = subparsers.add_parser("login", help="Authenticate with a provider")
    login_parser.add_argument(
        "provider",
        choices=["codex"],
        help="Provider to authenticate with (codex = ChatGPT subscription)",
    )

    args = parser.parse_args()

    if args.command == "run":
        return run_agent_cli(args.agent_path, args.log_level, session=args.session)
    elif args.command == "resume":
        return resume_cli(args.session_path, args.pwd, args.log_level)
    elif args.command == "list":
        return list_agents_cli(args.path)
    elif args.command == "info":
        return show_agent_info_cli(args.agent_path)
    elif args.command == "terrarium":
        return handle_terrarium_command(args)
    elif args.command == "login":
        return login_cli(args.provider)
    else:
        parser.print_help()
        return 0


def run_agent_cli(agent_path: str, log_level: str, session: str | None = None) -> int:
    """Run an agent from CLI."""

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

    store = None
    try:
        # Create agent
        agent = Agent.from_path(str(path))

        # Attach session store if requested
        if session is not None:
            if session == "__auto__":
                # Auto-generate path
                session_dir = Path(".kohaku/sessions")
                session_dir.mkdir(parents=True, exist_ok=True)
                session_file = session_dir / f"{agent.config.name}_{id(agent):08x}.kt"
            else:
                session_file = Path(session)

            store = SessionStore(session_file)
            store.init_meta(
                session_id=f"cli_{id(agent):08x}",
                config_type="agent",
                config_path=str(path),
                pwd=str(Path.cwd()),
                agents=[agent.config.name],
            )
            agent.attach_session_store(store)
            print(f"Session: {session_file}")

        asyncio.run(agent.run())
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        if store:
            store.close()


def resume_cli(session_path: str, pwd_override: str | None, log_level: str) -> int:
    """Resume an agent or terrarium from a .kt session file."""
    set_level(log_level)

    path = Path(session_path)
    if not path.exists():
        print(f"Error: Session file not found: {session_path}")
        return 1

    session_type = detect_session_type(path)
    store = None

    try:
        if session_type == "terrarium":
            runtime, store = resume_terrarium(path, pwd_override)
            print(f"Resuming terrarium from {path}")
            asyncio.run(runtime.run())
        else:
            agent, store = resume_agent(path, pwd_override)
            print(f"Resuming agent from {path}")
            asyncio.run(agent.run())
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        if store:
            store.close()


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


def login_cli(provider: str) -> int:
    """Authenticate with a provider."""
    if provider == "codex":
        return _login_codex()
    print(f"Unknown provider: {provider}")
    return 1


def _login_codex() -> int:
    """Authenticate with OpenAI Codex OAuth (ChatGPT subscription)."""

    # Check for existing tokens
    existing = CodexTokens.load()
    if existing and not existing.is_expired():
        print("Already authenticated (tokens valid).")
        print(
            f"Token path: {existing._path if hasattr(existing, '_path') else '~/.kohakuterrarium/codex-auth.json'}"
        )
        answer = input("Re-authenticate? [y/N]: ").strip().lower()
        if answer != "y":
            return 0

    print("Authenticating with OpenAI (ChatGPT subscription)...")
    print()

    try:
        tokens = asyncio.run(oauth_login())
        print()
        print("Authentication successful!")
        print(f"Tokens saved to: ~/.kohakuterrarium/codex-auth.json")
        print()
        print("You can now use auth_mode: codex-oauth in agent configs:")
        print("  controller:")
        print('    model: "gpt-4o"')
        print("    auth_mode: codex-oauth")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
