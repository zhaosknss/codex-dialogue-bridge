"use strict";
const $ = id => document.getElementById(id);
const el = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
let token = new URLSearchParams(location.hash.slice(1)).get("token") || sessionStorage.getItem("bridge-token") || "";
if (location.hash.includes("token=")) history.replaceState(null, "", location.pathname);
if (token) sessionStorage.setItem("bridge-token", token);
let space = "", view = "overview", snapshot = {}, documents = {}, spaces = [];
function notice(text, error = false) { $("notice").textContent = text; $("notice").className = error ? "error" : ""; }
async function api(action, args = {}, scoped = true) {
  const response = await fetch("/api/action", {method: "POST", headers: {"Content-Type": "application/json", "Authorization": "Bearer " + token}, body: JSON.stringify({action, arguments: {...(scoped && space ? {name: space} : {}), ...args}})});
  const data = await response.json();
  if (!response.ok) { if (response.status === 401) unlock(); throw new Error(data.error || "The operation failed"); }
  if (data.error) throw new Error(typeof data.error === "string" ? data.error : JSON.stringify(data.error));
  return data;
}
function unlock() { $("unlock").hidden = false; $("application").hidden = true; }
function rows(value, keys) { if (Array.isArray(value)) return value; for (const key of keys) if (Array.isArray(value?.[key])) return value[key]; return []; }
function detail(parent, title, value) { const d = el("details"); d.append(el("summary", title), el("pre", typeof value === "string" ? value : JSON.stringify(value, null, 2))); parent.append(d); }
function empty(parent, title, text) { const n = el("div", undefined, "empty"); n.append(el("strong", title), el("span", text)); parent.append(n); }
function badge(text, pending = false) { return el("span", text, "badge" + (pending ? " pending" : "")); }
function describe(value) { return typeof value === "string" ? value : value?.text || value?.summary || value?.title || value?.label || ""; }
function result(data) { $("operation-result").textContent = JSON.stringify(data, null, 2); }
async function run(task) { try { await task(); } catch (error) { notice(error.message, true); } }
async function loadSpaces(preferred) {
  const data = await api("list_spaces", {}, false); spaces = rows(data, ["spaces", "backgrounds"]);
  const selected = preferred || space;
  $("space").replaceChildren(el("option", "Choose a space")); $("space").firstChild.value = "";
  for (const row of spaces) { const option = el("option", row.name); option.value = row.name; $("space").append(option); }
  space = spaces.some(s => s.name === selected) ? selected : (spaces[0]?.name || "");
  $("space").value = space; $("sync").disabled = !space;
  $("space-label").textContent = space || "Your connected work";
  await refreshView();
}
async function refreshView() {
  if (space) snapshot = await api("open", {lightweight: true}); else snapshot = {};
  if (view === "overview") renderOverview();
  if (view === "understanding") await loadDocuments();
  if (view === "activity") await loadActivity();
}
function renderOverview() {
  const target = $("overview-content"); target.replaceChildren();
  if (!space) { empty(target, "Connect the work you want to carry forward", "Add selected chat links below to create your first understanding space."); $("connect-details").open = true; return; }
  const sources = snapshot.sources || spaces.find(s => s.name === space)?.sources || snapshot.index?.sources || [];
  const sourceCard = el("article", undefined, "card wide"); sourceCard.append(el("h2", "Connected sources"));
  if (!sources.length) sourceCard.append(el("p", "Source information is available in the space index.", "muted"));
  for (const source of sources) { const row = el("div", undefined, "source-row"); row.append(el("h3", source.label || source.scope || "Connected chat"), el("p", source.scope || ""), el("p", source.thread || source.actor || "")); sourceCard.append(row); }
  target.append(sourceCard);
  const changes = el("article", undefined, "card"); changes.append(el("h2", "What changed"));
  const changeRows = rows(snapshot.changes, ["changes", "items"]);
  if (changeRows.length) for (const change of changeRows.slice(0, 8)) changes.append(el("p", describe(change) || JSON.stringify(change)));
  else changes.append(el("p", "No new changes are reported in this view.", "muted")); target.append(changes);
  const attention = el("article", undefined, "card"); attention.append(el("h2", "Needs a closer look"));
  const pending = rows(snapshot.pending_reviews, ["items", "proposals"]);
  attention.append(el("p", pending.length ? `${pending.length} items await review. Open Collaboration & activity to inspect them.` : "Review proposals and queued work in Collaboration & activity.", "muted"));
  for (const warning of snapshot.warnings || []) attention.append(el("p", describe(warning) || JSON.stringify(warning)));
  if (snapshot.coverage) detail(attention, "History coverage", snapshot.coverage); target.append(attention);
  if (snapshot.index) { const index = el("article", undefined, "card wide"); index.append(el("h2", "Shared index")); detail(index, "Sources, documents and dependencies", snapshot.index); target.append(index); }
}
async function loadDocuments() {
  const target = $("document-content"); target.replaceChildren();
  if (!space) return empty(target, "Choose an understanding space", "Connect selected chats in Overview first.");
  documents = await api("documents", {scope: "all"});
  const shared = documents.shared || {text: "", revision: documents.revision};
  renderDocument(target, shared, "Shared understanding", null);
  const chats = rows(documents, ["chats", "documents"]);
  for (const chat of chats) renderDocument(target, chat, chat.label || "Chat understanding", chat.actor || chat.thread);
  if (!chats.length) empty(target, "Each chat keeps its own working understanding", "Chat documents appear here when connected chats contribute them.");
}
function renderDocument(target, doc, title, actor) {
  const card = el("article", undefined, "document"), head = el("div", undefined, "document-head"), titleGroup = el("div");
  titleGroup.append(el("h2", title)); if (actor) titleGroup.append(el("p", actor, "muted"));
  head.append(titleGroup, badge(doc.needs_review ? "Review needed" : `Revision ${doc.revision ?? "—"}`, !!doc.needs_review)); card.append(head);
  const form = el("form"), label = el("label", actor ? "Working understanding" : "Shared understanding and your correction"), text = el("textarea");
  text.value = typeof doc === "string" ? doc : doc.text || ""; text.setAttribute("aria-label", title); label.append(text); form.append(label);
  form.append(el("p", actor ? "Your correction is preserved for review. It is attributed to the local manager, not to this chat." : "Corrections are preserved as proposals for source-based review before shared understanding changes.", "muted"));
  const save = el("button", "Submit correction"); form.append(save);
  form.addEventListener("submit", event => { event.preventDefault(); run(async () => {
    const args = {text: text.value, operation_id: crypto.randomUUID(), ...(Number.isInteger(documents.revision) ? {expected_revision: documents.revision} : {})};
    const data = await api("import_document", {...args, scope: actor ? "chat" : "shared", ...(actor ? {actor} : {}), user_confirmed: true});
    result(data); notice("Correction submitted for review. Understanding changes after its sources are reviewed."); await loadDocuments();
  }); });
  card.append(form); if (doc.dependencies?.length) detail(card, "Referenced shared entries", doc.dependencies); if (doc.authorship) detail(card, "Authorship", doc.authorship); target.append(card);
}
async function loadActivity() {
  for (const id of ["proposals-content", "jobs-content", "inbox-content"]) $(id).replaceChildren();
  if (!space) return empty($("proposals-content"), "Choose an understanding space", "Activity belongs to the sources you connect.");
  const [proposals, jobs, inbox, settings] = await Promise.all([api("proposals"), api("jobs"), api("inbox"), api("settings")]);
  renderActivity($("proposals-content"), "Understanding proposals", rows(proposals, ["proposals", "items"]), "proposal");
  renderActivity($("jobs-content"), "Queued work", rows(jobs, ["jobs", "items"]), "job");
  renderActivity($("inbox-content"), "Contributions & handoffs", rows(inbox, ["items", "contributions", "records"]), "inbox");
  $("settings-json").value = JSON.stringify(settings.settings || settings, null, 2);
}
function renderActivity(target, title, items, kind) {
  target.append(el("h2", title)); if (!items.length) return empty(target, "Nothing pending here", "Refresh activity after connected chats contribute or history changes.");
  for (const item of items) {
    const card = el("article", undefined, "panel"), status = item.status || item.state || "Recorded";
    card.append(badge(status, /pending|queued|review/.test(status)), el("h3", item.title || item.kind || item.id || "Contribution"));
    const text = describe(item); if (text) card.append(el("p", text)); detail(card, "Sources and details", item);
    const actions = el("div", undefined, "row-actions");
    if (kind === "proposal" && /pending|review|proposed/.test(status)) for (const decision of ["accept", "reject"]) {
      const button = el("button", decision === "accept" ? "Review & accept" : "Reject", "quiet"); button.addEventListener("click", () => run(async () => { const data = await api("review_proposal", {id: item.id, decision}); result(data); notice(data.needs_source_review ? (data.next || "Ask Dialogue Bridge in Codex to review this correction against its sources.") : data.status ? `Proposal status: ${data.status}` : "Review recorded. Check the proposal's resulting status."); await loadActivity(); })); actions.append(button);
    }
    if (kind === "job" && /failed|error/.test(status)) { const retry = el("button", "Retry work", "quiet"); retry.addEventListener("click", () => run(async () => { result(await api("jobs", {id: item.id, operation: "retry"})); notice("Retry requested. Completion is shown in the work status."); await loadActivity(); })); actions.append(retry); }
    card.append(actions); target.append(card);
  }
}
for (const button of document.querySelectorAll("[data-view]")) button.addEventListener("click", () => run(async () => {
  view = button.dataset.view; for (const other of document.querySelectorAll("[data-view]")) other.removeAttribute("aria-current"); button.setAttribute("aria-current", "page");
  for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== view;
  $("view-title").textContent = button.textContent; await refreshView();
}));
$("unlock-form").addEventListener("submit", event => { event.preventDefault(); token = $("access-token").value.trim(); sessionStorage.setItem("bridge-token", token); $("unlock").hidden = true; $("application").hidden = false; run(() => loadSpaces()); });
$("space").addEventListener("change", () => run(async () => { space = $("space").value; $("sync").disabled = !space; $("space-label").textContent = space || "Your connected work"; notice(""); await refreshView(); }));
$("reload").addEventListener("click", () => run(() => loadSpaces()));
$("sync").addEventListener("click", () => run(async () => { result(await api("sync", {queue: true})); notice("Source refresh queued. Its actual progress is shown in Collaboration & activity."); }));
$("refresh-activity").addEventListener("click", () => run(loadActivity));
$("process-jobs").addEventListener("click", () => run(async () => { result(await api("process_jobs", {limit: 1})); notice("Queued work checked. See the recorded status for completed or pending work."); await loadActivity(); }));
$("connect-form").addEventListener("submit", event => { event.preventDefault(); run(async () => {
  const name = $("new-name").value.trim(), scope = $("source-scope").value.trim();
  const sources = $("source-links").value.split(/\r?\n/).map(s => s.trim()).filter(Boolean).map(thread => ({thread, scope}));
  const args = {name, sources, mode: $("connection-mode").value}; if ($("new-directory").value.trim()) args.directory = $("new-directory").value.trim();
  result(await api("connect", args, false)); notice("Selected chats connected. History coverage shows what has been collected."); await loadSpaces(name);
}); });
$("search-form").addEventListener("submit", event => { event.preventDefault(); run(async () => {
  const data = await api("search", {query: $("query").value, limit: 10}), target = $("search-results"); target.replaceChildren();
  const hits = rows(data, ["matches", "hits", "results", "items"]); if (!hits.length) empty(target, "No results in this scope", "Try a phrase from the original discussion.");
  for (const hit of hits) { const card = el("article", undefined, "panel"); card.append(el("p", hit.text || hit.excerpt || describe(hit))); if (hit.ref) { const open = el("button", "Read original context", "quiet"); open.addEventListener("click", () => run(async () => { const evidence = await api("evidence", {ref: hit.ref, before: 1, after: 1}); detail(card, "Original source", evidence); })); card.append(open); } detail(card, "Source reference", hit); target.append(card); }
}); });
$("settings-form").addEventListener("submit", event => { event.preventDefault(); run(async () => { const updates = JSON.parse($("settings-json").value); result(await api("settings", {updates})); notice("Space settings saved."); }); });
$("export-form").addEventListener("submit", event => { event.preventDefault(); run(async () => { result(await api("export", {path: $("export-path").value})); notice("Export operation completed. See its local destination in Last operation result."); }); });
$("import-form").addEventListener("submit", event => { event.preventDefault(); run(async () => { result(await api("import", {path: $("import-path").value, directory: $("import-directory").value}, false)); notice("Import operation completed. Refresh spaces to open the imported understanding."); await loadSpaces(); }); });
$("restore-form").addEventListener("submit", event => { event.preventDefault(); run(async () => { result(await api("restore", {revision: Number($("restore-revision").value)})); notice("Restore operation recorded. Review the resulting revision in Current understanding."); await refreshView(); }); });
if (!token) unlock(); else run(() => loadSpaces());
