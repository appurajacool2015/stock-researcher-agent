#!/usr/bin/env python3
"""
News Intelligence Engine v1.1.2

Deterministic interpretation of normalized company-news evidence.

Supports:
- canonical ResearchResult v1 articles
- legacy article formats
- Unicode news (Hindi, Marathi, Tamil, etc.)
- ResearchResult.news as a direct list
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


MODULE_VERSION = "1.1.2"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _lower(value: Any) -> str:
    return _normalize_text(value).casefold()


def _contains_any(
    text: str,
    terms: Sequence[str],
) -> List[str]:

    low = _lower(text)

    return [
        term
        for term in terms
        if _lower(term) in low
    ]


EVENT_RULES: Dict[str, List[str]] = {

    "REGULATORY": [
        "regulatory",
        "regulator",
        "visa",
        "h-1b",
        "h1b",
        "tariff",
        "compliance",
        "ban",
        "sanction",
        "fee increase",
        "fee hike",
        "higher fee",

        "नियम",
        "नियमन",
        "विसा",
        "वीज़ा",
        "व्हिसा",
        "शुल्क",
        "फी",

        "फी वाढ",
        "शुल्क वाढ",

        "விசா",
        "கட்டணம்",
        "கட்டண உயர்வு",
    ],

    "DEAL_CONTRACT": [
        "contract",
        "order",
        "deal",
        "agreement",
        "partnership",
        "wins contract",
        "won contract",
        "secures",
        "secured order",
        "new client",
        "client win",
        "large deal",
        "major contract",

        "करार",
        "ऑर्डर",
        "करार मिळाला",

        "ஒப்பந்தம்",
        "ஆர்டர்",
    ],

    "DIVIDEND_CAPITAL": [
        "dividend",
        "bonus",
        "buyback",
        "split",
        "special dividend",
        "ex-date",
        "record date",
        "capital return",

        "लाभांश",
        "बोनस",
        "बायबैक",

        "लाभांश",
        "बोनस",
        "बायबॅक",
    ],

    "EARNINGS": [
        "earnings",
        "results",
        "revenue",
        "profit",
        "net profit",
        "quarterly results",
        "q1",
        "q2",
        "q3",
        "q4",
        "margin",
        "eps",

        "कमाई",
        "नफा",
        "महसूल",
        "परिणाम",

        "வருவாய்",
        "லாபம்",
        "முடிவுகள்",
    ],

    "ANALYST_RATING": [
        "target price",
        "price target",
        "upgrade",
        "downgrade",
        "buy rating",
        "sell rating",
        "outperform",
        "underperform",
        "brokerage",
        "analyst",
    ],

    "MACRO_SECTOR": [
        "it sector",
        "information technology",
        "nifty it",
        "sector",
        "nvidia",
        "ai demand",
        "technology sector",
        "industry outlook",
        "indian it",
    ],
}


POSITIVE_TERMS = [

    "wins",
    "won",
    "secures",
    "secured",
    "new contract",
    "major contract",
    "large deal",
    "strong",
    "growth",
    "beats",
    "beat estimates",
    "upgrade",
    "outperform",
    "buy",
    "positive",
    "record",
    "raises",
    "increases",
    "higher profit",
    "higher revenue",
    "dividend",
    "bonus",
    "reward",
    "benefit",
    "up",

    "जिंकला",
    "मिळाला",
    "वाढ",
    "नफा वाढ",
    "महसूल वाढ",

    "वाढ",
    "नफा वाढ",
    "महसूल वाढ",

    "வெற்றி",
    "அதிகரிப்பு",
    "லாபம்",
]


NEGATIVE_TERMS = [

    "down",
    "decline",
    "declines",
    "drop",
    "drops",
    "fell",
    "fall",
    "cut",
    "cuts",
    "reduced",
    "reduction",
    "weak",
    "miss",
    "misses",
    "downgrade",
    "underperform",
    "sell",
    "negative",
    "risk",
    "layoff",
    "job cut",
    "variable pay cut",
    "fee increase",
    "fee hike",
    "higher fee",
    "tariff",
    "penalty",
    "ban",
    "loss",

    "कटौती",
    "कपात",
    "कमी",
    "घट",
    "घसरण",
    "धक्का",
    "फटका",
    "नुकसान",
    "वेतन में कटौती",

    "कपात",
    "कमी",
    "घट",
    "घसरण",
    "धक्का",
    "फटका",
    "नुकसान",
    "वेरिएबल पे मध्ये कपात",
    "पगारात कपात",

    "குறைப்பு",
    "வீழ்ச்சி",
    "கட்டண உயர்வு",
    "அதிக கட்டணம்",
    "கட்டணம் உயர்வு",
    "பாதிப்பு",
]


HIGH_MATERIALITY_TERMS = [
    "major contract",
    "major new contract",
    "large contract",
    "large new contract",
    "large deal",
    "multi-billion",
    "billion",
    "1000 crore",
    "1,000 crore",
    "2000 crore",
    "2,000 crore",
    "3000 crore",
    "3,000 crore",
    "5000 crore",
    "5,000 crore",
    "material",
    "acquisition",
    "merger",
    "buyback",
    "special dividend",
    "major regulatory",
    "ban",
    "penalty",
    "fraud",
    "resignation of ceo",
    "ceo resigns",
]


MEDIUM_MATERIALITY_TERMS = [
    "contract",
    "order",
    "deal",
    "agreement",
    "partnership",
    "upgrade",
    "downgrade",
    "target price",
    "dividend",
    "bonus",
    "results",
    "earnings",
    "visa",
    "tariff",
    "layoff",
    "job cut",
]


RELEVANCE_HIGH_TERMS = [
    "tcs",
    "tata consultancy services",
]


RELEVANCE_MEDIUM_TERMS = [
    "nifty it",
    "it sector",
    "information technology",
    "indian it",
    "tata",
    "infosys",
    "coforge",
    "ltimindtree",
]


def _article_id(
    article: Dict[str, Any],
) -> str:

    for key in (
        "article_id",
        "id",
    ):

        value = article.get(key)

        if value:
            return str(value)

    provenance = article.get(
        "provenance"
    )

    if isinstance(
        provenance,
        dict,
    ):

        value = provenance.get(
            "source_url"
        )

        if value:
            return str(value)

    for key in (
        "url",
        "link",
    ):

        value = article.get(key)

        if value:
            return str(value)

    title = (
        article.get("headline")
        or article.get("title")
    )

    if title:
        return _lower(title)

    return ""


def _article_fields(
    article: Dict[str, Any],
) -> Dict[str, Any]:

    provenance = article.get(
        "provenance"
    )

    if not isinstance(
        provenance,
        dict,
    ):
        provenance = {}

    title = (
        article.get("headline")
        or article.get("title")
        or ""
    )

    summary = (
        article.get("summary")
        or article.get("description")
        or ""
    )

    url = (
        article.get("url")
        or article.get("link")
        or provenance.get("source_url")
    )

    publisher = (
        article.get("publisher")
        or article.get("source")
        or provenance.get("source")
    )

    published_at = (
        article.get("published_at")
        or provenance.get("published_at")
    )

    retrieved_at = (
        article.get("retrieved_at")
        or provenance.get("retrieved_at")
    )

    source_query = (
        article.get("source_query")
        or article.get("query")
    )

    return {
        "article_id": _article_id(article),
        "title": _normalize_text(title),
        "summary": _normalize_text(summary),
        "url": url,
        "publisher": publisher,
        "published_at": published_at,
        "retrieved_at": retrieved_at,
        "source_query": source_query,
        "provenance": {
            "source": publisher,
            "source_url": url,
            "retrieved_at": retrieved_at,
            "published_at": published_at,
        },
    }


def _classify_event(
    title: str,
    summary: str = "",
) -> Dict[str, Any]:

    text = f"{title} {summary}".strip()

    for event_type in (
        "REGULATORY",
        "DEAL_CONTRACT",
        "DIVIDEND_CAPITAL",
        "MACRO_SECTOR",
        "EARNINGS",
        "ANALYST_RATING",
    ):

        matches = _contains_any(
            text,
            EVENT_RULES[event_type],
        )

        if matches:

            return {
                "event_type": event_type,
                "confidence": (
                    0.75
                    if len(matches) >= 2
                    else 0.65
                ),
                "matched_terms": matches,
            }

    return {
        "event_type": "GENERAL",
        "confidence": 0.40,
        "matched_terms": [],
    }


def _direction_for_event(
    title: str,
    summary: str,
    event_type: str,
) -> Dict[str, Any]:

    text = f"{title} {summary}"

    positives = _contains_any(
        text,
        POSITIVE_TERMS,
    )

    negatives = _contains_any(
        text,
        NEGATIVE_TERMS,
    )

    down_pct = re.search(
        r"\bdown\s+\d+(?:\.\d+)?\s*%",
        text,
        re.IGNORECASE,
    )

    up_pct = re.search(
        r"\bup\s+\d+(?:\.\d+)?\s*%",
        text,
        re.IGNORECASE,
    )

    if down_pct and "down" not in negatives:
        negatives.insert(
            0,
            "down",
        )

    if up_pct and "up" not in positives:
        positives.insert(
            0,
            "up",
        )

    if positives and negatives:

        direction = "NEUTRAL"
        score = 50
        confidence = 0.45

    elif positives:

        direction = "POSITIVE"
        score = 60
        confidence = 0.60

    elif negatives:

        direction = "NEGATIVE"
        score = 40
        confidence = 0.60

    else:

        direction = "NEUTRAL"
        score = 50
        confidence = 0.40

    return {
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "positive_matches": positives,
        "negative_matches": negatives,
    }


def _classify_materiality(
    title: str,
    summary: str = "",
) -> Dict[str, Any]:

    text = f"{title} {summary}"

    high = _contains_any(
        text,
        HIGH_MATERIALITY_TERMS,
    )

    crore_values = re.findall(
        r"(?:₹|rs\.?|inr)?\s*"
        r"([\d,]+(?:\.\d+)?)"
        r"\s*crore",
        text,
        flags=re.IGNORECASE,
    )

    for raw in crore_values:

        try:

            value = float(
                raw.replace(",", "")
            )

            if value >= 1000:

                high.append(
                    f"{raw} crore"
                )

        except ValueError:
            continue

    if high:

        return {
            "level": "HIGH",
            "score": 40,
            "matched_terms": list(
                dict.fromkeys(high)
            ),
        }

    medium = _contains_any(
        text,
        MEDIUM_MATERIALITY_TERMS,
    )

    if medium:

        return {
            "level": "MEDIUM",
            "score": 25,
            "matched_terms": medium,
        }

    return {
        "level": "LOW",
        "score": 10,
        "matched_terms": [],
    }


def _classify_relevance(
    title: str,
    summary: str,
    symbol: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:

    text = _lower(
        f"{title} {summary}"
    )

    high_terms = list(
        RELEVANCE_HIGH_TERMS
    )

    if symbol:
        high_terms.append(
            symbol
        )

    if company_name:
        high_terms.append(
            company_name
        )

    high = _contains_any(
        text,
        high_terms,
    )

    if high:

        return {
            "level": "HIGH",
            "score": 100,
            "matched_terms": list(
                dict.fromkeys(high)
            ),
        }

    medium = _contains_any(
        text,
        RELEVANCE_MEDIUM_TERMS,
    )

    if medium:

        return {
            "level": "MEDIUM",
            "score": 60,
            "matched_terms": medium,
        }

    return {
        "level": "LOW",
        "score": 25,
        "matched_terms": [],
    }


def _analyze_article(
    article: Dict[str, Any],
    symbol: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:

    fields = _article_fields(
        article
    )

    title = fields["title"]
    summary = fields["summary"]

    event = _classify_event(
        title,
        summary,
    )

    direction = _direction_for_event(
        title,
        summary,
        event["event_type"],
    )

    materiality = _classify_materiality(
        title,
        summary,
    )

    relevance = _classify_relevance(
        title,
        summary,
        symbol=symbol,
        company_name=company_name,
    )

    return {
        "article_id":
            fields["article_id"],

        "title":
            title,

        "url":
            fields["url"],

        "publisher":
            fields["publisher"],

        "published_at":
            fields["published_at"],

        "retrieved_at":
            fields["retrieved_at"],

        "source_query":
            fields["source_query"],

        "event":
            event,

        "direction":
            direction,

        "materiality":
            materiality,

        "relevance":
            relevance,

        "provenance":
            fields["provenance"],
    }


def _token_set(
    title: str,
) -> set[str]:

    text = _lower(
        title
    )

    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
        flags=re.UNICODE,
    )

    return {
        token
        for token in text.split()
        if len(token) > 2
    }


def _jaccard(
    a: set[str],
    b: set[str],
) -> float:

    if not a and not b:
        return 1.0

    union = a | b

    if not union:
        return 0.0

    return len(
        a & b
    ) / len(union)


def _cluster_articles(
    analyzed_articles: Sequence[
        Dict[str, Any]
    ],
) -> List[List[int]]:

    clusters: List[
        List[int]
    ] = []

    for index, article in enumerate(
        analyzed_articles
    ):

        placed = False

        current_tokens = _token_set(
            article["title"]
        )

        for cluster in clusters:

            representative = (
                analyzed_articles[
                    cluster[0]
                ]
            )

            if (
                article["event"]["event_type"]
                != representative["event"]["event_type"]
            ):
                continue

            similarity = _jaccard(
                current_tokens,
                _token_set(
                    representative["title"]
                ),
            )

            if similarity >= 0.55:

                cluster.append(
                    index
                )

                placed = True

                break

        if not placed:

            clusters.append(
                [index]
            )

    return clusters


def _aggregate_bias(
    analyzed_articles: Sequence[
        Dict[str, Any]
    ],
) -> Tuple[str, float]:

    if not analyzed_articles:
        return "NEUTRAL", 0.0

    weights = {
        "HIGH": 1.0,
        "MEDIUM": 0.8,
        "LOW": 0.5,
    }

    weighted = 0.0
    total_weight = 0.0

    for article in analyzed_articles:

        weight = weights.get(
            article["materiality"]["level"],
            0.5,
        )

        weighted += (
            article["direction"]["score"]
            - 50
        ) * weight

        total_weight += weight

    score = round(
        50
        + (
            weighted / total_weight
            if total_weight
            else 0
        ),
        2,
    )

    positive = any(
        article["direction"]["direction"]
        == "POSITIVE"
        for article in analyzed_articles
    )

    negative = any(
        article["direction"]["direction"]
        == "NEGATIVE"
        for article in analyzed_articles
    )

    if positive and negative:

        bias = "MIXED"

    elif score > 65:

        bias = "POSITIVE"

    elif score < 35:

        bias = "NEGATIVE"

    else:

        bias = "NEUTRAL"

    return bias, score


def analyze_news(
    articles: Sequence[
        Dict[str, Any]
    ],
    symbol: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:

    analyzed: List[
        Dict[str, Any]
    ] = []

    seen_ids: set[str] = set()

    for article in articles:

        if not isinstance(
            article,
            dict,
        ):
            continue

        article_id = _article_id(
            article
        )

        if (
            article_id
            and article_id in seen_ids
        ):
            continue

        if article_id:

            seen_ids.add(
                article_id
            )

        analyzed.append(
            _analyze_article(
                article,
                symbol=symbol,
                company_name=company_name,
            )
        )

    clusters = _cluster_articles(
        analyzed
    )

    cluster_lookup: Dict[
        int,
        int,
    ] = {}

    for cluster_number, cluster in enumerate(
        clusters,
        start=1,
    ):

        for index in cluster:

            cluster_lookup[index] = (
                cluster_number
            )

    for index, article in enumerate(
        analyzed
    ):

        article["cluster_id"] = (
            f"cluster-{cluster_lookup[index]:03d}"
        )

    bias, score = _aggregate_bias(
        analyzed
    )

    directions = Counter(
        article["direction"]["direction"]
        for article in analyzed
    )

    events = Counter(
        article["event"]["event_type"]
        for article in analyzed
    )

    materiality = Counter(
        article["materiality"]["level"]
        for article in analyzed
    )

    relevance = Counter(
        article["relevance"]["level"]
        for article in analyzed
    )

    material_count = sum(
        1
        for article in analyzed
        if article["materiality"]["level"]
        in {
            "MEDIUM",
            "HIGH",
        }
    )

    related_count = sum(
        1
        for cluster in clusters
        if len(cluster) > 1
    )

    return {
        "module":
            "news",

        "version":
            MODULE_VERSION,

        "symbol":
            symbol,

        "company_name":
            company_name,

        "overall_bias":
            bias,

        "score":
            score,

        "article_count":
            len(analyzed),

        "direction_counts":
            dict(directions),

        "event_counts":
            dict(events),

        "materiality_counts":
            dict(materiality),

        "relevance_counts":
            dict(relevance),

        "material_article_count":
            material_count,

        "event_cluster_count":
            len(clusters),

        "duplicate_or_related_cluster_count":
            related_count,

        "articles":
            analyzed,
    }


def analyze(
    articles: Sequence[
        Dict[str, Any]
    ],
    symbol: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:

    return analyze_news(
        articles,
        symbol=symbol,
        company_name=company_name,
    )


def research(
    articles: Sequence[
        Dict[str, Any]
    ],
    symbol: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:

    return analyze_news(
        articles,
        symbol=symbol,
        company_name=company_name,
    )


def _load_json(
    path: Path,
) -> Any:

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        return json.load(handle)


def _extract_articles_from_input(
    data: Any,
) -> List[Dict[str, Any]]:

    if isinstance(data, list):

        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    if not isinstance(
        data,
        dict,
    ):

        return []

    # ------------------------------------------------------------
    # Canonical ResearchResult v1:
    #
    # "news": [...]
    # ------------------------------------------------------------

    news = data.get(
        "news"
    )

    if isinstance(
        news,
        list,
    ):

        return [
            item
            for item in news
            if isinstance(item, dict)
        ]

    # ------------------------------------------------------------
    # Legacy:
    #
    # "articles": [...]
    # ------------------------------------------------------------

    articles = data.get(
        "articles"
    )

    if isinstance(
        articles,
        list,
    ):

        return [
            item
            for item in articles
            if isinstance(item, dict)
        ]

    # ------------------------------------------------------------
    # Legacy:
    #
    # "news": {
    #     "articles": [...]
    # }
    # ------------------------------------------------------------

    if isinstance(
        news,
        dict,
    ):

        articles = news.get(
            "articles"
        )

        if isinstance(
            articles,
            list,
        ):

            return [
                item
                for item in articles
                if isinstance(item, dict)
            ]

    return []


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Deterministic news "
            "intelligence engine."
        )
    )

    parser.add_argument(
        "input",
        help=(
            "JSON file containing "
            "news articles."
        ),
    )

    parser.add_argument(
        "--symbol",
        default=None,
    )

    parser.add_argument(
        "--company-name",
        default=None,
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
    )

    args = parser.parse_args()

    path = Path(
        args.input
    )

    if not path.exists():

        parser.error(
            f"Input file not found: {path}"
        )

    data = _load_json(
        path
    )

    articles = (
        _extract_articles_from_input(
            data
        )
    )

    symbol = args.symbol
    company_name = args.company_name

    if isinstance(
        data,
        dict,
    ):

        symbol = (
            symbol
            or data.get("symbol")
        )

        company_name = (
            company_name
            or data.get("company_name")
        )

    result = analyze_news(
        articles,
        symbol=symbol,
        company_name=company_name,
    )

    print(
        json.dumps(
            result,
            indent=(
                2
                if args.pretty
                else None
            ),
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
