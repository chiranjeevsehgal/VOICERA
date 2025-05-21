from pydantic import BaseModel


class GenerateOtpRequest(BaseModel):
    email: str
    
class OtpVerificationRequest(BaseModel):
    otp: str
    password: str
    