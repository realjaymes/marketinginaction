#!/usr/bin/env node
/*
Take a true-width screenshot of a page in the Playwright headless Chromium.

Why this exists
---------------
`chrome-headless-shell --screenshot --window-size=390,...` cannot open a window
narrower than about 500px, so its "phone" shots are really wider layouts, and
pages that scroll on load come out blank at the top. This script sets the
viewport through the DevTools protocol, the way tools/page-qa.mjs does, scrolls
to the top, and captures from y=0.

Usage
-----
  node tools/page-shot.mjs URL OUT.png [--width 390] [--height 2400] [--top 0 | --at "CSS selector"] [--click "CSS selector"]...

--click runs before the capture, in order, so a tab or channel can be switched
first (for example --click '[data-channel="tiktok"]'). --top starts the capture that many
pixels down the page, and --at starts it 20px above an element. The local server must
already be running (python3 -m http.server 8000).
*/
import { spawn } from "node:child_process";
import { homedir, tmpdir } from "node:os";
import { existsSync, readdirSync, readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
let width = 390, height = 2400, top = 0, at = null;
const clicks = [], pos = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--width") width = Number(args[++i]);
  else if (args[i] === "--height") height = Number(args[++i]);
  else if (args[i] === "--click") clicks.push(args[++i]);
  else if (args[i] === "--top") top = Number(args[++i]);
  else if (args[i] === "--at") at = args[++i];
  else pos.push(args[i]);
}
const [url, out] = pos;
if (!url || !out) {
  console.error('usage: node tools/page-shot.mjs URL OUT.png [--width 390] [--height 2400] [--click "selector"]');
  process.exit(2);
}

function findChrome() {
  const base = join(homedir(), "Library/Caches/ms-playwright");
  for (const dir of readdirSync(base).filter((d) => d.startsWith("chromium_headless_shell"))) {
    for (const sub of readdirSync(join(base, dir))) {
      const bin = join(base, dir, sub, "chrome-headless-shell");
      if (existsSync(bin)) return bin;
    }
  }
  throw new Error("Playwright chromium_headless_shell not found under " + base);
}

const profile = mkdtempSync(join(tmpdir(), "page-shot-"));
const chrome = spawn(findChrome(), [
  "--headless", "--disable-gpu", "--hide-scrollbars",
  `--user-data-dir=${profile}`, "--remote-debugging-port=0", "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function cdpTarget() {
  for (let i = 0; i < 50; i++) {
    try {
      const port = Number(readFileSync(join(profile, "DevToolsActivePort"), "utf8").split("\n")[0]);
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("Chrome DevTools endpoint did not come up");
}

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else listeners.forEach((fn) => fn(msg));
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const n = ++id;
      pending.set(n, { resolve, reject });
      ws.send(JSON.stringify({ id: n, method, params }));
    });
  const opened = new Promise((r) => (ws.onopen = r));
  return { ws, send, opened, on: (fn) => listeners.push(fn) };
}

async function main() {
  const c = connect(await cdpTarget());
  await c.opened;
  await c.send("Page.enable");
  await c.send("Runtime.enable");
  await c.send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 600 });
  const loaded = new Promise((r) => c.on((m) => m.method === "Page.loadEventFired" && r()));
  await c.send("Page.navigate", { url });
  await Promise.race([loaded, sleep(15000)]);
  await sleep(800);
  for (const sel of clicks) {
    const r = await c.send("Runtime.evaluate", {
      expression: `(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false; el.click(); return true; })()`,
      returnByValue: true,
    });
    if (!r.result.value) console.error(`no element for --click ${sel}`);
    await sleep(400);
  }
  await c.send("Runtime.evaluate", {
    expression: "document.documentElement.style.scrollBehavior='auto'; window.scrollTo(0,0)",
  });
  await sleep(500);
  if (at) {
    const r = await c.send("Runtime.evaluate", {
      expression: `(() => { const el = document.querySelector(${JSON.stringify(at)}); return el ? Math.max(0, Math.round(el.getBoundingClientRect().top + scrollY) - 20) : -1; })()`,
      returnByValue: true,
    });
    if (r.result.value < 0) console.error(`no element for --at ${at}`); else top = r.result.value;
  }
  const shot = await c.send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: true,
    clip: { x: 0, y: top, width, height, scale: 1 },
  });
  writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.log(`${out} (${width}x${height} from y=${top})`);
  c.ws.close();
}

main()
  .then(() => done(0))
  .catch((e) => { console.error(e.message); done(1); });

function done(code) {
  chrome.kill();
  setTimeout(() => { rmSync(profile, { recursive: true, force: true }); process.exit(code); }, 300);
}
