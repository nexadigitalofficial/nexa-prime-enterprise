import asyncio
import logging
import httpx
import json
import re
import html
from typing import Optional, Dict, Any, List
import aiosqlite

from app.core.config import settings
from app.services.rag_service import generate_cognitive_response, generate_project_intelligence_report

logger = logging.getLogger("nexa.telegram")

TELEGRAM_API_URL = "https://api.telegram.org/bot"

def format_text_for_telegram_html(raw_text: str) -> str:
    """
    Converts LLM GitHub Markdown into clean, beautifully styled Telegram HTML.
    Strips raw callouts, tables, and unescaped HTML characters.
    """
    if not raw_text:
        return ""

    text = raw_text

    # 1. Clean GitHub Callouts (> [!NOTE], > [!IMPORTANT], > [!WARNING])
    text = re.sub(r'>\s*\[!NOTE\]\s*', '💡 <b>BİLGİ NOTU:</b> ', text, flags=re.IGNORECASE)
    text = re.sub(r'>\s*\[!IMPORTANT\]\s*', '⭐ <b>ÖNEMLİ:</b> ', text, flags=re.IGNORECASE)
    text = re.sub(r'>\s*\[!WARNING\]\s*', '⚠️ <b>UYARI:</b> ', text, flags=re.IGNORECASE)
    text = re.sub(r'>\s*\[!TIP\]\s*', '🎯 <b>İPUCU:</b> ', text, flags=re.IGNORECASE)
    text = re.sub(r'>\s*', '▫️ ', text)

    # 2. Parse Markdown Tables into Clean Bullet Cards
    lines = text.splitlines()
    formatted_lines = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        # Table Header or Separator (e.g. | :--- | :--- |)
        if stripped.startswith('|') and stripped.endswith('|'):
            if '---' in stripped:
                continue # Skip table divider lines
            
            # Parse table cells
            cells = [c.strip() for c in stripped.strip('|').split('|') if c.strip()]
            if not cells:
                continue

            if not in_table:
                in_table = True
                formatted_lines.append("")

            # Format table row as a clean bullet
            if len(cells) >= 2:
                formatted_lines.append(f"• <b>{cells[0]}</b>: { ' — '.join(cells[1:]) }")
            else:
                formatted_lines.append(f"• {cells[0]}")
        else:
            in_table = False
            # Headers
            if stripped.startswith('### '):
                formatted_lines.append(f"\n🏛️ <b>{stripped[4:]}</b>")
            elif stripped.startswith('#### '):
                formatted_lines.append(f"\n📌 <b>{stripped[5:]}</b>")
            elif stripped.startswith('## '):
                formatted_lines.append(f"\n🏢 <b>{stripped[3:]}</b>")
            elif stripped.startswith('# '):
                formatted_lines.append(f"\n👑 <b>{stripped[2:]}</b>")
            else:
                formatted_lines.append(line)

    text = "\n".join(formatted_lines)

    # 3. Convert **bold** -> <b>bold</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # 4. Convert *italic* or _italic_ -> <i>italic</i>
    text = re.sub(r'(?<!\w)\*(.*?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(.*?)_(?!\w)', r'<i>\1</i>', text)

    # 5. Convert `code` -> <code>code</code>
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # Clean double blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


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

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
        """Send formatted message to a Telegram chat, splitting if >4000 chars."""
        if not self.bot_token:
            return False

        formatted_text = format_text_for_telegram_html(text) if parse_mode == "HTML" else text
        
        # Split message into chunks if exceeding Telegram limit of 4096 chars
        MAX_LEN = 3800
        chunks = [formatted_text[i:i+MAX_LEN] for i in range(0, len(formatted_text), MAX_LEN)] if len(formatted_text) > MAX_LEN else [formatted_text]

        url = f"{TELEGRAM_API_URL}{self.bot_token}/sendMessage"
        
        async with httpx.AsyncClient(timeout=12.0) as client:
            for chunk in chunks:
                payload = {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode
                }
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code != 200:
                        # Fallback to plain text if HTML parsing has unclosed tags
                        payload.pop("parse_mode", None)
                        payload["text"] = re.sub(r'<[^>]*>', '', chunk)
                        await client.post(url, json=payload)
                except Exception as e:
                    logger.error(f"Failed to send Telegram message chunk: {e}")
                    return False
        return True

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

        logger.info(f"📩 Telegram Message from Chat {chat_id}: '{text}'")

        # 1. Handle Command: /start or /help
        if text.startswith("/start") or text.startswith("/help"):
            welcome = (
                "🏛️ <b>NEXA PRIME Enterprise — AI Telegram Asistanı</b>\n\n"
                "Ben <b>NEXA PRIME Bilişsel Gayrimenkul Asistanıyım</b>. "
                "Portföyünüzdeki 20 projeyi, resmi tapu/kadastro kayıtlarını, kat planlarını ve fiyat verilerini anlık analiz ederim.\n\n"
                "📌 <b>Kullanabileceğiniz Komutlar:</b>\n"
                "• <code>/projeler</code> — Tüm lüks portföy projelerini listeler\n"
                "• <code>/proje ID</code> — Belirtilen projenin detaylarını getirir (Örn: <code>/proje 13</code>)\n"
                "• <code>/rapor ID</code> — Projenin AI Intelligence Raporunu üretir (Örn: <code>/rapor 13</code>)\n\n"
                "💬 <b>Veya doğrudan sorunuzu yazın:</b>\n"
                "<i>'VIP AKADEMİ projesinin fiyatı ve teslim tarihi nedir?'</i>"
            )
            await self.send_message(chat_id, welcome)
            return

        # 2. Handle Command: /projeler or /projects
        if text.startswith("/projeler") or text.startswith("/projects"):
            async with db.execute("SELECT id, name, location, ilce, il, ada_no, parsel_no FROM projects ORDER BY id ASC") as cursor:
                rows = await cursor.fetchall()
            
            lines = ["📋 <b>NEXA PRIME PORTFÖY LİSTESİ (20 Proje)</b>\n"]
            for r in rows:
                ada_p = f" (Ada: {r['ada_no']}/{r['parsel_no']})" if r['ada_no'] else ""
                lines.append(f"• <b>#{r['id']} {r['name']}</b>{ada_p}\n  📍 {r['location'] or r['ilce']}\n  🔍 Detay: <code>/proje {r['id']}</code> | Rapor: <code>/rapor {r['id']}</code>\n")
            
            lines.append("💬 <i>Sorularınızı doğrudan mesaj olarak yazabilirsiniz!</i>")
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
                        f"🏛️ <b>PROJE #{p_dict['id']} — {p_dict['name']}</b>\n\n"
                        f"📍 <b>Konum:</b> {p_dict['location'] or p_dict['ilce']}\n"
                        f"🗺️ <b>İl/İlçe:</b> {p_dict['ilce']}, {p_dict['il']}\n"
                        f"📜 <b>Tapu / Kadastro:</b> {ada_p} ({'✅ TKGM Onaylı' if p_dict['tkgm_verified'] else 'Prestij Portföy'})\n\n"
                        f"📝 <b>Açıklama:</b> {p_dict['description'] or 'Lüks konut ve yatırım projesi.'}\n\n"
                        f"🤖 <b>Derin AI Raporu için:</b> <code>/rapor {p_dict['id']}</code>"
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
                await self.send_message(chat_id, f"🧠 <i>Proje #{p_id} için AI Intelligence Raporu taranıyor, lütfen bekleyin...</i>")
                try:
                    report = await generate_project_intelligence_report(db, p_id)
                    await self.send_message(chat_id, report)
                except Exception as e:
                    await self.send_message(chat_id, f"❌ Rapor oluşturma hatası: {e}")
                return

        # 5. Natural Language AI Inquiry via RAG Search
        await self.send_message(chat_id, "🤖 <i>NEXA AI Hafızası Taranıyor...</i>")
        try:
            rag_response = await generate_cognitive_response(db, text)
            await self.send_message(chat_id, f"🏛️ <b>NEXA PRIME AI Yanıtı:</b>\n\n{rag_response}")
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
