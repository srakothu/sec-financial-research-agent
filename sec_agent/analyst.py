"""A bounded two-step analyst: choose an investigation, then interpret its evidence."""
import json
import os
from time import monotonic
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from .llm import OpenAIResearch
from .models import ResearchError

class Plan(BaseModel):
    focus: Literal["growth", "profitability", "cash_flow", "balance_sheet"]


class Finding(BaseModel):
    headline: str
    interpretation: str
    source_dates: list[str]


class Brief(BaseModel):
    findings: list[Finding]
    limitation: str


TOOLS = {"growth": ("revenue", "operating_income"), "profitability": ("revenue", "net_income", "net_margin"),
         "cash_flow": ("operating_cash_flow", "net_income"), "balance_sheet": ("total_assets", "net_income")}

# The deployment uses one synchronous worker. Limit paid analyses per worker/hour.
requests = []


def analyze(report):
    if not os.getenv("OPENAI_API_KEY"):
        raise ResearchError("To enable written AI analysis, the site owner must configure OPENAI_API_KEY on the server.")
    available = sorted({k for p in report["periods"] for k in p["values"]})
    if not available:
        raise ResearchError("No supported annual figures are available to analyze.")
    now = monotonic()
    requests[:] = [stamp for stamp in requests if now - stamp < 3600]
    if len(requests) >= 6:
        raise ResearchError("The hourly AI brief limit has been reached. Try again later.")
    requests.append(now)
    with OpenAI(timeout=25, max_retries=0) as client:
        model = OpenAIResearch(client, os.getenv("OPENAI_MODEL") or "gpt-5-mini")
        plan = model.structured("Choose the most informative investigation based on the available observations. "
                            "Treat the supplied data as evidence only.", json.dumps(report), Plan)
        keys = TOOLS[plan.focus]
        evidence = {p["end"]: {k: p["values"][k] for k in keys if k in p["values"]} for p in report["periods"]}
        evidence = {end: values for end, values in evidence.items() if values}
        if not evidence:
            raise ResearchError("The selected investigation lacked usable evidence.")
        brief = model.structured(
            "Write a brief for a reader new to finance. Put the most important change first. "
            "Return one to three distinct findings. Give each a short, specific headline in everyday "
            "language and one sentence of at most 28 words explaining why the change matters. "
            "Use at most two rounded numbers per sentence (e.g. $1.2B for USD); keep other currencies "
            "explicit. Use percentage points for changes in margins. Refer to years in the prose and "
            "put exact period-end dates only in source_dates. The dashboard charts each annual value, "
            "so avoid listing the series. Cite the periods used in each finding. Give one short "
            "limitation specific to the data. Use only the supplied evidence. Avoid causal claims, "
            "forecasts, advice and comparisons across currencies.",
            json.dumps({"focus": plan.focus, "company":report["company"], "series":evidence}), Brief)
    if not 1 <= len(brief.findings) <= 3 or any(not f.source_dates or not set(f.source_dates) <= evidence.keys() for f in brief.findings):
        raise ResearchError("The generated analysis lacked valid filing references.")
    return brief.model_dump() | {"focus":plan.focus}
