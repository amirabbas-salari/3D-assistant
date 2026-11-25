import { LiveKitAPI } from 'livekit-server-sdk';
export function livekitAPI() {
  const host = process.env.LIVEKIT_URL.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://');
  return new LiveKitAPI({ host, apiKey: process.env.LIVEKIT_API_KEY, secret: process.env.LIVEKIT_API_SECRET });
}
