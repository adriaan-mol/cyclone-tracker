"""Newspaper-style (Daily TradeWinds) map of cyclones near Mauritius / Madagascar."""
import datetime as dt
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from shapely.geometry import shape  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTC = dt.timezone.utc
MUT = dt.timezone(dt.timedelta(hours=4))

PAPER = "#efe4c6"
INK = "#2a1f14"
FADED = "#6b5a44"
LAND = "#d8c79f"

for f in ("IMFeENrm28P.ttf", "IMFeENit28P.ttf", "IMFeENsc28P.ttf"):
    p = os.path.join(ROOT, "fonts", f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
names = {f.name for f in font_manager.fontManager.ttflist}
SERIF = "IM FELL English" if "IM FELL English" in names else "DejaVu Serif"
SC = "IM FELL English SC" if "IM FELL English SC" in names else SERIF

PLACES = [("Mauritius", -20.16, 57.50), ("Antananarivo", -18.88, 47.51),
          ("Fort Dauphin", -25.03, 46.98), ("Toamasina", -18.15, 49.40),
          ("Reunion", -21.11, 55.53), ("Rodrigues", -19.70, 63.42)]


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def rel(t, now):
    h = round((t - now).total_seconds() / 3600)
    return "now" if h == 0 else (f"+{h} h" if h > 0 else f"{h} h")


def poly_patches(ax, geom, **kw):
    g = shape(geom) if isinstance(geom, dict) else geom
    polys = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
    for p in polys:
        if p.geom_type != "Polygon":
            continue
        verts, codes = [], []
        for ring in [p.exterior] + list(p.interiors):
            xy = list(ring.coords)
            verts += xy
            codes += [Path.MOVETO] + [Path.LINETO] * (len(xy) - 2) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), **kw))


def cyclone_symbol(ax, x, y, scale, color=INK, z=20):
    ax.plot([x], [y], marker="o", ms=9, mfc=color, mec=PAPER, mew=1, zorder=z + 1)
    for a0 in (0, math.pi):
        th = [a0 + i * 0.13 for i in range(16)]
        r = [scale * (0.25 + i * 0.05) for i in range(16)]
        # southern hemisphere: clockwise arms
        ax.plot([x + rr * math.cos(-t) for rr, t in zip(r, th)],
                [y + rr * math.sin(-t) for rr, t in zip(r, th)], color=color, lw=2.2, zorder=z,
                solid_capstyle="round")


def away(deg, dist):
    """Text offset (points) in compass direction deg; returns x, y, ha."""
    r = math.radians(deg)
    x, y = math.sin(r) * dist, math.cos(r) * dist
    return x, y, ("left" if x > 8 else "right" if x < -8 else "center")


def hm(t):
    """Forecast times are only good to the hour or so: round to 30 min."""
    t = t.astimezone(MUT).replace(second=0, microsecond=0)
    m = round((t.hour * 60 + t.minute) / 30) * 30
    t = t.replace(hour=0, minute=0) + dt.timedelta(minutes=m)
    return f"{t:%a %d %b} ~{t:%H:%M}"


def extent_for(storms, now):
    xs, ys = [57.5, 47.0], [-20.2, -19.0]
    for s in storms:
        cutoff = now - dt.timedelta(hours=72)
        for p in s["past"]:
            if T(p["t"]) >= cutoff:
                xs.append(p["lon"]); ys.append(p["lat"])
        xs.append(s["position"]["lon"]); ys.append(s["position"]["lat"])
        for p in s["forecast"] + ((s.get("jtwc") or {}).get("forecast") or []):
            xs.append(p["lon"]); ys.append(p["lat"])
    x0, x1, y0, y1 = min(xs) - 3, max(xs) + 3, min(ys) - 3, max(ys) + 3
    w, h = x1 - x0, y1 - y0
    if w < 20:
        c = (x0 + x1) / 2; x0, x1 = c - 10, c + 10
    # keep a pleasant 4:3 frame (in projected units)
    k = math.cos(math.radians((y0 + y1) / 2))
    w, h = (x1 - x0) * k, y1 - y0
    if w / h > 4 / 3:
        c = (y0 + y1) / 2; h = w * 3 / 4; y0, y1 = c - h / 2, c + h / 2
    else:
        c = (x0 + x1) / 2; w = h * 4 / 3 / k; x0, x1 = c - w / 2, c + w / 2
    return x0, x1, max(y0, -48), min(y1, 8)


def render(storms, now, out_path, note=None, warnings=None):
    storms = [s for s in storms if s["closing_in"]] or storms
    plt.rcParams["hatch.color"] = FADED
    plt.rcParams["hatch.linewidth"] = 0.35
    fig = plt.figure(figsize=(9.6, 7.6), dpi=125, facecolor=PAPER)
    ax = fig.add_axes([0.04, 0.09, 0.92, 0.74], facecolor=PAPER)
    if storms:
        x0, x1, y0, y1 = extent_for(storms, now)
    else:
        x0, x1, y0, y1 = 40, 66, -30, -10
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect(1 / math.cos(math.radians((y0 + y1) / 2)))
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color(INK); sp.set_linewidth(1.6)

    # graticule
    for lon in range(int(x0 // 5 * 5), int(x1) + 5, 5):
        ax.axvline(lon, color=FADED, lw=0.4, ls=(0, (1, 3)), zorder=1)
        if x0 < lon < x1:
            ax.text(lon, y0 + (y1 - y0) * 0.012, f"{lon}°E", fontsize=7, color=FADED, ha="center", family=SERIF)
    for lat in range(int(y0 // 5 * 5), int(y1) + 5, 5):
        ax.axhline(lat, color=FADED, lw=0.4, ls=(0, (1, 3)), zorder=1)
        if y0 < lat < y1:
            ax.text(x0 + (x1 - x0) * 0.008, lat + 0.15, f"{abs(lat)}°S", fontsize=7, color=FADED, family=SERIF)

    land = json.load(open(os.path.join(ROOT, "data", "region-land.geojson")))
    for f in land["features"]:
        poly_patches(ax, f["geometry"], facecolor=LAND, edgecolor=INK, lw=0.8, hatch="////", zorder=2)

    for name, la, lo in PLACES:
        if x0 < lo < x1 and y0 < la < y1:
            ax.plot(lo, la, "s", ms=4, mfc=PAPER, mec=INK, mew=1, zorder=8)
            ax.text(lo + 0.25, la - 0.45, name, fontsize=8.5, color=INK, family=SERIF, style="italic", zorder=8)

    for s in storms:
        if s.get("cone"):
            poly_patches(ax, s["cone"], facecolor="none", edgecolor=INK, lw=0.8, ls=(0, (4, 2)),
                         hatch="xx", alpha=0.55, zorder=3)
        hz = (s.get("wind_zones") or {}).get("hurricane")
        if hz:
            poly_patches(ax, hz, facecolor="none", edgecolor=INK, lw=1.0, ls=(0, (1, 1.5)), zorder=4)

        past = [p for p in s["past"] if T(p["t"]) >= now - dt.timedelta(hours=96)] or s["past"][-1:]
        ax.plot([p["lon"] for p in past], [p["lat"] for p in past], color=INK, lw=2.2, zorder=6)
        for p in past[:-1]:
            ax.plot(p["lon"], p["lat"], "o", ms=3.5, mfc=INK if p["cat"] == "TS" else PAPER, mec=INK, zorder=7)
        for seg in s.get("forecast_segments") or []:
            ax.plot([c[0] for c in seg], [c[1] for c in seg], color=INK, lw=1.8, ls=(0, (5, 3)), zorder=6)
        jt = s.get("jtwc")
        if jt and jt["forecast"]:
            chain = [s["position"]] + jt["forecast"]
            ax.plot([p["lon"] for p in chain], [p["lat"] for p in chain], color=FADED, lw=1.7, ls=(0, (6, 2, 1, 2)), zorder=5)
            ax.plot([p["lon"] for p in jt["forecast"]], [p["lat"] for p in jt["forecast"]], "x", ms=4, color=FADED, zorder=5)
            e = jt["forecast"][-1]
            ax.annotate("JTWC", (e["lon"], e["lat"]), xytext=(5, 5), textcoords="offset points", fontsize=7.5,
                        family=SERIF, style="italic", color=FADED, zorder=9)

        last = None
        labelled = [(s["position"]["lon"], s["position"]["lat"])]
        for p in s["forecast"]:
            t = T(p["t"])
            ax.plot(p["lon"], p["lat"], "o", ms=5, mfc=PAPER, mec=INK, mew=1.2, zorder=7)
            crowded = any(abs(p["lon"] - a) < (x1 - x0) * 0.06 and abs(p["lat"] - b) < (y1 - y0) * 0.04 for a, b in labelled)
            if not crowded and (last is None or (t - last).total_seconds() >= 11 * 3600):
                labelled.append((p["lon"], p["lat"]))
                ax.annotate(f"{t.astimezone(MUT):%a %Hh}  ({rel(t, now)})", (p["lon"], p["lat"]),
                            xytext=(7, -3), textcoords="offset points", fontsize=7.5, color=INK, family=SERIF,
                            zorder=9, bbox=dict(boxstyle="square,pad=0.1", fc=PAPER, ec="none", alpha=0.8))
                last = t

        pos = s["position"]
        scale = (x1 - x0) / 25
        cyclone_symbol(ax, pos["lon"], pos["lat"], scale)
        mv = s.get("motion") or {"toward_deg": 270}
        nx, ny, ha = away(mv["toward_deg"] - 90, 34)
        ax.annotate(s["name"].upper(), (pos["lon"], pos["lat"]), xytext=(nx, ny), textcoords="offset points",
                    ha=ha, va="center",
                    fontsize=13, family=SC, color=INK, zorder=21,
                    bbox=dict(boxstyle="square,pad=0.15", fc=PAPER, ec=INK, lw=0.8))

        for lf in s["landfalls"]:
            t = T(lf["time"])
            ax.plot(lf["lon"], lf["lat"], marker="*", ms=17, mfc=INK, mec=PAPER, zorder=22)
            lx, ly, lha = away(mv["toward_deg"] + 90, 60)
            ax.annotate(f"LANDFALL near {lf['near']}\n{hm(t)}  ({rel(t, now)})",
                        (lf["lon"], lf["lat"]), xytext=(lx, ly), textcoords="offset points", ha=lha, va="center",
                        fontsize=9, family=SERIF, color=INK, zorder=22,
                        bbox=dict(boxstyle="square,pad=0.3", fc=PAPER, ec=INK, lw=1),
                        arrowprops=dict(arrowstyle="-", color=INK, lw=0.8))

        mu = next((p for p in s["places"] if p["id"] == "mauritius"), None)
        if mu and not mu["moving_away"] and mu["closest_km"] < 1500:
            t = T(mu["closest_time"])
            # find the forecast point nearest that time for the connector
            pts = [s["position"]] + s["forecast"]
            near = min(pts, key=lambda p: abs((T(p["t"]) - t).total_seconds()))
            ax.annotate("", (57.5, -20.16), xytext=(near["lon"], near["lat"]),
                        arrowprops=dict(arrowstyle="-", ls=(0, (1, 2)), color=INK, lw=1), zorder=5)
            b = math.degrees(math.atan2(57.5 - pos["lon"], -20.16 - pos["lat"]))
            mx, my, mha = away(b, 48)
            ax.annotate(f"Closest to Mauritius: {mu['closest_km']:,} km\n{hm(t)}  ({rel(t, now)})",
                        (57.5, -20.16), xytext=(mx, my), textcoords="offset points", fontsize=9, ha=mha, va="center",
                        family=SERIF, color=INK, zorder=22,
                        bbox=dict(boxstyle="square,pad=0.3", fc=PAPER, ec=INK, lw=1))

    # masthead
    fig.text(0.5, 0.945, "CYCLONE WATCH", ha="center", va="center", fontsize=30, family=SC, color=INK)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.905, 0.905], color=INK, lw=1.6))
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.898, 0.898], color=INK, lw=0.6))
    if storms:
        sub = "  ·  ".join(f"{s['name']}: {s['status'].lower()}, max wind {s['max_wind_kmh']} km/h"
                           + (f", heading {s['motion']['toward']} at {s['motion']['speed_kmh']} km/h" if s.get("motion") else "")
                           for s in storms)
    else:
        sub = "All quiet. No active tropical cyclones in the South-West Indian Ocean."
        ax.text((x0 + x1) / 2, y1 - 2.2, "No Cyclones Abroad", ha="center", fontsize=22, family=SC, color=INK, zorder=10,
                bbox=dict(boxstyle="square,pad=0.4", fc=PAPER, ec=INK))
    fig.text(0.5, 0.865, sub, ha="center", fontsize=10.5, family=SERIF, style="italic", color=INK, wrap=True)
    warns = [w for w in ((warnings or {}).get("mauritius"), (warnings or {}).get("rodrigues")) if w]
    if warns:
        txt = "   ·   ".join(f"CYCLONE WARNING CLASS {w['class']} IN FORCE IN {w['island'].upper()}" for w in warns)
        ax.text(0.5, 0.965, txt, transform=ax.transAxes, ha="center", va="top", fontsize=12.5, family=SC,
                color=PAPER, zorder=30, bbox=dict(boxstyle="square,pad=0.45", fc=INK, ec=INK))

    # legend + credit
    y = 0.05
    items = [("line", dict(color=INK, lw=2.2), "observed track"),
             ("line", dict(color=INK, lw=1.8, ls=(0, (5, 3))), "official forecast (La Réunion)"),
             ("cone", None, "cone of uncertainty"),
             ("line", dict(color=INK, lw=1, ls=(0, (1, 1.5))), "hurricane-force winds")]
    if any(s.get("jtwc") for s in storms):
        items.append(("line", dict(color=FADED, lw=1.7, ls=(0, (6, 2, 1, 2))), "JTWC forecast"))
    x = 0.05
    for kind, style, label in items:
        if kind == "line":
            fig.add_artist(plt.Line2D([x, x + 0.035], [y, y], **style))
        else:
            fig.patches.append(Rectangle((x, y - 0.011), 0.035, 0.022, transform=fig.transFigure, fc="none", ec=INK,
                                         hatch="xx", lw=0.6, ls=(0, (4, 2))))
        fig.text(x + 0.04, y, label, va="center", fontsize=7.5, family=SERIF, color=INK)
        x += 0.045 + 0.0062 * len(label)
    stamp = note or f"As of {now.astimezone(MUT):%a %d %b %Y, %H:%M} Mauritius time"
    fig.text(0.06, 0.018, stamp + "  ·  times in Mauritius time (Madagascar is one hour behind)",
             fontsize=7.5, family=SERIF, style="italic", color=FADED)
    fig.text(0.94, 0.018, "Data: GDACS (RSMC La Réunion) · JTWC · Mauritius Met Services", ha="right", fontsize=7.5, family=SERIF,
             style="italic", color=FADED)
    fig.patches.append(Rectangle((0.012, 0.008), 0.976, 0.984, transform=fig.transFigure, fill=False, ec=INK, lw=2))
    fig.patches.append(Rectangle((0.02, 0.0), 0.96, 0.0, transform=fig.transFigure, fill=False, ec=INK, lw=0))
    fig.savefig(out_path, facecolor=PAPER)
    plt.close(fig)
