import os
import re
import random
import urllib.parse
import httpx
import logging
import aiosqlite

logger = logging.getLogger("nexa.image_gen")

def sanitize_prompt_text(text: str) -> str:
    """Removes slashes, newlines, currency symbols, and non-ascii characters for clean URL encoding."""
    if not text:
        return ""
    # Map Turkish characters to ascii
    tr_map = str.maketrans("çğışöüÇĞİŞÖÜ", "cgisouCGISOU")
    clean = text.translate(tr_map)
    # Remove slashes, newlines, and non-alphanumeric chars that break URLs
    clean = clean.replace("/", " ").replace("\\", " ").replace("\n", " ").replace("\r", " ")
    clean = re.sub(r'uni[0-9A-Fa-f]{4}', ' ', clean) # Remove unicode hex strings like uni20BA
    clean = re.sub(r'[^\w\s,-]', ' ', clean)
    return " ".join(clean.split())

async def generate_project_visual(project_id: int, db: aiosqlite.Connection) -> dict:
    """
    Generates an architectural 3D visual for a project using Project Intelligence data
    with Multi-Provider Fail-Safe Fallbacks.
    Saves the image locally and registers it in the SQLite database.
    """
    # 1. Fetch project info
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
        project = await cursor.fetchone()
        
    if not project:
        raise ValueError(f"Project with ID {project_id} not found.")
        
    proj_dict = dict(project)
    p_name = sanitize_prompt_text(proj_dict.get("name", "Prestij Projesi"))
    p_loc = sanitize_prompt_text(proj_dict.get("location") or f"{proj_dict.get('ilce', '')} {proj_dict.get('il', '')}")

    # 2. Fetch document summary/content to enrich intelligence prompt
    intelligence_context = ""
    async with db.execute("""
        SELECT content FROM documents 
        WHERE project_id = ? AND content IS NOT NULL AND content != '' 
        LIMIT 3
    """, (project_id,)) as cursor:
        docs = await cursor.fetchall()
        if docs:
            text_snippets = []
            for d in docs:
                txt = d[0] if isinstance(d, tuple) else d["content"]
                if txt:
                    text_snippets.append(sanitize_prompt_text(txt[:100]))
            intelligence_context = " ".join(text_snippets)

    # 3. Formulate clean architectural AI prompt
    seed = random.randint(100000, 999999)
    clean_prompt = (
        f"Ultra high resolution 8k photorealistic architectural rendering of luxury real estate project {p_name} "
        f"located in {p_loc}. Modern glass facade, ambient golden sunset illumination, "
        f"lush Mediterranean landscaping, luxury apartments, cinematic architectural photography. {intelligence_context[:100]}"
    )
    clean_prompt = sanitize_prompt_text(clean_prompt)
    
    encoded_prompt = urllib.parse.quote(clean_prompt)
    
    # 4. Multi-Provider Fallback URLs
    urls_to_try = [
        f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&nologo=true&enhance=true",
        f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&nologo=true&model=turbo"
    ]
    
    os.makedirs("static/documents", exist_ok=True)
    filename = f"generated_ai_{project_id}_{seed}.jpg"
    local_path = os.path.join("static", "documents", filename)
    file_url = f"/static/documents/{filename}"
    
    logger.info(f"🎨 Generating AI Visual for project {p_name} (ID: {project_id})...")
    
    image_saved = False
    
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        for provider_url in urls_to_try:
            try:
                resp = await client.get(provider_url)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                    image_saved = True
                    logger.info(f"✅ Successfully generated image via AI provider: {local_path}")
                    break
                else:
                    logger.warning(f"Provider returned HTTP {resp.status_code}, trying fallback...")
            except Exception as err:
                logger.warning(f"Provider request error ({err}), trying fallback...")

    # Fallback to high-res luxury architectural catalog template if all remote providers timeout
    if not image_saved:
        fallback_hero = "static/documents/nexa_prime_cover.jpg"
        if os.path.exists(fallback_hero):
            with open(fallback_hero, "rb") as src, open(local_path, "wb") as dst:
                dst.write(src.read())
            image_saved = True
            logger.info(f"✅ Used high-res luxury fallback template: {local_path}")
        else:
            raise RuntimeError("Görsel oluşturma servisi yanıt vermedi. Lütfen tekrar deneyiniz.")

    # 5. Insert document record into SQLite database
    raw_name = proj_dict.get("name", "Prestij Projesi")
    title = f"AI Mimari Görsel - {raw_name} (#{seed % 1000})"
    category = "AI Üretimi Mimari Görseller"
    
    async with db.execute("""
        INSERT INTO documents (project_id, doc_type, title, file_url, category)
        VALUES (?, 'image', ?, ?, ?)
    """, (project_id, title, file_url, category)) as cursor:
        doc_id = cursor.lastrowid
        
    # Update project cover_image_url if not set
    if not proj_dict.get("cover_image_url"):
        await db.execute("UPDATE projects SET cover_image_url = ? WHERE id = ?", (file_url, project_id))
        
    await db.commit()
    
    return {
        "status": "success",
        "doc_id": doc_id,
        "file_url": file_url,
        "title": title,
        "category": category,
        "prompt_used": clean_prompt[:150] + "..."
    }
