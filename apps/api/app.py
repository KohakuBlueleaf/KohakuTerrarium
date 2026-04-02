"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.deps import get_manager
from apps.api.routes import agents, channels, configs, creatures, sessions, terrariums
from apps.api.ws import agents as ws_agents, channels as ws_channels, chat as ws_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    yield
    # Shutdown: stop all running agents/terrariums
    manager = get_manager()
    await manager.shutdown()


def create_app(
    creatures_dirs: list[str] | None = None,
    terrariums_dirs: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="KohakuTerrarium API",
        description="HTTP API for managing agents and terrariums",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configure config discovery directories
    if creatures_dirs or terrariums_dirs:
        configs.set_config_dirs(
            creatures=creatures_dirs or [],
            terrariums=terrariums_dirs or [],
        )

    # REST routes
    app.include_router(terrariums.router, prefix="/api/terrariums", tags=["terrariums"])
    app.include_router(
        creatures.router,
        prefix="/api/terrariums/{terrarium_id}/creatures",
        tags=["creatures"],
    )
    app.include_router(
        channels.router,
        prefix="/api/terrariums/{terrarium_id}/channels",
        tags=["channels"],
    )
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
    app.include_router(configs.router, prefix="/api/configs", tags=["configs"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])

    # WebSocket routes
    app.include_router(ws_channels.router, tags=["ws"])
    app.include_router(ws_agents.router, tags=["ws"])
    app.include_router(ws_chat.router, tags=["ws"])

    return app
