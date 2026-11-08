from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

AIProvider = Literal["gemini", "grok"]


class AIProviderRequest(BaseModel):
    ai_provider: AIProvider = "gemini"

class IdeaRequest(BaseModel):
    project_id: int = Field(..., gt=0)
    raw_idea: str = Field(
        ..., min_length=10, max_length=4000,
        example="Một thợ sửa robot ở Sài Gòn năm 2088 tìm thấy con chip chứa ký ức bị cấm",
    )
    genre: Optional[str] = Field("Cyberpunk / Viễn tưởng", example="Sci-Fi / Cyberpunk")
    ai_provider: AIProvider = "gemini"

class ConceptChoiceRequest(BaseModel):
    project_id: int = Field(..., gt=0)
    selected_concept: Dict[str, Any]
    creator_answers: Dict[str, str] = Field(default_factory=dict, example={"tone": "Hồi hộp, ấm áp", "ending": "Bất ngờ"})
    ai_provider: AIProvider = "gemini"

class ScriptGenerationRequest(BaseModel):
    project_id: int = Field(..., gt=0)
    story_bible: Dict[str, Any]
    episode_number: Optional[int] = Field(default=1, ge=1, le=1000)
    ai_provider: AIProvider = "gemini"
