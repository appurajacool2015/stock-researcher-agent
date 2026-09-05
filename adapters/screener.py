#!/usr/bin/env python3

import json
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup


class ScreenerAdapter:
    """
    Screener.in adapter.

    Responsibilities:
      - Fetch Screener company pages
      - Parse financial tables
      - Extract fundamental metrics
      - Extract institutional/shareholding metrics
      - Extract period/as-of dates
      - Return normalized adapter output

    It does NOT:
      - perform investment analysis
      - assign stock ratings
      - make investment decisions
      - modify ResearchResult schema
    """

    # =========================================================
    # CONFIGURATION
    # =========================================================

    BASE_URL = (
        "https://www.screener.in/company/"
        "{symbol}/consolidated/"
    )

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    TIMEOUT = 30

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            self.HEADERS
        )

    # =========================================================
    # TIME
    # =========================================================

    @staticmethod
    def utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    # =========================================================
    # TEXT HELPERS
    # =========================================================

    @staticmethod
    def clean_text(
        value: Any,
    ) -> str:

        if value is None:
            return ""

        text = str(value)

        text = (
            text
            .replace("\xa0", " ")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("\t", " ")
        )

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

    @staticmethod
    def normalize_label(
        value: Any,
    ) -> str:

        text = ScreenerAdapter.clean_text(
            value
        ).lower()

        text = text.replace(
            "+",
            "",
        )

        text = re.sub(
            r"[^a-z0-9]+",
            " ",
            text,
        )

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

    # =========================================================
    # NUMBER PARSING
    # =========================================================

    @staticmethod
    def parse_number(
        value: Any,
    ) -> Optional[float]:
        """
        Convert Screener numeric text into float.

        Examples:

            16.2
            8.00
            869,924
            71.77%
            -0.59%
        """

        if value is None:
            return None

        if isinstance(
            value,
            (int, float),
        ):
            return float(value)

        text = (
            ScreenerAdapter.clean_text(
                value
            )
        )

        if not text:
            return None

        # Remove commas and percent signs.
        text = (
            text
            .replace(",", "")
            .replace("%", "")
        )

        # Keep only a numeric representation.
        match = re.search(
            r"[-+]?\d+(?:\.\d+)?",
            text,
        )

        if not match:
            return None

        try:
            return float(
                match.group(0)
            )
        except ValueError:
            return None

    # =========================================================
    # HTTP
    # =========================================================

    def fetch(
        self,
        symbol: str,
    ) -> str:

        symbol = (
            symbol
            .upper()
            .strip()
        )

        if not symbol:
            raise ValueError(
                "Stock symbol cannot be empty"
            )

        url = self.BASE_URL.format(
            symbol=symbol
        )

        response = self.session.get(
            url,
            timeout=self.TIMEOUT,
        )

        response.raise_for_status()

        if not response.text:
            raise RuntimeError(
                f"Empty response from Screener for {symbol}"
            )

        return response.text

    # =========================================================
    # TABLE PARSING
    # =========================================================

    @staticmethod
    def parse_tables(
        html: str,
    ):
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        return soup.find_all(
            "table"
        )

    def table_to_dict(
        self,
        table,
    ) -> Dict[str, list]:

        result: Dict[str, list] = {}

        rows = table.find_all(
            "tr"
        )

        for row in rows:

            cells = row.find_all(
                ["th", "td"]
            )

            if not cells:
                continue

            values = [
                self.clean_text(
                    cell.get_text(
                        " ",
                        strip=True,
                    )
                )
                for cell in cells
            ]

            if not values:
                continue

            label = values[0]

            if not label:
                continue

            result[label] = values[1:]

        return result

    # =========================================================
    # TABLE METRIC
    # =========================================================

    def find_metric(
        self,
        table_objects,
        metric_name: str,
    ) -> Optional[float]:

        target = self.normalize_label(
            metric_name
        )

        for table in table_objects:

            data = self.table_to_dict(
                table
            )

            for label, values in data.items():

                normalized = (
                    self.normalize_label(
                        label
                    )
                )

                if normalized != target:
                    continue

                # Screener stores historical
                # values left-to-right.
                # Last numeric value is latest.
                for value in reversed(values):

                    parsed = self.parse_number(
                        value
                    )

                    if parsed is not None:
                        return parsed

        return None

    # =========================================================
    # TABLE SEARCH
    # =========================================================

    def find_table_containing(
        self,
        tables,
        text: str,
    ) -> Optional[Any]:

        target = text.lower()

        for table in tables:

            table_text = self.clean_text(
                table.get_text(
                    " ",
                    strip=True,
                )
            ).lower()

            if target in table_text:
                return table

        return None

    # =========================================================
    # SNAPSHOT METRICS
    # =========================================================

    def find_snapshot_metric(
        self,
        soup: BeautifulSoup,
        metric_name: str,
    ) -> Optional[float]:
        """
        Extract a metric from Screener's top
        company snapshot.

        Screener renders metrics approximately as:

            <li>
                <span class="name">
                    Market Cap
                </span>
                ...
                <span class="number">
                    868088
                </span>
            </li>

        We locate the <span class="name"> and
        inspect its containing <li>.
        """

        target = self.normalize_label(
            metric_name
        )

        name_spans = soup.select(
            "span.name"
        )

        for name_span in name_spans:

            label = self.clean_text(
                name_span.get_text(
                    " ",
                    strip=True,
                )
            )

            if (
                self.normalize_label(label)
                != target
            ):
                continue

            # The metric normally lives inside
            # the surrounding <li>.
            container = name_span.find_parent(
                "li"
            )

            if container is None:
                container = (
                    name_span.parent
                )

            if container is None:
                continue

            # Prefer explicit numeric spans.
            number_nodes = container.select(
                ".number"
            )

            for node in number_nodes:

                value = self.parse_number(
                    node.get_text(
                        " ",
                        strip=True,
                    )
                )

                if value is not None:
                    return value

            # Fallback: inspect all text inside
            # the metric container.
            texts = list(
                container.stripped_strings
            )

            # Skip the label itself and look
            # for the first numeric value.
            for text in texts[1:]:

                value = self.parse_number(
                    text
                )

                if value is not None:
                    return value

        return None

    # =========================================================
    # COMPANY NAME
    # =========================================================

    def extract_company_name(
        self,
        soup: BeautifulSoup,
    ) -> Optional[str]:
        """
        Extract the actual company name rather
        than the browser <title>.
        """

        selectors = [
            "h1",
            "#top h1",
            ".company-name h1",
        ]

        for selector in selectors:

            node = soup.select_one(
                selector
            )

            if node is None:
                continue

            text = self.clean_text(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

            if text:

                text = re.split(
                    r"\s+share price\s*\|",
                    text,
                    flags=re.IGNORECASE,
                )[0]

                return text.strip()

        title = soup.find(
            "title"
        )

        if title is not None:

            text = self.clean_text(
                title.get_text(
                    " ",
                    strip=True,
                )
            )

            if text:
                return text

        return None

    # =========================================================
    # GROWTH
    # =========================================================

    def extract_growth(
        self,
        tables,
    ) -> Dict[str, Optional[float]]:
        """
        Extract 3-year CAGR growth metrics.

        Screener normally exposes:

            Compounded Sales Growth
            3 Years: X%

            Compounded Profit Growth
            3 Years: X%
        """

        result = {
            "sales_growth_3y": None,
            "profit_growth_3y": None,
        }

        for table in tables:

            rows = table.find_all(
                "tr"
            )

            if not rows:
                continue

            table_text = self.clean_text(
                table.get_text(
                    " ",
                    strip=True,
                )
            ).lower()

            # -------------------------------------------------
            # Sales growth
            # -------------------------------------------------

            if (
                "compounded sales growth"
                in table_text
            ):

                for row in rows:

                    cells = row.find_all(
                        ["th", "td"]
                    )

                    values = [
                        self.clean_text(
                            cell.get_text(
                                " ",
                                strip=True,
                            )
                        )
                        for cell in cells
                    ]

                    if not values:
                        continue

                    label = self.normalize_label(
                        values[0]
                    )

                    if label == "3 years":

                        if len(values) > 1:

                            result[
                                "sales_growth_3y"
                            ] = self.parse_number(
                                values[1]
                            )

            # -------------------------------------------------
            # Profit growth
            # -------------------------------------------------

            if (
                "compounded profit growth"
                in table_text
            ):

                for row in rows:

                    cells = row.find_all(
                        ["th", "td"]
                    )

                    values = [
                        self.clean_text(
                            cell.get_text(
                                " ",
                                strip=True,
                            )
                        )
                        for cell in cells
                    ]

                    if not values:
                        continue

                    label = self.normalize_label(
                        values[0]
                    )

                    if label == "3 years":

                        if len(values) > 1:

                            result[
                                "profit_growth_3y"
                            ] = self.parse_number(
                                values[1]
                            )

        return result

    # =========================================================
    # SHAREHOLDING
    # =========================================================

    def extract_shareholding(
        self,
        tables,
    ) -> Dict[str, Optional[float]]:
        """
        Extract latest and previous-quarter
        promoter/FII/DII holdings.

        Returns:

            promoter
            promoter_previous
            fii
            fii_previous
            dii
            dii_previous
            promoter_pledge
        """

        result = {
            "promoter": None,
            "promoter_previous": None,
            "fii": None,
            "fii_previous": None,
            "dii": None,
            "dii_previous": None,
            "promoter_pledge": None,
        }

        # Prefer the quarterly shareholding table.
        candidate_tables = []

        for table in tables:

            table_text = self.clean_text(
                table.get_text(
                    " ",
                    strip=True,
                )
            ).lower()

            if (
                "promoters" in table_text
                and "fiis" in table_text
                and "diis" in table_text
            ):
                candidate_tables.append(
                    table
                )

        # If multiple tables qualify, the first
        # matching one is the standard quarterly
        # shareholding table in the observed page.
        for table in candidate_tables:

            rows = table.find_all(
                "tr"
            )

            for row in rows:

                cells = row.find_all(
                    ["th", "td"]
                )

                values = [
                    self.clean_text(
                        cell.get_text(
                            " ",
                            strip=True,
                        )
                    )
                    for cell in cells
                ]

                if not values:
                    continue

                normalized = (
                    self.normalize_label(
                        values[0]
                    )
                )

                numeric_values = []

                for value in values[1:]:

                    parsed = self.parse_number(
                        value
                    )

                    if parsed is not None:
                        numeric_values.append(
                            parsed
                        )

                if len(numeric_values) < 1:
                    continue

                current = (
                    numeric_values[-1]
                )

                previous = (
                    numeric_values[-2]
                    if len(numeric_values) >= 2
                    else None
                )

                if normalized == "promoters":

                    result[
                        "promoter"
                    ] = current

                    result[
                        "promoter_previous"
                    ] = previous

                elif normalized == "fiis":

                    result[
                        "fii"
                    ] = current

                    result[
                        "fii_previous"
                    ] = previous

                elif normalized == "diis":

                    result[
                        "dii"
                    ] = current

                    result[
                        "dii_previous"
                    ] = previous

            # We found the expected table.
            if (
                result["promoter"] is not None
                or result["fii"] is not None
                or result["dii"] is not None
            ):
                break

        # -----------------------------------------------------
        # Promoter pledge
        # -----------------------------------------------------

        # Keep this conservative. If Screener exposes an
        # explicit pledge metric, attempt to find it.
        pledge_names = [
            "Promoter Pledge",
            "Pledged",
            "Promoter Pledge %",
        ]

        # No assumption is made if the page does not expose
        # a usable metric.
        for table in tables:

            for metric_name in pledge_names:

                value = self.find_metric(
                    [table],
                    metric_name,
                )

                if value is not None:

                    result[
                        "promoter_pledge"
                    ] = value

                    break

            if result[
                "promoter_pledge"
            ] is not None:
                break

        return result

    # =========================================================
    # PERIOD DATE HELPERS
    # =========================================================

    @staticmethod
    def parse_period_date(
        value: str,
    ) -> Optional[str]:
        """
        Convert Screener period labels such as:

            Mar 2026
            Jun 2026
            Sep 2025

        into ISO calendar dates representing
        the end of that period.

        Examples:

            Mar 2026 -> 2026-03-31
            Jun 2026 -> 2026-06-30
            Sep 2025 -> 2025-09-30
            Dec 2025 -> 2025-12-31
        """

        value = (
            value
            .strip()
            .replace("\xa0", " ")
        )

        match = re.fullmatch(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+(\d{4})",
            value,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        month_text = (
            match.group(1).lower()
        )

        year = int(
            match.group(2)
        )

        month_map = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }

        month = month_map[
            month_text
        ]

        # Determine actual final day of month.
        if month == 2:

            leap_year = (
                year % 400 == 0
                or (
                    year % 4 == 0
                    and year % 100 != 0
                )
            )

            day = (
                29
                if leap_year
                else 28
            )

        elif month in [
            4,
            6,
            9,
            11,
        ]:

            day = 30

        else:

            day = 31

        return (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        )

    # =========================================================
    # AS-OF DATES
    # =========================================================

    def extract_as_of_dates(
        self,
        tables,
    ) -> Dict[str, Optional[str]]:
        """
        Determine the period represented by each
        logical Screener data block.

        Fundamentals:
            Latest annual financial period.

        Institutional:
            Latest quarterly shareholding period.

        Example for the current TCS page:

            fundamentals -> 2026-03-31
            institutional -> 2026-06-30
        """

        fundamentals_date = None
        institutional_date = None

        # =====================================================
        # FUNDAMENTALS
        # =====================================================

        # Financial statement tables have annual headers
        # such as:
        #
        # Mar 2024
        # Mar 2025
        # Mar 2026
        #
        # We deliberately use annual "Mar YYYY" periods
        # rather than the newest date anywhere on the page.
        for table in tables:

            rows = table.find_all(
                "tr"
            )

            if not rows:
                continue

            first_row = rows[0]

            cells = first_row.find_all(
                ["th", "td"]
            )

            headers = [
                self.clean_text(
                    cell.get_text(
                        " ",
                        strip=True,
                    )
                )
                for cell in cells
            ]

            annual_dates = []

            for header in headers:

                if not re.fullmatch(
                    r"Mar\s+\d{4}",
                    header,
                    flags=re.IGNORECASE,
                ):
                    continue

                parsed = (
                    self.parse_period_date(
                        header
                    )
                )

                if parsed:
                    annual_dates.append(
                        parsed
                    )

            if annual_dates:

                latest = max(
                    annual_dates
                )

                if (
                    fundamentals_date is None
                    or latest > fundamentals_date
                ):
                    fundamentals_date = latest

        # =====================================================
        # INSTITUTIONAL
        # =====================================================

        # Find the shareholding table containing
        # Promoters / FIIs / DIIs.
        for table in tables:

            table_text = self.clean_text(
                table.get_text(
                    " ",
                    strip=True,
                )
            ).lower()

            if "promoters" not in table_text:
                continue

            if "fiis" not in table_text:
                continue

            rows = table.find_all(
                "tr"
            )

            if not rows:
                continue

            first_row = rows[0]

            cells = first_row.find_all(
                ["th", "td"]
            )

            headers = [
                self.clean_text(
                    cell.get_text(
                        " ",
                        strip=True,
                    )
                )
                for cell in cells
            ]

            quarter_dates = []

            for header in headers:

                if not re.fullmatch(
                    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                    r"\s+\d{4}",
                    header,
                    flags=re.IGNORECASE,
                ):
                    continue

                parsed = (
                    self.parse_period_date(
                        header
                    )
                )

                if parsed:
                    quarter_dates.append(
                        parsed
                    )

            if quarter_dates:

                latest = max(
                    quarter_dates
                )

                if (
                    institutional_date is None
                    or latest > institutional_date
                ):
                    institutional_date = latest

        return {
            "fundamentals": fundamentals_date,
            "institutional": institutional_date,
        }

    # =========================================================
    # FUNDAMENTALS
    # =========================================================

    def extract_fundamentals(
        self,
        soup: BeautifulSoup,
        tables,
    ) -> Dict[str, Optional[float]]:

        # -----------------------------------------------------
        # Snapshot metrics
        # -----------------------------------------------------

        pe = self.find_snapshot_metric(
            soup,
            "Stock P/E",
        )

        book_value = self.find_snapshot_metric(
            soup,
            "Book Value",
        )

        market_cap = self.find_snapshot_metric(
            soup,
            "Market Cap",
        )

        roe = self.find_snapshot_metric(
            soup,
            "ROE",
        )

        # ROCE is available in the financial tables.
        roce = self.find_metric(
            tables,
            "ROCE %",
        )

        # -----------------------------------------------------
        # Debt / Equity
        # -----------------------------------------------------

        debt_to_equity = None

        for metric_name in [
            "Debt to equity",
            "Debt / Equity",
            "Debt-to-equity",
            "D/E",
        ]:

            debt_to_equity = (
                self.find_snapshot_metric(
                    soup,
                    metric_name,
                )
            )

            if debt_to_equity is not None:
                break

        # -----------------------------------------------------
        # Growth
        # -----------------------------------------------------

        growth = self.extract_growth(
            tables
        )

        return {
            "pe": pe,
            "book_value": book_value,
            "market_cap": market_cap,
            "roe": roe,
            "roce": roce,
            "debt_to_equity": (
                debt_to_equity
            ),
            "sales_growth_3y": growth[
                "sales_growth_3y"
            ],
            "profit_growth_3y": growth[
                "profit_growth_3y"
            ],
        }

    # =========================================================
    # RESEARCH
    # =========================================================

    def research(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        symbol = (
            symbol
            .upper()
            .strip()
        )

        if not symbol:
            raise ValueError(
                "Stock symbol cannot be empty"
            )

        retrieved_at = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        url = self.BASE_URL.format(
            symbol=symbol
        )

        html = self.fetch(
            symbol
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        tables = self.parse_tables(
            html
        )

        company_name = (
            self.extract_company_name(
                soup
            )
        )

        fundamentals = (
            self.extract_fundamentals(
                soup,
                tables,
            )
        )

        institutional = (
            self.extract_shareholding(
                tables
            )
        )

        as_of_dates = (
            self.extract_as_of_dates(
                tables
            )
        )

        return {
            "symbol": symbol,

            "company_name": (
                company_name
                or symbol
            ),

            "url": url,

            "retrieved_at": (
                retrieved_at
            ),

            "as_of_dates": as_of_dates,

            "html_bytes": len(
                html.encode("utf-8")
            ),

            "table_count": len(
                tables
            ),

            "fundamentals": fundamentals,

            "institutional": institutional,
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

    adapter = ScreenerAdapter()

    try:

        result = adapter.research(
            symbol
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
            )
        )

        raise


if __name__ == "__main__":
    main()
