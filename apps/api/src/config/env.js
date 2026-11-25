function clean(v) {
  let s = String(v ?? '').trim();
  if ((s.startsWith('"') && s.endsWith('"') && s.length >= 2) || (s.startsWith("'") && s.endsWith("'") && s.length >= 2)) s = s.slice(1, -1).trim();
  if ((s.startsWith('"') || s.startsWith("'")) && s.length > 1 && !(s.endsWith('"') || s.endsWith("'"))) s = s.slice(1).trim();
  return s;
}
export function avatarEnabled() {
  return ['1','true','yes','on'].includes(clean(process.env.AVATAR_ENABLED ?? 'false').toLowerCase());
}
export function avatarProvider() {
  if (!avatarEnabled()) return 'none';
  const p = clean(process.env.AVATAR_PROVIDER ?? 'tavus').toLowerCase();
  if (['','none','off','false'].includes(p)) return 'none';
  if (['spatius','spatius-avatar','spatius_avatar','avatar'].includes(p)) return 'spatius';
  if (['tavus','tavus-cvi','cvi','daily','tavus-livekit','livekit','tavus_auto'].includes(p)) return 'tavus';
  if (['did','d-id','heygen','hedra'].includes(p)) return p;
  return p;
}
export function tavusAvatarMode() {
  const m = clean(process.env.TAVUS_AVATAR_MODE || process.env.TAVUS_MODE || 'livekit').toLowerCase();
  if (['cvi','daily','iframe'].includes(m)) return 'cvi';
  return 'livekit'; // livekit = lip-sync to project's TTS (recommended)
}
export function speechProvider() {
  const p = clean(process.env.SPEECH_PROVIDER ?? 'inference').toLowerCase();
  return ['direct','byok','provider','own-keys'].includes(p) ? 'direct' : 'inference';
}
export function sttProvider() {
  const raw = clean(process.env.STT_PROVIDER ?? '').toLowerCase();
  if (raw) return ['direct','byok','provider','own-keys'].includes(raw) ? 'direct' : 'inference';
  return speechProvider();
}
const _ELEVEN = new Set(['elevenlabs','eleven','elevenlabs.io','eleven_flash_v2_5','eleven_flash_v2','eleven_turbo_v2_5','eleven_turbo_v2','eleven_multilingual_v2','eleven_multilingual_v1','eleven_v3','eleven_v4','eleven_v4_turbo']);
const _OR = new Set(['openrouter','or','open-router','open_router','elevenlabs/eleven-v3-conversational','eleven-v3-conversational','eleven_v3_conversational','conversational','or-conversational','cloudflare','cf','eleven-v3','elevenlabs/eleven-v3-conversational']);
export function ttsProvider() {
  const raw = clean(process.env.TTS_PROVIDER ?? '').toLowerCase();
  if (!raw) {
    if (['1','true','yes','on'].includes(clean(process.env.OPENROUTER_TTS_ENABLED ?? process.env.CLOUDFLARE_TTS_ENABLED ?? '').toLowerCase())) return 'openrouter';
    const p = clean(process.env.SPEECH_PROVIDER ?? 'inference').toLowerCase();
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
  return Boolean(clean(process.env.OPENROUTER_API_KEY));
}
export function openrouterConfigured() {
  return Boolean(clean(process.env.OPENROUTER_API_KEY));
}
export function llmProvider() {
  const raw = clean(process.env.LLM_PROVIDER ?? '').toLowerCase();
  if (['livekit','inference','lk','livekit-inference','livekit_inference'].includes(raw)) return 'livekit';
  if (['openrouter','or','open_router'].includes(raw)) return 'openrouter';
  if (['cloudflare','cf','workers','workers-ai'].includes(raw)) return 'cloudflare';
  if (clean(process.env.OPENROUTER_API_KEY)) return 'openrouter';
  if (clean(process.env.CLOUDFLARE_API_TOKEN) && clean(process.env.CLOUDFLARE_ACCOUNT_ID)) return 'cloudflare';
  return 'livekit';
}
export function speechConfigured() {
  if (speechProvider() === 'direct') return Boolean(clean(process.env.DEEPGRAM_API_KEY) && clean(process.env.GOOGLE_API_KEY));
  return Boolean(clean(process.env.LIVEKIT_URL) && clean(process.env.LIVEKIT_API_KEY) && clean(process.env.LIVEKIT_API_SECRET));
}
export function tavusConfigured() { return Boolean(clean(process.env.TAVUS_API_KEY) && (clean(process.env.TAVUS_REPLICA_ID) || clean(process.env.TAVUS_PERSONA_ID) || clean(process.env.TAVUS_PAL_ID) || clean(process.env.TAVUS_FACE_ID))); }
// ── Tavus helpers ───────────────────────────────────────────────────
export function tavusLanguages() {
  const raw = clean(process.env.TAVUS_LANGUAGES || process.env.TAVUS_LANGUAGE || '');
  if (!raw) return null;
  return raw.split(/[,\\s]+/).map(s=>s.trim()).filter(Boolean);
}
export function tavusGreeting() {
  return clean(process.env.TAVUS_GREETING || process.env.TAVUS_CUSTOM_GREETING || process.env.TAVUS_CONVERSATION_GREETING || '') || null;
}
export function tavusContext() {
  return clean(process.env.TAVUS_CONTEXT || process.env.TAVUS_CONVERSATIONAL_CONTEXT || '') || null;
}
export function tavusProperties() {
  const raw = clean(process.env.TAVUS_PROPERTIES || process.env.TAVUS_PROPERTIES_JSON || '');
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
  const mode = tavusAvatarMode();
  if (mode === 'cvi') hints.push('حالت CVI/Daily فعال است — آواتار مستقل کار می‌کند (LLM/TTS خودش). برای لب‌زدن به TTS پروژه، TAVUS_AVATAR_MODE=livekit بگذارید');
  const langs = tavusLanguages();
  if (!langs) {
    // livekit mode: زبان از LiveKit TTS می‌آید، hint کمتر مهم
    if (mode === 'cvi') hints.push('TAVUS_LANGUAGES تنظیم نشده — اگر Persona در داشبورد انگلیسی باشد، آواتار انگلیسی صحبت می‌کند. برای فارسی: TAVUS_LANGUAGES=fa یا Persona را در maker.tavus.io فارسی کنید (system_prompt + languages)');
  } else if (!langs.some(l=>['fa','fa-ir','persian','ar','ur'].includes(l.toLowerCase()))) {
    hints.push(`TAVUS_LANGUAGES=${langs.join(',')} — اولین زبان، زبان شروع است. برای فارسی fa بگذارید`);
  }
  if (langs && langs.some(l=>l.toLowerCase()==='fa' || l.toLowerCase()==='fa-ir')) {
    hints.push('توجه: fa به صورت رسمی در 42 زبان Tavus لیست نشده — اگر 400 گرفتید، TAVUS_LANGUAGES را خالی بگذارید و persona را در داشبورد فارسی کنید، یا از TTS خارجی مثل ElevenLabs با صدای فارسی استفاده کنید');
  }
  return hints;
}
// ── Spatius helpers ─────────────────────────────────────────────────
export function spatiusConfigured() {
  return Boolean(clean(process.env.SPATIUS_API_KEY) && clean(process.env.SPATIUS_APP_ID) && clean(process.env.SPATIUS_AVATAR_ID));
}
export function spatiusHints() {
  const hints = [];
  if (!avatarEnabled() || avatarProvider() !== 'spatius') return hints;
  if (!spatiusConfigured()) {
    if (!clean(process.env.SPATIUS_API_KEY)) hints.push('SPATIUS_API_KEY تنظیم نشده — از https://app.spatius.ai/apps بگیرید');
    if (!clean(process.env.SPATIUS_APP_ID)) hints.push('SPATIUS_APP_ID تنظیم نشده');
    if (!clean(process.env.SPATIUS_AVATAR_ID)) hints.push('SPATIUS_AVATAR_ID تنظیم نشده — از https://app.spatius.ai/avatars/library انتخاب کنید');
    return hints;
  }
  const fmt = clean(process.env.SPATIUS_AUDIO_FORMAT || 'pcm_s16le').toLowerCase();
  const sr = clean(process.env.SPATIUS_SAMPLE_RATE || '24000');
  if (fmt === 'ogg_opus' && !['8000','12000','16000','24000','48000'].includes(sr)) {
    hints.push(`SPATIUS_AUDIO_FORMAT=ogg_opus فقط نرخ‌های 8000,12000,16000,24000,48000 را می‌پذیرد — شما ${sr} گذاشتید. pcm_s16le بگذارید یا نرخ را تغییر دهید`);
  }
  if (!clean(process.env.SPATIUS_REGION)) {
    // auto is fine, no hint
  }
  return hints;
}
export function isConfigured() {
  const rawLlm = clean(process.env.LLM_PROVIDER ?? '').toLowerCase();
  const isLivekitLlm = ['livekit','inference','lk','livekit-inference','livekit_inference',''].includes(rawLlm);
  const hasLlm = Boolean(
    (isLivekitLlm && clean(process.env.LIVEKIT_URL) && clean(process.env.LIVEKIT_API_KEY) && clean(process.env.LIVEKIT_API_SECRET)) ||
    (clean(process.env.OPENROUTER_API_KEY)) ||
    (clean(process.env.CLOUDFLARE_ACCOUNT_ID) && clean(process.env.CLOUDFLARE_API_TOKEN))
  );
  const voice = Boolean(clean(process.env.LIVEKIT_URL) && clean(process.env.LIVEKIT_API_KEY) && clean(process.env.LIVEKIT_API_SECRET) && hasLlm && speechConfigured());
  if (!voice) return false;
  const provider = avatarProvider();
  if (provider === 'none') return true;
  if (provider === 'tavus') return tavusConfigured();
  if (provider === 'spatius') return spatiusConfigured();
  return false;
}
