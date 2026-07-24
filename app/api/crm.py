from fastapi import APIRouter, Depends, HTTPException, Form, Query
from typing import Optional, List, Dict
import aiosqlite
import httpx
import os
import json
from app.core.database import get_db

router = APIRouter(prefix="/api/crm", tags=["Real Estate CRM & Admin"])

@router.get("/stats")
async def get_crm_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Fetch executive real estate CRM statistics"""
    async with db.execute("SELECT COUNT(*) as count FROM customers") as cursor:
        total_customers = (await cursor.fetchone())["count"]

    async with db.execute("SELECT COUNT(*) as count FROM projects") as cursor:
        total_projects = (await cursor.fetchone())["count"]

    async with db.execute("SELECT stage, COUNT(*) as count FROM customers GROUP BY stage") as cursor:
        rows = await cursor.fetchall()
        stages = {r["stage"]: r["count"] for r in rows}

    return {
        "total_customers": total_customers,
        "total_projects": total_projects,
        "stages": {
            "new": stages.get("Yeni Talep", 0),
            "contact": stages.get("İletişimde", 0),
            "presentation": stages.get("Sunum Yapıldı", 0),
            "proposal": stages.get("Teklif Verildi", 0),
            "closed": stages.get("Satış Kapandı", 0)
        }
    }

@router.get("/customers")
async def list_customers(
    stage: Optional[str] = Query(None),
    project_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    """List all real estate customer leads with project details"""
    query = """
        SELECT c.*, p.name as project_name 
        FROM customers c
        LEFT JOIN projects p ON c.project_id = p.id
        WHERE 1=1
    """
    params = []

    if stage:
        query += " AND c.stage = ?"
        params.append(stage)
    if project_id:
        query += " AND c.project_id = ?"
        params.append(project_id)
    if search:
        query += " AND (c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    query += " ORDER BY c.id DESC"

    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    return [dict(r) for r in rows]

@router.post("/customers")
async def create_customer(
    name: str = Form(...),
    phone: str = Form(...),
    project_id: int = Form(...),
    email: Optional[str] = Form(""),
    interested_units: Optional[str] = Form(""),
    notes: Optional[str] = Form(""),
    stage: Optional[str] = Form("Yeni Talep"),
    budget: Optional[str] = Form("Belirtilmedi"),
    assigned_agent: Optional[str] = Form("Yönetici"),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new customer lead"""
    try:
        cursor = await db.execute("""
            INSERT INTO customers (project_id, name, phone, email, interested_units, notes, stage, budget, assigned_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, name.strip(), phone.strip(), email.strip(), interested_units.strip(), notes.strip(), stage, budget, assigned_agent))
        await db.commit()
        return {"status": "ok", "customer_id": cursor.lastrowid, "message": "✅ Müşteri kaydı oluşturuldu."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Müşteri ekleme hatası: {e}")

@router.put("/customers/{customer_id}/stage")
async def update_customer_stage(
    customer_id: int,
    stage: str = Form(...),
    notes: Optional[str] = Form(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update pipeline stage for a customer lead (e.g. Kanban drag & drop)"""
    if notes:
        await db.execute("""
            UPDATE customers SET stage = ?, notes = notes || '\n[' || CURRENT_TIMESTAMP || '] Statü: ' || ? || ' - ' || ? WHERE id = ?
        """, (stage, stage, notes, customer_id))
    else:
        await db.execute("UPDATE customers SET stage = ? WHERE id = ?", (stage, customer_id))
    
    await db.commit()
    return {"status": "ok", "message": f"✅ Müşteri statüsü '{stage}' olarak güncellendi."}

@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a customer record"""
    await db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    await db.commit()
    return {"status": "ok", "message": "✅ Müşteri silindi."}

from app.services.firebase_service import firebase_manager

@router.get("/firebase-status")
async def get_firebase_status():
    """Check connection status with Firebase Realtime Database"""
    res = await firebase_manager.test_connection()
    return res

@router.post("/firebase-sync-all")
async def sync_all_firebase(
    firebase_url: Optional[str] = Form(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Sync all 20 projects + CRM leads to Firebase in 1-click"""
    if firebase_url and firebase_url.strip():
        firebase_manager.configure(firebase_url)
    
    try:
        res = await firebase_manager.sync_all(db)
        return {
            "status": "ok",
            "message": f"🔥 Tesis Senkronize Edildi! {res['synced_projects']} Proje ve {res['synced_customers']} Müşteri Kaydı Firebase Buluta Aktarıldı.",
            "data": res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Firebase Senkronizasyon Hatası: {e}")
