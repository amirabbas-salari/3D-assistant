import React from 'react';
import { AudioLines, Video, Volume2, RefreshCw } from 'lucide-react';

export default function VideoPanel({ avatarEnabled, avatarProvider, avatarReady, connected, avatarVideoRef, avatarContainerRef, assistantAudioTracks, audioNeedsGesture, enableAudioPlayback, lipSyncOffset, setLipSyncOffset }) {
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
  return (
    <section className="panel video-panel">
      <div className="panel-heading"><div><Video size={17} /><div><h2>تصویر آواتار</h2><small>{avatarReady ? (avatarProvider === 'did' ? 'ترک ویدیوی D-ID دریافت شد' : 'داده‌ی حرکت آواتار دریافت شد') : connected ? (avatarProvider === 'did' ? 'در انتظار ویدیوی D-ID' : 'در انتظار داده‌ی حرکت Spatius') : 'پس از اتصال نمایش داده می‌شود'}</small></div></div><span className={`video-state ${avatarReady ? 'ready' : ''}`}>{avatarReady ? 'آماده' : 'انتظار'}</span></div>
      <div className="video-stage">
        <video ref={avatarVideoRef} className={`avatar-video ${avatarReady && avatarProvider === 'did' ? 'video-visible' : ''}`} autoPlay playsInline />
        <div ref={avatarContainerRef} className={`spatius-avatar ${avatarReady && avatarProvider === 'spatius' ? 'avatar-visible' : ''}`} />
        {!avatarReady && <div className="video-placeholder"><Video size={22} /><span>{connected ? (avatarProvider === 'did' ? 'در انتظار آواتار D-ID…' : 'در انتظار آواتار Spatius…') : 'نشستی فعال نیست'}</span></div>}
        {audioNeedsGesture && <button className="audio-prompt" onClick={enableAudioPlayback}>برای شنیدن پاسخ، کلیک کنید</button>}
      </div>
      <div className="video-meta"><span><span className={`tiny-dot ${avatarReady ? 'green' : ''}`} />{avatarReady ? 'آواتار وصل است' : 'آواتار وصل نیست'}</span><span><Volume2 size={14} /> {assistantAudioTracks.length} ترک صوتی</span></div>
      {avatarProvider === 'spatius' && (
        <div className="lipsync-control">
          <div className="lipsync-head"><span>هماهنگی لب و صدا</span><strong>{lipSyncOffset} ms</strong></div>
          <input type="range" min="0" max="600" step="10" value={lipSyncOffset} onChange={(e) => setLipSyncOffset(Number(e.target.value))} aria-label="تأخیر شروع حرکت لب" />
          <small>اگر لب‌ها <strong>زودتر</strong> از صدا حرکت می‌کنند عدد را زیاد کنید؛ اگر دیرتر، کم کنید.</small>
        </div>
      )}
    </section>
  );
}
