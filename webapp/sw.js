// Minimal PWA shell cache (2026-07-14). Deliberately narrow scope: this only
// caches the static app shell (index.html, manifest, branding/icons, and
// leagues.js — the rarely-changing league registry) so the app can still
// open offline. It does NOT touch webapp/data/*.js payloads — those are
// already cache-busted per-request with a `?t=timestamp` query string by the
// app itself (see index.html's document.write calls), and a service worker
// caching them would fight that and serve stale odds/standings.
// Bump this version string on any shell/feature change to force every
// returning browser to purge its old cached shell and re-fetch the fresh
// one (the activate handler deletes all caches != CACHE). v2 (2026-07-15):
// flush shells cached before the momentum/postgame-WE/results features
// shipped, since some returning visitors reported seeing the pre-feature
// page from cache. v3 (2026-07-16): shell head changed — canonical link +
// JSON-LD + data-status badges (launch plan B2/C5/C6).
// NOTE: the static /leagues/<id>/ pages are deliberately NOT cached here —
// the fetch handler's SHELL allowlist below never matches them, so they
// always load fresh from the network (they carry daily-refreshed odds).
// v4 (2026-07-17): first-screen promise + plain-English trust copy (launch
// plan D) — flush shells cached with the old "explained and audited" head.
// v5 (2026-07-17): locale-aware dates + odds-format toggle (launch plan F).
const CACHE = "entenser-shell-v5";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/leagues.js",
  "/assets/branding/favicon.png",
  "/assets/pwa/icon-192.png",
  "/assets/pwa/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;       // don't touch cross-origin (crests, CDN)
  if (url.pathname.startsWith("/data/")) return;          // never cache dynamic payloads
  if (!SHELL.includes(url.pathname) && url.pathname !== "/") return;

  // Network-first, cache fallback: normal loads always get the freshest
  // shell; only an offline/network-failure load falls back to the cache.
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
