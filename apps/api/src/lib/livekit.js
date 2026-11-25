import { LiveKitAPI } from 'livekit-server-sdk';
import { livekitInternalUrl, livekitPublicUrl, livekitApiKey, livekitApiSecret } from '../config/env.js';
export function livekitAPI() {
  const url = livekitInternalUrl();
  const host = url.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://');
  return new LiveKitAPI({ host, apiKey: livekitApiKey(), secret: livekitApiSecret() });
}
export { livekitPublicUrl, livekitInternalUrl };
