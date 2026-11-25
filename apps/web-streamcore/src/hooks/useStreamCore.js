"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { StreamCoreAIClient } from "@streamcore/js-sdk";

function fmtTime(d = new Date()) {
  return d.toLocaleTimeString("fa-IR", { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

export function useStreamCore(config) {
  const [status, setStatus] = useState("idle");
  const [transcript, setTranscript] = useState([]);
  const [localStream, setLocalStream] = useState(null);
  const [remoteStream, setRemoteStream] = useState(null);
  const [isMuted, setIsMuted] = useState(false);
  const [logs, setLogs] = useState([]);
  const clientRef = useRef(null);
  const t0Ref = useRef(null);

  const addLog = useCallback((level, msg, data) => {
    const entry = {
      id: Date.now() + Math.random(),
      time: fmtTime(),
      ts: Date.now(),
      level,
      msg,
      data: data ? (typeof data === "string" ? data : (() => { try { return JSON.stringify(data, null, 2); } catch { return String(data); } })()) : undefined,
    };
    setLogs((prev) => [...prev.slice(-500), entry]);
    // also console
    const fn = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
    fn(`[streamcore ${entry.time} ${level}] ${msg}`, data ?? "");
  }, []);

  const getClient = useCallback(() => {
    if (!clientRef.current) {
      addLog("info", `init client`, { whipUrl: config.whipUrl, hasApiKey: !!config.apiKey });
      clientRef.current = new StreamCoreAIClient(config, {
        onTranscript: (entry, all) => {
          setTranscript([...all]);
          const isPartial = entry?.partial || entry?.isPartial;
          addLog(isPartial ? "debug" : "info", isPartial ? `STT interim: ${entry?.text?.slice(0, 120)}` : `transcript ${entry?.role || "?"}: ${entry?.text?.slice(0, 120)}`, entry);
        },
        onStatusChange: (s) => {
          const elapsed = t0Ref.current ? `${Date.now() - t0Ref.current}ms` : "-";
          addLog(s === "error" ? "error" : "info", `status → ${s} (${elapsed})`, { status: s });
          setStatus(s);
          setLocalStream(clientRef.current?.localStream || null);
          setRemoteStream(clientRef.current?.remoteStream || null);
        },
        onError: (e) => {
          const msg = e?.message || e?.toString?.() || "unknown error";
          const stack = e?.stack;
          addLog("error", `error: ${msg}`, { message: msg, stack, raw: e });
        },
      });
    }
    return clientRef.current;
  }, [config, addLog]);

  useEffect(() => {
    addLog("info", "صفحه لود شد", { whipUrl: config.whipUrl, ua: navigator.userAgent.slice(0, 120) });
    const onUnhandled = (e) => addLog("error", `unhandled: ${e.message}`, { stack: e.error?.stack });
    const onRejection = (e) => addLog("error", `promise rejection: ${e.reason?.message || e.reason}`, { reason: e.reason });
    window.addEventListener("error", onUnhandled);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onUnhandled);
      window.removeEventListener("unhandledrejection", onRejection);
      try { clientRef.current?.disconnect(); } catch {}
    };
  }, [config.whipUrl, addLog]);

  const connect = useCallback(async () => {
    t0Ref.current = Date.now();
    addLog("info", `connect() → ${config.whipUrl}`, { whipUrl: config.whipUrl });
    try {
      await getClient().connect();
      addLog("info", `connect() resolved in ${Date.now() - t0Ref.current}ms`);
    } catch (e) {
      const msg = e?.message || String(e);
      const isRefused = /Failed to fetch|ERR_CONNECTION_REFUSED|NetworkError/i.test(msg);
      if (isRefused) {
        addLog("error", `connect() failed: سرور StreamCore روی ${config.whipUrl} در دسترس نیست — آیا روشنه؟`, {
          hint: "باید هر دو روشن باشن: 1) uvicorn روی :8000  2) streamcore-server روی :8080  — تست: curl http://localhost:8000/health و curl http://localhost:8080/health",
          whipUrl: config.whipUrl,
          stack: e?.stack,
          raw: e,
        });
      } else {
        addLog("error", `connect() failed: ${msg}`, { stack: e?.stack, raw: e });
      }
      throw e;
    }
  }, [config.whipUrl, getClient, addLog]);

  const disconnect = useCallback(() => {
    addLog("info", "disconnect()");
    getClient().disconnect();
  }, [getClient, addLog]);

  const toggleMute = useCallback(() => {
    const c = getClient();
    c.toggleMute();
    const muted = c.isMuted;
    setIsMuted(muted);
    addLog("info", muted ? "mute ON" : "mute OFF");
  }, [getClient, addLog]);

  const clearLogs = useCallback(() => setLogs([]), []);

  const copyLogs = useCallback(async () => {
    const text = logs.map((l) => `[${l.time}] ${l.level.toUpperCase()} ${l.msg}${l.data ? "\n" + l.data : ""}`).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      addLog("info", "لاگ‌ها کپی شد");
    } catch {
      // fallback: select textarea
      addLog("warn", "clipboard API نشد — از دکمه دانلود استفاده کن");
    }
    return text;
  }, [logs, addLog]);

  return { status, transcript, localStream, remoteStream, isMuted, logs, addLog, connect, disconnect, toggleMute, clearLogs, copyLogs };
}
