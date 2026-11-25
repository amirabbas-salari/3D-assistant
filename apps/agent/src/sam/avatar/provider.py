import os

def avatar_provider() -> str:
    enabled = os.getenv("AVATAR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return "none"
    p = os.getenv("AVATAR_PROVIDER", "tavus").strip().lower()
    if p in {"", "none", "off", "false"}:
        return "none"
    if p in {"spatius", "spatius-avatar", "spatius_avatar", "avatar"}:
        return "spatius"
    if p in {"tavus", "tavus-cvi", "cvi", "daily", "tavus-livekit", "livekit", "tavus_auto"}:
        return "tavus"
    # برای backward-compat
    if p in {"did", "d-id", "heygen", "hedra"}:
        return p
    # اگر مقدار ناشناس بود، به همان مقدار برگردان تا isConfigured هشدار دهد
    # ولی برای جلوگیری از کرش، tavus را fallback نکن — صریحاً خطا به کاربر نشان داده شود
    # در عمل کاربر فقط tavus یا spatius می‌گذارد
    return p
