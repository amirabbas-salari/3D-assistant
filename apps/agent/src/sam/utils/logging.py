import asyncio, logging, re

_SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token)(\s*[:=]\s*)[^\s,;]+")
def redact(text: str) -> str:
    return _SECRET_RE.sub(r"\1\2[REDACTED]", text)

class RoomLogHandler(logging.Handler):
    def __init__(self, publish_log):
        super().__init__(level=logging.INFO)
        self._publish_log = publish_log
        self._formatter = logging.Formatter()
        # cache the main event loop at init time (created in entrypoint's async context)
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
    def emit(self, record):
        try:
            try:
                msg = record.getMessage()
            except Exception:
                # Bad % formatting — never crash the job
                msg = str(record.msg)
            details = self._formatter.formatException(record.exc_info) if record.exc_info else ""
            payload = {"type":"system_log","level":record.levelname.lower(),"message":redact(msg)[:1600],"details":redact(details)[:2600],"logger":record.name}
            # If we're on a worker thread (e.g. RAG to_thread or TTS httpx init), get_running_loop() fails.
            # Fall back to the loop captured at init, or simply skip publish (don't crash).
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._publish_log(payload))
                return
            except RuntimeError:
                pass
            if self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(lambda: self._loop.create_task(self._publish_log(payload)))
                    return
                except Exception:
                    pass
            # No loop available (thread at startup) — just drop the publish, don't error
            return
        except Exception:
            try:
                self.handleError(record)
            except Exception:
                pass
