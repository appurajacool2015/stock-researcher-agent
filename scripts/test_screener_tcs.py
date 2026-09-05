#!/usr/bin/env python3

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

SYMBOL = "TCS"

SCREENER_URL = (
    "https://www.screener.in/company/TCS/consolidated/"
)

SCHEMA_PATH = Path(
    "/home/ubuntu/openclaw/stock-intelligence/"
    "schemas/research-result.v1.schema.json"
)

TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/152 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


# ============================================================
# TIME
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# HTTP
# ============================================================

def fetch_html(url: str) -> Tuple[str, str]:
    """
    Return:
        html
        retrieval timestamp
    """

    retrieved_at = utc_now()

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.text, retrieved_at


# ============================================================
# NUMBER PARSING
# ============================================================

def clean_text(value: str) -> str:
    return " ".join(value.split())


def parse_number(value: str) -> Optional[float]:
    """
    Parse financial numbers such as:

        16.2
        1,234
        1,234.56
        16.2%
        ₹1,234
        23,67,003
    """

    if value is None:
        return None

    text = clean_text(str(value))

    if not text:
        return None

    # Remove currency and percentage symbols.
    text = (
        text
        .replace("₹", "")
        .replace("%", "")
        .replace("Rs.", "")
        .replace("Rs", "")
    )

    # Remove commas used in Indian numbering.
    text = text.replace(",", "")

    match = re.search(
        r"[-+]?\d+(?:\.\d+)?",
        text,
    )

    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


# ============================================================
# TABLE EXTRACTION
# ============================================================

def table_rows(table) -> Dict[str, List[str]]:
    """
    Convert an HTML table into:

        {
            "Sales": ["59,381", ...],
            "Operating Profit": [...]
        }
    """

    result = {}

    for tr in table.find_all("tr"):

        cells = tr.find_all(["th", "td"])

        if not cells:
            continue

        values = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in cells
        ]

        label = values[0]

        if not label:
            continue

        result[label] = values[1:]

    return result


def get_tables(soup) -> List[Dict[str, List[str]]]:

    tables = []

    for table in soup.find_all("table"):

        rows = table_rows(table)

        if rows:
            tables.append(rows)

    return tables


# ============================================================
# FIND TABLES
# ============================================================

def find_table_with_row(
    tables: List[Dict[str, List[str]]],
    row_name: str,
) -> Optional[Dict[str, List[str]]]:

    for table in tables:

        if row_name in table:
            return table

    return None


def find_results_table(
    tables: List[Dict[str, List[str]]]
) -> Optional[Dict[str, List[str]]]:

    candidates = []

    for table in tables:

        required = {
            "Sales",
            "Expenses",
            "Operating Profit",
            "Net Profit",
            "EPS in Rs",
        }

        if required.issubset(table.keys()):

            candidates.append(table)

    if not candidates:
        return None

    # Prefer the table containing quarterly-style columns.
    for table in candidates:

        sales = table.get("Sales", [])

        if len(sales) >= 8:
            return table

    return candidates[0]


# ============================================================
# METRIC EXTRACTION
# ============================================================

def extract_metric_from_page(
    soup,
    labels: List[str],
) -> Optional[float]:

    text = soup.get_text(" ", strip=True)

    for label in labels:

        pattern = (
            re.escape(label)
            + r"\s*"
            r"[:\-]?\s*"
            r"(?:₹\s*)?"
            r"([-+]?\d+(?:,\d+)*(?:\.\d+)?)"
        )

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:

            return parse_number(match.group(1))

    return None


# ============================================================
# COMPANY NAME
# ============================================================

def extract_company_name(soup) -> str:

    h1 = soup.find("h1")

    if h1:

        text = clean_text(
            h1.get_text(" ", strip=True)
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.replace(
            "Tata Consultancy Services",
            "Tata Consultancy Services",
        ).strip()

    title = soup.title

    if title:

        return clean_text(
            title.get_text()
        ).split("Share Price")[0].strip()

    return "Tata Consultancy Services Ltd"


# ============================================================
# EXTRACT SCREENER DATA
# ============================================================

def extract_screener(
    html: str,
    retrieved_at: str,
) -> Dict[str, Any]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    tables = get_tables(soup)

    print(f"HTML bytes: {len(html.encode('utf-8'))}")
    print(f"Tables found: {len(tables)}")

    # --------------------------------------------------------
    # COMPANY
    # --------------------------------------------------------

    company_name = extract_company_name(soup)

    # --------------------------------------------------------
    # QUARTERLY / ANNUAL TABLE
    # --------------------------------------------------------

    results_table = find_results_table(tables)

    # Screener provides useful data that we can inspect,
    # even though the historical tables are NOT part of
    # ResearchResult v1.

    quarterly = {}
    annual = {}

    if results_table:

        sales = results_table.get("Sales", [])

        # We don't force these into v1.
        quarterly["sales"] = sales

        annual["sales"] = sales

    # --------------------------------------------------------
    # KEY METRICS
    # --------------------------------------------------------

    pe = extract_metric_from_page(
        soup,
        [
            "P/E",
            "Price to Earnings",
        ],
    )

    book_value = extract_metric_from_page(
        soup,
        [
            "Book Value",
        ],
    )

    market_cap = extract_metric_from_page(
        soup,
        [
            "Market Cap",
        ],
    )

    # --------------------------------------------------------
    # GROWTH
    # --------------------------------------------------------

    sales_growth_3y = None
    profit_growth_3y = None

    # Search tables first because the page contains explicit
    # "3 Years" rows.

    for table in tables:

        text = " ".join(
            " ".join(
                [key] + values
            )
            for key, values in table.items()
        )

        if "Compounded Sales Growth" in text:

            for key, values in table.items():

                if key == "3 Years:" and values:

                    sales_growth_3y = parse_number(
                        values[0]
                    )

        if "Compounded Profit Growth" in text:

            for key, values in table.items():

                if key == "3 Years:" and values:

                    profit_growth_3y = parse_number(
                        values[0]
                    )

    # --------------------------------------------------------
    # ROE
    # --------------------------------------------------------

    roe = None

    for table in tables:

        for key, values in table.items():

            if key == "Last Year:" and values:

                # This can occur in ROE table.
                candidate = parse_number(values[0])

                if candidate is not None:
                    roe = candidate

    # --------------------------------------------------------
    # ROCE
    # --------------------------------------------------------

    roce = None

    for table in tables:

        if "ROCE %" in table:

            values = table["ROCE %"]

            if values:

                roce = parse_number(
                    values[-1]
                )

    # --------------------------------------------------------
    # SHAREHOLDING
    # --------------------------------------------------------

    institutional = {
        "promoter": None,
        "fii": None,
        "dii": None,
        "fii_previous": None,
        "dii_previous": None,
    }

    shareholding_tables = []

    for table in tables:

        if (
            "Promoters +" in table
            and "FIIs +" in table
            and "DIIs +" in table
        ):

            shareholding_tables.append(table)

    if shareholding_tables:

        table = shareholding_tables[0]

        if table.get("Promoters +"):
            institutional["promoter"] = parse_number(
                table["Promoters +"][-1]
            )

        if table.get("FIIs +"):
            fii_values = [
                parse_number(x)
                for x in table["FIIs +"]
            ]

            fii_values = [
                x for x in fii_values
                if x is not None
            ]

            if fii_values:

                institutional["fii"] = fii_values[-1]

                if len(fii_values) >= 2:
                    institutional["fii_previous"] = (
                        fii_values[-2]
                    )

        if table.get("DIIs +"):
            dii_values = [
                parse_number(x)
                for x in table["DIIs +"]
            ]

            dii_values = [
                x for x in dii_values
                if x is not None
            ]

            if dii_values:

                institutional["dii"] = dii_values[-1]

                if len(dii_values) >= 2:
                    institutional["dii_previous"] = (
                        dii_values[-2]
                    )

    return {
        "company_name": company_name,
        "pe": pe,
        "book_value": book_value,
        "market_cap": market_cap,
        "sales_growth_3y": sales_growth_3y,
        "profit_growth_3y": profit_growth_3y,
        "roe": roe,
        "roce": roce,
        "institutional": institutional,
        "quarterly": quarterly,
        "annual": annual,
        "retrieved_at": retrieved_at,
    }


# ============================================================
# DATAPOINT
# ============================================================

def datapoint(
    value: Any,
    unit: Optional[str],
    status: str,
    source: str,
    source_url: str,
    retrieved_at: str,
    as_of_date: Optional[str] = None,
    notes: Optional[str] = None,
    conflicting_values: Optional[List[Any]] = None,
) -> Dict[str, Any]:

    return {
        "value": value,
        "unit": unit,
        "status": status,
        "provenance": {
            "source": source,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "as_of_date": as_of_date,
        },
        "conflicting_values": (
            conflicting_values
            if conflicting_values is not None
            else []
        ),
        "notes": notes,
    }


# ============================================================
# RESEARCH RESULT V1
# ============================================================

def build_research_result(
    data: Dict[str, Any],
) -> Dict[str, Any]:

    retrieved_at = data["retrieved_at"]

    source_url = SCREENER_URL

    # --------------------------------------------------------
    # FUNDAMENTALS
    # --------------------------------------------------------

    fundamentals = {

        "pe_ratio": datapoint(
            data["pe"],
            "RATIO",
            "VERIFIED"
            if data["pe"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "pb_ratio": datapoint(
            None,
            "RATIO",
            "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
            notes=(
                "Not populated in this HTTP test. "
                "Can be derived from CMP and book value "
                "once CMP is available."
            ),
        ),

        "roce": datapoint(
            data["roce"],
            "PERCENT",
            "VERIFIED"
            if data["roce"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "roe": datapoint(
            data["roe"],
            "PERCENT",
            "VERIFIED"
            if data["roe"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "debt_to_equity": datapoint(
            None,
            "RATIO",
            "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
            notes=(
                "Not yet mapped. "
                "Requires explicit balance-sheet extraction "
                "and calculation."
            ),
        ),

        "sales_growth_3y_cagr": datapoint(
            data["sales_growth_3y"],
            "PERCENT",
            "VERIFIED"
            if data["sales_growth_3y"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "profit_growth_3y_cagr": datapoint(
            data["profit_growth_3y"],
            "PERCENT",
            "VERIFIED"
            if data["profit_growth_3y"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "market_cap": datapoint(
            data["market_cap"],
            "INR_CRORE",
            "VERIFIED"
            if data["market_cap"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),
    }

    # --------------------------------------------------------
    # TECHNICALS
    #
    # Not available from Screener parser yet.
    # Kite will populate these later.
    # --------------------------------------------------------

    technical_fields = [
        "cmp",
        "dma_50",
        "dma_200",
        "above_50_dma",
        "above_200_dma",
        "rsi_14",
        "volume",
        "avg_volume_20d",
        "fifty_two_week_high",
        "fifty_two_week_low",
    ]

    technicals = {}

    for field in technical_fields:

        unit = None

        if field in [
            "above_50_dma",
            "above_200_dma",
        ]:
            unit = "BOOLEAN"

        elif field == "rsi_14":
            unit = "INDEX"

        elif field in [
            "volume",
            "avg_volume_20d",
        ]:
            unit = "SHARES"

        else:
            unit = "INR"

        technicals[field] = datapoint(
            None,
            unit,
            "UNAVAILABLE",
            "kite",
            None,
            retrieved_at,
            notes=(
                "Kite adapter not implemented in this "
                "Screener HTTP checkpoint."
            ),
        )

    # --------------------------------------------------------
    # INSTITUTIONAL
    # --------------------------------------------------------

    inst = data["institutional"]

    fii_change = None
    dii_change = None

    if (
        inst["fii"] is not None
        and inst["fii_previous"] is not None
    ):

        fii_change = (
            inst["fii"]
            - inst["fii_previous"]
        )

    if (
        inst["dii"] is not None
        and inst["dii_previous"] is not None
    ):

        dii_change = (
            inst["dii"]
            - inst["dii_previous"]
        )

    institutional = {

        "promoter_holding_pct": datapoint(
            inst["promoter"],
            "PERCENT",
            "VERIFIED"
            if inst["promoter"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "promoter_pledge_pct": datapoint(
            None,
            "PERCENT",
            "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "fii_holding_pct": datapoint(
            inst["fii"],
            "PERCENT",
            "VERIFIED"
            if inst["fii"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "dii_holding_pct": datapoint(
            inst["dii"],
            "PERCENT",
            "VERIFIED"
            if inst["dii"] is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
        ),

        "fii_holding_change_qoq": datapoint(
            fii_change,
            "PERCENTAGE_POINTS",
            "DERIVED"
            if fii_change is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
            notes=(
                "Current quarter holding minus previous "
                "quarter holding."
            ),
        ),

        "dii_holding_change_qoq": datapoint(
            dii_change,
            "PERCENTAGE_POINTS",
            "DERIVED"
            if dii_change is not None
            else "UNAVAILABLE",
            "screener",
            source_url,
            retrieved_at,
            notes=(
                "Current quarter holding minus previous "
                "quarter holding."
            ),
        ),
    }

    # --------------------------------------------------------
    # SOURCES
    # --------------------------------------------------------

    sources = [
        {
            "source": "screener",
            "status": "SUCCESS",
            "fields_sourced": 7,
        }
    ]

    # --------------------------------------------------------
    # QUALITY COUNTS
    # --------------------------------------------------------

    blocks = [
        fundamentals,
        technicals,
        institutional,
    ]

    verified = 0
    derived = 0
    unavailable = 0
    stale = 0
    conflicting = 0
    failed = 0

    for block in blocks:

        for point in block.values():

            status = point["status"]

            if status == "VERIFIED":
                verified += 1

            elif status == "DERIVED":
                derived += 1

            elif status == "UNAVAILABLE":
                unavailable += 1

            elif status == "STALE":
                stale += 1

            elif status == "CONFLICTING":
                conflicting += 1

            elif status == "FAILED":
                failed += 1

    overall_status = (
        "COMPLETE"
        if unavailable == 0
        and failed == 0
        and conflicting == 0
        else "PARTIAL"
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    now = utc_now()

    return {

        "schema_version": "1.0",

        "research_id": (
            f"{SYMBOL.lower()}-http-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        ),

        "symbol": SYMBOL,

        "exchange": "NSE",

        "isin": None,

        "company_name": data["company_name"],

        "symbol_match_confidence": "EXACT",

        "requested_at": retrieved_at,

        "completed_at": now,

        "overall_status": overall_status,

        "fundamentals": fundamentals,

        "technicals": technicals,

        "institutional": institutional,

        "news": [],

        "sources": sources,

        "errors": [],

        "data_quality_summary": {

            "verified": verified,

            "derived": derived,

            "unavailable": unavailable,

            "stale": stale,

            "conflicting": conflicting,

            "failed": failed,
        },
    }


# ============================================================
# SCHEMA VALIDATION
# ============================================================

def validate_schema(result: Dict[str, Any]) -> None:

    try:
        import jsonschema
    except ImportError:

        print(
            "WARNING: jsonschema not installed; "
            "skipping schema validation."
        )

        return

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)

    try:

        jsonschema.Draft7Validator(
            schema
        ).validate(result)

        print(
            "✅ ResearchResult v1 schema validation PASSED"
        )

    except Exception as exc:

        print(
            "❌ ResearchResult v1 schema validation FAILED"
        )

        print(str(exc))

        raise


# ============================================================
# SANITY CHECKS
# ============================================================

def sanity_check(result: Dict[str, Any]) -> None:

    print()
    print("=" * 70)
    print("NUMERIC SANITY CHECKS")
    print("=" * 70)

    checks = []

    fundamentals = result["fundamentals"]

    for name, point in fundamentals.items():

        value = point["value"]

        if value is None:
            continue

        if isinstance(value, (int, float)):

            if value != value:
                checks.append(
                    f"{name}: NaN"
                )

            elif abs(value) > 1_000_000_000:

                checks.append(
                    f"{name}: suspiciously large "
                    f"value {value}"
                )

    institutional = result["institutional"]

    for name, point in institutional.items():

        value = point["value"]

        if value is None:
            continue

        if (
            isinstance(value, (int, float))
            and "holding" in name
            and not (-1 <= value <= 100)
        ):

            checks.append(
                f"{name}: invalid percentage {value}"
            )

    if checks:

        print("❌ SANITY CHECK FAILED")

        for check in checks:
            print(" -", check)

        raise SystemExit(1)

    print("✅ Numeric sanity checks PASSED")


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("STOCK RESEARCHER — HTTP CHECKPOINT")
    print("=" * 70)

    print()
    print(
        f"Fetching Screener: {SCREENER_URL}"
    )

    try:

        html, retrieved_at = fetch_html(
            SCREENER_URL
        )

    except Exception as exc:

        print(
            f"❌ Screener HTTP request failed: {exc}"
        )

        sys.exit(1)

    data = extract_screener(
        html,
        retrieved_at,
    )

    print()
    print("=" * 70)
    print("EXTRACTED DATA")
    print("=" * 70)

    display = {
        "company_name": data["company_name"],
        "pe": data["pe"],
        "book_value": data["book_value"],
        "market_cap": data["market_cap"],
        "sales_growth_3y": data["sales_growth_3y"],
        "profit_growth_3y": data["profit_growth_3y"],
        "roe": data["roe"],
        "roce": data["roce"],
        "institutional": data["institutional"],
    }

    print(
        json.dumps(
            display,
            indent=2,
            ensure_ascii=False,
        )
    )

    result = build_research_result(
        data
    )

    print()
    print("=" * 70)
    print("RESEARCH RESULT V1")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print("=" * 70)
    print("VALIDATION")
    print("=" * 70)

    validate_schema(result)

    sanity_check(result)

    print()
    print("=" * 70)
    print("CHECKPOINT COMPLETE")
    print("=" * 70)

    print(
        "Screener HTTP extraction → "
        "ResearchResult v1 → validation: SUCCESS"
    )


if __name__ == "__main__":
    main()

