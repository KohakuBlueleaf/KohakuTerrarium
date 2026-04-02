"""Entry point for the KohakuTerrarium HTTP API server."""

import os
import sys
from pathlib import Path

# Ensure project root (for apps.*) and src/ (for kohakuterrarium.*) are importable
_project_root = str(Path(__file__).resolve().parents[2])
_src_path = str(Path(__file__).resolve().parents[2] / "src")
for _p in (_project_root, _src_path):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import uvicorn

from apps.api.app import create_app

# Config directories - defaults to project's creatures/ and terrariums/
_creatures_dirs = os.environ.get(
    "KT_CREATURES_DIRS",
    str(Path(_project_root) / "creatures"),
).split(",")

_terrariums_dirs = os.environ.get(
    "KT_TERRARIUMS_DIRS",
    str(Path(_project_root) / "terrariums"),
).split(",")

app = create_app(
    creatures_dirs=_creatures_dirs,
    terrariums_dirs=_terrariums_dirs,
)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KohakuTerrarium API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--reload", action="store_true", help="Auto-reload on code changes (dev only)"
    )
    args = parser.parse_args()

    uvicorn.run(
        "apps.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
