"""
Package manager for KohakuTerrarium creature/terrarium packages.

Handles installing, listing, and resolving @package/path references.

Package layout:
  ~/.kohakuterrarium/packages/<name>/
    kohaku.yaml          # manifest
    creatures/           # creature configs
    terrariums/          # terrarium configs

Install methods:
  kt install <git-url>           # clone from git
  kt install <local-path> -e     # editable (symlink)

Reference syntax:
  @<package>/<path>  resolves to  ~/.kohakuterrarium/packages/<package>/<path>
"""

import shutil
import subprocess
from pathlib import Path

import yaml

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

PACKAGES_DIR = Path.home() / ".kohakuterrarium" / "packages"


def resolve_package_path(ref: str) -> Path:
    """Resolve a @package/path reference to an absolute path.

    Args:
        ref: Reference like "@kohaku-creatures/creatures/swe"

    Returns:
        Absolute path to the resolved location.

    Raises:
        FileNotFoundError: If the package or path doesn't exist.
    """
    if not ref.startswith("@"):
        raise ValueError(f"Not a package reference (must start with @): {ref}")

    ref = ref[1:]  # strip @
    parts = ref.split("/", 1)
    package_name = parts[0]
    sub_path = parts[1] if len(parts) > 1 else ""

    pkg_dir = PACKAGES_DIR / package_name
    if not pkg_dir.exists():
        raise FileNotFoundError(
            f"Package not installed: {package_name}. " f"Run: kt install <url-or-path>"
        )

    resolved = pkg_dir / sub_path if sub_path else pkg_dir
    if not resolved.exists():
        raise FileNotFoundError(f"Path not found in package {package_name}: {sub_path}")

    return resolved.resolve()


def is_package_ref(path: str) -> bool:
    """Check if a path is a @package reference."""
    return isinstance(path, str) and path.startswith("@")


def install_package(
    source: str,
    editable: bool = False,
    name_override: str | None = None,
) -> str:
    """Install a creature/terrarium package.

    Args:
        source: Git URL or local path.
        editable: If True, create symlink instead of copying (like pip -e).
        name_override: Override package name (default: from kohaku.yaml or dir name).

    Returns:
        Installed package name.
    """
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    source_path = Path(source).resolve()

    if (
        source.startswith("http://")
        or source.startswith("https://")
        or source.endswith(".git")
    ):
        # Git clone
        return _install_from_git(source, name_override)
    elif source_path.is_dir():
        # Local directory
        return _install_from_local(source_path, editable, name_override)
    else:
        raise ValueError(
            f"Cannot install from: {source}. "
            "Provide a git URL or local directory path."
        )


def _install_from_git(url: str, name_override: str | None = None) -> str:
    """Clone a git repo into packages directory."""
    # Determine package name from URL
    repo_name = url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    name = name_override or repo_name
    target = PACKAGES_DIR / name

    if target.exists():
        # Update existing
        logger.info("Updating package", package=name)
        try:
            subprocess.run(
                ["git", "-C", str(target), "pull", "--ff-only"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git pull failed: {e.stderr.decode()}")
    else:
        # Fresh clone
        logger.info("Cloning package", package=name, url=url)
        try:
            subprocess.run(
                ["git", "clone", url, str(target)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git clone failed: {e.stderr.decode()}")

    _validate_package(target, name)
    _install_python_deps(target)
    logger.info("Package installed", package=name, path=str(target))
    return name


def _install_from_local(
    source: Path, editable: bool, name_override: str | None = None
) -> str:
    """Install from local directory (copy or symlink)."""
    manifest = _load_manifest(source)
    name = name_override or manifest.get("name", source.name)
    target = PACKAGES_DIR / name

    if editable:
        # Symlink (like pip -e)
        if target.exists():
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        target.symlink_to(source)
        logger.info("Package linked (editable)", package=name, source=str(source))
    else:
        # Copy
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        logger.info("Package installed (copy)", package=name, source=str(source))

    _validate_package(target, name)
    _install_python_deps(target)
    return name


def uninstall_package(name: str) -> bool:
    """Remove an installed package."""
    target = PACKAGES_DIR / name
    if not target.exists():
        return False

    if target.is_symlink():
        target.unlink()
    else:
        shutil.rmtree(target)

    logger.info("Package uninstalled", package=name)
    return True


def list_packages() -> list[dict]:
    """List all installed packages with their creatures and terrariums."""
    if not PACKAGES_DIR.exists():
        return []

    results = []
    for pkg_dir in sorted(PACKAGES_DIR.iterdir()):
        if not pkg_dir.is_dir() and not pkg_dir.is_symlink():
            continue

        manifest = _load_manifest(pkg_dir)
        editable = pkg_dir.is_symlink()
        real_path = str(pkg_dir.resolve()) if editable else str(pkg_dir)

        results.append(
            {
                "name": manifest.get("name", pkg_dir.name),
                "version": manifest.get("version", "?"),
                "description": manifest.get("description", ""),
                "path": real_path,
                "editable": editable,
                "creatures": manifest.get("creatures", []),
                "terrariums": manifest.get("terrariums", []),
            }
        )
    return results


def get_package_path(name: str) -> Path | None:
    """Get the path to an installed package."""
    pkg = PACKAGES_DIR / name
    if pkg.exists():
        return pkg.resolve()
    return None


def _load_manifest(pkg_dir: Path) -> dict:
    """Load kohaku.yaml manifest from a package directory."""
    manifest_file = pkg_dir / "kohaku.yaml"
    if not manifest_file.exists():
        manifest_file = pkg_dir / "kohaku.yml"
    if not manifest_file.exists():
        return {"name": pkg_dir.name}

    with open(manifest_file) as f:
        return yaml.safe_load(f) or {}


def _validate_package(pkg_dir: Path, name: str) -> None:
    """Basic validation of a package structure."""
    has_creatures = (pkg_dir / "creatures").is_dir()
    has_terrariums = (pkg_dir / "terrariums").is_dir()
    if not has_creatures and not has_terrariums:
        logger.warning(
            "Package has no creatures/ or terrariums/ directory",
            package=name,
        )


def _install_python_deps(pkg_dir: Path) -> None:
    """Install Python dependencies from the package if any."""
    manifest = _load_manifest(pkg_dir)
    deps = manifest.get("python_dependencies", [])
    if deps:
        logger.info("Installing Python dependencies", count=len(deps))
        try:
            subprocess.run(
                ["pip", "install", *deps],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning("Dependency install failed", error=e.stderr.decode()[:200])

    # Also check for requirements.txt
    req_file = pkg_dir / "requirements.txt"
    if req_file.exists():
        try:
            subprocess.run(
                ["pip", "install", "-r", str(req_file)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(
                "requirements.txt install failed", error=e.stderr.decode()[:200]
            )
