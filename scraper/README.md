# Bet Scanner

Two tools in one folder:

1. **Two-site arbitrage scanner** (new) — compares **Vegas777** vs **bwin** and
   lists the games where a 2-way *surebet* exists. See **Arbitrage scanner** below.
2. **Cashback edge scanner** (original) — ranks one book by the guaranteed
   "dutch on Site A" edge from the 8% turnover + 20% net-loss deal (further down).

---

## Arbitrage scanner (Vegas777 vs bwin, 2-way)

Finds games where backing opposite outcomes of the same binary market (e.g.
**Over 2.5** on one site, **Under 2.5** on the other) locks a profit:

```
arb = 1/O_best_Over + 1/O_best_Under      # best odd per side across the two sites
arb < 1  ->  surebet     ROI = 1/arb - 1
stake split for total T:  S_i = T·(1/O_i)/arb   ->  same return T/arb either way
```

Files: `arb_scan.py` (the maths + game matching + report), `bwin_odds.py` (bwin
fetch/parse), `run_arb.py` (one-command orchestrator). Credentials live in the
gitignored `config.json` (Vegas login + bwin URL).

### Run it

Both sites bot-check headless browsers, so drive a real one by hand once:

```bash
# 1) capture bwin's Over/Under football view (log in / accept cookies, open the
#    OVER-UNDER market, then press Enter)
.venv/bin/python bwin_odds.py --manual --json bwin.json

# 2) capture Vegas777 (manual login), export its odds
.venv/bin/python bet_scanner.py --manual-login --json out.json

# 3) cross them for 2-way arbitrage
.venv/bin/python run_arb.py --stake 1000 --min-roi 0
```

Re-parse saved pages with no browser: `--vegas-html last_page.html`,
`--bwin-html last_bwin.html`. Check the maths with no sites at all:

```bash
.venv/bin/python arb_scan.py --demo      # built-in self-test
```

> **bwin selectors:** bwin's markup is a React SPA; the CSS selectors in
> `bwin_odds.py` (`SELECTORS`) are provisional. If a saved page parses to 0
> games, open `last_bwin.html` and adjust them — that's the one bit that needs a
> real captured page to pin down.

---

## Cashback edge scanner (original)

Scrapes a bookmaker's football page and ranks matches by the **guaranteed
"dutch on Site A" edge**, using your 8% turnover + 20% net-loss deal.

> ⚠️ Scraping usually breaks a bookmaker's Terms of Service, and these accounts
> get limited/banned for arbitrage. Use your own account, go slow, and treat this
> as personal tooling. Only you are responsible for how it's used.

## Setup

```bash
cd scraper
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

You also need Google Chrome installed (Selenium 4 finds the driver automatically).

## Credentials — kept on YOUR machine only

Copy the example config and fill it in (this file is gitignored, never committed):

```bash
cp config.example.json config.json
```

```json
{
  "odds_url": "https://your-book/sport/football",
  "login_url": "https://your-book/login",
  "username": "me",
  "password": "secret",
  "selectors": { "user": "#username", "pass": "#password", "submit": "button[type=submit]" }
}
```

`selectors` are the CSS selectors of the login form fields — right-click the
username box → Inspect to find them. If auto-login is fiddly, skip username/
password and just use `--manual-login` (log in by hand once in the window).

## Run

```bash
# log in by hand in the opened browser, then it scrapes
.venv/bin/python bet_scanner.py --manual-login

# fully automatic (uses config.json)
.venv/bin/python bet_scanner.py --top 10 --min-edge 3

# test the parser on a saved page, no browser
.venv/bin/python bet_scanner.py --html sample_page.html

# export for the web app
.venv/bin/python bet_scanner.py --json out.json
```

## Options

| flag | meaning |
|------|---------|
| `--url` | odds page URL (overrides config) |
| `--html FILE` | parse a saved HTML file instead of scraping |
| `--manual-login` | open browser, you log in, press Enter |
| `--headless` | run browser hidden (not with manual login) |
| `--comm 0.08` | turnover commission rate |
| `--loss 0.20` | net-loss refund rate |
| `--stake 1000` | turnover per match for the € column |
| `--top N` / `--min-edge X` | filter the table |
| `--json FILE` | also write results to JSON |

## What the numbers mean

- **Edge%** = guaranteed profit as a share of turnover cycled through Site A,
  from `comm − (M−1)/M × (1 − loss)`, where `M` is the book margin.
- Positive edge = profit on **every** result (the commission beats the margin).
- It picks the cheaper of the 1X2 (3-way) and Over/Under (2-way) market per match.

## Notes / robustness

- If the page markup changes, update the CSS selectors in `parse_matches()`.
- A faster, less brittle option long-term is to capture the site's JSON API
  (DevTools → Network) instead of scraping the DOM — ask and I'll adapt it.
