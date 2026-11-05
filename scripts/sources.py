"""Public cyclone sources besides GDACS, for the South-West Indian Ocean.

  JTWC (US Joint Typhoon Warning Center): public RSS feed + JMV 3.0 ".tcw" track files.
  Mauritius Meteorological Services (MMS): the public cyclone warning bulletin pages.

The Meteo-France La Reunion forecast reaches us through GDACS, which republishes it.

Every fetcher returns plain data and raises on failure; the caller decides the
fallback. Parsers are separate so they can be tested on saved samples.
"""
import datetime as dt
import html
import re
import urllib.request

UTC = dt.timezone.utc
MUT = dt.timezone(dt.timedelta(hours=4))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
KT = 1.852  # km/h per knot

JTWC_RSS = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
# Significant Tropical Weather Advisory for the Indian Ocean (ABIO10): the
# disturbances ("invests") JTWC is watching before they become numbered storms.
JTWC_ABIO = "https://www.metoc.navy.mil/jtwc/products/abioweb.txt"
MMS = "http://metservice.intnet.mu"
MMS_PAGES = {"mauritius": f"{MMS}/cyclone-bulletin-english-mauritius.php",
             "rodrigues": f"{MMS}/cyclone-bulletin-english-rodrigues.php"}


def _get(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ------------------------------------------------------------ JTWC

def jtwc_links(rss_text):
    """Southern Hemisphere warning track files (.tcw) listed in the RSS feed."""
    links = set()
    for item in re.findall(r"<item>(.*?)</item>", rss_text, re.S):
        title = re.search(r"<title>(.*?)</title>", item, re.S)
        if not title or "Southern Hemisphere" not in title.group(1):
            continue
        links.update(re.findall(r"https?://[^\"'\s<>]+?/sh\d{4}\.tcw", html.unescape(item)))
    return sorted(links)


def _ll(lat, ns, lon, ew):
    la = int(lat) / 10.0 * (-1 if ns == "S" else 1)
    lo = int(lon) / 10.0 * (-1 if ew == "W" else 1)
    return round(la, 2), round(lo, 2)


def parse_tcw(text):
    """JTWC JMV 3.0 file -> track dict (winds are 1-minute means, knots)."""
    head = re.search(r"^(\d{10}) (\d\d[A-Z]) (\S+)\s+(\d{3})", text, re.M)
    if not head:
        raise ValueError("not a JTWC track file")
    adv = dt.datetime.strptime(head.group(1), "%Y%m%d%H").replace(tzinfo=UTC)
    num, name = head.group(2), head.group(3)
    full = re.search(r"\b" + num + r" \(([A-Z][A-Z0-9 -]*)\)", text)  # the header truncates names
    if full:
        name = full.group(1).strip()
    fcst = []
    for tau, la, ns, lo, ew, wk in re.findall(r"^T(\d{3}) +(\d{1,3})([NS]) +(\d{1,4})([EW]) +(\d{3})", text, re.M):
        lat, lon = _ll(la, ns, lo, ew)
        fcst.append({"t": adv + dt.timedelta(hours=int(tau)), "lat": lat, "lon": lon, "wind_kt": int(wk)})
    past = {}
    for yy, mdh, la, ns, lo, ew, wk in re.findall(r"^\d\d(\d\d)(\d{6}) +(\d{1,3})([NS]) *(\d{1,4})([EW]) +(\d+)", text, re.M):
        t = dt.datetime.strptime("20" + yy + mdh, "%Y%m%d%H").replace(tzinfo=UTC)
        lat, lon = _ll(la, ns, lo, ew)
        past[t] = {"t": t, "lat": lat, "lon": lon, "wind_kt": int(wk)}
    past = [past[t] for t in sorted(past)]
    t0 = [p for p in fcst if p["t"] == adv]
    fcst = [p for p in fcst if p["t"] > adv]
    if t0 and (not past or past[-1]["t"] < adv):
        past.append(t0[0])
    if not past:
        raise ValueError("JTWC file without positions")
    return {"number": num, "name": name.title(), "advisory": adv, "past": past, "fcst": fcst,
            "max_wind_kmh": round(past[-1]["wind_kt"] * KT)}


def fetch_jtwc():
    rss = _get(JTWC_RSS).decode("utf-8", "ignore")
    return [parse_tcw(_get(url).decode("utf-8", "ignore")) for url in jtwc_links(rss)]


def _pos(la, ns, lo, ew):
    return round(float(la) * (-1 if ns == "S" else 1), 1), round(float(lo) * (-1 if ew == "W" else 1), 1)


def parse_abio(text):
    """JTWC ABIO10 advisory -> South Indian Ocean disturbances still suspect for development."""
    t = re.sub(r"\s+", " ", text.upper())
    issued = None
    m = re.search(r"ABIO10 \w+ (\d{2})(\d{2})(\d{2})", t)
    v = re.search(r"/(\d{6})Z-\d{6}Z([A-Z]{3})(\d{4})", t)
    if m and v:
        try:
            issued = dt.datetime.strptime(f"{m.group(1)} {v.group(2)} {v.group(3)} {m.group(2)}{m.group(3)}",
                                          "%d %b %Y %H%M").replace(tzinfo=UTC)
        except ValueError:
            issued = None
    sio = re.search(r"SOUTH INDIAN OCEAN AREA.*?(?=\b3\. |NNNN|$)", t)
    if not sio:
        return []
    dist = re.search(r"TROPICAL DISTURBANCE SUMMARY:(.*?)(?=\bC\. SUBTROPICAL|$)", sio.group(0))
    if not dist:
        return []
    out = []
    for para in re.split(r"\(\d\)\s", dist.group(1))[1:]:
        inv = re.search(r"INVEST (\d{2}[A-Z])", para)
        if not inv or re.search(r"DISSIPATED|NO LONGER (CONSIDERED )?SUSPECT|HAS BEEN (UPGRADED|DESIGNATED)|"
                                r"SEE REF|REFER TO", para):
            continue
        pts = re.findall(r"(\d{1,2}\.\d)([NS]) (\d{1,3}\.\d)([EW])", para)
        now = re.search(r"NOW LOCATED NEAR (\d{1,2}\.\d)([NS]) (\d{1,3}\.\d)([EW])", para)
        if not pts:
            continue
        lat, lon = _pos(*(now.groups() if now else pts[0]))
        ch = re.findall(r"24 HOURS (?:IS|REMAINS?) (?:\w+ TO )?(LOW|MEDIUM|HIGH)", para) or \
            re.findall(r"\b(LOW|MEDIUM|HIGH)\b(?=[^A-Z]*$)", para.rstrip(". "))
        wind = re.search(r"WINDS ARE ESTIMATED (?:AT|BETWEEN|TO BE)? ?(\d+) ?(?:TO|-) ?(\d+) ?(?:KNOTS|KTS|KT)", para)
        mslp = re.search(r"NEAR (\d{3,4}) ?MB", para)
        out.append({"id": inv.group(1), "lat": lat, "lon": lon,
                    "chance": (ch[-1] if ch else "UNKNOWN").lower(),
                    "tcfa": "FORMATION ALERT" in para,
                    "wind_kmh": [round(int(wind.group(1)) * KT), round(int(wind.group(2)) * KT)] if wind else None,
                    "pressure_mb": int(mslp.group(1)) if mslp else None,
                    "issued": issued})
    return out


def fetch_jtwc_disturbances(save_to=None):
    raw = _get(JTWC_ABIO).decode("utf-8", "ignore")
    if save_to:  # keep the raw outlook for checking the parser against the real wording
        open(save_to, "w").write(raw)
    return parse_abio(raw)


# ------------------------------------------------------------ Meteo-France La Reunion (RSMC)
# The WMO text bulletins of RSMC La Reunion, as relayed by the US National Weather Service:
#   AWIO20 FMEE  daily tropical weather outlook: every disturbance it is watching,
#                long before GDACS or JTWC carry it
#   WTIO30 FMEE  warning for a system it has taken charge of, with the forecast track
MF_OUTLOOK = "https://tgftp.nws.noaa.gov/data/raw/aw/awio20.fmee..txt"
MF_WARNINGS = ["https://tgftp.nws.noaa.gov/data/raw/wt/wtio30.fmee..txt",   # first active system
               "https://tgftp.nws.noaa.gov/data/raw/wt/wtio31.fmee..txt"]   # second one, when two run
MF_STAGES = ("ZONE OF DISTURBED WEATHER", "TROPICAL DISTURBANCE", "TROPICAL DEPRESSION",
             "MODERATE TROPICAL STORM", "SEVERE TROPICAL STORM", "TROPICAL CYCLONE",
             "INTENSE TROPICAL CYCLONE", "VERY INTENSE TROPICAL CYCLONE", "SUBTROPICAL DEPRESSION",
             "POST-TROPICAL DEPRESSION", "FILLING UP", "REMNANT LOW")
_STAGE_RE = "|".join(sorted(MF_STAGES, key=len, reverse=True)).replace(" ", r"\s+")
_LL = r"(\d{1,2}[.,]\d)\s*([NS])\s*/\s*(\d{1,3}[.,]\d)\s*([EW])"


def _mf_ll(la, ns, lo, ew):
    return _pos(la.replace(",", "."), ns, lo.replace(",", "."), ew)


def _mf_header_time(t):
    """'AWIO20 FMEE 051200' + a date somewhere in the text -> datetime."""
    h = re.search(r"FMEE (\d{2})(\d{2})(\d{2})", t)
    d = re.search(r"(20\d\d)[/-](\d\d)[/-](\d\d)|(\d\d)/(\d\d)/(20\d\d)", t)
    if not h or not d:
        return None
    y, mo = (int(d.group(1)), int(d.group(2))) if d.group(1) else (int(d.group(6)), int(d.group(5)))
    try:
        return dt.datetime(y, mo, int(h.group(1)), int(h.group(2)), int(h.group(3)), tzinfo=UTC)
    except ValueError:
        return None


def _mf_time(s, ref):
    """'2026/11/05 AT 0900 UTC', '05/11/2026 AT 09 UTC', '2026/11/06 00 UTC' -> datetime."""
    m = re.search(r"(20\d\d)/(\d\d)/(\d\d)\D{0,6}?(\d\d)(\d\d)?\s*UTC", s) or \
        re.search(r"(\d\d)/(\d\d)/(20\d\d)\D{0,6}?(\d\d)(\d\d)?\s*UTC", s)
    if not m:
        return None
    a, b, c, hh, mm = m.groups()
    y, mo, d = (int(a), int(b), int(c)) if len(a) == 4 else (int(c), int(b), int(a))
    try:
        return dt.datetime(y, mo, d, int(hh), int(mm or 0), tzinfo=UTC)
    except ValueError:
        return ref


def parse_mf_outlook(text):
    """AWIO20 FMEE -> systems RSMC La Reunion is watching, with position, wind and stage."""
    t = re.sub(r"[ \t]+", " ", text.upper())
    issued = _mf_header_time(t)
    out = {}
    for m in re.finditer(r"(" + _STAGE_RE + r")\s+(\d{1,2})-(20\d{6})(?:\s*\(([A-Z' -]+)\))?", t):
        num = f"{int(m.group(2)):02d}-{m.group(3)}"
        if num in out:
            continue
        # this system's paragraph: up to the next numbered system or section
        rest = t[m.end():]
        nxt = re.search(r"(" + _STAGE_RE + r")\s+\d{1,2}-20\d{6}(?!\s*\(?" + re.escape(m.group(2)) + ")", rest)
        para = rest[:nxt.start()] if nxt and int(re.search(r"(\d{1,2})-20", rest[nxt.start():]).group(1)) != int(m.group(2)) \
            else rest[:4000]
        ll = re.search(_LL, para)
        if not ll:
            continue
        lat, lon = _mf_ll(*ll.groups())
        wind = re.search(r"(?:MAX(?:IMUM)?\s+(?:AVERAGE\s+)?WINDS?[^:\n]{0,40}[:=]?|WINDS? OF|WINDS? ESTIMATED (?:AT|TO)?)\s*(\d{2,3})\s*KT", para)
        pres = re.search(r"(\d{3,4})\s*HPA", para)
        mv = re.search(r"MOVEMENT\s*:?\s*([A-Z -]+?)\s*,?\s+(\d{1,2})\s*KT", para)
        chance = None
        for word, val in (("VERY LOW", "very low"), ("LOW", "low"), ("MODERATE", "moderate"), ("HIGH", "high"), ("NIL", "nil")):
            if re.search(r"(?:RISK|PROBABILITY|POTENTIAL|CHANCE)S?[^.]{0,120}\b(?:IS|ARE|REMAINS?|BECOMES?)\s+(?:NOW\s+)?" + word + r"\b", para):
                chance = val
                break
        out[num] = {"id": num, "stage": " ".join(m.group(1).split()).capitalize(),
                    "name": (m.group(4) or "").strip().title() or None,
                    "lat": lat, "lon": lon, "t": _mf_time(para, issued),
                    "wind_kmh": round(int(wind.group(1)) * KT) if wind else None,
                    "pressure_mb": int(pres.group(1)) if pres else None,
                    "moving": f"{mv.group(1).strip().lower()} at {round(int(mv.group(2)) * KT)} km/h" if mv else None,
                    "chance": chance, "issued": issued, "source": "Meteo-France La Reunion"}
    return list(out.values())


def parse_mf_warning(text):
    """WTIO30 FMEE -> a track dict like parse_tcw (winds are 10-minute means, knots)."""
    t = re.sub(r"[ \t]+", " ", text.upper())
    issued = _mf_header_time(t)
    m = re.search(r"(" + _STAGE_RE + r")\s+(\d{1,2})(?:\s*\(([A-Z' -]+)\))?", t)
    pos = re.search(r"POSITION[^:\n]*?(20\d\d/\d\d/\d\d[^:\n]*UTC)\s*:?[\s\S]{0,80}?" + _LL, t)
    if not m or not pos:
        raise ValueError("not an RSMC La Reunion warning")
    adv = _mf_time(pos.group(1), issued) or issued
    lat, lon = _mf_ll(*pos.groups()[1:])
    w = re.search(r"MAX(?:IMUM)? AVERAGE WIND SPEED[^:\n]*:\s*(\d{2,3})\s*KT", t)
    past = [{"t": adv, "lat": lat, "lon": lon, "wind_kt": int(w.group(1)) if w else 25}]
    fcst = []
    for fm in re.finditer(r"\b\d{1,3}H\s*:\s*(20\d\d/\d\d/\d\d\s+\d\d(?:\d\d)?\s*UTC)\s*:\s*" + _LL +
                          r"[^\n]*?(?:MAX WIND|VENT MAX)\s*=\s*(\d{2,3})\s*KT", t):
        ft = _mf_time(fm.group(1), None)
        if ft and ft > adv:
            la, lo = _mf_ll(*fm.groups()[1:5])
            fcst.append({"t": ft, "lat": la, "lon": lo, "wind_kt": int(fm.group(6))})
    last = re.search(r"LAST (?:WARNING|BULLETIN)|LAST WARNING", t)
    name = (m.group(3) or "").strip().title() or f"Disturbance {int(m.group(2)):02d}"
    return {"number": f"{int(m.group(2)):02d}", "name": name, "stage": " ".join(m.group(1).split()).capitalize(),
            "advisory": adv, "past": past, "fcst": fcst, "final": bool(last),
            "max_wind_kmh": round(past[-1]["wind_kt"] * KT)}


def fetch_mf(save_dir=None):
    """(outlook systems, warning track or None). Either part may be missing."""
    outlook = _get(MF_OUTLOOK).decode("utf-8", "ignore")
    if save_dir:
        open(f"{save_dir}/mf_outlook.txt", "w").write(outlook)
    tracks = []
    for i, url in enumerate(MF_WARNINGS):
        try:
            raw = _get(url).decode("utf-8", "ignore")
        except Exception:
            continue
        if save_dir:
            open(f"{save_dir}/mf_warning{'' if i == 0 else i}.txt", "w").write(raw)
        try:
            tracks.append(parse_mf_warning(raw))
        except ValueError:
            pass
    return parse_mf_outlook(outlook), tracks


# ------------------------------------------------------------ Mauritius Met Services

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}


def page_text(raw):
    t = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
    t = re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


def parse_mms(raw, island, now):
    """The cyclone warning in force on an MMS bulletin page, or None."""
    text = page_text(raw)
    start = text.find(f"Cyclone Warning Bulletin {island} (English Version)")
    if start < 0:
        return None
    body = text[start:start + 6000]
    end = re.search(r"\n(Weather\nWeather Map|Quick links)", body)
    body = body[:end.start()] if end else body
    m = re.search(r"cyclone warning class (IV|III|II|I)\b[^.\n]*?(?:is|remains) in force in " + island, body, re.I)
    issued = None
    im = re.search(r"issued at (\d{1,2})\s*[h:]?\s*(\d{2})(?: hours)? on \w+,? (\d{1,2}) (\w+) (\d{4})", body, re.I)
    if im:
        hh, mm, d, mon, y = im.groups()
        if mon.lower() in MONTHS:
            issued = dt.datetime(int(y), MONTHS[mon.lower()], int(d), int(hh), int(mm), tzinfo=MUT).astimezone(UTC)
    terminated = re.search(r"terminat|no (longer|more) (any )?cyclone warning|"
                           r"all cyclone warnings? (have been|has been|are) (lifted|removed)", body, re.I)
    if not m or terminated:
        return None
    # the page can keep an old bulletin; only trust a recent one
    if issued and (now - issued) > dt.timedelta(hours=18):
        return None
    sentences = []
    for line in [l.strip() for l in body.split("\n") if l.strip()][2:]:
        if re.search(r"cyclone warning class", line, re.I) or re.search(r"cyclone bulletin for", line, re.I):
            continue
        sentences.append(line)
        if len(" ".join(sentences)) > 300:
            break
    nxt = re.search(r"next bulletin will be issued at (?:around )?([^.\n]+)", body, re.I)
    cls = m.group(1).upper()
    return {"island": island, "class": cls, "class_num": ROMAN[cls],
            "issued": issued.strftime("%Y-%m-%dT%H:%MZ") if issued else None,
            "summary": " ".join(sentences),
            "next_bulletin": nxt.group(1).strip() if nxt else None,
            "url": MMS_PAGES[island.lower()]}


def fetch_mms(now):
    return {island: parse_mms(_get(url), island.title(), now) for island, url in MMS_PAGES.items()}
