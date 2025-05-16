from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional, List
import google.generativeai as genai
import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from services.auth import get_current_user

load_dotenv()

router = APIRouter()

class LLMConfig_Translation:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL")
        self.temperature = 0.0  # 0 for deterministic translation
        self.max_tokens = 4096
        self.top_p = 1.0
        self.top_k = 1
        
        # Translation system prompt for language translation
        self.system_prompt = os.getenv("SYSTEM_PROMPT_TRANSLATION")
        
        # Initialize LLM if API key is available
        if self.api_key:
            genai.configure(api_key=self.api_key)

# Request and response models
class TranslationRequest(BaseModel):
    text: str = Field(..., description="Text to translate")
    target_language: str = Field(..., description="Target language for translation")
    source_language: Optional[str] = Field(None, description="Source language (auto-detected if not provided)")
    preserve_formatting: bool = Field(True, description="Whether to preserve formatting in the translation")
    formal: bool = Field(False, description="Whether to use formal language in translation")

class TranslationResponse(BaseModel):
    translated_text: str

# Get config for llm
def get_config():
    return LLMConfig_Translation()

# To get the desired translation
@router.post(
    "/llm/translate",
    summary="Translate text using Gemini API",
    description="Translates text to a target language using Google's Gemini model"
)
async def translate_text(
    request: TranslationRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Translate text to a target language using Google's Gemini model.
    
    Example body:
    {
        "text": "Hello world, how are you?",
        "target_language": "Spanish",
        "preserve_formatting": true,
        "formal": false
    }
    """
    config = get_config()

    if not config.api_key:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")
    
    system_prompt = config.system_prompt
    
    temperature = config.temperature
    
    try:
        # Configuring the model
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": config.max_tokens,
                "top_p": config.top_p,
                "top_k": config.top_k
            }
        )
        
        response = model.generate_content(
            [system_prompt, request.text]
        )
        
        translated_text = response.text
        
        return TranslationResponse(
            translated_text=translated_text
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation error: {str(e)}")
    
# Endpoint to get current configuration
@router.get("/llm/config")
async def get_configuration(config: LLMConfig_Translation = Depends(get_config)):
    """Get current Gemini configuration"""
    return {
        "model_name": config.model_name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "top_p": config.top_p,
        "top_k": config.top_k,
        "system_prompt": config.system_prompt,
        "api_key_configured": bool(config.api_key)
    }