from pydantic import BaseModel


class GenerateOtpRequest(BaseModel):
    email: str
    
class OtpVerificationRequest(BaseModel):
    email: str
    otp: str