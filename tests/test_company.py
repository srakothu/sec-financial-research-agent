from unittest.mock import Mock

import pytest

from sec_agent import analyst
from sec_agent.company import overview, trend
from sec_agent.models import Company, Filing, ResearchError


def issuer():
    client = Mock()
    client.lookup.return_value = Company(1, "Fixture PLC", "FXTR")
    filings = []
    rows = []
    for year, amount in enumerate((100, 110, 120, 150), 2020):
        end = f"{year}-12-31"
        start = f"{year}-01-01"
        filing = Filing(1,"20-F",f"0000000001-00-{year:06}",f"{year+1}-03-01",end,"report.htm","")
        filings.append(filing)
        rows.append(dict(form="20-F",accn=filing.accession,start=start,end=end,val=amount))
    client.filings.return_value = filings[::-1]
    client.facts.return_value = {"facts":{"ifrs-full":{
        "Revenue":{"units":{"EUR":rows}},
        "ProfitLoss":{"units":{"EUR":[r | {"val": r["val"]/5} for r in rows]}}}}}
    return client


def test_arbitrary_foreign_issuer_and_model_holdout():
    report = overview(issuer(), "FXTR")
    assert report["revenue_growth"] == 25
    assert report["periods"][-1]["values"]["net_margin"]["value"] == 20
    assert report["trend"]["baseline"] == pytest.approx(130,abs=.1)
    assert report["trend"]["training_years"] == 3
    assert report["trend"]["unit"] == "EUR"
    assert report["periods"][-1]["url"].endswith("/report.htm")


def test_insufficient_comparable_history():
    series = overview(issuer(), "FXTR")["periods"]
    series[0]["values"]["revenue"]["unit"] = "USD"
    assert trend(series, "revenue") is None


def test_ai_selects_evidence_and_validates_sources(monkeypatch):
    from unittest.mock import MagicMock
    report = overview(issuer(), "FXTR")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(analyst, "OpenAI",MagicMock())
    monkeypatch.setattr(analyst,"requests",[])
    model = Mock()
    monkeypatch.setattr(analyst,"OpenAIResearch",lambda *_:model)
    def run(end):
        model.structured.side_effect = [analyst.Plan(focus="profitability"), analyst.Brief(
            findings=[analyst.Finding(headline="Margins held steady", interpretation="Margins held steady.",source_dates=[end])],
            limitation="Four observations.") ]
        return analyst.analyze(report)
    assert run("2023-12-31")["focus"] == "profitability"
    assert "net_margin" in model.structured.call_args.args[1]
    with pytest.raises(ResearchError,match="filing references"):
        run("1990-01-01")


def test_filer_without_annual_reports():
    client = issuer()
    client.filings.return_value = []
    assert overview(client, "FXTR")["periods"] == []
    client.facts.assert_not_called()
