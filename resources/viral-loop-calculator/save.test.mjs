// Run: node resources/viral-loop-calculator/save.test.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const S = require("./save.js");

let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log("PASS " + name); };

const URL = "https://marketinginaction.xyz/resources/viral-loop-calculator/";
// The page defaults, the article's compare defaults, and a scored card.
const raw = {
  date: "2026-10-27", url: URL, cur: "$",
  scores: ["2", "1", "0", "2", "1", "2", "2"],
  notes: ["One line retell works", "", "Login wall", "", "", "", ""],
  kmode: "rate", inv: "5", join: "30", kdirect: "1.5",
  lu: "200", lc: "400", li: "600", lv: "300", ln: "120",
  n: "1000", pk: "1.5", cycle: "7", period: "28", cost: "5",
  cn: "1000", cp: "28", ak: "1.2", ac: "1", bk: "1.5", bc: "7",
  rn: "500", r1: "200", r7: "100", r30: "50"
};
const m = S.build(raw);

test("summary starts with the title and date, ends with the URL", () => {
  const t = S.summaryText(m);
  assert.ok(t.startsWith("Viral Loop Calculator results, 2026-10-27"));
  assert.ok(t.endsWith(URL));
});

test("summary holds the scorecard rows, notes, total and the break warning", () => {
  const t = S.summaryText(m);
  assert.ok(t.includes("Premise: 2 of 2. One line retell works"));
  assert.ok(t.includes("Access: 0 of 2. Login wall"));
  assert.ok(t.includes("Total: 10 of 14 (7 of 7 answered)"));
  assert.ok(t.includes("Access is at 0. This breaks the loop on its own, however well the rest scores."));
  assert.ok(!t.includes("below 9"));
});

test("summary holds K, projection, compare and retention", () => {
  const t = S.summaryText(m);
  assert.ok(t.includes("K from your numbers"));
  assert.ok(t.includes("K from your logged events"));
  assert.ok(t.includes("Open rate (visits ÷ invites): 50%"));
  assert.ok(t.includes("Total users after 28 days: 13,188"));
  assert.ok(t.includes("Loop A total: 984,068"));
  assert.ok(t.includes("Loop B total: 13,188"));
  assert.ok(t.includes("about 75 times"));
  assert.ok(t.includes("Day 7: 40%") || t.includes("Day 1: 40%"));
});

test("summary shows eventual total and cost per user when K is below 1", () => {
  const t = S.summaryText(S.build({ ...raw, pk: "0.5", cost: "1000", cur: "₦" }));
  assert.ok(t.includes("Eventual total if the loop runs to the end: 2,000"));
  assert.ok(t.includes("Effective cost per user (₦): 500"));
});

test("summary shows the below 9 warning when the score is low", () => {
  const t = S.summaryText(S.build({ ...raw, scores: ["0", "1", "1", "1", "1", "1", "1"] }));
  assert.ok(t.includes("Your score is below 9 out of 14."));
});

test("summary leaves out retention and logged events when they are empty", () => {
  const t = S.summaryText(S.build({ ...raw, rn: "", r1: "", r7: "", r30: "", lu: "", li: "", lv: "", ln: "", lc: "" }));
  assert.ok(!t.includes("Retention"));
  assert.ok(!t.includes("logged events"));
});

test("CSV has the scorecard rows with questions and notes", () => {
  const c = S.csv(m);
  assert.ok(c.includes("Scorecard\r\nIngredient,Question,Score (0 to 2),Note"));
  assert.ok(c.includes("Premise,Can a stranger retell it in one line after seeing one post?,2,One line retell works"));
  assert.ok(c.includes("Total (out of 14),,10,"));
});

test("CSV has raw numbers for the projection", () => {
  const c = S.csv(m);
  assert.ok(c.includes("13187.5"));
  assert.ok(c.includes("Total users after the period,13188"));
  assert.ok(c.includes("Round,Day,New users,Running total"));
  assert.ok(c.includes("4,28,5062.5,13187.5"));
});

test("CSV compare has 984068 against 13188 and the checkpoints", () => {
  const c = S.csv(m);
  assert.ok(c.includes("Total users after the period,984068,13188"));
  assert.ok(c.includes("Times bigger,74.6"));
  assert.ok(c.includes("7,16499,2500"));
  assert.ok(c.includes("14,72035,4750"));
  assert.ok(c.includes("21,271031,8125"));
  assert.ok(c.includes("28,984068,13188"));
});

test("CSV has K, retention and a final Saved row", () => {
  const c = S.csv(m);
  assert.ok(c.includes("Open rate (%),50"));
  assert.ok(c.includes("Came back on Day 7,100,20"));
  assert.ok(c.trimEnd().endsWith("Saved,2026-10-27," + URL));
});

test("CSV sections are separated by blank rows and parse back into a grid", () => {
  const rows = S.csv(m).split("\r\n");
  assert.ok(rows.includes(""));
  const titles = ["Scorecard", "K from your numbers", "K from your logged events", "Projection inputs", "Projection results", "Round by round", "Compare two loops", "Compare checkpoints", "Retention"];
  titles.forEach(t => assert.ok(rows.includes(t), t));
});

test("CSV escapes commas, quotes and keeps the BOM helper", () => {
  const c = S.csv(S.build({ ...raw, notes: ['Has, a comma and "quotes"', "", "", "", "", "", ""] }));
  assert.ok(c.includes('"Has, a comma and ""quotes"""'));
  assert.equal(S.withBom("a").charCodeAt(0), 0xFEFF);
});

test("module CSV holds only that module, and file names follow the date", () => {
  const c = S.csv(m, ["ret"]);
  assert.ok(c.startsWith("Retention"));
  assert.ok(!c.includes("Scorecard"));
  assert.equal(S.filename("all", "2026-10-27"), "viral-loop-results-2026-10-27.csv");
  assert.equal(S.filename("proj", "2026-10-27"), "viral-loop-proj-2026-10-27.csv");
});

console.log(`\n${passed} tests passed`);
