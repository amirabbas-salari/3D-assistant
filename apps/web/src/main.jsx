import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity, AudioLines, Check, CircleAlert, Copy, Mic, MicOff,
  RefreshCw, Send, Square, Trash2, Video, Volume2, Wifi, WifiOff,
} from 'lucide-react';
import { createLipSync } from './lipsync.js';
import './styles.css';

function RemoteAudioOutput({ track, registry, onRegistered }) {
  const audioRef = useRef(null);

  useEffect(() => {
    if (!audioRef.current) return undefined;
    track.attach(audioRef.current);
    // The lip-sync gate needs the element that is actually playing the agent's
    // voice; that is this one, created here and invisible on purpose.
    if (registry) {
      registry.current = [...registry.current.filter((item) => item !== audioRef.current), audioRef.current];
      onRegistered?.(registry.current);
    }
    return () => {
      track.detach(audioRef.current);
      if (registry) {
        registry.current = registry.current.filter((item) => item !== audioRef.current);
        onRegistered?.(registry.current);
      }
    };
  }, [track, registry, onRegistered]);

  return <audio ref={audioRef} autoPlay playsInline className="remote-audio-output" />;
}

function messageTime() {
  return new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// Labels match latency.py so the panel and the agent log describe the same stage.
const LATENCY_STAGES = [
  ['response_delay', 'پایان سوال → شروع پاسخ'],
  ['end_of_turn_delay', 'تشخیص پایان نوبت'],
  ['transcription_delay', 'متن نهایی STT'],
  ['llm_node_ttft', 'اولین توکن LLM'],
  ['llm_node_ttfs', 'اولین جمله به TTS'],
  ['knowledge_lookup', 'ابزار دانش'],
  ['tts_node_ttfb', 'اولین بایت صدا'],
  ['playback_latency', 'شروع پخش'],
  // A count, not a duration: how many TTS round-trips the reply cost.
  ['tts_requests', 'درخواست TTS'],
];

function msLabel(value) {
  if (value === null || value === undefined) return '—';
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  if (value >= 100) return `${Math.round(value)}ms`;
  return `${value.toFixed(1)}ms`;
}

function formatLatency(packet) {
  const stages = (packet.last && packet.last.stages) || {};
  const parts = LATENCY_STAGES
    .filter(([key]) => stages[key] !== null && stages[key] !== undefined)
    .map(([key, label]) => `${label}: ${msLabel(stages[key])}`);
  const e2e = packet.last ? `سراسری ${msLabel(packet.last.e2e_ms)}` : '';
  return [e2e, ...parts].filter(Boolean).join(' · ');
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error || 'خطای نامشخص');
}

function App() {
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
  // Per-turn millisecond timings published by the agent on the diagnostics topic.
  const [latency, setLatency] = useState(null);
  const roomRef = useRef(null);
  const avatarContainerRef = useRef(null);
  const avatarPlayerRef = useRef(null);
  const avatarViewRef = useRef(null);
  const motionWatchRef = useRef([]);
  const lipSyncRef = useRef(null);
  // The audio elements are created by React but consumed by a plain object, so
  // they are collected here rather than passed through props.
  const assistantAudioRefs = useRef([]);
  // The avatar's mouth runs on its own 25fps clock while the voice comes from a
  // media element, so motion lands slightly before the sound. This is how much
  // later the first frames of a turn are released; see src/lipsync.js. The right
  // value depends on the network path and the Spatius worker and no browser API
  // reports it, so the tuned number is remembered per browser.
  const [lipSyncOffset, setLipSyncOffset] = useState(() => {
    const saved = Number(window.localStorage?.getItem('sam.lipSyncOffsetMs'));
    return Number.isFinite(saved) && saved >= 0 && saved <= 600 ? saved : 120;
  });
  const lipSyncOffsetRef = useRef(lipSyncOffset);
  useEffect(() => {
    lipSyncOffsetRef.current = lipSyncOffset;
    lipSyncRef.current?.configure({ offsetMs: lipSyncOffset });
    try {
      window.localStorage?.setItem('sam.lipSyncOffsetMs', String(lipSyncOffset));
    } catch {
      // Private mode or a full quota: the value simply is not remembered.
    }
  }, [lipSyncOffset]);
  // D-ID publishes a normal video track, so it renders into a plain <video>.
  const avatarVideoRef = useRef(null);
  // Guards against a double click racing the async setPhase('connecting'): two
  // sessions would mean two agents and two STT connections in one room.
  const startingRef = useRef(false);
  const chatRef = useRef(null);
  const logRef = useRef(null);

  function addLog(level, message, details = '') {
    setLogs((current) => [...current, {
      id: `${Date.now()}-${Math.random()}`,
      time: messageTime(),
      level: String(level || 'info').toLowerCase(),
      message: String(message || ''),
      details: details ? String(details) : '',
    }]);
  }

  function addChat(role, text, source = '') {
    if (!String(text || '').trim()) return;
    setChatMessages((current) => [...current, {
      id: `${Date.now()}-${Math.random()}`,
      role,
      text: String(text),
      source,
      time: messageTime(),
    }]);
  }

  useEffect(() => {
    fetch('/api/health')
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        setHealth(data);
        addLog(data.configured ? 'info' : 'warning', 'بررسی پیکربندی API انجام شد', JSON.stringify(data, null, 2));
      })
      .catch((error) => {
        setHealth({ configured: false });
        addLog('error', 'دسترسی به API ناموفق بود', errorMessage(error));
      });
  }, []);

  useEffect(() => {
    const onWindowError = (event) => {
      addLog('error', 'خطای اجرا در مرورگر', event.message || 'خطای JavaScript');
    };
    const onUnhandledRejection = (event) => {
      addLog('error', 'وعده‌ی ناموفق در مرورگر', errorMessage(event.reason));
    };
    window.addEventListener('error', onWindowError);
    window.addEventListener('unhandledrejection', onUnhandledRejection);
    return () => {
      window.removeEventListener('error', onWindowError);
      window.removeEventListener('unhandledrejection', onUnhandledRejection);
    };
  }, []);


  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [chatMessages, draftTranscript]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // Reads the per-turn counter the SDK keeps, not the cumulative session one.
  // The cumulative count rarely moves inside a 1.2 s window, so it reports "no
  // motion" even while the face is visibly animating.
  function motionFrameCount() {
    const summary = avatarPlayerRef.current?.sessionSummary;
    if (!summary) return 0;
    if (summary.turnFrameCount != null) return Number(summary.turnFrameCount) || 0;
    if (summary.currentTurnFrames != null) return Number(summary.currentTurnFrames) || 0;
    return Number(summary.totalFrames) || 0;
  }

  // A cheap fingerprint of what is currently drawn. Motion frames can arrive
  // while nothing reaches the screen, so the picture — not the RTP counter — is
  // the only honest proof that the avatar is animating.
  async function canvasSignature() {
    const view = avatarViewRef.current;
    if (!view?.exportBitmap) return null;
    try {
      const blob = await view.exportBitmap();
      if (!blob) return null;
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let hash = 2166136261;
      const step = Math.max(1, Math.floor(bytes.length / 8192));
      for (let i = 0; i < bytes.length; i += step) {
        hash = Math.imul(hash ^ bytes[i], 16777619);
      }
      return String(hash >>> 0);
    } catch {
      return null;
    }
  }

  function clearMotionWatch() {
    for (const timer of motionWatchRef.current) window.clearTimeout(timer);
    motionWatchRef.current = [];
  }

  // Spatius needs a moment to synthesise motion, so sampling the first second
  // reports a false negative. Measure a window in the middle of the turn and
  // compare the rendered pixels across it.
  function startMotionWatch() {
    clearMotionWatch();
    const baseline = motionFrameCount();
    const timer = window.setTimeout(async () => {
      const first = await canvasSignature();
      const later = window.setTimeout(async () => {
        const second = await canvasSignature();
        // In room/RTC mode the SDK is told to use the clock we pass in, and a
        // new player instance may have appeared since the baseline was taken;
        // numbers from different players are not comparable, so only trust the
        // delta when it is a real one.
        const observed = motionFrameCount();
        const frames = observed >= baseline ? observed - baseline : null;
        const changed = first && second ? first !== second : null;
        const details = [
          frames === null ? 'شمارنده‌ی فریم بین دو نمونه بازنشانی شد' : `فریم حرکت در این بازه: ${frames}`,
          changed === null ? 'تصویر قابل نمونه‌برداری نبود' : changed ? 'تصویر در حال تغییر است' : 'تصویر تغییر نکرد',
        ].join(' · ');
        if (frames === null) {
          // The counter was replaced rather than merely unchanged: report what
          // the picture says instead of claiming no motion arrived.
          addLog(changed === false ? 'warning' : 'info',
            changed === false ? 'تصویر آواتار در این بازه تغییر نکرد' : 'آواتار در حال حرکت است', details);
        } else if (frames === 0) {
          addLog('warning', 'در این بازه فریم حرکتی به آواتار نرسید', details);
        } else if (changed === false) {
          addLog('warning', 'فریم حرکت می‌رسد اما تصویر آواتار تغییر نمی‌کند',
            `${details} — سمت رندر مشکل دارد، نه شبکه (مثلاً خطای avatar_id یا توقف رندر).`);
        } else {
          addLog('success', 'آواتار در حال حرکت است', details);
        }
      }, 1200);
      motionWatchRef.current.push(later);
    }, 1500);
    motionWatchRef.current = [timer];
  }

  async function startSession() {
    if (phase !== 'idle' || startingRef.current) return;
    startingRef.current = true;
    setPhase('connecting');
    addLog('info', 'درخواست ایجاد جلسه ارسال شد');
    let room;
    try {
      const response = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = [data.error, data.details].filter(Boolean).join('\n');
        throw new Error(detail || `ساخت جلسه ناموفق بود (HTTP ${response.status})`);
      }

      const { Room, RoomEvent, Track } = await import('livekit-client');
      // When the avatar runs, adaptiveStream MUST stay off: Spatius publishes
      // motion data on a video track that the SDK attaches to a hidden
      // (display:none) <video> element, so LiveKit would conclude nobody is
      // watching and ask the server to pause it — no motion frames, static face.
      // With the avatar off, motion is expected and adaptiveStream is safe.
      // `/api/session` reports the provider so the renderer is known before
      // connecting; health is only a fallback for older servers.
      const provider = ['did', 'spatius', 'none'].includes(data.avatarProvider)
        ? data.avatarProvider
        : avatarEnabled ? 'spatius' : 'none';
      const spatiusAvatar = provider === 'spatius';
      room = new Room({
        adaptiveStream: !spatiusAvatar,
        dynacast: true,
        singlePeerConnection: spatiusAvatar ? false : undefined,
      });
      roomRef.current = room;

      // Spatius publishes motion data on a LiveKit video track. Attach AvatarKit
      // to this app-owned room before connecting; the track is not an HTML video.
      // Skipped entirely while the avatar is disabled for LLM/TTS/STT work.
      if (provider === 'none') {
        addLog('info', 'آواتار خاموش است', 'AVATAR_ENABLED=false · فقط صدا و متن فعال است');
      } else if (provider === 'did') {
        addLog('info', 'آواتار D-ID فعال است', 'ویدیوی D-ID به‌صورت ترک ویدیویی در همین اتاق منتشر می‌شود');
      } else try {
        if (typeof globalThis.RTCRtpScriptTransform === 'undefined') {
          throw new Error('مرورگر از RTCRtpScriptTransform موردنیاز آواتار Spatius پشتیبانی نمی‌کند');
        }
        const [avatarKit, avatarRtc] = await Promise.all([
          import('@spatius/avatarkit'),
          import('@spatius/avatarkit-rtc'),
        ]);
        await avatarKit.AvatarSDK.initialize(data.spatiusAppId, {
          drivingServiceMode: avatarKit.DrivingServiceMode.rtc,
        });
        // The render backing buffer follows the panel's CSS size, which here is
        // only a couple of hundred pixels tall — the avatar is then upscaled and
        // looks soft. A minimum height keeps it sharp; 720 is enough for this
        // panel without paying for a full-HD buffer on a laptop GPU.
        try {
          avatarKit.AvatarSDK.setRenderResolutionConfig?.(true, { minHeight: 720 });
        } catch (error) {
          addLog('warning', 'تنظیم دقت رندر آواتار اعمال نشد', errorMessage(error));
        }
        const avatar = await avatarKit.AvatarManager.shared.load(data.spatiusAvatarId);
        const avatarView = new avatarKit.AvatarView(avatar, avatarContainerRef.current);
        avatarViewRef.current = avatarView;
        // AvatarKit reports render-side failures (mismatched avatar_id, blank
        // canvas, lost GPU device) only through this callback; without it they
        // are silent and the face simply never moves.
        avatarView.controller.onError = (error) => {
          addLog('error', 'خطای رندر AvatarKit', `${error?.code || 'unknown'} · ${errorMessage(error)}`);
        };
        await new Promise((resolve, reject) => {
          const timeout = window.setTimeout(() => reject(new Error('رندر اولیه‌ی آواتار Spatius بیش از حد طول کشید')), 20000);
          avatarView.onFirstRendering = () => {
            window.clearTimeout(timeout);
            resolve();
          };
        });
        const player = new avatarRtc.AvatarPlayer(new avatarRtc.LiveKitProvider(), avatarView);
        // AvatarKit renders motion on its own clock; the synchroniser holds the
        // opening frames of each turn so the mouth starts with the voice.
        lipSyncRef.current = createLipSync();
        lipSyncRef.current.configure({ offsetMs: lipSyncOffsetRef.current });
        lipSyncRef.current.attachView(avatarView);
        lipSyncRef.current.setAudioElements(assistantAudioRefs.current);
        player.on('error', (error) => addLog('error', 'خطای SDK آواتار Spatius', errorMessage(error)));
        // Motion (lip-sync) state comes from Spatius over the RTC adapter, not
        // from AvatarKit's own callback, which never fires in RTC mode.
        player.on('conversation-state-changed', (state) => {
          if (state === 'speaking') {
            addLog('info', 'آواتار شروع به صحبت کرد', 'حالت حرکتی Spatius: speaking');
            // A new turn: allow the opening frames to be held back again.
            lipSyncRef.current?.beginTurn();
            // Spatius needs a moment to synthesise motion, so the window starts
            // after the turn has begun rather than at the instant it starts.
            startMotionWatch();
            return;
          }
          clearMotionWatch();
          const summary = avatarPlayerRef.current?.sessionSummary;
          const frames = summary ? `فریم حرکت: ${summary.totalFrames} · fps≈${summary.avgFps}` : '';
          addLog(summary && summary.totalFrames > 0 ? 'success' : 'warning', 'آواتار به حالت آماده بازگشت', frames);
        });
        player.on('stalled', () => {
          // In the host-owned path the Room belongs to this app, so reconnecting
          // is our job; player.reconnect() only works for managed connections.
          addLog('warning', 'جریان حرکت آواتار متوقف شد', 'بررسی اتصال Room و ترک حرکت Spatius لازم است');
        });
        avatarPlayerRef.current = player;
        await player.attach(room);
        addLog('success', 'SDK آواتار Spatius آماده شد');
      } catch (error) {
        addLog('error', 'راه‌اندازی نمایشگر Spatius ناموفق بود', errorMessage(error));
        await avatarPlayerRef.current?.detach().catch(() => {});
        avatarPlayerRef.current = null;
        avatarViewRef.current?.dispose();
        avatarViewRef.current = null;
      }

      room.on(RoomEvent.DataReceived, (payload) => {
        try {
          const packet = JSON.parse(new TextDecoder().decode(payload));
          if (packet.type === 'system_log') {
            addLog(packet.level, packet.message, packet.details || '');
          } else if (packet.type === 'user_transcript' && typeof packet.text === 'string') {
            if (packet.final) {
              addChat('user', packet.text, 'voice');
              setDraftTranscript('');
            } else {
              setDraftTranscript(packet.text);
            }
          } else if (packet.type === 'latency') {
            setLatency(packet);
            const last = packet.last;
            if (last) {
              addLog('info', 'زمان‌بندی نوبت', formatLatency(packet));
            }
          } else if (packet.type === 'assistant_reply' && typeof packet.text === 'string') {
            addChat('assistant', packet.text, 'agent');
            addLog('info', 'پاسخ متنی Agent دریافت شد', `${packet.text.length} نویسه`);
          }
        } catch (error) {
          addLog('warning', 'بسته‌ی داده قابل خواندن نبود', errorMessage(error));
        }
      });

      room.on(RoomEvent.ParticipantConnected, (participant) => {
        addLog('info', 'شرکت‌کننده به اتاق پیوست', participant.identity);
      });
      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        addLog('warning', 'شرکت‌کننده از اتاق خارج شد', participant.identity);
      });
      room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        if (track.kind === Track.Kind.Video) {
          setAvatarReady(true);
          // The motion track is the only source of lip-sync. Keep it explicitly
          // flowing: a disabled publication silently freezes the avatar's face.
          publication.setEnabled?.(true);
          if (provider === 'did' && avatarVideoRef.current) {
            track.attach(avatarVideoRef.current);
          }
          addLog('info', 'ترک ویدیویی آواتار دریافت شد',
            `${participant.identity} · ${publication.source} · name=${publication.trackName || 'n/a'} · enabled=${publication.isEnabled}`);
        } else if (track.kind === Track.Kind.Audio) {
          setAssistantAudioTracks((current) => current.includes(track) ? current : [...current, track]);
          addLog('info', 'ترک صوتی دریافت شد', `${participant.identity} · ${publication.source}`);
        }
      });
      room.on(RoomEvent.TrackUnsubscribed, (track, _publication, participant) => {
        if (track.kind === Track.Kind.Video) {
          if (provider === 'did' && avatarVideoRef.current) track.detach(avatarVideoRef.current);
          setAvatarReady(false);
        }
        if (track.kind === Track.Kind.Audio) setAssistantAudioTracks((current) => current.filter((item) => item !== track));
        addLog('warning', 'ترک از اتاق لغو شد', `${participant.identity} · ${track.kind}`);
      });
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        const blocked = !room.canPlaybackAudio;
        setAudioNeedsGesture(blocked);
        addLog(blocked ? 'warning' : 'info', blocked ? 'مرورگر پخش خودکار صدا را مسدود کرد' : 'پخش صدا فعال است');
      });
      room.on(RoomEvent.Disconnected, (reason) => {
        addLog('warning', 'اتصال LiveKit قطع شد', String(reason || 'بدون جزئیات'));
      });

      await room.connect(data.serverUrl, data.token);
      startingRef.current = false;
      setPhase('connected');
      addLog('success', 'به اتاق LiveKit متصل شدیم', `room=${data.roomName || 'unknown'} · agent=${health?.agentName || 'configured agent'}`);

      // Microphone is optional: a permission/device error must not disable text chat.
      try {
        await room.localParticipant.setMicrophoneEnabled(true);
        setMicEnabled(true);
        addLog('success', 'میکروفون فعال شد');
      } catch (error) {
        setMicEnabled(false);
        addLog('warning', 'میکروفون در دسترس نیست؛ چت متنی همچنان فعال است', errorMessage(error));
      }
      try {
        await room.startAudio();
        setAudioNeedsGesture(!room.canPlaybackAudio);
      } catch (error) {
        setAudioNeedsGesture(true);
        addLog('warning', 'فعال‌سازی پخش صدا نیاز به تعامل کاربر دارد', errorMessage(error));
      }

      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.videoTrackPublications.values()) {
          if (publication.track) {
            setAvatarReady(true);
            // Publications already subscribed before these handlers were
            // registered never hit TrackSubscribed, so enable them here too.
            publication.setEnabled?.(true);
          }
        }
        for (const publication of participant.audioTrackPublications.values()) {
          if (publication.track) setAssistantAudioTracks((current) => current.includes(publication.track) ? current : [...current, publication.track]);
        }
      }
    } catch (error) {
      startingRef.current = false;
      try { await avatarPlayerRef.current?.detach(); } catch { /* session is already failing */ }
      avatarPlayerRef.current = null;
      avatarViewRef.current?.dispose();
      avatarViewRef.current = null;
      room?.disconnect();
      roomRef.current = null;
      setPhase('idle');
      setMicEnabled(false);
      setAvatarReady(false);
      setAssistantAudioTracks([]);
      addLog('error', 'شروع جلسه ناموفق بود', errorMessage(error));
    }
  }

  async function endSession() {
    addLog('info', 'درخواست پایان جلسه');
    startingRef.current = false;
    clearMotionWatch();
    try { await avatarPlayerRef.current?.detach(); } catch (error) { addLog('warning', 'جداسازی Spatius ناموفق بود', errorMessage(error)); }
    avatarPlayerRef.current = null;
    avatarViewRef.current?.dispose();
    avatarViewRef.current = null;
    lipSyncRef.current?.dispose();
    lipSyncRef.current = null;
    roomRef.current?.disconnect();
    roomRef.current = null;
    setPhase('idle');
    setMicEnabled(false);
    setAvatarReady(false);
    setAssistantAudioTracks([]);
    setAudioNeedsGesture(false);
    setDraftTranscript('');
  }

  async function toggleMic() {
    const room = roomRef.current;
    if (!room) return;
    try {
      await room.localParticipant.setMicrophoneEnabled(!micEnabled);
      setMicEnabled(!micEnabled);
      addLog('info', micEnabled ? 'میکروفون خاموش شد' : 'میکروفون روشن شد');
    } catch (error) {
      addLog('error', 'تغییر وضعیت میکروفون ناموفق بود', errorMessage(error));
    }
  }

  // Every leftover room keeps an agent, and every agent holds one STT and one
  // TTS connection against the LiveKit Inference limit. Closing them is what
  // clears a 429 that keeps coming back.
  async function closeStaleSessions() {
    if (cleanupBusy) return;
    setCleanupBusy(true);
    addLog('info', 'درخواست بستن نشست‌های باز قبلی');
    try {
      const response = await fetch('/api/sessions/cleanup', { method: 'POST' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error([data.error, data.details].filter(Boolean).join('\n') || `HTTP ${response.status}`);
      const count = Array.isArray(data.closedRooms) ? data.closedRooms.length : 0;
      addLog(count ? 'success' : 'info', count ? `${count} نشست قبلی بسته شد` : 'نشست بازی برای بستن پیدا نشد');
    } catch (error) {
      addLog('error', 'بستن نشست‌های قبلی ناموفق بود', errorMessage(error));
    } finally {
      setCleanupBusy(false);
    }
  }

  async function enableAudioPlayback() {
    try {
      await roomRef.current?.startAudio();
      const stillBlocked = Boolean(roomRef.current && !roomRef.current.canPlaybackAudio);
      setAudioNeedsGesture(stillBlocked);
      addLog(stillBlocked ? 'warning' : 'success', stillBlocked ? 'پخش صدا هنوز مسدود است' : 'پخش صدا فعال شد');
    } catch (error) {
      setAudioNeedsGesture(true);
      addLog('error', 'فعال‌سازی صدا ناموفق بود', errorMessage(error));
    }
  }

  async function sendText(event) {
    event.preventDefault();
    const text = draft.trim().slice(0, 4000);
    const room = roomRef.current;
    if (!text || !room || phase !== 'connected') return;
    try {
      const payload = new TextEncoder().encode(JSON.stringify({ type: 'chat_input', text }));
      await room.localParticipant.publishData(payload, { reliable: true, topic: 'chat-input' });
      addChat('user', text, 'text');
      addLog('info', 'پیام متنی برای Agent ارسال شد', `${text.length} نویسه`);
      setDraft('');
    } catch (error) {
      addLog('error', 'ارسال پیام متنی ناموفق بود', errorMessage(error));
    }
  }

  async function copyLogs() {
    const output = logs.map((entry) => `[${entry.time}] [${entry.level.toUpperCase()}] ${entry.message}${entry.details ? `\n${entry.details}` : ''}`).join('\n\n');
    try {
      await navigator.clipboard.writeText(output);
      addLog('success', 'گزارش رویدادها کپی شد');
    } catch (error) {
      addLog('error', 'کپی گزارش ناموفق بود', errorMessage(error));
    }
  }

  const connected = phase === 'connected';
  // Health is the single source of truth so the agent and the browser never
  // disagree about whether the avatar is on.
  const avatarEnabled = Boolean(health?.avatarEnabled);
  // "spatius" drives the AvatarKit canvas, "did" is a plain LiveKit video track.
  const avatarProvider = health?.avatarProvider === 'did' ? 'did' : avatarEnabled ? 'spatius' : 'none';

  return (
    <div className="app-shell" dir="rtl">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><AudioLines size={18}/></span><div><strong>{health?.assistantName || 'سام'}</strong><small>دستیار فروش صوتی · محیط توسعه</small></div></div>
        <div className={`connection-pill ${connected ? 'is-connected' : ''}`}><span className="connection-dot"/>{connected ? 'متصل' : phase === 'connecting' ? 'در حال اتصال' : 'قطع'}</div>
      </header>

      <main className="page-content">
        <section className="intro-row">
          <div><span className="eyebrow">PROTOTYPE / DEPLOYMENT TEST</span><h1>گفتگو و عیب‌یابی</h1><p>اگر میکروفون کار نکرد، از چت متنی استفاده کنید. وضعیت سرویس‌ها و رخدادهای همین نشست پایین صفحه ثبت می‌شوند.</p></div>
          <div className="session-actions">
            {phase === 'idle' ? <button className="primary-button" onClick={startSession} disabled={phase === 'connecting'}><Wifi size={16}/> شروع نشست آزمایشی</button> : null}
            {phase === 'connecting' ? <button className="primary-button" disabled><Activity size={16}/> در حال اتصال...</button> : null}
            {connected && <>
              <button className={`secondary-button ${micEnabled ? 'selected' : ''}`} onClick={toggleMic}>{micEnabled ? <Mic size={16}/> : <MicOff size={16}/>} {micEnabled ? 'میکروفون روشن' : 'میکروفون خاموش'}</button>
              <button className="secondary-button" onClick={enableAudioPlayback}><Volume2 size={16}/> فعال‌سازی صدا</button>
              <button className="danger-button" onClick={endSession}><Square size={14}/> پایان نشست</button>
            </>}
          </div>
        </section>

        <section className="workspace-grid">
          <section className="panel chat-panel">
            <div className="panel-heading"><div><MessageSquareIcon/><div><h2>چت</h2><small>ارسال متن مستقیم به Agent</small></div></div><span className="mode-tag">صوت + متن</span></div>
            <div className="chat-stream" ref={chatRef} aria-live="polite">
              {chatMessages.length === 0 && !draftTranscript && <div className="empty-chat"><MessageSquareIcon/><strong>پیام‌ها اینجا نمایش داده می‌شوند</strong><span>برای چت متنی ابتدا نشست را شروع کنید؛ در صورت خطای میکروفون، همین ورودی فعال می‌ماند.</span></div>}
              {chatMessages.map((item) => <article className={`chat-message ${item.role}`} key={item.id}>
                <div className="message-meta"><strong>{item.role === 'assistant' ? 'Agent' : 'شما'}</strong><time>{item.time}</time>{item.source && <span>{item.source === 'text' ? 'متن' : item.source === 'voice' ? 'صدا' : ''}</span>}</div>
                <p>{item.text}</p>
              </article>)}
              {draftTranscript && <article className="chat-message user draft-message"><div className="message-meta"><strong>در حال تشخیص گفتار</strong></div><p>{draftTranscript}</p></article>}
            </div>
            <form className="chat-composer" onSubmit={sendText}>
              <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendText(event); } }} placeholder={connected ? 'پیامت را بنویس… (Enter برای ارسال)' : 'برای فعال‌شدن چت، نشست آزمایشی را شروع کن'} disabled={!connected} rows={2}/>
              <button className="send-button" type="submit" disabled={!connected || !draft.trim()} aria-label="ارسال پیام"><Send size={17}/></button>
            </form>
            <div className="chat-footnote">پیام‌ها در اتاق LiveKit همین نشست برای Agent ارسال می‌شوند.</div>
          </section>

          <aside className="right-column">
            {/* Remote audio must stay mounted even with the avatar off, otherwise
                the assistant is silent. With the avatar on, Spatius publishes
                that audio; with it off, the agent publishes its own TTS audio. */}
            <div className="audio-output" aria-hidden="true">{assistantAudioTracks.map((track) => (
              <RemoteAudioOutput
                key={track.sid}
                track={track}
                registry={assistantAudioRefs}
                onRegistered={(elements) => lipSyncRef.current?.setAudioElements(elements)}
              />
            ))}</div>
            {avatarEnabled ? <section className="panel video-panel">
              <div className="panel-heading"><div><Video size={17}/><div><h2>تصویر آواتار</h2><small>{avatarReady ? (avatarProvider === 'did' ? 'ترک ویدیوی D-ID دریافت شد' : 'داده‌ی حرکت آواتار دریافت شد') : connected ? (avatarProvider === 'did' ? 'در انتظار ویدیوی D-ID' : 'در انتظار داده‌ی حرکت Spatius') : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : ''}`}>{avatarReady ? 'آماده' : 'انتظار'}</span></div>
              <div className="video-stage">
                {/* D-ID publishes a real video track; Spatius renders into a canvas. */}
                <video ref={avatarVideoRef} className={`avatar-video ${avatarReady && avatarProvider === 'did' ? 'video-visible' : ''}`} autoPlay playsInline />
                <div ref={avatarContainerRef} className={`spatius-avatar ${avatarReady && avatarProvider === 'spatius' ? 'avatar-visible' : ''}`} />
                {!avatarReady && <div className="video-placeholder"><Video size={22}/><span>{connected ? (avatarProvider === 'did' ? 'در انتظار آواتار D-ID…' : 'در انتظار آواتار Spatius…') : 'نشستی فعال نیست'}</span></div>}
                {audioNeedsGesture && <button className="audio-prompt" onClick={enableAudioPlayback}>برای شنیدن پاسخ، کلیک کنید</button>}
              </div>
              <div className="video-meta"><span><span className={`tiny-dot ${avatarReady ? 'green' : ''}`}/>{avatarReady ? 'آواتار وصل است' : 'آواتار وصل نیست'}</span><span><Volume2 size={14}/> {assistantAudioTracks.length} ترک صوتی</span></div>
              {avatarProvider === 'spatius' && (
                <div className="lipsync-control">
                  <div className="lipsync-head">
                    <span>هماهنگی لب و صدا</span>
                    <strong>{lipSyncOffset} ms</strong>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="600"
                    step="10"
                    value={lipSyncOffset}
                    onChange={(event) => setLipSyncOffset(Number(event.target.value))}
                    aria-label="تأخیر شروع حرکت لب"
                  />
                  <small>
                    اگر لب‌ها <strong>زودتر</strong> از صدا حرکت می‌کنند عدد را زیاد کنید؛
                    اگر دیرتر، کم کنید. تغییر بلافاصله روی نوبت بعدی اثر می‌گذارد.
                  </small>
                </div>
              )}
            </section> : <section className="panel voice-panel">
              <div className="panel-heading"><div><AudioLines size={17}/><div><h2>صدا و متن</h2><small>آواتار خاموش است؛ STT، LLM و TTS کامل اجرا می‌شوند</small></div></div><span className="video-state ready">آماده</span></div>
              <div className="voice-body">
                <div className="voice-row"><span>ترک صوتی Agent</span><strong>{assistantAudioTracks.length}</strong></div>
                <div className="voice-row"><span>پخش صدا</span><strong>{audioNeedsGesture ? 'نیازمند کلیک' : connected ? 'فعال' : 'غیرفعال'}</strong></div>
                {audioNeedsGesture && <button className="secondary-button" onClick={enableAudioPlayback}>فعال‌سازی پخش صدا</button>}
                <button className="secondary-button" onClick={closeStaleSessions} disabled={cleanupBusy}>
                  <RefreshCw size={14}/> {cleanupBusy ? 'در حال بستن…' : 'بستن نشست‌های باز قبلی'}
                </button>
              </div>
            </section>}

            <section className="panel status-panel">
              <div className="panel-heading"><div><Activity size={17}/><div><h2>اطلاعات اجرا</h2><small>بدون نمایش secretها</small></div></div></div>
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
                  <div className="latency-head">
                    <span>زمان‌بندی آخرین نوبت</span>
                    <strong>{msLabel(latency.last.e2e_ms)}</strong>
                  </div>
                  {/* Highlighted: time from end of user question to start of assistant answer — user requested */}
                  {(latency.last.response_delay_ms ?? latency.last.stages?.response_delay) != null && (
                    <div className="latency-highlight" style={{background:'linear-gradient(135deg,#e8f5e9,#f1f8e9)', border:'1.5px solid #4caf50', borderRadius:'10px', padding:'10px 12px', margin:'8px 0 10px', display:'flex', justifyContent:'space-between', alignItems:'center'}}>
                      <span style={{fontWeight:700, color:'#2e7d32', fontSize:'13px'}}>⏱ پایان سوال → شروع پاسخ</span>
                      <strong style={{color:'#1b5e20', fontSize:'18px', letterSpacing:'0.3px'}}>{msLabel(latency.last.response_delay_ms ?? latency.last.stages.response_delay)}</strong>
                    </div>
                  )}
                  {LATENCY_STAGES.map(([key, label]) => (
                    latency.last.stages[key] === null || latency.last.stages[key] === undefined ? null : (
                      <div className="latency-row" key={key} style={key==='response_delay' ? {background:'#f9fff9', borderRadius:'6px', padding:'2px 6px', border:'1px solid #c8e6c9'} : undefined}>
                        <span>{label}{key==='response_delay' ? ' ⭐' : ''}</span>
                        <div className="latency-bar">
                          <i style={{ width: `${Math.min(100, ((latency.last.stages[key] || 0) / Math.max(latency.last.e2e_ms || latency.last.response_delay_ms || 1, 1)) * 100)}%`, background: key==='response_delay' ? '#4caf50' : undefined }}/>
                        </div>
                        <b>{msLabel(latency.last.stages[key])}</b>
                      </div>
                    )
                  ))}
                  <small>{latency.turns} نوبت اندازه‌گیری‌شده · LATENCY_LOG برای میلی‌ثانیه‌ی هر نوبت در لاگ</small>
                </div>
              )}
            </section>
          </aside>
        </section>

        <section className="panel logs-panel">
          <div className="panel-heading log-heading"><div><div className="log-icon"><Activity size={17}/></div><div><h2>گزارش نشست</h2><small>تمام رخدادهای مرورگر، API و Agent در این نشست · {logs.length} مورد</small></div></div><div className="log-actions"><button className="secondary-button compact" onClick={copyLogs}><Copy size={14}/> کپی گزارش</button><button className="secondary-button compact" onClick={() => setLogs([])}><Trash2 size={14}/> پاک‌کردن</button></div></div>
          <div className="log-list" ref={logRef} role="log" aria-live="polite">
            {logs.length === 0 && <div className="empty-logs">هنوز رویدادی ثبت نشده است.</div>}
            {logs.map((entry) => <details className={`log-entry level-${entry.level}`} key={entry.id} open={entry.level === 'error'}>
              <summary><time>{entry.time}</time><span className="level-label">{entry.level.toUpperCase()}</span><span className="log-message">{entry.message}</span><span className="details-indicator">{entry.details ? 'جزئیات' : ''}</span></summary>
              {entry.details && <pre>{entry.details}</pre>}
            </details>)}
          </div>
          <div className="log-disclaimer"><CircleAlert size={14}/> اطلاعات حساس را در گزارش‌ها کپی یا عمومی نکنید؛ متن گفتگو و جزئیات خطا ممکن است در اینجا ثبت شود.</div>
        </section>

        <footer className="footer"><span><WifiOff size={14}/> نسخه‌ی آزمایشی برای تست استقرار؛ تضمین پایداری یا امنیت تولیدی ندارد.</span><span>{logs.length} رخداد ذخیره‌شده در همین صفحه</span></footer>
      </main>
    </div>
  );
}

function MessageSquareIcon() {
  return <AudioLines size={17}/>;
}

createRoot(document.getElementById('root')).render(<App/>);