// God's Eye Cyclone Tracker — focused on Eastern Indian Ocean / Madagascar–Mauritius
const GDACS_URL = 'https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC&alertlevel=green;orange;red';

let map;
let radarCanvas;
let radarCtx;
let storms = [];
let markers = [];
let selectedStorm = null;
let sweepAngle = 0;

function init() {
  initMap();
  initRadar();
  loadStorms();
  setInterval(loadStorms, 5 * 60 * 1000);
  animateRadar();

  document.getElementById('close-detail').addEventListener('click', closeDetail);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}

function initMap() {
  // Default view: centered on Madagascar / Mauritius / Eastern Indian Ocean
  map = L.map('map', {
    zoomControl: false,
    attributionControl: true,
    minZoom: 3,
    maxZoom: 8,
    worldCopyJump: true
  }).setView([-19.5, 52], 4.5);

  // Free OSM tiles + CSS dark filter (no API key needed)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(map);

  L.control.zoom({ position: 'bottomright' }).addTo(map);
}

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
  drawRadar();
  sweepAngle = (sweepAngle + 1.2) % 360;
}

function drawRadar() {
  if (!radarCtx) return;
  const w = radarCanvas.width;
  const h = radarCanvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const maxR = Math.min(w, h) * 0.42;

  radarCtx.clearRect(0, 0, w, h);

  // Concentric rings
  radarCtx.strokeStyle = 'rgba(0, 229, 255, 0.25)';
  radarCtx.lineWidth = 1;
  for (let r = 40; r < maxR; r += 50) {
    radarCtx.beginPath();
    radarCtx.arc(cx, cy, r, 0, Math.PI * 2);
    radarCtx.stroke();
  }

  // Crosshairs
  radarCtx.strokeStyle = 'rgba(0, 229, 255, 0.15)';
  radarCtx.beginPath();
  radarCtx.moveTo(cx, cy - maxR);
  radarCtx.lineTo(cx, cy + maxR);
  radarCtx.moveTo(cx - maxR, cy);
  radarCtx.lineTo(cx + maxR, cy);
  radarCtx.stroke();

  // Sweep fan
  const rad = (sweepAngle - 90) * Math.PI / 180;
  const gradient = radarCtx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
  gradient.addColorStop(0, 'rgba(0, 229, 255, 0.35)');
  gradient.addColorStop(0.7, 'rgba(0, 229, 255, 0.08)');
  gradient.addColorStop(1, 'rgba(0, 229, 255, 0)');

  radarCtx.fillStyle = gradient;
  radarCtx.beginPath();
  radarCtx.moveTo(cx, cy);
  radarCtx.arc(cx, cy, maxR, rad - 0.35, rad, false);
  radarCtx.closePath();
  radarCtx.fill();

  // Sweep line
  radarCtx.strokeStyle = 'rgba(0, 255, 200, 0.6)';
  radarCtx.lineWidth = 2;
  radarCtx.beginPath();
  radarCtx.moveTo(cx, cy);
  radarCtx.lineTo(cx + Math.cos(rad) * maxR, cy + Math.sin(rad) * maxR);
  radarCtx.stroke();

  // Center dot
  radarCtx.fillStyle = '#00e5ff';
  radarCtx.beginPath();
  radarCtx.arc(cx, cy, 4, 0, Math.PI * 2);
  radarCtx.fill();
}

async function loadStorms() {
  const status = document.getElementById('status');
  status.textContent = 'ACQUIRING TARGETS...';

  try {
    const res = await fetch(GDACS_URL);
    if (!res.ok) throw new Error('GDACS feed unavailable');
    const data = await res.json();
    const features = data.features || [];

    // Focus on Eastern Indian Ocean / Madagascar–Mauritius region (roughly 0–40°S, 30–90°E)
    storms = features
      .filter(f => {
        const [lon, lat] = f.geometry?.coordinates || [];
        return lat <= 5 && lat >= -40 && lon >= 30 && lon <= 90;
      })
      .map(f => {
        const [lon, lat] = f.geometry.coordinates;
        const props = f.properties || {};
        const severity = props.severitydata || {};
        const windKmh = severity.severity || 0;
        const windKt = Math.round(windKmh / 1.852);

        return {
          id: props.eventid || Math.random().toString(36).slice(2),
          name: (props.eventname || props.name || 'Unnamed').replace(/-\d+$/, ''),
          classification: severity.severitytext?.includes('Hurricane') || severity.severitytext?.includes('Typhoon') ? 'HU' :
                          severity.severitytext?.includes('Tropical Storm') ? 'TS' : 'TC',
          intensity: windKt,
          pressure: '—',
          latitudeNumeric: lat,
          longitudeNumeric: lon,
          movementDir: null,
          movementSpeed: null,
          lastUpdate: props.datemodified || props.todate || new Date().toISOString(),
          alertlevel: props.alertlevel || 'Green',
          reportUrl: props.url?.report || 'https://www.gdacs.org/',
          severityText: severity.severitytext || ''
        };
      });

    renderStorms();
    status.textContent = storms.length
      ? `TRACKING ${storms.length} TARGET${storms.length > 1 ? 'S' : ''} (INDIAN OCEAN)`
      : 'NO ACTIVE CYCLONES IN REGION';
  } catch (err) {
    console.error(err);
    status.textContent = 'FEED ERROR — USING DEMO';
    storms = getDemoStorms();
    renderStorms();
  }
}

function getDemoStorms() {
  return [
    {
      id: 'demo1',
      name: 'Madagascar Demo',
      classification: 'TS',
      intensity: 55,
      pressure: '995',
      latitudeNumeric: -18.5,
      longitudeNumeric: 48.5,
      movementDir: 220,
      movementSpeed: 12,
      lastUpdate: new Date().toISOString(),
      alertlevel: 'Orange',
      reportUrl: 'https://www.gdacs.org/',
      severityText: 'Tropical Storm'
    },
    {
      id: 'demo2',
      name: 'Mauritius Demo',
      classification: 'HU',
      intensity: 75,
      pressure: '980',
      latitudeNumeric: -19.8,
      longitudeNumeric: 58.0,
      movementDir: 280,
      movementSpeed: 8,
      lastUpdate: new Date().toISOString(),
      alertlevel: 'Red',
      reportUrl: 'https://www.gdacs.org/',
      severityText: 'Hurricane'
    }
  ];
}

function renderStorms() {
  markers.forEach(m => map.removeLayer(m));
  markers = [];

  const list = document.getElementById('storm-list');
  list.innerHTML = '';
  document.getElementById('count').textContent = storms.length;

  storms.forEach((storm) => {
    const lat = storm.latitudeNumeric;
    const lon = storm.longitudeNumeric;
    if (lat == null || lon == null) return;

    const icon = L.divIcon({
      className: 'storm-marker',
      iconSize: [24, 24],
      iconAnchor: [12, 12]
    });

    const marker = L.marker([lat, lon], { icon })
      .addTo(map)
      .bindPopup(`<b>${storm.name}</b><br>${storm.severityText || storm.classification}<br>${storm.intensity} kt`);

    marker.on('click', () => selectStorm(storm));
    markers.push(marker);

    const latStr = `${Math.abs(lat).toFixed(1)}°${lat < 0 ? 'S' : 'N'}`;
    const lonStr = `${Math.abs(lon).toFixed(1)}°${lon < 0 ? 'W' : 'E'}`;

    const item = document.createElement('div');
    item.className = `storm-item ${(storm.classification || 'tc').toLowerCase()} alert-${(storm.alertlevel || 'green').toLowerCase()}`;
    item.innerHTML = `
      <div class="storm-name">${storm.name}</div>
      <div class="storm-meta">
        ${storm.severityText || storm.classification} • 
        ${storm.intensity} kt • 
        ${latStr} ${lonStr} • 
        ${storm.alertlevel || ''}
      </div>
    `;
    item.addEventListener('click', () => selectStorm(storm));
    list.appendChild(item);
  });

  if (storms.length === 0) {
    list.innerHTML = '<div style="opacity:0.6; text-align:center; padding:20px;">No active tropical cyclones in the Eastern Indian Ocean region.</div>';
  }
}

function selectStorm(storm) {
  selectedStorm = storm;
  const lat = storm.latitudeNumeric;
  const lon = storm.longitudeNumeric;

  map.flyTo([lat, lon], 5, { duration: 1.2 });

  // Highlight
  document.querySelectorAll('.storm-item').forEach(el => el.classList.remove('active'));
  const items = document.querySelectorAll('.storm-item');
  const idx = storms.indexOf(storm);
  if (items[idx]) items[idx].classList.add('active');

  showDetail(storm);
}

function showDetail(storm) {
  const panel = document.getElementById('detail-panel');
  const content = document.getElementById('detail-content');
  const latStr = `${Math.abs(storm.latitudeNumeric).toFixed(1)}°${storm.latitudeNumeric < 0 ? 'S' : 'N'}`;
  const lonStr = `${Math.abs(storm.longitudeNumeric).toFixed(1)}°${storm.longitudeNumeric < 0 ? 'W' : 'E'}`;

  content.innerHTML = `
    <h2>${storm.name}</h2>
    <div class="detail-row"><span>Type</span><span>${storm.severityText || storm.classification}</span></div>
    <div class="detail-row"><span>Alert Level</span><span>${storm.alertlevel || 'N/A'}</span></div>
    <div class="detail-row"><span>Max Wind</span><span>${storm.intensity} kt</span></div>
    <div class="detail-row"><span>Position</span><span>${latStr}, ${lonStr}</span></div>
    <div class="detail-row"><span>Last Update</span><span>${formatTime(storm.lastUpdate)}</span></div>
    <div style="margin-top:12px;">
      <a href="${storm.reportUrl}" target="_blank" style="color:#00e5ff; text-decoration:none; border:1px solid #00e5ff; padding:6px 12px; display:inline-block;">OPEN GDACS REPORT →</a>
    </div>
  `;

  panel.classList.remove('hidden');
}

function closeDetail() {
  document.getElementById('detail-panel').classList.add('hidden');
  selectedStorm = null;
  document.querySelectorAll('.storm-item').forEach(el => el.classList.remove('active'));
}

function directionToCompass(deg) {
  if (deg == null) return 'N/A';
  const dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return dirs[Math.round(deg / 22.5) % 16];
}

function formatTime(iso) {
  if (!iso) return 'N/A';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// Start
document.addEventListener('DOMContentLoaded', init);