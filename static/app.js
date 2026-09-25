const API = "";
let chartInstances = {};

const stateClass = (state) => {
  if (!state) return "neutral";
  if (state.includes("BUY")) return "buy";
  if (state.includes("SELL")) return "sell";
  if (state === "WATCH") return "watch";
  return "neutral";
};

const scoreColor = (score) => {
  if (score >= 8) return "#26a69a";
  if (score <= -8) return "#ef5350";
  if (score >= 3) return "#f0b90b";
  return "#787b86";
};

function scoreRingSVG(score) {
  const max = 100;
  const pct = Math.min(Math.abs(score) / max, 1);
  const r = 26;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct);
  const color = scoreColor(score);
  return `
    <svg width="60" height="60">
      <circle cx="30" cy="30" r="${r}" stroke="#232838" stroke-width="5" fill="none"/>
      <circle cx="30" cy="30" r="${r}" stroke="${color}" stroke-width="5" fill="none"
        stroke-dasharray="${c}" stroke-dashoffset="${offset}"
        stroke-linecap="round"/>
    </svg>
    <span class="val" style="color:${color}">${score}</span>
  `;
}

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function loadSnapshots() {
  try {
    const data = await fetchJSON(`${API}/api/snapshots`);
    renderCards(data);
  } catch (e) { console.error(e); }
}

function renderCards(rows) {
  const container = document.getElementById("cards");
  if (!rows.length) {
    container.innerHTML = `<p style="color:var(--text-dim)">لا توجد بيانات بعد...</p>`;
    return;
  }

  container.innerHTML = rows.map(r => {
    const cls = stateClass(r.state);
    const bd = {
      trend: r.trend_score || 0,
      momentum: r.momentum_score || 0,
      volume: r.volume_score || 0,
      orderflow: r.orderflow_score || 0,
      structure: r.structure_score || 0,
      context: r.context_score || 0,
      risk: r.risk_score || 0,
    };
    const bdRow = (k, v) =>
      `<div class="bd-row"><span class="k">${k}</span>
       <span class="v ${v > 0 ? "pos" : v < 0 ? "neg" : ""}">${v > 0 ? "+" : ""}${v}</span></div>`;

    return `
      <div class="card ${cls}">
        <div class="card-header">
          <div>
            <div class="symbol">${r.symbol}</div>
            <div class="price">${Number(r.price).toLocaleString()}</div>
            <div class="state-pill ${cls}">${r.state}</div>
          </div>
          <div class="score-ring">${scoreRingSVG(r.total_score)}</div>
        </div>
        <div class="breakdown">
          ${bdRow("Trend", bd.trend)}
          ${bdRow("Momentum", bd.momentum)}
          ${bdRow("Volume", bd.volume)}
          ${bdRow("Flow", bd.orderflow)}
          ${bdRow("Structure", bd.structure)}
          ${bdRow("Context", bd.context)}
          ${bdRow("Risk", bd.risk)}
        </div>
      </div>
    `;
  }).join("");
}

async function loadSignals() {
  try {
    const data = await fetchJSON(`${API}/api/signals?limit=30`);
    renderSignals(data);
  } catch (e) { console.error(e); }
}

function renderSignals(rows) {
  const el = document.getElementById("signals-table");
  if (!rows.length) {
    el.innerHTML = `<p style="color:var(--text-dim)">لا توجد إشارات بعد...</p>`;
    return;
  }
  el.innerHTML = `
    <table>
      <thead><tr>
        <th>الرمز</th><th>الحالة</th><th>النقاط</th>
        <th>السعر</th><th>R:R</th><th>الوقت</th>
      </tr></thead>
      <tbody>
      ${rows.map(s => `
        <tr>
          <td>${s.symbol}</td>
          <td><span class="state-pill ${stateClass(s.state)}">${s.state}</span></td>
          <td>${s.score}</td>
          <td>${Number(s.price).toLocaleString()}</td>
          <td>${s.rr ?? "—"}</td>
          <td>${new Date(s.timestamp).toLocaleString("ar-EG")}</td>
        </tr>
      `).join("")}
      </tbody>
    </table>
  `;
}

async function triggerScan() {
  const btn = document.getElementById("btn-scan");
  btn.disabled = true;
  btn.textContent = "⏳ جاري الفحص...";
  try {
    await fetchJSON(`${API}/api/scan`, { method: "POST" });
    await Promise.all([loadSnapshots(), loadSignals()]);
  } catch (e) {
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = "🔍 فحص الآن";
  }
}

function updateTimestamp() {
  document.getElementById("last-update").textContent =
    "آخر تحديث: " + new Date().toLocaleTimeString("ar-EG");
}

async function refresh() {
  await Promise.all([loadSnapshots(), loadSignals()]);
  updateTimestamp();
}

document.getElementById("btn-scan").addEventListener("click", triggerScan);

refresh();
setInterval(refresh, 30000);
