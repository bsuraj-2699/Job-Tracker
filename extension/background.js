// JobTrack Agent — background service worker.
//
// content.js now loads on all URLs via the manifest content_scripts entry, so
// the programmatic domain-gated injection fallback is no longer needed. All this
// worker does is open the side panel when the toolbar icon is clicked.

// Side panel: clicking the toolbar icon opens the panel for the current tab.
// With this listener present, Chrome prefers the side panel over the popup.
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});

// Also let Chrome auto-open the panel on action click (no-op on older Chrome).
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(() => {}); // silently ignore if API unavailable
