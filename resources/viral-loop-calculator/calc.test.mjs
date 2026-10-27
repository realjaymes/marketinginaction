// Run: node resources/viral-loop-calculator/calc.test.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const VLC = require("./calc.js");

const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log("PASS " + name); };

test("1. N 1000, K 1.5, cycle 7, period 28 -> 4 rounds, total 13,188", () => {
  const r = VLC.project({ n: 1000, k: 1.5, cycle: 7, period: 28 });
  assert.equal(r.rounds, 4);
  close(r.total, 13187.5);
  assert.equal(Math.round(r.total), 13188);
  assert.equal(r.eventual, null);
  assert.equal(r.growing, true);
});

test("2. N 1000, K 1.2, cycle 1, period 28 -> 28 rounds, total 984,068", () => {
  const r = VLC.project({ n: 1000, k: 1.2, cycle: 1, period: 28 });
  assert.equal(r.rounds, 28);
  assert.equal(Math.round(r.total), 984068);
});

test("3. N 1000, K 0.5 -> eventual 2,000; cost 1,000 (NGN) -> 500 per user", () => {
  const r = VLC.project({ n: 1000, k: 0.5, cycle: 7, period: 28, cost: 1000 });
  close(r.eventual, 2000);
  close(r.effectiveCost, 500);
});

test("3b. K 0.6, cost $5 (USD, the page default) -> $2 per user", () => {
  const r = VLC.project({ n: 1000, k: 0.6, cycle: 7, period: 28, cost: 5 });
  close(r.effectiveCost, 2);
});

test("4. N 100, K 0.6 -> eventual 250", () => {
  const r = VLC.project({ n: 100, k: 0.6, cycle: 7, period: 28 });
  close(r.eventual, 250);
});

test("5. Measure: 200 users, 600 invites, 120 new -> 3 invites, 20% join, K 0.6", () => {
  const m = VLC.measure(200, 600, 120);
  close(m.invitesPerUser, 3);
  close(m.joinRatePct, 20);
  close(m.k, 0.6);
});

test("extra: default invites 5 x join 30% -> K 1.5", () => {
  close(VLC.kFromRate(5, 30), 1.5);
});

test("extra: decimal cycle floors correctly (period 28, cycle 3.5 -> 8 rounds)", () => {
  assert.equal(VLC.project({ n: 10, k: 1, cycle: 3.5, period: 28 }).rounds, 8);
});

test("extra: period shorter than one cycle -> 0 rounds, total = N", () => {
  const r = VLC.project({ n: 500, k: 2, cycle: 7, period: 5 });
  assert.equal(r.rounds, 0);
  assert.equal(r.total, 500);
});

test("6. Logged events: 200 users, 600 invites, 300 visits, 120 new", () => {
  const r = VLC.logged(200, "", 600, 300, 120);
  close(r.invitesPerUser, 3);
  close(r.openRate, 0.5);
  close(r.visitToJoin, 0.4);
  close(r.joinRate, 0.2);
  close(r.k, 0.6);
  assert.equal(r.weakest, "open");
  assert.equal(r.clicksPerUser, undefined);
});

test("7. Logged events with share clicks: 200 users, 400 clicks -> 2 per user, 1.5 invites per click", () => {
  const r = VLC.logged(200, 400, 600, 300, 120);
  close(r.clicksPerUser, 2);
  close(r.invitesPerClick, 1.5);
});

test("8. Logged events: weakest step is the join when most visits do not join", () => {
  assert.equal(VLC.logged(100, "", 100, 90, 10).weakest, "join");
});

test("9. Compare: A K 1.2 / 1 day vs B K 1.5 / 7 days, 1000 users, 28 days", () => {
  const c = VLC.compare(1000, { k: 1.2, cycle: 1 }, { k: 1.5, cycle: 7 }, 28);
  assert.equal(Math.round(c.a.total), 984068);
  assert.equal(Math.round(c.b.total), 13188);
  assert.equal(c.larger, "A");
  assert.equal(Math.round(c.ratio), 75);
  const A = [16499, 72035, 271031, 984068], B = [2500, 4750, 8125, 13188];
  c.checkpoints.forEach((p, i) => {
    assert.equal(p.day, [7, 14, 21, 28][i]);
    assert.equal(Math.round(p.a), A[i]);
    assert.equal(Math.round(p.b), B[i]);
  });
});

test("10. Compare: no checkpoints unless the period is 28 days", () => {
  assert.equal(VLC.compare(1000, { k: 1.2, cycle: 1 }, { k: 1.5, cycle: 7 }, 30).checkpoints, null);
});

test("11. Retention: 500 new, 200 / 100 / 50 back -> 40% / 20% / 10%", () => {
  const r = VLC.retention(500, 200, 100, 50);
  close(r.d1, 40); close(r.d7, 20); close(r.d30, 10);
});

console.log(`\n${passed} tests passed`);
