"""Self-contained HTML dashboard: dark "bento" layout, inline SVG, vanilla JS, no CDN (works offline, safe to e-mail).
Every scraped string is HTML-escaped - posts are untrusted input."""
from __future__ import annotations

import math
import random
from html import escape as e
from typing import Dict, List, Tuple

PALETTE = {"telegram": "#3ee6b8", "x": "#8fa2ff", "youtube": "#ff7a59", "tiktok": "#c08bff", "instagram": "#ff6fa8",
           "facebook": "#5aa0ff", "snapchat": "#ffd84d"}
FALLBACK = ["#9aa4b2", "#6ec1ff", "#d6e04f", "#59e0e0"]
SIGNAL_LABEL = {"text_dup": "Copy-pasted text", "sync": "Posting in sync", "amplify": "Reshare loops",
                "avatar": "Reused avatars", "created": "Created together", "handle": "Same handle"}


def color(pl: str) -> str:
    return PALETTE.get(pl, FALLBACK[sum(map(ord, pl)) % len(FALLBACK)])


def lerp_color(a: str, b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    ca, cb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def short(t: str, n=220) -> str:
    t = " ".join((t or "").split())
    return e(t if len(t) <= n else t[:n - 1] + "…")


def fmt_lag(minutes: float) -> str:
    if minutes < 1:
        return "origin"
    if minutes < 90:
        return f"+{minutes:.0f}m"
    if minutes < 48 * 60:
        return f"+{minutes / 60:.0f}h"
    return f"+{minutes / 1440:.0f}d"


# ------------------------------------------------------------------ SVG helpers
def _smooth(pts: List[Tuple[float, float]]) -> str:
    """Catmull-Rom -> cubic Bezier segments (without the initial M)."""
    n = len(pts)
    out = []
    for i in range(n - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(out)


def streamgraph(series: Dict[str, Dict[str, int]], w=900, h=270) -> str:
    buckets = sorted({b for s in series.values() for b in s})
    if not buckets:
        return "<p class=muted>no data</p>"
    hourly = len(buckets) > 1 and any(b[11:13] != "00" for b in buckets)
    lab = (lambda b: b[5:10] + " " + b[11:13] + "h") if hourly else (lambda b: b[5:10])
    plats = sorted(series, key=lambda p: -sum(series[p].values()))
    padl, padr, padt, padb = 8, 8, 10, 26
    n = len(buckets)
    xs = [padl + (w - padl - padr) * (i / (n - 1) if n > 1 else 0.5) for i in range(n)]
    tot = [sum(series[p].get(b, 0) for p in plats) for b in buckets]
    mx = max(tot) or 1
    sc = (h - padt - padb) / mx
    mid = padt + (h - padt - padb) / 2
    cum = [[0] * n]
    for p in plats:
        cum.append([cum[-1][i] + series[p].get(buckets[i], 0) for i in range(n)])
    o = [f'<svg viewBox="0 0 {w} {h}" class=chart role=img aria-label="volume over time per platform"><defs>']
    for p in plats:
        c = color(p)
        o.append(f'<linearGradient id="g_{e(p)}" x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="{c}" stop-opacity=".95"/>'
                 f'<stop offset=1 stop-color="{c}" stop-opacity=".45"/></linearGradient>')
    o.append('<filter id="soft" x="-5%" y="-20%" width="110%" height="140%"><feGaussianBlur stdDeviation="6"/></filter></defs>')
    for g in range(1, 4):
        y = padt + (h - padt - padb) * g / 4
        o.append(f'<line x1={padl} x2={w - padr} y1={y:.1f} y2={y:.1f} class=grid-l />')
    layers = []
    for k, p in enumerate(plats):
        top = [(xs[i], mid + (-tot[i] / 2 + cum[k + 1][i]) * sc) for i in range(n)]
        bot = [(xs[i], mid + (-tot[i] / 2 + cum[k][i]) * sc) for i in range(n)]
        if n == 1:
            top = [(xs[0] - 40, top[0][1]), (xs[0] + 40, top[0][1])]
            bot = [(xs[0] - 40, bot[0][1]), (xs[0] + 40, bot[0][1])]
        d = f"M{top[0][0]:.1f} {top[0][1]:.1f} {_smooth(top)} L{bot[-1][0]:.1f} {bot[-1][1]:.1f} {_smooth(bot[::-1])} Z"
        layers.append((p, d))
    for p, d in layers:      # blurred glow underlay
        o.append(f'<path d="{d}" fill="{color(p)}" opacity=".35" filter="url(#soft)"/>')
    for p, d in layers:
        o.append(f'<path d="{d}" fill="url(#g_{e(p)})" stroke="{color(p)}" stroke-width="1" class=layer data-p="{e(p)}"><title>{e(p)}</title></path>')
    step = max(1, math.ceil(n / 9))
    for i, b in enumerate(buckets):
        bw = (w - padl - padr) / max(n, 1)
        o.append(f'<rect x={xs[i] - bw / 2:.1f} y=0 width={bw:.1f} height={h - padb} fill="transparent" class=hit>'
                 f'<title>{e(lab(b))}: ' + ", ".join(f"{e(p)} {series[p].get(b, 0)}" for p in plats) + f' (total {tot[i]})</title></rect>')
        if i % step == 0:
            anc = 'start' if i == 0 else 'middle'
            o.append(f'<text x={xs[i]:.1f} y={h - 8} class=ax text-anchor={anc}>{e(lab(b))}</text>')
    o.append("</svg><div class=legend>" + "".join(f'<span><i style="background:{color(p)}"></i>{e(p)} · {sum(series[p].values())}</span>' for p in plats) + "</div>")
    return "".join(o)


def donut(parts: Dict[str, int], size=150) -> str:
    tot = sum(parts.values()) or 1
    r, c, sw = size * 0.34, size / 2, size * 0.17
    circ = 2 * math.pi * r
    o = [f'<svg viewBox="0 0 {size} {size}" class=donut role=img aria-label="platform mix">']
    off = 0.0
    for p, v in sorted(parts.items(), key=lambda kv: -kv[1]):
        ln = circ * v / tot
        o.append(f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{color(p)}" stroke-width="{sw}" stroke-dasharray="{max(ln - 2, 0):.1f} {circ:.1f}" '
                 f'stroke-dashoffset="{-off:.1f}" transform="rotate(-90 {c} {c})"><title>{e(p)}: {v}</title></circle>')
        off += ln
    o.append(f'<text x="{c}" y="{c + size * 0.08:.1f}" text-anchor="middle" class="donut-n" style="font-size:{size * 0.26:.0f}px">{len(parts)}</text></svg>')
    return "".join(o)


def ring(frac: float, size=120, col="#ff4d6d") -> str:
    r, c, sw = 46, size / 2, 11
    circ = 2 * math.pi * r
    return (f'<svg viewBox="0 0 {size} {size}" class=ring><circle cx={c} cy={c} r={r} fill="none" stroke="#262636" stroke-width="{sw}" />'
            f'<circle cx={c} cy={c} r={r} fill=none stroke="{col}" stroke-width={sw} stroke-linecap=round stroke-dasharray="{circ * frac:.1f} {circ:.1f}" '
            f'transform="rotate(-90 {c} {c})" class=ring-arc style="--len:{circ * frac:.1f}"/>'
            f'<text x={c} y={c + 8} text-anchor=middle class=ring-n>{frac:.0%}</text></svg>')


def bubble_map(nars: List[dict], w=640, h=470) -> str:
    items = [n for n in nars if n["id"] >= 0]
    if not items:
        return "<p class=muted>no narratives found</p>"
    mx = max(n["posts"] for n in items)
    placed: List[Tuple[float, float, float, dict]] = []
    cx, cy = w / 2, h / 2
    for n in sorted(items, key=lambda n: -n["posts"]):
        r = 20 + 62 * math.sqrt(n["posts"] / mx)
        for step in range(0, 4000):
            ang, rad = step * 0.35, 3.2 * math.sqrt(step) * 2
            x, y = cx + rad * math.cos(ang) * 1.35, cy + rad * math.sin(ang)
            if r + 4 > x or x > w - r - 4 or r + 4 > y or y > h - r - 4:
                continue
            if all(math.hypot(x - px, y - py) >= r + pr + 5 for px, py, pr, _ in placed):
                placed.append((x, y, r, n))
                break
    o = [f'<svg viewBox="0 0 {w} {h}" class=bubbles role=img aria-label="narrative bubble map"><defs><filter id=bglow x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter></defs>']
    for x, y, r, n in placed:
        col = lerp_color("#3ee6b8", "#ff4d6d", n.get("coordinated_post_share", 0) * 1.4)
        kw = [k for k in n["keywords"][:2]]
        title = (f'#{n["id"]} {n["label"]} — {n["posts"]} posts, {n["accounts"]} accounts, '
                 f'{n.get("coordinated_post_share", 0):.0%} from coordinated accounts. Click to filter posts.')
        o.append(f'<g class=bub data-n="{n["id"]}" tabindex=0 role=button aria-label="{e(title)}"><title>{e(title)}</title>'
                 f'<circle cx={x:.1f} cy={y:.1f} r={r:.1f} fill="{col}" opacity=".28" filter="url(#bglow)"/>'
                 f'<circle cx={x:.1f} cy={y:.1f} r={r:.1f} fill="{col}" fill-opacity=".16" stroke="{col}" stroke-width="1.5"/>'
                 f'<text x={x:.1f} y={y - (4 if r > 38 else -4):.1f} text-anchor=middle class=bub-id style="font-size:{min(26, 11 + r / 5):.0f}px">#{n["id"]}</text>')
        if r > 38 and kw:
            o.append(f'<text x={x:.1f} y={y + 14:.1f} text-anchor=middle class=bub-kw>{e(" · ".join(kw))[:int(r / 3.2)]}</text>')
        o.append("</g>")
    o.append("</svg><div class=legend><span><i style='background:#3ee6b8'></i>organic</span><span><i style='background:#ff4d6d'></i>mostly coordinated accounts</span>"
             "<span class=muted>bubble size = posts</span></div>")
    return "".join(o)


def fr_layout(nodes: List[str], edges: List[Tuple[str, str]], w: float, h: float, seed=3, iters=110) -> Dict[str, Tuple[float, float]]:
    rng = random.Random(seed)
    pos = {n: [rng.uniform(w * .2, w * .8), rng.uniform(h * .2, h * .8)] for n in nodes}
    k = math.sqrt(w * h / max(len(nodes), 1)) * 1.15
    for it in range(iters):
        t = (w / 7) * (1 - it / iters) + 0.5
        disp = {n: [0.0, 0.0] for n in nodes}
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
                d = max(math.hypot(dx, dy), 0.01)
                f = k * k / d
                disp[a][0] += dx / d * f; disp[a][1] += dy / d * f
                disp[b][0] -= dx / d * f; disp[b][1] -= dy / d * f
        for a, b in edges:
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d = max(math.hypot(dx, dy), 0.01)
            f = d * d / k * 0.12
            disp[a][0] -= dx / d * f; disp[a][1] -= dy / d * f
            disp[b][0] += dx / d * f; disp[b][1] += dy / d * f
        for n in nodes:
            disp[n][0] += (w / 2 - pos[n][0]) * 0.02; disp[n][1] += (h / 2 - pos[n][1]) * 0.02
            d = max(math.hypot(*disp[n]), 0.01)
            pos[n][0] = min(w - 14, max(14, pos[n][0] + disp[n][0] / d * min(d, t)))
            pos[n][1] = min(h - 14, max(14, pos[n][1] + disp[n][1] / d * min(d, t)))
    return {n: (p[0], p[1]) for n, p in pos.items()}


def group_graph(g: dict, w=440, h=330) -> str:
    accts = g["accounts"][:45]
    keep = set(accts)
    edges = [(ed["a"], ed["b"], ed["signals"]) for ed in g["edges"] if ed["a"] in keep and ed["b"] in keep]
    pos = fr_layout(accts, [(a, b) for a, b, _ in edges], w, h, seed=len(accts))
    o = [f'<svg viewBox="0 0 {w} {h}" class=graph role=img aria-label="account link graph of {e(g["id"])}"><defs><filter id="nglow-{e(g["id"])}" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3.5"/></filter></defs>']
    for a, b, sg in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        o.append(f'<line x1={x1:.1f} y1={y1:.1f} x2={x2:.1f} y2={y2:.1f} stroke="#ff4d6d" stroke-opacity="{min(.14 + .1 * len(sg), .5):.2f}" stroke-width="{.6 + .35 * len(sg):.2f}"/>')
    for a, (x, y) in pos.items():
        c = color(a.split(":")[0])
        o.append(f'<g class=node><circle cx={x:.1f} cy={y:.1f} r=7 fill="{c}" filter="url(#nglow-{e(g["id"])})" opacity=".8"/>'
                 f'<circle cx={x:.1f} cy={y:.1f} r=4.2 fill="{c}"><title>{e(a)}</title></circle></g>')
    o.append("</svg>")
    if len(g["accounts"]) > 45:
        o.append(f'<p class=muted style="margin:4px 0 0">showing 45 of {g["size"]} accounts</p>')
    return "".join(o)


def signal_bars(g: dict) -> str:
    rows = []
    for s, v in g["signal_coverage"].items():
        try:
            num, den = v.split()[0].split("/")
            frac = int(num) / max(int(den), 1)
        except Exception:
            frac = 0
        rows.append(f'<div class=sig><span>{e(SIGNAL_LABEL.get(s, s))}</span><div class=bar><b style="width:{frac * 100:.0f}%"></b></div><em>{frac:.0%}</em></div>')
    return "".join(rows)


def spread_map(o: dict, w=860) -> str:
    sp = o["platform_spread"]
    plats = [s["platform"] for s in sp]
    lanes = len(plats)
    lane_h, padl, padr, padt, padb = 46, 90, 30, 14, 28
    h = padt + padb + lane_h * lanes
    maxlag = max([s["lag_minutes"] for s in sp] + [60.0])
    horizon = max(maxlag * 1.15, 120.0)

    def X(m: float) -> float:       # sqrt scale so early seconds-to-minutes hops stay readable
        return padl + (w - padl - padr) * math.sqrt(max(m, 0) / horizon)
    casc = o.get("cascade_first_48h", {})
    cmax = max([v for c in casc.values() for v in c.values()] + [1])
    out = [f'<svg viewBox="0 0 {w} {h}" class=spread role=img aria-label="cross-platform spread timeline">']
    for tick in [0, 15, 60, 360, 1440, 2880]:
        if tick <= horizon:
            out.append(f'<line x1={X(tick):.1f} x2={X(tick):.1f} y1={padt} y2={h - padb} class=grid-l />'
                       f'<text x={X(tick):.1f} y={h - 8} class=ax text-anchor=middle>{"0" if tick == 0 else fmt_lag(tick)[1:]}</text>')
    for i, p in enumerate(plats):
        y = padt + lane_h * i + lane_h / 2
        out.append(f'<text x=0 y={y + 4:.1f} class=lane style="fill:{color(p)}">{e(p)}</text><line x1={padl} x2={w - padr} y1={y:.1f} y2={y:.1f} class=lane-l />')
        for hr, counts in casc.items():
            v = counts.get(p, 0)
            if v:
                hh = 4 + 20 * v / cmax
                out.append(f'<rect x={X(int(hr) * 60):.1f} y={y - hh / 2:.1f} width=5 height={hh:.1f} rx=2 fill="{color(p)}" opacity=".38"><title>{e(p)} hour {hr}: {v} posts</title></rect>')
    pts = []
    for i, s in enumerate(sp):
        pts.append((X(s["lag_minutes"]), padt + lane_h * i + lane_h / 2, s))
    for (x1, y1, _), (x2, y2, s2) in zip(pts, pts[1:]):
        out.append(f'<path d="M{x1:.1f} {y1:.1f} C{(x1 + x2) / 2:.1f} {y1:.1f} {(x1 + x2) / 2:.1f} {y2:.1f} {x2:.1f} {y2:.1f}" class=hop />'
                   f'<text x={(x1 + x2) / 2:.1f} y={(y1 + y2) / 2 - 6:.1f} class=hop-l text-anchor=middle>{e(fmt_lag(s2["lag_minutes"]))}</text>')
    for x, y, s in pts:
        c = color(s["platform"])
        out.append(f'<circle cx={x:.1f} cy={y:.1f} r=11 fill="{c}" opacity=".3" class=pulse /><circle cx={x:.1f} cy={y:.1f} r=5.5 fill="{c}" stroke="#0b0b11" stroke-width=2>'
                   f'<title>first on {e(s["platform"])}: {e(s["first_account"])} at {e(s["at"][:16])}</title></circle>')
    out.append("</svg>")
    return "".join(out)


CSS = """
:root{--bg:#09090e;--card:#12121b;--card2:#171723;--line:#24243a;--tx:#ececf6;--mut:#8b8ba3;--hot:#ff4d6d;--ok:#3ee6b8;--warn:#ffc04d}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:radial-gradient(1200px 600px at 12% -10%,#2a1b4d55,transparent 60%),radial-gradient(900px 500px at 95% 0%,#0f3a4a55,transparent 60%),var(--bg);color:var(--tx);
font:14px/1.5 Inter,system-ui,Segoe UI,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1240px;margin:0 auto;padding:28px 22px 80px}
.hero{padding:34px 4px 18px}.eyebrow{letter-spacing:.18em;text-transform:uppercase;font-size:11px;color:var(--mut)}
h1{margin:6px 0 10px;font-size:clamp(34px,6vw,64px);line-height:1.02;letter-spacing:-.03em;font-weight:800}
h1 span{background:linear-gradient(100deg,#8fa2ff 0%,#3ee6b8 45%,#ff7a59 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{border:1px solid var(--line);background:#ffffff08;border-radius:99px;padding:4px 12px;font-size:12px;color:#c9c9dc}
.bento{display:grid;grid-template-columns:repeat(12,1fr);gap:16px;margin-top:18px}
.tile{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:22px;padding:20px 22px;position:relative;overflow:hidden;min-width:0}
.tile:before{content:"";position:absolute;inset:0;background:radial-gradient(400px 120px at 20% 0,#ffffff0a,transparent 70%);pointer-events:none}
.s3{grid-column:span 3}.s4{grid-column:span 4}.s5{grid-column:span 5}.s6{grid-column:span 6}.s7{grid-column:span 7}.s8{grid-column:span 8}.s12{grid-column:span 12}
h2{margin:0 0 4px;font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);font-weight:600}
.sub{color:var(--mut);margin:0 0 12px;font-size:13px}
.big{font-size:clamp(38px,5vw,58px);font-weight:800;letter-spacing:-.03em;line-height:1}.big small{font-size:14px;color:var(--mut);font-weight:500;letter-spacing:0;margin-left:6px}
.stat .lbl{color:var(--mut);margin-top:8px}.hot{color:var(--hot)}.ok{color:var(--ok)}
.chart,.spread,.bubbles,.graph{width:100%;height:auto;display:block}.ring{width:112px;flex:none}.donut{width:44px;flex:none}.share{display:flex;gap:12px;align-items:center}.sh-t{min-width:0}.sh-t h2{letter-spacing:.06em}.sh-d{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12px}.gcard>div:last-child{align-self:center}.ax{font-size:10px;fill:#7b7b94}.grid-l{stroke:#ffffff10}
.layer{transition:opacity .2s}.chart:hover .layer{opacity:.55}.chart .layer:hover{opacity:1}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:#c0c0d6;margin-top:6px}.legend i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:6px}
.muted{color:var(--mut)}.donut-n,.ring-n{fill:#fff;font-weight:800}.donut-n{font-size:26px}.ring-n{font-size:22px}
.ring-arc{animation:draw 1.4s ease-out both}@keyframes draw{from{stroke-dasharray:0 999}to{stroke-dasharray:var(--len) 999}}
.bub{cursor:pointer;outline:none}.bub circle:nth-child(2){transition:fill-opacity .2s}.bub:hover circle:nth-child(2),.bub:focus circle:nth-child(2),.bub.sel circle:nth-child(2){fill-opacity:.4}
.bub-id{fill:#fff;font-weight:800;pointer-events:none}.bub-kw{fill:#d6d6ea;font-size:10px;pointer-events:none}
.nl{display:flex;flex-direction:column;gap:2px;max-height:470px;overflow:auto;padding-right:4px}.nrow{display:grid;grid-template-columns:34px 1fr 96px;gap:10px;align-items:center;padding:8px 8px;border-radius:12px;cursor:pointer}
.nrow:hover,.nrow.sel{background:#ffffff0c}.nrow .i{color:var(--mut);font-weight:700}.nrow b{display:block;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mix{display:flex;height:5px;border-radius:9px;overflow:hidden;margin-top:5px;background:#ffffff10}.mix i{display:block;height:100%}
.badge{font-size:11px;padding:2px 9px;border-radius:99px;border:1px solid var(--line);white-space:nowrap}.b-hot{color:var(--hot);border-color:#ff4d6d66;background:#ff4d6d14}.b-ok{color:var(--ok);border-color:#3ee6b855;background:#3ee6b812}.b-warn{color:var(--warn);border-color:#ffc04d55;background:#ffc04d12}
.gcard{display:grid;grid-template-columns:1.1fr 1fr;gap:20px}.gcard ul{margin:8px 0 12px;padding:0;list-style:none}.gcard li{padding:6px 0 6px 20px;position:relative;color:#d8d8ea}
.gcard li:before{content:"";position:absolute;left:2px;top:13px;width:8px;height:8px;border-radius:50%;background:var(--hot);box-shadow:0 0 10px var(--hot)}
.gh{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}.gh .gid{font-size:30px;font-weight:800;letter-spacing:-.02em}
.sig{display:grid;grid-template-columns:130px 1fr 40px;gap:10px;align-items:center;font-size:12px;color:#c0c0d6;margin:4px 0}.bar{height:6px;background:#ffffff12;border-radius:9px;overflow:hidden}.bar b{display:block;height:100%;background:linear-gradient(90deg,#8fa2ff,#ff4d6d);border-radius:9px}.sig em{font-style:normal;color:var(--mut);text-align:right}
.q{background:#ffffff08;border-left:2px solid var(--hot);border-radius:0 10px 10px 0;padding:7px 12px;margin:6px 0;font-size:13px;color:#dcdcee;word-break:break-word}.q small{display:block;color:var(--mut);margin-top:2px}
.origin{border-top:1px solid var(--line);padding:16px 0 4px;margin-top:10px}.origin:first-of-type{border-top:0;margin-top:0;padding-top:4px}
.oh{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px}.oh b{font-size:16px}
.lane{font-size:12px;font-weight:700}.lane-l{stroke:#ffffff12;stroke-dasharray:2 5}.hop{fill:none;stroke:#ffffff55;stroke-width:1.6;stroke-dasharray:5 4;animation:flow 1.6s linear infinite}@keyframes flow{to{stroke-dashoffset:-18}}
.hop-l{font-size:11px;fill:#fff;font-weight:700}.pulse{animation:pulse 2.2s ease-out infinite;transform-box:fill-box;transform-origin:center}@keyframes pulse{0%{transform:scale(.7);opacity:.6}100%{transform:scale(1.9);opacity:0}}
.fa{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}.fa a,.fa span{font-size:12px;padding:3px 10px;border-radius:99px;background:#ffffff0a;border:1px solid var(--line);color:#cfcfe4;text-decoration:none}
.tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0 10px}
input#f{background:#0d0d14;border:1px solid var(--line);color:var(--tx);padding:8px 14px;border-radius:12px;width:320px;max-width:100%}
.tbl{max-height:640px;overflow:auto;border:1px solid var(--line);border-radius:14px}table{border-collapse:collapse;width:100%}th{position:sticky;top:0;background:#14141f;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;text-align:left;padding:9px 10px;z-index:1}
td{padding:9px 10px;border-top:1px solid #1d1d2e;vertical-align:top}tr:hover td{background:#ffffff06}a{color:#9db0ff;text-decoration:none}a:hover{text-decoration:underline}
.pl{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;font-weight:700;border:1px solid}
.warn{background:#ffc04d12;border:1px solid #ffc04d44;color:#ffd890;border-radius:14px;padding:9px 14px;margin-top:14px;font-size:13px}
details summary{cursor:pointer;color:#c0c0d6}code{color:#b8c3ff;font-size:12px;word-break:break-all}
footer{color:var(--mut);margin-top:26px;font-size:12px;text-align:center}
@media(max-width:960px){.s3,.s4,.s5,.s6,.s7,.s8{grid-column:span 12}.gcard{grid-template-columns:1fr}.s3{grid-column:span 6}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
"""

JS = """
(function(){
function cnt(el){var t=+el.dataset.count,s=performance.now();function f(n){var p=Math.min(1,(n-s)/900);el.textContent=Math.round(t*(1-Math.pow(1-p,3))).toLocaleString();if(p<1)requestAnimationFrame(f)}requestAnimationFrame(f)}
if(!matchMedia('(prefers-reduced-motion: reduce)').matches)document.querySelectorAll('[data-count]').forEach(cnt);
var f=document.getElementById('f'),rows=document.querySelectorAll('#posts tbody tr'),cur=null,cnt_el=document.getElementById('shown');
function apply(){var q=f.value.toLowerCase(),n=0;rows.forEach(function(r){var ok=(!cur||r.dataset.n===cur)&&r.textContent.toLowerCase().indexOf(q)>=0;r.style.display=ok?'':'none';if(ok)n++});cnt_el.textContent=n;
document.querySelectorAll('[data-n].bub,[data-n].nrow').forEach(function(b){b.classList.toggle('sel',b.dataset.n===cur)});document.getElementById('clr').style.display=cur?'':'none';document.getElementById('cur').textContent=cur?'narrative #'+cur:'';var pm=document.getElementById('pickmsg');if(pm)pm.innerHTML=cur?'<b>Narrative #'+cur+' selected.</b> '+n+' of its posts are listed in the Posts table. <a href="#posts-tile" style="color:inherit;text-decoration:underline">Jump to the posts ↓</a> · <a href="#" id=pclr style="color:inherit;text-decoration:underline">Clear</a>':'';var pc=document.getElementById('pclr');if(pc)pc.onclick=function(ev){ev.preventDefault();cur=null;apply()}}
window.pick=function(n){cur=(cur===n)?null:n;apply();};
document.querySelectorAll('[data-n].bub,[data-n].nrow').forEach(function(b){b.addEventListener('click',function(){pick(b.dataset.n)});b.addEventListener('keydown',function(ev){if(ev.key==='Enter')pick(b.dataset.n)})});
apply();f.addEventListener('input',apply);document.getElementById('clr').addEventListener('click',function(){cur=null;apply()});
})();
"""



def overview_blocks(result: dict) -> dict:
    """HTML tiles for the plain-language overview, daily counts, per-term mentions and narratives-by-day."""
    ov = result.get("overview")
    if not ov:
        return {"top": "", "groups": "", "origins": ""}
    pl = ov["plain"]
    plats, terms, days = ov["platforms"], ov["terms"], ov["days"]
    top = ["<div class='tile s12'><h2>In plain words</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in pl["summary"]) + "</ul></div>"]
    peak = max((d["total"] for d in days), default=1) or 1
    rows = "".join(f"<tr><td>{e(d['date'])}</td><td><div style='background:var(--cyan,#5ac8fa);height:8px;border-radius:4px;width:{d['total'] / peak * 100:.0f}%;min-width:{1 if d['total'] else 0}px'></div></td>"
                   f"<td><b>{d['total']:,}</b></td>" + "".join(f"<td>{d['by_platform'].get(k, 0):,}</td>" for k in plats) +
                   "".join(f"<td>{d['by_term'].get(t['term'], 0):,}</td>" for t in terms) + "</tr>" for d in days)
    top.append("<div class='tile s12'><h2>Posts per day</h2><p class=sub>How many posts were made on each day of the time frame, per platform, and how many mentioned each search term.</p><div class=tbl><table><thead><tr><th>Date</th><th></th><th>Posts</th>" +
               "".join(f"<th>{e(k)}</th>" for k in plats) + "".join(f"<th>“{e(t['term'])}”</th>" for t in terms) + f"</tr></thead><tbody>{rows}</tbody></table></div></div>")
    trows = "".join(f"<tr><td><b>{e(t['term'])}</b></td><td>{e(t['kind'])}</td><td><b>{t['posts']:,}</b></td><td>{t['share']:.0%}</td><td>{t['accounts']:,}</td>" +
                    "".join(f"<td>{t['by_platform'].get(k, 0):,}</td>" for k in plats) + "</tr>" for t in terms)
    top.append("<div class='tile s12'><h2>Mentions per keyword, hashtag, person, brand or event</h2><div class=tbl><table><thead><tr><th>Search term</th><th>Type</th><th>Posts</th><th>Share</th><th>Accounts</th>" +
               "".join(f"<th>{e(k)}</th>" for k in plats) + f"</tr></thead><tbody>{trows}</tbody></table></div></div>")
    nmax = max((v for n in ov["narratives"] for v in n["by_day"].values()), default=1) or 1
    nrows = "".join(f"<tr><td style='white-space:nowrap'>#{n['id']} {e(n['label'])}</td><td><b>{n['posts']:,}</b></td>" +
                    "".join(f"<td style='text-align:center;background:rgba(90,200,250,{0.08 + 0.7 * n['by_day'].get(d['date'], 0) / nmax if n['by_day'].get(d['date'], 0) else 0:.2f})'>{n['by_day'].get(d['date'], 0) or ''}</td>" for d in days) +
                    "".join(f"<td>{n['by_term'].get(t['term'], 0):,}</td>" for t in terms) + "</tr>" for n in ov["narratives"])
    top.append("<div class='tile s12'><h2>What is being said, day by day and term by term</h2><ul>" + "".join(f"<li><b>#{n['id']}</b> {e(n['text'])}</li>" for n in pl["narratives"]) +
               "</ul><p class=sub>Posts per narrative on each date, then per search term.</p><div class=tbl><table><thead><tr><th>Narrative</th><th>Posts</th>" +
               "".join(f"<th>{e(d['date'][5:])}</th>" for d in days) + "".join(f"<th>“{e(t['term'])}”</th>" for t in terms) + f"</tr></thead><tbody>{nrows}</tbody></table></div></div>")
    groups = ("<div class='tile s12'><h2>Groups in simple words</h2><ul>" + ("".join(f"<li>{e(g['text'])}</li>" for g in pl["groups"]) or "<li>No group of accounts met the evidence thresholds.</li>") + "</ul></div>")
    origins = ("<div class='tile s12'><h2>Where each story started, in simple words</h2><ul>" + "".join(f"<li><b>#{o['narrative_id']} {e(o['label'])}</b><br>{e(o['text'])}</li>" for o in pl["origins"][:12]) + "</ul></div>")
    return {"top": "".join(top), "groups": groups, "origins": origins}


def render(result: dict, max_posts: int = 400) -> str:
    m = result["meta"]
    nars, posts, groups, origins = result["narratives"], result["posts"], result["coordinated_groups"], result["origins"]
    plat_counts: Dict[str, int] = {}
    for p in posts:
        plat_counts[p["platform"]] = plat_counts.get(p["platform"], 0) + 1
    ncoord = m["coordinated_accounts"]
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>coordwatch · {e(m['topic'])}</title><style>{CSS}</style></head><body><main>"]
    h.append(f"<section class=hero><div class=eyebrow>coordwatch · coordinated-activity &amp; narrative report</div>"
             f"<h1><span>{e(m['topic'])}</span></h1><div class=chips><span class=chip>{e((m['since'] or '')[:10])} → {e((m['until'] or '')[:10])}</span>"
             + "".join(f"<span class=chip style='border-color:{color(p)}66;color:{color(p)}'>{e(p)}</span>" for p in m["platforms"])
             + f"<span class=chip>generated {e(m['generated_at'][:16].replace('T', ' '))} UTC</span></div>")
    h.append("</section><div class=bento>")

    ovb = overview_blocks(result)
    # --- stat tiles
    h.append(f"<div class='tile s3 stat'><h2>Posts</h2><div class=big data-count={m['n_posts']}>{m['n_posts']}</div><div class=lbl>from {m['n_accounts']:,} accounts</div></div>")
    h.append(f"<div class='tile s3 stat'><h2>Narratives</h2><div class=big data-count={m['n_narratives']}>{m['n_narratives']}</div><div class=lbl>distinct storylines found</div></div>")
    h.append(f"<div class='tile s3 stat'><h2>Coordinated</h2><div class='big {'hot' if ncoord else 'ok'}'><span data-count={ncoord}>{ncoord}</span><small>accounts in {m['n_groups']} group(s)</small></div>"
             f"<div class=lbl>{'leads for analyst review' if ncoord else 'no group met the evidence thresholds'}</div></div>")
    h.append(f"<div class='tile s3 stat share'>{ring(m['coordinated_post_share'], col='#ff4d6d' if ncoord else '#3ee6b8')}"
             f"<div class=sh-t><h2>Coordinated posts</h2><div class=lbl style='margin:0'>share of all posts</div>"
             f"<div class=sh-d>{donut(plat_counts, 44)}<span class=muted>{len(plat_counts)} platform(s)</span></div></div></div>")

    # --- streamgraph
    h.append(ovb["top"])
    h.append(f"<div class='tile s12'><h2>Volume over time</h2><p class=sub>Posts per {e(m['bucket'])}, stacked by platform — hover a column for exact counts.</p>"
             f"{streamgraph(result['volume']['by_platform'])}</div>")

    # --- narratives: bubbles + ranked list
    h.append(f"<div class='tile s7'><h2>Narrative map</h2><p class=sub>Each bubble is a storyline. Click one to filter the posts below.</p>{bubble_map(nars)}<p id=pickmsg class=sub role=status></p></div>")
    h.append("<div class='tile s5'><h2>Main narratives</h2><p class=sub>Ranked by volume</p><div class=nl>")
    for n in nars:
        if n["id"] < 0:
            continue
        share = n.get("coordinated_post_share", 0)
        badge = (f"<span class='badge b-hot'>{share:.0%} coord.</span>" if share >= 0.5 else
                 f"<span class='badge b-warn'>{share:.0%} coord.</span>" if share > 0 else "<span class='badge b-ok'>organic</span>")
        mix = "".join(f"<i style='width:{v / n['posts'] * 100:.1f}%;background:{color(k)}' title='{e(k)} {v}'></i>" for k, v in n["platforms"].items())
        h.append(f"<div class=nrow data-n='{n['id']}' title='Click to filter posts'><span class=i>#{n['id']}</span><div><b>{e(n['label'])}</b>"
                 f"<span class=muted style='font-size:12px'>{n['posts']} posts · {n['accounts']} accounts</span><div class=mix>{mix}</div></div>{badge}</div>")
    h.append("</div></div>")

    # --- coordinated groups
    h.append(ovb["groups"])
    h.append("<div class='tile s12'><h2>Accounts acting together</h2>")
    if not groups:
        h.append("<p class=sub>No group of accounts met the evidence thresholds for this topic and window.</p>")
    else:
        h.append("<p class=sub>Each group lists <b>why</b> it was flagged. These are investigative leads, not attribution — see Limitations in the README.</p>")
    h.append("</div>")
    for g in groups:
        conf = {"high": "b-hot", "medium": "b-warn"}.get(g["confidence"], "b-ok")
        pl = " ".join(f"<span class=badge style='color:{color(k)};border-color:{color(k)}55'>{e(k)} {v}</span>" for k, v in g["platforms"].items())
        h.append(f"<div class='tile s12'><div class=gcard><div><div class=gh><span class=gid>{e(g['id'])}</span><span class='badge {conf}'>{e(g['confidence'])} confidence · {g['score']}</span>{pl}</div>"
                 f"<p class=sub style='margin:0'>{g['size']} accounts · {g['posts']} posts · active {e(g['first_post'][:16].replace('T', ' '))} → {e(g['last_post'][:16].replace('T', ' '))}</p>"
                 "<h2 style='margin-top:14px'>Why they're grouped</h2><ul>" + "".join(f"<li>{e(r)}</li>" for r in g["reasons"]) + "</ul>"
                 f"<h2>Signal strength</h2>{signal_bars(g)}<h2 style='margin-top:14px'>Evidence</h2>")
        for ev in g["evidence"]:
            if ev["type"] == "near_duplicate":
                h.append(f"<div class=q>{short(ev['text'], 200)}<small>near-verbatim from {ev['accounts']} accounts · {e(ev['first'][:16].replace('T', ' '))} → {e(ev['last'][:16].replace('T', ' '))}</small></div>")
            else:
                h.append(f"<div class=q><small style='margin:0 0 3px'>{ev['lag_seconds']:.0f}s apart</small>{e(ev['a']['account'])}: {short(ev['a']['text'], 100)}<br>{e(ev['b']['account'])}: {short(ev['b']['text'], 100)}</div>")
        h.append(f"<details><summary>Members ({g['size']})</summary><p><code>{e('  '.join(g['accounts']))}</code></p></details></div>"
                 f"<div>{group_graph(g)}<div class=legend>" + "".join(f"<span><i style='background:{color(k)}'></i>{e(k)}</span>" for k in g["platforms"]) +
                 "<span class=muted>lines = evidence links</span></div></div></div></div>")

    # --- cross-platform correlation
    cp = result.get("cross_platform")
    if cp and cp.get("summary"):
        h.append("<div class='tile s12'><h2>Cross-platform summary</h2><p class=sub>How the platforms relate: shared narratives, volume correlation, links and copied text.</p><ul>")
        h.extend(f"<li>{e(x)}</li>" for x in cp["summary"])
        h.append("</ul>")
        if cp["narrative_overlap"]:
            h.append("<div class=tbl><table><thead><tr><th>Narrative</th><th>Posts by platform</th><th>First on</th><th>Then</th><th>Lag (h)</th></tr></thead><tbody>")
            for o in cp["narrative_overlap"][:8]:
                h.append(f"<tr><td>#{o['narrative_id']} {e(o['label'])}</td><td>{e(', '.join(f'{k} {v}' for k, v in o['by_platform'].items()))}</td>"
                         f"<td>{e(o['first_platform'])}</td><td>{e(', '.join(o['then']))}</td><td>{o['lag_hours_to_next']}</td></tr>")
            h.append("</tbody></table></div>")
        if cp["youtube_links_in_telegram"]:
            h.append("<p class=sub style='margin-top:10px'>Telegram posts linking to collected YouTube videos</p><ul>")
            for l in cp["youtube_links_in_telegram"][:8]:
                h.append(f"<li><a href='{e(l['telegram_post'])}' rel='noreferrer noopener'>{e(l['telegram_account'])}</a> → <a href='{e(l['video_url'])}' rel='noreferrer noopener'>video</a> ({l['telegram_after_video_hours']} h after upload)</li>")
            h.append("</ul>")
        h.append("</div>")

    # --- origins / spread
    h.append(ovb["origins"])
    h.append("<div class='tile s12'><h2>Where each narrative started &amp; how it spread</h2><p class=sub>Glowing dots are the first appearance per platform; dashed arcs show the hop and its delay. Small bars show hourly volume after origin.</p>")
    top_orig = sorted(origins, key=lambda o: (o["seeding_group"] is None, -o["early_wave_coordinated_share"]))[:6]
    for o in top_orig:
        fp = o["first_post"]
        vb = ("b-hot" if o["seeding_group"] else "b-warn" if o["early_wave_coordinated_share"] > 0 else "b-ok")
        h.append(f"<div class=origin><div class=oh><b>#{o['narrative_id']} {e(o['label'])}</b><span class='badge {vb}'>{e(o['verdict'])}</span></div>"
                 f"<div class=muted style='font-size:12px'>first seen {e(fp['at'][:16].replace('T', ' '))} UTC on {e(fp['platform'])} by {e(fp['account'])}</div>{spread_map(o)}<div class=fa>")
        for a in o["first_accounts"]:
            lab = f"{a['account']} · {fmt_lag(a['minutes_after_origin'])}" + (f" · {a['coordinated_group']}" if a["coordinated_group"] else "")
            h.append(f"<a href='{e(a['url'])}' rel='noreferrer noopener' title='{short(a['text'], 140)}'>{e(lab)}</a>" if a["url"].startswith("http") else f"<span>{e(lab)}</span>")
        h.append("</div></div>")
    h.append("</div>")

    # --- web discovery (optional stage)
    disc = result.get("discovery")
    if disc:
        ok = sum(1 for q in disc["queries"] if q.get("ok"))
        h.append(f"<div class='tile s12'><h2>Web discovery</h2><p class=sub>Free search-engine sweep ({ok}/{len(disc['queries'])} queries answered). "
                 "Web mentions are leads only: no account or engagement data, never used as coordination evidence.</p>")
        first = disc.get("earliest_dated_mention")
        if first:
            h.append(f"<div class=muted style='font-size:12px'>Earliest dated web mention: {e(first['date'][:10])} · {e(first['platform'])} · "
                     f"<a href='{e(first['url'])}' rel='noreferrer noopener'>{short(first['title'] or first['url'], 90)}</a></div>")
        if disc["telegram_channels"]:
            h.append("<div class=muted style='font-size:12px'>Telegram channels found: " + ", ".join(f"{e(c['channel'])} ({c['hits']})" for c in disc["telegram_channels"][:12]) + "</div>")
        h.append("<div class=muted style='font-size:12px'>Mentions by platform: " + ", ".join(f"{e(k)} {v}" for k, v in sorted(disc["by_platform"].items(), key=lambda kv: -kv[1])) + "</div>")
        for q in disc["queries"]:
            if not q.get("ok"):
                h.append(f"<div class=warn>search failed: {e(q['query'])} - {e(q.get('error', ''))}</div>")
        h.append("</div>")

    # --- posts
    h.append(f"<div class='tile s12' id=posts-tile><h2>Posts</h2><p class=sub>Showing <b id=shown>{min(len(posts), max_posts)}</b> of {len(posts)} · full set in <code>posts.csv</code> / <code>results.json</code></p>"
             "<div class=tools><input id=f placeholder='filter posts…' aria-label='filter posts'><span class='badge b-warn' id=clr style='display:none;cursor:pointer'>✕ clear <span id=cur></span></span></div>"
             "<div class=tbl><table id=posts><thead><tr><th>Date (UTC)</th><th>Platform</th><th>Account</th><th>Text</th><th>Media</th><th>♥</th><th>↻</th><th>💬</th><th>Narr.</th><th>Group</th></tr></thead><tbody>")
    by_eng = sorted(posts, key=lambda p: -p["engagement"])
    shown_posts, seen_ids, per_n = [], set(), {}
    for p in by_eng:                                                    # top posts overall, but never leave a narrative with an empty filter
        if len(shown_posts) < max_posts:
            shown_posts.append(p); seen_ids.add(id(p)); per_n[p["narrative_id"]] = per_n.get(p["narrative_id"], 0) + 1
    for p in by_eng:
        if id(p) not in seen_ids and per_n.get(p["narrative_id"], 0) < 25:
            shown_posts.append(p); seen_ids.add(id(p)); per_n[p["narrative_id"]] = per_n.get(p["narrative_id"], 0) + 1
    shown_posts.sort(key=lambda p: -p["engagement"])
    for p in shown_posts:
        media = " ".join(f'<a href="{e(mm["url"])}" rel="noreferrer noopener">{e(mm["type"])}</a>' for mm in p["media"] if mm["url"].startswith("http"))
        when = e(p["created_at"][:16].replace("T", " "))
        link = f'<a href="{e(p["url"])}" rel="noreferrer noopener">{when}</a>' if p["url"].startswith("http") else when
        h.append(f"<tr data-n='{p['narrative_id']}'><td>{link}</td><td><span class=pl style='color:{color(p['platform'])};border-color:{color(p['platform'])}66'>{e(p['platform'])}</span></td>"
                 f"<td>{e(p['author_name'])}</td><td>{short(p['text'], 260)}</td><td>{media}</td><td>{p['likes']}</td><td>{p['shares']}</td><td>{p['replies']}</td>"
                 f"<td>{p['narrative_id'] if p['narrative_id'] >= 0 else '–'}</td><td>{e(p['coordinated_group'] or '')}</td></tr>")
    h.append("</tbody></table></div></div></div>"
             "<footer>coordwatch · findings are leads for human analysts, not attribution. Coordination ≠ inauthenticity.</footer>"
             f"</main><script>{JS}</script></body></html>")
    return "".join(h)
