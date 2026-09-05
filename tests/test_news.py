#!/usr/bin/env python3

"""
Tests for News Intelligence Engine v1.1.2.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT),
)


from intelligence.news import (  # noqa: E402
    MODULE_VERSION,
    _aggregate_bias,
    _analyze_article,
    _article_id,
    _classify_event,
    _classify_materiality,
    _classify_relevance,
    _cluster_articles,
    _direction_for_event,
    _extract_articles_from_input,
    _normalize_text,
    analyze_news,
)


class TestTextHelpers(unittest.TestCase):

    def test_none_normalizes_to_empty(self):

        self.assertEqual(
            _normalize_text(None),
            "",
        )

    def test_unicode_is_preserved(self):

        text = (
            "TCS कडून कर्मचाऱ्यांच्या "
            "वेरिएबल पे मध्ये कपात"
        )

        normalized = _normalize_text(
            text
        )

        self.assertIn(
            "कपात",
            normalized,
        )

    def test_whitespace_is_collapsed(self):

        self.assertEqual(
            _normalize_text(
                " A   B \n C "
            ),
            "A B C",
        )


class TestArticleId(unittest.TestCase):

    def test_canonical_source_url(self):

        article = {
            "headline":
                "Contract",

            "provenance": {
                "source_url":
                    "https://example.com/a",
            },
        }

        self.assertEqual(
            _article_id(article),
            "https://example.com/a",
        )

    def test_explicit_article_id_wins(self):

        article = {
            "article_id":
                "abc",

            "url":
                "https://example.com",
        }

        self.assertEqual(
            _article_id(article),
            "abc",
        )

    def test_legacy_url(self):

        article = {
            "title":
                "Hello",

            "url":
                "https://example.com",
        }

        self.assertEqual(
            _article_id(article),
            "https://example.com",
        )

    def test_headline_fallback(self):

        article = {
            "headline":
                "TCS wins contract",
        }

        self.assertTrue(
            _article_id(article)
        )


class TestCanonicalArticle(unittest.TestCase):

    def canonical(
        self,
        headline,
        summary="",
    ):

        return {
            "headline":
                headline,

            "summary":
                summary,

            "published_at":
                "2026-09-01T10:00:00+00:00",

            "provenance": {

                "source":
                    "Example News",

                "source_url":
                    "https://example.com/tcs",

                "retrieved_at":
                    "2026-09-01T11:00:00+00:00",

                "as_of_date":
                    None,
            },
        }

    def test_canonical_contract_is_classified_correctly(
        self
    ):

        result = _analyze_article(

            self.canonical(
                "TCS wins major new contract",

                (
                    "TCS announced a major "
                    "contract with a global client."
                ),
            ),

            symbol="TCS",

            company_name=(
                "Tata Consultancy Services Ltd"
            ),
        )

        self.assertEqual(
            result["title"],
            "TCS wins major new contract",
        )

        self.assertEqual(
            result["url"],
            "https://example.com/tcs",
        )

        self.assertEqual(
            result["publisher"],
            "Example News",
        )

        self.assertEqual(
            result["event"]["event_type"],
            "DEAL_CONTRACT",
        )

        self.assertEqual(
            result["direction"]["direction"],
            "POSITIVE",
        )

        self.assertEqual(
            result["materiality"]["level"],
            "HIGH",
        )

        self.assertEqual(
            result["provenance"]["source"],
            "Example News",
        )

    def test_legacy_format_still_works(
        self
    ):

        result = _analyze_article({

            "title":
                "TCS wins contract",

            "description":
                "New client deal",

            "url":
                "https://example.com/x",

            "publisher":
                "Example",

            "published_at":
                "2026-09-01T10:00:00Z",
        })

        self.assertEqual(
            result["title"],
            "TCS wins contract",
        )

        self.assertEqual(
            result["event"]["event_type"],
            "DEAL_CONTRACT",
        )


class TestEventClassification(unittest.TestCase):

    def test_contract(self):

        result = _classify_event(
            "TCS secures new contract"
        )

        self.assertEqual(
            result["event_type"],
            "DEAL_CONTRACT",
        )

    def test_order(self):

        result = _classify_event(
            "TCS wins ₹1,537 crore order"
        )

        self.assertEqual(
            result["event_type"],
            "DEAL_CONTRACT",
        )

    def test_dividend(self):

        result = _classify_event(
            "TCS dividend ex-date today"
        )

        self.assertEqual(
            result["event_type"],
            "DIVIDEND_CAPITAL",
        )

    def test_earnings(self):

        result = _classify_event(
            "TCS Q2 results: profit rises"
        )

        self.assertEqual(
            result["event_type"],
            "EARNINGS",
        )

    def test_analyst(self):

        result = _classify_event(
            "Brokerage raises TCS target price"
        )

        self.assertEqual(
            result["event_type"],
            "ANALYST_RATING",
        )

    def test_regulatory_visa(self):

        result = _classify_event(
            "H-1B visa fee increase hits Indian IT"
        )

        self.assertEqual(
            result["event_type"],
            "REGULATORY",
        )

    def test_macro(self):

        result = _classify_event(
            "Nifty IT surges after Nvidia results"
        )

        self.assertEqual(
            result["event_type"],
            "MACRO_SECTOR",
        )

    def test_price_headline_is_not_contract(
        self
    ):

        result = _classify_event(
            (
                "TCS Share Price August 31, 2026: "
                "Down 2.08% to ₹3,157.80"
            )
        )

        self.assertEqual(
            result["event_type"],
            "GENERAL",
        )


class TestDirection(unittest.TestCase):

    def test_positive_contract(self):

        result = _direction_for_event(
            "TCS wins major new contract",
            "",
            "DEAL_CONTRACT",
        )

        self.assertEqual(
            result["direction"],
            "POSITIVE",
        )

    def test_negative_cut(self):

        result = _direction_for_event(
            "TCS cuts variable pay",
            "",
            "GENERAL",
        )

        self.assertEqual(
            result["direction"],
            "NEGATIVE",
        )

    def test_price_down(self):

        result = _direction_for_event(
            "TCS share price down 2.08%",
            "",
            "GENERAL",
        )

        self.assertEqual(
            result["direction"],
            "NEGATIVE",
        )

    def test_hindi_negative_signal(self):

        result = _direction_for_event(
            (
                "TCS कर्मचारियों के "
                "वेतन में कटौती"
            ),
            "",
            "GENERAL",
        )

        self.assertEqual(
            result["direction"],
            "NEGATIVE",
        )

    def test_marathi_negative_signal(self):

        result = _direction_for_event(
            (
                "TCS कडून कर्मचाऱ्यांच्या "
                "वेरिएबल पे मध्ये कपात, "
                "वरिष्ठ स्तरावरील कर्मचाऱ्यांना फटका"
            ),
            "",
            "GENERAL",
        )

        self.assertEqual(
            result["direction"],
            "NEGATIVE",
        )

    def test_tamil_fee_increase_negative(
        self
    ):

        result = _direction_for_event(
            (
                "H-1B விசா கட்டண உயர்வு "
                "இந்திய ஐடி நிறுவனங்களுக்கு பாதிப்பு"
            ),
            "",
            "REGULATORY",
        )

        self.assertEqual(
            result["direction"],
            "NEGATIVE",
        )


class TestMateriality(unittest.TestCase):

    def test_major_contract_high(
        self
    ):

        result = _classify_materiality(
            "TCS wins major new contract"
        )

        self.assertEqual(
            result["level"],
            "HIGH",
        )

    def test_large_crore_order_high(
        self
    ):

        result = _classify_materiality(
            "TCS secures ₹1,537 crore order"
        )

        self.assertEqual(
            result["level"],
            "HIGH",
        )

    def test_small_contract_medium(
        self
    ):

        result = _classify_materiality(
            "TCS signs contract with client"
        )

        self.assertEqual(
            result["level"],
            "MEDIUM",
        )

    def test_unremarkable_headline_low(
        self
    ):

        result = _classify_materiality(
            "TCS share price today"
        )

        self.assertEqual(
            result["level"],
            "LOW",
        )


class TestRelevance(unittest.TestCase):

    def test_tcs_high(self):

        result = _classify_relevance(
            "TCS wins contract",
            "",
            "TCS",
            "Tata Consultancy Services Ltd",
        )

        self.assertEqual(
            result["level"],
            "HIGH",
        )

    def test_it_sector_medium(self):

        result = _classify_relevance(
            "Indian IT sector outlook",
            "",
            "TCS",
            "Tata Consultancy Services Ltd",
        )

        self.assertEqual(
            result["level"],
            "MEDIUM",
        )


class TestClustering(unittest.TestCase):

    def article(
        self,
        title,
        event="GENERAL",
    ):

        return {
            "title":
                title,

            "event": {
                "event_type":
                    event,
            },
        }

    def test_similar_headlines_cluster(
        self
    ):

        articles = [

            self.article(
                (
                    "TCS wins major contract "
                    "with global client"
                ),
                "DEAL_CONTRACT",
            ),

            self.article(
                (
                    "TCS wins major contract "
                    "from global client"
                ),
                "DEAL_CONTRACT",
            ),
        ]

        clusters = _cluster_articles(
            articles
        )

        self.assertEqual(
            len(clusters),
            1,
        )

    def test_unrelated_headlines_do_not_cluster(
        self
    ):

        articles = [

            self.article(
                "TCS wins major contract",
                "DEAL_CONTRACT",
            ),

            self.article(
                "TCS dividend ex-date today",
                "DIVIDEND_CAPITAL",
            ),
        ]

        clusters = _cluster_articles(
            articles
        )

        self.assertEqual(
            len(clusters),
            2,
        )


class TestAggregate(unittest.TestCase):

    def article(
        self,
        direction,
        materiality="MEDIUM",
    ):

        scores = {
            "POSITIVE": 60,
            "NEGATIVE": 40,
            "NEUTRAL": 50,
        }

        return {

            "direction": {

                "direction":
                    direction,

                "score":
                    scores[direction],
            },

            "materiality": {

                "level":
                    materiality,
            },
        }

    def test_mixed_news_bias(
        self
    ):

        bias, score = _aggregate_bias(

            [
                self.article(
                    "POSITIVE"
                ),

                self.article(
                    "NEGATIVE"
                ),
            ]
        )

        self.assertEqual(
            bias,
            "MIXED",
        )

        self.assertEqual(
            score,
            50.0,
        )

    def test_positive_news_bias(
        self
    ):

        bias, score = _aggregate_bias(

            [
                self.article(
                    "POSITIVE"
                ),

                self.article(
                    "POSITIVE"
                ),
            ]
        )

        self.assertEqual(
            bias,
            "NEUTRAL",
        )

        self.assertGreater(
            score,
            50,
        )

    def test_empty_is_neutral(
        self
    ):

        self.assertEqual(
            _aggregate_bias([]),
            (
                "NEUTRAL",
                0.0,
            ),
        )


class TestAnalyzeNews(unittest.TestCase):

    def test_counts(self):

        result = analyze_news(

            [
                {

                    "headline":
                        "TCS wins major new contract",

                    "summary":
                        "Large deal",

                    "published_at":
                        "2026-09-01T10:00:00Z",

                    "provenance": {

                        "source":
                            "Example",

                        "source_url":
                            "https://example.com/1",

                        "retrieved_at":
                            "2026-09-01T11:00:00Z",
                    },
                },

                {

                    "headline":
                        "TCS cuts variable pay",

                    "summary":
                        "Employees affected",

                    "published_at":
                        "2026-09-01T09:00:00Z",

                    "provenance": {

                        "source":
                            "Example",

                        "source_url":
                            "https://example.com/2",

                        "retrieved_at":
                            "2026-09-01T11:00:00Z",
                    },
                },
            ],

            symbol="TCS",

            company_name=(
                "Tata Consultancy Services Ltd"
            ),
        )

        self.assertEqual(
            result["article_count"],
            2,
        )

        self.assertEqual(
            result["overall_bias"],
            "MIXED",
        )

        self.assertEqual(
            len(result["articles"]),
            2,
        )

        self.assertEqual(
            result["version"],
            MODULE_VERSION,
        )

    def test_duplicate_urls_are_removed(
        self
    ):

        article = {

            "headline":
                "TCS wins contract",

            "url":
                "https://example.com/same",
        }

        result = analyze_news(
            [
                article,
                article,
            ]
        )

        self.assertEqual(
            result["article_count"],
            1,
        )


class TestResearchResultExtraction(
    unittest.TestCase
):

    def test_canonical_news_is_direct_list(
        self
    ):

        data = {

            "schema_version":
                "1.0",

            "symbol":
                "TCS",

            "company_name":
                "Tata Consultancy Services Ltd",

            "news": [

                {
                    "headline":
                        "TCS wins contract",
                }
            ],
        }

        articles = (
            _extract_articles_from_input(
                data
            )
        )

        self.assertEqual(
            len(articles),
            1,
        )

        self.assertEqual(
            articles[0]["headline"],
            "TCS wins contract",
        )

    def test_legacy_articles_list(
        self
    ):

        data = {

            "articles": [

                {
                    "title":
                        "TCS news",
                }
            ]
        }

        self.assertEqual(
            len(
                _extract_articles_from_input(
                    data
                )
            ),
            1,
        )

    def test_legacy_news_articles_wrapper(
        self
    ):

        data = {

            "news": {

                "articles": [

                    {
                        "title":
                            "TCS news",
                    }
                ]
            }
        }

        self.assertEqual(
            len(
                _extract_articles_from_input(
                    data
                )
            ),
            1,
        )

    def test_invalid_input(
        self
    ):

        self.assertEqual(
            _extract_articles_from_input(
                {
                    "news":
                        None
                }
            ),
            [],
        )


class TestCLI(unittest.TestCase):

    def test_cli_reads_canonical_research_result(
        self
    ):

        data = {

            "schema_version":
                "1.0",

            "symbol":
                "TCS",

            "company_name":
                "Tata Consultancy Services Ltd",

            "news": [

                {

                    "headline":
                        "TCS wins major new contract",

                    "summary":
                        "Major client deal",

                    "published_at":
                        "2026-09-01T10:00:00Z",

                    "provenance": {

                        "source":
                            "Example",

                        "source_url":
                            "https://example.com/1",

                        "retrieved_at":
                            "2026-09-01T11:00:00Z",
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:

            path = (
                Path(tmp)
                / "result.json"
            )

            path.write_text(
                json.dumps(
                    data,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(

                [
                    sys.executable,

                    str(
                        ROOT
                        / "intelligence"
                        / "news.py"
                    ),

                    str(path),

                    "--pretty",
                ],

                capture_output=True,

                text=True,

                check=False,
            )

            self.assertEqual(
                proc.returncode,
                0,
                proc.stderr,
            )

            output = json.loads(
                proc.stdout
            )

            self.assertEqual(
                output["article_count"],
                1,
            )

            self.assertEqual(
                output["symbol"],
                "TCS",
            )


if __name__ == "__main__":

    unittest.main(
        verbosity=2
    )
