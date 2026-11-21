#!/usr/bin/env python3
"""run_arb.py — one command: get Vegas777 + bwin odds and list the surebets.

Typical flow (browser you drive by hand, because both sites bot-check headless):

    # 1) capture bwin's Over/Under football view
    .venv/bin/python bwin_odds.py --manual --json bwin.json

    # 2) capture Vegas777 (manual login), export its odds
    .venv/bin/python bet_scanner.py --manual-login --json out.json

    # 3) cross them for 2-way arbitrage
    .venv/bin/python run_arb.py --stake 1000 --min-roi 0

Shortcuts: --vegas-html last_page.html / --bwin-html last_bwin.html re-parse saved
pages with no browser; --scrape-vegas does the Vegas manual-login for you.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bet_scanner
import bwin_odds
import arb_scan


def get_vegas(args):
    if args.scrape_vegas:
        cfg = bet_scanner.load_config()
        html = bet_scanner.fetch_html(cfg, manual_login=True)
        rows = bet_scanner.parse_matches(html)
    elif args.vegas_html:
        with open(os.path.join(HERE, args.vegas_html), encoding="utf-8") as f:
            rows = bet_scanner.parse_matches(f.read())
    else:
        path = os.path.join(HERE, args.vegas)
        if not os.path.exists(path):
            sys.exit(f"{args.vegas} not found. Run bet_scanner.py --json out.json first, "
                     "or pass --vegas-html / --scrape-vegas.")
        with open(path) as f:
            rows = json.load(f)
    return arb_scan.vegas_to_common(rows)


def get_bwin(args):
    if args.bwin_html:
        with open(os.path.join(HERE, args.bwin_html), encoding="utf-8") as f:
            return bwin_odds.parse_bwin(f.read())
    path = os.path.join(HERE, args.bwin)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    sys.exit(f"{args.bwin} not found. Run bwin_odds.py --manual --json bwin.json first, "
             "or pass --bwin-html last_bwin.html.")


def main():
    ap = argparse.ArgumentParser(description="Scan Vegas777 vs bwin for 2-way arbitrage")
    ap.add_argument("--vegas", default="out.json", help="Vegas JSON from bet_scanner (default out.json)")
    ap.add_argument("--vegas-html", help="parse a saved Vegas page instead")
    ap.add_argument("--scrape-vegas", action="store_true", help="fresh Vegas manual-login scrape")
    ap.add_argument("--bwin", default="bwin.json", help="bwin JSON from bwin_odds (default bwin.json)")
    ap.add_argument("--bwin-html", help="parse a saved bwin page instead")
    ap.add_argument("--stake", type=float, default=1000)
    ap.add_argument("--min-roi", type=float, default=0.0, help="hide arbs below this ROI%%")
    ap.add_argument("--json", default="arbs.json", help="write surebets here (default arbs.json)")
    args = ap.parse_args()

    a = get_vegas(args)
    b = get_bwin(args)
    print(f"Vegas777: {len(a)} games with O/U · bwin: {len(b)} games with O/U")
    arbs = arb_scan.find_arbs(a, b, stake=args.stake, min_roi=args.min_roi)
    arb_scan.print_report(arbs, args.stake)
    if args.json:
        out = os.path.join(HERE, args.json)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(arbs, f, indent=2, ensure_ascii=False)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
