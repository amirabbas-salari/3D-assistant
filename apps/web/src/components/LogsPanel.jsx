import React from 'react';
import { Activity, Copy, Trash2, CircleAlert } from 'lucide-react';

export default function LogsPanel({ logs, setLogs, copyLogs, logRef }) {
  return (
    <section className="panel logs-panel">
      <div className="panel-heading log-heading"><div><div className="log-icon"><Activity size={17} /></div><div><h2>گزارش نشست</h2><small>رخدادهای اخیر مرورگر، API و Agent · {logs.length} مورد</small></div></div><div className="log-actions"><button className="secondary-button compact" onClick={copyLogs}><Copy size={14} /> کپی گزارش</button><button className="secondary-button compact" onClick={() => setLogs([])}><Trash2 size={14} /> پاک‌کردن</button></div></div>
      <div className="log-list" ref={logRef} role="log" aria-live="polite">
        {logs.length === 0 && <div className="empty-logs">هنوز رویدادی ثبت نشده است.</div>}
        {logs.map((entry) => (
          <details className={`log-entry level-${entry.level}`} key={entry.id} open={entry.level === 'error'}>
            <summary><time>{entry.time}</time><span className="level-label">{entry.level.toUpperCase()}</span><span className="log-message">{entry.message}</span><span className="details-indicator">{entry.details ? 'جزئیات' : ''}</span></summary>
            {entry.details && <pre>{entry.details}</pre>}
          </details>
        ))}
      </div>
      <div className="log-disclaimer"><CircleAlert size={14} /> اطلاعات حساس را در گزارش‌ها کپی یا عمومی نکنید؛ متن گفتگو و جزئیات خطا ممکن است در اینجا ثبت شود.</div>
    </section>
  );
}
