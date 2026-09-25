/* ============================================================
   Smart Market Analyst — Frontend
   ============================================================ */

const API = "";
const REFRESH_MS = 10000; // 10 ثوانٍ

// ============ Helpers ============
const stateClass = (state) => {
  if (!state) return "neutral";
  if (state.includes("BUY")) return "buy";
  if (state.includes("SELL")) return "sell";
  if (state === "WATCH") return "watch";
  return "neutral";
};

const scoreColor = (s) => {
  if (s >= 8) return "#0ECB81";
  if (s <= -8) return "#F6465D";
  if (s >= 3) return "#FCD535";
  return "#848E9C";
};

const fmtNum = (n, digits = 2) => {
  if (n === null || n === undefined) return "—";
  const num = Number(n);
  if (isNaN(num)) return "—";
  if (Math.abs(num) >= 1000) return num.toLocaleString("en-US", { maximumFractionDigits: digits });
  if (Math.abs(num) >= 1) return num.toFixed(digits);
  return num.toFixed(6);
};

const fmtMoney = (n) => {
  const num = Number(n) || 0;
  const sign = num >= 0 ? "" : "-";
  return `${sign}$${Math.abs(num).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const fmtTime = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return "—"; }
};

const fmtDateTime = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("ar-EG", {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return "—"; }
};

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function scoreRingSVG(score) {
  const pct = Math.min(Math.abs(score) / 25, 1);
  const r = 20;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct);
  const color = scoreColor(score);
  return `
    <svg width="52" height="52" viewBox="0 0 52 52">
      <circle cx="26" cy="26" r="${r}" stroke="#2B3139" stroke-width="4" fill="none"/>
      <circle cx="26" cy="26" r="${r}" stroke="${color}" stroke-width="4" fill="none"
        stroke-dasharray="${c}" stroke-dashoffset="${offset}" stroke-linecap="round"/>
    </svg>
    <span class="val" style="color:${color}">${score > 0 ? "+" : ""}${score}</span>`;
}

// ============ Overview: Cards ============
async function loadSnapshots() {
  try {
    const data = await fetchJSON(`${API}/api/snapshots`);
    renderCards(data);
  } catch (e) { console.error("snapshots:", e); }
}

function renderCards(rows) {
  const el = document.getElementById("cards");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد بيانات بعد — انتظر أول دورة تحليل</div>`;
    return;
  }

  el.innerHTML = rows.map(r => {
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
    const row = (k, v) =>
      `<div class="bd-row">
        <span class="k">${k}</span>
        <span class="v ${v > 0 ? "pos" : v < 0 ? "neg" : ""}">${v > 0 ? "+" : ""}${v}</span>
      </div>`;

    const regime = r.details?.regime?.regime;
    const regimeLabel = regime ? ` • ${regime}` : "";

    return `
      <div class="card ${cls}">
        <div class="card-header">
          <div>
            <div class="symbol">${r.symbol}</div>
            <div class="price">${fmtNum(r.price, 4)}</div>
            <div class="state-pill ${cls}">${r.state}</div>
          </div>
          <div class="score-ring">${scoreRingSVG(r.total_score)}</div>
        </div>
        <div class="breakdown">
          ${row("Trend", bd.trend)}
          ${row("Momentum", bd.momentum)}
          ${row("Volume", bd.volume)}
          ${row("Flow", bd.orderflow)}
          ${row("Structure", bd.structure)}
          ${row("Context", bd.context)}
        </div>
      </div>`;
  }).join("");
}

// ============ Recent Signals ============
async function loadRecentSignals() {
  try {
    const data = await fetchJSON(`${API}/api/signals?limit=20`);
    document.getElementById("recent-count").textContent = data.length;
    renderSignalsTable(data, "signals-table-recent");
  } catch (e) { console.error("signals:", e); }
}

async function loadAllSignals() {
  try {
    const data = await fetchJSON(`${API}/api/signals?limit=100`);
    renderSignalsTable(data, "signals-table");
  } catch (e) { console.error("signals:", e); }
}

function renderSignalsTable(rows, targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;

  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد إشارات</div>`;
    return;
  }

  el.innerHTML = `
    <table>
      <thead><tr>
        <th>الرمز</th>
        <th>الحالة</th>
        <th>النقاط</th>
        <th>السعر</th>
        <th>R:R</th>
        <th>النتيجة</th>
        <th>الوقت</th>
      </tr></thead>
      <tbody>
      ${rows.map(s => `
        <tr>
          <td>${s.symbol}</td>
          <td><span class="state-pill ${stateClass(s.state)}">${s.state}</span></td>
          <td class="num">${s.score > 0 ? "+" : ""}${s.score}</td>
          <td class="num">${fmtNum(s.price, 4)}</td>
          <td class="num">${s.rr || "—"}</td>
          <td>${s.outcome || "—"}</td>
          <td class="num">${fmtDateTime(s.timestamp)}</td>
        </tr>
      `).join("")}
      </tbody>
    </table>`;
}

// ============ Active Signals ============
async function loadActiveSignals() {
  try {
    const data = await fetchJSON(`${API}/api/active-signals`);
    document.getElementById("stat-active").textContent = data.length;
    document.getElementById("active-count").textContent = data.length;
    renderActiveSignals(data);
  } catch (e) { console.error("active:", e); }
}

function renderActiveSignals(rows) {
  const el = document.getElementById("active-signals");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد إشارات نشطة حالياً</div>`;
    return;
  }

  el.innerHTML = rows.map(s => {
    const dir = (s.direction || "long").toLowerCase();
    const initial = s.initial_score || 0;
    const current = s.current_score || 0;
    const progress = initial ? Math.min(100, Math.max(0, (current / Math.max(initial, 1)) * 100)) : 0;
    const delta = current - initial;
    const deltaStr = delta === 0 ? "—" : (delta > 0 ? `+${delta}` : `${delta}`);
    const deltaColor = delta > 0 ? "var(--green)" : delta < 0 ? "var(--red)" : "var(--text-dim)";

    return `
      <div class="signal-card ${dir}">
        <div class="signal-header">
          <div class="signal-header-left">
            <span class="signal-symbol">${s.symbol}</span>
            <span class="signal-direction ${dir}">${s.direction}</span>
            <span class="state-pill ${stateClass(s.state)}">${s.state}</span>
          </div>
          <span class="signal-time">${fmtDateTime(s.opened_at)}</span>
        </div>

        <div class="signal-metrics">
          <div class="metric">
            <div class="metric-label">السعر عند الإشارة</div>
            <div class="metric-value">${fmtNum(s.price_at_signal, 4)}</div>
          </div>
          <div class="metric">
            <div class="metric-label">النقاط</div>
            <div class="metric-value">
              ${initial} → ${current}
              <span style="color:${deltaColor};font-size:11px;">${deltaStr}</span>
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">R:R</div>
            <div class="metric-value">${s.rr || "—"}</div>
          </div>
        </div>

        <div class="progress-bar">
          <div class="progress-fill" style="width:${progress}%"></div>
        </div>

        <div class="levels-grid">
          <div class="level-box">
            <div class="level-label">دخول (أدنى)</div>
            <div class="level-value">${fmtNum(s.entry_low, 4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">دخول (أعلى)</div>
            <div class="level-value">${fmtNum(s.entry_high, 4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">وقف</div>
            <div class="level-value sl">${fmtNum(s.stop_loss, 4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">TP1</div>
            <div class="level-value tp">${fmtNum(s.tp1, 4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">TP2</div>
            <div class="level-value tp">${fmtNum(s.tp2, 4)}</div>
          </div>
          <div class="level-box">
            <div class="level-label">TP3</div>
            <div class="level-value tp">${fmtNum(s.tp3, 4)}</div>
          </div>
        </div>
      </div>`;
  }).join("");
}

// ============ Paper Trading ============
async function loadPaperStats() {
  try {
    const s = await fetchJSON(`${API}/api/paper/stats`);
    const el = document.getElementById("paper-stats");

    document.getElementById("stat-equity").textContent = fmtMoney(s.equity);
    document.getElementById("stat-winrate").textContent = (s.win_rate || 0) + "%";
    const pnlEl = document.getElementById("stat-pnl");
    pnlEl.textContent = fmtMoney(s.total_pnl);
    pnlEl.className = "stat-value " + (s.total_pnl > 0 ? "pos" : s.total_pnl < 0 ? "neg" : "");

    el.innerHTML = `
      <div class="paper-stat">
        <div class="paper-stat-label">رأس المال الحالي</div>
        <div class="paper-stat-value">${fmtMoney(s.equity)}</div>
      </div>
      <div class="paper-stat">
        <div class="paper-stat-label">صافي الربح</div>
        <div class="paper-stat-value" style="color:${s.total_pnl >= 0 ? "var(--green)" : "var(--red)"}">
          ${s.total_pnl >= 0 ? "+" : ""}${fmtMoney(s.total_pnl)}
        </div>
      </div>
      <div class="paper-stat">
        <div class="paper-stat-label">النسبة %</div>
        <div class="paper-stat-value" style="color:${s.total_pnl_pct >= 0 ? "var(--green)" : "var(--red)"}">
          ${s.total_pnl_pct >= 0 ? "+" : ""}${s.total_pnl_pct}%
        </div>
      </div>
      <div class="paper-stat">
        <div class="paper-stat-label">نسبة الربح</div>
        <div class="paper-stat-value">${s.win_rate}%</div>
      </div>
      <div class="paper-stat">
        <div class="paper-stat-label">ربح/خسارة</div>
        <div class="paper-stat-value">${s.wins}/${s.losses}</div>
      </div>
      <div class="paper-stat">
        <div class="paper-stat-label">Profit Factor</div>
        <div class="paper-stat-value">${s.profit_factor || "—"}</div>
      </div>
      <div class="paper-stat">
        <div class="paper-stat-label">عدد الصفقات</div>
        <div class="paper-stat-value">${s.total_trades}</div>
      </div>
      <div class="paper-stat">
        <div class="paper-stat-label">مفتوحة</div>
        <div class="paper-stat-value">${s.open_trades}</div>
      </div>
    `;
  } catch (e) { console.error("paper stats:", e); }
}

async function loadPaperTrades() {
  try {
    const open = await fetchJSON(`${API}/api/paper/trades?status=open&limit=50`);
    const closed = await fetchJSON(`${API}/api/paper/trades?limit=50`).then(d =>
      d.filter(t => t.status !== "open")
    );

    document.getElementById("open-count").textContent = open.length;
    document.getElementById("closed-count").textContent = closed.length;

    renderPaperOpen(open);
    renderPaperClosed(closed);
  } catch (e) { console.error("paper trades:", e); }
}

function renderPaperOpen(rows) {
  const el = document.getElementById("paper-open");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد صفقات مفتوحة</div>`;
    return;
  }

  el.innerHTML = `
    <table>
      <thead><tr>
        <th>الرمز</th>
        <th>الاتجاه</th>
        <th>الدخول</th>
        <th>الوقف</th>
        <th>TP1</th>
        <th>الحجم</th>
        <th>النقاط</th>
        <th>مفتوحة منذ</th>
      </tr></thead>
      <tbody>
      ${rows.map(t => `
        <tr>
          <td>${t.symbol}</td>
          <td><span class="state-pill ${t.direction === "LONG" ? "buy" : "sell"}">${t.direction}</span></td>
          <td class="num">${fmtNum(t.entry_price, 4)}</td>
          <td class="num neg">${fmtNum(t.stop_loss, 4)}</td>
          <td class="num pos">${fmtNum(t.tp1, 4)}</td>
          <td class="num">${fmtNum(t.size, 4)}</td>
          <td class="num">${t.signal_score || "—"}</td>
          <td class="num">${fmtDateTime(t.opened_at)}</td>
        </tr>
      `).join("")}
      </tbody>
    </table>`;
}

function renderPaperClosed(rows) {
  const el = document.getElementById("paper-closed");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد صفقات مُغلقة</div>`;
    return;
  }

  el.innerHTML = `
    <table>
      <thead><tr>
        <th>الرمز</th>
        <th>الاتجاه</th>
        <th>الدخول</th>
        <th>الخروج</th>
        <th>النتيجة</th>
        <th>PnL</th>
        <th>أُغلقت في</th>
      </tr></thead>
      <tbody>
      ${rows.map(t => {
        const pnl = t.pnl || 0;
        const pnlCls = pnl > 0 ? "pos" : pnl < 0 ? "neg" : "";
        return `
          <tr>
            <td>${t.symbol}</td>
            <td><span class="state-pill ${t.direction === "LONG" ? "buy" : "sell"}">${t.direction}</span></td>
            <td class="num">${fmtNum(t.entry_price, 4)}</td>
            <td class="num">${fmtNum(t.exit_price, 4)}</td>
            <td>${t.status}</td>
            <td class="num ${pnlCls}">${pnl >= 0 ? "+" : ""}${fmtMoney(pnl)}</td>
            <td class="num">${fmtDateTime(t.closed_at)}</td>
          </tr>
        `;
      }).join("")}
      </tbody>
    </table>`;
}

// ============ Anomalies ============
async function loadAnomalies() {
  try {
    const data = await fetchJSON(`${API}/api/anomalies?limit=30`);
    const hourAgo = Date.now() - 3600 * 1000;
    const recent = data.filter(a => new Date(a.created_at).getTime() > hourAgo);
    document.getElementById("stat-anomalies").textContent = recent.length;
    renderAnomalies(data);
  } catch (e) { console.error("anomalies:", e); }
}

function renderAnomalies(rows) {
  const el = document.getElementById("anomalies-list");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد أحداث شاذة</div>`;
    return;
  }

  el.innerHTML = rows.map(a => `
    <div class="anomaly-item">
      <div class="anomaly-sev ${a.severity}"></div>
      <div class="anomaly-body">
        <div class="anomaly-title">${a.symbol} — ${a.type}</div>
        <div class="anomaly-details">${JSON.stringify(a.details)}</div>
      </div>
      <div class="event-time">${fmtTime(a.created_at)}</div>
    </div>
  `).join("");
}

// ============ Events ============
const EVENT_LABELS = {
  opened: "🆕 فتح إشارة",
  strengthened: "🚀 تقوّت",
  weakened: "📉 ضعف",
  stable: "➖ مستقر",
  tp1_hit: "🎯 TP1 تحقق",
  tp2_hit: "🎯 TP2 تحقق",
  tp3_hit: "🏆 TP3 تحقق",
  sl_hit: "🛑 وقف الخسارة",
  invalidated: "❌ إلغاء",
};

async function loadEvents() {
  try {
    const data = await fetchJSON(`${API}/api/signal-events?limit=50`);
    renderEvents(data);
  } catch (e) { console.error("events:", e); }
}

function renderEvents(rows) {
  const el = document.getElementById("events-list");
  if (!rows.length) {
    el.innerHTML = `<div class="empty">لا توجد أحداث</div>`;
    return;
  }

  el.innerHTML = rows.map(e => {
    const label = EVENT_LABELS[e.event_type] || e.event_type;
    const icon = label.charAt(0);
    const scoreStr = (e.old_score !== null && e.new_score !== null)
      ? ` • النقاط: ${e.old_score} → ${e.new_score}` : "";
    const stateStr = (e.old_state && e.new_state && e.old_state !== e.new_state)
      ? ` • ${e.old_state} → ${e.new_state}` : "";
    const priceStr = e.price ? ` • السعر: ${fmtNum(e.price, 4)}` : "";

    return `
      <div class="event-item">
        <div class="event-icon ${e.event_type}">${icon}</div>
        <div class="event-body">
          <div class="event-title">${label} — ${e.symbol}</div>
          <div class="event-meta">${scoreStr}${stateStr}${priceStr}</div>
        </div>
        <div class="event-time">${fmtTime(e.created_at)}</div>
      </div>`;
  }).join("");
}

// ============ Regime (stat) ============
async function loadRegime() {
  try {
    const data = await fetchJSON(`${API}/api/regime`);
    const el = document.getElementById("stat-regime");
    const counts = {};
    Object.values(data).forEach(r => {
      const k = r.regime || "unknown";
      counts[k] = (counts[k] || 0) + 1;
    });
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    el.textContent = top ? `${top[0]} (${top[1]})` : "—";
  } catch (e) { console.error("regime:", e); }
}

// ============ Backtest ============
async function runBacktest() {
  const symbol = document.getElementById("bt-symbol").value;
  const timeframe = document.getElementById("bt-timeframe").value;
  const btn = document.getElementById("btn-backtest");
  const el = document.getElementById("backtest-results");

  btn.disabled = true;
  btn.textContent = "⏳ جاري...";
  el.innerHTML = `<div class="empty">جارٍ تشغيل الاختبار على ${symbol} (${timeframe})...</div>`;

  try {
    const url = `${API}/api/backtest/${encodeURIComponent(symbol)}?timeframe=${timeframe}&lookback=200`;
    const data = await fetchJSON(url, { method: "POST" });

    if (data.error) {
      el.innerHTML = `<div class="empty">${data.error}</div>`;
      return;
    }
    renderBacktest(data, symbol, timeframe);
  } catch (e) {
    el.innerHTML = `<div class="empty">خطأ: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ تشغيل الاختبار";
  }
}

function renderBacktest(data, symbol, timeframe) {
  const s = data.stats || {};
  const el = document.getElementById("backtest-results");

  el.innerHTML = `
    <div style="margin-bottom:14px;font-size:13px;color:var(--text-dim)">
      النتائج لـ <b style="color:var(--text)">${symbol}</b> على إطار <b style="color:var(--text)">${timeframe}</b>
    </div>
    <div class="bt-stats-grid">
      <div class="bt-stat">
        <div class="bt-stat-label">إجمالي الصفقات</div>
        <div class="bt-stat-value">${s.total || 0}</div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">نسبة الربح</div>
        <div class="bt-stat-value" style="color:${(s.win_rate || 0) >= 50 ? "var(--green)" : "var(--red)"}">${s.win_rate || 0}%</div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">رابحة</div>
        <div class="bt-stat-value" style="color:var(--green)">${s.wins || 0}</div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">خاسرة</div>
        <div class="bt-stat-value" style="color:var(--red)">${s.losses || 0}</div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">متوسط العائد</div>
        <div class="bt-stat-value" style="color:${(s.avg_return || 0) >= 0 ? "var(--green)" : "var(--red)"}">
          ${s.avg_return || 0}%
        </div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">إجمالي العائد</div>
        <div class="bt-stat-value" style="color:${(s.total_return || 0) >= 0 ? "var(--green)" : "var(--red)"}">
          ${s.total_return || 0}%
        </div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">TP1</div>
        <div class="bt-stat-value">${s.tp1_hits || 0}</div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">TP2</div>
        <div class="bt-stat-value">${s.tp2_hits || 0}</div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">Stop Loss</div>
        <div class="bt-stat-value">${s.sl_hits || 0}</div>
      </div>
      <div class="bt-stat">
        <div class="bt-stat-label">Expired</div>
        <div class="bt-stat-value">${s.expired || 0}</div>
      </div>
    </div>
  `;
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
    btn.textContent = "⟳ فحص الآن";
  }
}

function updateTimestamp() {
  const el = document.getElementById("last-update");
  el.textContent = new Date().toLocaleTimeString("ar-EG");
}

async function refreshAll() {
  await Promise.all([
    loadSnapshots(),
    loadRecentSignals(),
    loadAllSignals(),
    loadActiveSignals(),
    loadPaperStats(),
    loadPaperTrades(),
    loadAnomalies(),
    loadEvents(),
    loadRegime(),
  ]);
  updateTimestamp();
}

// ============ Tabs ============
function initTabs() {
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.dataset.tab;
      const el = document.getElementById(`tab-${target}`);
      if (el) el.classList.add("active");
    });
  });
}

// ============ Init ============
document.addEventListener("DOMContentLoaded", () => {
  initTabs();

  const btnScan = document.getElementById("btn-scan");
  if (btnScan) btnScan.addEventListener("click", triggerScan);

  const btnBacktest = document.getElementById("btn-backtest");
  if (btnBacktest) btnBacktest.addEventListener("click", runBacktest);

  refreshAll();
  setInterval(refreshAll, REFRESH_MS);
});
