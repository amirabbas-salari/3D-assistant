import React from 'react';
import { Activity } from 'lucide-react';
import { LATENCY_STAGES, msLabel } from '../lib/latency.js';

export default function StatusPanel({ health, latency, connected }) {
  return (
    <section className="panel status-panel">
      <div className="panel-heading"><div><Activity size={17} /><div><h2>اطلاعات اجرا</h2><small>بدون نمایش secretها</small></div></div></div>
      <div className="status-grid">
        <div><span>API</span><strong className={health?.configured ? 'status-good' : health ? 'status-bad' : ''}>{health ? (health.configured ? 'پیکربندی‌شده' : 'ناقص') : 'در حال بررسی'}</strong></div>
        <div><span>Agent</span><strong>{health?.agentName || 'نامشخص'}</strong></div>
        <div><span>نام دستیار</span><strong>{health?.assistantName || 'سام'}</strong></div>
        <div><span>LLM</span><strong>{health?.llmModel || 'LiveKit Inference'}</strong></div>
        <div><span>STT / TTS</span><strong>{health?.speechProvider === 'direct' ? 'Deepgram + Google (کلید مستقیم)' : health ? 'LiveKit Inference' : '—'}</strong></div>
        <div><span>پایگاه دانش</span><strong>{health ? (health.ragEnabled ? `روشن · top ${health.ragTopK}` : 'خاموش') : '—'}</strong></div>
        <div><span>اتاق</span><strong>{connected ? 'متصل' : '—'}</strong></div>
      </div>
      <p className="status-note">اطلاعات سلامت API فقط وجود تنظیمات سرور را بررسی می‌کند و اتصال واقعی Spatius یا مدل را تضمین نمی‌کند.</p>
      {latency && latency.last && (
        <div className="latency-block">
          <div className="latency-head"><span>زمان‌بندی آخرین نوبت</span><strong>{msLabel(latency.last.e2e_ms)}</strong></div>
          {(latency.last.response_delay_ms ?? latency.last.stages?.response_delay) != null && (
            <div className="latency-highlight" style={{ background: 'linear-gradient(135deg,#e8f5e9,#f1f8e9)', border: '1.5px solid #4caf50', borderRadius: '10px', padding: '10px 12px', margin: '8px 0 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, color: '#2e7d32', fontSize: '13px' }}>⏱ پایان سوال → شروع پاسخ</span>
              <strong style={{ color: '#1b5e20', fontSize: '18px' }}>{msLabel(latency.last.response_delay_ms ?? latency.last.stages.response_delay)}</strong>
            </div>
          )}
          {LATENCY_STAGES.map(([key, label]) => (
            latency.last.stages[key] == null ? null : (
              <div className="latency-row" key={key} style={key === 'response_delay' ? { background: '#f9fff9', borderRadius: '6px', padding: '2px 6px', border: '1px solid #c8e6c9' } : undefined}>
                <span>{label}{key === 'response_delay' ? ' ⭐' : ''}</span>
                <div className="latency-bar"><i style={{ width: `${Math.min(100, ((latency.last.stages[key] || 0) / Math.max(latency.last.e2e_ms || latency.last.response_delay_ms || 1, 1)) * 100)}%`, background: key === 'response_delay' ? '#4caf50' : undefined }} /></div>
                <b>{msLabel(latency.last.stages[key])}</b>
              </div>
            )
          ))}
          <small>{latency.turns} نوبت اندازه‌گیری‌شده</small>
        </div>
      )}
    </section>
  );
}
