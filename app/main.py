"""
main.py — FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log"),
    ],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan manages startup and shutdown logic for the FastAPI app.

    WHY LIFESPAN INSTEAD OF @app.on_event("startup")?
      on_event is deprecated in modern FastAPI. Lifespan is the correct
      pattern — it uses a context manager so startup and shutdown code
      live together in one place, making the flow obvious.

    Everything BEFORE `yield` runs on startup.
    Everything AFTER `yield` runs on shutdown.
    """
    # --- Startup ---
    # Import here to avoid circular imports at module load time
    from app.routers.polling import scheduler
    scheduler.start()

    yield  # App is running and serving requests here

    # --- Shutdown ---
    # Gracefully stop the scheduler — waits for any running job to finish
    # before the process exits. Prevents jobs from being killed mid-execution.
    if scheduler.running:
        scheduler.shutdown(wait=True)


# --- App instantiation ---
app = FastAPI(
    title="Gmail AI Summarizer Agent",
    description="An AI-powered agent that fetches and summarizes your Gmail emails.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
from app.routers import auth, emails, polling, history

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(emails.router, prefix="/emails", tags=["Emails"])
app.include_router(polling.router, prefix="/polling", tags=["Background Polling"])
app.include_router(history.router, prefix="/history", tags=["History & Analytics"])


# --- Health Check ---
@app.get("/health", tags=["System"])
async def health_check():
    from app.routers.polling import scheduler
    return {
        "status": "healthy",
        "service": "Gmail AI Summarizer Agent",
        "environment": settings.app_env,
        "version": "1.0.0",
        "scheduler_running": scheduler.running,
    }


# --- Root ---
@app.get("/", tags=["System"])
async def root():
    return {
        "message": "Gmail AI Summarizer Agent is running.",
        "docs": "/docs",
        "health": "/health",
    }
