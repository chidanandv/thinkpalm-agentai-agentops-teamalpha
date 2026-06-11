/**
 * Fleet Health — Login page
 */

const THEME_KEY = "fleet-health-theme";

function initTheme() {
  const theme = localStorage.getItem(THEME_KEY) || "dark";
  document.documentElement.dataset.theme = theme;
}

function initParticles() {
  const canvas = document.getElementById("login-particles");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let w, h, dots;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
    const n = Math.min(45, Math.floor((w * h) / 22000));
    dots = Array.from({ length: n }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.2 + 0.4,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      a: Math.random() * 0.35 + 0.1,
    }));
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--login-accent").trim() || "#2dd4bf";
    dots.forEach((p) => {
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
  draw();
  window.addEventListener("resize", resize);
}

async function checkAlreadyLoggedIn() {
  try {
    const res = await fetch("/api/v1/auth/me", { credentials: "include" });
    if (!res.ok) return;
    const data = await res.json();
    if (data.authenticated && data.username && data.username !== "guest") {
      window.location.href = "/";
    }
  } catch {
    /* stay on login */
  }
}

function setLoading(on) {
  const btn = document.getElementById("login-btn");
  const spinner = btn?.querySelector(".login-spinner");
  const label = btn?.querySelector(".login-btn-label");
  if (btn) btn.disabled = on;
  if (spinner) spinner.hidden = !on;
  if (label) label.textContent = on ? "Signing in…" : "Sign in";
}

function showError(msg) {
  const el = document.getElementById("login-error");
  if (!el) return;
  el.textContent = msg;
  el.hidden = !msg;
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initParticles();
  checkAlreadyLoggedIn();

  document.getElementById("login-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    setLoading(true);

    const username = document.getElementById("username")?.value?.trim();
    const password = document.getElementById("password")?.value ?? "";

    if (!username || !password) {
      showError("Enter both username and password");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showError(typeof data.detail === "string" ? data.detail : "Invalid username or password");
        return;
      }
      window.location.href = data.redirect || "/";
    } catch {
      showError("Could not reach server. Is it running on port 8001?");
    } finally {
      setLoading(false);
    }
  });
});
