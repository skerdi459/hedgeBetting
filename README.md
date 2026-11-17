# Hedge Slip

Cashback-arbitrage **calculator + tracker** with a SQLite-backed history.

Enter the odds, the slip tells you what to bet where, you track each match and
keep a running per-site balance — and now every match, settlement and balance
change is **saved to a database** so your history survives cache clears, new
browsers and other devices. A separate **history dashboard** reads straight
from that database.

## Run it

```bash
npm install     # once
npm start       # → http://localhost:3000
```

- App:       http://localhost:3000
- Dashboard: http://localhost:3000/dashboard

The database is a single file, `hedge.db`, created automatically next to the
code. It is gitignored (it's your personal data).

### Options

| env var | meaning | default |
|---------|---------|---------|
| `HEDGE_PORT` | port to listen on | `3000` |
| `HEDGE_HOST` | `0.0.0.0` to reach it from your phone on the same Wi-Fi | `127.0.0.1` |
| `HEDGE_DB`   | path to the SQLite file | `./hedge.db` |

Example — use it from your phone on the same network:

```bash
HEDGE_HOST=0.0.0.0 npm start
# then open http://<your-computer-ip>:3000 on the phone
```

## How persistence works

- The browser still uses `localStorage` as an **instant, offline** cache, so the
  app works even with no server running (just open `index.html` directly).
- When served by the Node server, every change (`store.js`) is **mirrored** to
  the database through a small REST API, and on load the page **hydrates** from
  the database (`db-sync.js`).
- First time you run the server, any matches already in your browser's
  `localStorage` are **migrated up** into the database automatically.

## Architecture

| file | role |
|------|------|
| `index.html`, `styles.css` | app markup + styles |
| `calc.js` | the arbitrage math (pure, no DOM) |
| `store.js` | localStorage state **+ fire-and-forget mirror to the API** |
| `app.js` | DOM wiring: calculator slip, balance dashboard, tracker |
| `db-sync.js` | on load: hydrate from DB / migrate local data up |
| `server.js` | Express server: static files + REST API |
| `db.js` | SQLite schema and queries (`matches`, `bankroll`, `events`) |
| `dashboard.html`, `dashboard.js` | read-only history dashboard |
| `scraper/` | separate Python odds scanner (see `scraper/README.md`) |

### REST API

| method + path | purpose |
|---------------|---------|
| `GET /api/state` | current matches + bankroll (used to hydrate the app) |
| `GET /api/matches` · `POST /api/matches` | list / create-or-update a match |
| `PATCH /api/matches/:id` · `DELETE /api/matches/:id` | settle/reopen / delete |
| `GET /api/bankroll` · `PUT /api/bankroll` | balances + rates |
| `PUT /api/months/:key` | mark a month's refund paid/unpaid |
| `GET /api/events?limit=N` | the history log (powers the dashboard) |

### Database tables

- **matches** — one row per tracked match (nested bits stored as JSON).
- **bankroll** — single row: starting balances, commission/loss rates, paid months.
- **events** — append-only history: `saved`, `settled`, `reopened`, `deleted`,
  `bankroll`, `month_paid`, `month_unpaid`.

> Note: `TestArbritageBetting.html` is a standalone single-file copy of the app
> (localStorage only, no backend) kept for offline/deploy use.
