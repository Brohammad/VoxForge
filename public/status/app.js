(() => {
  const HEALTH_URL = "/api/v1/health";
  const READY_URL = "/api/v1/ready";
  const REFRESH_MS = 30_000;

  const overallEl = document.getElementById("overall");
  const checkedAtEl = document.getElementById("checked-at");
  const healthHttpEl = document.getElementById("health-http");
  const healthStatusEl = document.getElementById("health-status");
  const healthBodyEl = document.getElementById("health-body");
  const readyHttpEl = document.getElementById("ready-http");
  const readyStatusEl = document.getElementById("ready-status");
  const readyBodyEl = document.getElementById("ready-body");
  const readyChecksEl = document.getElementById("ready-checks");
  const refreshBtn = document.getElementById("refresh");

  function setPill(el, value) {
    const normalized = String(value || "unknown").toLowerCase();
    el.textContent = normalized;
    el.className = "pill";
    if (normalized === "ok") el.classList.add("ok");
    else if (normalized === "degraded") el.classList.add("degraded");
    else if (normalized === "unavailable" || normalized === "error") el.classList.add("unavailable");
    else el.classList.add("unknown");
  }

  function toneForCheck(value) {
    const v = String(value || "").toLowerCase();
    if (v === "ok" || v === "disabled" || v === "configured") return "ok";
    if (v.startsWith("error") || v === "unavailable") return "bad";
    return "warn";
  }

  function renderChecks(payload) {
    readyChecksEl.innerHTML = "";
    const skip = new Set(["status"]);
    Object.entries(payload || {}).forEach(([key, value]) => {
      if (skip.has(key)) return;
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = key;
      const val = document.createElement("strong");
      val.className = `pill ${toneForCheck(value)}`;
      val.textContent = String(value);
      li.append(name, val);
      readyChecksEl.appendChild(li);
    });
  }

  async function fetchJson(url) {
    const started = performance.now();
    try {
      const res = await fetch(url, { cache: "no-store" });
      const text = await res.text();
      let body = {};
      try {
        body = text ? JSON.parse(text) : {};
      } catch {
        body = { raw: text };
      }
      return {
        ok: res.ok,
        status: res.status,
        body,
        ms: Math.round(performance.now() - started),
        error: null,
      };
    } catch (err) {
      return {
        ok: false,
        status: 0,
        body: { error: String(err && err.message ? err.message : err) },
        ms: Math.round(performance.now() - started),
        error: err,
      };
    }
  }

  function computeOverall(health, ready) {
    if (!health.ok || health.status !== 200) return "unavailable";
    if (!ready.ok && ready.status === 0) return "unavailable";
    const readyStatus = String(ready.body.status || "").toLowerCase();
    if (ready.status === 503 || readyStatus === "unavailable") return "unavailable";
    if (readyStatus === "degraded") return "degraded";
    if (!ready.ok) return "unavailable";
    return "ok";
  }

  async function refresh() {
    setPill(overallEl, "unknown");
    overallEl.textContent = "checking…";

    const [health, ready] = await Promise.all([fetchJson(HEALTH_URL), fetchJson(READY_URL)]);

    healthHttpEl.textContent = health.status ? `${health.status} (${health.ms}ms)` : `error (${health.ms}ms)`;
    setPill(healthStatusEl, health.body.status || (health.ok ? "ok" : "error"));
    healthBodyEl.textContent = JSON.stringify(health.body, null, 2);

    readyHttpEl.textContent = ready.status ? `${ready.status} (${ready.ms}ms)` : `error (${ready.ms}ms)`;
    setPill(readyStatusEl, ready.body.status || (ready.ok ? "ok" : "error"));
    readyBodyEl.textContent = JSON.stringify(ready.body, null, 2);
    renderChecks(ready.body);

    setPill(overallEl, computeOverall(health, ready));
    checkedAtEl.textContent = new Date().toLocaleString();
  }

  refreshBtn.addEventListener("click", () => {
    refresh();
  });

  refresh();
  setInterval(refresh, REFRESH_MS);
})();
