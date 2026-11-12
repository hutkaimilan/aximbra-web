// Minimális service worker: a böngésző ettől ajánlja fel az alkalmazás telepítését.
// Szándékosan nem gyorsítótáraz: a számla adatai mindig élőben jönnek a szerverről.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
