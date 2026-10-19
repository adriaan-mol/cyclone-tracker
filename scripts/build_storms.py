#!/usr/bin/env python3
"""Build the cyclone picture for Mauritius and Madagascar from three public sources:

  GDACS        current storms with the official forecast of RSMC La Reunion
               (Meteo-France), cone and wind zones
  JTWC         the US Joint Typhoon Warning Center forecast, as a second opinion
               (and the only track for a storm GDACS has not picked up yet)
  MMS          Mauritius Meteorological Services cyclone warning class (I to IV)
               for Mauritius and Rodrigues

and write:
  data/storms.json   full data for the phone app
  data/brief.json    compact summary for The Daily TradeWinds
  data/brief.md      the same as readable text
  latest.png         newspaper-style map (TradeWinds picture)

Usage:
  python scripts/build_storms.py            # live
  python scripts/build_storms.py --demo     # historical samples -> demo/
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.request

from shapely.geometry import LineString, Point, shape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources as S  # noqa: E402
from shapely.ops import nearest_points, unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://www.gdacs.org/gdacsapi/api"
UTC = dt.timezone.utc
MUT = dt.timezone(dt.timedelta(hours=4), "MUT")  # Mauritius time

# Storms whose current position is inside this box are tracked (lon/lat).
REGION = dict(lat_min=-45.0, lat_max=5.0, lon_min=25.0, lon_max=100.0)
CLOSING_IN_KM = 800  # "closing in" threshold for TradeWinds

PLACES = [
    {"id": "mauritius", "name": "Mauritius", "short": "Mauritius", "lat": -20.16, "lon": 57.50},
    {"id": "fort-dauphin", "name": "Fort Dauphin", "short": "Ft Dauphin", "lat": -25.03, "lon": 46.98},
    {"id": "antananarivo", "name": "Antananarivo", "short": "Tana", "lat": -18.88, "lon": 47.51},
    {"id": "toamasina", "name": "Toamasina", "short": "Toamasina", "lat": -18.15, "lon": 49.40},
]

# Coastal towns used to name a landfall point.
TOWNS = [
    ("Antsiranana", -12.28, 49.29), ("Nosy Be", -13.33, 48.27), ("Vohemar", -13.37, 50.00),
    ("Sambava", -14.27, 50.17), ("Antalaha", -14.90, 50.28), ("Maroantsetra", -15.43, 49.74),
    ("Fenoarivo Atsinanana", -17.38, 49.41), ("Toamasina", -18.15, 49.40),
    ("Mahanoro", -19.90, 48.80), ("Mananjary", -21.23, 48.34), ("Manakara", -22.15, 48.00),
    ("Farafangana", -22.82, 47.83), ("Fort Dauphin", -25.03, 46.98), ("Ambovombe", -25.17, 46.08),
    ("Toliara", -23.35, 43.67), ("Morombe", -21.75, 43.37), ("Morondava", -20.28, 44.28),
    ("Maintirano", -18.06, 44.03), ("Mahajanga", -15.72, 46.32), ("Analalava", -14.63, 47.76),
    ("Port Louis", -20.16, 57.50), ("Mahebourg", -20.41, 57.70), ("Grand Baie", -20.01, 57.58),
    ("Rodrigues", -19.70, 63.42), ("Saint-Denis (Reunion)", -20.88, 55.45),
    ("Saint-Pierre (Reunion)", -21.34, 55.48),
    ("Moroni (Comoros)", -11.70, 43.26), ("Mamoudzou (Mayotte)", -12.78, 45.23),
    ("Pemba", -12.97, 40.52), ("Nacala", -14.56, 40.68), ("Angoche", -16.23, 39.91),
    ("Quelimane", -17.88, 36.89), ("Beira", -19.84, 34.84), ("Vilanculos", -22.00, 35.31),
    ("Inhambane", -23.86, 35.38), ("Maputo", -25.97, 32.57),
]

CATEGORY = {"TD": "Tropical depression", "TS": "Tropical storm"}


# ----------------------------------------------------------------- helpers

def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(deg):
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def mut(t, fmt="%a %d %b ~%H:%M"):
    """Mauritius time; forecast times rounded to 30 min."""
    t = t.astimezone(MUT).replace(second=0, microsecond=0)
    if "~" in fmt:
        m = round((t.hour * 60 + t.minute) / 30) * 30
        t = t.replace(hour=0, minute=0) + dt.timedelta(minutes=m)
    return t.strftime(fmt)


def rel_hours(t, now):
    h = round((t - now).total_seconds() / 3600)
    if h == 0:
        return "now"
    return f"in {h} h" if h > 0 else f"{-h} h ago"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cyclone-tracker (github.com/adriaan-mol)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def rnd(coords, nd=3):
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(coords[0], nd), round(coords[1], nd)]
    return [rnd(c, nd) for c in coords]


def load_land():
    gj = json.load(open(os.path.join(ROOT, "data", "region-land.geojson")))
    land = []
    for f in gj["features"]:
        name = f["properties"]["name"]
        if name == "France":
            name = "Reunion"
        if name == "Fr. S. Antarctic Lands":
            continue
        land.append((name, shape(f["geometry"])))
    return land


LAND = load_land()
LAND_ALL = unary_union([g for _, g in LAND])
MADAGASCAR = next(g for n, g in LAND if n == "Madagascar")


def land_at(lon, lat):
    p = Point(lon, lat)
    if not LAND_ALL.contains(p):
        return None
    for name, g in LAND:
        if g.contains(p):
            return name
    return None


def nearest_town(lat, lon):
    best = min(TOWNS, key=lambda t: haversine(lat, lon, t[1], t[2]))
    return best[0], round(haversine(lat, lon, best[1], best[2]))


# ------------------------------------------------------------ GDACS parsing

def parse_key_time(key, ref):
    """GDACS point key is MMDDHHMM; take the year from the advisory time."""
    mo, d, h, mi = int(key[0:2]), int(key[2:4]), int(key[4:6]), int(key[6:8])
    y = ref.year
    if mo - ref.month > 6:
        y -= 1
    elif ref.month - mo > 6:
        y += 1
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC)


def ring_centre(geom):
    ring = geom["coordinates"][0]
    return (sum(c[0] for c in ring) / len(ring), sum(c[1] for c in ring) / len(ring))


def parse_geometry(gj):
    feats = gj.get("features", [])
    advisory = None
    for f in feats:
        pdate = f["properties"].get("polygondate")
        if pdate:
            advisory = dt.datetime.fromisoformat(pdate).replace(tzinfo=UTC)
            break
    if advisory is None:
        raise ValueError("no advisory time in geometry")

    lines = []
    for f in feats:
        c = f["properties"].get("Class", "")
        if c.startswith("Line_Line") and f["geometry"]["type"] == "LineString":
            lines.append({"coords": f["geometry"]["coordinates"],
                          "forecast": bool(f["properties"].get("forecast")),
                          "cat": f["properties"].get("polygonlabel", "")})

    def cat_for(lon, lat):
        # category of the segment that ends (or starts) at this point
        best, bd = "", 0.15
        for ln in lines:
            for i, (x, y) in enumerate((ln["coords"][-1], ln["coords"][0])):
                d = abs(x - lon) + abs(y - lat) + i * 0.01
                if d < bd:
                    best, bd = ln["cat"], d
        return best

    pts = {}
    for f in feats:
        p = f["properties"]
        if not p.get("Class", "").startswith("Point_Polygon"):
            continue
        t = parse_key_time(p["key"], advisory)
        lon, lat = ring_centre(f["geometry"])
        if t in pts:  # duplicate time from an overlapping forecast; keep the first
            continue
        pts[t] = {"t": t, "lat": round(lat, 2), "lon": round(lon, 2)}
    points = [pts[t] for t in sorted(pts)]
    for p in points:
        p["cat"] = cat_for(p["lon"], p["lat"])

    past = [p for p in points if p["t"] <= advisory]
    fcst = [p for p in points if p["t"] > advisory]

    polys = {}
    for f in feats:
        c = f["properties"].get("Class", "")
        if c in ("Poly_Cones", "Poly_Green", "Poly_Orange", "Poly_Red") and f["geometry"]["type"] in ("Polygon", "MultiPolygon"):
            g = shape(f["geometry"]).buffer(0)
            polys[c] = g.union(polys[c]) if c in polys else g
    return advisory, past, fcst, lines, polys


# ------------------------------------------------------------- analysis

def densify(chain, step_km=8):
    """Sample a time-stamped chain of points every ~step_km."""
    out = []
    for a, b in zip(chain, chain[1:]):
        d = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
        n = max(1, int(d / step_km))
        for i in range(n):
            f = i / n
            out.append({"lat": a["lat"] + (b["lat"] - a["lat"]) * f,
                        "lon": a["lon"] + (b["lon"] - a["lon"]) * f,
                        "t": a["t"] + (b["t"] - a["t"]) * f})
    if chain:
        out.append(dict(chain[-1]))
    return out


def analyse(storm, now):
    past, fcst = storm["past"], storm["fcst"]
    cur = past[-1]
    chain = [cur] + fcst
    dense = densify(chain)

    # motion from the last ~12 h of observed track
    motion = None
    prev = next((p for p in reversed(past[:-1]) if (cur["t"] - p["t"]).total_seconds() >= 5 * 3600), None)
    if prev:
        hrs = (cur["t"] - prev["t"]).total_seconds() / 3600
        km = haversine(prev["lat"], prev["lon"], cur["lat"], cur["lon"])
        brg = bearing(prev["lat"], prev["lon"], cur["lat"], cur["lon"])
        motion = {"toward_deg": round(brg), "toward": compass(brg), "speed_kmh": round(km / hrs)}

    # landfalls along the forecast
    landfalls = []
    over = land_at(cur["lon"], cur["lat"])
    state = over
    for s in dense[1:]:
        here = land_at(s["lon"], s["lat"])
        if here and here != state:
            town, tkm = nearest_town(s["lat"], s["lon"])
            landfalls.append({"country": here, "lat": round(s["lat"], 2), "lon": round(s["lon"], 2),
                              "time": s["t"], "near": town, "near_km": tkm})
        state = here

    # closest approach to key places (from now on)
    places = []
    for pl in PLACES:
        dists = [(haversine(s["lat"], s["lon"], pl["lat"], pl["lon"]), s) for s in dense]
        dmin, smin = min(dists, key=lambda x: x[0])
        now_km = dists[0][0]
        zone = None
        for cls, label in (("Poly_Red", "hurricane-force winds (119+ km/h)"),
                           ("Poly_Orange", "storm-force winds (93+ km/h)"),
                           ("Poly_Green", "gale-force winds (63+ km/h)")):
            g = storm["polys"].get(cls)
            if g is not None and g.contains(Point(pl["lon"], pl["lat"])):
                zone = label
                break
        in_cone = bool(storm["polys"].get("Poly_Cones") is not None and storm["polys"]["Poly_Cones"].contains(Point(pl["lon"], pl["lat"])))
        places.append({"id": pl["id"], "name": pl["name"], "now_km": round(now_km),
                       "closest_km": round(dmin), "closest_time": smin["t"],
                       "moving_away": smin is dense[0] or dmin >= now_km - 1,
                       "wind_zone": zone, "in_cone": in_cone})

    # closest approach to the Madagascar coast
    mada = None
    for s in dense:
        p = Point(s["lon"], s["lat"])
        if MADAGASCAR.contains(p):
            km = 0.0
        else:
            q = nearest_points(MADAGASCAR, p)[0]
            km = haversine(s["lat"], s["lon"], q.y, q.x)
        if mada is None or km < mada[0]:
            mada = (km, s)
    madagascar = {"closest_km": round(mada[0]), "closest_time": mada[1]["t"]}

    closing = (any(lf["country"] in ("Madagascar", "Mauritius", "Reunion") for lf in landfalls)
               or madagascar["closest_km"] <= CLOSING_IN_KM
               or any(p["closest_km"] <= CLOSING_IN_KM or p["wind_zone"] for p in places
                      if p["id"] in ("mauritius",)))
    return {"motion": motion, "landfalls": landfalls, "places": places,
            "madagascar": madagascar, "over_land": over, "closing_in": closing}


# ------------------------------------------------------------- building

def storm_from(meta, gj, now, report_url=None, demo=False):
    advisory, past, fcst, lines, polys = parse_geometry(gj)
    if not past:
        raise ValueError("no observed track")
    s = {"past": past, "fcst": fcst, "polys": polys}
    a = analyse(s, now)
    sev = meta.get("severitydata") or {}
    status = (sev.get("severitytext") or "").split("(")[0].strip()
    name = (meta.get("eventname") or meta.get("name") or "Unnamed").rsplit("-", 1)[0].title()
    cur = past[-1]

    def pt(p):
        return {"t": iso(p["t"]), "lat": p["lat"], "lon": p["lon"], "cat": p["cat"]}

    def poly(cls, tol=0.03):
        g = polys.get(cls)
        if g is None or g.is_empty:
            return None
        return {"type": g.geom_type, "coordinates": rnd(json.loads(json.dumps(g.simplify(tol).__geo_interface__))["coordinates"])}

    return {
        "id": meta.get("eventid"),
        "name": name,
        "status": "Historical advisory (demo)" if demo else (status or CATEGORY.get(cur["cat"], "Tropical cyclone")),
        "category": cur["cat"],
        "max_wind_kmh": round(sev.get("severity") or 0),
        "alert": meta.get("alertlevel", ""),
        "source": meta.get("source", ""),
        "advisory": iso(advisory),
        "position": {"lat": cur["lat"], "lon": cur["lon"], "t": iso(cur["t"])},
        "over_land": a["over_land"],
        "motion": a["motion"],
        "past": [pt(p) for p in past],
        "forecast": [pt(p) for p in fcst],
        "forecast_segments": [rnd(ln["coords"], 2) for ln in lines if ln["forecast"]],
        "cone": poly("Poly_Cones"),
        "wind_zones": {k: poly(c) for k, c in (("gale", "Poly_Green"), ("storm", "Poly_Orange"), ("hurricane", "Poly_Red"))},
        "landfalls": [dict(lf, time=iso(lf["time"])) for lf in a["landfalls"]],
        "places": [dict(p, closest_time=iso(p["closest_time"])) for p in a["places"]],
        "madagascar": dict(a["madagascar"], closest_time=iso(a["madagascar"]["closest_time"])),
        "closing_in": a["closing_in"],
        "jtwc": None,
        "report_url": report_url or f"https://www.gdacs.org/report.aspx?eventid={meta.get('eventid')}&eventtype=TC",
    }


def _jt_cat(kt):
    return "Tropical depression" if kt < 34 else "Tropical storm" if kt < 64 else "Tropical cyclone"


def _jt_track(j):
    past = [dict(p, cat="") for p in j["past"]]
    fcst = [dict(p, cat="") for p in j["fcst"]]
    return past, fcst


def jtwc_view(j, now):
    """JTWC's take on a storm GDACS already tracks: second forecast line and its timings."""
    past, fcst = _jt_track(j)
    a = analyse({"past": past, "fcst": fcst, "polys": {}}, now)
    mu = next(p for p in a["places"] if p["id"] == "mauritius")
    return {
        "name": j["name"], "number": j["number"], "advisory": iso(j["advisory"]),
        "max_wind_kmh": j["max_wind_kmh"], "wind_note": "1-minute mean",
        "past": [{"t": iso(p["t"]), "lat": p["lat"], "lon": p["lon"]} for p in past
                 if p["t"] >= now - dt.timedelta(hours=96)],
        "forecast": [{"t": iso(p["t"]), "lat": p["lat"], "lon": p["lon"],
                      "wind_kmh": round(p["wind_kt"] * 1.852)} for p in fcst],
        "landfalls": [dict(lf, time=iso(lf["time"])) for lf in a["landfalls"]],
        "mauritius": dict(mu, closest_time=iso(mu["closest_time"])),
        "madagascar": dict(a["madagascar"], closest_time=iso(a["madagascar"]["closest_time"])),
    }


def storm_from_jtwc(j, now):
    """A storm only JTWC is warning on (GDACS has not picked it up yet)."""
    past, fcst = _jt_track(j)
    a = analyse({"past": past, "fcst": fcst, "polys": {}}, now)
    cur = past[-1]

    def pt(p):
        return {"t": iso(p["t"]), "lat": p["lat"], "lon": p["lon"], "cat": "TS" if p["wind_kt"] >= 34 else "TD"}

    chain = [cur] + fcst
    return {
        "id": f"JTWC-{j['number']}", "name": j["name"],
        "status": f"{_jt_cat(cur['wind_kt'])} (JTWC estimate)", "category": "",
        "max_wind_kmh": j["max_wind_kmh"], "alert": "", "source": "JTWC",
        "advisory": iso(j["advisory"]),
        "position": {"lat": cur["lat"], "lon": cur["lon"], "t": iso(cur["t"])},
        "over_land": a["over_land"], "motion": a["motion"],
        "past": [pt(p) for p in past if p["t"] >= now - dt.timedelta(hours=120)],
        "forecast": [pt(p) for p in fcst],
        "forecast_segments": [[[p["lon"], p["lat"]] for p in chain]] if fcst else [],
        "cone": None, "wind_zones": {},
        "landfalls": [dict(lf, time=iso(lf["time"])) for lf in a["landfalls"]],
        "places": [dict(p, closest_time=iso(p["closest_time"])) for p in a["places"]],
        "madagascar": dict(a["madagascar"], closest_time=iso(a["madagascar"]["closest_time"])),
        "closing_in": a["closing_in"], "jtwc": None,
        "report_url": "https://www.metoc.navy.mil/jtwc/jtwc.html",
    }


def merge_jtwc(storms, jtwc, now):
    for j in jtwc:
        cur = j["past"][-1]
        best = min(storms, key=lambda s: haversine(cur["lat"], cur["lon"], s["position"]["lat"], s["position"]["lon"]),
                   default=None)
        if best and haversine(cur["lat"], cur["lon"], best["position"]["lat"], best["position"]["lon"]) < 400 \
                and not best.get("jtwc"):
            best["jtwc"] = jtwc_view(j, now)
        else:
            storms.append(storm_from_jtwc(j, now))
    return storms


def in_region(lat, lon):
    return REGION["lat_min"] <= lat <= REGION["lat_max"] and REGION["lon_min"] <= lon <= REGION["lon_max"]


def gdacs_storms(now):
    data = fetch_json(f"{API}/events/geteventlist/SEARCH?eventlist=TC")
    storms, errors = [], []
    for f in data.get("features", []):
        p = f.get("properties", {})
        if str(p.get("iscurrent")).lower() != "true":
            continue
        lon, lat = (f.get("geometry", {}).get("coordinates") or [None, None])[:2]
        if lat is None or not in_region(lat, lon):
            continue
        url = (p.get("url") or {}).get("geometry") or \
            f"{API}/polygons/getgeometry?eventtype=TC&eventid={p['eventid']}&episodeid={p['episodeid']}"
        try:
            gj = fetch_json(url)
            storms.append(storm_from(p, gj, now, (p.get("url") or {}).get("report")))
        except Exception as e:  # keep going with the other storms
            errors.append(f"GDACS {p.get('eventname')}: {e}")
    return storms, errors


def build_live(now):
    """GDACS (carries the La Reunion forecast) + JTWC + Mauritius warnings.
    Each source can fail on its own; only all-tracks-failed is fatal."""
    errors, status = [], {}
    storms = None
    try:
        storms, errs = gdacs_storms(now)
        errors += errs
        status["gdacs"] = "ok"
    except Exception as e:
        errors.append(f"GDACS feed: {e}")
        status["gdacs"] = "error"
    jtwc = None
    try:
        jtwc = [j for j in S.fetch_jtwc() if in_region(j["past"][-1]["lat"], j["past"][-1]["lon"])]
        status["jtwc"] = "ok"
    except Exception as e:
        errors.append(f"JTWC: {e}")
        status["jtwc"] = "error"
    warnings = None
    try:
        warnings = S.fetch_mms(now)
        status["mms"] = "ok"
    except Exception as e:
        errors.append(f"Mauritius Meteorological Services: {e}")
        status["mms"] = "error"
    disturbances = []
    try:
        disturbances = S.fetch_jtwc_disturbances()
        status["jtwc_outlook"] = "ok"
    except Exception as e:
        errors.append(f"JTWC outlook: {e}")
        status["jtwc_outlook"] = "error"
    if storms is None and jtwc is None:
        raise RuntimeError("; ".join(errors))
    storms = merge_jtwc(storms or [], jtwc or [], now)
    return storms, errors, warnings, status, watch_list(disturbances, storms)


def watch_list(disturbances, storms):
    """Disturbances (JTWC invests) in the region that are not yet a tracked storm."""
    out = []
    for d in disturbances:
        if not in_region(d["lat"], d["lon"]):
            continue
        if any(haversine(d["lat"], d["lon"], s["position"]["lat"], s["position"]["lon"]) < 400 for s in storms):
            continue
        out.append(dict(d, issued=iso(d["issued"]) if d.get("issued") else None,
                        mauritius_km=round(haversine(d["lat"], d["lon"], -20.16, 57.50)),
                        antananarivo_km=round(haversine(d["lat"], d["lon"], -18.88, 47.51)),
                        name=f"Invest {d['id']}"))
    return out


def disturbance_line(d):
    w = f", winds {d['wind_kmh'][0]}-{d['wind_kmh'][1]} km/h" if d.get("wind_kmh") else ""
    tcfa = ", formation alert issued" if d.get("tcfa") else ""
    return (f"Watching {d['name']} near {abs(d['lat']):.1f}°{'S' if d['lat'] < 0 else 'N'} {d['lon']:.1f}°E{w}: "
            f"{d['mauritius_km']:,} km from Mauritius, {d['antananarivo_km']:,} km from Antananarivo. "
            f"JTWC chance of becoming a tropical cyclone within 24 h: {d['chance']}{tcfa}.")


def build_demo():
    metas = {m["eventid"]: m for m in json.load(open(os.path.join(ROOT, "demo", "events.json")))}
    storms = []
    for fn, eid in (("gezani.json", 1001256), ("belal.json", 1001041)):
        gj = json.load(open(os.path.join(ROOT, "demo", "raw", fn)))
        adv, *_ = parse_geometry(gj)
        st = storm_from(metas[eid], gj, adv, demo=True)
        warn = None
        if fn == "belal.json":  # the real Class III bulletin issued 30 min before this advisory
            raw = open(os.path.join(ROOT, "tests", "samples", "mms_20240115110449.html"), "rb").read()
            warn = {"mauritius": S.parse_mms(raw, "Mauritius", adv), "rodrigues": None}
        storms.append((adv, st, warn))
    return storms


# ------------------------------------------------------------- outputs

def describe(s, now):
    """One paragraph, plain English, Mauritius time."""
    t = lambda x: dt.datetime.fromisoformat(x.replace("Z", "+00:00"))
    pos = s["position"]
    mu = next(p for p in s["places"] if p["id"] == "mauritius")
    parts = [f"{s['name']} ({s['status'].lower()}, max wind {s['max_wind_kmh']} km/h) is "
             f"{mu['now_km']:,} km from Mauritius"]
    if s["motion"]:
        parts[0] += f", moving {s['motion']['toward']} at {s['motion']['speed_kmh']} km/h"
    parts[0] += "."
    for lf in s["landfalls"]:
        parts.append(f"Forecast landfall: {lf['country']} near {lf['near']}, {mut(t(lf['time']))} Mauritius time ({rel_hours(t(lf['time']), now)}).")
    if not s["landfalls"]:
        md = s["madagascar"]
        if md["closest_km"] > 0:
            parts.append(f"Closest to Madagascar's coast: {md['closest_km']:,} km, {mut(t(md['closest_time']))} ({rel_hours(t(md['closest_time']), now)}).")
    if mu["moving_away"]:
        parts.append("Mauritius: closest point already passed, moving away.")
    else:
        parts.append(f"Closest to Mauritius: {mu['closest_km']:,} km, {mut(t(mu['closest_time']))} ({rel_hours(t(mu['closest_time']), now)}).")
    if mu["wind_zone"]:
        parts.append(f"Mauritius lies inside the forecast zone for {mu['wind_zone']}.")
    j = s.get("jtwc")
    if j:
        bits = []
        for lf in j["landfalls"]:
            bits.append(f"landfall {lf['country']} near {lf['near']}, {mut(t(lf['time']))} ({rel_hours(t(lf['time']), now)})")
        jm = j["mauritius"]
        if not jm["moving_away"]:
            bits.append(f"closest to Mauritius {jm['closest_km']:,} km, {mut(t(jm['closest_time']))} ({rel_hours(t(jm['closest_time']), now)})")
        if bits:
            parts.append("For comparison, the US Joint Typhoon Warning Center (JTWC) forecasts: " + "; ".join(bits) + ".")
    return " ".join(parts)


def warning_line(w):
    if not w:
        return None
    t = dt.datetime.fromisoformat(w["issued"].replace("Z", "+00:00")) if w.get("issued") else None
    when = f", bulletin of {mut(t, '%a %d %b %H:%M')}" if t else ""
    return f"Cyclone warning Class {w['class']} in force in {w['island']}{when}."


def write_outputs(outdir, storms, now, errors, img_name, demo_note=None, warnings=None, status=None,
                  disturbances=None):
    os.makedirs(outdir, exist_ok=True)
    warnings = warnings or {}
    disturbances = disturbances or []
    doc = {"generated": iso(now),
           "source": "GDACS (forecast of RSMC La Reunion), JTWC, Mauritius Meteorological Services",
           "sources": status or {}, "warnings": warnings,
           "demo": demo_note, "errors": errors, "storms": storms, "disturbances": disturbances}
    json.dump(doc, open(os.path.join(outdir, "storms.json"), "w"), separators=(",", ":"))

    closing = [s for s in storms if s["closing_in"]]
    wlines = [warning_line(w) for w in (warnings.get("mauritius"), warnings.get("rodrigues")) if w]
    headline = (f"Cyclone watch: {', '.join(s['name'] for s in closing)} closing in"
                if closing else ("No cyclone threatening Mauritius or Madagascar"
                                 if storms else "No active cyclones in the South-West Indian Ocean"))
    if not storms and disturbances:
        headline = (f"No cyclones yet; watching {len(disturbances)} disturbance"
                    f"{'s' if len(disturbances) > 1 else ''} ({', '.join(d['id'] for d in disturbances)})")
    if wlines:
        headline = wlines[0].rstrip(".").split(",")[0] + ". " + headline
    brief = {
        "generated": iso(now),
        "generated_mut": mut(now, "%a %d %b %Y %H:%M"),
        "closing_in": bool(closing or wlines),
        "mauritius_warning": warnings.get("mauritius"),
        "rodrigues_warning": warnings.get("rodrigues"),
        "warning_lines": wlines,
        "storm_count": len(storms),
        "image_url": f"https://adriaan-mol.github.io/cyclone-tracker/{img_name}",
        "image_raw_url": f"https://raw.githubusercontent.com/adriaan-mol/cyclone-tracker/main/{img_name}",
        "tracker_url": "https://adriaan-mol.github.io/cyclone-tracker/",
        "headline": headline,
        "storms": [{"name": s["name"], "closing_in": s["closing_in"], "summary": describe(s, now)} for s in storms],
        "disturbances": [{"id": d["id"], "chance": d["chance"], "summary": disturbance_line(d)} for d in disturbances],
        "feed_errors": errors,
    }
    json.dump(brief, open(os.path.join(outdir, "brief.json"), "w"), indent=1)
    md = [f"# {brief['headline']}", "", f"_Checked {brief['generated_mut']} Mauritius time._", ""]
    md += [f"**{w}**" for w in wlines] + ([""] if wlines else [])
    md += [f"- {x['summary']}" for x in brief["storms"]]
    md += [f"- {x['summary']}" for x in brief["disturbances"]]
    if not brief["storms"] and not brief["disturbances"]:
        md += ["- All quiet."]
    open(os.path.join(outdir, "brief.md"), "w").write("\n".join(md) + "\n")
    return brief


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    from render_map import render  # noqa: E402

    if a.demo:
        for adv, s, warn in build_demo():
            key = s["name"].lower()
            out = os.path.join(ROOT, "demo", key)
            note = f"Historical advisory for {s['name']}, {mut(adv, '%d %b %Y %H:%M')} Mauritius time"
            write_outputs(out, [s], adv, [], f"demo/{key}/latest.png", note, warn)
            render([s], adv, os.path.join(out, "latest.png"), note, warn)
            print("demo", key, describe(s, adv))
        return

    now = dt.datetime.now(UTC).replace(second=0, microsecond=0)
    try:
        storms, errors, warnings, status, watch = build_live(now)
    except Exception as e:
        print("All track sources failed:", e, file=sys.stderr)
        sys.exit(1)  # keep the previous good data in place
    write_outputs(os.path.join(ROOT, "data"), storms, now, errors, "latest.png", None, warnings, status, watch)
    render(storms, now, os.path.join(ROOT, "latest.png"), None, warnings, watch)
    for s in storms:
        print(describe(s, now))
    for d in watch:
        print(disturbance_line(d))
    print(f"{len(storms)} storm(s), {len(watch)} disturbance(s) in region; sources {status}; errors: {errors}")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
