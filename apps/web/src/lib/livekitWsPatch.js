/**
 * LiveKit WebSocket Blob safeguard
 * Installed livekit-client@2.24.1 parseSignalResponse expects string (JSON) or ArrayBuffer (Protobuf).
 * If Worker or browser delivers Blob, String(Blob) = "[object Blob]" → JSON.parse throws Unexpected token 'o'.
 * This patch transparently converts Blob → ArrayBuffer/string BEFORE SDK sees it, preserving binary.
 * No JWT/secret/payload logged.
 */
export function installLiveKitWsPatch(log) {
  if (typeof window === 'undefined' || !window.WebSocket) return;
  const OrigWS = window.WebSocket;
  if (OrigWS.__lkPatched) return;

  function wrapHandler(handler, label) {
    if (!handler) return handler;
    return async function (event) {
      let data = event.data;
      if (data instanceof Blob) {
        // Diagnostic: type only, never payload
        try {
          log?.('info', `[ws-patch] ${label} Blob received`, `size=${data.size} type=${data.type} binaryType=${this.binaryType || 'unknown'}`);
        } catch {}
        try {
          const ab = await data.arrayBuffer();
          const bytes = new Uint8Array(ab);
          // Heuristic: JSON payloads are ASCII JSON; Protobuf is binary with non-printable bytes
          let text = '';
          try { text = new TextDecoder().decode(bytes); } catch {}
          const t = text.trim();
          const isJson = (t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']'));
          // Never JSON.parse here — just restore expected SDK types: string for JSON, ArrayBuffer for binary
          if (isJson) {
            const newEvent = new MessageEvent('message', { data: t });
            Object.defineProperty(newEvent, 'target', { value: event.target });
            return handler.call(this, newEvent);
          }
          const newEvent = new MessageEvent('message', { data: ab });
          Object.defineProperty(newEvent, 'target', { value: event.target });
          return handler.call(this, newEvent);
        } catch (e) {
          log?.('warning', `[ws-patch] Blob convert failed`, e instanceof Error ? e.message : String(e));
          return handler.call(this, event);
        }
      }
      return handler.call(this, event);
    };
  }

  // Patch prototype setters so SDK's `ws.onmessage = fn` and `ws.addEventListener('message', fn)` both get wrapped
  class PatchedWS extends OrigWS {
    constructor(url, protocols) {
      super(url, protocols);
      // Force SDK's intended binaryType, but allow SDK to set it after
      try { super.binaryType = 'arraybuffer'; } catch {}
      // Patch instance
      const origAdd = this.addEventListener;
      this.addEventListener = function (type, listener, opts) {
        if (type === 'message' && typeof listener === 'function') {
          const wrapped = wrapHandler(listener, 'addEventListener');
          wrapped.__orig = listener;
          return origAdd.call(this, type, wrapped, opts);
        }
        return origAdd.call(this, type, listener, opts);
      };
      const origRemove = this.removeEventListener;
      this.removeEventListener = function (type, listener, opts) {
        // Need to find wrapped version if any — simplified: pass through
        return origRemove.call(this, type, listener, opts);
      };
      let _onmessage = null;
      Object.defineProperty(this, 'onmessage', {
        get() { return _onmessage; },
        set(fn) {
          _onmessage = fn ? wrapHandler(fn, 'onmessage') : null;
          // Set underlying handler via Orig prototype to avoid recursion
          Object.getOwnPropertyDescriptor(OrigWS.prototype, 'onmessage')?.set?.call(this, _onmessage);
        },
        configurable: true,
      });
      // Also ensure binaryType stays arraybuffer if SDK sets it
      let _binaryType = 'arraybuffer';
      try {
        Object.defineProperty(this, 'binaryType', {
          get() { return _binaryType; },
          set(v) { _binaryType = v; try { Object.getOwnPropertyDescriptor(OrigWS.prototype, 'binaryType')?.set?.call(this, v); } catch {} },
          configurable: true,
        });
        this.binaryType = 'arraybuffer';
      } catch {}
    }
  }
  PatchedWS.__lkPatched = true;
  window.WebSocket = PatchedWS;
}
