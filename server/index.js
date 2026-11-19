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

// Temporary focus mode: the avatar can be switched off while the STT, LLM, and
// TTS pipeline is being worked on. Avatar credentials are then not required.
function avatarEnabled() {
  return ['1', 'true', 'yes', 'on'].includes(
    String(process.env.AVATAR_ENABLED ?? 'false').trim().toLowerCase(),
  );
}

// Which avatar backend runs inside the agent. "spatius" stays the default so an
// existing .env keeps working; "did" uses a D-ID Expressive Agent joined to the
// same LiveKit room. Must match _avatar_provider() in agent.py.
function avatarProvider() {
  if (!avatarEnabled()) return 'none';
  const provider = String(process.env.AVATAR_PROVIDER ?? 'spatius').trim().toLowerCase();
  if (['', 'none', 'off', 'false'].includes(provider)) return 'none';
  if (['did', 'd-id', 'didid'].includes(provider)) return 'did';
  return 'spatius';
}

// Where STT and TTS come from. "inference" uses the LiveKit gateway (included
// with LiveKit Cloud, capped by the Build-plan monthly allowance); "direct" uses the
// providers' own API keys and is not subject to that cap.
function speechProvider() {
  const provider = String(process.env.SPEECH_PROVIDER ?? 'inference').trim().toLowerCase();
  return ['direct', 'byok', 'provider', 'own-keys'].includes(provider) ? 'direct' : 'inference';
}

function speechConfigured() {
  if (speechProvider() === 'direct') {
    return Boolean(process.env.DEEPGRAM_API_KEY && process.env.GOOGLE_API_KEY);
  }
  // LiveKit Inference authenticates with the project credentials.
  return Boolean(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET);
}

function didConfigured() {
  return Boolean(process.env.DID_API_KEY && process.env.DID_AGENT_ID);
}

function spatiusConfigured() {
  return Boolean(
    process.env.SPATIUS_API_KEY && process.env.SPATIUS_APP_ID && process.env.SPATIUS_AVATAR_ID,
  );
}

function isConfigured() {
  const voicePipeline = Boolean(
    process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET &&
    process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN && speechConfigured(),
  );
  if (!voicePipeline) return false;
  const provider = avatarProvider();
  if (provider === 'none') return true;
  if (provider === 'did') return didConfigured();
  return spatiusConfigured();
}

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    configured: isConfigured(),
    agentName: process.env.LIVEKIT_AGENT_NAME || 'sam-voice-agent',
    assistantName: (process.env.ASSISTANT_NAME || 'سام').trim(),
    llmProvider: 'Cloudflare Workers AI',
    llmModel: process.env.CLOUDFLARE_LLM_MODEL || '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
    llmMaxTokens: Number(process.env.CLOUDFLARE_LLM_MAX_TOKENS || 8192),
    cloudflareConfigured: Boolean(process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN),
    avatarEnabled: avatarEnabled(),
    avatarProvider: avatarProvider(),
    didConfigured: didConfigured(),
    didAgentId: process.env.DID_AGENT_ID || null,
    spatiusConfigured: spatiusConfigured(),
    spatiusAppId: process.env.SPATIUS_APP_ID || null,
    spatiusAvatarId: process.env.SPATIUS_AVATAR_ID || null,
    speechProvider: speechProvider(),
    speechConfigured: speechConfigured(),
    deepgramConfigured: Boolean(process.env.DEEPGRAM_API_KEY),
    googleTtsConfigured: Boolean(process.env.GOOGLE_API_KEY),
    sttModel: process.env.LIVEKIT_STT_MODEL || 'deepgram/nova-3',
    sttLanguage: process.env.LIVEKIT_STT_LANGUAGE || 'fa',
    ttsProvider: speechProvider() === 'direct' ? 'Google Gemini API' : 'LiveKit Inference',
    ttsModel: process.env.LIVEKIT_TTS_MODEL || 'google/gemini-3.8-flash-lite-tts',
    ttsVoice: process.env.LIVEKIT_TTS_VOICE || 'Charon',
    ttsLanguage: process.env.LIVEKIT_TTS_LANGUAGE || 'fa',
    livekitTtsConfigured: Boolean(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET),
    // RAG: the panel can only report the setting; the agent logs whether the
    // index actually loaded, since that is where chromadb lives.
    ragEnabled: /^(1|true|yes|on)$/i.test((process.env.RAG_ENABLED || '').trim()),
    ragDocsDir: process.env.RAG_DOCS_DIR || 'knowledge',
    ragTopK: Number(process.env.RAG_TOP_K || 3),
  });
});

app.post('/api/session', async (req, res) => {
  if (!isConfigured()) {
    const provider = avatarProvider();
    const parts = ['اطلاعات LiveKit و Cloudflare Workers AI'];
    if (provider === 'did') parts.push('D-ID (DID_API_KEY و DID_AGENT_ID)');
    if (provider === 'spatius') parts.push('Spatius');
    if (!speechConfigured()) {
      parts.push('کلیدهای گفتار (DEEPGRAM_API_KEY و GOOGLE_API_KEY برای SPEECH_PROVIDER=direct)');
    }
    return res.status(503).json({
      error: `برای شروع، ${parts.join('، ')} را در فایل .env تنظیم کنید.`,
    });
  }

  const roomName = `sam-${randomUUID().slice(0, 12)}`;
  const identity = `guest-${randomUUID().slice(0, 8)}`;
  const name = typeof req.body?.name === 'string' ? req.body.name.slice(0, 80) : 'دوست من';
  const openingLine = typeof req.body?.message === 'string' ? req.body.message.trim().slice(0, 300) : '';

  try {
    const livekitHost = process.env.LIVEKIT_URL.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://');
    const api = new LiveKitAPI({ host: livekitHost, apiKey: process.env.LIVEKIT_API_KEY, secret: process.env.LIVEKIT_API_SECRET });
    await api.room.createRoom({ name: roomName, emptyTimeout: 30, maxParticipants: 4 });
    await api.agentDispatch.createDispatch(roomName, process.env.LIVEKIT_AGENT_NAME || 'sam-voice-agent', {
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
      // The browser needs to know which renderer to prepare before connecting.
      avatarProvider: avatarProvider(),
      // These identifiers are public SDK configuration; SPATIUS_API_KEY stays server-side.
      spatiusAppId: process.env.SPATIUS_APP_ID,
      spatiusAvatarId: process.env.SPATIUS_AVATAR_ID,
    });
  } catch (error) {
    console.error('Could not start LiveKit session:', error);
    res.status(502).json({
      error: 'ساخت جلسه‌ی صوتی/تصویری ناموفق بود. تنظیمات LiveKit، Agent و Spatius را بررسی کنید.',
      details: process.env.NODE_ENV === 'production' ? undefined : (error instanceof Error ? error.message : String(error)),
    });
  }
});

// Every open room keeps its agent running, and each agent holds one STT and one
// TTS connection against the LiveKit Inference limit. Rooms left behind by a
// closed tab therefore start answering 429 for every new session, so give the
// page a way to shut them down.
app.post('/api/sessions/cleanup', async (_req, res) => {
  if (!(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET)) {
    return res.status(503).json({ error: 'اطلاعات LiveKit در فایل .env تنظیم نشده است.' });
  }
  try {
    const livekitHost = process.env.LIVEKIT_URL.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://');
    const api = new LiveKitAPI({ host: livekitHost, apiKey: process.env.LIVEKIT_API_KEY, secret: process.env.LIVEKIT_API_SECRET });
    const rooms = await api.room.listRooms();
    const stale = rooms.filter((room) => String(room.name || '').startsWith('sam-'));
    for (const room of stale) {
      await api.room.deleteRoom(room.name);
    }
    res.json({ closedRooms: stale.map((room) => room.name) });
  } catch (error) {
    console.error('Could not close stale sessions:', error);
    res.status(502).json({
      error: 'بستن نشست‌های باز ناموفق بود.',
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
