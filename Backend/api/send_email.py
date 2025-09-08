from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from Backend.utils.email_util import send_email
from pydantic import BaseModel

load_dotenv()

router = APIRouter(prefix='/mail')

class EmailRequest(BaseModel):
    email: str

@router.post("/send-email")
async def send_email(req : EmailRequest):
    success = send_email(
        to=req.email,
    )
    if success:
        return {
            "status" : True,
            "message": "Email sent successfully!",
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send email"
        )