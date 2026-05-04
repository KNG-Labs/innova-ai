import httpx
from pydantic import ValidationError

from app.client.llm_client import LLMClient
from app.schemas.openai import ChatCompletionRequest, ChatCompletionResponse


class OpenRouterClient(LLMClient):
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def create_chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._http.post(
                url,
                headers=headers,
                json=self._build_payload(request),
                timeout=60,
            )
            response.raise_for_status()
            return ChatCompletionResponse.model_validate(response.json())
        except httpx.TimeoutException as exc:
            raise RuntimeError("LLM provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("LLM provider request failed") from exc
        except ValidationError as exc:
            raise RuntimeError("LLM provider returned invalid response schema") from exc

    @staticmethod
    def _build_payload(request: ChatCompletionRequest) -> dict:
        """Строит payload для OpenRouter API."""
        payload = request.model_dump(exclude_none=True)
        return payload
