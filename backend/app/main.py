"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.strategies import router as strategies_router

from app.api.agent import router as agent_router

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CapitalForge")

app.include_router(strategies_router)

app.include_router(agent_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)