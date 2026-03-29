"""Tests for NewsFetcher — verifies RSS parsing and symbol mapping."""
from __future__ import annotations

import urllib.error

from stock_ai_research.news_fetcher import NewsFetcher, _yahoo_symbol

_SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Yahoo Finance</title>
    <item>
      <title>Apple Posts Record Revenue</title>
      <link>https://finance.yahoo.com/news/apple-1</link>
      <description>Apple Inc reported &lt;b&gt;record&lt;/b&gt; quarterly revenue of $120B.</description>
      <pubDate>Sun, 29 Mar 2026 09:00:00 +0000</pubDate>
      <source url="https://reuters.com">Reuters</source>
    </item>
    <item>
      <title>Market Outlook Positive</title>
      <link>https://finance.yahoo.com/news/outlook-2</link>
      <description>Analysts remain optimistic about tech sector growth.</description>
      <pubDate>Sun, 29 Mar 2026 08:00:00 +0000</pubDate>
      <source url="https://cnbc.com">CNBC</source>
    </item>
  </channel>
</rss>"""


class DummyResp:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# ── RSS parsing ───────────────────────────────────────────────────────────────

def test_fetch_symbol_parses_rss(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=0: DummyResp(_SAMPLE_RSS)
    )
    fetcher = NewsFetcher()
    articles = fetcher.fetch_symbol("AAPL")

    assert len(articles) == 2
    assert articles[0]["title"] == "Apple Posts Record Revenue"
    assert "<b>" not in articles[0]["summary"]  # HTML stripped
    assert "&lt;" not in articles[0]["summary"]  # HTML entities unescaped
    assert articles[0]["source"] == "Reuters"
    assert "finance.yahoo.com" in articles[0]["url"]


# ── HK symbol mapping ─────────────────────────────────────────────────────────

def test_fetch_symbol_hk_converts_ticker(monkeypatch):
    captured_url: list[str] = []

    def fake_urlopen(req, timeout=0):
        captured_url.append(req.full_url)
        return DummyResp(_SAMPLE_RSS)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    NewsFetcher().fetch_symbol("00700")
    assert captured_url, "Expected an HTTP call"
    assert "700.HK" in captured_url[0]


# ── A-share returns empty without HTTP call ───────────────────────────────────

def test_fetch_symbol_a_share_returns_empty(monkeypatch):
    called: list = []
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **kw: called.append(1)
    )
    result = NewsFetcher().fetch_symbol("600519")
    assert result == []
    assert not called  # no HTTP call made


def test_fetch_symbol_etf_returns_empty(monkeypatch):
    called: list = []
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **kw: called.append(1)
    )
    assert NewsFetcher().fetch_symbol("513310") == []
    assert not called


# ── Network error ─────────────────────────────────────────────────────────────

def test_fetch_network_error_returns_empty(monkeypatch):
    def raise_err(*args, **kwargs):
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr("urllib.request.urlopen", raise_err)
    assert NewsFetcher().fetch_symbol("AAPL") == []


# ── Market fallback to Reuters ────────────────────────────────────────────────

def test_fetch_market_fallback_to_reuters(monkeypatch):
    call_count = [0]

    def fake_urlopen(req, timeout=0):
        call_count[0] += 1
        if call_count[0] == 1:
            raise urllib.error.URLError("Yahoo down")
        return DummyResp(_SAMPLE_RSS)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    articles = NewsFetcher().fetch_market()
    assert call_count[0] == 2  # tried Yahoo, fell back to Reuters
    assert len(articles) > 0


# ── _yahoo_symbol unit tests ──────────────────────────────────────────────────

def test_yahoo_symbol_mapping():
    assert _yahoo_symbol("AAPL") == "AAPL"
    assert _yahoo_symbol("MSFT") == "MSFT"
    assert _yahoo_symbol("00700") == "700.HK"
    assert _yahoo_symbol("01810") == "1810.HK"
    assert _yahoo_symbol("600519") is None
    assert _yahoo_symbol("513310") is None
