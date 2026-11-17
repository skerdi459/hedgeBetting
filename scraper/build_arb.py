#!/usr/bin/env python3
"""build_arb.py — combine Site A (Vegas) and Site B (Polymarket) odds into one
dataset and inject it into ../TestArbritageBetting.html so the calculator shows
real, ranked matches.

Pipeline:
  Vegas 1X2  (from bet_scanner: live scrape, a saved page, or an existing JSON)
    + Polymarket 1X2  (poly_odds.fetch_poly, matched by team names)
    -> combined.json
    -> injected between the LIVE_DATA markers in TestArbritageBetting.html

Usage:
  # reuse the Vegas odds already in out.json (fast, no browser)
  .venv/bin/python build_arb.py

  # re-parse a saved Vegas page, then add Polymarket
  .venv/bin/python build_arb.py --html last_page.html

  # full fresh scrape: log into Vegas by hand, then add Polymarket
  .venv/bin/python build_arb.py --scrape
"""
import argparse, json, os, re, sys
from datetime import datetime

import bet_scanner
from poly_odds import fetch_poly

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.normpath(os.path.join(HERE, "..", "TestArbritageBetting.html"))
MARK_A = "/*LIVE_DATA_START*/"
MARK_B = "/*LIVE_DATA_END*/"


def vegas_rows(args):
    """Return Vegas match dicts (home/away/o1/oX/o2/time)."""
    if args.scrape:
        cfg = bet_scanner.load_config()
        html = bet_scanner.fetch_html(cfg, manual_login=True)
        with open(os.path.join(HERE, "last_page.html"), "w", encoding="utf-8") as f:
            f.write(html)
        return bet_scanner.parse_matches(html)
    if args.html:
        with open(os.path.join(HERE, args.html), encoding="utf-8") as f:
            return bet_scanner.parse_matches(f.read())
    # default: reuse existing JSON produced by bet_scanner --json
    path = os.path.join(HERE, args.vegas)
    if not os.path.exists(path):
        sys.exit(f"{args.vegas} not found. Run bet_scanner first, or use --html / --scrape.")
    with open(path) as f:
        return json.load(f)


def build(args):
    rows = vegas_rows(args)
    out, skipped = [], []
    for r in rows:
        o1, oX, o2 = r.get("o1"), r.get("oX"), r.get("o2")
        if not (o1 and oX and o2) or r.get("locked_1x2"):
            skipped.append((r.get("home"), r.get("away"), "no/locked A odds"))
            continue
        home, away = r["home"], r["away"]
        poly = fetch_poly(home, away)
        if not poly or not (poly.get("b_home") and poly.get("b_away")):
            skipped.append((home, away, "no Polymarket match"))
            continue
        vmargin = round(1/o1 + 1/oX + 1/o2, 4)
        out.append({
            "name": f"{home}–{away}",
            "time": r.get("time", ""),
            "a": [o1, oX, o2],
            "b": [poly.get("b_home"), poly.get("b_draw"), poly.get("b_away")],
            "polyTitle": poly.get("title"),
            "polyMargin": poly.get("margin"),
            "vegasMargin": vmargin,
        })
        print(f"OK  {home}–{away:<22} A {o1}/{oX}/{o2}  B {poly['b_home']}/{poly['b_draw']}/{poly['b_away']}")

    for h, a, why in skipped:
        print(f"--  {h}–{a}  ({why})")
    print(f"\n{len(out)} matches with both sites · {len(skipped)} skipped")
    return out


def write_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Wrote {path}")


def inject(data, loss):
    with open(TARGET, encoding="utf-8") as f:
        html = f.read()
    if MARK_A not in html or MARK_B not in html:
        sys.exit(f"Markers {MARK_A}/{MARK_B} not found in {TARGET}. "
                 "Is this the updated TestArbritageBetting.html?")
    meta = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "comm": 0.08, "loss": loss, "source": "vegas+polymarket",
    }
    block = (f"{MARK_A}\n"
             f"window.LIVE_MATCHES = {json.dumps(data, ensure_ascii=False)};\n"
             f"window.LIVE_META = {json.dumps(meta)};\n"
             f"{MARK_B}")
    new = re.sub(re.escape(MARK_A) + r".*?" + re.escape(MARK_B), lambda _: block, html, flags=re.S)
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"Injected {len(data)} matches into {TARGET}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vegas", default="out.json", help="existing Vegas JSON (default out.json)")
    ap.add_argument("--html", help="parse this saved Vegas page instead")
    ap.add_argument("--scrape", action="store_true", help="fresh Vegas scrape (manual login)")
    ap.add_argument("--loss", type=float, default=0.20, help="Site A loss refund for the HTML (default 0.20)")
    ap.add_argument("--out", default="combined.json", help="combined output file")
    args = ap.parse_args()

    data = build(args)
    if not data:
        sys.exit("No matches had both Site A and Site B odds — nothing to inject.")
    write_json(data, os.path.join(HERE, args.out))
    inject(data, args.loss)


if __name__ == "__main__":
    main()
