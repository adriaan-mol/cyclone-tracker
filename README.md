# God's Eye Cyclone Tracker

Tropical cyclones in the South-West Indian Ocean, focused on Mauritius and Madagascar.
Live site: https://adriaan-mol.github.io/cyclone-tracker/

## What it shows
- Observed track, official forecast track and cone of uncertainty
- Forecast landfall (where and when, with "in X h")
- Closest approach to Mauritius, Antananarivo, Toamasina, Fort Dauphin and the Madagascar coast
- Whether a place falls inside the forecast gale, storm or hurricane-force wind zone
- A time slider: where the storm will be X hours from now
- Times in Mauritius time (Madagascar is one hour behind)

Demo with historical advisories: `?demo=gezani` (Feb 2026) or `?demo=belal` (Jan 2024).

## How it works
A GitHub Action (`.github/workflows/update.yml`) runs every 3 hours:
1. `scripts/build_storms.py` fetches current cyclones from GDACS, keeps those in the
   South-West Indian Ocean, and computes landfalls and closest approaches.
2. It writes `data/storms.json` (phone app), `data/brief.json` + `data/brief.md`
   (Daily TradeWinds) and `latest.png` (newspaper-style map, via `scripts/render_map.py`).
3. It commits when the data changed, and once a day regardless.

The phone app reads `data/storms.json` only, so it loads fast and works offline with the last data.

## Daily TradeWinds
- Summary: https://raw.githubusercontent.com/adriaan-mol/cyclone-tracker/main/data/brief.json
  (`closing_in` is true when a storm threatens Mauritius or Madagascar)
- Picture: https://raw.githubusercontent.com/adriaan-mol/cyclone-tracker/main/latest.png

## Install on Android
Open the site in Chrome, menu, "Add to Home screen" / "Install app".

## Run locally
```bash
pip install -r scripts/requirements.txt
python scripts/build_storms.py          # live
python scripts/build_storms.py --demo   # rebuild demo/
python3 -m http.server 8080
```

## Data
GDACS (gdacs.org); forecasts from RSMC La Reunion (Meteo-France) and JTWC.
Coastlines: Natural Earth. Font: IM FELL English (SIL Open Font License, `fonts/OFL.txt`).
Not an official warning service: follow Mauritius Meteorological Services and local authorities.
