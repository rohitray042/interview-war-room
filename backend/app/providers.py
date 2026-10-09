"""Optional Responses adapter; provider transport stays out of business logic."""

import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime

import httpx

from app.contracts import DisabledProvider, LLMResult, ProviderUnavailable


class HTTPProvider:
    provider_name = ""

    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport
        self.last_status = "unverified"

    @property
    def safe_model(self):
        model = self.settings.llm_model
        if (
            re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", model)
            and not model.startswith(("sk-", "AIza"))
            and model != self.settings.llm_api_key.get_secret_value()
        ):
            return model
        return "configured"

    async def generate_structured(self, request):
        started = time.monotonic()
        event = {
            "provider": self.provider_name,
            "model": self.safe_model,
            "operation": request.task,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "failure",
            "attempts": 0,
        }
        try:
            async with asyncio.timeout(20):
                result = await self._generate(request, event)
            self.last_status = "connected"
            event["status"] = "success"
            return result
        except TimeoutError:
            self.last_status = "unavailable"
            raise ProviderUnavailable("AI request timed out. Try again.") from None
        except BaseException:
            self.last_status = "unavailable"
            raise
        finally:
            event["latency_ms"] = round((time.monotonic() - started) * 1000)
            logging.getLogger("war_room.ai").info("%s", json.dumps(event))

    async def _post(self, client, event, *args, **kwargs):
        for attempt in range(2):
            event["attempts"] += 1
            try:
                response = await client.post(*args, **kwargs)
            except httpx.TimeoutException, httpx.NetworkError:
                if attempt:
                    raise
                await asyncio.sleep(0.5)
                continue
            if response.status_code in {401, 403}:
                raise ProviderUnavailable(
                    "AI provider authentication failed. Check server configuration."
                )
            if response.status_code in {408, 429, 500, 502, 503, 504} and not attempt:
                await asyncio.sleep(0.5)
                continue
            return response


class OpenAIProvider(HTTPProvider):
    provider_name = "openai"

    async def _generate(self, request, event):
        key = self.settings.llm_api_key.get_secret_value()
        if not key or not self.settings.llm_model:
            raise ProviderUnavailable("Provider configuration is incomplete")
        try:
            async with httpx.AsyncClient(timeout=9, transport=self.transport) as client:
                response = await self._post(
                    client,
                    event,
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": "Bearer " + key},
                    json={
                        "model": self.settings.llm_model,
                        "store": False,
                        "instructions": request.instructions,
                        "input": request.context,
                        "max_output_tokens": 10000,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": request.task,
                                "strict": True,
                                "schema": strict_schema(request.output_schema),
                            }
                        },
                    },
                )
            response.raise_for_status()
            body = response.json()
            usage = body.get("usage") or {}
            for name in ("input_tokens", "output_tokens"):
                value = usage.get(name)
                if type(value) is int and value >= 0:
                    event[name] = value
            if body.get("status") != "completed":
                raise ValueError("Incomplete response")
            if any(
                c.get("type") == "refusal"
                for item in body.get("output", [])
                for c in item.get("content", [])
            ):
                raise ValueError("Refused response")
            chunks = [
                c["text"]
                for item in body.get("output", [])
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            ]
            data = json.loads("".join(chunks))
            return LLMResult(
                data=data,
                provider="openai",
                model=self.settings.llm_model,
                request_id=body.get("id", ""),
            )
        except httpx.HTTPError:
            raise ProviderUnavailable("Provider request failed") from None
        except AttributeError, KeyError, TypeError, ValueError:
            raise ValueError("Provider response was invalid or refused") from None


def strict_schema(value):
    if isinstance(value, list):
        return [strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: strict_schema(item) for key, item in value.items() if key != "default"}
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


def make_provider(settings):
    if settings.llm_provider == "gemini":
        from app.gemini_provider import GeminiProvider

        if settings.gemini_model and settings.gemini_api_key.get_secret_value():
            return GeminiProvider(
                settings.model_copy(
                    update={
                        "llm_model": settings.gemini_model,
                        "llm_api_key": settings.gemini_api_key,
                    }
                )
            )
    if settings.llm_provider == "openai":
        model = settings.openai_model or settings.llm_model
        key = (
            settings.openai_api_key
            if settings.openai_api_key.get_secret_value()
            else settings.llm_api_key
        )
        if model and key.get_secret_value():
            return OpenAIProvider(
                settings.model_copy(update={"llm_model": model, "llm_api_key": key})
            )
    return DisabledProvider()
