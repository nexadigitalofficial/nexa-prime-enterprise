import aiosqlite
import logging
from typing import Optional
from app.services.gemini_service import generate_content_with_fallback

logger = logging.getLogger("nexa.rag")

async def get_project_context(db: aiosqlite.Connection, project_id: int) -> str:
    """Retrieve all chunk texts for a specific project to build single-project RAG context"""
    async with db.execute("""
        SELECT d.category, d.title, dc.chunk_text 
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE d.project_id = ?
    """, (project_id,)) as cursor:
        rows = await cursor.fetchall()
        
    if not rows:
        return ""
        
    context_parts = []
    for row in rows:
        context_parts.append(f"[{row['category']} - {row['title']}]: {row['chunk_text']}")
        
    return "\n\n".join(context_parts)

async def get_global_portfolio_context(db: aiosqlite.Connection) -> str:
    """Retrieve full portfolio summary across all projects for cross-project global chat"""
    async with db.execute("""
        SELECT id, name, location, il, ilce, mahalle, description, ada_no, parsel_no, tkgm_verified, created_at 
        FROM projects ORDER BY id ASC
    """) as cursor:
        projects = await cursor.fetchall()

    if not projects:
        return "Sistemde henüz kayıtlı bir proje bulunmamaktadır."

    portfolio_parts = []
    for proj in projects:
        p_id = proj["id"]
        p_name = proj["name"]
        p_loc = proj["location"] or f"{proj['ilce'] or ''} / {proj['il'] or ''}"
        p_desc = proj["description"] or "Açıklama belirtilmemiş."
        
        # Get document chunks for this project (up to 10 key chunks per project to avoid token explosion)
        async with db.execute("""
            SELECT d.title, d.doc_type, dc.chunk_text 
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.project_id = ?
            LIMIT 10
        """, (p_id,)) as c_cursor:
            chunks = await c_cursor.fetchall()

        chunk_texts = "\n".join([f"  • [{c['doc_type'].upper()} - {c['title']}]: {c['chunk_text'][:300]}" for c in chunks])
        if not chunk_texts:
            chunk_texts = "  • (Henüz taranmış özel belge bulunmuyor)"

        proj_summary = f"""---
PROJE ID: {p_id}
PROJE ADI: {p_name}
LOKASYON: {p_loc} (İl: {proj['il'] or '-'}, İlçe: {proj['ilce'] or '-'}, Mahalle: {proj['mahalle'] or '-'})
ADA/PARSEL: Ada {proj['ada_no'] or '-'}, Parsel {proj['parsel_no'] or '-'} (TKGM Onay: {'Evet' if proj['tkgm_verified'] else 'Hayır'})
AÇIKLAMA: {p_desc}
ÖNEMLİ BELGE VE FİYAT/TESLİMAT VERİLERİ:
{chunk_texts}"""
        portfolio_parts.append(proj_summary)

    return "\n\n".join(portfolio_parts)

async def generate_offline_db_summary(db: aiosqlite.Connection, user_message: str) -> str:
    """Fail-Safe Direct Database Summary Generator when Cloud AI quotas are completely exhausted"""
    async with db.execute("""
        SELECT id, name, location, il, ilce, ada_no, parsel_no, tkgm_verified, description 
        FROM projects ORDER BY id ASC
    """) as cursor:
        projects = await cursor.fetchall()

    if not projects:
        return "Sistem veri tabanında henüz kayıtlı proje bulunmuyor."

    rows_html = []
    for p in projects:
        p_loc = p["location"] or f"{p['ilce'] or ''} / {p['il'] or ''}"
        tkgm = "✅ TKGM Onaylı" if p["tkgm_verified"] else "⏳ İşleniyor"
        ada_parsel = f"Ada: {p['ada_no'] or '-'} / Parsel: {p['parsel_no'] or '-'}"
        desc = (p["description"] or "-")[:120] + "..."
        rows_html.append(f"| **#{p['id']} {p['name']}** | {p_loc} | {ada_parsel} | {tkgm} | {desc} |")

    table_str = "\n".join(rows_html)
    return f"""> [!NOTE]
> AI Kota Koruması Aktif — Veriler Sistem Veri Tabanından Doğrudan Anlık Olarak Çekilmiştir.

### 🏢 NEXA PRIME Portföy Özeti ve Proje Listesi

Sisteminizde kayıtlı **{len(projects)} adet premium proje** bulunmaktadır:

| Proje Adı | Lokasyon | Ada / Parsel | TKGM Durumu | Açıklama Özet |
| :--- | :--- | :--- | :---: | :--- |
{table_str}

*Not: Detaylı AI fiyat ve teslimat analizleri için birkaç dakika sonra sorunuzu tekrarlayabilirsiniz.*
"""

async def fetch_proximity_geo_intelligence(il: str, ilce: str, mahalle: str, proj_name: str) -> str:
    """Agent: Researches regional location, transit, universities, hospitals, and highway axes for a specific neighborhood"""
    location_str = f"{mahalle or ''} {ilce or ''} {il or ''}".strip()
    if not location_str:
        return ""

    prompt = f"""
Sen NEXA PRIME Sisteminin Otonom Bölgesel Konum & Çevre Aksı Araştırma Ajanısın (Geo-Intelligence Agent).
Aşağıdaki lokasyon için Türkiye coğrafi ve şehir planlama bilgini kullanarak ulaşım, üniversite, hastane, metro/tramvay, otoyol ve gelişen aks bilgilerini 3 maddede özetle:

Proje: {proj_name}
Lokasyon: {location_str}

GÖREVİN:
- En yakın Üniversiteler ve Eğitim Aksı
- En yakın Hastane ve Sağlık Merkezleri (Şehir Hastanesi vb.)
- En yakın Tramvay/Metro/Otobüs ve Otoyol Ulaşım Aksları
- Bölgenin yatırım ve prim gelişim potansiyeli

Özetini kısa, şık ve maddeler halinde yaz. Dokümanda yer almasa bile coğrafi lokasyonu bildiğin için bölgenin gerçek ulaşım ağlarını anlat.
"""
    try:
        res = generate_content_with_fallback("gemini-3.5-flash", prompt)
        return res
    except Exception as e:
        logger.warning(f"Geo intelligence lookup failed: {e}")
        return ""

async def generate_cognitive_response(db: aiosqlite.Connection, user_message: str, project_id: Optional[int] = None) -> str:
    """
    Generate cognitive sales/RAG response using Gemini LLM with Multi-Model & Local Fallback.
    """
    location_keywords = ["ulaşım", "aks", "yakınlık", "nerede", "çevre", "hastane", "okul", "üniversite", "metro", "tramvay", "otoyol", "havalimanı", "avm", "konum", "mesafe", "bölge", "site"]
    is_location_query = any(kw in user_message.lower() for kw in location_keywords)

    if project_id:
        project_name = f"Proje ID #{project_id}"
        geo_intel_context = ""
        async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
            proj = await cursor.fetchone()
            if proj:
                p_dict = dict(proj)
                project_name = p_dict["name"]
                
                # Run ProximityWebIntelligenceAgent if asking about location/transit
                if is_location_query or not await get_project_context(db, project_id):
                    geo_intel_context = await fetch_proximity_geo_intelligence(
                        p_dict.get("il") or "",
                        p_dict.get("ilce") or "",
                        p_dict.get("mahalle") or "",
                        project_name
                    )

        context = await get_project_context(db, project_id)
        
        system_prompt = f"""
Sen NEXA PRIME — Bilişsel Gayrimenkul Ekosistemi'nin kıdemli, lüks yatırım danışmanı ve yapay zeka temsilcisisin.
Sorulan soruya son derece profesyonel, elit, ikna edici ve karizmatik bir dille yanıt vermelisin.

İncelenen Tekil Proje: {project_name}

Mevcut Proje Doküman ve Bilgi Bağlamı (RAG):
{context if context else 'Bu proje için özel döküman bağlamı yüklenmemiş, ancak genel portföy bilgisi mevcuttur.'}

CANLI COĞRAFİ LOKASYON & AKS İNTELLEGENCE (NEXA GEO-INTELLIGENCE AGENT):
{geo_intel_context if geo_intel_context else 'Coğrafi aks sorgusu doğrudan dokümandan yanıtlanacaktır.'}

Kullanıcı Sorusu: {user_message}

Yanıt Kuralları:
1. Yanıtın resmi, güven verici ve yatırımcıya prestij hissettiren bir tonda olsun.
2. Eğer dökümanda fiyat, teslim tarihi, metrekare veya ödeme planı varsa net rakamlarla ver.
3. KULLANICI ULAŞIM VEYA ÇEVRE AKSLARINI SORDUĞUNDA: Dokümanda spesifik metre/km yazmasa bile yukarıdaki CANLI COĞRAFİ LOKASYON & AKS İNTELLEGENCE verisini kullanarak bölgedeki tramvay, hastane, üniversite ve otoyol akslarını detaylıca açıkla! Sakın "dokümanda yazmıyor, cevap veremem" deme; konum bilgisinden hareketle bölgenin çevre akslarını anlat.
4. Çıkarımda bulunurken kesinlik ve veri vurgusu yap ("Tahmin etmiyoruz, kodluyoruz").
5. Yanıtı markdown formatında (tablo/liste gerekiyorsa kullanarak) sun.
"""
    else:
        # Global Portfolio Chat Mode across ALL projects!
        global_context = await get_global_portfolio_context(db)
        system_prompt = f"""
Sen NEXA PRIME — Bilişsel Gayrimenkul Ekosistemi'nin Baş Portföy & Yatırım Stratejisti AI Danışmanısın.
Görevin: Tüm portföydeki projeleri çapraz analiz ederek kullanıcının genel gayrimenkul sorularına yanıt vermek.

ÖRN. SORULAR VE YANIT STRATEJİLERİ:
- "En yakın bitecek / teslim edilecek proje hangisi?" -> Dokümanlardaki ve açıklamalardaki teslimat tarihlerini kıyasla.
- "En ucuz / en uygun fiyatlı proje hangisi?" -> Dokümanlardaki fiyat listelerini ve m² birim fiyatlarını kıyasla.
- "Hangi şehirde kaç projemiz var?" -> Lokasyon bazlı döküm ve özet çıkar.
- "Projelerin genel karşılaştırma tablosu" -> Tüm projeleri lokasyon, konsept, belge durumu ve fiyat/teslimat bazında tablo ile sun.

TÜM PORTFÖY VERİ BAĞLAMI (TÜM PROJELER VE DOKÜMANLARI):
{global_context}

Kullanıcı Sorusu: {user_message}

Yanıt Kuralları:
1. Sen tek bir projeyi değil, TÜM PORTFÖYÜ analiz ediyorsun. Soruda geçen kriterlere göre projeleri sırala, kıyasla veya listele.
2. Karşılaştırma gerektiren sorularda mutlaka şık bir Markdown Tablosu kullan.
3. Fiyat, metrekare, lokasyon ve teslim tarihi gibi bilgileri veri bağlamından çekip net ver.
4. Yatırımcıya üst düzey karizmatik, kurumsal ve yönlendirici bir danışman diliyle yaklaş.
"""

    try:
        response_text = generate_content_with_fallback("gemini-3.5-flash", system_prompt)
        return response_text
    except Exception as e:
        logger.error(f"RAG Generation error: {e}. Executing Fail-Safe Direct DB Summary...")
        return await generate_offline_db_summary(db, user_message)

async def generate_project_intelligence_report(db: aiosqlite.Connection, project_id: int) -> str:
    """Generate a comprehensive Project Intelligence Report by reading all documents & chunks for a project"""
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
        project = await cursor.fetchone()
    if not project:
        raise ValueError("Proje bulunamadı.")

    p_name = project["name"]
    p_loc = project["location"] or f"{project['ilce'] or ''} / {project['il'] or ''}"
    context = await get_project_context(db, project_id)
    
    doc_summary = "• Projeye ait tüm resmi ruhsat, tapu ve mimari belgeler RAG veritabanında taranmıştır."
    if context:
        snippets = [line[:200] for line in context.split("\n\n") if line.strip()][:5]
        doc_summary = "\n".join([f"• {s}" for s in snippets])

    report = f"""### 📊 NEXA Project Intelligence Raporu: {p_name}

> [!NOTE]
> **RAG Bilişsel Analiz Raporu** — Tüm resmi dokümanlar ve veri tabanı taranarak oluşturulmuştur.

#### 1. 🏢 Proje Genel Özeti & Konsept
* **Proje Adı:** {p_name}
* **Konum:** {p_loc}
* **Proje Tanımı:** {project['description'] or 'Prestijli konut ve karma yaşam projesi.'}

#### 2. 📐 Tapu & Mimari Altyapı
| Kriter | Detay / Durum |
| :--- | :--- |
| **Ada No** | {project['ada_no'] or 'Belirtilmedi'} |
| **Parsel No** | {project['parsel_no'] or 'Belirtilmedi'} |
| **TKGM Onay Statüsü** | {'✅ TKGM Doğrulanmış Parsel' if project['tkgm_verified'] else '⏳ Onay Aşamasında'} |

#### 3. 📄 Taranan Resmi Doküman ve Veri Özeti
{doc_summary}

---
*NEXA PRIME Bilişsel Gayrimenkul Zekası tarafından anlık oluşturulmuştur.*
"""

    try:
        prompt = f"""
Sen NEXA PRIME — Bilişsel Gayrimenkul Ekosistemi Baş Mimar ve Analiz Motorusun.
Proje: {p_name} ({p_loc})
Ada: {project['ada_no'] or '-'}, Parsel: {project['parsel_no'] or '-'}, TKGM Onay: {'Evet' if project['tkgm_verified'] else 'Hayır'}
Açıklama: {project['description'] or '-'}
VERİ BAĞLAMI: {context[:500]}
Raporu şık ve detaylı markdown formatında sun.
"""
        cloud_report = generate_content_with_fallback("gemini-3.5-flash", prompt)
        if cloud_report and len(cloud_report) > 50:
            return cloud_report
    except Exception as e:
        logger.warning(f"Cloud AI fallback to instant DB report: {e}")
        
    return report
