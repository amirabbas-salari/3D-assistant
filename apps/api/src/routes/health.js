import { Router } from 'express';
import { avatarEnabled, avatarProvider, tavusConfigured, speechProvider, sttProvider, ttsProvider, speechConfigured, cloudflareTtsConfigured, openrouterConfigured, llmProvider, isConfigured, livekitPublicUrl, livekitInternalUrl, isLocalLivekit } from '../config/env.js';
const router = Router();
router.get('/health', (_req, res) => {
  const _llmProv = llmProvider();
  const local = isLocalLivekit();
  const hint = local && _llmProv === 'livekit'
    ? 'هشدار: LiveKit لوکال Inference ندارد — LLM_PROVIDER را openrouter یا cloudflare بگذارید'
    : null;
  res.json({
    ok: true, configured: isConfigured(), hint,
    agentName: process.env.LIVEKIT_AGENT_NAME || 'sam-voice-agent',
    assistantName: (process.env.ASSISTANT_NAME || 'سام').trim(),
    livekitUrl: livekitPublicUrl(),
    livekitInternalUrl: livekitInternalUrl(),
    livekitLocal: local,
    llmProvider: _llmProv === 'openrouter' ? 'OpenRouter' : _llmProv === 'livekit' ? 'LiveKit Inference' : 'Cloudflare Workers AI',
    llmModel: _llmProv === 'openrouter'
      ? (process.env.OPENROUTER_LLM_MODEL || process.env.LLM_MODEL || 'openai/gpt-4o-mini')
      : _llmProv === 'livekit'
        ? (process.env.LIVEKIT_LLM_MODEL || process.env.LLM_MODEL || 'openai/gpt-4o-mini')
        : (process.env.CLOUDFLARE_LLM_MODEL || '@cf/meta/llama-3.3-70b-instruct-fp8-fast'),
    llmMaxTokens: Number(process.env.LIVEKIT_LLM_MAX_TOKENS || process.env.OPENROUTER_LLM_MAX_TOKENS || process.env.LLM_MAX_TOKENS || process.env.CLOUDFLARE_LLM_MAX_TOKENS || 120),
    cloudflareConfigured: Boolean(process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN),
    openrouterConfigured: openrouterConfigured(), openrouterTtsConfigured: openrouterConfigured(), openrouterLlmConfigured: openrouterConfigured(),
    avatarEnabled: avatarEnabled(), avatarProvider: avatarProvider(), tavusConfigured: tavusConfigured(), tavusReplicaId: process.env.TAVUS_REPLICA_ID || null, tavusPersonaId: process.env.TAVUS_PERSONA_ID || null,
    speechProvider: speechProvider(), sttProvider: sttProvider(), ttsProvider: ttsProvider(), speechConfigured: speechConfigured(), deepgramConfigured: Boolean(process.env.DEEPGRAM_API_KEY), googleTtsConfigured: Boolean(process.env.GOOGLE_API_KEY), cloudflareTtsConfigured: cloudflareTtsConfigured(),
    sttModel: process.env.LIVEKIT_STT_MODEL || 'deepgram/nova-3', sttLanguage: process.env.LIVEKIT_STT_LANGUAGE || 'fa',
    ttsProviderLabel: ttsProvider() === 'openrouter' ? 'OpenRouter (elevenlabs/eleven-v3-conversational)' : ttsProvider() === 'direct' ? 'Google Gemini API' : 'LiveKit Inference',
    ttsProviderLegacy: ttsProvider() === 'direct' ? 'Google Gemini API' : 'LiveKit Inference',
    ttsModel: ttsProvider() === 'openrouter' ? (process.env.OPENROUTER_TTS_MODEL || 'elevenlabs/eleven-v3-conversational') : (process.env.LIVEKIT_TTS_MODEL || 'google/gemini-3.8-flash-lite-tts'),
    ttsVoice: ttsProvider() === 'openrouter' ? (process.env.OPENROUTER_TTS_VOICE || process.env.ELEVENLABS_VOICE_ID || 'george') : (process.env.LIVEKIT_TTS_VOICE || 'Charon'), ttsLanguage: process.env.LIVEKIT_TTS_LANGUAGE || 'fa',
    livekitTtsConfigured: Boolean(livekitPublicUrl() && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET),
    ragEnabled: /^(1|true|yes|on)$/i.test((process.env.RAG_ENABLED || '').trim()), ragDocsDir: process.env.RAG_DOCS_DIR || 'knowledge', ragTopK: Number(process.env.RAG_TOP_K || 3),
  });
});
export default router;
