"""Standalone agent chat routes."""

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import get_manager
from apps.api.events import get_event_log
from apps.api.schemas import AgentChat, AgentCreate

router = APIRouter()


@router.post("")
async def create_agent(req: AgentCreate, manager=Depends(get_manager)):
    """Create and start a standalone agent."""
    try:
        agent_id = await manager.agent_create(config_path=req.config_path)
        return {"agent_id": agent_id, "status": "running"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_agents(manager=Depends(get_manager)):
    """List all running agents."""
    return manager.agent_list()


@router.get("/{agent_id}")
def get_agent(agent_id: str, manager=Depends(get_manager)):
    """Get status of a specific agent."""
    try:
        return manager.agent_status(agent_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{agent_id}")
async def stop_agent(agent_id: str, manager=Depends(get_manager)):
    """Stop and cleanup an agent."""
    try:
        await manager.agent_stop(agent_id)
        return {"status": "stopped"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{agent_id}/interrupt")
async def interrupt_agent(agent_id: str, manager=Depends(get_manager)):
    """Interrupt the agent's current processing. Agent stays alive."""
    session = manager._agents.get(agent_id)
    if not session:
        raise HTTPException(404, f"Agent not found: {agent_id}")
    session.agent.interrupt()
    return {"status": "interrupted"}


@router.get("/{agent_id}/history")
def agent_history(agent_id: str, manager=Depends(get_manager)):
    """Get conversation history + event log for a standalone agent."""
    try:
        session = manager._agents.get(agent_id)
        if not session:
            raise ValueError(f"Agent not found: {agent_id}")

        # Prefer SessionStore events (persistent, works after resume)
        events = []
        agent = session.agent
        if hasattr(agent, "session_store") and agent.session_store:
            try:
                events = agent.session_store.get_events(agent.config.name)
            except Exception:
                pass

        # Fallback to in-memory log
        if not events:
            events = get_event_log(f"agent:{agent_id}")

        return {
            "agent_id": agent_id,
            "messages": agent.conversation_history,
            "events": events,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{agent_id}/chat")
async def chat_agent(
    agent_id: str, req: AgentChat, manager=Depends(get_manager)
):
    """Non-streaming chat with an agent."""
    try:
        chunks = []
        async for chunk in manager.agent_chat(agent_id, req.message):
            chunks.append(chunk)
        return {"response": "".join(chunks)}
    except ValueError as e:
        raise HTTPException(404, str(e))
