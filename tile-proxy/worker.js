// Opossum Foot — Mapbox tile proxy (Cloudflare Worker)
// Route: opossumfoot.com/tiles/*
//
// Why this exists: the native app (Capacitor/WKWebView) runs on the
// capacitor://localhost origin. Mapbox's tile endpoint enforces the
// token's URL restrictions against the request Referer, WebKit sends
// only the bare origin, and Mapbox refuses every capacitor:// referer
// (403) — so the app's map paints black. The app therefore asks THIS
// worker for Mapbox tiles; the worker fetches them server-side with a
// Referer Mapbox allows (https://opossumfoot.com/) and returns them.
//
// The app only uses this proxy in its native build; the web app keeps
// fetching tiles directly (its origin is on the token's allowlist).
//
// Guardrails:
//  - Only the three styles the app ships, only numeric tile coords.
//  - NO Referer gate (removed 2026-11-23, build 27 field failure):
//    the first version refused any request whose Referer was not on
//    an allowlist — but WKWebView sends no usable Referer for tile
//    <img> loads from the capacitor:// origin, so the proxy refused
//    the app's own tiles and the map stayed black. The token behind
//    this worker is the app's PUBLIC token (it ships in the app), so
//    the gate bought nothing and cost the map. Style/coords/method
//    constraints stay; if quota abuse ever appears, answer it with a
//    Cloudflare rate-limit rule on the route, not a header gate.
//  - Mapbox's own Cache-Control is passed through untouched; the
//    worker stores nothing beyond what those headers allow
//    (Mapbox terms: tiles may be cached at most 30 days; Mapbox
//    sends max-age=43200, i.e. 12 hours).

const STYLES = new Set([
  "satellite-streets-v12",
  "streets-v12",
  "outdoors-v12",
]);

export default {
  async fetch(request, env) {
    if (request.method !== "GET") {
      return new Response("Method not allowed", { status: 405 });
    }

    // /tiles/<style>/256/<z>/<x>/<y>  (an optional .png suffix is tolerated)
    const parts = new URL(request.url).pathname.split("/").filter(Boolean);
    if (parts.length !== 6 || parts[0] !== "tiles" || parts[2] !== "256") {
      return new Response("Not found", { status: 404 });
    }
    const [, style, , z, x, yRaw] = parts;
    const y = yRaw.replace(/\.png$/i, "");
    if (!STYLES.has(style) || !/^\d+$/.test(z) || !/^\d+$/.test(x) || !/^\d+$/.test(y)) {
      return new Response("Not found", { status: 404 });
    }

    const upstream =
      "https://api.mapbox.com/styles/v1/mapbox/" +
      style +
      "/tiles/256/" +
      z + "/" + x + "/" + y +
      "?access_token=" +
      env.MAPBOX_TOKEN;

    const res = await fetch(upstream, {
      headers: { Referer: "https://opossumfoot.com/" },
    });

    const headers = new Headers();
    headers.set(
      "Content-Type",
      res.headers.get("Content-Type") || "image/jpeg"
    );
    const cc = res.headers.get("Cache-Control");
    if (cc) headers.set("Cache-Control", cc);

    return new Response(res.body, { status: res.status, headers });
  },
};
