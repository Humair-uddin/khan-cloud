import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root=path.resolve(import.meta.dirname,"../..");
test("customer portal hides physical host identity",()=>{
  const html=fs.readFileSync(path.join(root,"customer-portal","index.html"),"utf8");
  const js=fs.readFileSync(path.join(root,"customer-portal","portal.js"),"utf8");
  assert.equal(html.includes("node_id"),false);
  assert.equal(js.includes("node_id"),false);
});
test("new VPS ordering remains payment gated",()=>{
  const html=fs.readFileSync(path.join(root,"customer-portal","index.html"),"utf8");
  assert.match(html,/id="new-vps" disabled/);
  assert.match(html,/pricing → payment → provisioning/);
});
