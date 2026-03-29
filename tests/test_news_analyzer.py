"""Tests for NewsAnalyzer — verifies orchestration, JSON parsing, and error handling."""
from __future__ import annotations

import json

import pytest

from stock_ai_research.news_analyzer import NewsAnalysis, NewsAnalyzer

_SAMPLE_ARTICLES = [
    {
        "title": "AAPL beats earnings",
        "summary": "Apple exceeded analyst expectations with strong iPhone sales.",
        "source": "Reuters",
        "url": "https://reuters.com/1",
        "published_at": "Sun, 29 Mar 2026 09:00:00 +0000",
    },
    {
        "title": "Apple raises guidance",
        "summary": "Management raised full-year guidance citing services growth.",
        "source": "CNBC",
        "url": "https://cnbc.com/2",
        "published_at": "Sun, 29 Mar 2026 08:00:00 +0000",
    },
]

_VALID_RESPONSE = json.dumps(
    {
        "sentiment": "bullish",
        "key_points": ["Strong earnings beat", "Revenue up 8%", "Guidance raised"],
        "risk_level": "low",
        "summary": "Apple reported strong Q2 results beating all expectations.",
    }
)


class FakeFetcher:
    def __init__(self, articles: list[dict]) -> None:
        self._articles = articles

    def fetch_symbol(self, _symbol: str) -> list[dict]:
        return list(self._articles)

    def fetch_market(self) -> list[dict]:
        return list(self._articles)


class FakeLLM:
    def __init__(self, response: str, provider: str = "openai") -> None:
        self._response = response
        self.provider = provider
        self.model = "gpt-4o-mini"

    def analyze(self, _prompt: str) -> str:
        return self._response


# ── Happy path ────────────────────────────────────────────────────────────────

def test_analyze_symbol_happy_path():
    result = NewsAnalyzer(FakeLLM(_VALID_RESPONSE), FakeFetcher(_SAMPLE_ARTICLES)).analyze_symbol("AAPL")
    assert isinstance(result, NewsAnalysis)
    assert result.symbol == "AAPL"
    assert result.sentiment == "bullish"
    assert result.risk_level == "low"
    assert len(result.key_points) == 3
    assert result.key_points[0] == "Strong earnings beat"
    assert result.error == ""
    assert len(result.articles) == 2


# ── No articles ───────────────────────────────────────────────────────────────

def test_analyze_symbol_no_articles():
    result = NewsAnalyzer(FakeLLM(_VALID_RESPONSE), FakeFetcher([])).analyze_symbol("AAPL")
    assert result.error == "No articles found"
    assert result.sentiment == "neutral"  # safe default


# ── LLM failures ─────────────────────────────────────────────────────────────

def test_analyze_llm_empty_response():
    result = NewsAnalyzer(FakeLLM(""), FakeFetcher(_SAMPLE_ARTICLES)).analyze_symbol("AAPL")
    assert result.error == "LLM returned empty response"


def test_analyze_llm_unparseable():
    result = NewsAnalyzer(
        FakeLLM("I cannot analyze this right now. Please try again."),
        FakeFetcher(_SAMPLE_ARTICLES),
    ).analyze_symbol("AAPL")
    assert result.error == "LLM returned unparseable output"


# ── JSON embedded in prose (substring extraction) ─────────────────────────────

def test_analyze_llm_embedded_json():
    wrapped = f"Sure! Here is the analysis:\n{_VALID_RESPONSE}\n\nHope that helps!"
    result = NewsAnalyzer(FakeLLM(wrapped), FakeFetcher(_SAMPLE_ARTICLES)).analyze_symbol("AAPL")
    assert result.sentiment == "bullish"
    assert result.error == ""


# ── Invalid enum values clamped to defaults ───────────────────────────────────

def test_analyze_invalid_enum_values():
    bad = json.dumps(
        {
            "sentiment": "very_bullish",
            "key_points": ["point a"],
            "risk_level": "extreme",
            "summary": "test",
        }
    )
    result = NewsAnalyzer(FakeLLM(bad), FakeFetcher(_SAMPLE_ARTICLES)).analyze_symbol("AAPL")
    assert result.sentiment == "neutral"
    assert result.risk_level == "medium"


# ── key_points always length 3 ───────────────────────────────────────────────

def test_key_points_padded_to_three():
    short = json.dumps(
        {"sentiment": "neutral", "key_points": ["only one"], "risk_level": "low", "summary": "ok"}
    )
    result = NewsAnalyzer(FakeLLM(short), FakeFetcher(_SAMPLE_ARTICLES)).analyze_symbol("AAPL")
    assert len(result.key_points) == 3
    assert result.key_points[1] == ""
    assert result.key_points[2] == ""


# ── Market analysis ───────────────────────────────────────────────────────────

def test_analyze_market():
    result = NewsAnalyzer(FakeLLM(_VALID_RESPONSE), FakeFetcher(_SAMPLE_ARTICLES)).analyze_market()
    assert result.symbol == "MARKET"
    assert result.sentiment == "bullish"


# ── Provider propagated ───────────────────────────────────────────────────────

def test_provider_in_result():
    result = NewsAnalyzer(
        FakeLLM(_VALID_RESPONSE, provider="gemini"), FakeFetcher(_SAMPLE_ARTICLES)
    ).analyze_symbol("AAPL")
    assert result.provider == "gemini"
