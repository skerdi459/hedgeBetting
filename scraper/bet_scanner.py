#!/usr/bin/env python3
"""
bet_scanner.py — scrape a bookmaker's football page and rank matches by the
GUARANTEED "dutch on Site A" edge, using the 8% turnover + 20% net-loss deal.

Dutch edge (as a fraction of turnover):
    edge = comm - (M-1)/M * (1 - loss)
where M = combined book margin (sum of 1/odds). Positive edge = guaranteed
profit on every result, purely from the turnover commission beating the margin.

Credentials are read from config.json (kept on your machine, gitignored) or you
can log in by hand with --manual-login. NEVER hard-code passwords in this file.

Usage:
    pip install -r requirements.txt
    python bet_scanner.py --manual-login                  # log in by hand, then scrape
    python bet_scanner.py                                 # uses config.json (auto-login)
    python bet_scanner.py --html saved_page.html          # parse a saved file (no browser)
    python bet_scanner.py --top 10 --min-edge 3 --json out.json
"""
import argparse, json, os, sys, time
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")


# ----------------------------- config -----------------------------
def load_config():
    """config.json shape (all optional):
    {
      "odds_url":  "https://site/sport/football",
      "login_url": "https://site/login",
      "username":  "me", "password": "...",
      "selectors": {"user": "#username", "pass": "#password", "submit": "button[type=submit]"}
    }
    """
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


# ----------------------------- scraping -----------------------------
def _grab_match_html(driver, wait):
    """The Vegas777 app renders matches inside nested <iframe>s, so the outer
    page_source never contains any .match-content. Walk into every frame, find
    the one that actually holds the match list, and return its HTML. Falls back
    to the top document if no frame has matches (e.g. page structure changed)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    def _has_matches():
        try:
            return bool(driver.find_elements(By.CSS_SELECTOR, "app-match, .match-content"))
        except Exception:
            return False

    # Remember the biggest document we saw, so a miss still gives real markup.
    richest = {"html": "", "size": 0}

    def _remember():
        try:
            src = driver.page_source
        except Exception:
            return
        if len(src) > richest["size"]:
            richest["html"], richest["size"] = src, len(src)

    def _search(depth=0):
        try:
            WebDriverWait(driver, 8).until(lambda d: _has_matches())
        except Exception:
            pass
        _remember()
        if _has_matches():
            return driver.page_source
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
        for i in range(len(frames)):
            # Re-fetch each loop: switching frames invalidates earlier handles.
            fr = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
            if i >= len(fr):
                break
            try:
                driver.switch_to.frame(fr[i])
                html = _search(depth + 1)
                if html:
                    return html
            except Exception:
                pass
            finally:
                driver.switch_to.parent_frame()
        return None

    driver.switch_to.default_content()
    html = _search()
    if html:
        return html
    # Nothing matched anywhere — return the richest frame so the dump is useful.
    driver.switch_to.default_content()
    print("Warning: no frame contained app-match/.match-content — "
          "returning the richest frame found for inspection.")
    return richest["html"] or driver.page_source


def fetch_html(cfg, manual_login=False, headless=False, wait=25):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    odds_url = cfg.get("odds_url")
    if not odds_url:
        sys.exit("No odds_url. Put it in config.json or pass --url.")

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=opts)
    try:
        # --- login ---
        if manual_login:
            driver.get(cfg.get("login_url") or odds_url)
            input("\n>>> Log in AND navigate to the football list, then press Enter here...")
            time.sleep(1)
            return _grab_match_html(driver, wait)  # dive into the app iframe
        elif cfg.get("username") and cfg.get("login_url"):
            sel = cfg.get("selectors", {})
            driver.get(cfg["login_url"])
            WebDriverWait(driver, wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel.get("user", "input[name=username]"))))
            driver.find_element(By.CSS_SELECTOR, sel.get("user", "input[name=username]")).send_keys(cfg["username"])
            driver.find_element(By.CSS_SELECTOR, sel.get("pass", "input[name=password]")).send_keys(cfg["password"])
            driver.find_element(By.CSS_SELECTOR, sel.get("submit", "button[type=submit]")).click()
            time.sleep(4)

        # --- odds page ---
        driver.get(odds_url)
        time.sleep(2)  # let odds settle
        return _grab_match_html(driver, wait)
    finally:
        driver.quit()


# ----------------------------- parsing -----------------------------
def _odd(el):
    """Return (float_odds_or_None, is_locked) for a .bet cell."""
    if el is None:
        return None, False
    locked = el.select_one(".lock-odd") is not None
    spans = el.select("span")
    txt = (spans[-1].get_text() if spans else el.get_text()).strip().replace(",", ".")
    try:
        return float(txt), locked
    except ValueError:
        return None, locked


def parse_matches(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for mc in soup.select(".match-content"):
        home = mc.select_one(".team-names .home")
        away = mc.select_one(".team-names .away")
        tm = mc.select_one(".info .time") or mc.select_one(".sub-info .time")
        code = mc.select_one(".info .code")
        line = mc.select_one(".market-container .msbv")
        bets = mc.select(".market-container .bet")  # order: 1, X, 2, Over, Under, (E2...)
        vals = [_odd(b) for b in bets]

        def g(i):
            return vals[i] if i < len(vals) else (None, False)

        o1, l1 = g(0); oX, lX = g(1); o2, l2 = g(2)
        over, lo = g(3); under, lu = g(4)
        if not (home and away):
            continue
        out.append({
            "home": home.get_text(strip=True),
            "away": away.get_text(strip=True),
            "time": tm.get_text(strip=True) if tm else "",
            "code": code.get_text(strip=True) if code else "",
            "o1": o1, "oX": oX, "o2": o2, "locked_1x2": l1 or lX or l2,
            "ou_line": line.get_text(strip=True) if line else "",
            "over": over, "under": under,
        })
    return out


# ----------------------------- analysis -----------------------------
def margin(odds):
    odds = [o for o in odds if o and o > 1]
    return sum(1.0 / o for o in odds) if odds else None


def dutch_edge(odds, comm, loss):
    """Guaranteed profit as a fraction of turnover from dutching all `odds`."""
    M = margin(odds)
    if M is None or M <= 0:
        return None
    margin_cost = (M - 1) / M            # fraction of turnover lost to the book
    return comm - margin_cost * (1 - loss), M


def analyze(matches, comm, loss):
    rows = []
    for m in matches:
        best = None
        # 3-way 1X2 dutch (needs all three, none locked)
        if m["o1"] and m["oX"] and m["o2"] and not m["locked_1x2"]:
            e3 = dutch_edge([m["o1"], m["oX"], m["o2"]], comm, loss)
            if e3:
                best = max(filter(None, [best, (e3[0], "1X2", e3[1])]), key=lambda x: x[0]) if best else (e3[0], "1X2", e3[1])
        # 2-way Over/Under dutch
        if m["over"] and m["under"]:
            e2 = dutch_edge([m["over"], m["under"]], comm, loss)
            if e2:
                cand = (e2[0], "O/U " + m["ou_line"], e2[1])
                best = cand if (best is None or cand[0] > best[0]) else best
        m = dict(m)
        if best:
            m["edge"], m["market"], m["margin"] = best
        else:
            m["edge"], m["market"], m["margin"] = None, "-", None
        rows.append(m)
    rows.sort(key=lambda r: (r["edge"] is not None, r["edge"] or -9), reverse=True)
    return rows


# ----------------------------- output -----------------------------
def print_report(rows, stake, top, min_edge):
    print(f"\n{'#':<3}{'Match':<34}{'Time':<7}{'1':>6}{'X':>7}{'2':>7}{'Mgn%':>7}{'Market':>10}{'Edge%':>7}{'€/'+str(int(stake)):>9}")
    print("-" * 100)
    shown = 0
    for r in rows:
        if r["edge"] is None:
            continue
        if min_edge is not None and r["edge"] * 100 < min_edge:
            continue
        if top and shown >= top:
            break
        shown += 1
        name = f"{r['home']}–{r['away']}"[:33]
        eur = r["edge"] * stake
        print(f"{shown:<3}{name:<34}{r['time']:<7}"
              f"{_f(r['o1']):>6}{_f(r['oX']):>7}{_f(r['o2']):>7}"
              f"{r['margin']*100:>6.1f}{r['market']:>10}{r['edge']*100:>6.2f}{eur:>9.2f}")
    if not shown:
        print("  (no dutchable matches found — check login / page loaded / selectors)")
    print("\nEdge% is guaranteed profit as a share of the money you cycle through Site A.")
    print(f"€/{int(stake)} = guaranteed profit if you dutch {int(stake)} of turnover on that match.\n")


def _f(x):
    return f"{x:.2f}" if x else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="odds page URL (overrides config.json)")
    ap.add_argument("--html", help="parse a saved HTML file instead of scraping")
    ap.add_argument("--manual-login", action="store_true", help="open browser, you log in by hand")
    ap.add_argument("--headless", action="store_true", help="run browser hidden (not with --manual-login)")
    ap.add_argument("--comm", type=float, default=0.08, help="turnover commission (default 0.08)")
    ap.add_argument("--loss", type=float, default=0.20, help="net-loss refund (default 0.20)")
    ap.add_argument("--stake", type=float, default=1000, help="turnover per match for € column")
    ap.add_argument("--top", type=int, default=0, help="show only top N")
    ap.add_argument("--min-edge", type=float, default=None, help="hide matches below this edge%%")
    ap.add_argument("--json", help="also write results to this JSON file")
    args = ap.parse_args()

    cfg = load_config()
    if args.url:
        cfg["odds_url"] = args.url

    if args.html:
        with open(args.html, encoding="utf-8") as f:
            html = f.read()
    else:
        html = fetch_html(cfg, manual_login=args.manual_login, headless=args.headless)
        # Always keep the raw page so we can inspect/fix selectors after a run.
        dump = os.path.join(HERE, "last_page.html")
        with open(dump, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved raw page to {dump} ({len(html)} bytes)")

    matches = parse_matches(html)
    print(f"Parsed {len(matches)} matches.")
    rows = analyze(matches, args.comm, args.loss)
    print_report(rows, args.stake, args.top, args.min_edge)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(rows, f, indent=2)
        print(f"Wrote {args.json}")


if __name__ == "__main__":
    main()
