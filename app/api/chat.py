from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from app.core.database import get_db
from app.models.schemas import ChatRequest
from app.services.rag_service import generate_cognitive_response

router = APIRouter(prefix="/api/chat", tags=["Cognitive AI Chat"])

@router.post("")
async def chat_endpoint(request: ChatRequest, db: aiosqlite.Connection = Depends(get_db)):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Mesaj içeriği boş olamaz.")
        
    try:
        reply = await generate_cognitive_response(
            db=db,
            user_message=request.message,
            project_id=request.project_id
        )
        return {
            "response": reply,
            "session_id": request.session_id,
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bilişsel yanıt oluşturulamadı: {str(e)}")
