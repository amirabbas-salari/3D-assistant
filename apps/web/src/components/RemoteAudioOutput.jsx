import React, { useEffect, useRef } from 'react';

export default function RemoteAudioOutput({ track, registry, onRegistered }) {
  const audioRef = useRef(null);
  useEffect(() => {
    if (!audioRef.current) return undefined;
    track.attach(audioRef.current);
    if (registry) {
      registry.current = [...registry.current.filter((item) => item !== audioRef.current), audioRef.current];
      onRegistered?.(registry.current);
    }
    return () => {
      track.detach(audioRef.current);
      if (registry) {
        registry.current = registry.current.filter((item) => item !== audioRef.current);
        onRegistered?.(registry.current);
      }
    };
  }, [track, registry, onRegistered]);
  return <audio ref={audioRef} autoPlay playsInline className="remote-audio-output" />;
}
