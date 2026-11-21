#!/usr/bin/env python3
"""arb_scan.py — find 2-way ARBITRAGE (surebets) between two sites.

Rule (two opposite outcomes of the same binary market, e.g. Over 2.5 / Under 2.5):

    take the BEST odd for each outcome across the two sites
    arb = 1/O_best_1 + 1/O_best_2
    arb < 1  ->  guaranteed profit on every result (a surebet)
    ROI      =  1/arb - 1
    stake split for total T:  S_i = T * (1/O_i) / arb   ->  return T/arb either way

Input: two lists of games in the COMMON shape produced by the adapters:

    {
      "home": "Partizani", "away": "Tirana", "time": "20:00",
      "markets": { "OU2.5": {"Over": 2.10, "Under": 1.80}, ... }
    }

Games are matched across the sites by fuzzy team-name comparison (orientation-
independent — two-way totals like Over/Under don't depend on home/away order).

Usage:
    python arb_scan.py --a vegas.json --b bwin.json --stake 1000 --min-roi 0.5
    python arb_scan.py --demo          # run the built-in self-test (no scraping)
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Reuse the team-name matcher that already works for this project.
try:
    from poly_odds import _norm, _teams_match
except Exception:  # pragma: no cover - keep arb_scan usable standalone
    import re, unicodedata
    _STOP = {"fc", "cf", "sc", "the", "of", "and", "u20", "u21", "u23", "women", "w"}

    def _norm(s):
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
        return set(w for w in s.split() if w not in _STOP)

    def _teams_match(a, b):
        x, y = _norm(a), _norm(b)
        if not x or not y:
            return False
        return x <= y or y <= x or len(x & y) >= 1


# ----------------------------- matching -----------------------------
def same_game(ga, gb):
    """True if two games refer to the same fixture (either home/away order)."""
    ah, aa, bh, ba = ga["home"], ga["away"], gb["home"], gb["away"]
    return ((_teams_match(ah, bh) and _teams_match(aa, ba)) or
            (_teams_match(ah, ba) and _teams_match(aa, bh)))


def match_games(a_games, b_games):
    """Yield (game_a, game_b) pairs for fixtures found on both sites."""
    used = set()
    for ga in a_games:
        for i, gb in enumerate(b_games):
            if i in used:
                continue
            if same_game(ga, gb):
                used.add(i)
                yield ga, gb
                break


# ----------------------------- the arb maths -----------------------------
def two_way_arb(odd1, odd2):
    """Return the arb sum and ROI for backing both opposite outcomes.
    Returns None if either odd is missing/invalid."""
    if not odd1 or not odd2 or odd1 <= 1 or odd2 <= 1:
        return None
    arb = 1.0 / odd1 + 1.0 / odd2
    return {"arb": arb, "roi": (1.0 / arb) - 1.0}


def stake_split(odd1, odd2, total):
    """How to split `total` across the two legs so profit is identical."""
    arb = 1.0 / odd1 + 1.0 / odd2
    s1 = total * (1.0 / odd1) / arb
    s2 = total * (1.0 / odd2) / arb
    ret = total / arb
    return {"s1": s1, "s2": s2, "return": ret, "profit": ret - total}


def scan_market(ga, gb, market_key, stake):
    """Check one shared 2-way market on a matched game for a surebet.
    Returns a result dict if it IS an arb, else None."""
    ma, mb = ga["markets"].get(market_key), gb["markets"].get(market_key)
    if not ma or not mb:
        return None
    labels = sorted(set(ma) & set(mb))
    if len(labels) != 2:
        return None  # need both opposite outcomes on both sites
    l1, l2 = labels

    # best (highest) odd for each outcome across the two sites, with its source
    def best(label):
        cands = [(ma.get(label), "A"), (mb.get(label), "B")]
        cands = [(o, s) for o, s in cands if o and o > 1]
        return max(cands, key=lambda x: x[0]) if cands else (None, None)

    (o1, s1site), (o2, s2site) = best(l1), best(l2)
    # A placeable two-site arb needs its two legs at DIFFERENT sites — a single
    # book never prices 1/O1+1/O2 < 1, so same-site "arbs" are noise.
    if s1site and s1site == s2site:
        return None
    m = two_way_arb(o1, o2)
    if not m or m["arb"] >= 1.0:
        return None

    split = stake_split(o1, o2, stake)
    return {
        "game": f'{ga["home"]} – {ga["away"]}',
        "time": ga.get("time") or gb.get("time") or "",
        "market": market_key,
        "leg1": {"outcome": l1, "odd": o1, "site": s1site, "stake": round(split["s1"], 2)},
        "leg2": {"outcome": l2, "odd": o2, "site": s2site, "stake": round(split["s2"], 2)},
        "arb": round(m["arb"], 4),
        "roi": m["roi"],
        "profit": round(split["profit"], 2),
        "stake": stake,
    }


def find_arbs(a_games, b_games, stake=1000.0, min_roi=0.0):
    """Return every 2-way surebet across the two sites, ranked by ROI."""
    out = []
    for ga, gb in match_games(a_games, b_games):
        keys = set(ga["markets"]) & set(gb["markets"])
        for mk in keys:
            res = scan_market(ga, gb, mk, stake)
            if res and res["roi"] * 100 >= min_roi:
                out.append(res)
    out.sort(key=lambda r: r["roi"], reverse=True)
    return out


# ----------------------------- adapters -----------------------------
SITE = {"A": "Vegas777", "B": "bwin"}


def vegas_to_common(rows):
    """Convert bet_scanner.parse_matches() output into the common game shape.
    (2-way only: we take the Over/Under market.)"""
    games = []
    for r in rows:
        markets = {}
        over, under, line = r.get("over"), r.get("under"), (r.get("ou_line") or "").strip()
        if over and under:
            key = "OU" + (line or "2.5")
            markets[key] = {"Over": float(over), "Under": float(under)}
        if markets:
            games.append({"home": r.get("home", ""), "away": r.get("away", ""),
                          "time": r.get("time", ""), "markets": markets})
    return games


def load_games(path, adapter=None):
    """Load a JSON file of games. If it looks like raw Vegas rows, convert it."""
    with open(path) as f:
        data = json.load(f)
    if adapter == "vegas":
        return vegas_to_common(data)
    # auto-detect: raw Vegas rows have 'over'/'o1' keys, common shape has 'markets'
    if data and isinstance(data, list) and data[0].get("markets") is None:
        return vegas_to_common(data)
    return data


# ----------------------------- report -----------------------------
def print_report(arbs, stake):
    if not arbs:
        print("\nNo 2-way surebets found between the two sites.\n"
              "(That's normal — real cross-book arbs are rare and short-lived.)\n")
        return
    print(f"\n{len(arbs)} surebet(s) found · stake €{int(stake)} per game\n")
    print(f"{'#':<3}{'Game':<32}{'Time':<7}{'Market':<9}{'Back 1':<22}{'Back 2':<22}{'ROI%':>6}{'€':>9}")
    print("-" * 112)
    for i, a in enumerate(arbs, 1):
        l1, l2 = a["leg1"], a["leg2"]
        leg1 = f'{l1["outcome"]} @{l1["odd"]:.2f} {SITE[l1["site"]]} (€{l1["stake"]:.0f})'
        leg2 = f'{l2["outcome"]} @{l2["odd"]:.2f} {SITE[l2["site"]]} (€{l2["stake"]:.0f})'
        print(f"{i:<3}{a['game'][:31]:<32}{a['time']:<7}{a['market']:<9}"
              f"{leg1:<22}{leg2:<22}{a['roi']*100:>5.2f}{a['profit']:>9.2f}")
    print("\nBack each leg at the site shown. Profit is guaranteed on either result.")
    print("Confirm the odds are still live before placing the second bet.\n")


# ----------------------------- demo / self-test -----------------------------
def _demo():
    a = [  # Vegas777 (common shape)
        {"home": "Partizani", "away": "Tirana", "time": "20:00",
         "markets": {"OU2.5": {"Over": 2.10, "Under": 1.72}}},
        {"home": "Arsenal", "away": "Chelsea", "time": "18:30",
         "markets": {"OU2.5": {"Over": 1.95, "Under": 1.85}}},
        {"home": "Barcelona", "away": "Real Madrid", "time": "21:00",
         "markets": {"OU2.5": {"Over": 1.50, "Under": 2.50}}},
    ]
    b = [  # bwin (common shape) — team names deliberately slightly different
        {"home": "KF Tirana", "away": "FK Partizani", "time": "20:00",
         "markets": {"OU2.5": {"Over": 1.90, "Under": 2.05}}},   # Over@A 2.10 + Under@B 2.05 -> arb
        {"home": "Arsenal FC", "away": "Chelsea FC", "time": "18:30",
         "markets": {"OU2.5": {"Over": 1.88, "Under": 1.90}}},   # best 1.95 + 1.90 -> no arb
        {"home": "Man City", "away": "Liverpool", "time": "19:45",
         "markets": {"OU2.5": {"Over": 2.00, "Under": 2.00}}},   # no matching game
    ]
    print("Running self-test (3 games, Vegas777 vs bwin)...")
    arbs = find_arbs(a, b, stake=1000, min_roi=0)
    print_report(arbs, 1000)
    assert len(arbs) == 1, f"expected 1 arb, got {len(arbs)}"
    one = arbs[0]
    assert one["market"] == "OU2.5"
    # Over 2.10 (Vegas) + Under 2.05 (bwin): arb = .4762+.4878 = .9640, ROI 3.73%
    assert abs(one["arb"] - 0.9640) < 0.001, one["arb"]
    assert abs(one["roi"] - 0.0373) < 0.001, one["roi"]
    assert one["leg1"]["site"] == "A" and one["leg2"]["site"] == "B"
    assert abs((one["leg1"]["stake"] + one["leg2"]["stake"]) - 1000) < 0.5
    print("SELF-TEST PASSED ✓  (matched flipped team names, found the one real surebet)\n")


# ----------------------------- cli -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Find 2-way arbitrage between two sites")
    ap.add_argument("--a", help="JSON of Site A (Vegas777) games")
    ap.add_argument("--b", help="JSON of Site B (bwin) games")
    ap.add_argument("--stake", type=float, default=1000, help="total stake per game (default 1000)")
    ap.add_argument("--min-roi", type=float, default=0.0, help="hide arbs below this ROI%% (default 0)")
    ap.add_argument("--json", help="also write the surebets to this JSON file")
    ap.add_argument("--demo", action="store_true", help="run the built-in self-test and exit")
    args = ap.parse_args()

    if args.demo:
        _demo()
        return
    if not args.a or not args.b:
        sys.exit("Need --a and --b JSON files (or use --demo). "
                 "Produce them with bet_scanner.py (Vegas) and bwin_odds.py (bwin).")

    a_games = load_games(args.a)
    b_games = load_games(args.b)
    print(f"Site A: {len(a_games)} games · Site B: {len(b_games)} games")
    arbs = find_arbs(a_games, b_games, stake=args.stake, min_roi=args.min_roi)
    print_report(arbs, args.stake)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(arbs, f, indent=2, ensure_ascii=False)
        print(f"Wrote {args.json}")


if __name__ == "__main__":
    main()
