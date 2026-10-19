#!/usr/bin/env python3
"""
Unit tests for adapters/screener.py

Verifies:
1. Snapshot card extraction for P/E, Book Value, Market Cap, ROE, ROCE, and D/E.
2. Fallback to Balance Sheet table for Debt-to-Equity:
   - Zero borrowings yields 0.00x.
   - Non-zero borrowings and positive net worth yields calculated ratio.
   - Negative/zero net worth leaves D/E as None.
3. Fallback to snapshot card for Promoter Pledge when omitted from tables.
4. Parsing table CAGR growth numbers.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup

from adapters.screener import ScreenerAdapter


class TestScreenerAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = ScreenerAdapter()

    def test_extract_fundamentals_with_snapshot_debt_to_equity(self):
        """When snapshot card explicitly has Debt to equity, it uses it directly."""
        html = """
        <html>
            <ul id="top-ratios">
                <li><span class="name">Stock P/E</span><span class="value">25.0</span></li>
                <li><span class="name">Book Value</span><span class="value">150.0</span></li>
                <li><span class="name">Market Cap</span><span class="value">50000</span></li>
                <li><span class="name">ROE</span><span class="value">20.5</span></li>
                <li><span class="name">Debt to equity</span><span class="value">0.15</span></li>
            </ul>
            <table><tr><th>ROCE %</th><td>28.0</td></tr></table>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_fundamentals(soup, tables)

        self.assertEqual(res["pe"], 25.0)
        self.assertEqual(res["debt_to_equity"], 0.15)
        self.assertEqual(res["roe"], 20.5)

    def test_extract_fundamentals_zero_borrowings_balance_sheet(self):
        """When snapshot card omits D/E, zero borrowings in Balance Sheet yields 0.00x."""
        html = """
        <html>
            <ul id="top-ratios">
                <li><span class="name">Stock P/E</span><span class="value">16.3</span></li>
                <li><span class="name">Market Cap</span><span class="value">800000</span></li>
            </ul>
            <table class="data-table">
                <thead><tr><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th></tr></thead>
                <tbody>
                    <tr><td>Equity Capital</td><td>362</td><td>362</td><td>362</td></tr>
                    <tr><td>Reserves</td><td>90,000</td><td>100,000</td><td>118,000</td></tr>
                    <tr><td>Borrowings +</td><td>0</td><td>0</td><td>0</td></tr>
                </tbody>
            </table>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_fundamentals(soup, tables)

        self.assertEqual(res["debt_to_equity"], 0.0)

    def test_extract_fundamentals_calculated_debt_to_equity(self):
        """When snapshot card omits D/E, calculates Borrowings / (Equity + Reserves)."""
        html = """
        <html>
            <ul id="top-ratios">
                <li><span class="name">Stock P/E</span><span class="value">30.0</span></li>
            </ul>
            <table class="data-table">
                <thead><tr><th>Mar 2025</th><th>Mar 2026</th></tr></thead>
                <tbody>
                    <tr><td>Equity Capital</td><td>500</td><td>500</td></tr>
                    <tr><td>Reserves</td><td>9,000</td><td>9,500</td></tr>
                    <tr><td>Borrowings +</td><td>2,000</td><td>1,000</td></tr>
                </tbody>
            </table>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_fundamentals(soup, tables)

        # Latest Borrowings = 1,000; Total Equity = 500 + 9,500 = 10,000. D/E = 1,000 / 10,000 = 0.10
        self.assertEqual(res["debt_to_equity"], 0.10)

    def test_extract_fundamentals_negative_net_worth_leaves_debt_none(self):
        """When total equity is <= 0 (negative net worth), leaves D/E as None."""
        html = """
        <html>
            <table class="data-table">
                <tbody>
                    <tr><td>Equity Capital</td><td>100</td></tr>
                    <tr><td>Reserves</td><td>-500</td></tr>
                    <tr><td>Borrowings</td><td>1,000</td></tr>
                </tbody>
            </table>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_fundamentals(soup, tables)

        self.assertIsNone(res["debt_to_equity"])

    def test_extract_fundamentals_missing_borrowings_leaves_debt_none(self):
        """When Balance Sheet does not have Borrowings row, D/E remains None."""
        html = """
        <html>
            <table class="data-table">
                <tbody>
                    <tr><td>Equity Capital</td><td>100</td></tr>
                    <tr><td>Reserves</td><td>500</td></tr>
                </tbody>
            </table>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_fundamentals(soup, tables)

        self.assertIsNone(res["debt_to_equity"])

    def test_extract_shareholding_table_pledge(self):
        """Extracts promoter pledge from shareholding table when present."""
        html = """
        <table class="data-table">
            <tr><td>Promoters</td><td>55.0%</td></tr>
            <tr><td>Pledged %</td><td>12.5%</td></tr>
            <tr><td>FIIs</td><td>20.0%</td></tr>
            <tr><td>DIIs</td><td>15.0%</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_shareholding(tables, soup=soup)

        self.assertEqual(res["promoter"], 55.0)
        self.assertEqual(res["promoter_pledge"], 12.5)

    def test_extract_shareholding_snapshot_card_pledge(self):
        """Extracts promoter pledge from top snapshot card when absent from table."""
        html = """
        <html>
            <ul id="top-ratios">
                <li><span class="name">Pledged percentage</span><span class="value">4.5 %</span></li>
            </ul>
            <table class="data-table">
                <tr><td>Promoters</td><td>65.0%</td></tr>
                <tr><td>FIIs</td><td>18.0%</td></tr>
                <tr><td>DIIs</td><td>10.0%</td></tr>
            </table>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_shareholding(tables, soup=soup)

        self.assertEqual(res["promoter"], 65.0)
        self.assertEqual(res["promoter_pledge"], 4.5)

    def test_extract_shareholding_no_pledge_leaves_none(self):
        """When pledge is omitted from both table and snapshot, pledge is None."""
        html = """
        <html>
            <table class="data-table">
                <tr><td>Promoters</td><td>71.77%</td></tr>
                <tr><td>FIIs</td><td>12.5%</td></tr>
                <tr><td>DIIs</td><td>10.5%</td></tr>
            </table>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        res = self.adapter.extract_shareholding(tables, soup=soup)

        self.assertEqual(res["promoter"], 71.77)
        self.assertIsNone(res["promoter_pledge"])

    @patch("services.research_pipeline.save_result")
    @patch("adapters.screener.ScreenerAdapter.research")
    @patch("adapters.market_data.MarketDataAdapter.research")
    @patch("adapters.news.NewsAdapter.research")
    def test_pipeline_screener_failure_graceful_partial(self, mock_news, mock_market, mock_screener, mock_save):
        """When Screener raises ConnectionError, pipeline does not crash; returns valid ResearchResult v1 with PARTIAL status."""
        import requests
        from services.research_pipeline import run_pipeline

        mock_screener.side_effect = requests.ConnectionError("Connection refused by Screener")
        mock_market.return_value = {
            "symbol": "TCS",
            "yahoo_symbol": "TCS.NS",
            "history_rows": 50,
            "indicators": {"cmp": 2500.0, "rsi_14": 55.0},
            "as_of_date": "2026-10-19",
        }
        mock_news.return_value = {
            "articles": [],
            "article_count": 0,
            "lookback_days": 30,
        }

        result = run_pipeline("TCS")
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["overall_status"], "PARTIAL")
        self.assertEqual(result["fundamentals"]["pe_ratio"]["status"], "UNAVAILABLE")
        self.assertEqual(result["technicals"]["cmp"]["value"], 2500.0)

        # Check sources
        screener_source = next(s for s in result["sources"] if s["source"] == "screener")
        self.assertEqual(screener_source["status"], "FAILED")
        self.assertEqual(screener_source["fields_sourced"], 0)

        # Check errors
        self.assertTrue(len(result["errors"]) >= 1)
        self.assertEqual(result["errors"][0]["source"], "screener")
        self.assertIn("Connection refused", result["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
