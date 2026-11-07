"""Unit tests for GeminiClient."""

import json
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from src.agents.gemini_client import GeminiClient, clean_json_response
from src.core.config import get_settings


def test_clean_json_response_no_fence():
    raw = '{"key": "value"}'
    assert clean_json_response(raw) == '{"key": "value"}'


def test_clean_json_response_with_markdown_fences():
    raw = "```json\n[{\"id\": 1, \"name\": \"vuln\"}]\n```"
    assert clean_json_response(raw) == '[{"id": 1, "name": "vuln"}]'


def test_clean_json_response_with_generic_fence():
    raw = "```\n{\"severity\": \"HIGH\"}\n```"
    assert clean_json_response(raw) == '{"severity": "HIGH"}'


def test_gemini_client_init_defaults():
    settings = get_settings()
    client = GeminiClient(api_key="test-key")
    assert client.api_key == "test-key"
    assert client.model_name == settings.gemini_model
    assert client.temperature == settings.gemini_temperature
    assert client.timeout == settings.agent_timeout_seconds
    assert client.max_retries == settings.gemini_max_retries


def test_gemini_client_missing_key_raises_value_error():
    client = GeminiClient(api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured in environment"):
        import asyncio
        asyncio.run(client.generate_structured_review("prompt", "system instruction"))


@pytest.mark.asyncio
async def test_generate_structured_review_success():
    expected_findings = [
        {
            "id": "FINDING-1",
            "title": "SQL Injection",
            "severity": "CRITICAL",
        }
    ]

    mock_response_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": f"```json\n{json.dumps(expected_findings)}\n```"
                        }
                    ]
                },
                "finishReason": "STOP",
            }
        ]
    }

    def custom_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response_payload)

    mock_http_client = httpx.AsyncClient(transport=httpx.MockTransport(custom_transport))
    client = GeminiClient(api_key="valid-dummy-key", client=mock_http_client)

    result = await client.generate_structured_review("Analyze this code", "You are an auditor")
    assert result == expected_findings


@pytest.mark.asyncio
async def test_generate_structured_review_retries_on_429():
    attempts = 0
    expected_findings = [{"id": "RETRY-OK", "title": "Recovered"}]

    def rate_limit_then_succeed(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, json={"error": {"message": "Resource has been exhausted"}})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(expected_findings)}]
                        }
                    }
                ]
            },
        )

    mock_http_client = httpx.AsyncClient(transport=httpx.MockTransport(rate_limit_then_succeed))
    client = GeminiClient(
        api_key="valid-dummy-key",
        max_retries=3,
        retry_delay=0.001,
        client=mock_http_client,
    )

    result = await client.generate_structured_review("Analyze this code", "You are an auditor")
    assert attempts == 3
    assert result == expected_findings


@pytest.mark.asyncio
async def test_generate_structured_review_exhausted_retries_raises():
    def always_503(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "Service Unavailable"}})

    mock_http_client = httpx.AsyncClient(transport=httpx.MockTransport(always_503))
    client = GeminiClient(
        api_key="valid-dummy-key",
        max_retries=2,
        retry_delay=0.001,
        client=mock_http_client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.generate_structured_review("Analyze this code", "You are an auditor")


@pytest.mark.asyncio
async def test_generate_structured_review_invalid_json():
    def returns_bad_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Not valid JSON payload here {"}]
                        }
                    }
                ]
            },
        )

    mock_http_client = httpx.AsyncClient(transport=httpx.MockTransport(returns_bad_json))
    client = GeminiClient(api_key="valid-dummy-key", client=mock_http_client)

    with pytest.raises(ValueError, match="Failed to parse structured JSON"):
        await client.generate_structured_review("Analyze this code", "You are an auditor")


@pytest.mark.asyncio
async def test_generate_structured_review_empty_candidates():
    def returns_empty_candidates(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})

    mock_http_client = httpx.AsyncClient(transport=httpx.MockTransport(returns_empty_candidates))
    client = GeminiClient(api_key="valid-dummy-key", client=mock_http_client)

    with pytest.raises(RuntimeError, match="No candidates returned"):
        await client.generate_structured_review("Analyze this code", "You are an auditor")

