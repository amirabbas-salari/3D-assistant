import React from 'react';
import { Activity, Database, Layers, Zap } from 'lucide-react';
import { LATENCY_STAGES, msLabel } from '../lib/latency.js';
import TimelineChart from './TimelineChart.jsx';

export default function StatusPanel({ health, latency, connected }) {
  return (
    <section className="panel status-panel">
      <div className="panel-heading"><div><Activity size={17} /><div><h2>اطلاعات اجرا</h2><small>بدون نمایش secretها</small></div></div></div>
      <div className="status-grid">
        <div><span>API</span><strong className={health?.configured ? 'status-good' : health ? 'status-bad' : ''}>{health ? (health.configured ? 'پیکربندی‌شده' : 'ناقص') : 'در حال بررسی'}</strong></div>
        <div><span>Agent</span><strong>{health?.agentName || 'نامشخص'}</strong></div>
        <div><span>نام دستیار</span><strong>{health?.assistantName || 'سام'}</strong></div>
        <div><span>LLM</span><strong>{health?.llmModel || 'LiveKit Inference'}</strong></div>
        <div><span>STT / TTS</span><strong>{health?.ttsProviderLabel || (health?.speechProvider === 'direct' ? 'Deepgram + Google (کلید مستقیم)' : health ? 'LiveKit Inference' : '—')}</strong></div>
        <div className={health?.ragEnabled ? 'rag-on' : ''}><span><Database size={10} style={{display:'inline',verticalAlign:'middle',marginLeft:4}}/>پایگاه دانش</span><strong>{health ? (health.ragEnabled ? `روشن · Chroma + BM25 · top ${health.ragTopK}` : 'خاموش') : '—'}</strong>{health?.ragEnabled && <small style={{color:'#00796b',fontSize:'8px',marginTop:2,display:'block'}}><Layers size={8} style={{display:'inline',verticalAlign:'middle',marginLeft:3}}/>پرسش → جستجوی BM25 → تزریق به پرامپت</small>}</div>
        <div><span>اتاق</span><strong>{connected ? 'متصل' : '—'}</strong></div>
      </div>
      {/* RAG tech badge */}
      {health?.ragEnabled && (
        <div style={{margin:'0 13px 10px', padding:'8px 10px', background:'linear-gradient(135deg,#e0f2f1,#f1f8e9)', border:'1px solid #b2dfdb', borderRadius:'8px', display:'flex', alignItems:'center', gap:'8px', fontSize:'10px', color:'#004d40'}}>
          <Database size={14} style={{color:'#00796b'}}/>
          <div style={{flex:1}}>
            <strong style={{fontSize:'10px'}}>RAG فعال — Chroma + BM25</strong>
            <div style={{fontSize:'8.5px', color:'#2e7d32', marginTop:1}}>پرسش فارسی → نرمال‌سازی → رتبه‌بندی BM25 → تزریق به LLM (بدون API خارجی)</div>
          </div>
          <span style={{background:'#00796b', color:'#fff', padding:'2px 6px', borderRadius:'4px', fontSize:'8px', fontWeight:700}}>BM25</span>
          <span style={{background:'#4527a0', color:'#fff', padding:'2px 6px', borderRadius:'4px', fontSize:'8px', fontWeight:700}}>Chroma</span>
        </div>
      )}
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
      {/* Timeline waterfall */}
      {latency && <TimelineChart latency={latency} />}
      {latency?.averages && Object.keys(latency.averages).length > 0 && (
        <div style={{margin:'10px 13px 0', padding:'8px 10px', background:'#f8f9fa', border:'1px solid #edf0f3', borderRadius:'6px', fontSize:'9px', color:'#5a6b7a'}}>
          <div style={{display:'flex', alignItems:'center', gap:6, marginBottom:4}}><Zap size={12} style={{color:'#ef6c00'}}/><strong>میانگین {latency.turns} نوبت</strong></div>
          <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:4}}>
            {Object.entries(latency.averages).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([k,v])=>(
              <span key={k} style={{background:'#fff', padding:'3px 6px', borderRadius:'4px', border:'1px solid #edf0f3'}}>{LATENCY_STAGES.find(x=>x[0]===k)?.[1]||k}: <b style={{fontFamily:'monospace', color:'#263238'}}>{msLabel(v)}</b></span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
