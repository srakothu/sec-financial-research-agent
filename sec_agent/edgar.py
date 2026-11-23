import re
from time import monotonic, sleep
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .models import Company, Excerpt, Filing, ResearchError

DATA = "https://data.sec.gov"
TICKERS = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = f"{DATA}/submissions/"


class Edgar:
    def __init__(self, http: httpx.Client, interval: float = 0.25):
        self.http = http
        self.interval = interval
        self.last_request = -interval
        self.cache: dict[str, httpx.Response] = {}

    def get(self, url: str) -> httpx.Response:
        if url in self.cache:
            return self.cache[url]
        try:
            sleep(max(0, self.interval - (monotonic() - self.last_request)))
            self.last_request = monotonic()
            response = self.http.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (403, 429):
                raise ResearchError(
                    f"SEC returned HTTP {code}. Check your SEC_USER_AGENT contact and "
                    "wait before retrying."
                ) from exc
            raise ResearchError(f"SEC returned HTTP {code} for {url}.") from exc
        except httpx.RequestError as exc:
            raise ResearchError("Could not reach SEC EDGAR. Check your connection and retry.") from exc
        self.cache[url] = response
        return response

    def json(self, url: str) -> dict:
        try:
            return self.get(url).json()
        except ValueError as exc:
            raise ResearchError("SEC EDGAR returned an unreadable JSON response.") from exc

    def submissions(self, cik: int) -> dict:
        return self.json(f"{SUBMISSIONS}CIK{cik:010}.json")

    def lookup(self, company: str) -> Company:
        key = company.strip().upper().removeprefix("$")
        if re.fullmatch(r"[0-9]{1,10}", key) and int(key) > 0:
            cik = int(key)
            data = self.submissions(cik)
            return Company(cik, data["name"], next(iter(data.get("tickers", [])), None))

        rows = list(self.json(TICKERS).values())
        # SEC uses hyphens for ticker share classes such as BRK-B.
        ticker_matches = [row for row in rows if row["ticker"] == key.replace(".", "-")]
        name = key.rstrip(".")
        matches = ticker_matches or [row for row in rows if row["title"].upper().rstrip(".") == name]
        if not matches or len({row["cik_str"] for row in matches}) != 1:
            raise ResearchError(f"Could not resolve {company!r} to one filer. Try its ticker or CIK.")
        row = matches[0]
        return Company(int(row["cik_str"]), row["title"], row["ticker"])

    def filings(
        self, cik: int, forms: set[str], filed_from: str = "", filed_to: str = "9999-12-31",
        *, limit: int | None = None, earnings_only: bool = False,
    ) -> list[Filing]:
        filing_data = self.submissions(cik)["filings"]
        results: dict[str, Filing] = {}
        def add_batch(batch: dict) -> None:
            for index, form in enumerate(batch["form"]):
                filed = batch["filingDate"][index]
                if form not in forms or not filed_from <= filed <= filed_to:
                    continue
                accession = batch["accessionNumber"][index]
                document = batch["primaryDocument"][index]
                if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
                    continue
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", document) or document in (".", ".."):
                    document = ""
                items = batch.get("items")
                filing = Filing(cik, form, accession, filed, batch["reportDate"][index],
                                document, items[index] if items else "")
                if not earnings_only or has_earnings_item(filing):
                    results.setdefault(accession, filing)

        add_batch(filing_data["recent"])
        parts = sorted(filing_data.get("files", []), key=lambda part: part["filingTo"], reverse=True)
        for part in parts:
            if part["filingTo"] < filed_from:
                break
            if limit and len(results) >= limit:
                cutoff = sorted((row.filed for row in results.values()), reverse=True)[limit - 1]
                if part["filingTo"] < cutoff:
                    break
            if part["filingFrom"] <= filed_to and re.fullmatch(
                r"CIK[0-9]{10}-submissions-[0-9]+\.json", part["name"]
            ):
                add_batch(self.json(SUBMISSIONS + part["name"]))
        ordered = sorted(results.values(), key=lambda row: (row.filed, row.accession), reverse=True)
        return ordered[:limit]

    def facts(self, cik: int) -> dict:
        return self.json(f"{DATA}/api/xbrl/companyfacts/CIK{cik:010}.json")

    def exhibit_99_1(self, filing: Filing) -> str | None:
        index = BeautifulSoup(self.get(filing.index_url).text, "html.parser")
        for row in index.select("table tr"):
            cells = row.find_all("td")
            if len(cells) < 4 or cells[3].get_text(strip=True) != "EX-99.1":
                continue
            link = cells[2].find("a", href=True)
            if link:
                href = link["href"]
                if urlsplit(href).path in ("/ix", "/ix.xhtml"):
                    href = parse_qs(urlsplit(href).query).get("doc", [""])[0]
                url = urljoin(filing.directory, href)
                if url.startswith(filing.directory) and re.fullmatch(
                    r"[A-Za-z0-9_.-]+\.html?", url.removeprefix(filing.directory), re.I
                ):
                    return url
        return None

    def excerpts(self, filing: Filing) -> list[Excerpt]:
        result = (
            extract_excerpts(self.get(filing.url).text, filing.url, "8-K")
            if filing.document else []
        )
        if has_earnings_item(filing) or any(
            excerpt.section.lower().startswith("item 2.02") for excerpt in result
        ):
            url = self.exhibit_99_1(filing)
            if url:
                result += extract_excerpts(self.get(url).text, url, "Exhibit 99.1")
        return result


BLOCKS = ("p", "div", "li", "h1", "h2", "h3", "h4")


def extract_excerpts(html: str, url: str, label: str) -> list[Excerpt]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, [hidden], ix\\:hidden"):
        tag.decompose()
    results: list[Excerpt] = []
    heading = ""
    for block in soup.find_all((*BLOCKS, "tr")):
        # Issuers sometimes split an item number and title across table cells.
        # Read the row as a heading but exclude ordinary financial table rows.
        table_row = block.name == "tr"
        if table_row and block.find("tr"):
            continue
        if not table_row and (block.find(BLOCKS) or block.find("table") or block.find_parent("table")):
            continue
        # Normalize HTML whitespace and strip terminal control characters.
        text = " ".join(block.get_text(" ", strip=True).split())
        text = "".join(char for char in text if char.isprintable())
        if label == "8-K":
            if re.match(r"^item\s+[0-9]+\.[0-9]{2}\b", text, re.I):
                heading = text[:160]
                if len(text) < 100:
                    continue
            elif not heading:
                continue
            elif re.match(r"^signatures?\b", text, re.I):
                break
        if table_row:
            continue
        if len(text) >= 35:
            if len(text) > 850:
                text = text[:850].rsplit(" ", 1)[0] + "…"
            excerpt = Excerpt(label, url, text, heading)
            if excerpt not in results:
                results.append(excerpt)
            if len(results) == 16:
                break
    return results


def has_earnings_item(filing: Filing) -> bool:
    return "2.02" in {item.strip() for item in filing.items.split(",")}
