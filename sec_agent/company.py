"""Annual evidence ledger, comparative analysis, and a robust trend baseline."""
from datetime import date
from itertools import combinations
from math import isfinite
from statistics import median
import re

from .facts import METRICS, matches_period
from .models import Query, ResearchError

IFRS = {
    "revenue": ("Revenue",),
    "net_income": ("ProfitLoss",),
    "total_assets": ("Assets",),
    "operating_income": ("ProfitLossFromOperatingActivities",),
    "operating_cash_flow": ("CashFlowsFromUsedInOperatingActivities",),
    "diluted_eps": ("DilutedEarningsLossPerShare",),
}


def annual_value(concepts, filing, key):
    metric = METRICS[key]
    query = Query(intent="fact", company=str(filing.cik), metric=key, period="annual")
    for taxonomy, tags in (("us-gaap", metric.tags), ("ifrs-full", IFRS[key])):
        for tag in tags:
            units = concepts.get(taxonomy, {}).get(tag, {}).get("units", {})
            found = []
            for unit, rows in units.items():
                pattern = r"[A-Z]{3}/shares" if key == "diluted_eps" else r"[A-Z]{3}"
                if not re.fullmatch(pattern, unit):
                    continue
                values = {(row.get("start"), row["val"]) for row in rows
                          if matches_period(row, filing, query, metric.instant)
                          and type(row.get("val")) in (int, float) and isfinite(row["val"])}
                if len(values) > 1:
                    return None
                if values:
                    start, value = values.pop()
                    found.append(dict(value=value, unit=unit, concept=f"{taxonomy}:{tag}", start=start))
            if found:
                return next((v for v in found if v["unit"].split("/")[0] == "USD"),
                            found[0] if len(found) == 1 else None)
    return None


def trend(periods, key):
    """Hold the latest observation out; fit Theil–Sen to earlier observations."""
    current = periods[-1]["values"].get(key)
    if not current:
        return None
    points = []
    for period in periods:
        value = period["values"].get(key)
        if value and value["unit"] == current["unit"]:
            points.append((date.fromisoformat(period["end"]).toordinal(), value["value"]))
    if len(points) < 4:
        return None
    history, (latest, actual) = points[:-1], points[-1]
    slope = median((b - a) / (y - x) for (x, a), (y, b) in combinations(history, 2))
    predicted = median(v + slope * (latest - day) for day, v in history)
    return dict(metric=key, baseline=predicted, actual=actual, unit=current["unit"],
                training_years=len(history), gap=actual - predicted)


def overview(client, symbol):
    company = client.lookup(symbol)
    filings = client.filings(company.cik, {"10-K", "20-F", "40-F"}, limit=6)
    by_end = {}
    for filing in filings:
        if filing.report_date:
            by_end.setdefault(filing.report_date, filing)
    periods = []
    concepts = {}
    if by_end:
        try:
            concepts = client.facts(company.cik).get("facts", {})
        except ResearchError as exc:
            if "HTTP 404" not in str(exc):
                raise
    for end, filing in sorted(by_end.items()):
        values = {key: val for key in METRICS if (val := annual_value(concepts, filing, key))}
        revenue, income = values.get("revenue"), values.get("net_income")
        if revenue and income and revenue["value"] > 0 and revenue["unit"] == income["unit"] and revenue["start"] == income["start"]:
            values["net_margin"] = dict(value=100 * income["value"] / revenue["value"], unit="%")
        periods.append(dict(end=end, form=filing.form, url=filing.url, values=values))
    model = None
    growth = None
    if periods:
        model = next((fit for key in ("revenue", "net_income", "total_assets")
                      if (fit := trend(periods, key))), None)
    if len(periods) >= 2:
        prior, current = periods[-2:]
        a, b = [p["values"].get("revenue") for p in (prior, current)]
        days = (date.fromisoformat(current["end"]) - date.fromisoformat(prior["end"])).days
        if a and b and a["value"] > 0 and a["unit"] == b["unit"] and 350 <= days <= 380:
            growth = 100 * (b["value"] - a["value"]) / a["value"]
    return dict(company=company.name, ticker=company.ticker, cik=company.cik, periods=periods,
                trend=model, revenue_growth=growth)
