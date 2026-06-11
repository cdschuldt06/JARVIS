from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
from time import monotonic, sleep
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from sqlalchemy.orm import Session

from jarvis.core.config import get_settings
from jarvis.llm import OpenAIClient
from jarvis.research.service import ResearchService


MARKET_CACHE_SECONDS = 15 * 60
ALPHA_VANTAGE_REQUEST_DELAY_SECONDS = 1.1
DEFAULT_SYMBOLS = ("SPY", "QQQ", "DIA", "VIX", "BTC")
COMPANY_SYMBOLS = {
    "aapl": "AAPL",
    "apple": "AAPL",
    "nvda": "NVDA",
    "nvidia": "NVDA",
    "msft": "MSFT",
    "microsoft": "MSFT",
    "tsla": "TSLA",
    "tesla": "TSLA",
    "amzn": "AMZN",
    "amazon": "AMZN",
    "googl": "GOOGL",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "amd": "AMD",
}
QUESTION_WORDS = {"CHECK", "HOW", "IS", "ME", "ABOUT", "TELL", "THE", "WHAT", "WHATS"}


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    latest_price: str
    change: str
    percent_change: str
    timestamp: str


@dataclass(frozen=True)
class MarketFailure:
    symbol: str
    reason: str


@dataclass(frozen=True)
class MarketResult:
    query: str
    provider: str
    summary: str
    quotes: list[MarketQuote]
    requested_symbols: list[str]
    failed_symbols: list[MarketFailure]
    sources: list[str]
    setup_message: str = ""
    fallback_used: bool = False


class MarketProvider(ABC):
    name: str

    @abstractmethod
    def fetch(self, query: str) -> MarketResult:
        raise NotImplementedError


class AlphaVantageProvider(MarketProvider):
    name = "Alpha Vantage market provider"

    _cache: dict[str, tuple[float, MarketResult]] = {}

    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.alpha_vantage_api_key

    def fetch(self, query: str) -> MarketResult:
        if not self.api_key:
            return MarketResult(
                query=query,
                provider=self.name,
                summary=(
                    "Alpha Vantage is not configured yet. Add ALPHA_VANTAGE_API_KEY to .env, restart the backend, "
                    "and market summaries will use Alpha Vantage before falling back to OpenAI research."
                ),
                quotes=[],
                requested_symbols=[],
                failed_symbols=[],
                sources=[],
                setup_message="Missing ALPHA_VANTAGE_API_KEY.",
            )

        symbols = self._symbols_for_query(query)
        if not symbols:
            return MarketResult(
                query=query,
                provider=self.name,
                summary="Which ticker should I check? Give me a stock symbol like NVDA, AAPL, TSLA, or AMD.",
                quotes=[],
                requested_symbols=[],
                failed_symbols=[],
                sources=[],
                setup_message="Ticker required.",
            )

        cache_key = ",".join(symbols)
        cached = self._cache.get(cache_key)
        if cached and monotonic() - cached[0] < MARKET_CACHE_SECONDS:
            return cached[1]

        quotes: list[MarketQuote] = []
        failures: list[MarketFailure] = []
        for index, symbol in enumerate(symbols):
            if index > 0:
                sleep(ALPHA_VANTAGE_REQUEST_DELAY_SECONDS)
            quote, failure = self._fetch_quote(symbol)
            if quote:
                quotes.append(quote)
            elif failure:
                failures.append(failure)

        result = MarketResult(
            query=query,
            provider=self.name,
            summary="",
            quotes=quotes,
            requested_symbols=list(symbols),
            failed_symbols=failures,
            sources=["https://www.alphavantage.co/"],
        )
        self._cache[cache_key] = (monotonic(), result)
        return result

    def _symbols_for_query(self, query: str) -> tuple[str, ...]:
        lowered = query.lower()
        text = query.upper()
        explicit = [symbol for symbol in DEFAULT_SYMBOLS if symbol in text or (symbol == "VIX" and "^VIX" in text)]
        if "BITCOIN" in text and "BTC" not in explicit:
            explicit.append("BTC")
        for company, symbol in COMPANY_SYMBOLS.items():
            if company in lowered and symbol not in explicit:
                explicit.append(symbol)
        for token in re.findall(r"\b[A-Z]{2,5}\b", query):
            if token not in QUESTION_WORDS and token not in explicit:
                explicit.append(token)
        if explicit:
            return tuple(explicit)
        if any(term in lowered for term in ("market", "markets", "stocks", "nasdaq", "dow", "s&p")):
            return DEFAULT_SYMBOLS
        if re.search(r"\b(how is|what'?s|check|tell me about)\b", lowered):
            return ()
        return tuple(explicit) if explicit else DEFAULT_SYMBOLS

    def _fetch_quote(self, symbol: str) -> tuple[MarketQuote | None, MarketFailure | None]:
        try:
            quote = self._fetch_crypto_quote(symbol) if symbol == "BTC" else self._fetch_equity_quote(symbol)
            if quote is None:
                return None, MarketFailure(symbol, "No quote payload returned by provider.")
            return quote, None
        except (KeyError, OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
            return None, MarketFailure(symbol, f"{type(exc).__name__}: {str(exc)[:160]}")

    def _fetch_equity_quote(self, symbol: str) -> MarketQuote | None:
        payload = self._get_json({"function": "GLOBAL_QUOTE", "symbol": "^VIX" if symbol == "VIX" else symbol})
        quote = payload.get("Global Quote") or {}
        price = quote.get("05. price")
        if not price:
            return None
        return MarketQuote(
            symbol=symbol,
            latest_price=price,
            change=quote.get("09. change", ""),
            percent_change=quote.get("10. change percent", ""),
            timestamp=quote.get("07. latest trading day", ""),
        )

    def _fetch_crypto_quote(self, symbol: str) -> MarketQuote | None:
        payload = self._get_json({"function": "CURRENCY_EXCHANGE_RATE", "from_currency": symbol, "to_currency": "USD"})
        quote = payload.get("Realtime Currency Exchange Rate") or {}
        price = quote.get("5. Exchange Rate")
        if not price:
            return None
        return MarketQuote(
            symbol=symbol,
            latest_price=price,
            change="",
            percent_change="",
            timestamp=quote.get("6. Last Refreshed", ""),
        )

    def _get_json(self, params: dict[str, str]) -> dict[str, object]:
        query = urlencode({**params, "apikey": self.api_key})
        request = Request(f"https://www.alphavantage.co/query?{query}", headers={"User-Agent": "Jarvis/0.1 market provider"})
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))


class OpenAIWebSearchFallback:
    name = "OpenAI research fallback"

    def __init__(self, db: Session) -> None:
        self.research = ResearchService(db)

    def run(self, query: str, project_id: int | None = None) -> MarketResult:
        result = self.research.run_research(query, project_id=project_id, include_project_context=False)
        return MarketResult(
            query=query,
            provider=self.name,
            summary=str(result["summary"]),
            quotes=[],
            requested_symbols=[],
            failed_symbols=[],
            sources=list(result["sources"]),
            fallback_used=True,
        )


class MarketService:
    def __init__(self, db: Session, provider: MarketProvider | None = None, llm: OpenAIClient | None = None) -> None:
        self.db = db
        self.provider = provider or AlphaVantageProvider()
        self.llm = llm or OpenAIClient(db)
        self.fallback = OpenAIWebSearchFallback(db)

    def summarize_market(self, query: str, project_id: int | None = None, conversation_id: str | None = None) -> MarketResult:
        result = self.provider.fetch(query)
        if result.setup_message:
            return result
        if not result.quotes:
            return self.fallback.run(query, project_id)

        summary = self._summarize(query, result.quotes, result.requested_symbols, result.failed_symbols, project_id, conversation_id)
        return MarketResult(
            query=query,
            provider=result.provider,
            summary=self._render_response(summary, result.quotes, result.failed_symbols),
            quotes=result.quotes,
            requested_symbols=result.requested_symbols,
            failed_symbols=result.failed_symbols,
            sources=result.sources,
        )

    def _summarize(
        self,
        query: str,
        quotes: list[MarketQuote],
        requested_symbols: list[str],
        failed_symbols: list[MarketFailure],
        project_id: int | None,
        conversation_id: str | None,
    ) -> str:
        quote_context = "\n".join(
            f"- {quote.symbol}: price {quote.latest_price}, change {quote.change}, percent change {quote.percent_change}, timestamp {quote.timestamp}"
            for quote in quotes
        )
        returned_symbols = {quote.symbol for quote in quotes}
        broad_indexes_available = {"SPY", "QQQ", "DIA"}.issubset(returned_symbols)
        completeness = (
            "SPY, QQQ, and DIA are available, so you can summarize broad market direction."
            if broad_indexes_available
            else "The snapshot is incomplete. If only one symbol is available, say that clearly."
        )
        failure_context = "\n".join(f"- {failure.symbol}: {failure.reason}" for failure in failed_symbols) or "None"
        messages = [
            {
                "role": "system",
                "content": (
                    "You summarize market snapshot data for Jarvis using only supplied Alpha Vantage quote data. "
                    "Do not provide investment advice. Keep it concise and mention missing context when data is sparse. "
                    "Do not use OpenAI web research or imply broader live market context beyond the supplied quotes."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User request: {query}\n"
                    f"Requested symbols: {', '.join(requested_symbols)}\n"
                    f"Returned symbols: {', '.join(sorted(returned_symbols))}\n"
                    f"Failed symbols:\n{failure_context}\n\n"
                    f"Market data:\n{quote_context}\n\n"
                    f"Completeness guidance: {completeness}\n\n"
                    "Return a concise market snapshot."
                ),
            },
        ]
        return self.llm.chat(messages, operation_type="market", project_id=project_id, conversation_id=conversation_id)

    def _render_response(self, summary: str, quotes: list[MarketQuote], failed_symbols: list[MarketFailure]) -> str:
        rows = "\n".join(
            f"- {quote.symbol}: {quote.latest_price} ({quote.change}, {quote.percent_change}) as of {quote.timestamp or 'latest available'}"
            for quote in quotes
        )
        parts = [summary.strip(), "## Market Data\n" + rows]
        if failed_symbols:
            failed = ", ".join(failure.symbol for failure in failed_symbols)
            parts.append(f"Some symbols were unavailable due to provider limits or unsupported symbols: {failed}.")
        parts.append("## Provider\nUsed Alpha Vantage market provider.")
        return "\n\n".join(parts)
