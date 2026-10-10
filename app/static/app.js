const $ = (selector) => document.querySelector(selector);
const DEMO_MINT = "So11111111111111111111111111111111111111112";
let runtimeConfig = null;

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#039;",'"':"&quot;"}[char]));
}
function shortAddress(value) { return value ? `${value.slice(0, 5)}…${value.slice(-5)}` : "—"; }
function formatUsd(value, compact = false) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const number = Number(value);
  if (compact && Math.abs(number) >= 1_000_000) return `$${(number / 1_000_000).toFixed(2)}m`;
  if (compact && Math.abs(number) >= 1_000) return `$${(number / 1_000).toFixed(1)}k`;
  if (number < 0.01 && number > 0) return `$${number.toFixed(6)}`;
  return new Intl.NumberFormat("en-US", { style:"currency", currency:"USD", maximumFractionDigits: number < 1 ? 5 : 2 }).format(number);
}
function formatDate(timestamp) {
  if (!timestamp) return "—";
  return new Intl.DateTimeFormat("id-ID", { dateStyle:"medium", hour:"2-digit", minute:"2-digit" }).format(new Date(timestamp * 1000));
}
function relativeDate(timestamp) {
  if (!timestamp) return "—";
  const hours = Math.max(0, Math.round((Date.now() / 1000 - timestamp) / 3600));
  if (hours < 24) return `${hours} jam lalu`;
  return `${Math.round(hours / 24)} hari lalu`;
}
function addressHtml(address, live = false) {
  if (!address) return "—";
  const text = escapeHtml(shortAddress(address));
  return live ? `<a class="addr-link address" target="_blank" rel="noreferrer" href="https://solscan.io/account/${encodeURIComponent(address)}">${text} ↗</a>` : `<span class="address">${text}</span>`;
}
function stateLabel(record) {
  if (!record.active) return `<span class="status inactive">Dormant</span>`;
  if (record.bot?.label === "likely_bot") return `<span class="status bot">Likely bot</span>`;
  if (record.bot?.label === "review") return `<span class="status review">Review</span>`;
  return `<span class="status human">Human-like</span>`;
}
function setError(text = "") {
  const target = $("#formError");
  target.textContent = text;
  target.classList.toggle("visible", Boolean(text));
}

async function loadConfig() {
  try {
    runtimeConfig = await fetch("/api/config").then((response) => response.json());
    const liveState = runtimeConfig.live_ready ? "siap" : "butuh API key";
    $("#configHint").innerHTML = `Live mode: <strong>${liveState}</strong>. Demo tidak perlu API key. Paper tracking tidak pernah mengeksekusi trade.`;
    $("#modeBadge").textContent = runtimeConfig.demo_default ? "Default: Demo" : "Default: Live";
    $("#modeBadge").classList.remove("neutral");
    $("#modeSelect").value = runtimeConfig.demo_default ? "demo" : "live";
    if (!runtimeConfig.live_ready) {
      $("#modeSelect").value = "demo";
    }
  } catch (_) {
    $("#configHint").textContent = "Status API tidak dapat dimuat; cek apakah server berjalan.";
  }
}

function renderMetrics(summary) {
  const cells = [
    [summary.early_buyers_found, "Pembeli awal", "DEX buy unik"],
    [summary.active_wallets, "Aktif", "swap dalam 30 hari"],
    [summary.human_like_wallets, "Dipantau", "bukan likely bot"],
    [summary.likely_bots, "Bot-like", "dikeluarkan dari sinyal"],
    [summary.eligible_paper_signals, "Paper signal", "lolos hard gate"],
  ];
  $("#metrics").innerHTML = cells.map(([value, label, note]) => `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></div>`).join("");
}

function renderBuyers(rows, live) {
  $("#buyersTable").innerHTML = rows.map((row) => `
    <tr>
      <td>${row.rank}</td>
      <td>${addressHtml(row.wallet, live)}</td>
      <td><span title="${escapeHtml(formatDate(row.first_buy_at))}">${relativeDate(row.first_buy_at)}</span><br><span class="muted">${formatUsd(row.first_buy_usd)}</span></td>
      <td>${row.active ? '<span class="status active">Aktif</span>' : '<span class="status inactive">Tidak</span>'}</td>
      <td>${stateLabel(row)} <span class="muted">${row.bot?.score ?? 0}/100</span></td>
    </tr>`).join("");
  $("#buyersSource").textContent = rows[0]?.source || "—";
}

function renderCohort(rows, live) {
  const shown = [...rows].sort((a,b) => Number(b.active) - Number(a.active) || (a.bot?.score ?? 0) - (b.bot?.score ?? 0));
  $("#cohortCount").textContent = `${shown.filter((row) => row.active && row.bot?.label !== "likely_bot").length} dipilih`;
  $("#cohortList").innerHTML = shown.map((row) => {
    const type = !row.active ? "bad" : row.bot?.label === "likely_bot" ? "bad" : row.bot?.label === "review" ? "wait" : "good";
    const label = !row.active ? "dormant" : row.bot?.label === "likely_bot" ? "dikecualikan" : "dipantau";
    const reason = row.bot?.reasons?.[0] || "—";
    return `<div class="cohort-item"><div><div class="cohort-top">${addressHtml(row.wallet, live)} <span class="micro-pill ${type}">${label}</span></div><div class="cohort-detail">Terakhir ${relativeDate(row.last_seen)} · bot ${row.bot?.score ?? 0}/100 · ${escapeHtml(reason)}</div></div><div class="status">Q${row.quality_proxy ?? 0}</div></div>`;
  }).join("");
}

function renderSignals(signals, live) {
  if (!signals.length) {
    $("#signals").innerHTML = `<div class="no-signals">Tidak ada token baru yang dibeli cohort aktif selama jendela pengamatan ini. Tidak adanya sinyal lebih baik daripada memaksa kandidat.</div>`;
    return;
  }
  $("#signals").innerHTML = signals.map((signal) => {
    const token = signal.token;
    const gates = signal.hard_gates.map((gate) => `<span class="gate ${gate.pass ? "pass" : "fail"}" title="${escapeHtml(gate.detail)}">${gate.pass ? "✓" : "×"} ${escapeHtml(gate.name)}</span>`).join("");
    const breakdown = Object.values(signal.breakdown).map((value) => `<i style="width:${Math.max(4, Number(value) * 1.65)}px"></i>`).join("");
    const status = signal.paper_track_eligible ? "LOLOS PAPER GATE" : "HARD GATE GAGAL";
    const caveat = signal.caveats?.[0] || "";
    return `<article class="signal-card ${signal.paper_track_eligible ? "eligible" : ""}">
      <div class="signal-top"><div><div class="symbol">${escapeHtml(signal.symbol || token.symbol)}</div><div class="token-name">${escapeHtml(token.name)} · ${addressHtml(token.address, live)}</div></div><div class="score-box"><div class="score-num">${signal.score}</div><div class="score-label">skor riset / 100</div></div></div>
      <div class="signal-meta"><div><span>Konsensus</span><b>${signal.independent_wallet_count} independen</b></div><div><span>Likuiditas</span><b>${formatUsd(token.liquidity_usd, true)}</b></div><div><span>Status</span><b>${status}</b></div></div>
      <div class="gate-list">${gates}</div><div class="breakdown" title="Breakdown skor: konvergensi, kualitas wallet, likuiditas, aktivitas pasar, keamanan, execution proxy">${breakdown}</div><p class="caveat">${escapeHtml(caveat)}</p>
    </article>`;
  }).join("");
}

function renderNotes(notes) {
  $("#methodNotes").innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
}

function renderResult(payload) {
  const result = payload.result;
  const live = !result.is_demo;
  $("#emptyState").classList.add("hidden");
  $("#results").classList.remove("hidden");
  $("#demoBanner").classList.toggle("hidden", !result.is_demo);
  $("#seedTitle").textContent = `${result.seed_token.symbol} · cohort dari pembeli awal`;
  $("#seedMeta").textContent = `${shortAddress(result.seed_token.address)} · pool ${result.seed_token.dex_id || "—"} · liquidity ${formatUsd(result.seed_token.liquidity_usd, true)} · dibuat ${relativeDate(result.seed_token.pair_created_at)}`;
  renderMetrics(result.summary);
  renderBuyers(result.early_buyers, live);
  renderCohort(result.early_buyers, live);
  renderSignals(result.signals, live);
  renderNotes(result.method_notes);
  loadPaperSignals();
  $("#results").scrollIntoView({ behavior:"smooth", block:"start" });
}

async function loadPaperSignals() {
  try {
    const signals = await fetch("/api/paper-signals").then((response) => response.json());
    $("#paperTable").innerHTML = signals.length ? signals.map((signal) => {
      const returnClass = signal.return_pct === null ? "" : signal.return_pct >= 0 ? "status human" : "status bot";
      const returnText = signal.return_pct === null ? "—" : `${signal.return_pct >= 0 ? "+" : ""}${Number(signal.return_pct).toFixed(2)}%`;
      return `<tr><td><strong>${escapeHtml(signal.symbol)}</strong><br><span class="address">${escapeHtml(shortAddress(signal.token_address))}</span></td><td>${signal.score}/100<br><span class="muted">${signal.consensus_wallets} konsensus</span></td><td>${formatUsd(signal.entry_price_usd)}</td><td>${formatUsd(signal.current_price_usd)}</td><td class="${returnClass}">${returnText}</td><td>${signal.alert_sent ? '<span class="status human">Terkirim</span>' : '<span class="muted">Tidak / demo</span>'}</td></tr>`;
    }).join("") : `<tr><td colspan="6" class="muted">Belum ada kandidat yang lolos hard gate untuk paper tracking.</td></tr>`;
  } catch (_) {
    $("#paperTable").innerHTML = `<tr><td colspan="6" class="muted">Paper tracking belum dapat dimuat.</td></tr>`;
  }
}

$("#exampleBtn").addEventListener("click", () => { $("#mintInput").value = DEMO_MINT; $("#modeSelect").value = "demo"; });
$("#modeSelect").addEventListener("change", (event) => {
  if (event.target.value === "live" && runtimeConfig && !runtimeConfig.live_ready) {
    setError("Live mode belum siap: isi HELIUS_API_KEY dan BIRDEYE_API_KEY di .env, lalu restart container.");
  } else setError("");
});

$("#analysisForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  setError("");
  const mint = $("#mintInput").value.trim();
  const mode = $("#modeSelect").value;
  if (mode === "live" && runtimeConfig && !runtimeConfig.live_ready) {
    setError("Live mode tidak tersedia sampai kedua API key disetel di .env."); return;
  }
  const button = $("#runButton");
  button.disabled = true; button.querySelector("span").textContent = "Menganalisis cohort…";
  try {
    const response = await fetch("/api/analyses", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ mint, mode }) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Permintaan analisis gagal.");
    renderResult(body);
  } catch (error) {
    setError(error.message || "Tidak dapat menjalankan analisis.");
  } finally {
    button.disabled = false; button.querySelector("span").textContent = "Jalankan analisis";
  }
});

$("#paperRefresh").addEventListener("click", async () => {
  const button = $("#paperRefresh"); button.disabled = true; button.textContent = "Memperbarui…";
  try { await fetch("/api/paper-signals/refresh", { method:"POST", headers:{"Content-Type":"application/json"}, body:"{}" }); await loadPaperSignals(); }
  finally { button.disabled = false; button.textContent = "Perbarui paper tracking"; }
});

loadConfig();
loadPaperSignals();
