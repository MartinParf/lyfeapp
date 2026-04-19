{% load static %}

const SW_VERSION = "v13-5";

const STATIC_CACHE = `lyfe-static-${SW_VERSION}`;
const PAGE_CACHE = `lyfe-pages-${SW_VERSION}`;
const RUNTIME_CACHE = `lyfe-runtime-${SW_VERSION}`;

const OFFLINE_URL = "/offline/";

const PRECACHE_URLS = [
    OFFLINE_URL,
    "/favicon.ico",
    "{% static 'core/manifest.webmanifest' %}",
    "{% static 'core/css/app.css' %}?v=theme-v2",
    "{% static 'core/icons/icon-192.svg' %}",
    "{% static 'core/icons/icon-512.svg' %}",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(STATIC_CACHE)
            .then((cache) => cache.addAll(PRECACHE_URLS))
    );
});

self.addEventListener("activate", (event) => {
    const allowedCaches = new Set([
        STATIC_CACHE,
        PAGE_CACHE,
        RUNTIME_CACHE,
    ]);

    event.waitUntil(
        caches
            .keys()
            .then((keys) =>
                Promise.all(
                    keys
                        .filter((key) => key.startsWith("lyfe-") && !allowedCaches.has(key))
                        .map((key) => caches.delete(key))
                )
            )
            .then(() => self.clients.claim())
    );
});

function isNavigationRequest(request) {
    return (
        request.mode === "navigate" ||
        (request.headers.get("accept") || "").includes("text/html")
    );
}

function isSameOrigin(url) {
    return url.origin === self.location.origin;
}

function isStaticAsset(url) {
    return (
        isSameOrigin(url) &&
        (
            url.pathname.startsWith("/static/") ||
            url.pathname === "/manifest.webmanifest" ||
            url.pathname.endsWith(".webmanifest")
        )
    );
}

function shouldCachePage(url, response) {
    if (!isSameOrigin(url)) {
        return false;
    }

    if (!response || response.status !== 200 || response.type !== "basic") {
        return false;
    }

    if (url.pathname.startsWith("/admin/")) {
        return false;
    }

    return true;
}

async function networkFirstPage(request) {
    const url = new URL(request.url);

    try {
        const response = await fetch(request);

        if (shouldCachePage(url, response)) {
            const cache = await caches.open(PAGE_CACHE);
            await cache.put(request, response.clone());
        }

        return response;
    } catch (error) {
        const cached = await caches.match(request);

        if (cached) {
            return cached;
        }

        return caches.match(OFFLINE_URL);
    }
}

async function cacheFirstStatic(request) {
    const cached = await caches.match(request);

    if (cached) {
        return cached;
    }

    const response = await fetch(request);

    if (response && response.status === 200) {
        const cache = await caches.open(STATIC_CACHE);
        await cache.put(request, response.clone());
    }

    return response;
}

function offlineFallbackResponse() {
    return new Response("", {
        status: 504,
        statusText: "Offline",
        headers: {
            "Content-Type": "text/plain",
        },
    });
}

async function staleWhileRevalidateRuntime(request) {
    const cache = await caches.open(RUNTIME_CACHE);
    const cached = await cache.match(request);

    const fetchPromise = fetch(request)
        .then((response) => {
            if (
                response &&
                response.status === 200 &&
                ["basic", "cors"].includes(response.type)
            ) {
                cache.put(request, response.clone());
            }

            return response;
        })
        .catch(() => cached || offlineFallbackResponse());

    return cached || fetchPromise;
}

self.addEventListener("fetch", (event) => {
    const request = event.request;
    const url = new URL(request.url);

    if (request.method !== "GET") {
        return;
    }

    if (isNavigationRequest(request)) {
        event.respondWith(networkFirstPage(request));
        return;
    }

    if (isStaticAsset(url)) {
        event.respondWith(cacheFirstStatic(request));
        return;
    }

    if (isSameOrigin(url)) {
        event.respondWith(staleWhileRevalidateRuntime(request));
        return;
    }

    if (["https:", "http:"].includes(url.protocol)) {
        event.respondWith(staleWhileRevalidateRuntime(request));
    }
});

self.addEventListener("message", (event) => {
    if (event.data && event.data.type === "SKIP_WAITING") {
        self.skipWaiting();
    }
});