export const CARD_DEFINITIONS = [
  ["deployments", "Deployments"],
  ["nodes", "Nodes"],
  ["online_nodes", "Online"],
  ["stale_nodes", "Stale"],
  ["failed_nodes", "Failed"],
  ["open_support_cases", "Open cases"],
];

export function healthClass(health = "") {
  if (health === "healthy") return "ok";
  if (["failed", "attention"].includes(health)) return "danger";
  if (["degraded", "installing"].includes(health)) return "warning";
  return "neutral";
}

export function priorityClass(priority = "") {
  if (["critical", "urgent", "high"].includes(priority)) return "danger";
  if (priority === "normal") return "warning";
  return "neutral";
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

export function dashboardSeverity(data) {
  const counts = data?.counts || {};
  if ((counts.failed_nodes || 0) > 0 || (counts.urgent_support_cases || 0) > 0) return "critical";
  if ((counts.attention_nodes || 0) > 0 || (counts.stale_nodes || 0) > 0 || (counts.open_support_cases || 0) > 0) return "attention";
  return "healthy";
}
