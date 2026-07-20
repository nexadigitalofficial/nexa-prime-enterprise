from pydantic import BaseModel
from typing import Optional, List

class ProjectCreate(BaseModel):
    name: str
    location: Optional[str] = None
    il: Optional[str] = None
    ilce: Optional[str] = None
    mahalle: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    ada_no: Optional[str] = None
    parsel_no: Optional[str] = None

class ProjectResponse(ProjectCreate):
    id: int
    tkgm_verified: int = 0
    created_at: str

class ChatRequest(BaseModel):
    message: str
    project_id: Optional[int] = None
    session_id: Optional[str] = "default"

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
