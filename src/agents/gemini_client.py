"""Google Gemini API client with schema enforcement and retry resilience."""

import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Union
import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)

# Global rate-limiting state to pace requests within API tier bounds
_last_request_time: float = 0.0
_throttle_lock: Optional[asyncio.Lock] = None


def _get_throttle_lock() -> asyncio.Lock:
    global _throttle_lock
    if _throttle_lock is None:
        _throttle_lock = asyncio.Lock()
    return _throttle_lock


async def _throttle_request(interval: float = 4.0) -> None:
    """Enforce a minimum spacing between outbound API requests to avoid rate limits."""
    if interval <= 0.0:
        return
    global _last_request_time
    lock = _get_throttle_lock()
    async with lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        _last_request_time = time.monotonic()


def clean_json_response(text: str) -> str:
    """Strip markdown code fence blocks and extraneous whitespace around JSON payload."""
    cleaned = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    return cleaned


class GeminiClient:
    """Asynchronous client for Google Gemini API with JSON enforcement and retry resilience."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_delay: float = 1.0,
        request_interval: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model_name = model_name or settings.gemini_model
        self.temperature = temperature if temperature is not None else settings.gemini_temperature
        self.timeout = timeout if timeout is not None else settings.agent_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.gemini_max_retries
        self.retry_delay = retry_delay
        self.request_interval = (
            request_interval
            if request_interval is not None
            else getattr(settings, "gemini_request_interval", 4.0)
        )
        self._client = client

    async def generate_structured_review(
        self,
        prompt: str,
        system_instruction: str,
    ) -> Union[Dict[str, Any], List[Any]]:
        """Send asynchronous structured review request to Gemini and return parsed JSON."""
        if not self.api_key or not self.api_key.strip():
            # Dynamically reload from settings / environment / .env
            fresh_settings = get_settings()
            self.api_key = fresh_settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
            if not self.api_key or not self.api_key.strip():
                from src.core.config import reload_settings
                self.api_key = reload_settings().gemini_api_key

        if not self.api_key or not self.api_key.strip():
            raise ValueError("GEMINI_API_KEY is not configured in environment")

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent?key={self.api_key}"
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "system_instruction": {
                "parts": [{"text": system_instruction}],
            },
            "generationConfig": {
                "temperature": self.temperature,
                "response_mime_type": "application/json",
            },
        }

        async def _execute_post(http_client: httpx.AsyncClient) -> httpx.Response:
            nonlocal endpoint
            last_response: Optional[httpx.Response] = None
            last_exc: Optional[Exception] = None

            for attempt in range(self.max_retries + 1):
                try:
                    await _throttle_request(self.request_interval)
                    response = await http_client.post(
                        endpoint,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                    # Check for model not found to dynamically fallback
                    if response.status_code == 404 and self.model_name != "gemini-3.5-flash-lite":
                        logger.warning(
                            "Model %s returned 404. Falling back to gemini-3.5-flash-lite...",
                            self.model_name,
                        )
                        self.model_name = "gemini-3.5-flash-lite"
                        endpoint = (
                            f"https://generativelanguage.googleapis.com/v1beta/models/"
                            f"{self.model_name}:generateContent?key={self.api_key}"
                        )
                        continue

                    # Check for rate limit (429) - wait for quota window to reset
                    if response.status_code == 429:
                        last_response = response
                        if attempt < self.max_retries:
                            retry_after = response.headers.get("Retry-After")
                            if retry_after:
                                try:
                                    backoff = float(retry_after)
                                except (ValueError, TypeError):
                                    backoff = 15.0 * (attempt + 1) + random.uniform(1.0, 5.0)
                            else:
                                backoff = 15.0 * (attempt + 1) + random.uniform(1.0, 5.0)
                            logger.warning(
                                "Gemini API rate limit reached (429). Retrying in %.1fs (attempt %d/%d)...",
                                backoff,
                                attempt + 1,
                                self.max_retries,
                            )
                            await asyncio.sleep(backoff)
                            continue

                    # Check for server error (503) to retry
                    if response.status_code == 503:
                        last_response = response
                        if attempt < self.max_retries:
                            backoff = self.retry_delay * (2 ** attempt)
                            logger.warning(
                                "Gemini API returned status %d. Retrying in %.2fs (attempt %d/%d)...",
                                response.status_code,
                                backoff,
                                attempt + 1,
                                self.max_retries,
                            )
                            await asyncio.sleep(backoff)
                            continue

                    response.raise_for_status()
                    return response

                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    if attempt < self.max_retries:
                        backoff = self.retry_delay * (2 ** attempt)
                        logger.warning(
                            "Network error calling Gemini API: %s. Retrying in %.2fs...",
                            exc,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    raise

            if last_response is not None:
                last_response.raise_for_status()
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("Exceeded maximum retries calling Gemini API")

        if self._client is not None:
            response = await _execute_post(self._client)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await _execute_post(client)

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            feedback = data.get("promptFeedback", {})
            raise RuntimeError(f"No candidates returned by Gemini API. Feedback: {feedback}")

        first_candidate = candidates[0]
        content_parts = first_candidate.get("content", {}).get("parts", [])
        if not content_parts:
            finish_reason = first_candidate.get("finishReason", "UNKNOWN")
            raise RuntimeError(f"Candidate contains no content parts (finishReason: {finish_reason})")

        raw_text = content_parts[0].get("text", "")
        cleaned_text = clean_json_response(raw_text)

        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError as exc:
            try:
                import json_repair
                repaired = json_repair.loads(cleaned_text)
                if repaired is not None and isinstance(repaired, (list, dict)):
                    logger.info("Successfully repaired malformed Gemini JSON with json_repair.")
                    return repaired
            except Exception:
                pass
            logger.error("Failed to parse Gemini response as JSON: %s\nRaw: %s", exc, raw_text)
            raise ValueError(f"Failed to parse structured JSON from Gemini response: {exc}") from exc

