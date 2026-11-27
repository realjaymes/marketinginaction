// Checks the gap between a button and the small line of text straight under it ("Secure payment via Selar",
// "Instant access the moment you pay.") on MIA pages, at phone (390px) and desktop (1280px) width. The rule is the
// Wholesome Girlies one: 14px from a button to the note under it, with a 2px allowance.
//
// A "note" is the next visible block under the button's wrapper that holds a short line of text (160 characters
// or fewer). Anything further than 40px away is treated as the next section, not a note, and is not checked.
//
// Needs the site running locally (python3 -m http.server 8000) and puppeteer-core, the same copy the Wholesome
// Girlies check uses:
//   NODE_PATH=/tmp/wgog/node_modules node tools/check-cta-spacing.js                      every page
//   NODE_PATH=/tmp/wgog/node_modules node tools/check-cta-spacing.js academy/dime/index.html   given pages only
// Options: MIA_PORT=8000, CTA_TOL=2, CTA_REPORT=1 (print every gap and always exit 0).
// The pre-push hook runs it on the pages a push changes, and skips it when the site or puppeteer is not available.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const PORT = process.env.MIA_PORT || '8000';
const BASE = 'http://localhost:' + PORT;
const WANT = 14;
const TOL = +(process.env.CTA_TOL || 2);
const NEAR = 40;
const REPORT = !!process.env.CTA_REPORT;
const SKIP_DIRS = new Set(['node_modules', 'tools', 'data', 'assets', 'images', 'img', 'css', 'js', 'fonts', 'options', 'example']);

let puppeteer;
try { puppeteer = require('puppeteer-core'); } catch (e) {
  console.log('check-cta-spacing: puppeteer-core not found, skipped (set NODE_PATH, see the top of this file).');
  process.exit(0);
}

function allPages() {
  const out = [];
  (function walk(dir) {
    for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
      if (f.name.startsWith('.') || f.name.startsWith('_') || SKIP_DIRS.has(f.name)) continue;
      const full = path.join(dir, f.name);
      if (f.isDirectory()) walk(full);
      else if (f.name === 'index.html') out.push(path.relative(ROOT, full).split(path.sep).join('/'));
    }
  })(ROOT);
  return out.sort();
}

function toUrl(file) {
  return BASE + '/' + file.replace(/index\.html$/, '');
}

// Runs inside the page.
function measure(near) {
  const BTN = 'a.btn, button.btn, a.button, a.button-primary, button[type="submit"], input[type="submit"]';
  const SKIP = 'header, nav, footer, .sticky-bar, [class*="modal"], [class*="popup"], [aria-hidden="true"]';
  const cs = (e) => getComputedStyle(e);
  const shown = (e) => { const r = e.getBoundingClientRect(); const c = cs(e); return r.width > 0 && r.height > 0 && c.visibility !== 'hidden' && c.display !== 'none' && c.opacity !== '0'; };
  const onlyButtons = (e) => { const b = [...e.querySelectorAll(BTN)].filter(shown); const t = (x) => (x.innerText || x.value || '').replace(/\s+/g, ''); return b.length > 0 && t(e) === b.map(t).join(''); };
  const found = [];
  const done = new Set();
  document.querySelectorAll(BTN).forEach((el) => {
    if (!shown(el) || el.closest(SKIP)) return;
    // climb to the wrapper that holds only buttons, so a row of buttons is measured once
    let u = el;
    while (u.parentElement && u.parentElement !== document.body) {
      const p = u.parentElement;
      if (p.matches('section, main, article, form, li') || [...p.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) break;
      if ([...p.children].some((c) => c !== u && shown(c) && cs(c).position !== 'absolute' && !onlyButtons(c))) break;
      u = p;
    }
    if (done.has(u)) return;
    done.add(u);
    let n = u.nextElementSibling;
    while (n && (!shown(n) || /^(SCRIPT|STYLE|TEMPLATE|NOSCRIPT|BR)$/.test(n.tagName) || ['absolute', 'fixed'].includes(cs(n).position))) n = n.nextElementSibling;
    if (!n || onlyButtons(n) || n.matches('section, header, footer, nav, form, ul, ol, table, img, picture, video, iframe')) return;
    const text = (n.innerText || '').trim();
    if (!text || text.length > 160) return;
    const gap = Math.round((n.getBoundingClientRect().top - u.getBoundingClientRect().bottom) * 10) / 10;
    if (gap < -1 || gap > near) return;
    found.push({ gap, button: (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 40), note: text.replace(/\s+/g, ' ').slice(0, 50) });
  });
  return found;
}

(async () => {
  try { await fetch(BASE + '/'); } catch (e) {
    console.log('check-cta-spacing: the site is not running on ' + BASE + ', skipped (python3 -m http.server ' + PORT + ').');
    process.exit(0);
  }
  const files = process.argv.slice(2).length ? process.argv.slice(2).filter((f) => !f.includes('/options/')) : allPages();
  if (!files.length) process.exit(0);
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', args: ['--no-first-run'] });
  const bad = [], errors = [];
  let gaps = 0;
  for (const file of files) {
    for (const width of [390, 1280]) {
      const page = await browser.newPage();
      try {
        await page.setViewport({ width, height: 900 });
        const res = await page.goto(toUrl(file), { waitUntil: 'networkidle2', timeout: 30000 });
        if (!res || res.status() >= 400) throw new Error('HTTP ' + (res ? res.status() : 'no response'));
        await new Promise((r) => setTimeout(r, 400));
        const found = await page.evaluate(measure, NEAR);
        gaps += found.length;
        found.forEach((f) => {
          const off = Math.abs(f.gap - WANT) > TOL;
          if (REPORT || off) console.log(`${off ? 'OFF ' : 'ok  '} ${file} @${width}  ${f.gap}px  "${f.button}" -> "${f.note}"`);
          if (off) bad.push(f);
        });
      } catch (e) { errors.push(`${file} @${width}: ${e.message}`); }
      finally { await page.close().catch(() => {}); }
    }
  }
  await browser.close().catch(() => {});
  errors.forEach((e) => console.log('could not measure ' + e));
  if (REPORT) process.exit(0);
  if (bad.length) {
    console.log(`\nFAIL  ${bad.length} button note gap(s) are not ${WANT}px (allowance ${TOL}px). Set the note's top margin to ${WANT}px.`);
    process.exit(1);
  }
  console.log(`check-cta-spacing: PASS, ${gaps} button note gap(s) on ${files.length} page(s) are ${WANT}px.`);
})();
