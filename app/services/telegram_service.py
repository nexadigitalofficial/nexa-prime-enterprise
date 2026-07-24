import asyncio
import logging
import httpx
import json
import re
from typing import Optional, Dict, Any
import aiosqlite

from app.core.config import settings
from app.services.rag_service import generate_cognitive_response, generate_project_intelligence_report

logger = logging.getLogger("nexa.telegram")

TELEGRAM_API_URL = "https://api.telegram.org/bot"

class TelegramBotManager:
    def __init__(self):
        self.bot_token: Optional[str] = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        self.is_running: bool = False
        self.polling_task: Optional[asyncio.Task] = None
        self.bot_info: Optional[Dict] = None

    def set_token(self, token: str):
        """Set or update Telegram Bot Token."""
        self.bot_token = token.strip()

    async def get_me(self) -> Optional[Dict]:
        """Fetch bot info from Telegram API."""
        if not self.bot_token:
            return None
        url = f"{TELEGRAM_API_URL}{self.bot_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        self.bot_info = data.get("result")
                        return self.bot_info
        except Exception as e:
            logger.warning(f"Telegram getMe failed: {e}")
        return None

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message to a Telegram chat."""
        if not self.bot_token:
            return False
        url = f"{TELEGRAM_API_URL}{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    # Retry without parse_mode if Markdown fails due to unescaped chars
                    payload.pop("parse_mode", None)
                    await client.post(url, json=payload)
                return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def process_update(self, update: Dict, db: aiosqlite.Connection):
        """Process an incoming update from Telegram."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()

        if not chat_id or not text:
            return

        logger.info(f"📩 Incoming Telegram message from chat {chat_id}: '{text}'")

        # 1. Handle Command: /start or /help
        if text.startswith("/start") or text.startswith("/help"):
            welcome = (
                "🏛️ *NEXA PRIME Enterprise — AI Telegram Asistanına Hoş Geldiniz!*\n\n"
                "Ben NEXA PRIME gayrimenkul ve topraktan yatırım yapay zeka asistanıyım. "
                "Tüm resmi proje belgelerini, kat planlarını, fiyat listelerini ve tapu verilerini anlık analiz ederim.\n\n"
                "📌 *Kullanabileceğiniz Komutlar:*\n"
                "• `/projeler` — Tüm lüks portföy projelerini listeler\n"
                "• `/proje <id>` — Belirtilen projenin detay ve kat planlarını getirir (örn: `/proje 13`)\n"
                "• `/rapor <id>` — Projenin AI Intelligence Raporunu üretir (örn: `/rapor 13`)\n"
                "• *Veya doğrudan sorunuzu yazın:* (örn: _'VIP AKADEMİ projesinin fiyatı ve teslim tarihi nedir?'_)\n"
            )
            await self.send_message(chat_id, welcome)
            return

        # 2. Handle Command: /projeler or /projects
        if text.startswith("/projeler") or text.startswith("/projects"):
            async with db.execute("SELECT id, name, location, ilce, il, ada_no, parsel_no FROM projects ORDER BY id ASC") as cursor:
                rows = await cursor.fetchall()
            
            lines = ["📋 *NEXA PRIME LÜKS PORTFÖY LİSTESİ (20 Proje)*\n"]
            for r in rows:
                ada_p = f" (Ada: {r['ada_no']}/{r['parsel_no']})" if r['ada_no'] else ""
                lines.append(f"• *#{r['id']} {r['name']}*{ada_p}\n  📍 {r['location'] or r['ilce']}\n  🔍 Detay: `/proje {r['id']}` | Rapor: `/rapor {r['id']}`\n")
            
            lines.append("💬 Sorularınızı doğrudan buraya yazabilirsiniz!")
            await self.send_message(chat_id, "\n".join(lines))
            return

        # 3. Handle Command: /proje <id> or /detay <id>
        if text.startswith("/proje") or text.startswith("/detay"):
            parts = text.split()
            if len(parts) > 1 and parts[1].isdigit():
                p_id = int(parts[1])
                async with db.execute("SELECT * FROM projects WHERE id = ?", (p_id,)) as cursor:
                    p = await cursor.fetchone()
                if p:
                    p_dict = dict(p)
                    ada_p = f"{p_dict['ada_no']} Ada / {p_dict['parsel_no']} Parsel" if p_dict['ada_no'] else "Kadastro Teyitli"
                    msg = (
                        f"🏛️ *PROJE #{p_dict['id']} — {p_dict['name']}*\n\n"
                        f"📍 *Konum:* {p_dict['location'] or p_dict['ilce']}\n"
                        f"🗺️ *İl/İlçe:* {p_dict['ilce']}, {p_dict['il']}\n"
                        f"📜 *Tapu / Kadastro:* {ada_p} ({'✅ TKGM Onaylı' if p_dict['tkgm_verified'] else 'Prestij Portföy'})\n\n"
                        f"📝 *Açıklama:* {p_dict['description'] or 'Lüks konut ve yatırım projesi.'}\n\n"
                        f"🤖 Derin AI Raporu için: `/rapor {p_dict['id']}`"
                    )
                    await self.send_message(chat_id, msg)
                    return
                else:
                    await self.send_message(chat_id, f"❌ #{p_id} ID'li proje bulunamadı.")
                    return

        # 4. Handle Command: /rapor <id> or /intelligence <id>
        if text.startswith("/rapor") or text.startswith("/intelligence"):
            parts = text.split()
            if len(parts) > 1 and parts[1].isdigit():
                p_id = int(parts[1])
                await self.send_message(chat_id, f"🧠 Proje #{p_id} için AI Intelligence Raporu taranıyor, lütfen bekleyin...")
                try:
                    report = await generate_project_intelligence_report(db, p_id)
                    # Limit length for Telegram
                    snippet = report[:3500] if len(report) > 3500 else report
                    await self.send_message(chat_id, snippet)
                except Exception as e:
                    await self.send_message(chat_id, f"❌ Rapor oluşturma hatası: {e}")
                return

        # 5. Natural Language AI Inquiry via RAG Search
        await self.send_message(chat_id, "🤖 *NEXA AI Hafızası Taranıyor...*")
        try:
            rag_response = await generate_cognitive_response(db, text)
            await self.send_message(chat_id, f"🏛️ *NEXA PRIME AI Yanıtı:*\n\n{rag_response}")
        except Exception as e:
            logger.error(f"Telegram RAG error: {e}")
            await self.send_message(chat_id, f"⚠️ Yanıt oluşturulamadı: {e}")

    async def start_polling(self, db_getter):
        """Start Long-Polling background loop for local environment without domain."""
        if self.is_running or not self.bot_token:
            return

        bot_data = await self.get_me()
        if not bot_data:
            logger.error("❌ Telegram Bot Token is invalid or API unreachable!")
            return

        self.is_running = True
        logger.info(f"🤖 Telegram Bot Polling Started: @{bot_data.get('username')}")

        offset = 0
        while self.is_running:
            try:
                url = f"{TELEGRAM_API_URL}{self.bot_token}/getUpdates?offset={offset}&timeout=20"
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            updates = data.get("result", [])
                            for up in updates:
                                offset = up["update_id"] + 1
                                # Get DB connection
                                db = await db_getter()
                                await self.process_update(up, db)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Telegram polling loop exception: {e}")
                await asyncio.sleep(3)

        self.is_running = False
        logger.info("🛑 Telegram Bot Polling Stopped.")

    def stop(self):
        """Stop polling worker."""
        self.is_running = False

telegram_manager = TelegramBotManager()
