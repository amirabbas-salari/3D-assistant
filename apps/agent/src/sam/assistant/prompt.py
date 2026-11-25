import os
from pathlib import Path
from ..config.env import PROJECT_ROOT

def assistant_name() -> str:
    return (os.getenv("ASSISTANT_NAME") or "سام").strip()

def _load_file(env_key: str, default_path: str, min_len: int = 100) -> str:
    cfg = (os.getenv(env_key) or default_path).strip()
    path = Path(cfg) if os.path.isabs(cfg) else PROJECT_ROOT / cfg
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text if len(text) >= min_len else ""

def sales_prompt() -> str:
    return _load_file("SALES_PLAYBOOK", "prompts/sales_playbook.md", 200)

def company_knowledge() -> str:
    return _load_file("COMPANY_KNOWLEDGE", "prompts/company_knowledge.md", 200)

def company_system_prompt() -> str:
    return _load_file("COMPANY_SYSTEM_PROMPT", "prompts/company_system_prompt.md", 200)
