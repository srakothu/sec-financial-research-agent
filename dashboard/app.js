"use strict";
const byId = id => document.getElementById(id);
const result = byId("results");
let mode = "sample";
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
    notation: compact ? "compact" : "standard", maximumFractionDigits:compact ? 3 : 2,
    minimumFractionDigits:0}).format(value);
}
function show(data) {
  result.replaceChildren();
  const hero = el("article", undefined, "hero");
  const fact = data.fact, growth = data.growth;
  hero.append(el("small", (mode === "sample" ? "Saved SEC sample" : "Live SEC result") + " · " + data.ticker),
    el("h2", data.company));
  hero.append(el("p", fact ? money(fact.value, true) : data.excerpts.length ? "Earnings announcement" : "Recent filings", "number"));
  if (fact) hero.append(el("p", fact.label + (fact.unit === "USD/shares" ? " per share" : "") + " · period ended " + fact.end));
  if (growth) hero.append(el("p", Number(growth.percent).toFixed(2) + "% year over year", "change"));
  result.append(hero);
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
}
function message(text) {
  result.replaceChildren(el("article", text));
}
function switchMode(next) {
  mode = next;
  version++;
  byId("sample").setAttribute("aria-pressed", next === "sample");
  byId("live").setAttribute("aria-pressed", next === "live");
  byId("presets").hidden = next !== "sample";
  byId("fields").hidden = next !== "live";
  if (next === "sample") show(samples[Number(byId("preset").value)]);
  else message(location.protocol === "file:" ? "Open Open-Dashboard.command from the project folder to connect to live SEC data." : "Choose a company and run a lookup.");
}
byId("sample").onclick = () => switchMode("sample");
byId("live").onclick = () => switchMode("live");
byId("preset").onchange = () => show(samples[Number(byId("preset").value)]);
byId("intent").onchange = () => {
  byId("financial").hidden = byId("intent").value !== "fact";
  byId("year").disabled = byId("financial").hidden;
  byId("eventDate").hidden = byId("intent").value !== "event";
};
byId("metric").onchange = () => { byId("compare").hidden = byId("metric").value !== "revenue"; };
byId("query").onsubmit = async event => {
  event.preventDefault();
  if (mode !== "live" || location.protocol === "file:") return;
  const ticket = ++version;
  const intent = byId("intent").value;
  const params = new URLSearchParams({company:byId("company").value.trim(),intent});
  if (intent === "fact") {
    const period = byId("period").value;
    params.set("metric",byId("metric").value);
    params.set("fiscal_year",byId("year").value);
    params.set("period",period === "annual" ? "annual" : "quarterly");
    if (period !== "annual") params.set("quarter",period);
    if (byId("metric").value === "revenue" && byId("growth").checked) params.set("year_over_year","true");
  } else if (intent === "event") {
    params.set("earnings_only","true");
    if (byId("date").value) params.set("event_date",byId("date").value);
  }
  message("Looking up SEC filings…");
  try {
    const response = await fetch("/api/research?" + params);
    const data = await response.json();
    if (ticket !== version) return;
    if (!response.ok) throw new Error(data.error || "The server could not complete this lookup.");
    show(data);
  } catch (err) {
    if (ticket === version) message(err.message);
  }
};
switchMode("sample");
