from fastapi import HTTPException

from app.core.config import settings
from app.schemas.ai_schemas import AIProvider
from app.services.gemini_service import gemini_orchestrator
from app.services.grok_service import grok_orchestrator


def get_ai_provider(provider: AIProvider):
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="GEMINI_API_KEY chưa được cấu hình ở backend.",
            )
        return gemini_orchestrator
    if not settings.XAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Grok chưa được cấu hình. Thêm XAI_API_KEY vào backend/.env rồi khởi động lại backend.",
        )
    return grok_orchestrator
