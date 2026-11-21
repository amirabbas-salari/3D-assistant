import os
from pathlib import Path
from ..config.env import PROJECT_ROOT
def assistant_name() -> str:
    return (os.getenv("ASSISTANT_NAME") or "سام").strip()
def sales_prompt() -> str:
    cfg=(os.getenv("SALES_PLAYBOOK") or "prompts/sales_playbook.md").strip()
    path = Path(cfg) if os.path.isabs(cfg) else PROJECT_ROOT / cfg
    try: text=path.read_text(encoding="utf-8").strip()
    except OSError: return ""
    return text if len(text)>=200 else ""
