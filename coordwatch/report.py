"""Self-contained HTML dashboard (no JS frameworks, no CDN: works offline, safe to e-mail).
All scraped text is HTML-escaped - posts are untrusted input."""
from __future__ import annotations

import math
from html import escape as e
from typing import Dict, List

PALETTE = {"telegram": "#2a9d8f", "x": "#264653", "youtube": "#e76f51", "tiktok": "#8d5fd3", "instagram": "#d6336c",
           "facebook": "#3b6fd4", "snapchat": "#c9a400"}
FALLBACK = ["#6c757d", "#1f77b4", "#bcbd22", "#17becf"]


def color(pl: str) -> str:
    return PALETTE.get(pl, FALLBACK[hash(pl) % len(FALLBACK)])


def stacked_bars(series: Dict[str, Dict[str, int]], w=860, h=190, label_fmt=None) -> str:
    buckets = sorted({b for s in series.values() for b in s})
    if not buckets:
        return "<p class=muted>no data</p>"
    if label_fmt is None:
        hourly = len(buckets) > 1 and buckets[0][:10] == buckets[-1][:10] or any(b[11:13] != '00' for b in buckets)
        label_fmt = (lambda s: s[5:10] + ' ' + s[11:13] + 'h') if hourly else (lambda s: s[5:10])
    plats = sorted(series)
    tot = [sum(series[p].get(b, 0) for p in plats) for b in buckets]
    mx = max(tot) or 1
    pad_l, pad_b, pad_t = 34, 22, 8
    bw = (w - pad_l) / len(buckets)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="volume over time" class=chart>']
    for g in range(0, 5):
        y = pad_t + (h - pad_b - pad_t) * (1 - g / 4)
        out.append(f'<line x1={pad_l} x2={w} y1={y:.1f} y2={y:.1f} stroke="#e5e7eb"/>'
                   f'<text x=0 y={y + 4:.1f} class=ax>{math.ceil(mx * g / 4)}</text>')
    for i, b in enumerate(buckets):
        y = h - pad_b
        for p in plats:
            v = series[p].get(b, 0)
            if not v:
                continue
            bh = (h - pad_b - pad_t) * v / mx
            y -= bh
            out.append(f'<rect x={pad_l + i * bw + 1:.1f} y={y:.1f} width={max(bw - 2, 1):.1f} height={bh:.1f} '
                       f'fill="{color(p)}"><title>{e(b)} {e(p)}: {v}</title></rect>')
        if len(buckets) <= 16 or i % math.ceil(len(buckets) / 14) == 0:
            out.append(f'<text x={pad_l + i * bw:.1f} y={h - 6} class=ax>{e(label_fmt(b))}</text>')
    out.append("</svg>")
    out.append('<div class=legend>' + "".join(f'<span><i style="background:{color(p)}"></i>{e(p)}</span>' for p in plats) + "</div>")
    return "".join(out)


def spark(series: Dict[str, int], buckets: List[str], w=140, h=28) -> str:
    vals = [series.get(b, 0) for b in buckets]
    mx = max(vals) or 1
    step = w / max(len(vals) - 1, 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (h - 4) * v / mx:.1f}" for i, v in enumerate(vals))
    return f'<svg width={w} height={h} class=spark><polyline points="{pts}" fill=none stroke="#264653" stroke-width=1.5 /></svg>'


def group_graph(g: dict, w=420, h=300) -> str:
    accts = g["accounts"][:40]
    n = len(accts)
    pos = {a: (w / 2 + (w / 2 - 28) * math.cos(2 * math.pi * i / n), h / 2 + (h / 2 - 22) * math.sin(2 * math.pi * i / n))
           for i, a in enumerate(accts)}
    out = [f'<svg viewBox="0 0 {w} {h}" class=graph role=img aria-label="account links in group {e(g["id"])}">']
    for ed in g["edges"]:
        if ed["a"] in pos and ed["b"] in pos:
            (x1, y1), (x2, y2) = pos[ed["a"]], pos[ed["b"]]
            out.append(f'<line x1={x1:.1f} y1={y1:.1f} x2={x2:.1f} y2={y2:.1f} stroke="#94a3b8" stroke-opacity=".35"/>')
    for a, (x, y) in pos.items():
        out.append(f'<circle cx={x:.1f} cy={y:.1f} r=5 fill="{color(a.split(":")[0])}"><title>{e(a)}</title></circle>')
    out.append("</svg>")
    return "".join(out)


CSS = """
body{font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1f2937}
header{background:#0f172a;color:#fff;padding:18px 28px}header h1{margin:0;font-size:20px}header p{margin:4px 0 0;color:#cbd5e1}
main{max-width:1180px;margin:0 auto;padding:18px 20px 60px}section{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin:16px 0}
h2{margin:0 0 10px;font-size:17px}h3{margin:14px 0 6px;font-size:14px}.cards{display:flex;gap:12px;flex-wrap:wrap}
.card{flex:1;min-width:150px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px}.card b{display:block;font-size:22px}
table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #eef0f3;padding:6px 8px;text-align:left;vertical-align:top}th{font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.03em}
.muted{color:#6b7280}.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;background:#eef2ff;color:#3730a3}
.high{background:#fee2e2;color:#991b1b}.medium{background:#fef3c7;color:#92400e}.low{background:#e0f2fe;color:#075985}
.chart{width:100%;height:auto}.ax{font-size:10px;fill:#6b7280}.legend span{margin-right:14px;font-size:12px}.legend i{display:inline-block;width:10px;height:10px;margin-right:4px;border-radius:2px}
.grid{display:grid;grid-template-columns:1fr 430px;gap:16px}.graph{width:100%;background:#f8fafc;border-radius:8px}
.q{font-style:italic;color:#374151;background:#f9fafb;border-left:3px solid #cbd5e1;padding:4px 10px;margin:4px 0;word-break:break-word}
details{margin:6px 0}summary{cursor:pointer;font-weight:600}input#f{padding:6px 10px;width:320px;border:1px solid #cbd5e1;border-radius:6px;margin-bottom:8px}
code{background:#f1f5f9;padding:1px 4px;border-radius:4px}.warn{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:8px 12px;margin:6px 0}
a{color:#1d4ed8;text-decoration:none}a:hover{text-decoration:underline}
"""

JS = """
document.getElementById('f').addEventListener('input',function(){var q=this.value.toLowerCase();
document.querySelectorAll('#posts tbody tr').forEach(function(r){r.style.display=r.textContent.toLowerCase().indexOf(q)<0?'none':''})});
"""


def short(t: str, n=220) -> str:
    t = " ".join((t or "").split())
    return e(t if len(t) <= n else t[:n - 1] + "…")


def render(result: dict, max_posts: int = 400) -> str:
    m = result["meta"]
    nars = [n for n in result["narratives"]]
    posts = result["posts"]
    ptext = {(p["platform"], p["id"]): p for p in posts}
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>coordwatch - {e(m['topic'])}</title><style>{CSS}</style></head><body>"]
    h.append(f"<header><h1>Coordinated activity &amp; narrative report: “{e(m['topic'])}”</h1>"
             f"<p>{e((m['since'] or '')[:10])} → {e((m['until'] or '')[:10])} · platforms: {e(', '.join(m['platforms']))} · generated {e(m['generated_at'][:19])}Z</p></header><main>")
    cards = [("Posts", m["n_posts"]), ("Accounts", m["n_accounts"]), ("Narratives", m["n_narratives"]),
             ("Coordinated groups", m["n_groups"]), ("Coordinated accounts", m["coordinated_accounts"]),
             ("Posts by coordinated accts", f"{m['coordinated_post_share']:.0%}")]
    h.append("<section><div class=cards>" + "".join(f"<div class=card><span class=muted>{e(k)}</span><b>{e(str(v))}</b></div>" for k, v in cards) + "</div>")
    for note in m.get("collector_notes", []):
        h.append(f"<div class=warn>⚠ {e(note)}</div>")
    h.append("<p class=muted>Findings are <b>investigative leads, not attribution</b>: coordination ≠ inauthenticity, and "
             "every signal has benign explanations (see README → Limitations).</p></section>")

    h.append(f"<section><h2>Volume over time ({e(m['bucket'])}s, per platform)</h2>{stacked_bars(result['volume']['by_platform'])}</section>")

    # narratives
    buckets = sorted(result["volume"]["total"])
    h.append("<section><h2>Main narratives</h2><table><tr><th>#</th><th>Narrative (top terms)</th><th>Posts</th><th>Accts</th><th>Platforms</th>"
             "<th>Over time</th><th>Coordinated</th><th>Example</th></tr>")
    for n in nars:
        ex = ptext.get(next(((p["platform"], p["id"]) for p in posts if p["id"] == (n["representative_posts"] or [None])[0] and p["narrative_id"] == n["id"]), None))
        pl = " ".join(f'<span class=tag style="background:{color(k)}22;color:{color(k)}">{e(k)} {v}</span>' for k, v in n["platforms"].items())
        co = f"{n['coordinated_post_share']:.0%} " + e(",".join(n.get("coordinated_groups", {}))) if n.get("coordinated_post_share") else "–"
        h.append(f"<tr><td>{n['id'] if n['id'] >= 0 else '–'}</td><td><b>{e(n['label'])}</b></td><td>{n['posts']}</td><td>{n['accounts']}</td>"
                 f"<td>{pl}</td><td>{spark(n['volume_over_time'], buckets)}</td><td>{co}</td>"
                 f"<td class=muted>{short(ex['text'], 140) if ex else ''}</td></tr>")
    h.append("</table></section>")
    h.append("<section><h2>Narrative volume per platform</h2>")
    for n in nars[:6]:
        if n["id"] >= 0:
            h.append(f"<h3>#{n['id']} {e(n['label'])}</h3>{stacked_bars(n['volume_by_platform'], h=120)}")
    h.append("</section>")

    # coordination
    h.append("<section><h2>Groups of accounts acting together</h2>")
    if not result["coordinated_groups"]:
        h.append("<p class=muted>No coordinated groups met the evidence thresholds.</p>")
    for g in result["coordinated_groups"]:
        pl = ", ".join(f"{k}:{v}" for k, v in g["platforms"].items())
        h.append(f"<details open><summary>{e(g['id'])} · {g['size']} accounts · {g['posts']} posts · <span class='tag {g['confidence']}'>"
                 f"{e(g['confidence'])} ({g['score']})</span> · {e(pl)}</summary><div class=grid><div>"
                 f"<h3>Why these accounts are grouped</h3><ul>" + "".join(f"<li>{e(r)}</li>" for r in g["reasons"]) + "</ul>"
                 f"<p class=muted>Narratives pushed (id: posts): {e(', '.join(f'{k}: {v}' for k, v in list(g.get('narratives', {}).items())[:5]))} · active {e(g['first_post'][:16])} → {e(g['last_post'][:16])}</p>"
                 "<h3>Evidence</h3>")
        for ev in g["evidence"]:
            if ev["type"] == "near_duplicate":
                h.append(f"<div class=q>{short(ev['text'])}<br><span class=muted>posted near-verbatim by {ev['accounts']} accounts, {e(ev['first'][:16])} → {e(ev['last'][:16])}</span></div>")
            else:
                h.append(f"<div class=q><span class=muted>{ev['lag_seconds']:.0f}s apart:</span> {e(ev['a']['account'])}: {short(ev['a']['text'], 110)}<br>"
                         f"{e(ev['b']['account'])}: {short(ev['b']['text'], 110)}</div>")
        h.append(f"<details><summary>Members ({g['size']})</summary><p><code>{e('  '.join(g['accounts']))}</code></p></details></div>"
                 f"<div>{group_graph(g)}</div></div></details>")
    h.append("</section>")

    # origins
    h.append("<section><h2>Where each narrative started &amp; how it spread</h2>")
    for o in result["origins"]:
        fp = o["first_post"]
        h.append(f"<details><summary>#{o['narrative_id']} {e(o['label'])} — first seen {e(fp['at'][:16])} on {e(fp['platform'])}</summary>"
                 f"<p><b>{e(o['verdict'])}</b></p><h3>First accounts</h3><table><tr><th>When</th><th>Account</th><th>Platform</th><th>Group</th><th>Post</th></tr>")
        for a in o["first_accounts"]:
            link = f'<a href="{e(a["url"])}" rel="noreferrer noopener">{short(a["text"], 120)}</a>' if a["url"].startswith("http") else short(a["text"], 120)
            h.append(f"<tr><td>{e(a['at'][:16])} <span class=muted>+{a['minutes_after_origin']}m</span></td><td>{e(a['account'])}</td><td>{e(a['platform'])}</td><td>{e(a['coordinated_group'] or '–')}</td><td>{link}</td></tr>")
        h.append("</table><h3>Cross-platform spread (first appearance)</h3><p>" +
                 " → ".join(f"<b>{e(s['platform'])}</b> <span class=muted>(+{s['lag_minutes']:.0f} min, {e(s['first_account'])})</span>" for s in o["platform_spread"]) + "</p>")
        if o["copy_paste_lineage"]:
            h.append("<p class=muted>Most-copied text first appeared: " + "; ".join(
                f"{e(x['platform'])} +{x['lag_minutes']:.0f}m ({e(x['account'])})" for x in o["copy_paste_lineage"]) + "</p>")
        h.append("</details>")
    h.append("</section>")

    # posts
    h.append(f"<section><h2>Posts ({min(len(posts), max_posts)} of {len(posts)} shown — full set in posts.csv / results.json)</h2>"
             "<input id=f placeholder='filter posts…'><table id=posts><thead><tr><th>Date (UTC)</th><th>Platform</th><th>Account</th><th>Text</th><th>Media</th>"
             "<th>♥</th><th>↻</th><th>💬</th><th>Narr.</th><th>Group</th></tr></thead><tbody>")
    for p in sorted(posts, key=lambda p: -p["engagement"])[:max_posts]:
        media = " ".join(f'<a href="{e(mm["url"])}" rel="noreferrer noopener">{e(mm["type"])}</a>' for mm in p["media"] if mm["url"].startswith("http"))
        link = f'<a href="{e(p["url"])}" rel="noreferrer noopener">{e(p["created_at"][:16].replace("T", " "))}</a>' if p["url"].startswith("http") else e(p["created_at"][:16])
        h.append(f"<tr><td>{link}</td><td>{e(p['platform'])}</td><td>{e(p['author_name'])}</td><td>{short(p['text'], 260)}</td><td>{media}</td>"
                 f"<td>{p['likes']}</td><td>{p['shares']}</td><td>{p['replies']}</td><td>{p['narrative_id'] if p['narrative_id'] >= 0 else '–'}</td><td>{e(p['coordinated_group'] or '')}</td></tr>")
    h.append(f"</tbody></table></section></main><script>{JS}</script></body></html>")
    return "".join(h)
