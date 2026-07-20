from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import aiosqlite
import os
import uuid
from app.core.database import get_db

router = APIRouter(prefix="/api/documents", tags=["Documents"])

UPLOAD_DIR = "static/documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload_document(
    project_id: int = Form(...),
    category: str = Form("Genel"),
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    try:
        ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{project_id}_{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
            
        file_url = f"/static/documents/{unique_filename}"
        doc_type = ext.replace(".", "").lower()
        if doc_type in ["jpg", "jpeg", "png", "webp"]:
            doc_type = "image"
            
        async with db.execute("""
            INSERT INTO documents (project_id, doc_type, title, file_url, category)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, doc_type, file.filename, file_url, category)) as cursor:
            doc_id = cursor.lastrowid
        await db.commit()
        
        return {"id": doc_id, "file_url": file_url, "message": "Belge başarıyla yüklendi"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yükleme hatası: {str(e)}")
