# SEC Financial Research Agent

[Open Filing Desk](https://sec-financial-research-agent.onrender.com/) to research a public company using live SEC filings. Search by ticker, CIK, or exact SEC company name. Choose **Run lookup**, or select a company from the landing page to open its report.

## Use the dashboard

The overview opens with the latest reported revenue, net income, operating cash flow and net margin. Select **Performance** to chart a metric across annual filings, **AI brief** for a cited interpretation, or **Filings** to read the source documents. For a specific financial fact, recent filing or earnings announcement, change **Research view** next to the company search. Those detailed results include a JSON evidence download. The browser remembers the last five successful searches.

On macOS, double-click **Open-Dashboard.command** in Finder to start the installed local app or open the hosted dashboard.

### Company dashboard and analyst

A ticker search resolves the filer against the SEC ticker directory. The company dashboard examines up to six original 10-K, 20-F or 40-F filings and looks for consolidated US GAAP or IFRS facts. Annual revenue, profit, assets, diluted EPS and operating cash flow can be explored as dated series. Net margin requires matching revenue and net income periods and units. Revenue growth compares adjacent annual reports as originally filed. Issuers without comparable tagged metrics show gaps and filing links. Foreign listings outside EDGAR and issuer-specific extensions can limit coverage.

The **historical comparison** fits a Theil–Sen regression to prior observations, holds out the latest year and compares the reported result to the historical baseline. It tries revenue, net income and then assets until it finds sufficient history in the same currency. This model runs without an external AI service.

The **AI analyst** is available when the host sets `OPENAI_API_KEY` on the server. Set it in Render under the service’s **Environment** settings and redeploy. Visitors can then request an AI brief. A model selects a research focus, Python gathers the corresponding series, and a second model call interprets the evidence. The app checks each cited period against the selected evidence before linking its filing. Valid citations do not guarantee that every interpretation is correct. Completed briefs are cached per lookup and fifteen-minute window. The single-worker deployment limits new brief attempts to six per rolling hour per worker lifetime. API usage is billed to the configured account.

### Host a public copy

[Deploy the dashboard on Render](https://render.com/deploy?repo=https://github.com/srakothu/sec-financial-research-agent). Sign in, review the free web service, and enter an app name plus your contact email for `SEC_USER_AGENT`. Apply the deployment. Open the service URL Render displays once it is live. The dashboard uses the existing Python research workflow and requires no OpenAI key.

## Local installation

Install Git and Python 3.12, then run:

```sh
git clone https://github.com/srakothu/sec-financial-research-agent.git
cd sec-financial-research-agent
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Configure the contact below and run `python -m sec_agent.dashboard` to open the local dashboard.

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

The scope excludes inferred Q4 results, separate amendments, segment metrics, and cross-company comparisons. A missing standalone quarter, unsupported tag, or ambiguous comparative produces an explanation.

The [selection logic](sec_agent/facts.py), [SEC client](sec_agent/edgar.py), [workflow](sec_agent/workflow.py), and [regression tests](tests/test_research.py) are the main entry points for reviewing the implementation.
