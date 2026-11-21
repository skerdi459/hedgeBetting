#!/usr/bin/env python3
"""bwin_odds.py — fetch football odds from bwin (Site B) for arbitrage scanning.

bwin is a heavy React single-page app behind bot protection and geo rules, so
the reliable way to capture it is a REAL browser you drive by hand once:

    # open bwin, let it load (log in / accept cookies / pick the Over-Under
    # market view if needed), then press Enter — it saves the page and parses it
    .venv/bin/python bwin_odds.py --manual --json bwin.json

    # re-parse a page you already saved (no browser)
    .venv/bin/python bwin_odds.py --html last_bwin.html --json bwin.json

Output is the COMMON game shape arb_scan.py expects:
    {"home","away","time","markets":{"OU2.5":{"Over":..,"Under":..}}}

NOTE ON MARKETS (2-way): bwin's default football list shows 1X2, not Over/Under.
To arbitrage O/U against Vegas you must view bwin's "Total Goals / Over-Under"
market before saving the page. The parser below extracts Over/Under when those
cells are present. The CSS selectors are bwin's current structure as best known
and are centralised in SELECTORS — if a saved page parses to 0 games, open it
and adjust these (that's the one bit that needs a real page to pin down).
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

# --- Selectors (verify against a real saved page; see note above) ---
SELECTORS = {
    "event":       "ms-event, .grid-event-wrapper",          # one fixture row
    "participants": ".participant, .grid-info-wrapper .participant",
    "time":        ".starting-time, .time",
    "option_group": "ms-option-group, .grid-option-group",   # a market's cells
    "option":      "ms-option, .grid-option",                # one odds cell
    "option_label": ".name, .label",                         # "Over"/"Under"/"O 2.5"
    "option_value": ".value, .option-value, .odds",          # the decimal odd
}


def load_bwin_cfg():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return (json.load(f).get("bwin") or {})
    return {}


# ----------------------------- fetch -----------------------------
def fetch_bwin(url, manual=True, headless=False, wait=30):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1500,1000")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(url)
        if manual:
            input("\n>>> In the browser: accept cookies, log in if needed, and open the "
                  "FOOTBALL list on the OVER/UNDER market.\n    Then press Enter here to capture the page...")
        else:
            time.sleep(wait)
        html = driver.page_source
        dump = os.path.join(HERE, "last_bwin.html")
        with open(dump, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved raw bwin page to {dump} ({len(html)} bytes)")
        return html
    finally:
        driver.quit()


# ----------------------------- parse -----------------------------
def _num(txt):
    try:
        return float(re.sub(r"[^0-9.,]", "", txt or "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _is_over(label):
    l = (label or "").lower()
    return l.startswith("o") or "over" in l or l.startswith("+") or "más" in l


def _is_under(label):
    l = (label or "").lower()
    return l.startswith("u") or "under" in l or l.startswith("-") or "menos" in l


def parse_bwin(html):
    """Best-effort: pull fixtures + an Over/Under 2.5 market into the common shape."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    games = []
    for ev in soup.select(SELECTORS["event"]):
        parts = [p.get_text(strip=True) for p in ev.select(SELECTORS["participants"]) if p.get_text(strip=True)]
        if len(parts) < 2:
            continue
        home, away = parts[0], parts[1]
        tm_el = ev.select_one(SELECTORS["time"])
        tm = tm_el.get_text(strip=True) if tm_el else ""

        over = under = None
        for cell in ev.select(SELECTORS["option"]):
            lab_el = cell.select_one(SELECTORS["option_label"])
            val_el = cell.select_one(SELECTORS["option_value"])
            label = lab_el.get_text(strip=True) if lab_el else cell.get_text(" ", strip=True)
            value = _num(val_el.get_text() if val_el else "")
            if value is None:
                continue
            # only accept the 2.5 line (ignore other totals)
            if "2.5" in label or "2,5" in label or label in ("Over", "Under", "O", "U"):
                if over is None and _is_over(label):
                    over = value
                elif under is None and _is_under(label):
                    under = value

        markets = {}
        if over and under:
            markets["OU2.5"] = {"Over": over, "Under": under}
        if markets:
            games.append({"home": home, "away": away, "time": tm, "markets": markets})
    return games


# ----------------------------- cli -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Fetch/parse bwin football O/U odds")
    ap.add_argument("--url", help="bwin football URL (overrides config.json bwin.odds_url)")
    ap.add_argument("--html", help="parse a saved page instead of scraping")
    ap.add_argument("--manual", action="store_true", help="drive a real browser by hand (recommended)")
    ap.add_argument("--headless", action="store_true", help="run hidden (often blocked by bwin)")
    ap.add_argument("--json", help="write parsed games to this JSON file")
    args = ap.parse_args()

    if args.html:
        with open(os.path.join(HERE, args.html) if not os.path.isabs(args.html) else args.html,
                  encoding="utf-8") as f:
            html = f.read()
    else:
        cfg = load_bwin_cfg()
        url = args.url or cfg.get("odds_url") or "https://www.bwin.com/en/sports/football-4"
        html = fetch_bwin(url, manual=args.manual or not args.headless, headless=args.headless)

    games = parse_bwin(html)
    print(f"Parsed {len(games)} bwin games with an Over/Under 2.5 market.")
    if not games:
        print("  → 0 games. Open last_bwin.html and adjust the selectors in SELECTORS, "
              "or make sure you captured the OVER/UNDER market view.")
    for g in games[:10]:
        ou = g["markets"].get("OU2.5", {})
        print(f"  {g['home']} – {g['away']:<22} O {ou.get('Over')}  U {ou.get('Under')}")

    if args.json:
        out = os.path.join(HERE, args.json) if not os.path.isabs(args.json) else args.json
        with open(out, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=2, ensure_ascii=False)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
