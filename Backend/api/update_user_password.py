from dotenv import load_dotenv
from fastapi import APIRouter


load_dotenv()

router = APIRouter(prefix='/mail')


@router.post("/update-password")
# async def update_user_password(request: ):