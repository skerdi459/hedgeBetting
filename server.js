/* server.js — serves the Hedge Slip frontend and a small REST API backed by
 * SQLite (see db.js). Single-user personal tool: no auth, binds localhost.
 *
 *   npm start           → http://localhost:3000
 *   HEDGE_PORT=4000 ... → change port
 *   HEDGE_HOST=0.0.0.0  → expose on your LAN (e.g. to use from your phone)
 */
const express = require("express");
const path = require("path");
const dbx = require("./db");

const app = express();
app.use(express.json({ limit: "1mb" }));

// --- API ---
const api = express.Router();

api.get("/health", (_req, res) => res.json({ ok: true, db: dbx.DB_PATH }));

// Full current state (used by the frontend to hydrate on load)
api.get("/state", (_req, res) => res.json(dbx.getState()));

api.get("/matches", (_req, res) => res.json(dbx.listMatches()));

api.post("/matches", (req, res) => {
  const m = req.body;
  if (!m || !m.id) return res.status(400).json({ error: "match.id required" });
  res.json(dbx.saveMatch(m));
});

api.patch("/matches/:id", (req, res) => {
  const updated = dbx.patchMatch(req.params.id, req.body || {});
  if (!updated) return res.status(404).json({ error: "not found" });
  res.json(updated);
});

api.delete("/matches/:id", (req, res) => {
  dbx.deleteMatch(req.params.id);
  res.json({ ok: true });
});

api.get("/bankroll", (_req, res) => res.json(dbx.getBankroll() || dbx.DEFAULT_BANKROLL));

api.put("/bankroll", (req, res) => res.json(dbx.saveBankroll(req.body || {})));

api.put("/months/:key", (req, res) =>
  res.json(dbx.setMonthPaid(req.params.key, !!(req.body && req.body.paid)))
);

// History log for the dashboard
api.get("/events", (req, res) => {
  const limit = Math.min(parseInt(req.query.limit, 10) || 500, 5000);
  res.json(dbx.listEvents(limit));
});

app.use("/api", api);

// --- static frontend ---
app.use(express.static(__dirname, { extensions: ["html"] }));
app.get("/", (_req, res) => res.sendFile(path.join(__dirname, "index.html")));
app.get("/dashboard", (_req, res) => res.sendFile(path.join(__dirname, "dashboard.html")));

const PORT = process.env.HEDGE_PORT || process.env.PORT || 3000;
const HOST = process.env.HEDGE_HOST || "127.0.0.1";
app.listen(PORT, HOST, () => {
  console.log(`Hedge Slip running → http://${HOST === "0.0.0.0" ? "localhost" : HOST}:${PORT}`);
  console.log(`Dashboard         → http://${HOST === "0.0.0.0" ? "localhost" : HOST}:${PORT}/dashboard`);
  console.log(`Database          → ${dbx.DB_PATH}`);
});
