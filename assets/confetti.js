/* MIA thank-you confetti — lightweight canvas burst, no dependencies.
 * Fires once per session per page, on load. Reduced-motion aware.
 * Include on post-purchase pages: <script src="/assets/confetti.js"></script>
 */
(function () {
  try {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var KEY = 'mia_confetti_' + location.pathname;
    if (sessionStorage.getItem(KEY)) return;
    sessionStorage.setItem(KEY, '1');
  } catch (e) {}

  function run() {
    var colors = ['#f1de71', '#7184f1', '#f171c4', '#71f19e', '#71c4f1', '#d4c35e'];
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var cv = document.createElement('canvas');
    cv.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:99998';
    document.body.appendChild(cv);
    var ctx = cv.getContext('2d'), W, H;
    function size() {
      W = cv.width = window.innerWidth * dpr;
      H = cv.height = window.innerHeight * dpr;
      cv.style.width = window.innerWidth + 'px';
      cv.style.height = window.innerHeight + 'px';
    }
    size();
    window.addEventListener('resize', size);

    var N = 140, P = [];
    for (var i = 0; i < N; i++) {
      P.push({
        x: Math.random() * W,
        y: Math.random() * -H * 0.5,
        w: (6 + Math.random() * 6) * dpr,
        h: (8 + Math.random() * 8) * dpr,
        c: colors[i % colors.length],
        vy: (2 + Math.random() * 4) * dpr,
        vx: (-1.5 + Math.random() * 3) * dpr,
        rot: Math.random() * 6.28,
        vr: -0.2 + Math.random() * 0.4,
        sway: Math.random() * 6.28
      });
    }

    var start = null, DUR = 3800;
    function frame(ts) {
      if (!start) start = ts;
      var t = ts - start;
      ctx.clearRect(0, 0, W, H);
      var fade = t > DUR - 900 ? Math.max(0, (DUR - t) / 900) : 1;
      for (var i = 0; i < P.length; i++) {
        var p = P[i];
        p.sway += 0.05;
        p.x += p.vx + Math.sin(p.sway) * 0.6 * dpr;
        p.y += p.vy;
        p.rot += p.vr;
        ctx.save();
        ctx.globalAlpha = fade;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      if (t < DUR) {
        requestAnimationFrame(frame);
      } else {
        cv.remove();
        window.removeEventListener('resize', size);
      }
    }
    requestAnimationFrame(frame);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
