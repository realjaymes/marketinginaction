/* Viral Loop Calculator maths. Shared by the page and calc.test.mjs. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.VLC = factory();
})(typeof self !== "undefined" ? self : this, function () {
  var MAX_ROUNDS = 5000;

  function num(x) {
    if (x === "" || x === null || x === undefined) return NaN;
    var n = typeof x === "number" ? x : parseFloat(String(x).replace(/,/g, ""));
    return isFinite(n) ? n : NaN;
  }

  // K = invites per user x join rate (join rate given as a percent)
  function kFromRate(invitesPerUser, joinRatePct) {
    return num(invitesPerUser) * (num(joinRatePct) / 100);
  }

  // Measure from data: invites per user = invites / users, join rate = new users / invites
  function measure(users, invites, newUsers) {
    var u = num(users), i = num(invites), n = num(newUsers);
    if (!(u > 0) || !(i > 0) || !(n >= 0)) return { valid: false };
    var invitesPerUser = i / u;
    var joinRate = n / i;
    return { valid: true, invitesPerUser: invitesPerUser, joinRatePct: joinRate * 100, k: invitesPerUser * joinRate };
  }

  // Round 0 = N. Round i = round (i-1) x K. Total = sum of rounds 0..rounds.
  function project(o) {
    var n = num(o.n), k = num(o.k), cycle = num(o.cycle), period = num(o.period), cost = num(o.cost);
    if (!(n >= 0)) return { valid: false, error: "Enter your starting users." };
    if (!(k >= 0)) return { valid: false, error: "Enter a K of 0 or more." };
    if (!(cycle > 0)) return { valid: false, error: "Enter a cycle time above 0 days." };
    if (!(period > 0)) return { valid: false, error: "Enter a period above 0 days." };
    var rounds = Math.floor(period / cycle + 1e-9);
    var capped = rounds > MAX_ROUNDS;
    if (capped) rounds = MAX_ROUNDS;
    var rows = [], cur = n, total = 0;
    for (var i = 0; i <= rounds; i++) {
      if (i > 0) cur = cur * k;
      total += cur;
      rows.push({ round: i, day: i * cycle, newUsers: cur, total: total });
    }
    var res = {
      valid: true, n: n, k: k, cycle: cycle, period: period,
      rounds: rounds, capped: capped, rows: rows, total: total,
      finite: isFinite(total), growing: k >= 1,
      eventual: null, effectiveCost: null
    };
    if (k < 1) {
      res.eventual = n / (1 - k);
      if (cost >= 0) res.effectiveCost = cost * (1 - k);
    }
    return res;
  }


  // Logged events: users, optional share clicks, invites sent, visits from share links, new users from share links.
  function logged(users, clicks, invites, visits, newUsers) {
    var u = num(users), c = num(clicks), i = num(invites), v = num(visits), n = num(newUsers);
    if (!(u > 0) || !(i > 0) || !(v >= 0) || !(n >= 0)) return { valid: false };
    var r = {
      valid: true,
      invitesPerUser: i / u,
      openRate: v / i,
      visitToJoin: v > 0 ? n / v : 0,
      joinRate: n / i
    };
    r.k = r.invitesPerUser * r.joinRate;
    r.lostOpen = Math.max(0, i - v);
    r.lostJoin = Math.max(0, v - n);
    r.weakest = r.lostOpen >= r.lostJoin ? "open" : "join";
    if (c > 0) { r.clicksPerUser = c / u; r.invitesPerClick = i / c; }
    return r;
  }

  // Two loops with the same starting users and period.
  function compare(n, loopA, loopB, period) {
    var a = project({ n: n, k: loopA.k, cycle: loopA.cycle, period: period });
    var b = project({ n: n, k: loopB.k, cycle: loopB.cycle, period: period });
    if (!a.valid || !b.valid) return { valid: false, error: a.error || b.error };
    var big = a.total >= b.total ? "A" : "B";
    var hi = Math.max(a.total, b.total), lo = Math.min(a.total, b.total);
    var res = { valid: true, a: a, b: b, larger: big, ratio: lo > 0 ? hi / lo : Infinity, checkpoints: null };
    if (num(period) === 28) {
      res.checkpoints = [7, 14, 21, 28].map(function (d) {
        return {
          day: d,
          a: project({ n: n, k: loopA.k, cycle: loopA.cycle, period: d }).total,
          b: project({ n: n, k: loopB.k, cycle: loopB.cycle, period: d }).total
        };
      });
    }
    return res;
  }

  // Retention: share of one day's new users who came back on Day 1, 7 and 30.
  function retention(newUsers, d1, d7, d30) {
    var n = num(newUsers);
    if (!(n > 0)) return { valid: false };
    function pct(x) { var v = num(x); return v >= 0 ? (v / n) * 100 : null; }
    return { valid: true, d1: pct(d1), d7: pct(d7), d30: pct(d30) };
  }

  return { kFromRate: kFromRate, measure: measure, logged: logged, compare: compare, retention: retention, project: project, num: num };
});
