// JobTrack Agent — side panel logic.
//
// Stays open across tab switches. On load it probes backend health and lists
// recent captures; the search box queries POST /search (debounced) and falls
// back to GET /recent when empty. "Capture This Job" drives the active tab's
// content script.

const BACKEND_URL = "http://localhost:8000";

const captureBtn = document.getElementById("capture-btn");
const exportBtn = document.getElementById("export-btn");
const statusDiv = document.getElementById("status");
const jobList = document.getElementById("job-list");
const searchInput = document.getElementById("search");
const healthDot = document.getElementById("health-dot");
const healthText = document.getElementById("health-text");

// border-left + badge color per status.
const STATUS_COLORS = {
  applied: "#63b3ed",
  screening: "#f6ad55",
  interview: "#4fd1c5",
  offer: "#68d391",
  rejected: "#fc8181",
  ghosted: "#64748b",
};

function platformEmoji(platform) {
  const key = (platform || "").toLowerCase();
  if (key.includes("linkedin")) return "💼";
  if (key.includes("naukri")) return "🇮🇳";
  if (key.includes("wellfound")) return "🚀";
  if (key.includes("internshala")) return "🎓";
  if (key.includes("indeed")) return "🔍";
  if (key.includes("glassdoor")) return "🪟";
  return "🌐";
}

function statusColor(status) {
  return STATUS_COLORS[status] || "#64748b";
}

function setStatus(message, kind) {
  statusDiv.textContent = message;
  statusDiv.className = kind ? `status-${kind}` : "";
}

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

async function checkHealth() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    healthDot.className = "dot online";
    healthText.textContent = "Online";
  } catch {
    healthDot.className = "dot offline";
    healthText.textContent = "Offline";
  }
}

// ---------------------------------------------------------------------------
// Job cards
// ---------------------------------------------------------------------------

function buildCard(job) {
  const card = document.createElement("div");
  card.className = "job-card";
  card.style.borderLeftColor = statusColor(job.status);

  // Row 1: company · role
  const row1 = document.createElement("div");
  row1.className = "job-row1";
  const company = document.createElement("span");
  company.className = "job-company";
  company.textContent = job.company || "Unknown company";
  const role = document.createElement("span");
  role.className = "job-role";
  role.textContent = job.role ? ` · ${job.role}` : "";
  row1.appendChild(company);
  row1.appendChild(role);

  // Row 2: platform emoji + date
  const row2 = document.createElement("div");
  row2.className = "job-row2";
  row2.textContent = `${platformEmoji(job.source_platform)} ${formatDate(
    job.date_applied
  )}`;

  // Row 3: status badge + first 3 skills
  const row3 = document.createElement("div");
  row3.className = "job-row3";
  const badge = document.createElement("span");
  badge.className = "badge";
  const status = job.status || "saved";
  badge.textContent = status;
  badge.style.background = statusColor(status);
  row3.appendChild(badge);

  (job.skills || []).slice(0, 3).forEach((skill) => {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = skill;
    row3.appendChild(pill);
  });

  // Status toggle: Saved <-> Applied. PATCHes the backend on change.
  const toggle = document.createElement("div");
  toggle.className = "status-toggle";
  toggle.innerHTML = `
    <span class="toggle-label">Saved</span>
    <label class="toggle-switch">
      <input type="checkbox" class="toggle-input"
             data-job-id="${job.id}"
             ${job.status === "applied" ? "checked" : ""}>
      <span class="toggle-slider"></span>
    </label>
    <span class="toggle-label">Applied</span>
  `;
  // Don't let interacting with the toggle open the job URL.
  toggle.addEventListener("click", (e) => e.stopPropagation());
  toggle.querySelector(".toggle-input").addEventListener("change", async (e) => {
    const jobId = e.target.dataset.jobId;
    const newStatus = e.target.checked ? "applied" : "saved";
    try {
      await fetch(`${BACKEND_URL}/application/${jobId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      // Reflect the new status on the card's badge + accent.
      badge.textContent = newStatus;
      badge.style.background = statusColor(newStatus);
      card.style.borderLeftColor = statusColor(newStatus);
    } catch {
      // Revert the switch if the update failed.
      e.target.checked = !e.target.checked;
    }
  });

  card.appendChild(row1);
  card.appendChild(row2);
  card.appendChild(row3);
  card.appendChild(toggle);

  if (job.url) {
    card.addEventListener("click", () => {
      chrome.tabs.create({ url: job.url });
    });
  }

  return card;
}

function renderJobs(jobs) {
  jobList.innerHTML = "";
  if (!Array.isArray(jobs) || jobs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No captures yet";
    jobList.appendChild(empty);
    return;
  }
  jobs.forEach((job) => jobList.appendChild(buildCard(job)));
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadRecent() {
  try {
    const res = await fetch(`${BACKEND_URL}/recent`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderJobs(await res.json());
  } catch {
    renderJobs([]);
  }
}

async function runSearch(query) {
  try {
    const res = await fetch(`${BACKEND_URL}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderJobs(await res.json());
  } catch {
    renderJobs([]);
  }
}

// ---------------------------------------------------------------------------
// Manual capture
// ---------------------------------------------------------------------------

// Ensure content.js is present in the active tab, then ask it to capture.
// chrome.tabs.sendMessage throws if the content script was never injected
// (e.g. the static content_scripts entry didn't run on this page), so we
// inject programmatically first and use the callback form to swallow the
// "Receiving end does not exist" lastError gracefully.
async function captureActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Step 1: Programmatically inject content.js if not already there
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (e) {
    // Already injected — ignore the error, this is expected
  }

  // Step 2: Small wait to let content.js initialise
  await new Promise((r) => setTimeout(r, 200));

  // Step 3: Now send the message — content.js is guaranteed to be there
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(
      tab.id,
      { action: "capture_manual", status: "applied" },
      (response) => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(response);
        }
      }
    );
  });
}

async function captureJob() {
  captureBtn.disabled = true;
  const originalText = captureBtn.textContent;
  captureBtn.textContent = "Capturing...";
  setStatus("Capturing…", "loading");

  try {
    const result = await captureActiveTab();

    if (result && result.success) {
      const job = result.data;
      setStatus(`✅ Saved: ${job.role} at ${job.company}`, "success");
      // Prepend the new card so it shows immediately.
      const firstChild = jobList.firstChild;
      if (firstChild && firstChild.classList?.contains("empty")) {
        jobList.innerHTML = "";
      }
      jobList.prepend(buildCard(job));
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

document.getElementById("dashboard-btn").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("dashboard.html") });
});

let searchTimer = null;
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const query = searchInput.value.trim();
    if (query) {
      runSearch(query);
    } else {
      loadRecent();
    }
  }, 400);
});

checkHealth();
loadRecent();
