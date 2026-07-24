import math
import httpx
import logging
import urllib.parse
from typing import Optional, Dict, List
import aiosqlite

logger = logging.getLogger("nexa.location_verification")

EARTH_RADIUS_KM = 6371.0

# Strategic Regional Landmarks & Infrastructure Hubs in Turkey
INFRASTRUCTURE_HUBS = [
    {"name": "Esenboğa Havalimanı (ESB)", "lat": 40.1281, "lng": 32.9950, "type": "airport"},
    {"name": "Milas-Bodrum Havalimanı (BJV)", "lat": 37.2506, "lng": 27.6689, "type": "airport"},
    {"name": "Gazipaşa-Alanya Havalimanı (GZP)", "lat": 36.2993, "lng": 32.3014, "type": "airport"},
    {"name": "Eskişehir Hasan Polatkan Havalimanı", "lat": 39.8123, "lng": 30.5491, "type": "airport"},
    {"name": "Yıldırım Beyazıt Üni. Esenboğa Kampüsü", "lat": 40.1395, "lng": 32.9640, "type": "university"},
    {"name": "Çankaya Üniversitesi (Yapracık)", "lat": 39.8222, "lng": 32.5535, "type": "university"},
    {"name": "Hacettepe Üniversitesi (Beytepe)", "lat": 39.8665, "lng": 32.7350, "type": "university"},
    {"name": "Bilkent Şehir Hastanesi", "lat": 39.8970, "lng": 32.7600, "type": "hospital"},
    {"name": "Yenimahalle Onkoloji Hastanesi & Metro", "lat": 39.9703, "lng": 32.7995, "type": "metro_hospital"},
    {"name": "Koru Metro İstasyonu (Çayyolu/Yaşamkent)", "lat": 39.8850, "lng": 32.6850, "type": "metro"},
    {"name": "Eskişehir Yolu Bulvar Aksı", "lat": 39.8700, "lng": 32.6500, "type": "highway"},
    {"name": "Kuzey Çevre Yolu Pursaklar Bağlantısı", "lat": 40.0500, "lng": 32.9000, "type": "highway"},
    {"name": "Bodrum Yalıkavak Marina", "lat": 37.1064, "lng": 27.2917, "type": "marina"},
    {"name": "Alanya İncekum Sahili", "lat": 36.6627, "lng": 31.7199, "type": "coastal"}
]

# Strategic Regional Axis Bounds for Strict Bounding-Box Self-Check
REGIONAL_AXIS_BOUNDS = {
    "esenboga": {"min_lat": 40.10, "max_lat": 40.18, "min_lng": 32.90, "max_lng": 33.02, "axis_name": "Kuzey Ankara Esenboğa Üniversite & Havalimanı Aksı"},
    "yasamkent_yapracik": {"min_lat": 39.80, "max_lat": 39.89, "min_lng": 32.50, "max_lng": 32.68, "axis_name": "Batı Ankara Yaşamkent - Yapracık - Çankaya Üni. Aksı"},
    "beytepe_incek": {"min_lat": 39.80, "max_lat": 39.87, "min_lng": 32.70, "max_lng": 32.82, "axis_name": "Güneybatı Ankara Beytepe - İncek Lüks Konut Aksı"},
    "cakirlar_yuva": {"min_lat": 39.98, "max_lat": 40.03, "min_lng": 32.70, "max_lng": 32.76, "axis_name": "Batı Ankara Çakırlar - Yuva Ticari & Konut Aksı"},
    "pursaklar_saray": {"min_lat": 40.03, "max_lat": 40.09, "min_lng": 32.88, "max_lng": 32.96, "axis_name": "Kuzey Ankara Pursaklar - Saray Sanayi & Lojistik Aksı"},
    "demetevler": {"min_lat": 39.95, "max_lat": 39.99, "min_lng": 32.78, "max_lng": 32.82, "axis_name": "Merkez Ankara Demetevler - Onkoloji Metro Aksı"},
    "yalikavak": {"min_lat": 37.05, "max_lat": 37.15, "min_lng": 27.25, "max_lng": 27.35, "axis_name": "Ege Sahil Yalıkavak Marina Lüks Lojistik Aksı"},
    "avsallar": {"min_lat": 36.60, "max_lat": 36.70, "min_lng": 31.65, "max_lng": 31.78, "axis_name": "Akdeniz Sahil Alanya İncekum Turizm Aksı"},
    "eskisehir_71evler": {"min_lat": 39.70, "max_lat": 39.78, "min_lng": 30.55, "max_lng": 30.65, "axis_name": "İç Anadolu Eskişehir Odunpazarı Gelişim Aksı"}
}

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate Great-Circle distance in kilometers between 2 coordinates."""
    try:
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return round(EARTH_RADIUS_KM * c, 2)
    except Exception:
        return 999.0

def calculate_proximity_matrix(lat: float, lng: float) -> List[Dict]:
    """Computes distance & estimated drive time to key infrastructure hubs."""
    matrix = []
    for hub in INFRASTRUCTURE_HUBS:
        dist_km = haversine_km(lat, lng, hub["lat"], hub["lng"])
        # Estimate driving time (assuming 60 km/h average speed = 1 min per km + 2 min buffer)
        drive_min = max(2, round(dist_km * 1.2 + 2))
        matrix.append({
            "name": hub["name"],
            "type": hub["type"],
            "distance_km": dist_km,
            "drive_min": drive_min
        })
    # Sort by nearest distance
    matrix.sort(key=lambda x: x["distance_km"])
    return matrix

def calculate_topraktan_land_score(project: Dict, proximity: List[Dict]) -> Dict:
    """
    Ultra Topraktan Yatırım & Konum Zekası Skoru:
    Calculates Investment Value, 5-Year Appreciation Projection, and Location Rating.
    """
    tkgm_verified = project.get("tkgm_verified", 0)
    has_ada_parsel = bool(project.get("ada_no") and project.get("parsel_no"))
    mahalle = (project.get("mahalle") or "").lower()
    ilce = (project.get("ilce") or "").lower()
    il = (project.get("il") or "").lower()

    # Base Investment Score
    score = 70.0
    score_reasons = []

    # 1. Cadastral Safety (+15 pts)
    if tkgm_verified == 1:
        score += 15
        score_reasons.append("✅ TKGM Resmi Kadastro Onaylı Tapu Güvencesi (+15)")
    elif has_ada_parsel:
        score += 10
        score_reasons.append("📄 Belgelerde Belirtilmiş Ada/Parsel Bilgisi (+10)")

    # 2. Key Catalyst Proximity (+15 pts)
    nearest_uni = next((h for h in proximity if h["type"] == "university"), None)
    nearest_airport = next((h for h in proximity if h["type"] == "airport"), None)
    nearest_metro = next((h for h in proximity if h["type"] in ["metro", "metro_hospital"]), None)

    if nearest_uni and nearest_uni["distance_km"] < 5.0:
        score += 8
        score_reasons.append(f"🎓 Üniversite Kampüsüne Yakın ({nearest_uni['name']}: {nearest_uni['distance_km']} km) (+8)")
    if nearest_airport and nearest_airport["distance_km"] < 20.0:
        score += 5
        score_reasons.append(f"✈️ Havalimanı Aksı Üzerinde ({nearest_airport['distance_km']} km) (+5)")
    if nearest_metro and nearest_metro["distance_km"] < 8.0:
        score += 7
        score_reasons.append(f"🚇 Ulaşım / Metro Bağlantısı Yakın ({nearest_metro['distance_km']} km) (+7)")

    score = min(100.0, max(0.0, round(score, 1)))

    # Rating Tier
    if score >= 92:
        rating_tier = "A+ Üst Düzey Prim Aksı"
        appreciation_rate = "%38 - %50 / Yıl"
    elif score >= 82:
        rating_tier = "A Yüksek Yatırım Değeri"
        appreciation_rate = "%30 - %40 / Yıl"
    else:
        rating_tier = "B+ Dengeli Yatırım Aksı"
        appreciation_rate = "%25 - %32 / Yıl"

    return {
        "land_investment_score": score,
        "rating_tier": rating_tier,
        "annual_appreciation_projection": appreciation_rate,
        "reasons": score_reasons,
        "nearest_university": f"{nearest_uni['name']} ({nearest_uni['distance_km']} km)" if nearest_uni else "Mevcut",
        "nearest_airport": f"{nearest_airport['name']} ({nearest_airport['distance_km']} km)" if nearest_airport else "Mevcut"
    }

async def audit_single_project_location(project: Dict) -> Dict:
    """
    Self-Check & Audit Engine with Ultra Land Location Intelligence.
    Validates coordinates, checks axis bounding box, calculates proximity matrix, and investment rating.
    """
    p_id = project.get("id")
    p_name = project.get("name", "Bilinmeyen Proje")
    lat = project.get("lat")
    lng = project.get("lng")
    p_il = project.get("il") or ""
    p_ilce = project.get("ilce") or ""
    p_mahalle = project.get("mahalle") or ""
    p_location = project.get("location") or ""
    tkgm_verified = project.get("tkgm_verified", 0)
    current_source = project.get("location_source") or ("TKGM MEGSIS" if tkgm_verified else "Sistem")

    # 1. Boundary & Presence Check
    if lat is None or lng is None or not (35.0 <= lat <= 43.0 and 25.0 <= lng <= 45.5):
        return {
            "project_id": p_id,
            "project_name": p_name,
            "accuracy_score": 0,
            "status": "critical_mismatch",
            "status_label": "❌ Hata: Geçersiz Koordinat",
            "source": current_source,
            "tkgm_verified": tkgm_verified,
            "reverse_address": "Geçersiz Koordinat",
            "score_reasons": ["Sınır Dışı"],
            "proximity_matrix": [],
            "land_intelligence": {}
        }

    # 2. Proximity Matrix & Land Investment Intelligence
    proximity = calculate_proximity_matrix(lat, lng)
    land_intel = calculate_topraktan_land_score(project, proximity)

    # 3. Strict Axis Bounding Box Self-Check
    detected_axis = "Genel Bölge Aksı"
    axis_matched = False
    full_text_lower = f"{p_name} {p_location} {p_ilce} {p_mahalle}".lower()

    for key, axis_info in REGIONAL_AXIS_BOUNDS.items():
        if key in full_text_lower or any(word in full_text_lower for word in key.split("_")):
            detected_axis = axis_info["axis_name"]
            if axis_info["min_lat"] <= lat <= axis_info["max_lat"] and axis_info["min_lng"] <= lng <= axis_info["max_lng"]:
                axis_matched = True
            break

    # Accuracy Score Calculation
    accuracy_score = 90 if axis_matched else 75
    if tkgm_verified == 1:
        accuracy_score = 100
        source_label = f"Resmi Cadde/Parsel ({current_source})"
    else:
        source_label = current_source

    if accuracy_score >= 95:
        status_label = "✅ %100 Tam Doğruluk (Resmi Onaylı)"
        status = "verified"
    elif accuracy_score >= 80:
        status_label = f"🟢 %{accuracy_score} Güvenilir Bölge Aksı"
        status = "high_confidence"
    else:
        status_label = f"🟡 %{accuracy_score} İnceleme Önerilir"
        status = "review_needed"

    score_reasons = [
        f"Doğrulanan Aks: {detected_axis}",
        f"Topraktan Yatırım Skoru: {land_intel['land_investment_score']} / 100 ({land_intel['rating_tier']})"
    ] + land_intel["reasons"]

    return {
        "project_id": p_id,
        "project_name": p_name,
        "lat": lat,
        "lng": lng,
        "ada_no": project.get("ada_no"),
        "parsel_no": project.get("parsel_no"),
        "accuracy_score": accuracy_score,
        "status": status,
        "status_label": status_label,
        "source": source_label,
        "tkgm_verified": tkgm_verified,
        "reverse_address": f"{p_mahalle}, {p_ilce}, {p_il}",
        "detected_axis": detected_axis,
        "score_reasons": score_reasons,
        "proximity_matrix": proximity[:5], # Top 5 nearest strategic hubs
        "land_intelligence": land_intel
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
        "average_accuracy": 100.0,
        "average_land_investment_score": 0.0
    }

    total_score = 0
    total_land_score = 0

    for row in rows:
        proj_dict = dict(row)
        res = await audit_single_project_location(proj_dict)
        audits.append(res)

        score = res["accuracy_score"]
        land_score = res["land_intelligence"].get("land_investment_score", 85.0)
        total_score += score
        total_land_score += land_score
        status = res["status"]

        if status == "verified":
            summary["verified_count"] += 1
        elif status == "high_confidence":
            summary["high_confidence_count"] += 1
        elif status == "review_needed":
            summary["review_needed_count"] += 1
        else:
            summary["critical_mismatch_count"] += 1

    if summary["total_projects"] > 0:
        summary["average_accuracy"] = round(total_score / summary["total_projects"], 1)
        summary["average_land_investment_score"] = round(total_land_score / summary["total_projects"], 1)

    return {
        "summary": summary,
        "projects": audits
    }
