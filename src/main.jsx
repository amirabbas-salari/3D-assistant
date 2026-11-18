import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity, AudioLines, Check, CircleAlert, Copy, Mic, MicOff,
  Send, Square, Trash2, Video, Volume2, Wifi, WifiOff,
} from 'lucide-react';
import './styles.css';

function RemoteAudioOutput({ track }) {
  const audioRef = useRef(null);

  useEffect(() => {
    if (!audioRef.current) return undefined;
    track.attach(audioRef.current);
    return () => track.detach(audioRef.current);
  }, [track]);

  return <audio ref={audioRef} autoPlay playsInline className="remote-audio-output" />;
}

function messageTime() {
  return new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
  const roomRef = useRef(null);
  const avatarContainerRef = useRef(null);
  const avatarPlayerRef = useRef(null);
  const avatarViewRef = useRef(null);
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

  async function probeMotionFrames() {
    const room = roomRef.current;
    if (!room) return;
    const sample = async () => {
      let received = 0;
      let decoded = 0;
      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.videoTrackPublications.values()) {
          const track = publication.track;
          if (!track?.getRTCStatsReport) continue;
          try {
            const report = await track.getRTCStatsReport();
            report?.forEach((entry) => {
              if (entry.type !== 'inbound-rtp') return;
              received += entry.framesReceived || 0;
              decoded += entry.framesDecoded || 0;
            });
          } catch { /* stats are best-effort diagnostics */ }
        }
      }
      return { received, decoded };
    };
    const before = await sample();
    window.setTimeout(async () => {
      const after = await sample();
      const received = after.received - before.received;
      const decoded = after.decoded - before.decoded;
      if (received > 0) {
        addLog('success', 'فریم‌های حرکت آواتار در حال دریافت است', `در یک ثانیه: ${received} فریم · decoded ${decoded}`);
      } else {
        addLog('error', 'هیچ فریم حرکتی در طول صحبت دریافت نشد',
          'ترک حرکت Spatius متوقف یا پخش‌نشده است؛ لب‌ها تکان نمی‌خورند. adaptiveStream و وضعیت publication را بررسی کنید.');
      }
    }, 1000);
  }

  async function startSession() {
    if (phase !== 'idle') return;
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
      // adaptiveStream MUST stay off. Spatius publishes motion data on a video
      // track and attaches it to a hidden (display:none) <video> element; with
      // adaptiveStream on, LiveKit sees "nobody is watching" and tells the
      // server to pause that track, so no motion frames arrive and the avatar
      // stops moving its lips (audio keeps playing). dynacast only affects
      // publishing, so it stays enabled.
      room = new Room({ adaptiveStream: false, dynacast: true, singlePeerConnection: false });
      roomRef.current = room;

      // Spatius publishes motion data on a LiveKit video track. Attach AvatarKit
      // to this app-owned room before connecting; the track is not an HTML video.
      try {
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
        const avatar = await avatarKit.AvatarManager.shared.load(data.spatiusAvatarId);
        const avatarView = new avatarKit.AvatarView(avatar, avatarContainerRef.current);
        avatarViewRef.current = avatarView;
        await new Promise((resolve, reject) => {
          const timeout = window.setTimeout(() => reject(new Error('رندر اولیه‌ی آواتار Spatius بیش از حد طول کشید')), 20000);
          avatarView.onFirstRendering = () => {
            window.clearTimeout(timeout);
            resolve();
          };
        });
        const player = new avatarRtc.AvatarPlayer(new avatarRtc.LiveKitProvider(), avatarView);
        player.on('error', (error) => addLog('error', 'خطای SDK آواتار Spatius', errorMessage(error)));
        // Motion (lip-sync) state comes from Spatius over the RTC adapter, not
        // from AvatarKit's own callback, which never fires in RTC mode.
        player.on('conversation-state-changed', (state) => {
          if (state === 'speaking') {
            addLog('info', 'آواتار شروع به صحبت کرد', 'حالت حرکتی Spatius: speaking');
            // Measure the motion track while it should be moving. Zero new
            // frames means the track is paused or not arriving; frames arriving
            // but a static face means a renderer problem instead.
            void probeMotionFrames();
            return;
          }
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
          addLog('info', 'ترک حرکت آواتار دریافت شد',
            `${participant.identity} · ${publication.source} · name=${publication.trackName || 'n/a'} · enabled=${publication.isEnabled}`);
        } else if (track.kind === Track.Kind.Audio) {
          setAssistantAudioTracks((current) => current.includes(track) ? current : [...current, track]);
          addLog('info', 'ترک صوتی دریافت شد', `${participant.identity} · ${publication.source}`);
        }
      });
      room.on(RoomEvent.TrackUnsubscribed, (track, _publication, participant) => {
        if (track.kind === Track.Kind.Video) setAvatarReady(false);
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
    try { await avatarPlayerRef.current?.detach(); } catch (error) { addLog('warning', 'جداسازی Spatius ناموفق بود', errorMessage(error)); }
    avatarPlayerRef.current = null;
    avatarViewRef.current?.dispose();
    avatarViewRef.current = null;
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

  return (
    <div className="app-shell" dir="rtl">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><AudioLines size={18}/></span><div><strong>دستیار صوتی</strong><small>نمونه‌ی آزمایشی · محیط توسعه</small></div></div>
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
            <section className="panel video-panel">
              <div className="panel-heading"><div><Video size={17}/><div><h2>تصویر آواتار</h2><small>{avatarReady ? 'داده‌ی حرکت آواتار دریافت شد' : connected ? 'در انتظار داده‌ی حرکت Spatius' : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : ''}`}>{avatarReady ? 'آماده' : 'انتظار'}</span></div>
              <div className="video-stage">
                <div ref={avatarContainerRef} className={`spatius-avatar ${avatarReady ? 'avatar-visible' : ''}`} />
                {!avatarReady && <div className="video-placeholder"><Video size={22}/><span>{connected ? 'در انتظار آواتار Spatius…' : 'نشستی فعال نیست'}</span></div>}
                <div className="audio-output" aria-hidden="true">{assistantAudioTracks.map((track) => <RemoteAudioOutput key={track.sid} track={track}/>)}</div>
                {audioNeedsGesture && <button className="audio-prompt" onClick={enableAudioPlayback}>برای شنیدن پاسخ، کلیک کنید</button>}
              </div>
              <div className="video-meta"><span><span className={`tiny-dot ${avatarReady ? 'green' : ''}`}/>{avatarReady ? 'آواتار وصل است' : 'آواتار وصل نیست'}</span><span><Volume2 size={14}/> {assistantAudioTracks.length} ترک صوتی</span></div>
            </section>

            <section className="panel status-panel">
              <div className="panel-heading"><div><Activity size={17}/><div><h2>اطلاعات اجرا</h2><small>بدون نمایش secretها</small></div></div></div>
              <div className="status-grid">
                <div><span>API</span><strong className={health?.configured ? 'status-good' : health ? 'status-bad' : ''}>{health ? (health.configured ? 'پیکربندی‌شده' : 'ناقص') : 'در حال بررسی'}</strong></div>
                <div><span>Agent</span><strong>{health?.agentName || 'نامشخص'}</strong></div>
                <div><span>LLM</span><strong>{health?.llmModel || 'LiveKit Inference'}</strong></div>
                <div><span>اتاق</span><strong>{connected ? 'متصل' : '—'}</strong></div>
              </div>
              <p className="status-note">اطلاعات سلامت API فقط وجود تنظیمات سرور را بررسی می‌کند و اتصال واقعی Spatius یا مدل را تضمین نمی‌کند.</p>
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