"""Tests for LLMClient — verifies request format for all 4 providers."""
from __future__ import annotations

import json
import urllib.error

import pytest

from stock_ai_research.llm_client import LLMClient, client_from_settings, load_llm_settings


class DummyResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# ── OpenAI ───────────────────────────────────────────────────────────────────

def test_openai_request_format(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data)
        body = {"choices": [{"message": {"content": "openai response"}}]}
        return DummyResp(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = LLMClient("openai", "sk-test")
    result = client.analyze("hello")

    assert "api.openai.com" in captured["url"]
    assert captured["headers"].get("Authorization") == "Bearer sk-test"
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["messages"][0]["content"] == "hello"
    assert result == "openai response"


# ── Claude ───────────────────────────────────────────────────────────────────

def test_claude_request_format(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data)
        body = {"content": [{"text": "claude response"}]}
        return DummyResp(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = LLMClient("claude", "claude-key-test")
    result = client.analyze("hello")

    assert "api.anthropic.com" in captured["url"]
    # urllib capitalizes first letter of header names
    assert captured["headers"].get("X-api-key") == "claude-key-test"
    assert captured["body"]["model"] == "claude-haiku-4-5-20251001"
    assert result == "claude response"


# ── Gemini ───────────────────────────────────────────────────────────────────

def test_gemini_request_format(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        body = {"candidates": [{"content": {"parts": [{"text": "gemini response"}]}}]}
        return DummyResp(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = LLMClient("gemini", "gemini-key-test")
    result = client.analyze("test prompt")

    assert "generativelanguage.googleapis.com" in captured["url"]
    assert "gemini-key-test" in captured["url"]  # key in query param
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "test prompt"
    assert result == "gemini response"


# ── DeepSeek ─────────────────────────────────────────────────────────────────

def test_deepseek_uses_openai_schema(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        body = {"choices": [{"message": {"content": "deepseek response"}}]}
        return DummyResp(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = LLMClient("deepseek", "ds-key")
    result = client.analyze("question")

    assert "deepseek.com" in captured["url"]
    assert captured["body"]["model"] == "deepseek-chat"
    assert captured["body"]["messages"][0]["content"] == "question"
    assert result == "deepseek response"


# ── Error handling ────────────────────────────────────────────────────────────

def test_network_error_returns_empty(monkeypatch):
    def raise_url_error(*args, **kwargs):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    client = LLMClient("openai", "key")
    assert client.analyze("x") == ""


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        LLMClient("badprovider", "key")


# ── client_from_settings ─────────────────────────────────────────────────────

def test_client_from_settings_selects_correct_provider():
    settings = {
        "active_provider": "deepseek",
        "deepseek_key": "ds-secret",
    }
    client = client_from_settings(settings)
    assert client.provider == "deepseek"
    assert client.model == "deepseek-chat"
