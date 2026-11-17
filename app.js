/* app.js — DOM wiring: calculator slip, balance dashboard, match tracker.
 *
 * The 28% refund is NEVER folded into the per-match settlement. Each match
 * settles on the cash that actually moves (full stakes). The refund accrues
 * separately ("Refund due") and is paid monthly — use "Mark refunds paid" to
 * move it into the Site A balance.
 */
(function () {
  const HS = window.HS;
  const OUT = HS.OUT;
  const DC_LABEL = HS.DC_LABEL;
  const { compute, committed, settle } = HS.calc;
  const store = HS.store;

  const $ = id => document.getElementById(id);
  const ids = ["match", "stake", "comm", "minp", "round",
    "a0", "a1", "a2", "b0", "b1", "b2", "dc0", "dc1", "dc2", "l0", "l1", "l2"];

  // pick: "auto" = app chooses best; otherwise an option key ("d2", "b2", "l0", ...)
  // that encodes which result is backed on Site A and the hedge method.
  let pick = "auto";
  let mode = "2way"; // "2way" (double chance) | "3way" (cover both)
  let lastCalc = null;
  let filter = "all";

  function setMode(m) {
    mode = m === "3way" ? "3way" : "2way";
    document.body.classList.toggle("mode-2way", mode === "2way");
    document.body.classList.toggle("mode-3way", mode === "3way");
    document.querySelectorAll("#modeToggle button").forEach(b =>
      b.setAttribute("aria-pressed", String(b.dataset.mode === mode))
    );
  }

  // Resolve the option to display given the current pick.
  function chosenOption(d) {
    const best = d.opts[0];
    if (pick === "auto") return best;
    return d.opts.find(x => x.key === pick) || null;
  }

  // Keep the Back-on-Site-A buttons in sync with the current pick.
  function syncPickButtons() {
    const k = pick === "auto" ? "auto" : String(+pick.slice(1));
    document.querySelectorAll("#backPick button").forEach(b =>
      b.setAttribute("aria-pressed", String(b.dataset.k === k))
    );
  }

  // ---- helpers ----
  const num = v => { const n = parseFloat(String(v).trim().replace(",", ".")); return isFinite(n) ? n : null; };
  const odd = v => { const n = num(v); return n && n > 1 ? n : null; };
  const eur = (n, sign) =>
    (sign ? (n > 0.004 ? "+" : n < -0.004 ? "−" : "") : (n < 0 ? "−" : "")) +
    "€" + Math.abs(n).toLocaleString("en-IE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = n => (n >= 0 ? "+" : "−") + Math.abs(n * 100).toFixed(1) + "%";
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const cls = n => (n >= 0 ? "pos" : "neg");

  function readInputs() {
    const bk = store.bankroll();
    return {
      mode,
      S: num($("stake").value),
      r: bk.lossRate,   // 20% net-loss refund (from settings)
      tc: bk.commRate,  // 8% turnover commission (from settings)
      c: (num($("comm").value) ?? 0) / 100,
      minP: (num($("minp").value) ?? 0) / 100,
      step: num($("round").value) || 0.01,
      coverOnA: $("coverOnA").checked,
      A: [0, 1, 2].map(i => odd($("a" + i).value)),
      B: [0, 1, 2].map(i => odd($("b" + i).value)),
      DC: [0, 1, 2].map(i => odd($("dc" + i).value)),
      L: [0, 1, 2].map(i => odd($("l" + i).value))
    };
  }

  function optLabel(o) {
    const how = o.type === "book" ? "cover the other two on Site B"
      : o.type === "dc" ? `cover ${DC_LABEL[o.k]} (double chance) on Site B`
      : `lay ${OUT[o.k]} on the exchange`;
    return `Back ${OUT[o.k]} on Site A, ${how}`;
  }

  // ---- the slip ----
  function renderSlip() {
    const d = (lastCalc = compute(readInputs()));
    const slip = $("slip"), m = $("match").value.trim();
    syncPickButtons();

    if (d.error) {
      slip.innerHTML = `<p class="match">${esc(m || "New match")}</p><p class="verdict thin">Waiting for odds</p><p class="sub">${d.error}</p>`;
      return;
    }

    const best = d.opts[0];
    const o = chosenOption(d);
    if (!o) {
      const k = +pick.slice(1);
      slip.innerHTML = `<p class="match">${esc(m || "New match")}</p><p class="verdict thin">No hedge for backing ${OUT[k]}</p><p class="sub">To back <strong>${OUT[k]}</strong> on Site A, add Site B odds for the other two results, or an exchange lay odd for ${OUT[k]}.</p>`;
      return;
    }
    const isBest = o === best;
    const tcp = Math.round(d.tc * 100);
    const rp = Math.round(d.r * 100);

    // Edge metrics. The 8% turnover commission is unconditional → part of the guaranteed result.
    const a = o.a;
    const marginPct = o.type === "dc" ? 1 / a + 1 / o.dc
      : o.type === "book" ? 1 / a + 1 / o.bets[0].odds + 1 / o.bets[1].odds
      : null;
    const settleEdge = o.minSettle / d.S;      // before any commission/refund
    const guarEdge = o.minGuar / d.S;          // settlement + 8% commission (guaranteed)
    const commPct = o.commission / d.S;
    const expRefund = d.r * d.S * (1 - 1 / a);  // optimistic per-ticket loss refund
    const evApprox = o.minGuar + expRefund;
    // DC cover thresholds (turnover from the back stake only): guaranteed incl. commission, and break-even incl. refund
    const coverGuar = a / (a - 1 + d.tc);
    const coverBE = a / (a - 1 + d.tc + d.r * (1 - 1 / a));

    const v = o.sureBet ? "play" : evApprox > 0 ? "thin" : "skip";
    const vText = { play: "Perfect bet — guaranteed", thin: "Playable via refund", skip: "Skip — loss too big" }[v];
    const vSub = o.sureBet
      ? `Guaranteed <strong>${eur(o.minGuar, true)}</strong> (${pct(guarEdge)} of stake) on <em>every</em> result once the ${tcp}% turnover commission is counted. Settlement alone is ${eur(o.minSettle, true)}; the ${rp}% loss refund is extra on top.`
      : evApprox > 0
      ? `Settlement ${eur(o.minSettle, true)} + ${tcp}% commission (${eur(o.commission, true)}) = <strong>${eur(o.minGuar, true)}</strong> guaranteed. You come out ahead once the ${rp}% net-loss refund (~${eur(expRefund)} est.) is added.`
      : `Even with the ${tcp}% commission the guaranteed result is <strong>${eur(o.minGuar, true)}</strong> (${pct(guarEdge)}); a better cover odd or dutching on Site A is needed.`;

    let steps = `<li class="a"><div><div class="amt">${eur(d.S)} on ${OUT[o.k]}</div><div class="where">Site A at odds ${o.a.toFixed(2)}</div></div></li>`;
    if (o.type === "book") {
      o.bets.forEach(b => steps += `<li class="b"><div><div class="amt">${eur(b.amt)} on ${OUT[b.j]}</div><div class="where">Site B at odds ${b.odds.toFixed(2)}</div></div></li>`);
    } else if (o.type === "dc") {
      steps += `<li class="b"><div><div class="amt">${eur(o.cover)} on ${DC_LABEL[o.k]}</div><div class="where">Site B double chance at odds ${o.dc.toFixed(2)}</div></div></li>`;
    } else {
      steps += `<li class="x"><div><div class="amt">Lay ${OUT[o.k]}, stake ${eur(o.lay)}</div><div class="where">Exchange at lay odds ${o.lodds.toFixed(2)} · liability ${eur(o.liab)}</div></div></li>`;
    }

    const rows = [0, 1, 2].map(i =>
      `<tr class="${i === o.k ? "backed" : ""}"><td>${OUT[i]} wins</td>` +
      `<td class="n ${cls(o.res[i])}">${eur(o.res[i], true)}</td>` +
      `<td class="n pos">${eur(o.commission, true)}</td>` +
      `<td class="n">${o.refund[i] > 0 ? eur(o.refund[i], true) : "—"}</td>` +
      `<td class="n ${cls(o.resTotal[i])}">${eur(o.resTotal[i], true)}</td></tr>`
    ).join("");

    const ranked = [...d.opts].sort((x, y) => y.minGuar - x.minGuar);
    const others = ranked.map(x =>
      `<li><button type="button" data-key="${x.key}" aria-pressed="${x === o}"><span>${optLabel(x)}${x.sureBet ? ' <strong class="pos">✓ sure</strong>' : ""}</span><span class="p ${cls(x.minGuar)}">${pct(x.minGuar / d.S)}</span></button></li>`
    ).join("");

    const edgeRows =
      (marginPct != null ? `<tr><td>Combined margin (1/a + 1/cover)</td><td class="n ${marginPct < 1 ? "pos" : "neg"}">${(marginPct * 100).toFixed(1)}%</td></tr>` : "") +
      `<tr><td>Settlement edge (before commission)</td><td class="n ${settleEdge >= 0 ? "pos" : "neg"}">${pct(settleEdge)}</td></tr>` +
      `<tr><td>+ ${tcp}% turnover commission${o.coverOnA ? " (dutch, full stake)" : ""}</td><td class="n pos">${pct(commPct)}</td></tr>` +
      `<tr class="backed"><td>Guaranteed edge (incl. commission)</td><td class="n ${guarEdge >= 0 ? "pos" : "neg"}">${pct(guarEdge)}</td></tr>` +
      (o.type === "dc"
        ? `<tr><td>Cover needed — guaranteed profit</td><td class="n">≥ ${coverGuar.toFixed(2)} &nbsp;(you: ${o.dc.toFixed(2)})</td></tr>` +
          `<tr><td>Cover needed — break even w/ refund</td><td class="n">≥ ${coverBE.toFixed(2)}</td></tr>`
        : "");

    slip.innerHTML = `
      <p class="match">${esc(m || "Unnamed match")} · stake ${eur(d.S)}</p>
      <p class="verdict ${v}">${vText}</p>
      <p class="sub">${vSub}</p>
      <section>
        <h2>Edge check</h2>
        <div class="tbl-wrap"><table class="res"><tbody>${edgeRows}</tbody></table></div>
        <p class="note">With the ${tcp}% commission, you're guaranteed whenever the <strong>Guaranteed edge</strong> row is green. Tip: covering the whole bet on Site A (dutch) puts the full stake through the commission — tick the box above to see it.</p>
      </section>
      <section>
        <h2>${isBest ? "How to play it" : "Your chosen option"}</h2>
        <ol class="steps">${steps}</ol>
        <p class="note">Money needed in total: <strong>${eur(o.money)}</strong>. Place one bet, confirm it was accepted at these odds, then place the next. If any odds change, update them here first.</p>
      </section>
      <section>
        <h2>What you end with</h2>
        <div class="tbl-wrap"><table class="res"><thead><tr><th>Result</th><th style="text-align:right">At settlement</th><th style="text-align:right">+Comm (${tcp}%)</th><th style="text-align:right">+Loss ref (${rp}%)</th><th style="text-align:right">Total</th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="note">The <strong>${tcp}% commission (${eur(o.commission)})</strong> is paid on every result — it's guaranteed. The <strong>${rp}% loss refund</strong> column is an <em>estimate</em>; the real one is ${rp}% of your whole month's <strong>net</strong> Site A loss, so a winning pick reduces it (see “Monthly refunds” below).</p>
      </section>
      <section>
        <h2>All options, guaranteed edge (✓ = profit every result)</h2>
        <ul class="opts">${others}</ul>
      </section>`;

    slip.querySelectorAll(".opts button").forEach(b =>
      b.addEventListener("click", () => { pick = b.dataset.key; renderSlip(); })
    );
  }

  // ---- balance dashboard ----
  const monthKey = ts => { const d = new Date(ts || Date.now()); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0"); };
  const monthLabel = key => { const [y, mo] = key.split("-"); return new Date(+y, +mo - 1, 1).toLocaleDateString("en-IE", { month: "long", year: "numeric" }); };

  function computeBalances() {
    const bk = store.bankroll();
    const commRate = bk.commRate, lossRate = bk.lossRate;
    const paid = bk.paidMonths || {};
    const ms = store.matches();
    const bal = { A: bk.A, B: bk.B, E: bk.E }; // settlement cash only (Site A credits added once paid)
    const tied = { A: 0, B: 0, E: 0 };
    const months = {}; // "YYYY-MM" -> { net, turnover, count }
    let settlePL = 0, pickLost = 0, pickWon = 0, pend = 0;

    ms.forEach(m => {
      if (m.status === "settled" && m.settlement) {
        bal.A += m.settlement.A; bal.B += m.settlement.B; bal.E += m.settlement.E;
        settlePL += m.settlement.total;
        if (m.result === m.option.k) pickWon++; else pickLost++;
        const key = monthKey(m.settledAt || m.savedAt);
        const mo = (months[key] = months[key] || { net: 0, turnover: 0, count: 0 });
        mo.net += m.settlement.A;
        mo.turnover += (m.turnoverA != null ? m.turnoverA : m.stake); // Site A turnover
        mo.count++;
      } else {
        tied.A += m.committed.A; tied.B += m.committed.B; tied.E += m.committed.E;
        pend++;
      }
    });

    // Monthly Site A credit = commission (commRate × turnover, always) + loss refund (lossRate × net loss).
    let creditDue = 0, creditPaidTot = 0, commTotal = 0, refundTotal = 0;
    const monthList = Object.keys(months).sort().reverse().map(key => {
      const { net, turnover, count } = months[key];
      const netLoss = Math.max(0, -net);
      const commission = commRate * turnover;
      const refund = lossRate * netLoss;
      const credit = commission + refund;
      const isPaid = !!paid[key];
      commTotal += commission; refundTotal += refund;
      if (isPaid) { bal.A += credit; creditPaidTot += credit; } else { creditDue += credit; }
      return { key, net, netLoss, turnover, commission, refund, credit, isPaid, count };
    });

    return { bal, tied, settlePL, creditDue, creditPaidTot, commTotal, refundTotal, pickLost, pickWon, pend, monthList, commRate, lossRate };
  }

  function renderDashboard() {
    const b = computeBalances();
    const defs = [["A", "Site A", "a"], ["B", "Site B", "b"], ["E", "Exchange", "e"]];
    $("cards").innerHTML = defs.map(([k, name, c]) =>
      `<div class="card ${c}">
        <p class="site">${name}</p>
        <div class="bal">${eur(b.bal[k])}</div>
        <div class="meta"><span>Available: <b>${eur(b.bal[k] - b.tied[k])}</b></span><span>Tied up: ${eur(b.tied[k])}</span></div>
      </div>`
    ).join("");

    const totalBal = b.bal.A + b.bal.B + b.bal.E;
    const totalTied = b.tied.A + b.tied.B + b.tied.E;
    const overall = b.settlePL + b.creditDue + b.creditPaidTot;
    $("totals").innerHTML = `
      <div class="t"><span class="k">Total balance</span><span class="v">${eur(totalBal)}</span></div>
      <div class="t"><span class="k">Settlement P&amp;L (bets only)</span><span class="v ${cls(b.settlePL)}">${eur(b.settlePL, true)}</span></div>
      <div class="t"><span class="k">Commission earned (${Math.round(b.commRate * 100)}%)</span><span class="v pos">${eur(b.commTotal, true)}</span></div>
      <div class="t"><span class="k">Loss refund (${Math.round(b.lossRate * 100)}%)</span><span class="v pos">${eur(b.refundTotal, true)}</span></div>
      <div class="t"><span class="k">Overall profit</span><span class="v ${cls(overall)}">${eur(overall, true)}</span></div>
      <div class="t"><span class="k">Site A credit due</span><span class="v pos">${eur(b.creditDue)}</span></div>
      <div class="t"><span class="k">Pending</span><span class="v">${b.pend}</span></div>`;

    renderRefunds(b);
  }

  function renderRefunds(b) {
    const el = $("refunds");
    if (!b.monthList.length) { el.innerHTML = ""; return; }
    const cp = Math.round(b.commRate * 100), lp = Math.round(b.lossRate * 100);
    const rows = b.monthList.map(mo => {
      const siteANet = mo.net >= 0 ? "net +" + eur(mo.net).slice(1) : "net −" + eur(Math.abs(mo.net)).slice(1);
      const action = mo.credit > 0.004
        ? (mo.isPaid
            ? `<button class="small" data-unpay="${mo.key}">Paid ✓ — undo</button>`
            : `<button class="small primary" data-pay="${mo.key}">Mark paid → Site A</button>`)
        : `<span class="empty">No credit</span>`;
      return `<li>
        <div><b>${monthLabel(mo.key)}</b> <span class="empty">· ${mo.count} settled · Site A ${siteANet}</span></div>
        <div class="m-sites" style="margin:4px 0 0">
          <span>Turnover: <b>${eur(mo.turnover)}</b></span>
          <span>Commission ${cp}%: <b class="pos">${eur(mo.commission)}</b></span>
          <span>Net loss: <b>${eur(mo.netLoss)}</b></span>
          <span>Refund ${lp}%: <b class="pos">${eur(mo.refund)}</b></span>
          <span>Total credit: <b class="pos">${eur(mo.credit)}</b></span>
        </div>
        <div class="m-actions" style="margin-top:8px">${action}</div>
      </li>`;
    }).join("");
    el.innerHTML = `<h2 style="margin:18px 0 10px">Monthly Site A credit (${cp}% turnover + ${lp}% net loss)</h2><ul class="matches">${rows}</ul>`;
    el.querySelectorAll("[data-pay]").forEach(x => x.addEventListener("click", () => { store.setMonthPaid(x.dataset.pay, true); refreshTracker(); }));
    el.querySelectorAll("[data-unpay]").forEach(x => x.addEventListener("click", () => { store.setMonthPaid(x.dataset.unpay, false); refreshTracker(); }));
  }

  // ---- match tracker ----
  function betSummary(m) {
    const o = m.option;
    const back = `Back <b>${OUT[o.k]}</b> ${eur(m.stake)} @${o.a.toFixed(2)} on Site A`;
    if (o.type === "book") {
      const cover = o.bets.map(b => `${OUT[b.j]} @${b.odds.toFixed(2)} (${eur(b.amt)})`).join(", ");
      return `${back} · cover ${cover} on Site B`;
    }
    if (o.type === "dc") {
      return `${back} · cover ${DC_LABEL[o.k]} @${o.dc.toFixed(2)} (${eur(o.cover)}) on Site B`;
    }
    return `${back} · lay ${OUT[o.k]} @${o.lodds.toFixed(2)} on Exchange (liability ${eur(o.liab)})`;
  }

  function matchRow(m) {
    const o = m.option;
    const badge = m.status === "settled"
      ? `<span class="badge settled">Settled · ${OUT[m.result]} won</span>`
      : `<span class="badge pending">Pending</span>`;

    let body = `<div class="m-line">${betSummary(m)}</div>`;

    if (m.status === "pending") {
      body += `<div class="m-sites">
        <span>Tied Site A: <b>${eur(m.committed.A)}</b></span>
        <span>Site B: <b>${eur(m.committed.B)}</b></span>
        <span>Exchange: <b>${eur(m.committed.E)}</b></span>
      </div>`;
      // settle buttons show settlement cash + refund that each outcome produces
      const btns = [0, 1, 2].map(i =>
        `<button data-settle="${m.id}" data-w="${i}"><span class="w">${OUT[i]}</span>` +
        `<span class="n ${cls(o.res[i])}">${eur(o.res[i], true)}</span>` +
        `<span class="n" style="color:var(--muted)">${o.refund[i] > 0 ? "refund " + eur(o.refund[i]) : "no refund"}</span></button>`
      ).join("");
      body += `<div class="settle"><span class="q">Who won?</span>${btns}</div>`;
      body += `<div class="m-actions">
        <button class="small" data-load="${m.id}">Load into calculator</button>
        <button class="small" data-del="${m.id}">Delete</button>
      </div>`;
    } else {
      const s = m.settlement;
      const pickLost = m.result !== o.k;
      const refTxt = pickLost
        ? ` · Site A pick lost → adds <b class="pos">${eur(Math.abs(s.A))}</b> to this month's refund base`
        : " · Site A pick won → no refund (reduces the month's refund base)";
      body += `<div class="m-result">Settlement <span class="big ${cls(s.total)}">${eur(s.total, true)}</span>${refTxt}</div>`;
      body += `<div class="m-sites">
        <span>Site A: <b class="${cls(s.A)}">${eur(s.A, true)}</b></span>
        <span>Site B: <b class="${cls(s.B)}">${eur(s.B, true)}</b></span>
        <span>Exchange: <b class="${cls(s.E)}">${eur(s.E, true)}</b></span>
      </div>`;
      body += `<div class="m-actions">
        <button class="small" data-reopen="${m.id}">Reopen</button>
        <button class="small" data-load="${m.id}">Load into calculator</button>
        <button class="small" data-del="${m.id}">Delete</button>
      </div>`;
    }

    return `<li>
      <div class="m-top"><span class="m-name">${esc(m.name)}</span>${badge}</div>
      ${body}
    </li>`;
  }

  function renderMatches() {
    const ul = $("matches");
    let ms = store.matches();
    if (filter !== "all") ms = ms.filter(m => m.status === filter);
    if (!ms.length) {
      ul.innerHTML = `<li><p class="empty">${filter === "all" ? "No matches yet. Enter odds and press “Save to tracker”." : "Nothing here with this filter."}</p></li>`;
      return;
    }
    ul.innerHTML = ms.map(matchRow).join("");

    ul.querySelectorAll("[data-settle]").forEach(b => b.addEventListener("click", () => {
      const m = store.matches().find(x => x.id === b.dataset.settle);
      if (!m) return;
      const w = +b.dataset.w;
      store.updateMatch(m.id, { status: "settled", result: w, settledAt: Date.now(), settlement: settle(m.option, w, m.stake) });
      refreshTracker();
    }));
    ul.querySelectorAll("[data-reopen]").forEach(b => b.addEventListener("click", () => {
      store.updateMatch(b.dataset.reopen, { status: "pending", result: null, settlement: null, settledAt: null });
      refreshTracker();
    }));
    ul.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", () => {
      store.deleteMatch(b.dataset.del);
      refreshTracker();
    }));
    ul.querySelectorAll("[data-load]").forEach(b => b.addEventListener("click", () => {
      const m = store.matches().find(x => x.id === b.dataset.load);
      if (!m) return;
      ids.forEach(id => { if (m.vals[id] !== undefined) $(id).value = m.vals[id]; });
      if (m.mode) setMode(m.mode);
      $("coverOnA").checked = !!m.coverOnA;
      pick = m.option.key;
      renderSlip();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }));
  }

  function refreshTracker() {
    renderDashboard();
    renderMatches();
  }

  // ---- actions ----
  $("save").addEventListener("click", () => {
    if (!lastCalc || lastCalc.error) return;
    const o = chosenOption(lastCalc) || lastCalc.opts[0];
    const vals = {}; ids.forEach(id => (vals[id] = $(id).value));
    store.addMatch({
      id: store.uid(),
      name: $("match").value.trim() || "Unnamed match",
      savedAt: Date.now(),
      status: "pending",
      stake: lastCalc.S,
      refund: lastCalc.r,
      mode,
      coverOnA: o.coverOnA,
      turnoverA: o.turnoverA,
      option: o,
      committed: committed(o, lastCalc.S),
      vals,
      result: null,
      settledAt: null,
      settlement: null
    });
    refreshTracker();
  });

  $("clear").addEventListener("click", () => {
    ["a0", "a1", "a2", "b0", "b1", "b2", "dc0", "dc1", "dc2", "l0", "l1", "l2", "match"].forEach(id => ($(id).value = ""));
    $("coverOnA").checked = false;
    pick = "auto";
    renderSlip();
  });

  $("coverOnA").addEventListener("change", renderSlip);

  // Back-on-Site-A picker
  $("backPick").querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    const k = b.dataset.k;
    if (k === "auto") { pick = "auto"; }
    else if (lastCalc && lastCalc.opts) {
      // prefer the hedge option (dc/book) for that result, fall back to the lay
      const o = lastCalc.opts.find(x => x.key === "d" + k)
        || lastCalc.opts.find(x => x.key === "b" + k)
        || lastCalc.opts.find(x => x.key === "l" + k);
      pick = o ? o.key : (mode === "2way" ? "d" : "b") + k; // keep intent even if no option yet
    } else { pick = (mode === "2way" ? "d" : "b") + k; }
    renderSlip();
  }));

  // Mode toggle (two-way double chance vs three-way)
  $("modeToggle").querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    setMode(b.dataset.mode);
    pick = "auto";
    renderSlip();
  }));

  // filters
  $("filters").querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    filter = b.dataset.f;
    $("filters").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    renderMatches();
  }));

  // bankroll editing
  const bankForm = $("bankForm");
  function fillBankForm() {
    const bk = store.bankroll();
    $("startA").value = bk.A || 0;
    $("startB").value = bk.B || 0;
    $("startE").value = bk.E || 0;
    $("commRate").value = (bk.commRate * 100).toString();
    $("lossRate").value = (bk.lossRate * 100).toString();
  }
  $("editBank").addEventListener("click", () => {
    fillBankForm();
    bankForm.hidden = !bankForm.hidden;
  });
  $("cancelBank").addEventListener("click", () => { bankForm.hidden = true; });
  bankForm.addEventListener("submit", e => {
    e.preventDefault();
    store.saveBankroll({
      A: num($("startA").value) ?? 0,
      B: num($("startB").value) ?? 0,
      E: num($("startE").value) ?? 0,
      commRate: (num($("commRate").value) ?? 0) / 100,
      lossRate: (num($("lossRate").value) ?? 0) / 100
    });
    bankForm.hidden = true;
    renderSlip();
    renderDashboard();
  });

  // live recompute (keep the user's backed selection across edits)
  ids.forEach(id => $(id).addEventListener("input", () => { renderSlip(); }));

  // let db-sync.js re-render once it hydrates matches/bankroll from the server
  HS.refresh = function () { renderSlip(); refreshTracker(); };

  // start in two-way (double chance) mode
  setMode("2way");

  // example: back 2 on Site A, cover 1X (double chance) on Site B
  [["a2", "2.28"], ["dc2", "1.62"], ["match", "Example match"]]
    .forEach(([id, v]) => ($(id).value = v));
  pick = "d2";

  renderSlip();
  refreshTracker();
})();
