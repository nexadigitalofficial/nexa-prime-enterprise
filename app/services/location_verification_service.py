import math
import httpx
import logging
import urllib.parse
from typing import Optional, Dict, List
import aiosqlite

logger = logging.getLogger("nexa.location_verification")

# Earth radius in meters
EARTH_RADIUS_METERS = 6371000.0

def haversine_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great-circle distance between two points in meters using Haversine formula."""
    try:
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return EARTH_RADIUS_METERS * c
    except Exception as e:
        logger.error(f"Error calculating Haversine distance: {e}")
        return 999999.0

async def reverse_geocode_nominatim(lat: float, lng: float) -> Optional[Dict]:
    """Reverse geocode lat, lng to obtain official address components via OpenStreetMap Nominatim."""
    if lat is None or lng is None:
        return None
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json&accept-language=tr"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url, headers={"User-Agent": "NexaPrimeEnterpriseLocationSelfCheck/3.0"})
            if resp.status_code == 200:
                data = resp.json()
                address = data.get("address", {})
                return {
                    "display_name": data.get("display_name", ""),
                    "il": address.get("province") or address.get("state") or address.get("city") or "",
                    "ilce": address.get("town") or address.get("district") or address.get("county") or address.get("suburb") or "",
                    "mahalle": address.get("neighbourhood") or address.get("suburb") or address.get("village") or "",
                    "road": address.get("road") or address.get("pedestrian") or "",
                    "raw": data
                }
    except Exception as e:
        logger.warning(f"Reverse geocoding failed for ({lat}, {lng}): {e}")
    return None

def normalize_tr_text(text: Optional[str]) -> str:
    """Normalize Turkish characters and text for comparison."""
    if not text:
        return ""
    tr_map = str.maketrans("ÇĞİÖŞÜIçğiöşüı", "cgiosuicgiosui")
    clean = text.translate(tr_map).lower()
    return " ".join(clean.split())

async def audit_single_project_location(project: Dict) -> Dict:
    """
    Self-Check & Audit Engine for a single project location.
    Evaluates geographical boundaries, reverse geocoding, text alignment, and TKGM status.
    Returns audit diagnostic dictionary with accuracy score, status, and recommendations.
    """
    p_id = project.get("id")
    p_name = project.get("name", "Bilinmeyen Proje")
    lat = project.get("lat")
    lng = project.get("lng")
    p_il = normalize_tr_text(project.get("il"))
    p_ilce = normalize_tr_text(project.get("ilce"))
    p_mahalle = normalize_tr_text(project.get("mahalle"))
    p_location = normalize_tr_text(project.get("location"))
    tkgm_verified = project.get("tkgm_verified", 0)
    current_source = project.get("location_source") or ("TKGM MEGSIS" if tkgm_verified else "Sistem")

    # 1. Boundary & Presence Check (Turkey Geographic Bounds: 35.5 - 42.5 Lat, 25.5 - 45.0 Lng)
    if lat is None or lng is None or not (35.0 <= lat <= 43.0 and 25.0 <= lng <= 45.5):
        return {
            "project_id": p_id,
            "project_name": p_name,
            "accuracy_score": 0,
            "status": "critical_mismatch",
            "status_label": "❌ Kritik Hata / Sınır Dışı",
            "source": current_source,
            "tkgm_verified": tkgm_verified,
            "reverse_address": "Sınır Dışı / Geçersiz Koordinat",
            "details": "Koordinatlar Türkiye coğrafi sınırları dışında veya eksik.",
            "suggested_action": "AI Konum Düzeltme çalıştırılmalı veya haritada el ile işaretlenmeli."
        }

    # 2. Reverse Geocode Self-Verification
    rev = await reverse_geocode_nominatim(lat, lng)
    rev_display = rev.get("display_name", "") if rev else "Ters Geo-Kod Alma Başarısız"
    rev_il = normalize_tr_text(rev.get("il")) if rev else ""
    rev_ilce = normalize_tr_text(rev.get("ilce")) if rev else ""
    rev_mahalle = normalize_tr_text(rev.get("mahalle")) if rev else ""

    # Combine text targets
    full_target_text = f"{p_name} {p_location} {p_ilce} {p_il} {p_mahalle}"
    full_rev_text = normalize_tr_text(rev_display)

    # 3. Calculate Accuracy Score
    accuracy_score = 50 # Base score for valid coordinate in Turkey
    score_reasons = []

    # Check TKGM Verification
    if tkgm_verified == 1:
        accuracy_score = 100
        score_reasons.append("TKGM MEGSIS Resmi Ada/Parsel Teyidi (+50)")
    elif "manuel" in current_source.lower() or "iğne" in current_source.lower():
        accuracy_score = 98
        score_reasons.append("Kullanıcı Tarafından Haritada Hassas İşaretlenmiş (+48)")
    else:
        # Check City Match
        city_matched = False
        if p_il and (p_il in rev_il or rev_il in p_il or p_il in full_rev_text):
            accuracy_score += 15
            city_matched = True
            score_reasons.append("İl Bilgisi Eşleşti (+15)")

        # Check District / Neighborhood Match
        district_matched = False
        if p_ilce and (p_ilce in rev_ilce or rev_ilce in p_ilce or p_ilce in full_rev_text):
            accuracy_score += 20
            district_matched = True
            score_reasons.append("İlçe Bilgisi Eşleşti (+20)")

        # Check Neighborhood Match
        if p_mahalle and (p_mahalle in rev_mahalle or rev_mahalle in p_mahalle or p_mahalle in full_rev_text):
            accuracy_score += 15
            score_reasons.append("Mahalle Bilgisi Eşleşti (+15)")

        # Check Location string overlap
        if p_location:
            loc_words = [w for w in p_location.split() if len(w) > 3]
            matched_words = [w for w in loc_words if w in full_rev_text]
            if matched_words:
                accuracy_score += 10
                score_reasons.append(f"Konum Kelimeleri Eşleşti ({', '.join(matched_words[:3])}) (+10)")

        # Penalty if city clearly mismatches (e.g. Ankara vs Mugla)
        if p_il and rev_il and not city_matched:
            # Major city mismatch!
            accuracy_score = max(20, accuracy_score - 35)
            score_reasons.append("⚠️ UYARI: Hedef İl ile Haritadaki İl Uyuşmuyor (-35)")

    accuracy_score = min(100, max(0, accuracy_score))

    # Determine Status Classification
    if accuracy_score >= 95:
        status = "verified"
        status_label = "✅ %100 Yüksek Doğruluk"
    elif accuracy_score >= 75:
        status = "high_confidence"
        status_label = "🟢 %" + str(accuracy_score) + " Güvenilir Konum"
    elif accuracy_score >= 50:
        status = "review_needed"
        status_label = "🟡 %" + str(accuracy_score) + " İnceleme Önerilir"
    else:
        status = "critical_mismatch"
        status_label = "🔴 %" + str(accuracy_score) + " Konum Uyuşmazlığı"

    return {
        "project_id": p_id,
        "project_name": p_name,
        "lat": lat,
        "lng": lng,
        "accuracy_score": accuracy_score,
        "status": status,
        "status_label": status_label,
        "source": current_source,
        "tkgm_verified": tkgm_verified,
        "reverse_address": rev_display,
        "score_reasons": score_reasons,
        "last_audit": "Anlık Self-Check"
    }

async def audit_all_projects_in_db(db: aiosqlite.Connection) -> Dict:
    """Run full location self-check audit across all portfolio projects."""
    async with db.execute("SELECT * FROM projects ORDER BY id ASC") as cursor:
        rows = await cursor.fetchall()

    audits = []
    summary = {
        "total_projects": len(rows),
        "verified_count": 0,
        "high_confidence_count": 0,
        "review_needed_count": 0,
        "critical_mismatch_count": 0,
        "average_accuracy": 0
    }

    total_score = 0
    for row in rows:
        proj_dict = dict(row)
        res = await audit_single_project_location(proj_dict)
        audits.append(res)

        score = res["accuracy_score"]
        total_score += score
        status = res["status"]

        if status == "verified":
            summary["verified_count"] += 1
        elif status == "high_confidence":
            summary["high_confidence_count"] += 1
        elif status == "review_needed":
            summary["review_needed_count"] += 1
        else:
            summary["critical_mismatch_count"] += 1

        # Optionally persist score to DB if columns exist
        try:
            await db.execute("""
                UPDATE projects 
                SET location_accuracy_score = ?, location_status = ?, reverse_geocoded_address = ?
                WHERE id = ?
            """, (score, status, res["reverse_address"], proj_dict["id"]))
        except Exception:
            pass # Ignored if columns not created yet

    await db.commit()

    if summary["total_projects"] > 0:
        summary["average_accuracy"] = round(total_score / summary["total_projects"], 1)

    return {
        "summary": summary,
        "projects": audits
    }
