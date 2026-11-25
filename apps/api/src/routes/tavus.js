import { Router } from 'express';

const router = Router();
function clean(v){ let s=String(v??'').trim(); if((s.startsWith('"')&&s.endsWith('"')&&s.length>=2)||(s.startsWith("'")&&s.endsWith("'")&&s.length>=2)) s=s.slice(1,-1).trim(); if((s.startsWith('"')||s.startsWith("'"))&&s.length>1&&!(s.endsWith('"')||s.endsWith("'"))) s=s.slice(1).trim(); return s; }
function tavusEnv() {
  const apiKey = clean(process.env.TAVUS_API_KEY || '');
  const replicaId = clean(process.env.TAVUS_REPLICA_ID || process.env.TAVUS_FACE_ID || '');
  const personaId = clean(process.env.TAVUS_PERSONA_ID || process.env.TAVUS_PAL_ID || '');
  const languagesRaw = clean(process.env.TAVUS_LANGUAGES || process.env.TAVUS_LANGUAGE || '');
  const languages = languagesRaw ? languagesRaw.split(/[,\\s]+/).map(s=>s.trim()).filter(Boolean) : null;
  const greeting = clean(process.env.TAVUS_GREETING || process.env.TAVUS_CUSTOM_GREETING || process.env.TAVUS_CONVERSATION_GREETING || '') || null;
  const context = clean(process.env.TAVUS_CONTEXT || process.env.TAVUS_CONVERSATIONAL_CONTEXT || '') || null;
  let propertiesJson = null;
  const propsRaw = clean(process.env.TAVUS_PROPERTIES || process.env.TAVUS_PROPERTIES_JSON || '');
  if (propsRaw) { try { propertiesJson = JSON.parse(propsRaw); } catch {} }
  const callbackUrl = clean(process.env.TAVUS_CALLBACK_URL || '') || null;
  return { apiKey, replicaId, personaId, languages, greeting, context, propertiesJson, callbackUrl };
}

router.post('/tavus/conversation', async (req, res) => {
  const { apiKey, replicaId, personaId, languages, greeting, context, propertiesJson, callbackUrl } = tavusEnv();
  if (!apiKey) return res.status(503).json({ error: 'TAVUS_API_KEY در .env تنظیم نشده — از https://platform.tavus.io بگیرید و API را ری‌استارت کنید', hint: 'AVATAR_ENABLED=true و TAVUS_API_KEY و TAVUS_REPLICA_ID/TAVUS_PERSONA_ID را پر کنید' });
  if (!replicaId && !personaId) return res.status(503).json({ error: 'TAVUS_REPLICA_ID یا TAVUS_PERSONA_ID لازم است', hint: 'حداقل یکی از این‌ها را بگذارید — اگر persona شما default replica دارد فقط persona_id کافیست' });

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
    if (!data.conversation_url) console.warn('[tavus] no conversation_url in response', data);
    res.json({
      conversationId: data.conversation_id,
      conversationUrl: data.conversation_url,
      conversation_url: data.conversation_url,
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
