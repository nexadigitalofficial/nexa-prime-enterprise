from fastapi import APIRouter, Depends, HTTPException, Form, BackgroundTasks
from typing import Optional, Dict
import aiosqlite
import asyncio
import os
from app.core.database import get_db
from app.services.telegram_service import telegram_manager

router = APIRouter(prefix="/api/telegram", tags=["Telegram Bot"])

# Master Admin PIN Key (Default: nexa2026, customizable via environment variable)
ADMIN_PIN_KEY = os.getenv("NEXA_ADMIN_PIN", "nexa2026")

@router.get("/status")
async def get_telegram_bot_status():
    """Get current public status of Telegram Bot connection"""
    me = await telegram_manager.get_me()
    return {
        "is_running": telegram_manager.is_running,
        "has_token": bool(telegram_manager.bot_token),
        "bot_info": me
    }

@router.post("/verify-admin")
async def verify_admin_pin(admin_pin: str = Form(...)):
    """Verify Admin Security PIN Key"""
    if admin_pin.strip() != ADMIN_PIN_KEY:
        raise HTTPException(status_code=403, detail="🔒 Geçersiz Admin PIN Şifresi. Yetkisiz Erişim Engellendi!")
    return {"status": "ok", "message": "✅ Admin yetkisi başarıyla doğrulandı."}

@router.post("/configure")
async def configure_telegram_bot(
    token: str = Form(...),
    admin_pin: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Set or update Telegram Bot Token (Protected by Admin PIN)"""
    if admin_pin.strip() != ADMIN_PIN_KEY:
        raise HTTPException(status_code=403, detail="🔒 Yetkisiz İşlem! Telegram API Token Değiştirmek İçin Geçerli Admin PIN Şifresi Gereklidir.")

    if not token or not token.strip():
        raise HTTPException(status_code=400, detail="Lütfen geçerli bir BotFather Token girin.")

    telegram_manager.set_token(token)
    me = await telegram_manager.get_me()

    if not me:
        raise HTTPException(status_code=400, detail="Girdiğiniz Telegram Bot Token geçersiz veya Telegram API'ye ulaşılamadı. Lütfen BotFather'dan aldığınız token'ı kontrol edin.")

    # Save token to .env file for persistence
    try:
        env_path = r"C:\Users\USER\Desktop\NEXA_PRIME_v2_ENTERPRISE\.env"
        env_content = ""
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_content = f.read()
        
        if "TELEGRAM_BOT_TOKEN=" in env_content:
            lines = env_content.splitlines()
            new_lines = []
            for l in lines:
                if l.startswith("TELEGRAM_BOT_TOKEN="):
                    new_lines.append(f"TELEGRAM_BOT_TOKEN={token.strip()}")
                else:
                    new_lines.append(l)
            env_content = "\n".join(new_lines)
        else:
            env_content += f"\nTELEGRAM_BOT_TOKEN={token.strip()}\n"

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
    except Exception as e:
        pass

    # Stop previous polling if running
    if telegram_manager.is_running:
        telegram_manager.stop()
        await asyncio.sleep(1)

    # Start polling in background task
    asyncio.create_task(telegram_manager.start_polling(get_db))

    return {
        "message": f"✅ Telegram Bot Başarıyla Bağlandı! @{me.get('username')} şu an aktif ve soruları yanıtlıyor.",
        "bot_username": me.get("username"),
        "bot_name": me.get("first_name")
    }

@router.post("/webhook")
async def telegram_webhook(update: Dict, db: aiosqlite.Connection = Depends(get_db)):
    """Webhook endpoint for production Telegram updates"""
    try:
        await telegram_manager.process_update(update, db)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
