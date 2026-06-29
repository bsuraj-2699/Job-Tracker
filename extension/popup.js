// JobTrack Agent — popup logic.
//
// On open: probe backend health and load the recent captures list.
// "Capture This Job" tells the active tab's content script to capture now.
// "Export CSV" opens the backend's CSV export in a new tab.

const BACKEND_URL = "http://localhost:8000";

const captureBtn = document.getElementById("capture-btn");
const exportBtn = document.getElementById("export-btn");
const statusDiv = document.getElementById("status");
const recentList = document.getElementById("recent-list");
const healthDot = document.getElementById("health-dot");
const healthText = document.getElementById("health-text");

// Status badge colors keyed by application status.
const STATUS_COLORS = {
  applied: "#63b3ed",
  screening: "#f6ad55",
  interview: "#4fd1c5",
  offer: "#68d391",
  rejected: "#fc8181",
  ghosted: "#64748b",
};

function setStatus(message, kind) {
  statusDiv.textContent = message;
  statusDiv.className = kind ? `status-${kind}` : "";
}

// ---------------------------------------------------------------------------
// Backend health
// ---------------------------------------------------------------------------

async function checkHealth() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    healthDot.className = "dot online";
    healthText.textContent = "Backend: Online";
  } catch {
    healthDot.className = "dot offline";
    healthText.textContent = "Backend: Offline";
  }
}

// ---------------------------------------------------------------------------
// Recent captures
// ---------------------------------------------------------------------------

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function renderRecent(jobs) {
  recentList.innerHTML = "";

  if (!Array.isArray(jobs) || jobs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No captures yet";
    recentList.appendChild(empty);
    return;
  }

  // Show at most the last 5.
  jobs.slice(0, 5).forEach((job) => {
    const row = document.createElement("div");
    row.className = "recent-row";

    const main = document.createElement("div");
    main.className = "recent-main";

    const company = document.createElement("div");
    company.className = "recent-company";
    company.textContent = job.company || "Unknown company";

    const meta = document.createElement("div");
    meta.className = "recent-meta";
    meta.textContent = `${job.role || "—"} · ${formatDate(job.date_applied)}`;

    main.appendChild(company);
    main.appendChild(meta);

    const badge = document.createElement("span");
    badge.className = "badge";
    const status = job.status || "saved";
    badge.textContent = status;
    badge.style.background = STATUS_COLORS[status] || "#64748b";

    row.appendChild(main);
    row.appendChild(badge);
    recentList.appendChild(row);
  });
}

async function loadRecent() {
  try {
    const res = await fetch(`${BACKEND_URL}/recent`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const jobs = await res.json();
    renderRecent(jobs);
  } catch {
    renderRecent([]);
  }
}

// ---------------------------------------------------------------------------
// Manual capture
// ---------------------------------------------------------------------------

async function captureJob() {
  captureBtn.disabled = true;
  const originalText = captureBtn.textContent;
  captureBtn.textContent = "Capturing...";
  setStatus("", null);

  try {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    if (!tab || !tab.id) throw new Error("No active tab");

    const result = await chrome.tabs.sendMessage(tab.id, {
      action: "capture_manual",
    });

    if (result && result.success) {
      const { role, company } = result.data;
      setStatus(`✅ Saved: ${role} at ${company}`, "success");
      await loadRecent();
    } else {
      setStatus("❌ Failed — is backend running?", "error");
    }
  } catch {
    setStatus("❌ Failed — is backend running?", "error");
  } finally {
    captureBtn.disabled = false;
    captureBtn.textContent = originalText;
  }
}

// ---------------------------------------------------------------------------
// Wire up
// ---------------------------------------------------------------------------

captureBtn.addEventListener("click", captureJob);

exportBtn.addEventListener("click", () => {
  chrome.tabs.create({ url: `${BACKEND_URL}/export` });
});

checkHealth();
loadRecent();
