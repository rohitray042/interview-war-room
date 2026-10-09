"""Gemini REST transport; application contracts and evidence validation stay shared."""

import json
import re

import httpx

from app.contracts import LLMResult, ProviderUnavailable
from app.providers import HTTPProvider


def gemini_schema(schema):
    """Inline local references and emit the native Gemini Schema subset.

    String constraints remain enforced by the original application models.
    """
    definitions = schema.get("$defs", {})
    supported = {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "anyOf",
        "minimum",
        "maximum",
        "description",
        "nullable",
    }

    def convert(node, resolving=()):
        if isinstance(node, list):
            return [convert(item, resolving) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/$defs/") or ref in resolving:
                raise ValueError("Unsupported schema reference")
            target = definitions[ref.removeprefix("#/$defs/")]
            return convert(
                {**target, **{k: v for k, v in node.items() if k != "$ref"}}, (*resolving, ref)
            )
        if "anyOf" in node:
            variants = node["anyOf"]
            non_null = [item for item in variants if item.get("type") != "null"]
            if len(non_null) == 1 and len(non_null) != len(variants):
                return {**convert(non_null[0], resolving), "nullable": True}
        return {
            key: (
                {name: convert(value, resolving) for name, value in item.items()}
                if key == "properties"
                else convert(item, resolving)
            )
            for key, item in node.items()
            if key in supported
        }

    return convert(schema)


class GeminiProvider(HTTPProvider):
    provider_name = "gemini"

    async def _generate(self, request, event):
        model = self.settings.llm_model
        key = self.settings.llm_api_key.get_secret_value()
        if not key or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", model):
            raise ProviderUnavailable("Gemini configuration is incomplete or invalid")
        try:
            async with httpx.AsyncClient(timeout=9, transport=self.transport) as client:
                response = await self._post(
                    client,
                    event,
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key},
                    json={
                        "systemInstruction": {"parts": [{"text": request.instructions}]},
                        "contents": [{"role": "user", "parts": [{"text": request.context}]}],
                        "generationConfig": {
                            "candidateCount": 1,
                            "maxOutputTokens": 10000,
                            "responseMimeType": "application/json",
                            "responseSchema": gemini_schema(request.output_schema),
                        },
                    },
                )
            response.raise_for_status()
            body = response.json()
            usage = body.get("usageMetadata") or {}
            for source, target in (
                ("promptTokenCount", "input_tokens"),
                ("candidatesTokenCount", "output_tokens"),
            ):
                value = usage.get(source)
                if type(value) is int and value >= 0:
                    event[target] = value
            candidates = body.get("candidates", [])
            if body.get("promptFeedback", {}).get("blockReason") or len(candidates) != 1:
                raise ValueError("Blocked or missing output")
            candidate = candidates[0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("Incomplete output")
            parts = candidate["content"]["parts"]
            output = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
            return LLMResult(
                data=json.loads(output),
                provider="gemini",
                model=model,
                request_id=body.get("responseId", ""),
            )
        except httpx.HTTPError:
            raise ProviderUnavailable(
                "Gemini request failed. Check model access and quota."
            ) from None
        except AttributeError, KeyError, TypeError, ValueError:
            raise ValueError("Gemini response was invalid, incomplete or refused") from None
