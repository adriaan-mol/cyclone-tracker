# God's Eye Cyclone Tracker

A holographic, Fast & Furious "God's Eye" inspired real-time tropical cyclone tracking PWA for Android (and any modern browser).

## Features
- Dark neon HUD with rotating radar sweep and concentric rings
- Live data from NOAA National Hurricane Center (`CurrentStorms.json`)
- Active storms plotted on a dark Carto basemap
- Tap any storm for detailed vitals (wind, pressure, movement, advisory link)
- Installable as a Progressive Web App on Android
- Works offline with cached UI (live data requires network)

## How to use on Android
1. Host these files on any static host (GitHub Pages, Netlify, Vercel, or even a simple local server).
2. Open the site in Chrome on your phone.
3. Tap the menu → "Add to Home screen" / "Install app".
4. Launch from home screen for the full immersive experience.

### Quick local test
```bash
cd cyclone-gods-eye
python3 -m http.server 8080
```
Then open http://localhost:8080 on your phone (same network) or desktop.

## Data source
- Primary: https://www.nhc.noaa.gov/CurrentStorms.json (Atlantic, Eastern & Central Pacific)
- Covers current positions, classification, intensity, pressure, movement.
- Links out to official NHC advisories and graphics.
- Note: NHC covers US basins only. Western Pacific typhoons and Indian Ocean cyclones are tracked by JTWC / other centers (not in this feed).

## Tech
Pure HTML/CSS/JS + Leaflet. No build step. Fully client-side.

Enjoy the vibe. Stay safe.