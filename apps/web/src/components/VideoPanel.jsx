import React from 'react';
import { AudioLines, Video, Volume2, AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react';

export default function VideoPanel({
  avatarEnabled,
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
}) {
  if (!avatarEnabled) {
    const hints = health?.tavusHints || (health?.hint ? [health.hint] : []);
    const hintText = hints.join(' | ');
    return (
      <section className="panel voice-panel">
        <div className="panel-heading"><div><AudioLines size={17} /><div><h2>صدا و متن</h2><small>آواتار خاموش است — AVATAR_ENABLED=false</small></div></div><span className="video-state">خاموش</span></div>
        <div className="voice-body">
          <div style={{ background: '#fef3c7', border: '1px solid #f59e0b', borderRadius: 8, padding: '10px 12px', fontSize: 11, lineHeight: 1.8, color: '#92400e' }}>
            <strong style={{ display: 'flex', alignItems: 'center', gap: 6 }}><AlertTriangle size={14} /> آواتار Tavus خاموش است</strong>
            <div style={{ marginTop: 6 }}>برای دیدن تصویر، در <code>.env</code> بگذارید:</div>
            <code style={{ display: 'block', marginTop: 6, background: '#fffbeb', border: '1px solid #fbbf24', borderRadius: 6, padding: '6px 8px', direction: 'ltr', textAlign: 'left', fontSize: 10 }}>AVATAR_ENABLED=true<br/>TAVUS_API_KEY=tv_...<br/>TAVUS_REPLICA_ID=r_...<br/>TAVUS_PERSONA_ID=p_...</code>
            <div style={{ marginTop: 6, opacity: 0.9 }}>سپس API را ری‌استارت کنید: <code>npm run dev:api</code></div>
            {hintText && <div style={{ marginTop: 8, background: '#fff', border: '1px solid #fde68a', borderRadius: 6, padding: '6px 8px', color: '#78350f' }}>💡 {hintText}</div>}
          </div>
          <div className="voice-row"><span>ترک صوتی Agent</span><strong>{assistantAudioTracks.length}</strong></div>
          <div className="voice-row"><span>پخش صدا</span><strong>{audioNeedsGesture ? 'نیازمند کلیک' : connected ? 'فعال' : 'غیرفعال'}</strong></div>
          {audioNeedsGesture && <button className="secondary-button" onClick={enableAudioPlayback}>فعال‌سازی پخش صدا</button>}
        </div>
      </section>
    );
  }

  const hasError = Boolean(tavusError);
  const isLoading = connected && !tavusUrl && !hasError;

  return (
    <section className="panel video-panel">
      <div className="panel-heading"><div><Video size={17} /><div><h2>تصویر آواتار</h2><small>{avatarReady ? 'آواتار Tavus متصل است' : hasError ? 'خطا در اتصال Tavus' : connected ? (tavusStatus || 'در انتظار Tavus…') : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : hasError ? 'error' : ''}`} style={hasError ? { color: '#b33838', borderColor: '#e6c1c1', background: '#fef2f2' } : undefined}>{avatarReady ? 'آماده' : hasError ? 'خطا' : 'انتظار'}</span></div>
      <div className="video-stage">
        {tavusUrl ? (
          <iframe
            src={tavusUrl}
            title="Tavus Avatar"
            allow="camera; microphone; autoplay; display-capture; fullscreen"
            allowFullScreen
            style={{ width: '100%', height: '100%', border: 0, borderRadius: 12, display: 'block' }}
            onLoad={() => console.log('[tavus] iframe loaded', tavusUrl)}
            onError={(e) => console.error('[tavus] iframe error', e)}
          />
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
      {hasError && health && !health.tavusConfigured && (
        <div style={{ padding: '8px 12px', fontSize: 11, color: '#991b1b', background: '#fef2f2', borderTop: '1px solid #fecaca', lineHeight: 1.7 }}>
          ⚠️ <code>TAVUS_API_KEY</code> یا <code>TAVUS_REPLICA_ID/TAVUS_PERSONA_ID</code> تنظیم نشده — <code>/api/health</code> مقدار <code>tavusConfigured: false</code> برمی‌گرداند
        </div>
      )}
      <div style={{ padding: '8px 12px', fontSize: 10, color: '#71717a', lineHeight: 1.7, borderTop: '1px solid #f1f5f9' }}>
        Tavus CVI — Daily iframe. اگر تصویر سیاه ماند: ۱) اجازه‌ی دوربین/میکروفون مرورگر را بدهید ۲) <code>TAVUS_API_KEY</code> را از platform.tavus.io چک کنید ۳) لاگ شبکه (F12) خطای 503/401 را نشان می‌دهد — آن را در گزارش‌ها ببینید.
      </div>
    </section>
  );
}
