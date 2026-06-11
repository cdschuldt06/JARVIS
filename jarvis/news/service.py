from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
import re
from time import monotonic
from urllib.error import URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from sqlalchemy.orm import Session

from jarvis.llm import OpenAIClient
from jarvis.research.service import ResearchService


RSS_CACHE_SECONDS = 20 * 60
MAX_FEED_ITEMS = 6


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    link: str
    published_at: str | None = None
    summary: str = ""


@dataclass(frozen=True)
class NewsResult:
    query: str
    provider: str
    summary: str
    items: list[NewsItem]
    sources: list[str]
    fallback_used: bool = False


class NewsProvider(ABC):
    name: str

    @abstractmethod
    def fetch(self, query: str) -> list[NewsItem]:
        raise NotImplementedError


class RSSNewsProvider(NewsProvider):
    name = "RSS news provider"

    feeds: tuple[tuple[str, str], ...] = (
        ("AP Top News", "https://apnews.com/hub/ap-top-news?output=rss"),
        ("Reuters Top News", "https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best"),
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("Hacker News", "https://hnrss.org/frontpage"),
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    )

    _cache: dict[str, tuple[float, list[NewsItem]]] = {}

    def fetch(self, query: str) -> list[NewsItem]:
        selected_feeds = self._feeds_for_query(query)
        cache_key = "|".join(url for _, url in selected_feeds)
        cached = self._cache.get(cache_key)
        if cached and monotonic() - cached[0] < RSS_CACHE_SECONDS:
            return cached[1]

        items: list[NewsItem] = []
        for source, url in selected_feeds:
            try:
                items.extend(self._fetch_feed(source, url))
            except (ET.ParseError, OSError, TimeoutError, URLError):
                continue

        deduped = self._dedupe(items)
        self._cache[cache_key] = (monotonic(), deduped)
        return deduped

    def _feeds_for_query(self, query: str) -> tuple[tuple[str, str], ...]:
        text = query.lower()
        if any(term in text for term in ("ai", "artificial intelligence", "tech", "technology", "hacker")):
            return tuple(feed for feed in self.feeds if feed[0] in {"TechCrunch AI", "Hacker News", "CNBC", "BBC World"})
        return self.feeds

    def _fetch_feed(self, source: str, url: str) -> list[NewsItem]:
        request = Request(url, headers={"User-Agent": "Jarvis/0.1 RSS reader"})
        with urlopen(request, timeout=8) as response:
            payload = response.read()
        root = ET.fromstring(payload)
        entries = root.findall(".//item") or root.findall("{http://www.w3.org/2005/Atom}entry")
        return [self._parse_entry(source, entry) for entry in entries[:MAX_FEED_ITEMS]]

    def _parse_entry(self, source: str, entry: ET.Element) -> NewsItem:
        title = self._text(entry, "title") or "Untitled"
        link = self._link(entry)
        summary = self._text(entry, "description") or self._text(entry, "summary")
        published = self._published(entry)
        return NewsItem(
            title=self._clean_text(title),
            source=source,
            link=link,
            published_at=published,
            summary=self._clean_text(summary)[:500],
        )

    def _text(self, entry: ET.Element, tag_name: str) -> str:
        found = entry.find(tag_name)
        if found is None:
            found = entry.find(f"{{http://www.w3.org/2005/Atom}}{tag_name}")
        return found.text.strip() if found is not None and found.text else ""

    def _link(self, entry: ET.Element) -> str:
        rss_link = self._text(entry, "link")
        if rss_link:
            return rss_link
        atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            return atom_link.attrib.get("href", "")
        return ""

    def _published(self, entry: ET.Element) -> str | None:
        raw = self._text(entry, "pubDate") or self._text(entry, "published") or self._text(entry, "updated")
        if not raw:
            return None
        try:
            return parsedate_to_datetime(raw).isoformat()
        except (TypeError, ValueError, IndexError):
            return raw

    def _clean_text(self, value: str) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", unescape(value))
        return re.sub(r"\s+", " ", without_tags).strip()

    def _dedupe(self, items: list[NewsItem]) -> list[NewsItem]:
        seen: set[str] = set()
        result: list[NewsItem] = []
        for item in items:
            key = item.link or item.title.lower()
            if not item.title or key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result[:24]


class OpenAIWebSearchFallback:
    name = "OpenAI research fallback"

    def __init__(self, db: Session) -> None:
        self.research = ResearchService(db)

    def run(self, query: str, project_id: int | None = None) -> NewsResult:
        result = self.research.run_research(query, project_id=project_id, include_project_context=False)
        return NewsResult(
            query=query,
            provider=self.name,
            summary=str(result["summary"]),
            items=[],
            sources=list(result["sources"]),
            fallback_used=True,
        )


class NewsService:
    def __init__(self, db: Session, provider: NewsProvider | None = None, llm: OpenAIClient | None = None) -> None:
        self.db = db
        self.provider = provider or RSSNewsProvider()
        self.llm = llm or OpenAIClient(db)
        self.fallback = OpenAIWebSearchFallback(db)

    def summarize_news(self, query: str, project_id: int | None = None, conversation_id: str | None = None) -> NewsResult:
        items = self.provider.fetch(query)
        if not items:
            return self.fallback.run(query, project_id)

        summary = self._summarize(query, items, project_id, conversation_id)
        return NewsResult(
            query=query,
            provider=self.provider.name,
            summary=self._render_response(summary, items),
            items=items,
            sources=[item.link for item in items if item.link],
        )

    def _summarize(
        self,
        query: str,
        items: list[NewsItem],
        project_id: int | None,
        conversation_id: str | None,
    ) -> str:
        feed_context = "\n".join(
            f"- {item.source}: {item.title}. {item.summary[:240]} Link: {item.link}"
            for item in items[:18]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You summarize RSS headlines for Jarvis using only the supplied feed items. "
                    "Do not claim live web research. Keep it concise and group related stories when useful."
                ),
            },
            {
                "role": "user",
                "content": f"User request: {query}\n\nRSS feed items:\n{feed_context}\n\nReturn a concise headline briefing with key themes.",
            },
        ]
        return self.llm.chat(messages, operation_type="news", project_id=project_id, conversation_id=conversation_id)

    def _render_response(self, summary: str, items: list[NewsItem]) -> str:
        sources = "\n".join(f"- {item.source}: {item.title} ({item.link})" for item in items[:12] if item.link)
        freshness = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        parts = [
            summary.strip(),
            f"## Provider\nUsed RSS news provider. Feed cache refreshed at {freshness}.",
        ]
        if sources:
            parts.append(f"## Sources\n{sources}")
        return "\n\n".join(parts)
