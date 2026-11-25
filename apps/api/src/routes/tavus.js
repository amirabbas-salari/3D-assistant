import { Router } from 'express';

const router = Router();

function tavusEnv() {
  const apiKey = (process.env.TAVUS_API_KEY || '').trim();
  const replicaId = (process.env.TAVUS_REPLICA_ID || '').trim();
  const personaId = (process.env.TAVUS_PERSONA_ID || '').trim();
  return { apiKey, replicaId, personaId };
}

// POST /api/tavus/conversation — ساخت CVI conversation و برگرداندن Daily URL
router.post('/tavus/conversation', async (req, res) => {
  const { apiKey, replicaId, personaId } = tavusEnv();
  if (!apiKey) return res.status(503).json({ error: 'TAVUS_API_KEY در .env تنظیم نشده' });
  if (!replicaId && !personaId) return res.status(503).json({ error: 'TAVUS_REPLICA_ID یا TAVUS_PERSONA_ID لازم است' });

  const body = {
    replica_id: replicaId || undefined,
    persona_id: personaId || undefined,
    conversation_name: (req.body?.conversation_name || `sam-${Date.now()}`).slice(0, 80),
    // optional overrides from request
    ...(req.body?.properties ? { properties: req.body.properties } : {}),
    ...(req.body?.callback_url ? { callback_url: req.body.callback_url } : {}),
  };

  try {
    const r = await fetch('https://tavusapi.com/v2/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return res.status(r.status).json({ error: data?.message || data?.error || 'Tavus error', details: data });

    // data: { conversation_id, conversation_url (daily.co), status, ... }
    res.json({
      conversationId: data.conversation_id,
      conversationUrl: data.conversation_url,
      status: data.status,
      replicaId: data.replica_id,
      personaId: data.persona_id,
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
