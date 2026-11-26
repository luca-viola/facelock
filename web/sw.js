// Shows Facelock's notifications, and opens the page to approve when one is tapped.

// Version 7.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

function encodeRequest(request) {
    const bytes = new TextEncoder().encode(JSON.stringify(request));
    let text = '';
    for (const byte of bytes)
        text += String.fromCharCode(byte);
    return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// The request waiting for an answer. Saved here, since iOS doesn't pass the address or a
// message to the page when a notification opens it.
const PENDING = 'facelock-pending';
const PENDING_URL = 'pending-request';

// A short record of what this worker did, shown at the bottom of the page for troubleshooting.
async function log(text) {
    try {
        const cache = await caches.open(PENDING);
        const old = await cache.match('log');
        const lines = old ? await old.json() : [];
        lines.push(`${new Date().toLocaleTimeString()} worker: ${text}`);
        await cache.put('log', new Response(JSON.stringify(lines.slice(-12))));
    } catch {
        // Only for troubleshooting.
    }
}

async function savePending(request) {
    const cache = await caches.open(PENDING);
    await cache.put(PENDING_URL, new Response(JSON.stringify(request), {
        headers: {'Content-Type': 'application/json'},
    }));
}

self.addEventListener('push', event => {
    let data = {};
    try {
        data = event.data.json();
    } catch {
        // Every push must still show a notification, or the browser may stop delivering them.
    }
    let title = 'Facelock';
    const options = {icon: 'icon-192.png', badge: 'icon-192.png', data};
    if (data.type === 'unlock') {
        title = `Unlock ${data.name}?`;
        options.body = Array.isArray(data.numbers)
            ? 'Tap, then pick the number on the lock screen.'
            : 'Tap to approve.';
        options.tag = `facelock-${data.topic}`;
        options.renotify = true;
        options.requireInteraction = true;
    } else if (data.type === 'paired') {
        title = 'Facelock is paired';
        options.body = `${data.name} can now ask this phone to approve unlocking it.`;
    }
    event.waitUntil(Promise.all([
        self.registration.showNotification(title, options),
        data.type === 'unlock' ? savePending(data) : Promise.resolve(),
        log(`push ${data.type ?? 'unreadable'}`),
    ]));
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    const request = event.notification.data;
    if (request?.type !== 'unlock') {
        event.waitUntil(log(`tapped ${request?.type ?? 'unknown'} notification`));
        return;
    }
    event.waitUntil((async () => {
        await savePending(request);
        const windows = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
        await log(`tapped unlock, ${windows.length} window(s) open`);
        for (const client of windows) {
            if ('focus' in client) {
                client.postMessage({type: 'unlock', request});
                return client.focus();
            }
        }
        const url = new URL(`./#r=${encodeRequest(request)}`, self.registration.scope);
        return self.clients.openWindow(url.href);
    })());
});
