import { clearSession, getApiBase, getToken, loadCurrentUser, loadDashboard, login, saveSession } from "./api.js";
import { CARD_DEFINITIONS, dashboardSeverity, formatDate, healthClass, priorityClass } from "./dashboard.js";

const $ = (id) => document.getElementById(id);
let refreshTimer = null;
let refreshing = false;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function showLogin(message = "") {
  $("dashboard-view").hidden = true;
  $("login-view").hidden = false;
  $("api-base").value = getApiBase();
  $("login-error").textContent = message;
  if (refreshTimer) clearInterval(refreshTimer);
}

function showDashboard() {
  $("login-view").hidden = true;
  $("dashboard-view").hidden = false;
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refreshDashboard, 30000);
}

function renderCards(counts) {
  $("summary-cards").innerHTML = CARD_DEFINITIONS.map(([key, label]) => {
    const value = counts[key] ?? 0;
    const alert = ["stale_nodes", "failed_nodes", "open_support_cases"].includes(key) && value > 0;
    return `<article class="card ${alert ? "card-alert" : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`;
  }).join("");
}

function renderDeployments(deployments) {
  $("deployment-count").textContent = deployments.length;
  $("deployments-body").innerHTML = deployments.length
    ? deployments.map((item) => `<tr>
        <td><strong>${escapeHtml(item.profile_name)}</strong><small>${escapeHtml(item.purpose)}</small></td>
        <td><span class="status ${healthClass(item.health)}">${escapeHtml(item.health)}</span></td>
        <td>${escapeHtml(item.total_nodes)}</td><td>${escapeHtml(item.online_nodes)}</td>
        <td>${escapeHtml(item.failed_nodes)}</td><td>${escapeHtml(item.attention_nodes)}</td>
      </tr>`).join("")
    : `<tr><td colspan="6" class="empty">No visible deployments.</td></tr>`;
}

function renderAttention(items) {
  $("attention-count").textContent = items.length;
  $("attention-list").innerHTML = items.length
    ? items.map((item) => `<article class="attention-item">
        <div class="attention-top"><span class="status ${priorityClass(item.priority)}">${escapeHtml(item.priority)}</span><span>${escapeHtml(item.kind.replaceAll("_", " "))}</span></div>
        <strong>${escapeHtml(item.summary)}</strong>
        <p>${escapeHtml(item.reason.replaceAll("_", " "))}</p>
        <time>${escapeHtml(formatDate(item.occurred_at))}</time>
      </article>`).join("")
    : `<div class="empty-state"><strong>No items need attention</strong><p>Current visible fleet has no active support or node alerts.</p></div>`;
}

function renderBanner(data) {
  const severity = dashboardSeverity(data);
  const banner = $("system-banner");
  banner.hidden = false;
  banner.className = `system-banner ${severity}`;
  if (severity === "critical") banner.textContent = "Action required";
  else if (severity === "attention") banner.textContent = "Fleet needs attention";
  else banner.textContent = "Fleet healthy";
}

async function refreshDashboard() {
  if (refreshing) return;
  refreshing = true;
  $("refresh-button").disabled = true;
  try {
    const data = await loadDashboard();
    renderCards(data.counts || {});
    renderDeployments(data.deployments || []);
    renderAttention(data.attention_queue || []);
    renderBanner(data);
    $("generated-label").textContent = `Updated ${formatDate(data.generated_at)} · auto-refresh 30s`;
  } catch (error) {
    if (error.status === 401) {
      clearSession();
      showLogin("Your session expired. Sign in again.");
      return;
    }
    $("system-banner").hidden = false;
    $("system-banner").className = "system-banner critical";
    $("system-banner").textContent = error.message || "Unable to load dashboard";
  } finally {
    refreshing = false;
    $("refresh-button").disabled = false;
  }
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("login-error").textContent = "";
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const apiBase = $("api-base").value;
    const result = await login($("username").value, $("password").value, apiBase);
    saveSession(result.access_token, apiBase);
    $("password").value = "";
    $("user-label").textContent = result.user?.username || result.user?.email || "Signed in";
    showDashboard();
    await refreshDashboard();
  } catch (error) {
    $("login-error").textContent = error.message || "Sign in failed.";
  } finally {
    button.disabled = false;
  }
});

$("logout-button").addEventListener("click", () => {
  clearSession();
  showLogin();
});
$("refresh-button").addEventListener("click", refreshDashboard);

async function bootstrap() {
  if (!getToken()) return showLogin();
  try {
    const user = await loadCurrentUser();
    $("user-label").textContent = user.username || user.email || "Signed in";
    showDashboard();
    await refreshDashboard();
  } catch {
    clearSession();
    showLogin("Sign in to continue.");
  }
}

bootstrap();
