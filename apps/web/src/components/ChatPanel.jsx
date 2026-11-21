import React from 'react';
import { AudioLines, Send } from 'lucide-react';

function MessageSquareIcon() { return <AudioLines size={17} />; }

export default function ChatPanel({ chatMessages, draftTranscript, draft, setDraft, connected, sendText, chatRef }) {
  return (
    <section className="panel chat-panel">
      <div className="panel-heading"><div><MessageSquareIcon /><div><h2>چت</h2><small>ارسال متن مستقیم به Agent</small></div></div><span className="mode-tag">صوت + متن</span></div>
      <div className="chat-stream" ref={chatRef} aria-live="polite">
        {chatMessages.length === 0 && !draftTranscript && <div className="empty-chat"><MessageSquareIcon /><strong>پیام‌ها اینجا نمایش داده می‌شوند</strong><span>برای چت متنی ابتدا نشست را شروع کنید؛ در صورت خطای میکروفون، همین ورودی فعال می‌ماند.</span></div>}
        {chatMessages.map((item) => (
          <article className={`chat-message ${item.role}`} key={item.id}>
            <div className="message-meta"><strong>{item.role === 'assistant' ? 'Agent' : 'شما'}</strong><time>{item.time}</time>{item.source && <span>{item.source === 'text' ? 'متن' : item.source === 'voice' ? 'صدا' : ''}</span>}</div>
            <p>{item.text}</p>
          </article>
        ))}
        {draftTranscript && <article className="chat-message user draft-message"><div className="message-meta"><strong>در حال تشخیص گفتار</strong></div><p>{draftTranscript}</p></article>}
      </div>
      <form className="chat-composer" onSubmit={sendText}>
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(e); } }} placeholder={connected ? 'پیامت را بنویس… (Enter برای ارسال)' : 'برای فعال‌شدن چت، نشست آزمایشی را شروع کن'} disabled={!connected} rows={2} />
        <button className="send-button" type="submit" disabled={!connected || !draft.trim()} aria-label="ارسال پیام"><Send size={17} /></button>
      </form>
      <div className="chat-footnote">پیام‌ها در اتاق LiveKit همین نشست برای Agent ارسال می‌شوند.</div>
    </section>
  );
}
