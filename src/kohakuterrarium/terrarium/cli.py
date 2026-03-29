"""CLI commands for terrarium management."""

import argparse
import asyncio
from pathlib import Path

from kohakuterrarium.utils.logging import get_logger

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
        "--observe",
        nargs="*",
        help="Channels to observe (prints messages)",
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
    from kohakuterrarium.terrarium import TerrariumRuntime, load_terrarium_config
    from kohakuterrarium.utils.logging import set_level

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
    print()

    async def _run() -> None:
        runtime = TerrariumRuntime(config)

        # Setup channel observation if requested
        observe_channels = args.observe or []
        if observe_channels:
            await runtime.start()
            # Try to import and setup observer
            try:
                from kohakuterrarium.terrarium.observer import ChannelObserver

                observer = ChannelObserver(runtime._session)

                def print_message(msg):
                    ts = msg.timestamp.strftime("%H:%M:%S")
                    content_preview = msg.content[:80].replace("\n", "\\n")
                    print(
                        f"  [{ts}] [{msg.channel}] " f"{msg.sender}: {content_preview}"
                    )

                observer.on_message(print_message)
                for ch_name in observe_channels:
                    await observer.observe(ch_name)
                    print(f"  Observing: {ch_name}")
                print()
            except ImportError:
                observer = None
                print("Warning: Observer not available")

            # Run creature tasks (already started, just launch loops)
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
        else:
            await runtime.run()

    try:
        asyncio.run(_run())
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _info_terrarium_cli(args: argparse.Namespace) -> int:
    """Show terrarium information."""
    from kohakuterrarium.terrarium import load_terrarium_config

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
        print(f"    config: {c.config_path}")
        if c.listen_channels:
            print(f"    listen: {c.listen_channels}")
        if c.send_channels:
            print(f"    send:   {c.send_channels}")
        if c.output_log:
            print(f"    log:    enabled (max {c.output_log_size})")

    print(f"\nChannels ({len(config.channels)}):")
    for ch in config.channels:
        desc = f" -- {ch.description}" if ch.description else ""
        print(f"  {ch.name} ({ch.channel_type}){desc}")

    return 0
