# Bet Scanner

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
