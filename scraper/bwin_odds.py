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


# bwin renders odds into SHADOW DOM, so page_source is empty of odds. This JS
# walks every shadow root and returns the fully-rendered HTML (light + shadow).
_DEEP_JS = r"""
function deep(root){
  let out = "";
  const els = root.querySelectorAll('*');
  for (const el of els){
    if (el.shadowRoot){
      out += el.shadowRoot.innerHTML;
      out += deep(el.shadowRoot);
    }
  }
  return out;
}
return document.documentElement.outerHTML + deep(document);
"""


def _dump_api_json(driver):
    """Grab bwin's odds API (CDS) JSON responses from the network log."""
    import re
    blobs = []
    try:
        logs = driver.get_log("performance")
    except Exception:
        return blobs
    seen = set()
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except Exception:
            continue
        if msg.get("method") != "Network.responseReceived":
            continue
        resp = msg.get("params", {}).get("response", {})
        url = resp.get("url", "")
        rid = msg["params"].get("requestId")
        if rid in seen:
            continue
        if re.search(r"cds-api|bettingoffer|fixtures|offer", url, re.I):
            seen.add(rid)
            try:
                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                blobs.append({"url": url, "body": body.get("body", "")})
            except Exception:
                pass
    return blobs


def _expand_over_under(driver):
    """Click open any collapsed 'Total Goals' / 'Over/Under' market so bwin
    lazy-loads its odds into the DOM before we capture."""
    import time as _t
    from selenium.webdriver.common.by import By
    titles = ["total goals", "over/under", "over / under", "goals over/under"]
    try:
        headers = driver.find_elements(By.CSS_SELECTOR, "[slot='title'], .ds-accordion-header")
    except Exception:
        headers = []
    clicked = 0
    for h in headers:
        try:
            txt = (h.text or "").strip().lower()
            if any(t in txt for t in titles):
                # click the header (or its clickable ancestor button)
                target = h
                try:
                    target = h.find_element(By.XPATH, "./ancestor-or-self::button[1]")
                except Exception:
                    pass
                driver.execute_script("arguments[0].click();", target)
                clicked += 1
                _t.sleep(1)
        except Exception:
            continue
    if clicked:
        print(f"  expanded {clicked} Over/Under market(s)")
        _t.sleep(2)
    return clicked


def fetch_bwin(url, manual=True, headless=False, wait=40):
    import re
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1500,1000")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=opts)
    try:
        try:
            driver.execute_cdp_cmd("Network.enable", {})
        except Exception:
            pass
        driver.get(url)
        if manual:
            input("\n>>> In the browser: accept cookies, then OPEN A MATCH (click a game) so "
                  "its markets show.\n    Then press Enter here — I'll expand Over/Under and capture...")

        # Expand any collapsed "Total Goals" / "Over/Under" market so its odds load.
        _expand_over_under(driver)

        # Poll the DEEP (shadow-DOM-inclusive) HTML until real odds appear.
        html = ""
        for i in range(wait):
            try:
                html = driver.execute_script(_DEEP_JS)
            except Exception:
                html = driver.page_source
            n_odds = len(re.findall(r"\b[1-9]\d?\.\d{2}\b", html or ""))
            if n_odds >= 10:
                print(f"  odds rendered ({n_odds} decimal values found) after {i}s")
                break
            time.sleep(1)
        else:
            print("  ⚠ still few/no odds in the DOM after waiting — saving what we have.")

        dump = os.path.join(HERE, "last_bwin.html")
        with open(dump, "w", encoding="utf-8") as f:
            f.write(html or "")
        print(f"Saved deep bwin DOM to {dump} ({len(html or '')} bytes)")

        # Also save the raw odds API JSON (most reliable source to parse).
        blobs = _dump_api_json(driver)
        if blobs:
            apath = os.path.join(HERE, "bwin_api.json")
            with open(apath, "w", encoding="utf-8") as f:
                json.dump(blobs, f, ensure_ascii=False)
            print(f"Captured {len(blobs)} bwin API response(s) to {apath} "
                  f"({sum(len(b['body']) for b in blobs)} bytes)")
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


def _panel_options(panel):
    """Return [(name, odd)] for the ms-option cells inside a market panel."""
    out = []
    for opt in panel.select("ms-option, ms-event-pick"):
        name_el = opt.select_one(".name")
        val_el = opt.select_one(".option-value, .value.option-value, .value")
        name = name_el.get_text(" ", strip=True) if name_el else ""
        odd = _num(val_el.get_text() if val_el else "")
        if name and odd:
            out.append((name, odd))
    return out


def parse_bwin(html):
    """Parse a bwin EVENT-DETAILS page into the common game shape.

    Real structure (confirmed from a live page): the scoreboard holds the two
    participants in `.participant-name-value`; each market is an `ms-option-panel`
    whose `[slot=title]` is the market name and whose `ms-option` cells carry a
    `.name` and an `.option-value`. Over/Under lives in the "Total Goals" panel —
    which is a collapsed accordion by default, so its odds are only present if the
    panel was expanded before the page was captured (see fetch_bwin).
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # two participants from the scoreboard (dedupe, keep order)
    names = []
    for e in soup.select(".participant-name-value, ms-scoreboard-participant .participant-name"):
        t = e.get_text(" ", strip=True)
        if t and t not in names:
            names.append(t)
    if len(names) < 2:
        return []   # not an event page we can read (e.g. still the loading shell)
    home, away = names[0], names[1]

    markets = {}
    for panel in soup.select("ms-option-panel"):
        title_el = panel.select_one('[slot="title"]')
        title = (title_el.get_text(" ", strip=True) if title_el else "").lower()
        opts = _panel_options(panel)
        if not opts:
            continue
        # Over/Under (Total Goals)
        if "total goals" in title or "over/under" in title or "over / under" in title:
            over = under = None
            for name, odd in opts:
                nl = name.lower()
                if over is None and ("over" in nl or nl.startswith("o")):
                    over = odd
                elif under is None and ("under" in nl or nl.startswith("u")):
                    under = odd
            if over and under:
                markets["OU2.5"] = {"Over": over, "Under": under}

    if markets:
        return [{"home": home, "away": away, "time": "", "markets": markets}]
    return []


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
