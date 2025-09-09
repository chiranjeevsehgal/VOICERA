from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv
from services.database import db, users_collection, guests_collection
from bson import ObjectId
from bson.errors import InvalidId
import random
import string

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

GUEST_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("GUEST_ACCESS_TOKEN_EXPIRE_MINUTES"))

# Password hash context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

guest_counter = 0

# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode a JWT token and return the payload.
    Returns None if the token is invalid.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_user(uid: str) -> Optional[Dict[str, Any]]:
    try:
        obj_id = ObjectId(uid)  # convert string to ObjectId
    except InvalidId:
        return None
    if (user := await users_collection.find_one({"_id": obj_id})):
        return user
    return None

async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if (user := await users_collection.find_one({"email": email})):
        return user
    return None

async def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = await get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["password"]):
        return None
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_next_guest_count() -> str:
    """Get a 4-digit random hash for guest identification"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

async def get_guest(uid: str) -> Optional[Dict[str, Any]]:
    """Get guest user by ID from guests collection"""
    try:
        obj_id = ObjectId(uid)
    except InvalidId:
        return None
    if (guest := await guests_collection.find_one({"_id": obj_id})):
        return guest
    return None

def is_guest_user(user: Dict[str, Any]) -> bool:
    """Check if a user is a guest user"""
    return user.get("role") == "guest" or "guest_id" in user

async def create_guest_user(guest_data: Dict[str, Any]) -> ObjectId:
    """Create a guest user in the guests collection"""
    result = await guests_collection.insert_one(guest_data)
    return result.inserted_id

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid: str = payload.get("sub")
        is_guest: bool = payload.get("is_guest", False)
        if uid is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    if is_guest:
        user = await get_guest(uid)
    else:
        user = await get_user(uid)
            
    if user is None:
        raise credentials_exception

    return user

# Role-based access control
def requires_role(required_role: str):
    async def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)):
        if current_user.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required"
            )
        return current_user
    return role_checker