import React from 'react';
import { msLabel } from '../lib/latency.js';

const STAGE_META = {
  end_of_turn_delay: { label: 'تشخیص پایان نوبت', short: 'Endpointing', color: '#ef6c00', bg: '#fff3e0', border: '#ffcc80' },
  transcription_delay: { label: 'STT نهایی', short: 'STT', color: '#1565c0', bg: '#e3f2fd', border: '#90caf9' },
  knowledge_lookup: { label: 'RAG دانش', short: 'RAG', color: '#00796b', bg: '#e0f2f1', border: '#80cbc4' },
  llm_node_ttft: { label: 'اولین توکن LLM', short: 'TTFT', color: '#6a1b9a', bg: '#f3e5f5', border: '#ce93d8' },
  llm_node_ttfs: { label: 'اولین جمله → TTS', short: 'TTFS', color: '#ad1457', bg: '#fce4ec', border: '#f48fb1' },
  tts_node_ttfb: { label: 'اولین بایت صدا', short: 'TTS', color: '#4527a0', bg: '#ede7f6', border: '#b39ddb' },
  playback_latency: { label: 'شروع پخش', short: 'Playback', color: '#283593', bg: '#e8eaf6', border: '#9fa8da' },
};

const PIPELINE_ORDER = [
  'end_of_turn_delay',
  'transcription_delay',
  'knowledge_lookup',
  'llm_node_ttft',
  'llm_node_ttfs',
  'tts_node_ttfb',
  'playback_latency',
];

function toNum(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function computeSpans(last) {
  try {
    const stages = last?.stages || {};
    const e2eRaw = last?.e2e_ms ?? last?.response_delay_ms ?? null;
    const e2e = e2eRaw != null ? toNum(e2eRaw, null) : null;
    const llmStart = Math.max(toNum(stages.end_of_turn_delay, 0), toNum(stages.transcription_delay, 0));

    const spans = [];
    for (const key of PIPELINE_ORDER) {
      const raw = stages[key];
      if (raw == null) continue;
      const dur = toNum(raw, null);
      if (dur == null || !Number.isFinite(dur) || dur < 0) continue;
      let start = 0;
      if (key === 'end_of_turn_delay' || key === 'transcription_delay') start = 0;
      else if (key === 'knowledge_lookup' || key === 'llm_node_ttft' || key === 'llm_node_ttfs') start = llmStart;
      else if (key === 'tts_node_ttfb') start = llmStart + toNum(stages.llm_node_ttfs ?? stages.llm_node_ttft ?? 0, 0);
      else if (key === 'playback_latency') {
        const ttsStart = llmStart + toNum(stages.llm_node_ttfs ?? stages.llm_node_ttft ?? 0, 0);
        start = ttsStart + toNum(stages.tts_node_ttfb, 0);
      }
      if (!Number.isFinite(start)) start = 0;
      const end = start + dur;
      const meta = STAGE_META[key] || { label: key, short: key, color: '#607d8b', bg: '#eceff1', border: '#cfd8dc' };
      spans.push({ key, label: meta.label, short: meta.short, color: meta.color, bg: meta.bg, border: meta.border, start, end, dur });
    }
    const ends = spans.map(s => s.end);
    const maxFromSpans = ends.length ? Math.max(...ends) : 0;
    const maxEnd = Math.max(1, maxFromSpans, e2e != null && Number.isFinite(e2e) ? e2e : 0);
    return { stages, e2e, maxEnd, spans, llmStart };
  } catch (e) {
    console.error('[TimelineChart computeSpans]', e);
    return { stages: {}, e2e: null, maxEnd: 1, spans: [], llmStart: 0 };
  }
}

export default function TimelineChart({ latency }) {
  // هیچ latency هنوز نیامده → کارت خالی ولی بدون کرش
  if (!latency?.last) {
    return (
      <section className="panel gantt-panel gantt-empty">
        <div className="panel-heading">
          <div>
            <span style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: 8, background: '#eef2f7', color: '#4a6fa5' }}>▦</span>
            <div><h2>گانت پایپ‌لاین صوت</h2><small>از پایان سوال تا شروع پاسخ — بازه‌ی هر مرحله</small></div>
          </div>
          <span className="mode-tag">منتظر اولین نوبت</span>
        </div>
        <div style={{ padding: '22px 16px', textAlign: 'center', color: '#7a8a9a', fontSize: 11, lineHeight: 1.9 }}>
          هنوز نوبتی ثبت نشده — پس از اولین پیام (صوتی یا متنی) اینجا هر مرحله را با بازه‌ی <b>«از X تا Y»</b> می‌بینی.
          <div style={{ marginTop: 10, display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
            {Object.values(STAGE_META).slice(0, 4).map(m => (
              <span key={m.short} style={{ background: m.bg, border: `1px solid ${m.border}`, color: m.color, padding: '2px 7px', borderRadius: 999, fontSize: 9, fontWeight: 700 }}>{m.short}</span>
            ))}
          </div>
        </div>
        <style>{ganttCss}</style>
      </section>
    );
  }

  let e2e, maxEnd, spans, llmStart;
  try {
    ({ e2e, maxEnd, spans, llmStart } = computeSpans(latency.last));
  } catch (err) {
    console.error('[TimelineChart]', err);
    return (
      <section className="panel gantt-panel">
        <div style={{ padding: 12, fontSize: 11, color: '#8a4444' }}>خطا در نمایش گانت — لاگ مرورگر را چک کن.</div>
        <style>{ganttCss}</style>
      </section>
    );
  }

  const turns = latency.turns ?? 0;
  const safeMaxEnd = Number.isFinite(maxEnd) && maxEnd > 0 ? maxEnd : 1;
  const tickVals = [0, safeMaxEnd * 0.25, safeMaxEnd * 0.5, safeMaxEnd * 0.75, safeMaxEnd];

  return (
    <section className="panel gantt-panel">
      <div className="panel-heading">
        <div>
          <span style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: 8, background: '#e8f0fe', color: '#2857a5', fontWeight: 800, fontSize: 11 }}>◧</span>
          <div><h2>گانت پایپ‌لاین — نوبت #{latency.last?.index ?? '—'}</h2><small>محور زمان: ۰ = پایان صحبت کاربر → {msLabel(safeMaxEnd)} سراسری</small></div>
        </div>
        <span className="gantt-e2e-badge" title={`e2e ${msLabel(e2e)} · max end ${msLabel(safeMaxEnd)}`}>{msLabel(e2e ?? safeMaxEnd)} سراسری</span>
      </div>

      <div className="gantt-axis">
        <div className="gantt-axis-track">
          {tickVals.map((v, i) => {
            const pct = Number.isFinite(v) && Number.isFinite(safeMaxEnd) ? (v / safeMaxEnd) * 100 : 0;
            return (
              <span key={i} className="gantt-tick" style={{ left: `${pct}%` }}>
                <i />
                <b>{i === 0 ? '۰' : msLabel(v)}</b>
              </span>
            );
          })}
          {e2e != null && Number.isFinite(e2e) && <span className="gantt-e2e-line" style={{ left: `${Math.min(100, (e2e / safeMaxEnd) * 100)}%` }} title={`پایان سراسری: ${msLabel(e2e)}`} />}
        </div>
        <div className="gantt-axis-labels">
          <span>شروع (پایان سوال)</span>
          <span>پایان (شروع پخش)</span>
        </div>
      </div>

      <div className="gantt-rows">
        {spans.length === 0 && <div style={{ padding: '10px 4px', fontSize: 10, color: '#6b7c8d', textAlign: 'center' }}>دادهٔ مرحله‌ای برای این نوبت ثبت نشد.</div>}
        {spans.map(s => {
          const leftPct = Number.isFinite(s.start) && Number.isFinite(safeMaxEnd) ? (s.start / safeMaxEnd) * 100 : 0;
          const widthPct = Number.isFinite(s.dur) && Number.isFinite(safeMaxEnd) ? Math.max(1.2, (s.dur / safeMaxEnd) * 100) : 1.2;
          const pctOfTotal = safeMaxEnd ? ((s.dur / safeMaxEnd) * 100).toFixed(1) : '0';
          const isNarrow = widthPct < 12;
          // clamp تا بیرون نزند
          const clampedLeft = Math.max(0, Math.min(100, leftPct));
          const clampedWidth = Math.max(1.2, Math.min(100 - clampedLeft, widthPct));
          return (
            <div key={s.key} className="gantt-row">
              <div className="gantt-label">
                <i style={{ background: s.color }} />
                <div>
                  <strong>{s.label}</strong>
                  <small>{s.short}</small>
                </div>
              </div>
              <div className="gantt-track">
                <div className="gantt-grid">
                  {[25, 50, 75].map(p => <span key={p} style={{ left: `${p}%` }} />)}
                </div>
                <div
                  className="gantt-bar"
                  style={{ left: `${clampedLeft}%`, width: `${clampedWidth}%`, background: s.color, borderColor: s.border, boxShadow: `0 1px 6px ${s.color}33` }}
                  title={`${s.label}: ${msLabel(s.start)} → ${msLabel(s.end)} (طول ${msLabel(s.dur)} · ${pctOfTotal}% کل)`}
                >
                  {!isNarrow && <span className="gantt-bar-text">{msLabel(s.dur)}</span>}
                </div>
                {isNarrow && <span className="gantt-bar-outside" style={{ left: `calc(${clampedLeft + clampedWidth}% + 6px)`, color: s.color }}>{msLabel(s.dur)}</span>}
                <span className="gantt-range-hint">{msLabel(s.start)} → {msLabel(s.end)}</span>
              </div>
              <div className="gantt-time">
                <b>{msLabel(s.dur)}</b>
                <small>{msLabel(s.start)} → {msLabel(s.end)}</small>
              </div>
            </div>
          );
        })}
      </div>

      <div className="gantt-footer">
        <div className="gantt-summary">
          <span>شروع LLM پس از <b>{msLabel(llmStart)}</b> (max تشخیص/STT)</span>
          <span>·</span>
          <span>{turns} نوبت ثبت‌شده</span>
          {latency.averages && Object.keys(latency.averages).length > 0 && (
            <>
              <span>·</span>
              <span>کندترین میانگین: <b>{(() => {
                try {
                  const top = Object.entries(latency.averages).sort((a, b) => toNum(b[1], 0) - toNum(a[1], 0))[0];
                  return top ? `${STAGE_META[top[0]]?.label || top[0]} ${msLabel(top[1])}` : '—';
                } catch { return '—'; }
              })()}</b></span>
            </>
          )}
        </div>
        <div className="gantt-legend">
          {spans.map(s => (
            <span key={s.key} className="gantt-legend-item"><i style={{ background: s.color }} />{s.short}</span>
          ))}
        </div>
      </div>

      <style>{ganttCss}</style>
    </section>
  );
}

const ganttCss = `
.gantt-panel{ overflow:hidden; }
.gantt-panel .panel-heading{ gap:12px }
.gantt-e2e-badge{ font-family:ui-monospace,monospace; font-weight:800; font-size:11px; color:#1b5e20; background:linear-gradient(135deg,#e8f5e9,#f1f8e9); padding:5px 10px; border-radius:999px; border:1px solid #aed581; white-space:nowrap }
.gantt-empty{ border-style:dashed }
.gantt-axis{ padding:10px 14px 6px; background:#fafbfc; border-bottom:1px solid #edf0f3 }
.gantt-axis-track{ position:relative; height:18px; background:#fff; border:1px solid #e6ebf0; border-radius:6px; overflow:hidden }
.gantt-tick{ position:absolute; top:0; bottom:0; display:flex; flex-direction:column; align-items:center; transform:translateX(-50%) }
.gantt-tick i{ width:1px; height:100%; background:#e6ebf0; display:block }
.gantt-tick b{ position:absolute; top:1px; font-size:8px; font-weight:700; color:#5a6b7a; background:#fff; padding:0 3px; border-radius:3px; white-space:nowrap; font-family:ui-monospace,monospace }
.gantt-e2e-line{ position:absolute; top:0; bottom:0; width:2px; background:#2e7d32; opacity:.9; transform:translateX(-50%) }
.gantt-e2e-line::after{ content:'e2e'; position:absolute; top:-1px; right:4px; font-size:7px; font-weight:800; color:#2e7d32; background:#e8f5e9; padding:0 3px; border-radius:3px; border:1px solid #aed581 }
.gantt-axis-labels{ display:flex; justify-content:space-between; font-size:8px; color:#8a99a8; margin-top:4px; letter-spacing:.02em }
.gantt-rows{ padding:10px 12px; display:grid; gap:8px; background:#fff }
.gantt-row{ display:grid; grid-template-columns:138px minmax(0,1fr) 110px; gap:8px; align-items:center; }
.gantt-label{ display:flex; align-items:center; gap:7px; min-width:0 }
.gantt-label i{ width:10px; height:10px; border-radius:3px; flex:none; box-shadow:0 1px 3px #0002 }
.gantt-label strong{ display:block; font-size:10px; color:#1e2d3a; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
.gantt-label small{ display:block; font-size:8px; color:#7a8da0; font-family:ui-monospace,monospace; letter-spacing:.02em }
.gantt-track{ position:relative; height:28px; background:#f6f8fa; border:1px solid #e9eef3; border-radius:8px; overflow:hidden; display:flex; align-items:center }
.gantt-grid{ position:absolute; inset:0; pointer-events:none }
.gantt-grid span{ position:absolute; top:0; bottom:0; width:1px; background:#ecf0f4 }
.gantt-bar{ position:absolute; top:4px; bottom:4px; border-radius:6px; border:1px solid transparent; display:flex; align-items:center; justify-content:center; min-width:6px; transition:width .35s ease, left .35s ease }
.gantt-bar-text{ color:#fff; font-size:9px; font-weight:800; font-family:ui-monospace,monospace; text-shadow:0 1px 2px rgba(0,0,0,.35); white-space:nowrap; padding:0 4px }
.gantt-bar-outside{ position:absolute; top:50%; transform:translateY(-50%); font-size:9px; font-weight:800; font-family:ui-monospace,monospace; white-space:nowrap; background:#fff; padding:1px 4px; border-radius:4px; border:1px solid #e3e8ee }
.gantt-range-hint{ position:absolute; bottom:1px; right:6px; font-size:7px; color:#9aaaba; font-family:ui-monospace,monospace; background:#ffffffe0; padding:0 3px; border-radius:3px; pointer-events:none }
.gantt-time{ text-align:left; direction:ltr; display:flex; flex-direction:column; align-items:flex-end; gap:1px; min-width:0 }
.gantt-time b{ font-size:10px; font-family:ui-monospace,monospace; color:#25313d; background:#f8f9fa; border:1px solid #eef2f5; padding:2px 6px; border-radius:6px }
.gantt-time small{ font-size:8px; color:#7b8da0; font-family:ui-monospace,monospace; white-space:nowrap }
.gantt-footer{ padding:8px 12px 10px; background:#f8f9fa; border-top:1px solid #edf0f3; display:grid; gap:6px }
.gantt-summary{ font-size:9px; color:#5a6b7a; display:flex; flex-wrap:wrap; gap:6px; align-items:center; line-height:1.6 }
.gantt-summary b{ color:#243140 }
.gantt-legend{ display:flex; flex-wrap:wrap; gap:6px }
.gantt-legend-item{ display:inline-flex; align-items:center; gap:5px; font-size:8px; color:#4a5a6a; background:#fff; border:1px solid #edf0f3; padding:3px 7px; border-radius:999px; font-weight:600 }
.gantt-legend-item i{ width:8px; height:8px; border-radius:2px; flex:none }
.left-column{ display:grid; gap:14px; align-content:start }
@media(max-width:850px){
  .gantt-row{ grid-template-columns:118px minmax(0,1fr) 92px; }
  .gantt-label strong{ font-size:9px }
  .gantt-time b{ font-size:9px; padding:2px 5px }
}
@media(max-width:560px){
  .gantt-row{ grid-template-columns:1fr; gap:4px }
  .gantt-label{ order:1 }
  .gantt-time{ order:2; flex-direction:row; justify-content:space-between; align-items:center; }
  .gantt-time small{ font-size:7px }
  .gantt-track{ order:3; height:24px }
  .gantt-axis{ padding:8px 10px 6px }
}
`;
