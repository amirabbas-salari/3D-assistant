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
  const avatarContainerRef = useRef(null);
  const avatarPlayerRef = useRef(null);
  const avatarViewRef = useRef(null);
  const motionWatchRef = useRef([]);
  const lipSyncRef = useRef(null);
  const assistantAudioRefs = useRef([]);
  const lipSyncOffsetRef = useRef(lipSyncOffset);
  const startingRef = useRef(false);
  const chatRef = useRef(null);
  const logRef = useRef(null);
  const avatarVideoRef = useRef(null);

  useEffect(() => {
    lipSyncOffsetRef.current = lipSyncOffset;
    lipSyncRef.current?.configure({ offsetMs: lipSyncOffset });
    try { window.localStorage?.setItem('sam.lipSyncOffsetMs', String(lipSyncOffset)); } catch {}
  }, [lipSyncOffset]);

  return {
    phase, setPhase, health, setHealth, chatMessages, setChatMessages, logs, setLogs,
    draft, setDraft, draftTranscript, setDraftTranscript, avatarReady, setAvatarReady,
    assistantAudioTracks, setAssistantAudioTracks, micEnabled, setMicEnabled,
    audioNeedsGesture, setAudioNeedsGesture, cleanupBusy, setCleanupBusy, latency, setLatency,
    lipSyncOffset, setLipSyncOffset, roomRef, avatarContainerRef, avatarPlayerRef, avatarViewRef,
    motionWatchRef, lipSyncRef, assistantAudioRefs, lipSyncOffsetRef, startingRef, chatRef, logRef, avatarVideoRef,
  };
}
