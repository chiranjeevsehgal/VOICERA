from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from datetime import timedelta
from services.auth import (
    authenticate_user, create_access_token, 
    get_current_user, get_password_hash,
    get_user, get_user_by_email, ACCESS_TOKEN_EXPIRE_MINUTES, GUEST_ACCESS_TOKEN_EXPIRE_MINUTES, users_collection, get_next_guest_count, create_guest_user
)
from models.auth import Token, UserCreate, UserResponse, ProfileResponse
from datetime import datetime
import logging

router = APIRouter(prefix='/auth')
logger = logging.getLogger(__name__)

@router.post("/login", response_model=Token)
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends()
    ):
    # Login User
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "status": False,
                "detail": "Incorrect username or password",
                "access_token": None,
                "token_type": None
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.get("status") == "inactive":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "status": False,
                "detail": "Your account is inactive. Please contact support for assistance.",
                "access_token": None,
                "token_type": None
            }
        )
    token_data = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "userId": str(user["_id"])
    }
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data=token_data, expires_delta=access_token_expires
    )
    
    return {
        "status": True,
        "detail": "Login Successful",
        "role": user["role"],
        "access_token": access_token, 
        "token_type": "bearer"
        }


@router.post("/guest", response_model=Token)
async def guest_login():
    try:
        # Get the next guest count
        guest_count = await get_next_guest_count()
        
        # Generate guest credentials
        guest_email = f"guest_vera{guest_count}@gmail.com"
        guest_name = f"Guest User {guest_count}"
        
        # Create guest user data (no password needed)
        guest_user_data = {
            "email": guest_email,
            "name": guest_name,
            "role": "guest",
            "status": "active",
            "guest_id": guest_count,
            "created_at": datetime.utcnow(),
            "last_login": datetime.utcnow()
        }
        
        # Insert the guest user into separate guests collection
        guest_user_id = await create_guest_user(guest_user_data)
        
        # Create token for guest user
        token_data = {
            "sub": str(guest_user_id),
            "email": guest_email,
            "role": "guest",
            "userId": str(guest_user_id),
            "is_guest": True,
            "guest_id": guest_count
        }
        
        access_token_expires = timedelta(minutes=GUEST_ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data=token_data, expires_delta=access_token_expires
        )
        
        return {
            "status": True,
            "detail": "Guest session created successfully",
            "role": "guest",
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except Exception as e:
        logger.error(f"Guest login error: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": False,
                "detail": "Failed to create guest session. Please try again.",
                "access_token": None,
                "token_type": None
            }
        )

@router.post("/register", response_model=UserResponse)
async def register_user(user: UserCreate):
    # Check if user already exists
    if await get_user_by_email(user.email):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": False,
                "detail": "Email already registered",
            },
        )
    
    # Create new user
    hashed_password = get_password_hash(user.password)
    user_dict = user.dict()
    user_dict["password"] = hashed_password
    user_dict["created_at"] = datetime.utcnow()
    
    await users_collection.insert_one(user_dict)
    
    # Return user data
    return UserResponse(
        status=True,
        detail="Account has been created successfully",
        email=user.email,
        full_name=user.full_name,
    )

@router.get("/users/profile", response_model=ProfileResponse)
async def usr_profile(current_user: dict = Depends(get_current_user)):
    return ProfileResponse(
        email=current_user["email"],
        full_name=current_user.get("full_name"),
        role=current_user.get("role", "user"),
    )


@router.get("/validate-token")
async def validate_token(current_user = Depends(get_current_user)):
    """
    Validate a JWT token and return user information.
    """
    return {
        "valid": True,
        "user": {
            "id": str(current_user["_id"]),
            "email": current_user["email"],
            "role": current_user["role"]
        }
    }
