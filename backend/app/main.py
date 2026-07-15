"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.strategies import router as strategies_router

from app.api.agent import router as agent_router

app = FastAPI(title="CapitalForge")

app.include_router(strategies_router)

app.include_router(agent_router)