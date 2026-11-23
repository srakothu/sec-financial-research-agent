"""Browser interface for the SEC research workflow."""
import json
import os
import re
import webbrowser
from time import monotonic
from .analyst import analyze
from .company import overview
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from .edgar import Edgar
from .models import Query, ResearchError
from .workflow import build_graph

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
ASSETS = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"),
          "/company.js": ("company.js", "text/javascript"), "/app.js": ("app.js", "text/javascript")}


def present(state):
    filing = state.get("fact").filing if state.get("fact") else state["filings"][0]
    rows = [filing] if state.get("fact") else state["filings"]
    return {
        "company": state["company"].name, "ticker": state["company"].ticker,
        "fact": asdict(state["fact"]) if state.get("fact") else None,
        "growth": asdict(state["growth"]) if state.get("growth") else None,
        "filings": [asdict(f) | {"url": f.url} for f in rows],
        "excerpts": [asdict(e) for e in state.get("excerpts", [])],
    }


@lru_cache(maxsize=1)
def live_client():
    agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not agent.isascii() or not agent.isprintable() or "example.com" in agent.lower() or not re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", agent):
        raise ResearchError("Live lookups need the site owner's contact email in SEC_USER_AGENT.")
    # One synchronous worker keeps outbound calls sequential across visitors.
    return Edgar(httpx.Client(headers={"User-Agent": agent}, timeout=15))


@lru_cache(maxsize=24)
def report_for(symbol, time_bucket):
    client = live_client()
    client.cache.clear()
    try:
        return overview(client, symbol)
    finally:
        client.cache.clear()


@lru_cache(maxsize=24)
def brief_for(symbol, time_bucket):
    return analyze(report_for(symbol, time_bucket))


def application(env, start):
    path = env["PATH_INFO"]
    status = "200 OK"
    mime = "application/json"
    if path in ASSETS:
        name, mime = ASSETS[path]
        body = (ROOT / "dashboard" / name).read_bytes()
    elif (path == "/api/company" and env["REQUEST_METHOD"] == "GET") or (
        path == "/api/brief" and env["REQUEST_METHOD"] == "POST"
    ):
        try:
            params = parse_qs(env["QUERY_STRING"], max_num_fields=1)
            symbol = params.get("company", [""])[0].strip().upper()
            if not 1 <= len(symbol) <= 128:
                raise ResearchError("Enter a ticker, CIK or exact SEC company name.")
            bucket = int(monotonic() // 900)
            if path == "/api/brief":
                if env.get("CONTENT_TYPE") != "application/json":
                    raise ResearchError("Use the dashboard to request an AI brief.")
                value = brief_for(symbol, bucket)
            else:
                value = report_for(symbol, bucket) | {"ai_enabled": bool(os.getenv("OPENAI_API_KEY"))}
            body = json.dumps(value).encode()
        except (ResearchError, ValueError) as exc:
            status, body = "400 Bad Request", json.dumps({"error": str(exc)}).encode()
    elif path == "/api/research" and env["REQUEST_METHOD"] == "GET":
        try:
            params = {k: v[-1] for k, v in parse_qs(env["QUERY_STRING"], max_num_fields=12).items()}
            if "quarter" in params:
                params["quarter"] = int(params["quarter"])
            query = Query.model_validate(params)
            query.check()
            client = live_client()
            client.cache.clear()
            graph = build_graph(client)
            # EDGAR responses are cached only within this lookup.
            graph_result = graph.invoke({"query": query})
            body = json.dumps(present(graph_result), default=str).encode()
        except (ResearchError, ValueError, ValidationError) as exc:
            status = "400 Bad Request"
            message = str(exc) if isinstance(exc, ResearchError) else "Check the company, fiscal year and selected period."
            body = json.dumps({"error": message}).encode()
    else:
        status, body = "404 Not Found", b'{"error":"Page not found"}'
    start(status, [("Content-Type", mime + "; charset=utf-8"), ("Content-Length", str(len(body)))])
    return [body]


if __name__ == "__main__":
    with make_server("127.0.0.1", 0, application) as server:
        webbrowser.open(f"http://127.0.0.1:{server.server_port}/")
        server.serve_forever()
