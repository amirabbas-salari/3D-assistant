# LiveKit WebSocket Proxy (Cloudflare Worker)

Frontend `livekit-client` needs `wss://` to LiveKit Cloud. This Worker proxies `wss://<worker>.workers.dev` → `wss://horno-avatar-jr68tfeq.livekit.cloud` with CORS.

Backend (`RoomServiceClient`) MUST NOT use this proxy — it uses `https://horno-avatar-jr68tfeq.livekit.cloud` directly via `LIVEKIT_API_URL`.

## Deploy

```bash
cd infra/worker
npx wrangler deploy
# set host if different:
npx wrangler secret put LIVEKIT_HOST
# or edit wrangler.toml [vars]
```

## Env

- `LIVEKIT_HOST` — LiveKit Cloud host without scheme (e.g. `horno-avatar-jr68tfeq.livekit.cloud`)
- `ALLOWED_ORIGINS` — CORS (`*` or `https://example.com,https://other.com`)

## Test

1. `curl -i https://<worker>.workers.dev/twirp/livekit.RoomService/CreateRoom` → `403` (expected, not proxied)
2. Browser: `room.connect("wss://<worker>.workers.dev", token)` → connects
3. Backend: `LIVEKIT_API_URL=https://horno-avatar-jr68tfeq.livekit.cloud npm run dev:api` → `/api/session` creates room
