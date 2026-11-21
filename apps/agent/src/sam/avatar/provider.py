import os
def avatar_provider() -> str:
    enabled = os.getenv("AVATAR_ENABLED","false").strip().lower() in {"1","true","yes","on"}
    if not enabled: return "none"
    p = os.getenv("AVATAR_PROVIDER","spatius").strip().lower()
    if p in {"","none","off","false"}: return "none"
    if p not in {"did","d-id","didid"}: return "spatius"
    return "did"
