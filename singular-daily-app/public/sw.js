// Service Worker for Keernel Push Notifications
// Location: /public/sw.js

const CACHE_NAME = 'keernel-v1';

// Install event - cache essential assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing Service Worker...');
  self.skipWaiting();
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Service Worker activated');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Push event - handle incoming notifications
self.addEventListener('push', (event) => {
  console.log('[SW] Push received:', event);

  let data = {
    title: 'Keernel',
    body: 'Votre podcast est prêt !',
    icon: '/logo-charcoal.svg',
    badge: '/logo-charcoal.svg',
    url: '/dashboard'
  };

  // Parse push data if available
  if (event.data) {
    try {
      const payload = event.data.json();
      data = { ...data, ...payload };
    } catch (e) {
      console.log('[SW] Push data not JSON:', event.data.text());
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/logo-charcoal.svg',
    badge: data.badge || '/logo-charcoal.svg',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/dashboard',
      dateOfArrival: Date.now()
    },
    actions: [
      { action: 'listen', title: '🎧 Écouter' },
      { action: 'later', title: 'Plus tard' }
    ],
    tag: 'keernel-podcast', // Prevents duplicate notifications
    renotify: true
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Notification click event - handle user interaction
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked:', event.action);
  
  event.notification.close();

  const urlToOpen = event.notification.data?.url || '/dashboard';

  // Handle action buttons
  if (event.action === 'later') {
    // User clicked "Plus tard" - just close
    return;
  }

  // Open or focus the app
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Check if app is already open
        for (const client of clientList) {
          if (client.url.includes('keernel') && 'focus' in client) {
            client.navigate(urlToOpen);
            return client.focus();
          }
        }
        // Open new window if not
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// Background sync (for offline actions)
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);
  
  if (event.tag === 'sync-subscription') {
    event.waitUntil(syncSubscription());
  }
});

async function syncSubscription() {
  // Retry failed subscription syncs when back online
  console.log('[SW] Syncing subscription...');
}
