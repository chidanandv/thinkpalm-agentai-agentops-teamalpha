/**
 * Fleet Health Operations Dashboard
 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let severityChart = null;
let typeChart = null;
let currentReport = null;
let pipelineAbort = null;
let pipelineRunning = false;
const PIPELINE_TIMEOUT_MS = 60000;

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
    btn.disabled = on;
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

    renderKPIs(payload, report, vessels, anomalies, escalations);
    renderCharts(anomalies);
    renderExecutive(payload, report);
    renderVessels(vessels);
    renderAnomalies(anomalies);
    renderEscalations(escalations);
    renderAgents(payload.agent_outputs || report.raw_agent_outputs || {});
  } catch (e) {
    console.error("renderReport failed:", e);
    showToast("Failed to render report: " + e.message, "error");
    throw e;
  }
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

function renderVessels(vessels) {
  $("#vessel-cards").innerHTML = vessels
    .map(
      (v) => `
    <article class="vessel-card">
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
}

function renderAnomalies(anomalies) {
  const tbody = $("#anomalies-table tbody");
  const empty = $("#no-anomalies");
  if (!anomalies.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
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
  checkHealth();
  initTabs();

  const hasHistory = await loadHistory();
  if (hasHistory) await loadLatestReport();

  $("#btn-run-sample").addEventListener("click", runSamplePipeline);
  $("#btn-cancel-pipeline")?.addEventListener("click", cancelPipeline);
  $("#btn-load-history").addEventListener("click", loadSelectedHistory);
  $("#btn-open-docs").addEventListener("click", () => window.open("/docs", "_blank"));
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
