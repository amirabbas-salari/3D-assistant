import os

def avatar_provider() -> str:
    enabled = os.getenv("AVATAR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return "none"
    p = os.getenv("AVATAR_PROVIDER", "tavus").strip().lower()
    if p in {"", "none", "off", "false"}:
        return "none"
    # فقط Tavus پشتیبانی می‌شود — did/spatius حذف شد
    if p in {"tavus", "tavus-cvi", "cvi"}:
        return "tavus"
    return "tavus"
