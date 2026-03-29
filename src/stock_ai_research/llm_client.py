"""LLM client supporting OpenAI, Claude (Anthropic), Gemini, and DeepSeek.

All HTTP calls use stdlib urllib.request — no external dependencies.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_PROVIDERS: dict[str, dict] = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
    "claude": {
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-haiku-4-5-20251001",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model": "gemini-2.0-flash",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-chat",
    },
}


class LLMClient:
    """Unified LLM client for 4 providers.

    Usage::

        client = LLMClient("openai", "sk-...")
        text = client.analyze("Summarize this news: ...")
    """

    def __init__(self, provider: str, api_key: str, timeout: int = 30) -> None:
        if provider not in _PROVIDERS:
            raise ValueError(f"Unknown provider: {provider!r}. Choose from {list(_PROVIDERS)}")
        self._provider = provider
        self._api_key = api_key
        self._timeout = timeout
        self._cfg = _PROVIDERS[provider]

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._cfg["model"]

    def analyze(self, prompt: str) -> str:
        """Call the LLM and return the text response.

        Returns empty string on any failure (network error, auth error, parse error).
        Never raises an exception.
        """
        try:
            url, body, headers = self._build_request(prompt)
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                response_data = json.loads(resp.read())
            return self._parse_response(response_data)
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError,
                json.JSONDecodeError, OSError, ValueError):
            return ""

    def _build_request(self, prompt: str) -> tuple[str, dict, dict]:
        """Returns (url, body_dict, headers_dict)."""
        p = self._provider
        if p in ("openai", "deepseek"):
            return (
                self._cfg["url"],
                {
                    "model": self._cfg["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 800,
                },
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
            )
        if p == "claude":
            return (
                self._cfg["url"],
                {
                    "model": self._cfg["model"],
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": prompt}],
                },
                {
                    "Content-Type": "application/json",
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
        if p == "gemini":
            url = f"{self._cfg['url']}?key={urllib.parse.quote(self._api_key, safe='')}"
            return (
                url,
                {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800},
                },
                {"Content-Type": "application/json"},
            )
        raise ValueError(f"Unhandled provider: {p}")  # unreachable

    def _parse_response(self, data: dict) -> str:
        p = self._provider
        if p in ("openai", "deepseek"):
            return data["choices"][0]["message"]["content"]
        if p == "claude":
            return data["content"][0]["text"]
        if p == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return ""


# ── Settings helpers ──────────────────────────────────────────────────────────

_DEFAULT_SETTINGS: dict = {
    "active_provider": "openai",
    "openai_key": "",
    "claude_key": "",
    "gemini_key": "",
    "deepseek_key": "",
}


def load_llm_settings(path: str = "configs/llm_settings.json") -> dict:
    """Load LLM settings from JSON file. Returns defaults if file missing or corrupt."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULT_SETTINGS)


def save_llm_settings(data: dict, path: str = "configs/llm_settings.json") -> None:
    """Save LLM settings to JSON file."""
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def client_from_settings(settings: dict) -> LLMClient:
    """Create an LLMClient from a settings dict."""
    provider = settings.get("active_provider", "openai")
    key_map = {
        "openai": "openai_key",
        "claude": "claude_key",
        "gemini": "gemini_key",
        "deepseek": "deepseek_key",
    }
    api_key = settings.get(key_map.get(provider, ""), "")
    return LLMClient(provider, api_key)
