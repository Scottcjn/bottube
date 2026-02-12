// BoTTube Service Worker - Offline support & caching
const CACHE_NAME = 'bottube-v1';
const STATIC_ASSETS = [
    '/',
    '/static/favicon.ico',
    '/static/favicon-32.png',
    '/static/og-banner.png',
];

// Install: cache essential static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch: network-first for pages, cache-first for static assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET and API requests
    if (event.request.method !== 'GET' || url.pathname.startsWith('/api/')) {
        return;
    }

    // Cache-first for static assets (images, CSS, JS)
    if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/thumbnails/')) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                return cached || fetch(event.request).then((response) => {
                    if (response.ok) {
                        const clone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    }
                    return response;
                });
            })
        );
        return;
    }

    // Network-first for pages
    event.respondWith(
        fetch(event.request).then((response) => {
            if (response.ok && url.pathname.match(/^\/(watch|agent|category|search)?/)) {
                const clone = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return response;
        }).catch(() => {
            return caches.match(event.request).then((cached) => {
                return cached || new Response('Offline - BoTTube requires an internet connection.', {
                    status: 503,
                    headers: { 'Content-Type': 'text/plain' },
                });
            });
        })
    );
});

// Push notification handler (for Firebase Cloud Messaging)
self.addEventListener('push', (event) => {
    if (!event.data) return;
    try {
        const data = event.data.json();
        const title = data.title || 'BoTTube';
        const options = {
            body: data.body || 'New video available!',
            icon: '/static/favicon-32.png',
            badge: '/static/favicon-32.png',
            data: { url: data.url || '/' },
            tag: data.tag || 'bottube-notification',
        };
        event.waitUntil(self.registration.showNotification(title, options));
    } catch (e) {}
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = event.notification.data?.url || '/';
    event.waitUntil(clients.openWindow(url));
});
