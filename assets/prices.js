/* MIA canonical product prices — single source of truth.
 *
 * Change a price HERE and every page that reads it updates at once.
 * No page should hardcode a price that also lives in this file.
 *
 * Consumers:
 *   - Display: any element with data-price="<slug>" gets its text set to the
 *     formatted Naira price (e.g. ₦45,000). Add data-price-suffix="/mo" for
 *     recurring prices.
 *   - Logic: read window.MIA_PRICES[slug] directly (e.g. a Purchase event value).
 *
 * Slugs match Selar product slugs.
 */
(function () {
  var PRICES = {
    // Business Owner family
    metaadssolutions:            15000,
    tiktokadssolutions:          15000,
    socialoptimizationsolutions: 15000,
    socialautomationsolutions:   15000,
    metaaccountsolutions:        15000,
    targetbuyer:                 5000,
    onlinemarketingbundle:       45000,   // Online Marketing Mentorship
    onlinemarketingconsulting:   250000,  // per month

    // Marketer family
    digitalmarketingguide:       5000,
    growthmarketinghandbook:     10000,
    productmarketingcourse:      15000,
    techsalescourse:             15000,
    marketingresources:          20000,
    aipromptplaybook:            20000,
    marketingprogramcore:        45000,   // AI Marketing Bootcamp (Core)
    marketingprogram:            75000,   // AI Marketing Bootcamp (Full)
    dimedfy:                     350000   // DIME Done-For-You (founding early-bird)
  };

  window.MIA_PRICES = PRICES;

  // 45000 -> "₦45,000"
  window.miaFormatNaira = function (amount) {
    return '₦' + Number(amount).toLocaleString('en-NG');
  };

  // Fill every [data-price] element from the table above.
  function render() {
    var nodes = document.querySelectorAll('[data-price]');
    for (var i = 0; i < nodes.length; i++) {
      var slug = nodes[i].getAttribute('data-price');
      if (PRICES[slug] == null) continue;
      var suffix = nodes[i].getAttribute('data-price-suffix') || '';
      nodes[i].textContent = window.miaFormatNaira(PRICES[slug]) + suffix;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
