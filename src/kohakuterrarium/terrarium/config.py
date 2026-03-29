"""
Terrarium configuration loading.

Loads multi-agent terrarium config from YAML, resolving creature
config paths relative to the terrarium config directory.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChannelConfig:
    """Configuration for a single terrarium channel."""

    name: str
    channel_type: str = "queue"  # "queue" or "broadcast"
    description: str = ""


@dataclass
class CreatureConfig:
    """Configuration for a single creature (agent) in the terrarium."""

    name: str
    config_path: str  # Path to agent config folder
    listen_channels: list[str] = field(default_factory=list)
    send_channels: list[str] = field(default_factory=list)
    output_log: bool = False
    output_log_size: int = 100


@dataclass
class TerrariumConfig:
    """Top-level terrarium configuration."""

    name: str
    creatures: list[CreatureConfig]
    channels: list[ChannelConfig]


def _find_terrarium_config(path: Path) -> Path:
    """
    Resolve the terrarium config file path.

    If *path* is a file, return it directly.
    If it is a directory, look for ``terrarium.yaml`` or ``terrarium.yml``.

    Raises:
        FileNotFoundError: If no config file can be located.
    """
    if path.is_file():
        return path

    for name in ("terrarium.yaml", "terrarium.yml"):
        candidate = path / name
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"No terrarium config found at {path} "
        "(expected terrarium.yaml or terrarium.yml)"
    )


def _parse_creature(data: dict, base_dir: Path) -> CreatureConfig:
    """Parse a single creature entry from raw YAML data."""
    name = data.get("name", "")
    if not name:
        raise ValueError("Creature entry missing 'name'")

    raw_path = data.get("config", "")
    if not raw_path:
        raise ValueError(f"Creature '{name}' missing 'config' path")

    # Resolve config_path relative to the terrarium config directory
    resolved = (base_dir / raw_path).resolve()

    channels = data.get("channels", {})

    return CreatureConfig(
        name=name,
        config_path=str(resolved),
        listen_channels=list(channels.get("listen", [])),
        send_channels=list(channels.get("can_send", [])),
        output_log=bool(data.get("output_log", False)),
        output_log_size=int(data.get("output_log_size", 100)),
    )


def _parse_channels(raw: dict) -> list[ChannelConfig]:
    """Parse the channels mapping from raw YAML data."""
    result: list[ChannelConfig] = []
    for ch_name, ch_data in raw.items():
        if isinstance(ch_data, dict):
            result.append(
                ChannelConfig(
                    name=ch_name,
                    channel_type=ch_data.get("type", "queue"),
                    description=ch_data.get("description", ""),
                )
            )
        else:
            # Bare channel name with no extra config
            result.append(ChannelConfig(name=ch_name))
    return result


def load_terrarium_config(path: str | Path) -> TerrariumConfig:
    """
    Load terrarium configuration from a YAML file or directory.

    Supports both a direct file path and a directory containing
    ``terrarium.yaml``.  Creature ``config`` paths are resolved
    relative to the directory that holds the terrarium YAML file.

    Args:
        path: File or directory path.

    Returns:
        Parsed TerrariumConfig.

    Raises:
        FileNotFoundError: If config file cannot be found.
        ValueError: If required fields are missing.
    """
    path = Path(path)
    config_file = _find_terrarium_config(path)
    base_dir = config_file.parent

    logger.debug("Loading terrarium config", path=str(config_file))

    with open(config_file, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # The top-level key is "terrarium"
    terrarium_data = raw.get("terrarium", raw)

    name = terrarium_data.get("name", "terrarium")

    # Parse creatures
    creatures_raw = terrarium_data.get("creatures", [])
    creatures = [_parse_creature(c, base_dir) for c in creatures_raw]

    # Parse channels
    channels_raw = terrarium_data.get("channels", {})
    channels = _parse_channels(channels_raw)

    config = TerrariumConfig(name=name, creatures=creatures, channels=channels)

    logger.info(
        "Terrarium config loaded",
        terrarium_name=config.name,
        creatures=len(config.creatures),
        channels=len(config.channels),
    )
    return config
