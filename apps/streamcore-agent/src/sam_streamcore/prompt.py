import os
from pathlib import Path

_par = Path(__file__).resolve().parents
PROJECT_ROOT = _par[4] if len(_par) > 4 else _par[-1]
# داخل Docker مسیر /app است و parents[4] وجود ندارد — fallback به جستجو
if not (PROJECT_ROOT / ".env.example").exists():
    for anc in _par:
        if (anc / ".env.example").exists():
            PROJECT_ROOT = anc
            break
    else:
        # اگر هیچ .env.example پیدا نشد (Docker)، از /app یا cwd استفاده کن
        PROJECT_ROOT = Path("/app") if Path("/app/prompts").exists() else Path.cwd()

def assistant_name() -> str:
    return (os.getenv("ASSISTANT_NAME") or "سام").strip()

def sales_prompt() -> str:
    cfg = (os.getenv("SALES_PLAYBOOK") or "prompts/sales_playbook.md").strip()
    path = Path(cfg) if os.path.isabs(cfg) else PROJECT_ROOT / cfg
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text if len(text) >= 200 else ""
