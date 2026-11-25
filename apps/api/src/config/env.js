export function avatarEnabled() {
  return ['1','true','yes','on'].includes(String(process.env.AVATAR_ENABLED ?? 'false').trim().toLowerCase());
}
export function avatarProvider() {
  if (!avatarEnabled()) return 'none';
  const p = String(process.env.AVATAR_PROVIDER ?? 'tavus').trim().toLowerCase();
  if (['','none','off','false'].includes(p)) return 'none';
  return 'tavus';
}
// ── LiveKit URLs ─────────────────────────────────────────────────────
// سه حالت:
//   Cloud:  LIVEKIT_URL=wss://proj.livekit.cloud  (کافی است)
//   لوکال بدون داکر: LIVEKIT_URL=ws://localhost:7880
//   لوکال با داکر:   LIVEKIT_PUBLIC_URL=ws://localhost:7880 (مرورگر)
//                   LIVEKIT_INTERNAL_URL=ws://livekit:7880 (سرور داخل داکر)
export function livekitPublicUrl() {
  return (process.env.LIVEKIT_PUBLIC_URL || process.env.LIVEKIT_URL || 'ws://localhost:7880').trim();
}
export function livekitInternalUrl() {
  return (process.env.LIVEKIT_INTERNAL_URL || process.env.LIVEKIT_URL_INTERNAL || process.env.LIVEKIT_URL || 'ws://localhost:7880').trim();
}
export function livekitApiKey() {
  return (process.env.LIVEKIT_API_KEY || '').trim();
}
export function livekitApiSecret() {
  return (process.env.LIVEKIT_API_SECRET || '').trim();
}
export function isLocalLivekit() {
  const u = (process.env.LIVEKIT_URL || process.env.LIVEKIT_PUBLIC_URL || process.env.LIVEKIT_INTERNAL_URL || '').toLowerCase();
  return u.includes('localhost') || u.includes('127.0.0.1') || u.includes('livekit:') || u.startsWith('ws://');
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
  if (isLocalLivekit() && !raw && !process.env.OPENROUTER_API_KEY && !(process.env.CLOUDFLARE_API_TOKEN && process.env.CLOUDFLARE_ACCOUNT_ID)) {
  }
  if (process.env.OPENROUTER_API_KEY) return 'openrouter';
  if (process.env.CLOUDFLARE_API_TOKEN && process.env.CLOUDFLARE_ACCOUNT_ID) return 'cloudflare';
  return 'livekit';
}
export function speechConfigured() {
  if (speechProvider() === 'direct') return Boolean(process.env.DEEPGRAM_API_KEY && process.env.GOOGLE_API_KEY);
  return Boolean(livekitInternalUrl() && livekitApiKey() && livekitApiSecret());
}
export function tavusConfigured() { return Boolean(process.env.TAVUS_API_KEY && (process.env.TAVUS_REPLICA_ID || process.env.TAVUS_PERSONA_ID || process.env.TAVUS_PAL_ID || process.env.TAVUS_FACE_ID)); }
// ── Tavus helpers ───────────────────────────────────────────────────
// مشکل رایج: persona انگلیسی + languages پیش‌فرض ["en"] → آواتار انگلیسی می‌شود
// برای فارسی باید یا persona در داشبورد فارسی شود، یا این envها پر شوند:
export function tavusLanguages() {
  // TAVUS_LANGUAGES=fa  یا  TAVUS_LANGUAGES=fa,en  یا  TAVUS_LANGUAGE=fa
  const raw = (process.env.TAVUS_LANGUAGES || process.env.TAVUS_LANGUAGE || '').trim();
  if (!raw) return null; // null = از تنظیمات persona استفاده کن (اگر persona فارسی نیست انگلیسی می‌ماند)
  return raw.split(/[,\s]+/).map(s=>s.trim()).filter(Boolean);
}
export function tavusGreeting() {
  return (process.env.TAVUS_GREETING || process.env.TAVUS_CUSTOM_GREETING || process.env.TAVUS_CONVERSATION_GREETING || '').trim() || null;
}
export function tavusContext() {
  return (process.env.TAVUS_CONTEXT || process.env.TAVUS_CONVERSATIONAL_CONTEXT || '').trim() || null;
}
export function tavusProperties() {
  // JSON خام برای override پیشرفته: TAVUS_PROPERTIES='{"languages":["fa"],"custom_greeting":"سلام!"}'
  const raw = (process.env.TAVUS_PROPERTIES || process.env.TAVUS_PROPERTIES_JSON || '').trim();
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}
export function tavusHints() {
  const hints = [];
  if (!avatarEnabled() || avatarProvider() !== 'tavus') return hints;
  if (!tavusConfigured()) {
    hints.push('TAVUS_API_KEY یا TAVUS_REPLICA_ID/TAVUS_PERSONA_ID تنظیم نشده');
    return hints;
  }
  const langs = tavusLanguages();
  // اگر هیچ language override نیست و persona انگلیسی باشد، Tavus انگلیسی می‌ماند
  if (!langs) {
    hints.push('TAVUS_LANGUAGES تنظیم نشده — اگر Persona در داشبورد انگلیسی باشد، آواتار انگلیسی صحبت می‌کند. برای فارسی: TAVUS_LANGUAGES=fa یا Persona را در maker.tavus.io فارسی کنید (system_prompt + languages)');
  } else if (!langs.some(l=>['fa','fa-ir','persian','ar','ur'].includes(l.toLowerCase()))) {
    hints.push(`TAVUS_LANGUAGES=${langs.join(',')} — اولین زبان، زبان شروع است. برای فارسی fa بگذارید`);
  }
  // fa به صورت رسمی در لیست 42 زبان Tavus نیست — ممکن است 400 بدهد، در این صورت persona باید فارسی باشد
  if (langs && langs.some(l=>l.toLowerCase()==='fa' || l.toLowerCase()==='fa-ir')) {
    hints.push('توجه: fa به صورت رسمی در 42 زبان Tavus لیست نشده — اگر 400 گرفتید، TAVUS_LANGUAGES را خالی بگذارید و persona را در داشبورد فارسی کنید، یا از TTS خارجی مثل ElevenLabs با صدای فارسی استفاده کنید');
  }
  return hints;
}
export function isConfigured() {
  const rawLlm = String(process.env.LLM_PROVIDER ?? '').trim().toLowerCase();
  const isLivekitLlm = ['livekit','inference','lk','livekit-inference','livekit_inference',''].includes(rawLlm);
  const hasLlm = Boolean(
    (isLivekitLlm && livekitInternalUrl() && livekitApiKey() && livekitApiSecret()) ||
    (process.env.OPENROUTER_API_KEY) ||
    (process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_API_TOKEN)
  );
  const voice = Boolean(livekitInternalUrl() && livekitApiKey() && livekitApiSecret() && hasLlm && speechConfigured());
  if (!voice) return false;
  const provider = avatarProvider();
  if (provider === 'none') return true;
  if (provider === 'tavus') return tavusConfigured();
  return false;
}
