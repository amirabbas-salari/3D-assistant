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

function tokenColor(idx, alpha = 'ff') {
  const palette = ['#6a1b9a', '#7b1fa2', '#8e24aa', '#ab47bc', '#9c27b0', '#512da8', '#5e35b1', '#673ab7', '#3949ab', '#303f9f', '#283593', '#1565c0', '#0277bd'];
  return palette[(idx - 1) % palette.length];
}
function ttsColor(idx) {
  const palette = ['#4527a0', '#512da8', '#5e35b1', '#673ab7', '#3f51b5', '#3949ab', '#303f9f', '#283593', '#1a237e', '#004d40', '#00695c'];
  return palette[(idx - 1) % palette.length];
}
function sttColor(idx) {
  const palette = ['#1565c0', '#1976d2', '#1e88e5', '#2196f3', '#0288d1', '#0277bd', '#01579b', '#0d47a1', '#00838f', '#00695c', '#2e7d32'];
  return palette[(idx - 1) % palette.length];
}

function computeSpans(last) {
  try {
    const stages = last?.stages || {};
    const e2eRaw = last?.e2e_ms ?? last?.response_delay_ms ?? null;
    const e2e = e2eRaw != null ? toNum(e2eRaw, null) : null;
    const llmStart = Math.max(toNum(stages.end_of_turn_delay, 0), toNum(stages.transcription_delay, 0));

    const hasLLMTokens = Array.isArray(last?.tokens) && last.tokens.length > 0;
    const hasTTSTokens = Array.isArray(last?.tts_tokens) && last.tts_tokens.length > 0;
    const hasSTTTokens = Array.isArray(last?.stt_tokens) && last.stt_tokens.length > 0;

    const spans = [];
    const baseOrder = PIPELINE_ORDER.filter(k => {
      if (hasLLMTokens && (k === 'llm_node_ttft' || k === 'llm_node_ttfs')) return false;
      if (hasTTSTokens && k === 'tts_node_ttfb') return false;
      if (hasSTTTokens && k === 'transcription_delay') return false;
      return true;
    });

    for (const key of baseOrder) {
      const raw = stages[key];
      if (raw == null) continue;
      const dur = toNum(raw, null);
      if (dur == null || !Number.isFinite(dur) || dur < 0) continue;
      let start = 0;
      if (key === 'end_of_turn_delay' || key === 'transcription_delay') start = 0;
      else if (key === 'knowledge_lookup') start = llmStart;
      else if (key === 'tts_node_ttfb') start = llmStart + toNum(stages.llm_node_ttfs ?? stages.llm_node_ttft ?? 0, 0);
      else if (key === 'playback_latency') {
        const ttsStart = llmStart + toNum(stages.llm_node_ttfs ?? stages.llm_node_ttft ?? 0, 0);
        start = ttsStart + toNum(stages.tts_node_ttfb, 0);
      }
      if (!Number.isFinite(start)) start = 0;
      const end = start + dur;
      const meta = STAGE_META[key] || { label: key, short: key, color: '#607d8b', bg: '#eceff1', border: '#cfd8dc' };
      spans.push({ key, label: meta.label, short: meta.short, color: meta.color, bg: meta.bg, border: meta.border, start, end, dur, kind: 'stage' });
    }

    // LLM: یک ردیف با تمام توکن‌ها
    let llmGroup = null;
    let llmTokenSegments = [];
    if (hasLLMTokens) {
      const toks = last.tokens;
      const MAX_TOK = 80;
      const sliced = toks.length > MAX_TOK ? toks.slice(0, MAX_TOK) : toks;
      for (const t of sliced) {
        const idx = toNum(t.idx, llmTokenSegments.length + 1);
        const tStartRel = toNum(t.start, 0);
        const tEndRel = toNum(t.end, 0);
        const tDur = toNum(t.dur, tEndRel - tStartRel);
        const absStart = llmStart + tStartRel;
        const absEnd = llmStart + tEndRel;
        llmTokenSegments.push({
          idx,
          start: absStart,
          end: absEnd,
          dur: tDur,
          text: String(t.text || '').slice(0, 20),
          color: tokenColor(idx),
        });
      }
      if (toks.length > MAX_TOK) {
        const rest = toks.slice(MAX_TOK);
        const restStartRel = toNum(rest[0].start, 0);
        const restEndRel = toNum(rest[rest.length - 1].end, 0);
        const absStart = llmStart + restStartRel;
        const absEnd = llmStart + restEndRel;
        llmTokenSegments.push({
          idx: MAX_TOK + 1,
          start: absStart,
          end: absEnd,
          dur: toNum(rest.reduce((s, x) => s + toNum(x.dur, 0), 0), 0),
          text: `+${rest.length} توکن`,
          color: '#78909c',
          isRest: true,
        });
      }
      if (llmTokenSegments.length) {
        const gStart = llmTokenSegments[0].start;
        const gEnd = llmTokenSegments[llmTokenSegments.length - 1].end;
        llmGroup = {
          key: 'llm_group',
          label: `LLM — همه توکن‌ها`,
          short: `LLM×${toks.length}`,
          color: '#6a1b9a',
          start: gStart,
          end: gEnd,
          dur: gEnd - gStart,
          kind: 'llm_group',
          segments: llmTokenSegments,
          totalCount: toks.length,
        };
      }
    }

    // TTS: یک ردیف با تمام تکه‌های صدا — t.start در tracker نسبت به llmStart ذخیره می‌شود، پس برای محور pipeline باید llmStart اضافه شود
    // برای سازگاری با داده‌های قدیمی (که ممکن است نسبت به turn_start باشند) هر دو حالت را پوشش می‌دهیم
    let ttsGroup = null;
    let ttsSegments = [];
    let _sttTotalForTTS = 0;
    if (hasSTTTokens) {
      try {
        const s0 = last.stt_tokens[0], sN = last.stt_tokens[last.stt_tokens.length-1];
        _sttTotalForTTS = Math.max(0, toNum(sN.end,0) - toNum(s0.start,0));
      } catch {}
    }
    if (hasTTSTokens) {
      const ttoks = last.tts_tokens;
      for (const t of ttoks) {
        const idx = toNum(t.idx, ttsSegments.length + 1);
        const rawStart = toNum(t.start, 0);
        const rawEnd = toNum(t.end, rawStart);
        const dur = toNum(t.dur, rawEnd - rawStart);
        // تشخیص مبدا: اگر t.start خیلی بزرگ (>2s و > llmStart+1s) یعنی نسبت به turn_start است
        let absStart, absEnd;
        if (hasSTTTokens && _sttTotalForTTS > 500 && rawStart > _sttTotalForTTS + llmStart + 200) {
          // turn-based → به pipeline تبدیل کن: کم کردن مدت صحبت
          absStart = rawStart - _sttTotalForTTS;
          absEnd = rawEnd - _sttTotalForTTS;
        } else {
          // llm-relative (حالت فعلی) → llmStart اضافه کن
          absStart = llmStart + rawStart;
          absEnd = llmStart + rawEnd;
        }
        ttsSegments.push({
          idx,
          start: absStart,
          end: absEnd,
          dur,
          text: String(t.text || '').slice(0, 24),
          color: ttsColor(idx),
        });
      }
      if (ttsSegments.length) {
        const gStart = ttsSegments[0].start;
        const gEnd = ttsSegments[ttsSegments.length - 1].end;
        ttsGroup = {
          key: 'tts_group',
          label: `صدا (TTS) — همه تکه‌ها`,
          short: `TTS×${ttoks.length}`,
          color: '#4527a0',
          start: gStart,
          end: gEnd,
          dur: gEnd - gStart,
          kind: 'tts_group',
          segments: ttsSegments,
          totalCount: ttoks.length,
        };
      }
    }

    // STT: یک ردیف با تمام تکه‌های دریافت صدا (interim)
    // interimها از turn_start (شروع صحبت) تا پایان صحبت ادامه دارند — روی محور pipeline (0=پایان گفتار) باید قبل از 0 یا جدا نمایش داده شوند
    // برای جلوگیری از هم‌پوشانی اشتباه با LLM (باگ اسکرین‌شات: STT 0→3.73 روی LLM 1→2.2)، STT را خارج از محور pipeline نگه می‌داریم
    let sttGroup = null;
    let sttSegments = [];
    let sttTotal = 0;
    if (hasSTTTokens) {
      const stoks = last.stt_tokens;
      // ابتدا سگمنت‌های خام (نسبت به turn_start)
      const rawSegs = [];
      for (const t of stoks) {
        const idx = toNum(t.idx, rawSegs.length + 1);
        const absStart = toNum(t.start, 0);
        const absEnd = toNum(t.end, absStart);
        const dur = toNum(t.dur, absEnd - absStart);
        rawSegs.push({ idx, start: absStart, end: absEnd, dur, text: String(t.text || '').slice(0, 24), color: sttColor(idx), final: !!t.final });
      }
      sttTotal = rawSegs.length ? (rawSegs[rawSegs.length-1].end - rawSegs[0].start) : 0;
      // STT را به عنوان ردیف جداگانه نگه می‌داریم ولی برای محور اصلی (pipeline) آن را در نظر نمی‌گیریم
      // تا maxEnd و مقیاس محور تحت تأثیر مدت صحبت قرار نگیرد — جزئیات STT در پایین گانت به صورت جداگانه نشان داده می‌شود
      // برای ردیف STT، سگمنت‌ها را نسبت به شروع خودش (0→sttTotal) نگه می‌داریم تا SegmentedBar درست پر شود
      sttSegments = rawSegs.map(s => ({ ...s, start: s.start - (rawSegs[0]?.start || 0), end: s.end - (rawSegs[0]?.start || 0) }));
      if (sttSegments.length) {
        const gStart = 0;
        const gEnd = sttTotal;
        sttGroup = {
          key: 'stt_group',
          label: `دریافت صدا (STT) — همه تکه‌ها`,
          short: `STT×${stoks.length}`,
          color: '#1565c0',
          start: gStart,
          end: gEnd,
          dur: gEnd - gStart,
          kind: 'stt_group',
          segments: sttSegments,
          totalCount: stoks.length,
          _rawStart: rawSegs[0]?.start || 0,
          _rawEnd: rawSegs[rawSegs.length-1]?.end || 0,
        };
      }
    }

    // ترتیب: head (endpointing,RAG) → LLM → TTS → playback — STT جداگانه (خارج از محور pipeline)
    // STT مدت صحبت کاربر است (تا 3-4 ثانیه) و نباید محور اصلی (پایپلاین از پایان گفتار تا شروع پخش) را بکشد — باگ اسکرین‌شات همین بود
    const ttsPlaybackOld = spans.filter(s => s.key === 'playback_latency');
    const endpointing = spans.filter(s => s.key === 'end_of_turn_delay');
    const headMid = spans.filter(s => s.key !== 'playback_latency' && s.key !== 'end_of_turn_delay');
    const ordered = [];
    ordered.push(...endpointing);
    ordered.push(...headMid);
    if (llmGroup) ordered.push(llmGroup);
    if (ttsGroup) ordered.push(ttsGroup);
    // playback را بعد از TTS/LLM قرار بده — اگر TTS گروهی داریم، playback باید بعد از آن باشد نه در llmStart
    if (ttsPlaybackOld.length) {
      // اگر playback 0ms بود ولی e2e داریم، playback را در e2e قرار بده
      for (const pb of ttsPlaybackOld) {
        if (pb.dur === 0 && e2e != null && Number.isFinite(e2e)) {
          pb.start = e2e;
          pb.end = e2e;
        } else if (ttsGroup) {
          // در غیر این صورت بعد از TTS
          const expectedStart = ttsGroup.end;
          // اگر محاسبه قبلی (llmStart) خیلی زودتر بود، اصلاح کن
          if (pb.start < expectedStart - 50) {
            pb.start = expectedStart;
            pb.end = expectedStart + pb.dur;
          }
        } else if (llmGroup && pb.start < llmGroup.end - 50) {
          pb.start = llmGroup.end;
          pb.end = llmGroup.end + pb.dur;
        }
      }
      ordered.push(...ttsPlaybackOld);
    }

    // STT را برای نمایش جداگانه نگه دار — در محور اصلی حساب نکن
    const pipelineEnds = [...ordered.map(s => s.end), ...llmTokenSegments.map(s => s.end), ...ttsSegments.map(s => s.end)];
    const maxFromSpans = pipelineEnds.length ? Math.max(...pipelineEnds) : 0;
    const maxEnd = Math.max(1, maxFromSpans, e2e != null && Number.isFinite(e2e) ? e2e : 0);

    // sttTotal را هم برگردان تا UI بتواند توضیح دهد
    return { stages, e2e, maxEnd, spans: ordered, llmGroup, ttsGroup, sttGroup, hasLLMTokens, hasTTSTokens, hasSTTTokens, llmStart, sttTotal };
  } catch (e) {
    console.error('[TimelineChart computeSpans]', e);
    return { stages: {}, e2e: null, maxEnd: 1, spans: [], llmGroup: null, ttsGroup: null, sttGroup: null, hasLLMTokens: false, hasTTSTokens: false, hasSTTTokens: false, llmStart: 0 };
  }
}

function SegmentedBar({ group, maxEnd }) {
  const safeMax = Number.isFinite(maxEnd) && maxEnd > 0 ? maxEnd : 1;
  const segs = group.segments || [];
  return (
    <div className="segmented-track" title={`${group.label}: ${msLabel(group.start)} → ${msLabel(group.end)} (${group.totalCount} سگمنت)`}>
      {segs.map(seg => {
        const leftPct = (seg.start / safeMax) * 100;
        const widthPct = Math.max(0.6, (seg.dur / safeMax) * 100);
        const clampedLeft = Math.max(0, Math.min(100, leftPct));
        const clampedWidth = Math.max(0.6, Math.min(100 - clampedLeft, widthPct));
        return (
          <span
            key={seg.idx}
            className="seg"
            style={{ left: `${clampedLeft}%`, width: `${clampedWidth}%`, background: seg.color, border: seg.final ? '1px solid #fff' : '1px solid rgba(255,255,255,.6)', boxShadow: seg.final ? '0 0 0 1px rgba(0,0,0,.15)' : undefined }}
            title={`#${seg.idx} "${seg.text}" — ${msLabel(seg.start)} → ${msLabel(seg.end)} (${msLabel(seg.dur)})${seg.final ? ' ✓ نهایی' : ''}`}
          >
            {widthPct > 6 && seg.text ? <em>{seg.text.slice(0, 8)}</em> : null}
          </span>
        );
      })}
    </div>
  );
}

export default function TimelineChart({ latency }) {
  if (!latency?.last) {
    return (
      <section className="panel gantt-panel gantt-empty">
        <div className="panel-heading">
          <div>
            <span style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: 8, background: '#eef2f7', color: '#4a6fa5' }}>▦</span>
            <div><h2>گانت پایپ‌لاین صوت</h2><small>هر ردیف = یک مرحله — دریافت‌ِصدا، LLM و TTS هر کدام یک ردیف با تمام توکن‌ها داخلش</small></div>
          </div>
          <span className="mode-tag">منتظر اولین نوبت</span>
        </div>
        <div style={{ padding: '22px 16px', textAlign: 'center', color: '#7a8a9a', fontSize: 11, lineHeight: 1.9 }}>
          هنوز نوبتی ثبت نشده — پس از اولین پیام، <b>یک ردیف برای دریافتِ‌صدا (STT)</b>، <b>یک ردیف برای LLM</b> و <b>یک ردیف برای صدا (TTS)</b> می‌بینی که همه توکن‌ها/تکه‌ها داخل همان ردیف مرحله‌ای هستند.
        </div>
        <style>{ganttCss}</style>
      </section>
    );
  }

  let e2e, maxEnd, spans, llmGroup, ttsGroup, sttGroup, hasLLMTokens, hasTTSTokens, hasSTTTokens, llmStart, sttTotal;
  try {
    ({ e2e, maxEnd, spans, llmGroup, ttsGroup, sttGroup, hasLLMTokens, hasTTSTokens, hasSTTTokens, llmStart, sttTotal } = computeSpans(latency.last));
  } catch (err) {
    console.error('[TimelineChart]', err);
    return <section className="panel gantt-panel"><div style={{ padding: 12, fontSize: 11, color: '#8a4444' }}>خطا در نمایش گانت</div><style>{ganttCss}</style></section>;
  }

  const turns = latency.turns ?? 0;
  const safeMaxEnd = Number.isFinite(maxEnd) && maxEnd > 0 ? maxEnd : 1;
  const tickVals = [0, safeMaxEnd * 0.25, safeMaxEnd * 0.5, safeMaxEnd * 0.75, safeMaxEnd];

  return (
    <section className="panel gantt-panel">
      <div className="panel-heading">
        <div>
          <span style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: 8, background: '#e8f0fe', color: '#2857a5', fontWeight: 800, fontSize: 11 }}>◧</span>
          <div><h2>گانت پایپ‌لاین — نوبت #{latency.last?.index ?? '—'} {hasSTTTokens ? `· دریافت ${sttGroup?.totalCount} تکه` : ''}{hasLLMTokens ? ` · LLM ${llmGroup?.totalCount} توکن` : ''}{hasTTSTokens ? ` · صدا ${ttsGroup?.totalCount} تکه` : ''}</h2><small>محور زمان: ۰ = پایان گفتار کاربر → {msLabel(e2e ?? safeMaxEnd)} سراسری{e2e != null && sttTotal > 0 ? ` · دریافت قبل از ۰` : ''}</small></div>
        </div>
        <span className="gantt-e2e-badge">{msLabel(e2e ?? safeMaxEnd)} سراسری</span>
      </div>

      <div className="gantt-axis">
        <div className="gantt-axis-track">
          {tickVals.map((v, i) => {
            const pct = Number.isFinite(v) && Number.isFinite(safeMaxEnd) ? (v / safeMaxEnd) * 100 : 0;
            return <span key={i} className="gantt-tick" style={{ left: `${pct}%` }}><i /><b>{i === 0 ? '۰' : msLabel(v)}</b></span>;
          })}
          {e2e != null && Number.isFinite(e2e) && <span className="gantt-e2e-line" style={{ left: `${Math.min(100, (e2e / safeMaxEnd) * 100)}%` }} />}
        </div>
        <div className="gantt-axis-labels"><span>۰ = پایان گفتار کاربر</span><span>پایان (شروع پخش · {msLabel(e2e ?? safeMaxEnd)})</span></div>
      </div>

      {(hasSTTTokens || hasLLMTokens || hasTTSTokens) && (
        <div style={{ padding: '7px 12px', fontSize: 8.5, color: '#5a6b7a', background: '#faf7ff', borderBottom: '1px solid #ede7f6', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {hasSTTTokens && <span style={{ background: '#e3f2fd', border: '1px solid #90caf9', padding: '2px 7px', borderRadius: 999, fontWeight: 700 }}>دریافت صدا: یک ردیف = همه تکه‌های STT (هر سگمنت یک interim)</span>}
          {hasLLMTokens && <span style={{ background: '#ede7f6', border: '1px solid #d1c4e9', padding: '2px 7px', borderRadius: 999, fontWeight: 700 }}>LLM: یک ردیف = همه توکن‌ها (سگمنت #۱ از {msLabel(llmGroup.start)} …)</span>}
          {hasTTSTokens && <span style={{ background: '#ede7f6', border: '1px solid #b39ddb', padding: '2px 7px', borderRadius: 999, fontWeight: 700 }}>صدا: یک ردیف = همه تکه‌های TTS</span>}
        </div>
      )}

      {hasSTTTokens && sttGroup && (
        <div className="gantt-stt-prelude">
          <div className="gantt-label">
            <i style={{ background: sttGroup.color }} />
            <div><strong>{sttGroup.label}</strong><small>{sttGroup.short} · {msLabel(sttGroup.dur)} قبل از پایپلاین</small></div>
          </div>
          <div className="gantt-track" style={{ background: '#e3f2fd', borderColor: '#90caf9' }}>
            <div className="gantt-grid">{[25, 50, 75].map(p => <span key={p} style={{ left: `${p}%` }} />)}</div>
            <SegmentedBar group={sttGroup} maxEnd={sttGroup.dur} />
            <span className="gantt-range-hint">مدت صحبت: {msLabel(sttTotal)} — قبل از ۰</span>
          </div>
          <div className="gantt-time"><b>{msLabel(sttGroup.dur)}</b><small>قبل از پایان گفتار</small></div>
        </div>
      )}
      <div className="gantt-rows">
        {spans.length === 0 && <div style={{ padding: '10px 4px', fontSize: 10, color: '#6b7c8d', textAlign: 'center' }}>داده‌ای ثبت نشد.</div>}
        {spans.map(s => {
          const isGrouped = s.kind === 'llm_group' || s.kind === 'tts_group' || s.kind === 'stt_group';
          const leftPct = (s.start / safeMaxEnd) * 100;
          const widthPct = Math.max(1.2, (s.dur / safeMaxEnd) * 100);
          const clampedLeft = Math.max(0, Math.min(100, leftPct));
          const clampedWidth = Math.max(0.6, Math.min(100 - clampedLeft, widthPct));
          const pctTotal = safeMaxEnd ? ((s.dur / safeMaxEnd) * 100).toFixed(1) : '0';
          return (
            <div key={s.key} className={`gantt-row ${isGrouped ? 'gantt-row-grouped' : ''}`}>
              <div className="gantt-label">
                <i style={{ background: s.color }} />
                <div>
                  <strong>{s.label}</strong>
                  <small>{s.short} · {msLabel(s.dur)}</small>
                </div>
              </div>
              <div className="gantt-track">
                <div className="gantt-grid">{[25, 50, 75].map(p => <span key={p} style={{ left: `${p}%` }} />)}</div>
                {isGrouped ? (
                  <SegmentedBar group={s} maxEnd={safeMaxEnd} />
                ) : (
                  <div className="gantt-bar" style={{ left: `${clampedLeft}%`, width: `${clampedWidth}%`, background: s.color, borderColor: s.border || s.color }} title={`${s.label}: ${msLabel(s.start)} → ${msLabel(s.end)} (${msLabel(s.dur)} · ${pctTotal}%)`}>
                    <span className="gantt-bar-text">{msLabel(s.dur)}</span>
                  </div>
                )}
                <span className="gantt-range-hint">{msLabel(s.start)} → {msLabel(s.end)}</span>
              </div>
              <div className="gantt-time"><b>{msLabel(s.dur)}</b><small>{msLabel(s.start)} → {msLabel(s.end)}</small></div>
            </div>
          );
        })}
      </div>

      {hasSTTTokens && sttGroup && (
        <div style={{ padding: '8px 12px', background: '#e3f2fd', borderTop: '1px solid #90caf9', fontSize: 8, color: '#0d47a1' }}>
          <strong style={{ fontSize: 9, color: '#1565c0' }}>جزئیات دریافت صدا — هر سگمنت یک تکه STT:</strong>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {sttGroup.segments.map(seg => (
              <span key={seg.idx} style={{ background: seg.color, color: '#fff', padding: '2px 6px', borderRadius: 4, fontFamily: 'ui-monospace,monospace', fontSize: 8 }} title={`#${seg.idx} ${msLabel(seg.start)}→${msLabel(seg.end)}${seg.final ? ' نهایی' : ''}`}>#{seg.idx} "{String(seg.text).slice(0,12)}" · {msLabel(seg.dur)}{seg.final ? ' ✓' : ''}</span>
            ))}
          </div>
        </div>
      )}
      {hasLLMTokens && llmGroup && (
        <div style={{ padding: '8px 12px', background: '#fff', borderTop: '1px solid #ede7f6', fontSize: 8, color: '#6a6a8a' }}>
          <strong style={{ fontSize: 9, color: '#4a148c' }}>جزئیات LLM — هر سگمنت یک توکن:</strong>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {llmGroup.segments.slice(0, 30).map(seg => (
              <span key={seg.idx} style={{ background: seg.color, color: '#fff', padding: '2px 6px', borderRadius: 4, fontFamily: 'ui-monospace,monospace', fontSize: 8 }} title={`#${seg.idx} ${msLabel(seg.start)}→${msLabel(seg.end)}`}>#{seg.idx} {seg.text} · {msLabel(seg.dur)}</span>
            ))}
            {llmGroup.segments.length > 30 && <span style={{ color: '#78909c' }}>+{llmGroup.segments.length - 30} بیشتر…</span>}
          </div>
        </div>
      )}
      {hasTTSTokens && ttsGroup && (
        <div style={{ padding: '8px 12px', background: '#f3e5f5', borderTop: '1px solid #d1c4e9', fontSize: 8, color: '#4a148c' }}>
          <strong style={{ fontSize: 9, color: '#4527a0' }}>جزئیات صدا — هر سگمنت یک تکه TTS:</strong>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {ttsGroup.segments.map(seg => (
              <span key={seg.idx} style={{ background: seg.color, color: '#fff', padding: '2px 6px', borderRadius: 4, fontFamily: 'ui-monospace,monospace', fontSize: 8 }} title={`#${seg.idx} ${msLabel(seg.start)}→${msLabel(seg.end)}`}>#{seg.idx} "{seg.text.slice(0,12)}" · {msLabel(seg.dur)}</span>
            ))}
          </div>
        </div>
      )}

      <div className="gantt-footer">
        <div className="gantt-summary">
          <span>شروع LLM پس از <b>{msLabel(llmStart)}</b> از پایان گفتار</span><span>·</span><span>{turns} نوبت</span>
          {hasSTTTokens && <><span>·</span><span><b>{sttGroup.totalCount} تکه دریافت صدا</b> در {msLabel(sttTotal)} قبل از پایپلاین</span></>}
          {hasLLMTokens && <><span>·</span><span><b>{llmGroup.totalCount} توکن LLM</b> در یک ردیف</span></>}
          {hasTTSTokens && <><span>·</span><span><b>{ttsGroup.totalCount} تکه صدا</b> در یک ردیف</span></>}
        </div>
        <div className="gantt-legend">
          {spans.slice(0,5).map(s => <span key={s.key} className="gantt-legend-item"><i style={{ background: s.color }} />{s.short}</span>)}
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
.gantt-rows{ padding:10px 12px; display:grid; gap:6px; background:#fff; max-height:520px; overflow-y:auto; scrollbar-width:thin; scrollbar-color:#c4ced8 transparent }
.gantt-row{ display:grid; grid-template-columns:138px minmax(0,1fr) 110px; gap:8px; align-items:center; }
.gantt-row-grouped{ background:#faf7ff; border:1px solid #ede7f6; border-radius:8px; padding:4px 4px; margin:0 -4px }
.gantt-label{ display:flex; align-items:center; gap:7px; min-width:0 }
.gantt-label i{ width:10px; height:10px; border-radius:3px; flex:none; box-shadow:0 1px 3px #0002 }
.gantt-label strong{ display:block; font-size:10px; color:#1e2d3a; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
.gantt-label small{ display:block; font-size:8px; color:#7a8da0; font-family:ui-monospace,monospace; letter-spacing:.02em }
.gantt-track{ position:relative; height:28px; background:#f6f8fa; border:1px solid #e9eef3; border-radius:8px; overflow:hidden; display:flex; align-items:center }
.gantt-grid{ position:absolute; inset:0; pointer-events:none }
.gantt-grid span{ position:absolute; top:0; bottom:0; width:1px; background:#ecf0f4 }
.gantt-bar{ position:absolute; top:4px; bottom:4px; border-radius:6px; border:1px solid transparent; display:flex; align-items:center; justify-content:center; min-width:6px; transition:width .35s ease, left .35s ease }
.gantt-bar-text{ color:#fff; font-size:9px; font-weight:800; font-family:ui-monospace,monospace; text-shadow:0 1px 2px rgba(0,0,0,.35); white-space:nowrap; padding:0 4px; overflow:hidden; text-overflow:ellipsis; max-width:100% }
.segmented-track{ position:absolute; inset:4px 2px; display:block; overflow:hidden; border-radius:6px; }
.segmented-track .seg{ position:absolute; top:0; bottom:0; border-radius:3px; border:1px solid rgba(255,255,255,.6); display:flex; align-items:center; justify-content:center; overflow:hidden; }
.segmented-track .seg em{ font-style:normal; font-size:7px; color:#fff; font-weight:800; text-shadow:0 1px 1px rgba(0,0,0,.4); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:0 2px; }
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
.gantt-stt-prelude{ display:grid; grid-template-columns:138px minmax(0,1fr) 110px; gap:8px; align-items:center; padding:6px 12px; background:#f0f7ff; border-bottom:1px solid #90caf9; }
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
