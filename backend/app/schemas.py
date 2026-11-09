from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    role: str = "employee"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    """Refresh token is optional: the access token in the header is revoked too."""

    refresh_token: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=8)

class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    is_active: bool
    roles: List[str] = []
    permissions: List[str] = []
    class Config:
        from_attributes = True

class DocumentOut(BaseModel):
    id: int
    filename: str
    original_filename: str
    mime_type: str
    size_bytes: int
    status: str
    owner_id: Optional[int] = None
    created_at: datetime
    page_count: int
    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    conversation_id: Optional[int] = None
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    conversation_id: int
    message_id: int
    latency_ms: int

class LLMConfigCreate(BaseModel):
    provider: str
    model_name: str
    temperature: float = 0.2
    max_tokens: int = 1024
    is_active: bool = False
    api_key: Optional[str] = None

class AuditOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True
