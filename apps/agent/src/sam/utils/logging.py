import asyncio, logging, re

_SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token)(\s*[:=]\s*)[^\s,;]+")
def redact(text: str) -> str:
    return _SECRET_RE.sub(r"\1\2[REDACTED]", text)

class RoomLogHandler(logging.Handler):
    def __init__(self, publish_log):
        super().__init__(level=logging.INFO)
        self._publish_log = publish_log
        self._formatter = logging.Formatter()
    def emit(self, record):
        try:
            details = self._formatter.formatException(record.exc_info) if record.exc_info else ""
            payload = {"type":"system_log","level":record.levelname.lower(),"message":redact(record.getMessage())[:1600],"details":redact(details)[:2600],"logger":record.name}
            asyncio.get_running_loop().create_task(self._publish_log(payload))
        except Exception:
            self.handleError(record)
