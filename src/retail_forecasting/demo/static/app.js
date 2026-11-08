"use strict";

const $ = id => document.getElementById(id);
const state = {metadata: null, forecast: null, inventory: null, evaluation: null, controller: null};
const names = {weekday_mean: "Weekday mean", seasonal_naive: "Seasonal naive", recent_mean: "Recent mean", ridge: "Ridge", hist_poisson: "Poisson boosting", static_reference: "Fixed-stock reference", buffered_weekday_mean: "Forecast +50% buffer"};
const policyNames = {static_reference: "Fixed-stock reference", weekday_mean: "Forecast order-up-to", buffered_weekday_mean: "Forecast +50% buffer"};
const policies = ["static_reference", "weekday_mean", "buffered_weekday_mean"];
const policyClasses = {static_reference: "policy-reference", weekday_mean: "policy-forecast", buffered_weekday_mean: "policy-buffer"};
const number = (value, digits = 2) => value == null || !Number.isFinite(Number(value)) ? "Unavailable" : new Intl.NumberFormat("en-GB", {maximumFractionDigits: digits, minimumFractionDigits: digits}).format(Number(value));
const dayLabel = value => new Date(value + "T00:00:00Z").toLocaleDateString("en-GB", {day: "2-digit", month: "short", timeZone: "UTC"});
const fullDate = value => new Date(value + "T00:00:00Z").toLocaleDateString("en-GB", {day: "2-digit", month: "short", year: "numeric", timeZone: "UTC"});

function element(tag, attributes = {}, children = []) {
  const result = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "class") result.className = value;
    else result.setAttribute(name, value);
  }
  for (const child of children) result.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return result;
}

function svgElement(tag, attributes = {}, text = null) {
  const result = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) result.setAttribute(key, value);
  if (text != null) result.textContent = text;
  return result;
}

function table(columns, rows, caption) {
  const result = element("table");
  if (caption) result.append(element("caption", {}, [caption]));
  result.append(element("thead", {}, [element("tr", {}, columns.map(column => element("th", {scope: "col"}, [column.label])))]));
  const body = element("tbody");
  for (const row of rows) {
    const tr = element("tr", row.model === "weekday_mean" ? {class: "selected-model"} : {});
    for (const column of columns) tr.append(element("td", {}, [column.render ? column.render(row) : String(row[column.key] ?? "Unavailable")]));
    body.append(tr);
  }
  result.append(body);
  return result;
}

async function request(url, options = {}) {
  const response = await fetch(url, {...options, signal: options.signal || AbortSignal.timeout(12000)});
  if (!response.ok) {
    const id = response.headers.get("X-Request-ID");
    throw new Error(`Request returned ${response.status}.${id ? " Request ID: " + id : ""}`);
  }
  return response.json();
}

function showForecastError(message) {
  $("forecast-error").hidden = false;
  $("forecast-error-text").textContent = message;
  $("forecast-message").hidden = true;
  $("forecast-result").setAttribute("aria-busy", "false");
  state.forecast = null;
  $("forecast-chart").replaceChildren(element("p", {class: "empty-state"}, ["No forecast available. Please try again."]));
  $("forecast-values").replaceChildren();
  $("cutoff").textContent = "—";
  $("forecast-caption").textContent = "A valid API response is required to display this forecast.";
}

async function loadMetadata() {
  $("forecast-error").hidden = true;
  $("forecast-message").hidden = false;
  $("forecast-message").textContent = "Loading supported products and historical origins…";
  try {
    const metadata = await request("/metadata");
    if (!metadata.supported_skus?.length || !metadata.supported_origins?.length) throw new Error("No supported products or origins were returned.");
    state.metadata = metadata;
    $("sku").replaceChildren(...metadata.supported_skus.map(sku => element("option", {value: sku}, [sku])));
    $("origin").replaceChildren(...metadata.supported_origins.map(origin => element("option", {value: origin}, [fullDate(origin)])));
    $("sku").value = metadata.supported_skus.includes("21212") ? "21212" : metadata.supported_skus[0];
    $("origin").value = metadata.supported_origins.at(-1);
    $("release-id").textContent = metadata.forecast_release_id;
    $("calibration-id").textContent = metadata.calibration_id;
    $("api-state").textContent = "API ready";
    $("api-state").className = "status-pill";
    $("sku").disabled = $("origin").disabled = $("load-forecast").disabled = false;
    await loadForecast();
  } catch (error) {
    state.metadata = null;
    $("api-state").textContent = "API unavailable";
    $("api-state").className = "status-pill unavailable";
    $("sku").disabled = $("origin").disabled = $("load-forecast").disabled = true;
    $("sku").replaceChildren(element("option", {}, ["Products unavailable"]));
    $("origin").replaceChildren(element("option", {}, ["Origins unavailable"]));
    $("release-id").textContent = $("calibration-id").textContent = "Unavailable until artifacts are restored";
    showForecastError(`The historical forecast service is unavailable. Saved evaluation and inventory reports may still be browsed. ${error.message}`);
  }
}

async function loadForecast() {
  if (!state.metadata) return loadMetadata();
  state.controller?.abort();
  const controller = new AbortController();
  state.controller = controller;
  const timeout = setTimeout(() => controller.abort(), 12000);
  const sku = $("sku").value, origin = $("origin").value;
  $("forecast-error").hidden = true;
  $("forecast-message").hidden = false;
  $("forecast-message").textContent = "Loading the 28-day forecast from the existing API…";
  $("forecast-result").setAttribute("aria-busy", "true");
  $("load-forecast").disabled = true;
  state.forecast = null;
  $("forecast-chart").replaceChildren(element("p", {class: "empty-state"}, ["Loading daily predictions and experimental bounds…"]));
  $("forecast-values").replaceChildren();
  $("cutoff").textContent = "—";
  try {
    const data = await request("/forecast", {method: "POST", headers: {"Content-Type": "application/json"}, signal: controller.signal,
      body: JSON.stringify({sku, origin, horizon_days: 28})});
    if (state.controller !== controller) return;
    if (data.sku !== sku || data.origin !== origin || data.predictions?.length !== 28 ||
      !data.predictions.every(row => [row.predicted_sales, row.interval_80?.lower, row.interval_80?.upper, row.interval_95?.lower, row.interval_95?.upper].every(Number.isFinite))) throw new Error("The API returned an invalid forecast response.");
    state.forecast = data;
    $("cutoff").textContent = fullDate(data.history_cutoff);
    $("release-id").textContent = data.forecast_release_id;
    $("calibration-id").textContent = data.calibration_id;
    $("forecast-caption").textContent = `SKU ${data.sku} · ${dayLabel(data.predictions[0].target_date)} – ${fullDate(data.predictions.at(-1).target_date)}`;
    $("forecast-message").textContent = `Historical demo · Issued ${fullDate(data.origin)}, using sales through ${fullDate(data.history_cutoff)}. Experimental daily intervals.`;
    renderForecastChart();
    $("forecast-values").replaceChildren(table([
      {label: "Target date", key: "target_date"}, {label: "Day", key: "horizon_day"},
      {label: "Point", render: row => number(row.predicted_sales, 3)},
      {label: "80% lower", render: row => number(row.interval_80.lower, 3)}, {label: "80% upper", render: row => number(row.interval_80.upper, 3)},
      {label: "95% lower", render: row => number(row.interval_95.lower, 3)}, {label: "95% upper", render: row => number(row.interval_95.upper, 3)}
    ], data.predictions, "Display values rounded to three decimals; original API values are unchanged."));
  } catch (error) {
    if (state.controller !== controller) return;
    showForecastError(error.name === "AbortError" ? "The request timed out. Please try again." : `Could not load this forecast. ${error.message}`);
  } finally {
    clearTimeout(timeout);
    if (state.controller === controller) {
      $("load-forecast").disabled = false;
      $("forecast-result").setAttribute("aria-busy", "false");
    }
  }
}

function renderForecastChart() {
  if (!state.forecast) return;
  const box = $("forecast-chart"), rows = state.forecast.predictions;
  const width = Math.max(290, box.clientWidth - (window.innerWidth <= 520 ? 10 : 32)), height = width < 450 ? 285 : 315;
  const margin = {left: 53, right: 15, top: 20, bottom: 40}, w = width - margin.left - margin.right, h = height - margin.top - margin.bottom;
  const maximum = Math.max(1, ...rows.map(row => Math.max(row.interval_95.upper, row.predicted_sales)));
  const scale = Math.pow(10, Math.floor(Math.log10(maximum))), top = Math.ceil(maximum / scale * 2) * scale / 2;
  const x = i => margin.left + i / 27 * w, y = value => margin.top + h - value / top * h;
  const svg = svgElement("svg", {viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-labelledby": "forecast-svg-title forecast-svg-desc"});
  svg.append(svgElement("title", {id: "forecast-svg-title"}, "28-day point forecast and experimental 80% and 95% daily intervals"));
  svg.append(svgElement("desc", {id: "forecast-svg-desc"}, "Line and shaded daily bounds. Use Daily forecast values for the accessible numerical table. No actual target sales are plotted; daily intervals do not guarantee simultaneous or total-horizon coverage."));
  for (let i = 0; i <= 4; i++) {
    const value = top * i / 4;
    svg.append(svgElement("line", {x1: margin.left, x2: width - margin.right, y1: y(value), y2: y(value), class: "chart-grid"}));
    svg.append(svgElement("text", {x: margin.left - 9, y: y(value) + 4, "text-anchor": "end", class: "chart-axis"}, number(value, top < 5 ? 1 : 0)));
  }
  for (const [level, cls] of [[95, "band-95"], [80, "band-80"]]) {
    const upper = rows.map((row, i) => `${x(i)},${y(row[`interval_${level}`].upper)}`);
    const lower = rows.map((row, i) => `${x(i)},${y(row[`interval_${level}`].lower)}`).reverse();
    svg.append(svgElement("polygon", {points: [...upper, ...lower].join(" "), class: cls}));
  }
  svg.append(svgElement("path", {d: rows.map((row, i) => `${i ? "L" : "M"}${x(i)} ${y(row.predicted_sales)}`).join(" "), class: "point-line"}));
  for (const i of [0, 7, 14, 21, 27]) svg.append(svgElement("text", {x: x(i), y: height - 12, "text-anchor": i === 0 ? "start" : i === 27 ? "end" : "middle", class: "chart-axis"}, dayLabel(rows[i].target_date)));
  box.replaceChildren(svg);
}

const pointColumns = [
  {label: "Method", render: row => names[row.model] || row.model}, {label: "MASE ↓", render: row => number(row.macro_mase, 4)},
  {label: "MAE", render: row => number(row.mae)}, {label: "WAPE", render: row => number(row.wape_pct) + "%"}, {label: "Bias %", render: row => number(row.bias_pct) + "%"}
];

function unavailable(message, retry) {
  const box = element("div", {class: "unavailable-panel", role: "alert"}, [element("h3", {}, ["Saved results unavailable"]), element("p", {}, [message])]);
  const button = element("button", {type: "button", class: "secondary"}, ["Try again"]);
  button.addEventListener("click", retry);
  box.append(button);
  return box;
}

function evidencePanel(id, section) {
  if (section.status !== "available") return $(id).replaceChildren(unavailable(section.message, loadEvaluation));
  const data = section.data;
  const main = ["weekday_mean", "seasonal_naive"].map(model => data.models.find(row => row.model === model)).filter(Boolean);
  const selected = main.find(row => row.model === "weekday_mean");
  const score = element("div", {class: "score-summary"}, [element("strong", {}, [number(selected?.macro_mase, 4)]), element("span", {}, ["selected weekday-mean macro MASE"])]);
  const pointTable = element("div", {class: "table-scroll", tabindex: "0", role: "region", "aria-label": id === "validation-content" ? "Validation point metrics" : "Final-test point metrics"}, [table(pointColumns, main)]);
  const interval = element("div", {class: "interval-summary"}, [element("h3", {}, ["Experimental daily intervals"]), element("div", {class: "table-scroll", tabindex: "0", role: "region", "aria-label": "Saved interval metrics"}, [table([
    {label: "Nominal", render: row => `${row.level}%`}, {label: "Coverage", render: row => number(row.coverage_pct) + "%"},
    {label: "Mean width", render: row => number(row.mean_width)}, {label: "Interval score", render: row => number(row.mean_interval_score)}
  ], data.intervals)])]);
  if (data.period === "final_test") {
    // Saved interval_metrics_by_target_weekday.csv: Thursday 66.725% / 88.15%, rounded to two decimals.
    interval.append(element("p", {class: "notice warning interval-coverage-note"}, [
      element("strong", {}, ["Overall coverage hides uneven performance:"]),
      " final-test Thursday coverage was 66.73% for the nominal 80% intervals and 88.15% for the nominal 95% intervals. Overall coverage does not guarantee coverage for each SKU or weekday."
    ]));
  }
  $(id).replaceChildren(score, pointTable, interval);
}

async function loadEvaluation() {
  $("evaluation-status").textContent = "Loading saved evaluation results…";
  $("view-evaluation").setAttribute("aria-busy", "true");
  try {
    const data = await request("/demo/api/evaluation");
    state.evaluation = data;
    evidencePanel("validation-content", data.validation);
    evidencePanel("final-content", data.final_test);
    if (data.validation.status === "available") {
      const candidates = ["recent_mean", "ridge", "hist_poisson"].map(model => data.validation.data.models.find(row => row.model === model)).filter(Boolean);
      $("candidate-content").replaceChildren(element("div", {class: "table-scroll", tabindex: "0", role: "region", "aria-label": "Validation-only candidate metrics"}, [table(pointColumns, candidates)]));
    } else $("candidate-content").replaceChildren(unavailable(data.validation.message, loadEvaluation));
    $("evaluation-status").textContent = "Saved results loaded. No evaluation was executed.";
  } catch (error) {
    $("evaluation-status").textContent = "Saved evaluation results could not be loaded.";
    for (const id of ["validation-content", "final-content", "candidate-content"]) $(id).replaceChildren(unavailable(error.message, loadEvaluation));
  } finally { $("view-evaluation").setAttribute("aria-busy", "false"); }
}

async function loadInventory() {
  $("inventory-status").textContent = "Loading saved inventory scenarios…";
  $("view-inventory").setAttribute("aria-busy", "true");
  try {
    const data = await request("/demo/api/inventory");
    if (data.status !== "available") throw new Error(data.message);
    state.inventory = data.data;
    $("inventory-content").hidden = false;
    $("assumption-list").replaceChildren(...data.data.assumptions.map(text => element("li", {}, [text])));
    renderInventory();
    $("inventory-status").textContent = "Saved comparisons loaded. No simulation or optimization was executed.";
  } catch (error) {
    $("inventory-content").hidden = true;
    $("inventory-status").replaceChildren(unavailable(error.message, loadInventory));
  } finally { $("view-inventory").setAttribute("aria-busy", "false"); }
}

function renderInventory() {
  if (!state.inventory) return;
  const lead = Number($("lead-time").value), penalty = Number($("penalty").value);
  const rows = policies.map(policy => state.inventory.scenarios.find(row => row.policy === policy && row.lead_time_days === lead && row.shortage_cost_per_unit === penalty));
  if (rows.some(row => !row)) { $("inventory-table").replaceChildren(unavailable("This saved scenario is unavailable; no values were substituted.", loadInventory)); return; }
  $("scenario-caption").textContent = `Lead time ${lead} day${lead === 1 ? "" : "s"} · shortage penalty ${penalty} · common starting stock ${number(rows[0].starting_stock, 0)} units`;
  $("inventory-table").replaceChildren(table([
    {label: "Policy", render: row => policyNames[row.policy]}, {label: "Fulfilled", render: row => number(row.fulfilled_unit_rate_pct) + "%"},
    {label: "Lost units", render: row => number(row.unfulfilled_units, 0)}, {label: "Avg. stock", render: row => number(row.average_total_closing_inventory)},
    {label: "Orders", render: row => number(row.order_count, 0)}, {label: "Simulated cost", render: row => number(row.total_simulated_cost)}
  ], rows));
  const maximum = Math.max(...rows.map(row => row.total_simulated_cost), 1);
  $("cost-bars").replaceChildren(...rows.map(row => {
    const bar = svgElement("svg", {viewBox: "0 0 100 12", preserveAspectRatio: "none", "aria-hidden": "true"});
    bar.append(svgElement("rect", {width: 100 * row.total_simulated_cost / maximum, height: 12, rx: 2, class: policyClasses[row.policy]}));
    return element("div", {class: "cost-item"}, [element("header", {}, [element("span", {}, [policyNames[row.policy]]), element("strong", {}, [number(row.total_simulated_cost)])]), element("div", {class: "cost-track"}, [bar])]);
  }));
  renderInventoryChart(rows);
}

function renderInventoryChart(rows) {
  const box = $("inventory-chart"), width = Math.max(290, box.clientWidth - 36), height = 265;
  const margin = {left: 45, right: 16, top: 28, bottom: 48}, w = width - margin.left - margin.right, h = height - margin.top - margin.bottom;
  const maximum = Math.max(...rows.map(row => row.average_total_closing_inventory)) * 1.12;
  const minimumRate = Math.max(0, Math.floor(Math.min(...rows.map(row => row.fulfilled_unit_rate_pct)) / 10) * 10 - 10);
  const x = value => margin.left + value / maximum * w, y = value => margin.top + h - (value - minimumRate) / (100 - minimumRate) * h;
  const svg = svgElement("svg", {viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": "Saved policy trade-off: fulfilled-unit rate versus average closing inventory. Exact values are in the policy table."});
  for (let value = minimumRate; value <= 100; value += 10) {
    svg.append(svgElement("line", {x1: margin.left, x2: width - margin.right, y1: y(value), y2: y(value), class: "chart-grid"}));
    svg.append(svgElement("text", {x: margin.left - 7, y: y(value) + 4, "text-anchor": "end", class: "chart-axis"}, `${value}%`));
  }
  for (let i = 0; i <= 3; i++) svg.append(svgElement("text", {x: x(maximum * i / 3), y: height - 29, "text-anchor": i === 0 ? "start" : i === 3 ? "end" : "middle", class: "chart-axis"}, number(maximum * i / 3, 0)));
  svg.append(svgElement("text", {x: margin.left, y: 14, class: "chart-label"}, "Fulfilled units (%)"));
  svg.append(svgElement("text", {x: margin.left + w / 2, y: height - 7, "text-anchor": "middle", class: "chart-label"}, "Avg. daily closing inventory (total units)"));
  for (const row of rows) {
    const circle = svgElement("circle", {cx: x(row.average_total_closing_inventory), cy: y(row.fulfilled_unit_rate_pct), r: 7, class: policyClasses[row.policy]});
    circle.append(svgElement("title", {}, `${policyNames[row.policy]}: ${number(row.fulfilled_unit_rate_pct)}% fulfilled, ${number(row.average_total_closing_inventory)} average units`));
    svg.append(circle);
  }
  const key = element("div", {class: "chart-key"}, rows.map(row => {
    const dot = svgElement("svg", {width: 10, height: 10, viewBox: "0 0 10 10", "aria-hidden": "true"});
    dot.append(svgElement("circle", {cx: 5, cy: 5, r: 4, class: policyClasses[row.policy]}));
    return element("span", {}, [dot, policyNames[row.policy]]);
  }));
  box.replaceChildren(svg, key);
}

function navigate(focus = false) {
  const view = location.hash.slice(1) || "forecast";
  if (!["forecast", "evaluation", "inventory"].includes(view)) return;
  for (const name of ["forecast", "evaluation", "inventory"]) $("view-" + name).hidden = name !== view;
  for (const link of document.querySelectorAll("nav [data-view]")) {
    if (link.dataset.view === view) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  }
  if (view === "evaluation" && !state.evaluation) loadEvaluation();
  if (view === "inventory" && !state.inventory) loadInventory();
  if (view === "forecast") renderForecastChart();
  if (focus) { const heading = $(view + "-heading"); heading.tabIndex = -1; heading.focus({preventScroll: true}); window.scrollTo({top: 0}); }
}

$("forecast-form").addEventListener("submit", event => { event.preventDefault(); loadForecast(); });
$("retry-forecast").addEventListener("click", () => state.metadata ? loadForecast() : loadMetadata());
$("lead-time").addEventListener("change", renderInventory);
$("penalty").addEventListener("change", renderInventory);
window.addEventListener("hashchange", () => navigate(true));
new ResizeObserver(() => { renderForecastChart(); if (state.inventory && !$("view-inventory").hidden) renderInventory(); }).observe($("main"));
navigate();
loadMetadata();
