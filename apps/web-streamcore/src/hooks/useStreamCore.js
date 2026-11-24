"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { StreamCoreAIClient } from "@streamcore/js-sdk";

export function useStreamCore(config) {
  const [status, setStatus] = useState("idle");
  const [transcript, setTranscript] = useState([]);
  const [localStream, setLocalStream] = useState(null);
  const [remoteStream, setRemoteStream] = useState(null);
  const [isMuted, setIsMuted] = useState(false);
  const clientRef = useRef(null);

  const getClient = useCallback(() => {
    if (!clientRef.current) {
      clientRef.current = new StreamCoreAIClient(config, {
        onTranscript: (_entry, all) => setTranscript([...all]),
        onStatusChange: (s) => {
          setStatus(s);
          setLocalStream(clientRef.current?.localStream || null);
          setRemoteStream(clientRef.current?.remoteStream || null);
        },
        onError: (e) => console.error("[streamcore]", e),
      });
    }
    return clientRef.current;
  }, [config]);

  useEffect(() => () => clientRef.current?.disconnect(), []);

  const connect = useCallback(async () => { await getClient().connect(); }, [getClient]);
  const disconnect = useCallback(() => getClient().disconnect(), [getClient]);
  const toggleMute = useCallback(() => {
    const c = getClient();
    c.toggleMute();
    setIsMuted(c.isMuted);
  }, [getClient]);

  return { status, transcript, localStream, remoteStream, isMuted, connect, disconnect, toggleMute };
}
