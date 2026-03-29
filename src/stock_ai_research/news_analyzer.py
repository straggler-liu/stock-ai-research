"""News analyzer: orchestrates news fetching + LLM analysis."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm_client import LLMClient
from .news_fetcher import NewsFetcher

_VALID_SENTIMENTS = {"bullish", "bearish", "neutral"}
_VALID_RISKS = {"low", "medium", "high"}

_PROMPT_TEMPLATE = """\
You are a financial news analyst. Analyze the following news articles about {subject} \
and return ONLY a JSON object — no prose, no markdown fences, no explanation.

Articles:
{articles_block}

Return this exact JSON structure:
{{
  "sentiment": "bullish" | "bearish" | "neutral",
  "key_points": ["<point 1>", "<point 2>", "<point 3>"],
  "risk_level": "low" | "medium" | "high",
  "summary": "<one sentence overall summary>"
}}

Rules:
- sentiment: overall market/stock sentiment derived from the articles
- key_points: exactly 3 most important takeaways
- risk_level: investor risk level implied by these articles
- summary: a single concise sentence
- Do NOT include any text outside the JSON object
"""


@dataclass
class NewsAnalysis:
    symbol: str
    sentiment: str = "neutral"          # "bullish" | "bearish" | "neutral"
    key_points: list[str] = field(default_factory=list)   # always length 3
    risk_level: str = "medium"          # "low" | "medium" | "high"
    summary: str = ""
    articles: list[dict] = field(default_factory=list)
    provider: str = ""
    error: str = ""                     # non-empty means analysis failed


class NewsAnalyzer:
    """Orchestrates news fetching and LLM sentiment analysis."""

    def __init__(self, llm: LLMClient, fetcher: NewsFetcher | None = None) -> None:
        self._llm = llm
        self._fetcher = fetcher or NewsFetcher()

    def analyze_symbol(self, symbol: str) -> NewsAnalysis:
        """Fetch and analyze news for a specific symbol."""
        articles = self._fetcher.fetch_symbol(symbol)
        if not articles:
            return NewsAnalysis(
                symbol=symbol,
                provider=self._llm.provider,
                error="No articles found",
            )
        return self._run_analysis(symbol, articles)

    def analyze_market(self) -> NewsAnalysis:
        """Fetch and analyze broad market news."""
        articles = self._fetcher.fetch_market()
        if not articles:
            return NewsAnalysis(
                symbol="MARKET",
                provider=self._llm.provider,
                error="No articles found",
            )
        return self._run_analysis("MARKET", articles)

    def _run_analysis(self, symbol: str, articles: list[dict]) -> NewsAnalysis:
        articles_block = "\n\n".join(
            f"[{i + 1}] Title: {a['title']}\n"
            f"    Summary: {a['summary']}\n"
            f"    Source: {a['source']} | Published: {a['published_at']}"
            for i, a in enumerate(articles[:5])
        )
        subject = f"stock {symbol}" if symbol != "MARKET" else "the overall market"
        prompt = _PROMPT_TEMPLATE.format(subject=subject, articles_block=articles_block)
        raw = self._llm.analyze(prompt)
        return self._parse(symbol, raw, articles)

    def _parse(self, symbol: str, raw: str, articles: list[dict]) -> NewsAnalysis:
        base = NewsAnalysis(symbol=symbol, articles=articles, provider=self._llm.provider)

        if not raw:
            base.error = "LLM returned empty response"
            return base

        # Try direct parse, then fallback to substring extraction
        data: dict | None = None
        text = raw.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    pass

        if data is None:
            base.error = "LLM returned unparseable output"
            return base

        raw_sentiment = data.get("sentiment", "neutral")
        base.sentiment = raw_sentiment if raw_sentiment in _VALID_SENTIMENTS else "neutral"

        pts = data.get("key_points", [])
        if not isinstance(pts, list):
            pts = []
        # Pad or truncate to exactly 3 items
        base.key_points = (list(pts) + ["", "", ""])[:3]

        raw_risk = data.get("risk_level", "medium")
        base.risk_level = raw_risk if raw_risk in _VALID_RISKS else "medium"

        base.summary = str(data.get("summary", ""))
        return base
