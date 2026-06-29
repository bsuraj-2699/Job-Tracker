// JobTrack Agent — content script.
//
// Manual capture only: the side panel sends a `capture_manual` message and we
// snapshot + POST the page. (Auto-capture on Apply-button clicks was removed.)
//
// Responsibilities:
//   A) Listen for a manual capture message from the panel -> capture on demand.
//   B) Show toast notifications on the page.

const BACKEND_URL = "http://localhost:8000";

// ---------------------------------------------------------------------------
// A) Manual capture message from the panel
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.action === "capture_manual") {
    // No 800ms wait for manual captures — fire immediately. The panel passes
    // the desired status (defaults to "applied").
    captureAndSend(message.status || "applied").then(sendResponse);
    return true; // keep the message channel open for the async response
  }
});

// ---------------------------------------------------------------------------
// Shared capture
// ---------------------------------------------------------------------------

// Resolve once `selector` is present in the DOM (or after `timeout` ms). Used
// to wait out portals that render job details asynchronously (e.g. Indeed).
function waitForContent(selector, timeout = 5000) {
  return new Promise((resolve) => {
    if (document.querySelector(selector)) {
      return resolve(true);
    }
    const observer = new MutationObserver(() => {
      if (document.querySelector(selector)) {
        observer.disconnect();
        resolve(true);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => {
      observer.disconnect();
      resolve(false);
    }, timeout);
  });
}

// Click any "show more" / "see more" toggles so the full job description is in
// the DOM before we snapshot outerHTML (LinkedIn/Indeed collapse long JDs).
async function expandCollapsedContent() {
  const expandSelectors = [
    // LinkedIn
    "button.jobs-description__footer-button",
    "button[aria-label='Click to see more description']",
    ".jobs-description__content--condensed button",
    "button.show-more-less-html__button--more",

    // Indeed
    "#jobDescriptionText .jobsearch-expandJobDescription",

    // Generic
    "button[data-testid='show-more']",
    "[class*='show-more']",
    "[class*='see-more']",
    "[class*='expand']",
  ];

  let expanded = false;
  for (const selector of expandSelectors) {
    const btn = document.querySelector(selector);
    if (btn && btn.offsetParent !== null) {
      // visible check
      btn.click();
      expanded = true;
    }
  }

  // Wait for content to render after expansion
  if (expanded) {
    await new Promise((r) => setTimeout(r, 800));
  }
}

async function captureAndSend(status = "applied") {
  // Expand collapsed descriptions before waiting on / snapshotting the DOM.
  await expandCollapsedContent();

  // Wait for known job detail containers per portal so outerHTML is complete.
  const portal = window.location.hostname;
  if (portal.includes("indeed.com")) {
    await waitForContent(
      ".jobsearch-JobComponent, [data-testid='jobsearch-JobInfoHeader-title']"
    );
  } else if (portal.includes("linkedin.com")) {
    await waitForContent(
      ".job-details-jobs-unified-top-card__job-title, .jobs-description"
    );
  } else if (portal.includes("naukri.com")) {
    await waitForContent(".jd-header-title, .job-tittle");
  } else if (portal.includes("wellfound.com")) {
    await waitForContent(".job-show, [data-test='job-title']");
  } else if (portal.includes("internshala.com")) {
    await waitForContent(".profile-header, .job_detail");
  }

  // Additional 600ms buffer for any remaining async rendering
  await new Promise((r) => setTimeout(r, 600));

  // NOW grab the HTML — page is fully loaded
  const raw_html = document.documentElement.outerHTML;

  const payload = {
    url: window.location.href,
    raw_html,
    page_title: document.title,
  };

  try {
    const res = await fetch(
      `${BACKEND_URL}/capture?status=${encodeURIComponent(status)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    // 409 = backend already has this URL; not an error, just inform the user.
    if (res.status === 409) {
      sessionStorage.setItem(`jt_captured_${window.location.href}`, "true");
      showToast("Already saved!", "info");
      return { success: true, duplicate: true };
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    sessionStorage.setItem(`jt_captured_${window.location.href}`, "true");
    showToast(`✅ Captured: ${data.role} at ${data.company}`, "success");
    return { success: true, data };
  } catch (err) {
    showToast("❌ Capture failed — is backend running?", "error");
    return { success: false, error: err.message };
  }
}

// ---------------------------------------------------------------------------
// B) Toast
// ---------------------------------------------------------------------------

function showToast(message, type) {
  const toast = document.createElement("div");
  toast.textContent = message;

  const accent =
    type === "success" ? "#4fd1c5" : type === "info" ? "#f6ad55" : "#fc8181";
  Object.assign(toast.style, {
    position: "fixed",
    bottom: "24px",
    right: "24px",
    zIndex: "999999",
    background: "#0d1117",
    borderRadius: "8px",
    padding: "12px 18px",
    font: "14px system-ui, -apple-system, sans-serif",
    color: "#e2e8f0",
    maxWidth: "320px",
    boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
    borderLeft: `3px solid ${accent}`,
    opacity: "0",
    transition: "opacity 0.3s",
  });

  document.body.appendChild(toast);

  // Fade in.
  setTimeout(() => {
    toast.style.opacity = "1";
  }, 10);

  // Fade out, then remove from the DOM.
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
