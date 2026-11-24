import React, { useEffect, useRef } from "react";
import { useStreamCore } from "./hooks/useStreamCore.js";

const WHIP_URL = import.meta.env.VITE_WHIP_URL || "http://localhost:8080/whip";

export default function App() {
  const { status, transcript, remoteStream, isMuted, connect, disconnect, toggleMute } = useStreamCore({
    whipUrl: WHIP_URL,
  });

  const audioRef = useRef(null);
  useEffect(() => {
    if (audioRef.current && remoteStream) {
      const el = audioRef.current;
      el.srcObject = remoteStream;
      el.play().catch(() => {});
    }
  }, [remoteStream]);

  const isActive = status === "connected";
  const canConnect = status === "idle" || status === "disconnected" || status === "error";

  return (
    <div className="app" dir="rtl">
      <div className="header">
        <h1>سام — مشاور صوتی (StreamCore)</h1>
        <span className="badge">
          <span className="dot" style={{ background: status === "connected" ? "#22c55e" : status === "connecting" || status === "reconnecting" ? "#eab308" : "#52525b" }} />
          {status}
        </span>
      </div>

      <div className="card">
        <div className="visualizer">
          <span style={{ fontSize: 12, color: "#a1a1aa" }}>
            {status === "connected" ? "در حال شنیدن... وسط حرفش بپر تا barge-in رو تست کنی" : "برای شروع وصل شو"}
          </span>
        </div>

        {canConnect && (
          <div className="controls">
            <button className="btn btn-primary" onClick={connect}>اتصال و شروع صحبت</button>
          </div>
        )}
        {isActive && (
          <div className="controls">
            <button className={`btn ${isMuted ? "btn-danger" : "btn-ghost"}`} onClick={toggleMute}>
              {isMuted ? "Unmute" : "Mute"}
            </button>
            <button className="btn btn-danger" onClick={disconnect}>قطع</button>
          </div>
        )}

        <div className="transcript">
          {transcript.length === 0 && <div style={{ color: "#71717a", fontSize: 13, textAlign: "center" }}>گفتگو اینجا نمایش داده می‌شود — فارسی صحبت کن</div>}
          {transcript.map((e, i) => (
            <div key={i} className={`bubble ${e.role === "user" ? "bubble-user" : "bubble-agent"} ${e.partial ? "bubble-partial" : ""}`}>
              <div style={{ fontSize: 10, opacity: 0.6, marginBottom: 4 }}>{e.role === "user" ? "شما" : "سام"}{e.partial ? " (interim)" : ""}</div>
              {e.text}
            </div>
          ))}
        </div>
      </div>

      <audio ref={audioRef} autoPlay playsInline />

      <div className="footer">
        StreamCore WHIP → {WHIP_URL} · بدون LiveKit · فقط صدا (voice_only) · پرسونا سام + RAG از طریق HTTP agent<br />
        latency per-turn در کنسول StreamCore نمایش داده می‌شود — مثل قبل 1.4-1.6s E2E هدف
      </div>
    </div>
  );
}
