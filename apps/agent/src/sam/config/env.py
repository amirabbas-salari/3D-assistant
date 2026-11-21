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
