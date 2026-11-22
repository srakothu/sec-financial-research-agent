from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .edgar import Edgar
from .facts import RevenueGrowth, revenue_growth, select_fact
from .llm import OpenAIResearch
from .models import Company, Excerpt, Fact, Filing, Query, ResearchError


class State(TypedDict, total=False):
    question: str
    query: Query
    company: Company
    filings: list[Filing]
    fact: Fact
    growth: RevenueGrowth
    excerpts: list[Excerpt]
    answer: str


def build_graph(edgar: Edgar, model: OpenAIResearch | None = None):
    def parse_question(state: State) -> dict:
        query = state.get("query")
        if query is None:
            if model is None:
                raise ResearchError("The ask command needs an OpenAI API key.")
            query = model.parse(state["question"])
        query.check()
        return {"query": query}

    def lookup_company(state: State) -> dict:
        return {"company": edgar.lookup(state["query"].company)}

    def discover_filings(state: State) -> dict:
        query, cik = state["query"], state["company"].cik
        if query.intent == "fact":
            form = "10-K" if query.period == "annual" else "10-Q"
            year = query.fiscal_year
            if year is None:
                filings = edgar.filings(cik, {form}, limit=1)
            else:
                # A fiscal Q1 can end in the previous calendar year. The filing
                # itself can land in the calendar year after the report ends.
                filings = edgar.filings(
                    cik, {form}, f"{year - 1}-01-01", f"{year + 1}-12-31",
                )
        elif query.intent == "event":
            if query.event_date:
                filings = edgar.filings(
                    cik, {"8-K"}, query.event_date, query.event_date, earnings_only=query.earnings_only,
                )
            else:
                filings = edgar.filings(cik, {"8-K"}, limit=1, earnings_only=query.earnings_only)
            if query.event_date and len(filings) > 1:
                urls = "\n".join(filing.url for filing in filings)
                raise ResearchError(
                    f"Multiple 8-Ks were filed on {query.event_date}. "
                    f"Review these filings or try the earnings filter.\n{urls}"
                )
            filings = filings[:1]
        else:
            forms = {query.form} if query.form else {"10-K", "10-Q", "8-K"}
            filings = edgar.filings(cik, forms, limit=3)
        if not filings:
            raise ResearchError("No SEC filings matched the requested company, form, and dates.")
        return {"filings": filings}

    def retrieve_fact(state: State) -> dict:
        data = edgar.facts(state["company"].cik)
        fact = select_fact(data, state["filings"], state["query"])
        if state["query"].year_over_year:
            return {"fact": fact, "growth": revenue_growth(data, fact)}
        return {"fact": fact}

    def retrieve_8k(state: State) -> dict:
        filing = state["filings"][0]
        excerpts = edgar.excerpts(filing)
        if model is not None and state.get("question") and excerpts:
            excerpts = model.choose_excerpts(state["question"], excerpts)
        else:
            # Prefer paragraphs over headlines in the explicit preview.
            main = [row for row in excerpts if row.label == "8-K"]
            exhibit = [row for row in excerpts if row.label == "Exhibit 99.1"]
            excerpts = main[:2] + sorted(exhibit, key=lambda row: len(row.text) < 75)[:2]
        if not excerpts:
            raise ResearchError(f"No relevant excerpts were found in this 8-K. Review {filing.url}")
        return {"excerpts": excerpts}

    def format_answer(state: State) -> dict:
        company = state["company"]
        issuer = f"{company.name} ({company.ticker})" if company.ticker else company.name
        if fact := state.get("fact"):
            period = f"{fact.start} to {fact.end}" if fact.start else f"as of {fact.end}"
            fiscal = " ".join(filter(None, (
                f"FY{fact.fiscal_year}" if fact.fiscal_year else "",
                fact.fiscal_period if fact.fiscal_period != "FY" else "",
            )))
            unit = "USD/share" if fact.unit == "USD/shares" else fact.unit
            lines = [
                f"{issuer} — {fact.label}: {fact.value:,} {unit}",
                f"Reporting period: {period}" + (f" ({fiscal})" if fiscal else ""),
            ]
            if growth := state.get("growth"):
                lines.extend([
                    f"Prior-year period: {growth.prior_start} to {growth.prior_end}"
                    f" · {growth.prior_value:,} {unit}",
                    f"Year-over-year change: {growth.change:+,} {unit} ({growth.percent:+.2f}%)",
                ])
            lines.extend([
                filing_reference(fact.filing),
                f"XBRL concept: {fact.tag}",
            ])
            return {"answer": "\n".join(lines)}
        if excerpts := state.get("excerpts"):
            lines = [f"{issuer} — 8-K excerpts", filing_reference(state["filings"][0])]
            for excerpt in excerpts:
                heading = f" · {excerpt.section}" if excerpt.section else ""
                lines.append(f'\n{excerpt.label}{heading}\n“{excerpt.text}”\n{excerpt.url}')
            return {"answer": "\n".join(lines)}
        references = "\n\n".join(filing_reference(filing) for filing in state["filings"])
        return {"answer": f"{issuer} — recent SEC filings\n\n{references}"}

    def route(state: State) -> Literal["retrieve_fact", "retrieve_8k", "format_answer"]:
        return {
            "fact": "retrieve_fact",
            "event": "retrieve_8k",
            "filings": "format_answer",
        }[state["query"].intent]

    graph = StateGraph(State)
    for node in (parse_question, lookup_company, discover_filings,
                 retrieve_fact, retrieve_8k, format_answer):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "parse_question")
    graph.add_edge("parse_question", "lookup_company")
    graph.add_edge("lookup_company", "discover_filings")
    graph.add_conditional_edges("discover_filings", route)
    graph.add_edge("retrieve_fact", "format_answer")
    graph.add_edge("retrieve_8k", "format_answer")
    graph.add_edge("format_answer", END)
    return graph.compile()


def filing_reference(filing: Filing) -> str:
    label = "SEC report/event date" if filing.form == "8-K" else "Report end"
    report_date = filing.report_date or "unavailable"
    return (
        f"Source: {filing.form} · filed {filing.filed} · {label}: {report_date}"
        f" · accession {filing.accession}\n{filing.url}"
    )
