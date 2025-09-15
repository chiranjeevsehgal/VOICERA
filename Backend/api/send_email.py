from fastapi import APIRouter, HTTPException, Depends
from dotenv import load_dotenv
from utils.email_util import send_email
from pydantic import BaseModel
from typing import Any, Optional
from services.auth import requires_role
load_dotenv()
router = APIRouter()

class EmailRequest(BaseModel):
    email: str
    subject: Optional[str] = 'Default Subject'
    content: Optional[str] = 'Default email content'

@router.post('/send-email')
async def send_email_endpoint(req: EmailRequest, current_user: dict[str, Any]=Depends(requires_role('admin'))):
    success = send_email(to=req.email, subject=req.subject, content=req.content)
    if success:
        return {'status': True, 'message': 'Email sent successfully!'}
    else:
        raise HTTPException(status_code=500, detail='Failed to send email')