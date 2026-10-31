self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => { event.waitUntil(caches.delete("todo-v1").then(() => self.registration.unregister())); });
