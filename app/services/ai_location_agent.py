import json
import logging
import re
from typing import Optional, Dict
from app.services.gemini_service import generate_content_with_fallback

logger = logging.getLogger("nexa.ai_location_agent")

async def research_project_location_with_ai(
    name: str,
    description: Optional[str] = None,
    location_hint: Optional[str] = None,
    il: Optional[str] = None,
    ilce: Optional[str] = None,
    mahalle: Optional[str] = None
) -> Optional[Dict]:
    """
    AI Fallback Location Research Agent:
    Uses Gemini LLM to analyze project metadata (name, description, address hints)
    and infer precise neighborhood/district search query or estimated coordinates in Turkey.
    """
    prompt = f"""
Sen bir Türk gayrimenkul ve coğrafi konum uzmanı AI Agent'ısın.
Aşağıda bilgileri verilen gayrimenkul projesinin konumunu (mahalle, ilçe, il veya simge yapı) analiz et ve Türkiye haritasındaki en yakın yerini belirle.

Proje Adı: {name}
Mevcut Konum Bilgisi: {location_hint or 'Belirtilmemiş'}
İl: {il or 'Belirtilmemiş'}
İlçe: {ilce or 'Belirtilmemiş'}
Mahalle: {mahalle or 'Belirtilmemiş'}
Açıklama / Metin:
{description or 'Açıklama bulunmuyor.'}

Görev:
Proje adından (örn. 'VIP ÜNİVERSİTE', 'GRANDE YAŞAMKENT', 'WM PRIME'), açıklamadaki ipuçlarından veya il/ilçe bilgisinden yola çıkarak OpenStreetMap Nominatim araması için en doğru Türkçe adresi çıkar.

Çıktıyı YALNIZCA geçerli bir JSON nesnesi olarak döndür:
{{
  "search_query": "mahalle veya ilçe veya belirgin konum adresi (örn. Yaşamkent Mahallesi, Çankaya, Ankara)",
  "confidence": "high/medium/low",
  "reasoning": "kısa açıklama"
}}
"""
    try:
        response_text = generate_content_with_fallback("gemini-3.5-flash", prompt)
        if not response_text:
            return None

        # Clean JSON markdown if wrapped in ```json ... ```
        cleaned = re.sub(r'```json\s*|\s*```', '', response_text).strip()
        data = json.loads(cleaned)
        
        search_query = data.get("search_query")
        if search_query:
            logger.info(f"🤖 AI Location Agent inferred location query: '{search_query}' (Confidence: {data.get('confidence')})")
            return {
                "search_query": search_query,
                "confidence": data.get("confidence", "medium"),
                "reasoning": data.get("reasoning", ""),
                "source": "AI Location Research Agent"
            }
    except Exception as e:
        logger.warning(f"AI Location Research Agent failed: {e}")

    return None
