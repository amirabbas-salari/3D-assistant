import { LiveKitAPI } from 'livekit-server-sdk';

function resolveApiHost() {
  const apiUrl = (process.env.LIVEKIT_API_URL || '').trim();
  if (apiUrl) return apiUrl.replace(/\/$/, '');
  const legacy = (process.env.LIVEKIT_URL || '').trim();
  if (legacy) {
    return legacy.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://').replace(/\/$/, '');
  }
  return '';
}

export function livekitAPI() {
  const host = resolveApiHost();
  if (!host) {
    throw new Error('LIVEKIT_API_URL (or LIVEKIT_URL) is not configured — set LIVEKIT_API_URL=https://your-project.livekit.cloud');
  }
  if (/^wss?:\/\//.test(host)) {
    throw new Error(`LIVEKIT_API_URL must be https://, not ${host} — WebSocket URLs (wss://) are for the frontend only (VITE_LIVEKIT_URL). See .env.example`);
  }
  return new LiveKitAPI({ host, apiKey: process.env.LIVEKIT_API_KEY, secret: process.env.LIVEKIT_API_SECRET });
}

export function frontendLivekitUrl() {
  const viteUrl = (process.env.VITE_LIVEKIT_URL || '').trim();
  if (viteUrl) return viteUrl;
  const livekitUrl = (process.env.LIVEKIT_URL || '').trim();
  if (livekitUrl) return livekitUrl;
  const apiUrl = (process.env.LIVEKIT_API_URL || '').trim();
  if (apiUrl) return apiUrl.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://');
  return '';
}
