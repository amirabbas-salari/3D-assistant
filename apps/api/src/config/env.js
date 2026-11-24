export function avatarEnabled() {
  return ['1','true','yes','on'].includes(String(process.env.AVATAR_ENABLED ?? 'false').trim().toLowerCase());
}
export function avatarProvider() {
  if (!avatarEnabled()) return 'none';
  const p = String(process.env.AVATAR_PROVIDER ?? 'spatius').trim().toLowerCase();
  if (['','none','off','false'].includes(p)) return 'none';
  if (['did','d-id','didid'].includes(p)) return 'did';
  return 'spatius';
}
export function speechProvider() {
  const p = String(process.env.SPEECH_PROVIDER ?? 'inference').trim().toLowerCase();
  return ['direct','byok','provider','own-keys'].includes(p) ? 'direct' : 'inference';
}
export function sttProvider() {
  const raw = String(process.env.STT_PROVIDER ?? '').trim().toLowerCase();
  if (raw) return ['direct','byok','provider','own-keys'].includes(raw) ? 'direct' : 'inference';
  return speechProvider();
}
const _ELEVEN = new Set(['elevenlabs','eleven','elevenlabs.io','eleven_flash_v2_5','eleven_flash_v2','eleven_turbo_v2_5','eleven_turbo_v2','eleven_multilingual_v2','eleven_multilingual_v1','eleven_v3','eleven_v4','eleven_v4_turbo']);
const _OR = new Set(['openrouter','or','open-router','open_router','elevenlabs/eleven-v3-conversational','eleven-v3-conversational','eleven_v3_conversational','conversational','or-conversational','cloudflare','cf','eleven-v3','elevenlabs/eleven-v3']);
export function ttsProvider() {
  const raw = String(process.env.TTS_PROVIDER ?? '').trim().toLowerCase();
  if (!raw) {
    if (['1','true','yes','on'].includes(String(process.env.OPENROUTER_TTS_ENABLED ?? process.env.CLOUDFLARE_TTS_ENABLED ?? '').trim().toLowerCase())) return 'openrouter';
    const p = String(process.env.SPEECH_PROVIDER ?? 'inference').trim().toLowerCase();
    if (_ELEVEN.has(p)) return 'elevenlabs';
    if (_OR.has(p) || ['openrouter','or','elevenlabs','eleven-v3-conversational','elevenlabs/eleven-v3-conversational'].includes(p)) return 'openrouter';
    return speechProvider();
  }
  if (_ELEVEN.has(raw)) return 'elevenlabs';
  if (_OR.has(raw) || ['openrouter','or','open_router','elevenlabs/eleven-v3-conversational','eleven-v3-conversational'].includes(raw)) return 'openrouter';
  if (['direct','byok','provider','own-keys'].includes(raw)) return 'direct';
  return 'inference';
}
export function cloudflareTtsConfigured() {
  return Boolean(process.env.OPENROUTER_API_KEY);
}
export function openrouterConfigured() {
  return Boolean(process.env.OPENROUTER_API_KEY);
}
export function llmProvider() {
  const raw = String(process.env.LLM_PROVIDER ?? '').trim().toLowerCase();
  if (['livekit','inference','lk','livekit-inference','livekit_inference'].includes(raw)) return 'livekit';
  if (['openrouter','or','open_router'].includes(raw)) return 'openrouter';
  if (['cloudflare','cf','workers','workers-ai'].includes(raw)) return 'cloudflare';
  if (process.env.OPENROUTER_API_KEY) return 'openrouter';
  if (process.env.CLOUDFLARE_API_TOKEN && process.env.CLOUDFLARE_ACCOUNT_ID) return 'cloudflare';
  return 'livekit';
}
export function speechConfigured() {
  if (speechProvider() === 'direct') return Boolean(process.env.DEEPGRAM_API_KEY && process.env.GOOGLE_API_KEY);
  return Boolean(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET);
}
export function didConfigured() { return Boolean(process.env.DID_API_KEY && process.env.DID_AGENT_ID); }
export function spatiusConfigured() { return Boolean(process.env.SPATIUS_API_KEY && process.env.SPATIUS_APP_ID && process.env.SPATIUS_AVATAR_ID); }
export function isConfigured() {
  const rawLlm = String(process.env.LLM_PROVIDER ?? '').trim().toLowerCase();
  const isLivekitLlm = ['livekit','inference','lk','livekit-inference','livekit_inference',''].includes(rawLlm);
  const hasLlm = Boolean(
    (isLivekitLlm && process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET) ||
    (process.env.OPENROUTER_API_KEY) ||
    (process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN)
  );
  const voice = Boolean(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET && hasLlm && speechConfigured());
  if (!voice) return false;
  const provider = avatarProvider();
  if (provider === 'none') return true;
  if (provider === 'did') return didConfigured();
  return spatiusConfigured();
}
