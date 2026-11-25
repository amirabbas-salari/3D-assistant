import React, { useEffect, useRef, useState } from "react";
import { useStreamCore } from "./hooks/useStreamCore.js";

const WHIP_URL = import.meta.env.VITE_WHIP_URL || "http://localhost:8080/whip";

export default function App() {
  const { status, transcript, remoteStream, isMuted, logs, connect, disconnect, toggleMute, clearLogs, copyLogs } =
    useStreamCore({
      whipUrl: WHIP_URL,
    });

  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState("all");
  const audioRef = useRef(null);
  const logRef = useRef(null);

  useEffect(() => {
    if (audioRef.current && remoteStream) {
      const el = audioRef.current;
      el.srcObject = remoteStream;
      el.play().catch(() => {});
    }
  }, [remoteStream]);

  useEffect(() => {
    if (autoScroll && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs, autoScroll]);

  const isActive = status === "connected";
  const canConnect = status === "idle" || status === "disconnected" || status === "error";

  const filtered = filter === "all" ? logs : logs.filter((l) => l.level === filter);
  const handleCopy = async () => {
    const text = await copyLogs();
    // fallback if clipboard blocked: show in prompt
    if (!navigator.clipboard) {
      prompt("کپی دستی (Ctrl+C):", text.slice(0, 8000));
    }
  };
  const handleDownload = () => {
    const text = logs.map((l) => `[${l.time}] ${l.level.toUpperCase()} ${l.msg}${l.data ? "\n" + l.data : ""}`).join("\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `streamcore-logs-${new Date().toISOString().slice(0, 19)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app" dir="rtl">
      <div className="header">
        <h1>سام — مشاور صوتی (StreamCore)</h1>
        <span className="badge">
          <span
            className="dot"
            style={{
              background:
                status === "connected"
                  ? "#22c55e"
                  : status === "connecting" || status === "reconnecting"
                    ? "#eab308"
                    : "#ef4444",
            }}
          />
          {status}
        </span>
      </div>

      <div className="card">
        <div className="visualizer">
          <span style={{ fontSize: 12, color: "#a1a1aa" }}>
            {status === "connected"
              ? "در حال شنیدن... وسط حرفش بپر تا barge-in رو تست کنی"
              : "برای شروع وصل شو"}
          </span>
        </div>

        {canConnect && (
          <div className="controls">
            <button className="btn btn-primary" onClick={connect}>
              اتصال و شروع صحبت
            </button>
          </div>
        )}
        {isActive && (
          <div className="controls">
            <button className={`btn ${isMuted ? "btn-danger" : "btn-ghost"}`} onClick={toggleMute}>
              {isMuted ? "Unmute" : "Mute"}
            </button>
            <button className="btn btn-danger" onClick={disconnect}>
              قطع
            </button>
          </div>
        )}

        <div className="transcript">
          {transcript.length === 0 && (
            <div style={{ color: "#71717a", fontSize: 13, textAlign: "center" }}>
              گفتگو اینجا نمایش داده می‌شود — فارسی صحبت کن
            </div>
          )}
          {transcript.map((e, i) => (
            <div
              key={i}
              className={`bubble ${e.role === "user" ? "bubble-user" : "bubble-agent"} ${e.partial ? "bubble-partial" : ""}`}
            >
              <div style={{ fontSize: 10, opacity: 0.6, marginBottom: 4 }}>
                {e.role === "user" ? "شما" : "سام"}
                {e.partial ? " (interim)" : ""}
              </div>
              {e.text}
            </div>
          ))}
        </div>
      </div>

      <audio ref={audioRef} autoPlay playsInline />

      {/* لاگ زنده و قابل کپی */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="log-header">
          <strong>لاگ زنده</strong>
          <span style={{ fontSize: 12, color: "#a1a1aa" }}>
            {logs.length} رویداد · WHIP: {WHIP_URL}
          </span>
          <div className="log-actions">
            <select value={filter} onChange={(e) => setFilter(e.target.value)} className="log-select">
              <option value="all">همه</option>
              <option value="info">info</option>
              <option value="error">error</option>
              <option value="debug">debug</option>
              <option value="warn">warn</option>
            </select>
            <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}>
              <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} /> auto-scroll
            </label>
            <button className="btn btn-ghost btn-sm" onClick={handleCopy}>
              کپی همه
            </button>
            <button className="btn btn-ghost btn-sm" onClick={handleDownload}>
              دانلود .txt
            </button>
            <button className="btn btn-ghost btn-sm" onClick={clearLogs}>
              پاک کردن
            </button>
          </div>
        </div>
        <div ref={logRef} className="log-body" dir="ltr">
          {filtered.length === 0 ? (
            <div style={{ color: "#71717a", fontSize: 12 }}>هنوز لاگی نیست — Connect بزن</div>
          ) : (
            filtered.map((l) => (
              <div key={l.id} className={`log-line log-${l.level}`}>
                <span className="log-time">[{l.time}]</span> <span className="log-level">{l.level}</span> {l.msg}
                {l.data && <pre className="log-data">{l.data}</pre>}
              </div>
            ))
          )}
        </div>
        <div style={{ padding: "8px 12px", fontSize: 11, color: "#71717a", borderTop: "1px solid #27272a" }}>
          برای کپی سریع: دکمه «کپی همه» یا کل متن را Select All (Ctrl+A) کن. لاگ‌ها هم در Console مرورگر هم می‌افتند.
        </div>
      </div>

      <div className="footer">
        StreamCore WHIP → {WHIP_URL} · بدون LiveKit · فقط صدا (voice_only) · پرسونا سام + RAG از طریق HTTP agent
        <br />
        latency per-turn در کنسول StreamCore نمایش داده می‌شود — مثل قبل 1.4-1.6s E2E هدف
      </div>
    </div>
  );
}
