#!/usr/bin/env python3
"""make_arb_report.py — standalone HTML report of 2-way surebets from arbs.json.

    .venv/bin/python make_arb_report.py                 # arbs.json -> arb_report.html
    .venv/bin/python make_arb_report.py arbs.json out.html 1000

Opens nothing; just writes the file. Double-click it (works with no server).
"""
import json, os, sys, html
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "arbs.json")
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "arb_report.html")

SITE = {"A": "Vegas777", "B": "bwin"}
arbs = json.load(open(src)) if os.path.exists(src) else []
arbs.sort(key=lambda a: a.get("roi", 0), reverse=True)

stake = arbs[0]["stake"] if arbs else 1000
total_profit = sum(a.get("profit", 0) for a in arbs)


def leg_html(l):
    site = SITE.get(l.get("site"), l.get("site", ""))
    return (f'<b>{html.escape(l.get("outcome",""))}</b> @{l.get("odd",0):.2f}'
            f' · <span class="site">{html.escape(site)}</span> · €{l.get("stake",0):.0f}')


trs = []
for i, a in enumerate(arbs, 1):
    trs.append(f"""<tr>
      <td class="num">{i}</td>
      <td class="match">{html.escape(a.get('game',''))}</td>
      <td>{html.escape(a.get('time',''))}</td>
      <td>{html.escape(a.get('market',''))}</td>
      <td>{leg_html(a.get('leg1',{}))}</td>
      <td>{leg_html(a.get('leg2',{}))}</td>
      <td class="num roi">+{a.get('roi',0)*100:.2f}%</td>
      <td class="num eur">€{a.get('profit',0):.2f}</td></tr>""")

empty = '<tr><td colspan="8" class="foot" style="padding:24px">No surebets in arbs.json. Run <code>run_arb.py</code>.</td></tr>'

doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arbitrage Report — Vegas777 × bwin</title>
<style>
 body{{font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1216;color:#e6e6e6;margin:0;padding:28px}}
 h1{{font-size:21px;margin:0 0 4px}} .sub{{color:#8a93a0;font-size:13px;margin-bottom:18px}}
 table{{border-collapse:collapse;width:100%;max-width:1150px;background:#171b21;border-radius:10px;overflow:hidden}}
 th,td{{padding:10px 13px;text-align:left;border-bottom:1px solid #222831;vertical-align:top}}
 th{{background:#1d222a;color:#9fb0c3;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
 .num{{text-align:right;font-variant-numeric:tabular-nums}}
 .match{{font-weight:600}} .roi,.eur{{font-weight:700;color:#4ade80}}
 .site{{color:#7fb2f0}} tr:hover td{{background:#1e242d}}
 code{{background:#222831;padding:1px 5px;border-radius:4px}}
 .foot{{color:#8a93a0;font-size:12px;margin-top:16px;max-width:1150px}}
 .tot{{display:inline-block;background:#14301f;color:#4ade80;padding:3px 10px;border-radius:999px;font-weight:700}}
</style></head><body>
<h1>⚽ Arbitrage Report — Vegas777 × bwin</h1>
<div class="sub">{len(arbs)} surebet(s) · €{stake:.0f} stake per game ·
 total guaranteed <span class="tot">€{total_profit:.2f}</span> ·
 generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<table>
 <thead><tr><th>#</th><th>Game</th><th>Time</th><th>Market</th>
 <th>Back leg 1</th><th>Back leg 2</th><th class="num">ROI</th><th class="num">Profit</th></tr></thead>
 <tbody>{''.join(trs) if trs else empty}</tbody>
</table>
<div class="foot">Each surebet backs both opposite outcomes, one leg at each site, so the
 profit is guaranteed whichever way the game goes. Odds move — confirm both are still live
 before placing the second bet.</div>
</body></html>"""

open(out, "w").write(doc)
print(f"Wrote {out} ({len(arbs)} surebets, €{total_profit:.2f} total)")
