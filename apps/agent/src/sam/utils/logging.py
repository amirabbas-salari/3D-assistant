import asyncio, logging, re

_SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token)(\s*[:=]\s*)[^\s,;]+")
def redact(text: str) -> str:
    return _SECRET_RE.sub(r"\1\2[REDACTED]", text)

class RoomLogHandler(logging.Handler):
    def __init__(self, publish_log):
        super().__init__(level=logging.INFO)
        self._publish_log = publish_log
        self._formatter = logging.Formatter()
        # cache main loop at init — RAG runs in to_thread without loop
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
    def emit(self, record):
        try:
            try:
                msg = record.getMessage()
            except Exception:
                msg = str(record.msg)
            details = self._formatter.formatException(record.exc_info) if record.exc_info else ""
            payload = {"type":"system_log","level":record.levelname.lower(),"message":redact(msg)[:1600],"details":redact(details)[:2600],"logger":record.name}
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
        except Exception:
            try:
                self.handleError(record)
            except Exception:
                pass
