export const LATENCY_STAGES = [
  ['response_delay', 'پایان سوال → شروع پاسخ'],
  ['end_of_turn_delay', 'تشخیص پایان نوبت'],
  ['transcription_delay', 'متن نهایی STT'],
  ['llm_node_ttft', 'اولین توکن LLM'],
  ['llm_node_ttfs', 'اولین جمله به TTS'],
  ['knowledge_lookup', 'ابزار دانش'],
  ['tts_node_ttfb', 'اولین بایت صدا'],
  ['playback_latency', 'شروع پخش'],
  ['tts_requests', 'درخواست TTS'],
];

export function msLabel(value) {
  if (value === null || value === undefined) return '—';
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  if (value >= 100) return `${Math.round(value)}ms`;
  return `${value.toFixed(1)}ms`;
}

export function formatLatency(packet) {
  const stages = (packet.last && packet.last.stages) || {};
  const parts = LATENCY_STAGES
    .filter(([key]) => stages[key] !== null && stages[key] !== undefined)
    .map(([key, label]) => `${label}: ${msLabel(stages[key])}`);
  const e2e = packet.last ? `سراسری ${msLabel(packet.last.e2e_ms)}` : '';
  return [e2e, ...parts].filter(Boolean).join(' · ');
}
