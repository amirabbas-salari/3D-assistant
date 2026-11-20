// Shifts the avatar's motion so the mouth lines up with the voice you hear.
//
// The problem this solves: in the host-owned RTC path (`AvatarPlayer.attach`)
// the Spatius cloud sends audio and motion on separate tracks, the adapter
// renders motion on its own 25 fps clock, and the browser plays the audio
// through a media element. Those are independent clocks, so motion lands
// slightly ahead of the sound — the lips start before the voice.
//
// What the SDK does and does not give us: animation frames carry a sequence
// number, not the audio position they belong to, so per-frame alignment is not
// possible from the browser. Every frame does, however, go through
// `avatarView.renderFromProtobuf`, and that call is what the adapter's pacing
// loop waits on. Holding the first frames of a turn therefore delays the whole
// motion track by exactly the amount we hold them — which is the correction
// this symptom needs, without disturbing the frames after it.
//
// The offset is deliberately a user-facing number rather than a magic constant:
// the real delay depends on the network path and the Spatius worker, and no
// browser API reports it. The panel shows the number and lets it be dialled in
// while listening.

const DEFAULT_OFFSET_MS = 120;
const MAX_OFFSET_MS = 900;
const WAIT_TIMEOUT_MS = 2500;

/**
 * @param {object} options
 * @param {(element: HTMLMediaElement|null) => void} [options.onAudioElement]
 *   called with whichever element is currently playing the agent's voice
 */
export function createLipSync({ onAudioElement } = {}) {
  let offsetMs = DEFAULT_OFFSET_MS;
  let enabled = true;

  let view = null;
  let original = null;
  let elements = [];

  // Release bookkeeping for the frame currently held back.
  let gate = null;
  let gateStartedAt = 0;
  let gateAudioStart = null;
  let timer = null;

  // A turn begins when a fresh audio element starts from silence; every frame
  // until that turn's audio has played `offsetMs` is held, then motion runs free
  // until the next turn.
  let turnOpen = false;
  let turnReleased = false;

  const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

  function playingElement() {
    for (const element of elements) {
      if (element && !element.paused && !element.ended && element.readyState >= 2) return element;
    }
    return null;
  }

  /** Hand the held frame to the real renderer, then mark the turn released. */
  function releaseHeld(render = true) {
    if (!gate) return;
    const held = gate;
    gate = null;
    if (render && held.args) original.apply(view, held.args);
    held.resolve(undefined);
  }

  /** How long the current turn's audio has been audible. */
  function audioElapsedMs(element) {
    if (!element) return null;
    if (gateAudioStart === null) gateAudioStart = element.currentTime;
    return Math.max(0, (element.currentTime - gateAudioStart) * 1000);
  }

  function checkGate() {
    if (!gate) return;
    const element = playingElement();
    const elapsed = audioElapsedMs(element);
    const timedOut = now() - gateStartedAt > WAIT_TIMEOUT_MS;

    if (!element) {
      // No audio yet. Waiting is the point of this gate, but not forever: a
      // silent turn must not freeze the face.
      if (timedOut) {
        turnReleased = true;
        releaseHeld();
      }
      return;
    }
    if (elapsed === null || elapsed >= offsetMs || timedOut) {
      turnReleased = true;
      releaseHeld();
    }
  }

  function startTurn() {
    turnOpen = true;
    turnReleased = false;
    gateAudioStart = null;
  }

  function handleFrame(data, args) {
    if (!enabled) return original.apply(view, args);

    if (turnReleased) return original.apply(view, args);
    if (!turnOpen) startTurn();

    // Hold the first frame until the voice has actually been playing for the
    // configured offset, then let the SDK's own pacing take over again.
    if (!gate) {
      gateStartedAt = now();
      const promise = new Promise((resolve) => {
        gate = { resolve, args };
      });
      if (timer === null) timer = window.setInterval(checkGate, 10);
      return promise;
    }
    // A second frame while the first is still held: let it through untouched.
    // The pacing loop only asks for the next frame after this one resolves, so
    // holding it too would queue frames for no benefit.
    return original.apply(view, args);
  }

  return {
    attachView(nextView) {
      if (!nextView || typeof nextView.renderFromProtobuf !== 'function') return;
      if (view === nextView) return;
      this.detachView();
      view = nextView;
      original = nextView.renderFromProtobuf;
      nextView.renderFromProtobuf = function patchedRenderFromProtobuf(data, ...rest) {
        return handleFrame(data, [data, ...rest]);
      };
    },

    detachView() {
      if (view && original) view.renderFromProtobuf = original;
      if (timer !== null) window.clearInterval(timer);
      timer = null;
      releaseHeld();
      view = null;
      original = null;
      // The audio elements outlive a single view: a re-render replaces the
      // view while the same element keeps playing the agent's voice.
      turnOpen = false;
      turnReleased = false;
      gateAudioStart = null;
    },

    /** Keep every element that may carry the agent's voice. */
    setAudioElements(next) {
      elements = (next || []).filter(Boolean);
      onAudioElement?.(playingElement());
    },

    /** Called by the UI on each new assistant turn. */
    beginTurn() {
      startTurn();
    },

    configure({ offsetMs: nextOffset, enabled: nextEnabled } = {}) {
      if (typeof nextOffset === 'number' && Number.isFinite(nextOffset)) {
        offsetMs = Math.max(0, Math.min(MAX_OFFSET_MS, nextOffset));
      }
      if (typeof nextEnabled === 'boolean') enabled = nextEnabled;
      if (!enabled) {
        releaseHeld();
        turnReleased = true;
      }
    },

    stats() {
      const element = playingElement();
      return {
        offsetMs,
        enabled,
        waiting: Boolean(gate),
        audioElapsedMs: audioElapsedMs(element) === null ? null : Math.round(audioElapsedMs(element)),
        elementTime: element ? Number(element.currentTime.toFixed(2)) : null,
      };
    },

    dispose() {
      this.detachView();
      elements = [];
    },
  };
}
