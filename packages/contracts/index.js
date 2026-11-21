// Shared contracts — keep API and Web in sync
export const LATENCY_STAGES = [
  'response_delay','end_of_turn_delay','transcription_delay',
  'llm_node_ttft','llm_node_ttfs','knowledge_lookup','tts_node_ttfb','playback_latency','tts_requests'
];
export const AVATAR_PROVIDERS = ['none','spatius','did'];
export const SPEECH_PROVIDERS = ['inference','direct'];
