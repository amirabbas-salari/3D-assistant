import { Router } from 'express';
import { randomUUID } from 'node:crypto';
import { AccessToken } from 'livekit-server-sdk';
import { avatarProvider, isConfigured, speechConfigured } from '../config/env.js';
import { frontendLivekitUrl, livekitAPI } from '../lib/livekit.js';
const router = Router();
router.post('/session', async (req, res) => {
  if (!isConfigured()) {
    const provider = avatarProvider();
    const parts = ['اطلاعات LiveKit و Cloudflare Workers AI'];
    if (provider === 'did') parts.push('D-ID (DID_API_KEY و DID_AGENT_ID)');
    if (provider === 'spatius') parts.push('Spatius');
    if (!speechConfigured()) parts.push('کلیدهای گفتار (DEEPGRAM_API_KEY و GOOGLE_API_KEY برای SPEECH_PROVIDER=direct)');
    return res.status(503).json({ error: `برای شروع، ${parts.join('، ')} را در فایل .env تنظیم کنید.` });
  }
  // Validate room/participant inputs (security)
  const roomName = `sam-${randomUUID().slice(0, 12)}`;
  const identity = `guest-${randomUUID().slice(0, 8)}`;
  const name = typeof req.body?.name === 'string' ? req.body.name.slice(0, 80).replace(/[<>\"'&]/g, '') : 'دوست من';
  const openingLine = typeof req.body?.message === 'string' ? req.body.message.trim().slice(0, 300) : '';
  // Basic rate-limit: require name/message to be reasonable (CORS already restricts origin)
  if (openingLine.length > 300 || name.length > 80) {
    return res.status(400).json({ error: 'درخواست نامعتبر است.' });
  }
  try {
    const api = livekitAPI();
    // LiveKit auto-creates rooms on first join; explicit create is optional but useful
    // to set emptyTimeout/maxParticipants. Failure here is non-fatal if room already exists.
    try {
      await api.room.createRoom({ name: roomName, emptyTimeout: 30, maxParticipants: 4 });
    } catch (roomErr) {
      const msg = roomErr instanceof Error ? roomErr.message : String(roomErr);
      // 409 = already exists (retry race), can continue; otherwise log and continue anyway
      // since join will auto-create. Only fail on auth/network errors.
      if (!/already exists|already.*exists|409/.test(msg)) {
        console.warn('[session] createRoom non-fatal (will auto-create on join):', msg);
      }
    }
    // Dispatch agent — non-fatal if already dispatched or agent not running
    try {
      await api.agentDispatch.createDispatch(roomName, process.env.LIVEKIT_AGENT_NAME || 'sam-voice-agent', { metadata: JSON.stringify({ opening_line: openingLine, participant_name: name }) });
    } catch (dispatchErr) {
      const msg = dispatchErr instanceof Error ? dispatchErr.message : String(dispatchErr);
      // Common: agent already dispatched, or not registered — warn but don't fail session
      console.warn('[session] agentDispatch non-fatal:', msg);
    }
    const accessToken = new AccessToken(process.env.LIVEKIT_API_KEY, process.env.LIVEKIT_API_SECRET, { identity, name, ttl: '10m' });
    accessToken.addGrant({ roomJoin: true, room: roomName, canPublish: true, canSubscribe: true, canPublishData: true });
    const serverUrl = frontendLivekitUrl();
    if (!serverUrl) {
      console.error('[session] No frontend LiveKit URL configured — set VITE_LIVEKIT_URL or LIVEKIT_URL');
    }
    res.json({ serverUrl, token: await accessToken.toJwt(), roomName, avatarProvider: avatarProvider(), spatiusAppId: process.env.SPATIUS_APP_ID, spatiusAvatarId: process.env.SPATIUS_AVATAR_ID });
  } catch (error) {
    console.error('Could not start LiveKit session:', error);
    // Provide diagnostic without leaking secrets
    const details = error instanceof Error ? error.message : String(error);
    const is426 = /426|Upgrade Required|WebSocket.*upgrade/i.test(details);
    const hint = is426
      ? ' — LIVEKIT_API_URL is incorrectly set to a WebSocket proxy (wss://). Backend must use https://your-project.livekit.cloud (see .env.example: LIVEKIT_API_URL vs VITE_LIVEKIT_URL).'
      : '';
    res.status(502).json({ error: 'ساخت جلسه‌ی صوتی/تصویری ناموفق بود. تنظیمات LiveKit، Agent و Spatius را بررسی کنید.', details: process.env.NODE_ENV === 'production' ? undefined : details + hint });
  }
});
export default router;
