"""Unified WebSocket endpoints.

  /ws/terrariums/{terrarium_id}  - ALL events for a terrarium
  /ws/creatures/{agent_id}       - ALL events for a standalone agent

Every event tagged with source. Channel messages captured via on_send
callbacks (works for both queue and broadcast channels).
"""

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.deps import get_manager
from kohakuterrarium.modules.output.base import OutputModule

router = APIRouter()

# ── Event logs (per mount, for history API) ─────────────────────────

_event_logs: dict[str, list] = {}


def get_event_log(key: str) -> list:
    if key not in _event_logs:
        _event_logs[key] = []
    return _event_logs[key]


# ── Stream output module (per creature/agent) ──────────────────────


class StreamOutput(OutputModule):
    """Secondary output that tags events with source and pushes to shared queue."""

    def __init__(self, source: str, queue: asyncio.Queue, log: list):
        self._src = source
        self._q = queue
        self._log = log
        self._n = 0

    def _put(self, msg):
        msg["source"] = self._src
        msg["ts"] = time.time()
        self._q.put_nowait(msg)
        self._log.append(msg)

    async def start(self):
        pass

    async def stop(self):
        pass

    async def flush(self):
        pass

    async def write(self, text):
        self._put({"type": "text", "content": text})

    async def write_stream(self, chunk):
        if chunk:
            self._put({"type": "text", "content": chunk})

    async def on_processing_start(self):
        self._put({"type": "processing_start"})

    async def on_processing_end(self):
        self._put({"type": "processing_end"})

    def on_activity(self, activity_type, detail):
        name, info = _parse_detail(detail)
        self._put(
            {
                "type": "activity",
                "activity_type": activity_type,
                "name": name,
                "detail": info,
                "id": f"{activity_type}_{self._n}",
            }
        )
        self._n += 1

    def on_activity_with_metadata(self, activity_type, detail, metadata):
        name, info = _parse_detail(detail)
        msg = {
            "type": "activity",
            "activity_type": activity_type,
            "name": name,
            "detail": info,
            "id": f"{activity_type}_{self._n}",
        }
        if metadata:
            for k in (
                "args",
                "job_id",
                "tools_used",
                "result",
                "turns",
                "duration",
                "task",
                "trigger_id",
                "event_type",
                "channel",
                "sender",
                "content",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            ):
                if k in metadata:
                    msg[k] = metadata[k]
        self._put(msg)
        self._n += 1


def _parse_detail(detail):
    try:
        if detail.startswith("["):
            end = detail.index("]", 1)
            return detail[1:end], detail[end + 2 :]
    except ValueError:
        pass
    return "unknown", detail


async def _forward_queue(queue, ws):
    try:
        while True:
            msg = await queue.get()
            if msg is None:
                break
            await ws.send_json(msg)
    except Exception:
        pass


# ── /ws/terrariums/{terrarium_id} ───────────────────────────────────


@router.websocket("/ws/terrariums/{terrarium_id}")
async def ws_terrarium(websocket: WebSocket, terrarium_id: str):
    await websocket.accept()
    manager = get_manager()

    try:
        runtime = manager._get_runtime(terrarium_id)
    except ValueError as e:
        await websocket.send_json({"type": "error", "content": str(e)})
        await websocket.close()
        return

    queue = asyncio.Queue()
    attached = []  # (name, StreamOutput, agent)
    channel_cbs = []  # (channel, callback) for cleanup

    # ── Attach to root agent ──
    if runtime.root_agent is not None:
        log = get_event_log(f"{terrarium_id}:root")
        out = StreamOutput("root", queue, log)
        runtime.root_agent.output_router.add_secondary(out)
        attached.append(("root", out, runtime.root_agent))
        manager.terrarium_mount(terrarium_id, "root")

    # ── Attach to all creatures ──
    for cname in runtime.get_status()["creatures"]:
        agent = runtime.get_creature_agent(cname)
        if agent is None:
            continue
        log = get_event_log(f"{terrarium_id}:{cname}")
        out = StreamOutput(cname, queue, log)
        agent.output_router.add_secondary(out)
        attached.append((cname, out, agent))
        manager.terrarium_mount(terrarium_id, cname)

    # ── Subscribe to ALL channel messages via on_send callback ──
    # This works for both queue and broadcast channels
    def make_channel_cb(ch_name):
        def cb(channel_name, message):
            ts = (
                message.timestamp.isoformat()
                if hasattr(message.timestamp, "isoformat")
                else str(message.timestamp)
            )
            queue.put_nowait(
                {
                    "type": "channel_message",
                    "source": "channel",
                    "channel": channel_name,
                    "sender": message.sender,
                    "content": (
                        message.content
                        if isinstance(message.content, str)
                        else str(message.content)
                    ),
                    "message_id": message.message_id,
                    "timestamp": ts,
                    "ts": time.time(),
                }
            )

        return cb

    for ch in runtime.environment.shared_channels._channels.values():
        cb = make_channel_cb(ch.name)
        ch.on_send(cb)
        channel_cbs.append((ch, cb))

    # ── Send channel history (messages that happened before WS connected) ──
    for ch in runtime.environment.shared_channels._channels.values():
        for msg in ch.history:
            ts = (
                msg.timestamp.isoformat()
                if hasattr(msg.timestamp, "isoformat")
                else str(msg.timestamp)
            )
            await websocket.send_json(
                {
                    "type": "channel_message",
                    "source": "channel",
                    "channel": ch.name,
                    "sender": msg.sender,
                    "content": (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    ),
                    "message_id": msg.message_id,
                    "timestamp": ts,
                    "ts": time.time(),
                    "history": True,
                }
            )

    fwd_task = asyncio.create_task(_forward_queue(queue, websocket))

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "input":
                target = data.get("target", "root")
                message = data.get("message", "")
                if not message:
                    continue
                try:
                    session = manager.terrarium_mount(terrarium_id, target)
                    # Record user input in the target's event log
                    log = get_event_log(f"{terrarium_id}:{target}")
                    log.append(
                        {
                            "type": "user_input",
                            "source": target,
                            "content": message,
                            "ts": time.time(),
                        }
                    )
                    await session.agent.inject_input(message, source="web")
                    await websocket.send_json(
                        {"type": "idle", "source": target, "ts": time.time()}
                    )
                except ValueError as e:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "source": target,
                            "content": str(e),
                            "ts": time.time(),
                        }
                    )
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        queue.put_nowait(None)
        fwd_task.cancel()
        for _, out, agent in attached:
            try:
                agent.output_router.remove_secondary(out)
            except Exception:
                pass
        for ch, cb in channel_cbs:
            try:
                ch.remove_on_send(cb)
            except Exception:
                pass
        try:
            await websocket.close()
        except RuntimeError:
            pass  # Already closed


# ── /ws/creatures/{agent_id} ────────────────────────────────────────


@router.websocket("/ws/creatures/{agent_id}")
async def ws_creature(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    manager = get_manager()

    session = manager._agents.get(agent_id)
    if not session:
        await websocket.send_json(
            {"type": "error", "content": f"Agent not found: {agent_id}"}
        )
        await websocket.close()
        return

    queue = asyncio.Queue()
    log = get_event_log(f"agent:{agent_id}")
    out = StreamOutput(session.agent.config.name, queue, log)
    session.agent.output_router.add_secondary(out)

    fwd_task = asyncio.create_task(_forward_queue(queue, websocket))

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "input":
                message = data.get("message", "")
                if not message:
                    continue
                log.append(
                    {
                        "type": "user_input",
                        "source": session.agent.config.name,
                        "content": message,
                        "ts": time.time(),
                    }
                )
                await session.agent.inject_input(message, source="web")
                await websocket.send_json(
                    {
                        "type": "idle",
                        "source": session.agent.config.name,
                        "ts": time.time(),
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        queue.put_nowait(None)
        fwd_task.cancel()
        try:
            session.agent.output_router.remove_secondary(out)
        except Exception:
            pass
        try:
            await websocket.close()
        except RuntimeError:
            pass  # Already closed
