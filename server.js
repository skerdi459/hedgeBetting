/* server.js — serves the Hedge Slip frontend and a small REST API backed by
 * SQLite (see db.js). Single-user personal tool: no auth, binds localhost.
 *
 *   npm start           → http://localhost:3000
 *   HEDGE_PORT=4000 ... → change port
 *   HEDGE_HOST=0.0.0.0  → expose on your LAN (e.g. to use from your phone)
 */
const express = require("express");
const path = require("path");
const fs = require("fs");
const { execFile } = require("child_process");
const dbx = require("./db");

const app = express();
app.use(express.json({ limit: "1mb" }));

// Optional HTTP Basic auth. Enabled only when HEDGE_PASSWORD is set (e.g. on a
// public deploy); left open for local use. User defaults to "hedge".
const AUTH_PASS = process.env.HEDGE_PASSWORD;
const AUTH_USER = process.env.HEDGE_USER || "hedge";
if (AUTH_PASS) {
  app.use((req, res, next) => {
    const hdr = req.headers.authorization || "";
    const [, b64] = hdr.split(" ");
    const [u, p] = Buffer.from(b64 || "", "base64").toString().split(":");
    if (u === AUTH_USER && p === AUTH_PASS) return next();
    res.set("WWW-Authenticate", 'Basic realm="Hedge Slip"').status(401).send("Authentication required");
  });
  console.log("Auth: password protection ENABLED (user: " + AUTH_USER + ")");
}

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

// Live arbitrage opportunities produced by the scraper (scraper/arbs.json)
api.get("/arbs", (_req, res) => {
  const p = path.join(__dirname, "scraper", "arbs.json");
  try {
    const arbs = JSON.parse(fs.readFileSync(p, "utf8"));
    res.json({ updatedAt: fs.statSync(p).mtimeMs, count: arbs.length, arbs });
  } catch (e) {
    res.json({ updatedAt: null, count: 0, arbs: [] });
  }
});

// "Scan now" — re-run the arbitrage scanner over the captured odds
// (scraper/out.json + scraper/bwin.json) and regenerate the HTML report.
api.post("/scan", (req, res) => {
  const stake = Number(req.body && req.body.stake);
  const stakeArg = Number.isFinite(stake) && stake > 0 ? String(stake) : "1000";
  const dir = path.join(__dirname, "scraper");
  const venvPy = path.join(dir, ".venv", "bin", "python");
  const py = fs.existsSync(venvPy) ? venvPy : "python3";
  const tail = s => (s || "").trim().split("\n").filter(Boolean).slice(-4).join("\n");

  execFile(py, ["run_arb.py", "--stake", stakeArg, "--min-roi", "0"],
    { cwd: dir, timeout: 120000 }, (err, stdout, stderr) => {
      // best-effort refresh of the standalone HTML report, then respond
      execFile(py, ["make_arb_report.py"], { cwd: dir, timeout: 30000 }, () => {
        let arbs = [];
        try { arbs = JSON.parse(fs.readFileSync(path.join(dir, "arbs.json"), "utf8")); } catch (e) {}
        if (err && !arbs.length) {
          return res.json({ ok: false, error: tail(stderr) || tail(stdout) || err.message, arbs: [] });
        }
        res.json({ ok: true, count: arbs.length, arbs, log: tail(stdout) });
      });
    });
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
