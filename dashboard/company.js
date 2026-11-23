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
  const ai = el("article"), button = el("button","Generate AI brief","export"), output = el("div");
  ai.append(el("h3","AI analyst"),el("p",data.ai_enabled ?
    "Investigate a financial theme and interpret the evidence with filing citations." :
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
      output.replaceChildren(el("h3",brief.focus.replaceAll("_"," ")));
      for (const f of brief.findings) {
        const paragraph = el("p", f.interpretation + " ");
        for (const end of new Set(f.source_dates)) {
          const period = periods.find(p => p.end === end);
          if (period) paragraph.append(link(end,period.url), " ");
        }
        output.append(paragraph);
      }
      output.append(el("small", brief.limitation));
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
