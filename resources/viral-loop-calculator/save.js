/* Viral Loop Calculator: summary text and CSV builders. Pure functions, shared by the page and save.test.mjs. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("./calc.js"));
  else root.VLCSave = factory(root.VLC);
})(typeof self !== "undefined" ? self : this, function (VLC) {
  var QUESTIONS = [
    ["Premise", "Can a stranger retell it in one line after seeing one post?"],
    ["Identity", "Can you list ten places, habits or jokes your audience already posts about that the product uses?"],
    ["Access", "Is it one tap from the post to the first moment of use?"],
    ["Share artifact", "Does using the product quickly produce something people want to post, with a share button next to it?"],
    ["Recruit loop", "Does a user get something useful when they bring another person in?"],
    ["Builder cadence", "Are the first five updates and their posts planned?"],
    ["Revenue", "Can the product earn money at launch, and do buyers have a reason to tell others?"]
  ];
  var BREAK = "This breaks the loop on its own, however well the rest scores.";
  var ALL = ["score", "k", "proj", "cmp", "ret"];
  var num = VLC.num;

  function fmt(n, d) {
    if (n === null || n === undefined || isNaN(n)) return "";
    if (!isFinite(n)) return "Too large to show";
    return n.toLocaleString("en-US", { maximumFractionDigits: d || 0 });
  }
  function pct(x, d) { return fmt(x, d === undefined ? 1 : d) + "%"; }
  function filled(v) { return v !== "" && v !== null && v !== undefined && !isNaN(num(v)); }

  /* Turn the raw field values into one model. */
  function build(raw) {
    var m = { date: raw.date, url: raw.url, cur: raw.cur || "$" };
    var items = QUESTIONS.map(function (q, i) {
      var s = raw.scores ? raw.scores[i] : null;
      s = s === "" || s === null || s === undefined ? null : parseInt(s, 10);
      return { name: q[0], question: q[1], score: s, note: ((raw.notes && raw.notes[i]) || "").trim() };
    });
    var total = 0, answered = 0, lowest = null, breaks = [];
    items.forEach(function (it, i) {
      if (it.score === null) return;
      total += it.score; answered++;
      if (it.score === 0 && (i === 2 || i === 3 || i === 4)) breaks.push(it.name);
      if (lowest === null || it.score < lowest.score) lowest = it;
    });
    m.score = { items: items, total: total, answered: answered, breaks: breaks,
      belowNine: answered === 7 && total < 9, fixFirst: answered === 7 && lowest && lowest.score < 2 ? lowest.name : null };

    var k1;
    if (raw.kmode === "direct") { var kd = num(raw.kdirect); k1 = isNaN(kd) ? null : { mode: "direct", k: kd }; }
    else { var kr = VLC.kFromRate(raw.inv, raw.join); k1 = isNaN(kr) ? null : { mode: "rate", inv: num(raw.inv), join: num(raw.join), k: kr }; }
    m.k1 = k1;
    var lg = VLC.logged(raw.lu, raw.lc, raw.li, raw.lv, raw.ln);
    m.k2 = lg.valid ? lg : null;
    var pr = VLC.project({ n: raw.n, k: raw.pk, cycle: raw.cycle, period: raw.period, cost: raw.cost });
    m.proj = pr.valid ? pr : null;
    m.projCost = filled(raw.cost) ? num(raw.cost) : null;
    var cm = VLC.compare(raw.cn, { k: raw.ak, cycle: raw.ac }, { k: raw.bk, cycle: raw.bc }, raw.cp);
    m.cmp = cm.valid ? cm : null;
    m.cmpIn = { n: num(raw.cn), period: num(raw.cp), ak: num(raw.ak), ac: num(raw.ac), bk: num(raw.bk), bc: num(raw.bc) };
    var rt = VLC.retention(raw.rn, raw.r1, raw.r7, raw.r30);
    m.ret = rt.valid && (filled(raw.r1) || filled(raw.r7) || filled(raw.r30)) ? rt : null;
    m.retIn = { n: num(raw.rn), d1: num(raw.r1), d7: num(raw.r7), d30: num(raw.r30) };
    return m;
  }

  /* Labelled rows of display strings, one block per module. */
  function sections(m, keys) {
    keys = keys || ALL;
    var out = [];
    if (keys.indexOf("score") >= 0) {
      var rows = m.score.items.map(function (it) {
        return [it.name, (it.score === null ? "Not scored" : it.score + " of 2") + (it.note ? ". " + it.note : "")];
      });
      rows.push(["Total", m.score.total + " of 14 (" + m.score.answered + " of 7 answered)"]);
      if (m.score.breaks.length) rows.push(["Warning", m.score.breaks.join(" and ") + (m.score.breaks.length > 1 ? " are" : " is") + " at 0. " + BREAK]);
      if (m.score.belowNine) rows.push(["Warning", "Your score is below 9 out of 14. Fix the gaps before you launch."]);
      if (m.score.fixFirst) rows.push(["Fix first", m.score.fixFirst]);
      out.push({ key: "score", title: "Scorecard", rows: rows });
    }
    if (keys.indexOf("k") >= 0) {
      if (m.k1) {
        var r1 = m.k1.mode === "rate" ? [["Invites per user", fmt(m.k1.inv, 2)], ["Join rate", pct(m.k1.join)], ["K", fmt(m.k1.k, 2)]] : [["K", fmt(m.k1.k, 2)]];
        out.push({ key: "k", title: "K from your numbers", rows: r1 });
      }
      if (m.k2) {
        var g = m.k2, r2 = [["Invites per user", fmt(g.invitesPerUser, 2)], ["Open rate (visits ÷ invites)", pct(g.openRate * 100)],
          ["Visit to join rate (new users ÷ visits)", pct(g.visitToJoin * 100)], ["Join rate (new users ÷ invites)", pct(g.joinRate * 100)], ["K", fmt(g.k, 2)],
          ["Step that loses the most people", g.weakest === "open" ? "Invites nobody opened (" + fmt(g.lostOpen) + ")" : "Visitors who did not join (" + fmt(g.lostJoin) + ")"]];
        if (g.clicksPerUser !== undefined) { r2.push(["Share clicks per user", fmt(g.clicksPerUser, 2)]); r2.push(["Invites per share click", fmt(g.invitesPerClick, 2)]); }
        out.push({ key: "k", title: "K from your logged events", rows: r2 });
      }
    }
    if (keys.indexOf("proj") >= 0 && m.proj) {
      var p = m.proj, rp = [["Starting users", fmt(p.n)], ["K", fmt(p.k, 2)], ["Cycle time (days)", fmt(p.cycle, 2)], ["Period (days)", fmt(p.period, 2)]];
      if (m.projCost !== null) rp.push(["Cost per user you paid for (" + m.cur + ")", fmt(m.projCost, 2)]);
      rp.push(["Rounds", fmt(p.rounds)]); rp.push(["Total users after " + fmt(p.period, 2) + " days", fmt(p.total)]);
      if (p.eventual !== null) {
        rp.push(["Eventual total if the loop runs to the end", fmt(p.eventual)]);
        if (p.effectiveCost !== null) rp.push(["Effective cost per user (" + m.cur + ")", fmt(p.effectiveCost, 2)]);
      } else rp.push(["Growth", "K is 1 or more, so the loop keeps growing while K and cycle time hold."]);
      out.push({ key: "proj", title: "Growth projection", rows: rp });
    }
    if (keys.indexOf("cmp") >= 0 && m.cmp) {
      var c = m.cmp, ci = m.cmpIn, big = c.larger, small = big === "A" ? "B" : "A";
      var rc = [["Starting users", fmt(ci.n)], ["Period (days)", fmt(ci.period, 2)], ["Loop A", "K " + fmt(ci.ak, 2) + ", cycle time " + fmt(ci.ac, 2) + " days"],
        ["Loop B", "K " + fmt(ci.bk, 2) + ", cycle time " + fmt(ci.bc, 2) + " days"], ["Loop A total", fmt(c.a.total)], ["Loop B total", fmt(c.b.total)]];
      if (isFinite(c.ratio) && c.ratio >= 1.005) rc.push(["Comparison", "Loop " + big + " ends about " + fmt(c.ratio, c.ratio >= 10 ? 0 : 1) + " times bigger than Loop " + small + "."]);
      else if (isFinite(c.ratio)) rc.push(["Comparison", "The two loops end at the same total."]);
      if (c.checkpoints) c.checkpoints.forEach(function (x) { rc.push(["Day " + x.day, "Loop A " + fmt(x.a) + ", Loop B " + fmt(x.b)]); });
      out.push({ key: "cmp", title: "Compare two loops", rows: rc });
    }
    if (keys.indexOf("ret") >= 0 && m.ret) {
      var t = m.retIn, rr = [["New users on one day", fmt(t.n)]];
      [["Day 1", "d1"], ["Day 7", "d7"], ["Day 30", "d30"]].forEach(function (x) {
        if (m.ret[x[1]] !== null) rr.push([x[0], pct(m.ret[x[1]]) + " (" + fmt(t[x[1]]) + " came back)"]);
      });
      out.push({ key: "ret", title: "Retention", rows: rr });
    }
    return out;
  }

  function summaryText(m, keys, title) {
    var lines = [title || "Viral Loop Calculator results, " + m.date, ""];
    sections(m, keys).forEach(function (s) {
      lines.push(s.title);
      s.rows.forEach(function (r) { lines.push(r[0] + ": " + r[1]); });
      lines.push("");
    });
    lines.push(m.url);
    return lines.join("\n");
  }

  /* CSV. User counts are rounded to whole users in the results rows. The round table keeps full decimals. */
  function n(x) { return typeof x === "number" && isFinite(x) ? String(+x.toPrecision(12)) : ""; }
  function w(x) { return typeof x === "number" && isFinite(x) ? String(Math.round(x)) : ""; }
  function cell(v) {
    var s = v === null || v === undefined ? "" : String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function csv(m, keys) {
    keys = keys || ALL;
    var rows = [];
    function add() { rows.push([].slice.call(arguments)); }
    function gap() { if (rows.length) rows.push([]); }
    if (keys.indexOf("score") >= 0) {
      gap(); add("Scorecard"); add("Ingredient", "Question", "Score (0 to 2)", "Note");
      m.score.items.forEach(function (it) { add(it.name, it.question, it.score === null ? "" : n(it.score), it.note); });
      add("Total (out of 14)", "", n(m.score.total), ""); add("Answered (out of 7)", "", n(m.score.answered), "");
      if (m.score.breaks.length) add("Warning", "", "", m.score.breaks.join(" and ") + (m.score.breaks.length > 1 ? " are" : " is") + " at 0. " + BREAK);
      if (m.score.belowNine) add("Warning", "", "", "Your score is below 9 out of 14. Fix the gaps before you launch.");
      if (m.score.fixFirst) add("Fix first", "", "", m.score.fixFirst);
    }
    if (keys.indexOf("k") >= 0) {
      if (m.k1) {
        gap(); add("K from your numbers"); add("Field", "Value");
        if (m.k1.mode === "rate") { add("Invites per user", n(m.k1.inv)); add("Join rate (%)", n(m.k1.join)); }
        add("K", n(m.k1.k));
      }
      if (m.k2) {
        var g = m.k2;
        gap(); add("K from your logged events"); add("Field", "Value");
        add("Invites per user", n(g.invitesPerUser)); add("Open rate (%)", n(g.openRate * 100)); add("Visit to join rate (%)", n(g.visitToJoin * 100));
        add("Join rate (%)", n(g.joinRate * 100)); add("K", n(g.k));
        add("Step that loses the most people", g.weakest === "open" ? "Invites nobody opened" : "Visitors who did not join");
        add("Users lost at that step", n(g.weakest === "open" ? g.lostOpen : g.lostJoin));
        if (g.clicksPerUser !== undefined) { add("Share clicks per user", n(g.clicksPerUser)); add("Invites per share click", n(g.invitesPerClick)); }
      }
    }
    if (keys.indexOf("proj") >= 0 && m.proj) {
      var p = m.proj;
      gap(); add("Projection inputs"); add("Field", "Value");
      add("Starting users", n(p.n)); add("K", n(p.k)); add("Cycle time (days)", n(p.cycle)); add("Period (days)", n(p.period));
      if (m.projCost !== null) add("Cost per user you paid for (" + m.cur + ")", n(m.projCost));
      gap(); add("Projection results"); add("Field", "Value");
      add("Rounds", n(p.rounds)); add("Total users after the period", w(p.total));
      if (p.eventual !== null) {
        add("Eventual total if the loop runs to the end", w(p.eventual));
        if (p.effectiveCost !== null) add("Effective cost per user (" + m.cur + ")", n(p.effectiveCost));
      } else add("Growth", "K is 1 or more, so the loop keeps growing while K and cycle time hold.");
      gap(); add("Round by round"); add("Round", "Day", "New users", "Running total");
      p.rows.forEach(function (r) { add(n(r.round), n(r.day), n(r.newUsers), n(r.total)); });
    }
    if (keys.indexOf("cmp") >= 0 && m.cmp) {
      var c = m.cmp, ci = m.cmpIn;
      gap(); add("Compare two loops"); add("Field", "Loop A", "Loop B");
      add("K", n(ci.ak), n(ci.bk)); add("Cycle time (days)", n(ci.ac), n(ci.bc));
      add("Rounds", n(c.a.rounds), n(c.b.rounds)); add("Total users after the period", w(c.a.total), w(c.b.total));
      add("Starting users", n(ci.n)); add("Period (days)", n(ci.period));
      add("Larger loop", c.larger); add("Times bigger", isFinite(c.ratio) ? n(c.ratio) : "");
      if (c.checkpoints) {
        gap(); add("Compare checkpoints"); add("Day", "Loop A", "Loop B");
        c.checkpoints.forEach(function (x) { add(n(x.day), w(x.a), w(x.b)); });
      }
    }
    if (keys.indexOf("ret") >= 0 && m.ret) {
      var t = m.retIn;
      gap(); add("Retention"); add("Measure", "Users", "Percent of new users");
      add("New users on one day", n(t.n), "");
      [["Day 1", "d1"], ["Day 7", "d7"], ["Day 30", "d30"]].forEach(function (x) {
        if (m.ret[x[1]] !== null) add("Came back on " + x[0], n(t[x[1]]), n(m.ret[x[1]]));
      });
    }
    gap(); add("Saved", m.date, m.url);
    return rows.map(function (r) { return r.map(cell).join(","); }).join("\r\n") + "\r\n";
  }

  function withBom(text) { return "﻿" + text; }
  function filename(kind, date) { return "viral-loop-" + (kind && kind !== "all" ? kind + "-" : "results-") + date + ".csv"; }

  return { QUESTIONS: QUESTIONS, ALL: ALL, build: build, sections: sections, summaryText: summaryText, csv: csv, withBom: withBom, filename: filename };
});
