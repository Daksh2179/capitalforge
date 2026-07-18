"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.strategies import router as strategies_router
from app.api.agent import router as agent_router
from app.api.logos import router as logos_router
from app.api.market import router as market_router
from app.api.portfolio import router as portfolio_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CapitalForge")

app.include_router(strategies_router)
app.include_router(agent_router)
app.include_router(logos_router)
app.include_router(market_router)
app.include_router(portfolio_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)