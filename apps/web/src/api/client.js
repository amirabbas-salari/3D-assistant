export async function fetchHealth() {
  const res = await fetch('/api/health');
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
export async function createSession(payload = {}) {
  const res = await fetch('/api/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail = [data.error, data.details].filter(Boolean).join('\n');
    throw new Error(detail || `ساخت جلسه ناموفق بود (HTTP ${res.status})`);
  }
  return data;
}
export async function cleanupSessions() {
  const res = await fetch('/api/sessions/cleanup', { method: 'POST' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error([data.error, data.details].filter(Boolean).join('\n') || `HTTP ${res.status}`);
  return data;
}
export async function createTavusConversation(payload = {}) {
  const res = await fetch('/api/tavus/conversation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error([data.error, data.details ? JSON.stringify(data.details) : ''].filter(Boolean).join('\n') || `HTTP ${res.status}`);
  return data;
}
export async function endTavusConversation(conversationId) {
  const res = await fetch(`/api/tavus/conversation/${encodeURIComponent(conversationId)}`, { method: 'DELETE' });
  const data = await res.json().catch(() => ({}));
  return data;
}
