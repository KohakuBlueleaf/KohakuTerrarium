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
import os
import sys
from pathlib import Path

import yaml

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.llm.codex_auth import CodexTokens, oauth_login
from kohakuterrarium.packages import resolve_package_path
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
        default="__auto__",
        help="Session file path (default: auto in ~/.kohakuterrarium/sessions/). Use --no-session to disable.",
    )
    run_parser.add_argument(
        "--no-session",
        action="store_true",
        help="Disable session persistence",
    )
    run_parser.add_argument(
        "--llm",
        default=None,
        help="Override LLM profile (e.g., gpt-5.4, gemini, claude-sonnet-4)",
    )
    run_parser.add_argument(
        "--mode",
        choices=["cli", "tui"],
        default=None,
        help="Input/output mode (overrides config input/output; omit to use config)",
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
        "resume", help="Resume a session (by name, path, or list recent)"
    )
    resume_parser.add_argument(
        "session",
        nargs="?",
        default=None,
        help="Session name/prefix, full path, or omit to list recent sessions",
    )
    resume_parser.add_argument("--pwd", help="Override working directory")
    resume_parser.add_argument(
        "--last",
        action="store_true",
        help="Resume the most recent session",
    )
    resume_parser.add_argument(
        "--mode",
        choices=["cli", "tui"],
        default="tui",
        help="Input/output mode (default: tui)",
    )
    resume_parser.add_argument(
        "--llm",
        default=None,
        help="Override LLM profile (e.g., gpt-5.4, gemini, claude-sonnet-4.6)",
    )
    resume_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )

    # Login command
    login_parser = subparsers.add_parser("login", help="Authenticate with a provider")
    login_parser.add_argument(
        "provider",
        choices=["codex", "openrouter", "openai", "anthropic", "gemini", "mimo"],
        help="Provider to authenticate with",
    )

    # Install command
    install_parser = subparsers.add_parser(
        "install", help="Install a creature/terrarium package"
    )
    install_parser.add_argument("source", help="Git URL or local path to package")
    install_parser.add_argument(
        "-e",
        "--editable",
        action="store_true",
        help="Install as editable (symlink, like pip -e)",
    )
    install_parser.add_argument("--name", default=None, help="Override package name")

    # Uninstall command
    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Remove an installed package"
    )
    uninstall_parser.add_argument("name", help="Package name to remove")

    # Edit command
    edit_parser = subparsers.add_parser(
        "edit", help="Open a creature/terrarium config in editor"
    )
    edit_parser.add_argument(
        "target",
        help="@package/creatures/name or @package/terrariums/name",
    )

    # Embedding command
    embed_parser = subparsers.add_parser(
        "embedding", help="Build embeddings for a session (offline indexing)"
    )
    embed_parser.add_argument("session", help="Session name/prefix or path")
    embed_parser.add_argument(
        "--provider",
        choices=["auto", "model2vec", "sentence-transformer", "api"],
        default="auto",
        help="Embedding provider (default: auto, prefers jina v5 nano)",
    )
    embed_parser.add_argument(
        "--model", default=None, help="Model name (default: provider-dependent)"
    )
    embed_parser.add_argument(
        "--dimensions", type=int, default=None, help="Embedding dimensions (Matryoshka)"
    )

    # Search command
    search_parser = subparsers.add_parser("search", help="Search a session's memory")
    search_parser.add_argument("session", help="Session name/prefix or path")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--mode",
        choices=["fts", "semantic", "hybrid", "auto"],
        default="auto",
        help="Search mode (default: auto)",
    )
    search_parser.add_argument("--agent", default=None, help="Filter by agent name")
    search_parser.add_argument(
        "-k", type=int, default=10, help="Max results (default: 10)"
    )

    # Web server command
    web_parser = subparsers.add_parser(
        "web", help="Serve web UI + API (single process)"
    )
    web_parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    web_parser.add_argument("--port", type=int, default=8001, help="Bind port")
    web_parser.add_argument(
        "--dev",
        action="store_true",
        help="API-only mode (run vite dev server separately)",
    )

    # Desktop app command
    app_parser = subparsers.add_parser(
        "app", help="Launch native desktop UI (requires pywebview)"
    )
    app_parser.add_argument(
        "--port", type=int, default=8001, help="Internal server port"
    )

    # Model command
    model_parser = subparsers.add_parser("model", help="Manage LLM profiles")
    model_sub = model_parser.add_subparsers(dest="model_command")
    model_sub.add_parser("list", help="List all profiles and presets")
    model_default_parser = model_sub.add_parser("default", help="Set default model")
    model_default_parser.add_argument("name", help="Model/profile name")
    model_show_parser = model_sub.add_parser("show", help="Show profile details")
    model_show_parser.add_argument("name", help="Model/profile name")

    args = parser.parse_args()

    if args.command == "run":
        # Resolve @package references in agent_path
        agent_path = args.agent_path
        if agent_path.startswith("@"):
            agent_path = str(resolve_package_path(agent_path))
        session = None if args.no_session else args.session
        return run_agent_cli(
            agent_path,
            args.log_level,
            session=session,
            io_mode=args.mode,
            llm_override=args.llm,
        )
    elif args.command == "resume":
        return resume_cli(
            args.session,
            args.pwd,
            args.log_level,
            last=args.last,
            io_mode=args.mode,
            llm_override=args.llm,
        )
    elif args.command == "list":
        return list_cli(args.path)
    elif args.command == "info":
        return show_agent_info_cli(args.agent_path)
    elif args.command == "terrarium":
        # Resolve @package references in terrarium path
        if hasattr(args, "terrarium_path") and args.terrarium_path:
            if args.terrarium_path.startswith("@"):
                args.terrarium_path = str(resolve_package_path(args.terrarium_path))
        return handle_terrarium_command(args)
    elif args.command == "login":
        return login_cli(args.provider)
    elif args.command == "install":
        return install_cli(args.source, args.editable, args.name)
    elif args.command == "uninstall":
        return uninstall_cli(args.name)
    elif args.command == "edit":
        return edit_cli(args.target)
    elif args.command == "embedding":
        return embedding_cli(args.session, args.provider, args.model, args.dimensions)
    elif args.command == "search":
        return search_cli(args.session, args.query, args.mode, args.agent, args.k)
    elif args.command == "web":
        from kohakuterrarium.serving.web import run_web_server

        run_web_server(host=args.host, port=args.port, dev=args.dev)
        return 0
    elif args.command == "app":
        from kohakuterrarium.serving.web import run_desktop_app

        run_desktop_app(port=args.port)
        return 0
    elif args.command == "model":
        return model_cli(args)
    else:
        parser.print_help()
        return 0


_SESSION_DIR = Path.home() / ".kohakuterrarium" / "sessions"


def run_agent_cli(
    agent_path: str,
    log_level: str,
    session: str | None = None,
    io_mode: str | None = None,
    llm_override: str | None = None,
) -> int:
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
    session_file = None
    try:
        # Create IO module overrides if mode specified
        io_kwargs: dict = {}
        if io_mode:
            from kohakuterrarium.session.resume import _create_io_modules

            inp, out = _create_io_modules(io_mode)
            io_kwargs["input_module"] = inp
            io_kwargs["output_module"] = out

        # Create agent
        agent = Agent.from_path(str(path), llm_override=llm_override, **io_kwargs)

        # Attach session store (default: ON)
        if session is not None:
            if session == "__auto__":
                _SESSION_DIR.mkdir(parents=True, exist_ok=True)
                session_file = (
                    _SESSION_DIR / f"{agent.config.name}_{id(agent):08x}.kohakutr"
                )
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
        if session_file and session_file.exists():
            print(f"\nSession saved. To resume:")
            print(f"  kt resume {session_file.stem}")


def _resolve_session(query: str | None, last: bool = False) -> Path | None:
    """Resolve a session query to a file path.

    Searches ~/.kohakuterrarium/sessions/ for matching files.
    Accepts: full path, filename, name prefix, or None (list/pick).
    """
    # Full path provided
    if query and Path(query).exists():
        return Path(query)

    # Strip extension from query if present (user may paste from hint)
    if query:
        for ext in (".kohakutr", ".kt"):
            if query.endswith(ext):
                query = query[: -len(ext)]
                break

    # Search in default session directory
    if not _SESSION_DIR.exists():
        return None

    sessions = sorted(
        _SESSION_DIR.glob("*.kohakutr"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # Also check legacy .kt files (pre-.kohakutr extension)
    sessions.extend(
        sorted(
            _SESSION_DIR.glob("*.kt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    )

    if not sessions:
        return None

    # --last: most recent
    if last:
        return sessions[0]

    # No query: list recent and let user pick
    if not query:
        print("Recent sessions:")
        shown = sessions[:10]
        for i, s in enumerate(shown, 1):
            meta = _session_preview(s)
            print(f"  {i}. {s.name}  {meta}")
        print()
        try:
            choice = input(f"Pick [1-{len(shown)}] or name prefix: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(shown):
                return shown[idx]
            return None
        query = choice

    # Prefix match
    matches = [s for s in sessions if s.stem.startswith(query) or query in s.stem]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Multiple matches for '{query}':")
        for i, s in enumerate(matches[:10], 1):
            meta = _session_preview(s)
            print(f"  {i}. {s.name}  {meta}")
        print()
        try:
            choice = input(f"Pick [1-{len(matches[:10])}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(matches[:10]):
                return matches[idx]
        return None

    # No match in session dir, try as path
    p = Path(query)
    if p.exists():
        return p
    # Try appending extension
    for ext in (".kohakutr", ".kt"):
        if (_SESSION_DIR / f"{query}{ext}").exists():
            return _SESSION_DIR / f"{query}{ext}"

    return None


def _session_preview(path: Path) -> str:
    """Get a short preview of session metadata."""
    try:
        store = SessionStore(path)
        meta = store.load_meta()
        store.close()
        config_type = meta.get("config_type", "?")
        config_path = meta.get("config_path", "")
        name = Path(config_path).name if config_path else "?"
        return f"({config_type}: {name})"
    except Exception:
        return ""


def resume_cli(
    query: str | None,
    pwd_override: str | None,
    log_level: str,
    last: bool = False,
    io_mode: str | None = None,
    llm_override: str | None = None,
) -> int:
    """Resume an agent or terrarium from a session file."""
    set_level(log_level)

    path = _resolve_session(query, last=last)
    if path is None:
        if query:
            print(f"No session found matching: {query}")
        else:
            print("No sessions found in ~/.kohakuterrarium/sessions/")
        return 1

    session_type = detect_session_type(path)
    store = None

    try:
        if session_type == "terrarium":
            # Don't pass io_mode - terrarium CLI controls all I/O
            runtime, store = resume_terrarium(path, pwd_override)
            from kohakuterrarium.terrarium.cli import run_terrarium_with_tui

            asyncio.run(run_terrarium_with_tui(runtime))
        else:
            agent, store = resume_agent(
                path, pwd_override, io_mode=io_mode, llm_override=llm_override
            )
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
        if path.exists():
            print(f"\nSession saved. To resume:")
            print(f"  kt resume {path.stem}")


def list_cli(agents_path: str = "agents") -> int:
    """List installed packages and available agents/terrariums."""
    from kohakuterrarium.packages import list_packages, PACKAGES_DIR

    # Show installed packages
    packages = list_packages()
    if packages:
        print("Installed packages:")
        print("=" * 50)
        for pkg in packages:
            editable_tag = " (editable)" if pkg["editable"] else ""
            print(f"  {pkg['name']} v{pkg['version']}{editable_tag}")
            print(f"    {pkg['path']}")
            if pkg["description"]:
                print(f"    {pkg['description']}")
            if pkg["creatures"]:
                names = [c["name"] for c in pkg["creatures"]]
                print(f"    Creatures: {', '.join(names)}")
            if pkg["terrariums"]:
                names = [t["name"] for t in pkg["terrariums"]]
                print(f"    Terrariums: {', '.join(names)}")
            print()
    else:
        print(f"No packages installed in {PACKAGES_DIR}")
        print()

    # Also show local agents if directory exists
    path = Path(agents_path)
    if path.exists():
        print(f"Local agents in {agents_path}:")
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
                print(f"  {agent_dir.name}")
        if not found:
            print("  (none)")

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


def install_cli(source: str, editable: bool = False, name: str | None = None) -> int:
    """Install a creature/terrarium package."""
    from kohakuterrarium.packages import install_package

    try:
        pkg_name = install_package(source, editable=editable, name_override=name)
        tag = " (editable)" if editable else ""
        print(f"Installed: {pkg_name}{tag}")
        print()
        print("Usage:")
        print(f"  kt run @{pkg_name}/creatures/<name>")
        print(f"  kt terrarium run @{pkg_name}/terrariums/<name>")
        print(f"  kt list")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def uninstall_cli(name: str) -> int:
    """Remove an installed package."""
    from kohakuterrarium.packages import uninstall_package

    if uninstall_package(name):
        print(f"Uninstalled: {name}")
        return 0
    else:
        print(f"Package not found: {name}")
        return 1


def edit_cli(target: str) -> int:
    """Open a creature/terrarium config in editor."""
    from kohakuterrarium.packages import resolve_package_path

    if not target.startswith("@"):
        target = "@" + target

    try:
        path = resolve_package_path(target)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return 1

    # Find config file
    config_file = None
    for name in ("config.yaml", "config.yml", "terrarium.yaml", "terrarium.yml"):
        candidate = path / name
        if candidate.exists():
            config_file = candidate
            break

    if not config_file:
        # Maybe they pointed to the file directly
        if path.is_file():
            config_file = path
        else:
            print(f"No config file found in: {path}")
            return 1

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
    print(f"Opening: {config_file}")
    os.execvp(editor, [editor, str(config_file)])
    return 0  # unreachable after execvp


def login_cli(provider: str) -> int:
    """Authenticate with a provider."""
    if provider == "codex":
        return _login_codex()
    if provider in ("openrouter", "openai", "anthropic", "gemini", "mimo"):
        return _login_api_key(provider)
    print(f"Unknown provider: {provider}")
    return 1


def _login_api_key(provider: str) -> int:
    """Store an API key for a provider."""
    from kohakuterrarium.llm.profiles import (
        PROVIDER_KEY_MAP,
        get_api_key,
        save_api_key,
    )

    env_var = PROVIDER_KEY_MAP.get(provider, "")
    existing = get_api_key(provider)

    if existing:
        masked = f"{existing[:4]}...{existing[-4:]}" if len(existing) > 8 else "****"
        print(f"Existing {provider} key: {masked}")
        answer = input("Replace? [y/N]: ").strip().lower()
        if answer != "y":
            return 0

    print(f"Enter your {provider} API key")
    if env_var:
        print(f"(get one from the provider's dashboard, usually starts with a prefix)")
    print()

    try:
        key = input("API key: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled")
        return 0

    if not key:
        print("No key provided")
        return 1

    save_api_key(provider, key)
    print(f"\nSaved {provider} API key to ~/.kohakuterrarium/api_keys.yaml")
    print(f"You can now use {provider} models:")
    print(f"  kt model list")
    print(f"  kt run @kohaku-creatures/creatures/swe --llm <model>")
    return 0


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
        asyncio.run(oauth_login())
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


def embedding_cli(
    session_query: str,
    provider: str = "model2vec",
    model: str | None = None,
    dimensions: int | None = None,
) -> int:
    """Build embeddings for a session (offline)."""
    path = _resolve_session(session_query)
    if path is None:
        print(f"Session not found: {session_query}")
        return 1

    from kohakuterrarium.session.embedding import create_embedder
    from kohakuterrarium.session.memory import SessionMemory
    from kohakuterrarium.session.store import SessionStore

    store = SessionStore(path)
    try:
        meta = store.load_meta()
        agents = meta.get("agents", [])

        # Build embedder config
        embed_config: dict = {"provider": provider}
        if model:
            embed_config["model"] = model
        if dimensions:
            embed_config["dimensions"] = dimensions

        print(f"Session: {path.name}")
        print(f"Agents: {', '.join(agents)}")
        print(f"Embedding: {provider}" + (f" ({model})" if model else ""))
        print()

        embedder = create_embedder(embed_config)
        memory = SessionMemory(str(path), embedder=embedder, store=store)

        total_blocks = 0
        for agent_name in agents:
            events = store.get_events(agent_name)
            if not events:
                print(f"  {agent_name}: no events")
                continue
            count = memory.index_events(agent_name, events)
            total_blocks += count
            print(f"  {agent_name}: {count} blocks indexed ({len(events)} events)")

        stats = memory.get_stats()
        print(
            f"\nDone. FTS: {stats['fts_blocks']} blocks, "
            f"Vector: {stats['vec_blocks']} blocks "
            f"({stats['dimensions']}d)"
        )
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        store.close()


def search_cli(
    session_query: str,
    query: str,
    mode: str = "auto",
    agent: str | None = None,
    k: int = 10,
) -> int:
    """Search a session's memory."""
    path = _resolve_session(session_query)
    if path is None:
        print(f"Session not found: {session_query}")
        return 1

    from kohakuterrarium.session.embedding import create_embedder
    from kohakuterrarium.session.memory import SessionMemory
    from kohakuterrarium.session.store import SessionStore

    store = SessionStore(path)
    try:
        # Try to create embedder for query encoding (semantic/hybrid)
        embedder = None
        if mode in ("semantic", "hybrid", "auto"):
            try:
                embedder = create_embedder({"provider": "auto"})
            except Exception:
                pass

        # SessionMemory discovers existing vector tables via saved dimensions
        memory = SessionMemory(str(path), embedder=embedder, store=store)

        if mode in ("semantic", "hybrid") and not memory.has_vectors:
            print("No vector index found. Run 'kt embedding' first, or use --mode fts")
            if mode == "semantic":
                return 1
            mode = "fts"

        results = memory.search(query, mode=mode, k=k, agent=agent)

        if not results:
            print("No results found.")
            return 0

        print(f"Found {len(results)} result(s) for: {query}")
        print(f"Mode: {mode}")
        print()

        for i, r in enumerate(results, 1):
            age = r.age_str
            header = f"#{i}  [round {r.round_num}]  {r.block_type}"
            if r.tool_name:
                header += f":{r.tool_name}"
            if r.agent:
                header += f"  ({r.agent})"
            if age:
                header += f"  {age}"
            print(header)
            # Show content (truncated for display)
            content = r.content
            if len(content) > 200:
                content = content[:200] + "..."
            for line in content.split("\n"):
                print(f"  {line}")
            print()

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        store.close()


def model_cli(args: argparse.Namespace) -> int:
    """Manage LLM profiles."""
    from kohakuterrarium.llm.profiles import (
        get_default_model,
        get_profile,
        list_all,
        set_default_model,
    )

    sub = getattr(args, "model_command", None)

    if sub == "list" or sub is None:
        default = get_default_model()
        entries = list_all()
        if default:
            print(f"Default model: {default}")
        else:
            print("No default model set. Use: kt model default <name>")
        print()
        print(
            f"{'Name':<25} {'Model':<40} {'Login':<12} {'Context':<10} {'Src':<6} {'Status'}"
        )
        print("-" * 105)
        for e in entries:
            marker = " *" if e.get("is_default") else ""
            ctx = e.get("max_context", 0)
            ctx_str = f"{ctx // 1000}k" if ctx else ""
            login = e.get("login_provider", "")
            available = e.get("available", False)
            status = "ok" if available else f"(kt login {login})"
            print(
                f"{e['name']:<25} {e['model']:<40} {login:<12} {ctx_str:<10} {e['source']:<6} {status}{marker}"
            )
        return 0

    elif sub == "default":
        name = args.name
        # Verify the profile exists
        profile = get_profile(name)
        if not profile:
            print(f"Profile/preset not found: {name}")
            print("Use 'kt model list' to see available options.")
            return 1
        set_default_model(name)
        print(f"Default model set to: {name} ({profile.model})")
        return 0

    elif sub == "show":
        name = args.name
        profile = get_profile(name)
        if not profile:
            print(f"Profile/preset not found: {name}")
            return 1
        print(f"Name:       {profile.name}")
        print(f"Provider:   {profile.provider}")
        print(f"Model:      {profile.model}")
        print(f"Context:    {profile.max_context:,} tokens")
        print(f"Max output: {profile.max_output:,} tokens")
        if profile.base_url:
            print(f"Base URL:   {profile.base_url}")
        if profile.api_key_env:
            print(f"API key:    ${profile.api_key_env}")
        if profile.temperature is not None:
            print(f"Temperature: {profile.temperature}")
        if profile.reasoning_effort:
            print(f"Reasoning:  {profile.reasoning_effort}")
        if profile.extra_body:
            print(f"Extra body: {profile.extra_body}")
        return 0

    print("Usage: kt model [list|default <name>|show <name>]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
