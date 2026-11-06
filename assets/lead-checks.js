/*
 * lead-checks.js: phone, email and ZIP checks for lead forms.
 *
 * Marks fields by data-lc="phone" | "email" | "zip". Each marked field gets a
 * custom validity message, so the page's own step check (checkValidity) stops
 * a bad entry before the form moves on or submits. Email is required only when
 * the input carries the required attribute; an optional email that is filled in
 * is still checked.
 *
 * Phone: a US number, 10 digits or 11 starting with 1, with a real area code
 * and exchange (neither starts with 0 or 1, no N11 area code), and no obvious
 * fakes (one digit repeated, 1234567890, 555-01xx). Formats as (703) 928-1618.
 * Email: a normal address with a real ending; common domain typos (gnail.com,
 * yaho.com, .con, .comp) are caught with a one-tap fix.
 * ZIP: five digits, not 00000.
 *
 * The same file is used by the MIA example pages (/assets/lead-checks.js) and
 * the Pure Care landing page (lead-checks.js in realjaymes/purecare-lp).
 * Keep the two copies identical.
 */
(function () {
  var PHONE_MSG = "Please check your mobile number. We'll call you on it.";
  var EMAIL_EMPTY = 'Please enter your email address.';
  var EMAIL_MSG = 'Please check your email address.';
  var ZIP_MSG = 'Please enter a 5-digit ZIP code.';

  var DOMAIN_FIXES = {
    'gnail.com': 'gmail.com', 'gmial.com': 'gmail.com', 'gmal.com': 'gmail.com',
    'gmai.com': 'gmail.com', 'gmaill.com': 'gmail.com', 'gamil.com': 'gmail.com',
    'gmil.com': 'gmail.com', 'gmail.co': 'gmail.com', 'gmail.cm': 'gmail.com',
    'gmail.om': 'gmail.com', 'gmailcom': 'gmail.com', 'g.mail.com': 'gmail.com',
    'yaho.com': 'yahoo.com', 'yahooo.com': 'yahoo.com', 'yhoo.com': 'yahoo.com',
    'yahoo.co': 'yahoo.com', 'yahho.com': 'yahoo.com', 'tahoo.com': 'yahoo.com',
    'hotmial.com': 'hotmail.com', 'hotmal.com': 'hotmail.com', 'hotmai.com': 'hotmail.com',
    'hotmil.com': 'hotmail.com', 'homail.com': 'hotmail.com', 'hotmail.co': 'hotmail.com',
    'outlok.com': 'outlook.com', 'outloo.com': 'outlook.com', 'outllook.com': 'outlook.com',
    'iclod.com': 'icloud.com', 'icoud.com': 'icloud.com', 'iclould.com': 'icloud.com',
    'icloud.co': 'icloud.com', 'aol.co': 'aol.com', 'comcast.com': 'comcast.net',
    'verizon.com': 'verizon.net', 'att.com': 'att.net'
  };
  var TLD_FIXES = { con: 'com', cmo: 'com', cpm: 'com', vom: 'com', comm: 'com', comp: 'com', coom: 'com', cim: 'com', ocm: 'com', xom: 'com', nte: 'net', ner: 'net', nett: 'net', ogr: 'org', orgg: 'org' };

  function digits(s) { return String(s || '').replace(/\D/g, ''); }

  function phoneDigits(v) {
    var d = digits(v);
    if (d.length === 11 && d.charAt(0) === '1') d = d.slice(1);
    return d;
  }

  function phoneOk(v) {
    var d = phoneDigits(v);
    if (d.length !== 10) return false;
    if (/^[01]/.test(d) || /^[01]/.test(d.slice(3))) return false;   // area code or exchange starts with 0 or 1
    if (d.charAt(1) === '1' && d.charAt(2) === '1') return false;      // N11 codes (211 to 911) are not area codes
    if (/^(\d)\1{9}$/.test(d)) return false;                            // one digit repeated
    if (d === '1234567890' || d === '2345678901') return false;
    if (d.slice(3, 6) === '555' && d.slice(6, 8) === '01') return false; // reserved fictional numbers
    return true;
  }

  function formatPhone(v) {
    var d = phoneDigits(v);
    if (d.length > 10) return d;   // too many digits: leave them as typed so the mistake shows, never trim to a guess
    if (d.length < 4) return d;
    if (d.length < 7) return '(' + d.slice(0, 3) + ') ' + d.slice(3);
    return '(' + d.slice(0, 3) + ') ' + d.slice(3, 6) + '-' + d.slice(6);
  }

  // Returns {ok, msg, fix}: fix is the corrected address when a typo is spotted.
  function checkEmail(v, required) {
    v = String(v || '').trim();
    if (!v) return required ? { ok: false, msg: EMAIL_EMPTY } : { ok: true };
    var m = /^([^\s@]+)@([^\s@]+)$/.exec(v);
    if (!m) return { ok: false, msg: EMAIL_MSG };
    var local = m[1], domain = m[2].toLowerCase().replace(/\.+$/, '');
    var fixed = DOMAIN_FIXES[domain];
    if (!fixed) {
      var parts = domain.split('.');
      var tld = parts[parts.length - 1];
      if (parts.length > 1 && TLD_FIXES[tld]) { parts[parts.length - 1] = TLD_FIXES[tld]; fixed = parts.join('.'); }
    }
    if (fixed && fixed !== domain) {
      var s = local + '@' + fixed;
      return { ok: false, msg: 'Did you mean ' + s + '?', fix: s };
    }
    if (!/^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/.test(domain) || /\.\./.test(local)) return { ok: false, msg: EMAIL_MSG };
    return { ok: true };
  }

  function zipOk(v) { var s = String(v || '').trim(); return /^\d{5}$/.test(s) && s !== '00000'; }

  function hintFor(input) {
    var h = input.nextElementSibling;
    if (h && h.classList && h.classList.contains('lc-hint')) return h;
    h = document.createElement('div');
    h.className = 'lc-hint';
    h.setAttribute('aria-live', 'polite');
    h.style.cssText = 'font-size:.9em;margin:6px 0 2px;line-height:1.35;';
    h.hidden = true;
    input.parentNode.insertBefore(h, input.nextSibling);
    return h;
  }

  function check(input) {
    var kind = input.getAttribute('data-lc'), v = input.value, msg = '';
    if (kind === 'phone') {
      if (v.trim() && !phoneOk(v)) msg = PHONE_MSG;
    } else if (kind === 'zip') {
      if (v.trim() && !zipOk(v)) msg = ZIP_MSG;
    } else if (kind === 'email') {
      var r = checkEmail(v, input.required), hint = hintFor(input);
      msg = r.ok ? '' : (r.fix ? EMAIL_MSG : r.msg);   // the fix itself shows in the hint under the field
      if (r.fix && input.dataset.lcTouched) {
        hint.innerHTML = '';
        hint.appendChild(document.createTextNode('Did you mean '));
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = r.fix;
        b.style.cssText = 'font:inherit;font-weight:700;text-decoration:underline;background:none;border:0;padding:0;color:inherit;cursor:pointer;';
        b.addEventListener('click', function () { input.value = r.fix; check(input); input.focus(); });
        hint.appendChild(b);
        hint.appendChild(document.createTextNode('? Tap to use it.'));
        hint.hidden = false;
      } else {
        hint.hidden = true;
      }
    }
    // Empty required fields keep the browser's own "required" handling.
    if (!v.trim() && kind !== 'email') msg = '';
    input.setCustomValidity(msg);
    return !msg;
  }

  function attach(input) {
    if (input.dataset.lcOn) return;
    input.dataset.lcOn = '1';
    var kind = input.getAttribute('data-lc');
    if (kind === 'phone') {
      input.setAttribute('inputmode', 'tel');
      input.setAttribute('autocomplete', 'tel-national');
      input.addEventListener('input', function (e) {
        var deleting = e.inputType && e.inputType.indexOf('delete') === 0;
        if (!deleting) input.value = formatPhone(input.value);
        check(input);
      });
    } else if (kind === 'zip') {
      input.setAttribute('inputmode', 'numeric');
      input.setAttribute('maxlength', '5');
      input.setAttribute('autocomplete', 'postal-code');
      input.addEventListener('input', function () { input.value = digits(input.value).slice(0, 5); check(input); });
    } else if (kind === 'email') {
      input.setAttribute('autocomplete', 'email');
      input.setAttribute('autocapitalize', 'off');
      input.setAttribute('spellcheck', 'false');
      input.addEventListener('input', function () { check(input); });
    }
    input.addEventListener('blur', function () {
      input.dataset.lcTouched = '1';
      if (kind === 'phone' && phoneOk(input.value)) input.value = formatPhone(input.value);
      if (kind === 'email') input.value = input.value.trim();
      check(input);
    });
    check(input);
  }

  function attachAll(root) {
    (root || document).querySelectorAll('[data-lc]').forEach(attach);
  }

  // The message to show for a field, or '' when the field has no custom problem.
  function msg(input) {
    if (!input || !input.getAttribute || !input.getAttribute('data-lc')) return '';
    input.dataset.lcTouched = '1';
    check(input);
    return input.validationMessage && input.validity.customError ? input.validationMessage : '';
  }

  window.LeadChecks = { attach: attachAll, check: check, msg: msg, phoneOk: phoneOk, checkEmail: checkEmail, zipOk: zipOk, formatPhone: formatPhone };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { attachAll(); });
  else attachAll();
})();
