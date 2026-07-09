"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.strategies import router as strategies_router

app = FastAPI(title="CapitalForge")

app.include_router(strategies_router)