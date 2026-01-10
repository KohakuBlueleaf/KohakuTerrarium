"""
Prompt loading utilities.

Load markdown prompts from files and folders.
"""

from pathlib import Path

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def load_prompt(path: str | Path) -> str:
    """
    Load a single prompt file.

    Args:
        path: Path to markdown/text file

    Returns:
        File contents as string

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    with open(path, encoding="utf-8") as f:
        content = f.read()

    logger.debug("Loaded prompt", path=str(path), length=len(content))
    return content


def load_prompts_folder(folder: str | Path) -> dict[str, str]:
    """
    Load all prompts from a folder.

    Loads all .md and .txt files, using filename (without extension) as key.

    Args:
        folder: Path to folder containing prompt files

    Returns:
        Dict mapping filename to content
    """
    folder = Path(folder)
    if not folder.exists():
        logger.warning("Prompts folder not found", path=str(folder))
        return {}

    prompts = {}
    for path in folder.iterdir():
        if path.suffix.lower() in (".md", ".txt"):
            name = path.stem
            prompts[name] = load_prompt(path)

    logger.debug("Loaded prompts folder", path=str(folder), count=len(prompts))
    return prompts


def load_prompt_with_fallback(
    primary: str | Path | None,
    fallback: str,
) -> str:
    """
    Load prompt from file, falling back to default string.

    Args:
        primary: Path to prompt file (can be None)
        fallback: Default prompt if file not found

    Returns:
        Prompt content
    """
    if primary is None:
        return fallback

    try:
        return load_prompt(primary)
    except FileNotFoundError:
        logger.debug("Prompt file not found, using fallback", path=str(primary))
        return fallback
