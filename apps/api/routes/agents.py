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


@router.get("/{agent_id}/jobs")
def agent_jobs(agent_id: str, manager=Depends(get_manager)):
    """List running background jobs for an agent."""
    session = manager._agents.get(agent_id)
    if not session:
        raise HTTPException(404, f"Agent not found: {agent_id}")
    agent = session.agent
    jobs = []
    for j in agent.executor.get_running_jobs():
        jobs.append(_job_to_dict(j))
    if hasattr(agent, "subagent_manager") and agent.subagent_manager:
        for j in agent.subagent_manager.get_running_jobs():
            jobs.append(_job_to_dict(j))
    return jobs


@router.post("/{agent_id}/tasks/{job_id}/stop")
async def stop_agent_task(agent_id: str, job_id: str, manager=Depends(get_manager)):
    """Stop a specific background task."""
    session = manager._agents.get(agent_id)
    if not session:
        raise HTTPException(404, f"Agent not found: {agent_id}")
    agent = session.agent
    if await agent.executor.cancel(job_id):
        return {"status": "cancelled", "job_id": job_id}
    if hasattr(agent, "subagent_manager") and agent.subagent_manager:
        if await agent.subagent_manager.cancel(job_id):
            return {"status": "cancelled", "job_id": job_id}
    status = agent.executor.get_status(job_id)
    if status:
        return {"status": status.state.value, "job_id": job_id}
    raise HTTPException(404, f"Task not found: {job_id}")


def _job_to_dict(j) -> dict:
    return {
        "job_id": j.job_id,
        "job_type": j.job_type.value,
        "type_name": j.type_name,
        "state": j.state.value,
        "start_time": j.start_time.isoformat() if j.start_time else "",
        "duration": j.duration,
        "preview": j.preview,
    }


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
async def chat_agent(agent_id: str, req: AgentChat, manager=Depends(get_manager)):
    """Non-streaming chat with an agent."""
    try:
        chunks = []
        async for chunk in manager.agent_chat(agent_id, req.message):
            chunks.append(chunk)
        return {"response": "".join(chunks)}
    except ValueError as e:
        raise HTTPException(404, str(e))
