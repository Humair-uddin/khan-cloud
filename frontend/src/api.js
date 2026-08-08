const TOKEN_KEY = "khan_cloud_access_token";
const API_BASE_KEY = "khan_cloud_api_base";

export function normalizeApiBase(value = "") {
  return value.trim().replace(/\/+$/, "");
}

export function getApiBase(storage = window.localStorage) {
  return normalizeApiBase(storage.getItem(API_BASE_KEY) || "");
}

export function saveSession(token, apiBase = "", storage = window.localStorage) {
  storage.setItem(TOKEN_KEY, token);
  storage.setItem(API_BASE_KEY, normalizeApiBase(apiBase));
}

export function clearSession(storage = window.localStorage) {
  storage.removeItem(TOKEN_KEY);
  storage.removeItem(API_BASE_KEY);
}

export function getToken(storage = window.localStorage) {
  return storage.getItem(TOKEN_KEY) || "";
}

export function apiUrl(path, apiBase = getApiBase()) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizeApiBase(apiBase)}${cleanPath}`;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail : payload;
    const error = new Error(detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

export async function login(username, password, apiBase = "") {
  const body = new URLSearchParams({ username, password });
  const response = await fetch(apiUrl("/api/v1/auth/login", apiBase), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  return parseResponse(response);
}

export async function authenticatedGet(path, { token = getToken(), apiBase = getApiBase() } = {}) {
  if (!token) throw new Error("Authentication required.");
  const response = await fetch(apiUrl(path, apiBase), {
    headers: { Authorization: `Bearer ${token}` },
  });
  return parseResponse(response);
}

export function loadDashboard(options = {}) {
  return authenticatedGet("/api/v1/operations/dashboard", options);
}

export function loadCurrentUser(options = {}) {
  return authenticatedGet("/api/v1/auth/me", options);
}

export function loadOrganizations(options = {}) {
  return authenticatedGet("/api/v1/organizations", options);
}

export async function createNodeInstaller(payload, { token = getToken(), apiBase = getApiBase() } = {}) {
  if (!token) throw new Error("Authentication required.");
  const response = await fetch(apiUrl("/api/v1/provider/node-installers", apiBase), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export function loadAccess(options = {}) {
  return authenticatedGet("/api/v1/rbac/me", options);
}

export function loadComputeHosts(options = {}) {
  return authenticatedGet("/api/v1/compute/hosts", options);
}

export function loadVPSInstances(options = {}) {
  return authenticatedGet("/api/v1/compute/vps", options);
}

export async function createVPSInstance(payload, { token = getToken(), apiBase = getApiBase() } = {}) {
  if (!token) throw new Error("Authentication required.");
  const response = await fetch(apiUrl("/api/v1/compute/vps", apiBase), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function vpsAction(vpsId, action, { token = getToken(), apiBase = getApiBase() } = {}) {
  const response = await fetch(apiUrl(`/api/v1/compute/vps/${vpsId}/actions`, apiBase), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  return parseResponse(response);
}

export function loadVPSImages(options = {}) { return authenticatedGet("/api/v1/compute/images", options); }
