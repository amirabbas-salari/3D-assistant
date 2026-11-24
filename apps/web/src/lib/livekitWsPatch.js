/**
 * LiveKit WebSocket Blob safeguard — livekit-client@2.24.1
 * parseSignalResponse expects string (JSON) or ArrayBuffer (Protobuf).
 * If Worker delivers Blob, String(Blob)="[object Blob]" → JSON.parse fails.
 * Patch converts Blob → ArrayBuffer/string before SDK sees it.
 */
export function installLiveKitWsPatch(log) {
  if (typeof window === 'undefined' || !window.WebSocket) return;
  const OrigWS = window.WebSocket;
  if (OrigWS.__lkPatched) return;

  function wrapFn(fn, label) {
    if (typeof fn !== 'function') return fn;
    return async function (event) {
      let data = event.data;
      if (data instanceof Blob) {
        try { log?.('warning', `[ws-patch] ${label} Blob→convert`, `size=${data.size} type=${data.type||'blob'} binaryType=${this.binaryType}`); } catch {}
        try {
          const ab = await data.arrayBuffer();
          const bytes = new Uint8Array(ab);
          let isJson = false;
          try {
            const t = new TextDecoder().decode(bytes).trim();
            isJson = (t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']'));
            if (isJson) {
              // SDK expects string for JSON signal messages
              const ev = new MessageEvent('message', { data: t });
              return fn.call(this, ev);
            }
          } catch {}
          const ev = new MessageEvent('message', { data: ab });
          return fn.call(this, ev);
        } catch (e) {
          log?.('warning', `[ws-patch] Blob convert failed`, e instanceof Error ? e.message : String(e));
        }
      }
      return fn.call(this, event);
    };
  }

  // Wrap window.WebSocket constructor — most reliable: SDK does `new WebSocket(url)` which hits this.
  function PatchedWS(url, protocols) {
    const ws = protocols !== undefined ? new OrigWS(url, protocols) : new OrigWS(url);
    // Ensure binaryType is arraybuffer for SDK (must be set before onopen)
    try { ws.binaryType = 'arraybuffer'; } catch {}
    // Wrap onmessage setter
    let _onmessage = null;
    const desc = Object.getOwnPropertyDescriptor(OrigWS.prototype, 'onmessage');
    if (desc && desc.set) {
      Object.defineProperty(ws, 'onmessage', {
        get() { return _onmessage; },
        set(v) { _onmessage = v ? wrapFn(v, 'onmessage') : v; desc.set.call(ws, _onmessage); },
        configurable: true, enumerable: true,
      });
    } else {
      // Fallback: pollute instance
      Object.defineProperty(ws, 'onmessage', {
        get() { return _onmessage; },
        set(v) { _onmessage = v ? wrapFn(v, 'onmessage') : v; ws.__origOnMessage = _onmessage; if (_onmessage) ws.addEventListener('message', _onmessage); },
        configurable: true,
      });
    }
    // Wrap addEventListener for 'message'
    const origAdd = ws.addEventListener.bind(ws);
    ws.addEventListener = function (type, listener, opts) {
      if (type === 'message' && typeof listener === 'function') {
        return origAdd(type, wrapFn(listener, 'addEventListener'), opts);
      }
      return origAdd(type, listener, opts);
    };
    return ws;
  }
  PatchedWS.prototype = OrigWS.prototype;
  Object.setPrototypeOf(PatchedWS, OrigWS);
  PatchedWS.__lkPatched = true;
  // Copy statics
  PatchedWS.CONNECTING = OrigWS.CONNECTING; PatchedWS.OPEN = OrigWS.OPEN; PatchedWS.CLOSING = OrigWS.CLOSING; PatchedWS.CLOSED = OrigWS.CLOSED;
  window.WebSocket = PatchedWS;
}
