/* db-sync.js — on page load, reconcile localStorage with the SQLite backend.
 *
 *  - DB empty + local data present  → migrate local data UP to the server (once).
 *  - DB has data                    → hydrate local storage DOWN from the server,
 *                                      then ask app.js to re-render (HS.refresh).
 *
 * Runs after calc.js/store.js/app.js. Safe no-op when opened as a file:// page
 * or when the server is unreachable (the app then stays localStorage-only).
 */
(function () {
  const HS = window.HS;
  if (!HS || !HS.sync || !HS.sync.canSync) return;

  const MK = "hedge-slip-matches";
  const BK = "hedge-slip-bankroll";
  const API = HS.sync.API;

  const readLocal = (k, def) => {
    try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? def : v; }
    catch (e) { return def; }
  };

  fetch(API + "/state")
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(state => {
      const serverMatches = Array.isArray(state.matches) ? state.matches : [];
      const localMatches = readLocal(MK, []);
      const localBankroll = readLocal(BK, null);

      if (serverMatches.length === 0 && !state.bankroll && localMatches.length) {
        // First run against an empty DB but we have local history → push it up.
        localMatches.forEach(m => HS.sync.send("POST", "/matches", m));
        if (localBankroll) HS.sync.send("PUT", "/bankroll", localBankroll);
        console.info("[hedge] migrated " + localMatches.length + " local match(es) to the database.");
        return;
      }

      // Server is the source of truth → mirror it into localStorage.
      localStorage.setItem(MK, JSON.stringify(serverMatches));
      if (state.bankroll) localStorage.setItem(BK, JSON.stringify(state.bankroll));
      if (typeof HS.refresh === "function") HS.refresh();
      console.info("[hedge] loaded " + serverMatches.length + " match(es) from the database.");
    })
    .catch(() => { /* offline / no server → keep using localStorage silently */ });
})();
