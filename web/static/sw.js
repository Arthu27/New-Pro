// Aether Panel Service Worker (Light Edition)
const CACHE_NAME = 'Aether-light-v5';
const STATIC_ASSETS = [
  '/static/style.css',
  '/static/app.js',
  '/static/pickers.js',
  '/static/api-guard.js',
  '/static/websocket-client.js',
  '/static/vendor/fontawesome/css/all.min.css',
  '/static/vendor/fonts/fonts.css',
  '/static/brand/emblem-dragon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.url.includes('/api/') || event.request.method !== 'GET') {
    return;
  }
  if (event.request.url.includes('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});
