import { Router } from 'express';

const router = Router();

function tavusEnv() {
  const apiKey = (process.env.TAVUS_API_KEY || '').trim();
  // legacy: replica/persona, new: face/pal
  const replicaId = (process.env.TAVUS_REPLICA_ID || process.env.TAVUS_FACE_ID || '').trim();
  const personaId = (process.env.TAVUS_PERSONA_ID || process.env.TAVUS_PAL_ID || '').trim();
  // language override — مهم‌ترین فیکس انگلیسی بودن
  const languagesRaw = (process.env.TAVUS_LANGUAGES || process.env.TAVUS_LANGUAGE || '').trim();
  const languages = languagesRaw ? languagesRaw.split(/[,\s]+/).map(s=>s.trim()).filter(Boolean) : null;
  const greeting = (process.env.TAVUS_GREETING || process.env.TAVUS_CUSTOM_GREETING || process.env.TAVUS_CONVERSATION_GREETING || '').trim() || null;
  const context = (process.env.TAVUS_CONTEXT || process.env.TAVUS_CONVERSATIONAL_CONTEXT || '').trim() || null;
  let propertiesJson = null;
  const propsRaw = (process.env.TAVUS_PROPERTIES || process.env.TAVUS_PROPERTIES_JSON || '').trim();
  if (propsRaw) { try { propertiesJson = JSON.parse(propsRaw); } catch {} }
  const callbackUrl = (process.env.TAVUS_CALLBACK_URL || '').trim() || null;
  return { apiKey, replicaId, personaId, languages, greeting, context, propertiesJson, callbackUrl };
}

// POST /api/tavus/conversation — ساخت CVI conversation و برگرداندن Daily URL
router.post('/tavus/conversation', async (req, res) => {
  const { apiKey, replicaId, personaId, languages, greeting, context, propertiesJson, callbackUrl } = tavusEnv();
  if (!apiKey) return res.status(503).json({ error: 'TAVUS_API_KEY در .env تنظیم نشده' });
  if (!replicaId && !personaId) return res.status(503).json({ error: 'TAVUS_REPLICA_ID یا TAVUS_PERSONA_ID لازم است' });

  // body: legacy replica_id/persona_id همچنان کار می‌کند (docs: backward compatible)
  // اما اگر face_id/pal_id جدید دارید، آن هم می‌فرستیم
  const body = {
    replica_id: replicaId || undefined,
    persona_id: personaId || undefined,
    // new aliases (اگر Tavus فقط این‌ها را بخواند)
    ...(replicaId ? { face_id: replicaId } : {}),
    ...(personaId ? { pal_id: personaId } : {}),
    conversation_name: (req.body?.conversation_name || `sam-${Date.now()}`).slice(0, 80),
  };

  // --- language / greeting / context از env + request ---
  // اولویت: request body > env > persona default
  const props = { ...(propertiesJson || {}), ...(req.body?.properties || {}) };

  // languages: اگر env دارد، به properties.languages برود؛ اگر request هم دارد، request برنده است
  if (languages && !props.languages) props.languages = languages;
  // legacy single language → languages
  if (props.language && !props.languages) {
    props.languages = [props.language];
    delete props.language;
  }

  if (Object.keys(props).length) body.properties = props;

  // custom_greeting / conversational_context در سطح root هم پذیرفته می‌شوند
  const finalGreeting = (req.body?.custom_greeting || req.body?.greeting || greeting || undefined);
  if (finalGreeting) {
    body.custom_greeting = finalGreeting;
    body.properties = { ...(body.properties || {}), custom_greeting: finalGreeting };
  }
  const finalContext = (req.body?.conversational_context || req.body?.context || context || undefined);
  if (finalContext) {
    body.conversational_context = finalContext;
    // بعضی نسخه‌ها در properties می‌خواهند
    body.properties = { ...(body.properties || {}), conversational_context: finalContext };
  }

  const finalCallback = req.body?.callback_url || callbackUrl || undefined;
  if (finalCallback) body.callback_url = finalCallback;

  // passthrough برای فیلدهای اضافی مجاز Tavus (document_ids, audio_only, etc.)
  for (const k of ['document_ids','document_tags','memory_stores','audio_only','require_auth','meeting_url','participant_name']) {
    if (req.body?.[k] !== undefined) body[k] = req.body[k];
  }

  try {
    const r = await fetch('https://tavusapi.com/v2/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      // اگر fa پشتیبانی نشود Tavus با 400 برمی‌گردد — پیام فارسی بده
      const msg = data?.message || data?.error || 'Tavus error';
      if (languages && /language|fa/i.test(String(msg))) {
        return res.status(r.status).json({
          error: `زبان ${languages.join(',')} توسط Tavus رد شد — fa به صورت رسمی پشتیبانی نمی‌شود. راه‌حل: TAVUS_LANGUAGES را خالی بگذارید و persona را در maker.tavus.io فارسی کنید، یا از ElevenLabs TTS با صدای فارسی استفاده کنید.`,
          details: data, tavusMessage: msg
        });
      }
      return res.status(r.status).json({ error: msg, details: data });
    }

    res.json({
      conversationId: data.conversation_id,
      conversationUrl: data.conversation_url,
      status: data.status,
      replicaId: data.replica_id || data.face_id,
      personaId: data.persona_id || data.pal_id,
      languages: data.languages || props.languages || null,
    });
  } catch (e) {
    res.status(502).json({ error: 'اتصال به Tavus ناموفق بود', details: e instanceof Error ? e.message : String(e) });
  }
});

// DELETE /api/tavus/conversation/:id — پایان conversation (اختیاری)
router.delete('/tavus/conversation/:id', async (req, res) => {
  const { apiKey } = tavusEnv();
  if (!apiKey) return res.status(503).json({ error: 'TAVUS_API_KEY تنظیم نشده' });
  const id = req.params.id;
  try {
    const r = await fetch(`https://tavusapi.com/v2/conversations/${encodeURIComponent(id)}/end`, {
      method: 'POST',
      headers: { 'x-api-key': apiKey },
    });
    const data = await r.json().catch(() => ({}));
    res.json({ ok: r.ok, data });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
});

export default router;
