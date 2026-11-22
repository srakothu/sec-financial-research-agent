from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Form = Literal["10-K", "10-Q", "8-K"]
MetricName = Literal[
    "revenue", "net_income", "operating_income", "total_assets",
    "diluted_eps", "operating_cash_flow",
]


class ResearchError(Exception):
    """A user-facing request, data, or provider error."""


class Query(BaseModel):
    intent: Literal["fact", "filings", "event", "unsupported"]
    company: str | None = None
    metric: MetricName | None = None
    period: Literal["annual", "quarterly"] | None = None
    fiscal_year: int | None = None
    quarter: Literal[1, 2, 3] | None = None
    form: Form | None = None
    event_date: str | None = None
    earnings_only: bool = Field(default_factory=bool)
    year_over_year: bool = Field(default_factory=bool)

    def check(self) -> None:
        if self.intent == "unsupported":
            raise ResearchError(
                "Try one company and one reported metric, a recent filing list, "
                "or a question about the latest or a dated 8-K. "
                "Quarterly facts cover fiscal Q1–Q3."
            )
        if not self.company or not self.company.strip():
            raise ResearchError("Specify one company by ticker, exact SEC name, or CIK.")
        if self.year_over_year and (self.intent != "fact" or self.metric != "revenue"):
            raise ResearchError("Year-over-year growth is supported for revenue only.")
        if self.intent != "event" and (self.event_date or self.earnings_only):
            raise ResearchError("A filing date and earnings filter apply only to 8-K questions.")
        if self.intent != "fact" and any(
            field is not None for field in (self.metric, self.period, self.fiscal_year, self.quarter)
        ):
            raise ResearchError("Ask for a reported fact separately from a filing or 8-K search.")
        if self.intent == "fact":
            if self.metric is None or self.period is None:
                raise ResearchError("Specify a supported metric and an annual or quarterly period.")
            if self.fiscal_year is not None and not 2009 <= self.fiscal_year <= date.today().year + 1:
                raise ResearchError("Specify a fiscal year from 2009 through next year.")
            if self.period == "annual" and self.quarter is not None:
                raise ResearchError("An annual question cannot specify a fiscal quarter.")
            if self.period == "quarterly" and (self.fiscal_year is None) != (self.quarter is None):
                raise ResearchError("Specify both a fiscal year and Q1–Q3, or ask for the latest 10-Q.")
            expected_form = "10-K" if self.period == "annual" else "10-Q"
            if self.form and self.form != expected_form:
                raise ResearchError(f"The requested reporting period uses {expected_form} filings.")
        if self.intent == "event" and self.form not in (None, "8-K"):
            raise ResearchError("Event excerpts use Form 8-K.")
        if self.event_date is not None:
            try:
                if date.fromisoformat(self.event_date).isoformat() != self.event_date:
                    raise ValueError
            except ValueError as exc:
                raise ResearchError("Use YYYY-MM-DD for the 8-K filing date.") from exc


@dataclass(frozen=True)
class Company:
    cik: int
    name: str
    ticker: str | None


@dataclass(frozen=True)
class Filing:
    cik: int
    form: str
    accession: str
    filed: str
    report_date: str
    document: str
    items: str

    @property
    def directory(self) -> str:
        compact_accession = self.accession.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{self.cik}/{compact_accession}/"

    @property
    def index_url(self) -> str:
        return f"{self.directory}{self.accession}-index.htm"

    @property
    def url(self) -> str:
        return self.directory + self.document if self.document else self.index_url


@dataclass(frozen=True)
class Fact:
    filing: Filing
    label: str
    tag: str
    unit: str
    value: int | float
    start: str | None
    end: str
    fiscal_year: int | None
    fiscal_period: str


@dataclass(frozen=True)
class Excerpt:
    label: str
    url: str
    text: str
    section: str = ""
