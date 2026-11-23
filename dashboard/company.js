"use strict";
const metricNames = {
  revenue: "Revenue", net_income: "Net income", operating_income: "Operating income",
  total_assets: "Total assets", diluted_eps: "Diluted EPS",
  operating_cash_flow: "Operating cash flow", net_margin: "Net margin"
};

function figure(value, unit) {
  if (unit === "%") return value.toFixed(2) + "%";
  const number = new Intl.NumberFormat("en-US", {notation:"compact", maximumFractionDigits:2}).format(value);
  return number + " " + unit;
}

function chartSeries(card, periods, metric) {
  card.replaceChildren();
  const unit = periods.map(p => p.values[metric]?.unit).filter(Boolean).pop();
  const points = periods.map(p => p.values[metric]).filter(v => v && v.unit === unit);
  const max = Math.max(1, ...points.map(v => Math.abs(v.value)));
  // Each observation is labelled with its sign. Bars show absolute magnitude.
  for (const period of periods) {
    const v = period.values[metric];
    card.append(row(period.end, v ? figure(v.value, v.unit) : "Unavailable"));
    if (v && v.unit === unit) {
      const track = el("div", undefined, "track");
      const bar = el("div", undefined, v.value < 0 ? "bar negative" : "bar");
      bar.style.width = (100 * Math.abs(v.value) / max) + "%";
      track.append(bar);
      card.append(track);
    }
  }
}

const briefThemes = {
  growth: {title: "Growth", metrics: ["revenue", "operating_income", "operating_margin"]},
  profitability: {title: "Profitability", metrics: ["revenue", "net_income", "net_margin"]},
  cash_flow: {title: "Cash flow", metrics: ["operating_cash_flow", "net_income"]},
  balance_sheet: {title: "Balance sheet", metrics: ["total_assets", "net_income"]}
};

function annualPoint(period, metric) {
  if (metric !== "operating_margin") return period.values[metric];
  const {revenue, operating_income: income} = period.values;
  if (revenue?.value > 0 && income && income.unit === revenue.unit && income.start === revenue.start) {
    return {value: 100 * income.value / revenue.value, unit: "%"};
  }
}

function briefNumber(value, unit) {
  if (unit === "%") return value.toLocaleString("en-US", {maximumFractionDigits: 1}) + "%";
  const compact = new Intl.NumberFormat("en-US", {notation: "compact", maximumFractionDigits: 1});
  return unit === "USD" ? (value < 0 ? "−$" : "$") + compact.format(Math.abs(value)) : compact.format(value) + " " + unit;
}

function briefChart(periods, metric) {
  const series = periods.map(p => annualPoint(p, metric));
  const unit = series.filter(Boolean).at(-1)?.unit;
  if (!unit) return null;
  const values = series.map(point => point?.unit === unit ? point.value : null);
  const low = Math.min(0, ...values.filter(v => v !== null));
  const high = Math.max(0, ...values.filter(v => v !== null));
  const span = high - low || 1;
  const zero = -100 * low / span;
  const chart = el("figure", undefined, "brief-chart");
  const title = metricNames[metric] || "Operating margin";
  const caption = el("figcaption", title);
  chart.append(caption);
  if (metric.endsWith("_margin")) {
    chart.append(el("small", metric === "operating_margin" ? "Share of revenue left after operating costs" : "Share of revenue kept as profit"));
  }
  periods.forEach((period, i) => {
    const value = values[i];
    const line = el("div", undefined, "brief-point");
    const year = el("time", period.end.slice(0, 4));
    year.dateTime = period.end;
    year.title = "Period ended " + period.end;
    const track = el("span", undefined, "brief-track");
    track.setAttribute("aria-hidden", "true");
    track.style.setProperty("--zero", zero + "%");
    const label = el("span", value === null ? "—" : briefNumber(value, unit));
    if (value !== null) {
      const bar = el("i", undefined, value < 0 ? "loss" : "gain");
      bar.style.left = (zero + Math.min(0, value) * 100 / span) + "%";
      bar.style.width = (100 * Math.abs(value) / span) + "%";
      track.append(bar);
      label.title = period.end + " · " + value.toLocaleString("en-US") + " " + unit;
    } else {
      label.title = "No comparable figure in " + unit;
      label.setAttribute("aria-label", label.title);
    }
    line.append(year, track, label);
    chart.append(line);
  });
  if (values.includes(null)) chart.append(el("small", "— No comparable figure in " + unit));
  return chart;
}

function renderBrief(output, brief, periods) {
  const theme = briefThemes[brief.focus];
  const heading = el("div", undefined, "brief-heading");
  heading.append(el("h4", theme.title + " brief"), el("span", "Annual filings · " +
    periods[0].end.slice(0, 4) + "–" + periods.at(-1).end.slice(0, 4)));
  const charts = el("div", undefined, "brief-charts");
  for (const metric of theme.metrics) {
    const chart = briefChart(periods, metric);
    if (chart) charts.append(chart);
  }
  const findings = el("div", undefined, "brief-findings");
  for (const finding of brief.findings) {
    const card = el("section", undefined, "brief-finding");
    card.append(el("h5", finding.headline), el("p", finding.interpretation));
    const cited = periods.filter(p => finding.source_dates.includes(p.end));
    if (cited.length) {
      const details = el("details");
      const links = el("div", undefined, "brief-links");
      details.append(el("summary", "View " + (cited.length === 1 ? "1 filing" : cited.length + " filings")));
      for (const p of cited) links.append(link(p.form + " · " + p.end, p.url));
      details.append(links);
      card.append(details);
    }
    findings.append(card);
  }
  const limit = el("details", undefined, "brief-limit");
  limit.append(el("summary", "Limits of this analysis"), el("p", brief.limitation));
  output.replaceChildren(heading, charts, findings, limit);
}

function showCompany(data, symbol) {
  const periods = data.periods;
  result.replaceChildren();
  const title = el("article", undefined, "hero");
  title.append(el("small", (data.ticker || symbol) + " · SEC annual filings"),
    el("h2",data.company,"introTitle"));
  if (periods.length) title.append(el("p",periods[0].end + " through " + periods.at(-1).end));
  result.append(title);
  if (!periods.length) {
    result.append(el("article","No original 10-K, 20-F or 40-F annual reports were found for this filer."));
    return;
  }
  const latest = periods.at(-1);
  const grid = el("div",undefined,"metrics");
  for (const key of ["revenue","net_income","operating_cash_flow","net_margin"]) {
    const v = latest.values[key];
    const cell = el("article");
    cell.append(el("small",metricNames[key]),el("strong",v ? figure(v.value,v.unit) : "Unavailable"));
    grid.append(cell);
  }
  result.append(grid);
  const keys = Object.keys(metricNames).filter(k => periods.some(p => p.values[k]));
  if (keys.length) {
    const series = el("article"), select = el("select"), bars = el("div");
    select.setAttribute("aria-label","Annual series");
    for (const key of keys) {
      const opt = el("option",metricNames[key]); opt.value = key; select.append(opt);
    }
    select.onchange = () => chartSeries(bars, periods, select.value);
    series.append(el("h3","Annual performance"),select,bars);
    result.append(series);
    select.onchange();
  }
  const analysis = el("article");
  analysis.append(el("h3","Trend investigation"));
  if (data.revenue_growth !== null) analysis.append(row("Annual revenue change",figure(data.revenue_growth,"%")));
  const t = data.trend;
  if (t) {
    analysis.append(el("p",metricNames[t.metric] + " came in " + figure(Math.abs(t.gap),t.unit)
      + (t.gap < 0 ? " below" : " above") + " its historical trend baseline."),
      row("Historical baseline",figure(t.baseline,t.unit)),row("Reported",figure(t.actual,t.unit)),
      el("small","Theil–Sen regression fitted to " + t.training_years + " earlier annual observations. The latest observation was held out. This comparison does not establish a cause."));
  } else analysis.append(el("p","The trend model needs a latest value and three earlier annual observations in the same unit for revenue, net income or assets."));
  result.append(analysis);
  const ai = el("article"), button = el("button","Generate AI brief","export"), output = el("div", undefined, "brief-output");
  output.setAttribute("aria-live", "polite");
  ai.append(el("h3","AI analyst"),el("p",data.ai_enabled ?
    "See what changed across annual filings, with charts and a short explanation." :
    "Written analysis requires an OpenAI API key configured by the site owner. The historical trend model runs independently."));
  if (data.ai_enabled && keys.length) ai.append(button,output);
  result.append(ai);
  button.onclick = async () => {
    button.disabled = true;
    output.replaceChildren(el("p","Selecting an investigation and reviewing the evidence…"));
    try {
      const response = await fetch("/api/brief?company="+encodeURIComponent(symbol),{method:"POST", headers:{"Content-Type":"application/json"}});
      const brief = await response.json();
      if (!response.ok) throw new Error(brief.error || "Analysis unavailable.");
      renderBrief(output, brief, periods);
      button.hidden = true;
    } catch (err) { output.replaceChildren(el("p",err.message)); button.disabled=false; }
  };
  const filings = el("article");
  filings.append(el("h3","Annual filing sources"));
  for (const p of [...periods].reverse()) {
    const source = el("div",undefined,"row");
    source.append(el("span",p.end),link("Open "+p.form,p.url));
    filings.append(source);
  }
  result.append(filings);
}
