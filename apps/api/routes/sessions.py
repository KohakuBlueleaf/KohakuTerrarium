"""Session management routes. List saved sessions and resume them."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from apps.api.deps import get_manager
from kohakuterrarium.session.resume import (
    detect_session_type,
    resume_agent,
    resume_terrarium,
)
from kohakuterrarium.session.store import SessionStore

router = APIRouter()

_SESSION_DIR = Path.home() / ".kohakuterrarium" / "sessions"


@router.get("")
def list_sessions(limit: int = 20):
    """List saved sessions, most recent first."""
    if not _SESSION_DIR.exists():
        return []

    sessions = sorted(
        list(_SESSION_DIR.glob("*.kohakutr")) + list(_SESSION_DIR.glob("*.kt")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    results = []
    for path in sessions:
        try:
            store = SessionStore(path)
            meta = store.load_meta()
            store.close()
            results.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "config_type": meta.get("config_type", "unknown"),
                    "config_path": meta.get("config_path", ""),
                    "terrarium_name": meta.get("terrarium_name", ""),
                    "agents": meta.get("agents", []),
                    "status": meta.get("status", ""),
                    "created_at": meta.get("created_at", ""),
                    "last_active": meta.get("last_active", ""),
                }
            )
        except Exception:
            results.append({"name": path.stem, "filename": path.name, "error": True})
    return results


@router.post("/{session_name}/resume")
async def resume_session(session_name: str):
    """Resume a saved session. Returns the created instance ID.

    The frontend can then connect to the instance via normal
    terrarium/agent WebSocket and history endpoints.
    """
    # Find the session file
    path = None
    for ext in (".kohakutr", ".kt"):
        candidate = _SESSION_DIR / f"{session_name}{ext}"
        if candidate.exists():
            path = candidate
            break

    if path is None:
        # Try prefix match
        matches = [
            p
            for p in list(_SESSION_DIR.glob("*.kohakutr"))
            + list(_SESSION_DIR.glob("*.kt"))
            if p.stem.startswith(session_name) or session_name in p.stem
        ]
        if len(matches) == 1:
            path = matches[0]
        elif len(matches) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Ambiguous session name, {len(matches)} matches. "
                f"Options: {[m.stem for m in matches[:5]]}",
            )

    if path is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_name}")

    session_type = detect_session_type(path)
    manager = get_manager()

    try:
        # Force CLI mode (headless) for web resume. TUI can't run without a TTY.
        if session_type == "terrarium":
            runtime, store = resume_terrarium(path, io_mode="cli")
            tid = await manager.register_terrarium(runtime, store)
            return {
                "instance_id": tid,
                "type": "terrarium",
                "session_name": path.stem,
            }
        else:
            agent, store = resume_agent(path, io_mode="cli")
            aid = await manager.register_agent(agent, store)
            return {
                "instance_id": aid,
                "type": "agent",
                "session_name": path.stem,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")
