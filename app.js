// God's Eye Cyclone Tracker
const NHC_URL = 'https://www.nhc.noaa.gov/CurrentStorms.json';

let map;
let radarCanvas;
let radarCtx;
let storms = [];
let markers = [];
let selectedStorm = null;
let sweepAngle = 0;

const classificationNames = {
  HU: 'Hurricane',
  TS: 'Tropical Storm',
  TD: 'Tropical Depression',
  PTC: 'Post-Tropical Cyclone',
  STS: 'Subtropical Storm',
  STD: 'Subtropical Depression',
  PC: 'Potential Tropical Cyclone'
};

function init() {
  initMap();
  initRadar();
  loadStorms();
  setInterval(loadStorms, 5 * 60 * 1000); // refresh every 5 min
  animateRadar();

  document.getElementById('close-detail').addEventListener('click', closeDetail);

  // Register service worker if supported
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}

function initMap() {
  map = L.map('map', {
    zoomControl: false,
    attributionControl: true,
    minZoom: 2,
    maxZoom: 8,
    worldCopyJump: true
  }).setView([20, -60], 3);

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(map);

  // Custom zoom controls style later if needed
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
    const res = await fetch(NHC_URL, {
      headers: { 'User-Agent': 'GodsEyeCycloneTracker/1.0 (educational, personal use)' }
    });
    if (!res.ok) throw new Error('NHC feed unavailable');
    const data = await res.json();
    storms = data.activeStorms || [];
    renderStorms();
    status.textContent = storms.length ? `TRACKING ${storms.length} TARGET${storms.length > 1 ? 'S' : ''}` : 'NO ACTIVE CYCLONES';
  } catch (err) {
    console.error(err);
    status.textContent = 'FEED ERROR — RETRYING';
    // Fallback demo data if offline or CORS issue in some environments
    if (storms.length === 0) {
      storms = getDemoStorms();
      renderStorms();
      status.textContent = 'DEMO MODE (live feed offline)';
    }
  }
}

function getDemoStorms() {
  return [
    {
      id: 'al092026',
      name: 'Isaias',
      classification: 'PTC',
      intensity: '20',
      pressure: '1010',
      latitudeNumeric: 35.4,
      longitudeNumeric: -85.9,
      movementDir: 55,
      movementSpeed: 23,
      lastUpdate: new Date().toISOString(),
      publicAdvisory: { url: 'https://www.nhc.noaa.gov/' }
    },
    {
      id: 'ep182026',
      name: 'Rachel',
      classification: 'TS',
      intensity: '45',
      pressure: '1000',
      latitudeNumeric: 18.5,
      longitudeNumeric: -105.2,
      movementDir: 300,
      movementSpeed: 8,
      lastUpdate: new Date().toISOString(),
      publicAdvisory: { url: 'https://www.nhc.noaa.gov/' }
    }
  ];
}

function renderStorms() {
  // Clear old markers
  markers.forEach(m => map.removeLayer(m));
  markers = [];

  const list = document.getElementById('storm-list');
  list.innerHTML = '';
  document.getElementById('count').textContent = storms.length;

  storms.forEach((storm, idx) => {
    const lat = storm.latitudeNumeric;
    const lon = storm.longitudeNumeric;
    if (lat == null || lon == null) return;

    // Marker
    const icon = L.divIcon({
      className: 'storm-marker',
      iconSize: [24, 24],
      iconAnchor: [12, 12]
    });

    const marker = L.marker([lat, lon], { icon })
      .addTo(map)
      .bindPopup(`<b>${storm.name}</b><br>${classificationNames[storm.classification] || storm.classification}<br>${storm.intensity} kt`);

    marker.on('click', () => selectStorm(storm));
    markers.push(marker);

    // List item
    const item = document.createElement('div');
    item.className = `storm-item ${storm.classification.toLowerCase()}`;
    item.innerHTML = `
      <div class="storm-name">${storm.name}</div>
      <div class="storm-meta">
        ${classificationNames[storm.classification] || storm.classification} • 
        ${storm.intensity} kt • 
        ${lat.toFixed(1)}°N ${Math.abs(lon).toFixed(1)}°${lon < 0 ? 'W' : 'E'}
      </div>
    `;
    item.addEventListener('click', () => selectStorm(storm));
    list.appendChild(item);
  });

  if (storms.length === 0) {
    list.innerHTML = '<div style="opacity:0.6; text-align:center; padding:20px;">No active tropical cyclones in NHC basins.</div>';
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
  const cls = classificationNames[storm.classification] || storm.classification;
  const windMph = Math.round(storm.intensity * 1.15078);
  const dir = directionToCompass(storm.movementDir);

  content.innerHTML = `
    <h2>${storm.name}</h2>
    <div class="detail-row"><span>Classification</span><span>${cls}</span></div>
    <div class="detail-row"><span>Max Wind</span><span>${storm.intensity} kt / ${windMph} mph</span></div>
    <div class="detail-row"><span>Pressure</span><span>${storm.pressure} mb</span></div>
    <div class="detail-row"><span>Position</span><span>${storm.latitudeNumeric.toFixed(1)}°N, ${Math.abs(storm.longitudeNumeric).toFixed(1)}°${storm.longitudeNumeric < 0 ? 'W' : 'E'}</span></div>
    <div class="detail-row"><span>Movement</span><span>${dir} at ${storm.movementSpeed} mph</span></div>
    <div class="detail-row"><span>Last Update</span><span>${formatTime(storm.lastUpdate)}</span></div>
    ${storm.publicAdvisory?.url ? `<div style="margin-top:12px;"><a href="${storm.publicAdvisory.url}" target="_blank" style="color:#00e5ff; text-decoration:none; border:1px solid #00e5ff; padding:6px 12px; display:inline-block;">OPEN NHC ADVISORY →</a></div>` : ''}
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