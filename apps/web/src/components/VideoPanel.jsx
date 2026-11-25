import React from 'react';
import { AudioLines, Video, Volume2 } from 'lucide-react';

export default function VideoPanel({
  avatarEnabled,
  avatarProvider,
  avatarReady,
  connected,
  avatarVideoRef,
  avatarContainerRef,
  assistantAudioTracks,
  audioNeedsGesture,
  enableAudioPlayback,
  tavusUrl,
  tavusStatus,
}) {
  if (!avatarEnabled) {
    return (
      <section className="panel voice-panel">
        <div className="panel-heading"><div><AudioLines size={17} /><div><h2>صدا و متن</h2><small>آواتار خاموش است؛ STT، LLM و TTS کامل اجرا می‌شوند</small></div></div><span className="video-state ready">آماده</span></div>
        <div className="voice-body">
          <div className="voice-row"><span>ترک صوتی Agent</span><strong>{assistantAudioTracks.length}</strong></div>
          <div className="voice-row"><span>پخش صدا</span><strong>{audioNeedsGesture ? 'نیازمند کلیک' : connected ? 'فعال' : 'غیرفعال'}</strong></div>
          {audioNeedsGesture && <button className="secondary-button" onClick={enableAudioPlayback}>فعال‌سازی پخش صدا</button>}
        </div>
      </section>
    );
  }

  const isTavus = avatarProvider === 'tavus';

  return (
    <section className="panel video-panel">
      <div className="panel-heading"><div><Video size={17} /><div><h2>تصویر آواتار</h2><small>{avatarReady ? (isTavus ? 'آواتار Tavus متصل است' : 'ویدیوی آواتار دریافت شد') : connected ? (isTavus ? (tavusStatus || 'در انتظار Tavus…') : 'در انتظار ویدیوی آواتار') : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : ''}`}>{avatarReady ? 'آماده' : 'انتظار'}</span></div>
      <div className="video-stage">
        {/* Tavus CVI — Daily iframe */}
        {isTavus ? (
          tavusUrl ? (
            <iframe
              src={tavusUrl}
              title="Tavus Avatar"
              allow="camera; microphone; autoplay; display-capture"
              style={{ width: '100%', height: '100%', border: 0, borderRadius: 12 }}
            />
          ) : (
            <div className="video-placeholder"><Video size={22} /><span>{connected ? 'در حال ساخت گفتگوی Tavus…' : 'نشستی فعال نیست'}</span></div>
          )
        ) : (
          <>
            <video ref={avatarVideoRef} className={`avatar-video ${avatarReady ? 'video-visible' : ''}`} autoPlay playsInline />
            <div ref={avatarContainerRef} className="spatius-avatar" />
            {!avatarReady && <div className="video-placeholder"><Video size={22} /><span>{connected ? 'در انتظار آواتار…' : 'نشستی فعال نیست'}</span></div>}
          </>
        )}
        {audioNeedsGesture && <button className="audio-prompt" onClick={enableAudioPlayback}>برای شنیدن پاسخ، کلیک کنید</button>}
      </div>
      <div className="video-meta"><span><span className={`tiny-dot ${avatarReady ? 'green' : ''}`} />{avatarReady ? 'آواتار وصل است' : 'آواتار وصل نیست'}</span><span><Volume2 size={14} /> {assistantAudioTracks.length} ترک صوتی</span></div>
      {isTavus && <div style={{ padding: '8px 12px', fontSize: 11, color: '#71717a' }}>Tavus CVI: replica + persona از .env می‌آید. برای تغییر replica/persona، <code>TAVUS_REPLICA_ID</code> / <code>TAVUS_PERSONA_ID</code> را عوض کنید.</div>}
    </section>
  );
}
