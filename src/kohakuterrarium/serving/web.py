"""
Web server and desktop app launcher for KohakuTerrarium.

``kt web``  — FastAPI + built Vue frontend in a single process.
``kt app``  — Same, but wrapped in a native pywebview window.
"""

import os
import sys
import threading
from pathlib import Path

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

# web_dist lives at src/kohakuterrarium/web_dist/ (built by vite)
WEB_DIST_DIR = Path(__file__).resolve().parent.parent / "web_dist"


def _resolve_config_dirs() -> tuple[list[str], list[str]]:
    """Resolve creature/terrarium config directories.

    Sources (all merged):
      1. KT_CREATURES_DIRS / KT_TERRARIUMS_DIRS env vars
      2. Installed packages (``~/.kohakuterrarium/packages/``)
      3. Local project dirs (``creatures/``, ``terrariums/`` in project root)
    """
    from kohakuterrarium.packages import PACKAGES_DIR, _get_package_root, list_packages

    creatures: list[str] = []
    terrariums: list[str] = []

    # 1. Env vars (highest priority, explicit override)
    env_creatures = os.environ.get("KT_CREATURES_DIRS")
    if env_creatures:
        creatures.extend(env_creatures.split(","))
    env_terrariums = os.environ.get("KT_TERRARIUMS_DIRS")
    if env_terrariums:
        terrariums.extend(env_terrariums.split(","))

    # 2. Installed packages
    if PACKAGES_DIR.exists():
        for pkg in list_packages():
            pkg_root = _get_package_root(pkg["name"])
            if pkg_root:
                c = pkg_root / "creatures"
                t = pkg_root / "terrariums"
                if c.is_dir():
                    creatures.append(str(c))
                if t.is_dir():
                    terrariums.append(str(t))

    # 3. Current working directory (where the user runs kt web/app from)
    cwd = Path.cwd()
    for d in (cwd / "creatures", cwd / "agents"):
        if d.is_dir() and str(d) not in creatures:
            creatures.append(str(d))
    cwd_t = cwd / "terrariums"
    if cwd_t.is_dir() and str(cwd_t) not in terrariums:
        terrariums.append(str(cwd_t))

    return creatures, terrariums


def run_web_server(
    host: str = "0.0.0.0",
    port: int = 8001,
    dev: bool = False,
) -> None:
    """Start the FastAPI server, optionally serving the built frontend.

    Args:
        host: Bind address.
        port: Bind port.
        dev: If True, skip static file serving (user runs vite dev separately).
    """
    import uvicorn

    from kohakuterrarium.api.app import create_app

    static_dir = None if dev else WEB_DIST_DIR

    if not dev and not (static_dir and static_dir.is_dir()):
        logger.error(
            "web_dist not found — run 'npm run build --prefix src/kohakuterrarium-frontend' first, "
            "or use --dev mode",
            path=str(WEB_DIST_DIR),
        )
        sys.exit(1)

    creatures_dirs, terrariums_dirs = _resolve_config_dirs()

    app = create_app(
        creatures_dirs=creatures_dirs,
        terrariums_dirs=terrariums_dirs,
        static_dir=static_dir,
    )

    if dev:
        print(f"API-only mode on http://{host}:{port}")
        print(
            "Start vite dev server separately: "
            "npm run dev --prefix src/kohakuterrarium-frontend"
        )
    else:
        print(f"KohakuTerrarium web UI: http://{host}:{port}")

    uvicorn.run(app, host=host, port=port)


def run_desktop_app(port: int = 8001) -> None:
    """Launch the web UI in a native pywebview window.

    Starts FastAPI + static files on 127.0.0.1 in a daemon thread,
    then opens a native OS webview window pointing at it.
    """
    try:
        import webview
    except ImportError:
        print("pywebview is required for 'kt app'.")
        print("Install: pip install 'KohakuTerrarium[desktop]'")
        sys.exit(1)

    import uvicorn

    from kohakuterrarium.api.app import create_app

    if not WEB_DIST_DIR.is_dir():
        logger.error(
            "web_dist not found — run 'npm run build --prefix src/kohakuterrarium-frontend' first",
            path=str(WEB_DIST_DIR),
        )
        sys.exit(1)

    creatures_dirs, terrariums_dirs = _resolve_config_dirs()

    app = create_app(
        creatures_dirs=creatures_dirs,
        terrariums_dirs=terrariums_dirs,
        static_dir=WEB_DIST_DIR,
    )

    # Uvicorn in a daemon thread — dies when the main thread (webview) exits
    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": app,
            "host": "127.0.0.1",
            "port": port,
            "log_level": "warning",
        },
        daemon=True,
    )
    server_thread.start()

    webview.create_window(
        "KohakuTerrarium",
        f"http://127.0.0.1:{port}",
        width=1280,
        height=800,
        zoomable=True,
    )
    webview.start()
