"""Central env + project root resolution — single source of truth."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve repo root: apps/agent/src/sam → 4 up or search for .env.example
_par = Path(__file__).resolve().parents
PROJECT_ROOT = _par[4] if len(_par) > 4 and _par[3].name == "apps" else _par[3] if len(_par) > 3 and _par[2].name == "apps" else _par[3]
if not (PROJECT_ROOT / ".env.example").exists():
    for _anc in _par:
        if (_anc / ".env.example").exists():
            PROJECT_ROOT = _anc
            break

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "apps/agent/.env")
load_dotenv()

def flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def livekit_url() -> str:
    """URL that the agent should connect to. Prefers INTERNAL when inside Docker."""
    for k in ("LIVEKIT_INTERNAL_URL", "LIVEKIT_URL_INTERNAL", "LIVEKIT_URL"):
        v = (os.getenv(k) or "").strip()
        if v:
            return v
    return "ws://localhost:7880"

def livekit_public_url() -> str:
    for k in ("LIVEKIT_PUBLIC_URL", "LIVEKIT_URL"):
        v = (os.getenv(k) or "").strip()
        if v:
            return v
    return "ws://localhost:7880"

def is_local_livekit() -> bool:
    u = (os.getenv("LIVEKIT_URL") or os.getenv("LIVEKIT_PUBLIC_URL") or os.getenv("LIVEKIT_INTERNAL_URL") or "").lower()
    return "localhost" in u or "127.0.0.1" in u or "livekit:" in u or u.startswith("ws://")

def ensure_livekit_env():
    """If INTERNAL is set, mirror it to LIVEKIT_URL for SDKs that only read LIVEKIT_URL."""
    internal = (os.getenv("LIVEKIT_INTERNAL_URL") or os.getenv("LIVEKIT_URL_INTERNAL") or "").strip()
    if internal and not (os.getenv("LIVEKIT_URL") or "").strip().startswith("ws"):
        # Only override when LIVEKIT_URL is cloud/missing; don't clobber explicit cloud url outside docker
        pass
    # Always ensure LIVEKIT_URL is set for livekit-agents SDK when INTERNAL exists but URL missing
    if internal and not os.getenv("LIVEKIT_URL"):
        os.environ["LIVEKIT_URL"] = internal
    # Also support LIVEKIT_PUBLIC_URL → LIVEKIT_URL for non-docker local
    public = (os.getenv("LIVEKIT_PUBLIC_URL") or "").strip()
    if public and not os.getenv("LIVEKIT_URL"):
        os.environ["LIVEKIT_URL"] = public
