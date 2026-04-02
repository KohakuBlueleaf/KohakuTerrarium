"""CLI commands for terrarium management."""

import argparse
import asyncio
from pathlib import Path

from kohakuterrarium.session.store import SessionStore
from kohakuterrarium.terrarium.config import load_terrarium_config
from kohakuterrarium.terrarium.observer import ChannelObserver
from kohakuterrarium.terrarium.runtime import TerrariumRuntime
from kohakuterrarium.utils.logging import get_logger, set_level

logger = get_logger(__name__)


async def run_terrarium_with_tui(runtime: TerrariumRuntime) -> None:
    """Run a terrarium with a full TUI (tabs, terrarium panel, etc.).

    This is the canonical way to run a terrarium interactively.
    Used by both 'kt terrarium run' and 'kt resume' for terrarium sessions.

    The runtime is started as a background task (same pattern as the web
    backend). The TUI handles all user I/O, routing input to the root
    agent via inject_input().
    """
    # Run runtime as background task (conversations/scratchpad restored inside)
    runtime_task = asyncio.create_task(runtime.run())

    # Wait for runtime to be fully started
    for _ in range(20):
        await asyncio.sleep(0.25)
        if runtime.is_running and runtime.root_agent:
            break

    root = runtime.root_agent
    if not root:
        runtime_task.cancel()
        raise RuntimeError("Root agent not available after runtime start")

    # Build tab list
    tui_tabs = ["root"]
    tui_tabs.extend(h.name for h in runtime.creatures.values())
    for ch_info in runtime.list_channels():
        tui_tabs.append(f"#{ch_info['name']}")

    # Create terrarium-level TUI
    from kohakuterrarium.builtins.tui.session import TUISession

    terrarium_name = getattr(runtime.config, "name", "terrarium")
    tui = TUISession(agent_name=terrarium_name)
    tui.set_terrarium_tabs(tui_tabs)
    await tui.start()

    # Suppress logging
    from kohakuterrarium.utils.logging import suppress_logging

    suppress_logging()

    # Wire root agent output to TUI "root" tab
    from kohakuterrarium.builtins.tui.output import TUIOutput

    tui_output = TUIOutput(session_key="root")
    tui_output._tui = tui
    tui_output._running = True
    tui_output._default_target = "root"
    root.output_router.default_output = tui_output

    # Wire each creature's output to its TUI tab
    for name, handle in runtime.creatures.items():
        creature_out = TUIOutput(session_key=name)
        creature_out._tui = tui
        creature_out._running = True
        creature_out._default_target = name
        handle.agent.output_router.default_output = creature_out

    # Wire Escape interrupt
    if tui._app:
        tui._app.on_interrupt = root.interrupt

    # Start TUI app
    app_task = asyncio.create_task(tui.run_app())
    await tui.wait_ready()

    # Update terrarium panel
    creature_info = []
    for name, handle in runtime.creatures.items():
        creature_info.append(
            {
                "name": name,
                "running": handle.is_running,
                "listen": handle.listen_channels,
                "send": handle.send_channels,
            }
        )
    tui.update_terrarium(creature_info, runtime.list_channels())

    # Replay resume history from SessionStore (if available)
    session_store = runtime.session_store
    if session_store:
        # Root agent events -> root tab
        root_events = session_store.get_events("root")
        if root_events and tui_output:
            await tui_output.on_resume(root_events)

        # Creature events -> creature tabs
        for name, handle in runtime.creatures.items():
            creature_events = session_store.get_events(name)
            if creature_events:
                creature_out = handle.agent.output_router.default_output
                if hasattr(creature_out, "on_resume"):
                    await creature_out.on_resume(creature_events)

        # Channel messages -> channel tabs
        for ch_info in runtime.list_channels():
            ch_name = ch_info["name"]
            ch_messages = session_store.get_channel_messages(ch_name)
            if ch_messages:
                tab_target = f"#{ch_name}"
                for msg in ch_messages:
                    sender = msg.get("sender", "")
                    content = msg.get("content", "")
                    tui.add_trigger_message(
                        f"[{ch_name}] {sender}", str(content)[:500],
                        target=tab_target,
                    )

    # Main loop: TUI input -> root agent via inject_input
    try:
        while True:
            text = await tui.get_input()
            if not text:
                break
            if text.lower() in ("exit", "quit", "/exit", "/quit"):
                break

            active_tab = tui.get_active_tab()

            if not active_tab or active_tab == "root":
                tui.set_active_target("root")
                await root.inject_input(text, source="tui")
            elif active_tab.startswith("#"):
                ch_name = active_tab[1:]
                tui.add_user_message(text, target=active_tab)
                await runtime.api.send_to_channel(ch_name, text, sender="human")
            else:
                tui.set_active_target(active_tab)
                await root.inject_input(
                    f"Send this to {active_tab}: {text}", source="tui"
                )
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        from kohakuterrarium.utils.logging import restore_logging

        restore_logging()
        runtime_task.cancel()
        try:
            await runtime_task
        except (asyncio.CancelledError, Exception):
            pass
        await runtime.stop()
        tui.stop()


def add_terrarium_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Add terrarium subcommands to the CLI parser."""
    terrarium_parser = subparsers.add_parser(
        "terrarium",
        help="Run and manage multi-agent terrariums",
    )
    terrarium_sub = terrarium_parser.add_subparsers(dest="terrarium_command")

    # terrarium run <path>
    run_p = terrarium_sub.add_parser("run", help="Run a terrarium")
    run_p.add_argument("terrarium_path", help="Path to terrarium config")
    run_p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    run_p.add_argument(
        "--seed",
        help="Seed prompt to inject into the 'seed' channel on startup",
    )
    run_p.add_argument(
        "--seed-channel",
        default="seed",
        help="Channel to send the seed prompt to (default: seed)",
    )
    run_p.add_argument(
        "--observe",
        nargs="*",
        help="Channels to observe. Omit to observe all channels.",
    )
    run_p.add_argument(
        "--no-observe",
        action="store_true",
        help="Disable channel observation",
    )
    run_p.add_argument(
        "--session",
        nargs="?",
        const="__auto__",
        default="__auto__",
        help="Session file path (default: auto in ~/.kohakuterrarium/sessions/)",
    )
    run_p.add_argument(
        "--no-session",
        action="store_true",
        help="Disable session persistence",
    )

    # terrarium info <path>
    info_p = terrarium_sub.add_parser("info", help="Show terrarium info")
    info_p.add_argument("terrarium_path", help="Path to terrarium config")


def handle_terrarium_command(args: argparse.Namespace) -> int:
    """Dispatch terrarium subcommand."""
    match args.terrarium_command:
        case "run":
            return _run_terrarium_cli(args)
        case "info":
            return _info_terrarium_cli(args)
        case _:
            print("Usage: kohakuterrarium terrarium {run,info}")
            return 0


def _run_terrarium_cli(args: argparse.Namespace) -> int:
    """Run a terrarium from CLI."""
    set_level(args.log_level)

    path = Path(args.terrarium_path)
    if not path.exists():
        print(f"Error: Path not found: {args.terrarium_path}")
        return 1

    try:
        config = load_terrarium_config(str(path))
    except Exception as e:
        print(f"Error loading config: {e}")
        return 1

    print(f"Terrarium: {config.name}")
    print(f"Creatures: {[c.name for c in config.creatures]}")
    print(f"Channels: {[c.name for c in config.channels]}")
    if config.root:
        base = config.root.config_data.get("base_config", "(inline)")
        print(f"Root agent: {base}")

    # Session store setup
    session_arg = getattr(args, "session", None)
    no_session = getattr(args, "no_session", False)
    if no_session:
        session_arg = None
    store = None
    session_file = None

    _session_dir = Path.home() / ".kohakuterrarium" / "sessions"

    if session_arg is not None:
        if session_arg == "__auto__":
            _session_dir.mkdir(parents=True, exist_ok=True)
            session_file = _session_dir / f"{config.name}_{id(config):08x}.kohakutr"
        else:
            session_file = Path(session_arg)

        store = SessionStore(session_file)
        store.init_meta(
            session_id=f"cli_{config.name}",
            config_type="terrarium",
            config_path=str(path),
            pwd=str(Path.cwd()),
            agents=[c.name for c in config.creatures]
            + (["root"] if config.root else []),
            terrarium_name=config.name,
            terrarium_channels=[
                {
                    "name": ch.name,
                    "type": ch.channel_type,
                    "description": ch.description,
                }
                for ch in config.channels
            ],
            terrarium_creatures=[
                {"name": c.name, "listen": c.listen_channels, "send": c.send_channels}
                for c in config.creatures
            ],
        )

    # When root agent is configured, launch terrarium TUI
    if config.root:
        print()

        async def _run_with_tui() -> None:
            runtime = TerrariumRuntime(config)
            if store:
                runtime._pending_session_store = store
            await run_terrarium_with_tui(runtime)

        try:
            asyncio.run(_run_with_tui())
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

    # No root agent: basic seed/observe CLI
    seed_prompt = args.seed
    seed_channel = args.seed_channel
    has_seed_channel = any(c.name == seed_channel for c in config.channels)

    if has_seed_channel and not seed_prompt:
        print()
        try:
            seed_prompt = input(f"Enter seed prompt (for '{seed_channel}' channel): ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled")
            return 0

    if seed_prompt:
        print(f"Seed: {seed_prompt[:80]}")
    print()

    async def _run() -> None:
        runtime = TerrariumRuntime(config)
        await runtime.start()

        # Setup observer
        observer = None
        if not args.no_observe:
            observer = await _setup_observer(runtime, args, config)

        # Inject seed prompt
        if seed_prompt and has_seed_channel:
            await runtime.api.send_to_channel(seed_channel, seed_prompt, sender="human")
            print(f"  Seed sent to '{seed_channel}' channel")
            print()

        # Run creature tasks
        try:
            for handle in runtime._creatures.values():
                task = asyncio.create_task(
                    runtime._run_creature(handle),
                    name=f"creature_{handle.name}",
                )
                runtime._creature_tasks.append(task)
            await asyncio.gather(*runtime._creature_tasks, return_exceptions=True)
        except KeyboardInterrupt:
            pass
        finally:
            if observer is not None:
                await observer.stop()
            await runtime.stop()

    try:
        asyncio.run(_run())
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


async def _setup_observer(runtime, args, config):
    """Setup channel observer and return it."""
    observer = ChannelObserver(runtime._session)

    def print_message(msg):
        ts = msg.timestamp.strftime("%H:%M:%S")
        content_preview = msg.content[:100].replace("\n", "\\n")
        print(f"  [{ts}] [{msg.channel}] {msg.sender}: {content_preview}")

    observer.on_message(print_message)

    # Determine which channels to observe
    if args.observe is not None:
        # Explicit list (--observe ideas outline)
        channels = args.observe if args.observe else []
    else:
        # Default: observe all channels
        channels = [c.name for c in config.channels]

    for ch_name in channels:
        await observer.observe(ch_name)

    if channels:
        print(f"  Observing: {', '.join(channels)}")

    return observer


def _info_terrarium_cli(args: argparse.Namespace) -> int:
    """Show terrarium information."""
    path = Path(args.terrarium_path)
    if not path.exists():
        print(f"Error: Path not found: {args.terrarium_path}")
        return 1

    try:
        config = load_terrarium_config(str(path))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print(f"Terrarium: {config.name}")
    print("=" * 40)

    print(f"\nCreatures ({len(config.creatures)}):")
    for c in config.creatures:
        print(f"  {c.name}")
        base = c.config_data.get("base_config", "(inline)")
        print(f"    base: {base}")
        if c.listen_channels:
            print(f"    listen: {c.listen_channels}")
        if c.send_channels:
            print(f"    send:   {c.send_channels}")
        if c.output_log:
            print(f"    log:    enabled (max {c.output_log_size})")

    print(f"\nChannels ({len(config.channels)}):")
    for ch in config.channels:
        desc = f" - {ch.description}" if ch.description else ""
        print(f"  {ch.name} ({ch.channel_type}){desc}")

    return 0
