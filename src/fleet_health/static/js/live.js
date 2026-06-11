/**
 * Fleet Command Center — Live dashboard with animated effects
 */

const $ = (sel) => document.querySelector(sel);
const THEME_KEY = "fleet-health-theme";

const AGENT_NAMES = {
  ingestion_agent: "Ingestion",
  anomaly_agent: "Anomaly",
  performance_agent: "Performance",
  escalation_agent: "Escalation",
};

/* ── Particles ───────────────────────────────────────────── */

function initParticles() {
  const canvas = $("#particle-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let w, h, particles;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }

  function mkParticles() {
    const n = Math.min(60, Math.floor((w * h) / 18000));
    particles = Array.from({ length: n }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.5 + 0.5,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      a: Math.random() * 0.4 + 0.1,
    }));
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--live-accent").trim() || "#22d3ee";
    particles.forEach((p) => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = accent;
      ctx.globalAlpha = p.a;
      ctx.fill();
    });
    ctx.globalAlpha = 1;
    requestAnimationFrame(draw);
  }

  resize();
  mkParticles();
  draw();
  window.addEventListener("resize", () => {
    resize();
    mkParticles();
  });
}

/* ── API ─────────────────────────────────────────────────── */

async function api(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" }, credentials: "include" });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Not authenticated");
  }
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

function computeScore(vessels, anomalies) {
  let score = 100;
  vessels.forEach((v) => {
    if (v.overall_status === "Red") score -= 22;
    else if (v.overall_status === "Amber") score -= 10;
  });
  anomalies.forEach((a) => {
    const s = (a.severity || "").toLowerCase();
    if (s === "critical") score -= 8;
    else if (s === "high") score -= 3;
  });
  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreGrade(score) {
  if (score >= 85) return "Excellent";
  if (score >= 70) return "Good";
  if (score >= 50) return "Fair";
  return "Critical";
}

function statusCls(s) {
  return { Green: "green", Amber: "amber", Red: "red" }[s] || "amber";
}

function animateCount(el, target, duration = 800) {
  if (!el) return;
  const start = parseInt(el.textContent, 10) || 0;
  if (start === target) {
    el.textContent = String(target);
    return;
  }
  const t0 = performance.now();
  const step = (now) => {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - (1 - p) ** 3;
    el.textContent = String(Math.round(start + (target - start) * eased));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderRadar(vessels) {
  const dots = $("#radar-dots");
  if (!dots) return;
  dots.innerHTML = "";
  const positions = [
    { x: 35, y: 40 },
    { x: 65, y: 35 },
    { x: 50, y: 62 },
    { x: 28, y: 68 },
    { x: 72, y: 58 },
  ];
  vessels.forEach((v, i) => {
    const pos = positions[i % positions.length];
    const d = document.createElement("div");
    d.className = `radar-dot ${statusCls(v.overall_status)}`;
    d.style.left = `${pos.x}%`;
    d.style.top = `${pos.y}%`;
    d.title = v.vessel_id;
    dots.appendChild(d);
  });
}

function renderVesselOrbs(vessels) {
  const wrap = $("#vessel-orbs");
  const empty = $("#no-vessels-live");
  if (!wrap) return;
  if (!vessels.length) {
    wrap.innerHTML = "";
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;
  wrap.innerHTML = vessels
    .map(
      (v) => `
    <div class="vessel-orb ${statusCls(v.overall_status)}">
      <h4>${v.vessel_id}</h4>
      <span class="orb-status">${v.overall_status}</span>
      <div style="font-size:0.7rem;color:var(--live-muted);margin-top:0.35rem">${v.anomalies_count ?? 0} anomalies</div>
    </div>`
    )
    .join("");
}

function renderAgentStream(outputs) {
  const ul = $("#agent-stream");
  if (!ul) return;
  const entries = Object.entries(outputs || {});
  if (!entries.length) {
    ul.innerHTML = `<li><span class="dot"></span><span class="name">system</span><span>Waiting for pipeline run…</span></li>`;
    return;
  }
  ul.innerHTML = entries
    .map(
      ([key, val], i) => `
    <li style="animation-delay:${i * 0.1}s">
      <span class="dot"></span>
      <span class="name">${AGENT_NAMES[key] || key}</span>
      <span>${typeof val === "string" ? val.split("\n")[0].slice(0, 80) : "Complete"}…</span>
    </li>`
    )
    .join("");
}

function renderPriorityQueue(anomalies, escalations) {
  const ul = $("#priority-queue");
  const empty = $("#no-priority");
  if (!ul) return;
  const items = [];
  anomalies
    .filter((a) => ["critical", "high"].includes((a.severity || "").toLowerCase()))
    .forEach((a) => items.push({ title: a.vessel_id, text: a.description }));
  escalations
    .filter((e) => (e.severity || "").toLowerCase() === "critical")
    .forEach((e) => items.push({ title: `${e.vessel_id} · ${e.equipment}`, text: e.reason }));

  if (!items.length) {
    ul.innerHTML = "";
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;
  ul.innerHTML = items
    .slice(0, 5)
    .map((it) => `<li><strong>${it.title}</strong>${it.text}</li>`)
    .join("");
}

function renderTrendBars(trends) {
  const wrap = $("#trend-bars");
  const empty = $("#no-trends-live");
  if (!wrap) return;
  if (!trends?.length) {
    wrap.innerHTML = "";
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;
  const max = Math.max(...trends.map((t) => t.anomaly_count), 1);
  wrap.innerHTML = trends
    .map((t, i) => {
      const pct = (t.anomaly_count / max) * 100;
      const label = (() => {
        try {
          return new Date(t.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
        } catch {
          return `#${t.id}`;
        }
      })();
      return `
      <div class="trend-bar-wrap">
        <div class="trend-bar" style="height:${pct}%;animation-delay:${i * 0.08}s" title="${t.anomaly_count} anomalies"></div>
        <label>${label}</label>
      </div>`;
    })
    .join("");
}

async function syncData() {
  const pill = $("#live-api");
  const btn = $("#btn-live-refresh");
  if (btn) btn.disabled = true;
  try {
    const [health, report, trends] = await Promise.all([
      api("/health"),
      api("/api/v1/reports/latest").catch(() => null),
      api("/api/v1/fleet/trends?limit=8").catch(() => ({ trends: [] })),
    ]);

    pill.textContent = "Live";
    pill.dataset.state = "ok";

    if (!report) {
      $("#hero-summary").textContent = "No reports yet — run the sample pipeline from the Operations Dashboard.";
      return;
    }

    const rep = report.report || report;
    const vessels = rep.vessel_summaries || [];
    const anomalies = rep.anomalies || [];
    const escalations = rep.escalations || [];
    const score = computeScore(vessels, anomalies);

    animateCount($("#hero-score"), score);
    $("#hero-grade").textContent = scoreGrade(score);
    animateCount($("#hero-vessels"), vessels.length);
    animateCount($("#hero-anomalies"), report.anomalies_count ?? anomalies.length);
    animateCount($("#hero-escalations"), report.escalations_count ?? escalations.length);
    $("#hero-summary").textContent =
      report.executive_summary || rep.executive_summary || "Fleet report loaded.";

    renderRadar(vessels);
    renderVesselOrbs(vessels);
    renderAgentStream(report.agent_outputs || rep.raw_agent_outputs);
    renderPriorityQueue(anomalies, escalations);
    renderTrendBars(trends.trends || []);

    $("#last-sync").textContent = new Date().toLocaleTimeString();
  } catch {
    pill.textContent = "Offline";
    pill.dataset.state = "error";
    $("#hero-summary").textContent = "Could not reach API — ensure the server is running on port 8001.";
  } finally {
    if (btn) btn.disabled = false;
  }
}

function initClock() {
  const el = $("#live-clock");
  const tick = () => {
    if (el) el.textContent = new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  tick();
  setInterval(tick, 1000);
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY) || "dark";
  document.documentElement.dataset.theme = saved;
  const btn = $("#btn-live-theme");
  const update = (t) => {
    if (btn) btn.textContent = t === "light" ? "🌙" : "☀️";
  };
  update(saved);
  btn?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
    update(next);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initParticles();
  initClock();
  syncData();
  $("#btn-live-refresh")?.addEventListener("click", syncData);
  $("#btn-live-logout")?.addEventListener("click", async () => {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
    window.location.href = "/login";
  });
  setInterval(syncData, 60000);
});
