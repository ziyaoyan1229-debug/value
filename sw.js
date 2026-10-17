// 價值台股 service worker：只處理背景推播（網站關著也會跳通知），不做離線快取
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {}; try { d = e.data.json(); } catch (x) { d = {body: e.data ? e.data.text() : ''}; }
  e.waitUntil(self.registration.showNotification(d.title || '價值台股', {body: d.body || '', tag: d.tag, icon: 'icon-192.png', badge: 'icon-192.png', data: {url: d.url || './'}}));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const u = new URL((e.notification.data && e.notification.data.url) || './', self.registration.scope).href;
  e.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(ws => { const w = ws.find(x => x.url.startsWith(self.registration.scope)); return w ? w.focus().then(c => c.navigate ? c.navigate(u) : c) : clients.openWindow(u); }));
});
