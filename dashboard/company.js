"use strict";
const metricNames = {
  revenue: "Revenue", net_income: "Net income", operating_income: "Operating income",
  total_assets: "Total assets", diluted_eps: "Diluted EPS",
  operating_cash_flow: "Operating cash flow", net_margin: "Net margin"
};

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

function performancePanel(data, keys) {
  const panel = el("div", undefined, "performance");
  if (keys.length) {
    const chart = el("article"), head = el("div", undefined, "section-head");
    const select = el("select"), plot = el("div");
    select.setAttribute("aria-label", "Chart metric");
    for (const key of keys) {
      const option = el("option", metricNames[key]);
      option.value = key;
      select.append(option);
    }
    select.onchange = () => {
      const metric = select.value;
      const evidence = el("details", undefined, "period-values");
      evidence.append(el("summary", "Period figures and filings"));
      for (const period of data.periods) {
        const point = period.values[metric];
        const record = el("div", undefined, "row");
        record.append(link(period.end + " · " + period.form, period.url),
          el("span", point ? point.value.toLocaleString("en-US", {maximumFractionDigits: 6}) + " " + point.unit : "Unavailable"));
        evidence.append(record);
      }
      plot.replaceChildren(briefChart(data.periods, metric), evidence);
    };
    head.append(el("h3", "Annual performance"), select);
    chart.append(head, plot);
    panel.append(chart);
    select.onchange();
  }
  const signal = el("article", undefined, "signal");
  signal.append(el("h3", "Historical comparison"));
  const t = data.trend;
  if (t) {
    const direction = t.gap === 0 ? "Matched the baseline" : t.gap > 0 ? "Above the baseline" : "Below the baseline";
    signal.append(el("strong", direction), el("p", metricNames[t.metric] + " in the latest annual filing, compared with the trend from earlier years."),
      row("Reported", briefNumber(t.actual, t.unit)), row("Trend baseline", briefNumber(t.baseline, t.unit)));
    const method = el("details");
    method.append(el("summary", "How this is calculated"), el("p", "A Theil–Sen regression fits a trend to " + t.training_years +
      " earlier observations in the same unit. The latest year is held out for comparison."));
    signal.append(method);
  } else signal.append(el("p", "A trend comparison needs a latest figure and three earlier annual figures in the same currency for revenue, net income or assets."));
  panel.append(signal);
  return panel;
}

function analystPanel(data, symbol, keys) {
  const ai = el("article"), button = el("button", "Generate AI brief", "primary"), output = el("div", undefined, "brief-output");
  output.setAttribute("aria-live", "polite");
  ai.append(el("h3", "AI analyst"));
  if (!data.ai_enabled || !keys.length) {
    ai.append(el("p", !keys.length ? "This filer has too few tagged figures for an AI brief." : "AI briefs are currently unavailable. Explore the reported figures in Performance."));
    return ai;
  }
  ai.append(el("p", "Investigate a change in the financials and see the annual filings behind each finding."), button, output);
  button.onclick = async () => {
    button.disabled = true;
    button.textContent = "Generating…";
    output.replaceChildren(el("p", "Reviewing annual figures for " + data.company + "…"));
    try {
      const response = await fetch("/api/brief?company=" + encodeURIComponent(symbol), {method:"POST", headers:{"Content-Type":"application/json"}});
      if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("The analyst service is temporarily unavailable. Try again.");
      const brief = await response.json();
      if (!response.ok) throw new Error(brief.error || "Analysis unavailable.");
      renderBrief(output, brief, data.periods);
      button.hidden = true;
    } catch (err) {
      output.replaceChildren(el("p", err.message));
      button.textContent = "Retry AI brief";
      button.disabled = false;
    }
  };
  return ai;
}

function showCompany(data, symbol) {
  const periods = data.periods, latest = periods.at(-1);
  const title = el("div", undefined, "company-title");
  title.append(el("span", data.ticker || symbol, "ticker"), el("h2", data.company));
  if (latest) title.append(el("small", "Annual results through " + latest.end));
  result.replaceChildren(title);
  if (!latest) {
    result.append(el("article", "No original 10-K, 20-F or 40-F annual reports were found for this filer."));
    return;
  }
  const metrics = el("div", undefined, "metrics");
  for (const key of ["revenue", "net_income", "operating_cash_flow", "net_margin"]) {
    const point = latest.values[key];
    const cell = el("div");
    cell.append(el("span", metricNames[key]), el("strong", point ? briefNumber(point.value, point.unit) : "Unavailable"));
    if (key === "revenue" && data.revenue_growth != null) {
      cell.append(el("small", (data.revenue_growth > 0 ? "+" : "") + briefNumber(data.revenue_growth, "%") + " year over year"));
    }
    metrics.append(cell);
  }
  const keys = Object.keys(metricNames).filter(k => periods.some(p => p.values[k]));
  const filings = el("article");
  filings.append(el("h3", "Annual filing sources"));
  for (const p of [...periods].reverse()) {
    const source = el("div", undefined, "row");
    source.append(el("span", "Period ended " + p.end), link("Form " + p.form + " ↗", p.url));
    filings.append(source);
  }
  const views = [["Performance", performancePanel(data, keys)], ["AI brief", analystPanel(data, symbol, keys)], ["Filings (" + periods.length + ")", filings]];
  const nav = el("div", undefined, "report-nav");
  nav.setAttribute("role", "group");
  nav.setAttribute("aria-label", "Company report sections");
  result.append(metrics, nav);
  for (const [name, view] of views) {
    const button = el("button", name);
    view.id = "report-panel-" + nav.children.length;
    button.setAttribute("aria-controls", view.id);
    button.setAttribute("aria-pressed", String(!nav.children.length));
    view.hidden = Boolean(nav.children.length);
    button.onclick = () => {
      for (const child of nav.children) child.setAttribute("aria-pressed", String(child === button));
      for (const [, section] of views) section.hidden = section !== view;
    };
    nav.append(button);
    result.append(view);
  }
}
