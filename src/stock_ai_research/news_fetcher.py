"""News fetcher using Yahoo Finance RSS (no API key required).

Supports US stocks and HK stocks. A-shares and ETFs (6-digit codes) are
not covered by Yahoo Finance RSS and return an empty list.
"""
from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

_YAHOO_RSS = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s={symbol}&region=US&lang=en-US"
)
_MARKET_RSS = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s=%5EGSPC,%5EIXIC&region=US&lang=en-US"
)
_REUTERS_RSS = "https://feeds.reuters.com/reuters/businessNews"

_USER_AGENT = "Mozilla/5.0 (stock-ai-research/1.0)"


def _yahoo_symbol(symbol: str) -> str | None:
    """Map internal symbol to Yahoo Finance ticker.

    Returns None if the symbol is not supported (A-share, ETF, etc.).
    """
    s = symbol.strip().upper()
    if re.fullmatch(r"[A-Z]{1,6}", s):
        return s  # US stock — use as-is
    if re.fullmatch(r"\d{5}", s):
        # HK stock: strip leading zeros, append .HK  ("00700" → "700.HK")
        return str(int(s)) + ".HK"
    # 6-digit A-shares or ETFs — not supported
    return None


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    return re.sub(r"<[^>]+>", "", text).strip()


def _domain(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1) if m else ""


def _parse_rss(xml_bytes: bytes) -> list[dict]:
    """Parse RSS 2.0 XML bytes into a list of article dicts."""
    root = ET.fromstring(xml_bytes)
    articles: list[dict] = []
    for item in root.iter("item"):
        title = _strip_html((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        desc = _strip_html(item.findtext("description") or "")
        pub = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if (source_el is not None and source_el.text) else _domain(link)
        articles.append({
            "title": title,
            "summary": desc[:300],
            "source": source,
            "url": link,
            "published_at": pub,
        })
    return articles


class NewsFetcher:
    """Fetch financial news articles from free RSS feeds."""

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def fetch_symbol(self, symbol: str, max_articles: int = 5) -> list[dict]:
        """Fetch news for a specific symbol.

        Returns an empty list if the symbol is unsupported or on any network error.
        """
        ticker = _yahoo_symbol(symbol)
        if ticker is None:
            return []
        url = _YAHOO_RSS.format(symbol=urllib.parse.quote(ticker, safe=""))
        return self._fetch_rss(url, max_articles)

    def fetch_market(self, max_articles: int = 5) -> list[dict]:
        """Fetch broad market news (S&P 500 + Nasdaq). Falls back to Reuters."""
        articles = self._fetch_rss(_MARKET_RSS, max_articles)
        if not articles:
            articles = self._fetch_rss(_REUTERS_RSS, max_articles)
        return articles

    def _fetch_rss(self, url: str, max_articles: int) -> list[dict]:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": _USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
            return _parse_rss(raw)[:max_articles]
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError):
            return []
