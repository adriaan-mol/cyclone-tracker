// God's Eye Cyclone Tracker: South-West Indian Ocean (Mauritius / Madagascar)
// Data: data/storms.json, refreshed every 3 h by a GitHub Action from GDACS.
// Demo: ?demo=gezani or ?demo=belal (historical advisories).

const params = new URLSearchParams(location.search);
const DEMO = params.get('demo');
const DATA_URL = DEMO ? `demo/${DEMO}/storms.json` : 'data/storms.json';
const MUT_OFFSET_MIN = 240; // Mauritius is UTC+4

const PLACES = [
  { id: 'mauritius', name: 'Mauritius', lat: -20.16, lon: 57.50 },
  { id: 'antananarivo', name: 'Antananarivo', lat: -18.88, lon: 47.51 },
  { id: 'fort-dauphin', name: 'Fort Dauphin', lat: -25.03, lon: 46.98 },
  { id: 'toamasina', name: 'Toamasina', lat: -18.15, lon: 49.40 },
];

let map, radarCanvas, radarCtx, layer, ghost;
let doc = null;
let sweepAngle = 0;
let selected = 0;

// ------------------------------------------------------------- time helpers

function nowRef() {
  // In demo mode "now" is the advisory time of the historical data.
  return doc && doc.demo ? new Date(doc.generated) : new Date();
}

function mutParts(d) {
  const m = new Date(d.getTime() + MUT_OFFSET_MIN * 60000);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const mons = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return { day: days[m.getUTCDay()], date: m.getUTCDate(), mon: mons[m.getUTCMonth()],
           hh: String(m.getUTCHours()).padStart(2, '0'), mm: String(m.getUTCMinutes()).padStart(2, '0') };
}

function fmtShort(d) {
  d = new Date(Math.round(d.getTime() / 1800000) * 1800000);
  const p = mutParts(d);
  return `${p.day} ${p.hh}:${p.mm}`;
}

function fmtTime(d, approx) {
  if (approx) d = new Date(Math.round(d.getTime() / 1800000) * 1800000); // forecasts: nearest 30 min
  const p = mutParts(d);
  return `${p.day} ${p.date} ${p.mon} ${approx ? '~' : ''}${p.hh}:${p.mm}`;
}

function relHours(d) {
  const h = Math.round((d - nowRef()) / 3600000);
  if (h === 0) return 'now';
  return h > 0 ? `in ${h} h` : `${-h} h ago`;
}

function km(n) { return `${Math.round(n).toLocaleString('en')} km`; }

function haversine(lat1, lon1, lat2, lon2) {
  const r = 6371, rad = Math.PI / 180;
  const dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ------------------------------------------------------------- init

function init() {
  initMap();
  initRadar();
  animateRadar();
  loadStorms();
  setInterval(loadStorms, 10 * 60 * 1000);
  setInterval(() => { if (doc) { renderMap(false); renderPanel(); } }, 60 * 1000); // keep "in X h" current
  document.getElementById('scrub').addEventListener('input', onScrub);

  if (DEMO) {
    const b = document.getElementById('demo-banner');
    b.classList.remove('hidden');
    b.innerHTML = `DEMO: HISTORICAL ADVISORY // <a href="./">BACK TO LIVE</a>`;
  }
  if ('serviceWorker' in navigator) {
    // When a new version takes over, reload once so the new code runs.
    let reloaded = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!reloaded) { reloaded = true; location.reload(); }
    });
    navigator.serviceWorker.register('sw.js', { updateViaCache: 'none' })
      .then(r => r.update()).catch(() => {});
  }
}

function initMap() {
  map = L.map('map', { zoomControl: false, attributionControl: true, minZoom: 3, maxZoom: 9, worldCopyJump: true })
    .setView([-19.5, 52], 5);
  // Esri dark grey basemap: free, no API key. Labels come from a second layer.
  const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
  L.tileLayer(esri + 'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri', maxZoom: 16,
  }).addTo(map);
  L.tileLayer(esri + 'World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16, opacity: 0.8 }).addTo(map);
  layer = L.layerGroup().addTo(map);
  map.on('zoomend', () => doc && drawForecastLabels());

  PLACES.forEach(p => {
    L.circleMarker([p.lat, p.lon], { radius: 4, color: '#ffffff', weight: 1, fillColor: '#00e5ff', fillOpacity: 0.9 })
      .addTo(map)
      .bindTooltip(p.name, { permanent: true, direction: 'right', className: 'place-label', offset: [6, 0] });
  });
}

// ------------------------------------------------------------- radar look

function initRadar() {
  radarCanvas = document.getElementById('radar-overlay');
  radarCtx = radarCanvas.getContext('2d');
  resizeRadar();
  window.addEventListener('resize', resizeRadar);
}

function resizeRadar() {
  radarCanvas.width = window.innerWidth;
  radarCanvas.height = window.innerHeight;
}

function animateRadar() {
  requestAnimationFrame(animateRadar);
  if (document.hidden) return;
  sweepAngle = (sweepAngle + 0.8) % 360;
  const w = radarCanvas.width, h = radarCanvas.height;
  const cx = w / 2, cy = h * 0.4, maxR = Math.min(w, h) * 0.42;
  const c = radarCtx;
  c.clearRect(0, 0, w, h);
  c.strokeStyle = 'rgba(0,229,255,0.10)';
  c.lineWidth = 1;
  for (let r = 60; r < maxR; r += 60) { c.beginPath(); c.arc(cx, cy, r, 0, Math.PI * 2); c.stroke(); }
  const rad = (sweepAngle - 90) * Math.PI / 180;
  const g = c.createRadialGradient(cx, cy, 0, cx, cy, maxR);
  g.addColorStop(0, 'rgba(0,229,255,0.16)');
  g.addColorStop(1, 'rgba(0,229,255,0)');
  c.fillStyle = g;
  c.beginPath(); c.moveTo(cx, cy); c.arc(cx, cy, maxR, rad - 0.35, rad); c.closePath(); c.fill();
}

// ------------------------------------------------------------- data

async function loadStorms() {
  const status = document.getElementById('status');
  try {
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    doc = await res.json();
    const n = doc.storms.length;
    const w = (doc.warnings || {}).mauritius;
    status.textContent = w ? `CLASS ${w.class} WARNING // MAURITIUS`
      : n ? `TRACKING ${n} TARGET${n > 1 ? 'S' : ''}` : 'NO ACTIVE CYCLONES';
    status.classList.toggle('alert', !!w || doc.storms.some(s => s.closing_in));
    if (selected >= n) selected = 0;
    renderMap(true);
    renderPanel();
  } catch (err) {
    console.error(err);
    status.textContent = doc ? 'OFFLINE // SHOWING LAST DATA' : 'FEED ERROR // NO DATA';
    if (!doc) {
      document.getElementById('storm-list').innerHTML =
        '<div class="empty">Could not load cyclone data. Check your connection and reopen the app.</div>';
    }
  }
}

// ------------------------------------------------------------- map drawing

function lonlat(coords) { return coords.map(c => [c[1], c[0]]); }

function addGeoPolygon(geom, style) {
  if (!geom) return;
  const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
  polys.forEach(rings => L.polygon(rings.map(lonlat), style).addTo(layer));
}

function renderMap(fit) {
  layer.clearLayers();
  ghost = null;
  const bounds = [];
  doc.storms.forEach((s, i) => {
    const sel = i === selected;
    addGeoPolygon(s.cone, { color: '#00e5ff', weight: 1, dashArray: '4 4', fillColor: '#00e5ff', fillOpacity: sel ? 0.10 : 0.05, interactive: false });
    addGeoPolygon(s.wind_zones && s.wind_zones.hurricane, { color: '#ff3366', weight: 1, dashArray: '2 4', fillColor: '#ff3366', fillOpacity: 0.08, interactive: false });

    const past = s.past.map(p => [p.lat, p.lon]);
    L.polyline(past, { color: '#00e5ff', weight: 3, opacity: 0.9 }).addTo(layer);
    s.past.slice(0, -1).forEach(p => L.circleMarker([p.lat, p.lon], {
      radius: 3, color: '#00e5ff', weight: 1, fillColor: p.cat === 'TS' ? '#00e5ff' : '#000', fillOpacity: 1,
    }).addTo(layer).bindTooltip(`${fmtTime(new Date(p.t))} (observed)`));

    (s.forecast_segments || []).forEach(seg =>
      L.polyline(lonlat(seg), { color: '#ffaa00', weight: 2.5, dashArray: '8 6' }).addTo(layer));

    if (s.jtwc && s.jtwc.forecast.length) {
      const jt = [[s.position.lat, s.position.lon], ...s.jtwc.forecast.map(p => [p.lat, p.lon])];
      L.polyline(jt, { color: '#c58cff', weight: 2, dashArray: '2 6', opacity: 0.9 }).addTo(layer);
      s.jtwc.forecast.forEach(p => {
        const t = new Date(p.t);
        L.circleMarker([p.lat, p.lon], { radius: 3, color: '#c58cff', weight: 1.5, fillColor: '#000', fillOpacity: 1 })
          .addTo(layer).bindTooltip(`JTWC · ${fmtTime(t, true)} · ${relHours(t)} · ${p.wind_kmh} km/h`);
        bounds.push([p.lat, p.lon]);
      });
    }

    s.forecast.forEach(p => {
      const t = new Date(p.t);
      L.circleMarker([p.lat, p.lon], { radius: 4, color: '#ffaa00', weight: 2, fillColor: '#000', fillOpacity: 1 })
        .addTo(layer).bindTooltip(`${fmtTime(t, true)} · ${relHours(t)}`);
      bounds.push([p.lat, p.lon]);
    });

    const pos = s.position;
    const icon = L.divIcon({ className: '', html: `<div class="storm-marker ${s.closing_in ? 'hot' : ''}"></div>`, iconSize: [26, 26], iconAnchor: [13, 13] });
    L.marker([pos.lat, pos.lon], { icon }).addTo(layer)
      .bindTooltip(s.name.toUpperCase(), { permanent: true, direction: 'top', className: 'storm-label', offset: [0, -12] })
      .on('click', () => select(i));
    bounds.push([pos.lat, pos.lon]);
    s.past.slice(-8).forEach(p => bounds.push([p.lat, p.lon]));

    s.landfalls.forEach(lf => {
      const t = new Date(lf.time);
      const star = L.divIcon({ className: '', html: '<div class="landfall-star">★</div>', iconSize: [22, 22], iconAnchor: [11, 11] });
      L.marker([lf.lat, lf.lon], { icon: star }).addTo(layer)
        .bindTooltip(`LANDFALL ${fmtShort(t)} · ${relHours(t).replace('in ', '+')}`,
          { permanent: sel, direction: 'bottom', className: 'lf-label', offset: [0, 10] });
      bounds.push([lf.lat, lf.lon]);
    });
  });

  if (fit) fitMap(bounds);
  drawForecastLabels();
}

function fitMap(bounds) {
  {
    if (bounds.length) {
      bounds.push([-20.16, 57.5]);
      map.fitBounds(bounds, { paddingTopLeft: [20, 70], paddingBottomRight: [20, window.innerHeight * 0.42] });
    } else {
      map.setView([-19.5, 52], 5);
    }
  }
}

// Permanent time labels on forecast points of the selected storm, skipping any
// that would overlap at the current zoom.
let labelLayer = null;
function drawForecastLabels() {
  if (labelLayer) map.removeLayer(labelLayer);
  labelLayer = L.layerGroup().addTo(map);
  if (!doc || !doc.storms.length) return;
  const s = doc.storms[selected];
  const taken = [map.latLngToContainerPoint([s.position.lat, s.position.lon])];
  s.forecast.forEach(p => {
    const pt = map.latLngToContainerPoint([p.lat, p.lon]);
    if (taken.some(q => Math.abs(q.x - pt.x) < 95 && Math.abs(q.y - pt.y) < 18)) return;
    taken.push(pt);
    const t = new Date(p.t);
    L.tooltip({ permanent: true, direction: 'right', className: 'fc-label', offset: [6, 0], interactive: false })
      .setLatLng([p.lat, p.lon]).setContent(`${fmtShort(t)} · ${relHours(t).replace('in ', '+')}`).addTo(labelLayer);
  });
}

// ------------------------------------------------------------- panel

function select(i) {
  selected = i;
  renderMap(false);
  renderPanel();
  const s = doc.storms[i];
  map.flyTo([s.position.lat, s.position.lon], Math.max(map.getZoom(), 5), { duration: 0.8 });
}

function placeLine(p) {
  const t = new Date(p.closest_time);
  if (p.moving_away) return `<b>${esc(p.name)}</b> ${km(p.now_km)} now, moving away`;
  return `<b>${esc(p.name)}</b> closest ${km(p.closest_km)} · ${fmtTime(t, true)} · <em>${relHours(t)}</em>`;
}

function renderWarnings() {
  const box = document.getElementById('warnings');
  const ws = ['mauritius', 'rodrigues'].map(k => (doc.warnings || {})[k]).filter(Boolean);
  box.innerHTML = ws.map(w => `
    <a class="warning" href="${esc(w.url)}" target="_blank" rel="noopener">
      <div class="w-title">CYCLONE WARNING CLASS ${esc(w.class)} // ${esc(w.island.toUpperCase())}</div>
      <div class="w-meta">Mauritius Meteorological Services${w.issued ? ` · bulletin ${fmtTime(new Date(w.issued))}` : ''}${w.next_bulletin ? ` · next ${esc(w.next_bulletin)}` : ''}</div>
      <div class="w-text">${esc(w.summary)}</div>
    </a>`).join('');
  const st = doc.sources || {};
  const names = { gdacs: 'GDACS / LA RÉUNION', jtwc: 'JTWC', mms: 'MAURITIUS MET' };
  document.getElementById('source-status').innerHTML = Object.keys(names).filter(k => st[k])
    .map(k => `<span class="${st[k] === 'ok' ? 'ok' : 'bad'}">${names[k]} ${st[k] === 'ok' ? '✓' : '✕'}</span>`).join('');
}

function renderPanel() {
  renderWarnings();
  const list = document.getElementById('storm-list');
  document.getElementById('count').textContent = doc.storms.length;
  document.getElementById('checked').textContent =
    doc.demo ? 'DEMO' : `CHECKED ${fmtTime(new Date(doc.generated))}`;

  if (!doc.storms.length) {
    list.innerHTML = `
      <div class="empty">No active tropical cyclones in the South-West Indian Ocean.
        <div class="demo-links">See how it looks:
          <a href="?demo=gezani">GEZANI (Feb 2026)</a>
          <a href="?demo=belal">BELAL (Jan 2024)</a>
        </div>
      </div>`;
    document.getElementById('scrubber').classList.add('hidden');
    return;
  }

  list.innerHTML = doc.storms.map((s, i) => {
    const mv = s.motion ? ` · moving ${s.motion.toward} ${s.motion.speed_kmh} km/h` : '';
    const lfs = s.landfalls.map(lf => {
      const t = new Date(lf.time);
      return `<div class="row warn">★ LANDFALL <b>${esc(lf.country)}</b> near ${esc(lf.near)} · ${fmtTime(t, true)} · <em>${relHours(t)}</em></div>`;
    }).join('');
    const md = s.madagascar;
    const mdAway = new Date(md.closest_time) <= new Date(s.position.t);
    const mdLine = s.landfalls.some(l => l.country === 'Madagascar') || md.closest_km === 0 ? '' : mdAway
      ? `<div class="row"><b>Madagascar coast</b> ${km(md.closest_km)} now, moving away</div>`
      : `<div class="row"><b>Madagascar coast</b> closest ${km(md.closest_km)} · ${fmtTime(new Date(md.closest_time), true)} · <em>${relHours(new Date(md.closest_time))}</em></div>`;
    const zones = s.places.filter(p => p.wind_zone)
      .map(p => `<div class="row warn">⚠ ${esc(p.name)} inside forecast zone for ${esc(p.wind_zone)}</div>`).join('');
    const places = s.places.map(p => `<div class="row">${placeLine(p)}</div>`).join('');
    let jt = '';
    if (s.jtwc) {
      const bits = s.jtwc.landfalls.map(lf => `landfall ${esc(lf.country)} near ${esc(lf.near)} · ${fmtTime(new Date(lf.time), true)} · <em>${relHours(new Date(lf.time))}</em>`);
      const m = s.jtwc.mauritius;
      bits.push(m.moving_away ? `Mauritius ${km(m.now_km)}, moving away`
        : `Mauritius closest ${km(m.closest_km)} · ${fmtTime(new Date(m.closest_time), true)} · <em>${relHours(new Date(m.closest_time))}</em>`);
      jt = `<div class="row jtwc"><b>JTWC forecast</b> (max wind ${s.jtwc.max_wind_kmh} km/h, 1-min): ${bits.join(' · ')}</div>`;
    }
    const src = s.source === 'JTWC' ? 'JTWC only (not yet in GDACS / La Réunion feed)' : 'La Réunion forecast via GDACS';
    return `
      <div class="storm-item ${i === selected ? 'active' : ''} alert-${esc((s.alert || 'green').toLowerCase())}" data-i="${i}">
        <div class="storm-name">${esc(s.name.toUpperCase())} ${s.closing_in ? '<span class="tag">CLOSING IN</span>' : ''}</div>
        <div class="storm-meta">${esc(s.status)} · max wind ${s.max_wind_kmh} km/h${mv}${s.over_land ? ` · over ${esc(s.over_land)}` : ''}</div>
        <div class="storm-meta">Position ${fmtTime(new Date(s.position.t))} (${relHours(new Date(s.position.t))}) · advisory ${fmtTime(new Date(s.advisory))}</div>
        ${lfs}${zones}${places}${mdLine}${jt}
        <div class="storm-meta src">Source: ${src}</div>
        <a class="report" href="${esc(s.report_url)}" target="_blank" rel="noopener">${s.source === 'JTWC' ? 'JTWC' : 'GDACS REPORT'} →</a>
      </div>`;
  }).join('');
  list.querySelectorAll('.storm-item').forEach(el =>
    el.addEventListener('click', e => { if (e.target.tagName !== 'A') select(+el.dataset.i); }));

  setupScrubber();
}

// ------------------------------------------------------------- time scrubber

function track(s) {
  return [s.position, ...s.forecast].map(p => ({ lat: p.lat, lon: p.lon, t: new Date(p.t) }));
}

function setupScrubber() {
  const s = doc.storms[selected];
  const box = document.getElementById('scrubber');
  const tr = track(s);
  const start = nowRef();
  const end = tr[tr.length - 1].t;
  const maxH = Math.floor((end - start) / 3600000);
  if (!s.forecast.length || maxH < 1) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  const r = document.getElementById('scrub');
  r.max = maxH;
  if (+r.value > maxH) r.value = 0;
  onScrub();
}

function positionAt(tr, t) {
  if (t <= tr[0].t) return tr[0];
  for (let i = 1; i < tr.length; i++) {
    if (t <= tr[i].t) {
      const a = tr[i - 1], b = tr[i];
      const f = (t - a.t) / (b.t - a.t);
      return { lat: a.lat + (b.lat - a.lat) * f, lon: a.lon + (b.lon - a.lon) * f, t };
    }
  }
  return tr[tr.length - 1];
}

function onScrub() {
  if (!doc || !doc.storms.length) return;
  const s = doc.storms[selected];
  const h = +document.getElementById('scrub').value;
  const t = new Date(nowRef().getTime() + h * 3600000);
  const p = positionAt(track(s), t);
  document.getElementById('scrub-time').textContent = h === 0 ? 'NOW' : `+${h} H · ${fmtTime(t, true)}`;
  const dMu = haversine(p.lat, p.lon, -20.16, 57.5);
  const dTn = haversine(p.lat, p.lon, -18.88, 47.51);
  document.getElementById('scrub-info').innerHTML =
    `${esc(s.name)} ${Math.abs(p.lat).toFixed(1)}°S ${p.lon.toFixed(1)}°E · Mauritius ${km(dMu)} · Tana ${km(dTn)}`;
  if (ghost) layer.removeLayer(ghost);
  if (h > 0) {
    ghost = L.circleMarker([p.lat, p.lon], { radius: 9, color: '#ffaa00', weight: 2, fillColor: '#ffaa00', fillOpacity: 0.35 }).addTo(layer);
  } else {
    ghost = null;
  }
}

document.addEventListener('DOMContentLoaded', init);
