chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.local.remove(["agentToken", "pairedName", "lastCycle", "lastError", "lastInboxTs", "reconnectAttempts", "backoffUntil", "li_at", "JSESSIONID"]);
});
