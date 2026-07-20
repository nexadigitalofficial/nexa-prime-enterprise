import logging
import httpx
from google import genai
from app.core.config import settings

logger = logging.getLogger("nexa.gemini")

FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash"
]

def generate_content_with_fallback(model_name: str, contents: str) -> str:
    """
    Robust Multi-Model & Multi-Key Fallback Engine:
    1. Iterates over all configured Gemini API keys.
    2. For each key, tries requested model + alternative Gemini models (to bypass model-specific Free Tier quota limits).
    3. Fallback to Local Ollama AI if cloud quotas are completely exhausted.
    """
    keys = settings.api_keys_list
    if not keys:
        logger.warning("No Gemini API keys found in settings. Attempting local Ollama fallback...")
        ollama_reply = _try_ollama_fallback(contents)
        if ollama_reply:
            return ollama_reply
        raise Exception("Sistemde yapılandırılmış Gemini API anahtarı veya çalışan yerel AI bulunamadı.")

    # Deduplicate and clean model list starting with requested model
    target_models = [model_name] + [m for m in FALLBACK_MODELS if m != model_name]

    for key in keys:
        if not key or "YENI_API_KEY" in key or len(key) < 10:
            continue
            
        try:
            client = genai.Client(api_key=key)
            for m in target_models:
                try:
                    logger.info(f"🔑 Trying Gemini Model '{m}' with API Key {key[:8]}...")
                    response = client.models.generate_content(
                        model=m,
                        contents=contents
                    )
                    if response and response.text:
                        return response.text
                except Exception as model_err:
                    logger.warning(f"Model '{m}' failed with Key {key[:8]}... ({model_err}). Trying next model/key.")
                    continue
        except Exception as key_err:
            logger.warning(f"Key {key[:8]} failed client init: {key_err}. Moving to next key.")
            continue

    # Attempt Local Ollama Fallback if all Cloud Keys & Models fail
    logger.warning("⚠️ All Gemini API keys/models exhausted. Attempting Local Ollama fallback...")
    ollama_reply = _try_ollama_fallback(contents)
    if ollama_reply:
        return ollama_reply

    raise Exception("Tüm Gemini API anahtarları ve alternatif modeller kota limitine ulaştı. Lütfen birkaç dakika sonra tekrar deneyiniz.")

def _try_ollama_fallback(prompt: str) -> str:
    """Attempt synchronous call to local Ollama instance if available"""
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "llama3",
            "prompt": prompt,
            "stream": False
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("response")
                if reply:
                    logger.info("✅ Responded via Local Ollama Fallback AI.")
                    return reply
    except Exception as e:
        logger.warning(f"Local Ollama Fallback unavailable: {e}")
    return None
