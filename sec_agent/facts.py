from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isfinite

from .models import Fact, Filing, MetricName, Query, ResearchError


@dataclass(frozen=True)
class Metric:
    label: str
    tags: tuple[str, ...]
    unit: str = "USD"
    instant: bool = False


METRICS: dict[MetricName, Metric] = {
    "revenue": Metric("Revenue", (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    )),
    "net_income": Metric("Net income", ("NetIncomeLoss",)),
    "operating_income": Metric("Operating income", ("OperatingIncomeLoss",)),
    "total_assets": Metric("Total assets", ("Assets",), instant=True),
    "diluted_eps": Metric("Diluted EPS", ("EarningsPerShareDiluted",), unit="USD/shares"),
    "operating_cash_flow": Metric(
        "Operating cash flow", ("NetCashProvidedByUsedInOperatingActivities",),
    ),
}


def matches_period(row: dict, filing: Filing, query: Query, instant: bool) -> bool:
    if (
        not filing.report_date
        or row.get("accn") != filing.accession
        or row.get("form") != filing.form
        or row.get("end") != filing.report_date
    ):
        return False
    if query.fiscal_year is not None:
        expected_period = f"Q{query.quarter}" if query.quarter else "FY"
        if row.get("fy") != query.fiscal_year or row.get("fp") != expected_period:
            return False
    if instant:
        return not row.get("start")
    try:
        days = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days + 1
    except (KeyError, ValueError, TypeError):
        return False
    return 350 <= days <= 380 if query.period == "annual" else 75 <= days <= 105


def select_fact(data: dict, filings: list[Filing], query: Query) -> Fact:
    metric = METRICS[query.metric]
    concepts = data.get("facts", {}).get("us-gaap", {})
    for filing in filings:
        for tag in metric.tags:
            rows = concepts.get(tag, {}).get("units", {}).get(metric.unit, [])
            matches = {
                (row.get("start"), row.get("val"), row.get("fy"), row.get("fp"))
                for row in rows
                if matches_period(row, filing, query, metric.instant)
                and type(row.get("val")) in (int, float)
                and isfinite(row["val"])
            }
            if len(matches) > 1:
                raise ResearchError(
                    f"{filing.form} {filing.accession} contains conflicting candidates "
                    f"for {metric.label.lower()}. Inspect {filing.url}"
                )
            if matches:
                start, value, fiscal_year, fiscal_period = matches.pop()
                return Fact(
                    filing, metric.label, f"us-gaap:{tag}", metric.unit, value, start,
                    filing.report_date, fiscal_year, fiscal_period or "",
                )
    target = (
        f"fiscal {query.fiscal_year}" + (f" Q{query.quarter}" if query.quarter else "")
        if query.fiscal_year is not None
        else f"the latest {filings[0].form} (report end {filings[0].report_date or 'unknown'})"
    )
    raise ResearchError(
        f"No supported {metric.label.lower()} fact matched {target}. "
        "The filing may use a different tag, unit, or duration."
    )


@dataclass(frozen=True)
class RevenueGrowth:
    prior_start: str
    prior_end: str
    prior_value: Decimal
    change: Decimal
    percent: Decimal


def revenue_growth(data: dict, current: Fact) -> RevenueGrowth:
    """Compare the prior-year column as presented in the current filing."""
    taxonomy, tag = current.tag.split(":", 1)
    rows = data["facts"][taxonomy][tag]["units"][current.unit]
    current_start = date.fromisoformat(current.start)
    current_end = date.fromisoformat(current.end)
    candidates = set()
    for row in rows:
        if row.get("accn") != current.filing.accession or row.get("form") != current.filing.form:
            continue
        try:
            start = date.fromisoformat(row["start"])
            end = date.fromisoformat(row["end"])
        except (KeyError, TypeError, ValueError):
            continue
        # Allow calendar years and 52/53-week fiscal years at both boundaries.
        if not (357 <= (current_start - start).days <= 373 and
                357 <= (current_end - end).days <= 373):
            continue
        value = row.get("val")
        if type(value) in (float, int) and isfinite(value):
            candidates.add((row["start"], row["end"], Decimal(str(value))))
    if len(candidates) != 1:
        raise ResearchError(
            f"Expected one comparable prior-year revenue observation in {current.filing.url}, "
            f"found {len(candidates)}."
        )
    start, end, previous = candidates.pop()
    if previous <= 0:
        raise ResearchError("Revenue growth requires a positive prior-year revenue base.")
    change = Decimal(str(current.value)) - previous
    return RevenueGrowth(start, end, previous, change, change / previous * 100)
