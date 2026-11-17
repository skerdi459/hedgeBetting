/* dashboard.js — reads the SQLite-backed history via the REST API and renders
 * totals, a monthly breakdown and the full activity log. Read-only.
 */
(function () {
  const $ = id => document.getElementById(id);
  const eur = (n, sign) =>
    (sign ? (n > 0.004 ? "+" : n < -0.004 ? "−" : "") : (n < 0 ? "−" : "")) +
    "€" + Math.abs(n || 0).toLocaleString("en-IE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const cls = n => (n >= 0 ? "pos" : "neg");
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const monthKey = ts => { const d = new Date(ts); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0"); };
  const monthLabel = key => { const [y, m] = key.split("-"); return new Date(+y, +m - 1, 1).toLocaleDateString("en-IE", { month: "long", year: "numeric" }); };
  const dt = ts => new Date(ts).toLocaleString("en-IE", { dateStyle: "medium", timeStyle: "short" });

  const EV_LABEL = {
    saved: "Saved", updated: "Updated", settled: "Settled", reopened: "Reopened",
    deleted: "Deleted", bankroll: "Balances", month_paid: "Month paid", month_unpaid: "Month unpaid"
  };

  Promise.all([
    fetch("/api/state").then(r => r.json()),
    fetch("/api/events?limit=2000").then(r => r.json()),
    fetch("/api/health").then(r => r.json()).catch(() => null)
  ]).then(([state, events, health]) => {
    const matches = state.matches || [];
    const bank = state.bankroll || { commRate: 0.08, lossRate: 0.2 };
    if (health && $("dbnote")) $("dbnote").textContent = "DB: " + health.db;

    // ---- totals ----
    const settled = matches.filter(m => m.status === "settled" && m.settlement);
    const pending = matches.filter(m => m.status !== "settled");
    let settlePL = 0, turnover = 0;
    const months = {};
    settled.forEach(m => {
      settlePL += m.settlement.total;
      const tov = m.turnoverA != null ? m.turnoverA : m.stake || 0;
      turnover += tov;
      const key = monthKey(m.settledAt || m.savedAt);
      const mo = (months[key] = months[key] || { net: 0, turnover: 0, count: 0, total: 0 });
      mo.net += m.settlement.A;           // Site A settlement cash (for refund base)
      mo.total += m.settlement.total;     // overall settlement P&L
      mo.turnover += tov;
      mo.count++;
    });
    const commission = (bank.commRate || 0) * turnover;
    let refund = 0;
    Object.values(months).forEach(mo => { refund += (bank.lossRate || 0) * Math.max(0, -mo.net); });
    const overall = settlePL + commission + refund;

    const tiles = [
      ["Matches tracked", String(matches.length), ""],
      ["Settled", String(settled.length), ""],
      ["Pending", String(pending.length), ""],
      ["Site A turnover", eur(turnover), ""],
      ["Settlement P&L", eur(settlePL, true), cls(settlePL)],
      ["Commission (" + Math.round((bank.commRate || 0) * 100) + "%)", eur(commission, true), "pos"],
      ["Loss refund (" + Math.round((bank.lossRate || 0) * 100) + "%)", eur(refund, true), "pos"],
      ["Overall profit", eur(overall, true), cls(overall)]
    ];
    $("tiles").innerHTML = tiles.map(([k, v, c]) =>
      `<div class="tile"><p class="k">${k}</p><div class="v ${c}">${v}</div></div>`
    ).join("");

    // ---- by month ----
    const mKeys = Object.keys(months).sort().reverse();
    const mBody = $("months").querySelector("tbody");
    if (!mKeys.length) {
      mBody.innerHTML = `<tr><td class="muted">No settled matches yet.</td></tr>`;
    } else {
      mBody.innerHTML =
        `<tr><th>Month</th><th class="n">Settled</th><th class="n">Turnover</th>` +
        `<th class="n">Settlement P&amp;L</th><th class="n">Site A net</th><th class="n">Est. credit</th></tr>` +
        mKeys.map(k => {
          const mo = months[k];
          const credit = (bank.commRate || 0) * mo.turnover + (bank.lossRate || 0) * Math.max(0, -mo.net);
          return `<tr>
            <td>${monthLabel(k)}</td>
            <td class="n">${mo.count}</td>
            <td class="n">${eur(mo.turnover)}</td>
            <td class="n ${cls(mo.total)}">${eur(mo.total, true)}</td>
            <td class="n ${cls(mo.net)}">${eur(mo.net, true)}</td>
            <td class="n pos">${eur(credit)}</td>
          </tr>`;
        }).join("");
    }

    // ---- activity history ----
    $("evcount").textContent = events.length + " event" + (events.length === 1 ? "" : "s");
    const eBody = $("events").querySelector("tbody");
    if (!events.length) {
      eBody.innerHTML = `<tr><td class="muted">No activity yet. Save a match in the calculator.</td></tr>`;
    } else {
      eBody.innerHTML =
        `<tr><th>When</th><th>Event</th><th>Match</th><th>Detail</th></tr>` +
        events.map(ev => {
          const d = ev.detail || {};
          let detail = "";
          if (ev.type === "settled") {
            detail = (d.settlement ? eur(d.settlement.total, true) + " settlement" : "") +
              (d.winner != null ? ` · ${["1", "X", "2"][d.winner] || d.winner} won` : "");
          } else if (ev.type === "saved" || ev.type === "updated") {
            detail = (d.stake != null ? "stake " + eur(d.stake) : "") + (d.status ? " · " + d.status : "");
          } else if (ev.type === "bankroll") {
            detail = `A ${eur(d.A || 0)} · B ${eur(d.B || 0)} · E ${eur(d.E || 0)}`;
          } else if (ev.type === "month_paid" || ev.type === "month_unpaid") {
            detail = d.month ? monthLabel(d.month) : "";
          }
          return `<tr>
            <td class="muted">${dt(ev.ts)}</td>
            <td><span class="ev ${ev.type}">${EV_LABEL[ev.type] || ev.type}</span></td>
            <td>${esc(ev.matchName || "—")}</td>
            <td class="muted">${detail}</td>
          </tr>`;
        }).join("");
    }
  }).catch(err => {
    document.querySelector(".wrap").insertAdjacentHTML("beforeend",
      `<section class="panel" style="margin-top:24px"><p class="neg">Couldn't reach the database API. Is the server running? (<code>npm start</code>)</p></section>`);
    console.error(err);
  });
})();
