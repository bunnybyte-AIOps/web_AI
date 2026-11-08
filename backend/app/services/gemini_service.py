import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings


class GeminiAPIError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


class GeminiOrchestrator:
    def __init__(self) -> None:
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.fallback_model = settings.GEMINI_FALLBACK_MODEL
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def _request_model(
        self, model: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{model}:generateContent?key={self.api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(response_body)
            except json.JSONDecodeError:
                error_data = {}
            provider_message = (
                error_data.get("error", {}).get("message")
                if isinstance(error_data, dict)
                and isinstance(error_data.get("error"), dict)
                else None
            )
            if exc.code == 404:
                detail = (
                    f"Model '{model}' không tồn tại hoặc không được API key "
                    "cho phép sử dụng."
                )
            else:
                detail = f"Gemini API trả về HTTP {exc.code}."
            if provider_message:
                detail = f"{detail} Chi tiết từ Google: {provider_message}"
            raise GeminiAPIError(exc.code, detail) from exc
        except TimeoutError as exc:
            raise GeminiAPIError(
                503, f"Gemini không phản hồi trong 45 giây với model '{model}'."
            ) from exc
        except urllib.error.URLError as exc:
            raise GeminiAPIError(
                503, f"Không kết nối được Gemini với model '{model}'. Kiểm tra mạng rồi thử lại."
            ) from exc

    def _call_gemini(
        self, system_instruction: str, prompt: str, temperature: float = 0.7
    ) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")

        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        try:
            body = self._request_model(self.model, payload)
        except GeminiAPIError as primary_error:
            transient_statuses = {429, 500, 502, 503, 504}
            if (
                primary_error.status_code not in transient_statuses
                or not self.fallback_model
                or self.fallback_model == self.model
            ):
                raise
            try:
                body = self._request_model(self.fallback_model, payload)
            except GeminiAPIError as fallback_error:
                raise RuntimeError(
                    f"Model chính lỗi: {primary_error}. "
                    f"Model dự phòng '{self.fallback_model}' cũng lỗi: {fallback_error}"
                ) from fallback_error

        candidates = body.get("candidates", [])
        if not candidates or not candidates[0].get("content", {}).get("parts"):
            raise RuntimeError("Gemini không trả về nội dung có thể sử dụng.")
        return candidates[0]["content"]["parts"][0]["text"]

    def generate_concepts(self, raw_idea: str, genre: str = "Tự do") -> dict[str, Any]:
        system_prompt = (
            "Bạn là Giám đốc Sáng tạo Điện ảnh của CINAI. Phát triển ý tưởng thô "
            "thành 3 concept phim ngắn độc đáo. Chỉ trả về JSON hợp lệ."
        )
        user_prompt = (
            f'Sinh 3 concept phim từ ý tưởng: "{raw_idea}", thể loại: "{genre}".'
        )
        return json.loads(self._call_gemini(system_prompt, user_prompt))

    def generate_story_bible(
        self, selected_concept: dict[str, Any], creator_answers: dict[str, str]
    ) -> dict[str, Any]:
        system_prompt = (
            "Bạn là nhà biên kịch và kiến trúc sư thế giới của CINAI. "
            "Xây dựng Story Bible hoàn chỉnh. Chỉ trả về JSON hợp lệ."
        )
        user_prompt = (
            f"Story Bible cho concept: {json.dumps(selected_concept, ensure_ascii=False)}, "
            f"câu trả lời: {json.dumps(creator_answers, ensure_ascii=False)}"
        )
        return json.loads(self._call_gemini(system_prompt, user_prompt))

    def generate_script_and_scenes(
        self, story_bible: dict[str, Any], episode_number: int = 1
    ) -> dict[str, Any]:
        system_prompt = (
            "Bạn là đạo diễn phân cảnh của CINAI. Sinh kịch bản và phân cảnh có "
            "visual prompt tiếng Anh và lời thoại tiếng Việt. Nếu Story Bible có "
            "_cinai_continuity, phải dùng các dữ kiện đó để giữ nhất quán nhân vật, "
            "thế giới và tiếp nối sự kiện. Chỉ trả về JSON hợp lệ."
        )
        user_prompt = (
            f"Sinh kịch bản và phân cảnh cho Story Bible: "
            f"{json.dumps(story_bible, ensure_ascii=False)}, tập {episode_number}."
        )
        return json.loads(self._call_gemini(system_prompt, user_prompt))

    def generate_analytics_recommendations(
        self, project_data: dict[str, Any], analytics: dict[str, Any]
    ) -> dict[str, Any]:
        system_prompt = (
            "Bạn là chuyên gia phân tích nội dung video. Đưa ra 3 gợi ý cụ thể "
            "dựa trên số liệu thật, tránh khẳng định xu hướng khi dữ liệu chưa đủ. "
            "Gợi ý tập tiếp theo phải giữ tính nhất quán với Story Bible. Chỉ trả JSON."
        )
        user_prompt = (
            f"Thông tin dự án: {json.dumps(project_data, ensure_ascii=False)}\n"
            f"Số liệu analytics gần nhất: {json.dumps(analytics, ensure_ascii=False)}\n"
            'Trả JSON dạng {"recommendations":[{"title":"...","description":"..."}]}.'
        )
        return json.loads(self._call_gemini(system_prompt, user_prompt))


gemini_orchestrator = GeminiOrchestrator()
