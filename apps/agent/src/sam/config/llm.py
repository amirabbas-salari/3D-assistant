"""LLM provider abstraction — Cloudflare Workers AI ↔ OpenRouter.

- LLM_PROVIDER=openrouter → uses OpenRouter (https://openrouter.ai/api/v1)
- LLM_PROVIDER=cloudflare → uses Cloudflare Workers AI
- Auto-detect: if OPENROUTER_API_KEY is set → openrouter, else cloudflare if CLOUDFLARE_* set
- Supports both CLOUDFLARE_LLM_* and generic LLM_* / OPENROUTER_LLM_* env vars for smooth migration

تغییرات: routing ارائه‌دهندهٔ OpenRouter بر اساس تأخیر، تشخیص دقیق مدل‌های reasoning (قبلاً زیررشتهٔ
"o1"/"o3" روی نام‌های نامرتبط هم می‌خورد)، و خاموش‌کردن واقعی thinking در Qwen.
"""
import os
import re
import logging

# Defaults
DEFAULT_CLOUDFLARE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"  # fast, cheap, good Persian + tool-calling; alternatives: meta-llama/llama-3.3-70b-instruct, google/gemini-2.0-flash-001
DEFAULT_MAX_TOKENS = 90  # برای ۲ جمله + سوال؛ توجه: فارسی توکن‌خور است — اگر جواب‌ها نیمه‌کاره بریده شد LLM_MAX_TOKENS=130..150

_REASONING_KEYWORDS = ("gpt-oss", "deepseek-r1", "qwen3", "qwen-3", "qwq", "r1-distill", "reasoning", "thinking")
# o1/o3/o4 فقط وقتی «نام کامل بخش» باشند (openai/o3-mini)، نه داخل gpt-4o-mini یا اعداد
_REASONING_NAME_RE = re.compile(r"(^|[/\-_:])(o1|o3|o4)(?=$|[-_:./])", re.I)


def looks_like_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return any(k in m for k in _REASONING_KEYWORDS) or bool(_REASONING_NAME_RE.search(m))


def llm_provider() -> str:
    """Which LLM gateway to use."""
    raw = os.getenv("LLM_PROVIDER", "").strip().lower()
    if raw in {"openrouter", "or", "open_router", "open-router"}:
        return "openrouter"
    if raw in {"cloudflare", "cf", "workers", "workers-ai", "workers_ai"}:
        return "cloudflare"
    # explicit OPENROUTER_LLM_ENABLED flag
    if os.getenv("OPENROUTER_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        return "openrouter"
    # auto-detect by key presence: prefer OpenRouter when its key exists (user asked for it)
    if os.getenv("OPENROUTER_API_KEY", "").strip():
        return "openrouter"
    if os.getenv("CLOUDFLARE_API_TOKEN", "").strip() and os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip():
        return "cloudflare"
    # default: openrouter if nothing configured (will error with helpful message later)
    return "openrouter"


def llm_max_tokens() -> int:
    """Unified max_tokens with fallbacks for migration."""
    for key in ("LLM_MAX_TOKENS", "OPENROUTER_LLM_MAX_TOKENS", "CLOUDFLARE_LLM_MAX_TOKENS"):
        val = os.getenv(key, "").strip()
        if val:
            try:
                v = int(val)
                if 1 <= v <= 24000:
                    return v
            except ValueError:
                pass
    return DEFAULT_MAX_TOKENS


def llm_model() -> str:
    """Resolve model name for current provider."""
    prov = llm_provider()
    if prov == "openrouter":
        for key in ("OPENROUTER_LLM_MODEL", "LLM_MODEL", "CLOUDFLARE_LLM_MODEL"):
            val = os.getenv(key, "").strip()
            if val:
                # translate old Cloudflare @cf/... to OpenRouter equivalent if user didn't update model yet
                if val.startswith("@cf/"):
                    mapping = {
                        "@cf/meta/llama-3.3-70b-instruct-fp8-fast": "meta-llama/llama-3.3-70b-instruct",
                        "@cf/meta/llama-3.1-8b-instruct": "meta-llama/llama-3.1-8b-instruct",
                        "@cf/openai/gpt-oss-120b": "openai/gpt-oss-120b",
                        "@cf/mistral/mistral-7b-instruct-v0.1": "mistralai/mistral-7b-instruct",
                    }
                    return mapping.get(val, DEFAULT_OPENROUTER_MODEL)
                return val
        return DEFAULT_OPENROUTER_MODEL
    else:  # cloudflare
        for key in ("CLOUDFLARE_LLM_MODEL", "LLM_MODEL", "OPENROUTER_LLM_MODEL"):
            val = os.getenv(key, "").strip()
            if val:
                return val
        return DEFAULT_CLOUDFLARE_MODEL


def llm_api_key() -> str:
    prov = llm_provider()
    if prov == "openrouter":
        return os.getenv("OPENROUTER_API_KEY", "").strip()
    return os.getenv("CLOUDFLARE_API_TOKEN", "").strip()


def llm_base_url() -> str:
    prov = llm_provider()
    if prov == "openrouter":
        return (os.getenv("OPENROUTER_BASE_URL", "").strip() or os.getenv("OPENROUTER_API_BASE", "").strip() or "https://openrouter.ai/api/v1")
    # cloudflare
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if os.getenv("CLOUDFLARE_BASE_URL", "").strip():
        return os.getenv("CLOUDFLARE_BASE_URL", "").strip()
    if not account_id:
        return ""
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"


def llm_extra_headers() -> dict:
    """Optional headers for OpenRouter (referer/title)."""
    headers: dict = {}
    if llm_provider() == "openrouter":
        ref = os.getenv("OPENROUTER_HTTP_REFERER", "").strip() or os.getenv("OPENROUTER_REFERER", "").strip()
        if ref:
            headers["HTTP-Referer"] = ref
        title = os.getenv("OPENROUTER_X_TITLE", "").strip()
        if title:
            headers["X-Title"] = title
    return headers


def _openrouter_provider_prefs() -> dict:
    """Provider routing OpenRouter.

    پیش‌فرض OpenRouter بین ارائه‌دهنده‌ها بر اساس قیمت load-balance می‌کند؛ برای voice، TTFT مهم‌تر از
    قیمت است. OPENROUTER_PROVIDER_SORT = latency (پیش‌فرض) | throughput | price | off
    یا OPENROUTER_PROVIDER_ORDER=OpenAI,Azure برای ترتیب دستی (در این حالت sort اعمال نمی‌شود).
    توجه: routing بر پایهٔ latency ممکن است بین ارائه‌دهنده‌ها جابه‌جا شود و prompt-cache را کم‌اثر کند؛
    با گانت خودتان A/B کنید.
    """
    order = [p.strip() for p in os.getenv("OPENROUTER_PROVIDER_ORDER", "").split(",") if p.strip()]
    if order:
        return {"order": order, "allow_fallbacks": True}
    sort = os.getenv("OPENROUTER_PROVIDER_SORT", "latency").strip().lower()
    if sort in {"latency", "throughput", "price"}:
        return {"sort": sort}
    return {}


def _openrouter_fields(max_tokens: int, job_logger: logging.Logger | None, model: str) -> dict:
    fields: dict = {"max_tokens": max_tokens}
    m = model.lower() if model else ""
    # Qwen/QwQ thinking را داخل content می‌ریزد — برای gpt-oss نباید enable_thinking=false فرستاد (خالی برمی‌گرداند)
    qwen_models = ("qwen3", "qwen-3", "qwen3.5", "qwq", "qwen/qwen3")
    gpt_oss = "gpt-oss" in m
    is_qwen = any(k in m for k in qwen_models)
    is_reasoning = looks_like_reasoning_model(model)

    # اگر کاربر صراحتاً خواسته thinking روشن بماند
    if is_reasoning and os.getenv("OPENROUTER_INCLUDE_REASONING", "").strip().lower() in {"1", "true", "yes", "on"}:
        raw = os.getenv("OPENROUTER_REASONING_EFFORT", "").strip().lower() or os.getenv("OPENROUTER_LLM_REASONING_EFFORT", "").strip().lower()
        effort = "" if raw in {"", "default", "unset", "none"} else raw
        if effort in {"low", "medium", "high"}:
            fields["reasoning"] = {"effort": effort}
            if job_logger:
                job_logger.info("LLM speed: provider=openrouter model=%s reasoning=%s (explicit include), max_tokens=%s", model or "?", effort, max_tokens)
        elif job_logger:
            job_logger.info("LLM speed: provider=openrouter model=%s reasoning=included, max_tokens=%s", model or "?", max_tokens)
        return fields

    if is_qwen:
        # reasoning.exclude فقط پنهان‌کردن توکن‌های thinking از پاسخ است؛ مدل همچنان فکر می‌کند (تأخیر می‌ماند).
        # برای خاموش‌کردن واقعی: enabled=False (+ enable_thinking=false برای ارائه‌دهنده‌هایی که chat_template می‌خوانند)
        fields["reasoning"] = {"enabled": False, "exclude": True}
        fields["chat_template_kwargs"] = {"enable_thinking": False}
        fields["enable_thinking"] = False
        if job_logger:
            job_logger.info("LLM speed: provider=openrouter model=%s reasoning=DISABLED (enabled=false + enable_thinking=false), max_tokens=%s", model or "?", max_tokens)
        return fields
    if gpt_oss:
        auto = os.getenv("OPENROUTER_LLM_AUTO_FALLBACK", "true").strip().lower() not in {"0", "false", "no", "off", ""}
        if auto and job_logger:
            job_logger.warning("LLM %s برای voice مناسب نیست و ممکن است خالی برگرداند — اگر پاسخی نگرفتید OPENROUTER_LLM_MODEL=openai/gpt-4o-mini بگذارید", model)
        if job_logger:
            job_logger.info("LLM speed: provider=openrouter model=%s reasoning=default (gpt-oss, no exclude), max_tokens=%s", model or "?", max_tokens)
        return fields

    if is_reasoning:
        # توجه: exclude فقط خروجی را پنهان می‌کند؛ این مدل‌ها برای voice همچنان کندند (هشدار در entrypoint)
        fields["reasoning"] = {"exclude": True}
        fields["chat_template_kwargs"] = {"enable_thinking": False}
        fields["enable_thinking"] = False
        if job_logger:
            job_logger.info("LLM speed: provider=openrouter model=%s reasoning=HIDDEN (exclude + enable_thinking=false; may still think), max_tokens=%s", model or "?", max_tokens)
        return fields

    raw = os.getenv("OPENROUTER_REASONING_EFFORT", "").strip().lower() or os.getenv("OPENROUTER_LLM_REASONING_EFFORT", "").strip().lower()
    effort = "" if raw in {"", "default", "unset", "none"} else raw
    if effort in {"low", "medium", "high"}:
        fields["reasoning"] = {"effort": effort}
        if job_logger:
            job_logger.info("LLM speed: provider=openrouter model=%s reasoning=%s, max_tokens=%s", model or "?", effort, max_tokens)
    elif job_logger:
        job_logger.info("LLM speed: provider=openrouter model=%s, max_tokens=%s", model or "?", max_tokens)
    return fields


def llm_request_body(max_tokens: int, job_logger: logging.Logger | None = None, *, model: str = "") -> dict:
    fields: dict = {"max_tokens": max_tokens}
    prov = llm_provider()
    if prov == "cloudflare":
        raw = os.getenv("CLOUDFLARE_LLM_REASONING_EFFORT", "low").strip().lower()
        effort = "" if raw in {"", "default", "unset", "none"} else raw
        is_reasoning_model = "gpt-oss" in model.lower() if model else True
        if not is_reasoning_model and effort:
            if job_logger:
                job_logger.info("LLM %s نیازی به reasoning_effort ندارد — %r نادیده گرفته شد (payload سبک‌تر)", model, effort)
            effort = ""
        if effort in {"low", "medium", "high"}:
            fields["reasoning_effort"] = effort
        elif effort:
            if job_logger:
                job_logger.warning("Unknown CLOUDFLARE_LLM_REASONING_EFFORT=%r; valid: low,medium,high,default", raw)
            effort = ""
        if effort and os.getenv("CLOUDFLARE_LLM_REASONING_NESTED", "false").strip().lower() in {"1", "true", "yes", "on"}:
            fields["reasoning"] = {"effort": effort}
        if job_logger:
            job_logger.info("LLM speed: provider=cloudflare model=%s reasoning_effort=%s, max_tokens=%s", model or "?", effort or "provider default", max_tokens)
        return fields

    fields = _openrouter_fields(max_tokens, job_logger, model)
    prefs = _openrouter_provider_prefs()
    if prefs:
        fields["provider"] = prefs
        if job_logger:
            job_logger.info("LLM routing: openrouter provider=%s", prefs)
    return fields


def validate_llm_config(job_logger: logging.Logger | None = None) -> tuple[str, str, str]:
    """Return (provider, model, base_url) or raise with helpful message."""
    prov = llm_provider()
    model = llm_model()
    base_url = llm_base_url()
    api_key = llm_api_key()
    if prov == "openrouter":
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY (get one at https://openrouter.ai/settings/keys — free tier available). Set it in .env and optionally OPENROUTER_LLM_MODEL.")
        if not base_url:
            base_url = "https://openrouter.ai/api/v1"
    else:  # cloudflare
        if not api_key or not os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip():
            raise RuntimeError("LLM_PROVIDER=cloudflare requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN. Or set LLM_PROVIDER=openrouter with OPENROUTER_API_KEY.")
    if job_logger:
        job_logger.info("LLM provider=%s model=%s base_url=%s", prov, model, base_url)
    return prov, model, base_url
