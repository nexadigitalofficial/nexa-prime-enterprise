from fastapi import APIRouter, Depends, HTTPException, Form
from typing import List, Optional
import aiosqlite
from app.core.database import get_db
from app.models.schemas import ProjectCreate
from app.services.tkgm_service import resolve_coordinates_with_fallback

router = APIRouter(prefix="/api/projects", tags=["Projects"])

from app.services.location_verification_service import audit_single_project_location, audit_all_projects_in_db

@router.get("/location-audit-all")
async def audit_all_locations(db: aiosqlite.Connection = Depends(get_db)):
    """Run location self-check audit across all projects in the portfolio"""
    try:
        report = await audit_all_projects_in_db(db)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Konum denetimi hatası: {str(e)}")

@router.get("")
async def get_projects(is_portfolio: Optional[str] = None, db: aiosqlite.Connection = Depends(get_db)):
    if is_portfolio is not None and is_portfolio.lower() != 'all':
        val = 1 if str(is_portfolio).lower() in ['1', 'true', 'portfolio'] else 0
        query = "SELECT * FROM projects WHERE COALESCE(is_portfolio, 0) = ? ORDER BY id DESC"
        params = (val,)
    else:
        query = "SELECT * FROM projects ORDER BY id DESC"
        params = ()

    async with db.execute(query, params) as cursor:
        projects = await cursor.fetchall()
        
    result = []
    for p in projects:
        proj_dict = dict(p)
        async with db.execute("SELECT COUNT(*) as cnt FROM documents WHERE project_id = ?", (p["id"],)) as d_cursor:
            cnt_row = await d_cursor.fetchone()
            proj_dict["doc_count"] = cnt_row["cnt"] if cnt_row else 0
        result.append(proj_dict)
    return result

@router.get("/{project_id}")
async def get_project_detail(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
        project = await cursor.fetchone()
        
    if not project:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
        
    async with db.execute("SELECT * FROM units WHERE project_id = ?", (project_id,)) as cursor:
        units = await cursor.fetchall()
        
    async with db.execute("SELECT COUNT(*) as count FROM customers WHERE project_id = ?", (project_id,)) as cursor:
        customers = await cursor.fetchone()
        
    async with db.execute("SELECT COUNT(*) as count FROM sales WHERE customer_id IN (SELECT id FROM customers WHERE project_id = ?)", (project_id,)) as cursor:
        sales = await cursor.fetchone()
        
    # For portfolio listings: exclude thumbnail/system images (thmb_, x5_, logo, blank, etbis, profile)
    PORTFOLIO_EXCLUDE = [
        'thmb_', 'x5_', 'logo.', 'blank_', 'etbis_', 'p200_profile',
        'fafe09', 'p200_'
    ]
    is_portfolio_project = dict(project).get('is_portfolio', 0)

    async with db.execute("SELECT id, doc_type, title, file_url, category FROM documents WHERE project_id = ?", (project_id,)) as cursor:
        docs_raw = await cursor.fetchall()

    docs = []
    for d in docs_raw:
        d_dict = dict(d)
        furl = (d_dict.get('file_url') or '').strip()
        if not furl or furl == '#':
            continue
        fname_lower = furl.split('/')[-1].lower()
        # For portfolio listings: skip thumbnail and system files
        if is_portfolio_project:
            skip = any(fname_lower.startswith(pat) or pat in fname_lower for pat in PORTFOLIO_EXCLUDE)
            if skip:
                continue
        docs.append(d_dict)

    return {
        **dict(project),
        "units": [dict(u) for u in units],
        "documents": docs,
        "stats": {
            "total_customers": customers["count"],
            "total_sales": sales["count"]
        }
    }

@router.post("")
async def create_project(
    name: str = Form(...),
    location: str = Form(None),
    il: str = Form(None),
    ilce: str = Form(None),
    mahalle: str = Form(None),
    description: str = Form(None),
    lat: float = Form(None),
    lng: float = Form(None),
    ada_no: str = Form(None),
    parsel_no: str = Form(None),
    mahalle_id: int = Form(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    try:
        # Fallback coordinate resolution if lat/lng missing
        tkgm_verified = 0
        coord_source = "User Provided"
        
        if lat is None or lng is None:
            coord_data = await resolve_coordinates_with_fallback(
                mahalle_id=mahalle_id,
                ada=ada_no,
                parsel=parsel_no,
                il=il,
                ilce=ilce,
                mahalle=mahalle,
                location=location,
                project_name=name,
                description=description
            )
            lat = coord_data["lat"]
            lng = coord_data["lng"]
            tkgm_verified = coord_data.get("tkgm_verified", 0)
            coord_source = coord_data.get("source", "Fallback")

        async with db.execute("""
            INSERT INTO projects (name, location, il, ilce, mahalle, description, lat, lng, ada_no, parsel_no, tkgm_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, location, il, ilce, mahalle, description, lat, lng, ada_no, parsel_no, tkgm_verified)) as cursor:
            project_id = cursor.lastrowid
        await db.commit()
        
        return {
            "id": project_id,
            "lat": lat,
            "lng": lng,
            "tkgm_verified": tkgm_verified,
            "coordinate_source": coord_source,
            "message": "Proje ve koordinat altyapısı başarıyla oluşturuldu"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Proje ekleme hatası: {str(e)}")

@router.post("/{project_id}/resolve-coords")
async def resolve_project_coords(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Force re-run 4-Tier Fallback resolution for an existing project"""
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
        project = await cursor.fetchone()
        
    if not project:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
        
    coord_data = await resolve_coordinates_with_fallback(
        ada=project["ada_no"],
        parsel=project["parsel_no"],
        il=project["il"],
        ilce=project["ilce"],
        mahalle=project["mahalle"],
        location=project["location"],
        project_name=project["name"],
        description=project["description"]
    )
    
    await db.execute("""
        UPDATE projects SET lat = ?, lng = ?, tkgm_verified = ? WHERE id = ?
    """, (coord_data["lat"], coord_data["lng"], coord_data.get("tkgm_verified", 0), project_id))
    await db.commit()
    
    return {
        "project_id": project_id,
        "lat": coord_data["lat"],
        "lng": coord_data["lng"],
        "source": coord_data["source"],
        "tkgm_verified": coord_data.get("tkgm_verified", 0)
    }

from app.services.image_gen_service import generate_project_visual
from app.services.rag_service import generate_project_intelligence_report

@router.get("/{project_id}/location-audit")
async def get_single_location_audit(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Run location self-check audit for a single project"""
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
        project = await cursor.fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
        
    audit_res = await audit_single_project_location(dict(project))
    return audit_res

@router.post("/{project_id}/update-location")
async def update_project_location_pin(
    project_id: int,
    lat: float = Form(...),
    lng: float = Form(...),
    source: str = Form("Manuel Pinpoint Ayarlaması"),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update project coordinates (e.g. from drag & drop map pin adjustment in UI)"""
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
        project = await cursor.fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
        
    proj_dict = dict(project)
    proj_dict["lat"] = lat
    proj_dict["lng"] = lng
    proj_dict["location_source"] = source

    audit_res = await audit_single_project_location(proj_dict)
    
    await db.execute("""
        UPDATE projects 
        SET lat = ?, lng = ?, location_source = ?, location_accuracy_score = ?, location_status = ?, reverse_geocoded_address = ?
        WHERE id = ?
    """, (lat, lng, source, audit_res["accuracy_score"], audit_res["status"], audit_res["reverse_address"], project_id))
    await db.commit()
    
    return {
        "message": "Proje konumu haritada başarıyla güncellendi ve doğrulandı",
        "project_id": project_id,
        "lat": lat,
        "lng": lng,
        "source": source,
        "audit": audit_res
    }

@router.post("/{project_id}/auto-repair-location")
async def auto_repair_location(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Auto-repair project location using 5-Tier Fallback Engine & AI Agent"""
    async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
        project = await cursor.fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")

    p = dict(project)
    coord_data = await resolve_coordinates_with_fallback(
        ada=p.get("ada_no"),
        parsel=p.get("parsel_no"),
        il=p.get("il"),
        ilce=p.get("ilce"),
        mahalle=p.get("mahalle"),
        location=p.get("location"),
        project_name=p.get("name"),
        description=p.get("description")
    )
    
    p["lat"] = coord_data["lat"]
    p["lng"] = coord_data["lng"]
    p["location_source"] = f"AI Auto-Repair ({coord_data.get('source', 'Fallback')})"
    p["tkgm_verified"] = coord_data.get("tkgm_verified", 0)

    audit_res = await audit_single_project_location(p)

    await db.execute("""
        UPDATE projects 
        SET lat = ?, lng = ?, tkgm_verified = ?, location_source = ?, location_accuracy_score = ?, location_status = ?, reverse_geocoded_address = ?
        WHERE id = ?
    """, (coord_data["lat"], coord_data["lng"], coord_data.get("tkgm_verified", 0), p["location_source"], audit_res["accuracy_score"], audit_res["status"], audit_res["reverse_address"], project_id))
    await db.commit()

    return {
        "project_id": project_id,
        "lat": coord_data["lat"],
        "lng": coord_data["lng"],
        "source": p["location_source"],
        "audit": audit_res
    }

@router.get("/{project_id}/intelligence")
async def get_project_intelligence(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Generate Deep Project Intelligence Report for a single project"""
    try:
        report = await generate_project_intelligence_report(db, project_id)
        return {"project_id": project_id, "intelligence_report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Intelligence raporu oluşturulamadı: {str(e)}")

@router.post("/{project_id}/generate-visual")
async def generate_visual_for_project(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Generates an AI 3D architectural visual from Project Intelligence & DB data"""
    try:
        result = await generate_project_visual(project_id, db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Görsel üretme hatası: {str(e)}")
