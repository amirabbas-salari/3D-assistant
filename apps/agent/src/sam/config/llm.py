"""LLM Workers AI request body + reasoning controls."""
import os
import logging

def llm_request_body(max_tokens: int, job_logger: logging.Logger | None = None) -> dict:
    fields: dict = {"max_tokens": max_tokens}
    raw = os.getenv("CLOUDFLARE_LLM_REASONING_EFFORT", "low").strip().lower()
    effort = "" if raw in {"", "default", "unset", "none"} else raw
    if effort in {"low", "medium", "high"}:
        fields["reasoning_effort"] = effort
    elif effort:
        if job_logger:
            job_logger.warning("Unknown CLOUDFLARE_LLM_REASONING_EFFORT=%r; valid: low,medium,high,default", raw)
        effort = ""
    if effort and os.getenv("CLOUDFLARE_LLM_REASONING_NESTED", "false").strip().lower() in {"1","true","yes","on"}:
        fields["reasoning"] = {"effort": effort}
    if job_logger:
        job_logger.info("LLM speed: reasoning_effort=%s, max_tokens=%s", effort or "provider default", max_tokens)
    return fields
