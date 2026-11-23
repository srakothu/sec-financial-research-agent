"use strict";
const byId = id => document.getElementById(id);
const result = byId("results");

let version = 0;

function el(tag, text, css) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (css) node.className = css;
  return node;
}
function link(title, url) {
  const a = el("a", title);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
function row(label, value) {
  const div = el("div", undefined, "row");
  div.append(el("span", label), el("strong", value));
  return div;
}
function money(value, compact = false) {
  return new Intl.NumberFormat("en-US", {style:"currency", currency:"USD",
    notation: compact ? "compact" : "standard", maximumFractionDigits:compact ? 2 : 4,
    minimumFractionDigits:0}).format(value);
}
function show(data) {
  result.replaceChildren();
  const hero = el("article", undefined, "hero");
  const fact = data.fact, growth = data.growth;
  hero.append(el("small", "SEC filing · " + (data.ticker || data.filings[0].cik)),
    el("h2", data.company));
  hero.append(el("p", fact ? money(fact.value, true) : data.excerpts.length ? "Earnings announcement" : "Recent filings", "number"));
  if (fact) hero.append(el("p", fact.label + (fact.unit === "USD/shares" ? " per share" : "") + " · period ended " + fact.end));
  if (growth) hero.append(el("p", Number(growth.percent).toFixed(2) + "% year over year", "change"));
  result.append(hero);
  if (growth && fact.value >= 0) result.append(comparisonChart(fact, growth));
  if (fact) {
    const details = el("article");
    details.append(el("h3", "Reported figures"), row(fact.start ? fact.start + " – " + fact.end : "As of " + fact.end, money(fact.value)));
    if (growth) details.append(row(growth.prior_start + " – " + growth.prior_end, money(growth.prior_value)), row("Change", money(growth.change)));
    details.append(el("small", "XBRL concept · " + fact.tag));
    result.append(details);
  }
  for (const excerpt of data.excerpts) {
    const card = el("article");
    card.append(el("h3", excerpt.label), el("blockquote", excerpt.text), link("Read original document", excerpt.url));
    result.append(card);
  }
  const sources = el("article");
  sources.append(el("h3", "Source filings"));
  for (const filing of data.filings) {
    const item = el("div", undefined, "row");
    item.append(link("Form " + filing.form, filing.url), el("span", "Filed " + filing.filed), el("small", filing.accession));
    sources.append(item);
  }
  result.append(sources);
  const download = el("button", "Download evidence (.json)", "export");
  download.type = "button";
  download.onclick = () => {
    const file = new Blob([JSON.stringify({source: "live", ...data}, null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(file);
    const anchor = el("a");
    anchor.href = url;
    anchor.download = (data.ticker || "SEC") + "-research.json";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };
  result.append(download);
}
function message(title, text) {
  const panel = el("article", undefined, "notice");
  panel.append(el("h2", title), el("p", text));
  result.replaceChildren(panel);
  byId("notice").textContent = title + ". " + text;
}
byId("intent").onchange = () => {
  byId("financial").hidden = byId("intent").value !== "fact";
  byId("formFilter").hidden = byId("intent").value !== "filings";
  updatePeriod();
  byId("eventDate").hidden = byId("intent").value !== "event";
};
byId("metric").onchange = () => { byId("compare").hidden = byId("metric").value !== "revenue"; };
byId("query").onsubmit = async event => {
  event.preventDefault();
  if (location.protocol === "file:") {
    location.assign("https://sec-financial-research-agent.onrender.com/");
    return;
  }
  const company = byId("company");
  company.value = company.value.trim();
  if (!company.reportValidity()) return;
  document.body.classList.add("researching");
  byId("explore").hidden = true;
  const ticket = ++version;
  const entry = Object.fromEntries(fieldIds.map(id => [id, byId(id).value]));
  entry.growth = byId("growth").checked;
  const intent = byId("intent").value;
  const params = new URLSearchParams({company:byId("company").value.trim(),intent});
  if (intent === "fact") {
    const period = byId("period").value;
    params.set("metric",byId("metric").value);
    if (!period.startsWith("latest")) params.set("fiscal_year",byId("year").value);
    params.set("period",["annual","latestAnnual"].includes(period) ? "annual" : "quarterly");
    if (["1","2","3"].includes(period)) params.set("quarter",period);
    if (byId("metric").value === "revenue" && byId("growth").checked) params.set("year_over_year","true");
  } else if (intent === "filings" && byId("formType").value) {
    params.set("form",byId("formType").value);
  } else if (intent === "event") {
    params.set("earnings_only","true");
    if (byId("date").value) params.set("event_date",byId("date").value);
  }
  message("Retrieving filings for " + entry.company, "Checking the SEC filing history…");
  result.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(intent === "company" ? "/api/company?company=" + encodeURIComponent(entry.company) : "/api/research?" + params);
    if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("The service is temporarily unavailable. Please try again.");
    const data = await response.json();
    if (ticket !== version) return;
    if (!response.ok) throw new Error(data.error || "The server could not complete this lookup.");
    if (intent === "company") showCompany(data, entry.company);
    else show(data);
    byId("notice").textContent = "Results ready for " + data.company;
    rememberLookup(entry);
  } catch (err) {
    if (ticket === version) {
      message("Lookup unavailable", err.message);
      const retry = el("button", "Retry lookup", "export");
      retry.onclick = () => byId("query").requestSubmit();
      result.firstChild.append(retry);
    }
  } finally {
    if (ticket === version) result.removeAttribute("aria-busy");
  }
};
function comparisonChart(fact, growth) {
  const chart = el("article", undefined, "chart");
  chart.append(el("h3", "Revenue comparison"));
  const max = Math.max(fact.value, Number(growth.prior_value));
  for (const [label, value] of [[growth.prior_end, Number(growth.prior_value)], [fact.end, fact.value]]) {
    chart.append(row("Period ending " + label, money(value, true)));
    const track = el("div", undefined, "track");
    const bar = el("div", undefined, "bar");
    bar.style.width = (100 * value / max) + "%";
    track.append(bar);
    chart.append(track);
  }
  return chart;
}

function updatePeriod() {
  const hide = byId("period").value.startsWith("latest");
  byId("yearLabel").hidden = hide;
  byId("year").disabled = hide || byId("financial").hidden;
}
byId("period").onchange = updatePeriod;
for (const [ticker, name, industry] of [
  ["MSFT", "Microsoft", "Software"], ["JPM", "JPMorgan Chase", "Banking"],
  ["NVDA", "NVIDIA", "Semiconductors"], ["COST", "Costco", "Retail"]
]) {
  const button = el("button", undefined, "issuer");
  button.type = "button";
  const top = el("span", undefined, "issuer-top");
  top.append(el("b", ticker), el("span", "↗"));
  button.append(top, el("strong", name), el("small", industry));
  button.onclick = () => {
    byId("company").value = ticker;
    byId("intent").value = "company";
    byId("intent").onchange();
    byId("query").requestSubmit();
  };
  byId("shortcuts").append(button);
}

const fieldIds = ["company","intent","metric","year","period","date","formType"];
const historyKey = "filing-desk.history.v1";
let historyItems = [];
try {
  const stored = JSON.parse(localStorage.getItem(historyKey) || "[]");
  historyItems = stored.filter(item => fieldIds.every(id => typeof item[id] === "string")).slice(0,5);
} catch { /* Storage may be disabled in private browsing. */ }
function drawHistory() {
  byId("history").replaceChildren();
  byId("recent").hidden = !historyItems.length;
  for (const item of historyItems) {
    const queryLabel = item.intent === "fact" ? item.metric.replaceAll("_"," ") : {company:"Overview", filings:"Filings", event:"Earnings"}[item.intent];
    const button = el("button", item.company + " · " + queryLabel);
    button.type = "button";
    button.onclick = () => {
      for (const id of fieldIds) byId(id).value = item[id];
      byId("growth").checked = item.growth;
      byId("intent").onchange();
      byId("metric").onchange();
      byId("query").requestSubmit();
    };
    byId("history").append(button);
  }
}
function rememberLookup(entry) {
  historyItems = [entry, ...historyItems.filter(x => JSON.stringify(x) !== JSON.stringify(entry))].slice(0,5);
  try { localStorage.setItem(historyKey, JSON.stringify(historyItems)); } catch {}
  drawHistory();
}
byId("intent").onchange();
byId("year").value = new Date().getFullYear() - 1;
drawHistory();
if (location.protocol === "file:") {
  byId("query").hidden = byId("explore").hidden = byId("recent").hidden = true;
  message("Open the live dashboard", "Company research uses the hosted SEC connection.");
  result.firstChild.append(link("Go to Filing Desk ↗", "https://sec-financial-research-agent.onrender.com/"));
}
