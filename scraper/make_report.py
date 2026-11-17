#!/usr/bin/env python3
"""Build a standalone HTML report from bet_scanner's JSON output."""
import json, os, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out.json")
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "report.html")
stake = float(sys.argv[3]) if len(sys.argv) > 3 else 1000.0

rows = [r for r in json.load(open(src)) if r.get("edge") is not None]
rows.sort(key=lambda r: r["edge"], reverse=True)

def f(x):
    return f"{x:.2f}" if isinstance(x, (int, float)) else "—"

trs = []
for i, r in enumerate(rows, 1):
    name = html.escape(f"{r['home']}–{r['away']}")
    edge_pct = r["edge"] * 100
    eur = r["edge"] * stake
    cls = "pos" if r["edge"] > 0 else "neg"
    trs.append(f"""<tr class="{cls}">
      <td class="num">{i}</td><td class="match">{name}</td>
      <td>{html.escape(r.get('time',''))}</td>
      <td class="num">{f(r.get('o1'))}</td><td class="num">{f(r.get('oX'))}</td>
      <td class="num">{f(r.get('o2'))}</td>
      <td class="num">{r['margin']*100:.1f}%</td>
      <td>{html.escape(r.get('market','-'))}</td>
      <td class="num edge">{edge_pct:.2f}%</td>
      <td class="num eur">€{eur:.2f}</td></tr>""")

doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Dutch Edge Report — Vegas777</title>
<style>
 body{{font:15px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1216;color:#e6e6e6;margin:0;padding:28px}}
 h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#8a93a0;font-size:13px;margin-bottom:18px}}
 table{{border-collapse:collapse;width:100%;max-width:1000px;background:#171b21;border-radius:10px;overflow:hidden}}
 th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #222831}}
 th{{background:#1d222a;color:#9fb0c3;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
 .num{{text-align:right;font-variant-numeric:tabular-nums}}
 .match{{font-weight:600}} .edge{{font-weight:700}}
 tr.pos .edge,tr.pos .eur{{color:#4ade80}} tr.neg .edge,tr.neg .eur{{color:#f87171}}
 tr:hover td{{background:#1e242d}}
 .foot{{color:#8a93a0;font-size:12px;margin-top:16px;max-width:1000px}}
</style></head><body>
<h1>⚽ Dutch Edge Report — Vegas777</h1>
<div class="sub">{len(rows)} matches · profit shown per €{stake:.0f} of turnover · 8% commission, 20% net-loss refund</div>
<table>
 <thead><tr><th>#</th><th>Match</th><th>Time</th><th class="num">1</th><th class="num">X</th>
 <th class="num">2</th><th class="num">Mgn%</th><th>Market</th><th class="num">Edge%</th><th class="num">€/{stake:.0f}</th></tr></thead>
 <tbody>{''.join(trs)}</tbody>
</table>
<div class="foot">Edge% is guaranteed profit as a share of the money cycled through Site A.
€/{stake:.0f} = guaranteed profit if you dutch €{stake:.0f} of turnover on that match.</div>
</body></html>"""

open(out, "w").write(doc)
print(f"Wrote {out} ({len(rows)} rows)")
