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
        default=None,
        help="Enable session persistence (optionally specify .kt file path)",
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
    store = None
    session_file = None
    if session_arg is not None:
        if session_arg == "__auto__":
            session_dir = Path(".kohaku/sessions")
            session_dir.mkdir(parents=True, exist_ok=True)
            session_file = session_dir / f"{config.name}_{id(config):08x}.kt"
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
        print(f"Session: {session_file}")

    # When root agent is configured, it handles all user interaction
    if config.root:
        print()

        async def _run_with_root() -> None:
            runtime = TerrariumRuntime(config)
            if store:
                runtime._pending_session_store = store
            await runtime.run()

        try:
            asyncio.run(_run_with_root())
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
