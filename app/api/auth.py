from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.schemas import UserLogin, Token

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM users WHERE username = ?", (user_data.username,)) as cursor:
        user = await cursor.fetchone()
        
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı adı veya şifre."
        )
        
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer"}
