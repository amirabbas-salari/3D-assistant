import React from 'react';
import { Activity, AudioLines, Mic, MicOff, Video, Wifi, WifiOff, RefreshCw, Square, Volume2 } from 'lucide-react';
import ChatPanel from '../components/ChatPanel.jsx';
import VideoPanel from '../components/VideoPanel.jsx';
import StatusPanel from '../components/StatusPanel.jsx';
import LogsPanel from '../components/LogsPanel.jsx';
import TimelineChart from '../components/TimelineChart.jsx';
import ErrorBoundary from '../components/ErrorBoundary.jsx';
import RemoteAudioOutput from '../components/RemoteAudioOutput.jsx';
import { useAppState } from '../hooks/useAppState.js';
import { fetchHealth, createSession, cleanupSessions, createTavusConversation, endTavusConversation } from '../api/client.js';
import { errorMessage, messageTime } from '../lib/utils.js';
import { formatLatency } from '../lib/latency.js';

const MAX_CHAT_MESSAGES = 200;
const MAX_LOG_ENTRIES = 500;

export default function App() {
  const s = useAppState();
  const [tavusUrl, setTavusUrl] = React.useState(null);
  const [tavusStatus, setTavusStatus] = React.useState('');
  const [tavusConversationId, setTavusConversationId] = React.useState(null);
  const [tavusError, setTavusError] = React.useState('');
  const [avatarVideoTrack, setAvatarVideoTrack] = React.useState(null);
  const avatarVideoRef = React.useRef(null);

  function addLog(level, message, details = '') {
    s.setLogs((cur) => [...cur.slice(-(MAX_LOG_ENTRIES - 1)), { id: `${Date.now()}-${Math.random()}`, time: messageTime(), level: String(level || 'info').toLowerCase(), message: String(message || ''), details: details ? String(details) : '' }]);
  }
  function addChat(role, text, source = '') {
    if (!String(text || '').trim()) return;
    s.setChatMessages((cur) => [...cur.slice(-(MAX_CHAT_MESSAGES - 1)), { id: `${Date.now()}-${Math.random()}`, role, text: String(text), source, time: messageTime() }]);
  }

  const refreshHealth = React.useCallback(() => {
    fetchHealth().then((data) => { s.setHealth(data); addLog(data.configured ? 'info' : 'warning', 'بررسی پیکربندی API انجام شد', JSON.stringify(data, null, 2)); }).catch((e) => { s.setHealth({ configured: false }); addLog('error', 'دسترسی به API ناموفق بود', errorMessage(e)); });
  }, []);
  React.useEffect(() => { refreshHealth(); }, []);
  React.useEffect(() => {
    const onErr = (e) => addLog('error', 'خطای اجرا در مرورگر', e.message || 'خطای JavaScript');
    const onRej = (e) => addLog('error', 'وعده‌ی ناموفق در مرورگر', errorMessage(e.reason));
    window.addEventListener('error', onErr); window.addEventListener('unhandledrejection', onRej);
    return () => { window.removeEventListener('error', onErr); window.removeEventListener('unhandledrejection', onRej); };
  }, []);
  React.useEffect(() => { if (s.chatRef.current) s.chatRef.current.scrollTop = s.chatRef.current.scrollHeight; }, [s.chatMessages, s.draftTranscript]);
  React.useEffect(() => { if (s.logRef.current) s.logRef.current.scrollTop = s.logRef.current.scrollHeight; }, [s.logs]);

  function doCreateTavus(roomName) {
    // فقط در حالت CVI استفاده می‌شود — livekit mode ویدیو را از LiveKit track می‌گیرد
    const mode = s.health?.tavusAvatarMode || 'livekit';
    if (mode === 'livekit') return;
    setTavusError('');
    setTavusStatus('در حال اتصال به Tavus…');
    createTavusConversation({ conversation_name: `sam-${roomName || Date.now()}` })
      .then((t) => {
        const url = t.conversationUrl || t.conversation_url;
        if (!url) throw new Error('Tavus conversation_url خالی برگشت — پاسخ: ' + JSON.stringify(t));
        setTavusUrl(url);
        setTavusConversationId(t.conversationId || t.conversation_id);
        setTavusStatus('متصل');
        s.setAvatarReady(true);
        addLog('success', 'Tavus conversation ساخته شد', `url=${url} id=${t.conversationId || t.conversation_id}`);
      })
      .catch((e) => {
        const msg = errorMessage(e);
        setTavusStatus('خطا');
        setTavusError(msg);
        addLog('error', 'ساخت Tavus conversation ناموفق بود', msg + '\n\nعلت‌های رایج:\n• TAVUS_API_KEY اشتباه یا خالی (.env)\n• TAVUS_REPLICA_ID / TAVUS_PERSONA_ID اشتباه — از platform.tavus.io کپی کنید\n• AVATAR_ENABLED هنوز false است — باید true شود و API ری‌استارت شود\n• Tavus حساب شما محدود شده (401/403) — داشبورد را چک کنید');
      });
  }

  async function startSession() {
    if (s.phase !== 'idle' || s.startingRef.current) return;
    s.startingRef.current = true; s.setPhase('connecting'); addLog('info', 'درخواست ایجاد جلسه ارسال شد');
    setTavusError(''); setTavusUrl(null); setTavusConversationId(null); setTavusStatus(''); setAvatarVideoTrack(null); s.setAvatarReady(false);
    let room;
    try {
      const [data, livekit] = await Promise.all([createSession({}), import('livekit-client')]);
      const { Room, RoomEvent, Track } = livekit;
      const provider = data.avatarProvider || s.health?.avatarProvider || 'none';
      const tavusMode = data.tavusAvatarMode || s.health?.tavusAvatarMode || 'livekit';
      room = new Room({ adaptiveStream: false, dynacast: true });
      s.roomRef.current = room;
      if (provider === 'none') addLog('info', 'آواتار خاموش است', 'AVATAR_ENABLED=false · فقط صدا و متن فعال است');
      else if (provider === 'tavus') {
        if (tavusMode === 'livekit') {
          addLog('info', 'آواتار Tavus (livekit lip-sync) فعال است', `replica=${data.tavusReplicaId || 'env'} persona=${data.tavusPersonaId || 'env'} — صدای TTS پروژه به آواتار stream می‌شود، ویدیو از LiveKit می‌آید`);
          setTavusStatus('در انتظار ویدیوی آواتار…');
        } else {
          addLog('info', 'آواتار Tavus (CVI Daily) فعال است', `replica=${data.tavusReplicaId || 'env'} persona=${data.tavusPersonaId || 'env'} — در حال ساخت conversation...`);
          doCreateTavus(data.roomName);
        }
      } else if (provider === 'spatius') {
        addLog('info', 'آواتار Spatius فعال است', `app=${data.spatiusAppId || 'env'} avatar=${data.spatiusAvatarId || 'env'} region=${data.spatiusRegion || 'auto'} — رندر AvatarKit روی کلاینت، صدا از LiveKit`);
        setTavusStatus('در انتظار Spatius motion…');
      } else {
        addLog('warning', `آواتار provider ناشناس: ${provider}`, 'مقادیر مجاز: tavus, spatius, none');
      }
      refreshHealth();

      room.on(RoomEvent.DataReceived, (payload) => {
        try {
          const packet = JSON.parse(new TextDecoder().decode(payload));
          if (packet.type === 'system_log') addLog(packet.level, packet.message, packet.details || '');
          else if (packet.type === 'user_transcript' && typeof packet.text === 'string') { if (packet.final) { addChat('user', packet.text, 'voice'); s.setDraftTranscript(''); } else s.setDraftTranscript(packet.text); }
          else if (packet.type === 'latency') { s.setLatency(packet); if (packet.last) addLog('info', 'زمان‌بندی نوبت', formatLatency(packet)); }
          else if (packet.type === 'assistant_reply' && typeof packet.text === 'string') { addChat('assistant', packet.text, 'agent'); addLog('info', 'پاسخ متنی Agent دریافت شد', `${packet.text.length} نویسه`); }
        } catch (error) { addLog('warning', 'بسته‌ی داده قابل خواندن نبود', errorMessage(error)); }
      });
      room.on(RoomEvent.ParticipantConnected, (p) => addLog('info', 'شرکت‌کننده به اتاق پیوست', p.identity));
      room.on(RoomEvent.ParticipantDisconnected, (p) => addLog('warning', 'شرکت‌کننده از اتاق خارج شد', p.identity));
      room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        if (track.kind === Track.Kind.Audio) {
          s.setAssistantAudioTracks((cur) => cur.includes(track) ? cur : [...cur, track]);
          addLog('info', 'ترک صوتی دریافت شد', `${participant.identity} · ${publication.source}`);
        } else if (track.kind === Track.Kind.Video) {
          const isAvatar = participant.identity.includes('tavus') || participant.identity.includes('avatar') || participant.identity.includes('spatius');
          if (isAvatar) {
            setAvatarVideoTrack(track);
            s.setAvatarReady(true);
            setTavusStatus('متصل');
            addLog('success', `ویدیوی آواتار ${provider} دریافت شد`, `${participant.identity}`);
          } else {
            s.setAvatarReady(true);
            addLog('info', 'ترک ویدیویی دریافت شد', `${participant.identity}`);
          }
        }
      });
      room.on(RoomEvent.TrackUnsubscribed, (track, _pub, participant) => {
        if (track.kind === Track.Kind.Audio) s.setAssistantAudioTracks((cur) => cur.filter((item) => item !== track));
        if (track.kind === Track.Kind.Video) {
          setAvatarVideoTrack(null);
          s.setAvatarReady(false);
        }
        addLog('warning', 'ترک از اتاق لغو شد', `${participant.identity} · ${track.kind}`);
      });
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => { const blocked = !room.canPlaybackAudio; s.setAudioNeedsGesture(blocked); addLog(blocked ? 'warning' : 'info', blocked ? 'مرورگر پخش خودکار صدا را مسدود کرد' : 'پخش صدا فعال است'); });
      room.on(RoomEvent.Disconnected, (reason) => addLog('warning', 'اتصال LiveKit قطع شد', String(reason || 'بدون جزئیات')));
      await room.connect(data.serverUrl, data.token);
      s.startingRef.current = false; s.setPhase('connected');
      addLog('success', 'به اتاق LiveKit متصل شدیم', `room=${data.roomName || 'unknown'} · agent=${s.health?.agentName || 'configured agent'} · avatarProvider=${provider}`);
      try { await room.localParticipant.setMicrophoneEnabled(true); s.setMicEnabled(true); addLog('success', 'میکروفون فعال شد'); } catch (error) { s.setMicEnabled(false); addLog('warning', 'میکروفون در دسترس نیست؛ چت متنی همچنان فعال است', errorMessage(error)); }
      try { await room.startAudio(); s.setAudioNeedsGesture(!room.canPlaybackAudio); } catch (error) { s.setAudioNeedsGesture(true); addLog('warning', 'فعال‌سازی پخش صدا نیاز به تعامل کاربر دارد', errorMessage(error)); }
      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.audioTrackPublications.values()) if (publication.track) s.setAssistantAudioTracks((cur) => cur.includes(publication.track) ? cur : [...cur, publication.track]);
        for (const pub of participant.videoTrackPublications.values()) if (pub.track) { setAvatarVideoTrack(pub.track); s.setAvatarReady(true); }
      }
    } catch (error) {
      s.startingRef.current = false;
      s.setPhase('idle'); s.setMicEnabled(false); s.setAvatarReady(false); s.setAssistantAudioTracks([]); setTavusUrl(null); setTavusConversationId(null); setAvatarVideoTrack(null);
      addLog('error', 'شروع جلسه ناموفق بود', errorMessage(error));
    }
  }

  async function endSession() {
    addLog('info', 'درخواست پایان جلسه'); s.startingRef.current = false;
    if (tavusConversationId) {
      try { await endTavusConversation(tavusConversationId); addLog('info', 'Tavus conversation پایان یافت'); } catch (e) { addLog('warning', 'پایان Tavus ناموفق', errorMessage(e)); }
      setTavusConversationId(null); setTavusUrl(null); setTavusStatus(''); setTavusError('');
    }
    setAvatarVideoTrack(null);
    s.roomRef.current?.disconnect(); s.roomRef.current = null; s.setPhase('idle'); s.setMicEnabled(false); s.setAvatarReady(false); s.setAssistantAudioTracks([]); s.setAudioNeedsGesture(false); s.setDraftTranscript(''); setTavusStatus('');
  }
  async function toggleMic() { const room = s.roomRef.current; if (!room) return; try { await room.localParticipant.setMicrophoneEnabled(!s.micEnabled); s.setMicEnabled(!s.micEnabled); addLog('info', s.micEnabled ? 'میکروفون خاموش شد' : 'میکروفون روشن شد'); } catch (e) { addLog('error', 'تغییر وضعیت میکروفون ناموفق بود', errorMessage(e)); } }
  async function closeStaleSessions() { if (s.cleanupBusy) return; s.setCleanupBusy(true); addLog('info', 'درخواست بستن نشست‌های باز قبلی'); try { const data = await cleanupSessions(); const count = Array.isArray(data.closedRooms) ? data.closedRooms.length : 0; addLog(count ? 'success' : 'info', count ? `${count} نشست قبلی بسته شد` : 'نشست بازی برای بستن پیدا نشد'); } catch (e) { addLog('error', 'بستن نشست‌های قبلی ناموفق بود', errorMessage(e)); } finally { s.setCleanupBusy(false); } }
  async function enableAudioPlayback() { try { await s.roomRef.current?.startAudio(); const stillBlocked = Boolean(s.roomRef.current && !s.roomRef.current.canPlaybackAudio); s.setAudioNeedsGesture(stillBlocked); addLog(stillBlocked ? 'warning' : 'success', stillBlocked ? 'پخش صدا هنوز مسدود است' : 'پخش صدا فعال شد'); } catch (e) { s.setAudioNeedsGesture(true); addLog('error', 'فعال‌سازی صدا ناموفق بود', errorMessage(e)); } }
  async function sendText(e) { e.preventDefault(); const text = s.draft.trim().slice(0, 4000); const room = s.roomRef.current; if (!text || !room || s.phase !== 'connected') return; try { const payload = new TextEncoder().encode(JSON.stringify({ type: 'chat_input', text })); await room.localParticipant.publishData(payload, { reliable: true, topic: 'chat-input' }); addChat('user', text, 'text'); addLog('info', 'پیام متنی برای Agent ارسال شد', `${text.length} نویسه`); s.setDraft(''); } catch (e) { addLog('error', 'ارسال پیام متنی ناموفق بود', errorMessage(e)); } }
  async function copyLogs() { const output = s.logs.map((en) => `[${en.time}] [${en.level.toUpperCase()}] ${en.message}${en.details ? `\n${en.details}` : ''}`).join('\n\n'); try { await navigator.clipboard.writeText(output); addLog('success', 'گزارش رویدادها کپی شد'); } catch (e) { addLog('error', 'کپی گزارش ناموفق بود', errorMessage(e)); } }

  const connected = s.phase === 'connected';
  const avatarEnabled = Boolean(s.health?.avatarEnabled);
  const avatarProvider = s.health?.avatarProvider || 'none';

  function retryTavus() {
    const roomName = s.roomRef.current?.name || `retry-${Date.now()}`;
    doCreateTavus(roomName);
  }

  return (
    <div className="app-shell" dir="rtl">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><AudioLines size={18} /></span><div><strong>{s.health?.assistantName || 'سام'}</strong><small>دستیار فروش صوتی · محیط توسعه</small></div></div>
        <div className={`connection-pill ${connected ? 'is-connected' : ''}`}><span className="connection-dot" />{connected ? 'متصل' : s.phase === 'connecting' ? 'در حال اتصال' : 'قطع'}</div>
      </header>
      <main className="page-content">
        <section className="intro-row">
          <div><span className="eyebrow">PROTOTYPE / DEPLOYMENT TEST</span><h1>گفتگو و عیب‌یابی</h1><p>اگر میکروفون کار نکرد، از چت متنی استفاده کنید. وضعیت سرویس‌ها و رخدادهای همین نشست پایین صفحه ثبت می‌شوند.</p></div>
          <div className="session-actions">
            {s.phase === 'idle' ? <button className="primary-button" onClick={startSession} disabled={s.phase === 'connecting'}><Wifi size={16} /> شروع نشست آزمایشی</button> : null}
            {s.phase === 'connecting' ? <button className="primary-button" disabled><Activity size={16} /> در حال اتصال...</button> : null}
            {connected && <><button className={`secondary-button ${s.micEnabled ? 'selected' : ''}`} onClick={toggleMic}>{s.micEnabled ? <Mic size={16} /> : <MicOff size={16} />} {s.micEnabled ? 'میکروفون روشن' : 'میکروفون خاموش'}</button><button className="secondary-button" onClick={enableAudioPlayback}><Volume2 size={16} /> فعال‌سازی صدا</button><button className="danger-button" onClick={endSession}><Square size={14} /> پایان نشست</button></>}
          </div>
        </section>
        <section className="workspace-grid">
          <div className="left-column">
            <ErrorBoundary>
              <ChatPanel chatMessages={s.chatMessages} draftTranscript={s.draftTranscript} draft={s.draft} setDraft={s.setDraft} connected={connected} sendText={sendText} chatRef={s.chatRef} />
            </ErrorBoundary>
            <ErrorBoundary>
              <TimelineChart latency={s.latency} />
            </ErrorBoundary>
          </div>
          <aside className="right-column">
            <div className="audio-output" aria-hidden="true">{s.assistantAudioTracks.map((track) => <RemoteAudioOutput key={track.sid} track={track} registry={s.assistantAudioRefs} />)}</div>
            <VideoPanel avatarEnabled={avatarEnabled} avatarProvider={avatarProvider} avatarReady={s.avatarReady} connected={connected} assistantAudioTracks={s.assistantAudioTracks} audioNeedsGesture={s.audioNeedsGesture} enableAudioPlayback={enableAudioPlayback} tavusUrl={tavusUrl} tavusStatus={tavusStatus} tavusError={tavusError} health={s.health} onRetryTavus={retryTavus} avatarVideoTrack={avatarVideoTrack} avatarVideoRef={avatarVideoRef} />
            <ErrorBoundary>
              <StatusPanel health={s.health} latency={s.latency} connected={connected} />
            </ErrorBoundary>
            {s.audioNeedsGesture && !avatarEnabled && <button className="secondary-button" onClick={closeStaleSessions} disabled={s.cleanupBusy}><RefreshCw size={14} /> {s.cleanupBusy ? 'در حال بستن…' : 'بستن نشست‌های باز قبلی'}</button>}
          </aside>
        </section>
        <LogsPanel logs={s.logs} setLogs={s.setLogs} copyLogs={copyLogs} logRef={s.logRef} />
        <footer className="footer"><span><WifiOff size={14} /> نسخه‌ی آزمایشی برای تست استقرار؛ تضمین پایداری یا امنیت تولیدی ندارد.</span><span>{s.logs.length} رخداد ذخیره‌شده در همین صفحه</span></footer>
      </main>
    </div>
  );
}
