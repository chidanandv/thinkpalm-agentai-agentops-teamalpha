/**
 * Fleet Health Operations Dashboard
 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let severityChart = null;
let typeChart = null;
let trendsChart = null;
let currentReport = null;
let allAnomalies = [];
let pipelineAbort = null;
let pipelineRunning = false;
const PIPELINE_TIMEOUT_MS = 60000;
const THEME_KEY = "fleet-health-theme";

const SEV_COLORS = {
  critical: "#dc2626",
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#64748b",
};

const TYPE_LABELS = {
  fuel_overconsumption: "Fuel",
  schedule_slippage: "Schedule",
  overdue_maintenance: "Maintenance",
};

/* ── Utilities ───────────────────────────────────────────── */

function showToast(msg, type = "success") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => (el.hidden = true), 3500);
}

function setLoading(on) {
  const overlay = $("#loading-overlay");
  const btn = $("#btn-run-sample");
  if (overlay) overlay.hidden = !on;
  if (btn) {
    btn.disabled = !!on;
    btn.classList.toggle("is-loading", !!on);
    btn.setAttribute("aria-busy", on ? "true" : "false");
    const spinner = btn.querySelector(".btn-spinner");
    if (spinner) spinner.hidden = !on;
  }
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function sevClass(s) {
  return (s || "low").toLowerCase();
}

function statusClass(s) {
  const m = { Green: "green", Amber: "amber", Red: "red" };
  return m[s] || "amber";
}

function computeFleetScore(vessels, anomalies) {
  let score = 100;
  vessels.forEach((v) => {
    if (v.overall_status === "Red") score -= 22;
    else if (v.overall_status === "Amber") score -= 10;
  });
  anomalies.forEach((a) => {
    const s = sevClass(a.severity);
    if (s === "critical") score -= 8;
    else if (s === "high") score -= 3;
  });
  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreGrade(score) {
  if (score >= 85) return { label: "Excellent", cls: "excellent" };
  if (score >= 70) return { label: "Good", cls: "good" };
  if (score >= 50) return { label: "Fair", cls: "fair" };
  return { label: "Critical", cls: "critical" };
}

function switchToTab(tabId) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabId));
  $$(".tab-panel").forEach((p) => {
    const on = p.id === `panel-${tabId}`;
    p.hidden = !on;
    p.classList.toggle("active", on);
  });
}

/* ── API ─────────────────────────────────────────────────── */

async function api(path, opts = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  if (opts.signal) {
    if (opts.signal.aborted) controller.abort();
    else opts.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  try {
    const { signal: _ignored, ...fetchOpts } = opts;
    const res = await fetch(path, {
      headers: { Accept: "application/json", ...fetchOpts.headers },
      ...fetchOpts,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(
        typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail) || res.statusText
      );
    }
    return res.json();
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out or was cancelled. Try again.");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

async function checkHealth() {
  const pill = $("#api-status");
  const llm = $("#llm-status");
  try {
    const h = await api("/health");
    pill.textContent = "API Online";
    pill.dataset.state = "ok";
    llm.textContent = h.anthropic_configured ? "Claude Active" : "Deterministic";
    llm.dataset.state = h.anthropic_configured ? "ok" : "unknown";
  } catch {
    pill.textContent = "API Offline";
    pill.dataset.state = "error";
  }
}

async function loadFleetTrends() {
  try {
    const data = await api("/api/v1/fleet/trends?limit=10");
    renderTrendChart(data.trends || []);
    return data;
  } catch {
    renderTrendChart([]);
    return null;
  }
}

async function loadHistory() {
  const sel = $("#recent-select");
  try {
    const data = await api("/api/v1/reports/history?limit=15");
    sel.innerHTML = "";
    if (!data.reports?.length) {
      sel.innerHTML = '<option value="">No saved reports yet</option>';
      $("#btn-load-history").disabled = true;
      return false;
    }
    sel.innerHTML = '<option value="">Select a report…</option>';
    data.reports.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r.id;
      const rep = r.report || {};
      opt.textContent = `${rep.fleet_name || "Fleet"} · ${formatDate(r.created_at)} · ${r.anomaly_count} anomalies`;
      opt._reportData = rep;
      opt._meta = r;
      sel.appendChild(opt);
    });
    $("#btn-load-history").disabled = false;
    $("#stat-report-count").textContent = String(data.count);
    return true;
  } catch (e) {
    sel.innerHTML = `<option value="">Failed to load history</option>`;
    showToast(e.message, "error");
    return false;
  }
}

async function loadLatestReport() {
  try {
    const result = await api("/api/v1/reports/latest");
    renderReport(result);
    return true;
  } catch {
    return false;
  }
}

function cancelPipeline(silent = false) {
  if (pipelineAbort) {
    pipelineAbort.abort();
    pipelineAbort = null;
  }
  setLoading(false);
  if (!silent) showToast("Pipeline cancelled", "error");
}

async function runSamplePipeline() {
  if (pipelineRunning) return;

  pipelineRunning = true;
  if (pipelineAbort) cancelPipeline(true);

  pipelineAbort = new AbortController();
  setLoading(true);
  const statusEl = $("#loading-status");
  if (statusEl) statusEl.textContent = "Starting pipeline…";
  animatePipeline(true);

  const steps = [
    "Ingestion agent — normalising data…",
    "Anomaly agent — scanning fleet…",
    "Performance agent — drafting summaries…",
    "Escalation agent — flagging defects…",
    "Compiling report…",
  ];
  const timers = steps.map((msg, i) =>
    setTimeout(() => {
      if (pipelineRunning && statusEl) statusEl.textContent = msg;
    }, i * 600)
  );

  try {
    const result = await api(
      "/api/v1/reports/generate/sample",
      { method: "GET", signal: pipelineAbort.signal },
      PIPELINE_TIMEOUT_MS
    );
    renderReport(result);
    showToast("Report generated successfully");
    await loadHistory();
    animatePipeline(false, true);
  } catch (e) {
    showToast(e.message || "Pipeline failed", "error");
    if (statusEl) statusEl.textContent = "Pipeline failed — try again or load history";
    animatePipeline(false, false);
    await loadLatestReport();
  } finally {
    timers.forEach(clearTimeout);
    pipelineAbort = null;
    pipelineRunning = false;
    setLoading(false);
  }
}

/* ── Pipeline animation ──────────────────────────────────── */

function animatePipeline(running, done = false) {
  $$(".pipeline-steps li").forEach((li, i) => {
    li.classList.remove("active", "done");
    if (done) li.classList.add("done");
    else if (running) {
      setTimeout(() => {
        $$(".pipeline-steps li").forEach((x, j) => {
          x.classList.toggle("active", j === i);
          x.classList.toggle("done", j < i);
        });
      }, i * 600);
    }
  });
}

/* ── Render ──────────────────────────────────────────────── */

function renderReport(payload) {
  try {
    currentReport = payload;
    const report = payload.report || payload;
    const anomalies = report.anomalies || [];
    const escalations = report.escalations || [];
    const vessels = report.vessel_summaries || [];

    $("#empty-state").hidden = true;
    $("#dashboard").hidden = false;

    $("#display-thread-id").textContent = String(payload.thread_id || "—").slice(0, 12);
    $("#display-generated-at").textContent = formatDate(report.generated_at);
    $("#display-fleet-name").textContent = `${report.fleet_name || "—"} · ${report.report_period || ""}`;

    allAnomalies = anomalies;
    if ($("#anomaly-search")) $("#anomaly-search").value = "";
    if ($("#anomaly-filter-severity")) $("#anomaly-filter-severity").value = "";
    renderFleetOverview(vessels, anomalies);
    renderKPIs(payload, report, vessels, anomalies, escalations);
    renderCharts(anomalies);
    renderExecutive(payload, report);
    renderVessels(vessels);
    populateVesselFilter(vessels);
    renderAnomalies(anomalies);
    renderEscalations(escalations);
    renderAgents(payload.agent_outputs || report.raw_agent_outputs || {});
    loadFleetTrends();
    $("#sidebar-stats").hidden = false;
  } catch (e) {
    console.error("renderReport failed:", e);
    showToast("Failed to render report: " + e.message, "error");
    throw e;
  }
}

function renderFleetOverview(vessels, anomalies) {
  const score = computeFleetScore(vessels, anomalies);
  const grade = scoreGrade(score);
  const total = vessels.length || 1;
  const green = vessels.filter((v) => v.overall_status === "Green").length;
  const amber = vessels.filter((v) => v.overall_status === "Amber").length;
  const red = vessels.filter((v) => v.overall_status === "Red").length;

  $("#health-score-value").textContent = String(score);
  $("#health-score-grade").textContent = grade.label;
  $("#health-score-grade").className = grade.cls;
  $("#health-ring")?.setAttribute("data-score", String(score));
  const ring = $("#health-ring .health-ring-fill");
  if (ring) {
    const c = 264;
    ring.style.strokeDashoffset = String(c * (1 - score / 100));
    const colors = { excellent: "#22c55e", good: "#2dd4bf", fair: "#f59e0b", critical: "#dc2626" };
    ring.style.stroke = colors[grade.cls] || colors.good;
  }
  $("#health-score-desc").textContent =
    score >= 85
      ? "Fleet operating within normal parameters."
      : score >= 70
        ? "Some vessels need superintendent attention."
        : score >= 50
          ? "Multiple vessels flagged — review escalations."
          : "Immediate fleet-wide review recommended.";

  $("#posture-green").style.width = `${(green / total) * 100}%`;
  $("#posture-amber").style.width = `${(amber / total) * 100}%`;
  $("#posture-red").style.width = `${(red / total) * 100}%`;
  $("#posture-legend").innerHTML = `
    <span class="posture-key green">${green} Green</span>
    <span class="posture-key amber">${amber} Amber</span>
    <span class="posture-key red">${red} Red</span>`;

  $("#stat-health-score").textContent = String(score);
  $("#stat-health-score").className = `sidebar-stat-val ${grade.cls}`;
}

function renderTrendChart(trends) {
  const empty = $("#no-trends");
  const canvas = $("#chart-trends");
  if (!canvas) return;

  if (trendsChart) trendsChart.destroy();

  if (!trends.length) {
    empty.hidden = false;
    canvas.hidden = true;
    return;
  }
  empty.hidden = true;
  canvas.hidden = false;

  if (typeof Chart === "undefined") return;

  const labels = trends.map((t) => {
    try {
      return new Date(t.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    } catch {
      return `#${t.id}`;
    }
  });

  trendsChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Anomalies",
          data: trends.map((t) => t.anomaly_count),
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.12)",
          tension: 0.35,
          fill: true,
        },
        {
          label: "Escalations",
          data: trends.map((t) => t.escalation_count),
          borderColor: "#ef4444",
          backgroundColor: "rgba(239, 68, 68, 0.08)",
          tension: 0.35,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#8b9cb8", font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { color: "#8b9cb8", maxRotation: 0 }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: { ticks: { color: "#8b9cb8", stepSize: 1 }, grid: { color: "rgba(255,255,255,0.04)" }, beginAtZero: true },
      },
    },
  });
}

function renderKPIs(payload, report, vessels, anomalies, escalations) {
  const red = vessels.filter((v) => v.overall_status === "Red").length;
  const amber = vessels.filter((v) => v.overall_status === "Amber").length;
  const critical = anomalies.filter((a) => a.severity === "critical").length;

  const kpis = [
    { label: "Vessels", value: vessels.length, cls: "info" },
    { label: "Anomalies", value: payload.anomalies_count ?? anomalies.length, cls: anomalies.length ? "warning" : "success" },
    { label: "Critical", value: critical, cls: critical ? "critical" : "success" },
    { label: "Escalations", value: payload.escalations_count ?? escalations.length, cls: escalations.length ? "critical" : "success" },
    { label: "Red status", value: red, cls: red ? "critical" : "success" },
    { label: "Amber status", value: amber, cls: amber ? "warning" : "success" },
  ];

  $("#kpi-grid").innerHTML = kpis
    .map(
      (k) => `
    <div class="kpi-card ${k.cls}">
      <div class="label">${k.label}</div>
      <div class="value">${k.value}</div>
    </div>`
    )
    .join("");
}

function renderCharts(anomalies) {
  const sevCounts = { critical: 0, high: 0, medium: 0, low: 0 };
  const typeCounts = {};
  anomalies.forEach((a) => {
    const s = sevClass(a.severity);
    sevCounts[s] = (sevCounts[s] || 0) + 1;
    const t = a.anomaly_type || "unknown";
    typeCounts[t] = (typeCounts[t] || 0) + 1;
  });

  if (typeof Chart === "undefined") {
    console.warn("Chart.js not loaded — skipping charts");
    return;
  }

  if (severityChart) severityChart.destroy();
  if (typeChart) typeChart.destroy();

  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#8b9cb8", font: { size: 11 } } } },
  };

  severityChart = new Chart($("#chart-severity"), {
    type: "doughnut",
    data: {
      labels: Object.keys(sevCounts).filter((k) => sevCounts[k]),
      datasets: [{
        data: Object.keys(sevCounts).filter((k) => sevCounts[k]).map((k) => sevCounts[k]),
        backgroundColor: Object.keys(sevCounts).filter((k) => sevCounts[k]).map((k) => SEV_COLORS[k]),
        borderWidth: 0,
      }],
    },
    options: chartDefaults,
  });

  const typeKeys = Object.keys(typeCounts);
  typeChart = new Chart($("#chart-type"), {
    type: "bar",
    data: {
      labels: typeKeys.map((k) => TYPE_LABELS[k] || k),
      datasets: [{
        data: typeKeys.map((k) => typeCounts[k]),
        backgroundColor: "rgba(45, 212, 191, 0.6)",
        borderRadius: 6,
      }],
    },
    options: {
      ...chartDefaults,
      scales: {
        x: { ticks: { color: "#8b9cb8" }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: { ticks: { color: "#8b9cb8", stepSize: 1 }, grid: { color: "rgba(255,255,255,0.04)" } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderExecutive(payload, report) {
  $("#executive-summary").textContent =
    payload.executive_summary || report.executive_summary || "No summary available.";
  const recs = payload.recommendations || report.recommendations || [];
  $("#recommendations-list").innerHTML = recs.map((r) => `<li>${r}</li>`).join("") || "<li>No recommendations.</li>";
}

function populateVesselFilter(vessels) {
  const sel = $("#anomaly-filter-vessel");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">All vessels</option>';
  vessels.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v.vessel_id;
    opt.textContent = v.vessel_id;
    sel.appendChild(opt);
  });
  if ([...sel.options].some((o) => o.value === current)) sel.value = current;
}

function renderVessels(vessels) {
  $("#vessel-cards").innerHTML = vessels
    .map(
      (v) => `
    <article class="vessel-card" data-vessel="${v.vessel_id}" role="button" tabindex="0" title="View anomalies for this vessel">
      <header>
        <h4>${v.vessel_id}</h4>
        <span class="status-badge ${statusClass(v.overall_status)}">${v.overall_status}</span>
      </header>
      <dl class="vessel-metrics">
        <div><dt>Fuel</dt><dd>${v.fuel_performance}</dd></div>
        <div><dt>Schedule</dt><dd>${v.schedule_compliance}</dd></div>
        <div><dt>Maintenance</dt><dd>${v.maintenance_status}</dd></div>
        <div><dt>Anomalies</dt><dd>${v.anomalies_count}</dd></div>
      </dl>
      ${
        v.key_observations?.length
          ? `<div class="vessel-obs"><strong>Observations</strong><ul>${v.key_observations.map((o) => `<li>${o}</li>`).join("")}</ul></div>`
          : ""
      }
    </article>`
    )
    .join("");

  $$(".vessel-card[data-vessel]").forEach((card) => {
    const open = () => {
      const id = card.dataset.vessel;
      $("#anomaly-filter-vessel").value = id;
      switchToTab("anomalies");
      applyAnomalyFilters();
      showToast(`Filtering anomalies for ${id}`);
    };
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
  });
}

function getFilteredAnomalies() {
  const q = ($("#anomaly-search")?.value || "").trim().toLowerCase();
  const sev = $("#anomaly-filter-severity")?.value || "";
  const vessel = $("#anomaly-filter-vessel")?.value || "";
  return allAnomalies.filter((a) => {
    if (sev && sevClass(a.severity) !== sev) return false;
    if (vessel && a.vessel_id !== vessel) return false;
    if (q) {
      const hay = `${a.vessel_id} ${a.anomaly_type} ${a.severity} ${a.description}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function applyAnomalyFilters() {
  renderAnomalies(getFilteredAnomalies(), true);
}

function renderAnomalies(anomalies, isFiltered = false) {
  const tbody = $("#anomalies-table tbody");
  const empty = $("#no-anomalies");
  if (!anomalies.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
    empty.textContent = isFiltered
      ? "No anomalies match the current filters."
      : "No anomalies detected.";
    return;
  }
  empty.hidden = true;
  tbody.innerHTML = anomalies
    .map(
      (a) => `
    <tr>
      <td>${a.vessel_id}</td>
      <td><span class="type-tag">${TYPE_LABELS[a.anomaly_type] || a.anomaly_type}</span></td>
      <td><span class="sev ${sevClass(a.severity)}">${a.severity}</span></td>
      <td>${a.description}</td>
      <td>${a.metric_value != null ? a.metric_value : "—"}</td>
    </tr>`
    )
    .join("");
}

function renderEscalations(escalations) {
  const list = $("#escalation-list");
  const empty = $("#no-escalations");
  if (!escalations.length) {
    list.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  list.innerHTML = escalations
    .map(
      (e) => `
    <article class="escalation-card ${sevClass(e.severity)}">
      <h4>${e.vessel_id} — ${e.equipment}</h4>
      <p class="meta"><span class="sev ${sevClass(e.severity)}">${e.severity}</span> · ${e.shore_contact || "Fleet Technical Superintendent"}</p>
      <p>${e.reason}</p>
      <p class="action">→ ${e.recommended_action}</p>
    </article>`
    )
    .join("");
}

function renderAgents(outputs) {
  const names = {
    ingestion_agent: "Ingestion Agent",
    anomaly_agent: "Anomaly Agent",
    performance_agent: "Performance Agent",
    escalation_agent: "Escalation Agent",
  };
  $("#agent-cards").innerHTML = Object.entries(outputs)
    .map(
      ([key, val]) => `
    <article class="agent-card">
      <h4>${names[key] || key}</h4>
      <pre>${typeof val === "string" ? val : JSON.stringify(val, null, 2)}</pre>
    </article>`
    )
    .join("") || '<p class="empty-inline">No agent outputs recorded.</p>';
}

/* ── Export, print, theme ─────────────────────────────────── */

function exportReportJson() {
  if (!currentReport) {
    showToast("No report loaded", "error");
    return;
  }
  const blob = new Blob([JSON.stringify(currentReport, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const fleet = currentReport.report?.fleet_name || "fleet";
  a.href = url;
  a.download = `fleet-health-${fleet.replace(/\s+/g, "-").toLowerCase()}-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
  showToast("Report exported as JSON");
}

function printReport() {
  if (!currentReport) {
    showToast("No report loaded", "error");
    return;
  }
  window.print();
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY) || "dark";
  document.documentElement.dataset.theme = saved;
  updateThemeButton(saved);

  $("#btn-theme")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
    updateThemeButton(next);
  });
}

function updateThemeButton(theme) {
  const btn = $("#btn-theme");
  if (!btn) return;
  btn.textContent = theme === "light" ? "🌙" : "☀️";
  btn.title = theme === "light" ? "Switch to dark mode" : "Switch to light mode";
}

function initAnomalyFilters() {
  const rerender = () => applyAnomalyFilters();
  $("#anomaly-search")?.addEventListener("input", rerender);
  $("#anomaly-filter-severity")?.addEventListener("change", rerender);
  $("#anomaly-filter-vessel")?.addEventListener("change", rerender);
  $("#btn-clear-filters")?.addEventListener("click", () => {
    $("#anomaly-search").value = "";
    $("#anomaly-filter-severity").value = "";
    $("#anomaly-filter-vessel").value = "";
    applyAnomalyFilters();
  });
}

/* ── User guide modal ─────────────────────────────────────── */

function openHelp() {
  const modal = $("#help-modal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("help-open");
  $("#btn-close-help")?.focus();
}

function closeHelp() {
  const modal = $("#help-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("help-open");
}

function initHelp() {
  $("#btn-open-guide")?.addEventListener("click", openHelp);
  $("#btn-close-help")?.addEventListener("click", closeHelp);
  $$("[data-close-help]").forEach((el) => el.addEventListener("click", closeHelp));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#help-modal")?.hidden) closeHelp();
  });
}

/* ── Tabs ────────────────────────────────────────────────── */

function initTabs() {
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const id = tab.dataset.tab;
      $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      $$(".tab-panel").forEach((p) => {
        p.hidden = p.id !== `panel-${id}`;
        p.classList.toggle("active", p.id === `panel-${id}`);
      });
    });
  });
}

/* ── History load ────────────────────────────────────────── */

function loadSelectedHistory() {
  const sel = $("#recent-select");
  const opt = sel.selectedOptions[0];
  if (!opt?._reportData) return;
  renderReport({
    thread_id: opt._meta?.id?.toString() || "history",
    executive_summary: opt._reportData.executive_summary,
    recommendations: opt._reportData.recommendations,
    anomalies_count: opt._reportData.anomalies?.length || 0,
    escalations_count: opt._reportData.escalations?.length || 0,
    report: opt._reportData,
    agent_outputs: opt._reportData.raw_agent_outputs || {},
  });
  showToast("Report loaded from history");
}

/* ── Init ────────────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", async () => {
  setLoading(false);
  initTheme();
  checkHealth();
  initTabs();
  initHelp();
  initAnomalyFilters();

  const hasHistory = await loadHistory();
  if (hasHistory) await loadLatestReport();

  $("#btn-run-sample").addEventListener("click", runSamplePipeline);
  $("#btn-cancel-pipeline")?.addEventListener("click", cancelPipeline);
  $("#btn-load-history").addEventListener("click", loadSelectedHistory);
  $("#btn-open-docs").addEventListener("click", () => window.open("/docs", "_blank"));
  $("#btn-export-json")?.addEventListener("click", exportReportJson);
  $("#btn-print-report")?.addEventListener("click", printReport);
  $("#btn-copy-summary").addEventListener("click", () => {
    const text = currentReport?.executive_summary || currentReport?.report?.executive_summary;
    if (text) {
      navigator.clipboard.writeText(text);
      showToast("Summary copied to clipboard");
    }
  });

  setInterval(checkHealth, 60000);
  window.addEventListener("error", () => {
    pipelineRunning = false;
    setLoading(false);
  });
  window.addEventListener("unhandledrejection", () => {
    pipelineRunning = false;
    setLoading(false);
  });
});
