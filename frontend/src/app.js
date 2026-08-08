import { clearSession, createNodeInstaller, getApiBase, getToken, loadAccess, loadComputeHosts, loadCurrentUser, loadDashboard, loadOrganizations, loadVPSInstances, createVPSInstance, vpsAction, login, saveSession } from "./api.js";
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

function formatBytes(value) {
  const n = Number(value || 0);
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GiB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MiB`;
  return `${n} B`;
}

function renderComputeHosts(hosts) {
  const root = $("compute-hosts");
  $("compute-host-count").textContent = hosts.length;
  root.innerHTML = hosts.length ? hosts.map((host) => {
    const c = host.capacity;
    const readiness = c.scheduling_enabled ? "Schedulable" : `Not ready: ${(c.readiness_reasons || []).join(", ")}`;
    return `<article class="compute-host-card">
      <div><strong>${escapeHtml(host.name)}</strong><small>${escapeHtml(host.hostname)}</small></div>
      <span class="status ${c.scheduling_enabled ? "healthy" : "attention"}">${escapeHtml(readiness)}</span>
      <div class="capacity-grid">
        <span>CPU <strong>${escapeHtml(c.cpu_allocated)} / ${escapeHtml(c.cpu_allocatable)}</strong></span>
        <span>RAM <strong>${escapeHtml(formatBytes(c.memory_allocated_bytes))} / ${escapeHtml(formatBytes(c.memory_allocatable_bytes))}</strong></span>
        <span>Storage <strong>${escapeHtml(formatBytes(c.storage_allocated_bytes))} / ${escapeHtml(formatBytes(c.storage_allocatable_bytes))}</strong></span>
        <span>KVM <strong>${c.kvm_available ? "yes" : "no"}</strong></span>
        <span>libvirt <strong>${c.libvirt_available ? "yes" : "no"}</strong></span>
      </div>
    </article>`;
  }).join("") : `<div class="empty-state"><strong>No VPS hosts</strong><p>Enroll a node with VPS infrastructure purpose.</p></div>`;
}

function renderVPS(items) {
  $("vps-count").textContent = items.length;
  $("vps-body").innerHTML = items.length ? items.map((item) => `<tr>
    <td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.image)}</small></td>
    <td><span class="status">${escapeHtml(item.status)}</span></td>
    <td>${escapeHtml(item.vcpu)}</td>
    <td>${escapeHtml(formatBytes(item.memory_bytes))}</td>
    <td>${escapeHtml(formatBytes(item.disk_bytes))}</td>
    <td>${escapeHtml(item.node_id || "pending")}<small>${escapeHtml(item.primary_ip || "")}</small></td>
    <td>
      ${item.status === "running" ? `<button class="secondary vps-action" data-id="${escapeHtml(item.id)}" data-action="stop">Stop</button><button class="secondary vps-action" data-id="${escapeHtml(item.id)}" data-action="reboot">Reboot</button>` : ""}
      ${item.status === "stopped" ? `<button class="secondary vps-action" data-id="${escapeHtml(item.id)}" data-action="start">Start</button>` : ""}
      ${!["deleted","provisioning"].includes(item.status) ? `<button class="ghost vps-action" data-id="${escapeHtml(item.id)}" data-action="delete">Delete</button>` : ""}
    </td>
  </tr>`).join("") : `<tr><td colspan="6" class="empty">No VPS instances.</td></tr>`;
}

async function refreshCompute() {
  const perms = new Set(currentAccess?.permissions || []);
  if (currentAccess?.is_superuser || perms.has("*") || perms.has("compute.hosts.read")) {
    try { renderComputeHosts(await loadComputeHosts()); } catch (error) { renderComputeHosts([]); }
  } else { $("compute-hosts").innerHTML = `<div class="empty-state">Host capacity is restricted.</div>`; }
  if (currentAccess?.is_superuser || perms.has("*") || perms.has("vps.read")) {
    try { renderVPS(await loadVPSInstances()); } catch (error) { renderVPS([]); }
  }
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
    await refreshCompute();
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



let currentAccess = null;

async function openNodeModal() {
  $("node-form-error").textContent = "";
  $("installer-result").hidden = true;
  $("node-installer-form").hidden = false;
  $("node-modal").hidden = false;
}

function closeNodeModal() { $("node-modal").hidden = true; }

$("add-node-button").addEventListener("click", openNodeModal);
$("node-modal-close").addEventListener("click", closeNodeModal);
$("node-modal").addEventListener("click", (event) => { if (event.target === $("node-modal")) closeNodeModal(); });

$("node-installer-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("generate-installer");
  button.disabled = true;
  button.textContent = "Building installer…";
  $("node-form-error").textContent = "";
  try {
    const result = await createNodeInstaller({
      node_name: $("node-name").value || null,
      node_role: $("node-role").value,
      download_expires_minutes: 60,
    });
    $("node-installer-form").hidden = true;
    $("installer-result").hidden = false;
    $("installer-download").href = result.download_url;
    $("installer-download").download = result.filename;
    $("installer-command").textContent = result.one_command;
    $("installer-expiry").textContent = `Download link expires ${formatDate(result.expires_at)}. Enrollment is one-use.`;
  } catch (error) {
    $("node-form-error").textContent = error.message || "Installer generation failed.";
  } finally {
    button.disabled = false;
    button.textContent = "Generate installer";
  }
});

$("copy-command").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("installer-command").textContent);
  $("copy-command").textContent = "Copied";
  setTimeout(() => { $("copy-command").textContent = "Copy"; }, 1200);
});


function openVPSModal() { $("vps-form-error").textContent = ""; $("vps-modal").hidden = false; }
function closeVPSModal() { $("vps-modal").hidden = true; }
$("create-vps-button").addEventListener("click", openVPSModal);
$("vps-modal-close").addEventListener("click", closeVPSModal);
$("vps-modal").addEventListener("click", (event) => { if (event.target === $("vps-modal")) closeVPSModal(); });
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { closeNodeModal(); closeVPSModal(); }
});
$("vps-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("vps-form-error").textContent = "";
  try {
    await createVPSInstance({
      name: $("vps-name").value,
      image: $("vps-image").value,
      vcpu: Number($("vps-cpu").value),
      memory_mb: Number($("vps-memory").value),
      disk_gb: Number($("vps-disk").value),
    });
    closeVPSModal();
    await refreshDashboard();
  } catch (error) { $("vps-form-error").textContent = error.message || "VPS creation failed."; }
});
$("vps-body").addEventListener("click", async (event) => {
  const button = event.target.closest(".vps-action");
  if (!button) return;
  button.disabled = true;
  try { await vpsAction(button.dataset.id, button.dataset.action); await refreshDashboard(); }
  finally { button.disabled = false; }
});

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
    currentAccess = await loadAccess();
    $("add-node-button").hidden = !(currentAccess.is_superuser || currentAccess.permissions.includes("node_installers.manage") || currentAccess.permissions.includes("*"));
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
    currentAccess = await loadAccess();
    $("user-label").textContent = user.username || user.email || "Signed in";
    $("add-node-button").hidden = !(currentAccess.is_superuser || currentAccess.permissions.includes("node_installers.manage") || currentAccess.permissions.includes("*"));
    showDashboard();
    await refreshDashboard();
  } catch {
    clearSession();
    showLogin("Sign in to continue.");
  }
}

bootstrap();
