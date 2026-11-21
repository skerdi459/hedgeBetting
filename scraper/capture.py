#!/usr/bin/env python3
"""capture.py — ONE command to get tomorrow's matches and scan for arbitrage.

It opens a real browser for each site so YOU can pass the Vegas777 CAPTCHA and
bwin's cookie/login wall by hand (the only step a server can't do). Everything
after that — parsing, matching, the arbitrage scan, the HTML report — is
automatic.

    cd scraper
    .venv/bin/python capture.py                 # stake €1000 per game
    .venv/bin/python capture.py --stake 1500

For each site: a window opens → log in / accept cookies → open tomorrow's
FOOTBALL list (bwin: the OVER/UNDER view) → come back here and press Enter.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bet_scanner
import bwin_odds
import arb_scan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stake", type=float, default=1000)
    ap.add_argument("--min-roi", type=float, default=0.0)
    ap.add_argument("--skip-vegas", action="store_true", help="reuse existing out.json")
    ap.add_argument("--skip-bwin", action="store_true", help="reuse existing bwin.json")
    ap.add_argument("--bwin-all", action="store_true",
                    help="auto-walk every bwin match for Over/Under (vs one match)")
    args = ap.parse_args()

    # 1) Vegas777 (manual login — handles the CAPTCHA)
    if not args.skip_vegas:
        print("\n=== STEP 1/3 · Vegas777 ===")
        cfg = bet_scanner.load_config()
        html = bet_scanner.fetch_html(cfg, manual_login=True)
        rows = bet_scanner.parse_matches(html)
        json.dump(rows, open(os.path.join(HERE, "out.json"), "w"), indent=2, ensure_ascii=False)
        print(f"Vegas777: saved {len(rows)} matches to out.json")
    else:
        rows = json.load(open(os.path.join(HERE, "out.json")))

    # 2) bwin (manual — accept cookies, open the Over/Under view)
    if not args.skip_bwin:
        print("\n=== STEP 2/3 · bwin ===")
        bcfg = bwin_odds.load_bwin_cfg()
        url = bcfg.get("odds_url") or "https://www.bwin.com/en/sports/football-4"
        if args.bwin_all:
            bgames = bwin_odds.fetch_bwin_all(url, manual=True)
        else:
            bhtml = bwin_odds.fetch_bwin(url, manual=True)
            bgames = bwin_odds.parse_bwin(bhtml)
        json.dump(bgames, open(os.path.join(HERE, "bwin.json"), "w"), indent=2, ensure_ascii=False)
        print(f"bwin: parsed {len(bgames)} games with Over/Under to bwin.json")
        if not bgames:
            print("  ⚠ 0 bwin games parsed — open last_bwin.html and adjust SELECTORS "
                  "in bwin_odds.py, or make sure you captured the OVER/UNDER view.")
    else:
        bgames = json.load(open(os.path.join(HERE, "bwin.json")))

    # 3) scan + report
    print("\n=== STEP 3/3 · arbitrage scan ===")
    a = arb_scan.vegas_to_common(rows)
    arbs = arb_scan.find_arbs(a, bgames, stake=args.stake, min_roi=args.min_roi)
    arb_scan.print_report(arbs, args.stake)
    json.dump(arbs, open(os.path.join(HERE, "arbs.json"), "w"), indent=2, ensure_ascii=False)
    print("Wrote arbs.json — open the dashboard and it's already there (or press Scan now).")

    # best-effort: refresh the standalone HTML report
    try:
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "make_arb_report.py")], check=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
