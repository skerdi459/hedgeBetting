/* db.js — SQLite persistence for Hedge Slip.
 *
 * One file on disk (hedge.db). Three tables:
 *   matches    — one row per tracked match (JSON blobs for the nested bits)
 *   bankroll   — single row (id=1): starting balances + rates + paid months
 *   events     — append-only history log (the "history" the dashboard reads)
 *
 * The frontend talks to this through the REST API in server.js. The match row
 * is round-tripped back into the exact shape store.js/app.js already expect.
 */
const Database = require("better-sqlite3");
const path = require("path");

const DB_PATH = process.env.HEDGE_DB || path.join(__dirname, "hedge.db");
const db = new Database(DB_PATH);
db.pragma("journal_mode = WAL");

db.exec(`
  CREATE TABLE IF NOT EXISTS matches (
    id             TEXT PRIMARY KEY,
    name           TEXT,
    saved_at       INTEGER,
    status         TEXT,
    stake          REAL,
    refund         REAL,
    mode           TEXT,
    cover_on_a     INTEGER,
    turnover_a     REAL,
    result         INTEGER,
    settled_at     INTEGER,
    option_json    TEXT,
    committed_json TEXT,
    settlement_json TEXT,
    vals_json      TEXT,
    updated_at     INTEGER
  );

  CREATE TABLE IF NOT EXISTS bankroll (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    a                REAL,
    b                REAL,
    e                REAL,
    comm_rate        REAL,
    loss_rate        REAL,
    paid_months_json TEXT,
    updated_at       INTEGER
  );

  CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER,
    type       TEXT,
    match_id   TEXT,
    match_name TEXT,
    detail_json TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts DESC);
`);

const now = () => Date.now();
const j = v => (v == null ? null : JSON.stringify(v));
const p = s => { try { return s == null ? null : JSON.parse(s); } catch { return null; } };

// ---- events (history) ----
const insEvent = db.prepare(
  `INSERT INTO events (ts, type, match_id, match_name, detail_json)
   VALUES (@ts, @type, @match_id, @match_name, @detail_json)`
);
function logEvent(type, { matchId = null, matchName = null, detail = null } = {}) {
  insEvent.run({ ts: now(), type, match_id: matchId, match_name: matchName, detail_json: j(detail) });
}

// ---- matches ----
function rowToMatch(r) {
  if (!r) return null;
  return {
    id: r.id,
    name: r.name,
    savedAt: r.saved_at,
    status: r.status,
    stake: r.stake,
    refund: r.refund,
    mode: r.mode,
    coverOnA: !!r.cover_on_a,
    turnoverA: r.turnover_a,
    result: r.result,
    settledAt: r.settled_at,
    option: p(r.option_json),
    committed: p(r.committed_json),
    settlement: p(r.settlement_json),
    vals: p(r.vals_json) || {}
  };
}

const selMatches = db.prepare(`SELECT * FROM matches ORDER BY saved_at DESC`);
const selMatch = db.prepare(`SELECT * FROM matches WHERE id = ?`);
const upMatch = db.prepare(`
  INSERT INTO matches
    (id, name, saved_at, status, stake, refund, mode, cover_on_a, turnover_a,
     result, settled_at, option_json, committed_json, settlement_json, vals_json, updated_at)
  VALUES
    (@id, @name, @saved_at, @status, @stake, @refund, @mode, @cover_on_a, @turnover_a,
     @result, @settled_at, @option_json, @committed_json, @settlement_json, @vals_json, @updated_at)
  ON CONFLICT(id) DO UPDATE SET
    name=@name, saved_at=@saved_at, status=@status, stake=@stake, refund=@refund,
    mode=@mode, cover_on_a=@cover_on_a, turnover_a=@turnover_a, result=@result,
    settled_at=@settled_at, option_json=@option_json, committed_json=@committed_json,
    settlement_json=@settlement_json, vals_json=@vals_json, updated_at=@updated_at
`);
const delMatchStmt = db.prepare(`DELETE FROM matches WHERE id = ?`);

function matchToRow(m) {
  return {
    id: m.id,
    name: m.name ?? "Unnamed match",
    saved_at: m.savedAt ?? now(),
    status: m.status ?? "pending",
    stake: m.stake ?? null,
    refund: m.refund ?? null,
    mode: m.mode ?? null,
    cover_on_a: m.coverOnA ? 1 : 0,
    turnover_a: m.turnoverA ?? null,
    result: m.result ?? null,
    settled_at: m.settledAt ?? null,
    option_json: j(m.option),
    committed_json: j(m.committed),
    settlement_json: j(m.settlement),
    vals_json: j(m.vals),
    updated_at: now()
  };
}

function listMatches() {
  return selMatches.all().map(rowToMatch);
}

function saveMatch(m) {
  const existing = selMatch.get(m.id);
  upMatch.run(matchToRow(m));
  logEvent(existing ? "updated" : "saved", {
    matchId: m.id, matchName: m.name,
    detail: { status: m.status, stake: m.stake, option: m.option && m.option.key }
  });
  return rowToMatch(selMatch.get(m.id));
}

function patchMatch(id, patch) {
  const cur = rowToMatch(selMatch.get(id));
  if (!cur) return null;
  const merged = { ...cur, ...patch };
  upMatch.run(matchToRow(merged));
  let type = "updated";
  if (patch.status === "settled") type = "settled";
  else if (patch.status === "pending" && cur.status === "settled") type = "reopened";
  logEvent(type, {
    matchId: id, matchName: merged.name,
    detail: {
      result: merged.result,
      settlement: merged.settlement,
      winner: patch.result
    }
  });
  return merged;
}

function deleteMatch(id) {
  const cur = rowToMatch(selMatch.get(id));
  delMatchStmt.run(id);
  logEvent("deleted", { matchId: id, matchName: cur && cur.name });
  return !!cur;
}

// ---- bankroll ----
const DEFAULT_BANKROLL = { A: 0, B: 0, E: 0, commRate: 0.08, lossRate: 0.2, paidMonths: {} };
const selBankroll = db.prepare(`SELECT * FROM bankroll WHERE id = 1`);
const upBankroll = db.prepare(`
  INSERT INTO bankroll (id, a, b, e, comm_rate, loss_rate, paid_months_json, updated_at)
  VALUES (1, @a, @b, @e, @comm_rate, @loss_rate, @paid_months_json, @updated_at)
  ON CONFLICT(id) DO UPDATE SET
    a=@a, b=@b, e=@e, comm_rate=@comm_rate, loss_rate=@loss_rate,
    paid_months_json=@paid_months_json, updated_at=@updated_at
`);

function getBankroll() {
  const r = selBankroll.get();
  if (!r) return null;
  return {
    A: r.a, B: r.b, E: r.e,
    commRate: r.comm_rate, lossRate: r.loss_rate,
    paidMonths: p(r.paid_months_json) || {}
  };
}

function saveBankroll(b) {
  const cur = getBankroll() || DEFAULT_BANKROLL;
  const merged = { ...cur, ...b, paidMonths: b.paidMonths || cur.paidMonths };
  upBankroll.run({
    a: merged.A ?? 0, b: merged.B ?? 0, e: merged.E ?? 0,
    comm_rate: merged.commRate ?? 0.08, loss_rate: merged.lossRate ?? 0.2,
    paid_months_json: j(merged.paidMonths || {}), updated_at: now()
  });
  logEvent("bankroll", { detail: { A: merged.A, B: merged.B, E: merged.E, commRate: merged.commRate, lossRate: merged.lossRate } });
  return merged;
}

function setMonthPaid(key, paid) {
  const b = getBankroll() || DEFAULT_BANKROLL;
  const pm = { ...(b.paidMonths || {}) };
  if (paid) pm[key] = true; else delete pm[key];
  const merged = { ...b, paidMonths: pm };
  upBankroll.run({
    a: merged.A ?? 0, b: merged.B ?? 0, e: merged.E ?? 0,
    comm_rate: merged.commRate ?? 0.08, loss_rate: merged.lossRate ?? 0.2,
    paid_months_json: j(pm), updated_at: now()
  });
  logEvent(paid ? "month_paid" : "month_unpaid", { detail: { month: key } });
  return merged;
}

// ---- history / state ----
const selEvents = db.prepare(`SELECT * FROM events ORDER BY ts DESC, id DESC LIMIT ?`);
function listEvents(limit = 500) {
  return selEvents.all(limit).map(e => ({
    id: e.id, ts: e.ts, type: e.type,
    matchId: e.match_id, matchName: e.match_name,
    detail: p(e.detail_json)
  }));
}

function getState() {
  return { matches: listMatches(), bankroll: getBankroll() };
}

module.exports = {
  db, DB_PATH, DEFAULT_BANKROLL,
  listMatches, saveMatch, patchMatch, deleteMatch,
  getBankroll, saveBankroll, setMonthPaid,
  listEvents, getState, logEvent
};
