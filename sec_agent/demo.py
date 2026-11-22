import json
from pathlib import Path

import httpx

from .edgar import DATA, SUBMISSIONS, TICKERS
from .models import Query

APPLE = "0000320193"
EVENT_ACCESSION = "0000320193-25-000055"
EVENT_DIR = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000055/"
EVENT_DOC = "aapl-20250501.htm"
EXHIBIT_DOC = "a8-kex991q2202503292025.htm"


def demo_client() -> httpx.Client:
    sample = json.loads((Path(__file__).parent / "sample" / "apple.json").read_text(encoding="utf-8"))
    responses = {
        TICKERS: ("json", sample["tickers"]),
        f"{SUBMISSIONS}CIK{APPLE}.json": ("json", sample["submissions"]),
        f"{DATA}/api/xbrl/companyfacts/CIK{APPLE}.json": ("json", sample["companyfacts"]),
        EVENT_DIR + EVENT_DOC: ("text", sample["8-k"]),
        EVENT_DIR + EVENT_ACCESSION + "-index.htm": ("text", sample["index"]),
        EVENT_DIR + EXHIBIT_DOC: ("text", sample["exhibit"]),
    }

    def handle(request: httpx.Request) -> httpx.Response:
        response = responses.get(str(request.url))
        if response is None:
            return httpx.Response(404)
        body_type, data = response
        return httpx.Response(200, **{body_type: data})

    return httpx.Client(transport=httpx.MockTransport(handle))


def demo_queries() -> list[tuple[str, Query]]:
    return [
        (
            "What was Apple's FY2025 revenue?",
            Query(intent="fact", company="AAPL", metric="revenue", period="annual", fiscal_year=2025),
        ),
        (
            "How much did Apple's FY2026 Q1 revenue grow year over year?",
            Query(
                intent="fact", company="AAPL", metric="revenue",
                period="quarterly", fiscal_year=2026, quarter=1, year_over_year=True,
            ),
        ),
        (
            "Which forms are in the Apple sample?",
            Query(intent="filings", company="AAPL"),
        ),
        (
            "What did Apple's May 1, 2025 earnings 8-K announce?",
            Query(intent="event", company="AAPL", earnings_only=True, event_date="2025-05-01"),
        ),
    ]
