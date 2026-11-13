/* LUZ EMS admin service worker: shows phone notifications and opens the right page when tapped.
   It deliberately does not cache the app, so updates always load fresh. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let msg = {};
  try { msg = event.data ? event.data.json() : {}; } catch (e) { msg = { body: event.data ? event.data.text() : '' }; }
  const title = msg.title || 'LUZ EMS';
  // iOS requires every push to show a notification, so this always does.
  event.waitUntil(self.registration.showNotification(title, {
    body: msg.body || '',
    tag: msg.tag || undefined,
    renotify: !!msg.tag,
    icon: '/icons/icon-192.png?v=2',
    badge: '/icons/badge-96.png',
    data: { url: msg.url || '/admin' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/admin';
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const admin = wins.find(w => new URL(w.url).pathname.startsWith('/admin'));
    if (admin) {
      admin.postMessage({ type: 'navigate', url });
      try { return await admin.focus(); } catch (e) { /* fall through */ }
    }
    return self.clients.openWindow(url);
  })());
});
