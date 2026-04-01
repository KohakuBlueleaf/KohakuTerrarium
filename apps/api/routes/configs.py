"""Config discovery routes - scan directories for available creature/terrarium configs."""

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter()

# Default directories - can be overridden via environment variables
_creatures_dirs: list[Path] = []
_terrariums_dirs: list[Path] = []


def set_config_dirs(creatures: list[str], terrariums: list[str]) -> None:
    """Set directories to scan for configs."""
    global _creatures_dirs, _terrariums_dirs
    _creatures_dirs = [Path(d).resolve() for d in creatures]
    _terrariums_dirs = [Path(d).resolve() for d in terrariums]


def _scan_creature_configs() -> list[dict]:
    """Scan creature directories for config.yaml files."""
    results = []
    for base_dir in _creatures_dirs:
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            config_file = child / "config.yaml"
            if not config_file.exists():
                config_file = child / "config.yml"
            if not config_file.exists():
                continue
            try:
                data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
                results.append(
                    {
                        "name": data.get("name", child.name),
                        "path": str(child),
                        "description": data.get("description", ""),
                    }
                )
            except Exception:
                results.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "description": "",
                    }
                )
    return results


def _scan_terrarium_configs() -> list[dict]:
    """Scan terrarium directories for terrarium.yaml files."""
    results = []
    for base_dir in _terrariums_dirs:
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            config_file = child / "terrarium.yaml"
            if not config_file.exists():
                config_file = child / "terrarium.yml"
            if not config_file.exists():
                continue
            try:
                data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
                terrarium = data.get("terrarium", data)
                results.append(
                    {
                        "name": terrarium.get("name", child.name),
                        "path": str(child),
                        "description": terrarium.get("description", ""),
                    }
                )
            except Exception:
                results.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "description": "",
                    }
                )
    return results


@router.get("/creatures")
def list_creature_configs():
    """List available creature configs from configured directories."""
    return _scan_creature_configs()


@router.get("/terrariums")
def list_terrarium_configs():
    """List available terrarium configs from configured directories."""
    return _scan_terrarium_configs()
