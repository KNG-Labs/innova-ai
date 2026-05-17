import httpx
from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from app.client.llm_client import LLMClient, LLMProviderError
from app.schemas.openai_schema import ChatCompletionRequest, ChatCompletionResponse


class OpenRouterClient(LLMClient):
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            http_client=http,
        )

    async def create_chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        completion_params = request.to_sdk_completion_params()
        extra_body = request.to_openrouter_extra_body()

        try:
            if extra_body is not None:
                # reasoning не является стандартным параметром OpenAI Chat Completions,
                # поэтому для OpenRouter его нужно пробросить как extra_body.
                response = await self._client.chat.completions.create(
                    **completion_params,
                    extra_body=extra_body,
                )
            else:
                response = await self._client.chat.completions.create(
                    **completion_params,
                )
            return ChatCompletionResponse.model_validate(response.model_dump())
        except APITimeoutError as exc:
            raise LLMProviderError(
                "LLM provider request timed out",
                retryable=True,
            ) from exc
        except APIStatusError as exc:
            error_body = _extract_error_body(exc)
            raise LLMProviderError(
                f"LLM provider request failed with status {exc.status_code}: "
                f"{error_body}",
                retryable=exc.status_code == 429 or exc.status_code >= 500,
            ) from exc
        except OpenAIError as exc:
            raise LLMProviderError(
                "LLM provider request failed", retryable=True
            ) from exc
        except ValidationError as exc:
            raise LLMProviderError(
                "LLM provider returned invalid response schema",
                retryable=False,
            ) from exc


def _extract_error_body(exc: APIStatusError) -> str:
    if isinstance(exc.body, dict):
        error = exc.body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
        if error:
            return str(error)

    if exc.body:
        return str(exc.body)

    return "unknown error"
