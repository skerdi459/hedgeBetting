/* store.js — localStorage persistence. Exposes window.HS.store
 *
 * Matches (key hedge-slip-matches): array of tracked matches.
 *   { id, name, savedAt, status:"pending"|"settled",
 *     stake, refund, option, committed:{A,B,E},
 *     vals:{...inputs}, result:null|0|1|2, settlement:null|{A,B,E,total} }
 *
 * Bankroll (key hedge-slip-bankroll): starting balance per site { A, B, E }.
 */
(function () {
  const HS = (window.HS = window.HS || {});
  const MK = "hedge-slip-matches";
  const BK = "hedge-slip-bankroll";

  const read = (k, def) => {
    try {
      const v = JSON.parse(localStorage.getItem(k));
      return v == null ? def : v;
    } catch (e) {
      return def;
    }
  };
  const write = (k, v) => {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {}
  };

  const uid = () => "m" + Date.now().toString(36) + Math.floor(Math.random() * 1e6).toString(36);

  // Fire-and-forget mirror to the SQLite backend. localStorage stays the
  // instant source of truth for the UI; the server is the durable history.
  // Failures (e.g. opened as a file:// page, or server down) are ignored so
  // the app keeps working fully offline.
  const API = "/api";
  const canSync = typeof fetch === "function" && /^https?:$/.test(location.protocol);
  const send = (method, pathname, body) => {
    if (!canSync) return;
    try {
      fetch(API + pathname, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        keepalive: true
      }).catch(() => {});
    } catch (e) {}
  };
  HS.sync = { send, canSync, API };

  HS.store = {
    matches: () => read(MK, []),
    saveMatches: m => write(MK, m),
    addMatch(m) {
      const list = this.matches();
      list.unshift(m);
      this.saveMatches(list.slice(0, 200));
      send("POST", "/matches", m);
      return list;
    },
    updateMatch(id, patch) {
      const list = this.matches().map(m => (m.id === id ? { ...m, ...patch } : m));
      this.saveMatches(list);
      send("PATCH", "/matches/" + encodeURIComponent(id), patch);
      return list;
    },
    deleteMatch(id) {
      const list = this.matches().filter(m => m.id !== id);
      this.saveMatches(list);
      send("DELETE", "/matches/" + encodeURIComponent(id));
      return list;
    },
    // bankroll: starting balances + Site A rates (turnover commission, loss refund) + paid months
    bankroll() {
      const b = read(BK, {});
      return {
        A: b.A || 0, B: b.B || 0, E: b.E || 0,
        commRate: b.commRate == null ? 0.08 : b.commRate, // 8% of turnover, unconditional
        lossRate: b.lossRate == null ? 0.20 : b.lossRate, // 20% of net monthly loss
        paidMonths: b.paidMonths || {}
      };
    },
    saveBankroll(b) {
      const cur = this.bankroll();
      const merged = { ...cur, ...b, paidMonths: b.paidMonths || cur.paidMonths };
      write(BK, merged);
      send("PUT", "/bankroll", merged);
    },
    setMonthPaid(key, paid) {
      const b = this.bankroll();
      b.paidMonths = { ...b.paidMonths };
      if (paid) b.paidMonths[key] = true; else delete b.paidMonths[key];
      write(BK, b);
      send("PUT", "/months/" + encodeURIComponent(key), { paid: !!paid });
    },
    uid
  };
})();
