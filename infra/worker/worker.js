/**
 * Cloudflare Worker — LiveKit WebSocket proxy (frontend only)
 *
 * Frontend (livekit-client) connects via WSS to this Worker (wss://*.workers.dev),
 * Worker forwards the WS upgrade to LiveKit Cloud (wss://<project>.livekit.cloud).
 *
 * Backend (RoomServiceClient) MUST NOT use this proxy — it uses https://<project>.livekit.cloud directly.
 * Deploy: cd infra/worker && npx wrangler deploy
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const livekitHost = (env.LIVEKIT_HOST || "horno-avatar-jr68tfeq.livekit.cloud").trim();
    const allowedOrigins = (env.ALLOWED_ORIGINS || "*").trim();

    if (request.method === "OPTIONS") {
      return corsResponse(null, allowedOrigins, request);
    }

    // Reject backend RoomService via this proxy — operator misconfiguration
    if (url.pathname.startsWith("/twirp/")) {
      return new Response(
        JSON.stringify({
          error: "RoomService HTTP must NOT go through the WS proxy",
          detail: `Backend misconfigured: LIVEKIT_API_URL must be https://${livekitHost} (not wss://worker). This Worker only proxies WSS signaling.`,
          hint: "Set LIVEKIT_API_URL=https://horno-avatar-jr68tfeq.livekit.cloud in backend .env; VITE_LIVEKIT_URL=wss://<worker>.workers.dev for frontend.",
        }),
        {
          status: 403,
          headers: {
            "content-type": "application/json; charset=utf-8",
            ...corsHeaders(allowedOrigins, request),
          },
        }
      );
    }

    const upstreamUrl = new URL(request.url);
    upstreamUrl.hostname = livekitHost;
    upstreamUrl.protocol = "https:";
    upstreamUrl.port = "";

    const upgradeHeader = request.headers.get("Upgrade");
    const isWebSocket = upgradeHeader && upgradeHeader.toLowerCase() === "websocket";

    if (isWebSocket) {
      const upstreamHeaders = new Headers(request.headers);
      upstreamHeaders.set("host", livekitHost);
      upstreamHeaders.set("x-forwarded-host", url.hostname);
      const ip = request.headers.get("cf-connecting-ip");
      if (ip) upstreamHeaders.set("x-real-ip", ip);

      try {
        const upstreamResponse = await fetch(upstreamUrl.toString(), {
          method: request.method,
          headers: upstreamHeaders,
          body: request.body,
        });
        const responseHeaders = new Headers(upstreamResponse.headers);
        for (const [k, v] of Object.entries(corsHeaders(allowedOrigins, request))) responseHeaders.set(k, v);
        responseHeaders.set("x-proxied-by", "livekit-ws-proxy");
        responseHeaders.set("x-upstream-host", livekitHost);
        return new Response(upstreamResponse.body, {
          status: upstreamResponse.status,
          statusText: upstreamResponse.statusText,
          headers: responseHeaders,
        });
      } catch (err) {
        return jsonError(502, "WebSocket proxy failed", err, allowedOrigins, request);
      }
    }

    // Non-WS HTTP: allow LiveKit signaling paths only (not an open proxy)
    const ALLOWED_HTTP_PREFIXES = ["/rtc", "/cluster", "/validate", "/health"];
    const isAllowedHttp = ALLOWED_HTTP_PREFIXES.some((p) => url.pathname.startsWith(p));
    if (!isAllowedHttp && url.pathname !== "/" && url.pathname !== "") {
      return new Response(
        JSON.stringify({
          error: "Not proxied — unknown path for WS proxy",
          path: url.pathname,
          allowed: ALLOWED_HTTP_PREFIXES.join(", ") + " (+ WebSocket Upgrade)",
        }),
        {
          status: 404,
          headers: { "content-type": "application/json", ...corsHeaders(allowedOrigins, request) },
        }
      );
    }

    const upstreamHeaders = new Headers(request.headers);
    upstreamHeaders.set("host", livekitHost);
    upstreamHeaders.set("x-forwarded-host", url.hostname);

    try {
      const upstreamResponse = await fetch(upstreamUrl.toString(), {
        method: request.method,
        headers: upstreamHeaders,
        body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      });
      const responseHeaders = new Headers(upstreamResponse.headers);
      for (const [k, v] of Object.entries(corsHeaders(allowedOrigins, request))) responseHeaders.set(k, v);
      responseHeaders.set("x-proxied-by", "livekit-ws-proxy");
      return new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return jsonError(502, "HTTP proxy failed", err, allowedOrigins, request);
    }
  },
};

function corsHeaders(allowedOrigins, request) {
  const origin = request.headers.get("Origin") || "";
  if (allowedOrigins === "*") {
    return {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET,POST,OPTIONS",
      "access-control-allow-headers": "Content-Type, Authorization, X-LiveKit-*, Upgrade, Connection, Sec-WebSocket-*",
      "access-control-expose-headers": "X-Proxied-By, X-Upstream-Host",
    };
  }
  const allowed = allowedOrigins.split(",").map((s) => s.trim()).filter(Boolean);
  const matched = allowed.find((a) => a === origin) || allowed[0] || "";
  return {
    "access-control-allow-origin": matched,
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "Content-Type, Authorization, X-LiveKit-*, Upgrade, Connection, Sec-WebSocket-*",
    "access-control-expose-headers": "X-Proxied-By, X-Upstream-Host",
    vary: "Origin",
  };
}

function corsResponse(body, allowedOrigins, request) {
  return new Response(body, {
    status: 204,
    headers: {
      ...corsHeaders(allowedOrigins, request),
      "access-control-max-age": "86400",
    },
  });
}

function jsonError(status, message, err, allowedOrigins, request) {
  return new Response(
    JSON.stringify({
      error: message,
      details: err instanceof Error ? err.message : String(err),
      upstream: request.url,
    }),
    {
      status,
      headers: { "content-type": "application/json", ...corsHeaders(allowedOrigins, request) },
    }
  );
}
