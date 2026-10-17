const $ = (id) => document.getElementById(id);
const CIRC = 2 * Math.PI * 58;
let lastScan = null;
let filter = "all";

const CAT = {
  firmware: "Прошивка",
  hardware: "Железо",
  graphics: "Графика",
  security: "Безопасность",
  identity: "Система",
  health: "Здоровье",
};

const PILL = { pass: "ОК", warn: "СПОРНО", fail: "НЕТ", skip: "—" };

function ready() {
  return window.pywebview && window.pywebview.api;
}

function toast(text) {
  const el = $("toast");
  el.hidden = false;
  el.textContent = text;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4200);
}

function setBusy(on) {
  $("scanBtn").disabled = on;
  $("scanBtn").textContent = on ? "Сканирую…" : "Сканировать";
  $("status").textContent = on ? "Опрашиваю TPM, UEFI, WMI, защиту…" : "Готово.";
}

function setScore(value, label, tone) {
  const bar = document.querySelector(".bar");
  const offset = CIRC - CIRC * Math.max(0, Math.min(100, value || 0)) / 100;
  bar.style.strokeDashoffset = String(offset);
  $("score").textContent = value == null ? "—" : String(value);
  $("scoreLabel").textContent = label || "ожидание";
  $("score").style.color = { pass: "#5dffc0", warn: "#ffc14d", fail: "#ff5d73" }[tone] || "#f4efe6";
}

function render(scan) {
  lastScan = scan;
  const ident = scan.identity || {};
  const meta = scan.meta || {};
  const score = scan.score || {};
  $("fHost").textContent = meta.hostname || "—";
  $("fOs").textContent = ident.os || "—";
  $("fCpu").textContent = ident.cpu || "—";
  $("fTime").textContent = meta.elapsedMs != null ? `${meta.elapsedMs} мс` : "—";
  $("headline").textContent = score.label || "Helios";
  $("lede").textContent = score.ready
    ? "Железо проходит врата Microsoft. Ниже — нюансы, которые всё ещё стоит починить."
    : "Есть блокеры официальной Windows 11. Карточки с красным — то, что Microsoft не простит.";
  setScore(score.value, score.label, score.tone);
  paintGrid();
}

function paintGrid() {
  const grid = $("grid");
  grid.innerHTML = "";
  const checks = (lastScan && lastScan.checks) || [];
  const list = checks.filter((c) => filter === "all" || c.category === filter);
  list.forEach((c, i) => {
    const el = document.createElement("article");
    el.className = "card";
    el.style.animationDelay = `${i * 40}ms`;
    el.innerHTML = `
      <div class="head">
        <h3>${escapeHtml(c.title)}</h3>
        <span class="pill ${c.status}">${PILL[c.status] || c.status}</span>
      </div>
      <div class="val">${escapeHtml(c.value || CAT[c.category] || "")}</div>
      <p class="sum">${escapeHtml(c.summary || "")}</p>
      ${c.hint ? `<p class="hint">${escapeHtml(c.hint)}</p>` : ""}
    `;
    grid.appendChild(el);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

async function scan() {
  if (!ready()) {
    toast("Мост pywebview ещё не поднялся.");
    return;
  }
  setBusy(true);
  try {
    const data = await window.pywebview.api.scan();
    render(data);
    $("status").textContent = `Скан завершён за ${data.meta.elapsedMs} мс.`;
  } catch (err) {
    $("status").textContent = String(err);
    toast("Скан сорвался. Смотри статус.");
  } finally {
    setBusy(false);
  }
}

async function tick() {
  if (!ready()) return;
  try {
    const t = await window.pywebview.api.telemetry();
    $("mCpu").textContent = `${t.cpu}%`;
    $("mRam").textContent = `${t.ram}%`;
    $("mDisk").textContent = `${t.disk}%`;
    $("bCpu").style.width = `${t.cpu}%`;
    $("bRam").style.width = `${t.ram}%`;
    $("bDisk").style.width = `${t.disk}%`;
    $("liveNote").textContent = t.ramText + " · " + t.diskText;
  } catch {
    /* ignore */
  }
}

window.addEventListener("pywebviewready", () => {
  $("status").textContent = "Мост живой. Запускаю первый скан.";
  scan();
  tick();
  setInterval(tick, 1200);
});

$("scanBtn").addEventListener("click", scan);
$("minBtn").addEventListener("click", () => ready() && window.pywebview.api.minimize());
$("closeBtn").addEventListener("click", () => ready() && window.pywebview.api.close());
$("exportBtn").addEventListener("click", async () => {
  if (!ready()) return;
  const res = await window.pywebview.api.export();
  toast(res.ok ? `Сохранено в ${res.md}` : res.error);
});
$("copyBtn").addEventListener("click", async () => {
  if (!ready()) return;
  await window.pywebview.api.copy_markdown();
  toast("Отчёт в буфере обмена.");
});
$("chips").addEventListener("click", (e) => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  filter = btn.dataset.cat;
  for (const c of $("chips").children) c.classList.toggle("on", c === btn);
  paintGrid();
});
window.addEventListener("keydown", (e) => {
  if (e.code === "Space" && e.target === document.body) {
    e.preventDefault();
    scan();
  }
});
