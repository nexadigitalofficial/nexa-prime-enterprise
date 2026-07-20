from fastapi import APIRouter, Depends
import aiosqlite
import httpx
from app.core.database import get_db

router = APIRouter(prefix="/api/system", tags=["System Status"])

@router.get("/status")
async def get_system_status(db: aiosqlite.Connection = Depends(get_db)):
    status = {
        "ollama_active": False,
        "total_documents": 0,
        "total_chunks": 0,
        "embedded_chunks": 0,
        "enterprise_mode": True
    }
    
    # Check Ollama if local
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:11434/", timeout=2.0)
            if resp.status_code == 200:
                status["ollama_active"] = True
    except Exception:
        pass
        
    try:
        async with db.execute("SELECT COUNT(*) FROM documents") as cursor:
            row = await cursor.fetchone()
            status["total_documents"] = row[0] if row else 0
            
        async with db.execute("SELECT COUNT(*) FROM document_chunks") as cursor:
            row = await cursor.fetchone()
            status["total_chunks"] = row[0] if row else 0
            
        async with db.execute("SELECT COUNT(*) FROM document_chunks WHERE embedding != '[]' AND embedding IS NOT NULL AND embedding != ''") as cursor:
            row = await cursor.fetchone()
            status["embedded_chunks"] = row[0] if row else 0
    except Exception:
        pass
        
    return status
