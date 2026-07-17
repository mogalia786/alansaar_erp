const CACHE_NAME = 'al-ansaar-v1';
const STATIC_CACHE = 'al-ansaar-static-v1';

const PRECACHE_URLS = [
    '/',
    '/static/manifest.json',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(key => key !== CACHE_NAME && key !== STATIC_CACHE)
                    .map(key => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    if (event.request.method !== 'GET') return;

    if (url.pathname.startsWith('/admin/') || url.pathname.startsWith('/portal/') || url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return new Response('Offline - please check your connection', {
                    status: 503,
                    headers: { 'Content-Type': 'text/plain' }
                });
            })
        );
        return;
    }

    event.respondWith(
        caches.match(event.request).then(cached => {
            const fetched = fetch(event.request).then(response => {
                if (response && response.status === 200) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            }).catch(() => cached);

            return cached || fetched;
        })
    );
});
