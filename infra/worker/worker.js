/**
 * Cloudflare Worker — LiveKit signaling proxy (frontend only)
 * Frontend: wss://<worker>.workers.dev  →  wss://horno-avatar-jr68tfeq.livekit.cloud
 * Backend MUST use LIVEKIT_API_URL=https://horno-avatar-jr68tfeq.livekit.cloud directly (never this Worker).
 *
 * LiveKit signaling = Protobuf over WebSocket (binary frames) interleaved with JSON.
 * Do NOT JSON.parse / stringify frames here — preserve binary verbatim.
 * Use the native fetch-passthrough so Cloudflare preserves Upgrade, message boundaries and ordering.
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const livekitHost = (env.LIVEKIT_HOST || "horno-avatar-jr68tfeq.livekit.cloud").trim();
    const allowedOrigins = (env.ALLOWED_ORIGINS || "*").trim();

    if (request.method === "OPTIONS") return corsResponse(null, allowedOrigins, request);

    // Backend RoomService must NOT go through WS proxy (would 426)
    if (url.pathname.startsWith("/twirp/")) {
      return new Response(
        JSON.stringify({
          error: "RoomService HTTP must NOT go through the WS proxy",
          detail: `Backend misconfigured: LIVEKIT_API_URL must be https://${livekitHost}`,
          hint: "Set LIVEKIT_API_URL=https://horno-avatar-jr68tfeq.livekit.cloud in backend .env; VITE_LIVEKIT_URL=wss://<worker>.workers.dev for frontend.",
        }),
        { status: 403, headers: { "content-type": "application/json; charset=utf-8", ...corsHeaders(allowedOrigins, request) } }
      );
    }

    const upgrade = request.headers.get("Upgrade");
    const isWebSocket = upgrade && upgrade.toLowerCase() === "websocket";

    // WebSocket signaling: preserve Upgrade/Connection/Sec-WebSocket-* verbatim via native proxy
    if (isWebSocket) {
      const upstreamUrl = new URL(request.url);
      upstreamUrl.hostname = livekitHost;
      upstreamUrl.protocol = "https:";
      upstreamUrl.port = "";
      // Clone request with upstream host, keep all WS headers/body intact
      const upstreamRequest = new Request(upstreamUrl.toString(), request);
      upstreamRequest.headers.set("host", livekitHost);
      upstreamRequest.headers.set("x-forwarded-host", url.hostname);
      const ip = request.headers.get("cf-connecting-ip");
      if (ip) upstreamRequest.headers.set("x-real-ip", ip);
      upstreamRequest.headers.set("x-proxied-by", "livekit-ws-proxy");

      try {
        // Native fetch passthrough preserves 101 Switching Protocols and binary frames
        const upstreamResponse = await fetch(upstreamRequest);
        // Add CORS/expose headers (safe to mutate)
        const headers = new Headers(upstreamResponse.headers);
        for (const [k, v] of Object.entries(corsHeaders(allowedOrigins, request))) headers.set(k, v);
        headers.set("x-proxied-by", "livekit-ws-proxy");
        headers.set("x-upstream-host", livekitHost);
        return new Response(upstreamResponse.body, {
          status: upstreamResponse.status,
          statusText: upstreamResponse.statusText,
          headers,
          webSocket: upstreamResponse.webSocket ?? undefined,
        });
      } catch (err) {
        return jsonError(502, "WebSocket proxy failed", err, allowedOrigins, request);
      }
    }

    // Non-WS HTTP: allow only LiveKit signaling paths (not an open proxy)
    const ALLOWED_HTTP_PREFIXES = ["/rtc", "/cluster", "/validate", "/health"];
    const isAllowedHttp = ALLOWED_HTTP_PREFIXES.some((p) => url.pathname.startsWith(p));
    if (!isAllowedHttp && url.pathname !== "/" && url.pathname !== "") {
      return new Response(
        JSON.stringify({ error: "Not proxied — unknown path for WS proxy", path: url.pathname, allowed: ALLOWED_HTTP_PREFIXES.join(", ") + " (+ WebSocket Upgrade)" }),
        { status: 404, headers: { "content-type": "application/json", ...corsHeaders(allowedOrigins, request) } }
      );
    }

    const upstreamUrl = new URL(request.url);
    upstreamUrl.hostname = livekitHost;
    upstreamUrl.protocol = "https:";
    upstreamUrl.port = "";
    const upstreamHeaders = new Headers(request.headers);
    upstreamHeaders.set("host", livekitHost);
    upstreamHeaders.set("x-forwarded-host", url.hostname);
    try {
      const upstreamResponse = await fetch(upstreamUrl.toString(), {
        method: request.method,
        headers: upstreamHeaders,
        body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      });
      const headers = new Headers(upstreamResponse.headers);
      for (const [k, v] of Object.entries(corsHeaders(allowedOrigins, request))) headers.set(k, v);
      headers.set("x-proxied-by", "livekit-ws-proxy");
      return new Response(upstreamResponse.body, { status: upstreamResponse.status, statusText: upstreamResponse.statusText, headers });
    } catch (err) {
      return jsonError(502, "HTTP proxy failed", err, allowedOrigins, request);
    }
  },
};

function corsHeaders(allowedOrigins, request) {
  const origin = request.headers.get("Origin") || "";
  if (allowedOrigins === "*") return { "access-control-allow-origin": "*", "access-control-allow-methods": "GET,POST,OPTIONS", "access-control-allow-headers": "Content-Type, Authorization, X-LiveKit-*, Upgrade, Connection, Sec-WebSocket-*", "access-control-expose-headers": "X-Proxied-By, X-Upstream-Host" };
  const allowed = allowedOrigins.split(",").map((s) => s.trim()).filter(Boolean);
  return { "access-control-allow-origin": allowed.find((a) => a === origin) || allowed[0] || "", "access-control-allow-methods": "GET,POST,OPTIONS", "access-control-allow-headers": "Content-Type, Authorization, X-LiveKit-*, Upgrade, Connection, Sec-WebSocket-*", "access-control-expose-headers": "X-Proxied-By, X-Upstream-Host", vary: "Origin" };
}
function corsResponse(body, allowedOrigins, request) {
  return new Response(body, { status: 204, headers: { ...corsHeaders(allowedOrigins, request), "access-control-max-age": "86400" } });
}
function jsonError(status, message, err, allowedOrigins, request) {
  return new Response(JSON.stringify({ error: message, details: err instanceof Error ? err.message : String(err), upstream: request.url }), { status, headers: { "content-type": "application/json", ...corsHeaders(allowedOrigins, request) } });
}
