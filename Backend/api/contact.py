from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import logging
from Backend.utils.voicera_contact_email import send_contact_form_email

logger = logging.getLogger('voicera.contact')

router = APIRouter()

class ContactRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Contact person's name")
    email: EmailStr = Field(..., description="Contact person's email address")
    phone_number: Optional[str] = Field(None, max_length=30, description="Contact person's phone number")
    message: str = Field(..., min_length=2, max_length=2000, description="Contact message")

class ContactResponse(BaseModel):
    success: bool
    message: str

@router.post("/contact/voicera", response_model=ContactResponse)
async def submit_contact_form(contact_data: ContactRequest, request: Request):
    """
    Submit contact form and send notification email to admins
    """
    try:
        logger.info(f"Contact form submission from {contact_data.email} (name: {contact_data.name})")
        
        # Send email to admins
        email_sent = await send_contact_form_email(
            name=contact_data.name,
            email=contact_data.email,
            message=contact_data.message,
            phone_number=contact_data.phone_number
        )
        
        if email_sent:
            logger.info(f"Contact form email sent successfully for {contact_data.email}")
            return ContactResponse(
                success=True,
                message="Thank you for your message! We'll get back to you soon."
            )
        else:
            logger.error(f"Failed to send contact form email for {contact_data.email}")
            return ContactResponse(
                success=False,
                message="We're experiencing technical difficulties. Please try again later or contact us directly."
            )
            
    except Exception as e:
        logger.exception(f"Error processing contact form submission: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later."
        )