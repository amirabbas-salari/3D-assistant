import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AudioLines, ArrowUpLeft, Check, CircleHelp, Mic, MicOff, MoreHorizontal,
  Phone, PhoneOff, Settings2, ShieldCheck, Sparkles, Video, Volume2, Waves,
} from 'lucide-react';
import './styles.css';

function App() {
  const [phase, setPhase] = useState('idle');
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  const [openingLine, setOpeningLine] = useState('');
  const [muted, setMuted] = useState(false);
  const [assistantVideo, setAssistantVideo] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const roomRef = useRef(null);
  const videoRef = useRef(null);

  useEffect(() => {
    fetch('/api/health').then((r) => r.json()).then(setHealth).catch(() => setHealth({ configured: false }));
  }, []);

  useEffect(() => {
    if (!assistantVideo || !videoRef.current) return undefined;
    assistantVideo.attach(videoRef.current);
    return () => assistantVideo.detach(videoRef.current);
  }, [assistantVideo]);

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
      room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
        if (track.kind === Track.Kind.Video && participant.identity !== room.localParticipant.identity) setAssistantVideo(track);
      });
      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === Track.Kind.Video) setAssistantVideo(null);
      });
      await room.connect(data.serverUrl, data.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      await room.startAudio().catch(() => {});
      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.videoTrackPublications.values()) {
          if (publication.track) setAssistantVideo(publication.track);
        }
      }
      setPhase('live');
    } catch (e) {
      roomRef.current?.disconnect();
      roomRef.current = null;
      setError(e.message || 'ارتباط برقرار نشد. دوباره تلاش کنید.');
      setPhase('idle');
    }
  }

  function endConversation() {
    roomRef.current?.disconnect();
    roomRef.current = null;
    setAssistantVideo(null);
    setPhase('idle');
    setMuted(false);
    setOpeningLine('');
  }

  async function toggleMute() {
    const nextMuted = !muted;
    await roomRef.current?.localParticipant.setMicrophoneEnabled(!nextMuted);
    setMuted(nextMuted);
  }

  const isLive = phase === 'live';

  return (
    <div className="app-shell" dir="rtl">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="همراه">
          <span className="brand-mark"><AudioLines size={21} strokeWidth={2.2} /></span>
          <span className="brand-name">همراه<span className="brand-dot">.</span></span>
        </a>
        <nav className="top-nav"><a className="nav-active" href="#talk">گفتگوی من</a><a href="#about">درباره همراه</a></nav>
        <div className="top-actions">
          <span className="privacy-pill"><ShieldCheck size={15} /> گفتگوی خصوصی</span>
          <button className="icon-button settings-button" aria-label="تنظیمات" onClick={() => setShowSettings(!showSettings)}><Settings2 size={19}/></button>
          {showSettings && <div className="settings-pop"><strong>تنظیمات اتصال</strong><p>آواتار با Tavus، STT/TTS فارسی با LiveKit و LLM با OpenRouter اجرا می‌شود. کلیدها فقط روی سرور می‌مانند.</p><div className="settings-state"><span className={health?.configured ? 'status-dot green' : 'status-dot'} />{health?.configured ? 'پیکربندی کامل است' : 'تنظیمات سرویس‌ها ناقص است'}</div></div>}
        </div>
      </header>

      <main className="workspace" id="talk">
        <section className="intro">
          <div className="eyebrow"><span className="eyebrow-line"/> دستیار هوشمند فارسی <Sparkles size={14}/></div>
          <h1>یک گفتگوی واقعی،<br/><span>با همراه.</span></h1>
          <p className="intro-copy">حرف بزن، سؤال بپرس، یا فقط فکرهایت را با صدای بلند بگو.<br className="desktop-break"/> همراه اینجاست تا گوش کند و پاسخ بدهد.</p>
          <div className="intro-trust"><div className="avatar-stack"><span>م</span><span>ن</span><span>ر</span></div><span>همیشه آماده‌ی شنیدن</span><span className="trust-divider"/><span className="online-indicator"/> آنلاین و در دسترس</div>
        </section>

        <section className={`call-layout ${isLive ? 'call-layout-live' : ''}`} aria-label="محیط گفتگوی صوتی و تصویری">
          <div className={`video-panel ${isLive ? 'video-panel-live' : ''}`}>
            <div className="panel-topline"><span className="panel-label"><span className={`status-dot ${isLive ? 'green pulse' : ''}`}/>{isLive ? 'در حال گفتگو' : 'فضای گفتگوی تصویری'}</span><button className="icon-button dots-button" aria-label="گزینه‌های بیشتر"><MoreHorizontal size={21}/></button></div>
            {isLive ? (
              <div className="video-frame-wrap">
                <video ref={videoRef} className={`assistant-video ${assistantVideo ? 'visible' : ''}`} autoPlay playsInline />
                {!assistantVideo && <div className="avatar-waiting"><div className="waiting-orb"><AudioLines size={28}/></div><strong>همراه در حال آماده‌شدن است</strong><span>چند لحظه صبر کن...</span></div>}
                <div className="live-badge"><span className="live-dot"/> زنده</div>
                <div className="call-controls">
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
                <div className="stage-caption"><span className="caption-greeting">سلام، من همراه هستم</span><span className="caption-sub">برای شروع، دکمه‌ی گفتگو را بزن</span></div>
              </div>
            )}
            <div className="video-footer">
              <div className="voice-status"><span className="sound-icon"><Volume2 size={16}/></span><div><strong>{isLive ? 'صدای گفتگو فعال است' : 'صدای طبیعی و روان'}</strong><small>{isLive ? 'از کنترل‌های داخل تصویر استفاده کن' : 'به زبان فارسی با هم صحبت می‌کنیم'}</small></div></div>
              <div className="video-quality"><span className="quality-dot"/> HD</div>
            </div>
          </div>

          <aside className="side-panel">
            <div className="side-heading"><div><span className="side-kicker">جلسه‌ی جدید</span><h2>با چی کمکت کنم؟</h2></div><span className="sparkle-bubble"><Sparkles size={17}/></span></div>
            <p className="side-description">از یک سؤال ساده تا یک گفتگوی طولانی؛ از همین‌جا شروع کن.</p>
            <div className="suggestion-label">شاید این‌ها شروع خوبی باشند</div>
            <div className="suggestions">
              <button className="suggestion" onClick={() => setOpeningLine('می‌تونی برای امروز یک برنامه‌ی خوب بهم پیشنهاد بدی؟')}><span className="suggestion-emoji">☀️</span><span>برای امروز برنامه‌ریزی کنیم</span><ArrowUpLeft size={15}/></button>
              <button className="suggestion" onClick={() => setOpeningLine('یک موضوع جالب بهم یاد بده.')}><span className="suggestion-emoji">💡</span><span>یه چیز تازه یادم بده</span><ArrowUpLeft size={15}/></button>
              <button className="suggestion" onClick={() => setOpeningLine('می‌خوام کمی گپ بزنیم.')}><span className="suggestion-emoji">💬</span><span>فقط یکم گپ بزنیم</span><ArrowUpLeft size={15}/></button>
            </div>
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

        <section className="feature-strip" id="about">
          <div className="feature"><span className="feature-icon purple"><Mic size={18}/></span><div><strong>گفتگوی صوتی</strong><small>طبیعی، راحت و فارسی</small></div></div>
          <span className="feature-separator"/>
          <div className="feature"><span className="feature-icon teal"><Video size={18}/></span><div><strong>همراه تصویری</strong><small>حضور زنده با Tavus</small></div></div>
          <span className="feature-separator"/>
          <div className="feature"><span className="feature-icon amber"><ShieldCheck size={18}/></span><div><strong>حریم خصوصی</strong><small>کلیدها امن روی سرور</small></div></div>
          <a className="help-link" href="https://docs.tavus.io/" target="_blank" rel="noreferrer"><CircleHelp size={16}/> راهنمای راه‌اندازی <ArrowUpLeft size={14}/></a>
        </section>
      </main>
      <footer className="footer"><span>ساخته‌شده برای گفتگوهای بهتر <span className="footer-heart">♥</span></span><span>همراه <span className="footer-sep">·</span> نسخه‌ی آزمایشی</span></footer>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
