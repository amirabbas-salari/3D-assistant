import { Router } from 'express';

const router = Router();

function tavusEnv() {
  const apiKey = (process.env.TAVUS_API_KEY || '').trim();
  const replicaId = (process.env.TAVUS_REPLICA_ID || process.env.TAVUS_FACE_ID || '').trim();
  const personaId = (process.env.TAVUS_PERSONA_ID || process.env.TAVUS_PAL_ID || '').trim();
  const languagesRaw = (process.env.TAVUS_LANGUAGES || process.env.TAVUS_LANGUAGE || '').trim();
  const languages = languagesRaw ? languagesRaw.split(/[,\\s]+/).map(s=>s.trim()).filter(Boolean) : null;
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
  if (!apiKey) return res.status(503).json({ error: 'TAVUS_API_KEY در .env تنظیم نشده — از https://platform.tavus.io بگیرید و API را ری‌استارت کنید', hint: 'AVATAR_ENABLED=true و TAVUS_API_KEY و TAVUS_REPLICA_ID/TAVUS_PERSONA_ID را پر کنید' });
  if (!replicaId && !personaId) return res.status(503).json({ error: 'TAVUS_REPLICA_ID یا TAVUS_PERSONA_ID لازم است', hint: 'حداقل یکی از این‌ها را بگذارید — اگر persona شما default replica دارد فقط persona_id کافیست' });

  // Tavus docs: replica_id + persona_id (face_id/pal_id aliases removed — they cause 400)
  const body = {
    replica_id: replicaId || undefined,
    persona_id: personaId || undefined,
    conversation_name: (req.body?.conversation_name || `sam-${Date.now()}`).slice(0, 80),
  };

  const props = { ...(propertiesJson || {}), ...(req.body?.properties || {}) };
  if (languages && !props.languages) props.languages = languages;
  if (props.language && !props.languages) {
    props.languages = [props.language];
    delete props.language;
  }
  if (Object.keys(props).length) body.properties = props;

  const finalGreeting = (req.body?.custom_greeting || req.body?.greeting || greeting || undefined);
  if (finalGreeting) {
    body.custom_greeting = finalGreeting;
    body.properties = { ...(body.properties || {}), custom_greeting: finalGreeting };
  }
  const finalContext = (req.body?.conversational_context || req.body?.context || context || undefined);
  if (finalContext) {
    body.conversational_context = finalContext;
    body.properties = { ...(body.properties || {}), conversational_context: finalContext };
  }
  const finalCallback = req.body?.callback_url || callbackUrl || undefined;
  if (finalCallback) body.callback_url = finalCallback;

  for (const k of ['document_ids','document_tags','memory_stores','audio_only','require_auth','meeting_url','participant_name']) {
    if (req.body?.[k] !== undefined) body[k] = req.body[k];
  }

  try {
    // log outgoing body for debugging (without api key)
    console.log('[tavus] POST /v2/conversations', JSON.stringify({ ...body, replica_id: replicaId ? replicaId.slice(0,4)+'…' : undefined, persona_id: personaId ? personaId.slice(0,4)+'…' : undefined }));
    const r = await fetch('https://tavusapi.com/v2/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = data?.message || data?.error || data?.detail || `Tavus ${r.status}`;
      console.error('[tavus] error', r.status, msg, data);
      if (languages && /language|fa/i.test(String(msg))) {
        return res.status(r.status).json({
          error: `زبان ${languages.join(',')} توسط Tavus رد شد — fa به صورت رسمی پشتیبانی نمی‌شود. راه‌حل: TAVUS_LANGUAGES را خالی بگذارید و persona را در maker.tavus.io فارسی کنید`,
          details: data, tavusMessage: msg, status: r.status
        });
      }
      return res.status(r.status).json({ error: msg, details: data, status: r.status });
    }
    // Tavus returns snake_case
    if (!data.conversation_url) console.warn('[tavus] no conversation_url in response', data);
    res.json({
      conversationId: data.conversation_id,
      conversationUrl: data.conversation_url,
      conversation_url: data.conversation_url, // alias for compatibility
      status: data.status,
      replicaId: data.replica_id || data.face_id,
      personaId: data.persona_id || data.pal_id,
      languages: data.languages || props.languages || null,
    });
  } catch (e) {
    console.error('[tavus] fetch failed', e);
    res.status(502).json({ error: 'اتصال به Tavus ناموفق بود', details: e instanceof Error ? e.message : String(e) });
  }
});

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
