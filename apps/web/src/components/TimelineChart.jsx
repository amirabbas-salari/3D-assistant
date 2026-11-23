import React from 'react';
import { msLabel } from '../lib/latency.js';

// Color per stage — distinct, accessible
const STAGE_META = {
  response_delay: { label: 'پاسخ‌دهی', color: '#2e7d32', light: '#e8f5e9', icon: '⭐' },
  end_of_turn_delay: { label: 'تشخیص پایان', color: '#ef6c00', light: '#fff3e0' },
  transcription_delay: { label: 'STT نهایی', color: '#1565c0', light: '#e3f2fd' },
  llm_node_ttft: { label: 'اولین توکن', color: '#6a1b9a', light: '#f3e5f5' },
  llm_node_ttfs: { label: 'اولین جمله', color: '#ad1457', light: '#fce4ec' },
  knowledge_lookup: { label: 'RAG دانش', color: '#00796b', light: '#e0f2f1' },
  tts_node_ttfb: { label: 'صدای TTS', color: '#4527a0', light: '#ede7f6' },
  playback_latency: { label: 'پخش', color: '#283593', light: '#e8eaf6' },
};

const ORDER = ['end_of_turn_delay','transcription_delay','llm_node_ttft','llm_node_ttfs','knowledge_lookup','tts_node_ttfb','playback_latency'];

export default function TimelineChart({ latency }) {
  if (!latency?.last) return null;
  const { last, turns } = latency;
  const stages = last.stages || {};
  const e2e = last.e2e_ms || last.response_delay_ms || 1;
  // Filter to ordered stages that have value
  const segs = ORDER.filter(k => stages[k] != null).map(k => ({ key: k, val: stages[k], meta: STAGE_META[k] || { label: k, color: '#607d8b', light: '#eceff1' } }));
  if (segs.length === 0) return null;
  const sum = segs.reduce((s, x) => s + x.val, 0);
  const denom = Math.max(e2e, sum, 1);
  const isOverflow = sum > e2e * 1.05;

  return (
    <div className="timeline-chart">
      <div className="timeline-head">
        <span>تایم‌لاین پایپ‌لاین (نوبت #{last.index})</span>
        <span className="timeline-e2e">{msLabel(e2e)} سراسری</span>
      </div>

      {/* Waterfall bar */}
      <div className="timeline-bar" title={`e2e ${msLabel(e2e)} — جمع مراحل ${msLabel(sum)}${isOverflow ? ' (هم‌پوشانی دارد)' : ''}`}>
        {segs.map(s => {
          const w = Math.max(2, (s.val / denom) * 100);
          return (
            <div key={s.key} className="timeline-seg" style={{ width: `${w}%`, background: s.meta.color }} title={`${s.meta.label}: ${msLabel(s.val)}`}>
              <span className="seg-label">{s.meta.label}</span>
            </div>
          );
        })}
      </div>

      {/* Legend with ms */}
      <div className="timeline-legend">
        {segs.map(s => (
          <div key={s.key} className="legend-item">
            <i style={{ background: s.meta.color }} />
            <span>{s.meta.label}</span>
            <b>{msLabel(s.val)}</b>
          </div>
        ))}
        {stages.response_delay != null && (
          <div className="legend-item highlight">
            <i style={{ background: STAGE_META.response_delay.color }} />
            <span>پاسخ‌دهی ⭐</span>
            <b>{msLabel(stages.response_delay)}</b>
          </div>
        )}
      </div>

      {/* Turn history sparkline if we have averages */}
      {latency.averages && Object.keys(latency.averages).length > 0 && (
        <div className="timeline-avg">
          <small>میانگین {turns} نوبت — کندترین: {(() => {
            const avg = latency.averages;
            const top = Object.entries(avg).sort((a,b) => b[1]-a[1])[0];
            return top ? `${top[0]} ${msLabel(top[1])}` : '—';
          })()}</small>
        </div>
      )}

      <style>{`
        .timeline-chart { border:1px solid #edf0f3; border-radius:8px; overflow:hidden; background:#fff; margin-top:10px }
        .timeline-head { display:flex; justify-content:space-between; align-items:center; padding:8px 10px; font-size:10px; color:#5a6b7a; background:#f8f9fa; border-bottom:1px solid #edf0f3 }
        .timeline-head .timeline-e2e { font-family:ui-monospace,monospace; font-weight:700; color:#1b5e20; background:#e8f5e9; padding:2px 6px; border-radius:4px; border:1px solid #c8e6c9 }
        .timeline-bar { display:flex; height:32px; background:#f3f5f7; overflow:hidden; }
        .timeline-seg { display:flex; align-items:center; justify-content:center; min-width:20px; position:relative; transition:width .3s; }
        .seg-label { font-size:8px; color:#fff; font-weight:700; text-shadow:0 1px 2px rgba(0,0,0,.3); white-space:nowrap; padding:0 3px; overflow:hidden }
        .timeline-legend { display:grid; grid-template-columns:1fr 1fr; gap:5px; padding:8px 10px; }
        .legend-item { display:flex; align-items:center; gap:6px; font-size:9px; color:#4a5a6a; background:#f8f9fa; padding:4px 6px; border-radius:4px; border:1px solid #edf0f3 }
        .legend-item.highlight { background:#f1f8e9; border-color:#c8e6c9; }
        .legend-item i { width:10px; height:10px; border-radius:2px; flex:none }
        .legend-item b { margin-inline-start:auto; font-family:ui-monospace,monospace; font-size:9px; color:#25313d }
        .timeline-avg { padding:6px 10px; border-top:1px solid #edf0f3; background:#fafbfc; text-align:center }
        .timeline-avg small { font-size:9px; color:#6b7c8d }
      `}</style>
    </div>
  );
}
