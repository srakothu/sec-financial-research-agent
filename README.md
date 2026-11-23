# SEC Financial Research Agent

**How much did Apple’s revenue grow in fiscal Q1 2026?** Apple reported $143.756 billion for the quarter, up $19.456 billion **(+15.65%)** from $124.300 billion a year earlier. The quarter ended in December 2025. Both sales figures appear on the same line of the company’s quarterly filing. [Apple Form 10-Q, “Total net sales”](https://www.sec.gov/Archives/edgar/data/320193/000032019326000006/aapl-20251227.htm)

This Python CLI answers questions like that one using SEC EDGAR. Each numeric answer includes the period, unit, XBRL concept, filing date, accession number, and document link. It also lists recent filings and retrieves passages from 8-K announcements and their earnings exhibits.

## Open the dashboard

On a Mac with the project installed, double-click **Open-Dashboard.command** in Finder. Your browser opens Filing Desk. The dashboard opens in **Live SEC lookup** mode. Enter a ticker and select **Run lookup** for the company dashboard. You can also choose a single metric, a filing list, or an earnings release. Revenue comparisons include a chart. Each result can be downloaded as a JSON evidence file with its sources. Your last five successful queries are stored in your browser for reuse. Choose **Apple sample** for the offline examples. Live requests use the contact configured in `.env`. To explore the four saved examples on any computer without Python, open `dashboard/index.html` in a browser.

### Company dashboard and analyst

A ticker search resolves the filer against the SEC ticker directory. The company dashboard examines up to six original 10-K, 20-F or 40-F filings and looks for consolidated US GAAP or IFRS facts. Annual revenue, profit, assets, diluted EPS and operating cash flow can be explored as dated series. Net margin requires matching revenue and net income periods and units. Revenue growth compares adjacent annual reports as originally filed. Issuers without comparable tagged metrics show gaps and filing links. Foreign listings outside EDGAR and issuer-specific extensions can limit coverage.

The **Trend investigation** fits a Theil–Sen regression to prior observations, holds out the latest year and compares the reported result to the historical baseline. It tries revenue, net income and then assets until it finds sufficient history in the same currency. This model runs without an external AI service.

The **AI analyst** is available when the host sets `OPENAI_API_KEY` on the server. Set it in Render under the service’s **Environment** settings and redeploy. Visitors can then request an AI brief. A model selects a research focus, Python gathers the corresponding series, and a second model call interprets the evidence. The app checks each cited period against the selected evidence before linking its filing. Valid citations do not guarantee that every interpretation is correct. Completed briefs are cached per lookup and fifteen-minute window. The single-worker deployment limits new brief attempts to six per rolling hour per worker lifetime. API usage is billed to the configured account.

### Host a public copy

[Deploy the dashboard on Render](https://render.com/deploy?repo=https://github.com/srakothu/sec-financial-research-agent). Sign in, review the free web service, and enter an app name plus your contact email for `SEC_USER_AGENT`. Apply the deployment. Open the service URL Render displays once it is live. The dashboard uses the existing Python research workflow and requires no OpenAI key.

## Run the demo

With Git and Python 3.12 installed, run the following in a macOS or Linux terminal.

```sh
git clone https://github.com/srakothu/sec-financial-research-agent.git
cd sec-financial-research-agent
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m sec_agent demo
python -m pytest -q
```

The four demo questions use a small, curated Apple dataset. They run through the same filing lookup, fact selection, and formatting code as the live commands. After installation the demo runs offline and needs no keys. To inspect a single result and the nodes that produced it, run

```sh
python -m sec_agent --sample --trace fact AAPL revenue --period quarterly --year 2026 --quarter 1 --yoy
```

```text
Apple Inc. (AAPL) — Revenue: 143,756,000,000 USD
Reporting period: 2025-09-28 to 2025-12-27 (FY2026 Q1)
Prior-year period: 2024-09-29 to 2024-12-28 · 124,300,000,000 USD
Year-over-year change: +19,456,000,000 USD (+15.65%)
Source: 10-Q · filed 2026-01-30 · Report end: 2025-12-27 · accession 0000320193-26-000006
https://www.sec.gov/Archives/edgar/data/320193/000032019326000006/aapl-20251227.htm
XBRL concept: us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax
```

## Query live filings

Copy `.env.example` to `.env` and set `SEC_USER_AGENT` to your app name and contact email. The SEC data APIs are public. The client spaces outgoing requests at least 250 milliseconds apart and reuses responses within each run. [SEC data access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

```sh
python -m sec_agent fact MSFT revenue --year 2025
python -m sec_agent fact AAPL revenue --period quarterly --year 2026 --quarter 1 --yoy
python -m sec_agent filings AAPL --form 10-Q
python -m sec_agent event AAPL --date 2025-05-01 --earnings
```

For natural-language questions, set `OPENAI_API_KEY` in the same file. `OPENAI_MODEL` defaults to `gpt-5-mini`. The chosen model must support Structured Outputs through the Responses API. The question goes to OpenAI and an 8-K query can also send retrieved excerpts for selection. [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs)

```sh
python -m sec_agent --trace ask "How much did Apple's FY2026 Q1 revenue grow year over year?"
python -m sec_agent ask "What did Apple's May 1, 2025 earnings 8-K say about quarterly revenue?"
```

## How an answer is built

1. A typed request identifies the company, metric, and period. Explicit commands construct it directly. Natural-language requests use the OpenAI Responses API to populate the same fields.
2. The SEC ticker map resolves the company to its CIK. The Submissions API identifies original filings and supplies their report dates and accession numbers.
3. A LangGraph workflow routes the request. Numeric queries join Company Facts to the filing by accession, then check tag, unit, period end, and duration. Growth also requires a comparable prior-year observation in that filing. Filing-list requests already have their evidence after discovery.
4. For an earnings 8-K, the client looks for a linked HTML Exhibit 99.1. A natural-language question can select up to three retrieved excerpts by ID. Python validates the IDs and renders the original passages and their source links. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

| Coverage | Supported inputs |
| --- | --- |
| Financial facts | One issuer and one consolidated US GAAP metric. Revenue, net income, operating income, total assets, diluted EPS, or operating cash flow. USD or USD per share. |
| Reporting periods | Annual 10-K or standalone fiscal Q1–Q3 from a 10-Q. Assets use a single balance-sheet date. A request for the latest period uses the latest original filing of that form. |
| Growth | Annual or quarterly year-over-year revenue change in dollars and percent. Requires comparable periods in the same filing, tag, and unit, with a positive prior-year base. |
| Filing research | Up to three recent original 10-K, 10-Q, or 8-K filings. 8-K excerpts support the latest filing or an exact filing date, optionally filtered to earnings Item 2.02. |

The scope excludes inferred Q4 results, separate amendments, segment metrics, and cross-company comparisons. A missing standalone quarter, unsupported tag, or ambiguous comparative produces an explanation. The demo represents only the dates and observations bundled in the sample.

The [selection logic](sec_agent/facts.py), [SEC client](sec_agent/edgar.py), [workflow](sec_agent/workflow.py), and [regression tests](tests/test_research.py) are the main entry points for reviewing the implementation.
