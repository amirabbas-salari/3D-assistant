import { Router } from 'express';
import { randomUUID } from 'node:crypto';
import { AccessToken } from 'livekit-server-sdk';
import { avatarProvider, tavusAvatarMode, isConfigured, speechConfigured } from '../config/env.js';
import { livekitAPI } from '../lib/livekit.js';
const router = Router();
router.post('/session', async (req, res) => {
  if (!isConfigured()) {
    const provider = avatarProvider();
    const parts = ['اطلاعات LiveKit و Cloudflare Workers AI'];
    if (provider === 'tavus') parts.push('Tavus (TAVUS_API_KEY و TAVUS_REPLICA_ID)');
    if (provider === 'spatius') parts.push('Spatius (SPATIUS_API_KEY, SPATIUS_APP_ID و SPATIUS_AVATAR_ID)');
    if (!speechConfigured()) parts.push('کلیدهای گفتار (DEEPGRAM_API_KEY و GOOGLE_API_KEY برای SPEECH_PROVIDER=direct)');
    return res.status(503).json({ error: `برای شروع، ${parts.join('، ')} را در فایل .env تنظیم کنید.` });
  }
  const roomName = `sam-${randomUUID().slice(0, 12)}`;
  const identity = `guest-${randomUUID().slice(0, 8)}`;
  const name = typeof req.body?.name === 'string' ? req.body.name.slice(0, 80) : 'دوست من';
  const openingLine = typeof req.body?.message === 'string' ? req.body.message.trim().slice(0, 300) : '';
  try {
    const api = livekitAPI();
    await api.room.createRoom({ name: roomName, emptyTimeout: 30, maxParticipants: 4 });
    await api.agentDispatch.createDispatch(roomName, process.env.LIVEKIT_AGENT_NAME || 'sam-voice-agent', { metadata: JSON.stringify({ opening_line: openingLine, participant_name: name }) });
    const accessToken = new AccessToken(process.env.LIVEKIT_API_KEY, process.env.LIVEKIT_API_SECRET, { identity, name, ttl: '10m' });
    accessToken.addGrant({ roomJoin: true, room: roomName, canPublish: true, canSubscribe: true, canPublishData: true });
    res.json({
      serverUrl: process.env.LIVEKIT_URL, token: await accessToken.toJwt(), roomName,
      avatarProvider: avatarProvider(), tavusAvatarMode: tavusAvatarMode(),
      tavusReplicaId: process.env.TAVUS_REPLICA_ID || process.env.TAVUS_FACE_ID || null, tavusPersonaId: process.env.TAVUS_PERSONA_ID || process.env.TAVUS_PAL_ID || null,
      spatiusAppId: process.env.SPATIUS_APP_ID || null, spatiusAvatarId: process.env.SPATIUS_AVATAR_ID || null, spatiusRegion: process.env.SPATIUS_REGION || 'auto',
    });
  } catch (error) {
    console.error('Could not start LiveKit session:', error);
    res.status(502).json({ error: 'ساخت جلسه‌ی صوتی/تصویری ناموفق بود. تنظیمات LiveKit، Agent و Tavus/Spatiaus را بررسی کنید.', details: process.env.NODE_ENV === 'production' ? undefined : (error instanceof Error ? error.message : String(error)) });
  }
});
export default router;
