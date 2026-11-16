import 'dotenv/config';
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { AccessToken, LiveKitAPI } from 'livekit-server-sdk';

const app = express();
const port = Number(process.env.PORT || 3001);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
app.use(express.json({ limit: '32kb' }));

function isConfigured() {
  return Boolean(
    process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET &&
    process.env.SIMLI_API_KEY && process.env.SIMLI_FACE_ID &&
    process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN &&
    process.env.ELEVEN_API_KEY && process.env.ELEVEN_VOICE_ID,
  );
}

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    configured: isConfigured(),
    agentName: process.env.LIVEKIT_AGENT_NAME || 'hamrah-agent',
    llmProvider: 'Cloudflare Workers AI',
    llmModel: process.env.CLOUDFLARE_LLM_MODEL || '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
    cloudflareConfigured: Boolean(process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN),
    avatarProvider: 'Simli',
    simliConfigured: Boolean(process.env.SIMLI_API_KEY && process.env.SIMLI_FACE_ID),
    sttModel: process.env.LIVEKIT_STT_MODEL || 'deepgram/nova-3',
    sttLanguage: process.env.LIVEKIT_STT_LANGUAGE || 'fa',
    ttsProvider: 'ElevenLabs',
    ttsModel: process.env.ELEVEN_TTS_MODEL || 'eleven_multilingual_v2',
    ttsVoice: process.env.ELEVEN_VOICE_ID || null,
    ttsLanguage: process.env.ELEVEN_TTS_LANGUAGE || 'fa',
    elevenLabsConfigured: Boolean(process.env.ELEVEN_API_KEY && process.env.ELEVEN_VOICE_ID),
  });
});

app.post('/api/session', async (req, res) => {
  if (!isConfigured()) {
    return res.status(503).json({ error: 'برای شروع، اطلاعات LiveKit، Simli، Cloudflare Workers AI و ElevenLabs (ELEVEN_API_KEY و ELEVEN_VOICE_ID) را در فایل .env تنظیم کنید.' });
  }

  const roomName = `hamrah-${randomUUID().slice(0, 12)}`;
  const identity = `guest-${randomUUID().slice(0, 8)}`;
  const name = typeof req.body?.name === 'string' ? req.body.name.slice(0, 80) : 'دوست من';
  const openingLine = typeof req.body?.message === 'string' ? req.body.message.trim().slice(0, 300) : '';

  try {
    const livekitHost = process.env.LIVEKIT_URL.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://');
    const api = new LiveKitAPI({ host: livekitHost, apiKey: process.env.LIVEKIT_API_KEY, secret: process.env.LIVEKIT_API_SECRET });
    await api.room.createRoom({ name: roomName, emptyTimeout: 30, maxParticipants: 4 });
    await api.agentDispatch.createDispatch(roomName, process.env.LIVEKIT_AGENT_NAME || 'hamrah-agent', {
      metadata: JSON.stringify({ opening_line: openingLine, participant_name: name }),
    });

    const accessToken = new AccessToken(process.env.LIVEKIT_API_KEY, process.env.LIVEKIT_API_SECRET, {
      identity,
      name,
      ttl: '10m',
    });
    accessToken.addGrant({
      roomJoin: true,
      room: roomName,
      canPublish: true,
      canSubscribe: true,
      canPublishData: true,
    });

    res.json({
      serverUrl: process.env.LIVEKIT_URL,
      token: await accessToken.toJwt(),
      roomName,
    });
  } catch (error) {
    console.error('Could not start LiveKit session:', error);
    res.status(502).json({
      error: 'ساخت جلسه‌ی صوتی/تصویری ناموفق بود. تنظیمات LiveKit، Agent و Simli را بررسی کنید.',
      details: process.env.NODE_ENV === 'production' ? undefined : (error instanceof Error ? error.message : String(error)),
    });
  }
});

if (process.env.NODE_ENV === 'production') {
  const clientDist = path.resolve(__dirname, '../dist');
  app.use(express.static(clientDist));
  app.get('*', (_req, res) => res.sendFile(path.join(clientDist, 'index.html')));
}

app.listen(port, '0.0.0.0', () => console.log(`API server listening on http://0.0.0.0:${port}`));
