import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AudioLines, ArrowUpLeft, Check, CircleHelp, Mic, MicOff, MoreHorizontal,
  Phone, PhoneOff, Settings2, ShieldCheck, Sparkles, Video, Volume2, Waves,
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

function App() {
  const [phase, setPhase] = useState('idle');
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  const [openingLine, setOpeningLine] = useState('');
  const [muted, setMuted] = useState(false);
  const [transcriptLines, setTranscriptLines] = useState([]);
  const [draftTranscript, setDraftTranscript] = useState('');
  const [assistantVideo, setAssistantVideo] = useState(null);
  const [assistantAudioTracks, setAssistantAudioTracks] = useState([]);
  const [audioNeedsGesture, setAudioNeedsGesture] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const roomRef = useRef(null);
  const videoRef = useRef(null);
  const transcriptRef = useRef(null);

  useEffect(() => {
    fetch('/api/health').then((r) => r.json()).then(setHealth).catch(() => setHealth({ configured: false }));
  }, []);

  useEffect(() => {
    if (!assistantVideo || !videoRef.current) return undefined;
    assistantVideo.attach(videoRef.current);
    return () => assistantVideo.detach(videoRef.current);
  }, [assistantVideo]);

  useEffect(() => {
    if (transcriptRef.current) transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [transcriptLines, draftTranscript]);

  async function startConversation() {
    setPhase('connecting');
    setError('');
    try {
      const response = await fetch('/api/session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: openingLine }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'شروع گفتگو با خطا روبه‌رو شد.');
      const { Room, RoomEvent, Track } = await import('livekit-client');
      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;
      setTranscriptLines([]);
      setDraftTranscript('');
      room.on(RoomEvent.DataReceived, (payload) => {
        try {
          const message = JSON.parse(new TextDecoder().decode(payload));
          if (typeof message.text !== 'string') return;
          if (message.type === 'user_transcript') {
            if (message.final) {
              setTranscriptLines((lines) => [...lines, { id: `${Date.now()}-${Math.random()}`, role: 'user', text: message.text }].slice(-40));
              setDraftTranscript('');
            } else {
              setDraftTranscript(message.text);
            }
          } else if (message.type === 'assistant_reply') {
            setTranscriptLines((lines) => [...lines, { id: `${Date.now()}-${Math.random()}`, role: 'assistant', text: message.text }].slice(-40));
          }
        } catch (parseError) {
          console.warn('Could not parse transcript data packet', parseError);
        }
      });
      room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
        if (participant.identity === room.localParticipant.identity) return;
        if (track.kind === Track.Kind.Video) setAssistantVideo(track);
        if (track.kind === Track.Kind.Audio) setAssistantAudioTracks((tracks) => tracks.includes(track) ? tracks : [...tracks, track]);
      });
      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === Track.Kind.Video) setAssistantVideo(null);
        if (track.kind === Track.Kind.Audio) setAssistantAudioTracks((tracks) => tracks.filter((item) => item !== track));
      });
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        setAudioNeedsGesture(!room.canPlaybackAudio);
      });
      await room.connect(data.serverUrl, data.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      try {
        await room.startAudio();
        setAudioNeedsGesture(!room.canPlaybackAudio);
      } catch {
        setAudioNeedsGesture(true);
      }
      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.videoTrackPublications.values()) {
          if (publication.track) setAssistantVideo(publication.track);
        }
        for (const publication of participant.audioTrackPublications.values()) {
          if (publication.track) setAssistantAudioTracks((tracks) => tracks.includes(publication.track) ? tracks : [...tracks, publication.track]);
        }
      }
      setPhase('live');
    } catch (e) {
      roomRef.current?.disconnect();
      roomRef.current = null;
      setAssistantAudioTracks([]);
      setAudioNeedsGesture(false);
      setError(e.message || 'ارتباط برقرار نشد. دوباره تلاش کنید.');
      setPhase('idle');
    }
  }

  function endConversation() {
    roomRef.current?.disconnect();
    roomRef.current = null;
    setAssistantVideo(null);
    setAssistantAudioTracks([]);
    setAudioNeedsGesture(false);
    setPhase('idle');
    setMuted(false);
    setOpeningLine('');
  }

  async function toggleMute() {
    const nextMuted = !muted;
    await roomRef.current?.localParticipant.setMicrophoneEnabled(!nextMuted);
    setMuted(nextMuted);
  }

  async function enableAudioPlayback() {
    try {
      await roomRef.current?.startAudio();
      setAudioNeedsGesture(Boolean(roomRef.current && !roomRef.current.canPlaybackAudio));
    } catch {
      setAudioNeedsGesture(true);
    }
  }

  const isLive = phase === 'live';

  return (
    <div className="app-shell" dir="rtl">
      <main className="workspace" id="talk">
        <button className="icon-button settings-button" aria-label="تنظیمات" onClick={() => setShowSettings(!showSettings)}><Settings2 size={19}/></button>
        <section className={`call-layout ${isLive ? 'call-layout-live' : ''}`} aria-label="محیط گفتگوی صوتی و تصویری">
          <div className={`video-panel ${isLive ? 'video-panel-live' : ''}`}>
            <div className="panel-topline"><span className="panel-label"><span className={`status-dot ${isLive ? 'green pulse' : ''}`}/>{isLive ? 'در حال گفتگو' : 'فضای گفتگوی تصویری'}</span><button className="icon-button dots-button" aria-label="گزینه‌های بیشتر"><MoreHorizontal size={21}/></button></div>
            {isLive ? (
              <div className="video-frame-wrap">
                <video ref={videoRef} className={`assistant-video ${assistantVideo ? 'visible' : ''}`} autoPlay playsInline />
                <div className="audio-track-output" aria-hidden="true">
                  {assistantAudioTracks.map((track) => <RemoteAudioOutput key={track.sid} track={track} />)}
                </div>
                {audioNeedsGesture && <button className="enable-audio-button" onClick={enableAudioPlayback}><Volume2 size={15}/> برای شنیدن صدا بزن</button>}
                {!assistantVideo && <div className="avatar-waiting"><div className="waiting-orb"><AudioLines size={28}/></div><strong>در حال آماده‌شدن است</strong><span>چند لحظه صبر کن...</span></div>}
                <div className="live-badge"><span className="live-dot"/> زنده</div>
                <div className="call-controls">
                  <button className="call-control" onClick={enableAudioPlayback} aria-label="فعال‌کردن پخش صدای"><Volume2 size={17}/></button>
                  <button className={`call-control ${muted ? 'control-muted' : ''}`} onClick={toggleMute} aria-label={muted ? 'روشن‌کردن میکروفون' : 'بی‌صداکردن میکروفون'}>{muted ? <MicOff size={17}/> : <Mic size={17}/>}</button>
                  <span>{muted ? 'میکروفون خاموش' : 'میکروفون روشن'}</span>
                </div>
              </div>
            ) : (
              <div className="visual-stage">
                <div className="stage-orbit orbit-one"/><div className="stage-orbit orbit-two"/><div className="stage-orbit orbit-three"/>
                <div className="stage-glow"/>
                <div className="assistant-avatar"><div className="avatar-shine"/><span className="avatar-face">ه</span><span className="avatar-wave wave-a"/><span className="avatar-wave wave-b"/></div>
                <div className="floating-note note-top"><span className="note-icon"><Waves size={15}/></span><span>فارسی را می‌فهمم</span><Check size={13}/></div>
                <div className="floating-note note-bottom"><span className="equalizer"><i/><i/><i/><i/><i/></span><span>آماده‌ی گفتگو</span></div>
              </div>
            )}
            <div className="video-footer">
              <div className="voice-status"><span className="sound-icon"><Volume2 size={16}/></span><div><strong>{isLive ? (assistantAudioTracks.length ? 'ترک صدای آواتار متصل است' : 'در انتظار صدای آواتار') : 'صدای طبیعی و روان'}</strong><small>{isLive ? (audioNeedsGesture ? 'برای پخش، دکمه‌ی صدا را بزن' : `تعداد ترک‌های صوتی: ${assistantAudioTracks.length}`) : 'به زبان فارسی با هم صحبت می‌کنیم'}</small></div></div>
              <div className="video-quality"><span className="quality-dot"/> HD</div>
            </div>
          </div>

          <aside className="side-panel">
            <div className="side-heading"><div><span className="side-kicker">جلسه‌ی جدید</span><h2>با چی کمکت کنم؟</h2></div><span className="sparkle-bubble"><Sparkles size={17}/></span></div>
            <p className="side-description">{isLive ? 'حرف‌های تشخیص‌داده‌شده و متن پاسخ اینجا می‌آیند؛ کمک می‌کند بفهمیم مدل زبانی جواب داده است یا نه.' : 'از یک سؤال ساده تا یک گفتگوی طولانی؛ از همین‌جا شروع کن.'}</p>
            {isLive ? (
              <>
                <div className="suggestion-label">متن زنده‌ی گفتگو</div>
                <div className="transcript-box" ref={transcriptRef} aria-live="polite" aria-label="متن تشخیص‌داده‌شده از صحبت‌های شما">
                  {transcriptLines.length === 0 && !draftTranscript && <div className="transcript-empty"><span className="online-indicator"/>منتظر اولین جمله‌ات هستم...</div>}
                  {transcriptLines.map((line) => <div className={`transcript-line ${line.role === 'assistant' ? 'transcript-assistant' : ''}`} key={line.id}><span>{line.role === 'assistant' ? 'همراه' : 'شما'}</span><p>{line.text}</p></div>)}
                  {draftTranscript && <div className="transcript-line transcript-partial"><span>در حال تشخیص</span><p>{draftTranscript}</p></div>}
                </div>
              </>
            ) : (
              <>
                <div className="suggestion-label">شاید این‌ها شروع خوبی باشند</div>
                <div className="suggestions">
                  <button className="suggestion" onClick={() => setOpeningLine('می‌تونی برای امروز یک برنامه‌ی خوب بهم پیشنهاد بدی؟')}><span className="suggestion-emoji">☀️</span><span>برای امروز برنامه‌ریزی کنیم</span><ArrowUpLeft size={15}/></button>
                  <button className="suggestion" onClick={() => setOpeningLine('یک موضوع جالب بهم یاد بده.')}><span className="suggestion-emoji">💡</span><span>یه چیز تازه یادم بده</span><ArrowUpLeft size={15}/></button>
                  <button className="suggestion" onClick={() => setOpeningLine('می‌خوام کمی گپ بزنیم.')}><span className="suggestion-emoji">💬</span><span>فقط یکم گپ بزنیم</span><ArrowUpLeft size={15}/></button>
                </div>
              </>
            )}
            <div className="divider"/>
            <label className="input-label" htmlFor="opening-line">یا با یک جمله شروع کن <span>اختیاری</span></label>
            <div className="message-input-wrap"><input id="opening-line" value={openingLine} onChange={(e) => setOpeningLine(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && !isLive && startConversation()} placeholder="مثلاً: امروز حالم خوب نیست..." disabled={isLive || phase === 'connecting'}/><Mic size={17} className="input-mic"/></div>
            {error && <div className="error-message" role="alert"><CircleHelp size={15}/><span>{error}</span></div>}
            {isLive ? (
              <button className="start-button end-button" onClick={endConversation}><PhoneOff size={18}/> پایان گفتگو</button>
            ) : (
              <button className="start-button" onClick={startConversation} disabled={phase === 'connecting'}>
                {phase === 'connecting' ? <><span className="spinner"/> در حال آماده‌سازی...</> : <><Phone size={17} fill="currentColor"/> شروع گفتگوی صوتی و تصویری <ArrowUpLeft size={17}/></>}
              </button>
            )}
            {!health?.configured && <div className="setup-hint"><span className="hint-icon"><Settings2 size={15}/></span><span>برای فعال‌سازی گفتگو، کلیدهای LiveKit، Tavus و OpenRouter را در فایل <code>.env</code> تنظیم کن.</span></div>}
            <div className="privacy-note"><ShieldCheck size={14}/><span>با شروع تماس، مرورگر برای دسترسی به میکروفون اجازه می‌خواهد.</span></div>
          </aside>
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
