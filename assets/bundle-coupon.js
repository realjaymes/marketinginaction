/* MIA — Online Marketing Bundle "pay-the-difference" upgrade coupon.
 *
 * Single source of truth for the single-workshop → Mentorship upgrade offer.
 * A ₦15,000-workshop buyer gets their ₦15,000 credited toward the ₦45,000
 * Mentorship, so they finish at the same ₦45,000 total a direct bundle buyer pays.
 *
 * ── To rotate / end the coupon ────────────────────────────────────────────
 *   Edit BUNDLE_COUPON below (code, discount, endDate) AND create the matching
 *   fixed-amount coupon in Selar on product `onlinemarketingbundle`. Rotate the
 *   code + endDate each month, aligned to the ₦5,000 price bump.
 *
 * ── The "no expired banner" rule ──────────────────────────────────────────
 *   This is progressive enhancement. The pages' DEFAULT HTML is the normal
 *   full-price Mentorship offer. This script UPGRADES it to the coupon offer
 *   ONLY while the coupon window is open. Past endDate — or if the code is
 *   blanked, or if JS fails — the pages silently show the full-price offer.
 *   No "expired" message, no countdown-to-zero flip. Ever.
 *
 * ── Two surfaces, one script ──────────────────────────────────────────────
 *   1. Single-workshop THANK-YOU pages: any [data-bundle-upsell] block is
 *      rewritten to the pay-the-difference offer (per-page copy lives in
 *      data-coupon-headline / data-coupon-body on that block).
 *   2. The BUNDLE sales page: a visitor who arrives with ?coupon=<code> that
 *      matches the active coupon sees a credit banner, and the code is appended
 *      to every Selar buy link (before &email=, so the prefill modal preserves
 *      it) and reflected in the button price.
 *
 * Net price = base − discount, where base prefers MIA_PRICES.onlinemarketingbundle
 * (loaded from /assets/prices.js on the thank-you pages) and falls back to the
 * constant below on pages that don't load prices.js (the bundle page). Keep the
 * fallback in sync with /assets/prices.js when you bump the base price.
 *
 * NOTE on Selar: the visible code is a deliberate belt-and-suspenders. Even if
 * Selar's cart flow does not auto-apply the URL coupon, the buyer sees the code
 * and can type it at checkout (mirrors the DIME DIMEWEBINAR pattern).
 */
(function () {
  var BUNDLE_COUPON = {
    code: 'UPGRADE15',
    discount: 15000,                        // fixed ₦ off — drives net = base − discount
    endDate: '2026-08-01T00:00:00+01:00'    // WAT; monthly, aligned to the price bump
  };
  var BASE_FALLBACK = 45000;                // keep in sync with /assets/prices.js onlinemarketingbundle
  var VALUE_ANCHOR = 255000;                // bundle page "total value if purchased separately" — drives the savings %

  window.BUNDLE_COUPON = BUNDLE_COUPON;

  function isActive() {
    if (!BUNDLE_COUPON || !BUNDLE_COUPON.code) return false;
    var end = Date.parse(BUNDLE_COUPON.endDate);
    if (isNaN(end)) return false;
    return Date.now() < end;
  }
  window.miaBundleCouponActive = isActive;

  function naira(n) {
    return window.miaFormatNaira ? window.miaFormatNaira(n) : '₦' + Number(n).toLocaleString('en-NG');
  }
  function basePrice() {
    if (window.MIA_PRICES && window.MIA_PRICES.onlinemarketingbundle) {
      return window.MIA_PRICES.onlinemarketingbundle;
    }
    return BASE_FALLBACK;
  }
  function netPrice() {
    return Math.max(0, basePrice() - BUNDLE_COUPON.discount);
  }

  // ── Surface 1: single-workshop thank-you pages ─────────────────────────
  function enhanceThankYou() {
    var block = document.querySelector('[data-bundle-upsell]');
    if (!block || !isActive()) return;      // default full-price HTML stays

    var code = BUNDLE_COUPON.code;
    var headline = block.getAttribute('data-coupon-headline');
    var body = block.getAttribute('data-coupon-body');

    var h2 = block.querySelector('h2');
    if (h2 && headline) h2.textContent = headline;

    var desc = block.querySelector('p:not(.price-line)');
    if (desc && body) desc.textContent = body;

    var priceLine = block.querySelector('.price-line');
    if (priceLine) {
      priceLine.innerHTML =
        '<s>' + naira(basePrice()) + '</s> ' + naira(netPrice()) +
        ' <span style="font-weight:600;color:var(--text-muted,#6b6470);">— your ' +
        naira(BUNDLE_COUPON.discount) + ' applied</span>';
    }

    var cta = block.querySelector('a.btn');
    if (cta) {
      var chip = document.createElement('div');
      chip.style.cssText = 'margin:0 0 16px;font-size:0.9rem;font-weight:700;color:var(--primary-dark,#1c1422);';
      chip.innerHTML = 'Use code <strong style="letter-spacing:0.06em;background:var(--mia-accent,#f1de71);padding:2px 8px;border-radius:6px;">' + code + '</strong> at checkout';
      cta.parentNode.insertBefore(chip, cta);
      cta.setAttribute('href', '/academy/sme/bundle/?coupon=' + encodeURIComponent(code));
      cta.innerHTML = 'Apply my ' + naira(BUNDLE_COUPON.discount) + ' discount to the bundle &rarr;';
    }
  }

  // ── Surface 2: the bundle sales page ───────────────────────────────────
  function getParam(name) {
    var m = new RegExp('[?&]' + name + '=([^&]+)').exec(window.location.search);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function enhanceBundlePage() {
    var links = document.querySelectorAll('a[href*="selar.com/onlinemarketingbundle"]');
    if (!links.length) return;

    var supplied = getParam('coupon');
    if (!supplied || !isActive() || supplied.toUpperCase() !== BUNDLE_COUPON.code.toUpperCase()) return;

    var code = BUNDLE_COUPON.code;
    var baseStr = naira(basePrice());
    var netStr = naira(netPrice());

    for (var i = 0; i < links.length; i++) {
      var href = links[i].getAttribute('href');
      if (href.indexOf('coupon=') === -1) {
        // insert before &email= so the prefill modal (truncates at &email=) keeps it
        href = href.replace('add_to_cart=1', 'add_to_cart=1&coupon=' + encodeURIComponent(code));
        links[i].setAttribute('href', href);
      }
      // reflect the discounted price in any button that shows the base price
      if (links[i].innerHTML.indexOf(baseStr) > -1) {
        links[i].innerHTML = links[i].innerHTML.split(baseStr).join(netStr);
      }
    }

    // rewrite the "price you pay" spots so they never contradict the ₦30,000
    // banner/buttons. strike = struck list + net; net = net only (mid-sentence);
    // savings = recomputed against the value anchor. Value-stack component prices
    // and the ₦255,000 anchor are deliberately left untouched.
    var payEls = document.querySelectorAll('[data-payprice]');
    for (var j = 0; j < payEls.length; j++) {
      var el = payEls[j];
      var mode = el.getAttribute('data-payprice');
      if (mode === 'strike') {
        el.innerHTML = '<s style="opacity:.55;font-weight:inherit;">' + baseStr + '</s> ' + netStr;
      } else if (mode === 'net') {
        el.textContent = netStr;
      } else if (mode === 'savings') {
        var save = Math.max(0, VALUE_ANCHOR - netPrice());
        var pct = Math.round(save / VALUE_ANCHOR * 100);
        el.textContent = 'Save ' + naira(save) + ' (' + pct + '% off)';
      }
    }

    var banner = document.createElement('div');
    banner.setAttribute('data-bundle-coupon-banner', '');
    banner.style.cssText = 'max-width:640px;margin:14px auto 0;padding:14px 18px;border-radius:14px;background:var(--mia-accent-light,#fdf8e8);border:2px solid var(--mia-accent,#f1de71);text-align:center;font-size:0.95rem;line-height:1.5;color:var(--primary-dark,#1c1422);';
    banner.innerHTML =
      '<strong>Your ' + naira(BUNDLE_COUPON.discount) + ' upgrade credit is applied.</strong> ' +
      'You pay <strong>' + netStr + '</strong> at checkout (' + baseStr + ' − ' + naira(BUNDLE_COUPON.discount) +
      ') with code <strong style="letter-spacing:0.06em;">' + code + '</strong>.';

    var anchor = document.getElementById('pricing');
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(banner, anchor);
    } else {
      document.body.insertBefore(banner, document.body.firstChild);
    }
  }

  function run() {
    try { enhanceThankYou(); } catch (e) {}
    try { enhanceBundlePage(); } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
