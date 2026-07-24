import json
import logging
import re
from typing import Optional, Dict
from app.services.gemini_service import generate_content_with_fallback

logger = logging.getLogger("nexa.ai_location_agent")

ADA_PARSEL_PATTERNS = [
    r'(\d{4,6})\s*ADA\s*(\d{1,4})\s*(?:VE\s*\d+\s*)?(?:SAYILI\s*)?PARSEL',
    r'(\d{4,6})\s*ADA\s*,\s*(\d{1,4})\s*PARSEL',
    r'ADA\s*:\s*(\d{4,6})\s*PARSEL\s*:\s*(\d{1,4})',
    r'(\d{4,6})\s*/\s*(\d{1,4})'
]

def extract_ada_parsel_from_text(text: str) -> Optional[Dict]:
    """
    Scans document text, file names, contract titles, and text snippets 
    for Ada/Parsel cadastral metadata (e.g. 190473 Ada 8 Parsel, 62879/2).
    """
    if not text:
        return None
        
    for pattern in ADA_PARSEL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            ada = match.group(1)
            parsel = match.group(2)
            logger.info(f"📄 Extracted Cadastral Data from Document Text: Ada {ada}, Parsel {parsel}")
            return {
                "ada": ada,
                "parsel": parsel,
                "source": "Document Ada/Parsel OCR & Pattern Matching"
            }
            
    return None

async def research_project_location_with_ai(
    name: str,
    description: Optional[str] = None,
    location_hint: Optional[str] = None,
    il: Optional[str] = None,
    ilce: Optional[str] = None,
    mahalle: Optional[str] = None
) -> Optional[Dict]:
    """
    AI Location Research Agent:
    1. First scans description & location_hint for Ada/Parsel patterns.
    2. Uses Gemini LLM to infer precise neighborhood/district search query or estimated coordinates in Turkey.
    """
    # 1. Document / Description Cadastral Scan
    combined_text = f"{name} {location_hint or ''} {description or ''}"
    cadastral_found = extract_ada_parsel_from_text(combined_text)
    if cadastral_found:
        return {
            "search_query": f"{ilce or ''} {mahalle or ''} {cadastral_found['ada']} Ada {cadastral_found['parsel']} Parsel {il or 'Ankara'}".strip(),
            "ada": cadastral_found["ada"],
            "parsel": cadastral_found["parsel"],
            "confidence": "high",
            "reasoning": "Resmi belgeden Ada/Parsel verisi çıkarıldı",
            "source": cadastral_found["source"]
        }

    # 2. Gemini LLM Inference
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
Proje adından (örn. 'VIP ÜNİVERSİTE', 'GRANDE YAŞAMKENT', 'START BRAVO IDEA'), açıklamadaki ipuçlarından veya il/ilçe bilgisinden yola çıkarak OpenStreetMap veya TKGM araması için en doğru Türkçe adresi çıkar.

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
