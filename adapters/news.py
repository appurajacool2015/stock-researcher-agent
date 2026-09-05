#!/usr/bin/env python3

"""
News Adapter
============

Fetch recent company-related news using Google News RSS.

Responsibilities:
    - Build a company-specific news query
    - Fetch RSS feed
    - Parse news items
    - Keep only recent articles
    - Deduplicate articles
    - Sort newest -> oldest
    - Normalize headline, summary, publication time,
      publisher and URL
    - Return adapter-level provenance metadata

It does NOT:
    - perform sentiment analysis
    - assign investment ratings
    - interpret news
    - make investment decisions
    - modify ResearchResult schema
"""

import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional


class NewsAdapter:
    """
    Google News RSS adapter.

    The adapter returns normalized raw news evidence.
    Interpretation belongs to a later research/AI layer.
    """

    # =========================================================
    # CONFIGURATION
    # =========================================================

    BASE_URL = (
        "https://news.google.com/rss/search"
    )

    DEFAULT_LIMIT = 10

    DEFAULT_LOOKBACK_DAYS = 30

    REQUEST_TIMEOUT = 20

    USER_AGENT = (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )

    # =========================================================
    # TIME
    # =========================================================

    @staticmethod
    def utc_now() -> str:
        """
        Return current UTC timestamp.
        """

        return datetime.now(
            timezone.utc
        ).isoformat()

    # =========================================================
    # SYMBOL / QUERY
    # =========================================================

    @staticmethod
    def build_query(
        symbol: str,
        company_name: Optional[str] = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> str:
        """
        Build a company-focused Google News query.

        Example:

            TCS
            Tata Consultancy Services Ltd

        becomes approximately:

            "Tata Consultancy Services Ltd" TCS when:30d
        """

        symbol = (
            symbol.upper().strip()
        )

        if not symbol:
            raise ValueError(
                "Stock symbol cannot be empty."
            )

        if lookback_days < 1:
            raise ValueError(
                "lookback_days must be >= 1."
            )

        if company_name:
            company_name = (
                company_name.strip()
            )

        if company_name:

            base_query = (
                f'"{company_name}" {symbol}'
            )

        else:

            base_query = symbol

        return (
            f"{base_query} "
            f"when:{lookback_days}d"
        )

    # =========================================================
    # RSS URL
    # =========================================================

    @classmethod
    def build_url(
        cls,
        query: str,
    ) -> str:
        """
        Build Google News RSS search URL.
        """

        params = {
            "q": query,
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en",
        }

        return (
            cls.BASE_URL
            + "?"
            + urllib.parse.urlencode(
                params
            )
        )

    # =========================================================
    # HTTP
    # =========================================================

    def fetch(
        self,
        query: str,
    ) -> bytes:
        """
        Fetch Google News RSS XML.
        """

        url = self.build_url(
            query
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    self.USER_AGENT
                ),
                "Accept": (
                    "application/rss+xml,"
                    "application/xml,"
                    "text/xml"
                ),
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=self.REQUEST_TIMEOUT,
        ) as response:

            payload = response.read()

        if not payload:
            raise RuntimeError(
                "News RSS returned an empty response."
            )

        return payload

    # =========================================================
    # TEXT CLEANING
    # =========================================================

    @staticmethod
    def clean_text(
        value: Optional[str],
    ) -> Optional[str]:
        """
        Remove HTML and normalize whitespace.
        """

        if value is None:
            return None

        value = html.unescape(
            value
        )

        value = re.sub(
            r"<[^>]+>",
            " ",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        value = value.strip()

        return value or None

    # =========================================================
    # DATE
    # =========================================================

    @staticmethod
    def parse_datetime(
        value: Optional[str],
    ) -> Optional[datetime]:
        """
        Parse RSS date into timezone-aware UTC datetime.
        """

        if not value:
            return None

        try:

            dt = parsedate_to_datetime(
                value
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):

            return None

    @classmethod
    def normalize_date(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        """
        Convert RSS publication date into ISO-8601 UTC.
        """

        dt = cls.parse_datetime(
            value
        )

        if dt is None:
            return None

        return dt.isoformat()

    # =========================================================
    # SOURCE
    # =========================================================

    @staticmethod
    def extract_source(
        item: ET.Element,
    ) -> Optional[str]:
        """
        Extract publisher/source name.
        """

        source = item.find(
            "source"
        )

        if source is not None:

            text = (
                source.text
                or ""
            ).strip()

            if text:
                return text

        # Fallback:
        #
        # Google News titles frequently have:
        #
        # Headline - Publisher
        #
        title_node = item.find(
            "title"
        )

        if title_node is not None:

            title = (
                title_node.text
                or ""
            ).strip()

            parts = re.split(
                r"\s+-\s+",
                title,
            )

            if len(parts) >= 2:

                source_name = (
                    parts[-1].strip()
                )

                if source_name:
                    return source_name

        return None

    # =========================================================
    # TITLE
    # =========================================================

    @staticmethod
    def clean_title(
        value: Optional[str],
    ) -> Optional[str]:
        """
        Clean article headline.
        """

        return NewsAdapter.clean_text(
            value
        )

    # =========================================================
    # URL NORMALIZATION
    # =========================================================

    @staticmethod
    def normalize_url(
        value: Optional[str],
    ) -> Optional[str]:
        """
        Normalize an article URL.

        At this stage we intentionally preserve the
        Google News redirect URL rather than attempting
        to resolve it to the publisher URL.
        """

        if not value:
            return None

        value = html.unescape(
            value
        ).strip()

        return value or None

    # =========================================================
    # DEDUPLICATION KEY
    # =========================================================

    @staticmethod
    def dedup_key(
        article: Dict[str, Any],
    ) -> str:
        """
        Build a stable deduplication key.

        Prefer URL when available.

        Otherwise use:
            normalized headline + publisher
        """

        url = (
            article.get("url")
            or ""
        ).strip().lower()

        if url:
            return (
                "url:"
                + url
            )

        headline = (
            article.get("headline")
            or ""
        ).strip().lower()

        source = (
            article.get("source")
            or ""
        ).strip().lower()

        headline = re.sub(
            r"\s+",
            " ",
            headline,
        )

        return (
            "text:"
            + headline
            + "|"
            + source
        )

    # =========================================================
    # RECENCY
    # =========================================================

    @classmethod
    def is_recent(
        cls,
        published_at: datetime,
        retrieved_at: datetime,
        lookback_days: int,
    ) -> bool:
        """
        Return True when an article is within the
        configured lookback window.

        Future-dated articles are also rejected.
        """

        if lookback_days < 1:
            return False

        cutoff = (
            retrieved_at
            - timedelta(
                days=lookback_days
            )
        )

        if published_at > retrieved_at:
            return False

        return published_at >= cutoff

    # =========================================================
    # PARSING
    # =========================================================

    def parse(
        self,
        payload: bytes,
        query: str,
        retrieved_at: Optional[str] = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        limit: int = DEFAULT_LIMIT,
    ) -> List[Dict[str, Any]]:
        """
        Parse RSS XML into normalized recent news.

        Processing order:

            XML
             ↓
            parse
             ↓
            validate dates
             ↓
            recency filter
             ↓
            deduplicate
             ↓
            newest first
             ↓
            limit
        """

        if limit < 1:
            return []

        if lookback_days < 1:
            return []

        if retrieved_at:

            retrieval_dt = (
                self.parse_iso_datetime(
                    retrieved_at
                )
            )

        else:

            retrieval_dt = datetime.now(
                timezone.utc
            )

        if retrieval_dt is None:

            retrieval_dt = datetime.now(
                timezone.utc
            )

        try:

            root = ET.fromstring(
                payload
            )

        except ET.ParseError:

            return []

        channel = root.find(
            "channel"
        )

        if channel is None:
            return []

        items = channel.findall(
            "item"
        )

        candidates: List[
            Dict[str, Any]
        ] = []

        for item in items:

            title_node = item.find(
                "title"
            )

            link_node = item.find(
                "link"
            )

            description_node = (
                item.find(
                    "description"
                )
            )

            pub_date_node = (
                item.find(
                    "pubDate"
                )
            )

            title = self.clean_title(
                (
                    title_node.text
                    if title_node is not None
                    else None
                )
            )

            if not title:
                continue

            published_dt = (
                self.parse_datetime(
                    (
                        pub_date_node.text
                        if pub_date_node is not None
                        else None
                    )
                )
            )

            # ResearchResult v1 requires a
            # valid published_at timestamp.
            if published_dt is None:
                continue

            if not self.is_recent(
                published_at=published_dt,
                retrieved_at=retrieval_dt,
                lookback_days=lookback_days,
            ):
                continue

            url = self.normalize_url(
                (
                    link_node.text
                    if link_node is not None
                    else None
                )
            )

            summary = self.clean_text(
                (
                    description_node.text
                    if description_node is not None
                    else None
                )
            )

            source = (
                self.extract_source(
                    item
                )
            )

            candidates.append(
                {
                    "headline": title,
                    "summary": summary,
                    "published_at": (
                        published_dt.isoformat()
                    ),
                    "source": source,
                    "url": url,
                    "query": query,
                }
            )

        # =====================================================
        # DEDUPLICATE
        # =====================================================

        unique: Dict[
            str,
            Dict[str, Any],
        ] = {}

        for article in candidates:

            key = self.dedup_key(
                article
            )

            if key not in unique:

                unique[key] = article

        articles = list(
            unique.values()
        )

        # =====================================================
        # SORT NEWEST -> OLDEST
        # =====================================================

        articles.sort(
            key=lambda article: (
                article.get(
                    "published_at"
                )
                or ""
            ),
            reverse=True,
        )

        # =====================================================
        # LIMIT
        # =====================================================

        return articles[:limit]

    # =========================================================
    # ISO DATE PARSER
    # =========================================================

    @staticmethod
    def parse_iso_datetime(
        value: Optional[str],
    ) -> Optional[datetime]:
        """
        Parse an ISO-8601 timestamp.
        """

        if not value:
            return None

        try:

            normalized = value

            if normalized.endswith(
                "Z"
            ):

                normalized = (
                    normalized[:-1]
                    + "+00:00"
                )

            dt = (
                datetime.fromisoformat(
                    normalized
                )
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

    # =========================================================
    # RESEARCH
    # =========================================================

    def research(
        self,
        symbol: str,
        company_name: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> Dict[str, Any]:
        """
        Fetch, filter and normalize recent company news.

        Failure policy:

            Network/feed/parsing failures raise an exception
            to the caller.

        The pipeline should decide whether such an adapter
        failure becomes a pipeline error or an empty news
        result.
        """

        symbol = (
            symbol.upper().strip()
        )

        if not symbol:
            raise ValueError(
                "Stock symbol cannot be empty."
            )

        retrieved_at = (
            self.utc_now()
        )

        query = self.build_query(
            symbol=symbol,
            company_name=company_name,
            lookback_days=lookback_days,
        )

        url = self.build_url(
            query
        )

        try:

            payload = self.fetch(
                query
            )

            articles = self.parse(
                payload=payload,
                query=query,
                retrieved_at=retrieved_at,
                lookback_days=lookback_days,
                limit=limit,
            )

        except Exception:

            # The adapter deliberately does not hide
            # network or malformed-feed failures.
            #
            # The pipeline will later decide how to
            # represent the failure in ResearchResult.
            raise

        return {
            "symbol": symbol,
            "query": query,
            "url": url,
            "retrieved_at": retrieved_at,
            "lookback_days": lookback_days,
            "article_count": len(
                articles
            ),
            "articles": articles,
        }


# =============================================================
# CLI
# =============================================================

def main():

    symbol = (
        sys.argv[1].upper().strip()
        if len(sys.argv) > 1
        else "TCS"
    )

    company_name = (
        sys.argv[2]
        if len(sys.argv) > 2
        else None
    )

    adapter = NewsAdapter()

    try:

        result = adapter.research(
            symbol=symbol,
            company_name=company_name,
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

    except Exception as exc:

        print(
            json.dumps(
                {
                    "symbol": symbol,
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        raise


if __name__ == "__main__":
    main()
