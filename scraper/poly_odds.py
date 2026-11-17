#!/usr/bin/env python3
"""poly_odds.py — fetch Polymarket (Site B) decimal odds for a football match.

Polymarket lists each match as an *event* titled "Home vs. Away" containing
three Yes/No *markets*: "Will {Home} win", "...end in a draw", "Will {Away} win".
The "Yes" price is the implied probability, so decimal odds = 1 / price.

Public, no auth: https://gamma-api.polymarket.com
"""
import json, re, unicodedata, urllib.parse, urllib.request

GAMMA = "https://gamma-api.polymarket.com"
_UA = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 (odds-tool)"}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _norm(s):
    """lowercase, strip accents & punctuation, collapse whitespace -> token set."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return set(w for w in s.split() if w not in _STOP)


# Words that don't help identify a country/club.
_STOP = {"fc", "cf", "sc", "the", "of", "and", "u20", "u21", "u23", "women", "w"}


def _teams_match(vegas_name, poly_side):
    """True if the Vegas team name and a Polymarket side refer to the same team."""
    v, p = _norm(vegas_name), _norm(poly_side)
    if not v or not p:
        return False
    # one side's significant tokens must be contained in the other's
    return v <= p or p <= v or len(v & p) >= 1 and (len(v & p) >= min(len(v), len(p)))


def _price(market, outcome_name="Yes"):
    try:
        outs = json.loads(market.get("outcomes") or "[]")
        prices = json.loads(market.get("outcomePrices") or "[]")
    except Exception:
        return None
    for o, pr in zip(outs, prices):
        if o.strip().lower() == outcome_name.lower():
            try:
                f = float(pr)
                return f if f > 0 else None
            except ValueError:
                return None
    return None


def _classify(question, home, away):
    """Return 'home' | 'draw' | 'away' | None for a market question."""
    q = question.lower()
    if "draw" in q or "end in a tie" in q:
        return "draw"
    # "Will {team} win ..."  -> extract team between 'will' and 'win'
    m = re.search(r"will\s+(.*?)\s+win", q)
    team = m.group(1) if m else q
    if _teams_match(home, team):
        return "home"
    if _teams_match(away, team):
        return "away"
    return None


def fetch_poly(home, away, timeout=25, debug=False):
    """Return {'b_home','b_draw','b_away','title','slug','margin'} decimal odds,
    or None if no open Polymarket match is found."""
    q = urllib.parse.quote(f"{home} {away}")
    try:
        data = _get(f"{GAMMA}/public-search?q={q}&limit_per_type=12", timeout)
    except Exception as e:
        if debug:
            print(f"    [poly] search error for {home} vs {away}: {e}")
        return None

    best = None
    for e in data.get("events", []) or []:
        if e.get("closed"):
            continue
        title = e.get("title", "")
        if " vs" not in title.lower():
            continue
        # split "Home vs. Away" (strip any "Competition: " prefix)
        t = re.sub(r"^[^:]*:\s*", "", title)
        sides = re.split(r"\s+vs\.?\s+", t, maxsplit=1, flags=re.I)
        if len(sides) != 2:
            continue
        s_home, s_away = sides
        # require both Vegas teams present in the two sides (either orientation)
        ok = ((_teams_match(home, s_home) and _teams_match(away, s_away)) or
              (_teams_match(home, s_away) and _teams_match(away, s_home)))
        if not ok:
            continue
        best = e
        break

    if not best:
        return None

    odds = {"b_home": None, "b_draw": None, "b_away": None}
    probs = {}
    for mk in best.get("markets", []):
        if mk.get("closed"):
            continue
        slot = _classify(mk.get("question", ""), home, away)
        if slot is None:
            continue
        p = _price(mk, "Yes")
        if not p:
            continue
        probs[slot] = p
        odds["b_" + slot] = round(1.0 / p, 2)

    if not any(odds.values()):
        return None
    odds["title"] = best.get("title")
    odds["slug"] = best.get("slug")
    odds["margin"] = round(sum(probs.values()), 4) if probs else None
    return odds


if __name__ == "__main__":
    import sys
    h, a = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("Germany", "Netherlands")
    print(json.dumps(fetch_poly(h, a, debug=True), indent=2))
