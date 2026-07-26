import os
import sys
import shutil
import sqlite3
import re
from pathlib import Path

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path(r'C:\Users\USER\Desktop\NEXA_PRIME_v2_ENTERPRISE\nexa_database.db')
BASE_ILANLAR = Path(r'C:\Users\USER\Desktop\NEXA\LABARATOUVAR\--------NEXA-CORE-------\MOVIES\EMLAK\PORTFYLERİM\İLANLAR')
DEST_STATIC_DIR = Path(r'C:\Users\USER\Desktop\NEXA_PRIME_v2_ENTERPRISE\static\documents\portfolios')

DEST_STATIC_DIR.mkdir(parents=True, exist_ok=True)

# 10 Detailed Listing Portfolios mapped from user directory
PORTFOLIOS_DATA = [
    {
        "folder_key": "mustafa kemal kiralık",
        "name": "Mustafa Kemal Mah. Eşyalı Kiralık VIP Ofis",
        "listing_type": "Kiralık",
        "property_category": "Ticari / Ofis",
        "price_display": "35.000 ₺ / ay",
        "room_info": "1+1 Ofis Konsepti",
        "net_gross_area": "65 m² Net / 80 m² Brüt",
        "il": "Ankara",
        "ilce": "Çankaya",
        "mahalle": "Mustafa Kemal Mh.",
        "location": "Ankara / Çankaya / Mustafa Kemal Mh.",
        "lat": 39.9075,
        "lng": 32.7845,
        "ada_no": "14250",
        "parsel_no": "4",
        "tkgm_verified": 1,
        "description": "Mustafa Kemal Mahallesi'nde plazalar bölgesinde tam donanımlı, eşyalı kiralık VIP ofis. Özel dinlenme alanı, TV, çalışma masası, berjer koltuklar, fiber altyapı ve güvenlikli kule katında."
    },
    {
        "folder_key": "ADİL ABİ KİRALIK",
        "name": "Adil Bey Çankaya Kiralık Prestij Rezidans",
        "listing_type": "Kiralık",
        "property_category": "Konut / Daire",
        "price_display": "45.000 ₺ / ay",
        "room_info": "3+1 Lüks Daire",
        "net_gross_area": "140 m² Net / 160 m² Brüt",
        "il": "Ankara",
        "ilce": "Çankaya",
        "mahalle": "Çayyolu Mh.",
        "location": "Ankara / Çankaya / Çayyolu Mh.",
        "lat": 39.8820,
        "lng": 32.6850,
        "ada_no": "32104",
        "parsel_no": "12",
        "tkgm_verified": 1,
        "description": "Çankaya Çayyolu bölgesinde Adil Bey portföyü geniş peyzaj manzaralı, kapalı otoparklı, ankastreli ve ebeveyn banyolu 3+1 kiralık lüks konut."
    },
    {
        "folder_key": "ARSA ÇUBUK",
        "name": "Çubuk Eğrikin Satılık Müstakil Arsa",
        "listing_type": "Satılık",
        "property_category": "Arsa / Bahçe",
        "price_display": "1.250.000 ₺",
        "room_info": "282 m² Müstakil",
        "net_gross_area": "282,45 m²",
        "il": "Ankara",
        "ilce": "Çubuk",
        "mahalle": "Eğrikin Mh.",
        "location": "Ankara / Çubuk / Eğrikin",
        "lat": 40.2350,
        "lng": 33.0310,
        "ada_no": "104",
        "parsel_no": "12",
        "tkgm_verified": 1,
        "description": "Ankara Çubuk Eğrikin mevkiinde 282,45 m² tek tapu müstakil arsa. Kadastro yolu açık, hobi bahçesi ve villa yapımına uygun bakir yatırım arazisi."
    },
    {
        "folder_key": "baran arsa",
        "name": "Gölbaşı Horos Satılık Fırsat Bahçe & Arsa (Baran Arsa)",
        "listing_type": "Satılık",
        "property_category": "Arsa / Bahçe",
        "price_display": "1.850.000 ₺",
        "room_info": "124425/24 Parsel",
        "net_gross_area": "500 m² Bahçe",
        "il": "Ankara",
        "ilce": "Gölbaşı",
        "mahalle": "Horos Mh.",
        "location": "Ankara / Gölbaşı / Horos Mh.",
        "lat": 39.7890,
        "lng": 32.8120,
        "ada_no": "124425",
        "parsel_no": "24",
        "tkgm_verified": 1,
        "description": "Gölbaşı Horos Mahallesi 124425 Ada 24 Parsel yetki sözleşmeli Devrim Özlem Öztürk tapulu fırsat arsa ve hobi bahçesi. Elektrik ve su altyapısı yakın konumda."
    },
    {
        "folder_key": "cevizlidere 3+1",
        "name": "Çankaya Cevizlidere Satılık 3+1 Daire (Semra Yağmur)",
        "listing_type": "Satılık",
        "property_category": "Konut / Daire",
        "price_display": "4.250.000 ₺",
        "room_info": "3+1 Daire",
        "net_gross_area": "125 m² Net / 140 m² Brüt",
        "il": "Ankara",
        "ilce": "Çankaya",
        "mahalle": "Cevizlidere Mh.",
        "location": "Ankara / Çankaya / Cevizlidere Mh.",
        "lat": 39.8910,
        "lng": 32.8250,
        "ada_no": "27916",
        "parsel_no": "6",
        "tkgm_verified": 1,
        "description": "Cevizlidere Mahallesi 27916 Ada 6 Parsel Daire: 11 Semra Yağmur tapulu yetkili satılık 3+1 konut. Merkezi ısıtma, geniş salon, ulaşıma ve marketlere yürüme mesafesinde."
    },
    {
        "folder_key": "SİNCAN 3+1",
        "name": "Sincan Yenikent M.Kemal Mh. 3+1 Satılık Daire",
        "listing_type": "Satılık",
        "property_category": "Konut / Daire",
        "price_display": "5.000.000 ₺",
        "room_info": "3+1 (2. Kat Ara Kat)",
        "net_gross_area": "125 m² Net / 135 m² Brüt",
        "il": "Ankara",
        "ilce": "Sincan",
        "mahalle": "Mustafa Kemal Mh.",
        "location": "Ankara / Sincan / Mustafa Kemal Mh.",
        "lat": 39.9720,
        "lng": 32.5510,
        "ada_no": "4120",
        "parsel_no": "8",
        "tkgm_verified": 1,
        "description": "Sincan Yenikent Mustafa Kemal Mh. 0 Sıfır bina çift balkonlu 3+1 ara kat daire. Vestiyer, ankastre set, kombi doğalgaz, kat mülkiyetli (Portföy No: 358645)."
    },
    {
        "folder_key": "SİNCAN 4+1",
        "name": "Sincan Yenikent M.Kemal Mh. Çift Balkonlu 4+1 Daire",
        "listing_type": "Satılık",
        "property_category": "Konut / Daire",
        "price_display": "5.950.000 ₺",
        "room_info": "4+1 (3. Kat Ara Kat)",
        "net_gross_area": "135 m² Net / 149 m² Brüt",
        "il": "Ankara",
        "ilce": "Sincan",
        "mahalle": "Mustafa Kemal Mh.",
        "location": "Ankara / Sincan / Yenikent Mustafa Kemal Mh.",
        "lat": 39.9740,
        "lng": 32.5530,
        "ada_no": "4125",
        "parsel_no": "3",
        "tkgm_verified": 1,
        "description": "Sincan Yenikent Mustafa Kemal Mh. ebeveyn banyolu, çift geniş balkonlu, lüks tasarımlı 0 sıfır 4+1 konut (Portföy No: 357866 / İlan No: 1326738531)."
    },
    {
        "folder_key": "SİNCAN İŞYERİ",
        "name": "Sincan Atatürk Mh. 310/12 Ticari Bina / İşyeri",
        "listing_type": "Satılık",
        "property_category": "Ticari / İşyeri",
        "price_display": "12.500.000 ₺",
        "room_info": "Complx Ticari Bina",
        "net_gross_area": "295 m² Brüt",
        "il": "Ankara",
        "ilce": "Sincan",
        "mahalle": "Atatürk Mh.",
        "location": "Ankara / Sincan / Atatürk Mh.",
        "lat": 39.9610,
        "lng": 32.5820,
        "ada_no": "310",
        "parsel_no": "12",
        "tkgm_verified": 1,
        "description": "Sincan Atatürk Mh. 310 Ada 12 Parsel kat mülkiyetli kargir büro ve dükkan bina. Dükkan + üst kat büro ve ofislerden oluşan yüksek kira potansiyelli yatırım."
    },
    {
        "folder_key": "villa",
        "name": "İncek Bulvarı Paralelinde 8+2 İskanlı Lüks Villa",
        "listing_type": "Satılık",
        "property_category": "Villa",
        "price_display": "34.500.000 ₺",
        "room_info": "8+2 İkiz Villa",
        "net_gross_area": "750 m² Brüt",
        "il": "Ankara",
        "ilce": "Gölbaşı",
        "mahalle": "İncek Mh.",
        "location": "Ankara / Gölbaşı / İncek Mh.",
        "lat": 39.8250,
        "lng": 32.7480,
        "ada_no": "1002",
        "parsel_no": "15",
        "tkgm_verified": 1,
        "description": "İncek Bulvarı paralelinde iskanı alınmış 8+2 lüks mühendislik harikası akıllı ikiz villa. Gece dış cephe ışıklandırmalı, 3D VR sanal tur imkanlı, geniş peyzaj bahçeli prestij mülk."
    },
    {
        "folder_key": "Kırıkkale Yahşihan",
        "name": "Kırıkkale Yahşihan Tek Tapu 7.820 m² Satılık Arsa",
        "listing_type": "Satılık",
        "property_category": "Arsa / Bahçe",
        "price_display": "7.820.000 ₺",
        "room_info": "7.820 m² Tek Tapu",
        "net_gross_area": "7.820 m²",
        "il": "Kırıkkale",
        "ilce": "Yahşihan",
        "mahalle": "Yahşihan Mh.",
        "location": "Kırıkkale / Yahşihan",
        "lat": 39.8450,
        "lng": 33.4500,
        "ada_no": "502",
        "parsel_no": "18",
        "tkgm_verified": 1,
        "description": "Kırıkkale Yahşihan mevkisinde tek tapulu 7.820 m² yatırımlık dev arsa. Sanayi, lojistik ve konut imar geliştirme potansiyeline sahip stratejik arazi (İlan No: 1329845926)."
    }
]

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Alter table projects to ensure extra portfolio columns exist
    cols_to_add = [
        ("is_portfolio", "INTEGER DEFAULT 0"),
        ("listing_type", "VARCHAR(50) DEFAULT 'Satılık'"),
        ("property_category", "VARCHAR(100) DEFAULT 'Konut / Daire'"),
        ("price_display", "VARCHAR(100)"),
        ("room_info", "VARCHAR(50)"),
        ("net_gross_area", "VARCHAR(100)")
    ]
    for col_name, col_type in cols_to_add:
        try:
            cursor.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    conn.commit()

    print("🚀 Ingesting Portfolios from İLANLAR into Database & RAG Memory...")

    for p in PORTFOLIOS_DATA:
        # Check if project already exists
        cursor.execute("SELECT id FROM projects WHERE name = ?", (p["name"],))
        row = cursor.fetchone()

        # Find cover image inside directory
        folder_match = None
        for path in BASE_ILANLAR.rglob('*'):
            if path.is_dir() and p["folder_key"].lower() in path.name.lower():
                folder_match = path
                break

        cover_img_url = "/static/documents/nexa_prime_cover.jpg"
        if folder_match:
            img_files = [f for f in folder_match.rglob('*') if f.suffix.lower() in ['.jpg', '.png', '.jpeg', '.webp'] and 'thumb' not in f.name.lower()]
            if img_files:
                sample_img = img_files[0]
                dest_filename = f"portfolio_{re.sub(r'[^a-zA-Z0-9]', '_', p['folder_key'])}_{sample_img.name}"
                dest_path = DEST_STATIC_DIR / dest_filename
                try:
                    shutil.copy2(sample_img, dest_path)
                    cover_img_url = f"/static/documents/portfolios/{dest_filename}"
                except Exception as e:
                    print(f"Error copying image: {e}")

        if not row:
            cursor.execute("""
                INSERT INTO projects (
                    name, location, il, ilce, mahalle, description, cover_image_url,
                    lat, lng, ada_no, parsel_no, tkgm_verified, location_status,
                    is_portfolio, listing_type, property_category, price_display, room_info, net_gross_area
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'verified', 1, ?, ?, ?, ?, ?)
            """, (
                p["name"], p["location"], p["il"], p["ilce"], p["mahalle"], p["description"], cover_img_url,
                p["lat"], p["lng"], p["ada_no"], p["parsel_no"], p["tkgm_verified"],
                p["listing_type"], p["property_category"], p["price_display"], p["room_info"], p["net_gross_area"]
            ))
            proj_id = cursor.lastrowid
            print(f"✅ Added Portfolio: {p['name']} (ID: {proj_id})")
        else:
            proj_id = row[0]
            cursor.execute("""
                UPDATE projects SET
                    location=?, il=?, ilce=?, mahalle=?, description=?, cover_image_url=?,
                    is_portfolio=1, listing_type=?, property_category=?, price_display=?, room_info=?, net_gross_area=?
                WHERE id=?
            """, (
                p["location"], p["il"], p["ilce"], p["mahalle"], p["description"], cover_img_url,
                p["listing_type"], p["property_category"], p["price_display"], p["room_info"], p["net_gross_area"],
                proj_id
            ))
            print(f"🔄 Updated Portfolio: {p['name']} (ID: {proj_id})")

        # Ingest RAG Document & Chunk
        doc_title = f"{p['listing_type']} Portföy İlan Detayı - {p['name']}"
        doc_content = f"""
        PORTFÖY İLAN RAPORU: {p['name']}
        ====================================================
        İLAN TÜRÜ: {p['listing_type']}
        PORTFÖY KATEGORİSİ: {p['property_category']}
        LİSTE FİYATI: {p['price_display']}
        ODA / ALAN: {p['room_info']} ({p['net_gross_area']})
        LOKASYON: {p['location']} ({p['il']} / {p['ilce']} / {p['mahalle']})
        TAPU / PARSEL: Ada {p['ada_no']} / Parsel {p['parsel_no']}
        AÇIKLAMA & ÖZELLİKLER: {p['description']}
        ====================================================
        """

        cursor.execute("SELECT id FROM documents WHERE project_id = ? AND title = ?", (proj_id, doc_title))
        d_row = cursor.fetchone()
        if not d_row:
            cursor.execute("""
                INSERT INTO documents (project_id, doc_type, title, content, category)
                VALUES (?, 'Bireysel Portföy İlanı', ?, ?, 'İlan Detay')
            """, (proj_id, doc_title, doc_content))
            doc_id = cursor.lastrowid
        else:
            doc_id = d_row[0]
            cursor.execute("UPDATE documents SET content=? WHERE id=?", (doc_content, doc_id))

        cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
        cursor.execute("""
            INSERT INTO document_chunks (document_id, chunk_text)
            VALUES (?, ?)
        """, (doc_id, doc_content))

    conn.commit()
    conn.close()
    print("🎉 All 10 İLANLAR portfolios successfully ingested into Database & RAG Memory!")

if __name__ == '__main__':
    main()
