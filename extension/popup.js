const workspace = document.getElementById("workspace"), draft = document.getElementById("draft"), status = document.getElementById("status");
chrome.storage.local.get(["workspaceUrl", "draftIdea"]).then(data => { workspace.value = data.workspaceUrl || "http://localhost:5173"; draft.value = data.draftIdea || ""; });
function origin() {
 const url = new URL(workspace.value);
 if (url.username || url.password || (url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)))) throw new Error("Use HTTPS, or HTTP localhost for development.");
 return url.origin;
}
async function open(path, capture = false) {
 try {
  const base = origin(); await chrome.storage.local.set({workspaceUrl: base, draftIdea: draft.value});
  const url = new URL(path, base);
  if (capture) { if (!draft.value.trim()) throw new Error("Write an idea first."); url.searchParams.set("text", draft.value); }
  await chrome.tabs.create({url: url.href}); status.textContent = capture ? "Review and save your draft in the studio." : "Workspace opened.";
 } catch (e) { status.textContent = e.message; }
}
draft.addEventListener("input", () => chrome.storage.local.set({draftIdea: draft.value}));
document.getElementById("capture").addEventListener("click", () => open("/studio?new=extension", true));
document.getElementById("connect").addEventListener("click", () => open("/others/publishing/connections"));
document.getElementById("login").addEventListener("click", () => open("/login"));
