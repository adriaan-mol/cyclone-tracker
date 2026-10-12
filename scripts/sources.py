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
