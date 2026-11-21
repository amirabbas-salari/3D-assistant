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
export function ttsProvider() {
  const raw = String(process.env.TTS_PROVIDER ?? '').trim().toLowerCase();
  if (!raw) {
    if (['1','true','yes','on'].includes(String(process.env.CLOUDFLARE_TTS_ENABLED ?? '').trim().toLowerCase())) return 'cloudflare';
    const p = String(process.env.SPEECH_PROVIDER ?? 'inference').trim().toLowerCase();
    if (['cloudflare','cf','elevenlabs','eleven-v3','eleven_v3','elevenlabs/eleven-v3'].includes(p)) return 'cloudflare';
    return speechProvider();
  }
  if (['cloudflare','cf','elevenlabs','eleven-v3','eleven_v3','elevenlabs/eleven-v3'].includes(raw)) return 'cloudflare';
  if (['direct','byok','provider','own-keys'].includes(raw)) return 'direct';
  return 'inference';
}
export function cloudflareTtsConfigured() {
  return Boolean(process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN);
}
export function speechConfigured() {
  if (speechProvider() === 'direct') return Boolean(process.env.DEEPGRAM_API_KEY && process.env.GOOGLE_API_KEY);
  return Boolean(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET);
}
export function didConfigured() { return Boolean(process.env.DID_API_KEY && process.env.DID_AGENT_ID); }
export function spatiusConfigured() { return Boolean(process.env.SPATIUS_API_KEY && process.env.SPATIUS_APP_ID && process.env.SPATIUS_AVATAR_ID); }
export function isConfigured() {
  const voice = Boolean(process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET && process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN && speechConfigured());
  if (!voice) return false;
  const provider = avatarProvider();
  if (provider === 'none') return true;
  if (provider === 'did') return didConfigured();
  return spatiusConfigured();
}
