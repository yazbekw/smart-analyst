const API = "";
let currentTab = "overview";

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
  const pct = Math.min(Math.abs(score) / 100, 1);
  const r = 26, c = 2 * Math.PI * r;
  const offset = c * (1 - pct);
  const color = scoreColor(score);
  return `
    <svg width="60" height="60">
      <circle cx="30" cy="30" r="${r}" stroke="#232838" stroke-width="5" fill="none"/>
      <circle cx="30" cy="30" r="${r}" stroke="${color}" stroke-width="5" fill="none"
        stroke-dasharray="${c}" stroke-dashoffset="${offset}" stroke-linecap="round"/>
    </svg>
    <span class="val" style="color:${color}">${score}</span>`;
}

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ============ Overview ============
async function loadSnapshots() {
  try {
    const data = await fetchJSON(`${API}/api/snapshots`);
    renderCards(data);
  } catch (e) { console.error(e); }
}

function renderCards(rows) {
  const container = document.getElementById("cards");
  if (!rows.length) {
    container.innerHTML = `<div class="empty">لا توجد بيانات بعد...</div>`;
    return;
  }
  container.innerHTML = rows.map(r => {
    const cls = stateClass(r.state);
    const bd = {
      trend: r.trend_score || 0, momentum: r.momentum_score || 0,
      volume: r.volume_score || 0, orderflow: r.orderflow_score || 0,
      structure: r.structure_score || 0, context: r.context_score || 0,
      risk: r.risk_score || 0,
    };
    const row = (k, v) =>
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
          ${row("Trend", bd.trend)}${row("Momentum", bd.momentum)}
          ${row("Volume", bd.volume)}${row("Flow", bd.orderflow)}
          ${row("Structure", bd.structure)}${row("Context", bd.context)}
          ${row("Risk", bd.risk)}
        </div>
      </div>`;
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
    el.innerHTML = `<div class="empty">لا توجد إشارات بعد...</div>`;
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
        </tr>`).join("")}
      </tbody>
    </table>`;
}

// ============ Active Signals ============
async function loadActiveSignals() {
  try {
    const data = await fetchJSON(`${API}/api/active-signals`);
    renderActiveSignals(data);
    document.getElementById("stat-active").textContent = data.length;
  } catch (e) { console.error(e); }
}

function renderActiveSignals(rows) {
  const el = document.getElementById("active-signals");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد إشارات نشطة حالياً</div>`;
    return;
  }
  el.innerHTML = rows.map(s => {
    const dir = s.direction.toLowerCase();
    const progress = s.initial_score ? 
      Math.min(100, Math.max(0, (s.current_score / s.initial_score) * 100)) : 0;
    const scoreDelta = s.current_score - s.initial_score;
    const deltaStr = scoreDelta === 0 ? "—" :
      `${scoreDelta > 0 ? "+" : ""}${scoreDelta}`;

    return `
      <div class="signal-card ${dir}">
        <div class="signal-header">
          <div style="display:flex;align-items:center;gap:10px;">
            <span class="signal-symbol">${s.symbol}</span>
            <span class="signal-direction ${dir}">${s.direction}</span>
            <span class="state-pill ${stateClass(s.state)}">${s.state}</span>
          </div>
          <div style="color:var(--text-dim);font-size:12px;">
            ${new Date(s.opened_at).toLocaleString("ar-EG")}
          </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <div style="color:var(--text-dim);font-size:12px;">السعر عند الإشارة</div>
            <div style="font-weight:700;font-size:16px;">${Number(s.price_at_signal).toLocaleString()}</div>
          </div>
          <div style="text-align:center;">
            <div style="color:var(--text-dim);font-size:12px;">النقاط</div>
            <div style="font-weight:700;font-size:16px;">
              ${s.initial_score} → ${s.current_score}
              <span style="color:${scoreDelta >= 0 ? 'var(--green)' : 'var(--red)'};font-size:13px;margin-right:6px;">${deltaStr}</span>
            </div>
          </div>
          <div style="text-align:center;">
            <div style="color:var(--text-dim);font-size:12px;">R:R</div>
            <div style="font-weight:700;font-size:16px;">${s.rr ?? "—"}</div>
          </div>
        </div>

        <div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>

        <div class="levels-grid">
          <div class="level-box">
            <div class="level-label">دخول</div>
            <div class="level-value">${Number(s.entry_low).toFixed(4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">دخول</div>
            <div class="level-value">${Number(s.entry_high).toFixed(4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">وقف</div>
            <div class="level-value sl">${Number(s.stop_loss).toFixed(4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">TP1</div>
            <div class="level-value tp">${Number(s.tp1).toFixed(4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">TP2</div>
            <div class="level-value tp">${Number(s.tp2).toFixed(4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">TP3</div>
            <div class="level-value tp">${Number(s.tp3).toFixed(4)}</div>
          </div>
        </div>

        ${s.last_reasons?.length ? `
          <details style="margin-top:12px;">
            <summary style="cursor:pointer;color:var(--text-dim);font-size:13px;">الأسباب (${s.last_reasons.length})</summary>
            <ul style="margin-top:8px;padding-right:20px;font-size:12px;line-height:1.8;">
              ${s.last_reasons.map(r => `<li>${r}</li>`).join("")}
            </ul>
          </details>` : ""}
      </div>`;
  }).join("");
}

// ============ Events ============
async function loadEvents() {
  try {
    const data = await fetchJSON(`${API}/api/signal-events?limit=50`);
    renderEvents(data);
  } catch (e) { console.error(e); }
}

const eventLabels = {
  opened: "🆕 فتح إشارة", strengthened: "🚀 تقوّت", weakened: "📉 ضعف",
  stable: "➖ مستقر", tp1_hit: "🎯 TP1", tp2_hit: "🎯 TP2", tp3_hit: "🏆 TP3",
  sl_hit: "🛑 وقف الخسارة", invalidated: "❌ إلغاء",
};

function renderEvents(rows) {
  const el = document.getElementById("events-list");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد أحداث بعد...</div>`;
    return;
  }
  el.innerHTML = rows.map(e => `
    <div class="event-item">
      <div class="event-icon ${e.event_type}">${(eventLabels[e.event_type] || "•")[0]}</div>
      <div class="event-body">
        <div class="event-title">${eventLabels[e.event_type] || e.event_type} — ${e.symbol}</div>
        <div class="event-meta">
          ${e.old_score !== null && e.new_score !== null ?
            `النقاط: ${e.old_score} → ${e.new_score}` : ""}
          ${e.old_state && e.new_state && e.old_state !== e.new_state ?
            ` • ${e.old_state} → ${e.new_state}` : ""}
          ${e.price ? ` • السعر: ${Number(e.price).toLocaleString()}` : ""}
        </div>
      </div>
      <div class="event-time">${new Date(e.created_at).toLocaleTimeString("ar-EG")}</div>
    </div>`).join("");
}

// ============ Anomalies ============
async function loadAnomalies() {
  try {
    const data = await fetchJSON(`${API}/api/anomalies?limit=30`);
    renderAnomalies(data);
    const hourAgo = Date.now() - 3600 * 1000;
    const recent = data.filter(a => new Date(a.created_at).getTime() > hourAgo);
    document.getElementById("stat-anomalies").textContent = recent.length;
  } catch (e) { console.error(e); }
}

function renderAnomalies(rows) {
  const el = document.getElementById("anomalies-list");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد أحداث شاذة</div>`;
    return;
  }
  el.innerHTML = rows.map(a => `
    <div class="anomaly-item">
      <div class="anomaly-severity ${a.severity}"></div>
      <div style="flex:1;">
        <div style="font-weight:600;font-size:13px;">${a.type} — ${a.symbol}</div>
        <div style="color:var(--text-dim);font-size:12px;margin-top:4px;">
          ${JSON.stringify(a.details)}
        </div>
      </div>
      <div class="event-time">${new Date(a.created_at).toLocaleTimeString("ar-EG")}</div>
    </div>`).join("");
}

// ============ Controls ============
async function triggerScan() {
  const btn = document.getElementById("btn-scan");
  btn.disabled = true;
  btn.textContent = "⏳ جاري الفحص...";
  try {
    await fetchJSON(`${API}/api/scan`, { method: "POST" });
    await refreshAll();
  } catch (e) { console.error(e); }
  finally {
    btn.disabled = false;
    btn.textContent = "🔍 فحص الآن";
  }
}

function updateTimestamp() {
  document.getElementById("last-update").textContent =
    "آخر تحديث: " + new Date().toLocaleTimeString("ar-EG");
}

async function refreshAll() {
  await Promise.all([
    loadSnapshots(), loadSignals(),
    loadActiveSignals(), loadEvents(), loadAnomalies(),
  ]);
  updateTimestamp();
  document.getElementById("stat-last-scan").textContent =
    new Date().toLocaleTimeString("ar-EG");
}

// ============ Tabs ============
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    tab.classList.add("active");
    const target = tab.dataset.tab;
    document.getElementById(`tab-${target}`).classList.add("active");
    currentTab = target;
  });
});

document.getElementById("btn-scan").addEventListener("click", triggerScan);

refreshAll();
setInterval(refreshAll, 30000);
