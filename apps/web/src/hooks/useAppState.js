import { useState, useEffect, useRef } from 'react';

export function useAppState() {
  const [phase, setPhase] = useState('idle');
  const [health, setHealth] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [logs, setLogs] = useState([]);
  const [draft, setDraft] = useState('');
  const [draftTranscript, setDraftTranscript] = useState('');
  const [avatarReady, setAvatarReady] = useState(false);
  const [assistantAudioTracks, setAssistantAudioTracks] = useState([]);
  const [micEnabled, setMicEnabled] = useState(false);
  const [audioNeedsGesture, setAudioNeedsGesture] = useState(false);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [latency, setLatency] = useState(null);
  const [lipSyncOffset, setLipSyncOffset] = useState(() => {
    const saved = Number(window.localStorage?.getItem('sam.lipSyncOffsetMs'));
    return Number.isFinite(saved) && saved >= 0 && saved <= 600 ? saved : 120;
  });
  const roomRef = useRef(null);
  const assistantAudioRefs = useRef([]);
  const startingRef = useRef(false);
  const chatRef = useRef(null);
  const logRef = useRef(null);

  useEffect(() => {
    try { window.localStorage?.setItem('sam.lipSyncOffsetMs', String(lipSyncOffset)); } catch {}
  }, [lipSyncOffset]);

  return {
    phase, setPhase, health, setHealth, chatMessages, setChatMessages, logs, setLogs,
    draft, setDraft, draftTranscript, setDraftTranscript, avatarReady, setAvatarReady,
    assistantAudioTracks, setAssistantAudioTracks, micEnabled, setMicEnabled,
    audioNeedsGesture, setAudioNeedsGesture, cleanupBusy, setCleanupBusy, latency, setLatency,
    lipSyncOffset, setLipSyncOffset, roomRef, assistantAudioRefs, startingRef, chatRef, logRef,
  };
}
