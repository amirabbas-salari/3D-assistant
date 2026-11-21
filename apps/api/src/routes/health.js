import { Router } from 'express';
import { avatarEnabled, avatarProvider, didConfigured, spatiusConfigured, speechProvider, speechConfigured, isConfigured } from '../config/env.js';
const router = Router();
router.get('/health', (_req, res) => {
  res.json({
    ok: true, configured: isConfigured(),
    agentName: process.env.LIVEKIT_AGENT_NAME || 'sam-voice-agent',
    assistantName: (process.env.ASSISTANT_NAME || 'سام').trim(),
    llmProvider: 'Cloudflare Workers AI', llmModel: process.env.CLOUDFLARE_LLM_MODEL || '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
    llmMaxTokens: Number(process.env.CLOUDFLARE_LLM_MAX_TOKENS || 8192),
    cloudflareConfigured: Boolean(process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN),
    avatarEnabled: avatarEnabled(), avatarProvider: avatarProvider(), didConfigured: didConfigured(), didAgentId: process.env.DID_AGENT_ID || null,
    spatiusConfigured: spatiusConfigured(), spatiusAppId: process.env.SPATIUS_APP_ID || null, spatiusAvatarId: process.env.SPATIUS_AVATAR_ID || null,
    speechProvider: speechProvider(), speechConfigured: speechConfigured(), deepgramConfigured: Boolean(process.env.DEEPGRAM_API_KEY), googleTtsConfigured: Boolean(process.env.GOOGLE_API_KEY),
    sttModel: process.env.LIVEKIT_STT_MODEL || 'deepgram/nova-3', sttLanguage: process.env.LIVEKIT_STT_LANGUAGE || 'fa',
    ttsProvider: speechProvider() === 'direct' ? 'Google Gemini API' : 'LiveKit Inference',
    ttsModel: process.env.LIVEKIT_TTS_MODEL || 'google/gemini-3.8-flash-lite-tts', ttsVoice: process.env.LIVEKIT_TTS_VOICE || 'Charon', ttsLanguage: process.env.LIVEKIT_TTS_LANGUAGE || 'fa',
    livekitTtsConfigured: Boolean(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET),
    ragEnabled: /^(1|true|yes|on)$/i.test((process.env.RAG_ENABLED || '').trim()), ragDocsDir: process.env.RAG_DOCS_DIR || 'knowledge', ragTopK: Number(process.env.RAG_TOP_K || 3),
  });
});
export default router;
