from pydantic import BaseModel, EmailStr
from typing import Optional

class Token(BaseModel):
    status: str
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: str = "user"  # Default role

class UserResponse(BaseModel):
    status: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    disabled: bool = False

class ProfileResponse(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    disabled: bool = False