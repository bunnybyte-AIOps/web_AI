import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.gemini_service import GeminiAPIError, GeminiOrchestrator


class GrokOrchestrator(GeminiOrchestrator):
    def __init__(self) -> None:
        self.api_key = settings.XAI_API_KEY
        self.model = settings.XAI_MODEL
        self.base_url = "https://api.x.ai/v1/chat/completions"

    def _call_gemini(
        self, system_instruction: str, prompt: str, temperature: float = 0.7
    ) -> str:
        if not self.api_key:
            raise RuntimeError("XAI_API_KEY chưa được cấu hình trong backend/.env.")

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(response_body)
            except json.JSONDecodeError:
                error_data = {}
            provider_error = (
                error_data.get("error") if isinstance(error_data, dict) else None
            )
            if isinstance(provider_error, dict):
                provider_message = provider_error.get("message")
            elif isinstance(provider_error, str):
                provider_message = provider_error
            else:
                provider_message = None
            detail = f"xAI Grok API trả về HTTP {exc.code}."
            if provider_message:
                detail = f"{detail} Chi tiết từ xAI: {provider_message}"
            elif isinstance(error_data, dict) and error_data.get("message"):
                detail = f"{detail} Chi tiết từ xAI: {error_data['message']}"
            raise GeminiAPIError(exc.code, detail) from exc
        except TimeoutError as exc:
            raise RuntimeError("Grok không phản hồi trong 60 giây.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Không kết nối được xAI Grok API. Kiểm tra mạng rồi thử lại.") from exc

        choices = body.get("choices", [])
        if not choices or not isinstance(choices[0].get("message", {}).get("content"), str):
            raise RuntimeError("xAI Grok không trả về nội dung có thể sử dụng.")
        return choices[0]["message"]["content"]


grok_orchestrator = GrokOrchestrator()
