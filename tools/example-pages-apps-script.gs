/**
 * Backend for the example customer pages at /acquisition/[niche]/example/.
 *
 * Lives as a container-bound Apps Script on the "MIA Acquisition View Leads"
 * Google Sheet (Extensions > Apps Script). This file is the source of truth;
 * paste it into the editor when it changes and redeploy the existing web app
 * (Deploy > Manage deployments > edit > New version) so the URL stays the same.
 *
 * What it does
 *   setup()            creates the "Demo submissions" tab with its headers. Safe to rerun.
 *   doPost(e)          the web app endpoint. Each example-page form posts JSON here
 *                      and it appends one row to "Demo submissions". No email alerts.
 *   doGet()            health check: open the web app URL and it says ok.
 *   swapExampleUrls()  points every niche tab's Page URL at that niche's example page,
 *                      keeping the row's existing query string (or building one from the
 *                      UTM columns), so a prospect who clicks a row lands on the page
 *                      that "produced" it. Safe to rerun.
 *
 * Deployment: Deploy > New deployment > Web app, Execute as: Me, Who has access: Anyone.
 * The /exec URL goes into ENDPOINT in tools/build-example-pages.py, then rebuild the pages.
 */

var TAB = 'Demo submissions';
var HEADERS = ['Timestamp', 'Niche', 'Business', 'Name', 'Phone', 'Email', 'ZIP',
  'Answer 1', 'Answer 2', 'Answer 3', 'Answer 4', 'Best time', 'City', 'Page URL',
  'UTM Source', 'UTM Medium', 'UTM Campaign'];

// Sheet tab name -> page slug on marketinginaction.xyz/acquisition/[slug]/example/
var SLUGS = {
  'Home Care': 'home-care', 'ADU Builders': 'adu-builders', 'Basement Waterproofing': 'basement-waterproofing',
  'Electrical': 'electrical', 'Excavation & Septic': 'excavation-septic', 'Fencing': 'fencing',
  'Garage Door': 'garage-door', 'Garage Floor Epoxy': 'garage-floor-epoxy', 'General Contracting': 'general-contracting',
  'HVAC Install': 'hvac', 'Handyman': 'handyman', 'Hearing Aid Practices': 'hearing-aid',
  'Home Cleaning': 'home-cleaning', 'Junk Removal': 'junk-removal', 'Landscaping': 'landscaping',
  'Medspa': 'medspa', 'Moving Services': 'moving', 'Painting': 'painting', 'Pest Control': 'pest-control',
  'Pet Waste Removal': 'pet-waste-removal', 'Plumbing': 'plumbing', 'Pool Service': 'pool-service',
  'Pressure Washing': 'pressure-washing', 'Restaurants': 'restaurants', 'Roofing': 'roofing',
  'Spray Foam Insulation': 'spray-foam', 'Waste Management': 'waste-management', 'Water Treatment': 'water-treatment'
};

function setup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(TAB) || ss.insertSheet(TAB);
  sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
  sh.setFrozenRows(1);
  // Plain text after the timestamp, so phone numbers and ZIPs like 02134 keep their digits.
  sh.getRange(1, 2, sh.getMaxRows(), HEADERS.length - 1).setNumberFormat('@');
  return 'ok';
}

// Cap length and stop a value starting with = + - @ from running as a formula.
function clean_(v) {
  var s = String(v == null ? '' : v).slice(0, 300);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

// Phone numbers and ZIPs are stored as text, so 02134 keeps its leading zero.
function text_(v) {
  var s = clean_(v);
  return s && s.charAt(0) !== "'" ? "'" + s : s;
}

function doPost(e) {
  var d = {};
  try { d = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) { return out_({ ok: false }); }
  if (d.company) return out_({ ok: true }); // honeypot field filled: a bot
  if (!d.name || !d.phone) return out_({ ok: false });
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TAB);
    if (!sh) { setup(); sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TAB); }
    sh.appendRow([new Date(), clean_(d.niche), clean_(d.business), clean_(d.name), text_(d.phone),
      clean_(d.email), text_(d.zip), clean_(d.answer1), clean_(d.answer2), clean_(d.answer3),
      clean_(d.answer4), clean_(d.bestTime), clean_(d.city), clean_(d.pageUrl), clean_(d.utmSource),
      clean_(d.utmMedium), clean_(d.utmCampaign)]);
  } finally {
    lock.releaseLock();
  }
  return out_({ ok: true });
}

function doGet() {
  return out_({ ok: true, tab: TAB });
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// "Katy, TX 77494" -> "Katy". Returns '' when there is no town name.
function town_(v) {
  var s = String(v || '').replace(/\s*\d{5}(-\d{4})?\s*$/, '').replace(/,\s*[A-Z]{2}\s*$/, '').trim();
  return /[A-Za-z]/.test(s) ? s : '';
}

function swapExampleUrls() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var report = [];
  Object.keys(SLUGS).forEach(function (tab) {
    var sh = ss.getSheetByName(tab);
    if (!sh || sh.getLastRow() < 2) { report.push(tab + ': skipped'); return; }
    var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (h) { return String(h).trim(); });
    var col = function (name) { return head.indexOf(name); };
    var cUrl = col('Page URL'), cSrc = col('UTM Source'), cMed = col('UTM Medium'), cCmp = col('UTM Campaign'), cTown = col('Town/ZIP');
    if (cUrl < 0) { report.push(tab + ': no Page URL column'); return; }
    var n = sh.getLastRow() - 1;
    var rows = sh.getRange(2, 1, n, sh.getLastColumn()).getValues();
    var urls = rows.map(function (r) {
      var base = 'https://marketinginaction.xyz/acquisition/' + SLUGS[tab] + '/example/';
      // Keep the row's own query string (fbclid, utm_id and the rest) and swap only the address.
      var old = String(r[cUrl] || '');
      var qi = old.indexOf('?');
      if (qi >= 0 && qi < old.length - 1) return [base + old.slice(qi)];
      var p = [];
      if (cSrc >= 0 && r[cSrc]) p.push('utm_source=' + encodeURIComponent(r[cSrc]));
      if (cMed >= 0 && r[cMed]) p.push('utm_medium=' + encodeURIComponent(r[cMed]));
      if (cCmp >= 0 && r[cCmp]) p.push('utm_campaign=' + encodeURIComponent(r[cCmp]));
      var town = cTown >= 0 ? town_(r[cTown]) : '';
      if (town) p.push('city=' + encodeURIComponent(town));
      return [base + (p.length ? '?' + p.join('&') : '')];
    });
    sh.getRange(2, cUrl + 1, n, 1).setValues(urls);
    report.push(tab + ': ' + n + ' rows');
  });
  Logger.log(report.join('\n'));
  return report;
}
