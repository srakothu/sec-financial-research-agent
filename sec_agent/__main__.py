import argparse
import os
import re
import sys
from contextlib import ExitStack

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from .demo import demo_client, demo_queries
from .edgar import Edgar
from .facts import METRICS
from .llm import OpenAIResearch
from .models import Query, ResearchError
from .workflow import build_graph


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Research SEC filings and cited financial facts.")
    cli.add_argument("--trace", action="store_true", help="Show LangGraph node names and parsed query")
    cli.add_argument("--sample", action="store_true", help="Use the bundled Apple data with fact, filings, or event")
    commands = cli.add_subparsers(dest="command", required=True)
    ask = commands.add_parser("ask", help="Ask a natural-language question using OpenAI")
    ask.add_argument("question")
    fact = commands.add_parser("fact", help="Look up a reported financial fact without OpenAI")
    fact.add_argument("company", help="Ticker, CIK, or exact SEC name")
    fact.add_argument("metric", choices=METRICS)
    fact.add_argument("--period", choices=("annual", "quarterly"), default="annual")
    fact.add_argument("--year", type=int, help="Fiscal year")
    fact.add_argument("--quarter", type=int, choices=(1, 2, 3))
    fact.add_argument("--yoy", action="store_true", help="Calculate year-over-year revenue growth")
    filings = commands.add_parser("filings", help="List up to three recent filings")
    filings.add_argument("company")
    filings.add_argument("--form", choices=("10-K", "10-Q", "8-K"))
    event = commands.add_parser("event", help="Show excerpts from a recent or dated 8-K")
    event.add_argument("company")
    event.add_argument("--date", help="Exact filing date, YYYY-MM-DD")
    event.add_argument("--earnings", action="store_true", help="Filter to Item 2.02")
    commands.add_parser("demo", help="Run Apple examples with local SEC data and no credentials")
    commands.add_parser("graph", help="Print the compiled workflow as Mermaid")
    return cli


def run(graph, state: dict, trace: bool) -> None:
    if not trace:
        print(graph.invoke(state)["answer"])
        return
    for update in graph.stream(state, stream_mode="updates"):
        for node, values in update.items():
            print(f"[{node}]", file=sys.stderr)
            if node == "parse_question":
                print(values["query"].model_dump_json(exclude_none=True), file=sys.stderr)
            if "answer" in values:
                print(values["answer"])


def main() -> int:
    args = parser().parse_args()
    load_dotenv()
    try:
        with ExitStack() as stack:
            if args.command in ("demo", "graph"):
                client = stack.enter_context(demo_client())
                graph = build_graph(Edgar(client, interval=0))
                if args.command == "graph":
                    print(graph.get_graph().draw_mermaid())
                else:
                    print("OFFLINE DEMO · Apple filing sample · no live network or OpenAI calls")
                    for question, query in demo_queries():
                        print(f"\n{question}", flush=True)
                        run(graph, {"query": query}, args.trace)
                return 0

            if args.sample:
                if args.command == "ask":
                    raise ResearchError("Use fact, filings, or event to query the offline Apple sample.")
                edgar = Edgar(stack.enter_context(demo_client()), interval=0)
                print("OFFLINE SAMPLE · selected Apple filings", file=sys.stderr)
            else:
                user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
                if (
                    not user_agent.isascii()
                    or not all(char.isprintable() for char in user_agent)
                    or not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", user_agent)
                    or "example.com" in user_agent.lower()
                ):
                    raise ResearchError("Set SEC_USER_AGENT in .env to the app name and your contact email.")
                http = stack.enter_context(httpx.Client(headers={"User-Agent": user_agent}, timeout=20))
                edgar = Edgar(http)
            if args.command == "ask":
                if not os.environ.get("OPENAI_API_KEY", "").strip():
                    raise ResearchError("Set OPENAI_API_KEY in .env, or use demo, fact, filings, or event.")
                if not 1 <= len(args.question.strip()) <= 2000:
                    raise ResearchError("Enter a question of 1 to 2,000 characters.")
                openai = stack.enter_context(OpenAI(timeout=35, max_retries=1))
                model = OpenAIResearch(openai, os.environ.get("OPENAI_MODEL") or "gpt-5-mini")
                run(build_graph(edgar, model), {"question": args.question}, args.trace)
                return 0

            query = Query(
                intent=args.command, company=args.company, metric=getattr(args, "metric", None),
                period=getattr(args, "period", None), fiscal_year=getattr(args, "year", None),
                quarter=getattr(args, "quarter", None), form=getattr(args, "form", None),
                event_date=getattr(args, "date", None), earnings_only=getattr(args, "earnings", False),
                year_over_year=getattr(args, "yoy", False),
            )
            run(build_graph(edgar), {"query": query}, args.trace)
    except ResearchError as exc:
        print(f"Research error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
