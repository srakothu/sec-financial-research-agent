import json

import httpx
import pytest
from openai import OpenAI

from sec_agent.demo import demo_client, demo_queries
from sec_agent.edgar import Edgar, extract_excerpts
from sec_agent.facts import revenue_growth, select_fact
from sec_agent.llm import OpenAIResearch
from sec_agent.models import Excerpt, Filing, Query, ResearchError
from sec_agent.workflow import build_graph

REVENUE_TAG = "RevenueFromContractWithCustomerExcludingAssessedTax"
QUARTER = Filing(
    320193, "10-Q", "0000320193-25-000057", "2025-05-02", "2025-03-29",
    "aapl-20250329.htm", "",
)


@pytest.mark.parametrize(("index", "answer", "source"), [
    (0, "416,161,000,000 USD", "2024-09-29 to 2025-09-27 (FY2025)"),
    (1, "143,756,000,000 USD", "2025-09-28 to 2025-12-27 (FY2026 Q1)"),
    (2, "recent SEC filings", "aapl-20250501.htm"),
    (3, "$95.4 billion", "a8-kex991q2202503292025.htm"),
])
def test_demo_branches(index, answer, source):
    with demo_client() as client:
        result = build_graph(Edgar(client, interval=0)).invoke({"query": demo_queries()[index][1]})
    assert answer in result["answer"]
    assert source in result["answer"]
    if index < 2:
        assert result["fact"].filing.url in result["answer"]
        assert result["fact"].filing.accession in result["answer"]
    if index == 1:
        assert "124,300,000,000 USD" in result["answer"]
        assert "+19,456,000,000 USD (+15.65%)" in result["answer"]


def test_annual_growth_uses_comparative_column_in_current_filing():
    annual = demo_queries()[0][1].model_copy(update={"year_over_year": True})
    with demo_client() as client:
        result = build_graph(Edgar(client, interval=0)).invoke({"query": annual})
    assert "2023-10-01 to 2024-09-28" in result["answer"]
    assert "+25,126,000,000 USD (+6.43%)" in result["answer"]


def quarter_row(**updates):
    return {
        "start": "2024-12-29", "end": QUARTER.report_date, "accn": QUARTER.accession,
        "form": "10-Q", "fy": 2025, "fp": "Q2", "val": 95_359_000_000,
    } | updates


def concepts(tag, *rows, unit="USD"):
    return {"facts": {"us-gaap": {tag: {"units": {unit: rows}}}}}


def quarterly_query(metric="revenue"):
    return Query(intent="fact", company="AAPL", metric=metric, period="quarterly")


def test_ignores_year_to_date_and_comparative_rows_even_with_same_fy_fp():
    data = concepts(
        REVENUE_TAG, quarter_row(start="2024-09-29", val=219_659_000_000),
        quarter_row(start="2023-12-31", end="2024-03-30", val=90_753_000_000),
        quarter_row(accn="0000320193-26-000022", val=77), quarter_row(),
    )
    fact = select_fact(data, [QUARTER], quarterly_query())
    assert fact.value == 95_359_000_000
    assert fact.start == "2024-12-29"


def test_ignores_year_to_date_when_no_standalone_quarter_exists():
    data = concepts(
        "NetCashProvidedByUsedInOperatingActivities", quarter_row(start="2024-09-29"),
    )
    with pytest.raises(ResearchError, match="No supported operating cash flow"):
        select_fact(data, [QUARTER], quarterly_query("operating_cash_flow"))


def test_conflicting_values_for_the_same_period_fail_closed():
    data = concepts(REVENUE_TAG, quarter_row(), quarter_row(val=1))
    with pytest.raises(ResearchError, match="conflicting candidates"):
        select_fact(data, [QUARTER], quarterly_query())


@pytest.mark.parametrize(("previous", "error"), [
    ([], "found 0"),
    ([{"val": 0}], "positive prior-year"),
    ([{"val": 1}, {"val": 2}], "found 2"),
    ([{"start": "2023-10-01"}], "found 0"),
    ([{"accn": "0000320193-24-000069"}], "found 0"),
])
def test_growth_rejects_unusable_comparatives(previous, error):
    prior = quarter_row(start="2023-12-31", end="2024-03-30")
    data = concepts(REVENUE_TAG, quarter_row(), *(prior | override for override in previous))
    fact = select_fact(data, [QUARTER], quarterly_query())
    with pytest.raises(ResearchError, match=error):
        revenue_growth(data, fact)


def test_revenue_decline_and_duplicate_prior_observation():
    prior = quarter_row(start="2023-12-31", end="2024-03-30", val=100)
    data = concepts(REVENUE_TAG, quarter_row(val=80), prior, prior)
    fact = select_fact(data, [QUARTER], quarterly_query())
    assert revenue_growth(data, fact).percent == -20


def test_growth_rejects_non_revenue_metric():
    with pytest.raises(ResearchError, match="for revenue only"):
        quarterly_query("diluted_eps").model_copy(update={"year_over_year": True}).check()


def test_snapshot_and_per_share_units():
    instant = quarter_row(val=100_000)
    instant.pop("start")
    asset = select_fact(concepts("Assets", instant), [QUARTER], quarterly_query("total_assets"))
    eps = select_fact(
        concepts("EarningsPerShareDiluted", quarter_row(val=1.65), unit="USD/shares"),
        [QUARTER], quarterly_query("diluted_eps"),
    )
    assert asset.start is None and asset.end == QUARTER.report_date
    assert eps.value == 1.65 and eps.unit == "USD/shares"


def test_lookup_fails_clearly_and_quarter_requires_a_year():
    with demo_client() as client:
        graph = build_graph(Edgar(client, interval=0))
        with pytest.raises(ResearchError, match="Could not resolve"):
            graph.invoke({"query": Query(intent="filings", company="NOTATICKER")})
        with pytest.raises(ResearchError, match="both a fiscal year and Q1"):
            graph.invoke({"query": quarterly_query().model_copy(update={"quarter": 1})})


def test_8k_parser_omits_hidden_content_and_signatures():
    html = """
    <p>Cover text that should not appear in the result.</p>
    <h2>Item 5.02 Departure of Directors or Certain Officers.</h2>
    <ix:hidden><div>This Inline XBRL content should be hidden.</div></ix:hidden>
    <p>The company's chief executive officer gave notice of resignation.</p>
    <p>SIGNATURES</p><p>This signature block should not be included.</p>
    """
    result = extract_excerpts(html, "https://www.sec.gov/example.htm", "8-K")
    assert len(result) == 1
    assert result[0].text.startswith("The company's chief executive officer")
    assert result[0].section.startswith("Item 5.02")


def test_sec_rate_limit_reports_clear_error():
    transport = httpx.MockTransport(lambda _: httpx.Response(429))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ResearchError, match="HTTP 429"):
            Edgar(client, interval=0).lookup("AAPL")


def model_response(payload):
    return httpx.Response(200, json={
        "id": "resp_test", "object": "response", "created_at": 0, "model": "gpt-5-mini",
        "status": "completed", "tools": [], "parallel_tool_calls": False,
        "tool_choice": "none", "output": [{
            "id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(payload), "annotations": []}],
        }],
    })


def test_openai_sdk_parses_intent_and_selects_existing_evidence():
    seen = []

    def mock_openai(request):
        assert request.url.path.endswith("/responses")
        body = json.loads(request.content)
        seen.append(body)
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False
        if body["text"]["format"]["name"] == "Query":
            query = demo_queries()[3][1]
            return model_response(query.model_dump())
        excerpts = json.loads(body["input"])["excerpts"]
        assert excerpts[1]["document"] == "Exhibit 99.1"
        return model_response({"ids": [2]})

    with demo_client() as sec, OpenAI(
        api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(mock_openai))
    ) as client:
        graph = build_graph(Edgar(sec, interval=0), OpenAIResearch(client, "gpt-5-mini"))
        result = graph.invoke({"question": demo_queries()[3][0]})
    assert len(seen) == 2
    assert "$95.4 billion" in result["answer"]
    assert len(result["excerpts"]) == 1
    assert result["excerpts"][0].label == "Exhibit 99.1"


def test_model_cannot_cite_an_unknown_excerpt_id():
    transport = httpx.MockTransport(lambda _: model_response({"ids": [99]}))
    with OpenAI(api_key="test-key", http_client=httpx.Client(transport=transport)) as client:
        model = OpenAIResearch(client, "gpt-5-mini")
        with pytest.raises(ResearchError, match="invalid evidence IDs"):
            model.choose_excerpts("What happened?", [Excerpt("8-K", "https://www.sec.gov/", "text")])
