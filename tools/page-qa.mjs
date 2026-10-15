#!/usr/bin/env node
/*
Measure pages in a real headless browser at phone and laptop width.

Why this exists
---------------
Screenshots catch layout problems by eye, but miss a headline that runs 4px
off the right edge or an image that 404s below the fold. This script loads
each page in the Playwright headless Chromium, through the Chrome DevTools
Protocol, and reports measured facts.

Usage
-----
  node tools/page-qa.mjs URL [URL ...]
  node tools/page-qa.mjs --widths 390,1280 URL

The local server must already be running (python3 -m http.server 8000).

For each URL and width it reports:
  overflow    page wider than the viewport (horizontal scroll), with the widest
              offending elements
  images      <img> elements that failed to load
  h1 lines    how many lines the hero headline wraps to, and any single-word line
  tabs        hero tab labels and which one is selected
  footer      the footer's background colour
  robots      the robots meta tag (previews should be noindex)
Exit code 1 when any page overflows or has a broken image.
*/
import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
let widths = [390, 1280];
const urls = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--widths") widths = args[++i].split(",").map(Number);
  else urls.push(args[i]);
}
if (!urls.length) {
  console.error("usage: node tools/page-qa.mjs [--widths 390,1280] URL [URL ...]");
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

const PORT = 9333;
const chrome = spawn(findChrome(), [
  "--headless", "--disable-gpu", "--hide-scrollbars",
  `--remote-debugging-port=${PORT}`, "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function cdpTarget() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
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

// Runs inside the page. Scrolls through once so lazy images load, then measures.
const MEASURE = `(async () => {
  const H = document.documentElement.scrollHeight;
  for (let y = 0; y < H; y += 600) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 40)); }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 400));
  const vw = document.documentElement.clientWidth;
  const sw = document.documentElement.scrollWidth;
  const wide = [];
  if (sw > vw) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1 && r.width > 0 && getComputedStyle(el).position !== 'fixed') {
        wide.push((el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '')).slice(0, 70) + ' right=' + Math.round(r.right));
      }
    }
  }
  const broken = [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.getAttribute('src')).map(i => i.getAttribute('src'));
  const h1 = document.querySelector('h1');
  let h1info = null;
  if (h1) {
    const range = document.createRange(); range.selectNodeContents(h1);
    const tops = new Map();
    const walker = document.createTreeWalker(h1, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const words = node.textContent.split(/(\\s+)/);
      let offset = 0;
      for (const w of words) {
        if (w.trim()) {
          const rr = document.createRange(); rr.setStart(node, offset); rr.setEnd(node, offset + w.length);
          const rect = rr.getClientRects()[0];
          if (rect) { const k = Math.round(rect.top); tops.set(k, (tops.get(k) || []).concat(w)); }
        }
        offset += w.length;
      }
    }
    const lines = [...tops.entries()].sort((a, b) => a[0] - b[0]).map(e => e[1].join(' '));
    h1info = { lines: lines.length, lone: lines.filter(l => !/\\s/.test(l.trim())), text: lines };
  }
  const tabs = [...document.querySelectorAll('[role=tab]')].slice(0, 4).map(t => t.textContent.trim() + (t.getAttribute('aria-selected') === 'true' ? '*' : ''));
  const footer = document.querySelector('footer');
  const robots = document.querySelector('meta[name=robots]');
  return JSON.stringify({ vw, sw, wide: wide.slice(0, 6), broken, h1: h1info, tabs,
    footer: footer ? getComputedStyle(footer).backgroundColor : null,
    robots: robots ? robots.content : null });
})()`;

async function main() {
  const c = connect(await cdpTarget());
  await c.opened;
  await c.send("Page.enable");
  await c.send("Runtime.enable");
  let failed = false;
  for (const url of urls) {
    for (const w of widths) {
      await c.send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: w < 600 });
      const loaded = new Promise((r) => c.on((m) => m.method === "Page.loadEventFired" && r()));
      await c.send("Page.navigate", { url });
      await Promise.race([loaded, sleep(15000)]);
      await sleep(800);
      const res = await c.send("Runtime.evaluate", { expression: MEASURE, awaitPromise: true, returnByValue: true });
      const d = JSON.parse(res.result.value);
      const over = d.sw > d.vw;
      if (over || d.broken.length) failed = true;
      console.log(`\n${url} @ ${w}px`);
      console.log(`  overflow: ${over ? `YES (${d.sw}px wide in ${d.vw}px)` : "no"}`);
      d.wide.forEach((x) => console.log(`    ${x}`));
      console.log(`  broken images: ${d.broken.length ? d.broken.join(", ") : "none"}`);
      if (d.h1) console.log(`  h1: ${d.h1.lines} lines${d.h1.lone.length ? `, LONE WORD: ${d.h1.lone.join(" | ")}` : ""}  [${d.h1.text.join(" / ")}]`);
      console.log(`  tabs: ${d.tabs.length ? d.tabs.join(", ") : "none"}`);
      console.log(`  footer: ${d.footer}   robots: ${d.robots}`);
    }
  }
  c.ws.close();
  return failed;
}

main()
  .then((failed) => { chrome.kill(); process.exit(failed ? 1 : 0); })
  .catch((e) => { console.error(e); chrome.kill(); process.exit(2); });
