"""
NEXA PRIME — Enterprise Edition v2.0
Modular FastAPI Architecture with Hardened Security & DB Pool
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api import auth, projects, documents, chat, system, telegram
from app.services.telegram_service import telegram_manager
from app.core.database import get_db
import asyncio

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nexa.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting NEXA PRIME Enterprise Server v2.0...")
    await init_db()
    
    # Auto-start Telegram Bot Polling if token is set in env
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        telegram_manager.set_token(token)
        asyncio.create_task(telegram_manager.start_polling(get_db))

    yield
    # Shutdown
    logger.info("🛑 Shutting down server...")
    if telegram_manager.is_running:
        telegram_manager.stop()
    await close_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Enterprise CORS Settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api import auth, projects, documents, chat, system, telegram, crm, swarm

# Register API Routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(system.router)
app.include_router(telegram.router)
app.include_router(crm.router)
app.include_router(swarm.router)

# Static files for documents & images
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_portal():
    response = FileResponse("portal.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/admin")
async def serve_admin():
    response = FileResponse("admin.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8050, reload=True)
