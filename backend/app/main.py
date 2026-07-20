"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.strategies import router as strategies_router
from app.api.agent import router as agent_router
from app.api.logos import router as logos_router
from app.api.market import router as market_router
from app.api.portfolio import router as portfolio_router
from app.db.session import SessionLocal
from app.workers.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler(SessionLocal, interval_minutes=15)
    yield
    scheduler.shutdown()


app = FastAPI(title="CapitalForge", lifespan=lifespan)

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