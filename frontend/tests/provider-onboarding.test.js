import test from "node:test";
import assert from "node:assert/strict";
import { apiUrl } from "../src/api.js";

test("provider API path remains same-origin by default", () => {
  assert.equal(apiUrl("/api/v1/provider/node-installers", ""), "/api/v1/provider/node-installers");
});
