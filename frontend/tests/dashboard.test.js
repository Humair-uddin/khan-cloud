import test from "node:test";
import assert from "node:assert/strict";
import { apiUrl, normalizeApiBase } from "../src/api.js";
import { dashboardSeverity, healthClass, priorityClass } from "../src/dashboard.js";

test("API base normalization preserves same-origin mode", () => {
  assert.equal(normalizeApiBase(""), "");
  assert.equal(normalizeApiBase(" https://cp.example/ "), "https://cp.example");
  assert.equal(apiUrl("/api/v1/operations/dashboard", ""), "/api/v1/operations/dashboard");
});

test("health classes are operationally meaningful", () => {
  assert.equal(healthClass("healthy"), "ok");
  assert.equal(healthClass("failed"), "danger");
  assert.equal(healthClass("installing"), "warning");
});

test("attention priority emphasizes urgent work", () => {
  assert.equal(priorityClass("critical"), "danger");
  assert.equal(priorityClass("normal"), "warning");
  assert.equal(priorityClass("low"), "neutral");
});

test("dashboard severity fails upward", () => {
  assert.equal(dashboardSeverity({counts:{}}), "healthy");
  assert.equal(dashboardSeverity({counts:{stale_nodes:1}}), "attention");
  assert.equal(dashboardSeverity({counts:{failed_nodes:1}}), "critical");
  assert.equal(dashboardSeverity({counts:{urgent_support_cases:1}}), "critical");
});
