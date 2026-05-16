from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable

import httpx
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.storage.database import json_dumps


class LLMTransientError(Exception):
    pass


class LLMFatalError(Exception):
    pass


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 3)


class DeepSeekClient:
    def __init__(self, settings: Settings | None = None, http_client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self._own_client = http_client is None
        self.http = http_client or httpx.Client(timeout=120.0)

    def close(self) -> None:
        if self._own_client:
            self.http.close()

    def _require_key(self) -> str:
        key = (self.settings.deepseek_api_key or "").strip()
        if not key:
            raise LLMFatalError("Missing DEEPSEEK_API_KEY")
        return key

    def generate_json(
        self,
        *,
        messages: list[dict[str, str]],
        response_format_model: type[BaseModel] | None = None,
        max_retries: int = 3,
        backoff_s: tuple[int, ...] = (1, 2, 4),
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Returns (parsed_dict, raw_meta) where raw_meta includes usage and content.
        """
        key = self._require_key()
        url = f"{self.settings.deepseek_base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.settings.deepseek_model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        prompt_for_hash = json_dumps({"messages": messages, "model": self.settings.deepseek_model})
        input_hash = hashlib.sha256(prompt_for_hash.encode("utf-8")).hexdigest()

        last_err: Exception | None = None
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            try:
                r = self.http.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                if r.status_code in (408, 409, 429) or 500 <= r.status_code <= 599:
                    raise LLMTransientError(f"HTTP {r.status_code}: {r.text[:500]}")
                if r.status_code == 401:
                    raise LLMFatalError("DeepSeek API unauthorized (check API key)")
                if r.status_code == 404:
                    raise LLMFatalError("DeepSeek API route not found (check base URL / model)")
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise LLMTransientError("Empty model content")
                parsed = json.loads(content)
                if response_format_model is not None:
                    response_format_model.model_validate(parsed)
                usage = data.get("usage") or {}
                meta = {
                    "input_hash": input_hash,
                    "latency_ms": latency_ms,
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "raw": data,
                    "parsed": parsed,
                }
                return parsed, meta
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = LLMTransientError(str(e))
            except json.JSONDecodeError as e:
                last_err = LLMTransientError(f"JSON decode error: {e}")
            except LLMTransientError as e:
                last_err = e
            except LLMFatalError:
                raise
            except Exception as e:
                last_err = e

            if attempt < max_retries - 1:
                sleep_for = backoff_s[min(attempt, len(backoff_s) - 1)]
                time.sleep(sleep_for)

        assert last_err is not None
        raise last_err


def get_deepseek_client() -> DeepSeekClient:
    return DeepSeekClient()
