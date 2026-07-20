import httpx
import logging
import urllib.parse
from typing import Optional, Dict

logger = logging.getLogger("nexa.coordinates")

# Extensive District & Neighborhood Micro-Coordinate Map for High-Precision Fallbacks
CITY_CENTROIDS = {
    # Ankara Districts & Neighborhoods
    "cankaya": {"lat": 39.8897, "lng": 32.8650},
    "beytepe": {"lat": 39.83949, "lng": 32.74007},
    "incek": {"lat": 39.81850, "lng": 32.79320},
    "ahlatlibel": {"lat": 39.8220, "lng": 32.7880},
    "etimesgut": {"lat": 39.9482, "lng": 32.6593},
    "yasamkent": {"lat": 39.85841, "lng": 32.64387},
    "yapracik": {"lat": 39.85074, "lng": 32.62163},
    "baglica": {"lat": 39.89000, "lng": 32.65000},
    "eryaman": {"lat": 39.99500, "lng": 32.63000},
    "yenimahalle": {"lat": 39.9703, "lng": 32.7995},
    "cakirlar": {"lat": 40.00380, "lng": 32.72807},
    "yuva": {"lat": 40.00380, "lng": 32.72807},
    "pursaklar": {"lat": 40.0384, "lng": 32.9031},
    "saray": {"lat": 40.06200, "lng": 32.92120},
    "cubuk": {"lat": 40.2386, "lng": 33.0322},
    "esenboga": {"lat": 40.14404, "lng": 32.96429},
    "golbasi": {"lat": 39.7950, "lng": 32.8050},
    "ankara": {"lat": 39.9334, "lng": 32.8597},
    
    # Other Major Cities & Luxury Coastal Hubs
    "bodrum": {"lat": 37.0344, "lng": 27.4305},
    "yalikavak": {"lat": 37.1064, "lng": 27.2917},
    "mugla": {"lat": 37.2153, "lng": 28.3636},
    "alanya": {"lat": 36.5438, "lng": 31.9998},
    "incekum": {"lat": 36.66271, "lng": 31.71990},
    "antalya": {"lat": 36.8969, "lng": 30.7133},
    "odunpazari": {"lat": 39.7562, "lng": 30.5284},
    "71 evler": {"lat": 39.74336, "lng": 30.60180},
    "eskisehir": {"lat": 39.7667, "lng": 30.5256},
    "istanbul": {"lat": 41.0082, "lng": 28.9784},
    "izmir": {"lat": 38.4237, "lng": 27.1428},
    "fethiye": {"lat": 36.6217, "lng": 29.1164},
    "mersin": {"lat": 36.8000, "lng": 34.6333},
    "bursa": {"lat": 40.1885, "lng": 29.0610}
}

DEFAULT_TURKEY_CENTER = {"lat": 39.9334, "lng": 32.8597}

async def get_tkgm_parsel_info(mahalle_id: int, ada: str, parsel: str) -> Optional[Dict]:
    """Tier 1: Fetch official parcel coordinates from TKGM MEGSIS API"""
    if not mahalle_id or not ada or not parsel:
        return None
        
    url = f"https://cbsapi.tkgm.gov.tr/megsiswebapi.v3/api/parsel/{mahalle_id}/{ada}/{parsel}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                geometry = data.get("geometry", {})
                coordinates = geometry.get("coordinates", [])
                if coordinates:
                    first_ring = coordinates[0]
                    avg_lng = sum(p[0] for p in first_ring) / len(first_ring)
                    avg_lat = sum(p[1] for p in first_ring) / len(first_ring)
                    return {
                        "lat": avg_lat,
                        "lng": avg_lng,
                        "source": "TKGM MEGSIS",
                        "tkgm_verified": 1,
                        "raw_geojson": data
                    }
    except Exception as e:
        logger.warning(f"Tier 1 (TKGM) Fetch Failed: {e}")
    return None

async def geocode_nominatim(address_query: str) -> Optional[Dict]:
    """Tier 2: OpenStreetMap Nominatim Geocoding Fallback"""
    if not address_query or not address_query.strip():
        return None
        
    encoded_q = urllib.parse.quote(f"{address_query}, Turkey")
    url = f"https://nominatim.openstreetmap.org/search?q={encoded_q}&format=json&limit=1"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url, headers={"User-Agent": "NexaPrimeEnterprise/2.0"})
            if resp.status_code == 200:
                results = resp.json()
                if results and len(results) > 0:
                    lat = float(results[0]["lat"])
                    lng = float(results[0]["lon"])
                    return {
                        "lat": lat,
                        "lng": lng,
                        "source": "OpenStreetMap Nominatim",
                        "tkgm_verified": 0
                    }
    except Exception as e:
        logger.warning(f"Tier 2 (Nominatim) Geocoding Failed: {e}")
    return None

def get_city_centroid(il: Optional[str], ilce: Optional[str] = None, mahalle: Optional[str] = None) -> Dict:
    """Tier 3 & Tier 4: Micro-Region, District & City Centroid Fallback"""
    for search_term in [mahalle, ilce, il]:
        if search_term:
            clean_term = search_term.lower().strip().replace("i̇", "i")
            for key in CITY_CENTROIDS:
                if key in clean_term or clean_term in key:
                    res = CITY_CENTROIDS[key].copy()
                    res.update({"source": f"Micro-Region Centroid ({search_term})", "tkgm_verified": 0})
                    return res

    res = DEFAULT_TURKEY_CENTER.copy()
    res.update({"source": "Turkey Default Fallback", "tkgm_verified": 0})
    return res

from app.services.ai_location_agent import research_project_location_with_ai

async def resolve_coordinates_with_fallback(
    mahalle_id: Optional[int] = None,
    ada: Optional[str] = None,
    parsel: Optional[str] = None,
    il: Optional[str] = None,
    ilce: Optional[str] = None,
    mahalle: Optional[str] = None,
    location: Optional[str] = None,
    project_name: Optional[str] = None,
    description: Optional[str] = None
) -> Dict:
    """
    Robust 5-Tier Coordinate Fallback Engine:
    Tier 1: TKGM MEGSIS API (Ada/Parsel)
    Tier 2: OpenStreetMap Nominatim Geocoding (Direct Address Text)
    Tier 2.5: AI Location Research Agent (LLM research from project name & description)
    Tier 3: İl/İlçe/Mahalle Merkez Koordinat Tablosu (City & Micro-Region Centroids)
    Tier 4: Türkiye Genel Merkez Koordinatı (Default Center)
    """
    # Tier 1: TKGM MEGSIS
    if mahalle_id and ada and parsel:
        tkgm_res = await get_tkgm_parsel_info(mahalle_id, ada, parsel)
        if tkgm_res:
            logger.info(f"📍 Coordinates resolved via Tier 1 (TKGM): {tkgm_res['lat']}, {tkgm_res['lng']}")
            return tkgm_res

    # Tier 2: OpenStreetMap Nominatim Direct
    address_parts = [p for p in [mahalle, ilce, il, location] if p]
    if address_parts:
        query = ", ".join(address_parts)
        osm_res = await geocode_nominatim(query)
        if osm_res:
            logger.info(f"📍 Coordinates resolved via Tier 2 (Nominatim): {osm_res['lat']}, {osm_res['lng']}")
            return osm_res

    # Tier 2.5: AI Location Research Agent (LLM Fallback)
    if project_name or description or location or il:
        try:
            ai_loc = await research_project_location_with_ai(
                name=project_name or "Bilinmeyen Proje",
                description=description,
                location_hint=location,
                il=il,
                ilce=ilce,
                mahalle=mahalle
            )
            if ai_loc and ai_loc.get("search_query"):
                ai_osm = await geocode_nominatim(ai_loc["search_query"])
                if ai_osm:
                    ai_osm["source"] = f"AI Location Agent ({ai_loc['search_query']})"
                    logger.info(f"📍 Coordinates resolved via Tier 2.5 (AI Agent): {ai_osm['lat']}, {ai_osm['lng']}")
                    return ai_osm
        except Exception as e:
            logger.warning(f"Tier 2.5 (AI Agent) error: {e}")

    # Tier 3 & 4: Centroids & Default Fallback
    fallback_res = get_city_centroid(il, ilce, mahalle)
    logger.info(f"📍 Coordinates resolved via Tier 3/4 ({fallback_res['source']}): {fallback_res['lat']}, {fallback_res['lng']}")
    return fallback_res
