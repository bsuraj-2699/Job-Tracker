// JobTrack Agent — full-page dashboard.
//
// Loads all applications once (GET /recent?limit=200) into `allJobs`, then does
// all search/status/platform filtering client-side. Status changes PATCH and
// deletes DELETE the backend, mutating `allJobs` in place (no full reloads).

const BACKEND_URL = "http://localhost:8000";

const KNOWN_PLATFORMS = [
  "LinkedIn",
  "Naukri",
  "Indeed",
  "Wellfound",
  "Internshala",
];

const STATUS_OPTIONS = [
  "saved",
  "applied",
  "screening",
  "interview",
  "offer",
  "rejected",
  "ghosted",
];

const STATUS_COLORS = {
  saved: "#94a3b8",
  applied: "#63b3ed",
  screening: "#f6ad55",
  interview: "#4fd1c5",
  offer: "#68d391",
  rejected: "#fc8181",
  ghosted: "#64748b",
};

let allJobs = [];

// DOM refs
const tableBody = document.getElementById("table-body");
const emptyEl = document.getElementById("empty");
const searchInput = document.getElementById("search");
const statusFilter = document.getElementById("status-filter");
const platformFilter = document.getElementById("platform-filter");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status) {
  return STATUS_COLORS[status] || "#64748b";
}

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

// "Today" / "Yesterday" / "Jun 27"
function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "—";

  const today = new Date();
  const startOf = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
  const days = Math.round((startOf(today) - startOf(d)) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function platformBucket(platform) {
  if (platform && KNOWN_PLATFORMS.includes(platform)) return platform;
  return "Other";
}

// ---------------------------------------------------------------------------
// Row building
// ---------------------------------------------------------------------------

function buildRow(job, index) {
  const tr = document.createElement("tr");
  tr.dataset.jobId = job.id;

  // #
  const numTd = document.createElement("td");
  numTd.className = "col-num";
  numTd.textContent = index + 1;

  // Company
  const companyTd = document.createElement("td");
  companyTd.className = "col-company";
  companyTd.textContent = job.company || "—";

  // Position
  const positionTd = document.createElement("td");
  positionTd.className = "col-position";
  positionTd.textContent = job.role || "—";

  // JD (truncated, expandable inline)
  const jdTd = document.createElement("td");
  jdTd.className = "col-jd";
  const jdText = job.jd_summary || "";
  if (jdText.length > 80) {
    let expanded = false;
    const render = () => {
      jdTd.textContent = "";
      const span = document.createElement("span");
      span.textContent = expanded ? jdText + " " : jdText.slice(0, 80) + "... ";
      const toggle = document.createElement("span");
      toggle.className = "jd-toggle";
      toggle.textContent = expanded ? "▲ collapse" : "▼ expand";
      toggle.addEventListener("click", () => {
        expanded = !expanded;
        render();
      });
      jdTd.appendChild(span);
      jdTd.appendChild(toggle);
    };
    render();
  } else {
    jdTd.textContent = jdText || "—";
  }

  // Skills (first 3 pills + "+N more")
  const skillsTd = document.createElement("td");
  const skills = Array.isArray(job.skills) ? job.skills : [];
  skills.slice(0, 3).forEach((skill) => {
    const pill = document.createElement("span");
    pill.className = "skill-pill";
    pill.textContent = skill;
    skillsTd.appendChild(pill);
  });
  if (skills.length > 3) {
    const more = document.createElement("span");
    more.className = "skill-more";
    more.textContent = `+${skills.length - 3} more`;
    skillsTd.appendChild(more);
  }
  if (skills.length === 0) skillsTd.textContent = "—";

  // Status (badge + change dropdown)
  const statusTd = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = job.status || "saved";
  badge.style.background = statusColor(job.status);
  const select = document.createElement("select");
  select.className = "status-select";
  STATUS_OPTIONS.forEach((opt) => {
    const o = document.createElement("option");
    o.value = opt;
    o.textContent = opt;
    if (opt === job.status) o.selected = true;
    select.appendChild(o);
  });
  select.addEventListener("change", async (e) => {
    const newStatus = e.target.value;
    const prev = job.status;
    try {
      await fetch(`${BACKEND_URL}/application/${job.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      job.status = newStatus; // mutate in-memory copy
      badge.textContent = newStatus;
      badge.style.background = statusColor(newStatus);
      updateStats(currentFiltered());
    } catch {
      select.value = prev; // revert on failure
    }
  });
  statusTd.appendChild(badge);
  statusTd.appendChild(select);

  // Date
  const dateTd = document.createElement("td");
  dateTd.textContent = formatDate(job.date_applied);

  // Platform
  const platformTd = document.createElement("td");
  platformTd.className = "platform";
  platformTd.textContent = `${platformEmoji(job.source_platform)} ${
    job.source_platform || "Other"
  }`;

  // Actions
  const actionsTd = document.createElement("td");
  const openBtn = document.createElement("button");
  openBtn.className = "action-btn";
  openBtn.title = "Open job posting";
  openBtn.textContent = "🔗";
  openBtn.addEventListener("click", () => {
    if (job.url) window.open(job.url, "_blank");
  });
  const delBtn = document.createElement("button");
  delBtn.className = "action-btn";
  delBtn.title = "Delete";
  delBtn.textContent = "🗑️";
  delBtn.addEventListener("click", () => deleteJob(job, tr));
  actionsTd.appendChild(openBtn);
  actionsTd.appendChild(delBtn);

  tr.append(
    numTd,
    companyTd,
    positionTd,
    jdTd,
    skillsTd,
    statusTd,
    dateTd,
    platformTd,
    actionsTd
  );
  return tr;
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

async function deleteJob(job, tr) {
  if (!confirm("Are you sure?")) return;
  try {
    await fetch(`${BACKEND_URL}/application/${job.id}`, { method: "DELETE" });
    allJobs = allJobs.filter((j) => j.id !== job.id);
    // Fade out, then remove the row from the DOM.
    tr.style.opacity = "0";
    setTimeout(() => {
      tr.remove();
      updateStats(currentFiltered());
      if (tableBody.children.length === 0) emptyEl.style.display = "block";
    }, 300);
  } catch {
    alert("Failed to delete — is the backend running?");
  }
}

// ---------------------------------------------------------------------------
// Filtering + rendering
// ---------------------------------------------------------------------------

function currentFiltered() {
  const q = searchInput.value.trim().toLowerCase();
  const status = statusFilter.value;
  const platform = platformFilter.value;

  return allJobs.filter((job) => {
    if (status !== "All" && (job.status || "") !== status) return false;
    if (platform !== "All" && platformBucket(job.source_platform) !== platform)
      return false;
    if (q) {
      const haystack = [
        job.company || "",
        job.role || "",
        ...(Array.isArray(job.skills) ? job.skills : []),
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

function updateStats(jobs) {
  document.getElementById("stat-total").textContent = jobs.length;
  document.getElementById("stat-applied").textContent = jobs.filter(
    (j) => j.status === "applied"
  ).length;
  document.getElementById("stat-saved").textContent = jobs.filter(
    (j) => j.status === "saved"
  ).length;
}

function filterAndRender() {
  const jobs = currentFiltered();

  tableBody.textContent = "";
  jobs.forEach((job, i) => tableBody.appendChild(buildRow(job, i)));

  emptyEl.style.display = jobs.length === 0 ? "block" : "none";
  updateStats(jobs);
}

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

async function load() {
  try {
    const res = await fetch(`${BACKEND_URL}/recent?limit=200`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    allJobs = await res.json();
  } catch {
    allJobs = [];
  }
  filterAndRender();
}

searchInput.addEventListener("input", filterAndRender);
statusFilter.addEventListener("change", filterAndRender);
platformFilter.addEventListener("change", filterAndRender);
document.getElementById("export-btn").addEventListener("click", () => {
  window.open(`${BACKEND_URL}/export`, "_blank");
});

load();
