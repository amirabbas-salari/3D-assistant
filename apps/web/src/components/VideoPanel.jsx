import React from 'react';
import { AudioLines, Video, Volume2, AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react';

// ── Spatius avatar view (client-side rendering) ──
function SpatiusView({ enabled, provider, connected, health, tavusError }) {
  const containerRef = React.useRef(null);
  const [status, setStatus] = React.useState('');
  const [error, setError] = React.useState('');
  const playerRef = React.useRef(null);

  React.useEffect(() => {
    if (provider !== 'spatius' || !enabled || !connected || !containerRef.current) return;
    let cancelled = false;
    let dispose = null;

    async function initSpatius() {
      try {
        setError('');
        setStatus('در حال بارگذاری Spatius AvatarKit…');
        // dynamic import — optional peer deps
        const { AvatarSDK, AvatarManager, AvatarView } = await import('@spatius/avatarkit').catch((e) => {
          throw new Error('پکیج @spatius/avatarkit نصب نیست — npm install @spatius/avatarkit @spatius/avatarkit-rtc را اجرا کنید. ' + e.message);
        });
        const { AvatarPlayer, LiveKitProvider } = await import('@spatius/avatarkit-rtc').catch((e) => {
          throw new Error('پکیج @spatius/avatarkit-rtc نصب نیست. ' + e.message);
        });

        const appId = health?.spatiusAppId;
        const avatarId = health?.spatiusAvatarId;
        if (!appId || !avatarId) {
          throw new Error('SPATIUS_APP_ID یا SPATIUS_AVATAR_ID در /api/health خالی است — .env را پر کنید');
        }

        setStatus('اتصال به Spatius… (AvatarKit)');
        // DrivingServiceMode.rtc is default for LiveKit integration
        await AvatarSDK.initialize(appId, { drivingServiceMode: 'rtc' });
        const avatar = await AvatarManager.shared.load(avatarId);
        const avatarView = new AvatarView(avatar, containerRef.current);
        const provider = new LiveKitProvider();
        const player = new AvatarPlayer(provider, avatarView);

        // LiveKit session info comes from health? Actually need token+url from room.
        // The LiveKitProvider expects to attach to existing room — App.jsx passes room via window
        // For now we use the adapter's attach flow if available, else connect flow
        // If the backend started Spatius avatar, the motion track will be decoded automatically
        // when player is connected to the same room.
        // Note: avatar rendering is client-side; the video track is black frames with motion data
        playerRef.current = player;
        setStatus('آواتار Spatius آماده — در انتظار motion track…');

        // keep alive until unmount
        dispose = async () => {
          try { await player.stopPublishing?.(); } catch {}
          try { await player.disconnect?.(); } catch {}
          try { avatarView.dispose?.(); } catch {}
        };
        if (cancelled) { await dispose(); }
      } catch (e) {
        console.error('[spatius] init error', e);
        setError(e.message || String(e));
        setStatus('خطا');
      }
    }
    initSpatius();
    return () => {
      cancelled = true;
      if (dispose) dispose();
      if (playerRef.current) {
        try { playerRef.current.disconnect?.(); } catch {}
      }
    };
  }, [enabled, provider, connected, health?.spatiusAppId, health?.spatiusAvatarId]);

  if (error) {
    return (
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 16, background: '#1a2332', color: '#e2e8f0', textAlign: 'center' }}>
        <AlertTriangle size={22} color="#f87171" />
        <strong style={{ fontSize: 12, color: '#fecaca' }}>آواتار Spatius لود نشد</strong>
        <span style={{ fontSize: 11, lineHeight: 1.7, maxWidth: 320, opacity: 0.9, wordBreak: 'break-word' }}>{error}</span>
        <small style={{ fontSize: 10, opacity: 0.6, direction: 'ltr' }}>npm install @spatius/avatarkit @spatius/avatarkit-rtc && vite --host</small>
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%', borderRadius: 12, overflow: 'hidden', background: '#0f172a' }} />
      {!connected && <div className="video-placeholder"><Video size={22} /><span>نشستی فعال نیست</span></div>}
      {status && connected && <div style={{ position: 'absolute', bottom: 8, left: 8, background: 'rgba(0,0,0,0.6)', color: '#fff', fontSize: 9, padding: '4px 6px', borderRadius: 4 }}>{status}</div>}
    </div>
  );
}

export default function VideoPanel({
  avatarEnabled,
  avatarProvider: providerProp,
  avatarReady,
  connected,
  assistantAudioTracks,
  audioNeedsGesture,
  enableAudioPlayback,
  tavusUrl,
  tavusStatus,
  tavusError,
  health,
  onRetryTavus,
  // LiveKit avatar mode (لب‌زدن به TTS پروژه)
  avatarVideoTrack,
  avatarVideoRef,
}) {
  const provider = providerProp || health?.avatarProvider || 'none';
  const avatarMode = health?.tavusAvatarMode || 'livekit';
  const isLivekitMode = avatarMode === 'livekit';
  const isSpatiaus = provider === 'spatius';
  const isTavus = provider === 'tavus';

  // attach LiveKit video track to < video> element (for Tavus livekit lip-sync)
  React.useEffect(() => {
    const el = avatarVideoRef?.current;
    if (!el) return;
    if (avatarVideoTrack) {
      avatarVideoTrack.attach(el);
      return () => { try { avatarVideoTrack.detach(el); } catch {} };
    } else {
      el.srcObject = null;
    }
  }, [avatarVideoTrack, avatarVideoRef]);

  if (!avatarEnabled) {
    const hints = health?.tavusHints || health?.spatiusHints || (health?.hint ? [health.hint] : []);
    const hintText = hints.join(' | ');
    return (
      <section className="panel voice-panel">
        <div className="panel-heading"><div><AudioLines size={17} /><div><h2>صدا و متن</h2><small>آواتار خاموش است — AVATAR_ENABLED=false</small></div></div><span className="video-state">خاموش</span></div>
        <div className="voice-body">
          <div style={{ background: '#fef3c7', border: '1px solid #f59e0b', borderRadius: 8, padding: '10px 12px', fontSize: 11, lineHeight: 1.8, color: '#92400e' }}>
            <strong style={{ display: 'flex', alignItems: 'center', gap: 6 }}><AlertTriangle size={14} /> آواتار خاموش است</strong>
            <div style={{ marginTop: 6 }}>برای دیدن تصویر، در <code>.env</code> بگذارید و <code>AVATAR_PROVIDER</code> را انتخاب کنید:</div>
            <code style={{ display: 'block', marginTop: 6, background: '#fffbeb', border: '1px solid #fbbf24', borderRadius: 6, padding: '6px 8px', direction: 'ltr', textAlign: 'left', fontSize: 10 }}>
              AVATAR_ENABLED=true<br/>
              # یکی را انتخاب کنید:<br/>
              AVATAR_PROVIDER=tavus<br/>TAVUS_API_KEY=tv_...<br/>TAVUS_REPLICA_ID=r_...<br/>TAVUS_PERSONA_ID=p_...<br/>
              # یا Spatius:<br/>AVATAR_PROVIDER=spatius<br/>SPATIUS_API_KEY=...<br/>SPATIUS_APP_ID=...<br/>SPATIUS_AVATAR_ID=...
            </code>
            <div style={{ marginTop: 6, opacity: 0.9 }}>سپس API و Agent را ری‌استارت کنید: <code>npm run dev</code></div>
            {hintText && <div style={{ marginTop: 8, background: '#fff', border: '1px solid #fde68a', borderRadius: 6, padding: '6px 8px', color: '#78350f' }}>💡 {hintText}</div>}
          </div>
          <div className="voice-row"><span>ترک صوتی Agent</span><strong>{assistantAudioTracks.length}</strong></div>
          <div className="voice-row"><span>پخش صدا</span><strong>{audioNeedsGesture ? 'نیازمند کلیک' : connected ? 'فعال' : 'غیرفعال'}</strong></div>
          {audioNeedsGesture && <button className="secondary-button" onClick={enableAudioPlayback}>فعال‌سازی پخش صدا</button>}
        </div>
      </section>
    );
  }

  // ── Spatius provider ──
  if (isSpatiaus) {
    const hasError = Boolean(tavusError);
    // Even with Spatius, audio comes from LiveKit; video is motion via AvatarKit
    return (
      <section className="panel video-panel">
        <div className="panel-heading"><div><Video size={17} /><div><h2>تصویر آواتار</h2><small>{avatarReady ? 'آواتار Spatius متصل است' : hasError ? 'خطا در اتصال Spatius' : connected ? (tavusStatus || 'در انتظار Spatius…') : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : hasError ? 'error' : ''}`} style={hasError ? { color: '#b33838', borderColor: '#e6c1c1', background: '#fef2f2' } : undefined}>{avatarReady ? 'آماده' : hasError ? 'خطا' : 'انتظار'}</span></div>
        <div className="video-stage" style={{ background: '#020617' }}>
          <SpatiausView enabled={avatarEnabled} provider={provider} connected={connected} health={health} tavusError={tavusError} />
          {hasError && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 16, background: '#1a2332', color: '#e2e8f0', textAlign: 'center' }}>
              <AlertTriangle size={22} color="#f87171" />
              <strong style={{ fontSize: 12, color: '#fecaca' }}>تصویر Spatius لود نشد</strong>
              <span style={{ fontSize: 11, lineHeight: 1.7, maxWidth: 280, opacity: 0.9, wordBreak: 'break-word' }}>{tavusError}</span>
            </div>
          )}
          {audioNeedsGesture && <button className="audio-prompt" onClick={enableAudioPlayback}>برای شنیدن پاسخ، کلیک کنید</button>}
        </div>
        <div className="video-meta"><span><span className={`tiny-dot ${avatarReady ? 'green' : hasError ? 'red' : ''}`} style={hasError ? { background: '#ef4444' } : undefined} />{avatarReady ? 'آواتار Spatius وصل است — رندر کلاینت' : hasError ? 'خطا — لاگ را ببینید' : 'آواتار وصل نیست'}</span><span><Volume2 size={14} /> {assistantAudioTracks.length} ترک صوتی</span></div>
        <div style={{ padding: '8px 12px', fontSize: 10, color: '#71717a', lineHeight: 1.7, borderTop: '1px solid #f1f5f9' }}>
          حالت <code>spatius</code> — رندر AvatarKit روی کلاینت (نیاز به <code>@spatius/avatarkit</code>). ترک ویدیو شامل motion data است، نه تصویر معمولی. اگر سیاه ماند، پکیج‌ها را نصب کنید: <code>npm install @spatius/avatarkit @spatius/avatarkit-rtc</code>
        </div>
      </section>
    );
  }

  const hasError = Boolean(tavusError);

  // ── LiveKit mode: آواتار از TTS پروژه لب می‌زند (video track از LiveKit) ──
  if (isTavus && isLivekitMode) {
    return (
      <section className="panel video-panel">
        <div className="panel-heading"><div><Video size={17} /><div><h2>تصویر آواتار</h2><small>{avatarReady ? 'آواتار Tavus متصل است (لب‌سینک به TTS پروژه)' : hasError ? 'خطا در اتصال Tavus' : connected ? (tavusStatus || 'در انتظار ویدیوی آواتار…') : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : hasError ? 'error' : ''}`} style={hasError ? { color: '#b33838', borderColor: '#e6c1c1', background: '#fef2f2' } : undefined}>{avatarReady ? 'آماده' : hasError ? 'خطا' : 'انتظار'}</span></div>
        <div className="video-stage">
          <video ref={avatarVideoRef} autoPlay playsInline muted={false} className={`avatar-video ${avatarReady ? 'video-visible' : ''}`} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: avatarReady ? 1 : 0 }} />
          {!avatarReady && (
            hasError ? (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 16, background: '#1a2332', color: '#e2e8f0', textAlign: 'center' }}>
                <AlertTriangle size={22} color="#f87171" />
                <strong style={{ fontSize: 12, color: '#fecaca' }}>تصویر Tavus لود نشد</strong>
                <span style={{ fontSize: 11, lineHeight: 1.7, maxWidth: 280, opacity: 0.9, wordBreak: 'break-word' }}>{tavusError}</span>
                {onRetryTavus && <button className="secondary-button" onClick={onRetryTavus} style={{ background: '#fff', color: '#1e293b' }}><RefreshCw size={12} /> تلاش مجدد</button>}
              </div>
            ) : (
              <div className="video-placeholder"><Video size={22} /><span>{connected ? 'در انتظار ویدیوی آواتار… (Agent و Tavus در حال اتصال)' : 'نشستی فعال نیست'}</span></div>
            )
          )}
          {audioNeedsGesture && <button className="audio-prompt" onClick={enableAudioPlayback}>برای شنیدن پاسخ، کلیک کنید</button>}
        </div>
        <div className="video-meta"><span><span className={`tiny-dot ${avatarReady ? 'green' : hasError ? 'red' : ''}`} style={hasError ? { background: '#ef4444' } : undefined} />{avatarReady ? 'آواتار وصل است — لب‌سینک به TTS پروژه' : hasError ? 'خطا — لاگ را ببینید' : 'آواتار وصل نیست'}</span><span><Volume2 size={14} /> {assistantAudioTracks.length} ترک صوتی</span></div>
        <div style={{ padding: '8px 12px', fontSize: 10, color: '#71717a', lineHeight: 1.7, borderTop: '1px solid #f1f5f9' }}>
          حالت <code>livekit</code> — صدای TTS پروژه (OpenRouter/Google) به Tavus stream می‌شود و آواتار لب می‌زند. اگر تصویر نیامد، لاگ Agent را ببینید. برای حالت مستقل CVI: <code>TAVUS_AVATAR_MODE=cvi</code> یا برای Spatius: <code>AVATAR_PROVIDER=spatius</code>
        </div>
      </section>
    );
  }

  // ── CVI mode: Daily iframe مستقل (Tavus) ──
  return (
    <section className="panel video-panel">
      <div className="panel-heading"><div><Video size={17} /><div><h2>تصویر آواتار</h2><small>{avatarReady ? 'آواتار Tavus متصل است' : hasError ? 'خطا در اتصال Tavus' : connected ? (tavusStatus || 'در انتظار Tavus…') : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : hasError ? 'error' : ''}`} style={hasError ? { color: '#b33838', borderColor: '#e6c1c1', background: '#fef2f2' } : undefined}>{avatarReady ? 'آماده' : hasError ? 'خطا' : 'انتظار'}</span></div>
      <div className="video-stage">
        {tavusUrl ? (
          <iframe src={tavusUrl} title="Tavus Avatar" allow="camera; microphone; autoplay; display-capture; fullscreen" allowFullScreen style={{ width: '100%', height: '100%', border: 0, borderRadius: 12, display: 'block' }} onLoad={() => console.log('[tavus] iframe loaded', tavusUrl)} onError={(e) => console.error('[tavus] iframe error', e)} />
        ) : hasError ? (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 16, background: '#1a2332', color: '#e2e8f0', textAlign: 'center' }}>
            <AlertTriangle size={22} color="#f87171" />
            <strong style={{ fontSize: 12, color: '#fecaca' }}>تصویر Tavus لود نشد</strong>
            <span style={{ fontSize: 11, lineHeight: 1.7, maxWidth: 280, opacity: 0.9, wordBreak: 'break-word' }}>{tavusError}</span>
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              {onRetryTavus && <button className="secondary-button" onClick={onRetryTavus} style={{ background: '#fff', color: '#1e293b' }}><RefreshCw size={12} /> تلاش مجدد</button>}
              <a href="https://platform.tavus.io" target="_blank" rel="noreferrer" className="secondary-button" style={{ textDecoration: 'none', background: '#1e293b', color: '#fff', borderColor: '#334155' }}><ExternalLink size={12} /> داشبورد Tavus</a>
            </div>
            <small style={{ fontSize: 9, opacity: 0.6, marginTop: 4 }}>لاگ کامل را در پنل «گزارش‌ها» ببینید</small>
          </div>
        ) : (
          <div className="video-placeholder"><Video size={22} /><span>{connected ? 'در حال ساخت گفتگوی Tavus…' : 'نشستی فعال نیست'}</span></div>
        )}
        {audioNeedsGesture && <button className="audio-prompt" onClick={enableAudioPlayback}>برای شنیدن پاسخ، کلیک کنید</button>}
      </div>
      <div className="video-meta"><span><span className={`tiny-dot ${avatarReady ? 'green' : hasError ? 'red' : ''}`} style={hasError ? { background: '#ef4444' } : undefined} />{avatarReady ? 'آواتار وصل است' : hasError ? 'خطا — لاگ را ببینید' : 'آواتار وصل نیست'}</span><span><Volume2 size={14} /> {assistantAudioTracks.length} ترک صوتی</span></div>
      <div style={{ padding: '8px 12px', fontSize: 10, color: '#71717a', lineHeight: 1.7, borderTop: '1px solid #f1f5f9' }}>
        حالت CVI — Daily iframe مستقل. برای لب‌زدن به TTS پروژه: <code>TAVUS_AVATAR_MODE=livekit</code> یا برای Spatius: <code>AVATAR_PROVIDER=spatius</code>
      </div>
    </section>
  );
}
