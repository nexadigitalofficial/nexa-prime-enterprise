from fastapi import APIRouter, Depends, HTTPException, Form
from typing import Optional, Dict
import aiosqlite
from app.core.database import get_db
from app.services.ai_swarm_service import swarm_orchestrator

router = APIRouter(prefix="/api/swarm", tags=["Multi-Agent AI Swarm"])

@router.post("/score-lead/{customer_id}")
async def score_customer_lead(customer_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Evaluate a customer lead using LeadScoringAgent"""
    try:
        res = await swarm_orchestrator.lead_agent.evaluate_lead(db, customer_id)
        
        # Save score to notes in SQLite
        note_entry = f"\n[AI Lead Score: {res.get('score')}/100 - {res.get('tier')}] {res.get('summary')}"
        await db.execute("UPDATE customers SET notes = notes || ? WHERE id = ?", (note_entry, customer_id))
        await db.commit()

        return {"status": "ok", "evaluation": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lead scoring failed: {e}")

@router.get("/predict-valuation/{project_id}")
async def predict_project_valuation(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Run Automated Valuation Model (AVM) for a project"""
    try:
        res = await swarm_orchestrator.valuation_agent.predict_valuation(db, project_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Valuation prediction failed: {e}")

@router.get("/competitor-analysis/{project_id}")
async def analyze_project_competitors(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Run regional benchmark & competitor analysis"""
    try:
        res = await swarm_orchestrator.competitor_agent.analyze_competitors(db, project_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Competitor analysis failed: {e}")

@router.post("/full-analysis/{project_id}")
async def run_full_swarm_analysis(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Run full multi-agent swarm analysis for a project"""
    try:
        res = await swarm_orchestrator.run_full_project_swarm_analysis(db, project_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Swarm analysis failed: {e}")
