from fastapi import APIRouter, Depends, HTTPException, Form
from typing import List, Optional
import aiosqlite
from app.core.database import get_db
from app.models.schemas import ProjectCreate
from app.services.tkgm_service import resolve_coordinates_with_fallback

router = APIRouter(prefix="/api/projects", tags=["Projects"])

@router.get("")
async def get_projects(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM projects ORDER BY created_at DESC") as cursor:
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
        
    async with db.execute("SELECT id, doc_type, title, file_url, category FROM documents WHERE project_id = ?", (project_id,)) as cursor:
        docs = await cursor.fetchall()
        
    return {
        **dict(project),
        "units": [dict(u) for u in units],
        "documents": [dict(d) for d in docs],
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
