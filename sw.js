// Network first, cache as fallback: updates reach the phone on the next open,
// and the last good version still works offline.
const CACHE = 'gods-eye-v6';
const SHELL = ['./', './index.html', './style.css', './app.js', './manifest.json', './icon-192.png', './data/storms.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameOrigin = url.origin === location.origin;
  e.respondWith(
    fetch(sameOrigin ? new Request(req, { cache: 'no-cache' }) : req).then(res => {
      if (res.ok && (sameOrigin || url.hostname.includes('unpkg.com'))) {
        const copy = res.clone();
        const key = sameOrigin ? url.pathname : req; // ignore ?t= cache-busters
        caches.open(CACHE).then(c => c.put(key, copy));
      }
      return res;
    }).catch(() =>
      caches.match(sameOrigin ? url.pathname : req).then(r => r || caches.match(req, { ignoreSearch: true }))
        .then(r => r || caches.match('./index.html')))
  );
});
