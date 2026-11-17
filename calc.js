/* calc.js — pure hedge/arbitrage math. No DOM. Exposes window.HS.calc
 *
 * Site A pays the player TWO things, monthly:
 *   tc = turnover commission (e.g. 8%) — paid on EVERYTHING staked on Site A,
 *        win or lose. Unconditional, so it is part of the GUARANTEED result.
 *   r  = loss refund (e.g. 20%) — paid on the NET loss on Site A for the month.
 *        Only a bonus; it needs the Site A account to end the month net-loss.
 *
 * Notation: S = Site A back stake, a = Site A odds of backed outcome k,
 * B[j] = Site B odds, dc[k] = Site B double-chance cover, L[k] = exchange lay, c = exchange commission.
 *
 * coverOnA: when true the cover bets are placed on Site A too (dutching), so
 * their stakes also earn the turnover commission (turnover = S + cover stakes).
 *
 * Methods:
 *   dc  (2-way): cover "not k" with a double chance.  H = S*a / dc[k]
 *   book(3-way): cover the other two outcomes.         H_j = S*a / B[j]
 *   lay (2-way): lay outcome k on an exchange.         L = S*a / (Lk - c)   (exchange, never Site A)
 */
(function () {
  const HS = (window.HS = window.HS || {});
  const OUT = ["1", "X", "2"];
  const DC_LABEL = ["X2", "12", "1X"];

  // inp = {mode, S, r, tc, c, minP, step, coverOnA, A:[], B:[], DC:[], L:[]}
  function compute(inp) {
    const mode = inp.mode === "3way" ? "3way" : "2way";
    const S = inp.S;
    const r = inp.r ?? 0;    // loss refund rate (net, monthly)
    const tc = inp.tc ?? 0;  // turnover commission rate (unconditional)
    const c = inp.c ?? 0;    // exchange commission
    const minP = inp.minP ?? 0;
    const step = inp.step || 0.01;
    const coverOnA = !!inp.coverOnA;
    const rnd = x => Math.round(x / step) * step;
    const A = inp.A, B = inp.B || [], DC = inp.DC || [], L = inp.L || [];
    const opts = [];

    if (!S || S <= 0) return { S, r, tc, mode, coverOnA, opts, minP, error: "Enter your Site A stake to start." };

    for (let k = 0; k < 3; k++) {
      const a = A[k];
      if (!a) continue;
      const refund = [0, 1, 2].map(i => (i === k ? 0 : r * S)); // loss-refund estimate (real one is monthly/net)

      if (mode === "2way" && DC[k]) {
        const H = rnd(S * a / DC[k]);
        const res = [0, 1, 2].map(i => (i === k ? S * (a - 1) - H : H * DC[k] - S - H));
        opts.push(build({ key: "d" + k, type: "dc", k, a, dc: DC[k], cover: H, total: H, res, refund, money: S + H }, S, tc, coverOnA, H));
      }

      if (mode === "3way" && [0, 1, 2].filter(j => j !== k).every(j => B[j])) {
        const others = [0, 1, 2].filter(j => j !== k);
        const bets = others.map(j => ({ j, odds: B[j], amt: rnd(S * a / B[j]) }));
        const total = bets.reduce((s, b) => s + b.amt, 0);
        const res = [0, 1, 2].map(i =>
          i === k ? S * (a - 1) - total : -S + bets.find(b => b.j === i).amt * B[i] - total
        );
        opts.push(build({ key: "b" + k, type: "book", k, a, bets, total, res, refund, money: S + total }, S, tc, coverOnA, total));
      }

      if (L[k] && L[k] - c > 0) {
        const lay = rnd(S * a / (L[k] - c));
        const liab = lay * (L[k] - 1);
        const res = [0, 1, 2].map(i => (i === k ? S * (a - 1) - liab : -S + lay * (1 - c)));
        opts.push(build({ key: "l" + k, type: "lay", k, a, lodds: L[k], lay, liab, total: 0, res, refund, money: S + liab }, S, tc, false, 0));
      }
    }

    // Rank by GUARANTEED result (settlement + unconditional commission), best first.
    opts.sort((x, y) => y.minGuar - x.minGuar);
    let error = null;
    if (!A.some(Boolean)) error = "Enter at least one Site A odd.";
    else if (!opts.length) {
      error = mode === "2way"
        ? "Add a double-chance cover odd for the result you back, or an exchange lay odd."
        : "Add Site B odds for the other two results, or an exchange lay odd for the result you back.";
    }
    return { S, r, tc, mode, coverOnA, opts, minP, error };
  }

  // Attach commission + derived metrics. coverOnB flag: if covers sit on Site A,
  // their stakes earn commission too (turnover = S + coverTotal).
  function build(o, S, tc, coverOnA, coverTotal) {
    o.coverOnA = coverOnA && o.type !== "lay";
    o.turnoverA = o.coverOnA ? S + coverTotal : S;
    o.commission = tc * o.turnoverA;             // unconditional, same on every result
    o.guaranteed = o.res.map(v => v + o.commission);
    o.resTotal = o.res.map((v, i) => v + o.commission + o.refund[i]); // full estimate incl loss refund
    o.minSettle = Math.min(...o.res);
    o.maxSettle = Math.max(...o.res);
    o.minGuar = o.minSettle + o.commission;      // guaranteed incl. commission (verdict basis)
    o.min = Math.min(...o.resTotal);             // optimistic incl. loss refund
    o.sureBet = o.minGuar > 0.004;               // guaranteed + on every result
    o.refundMax = Math.max(...o.refund);
    return o;
  }

  const hedgesToB = t => t === "book" || t === "dc";

  function committed(opt, S) {
    if (opt.coverOnA) return { A: S + opt.total, B: 0, E: 0 };
    if (opt.type === "lay") return { A: S, B: 0, E: opt.liab };
    return { A: S, B: hedgesToB(opt.type) ? opt.total : 0, E: 0 };
  }

  // Cash per site when outcome w wins (settlement only; commission/refund are monthly).
  function settle(opt, w, S) {
    if (opt.coverOnA) return { A: opt.res[w], B: 0, E: 0, total: opt.res[w] };
    const A = w === opt.k ? S * (opt.a - 1) : -S;
    const other = opt.res[w] - A;
    return hedgesToB(opt.type)
      ? { A, B: other, E: 0, total: opt.res[w] }
      : { A, B: 0, E: other, total: opt.res[w] };
  }

  HS.OUT = OUT;
  HS.DC_LABEL = DC_LABEL;
  HS.calc = { compute, committed, settle };
})();
