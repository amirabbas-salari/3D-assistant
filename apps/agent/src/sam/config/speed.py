"""Latency profiles — endpointing + preemptive generation knobs."""
import json, os, logging

SPEED_PROFILES: dict[str, dict] = {
    "balanced": {"preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 20.0}},
    "fast": {"endpointing": {"min_delay": 0.2, "max_delay": 2.0}, "preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 20.0}},
    "fastest": {"endpointing": {"min_delay": 0.15, "max_delay": 1.5}, "preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 30.0}},
    # ultra: تعادل دقت/سرعت برای فارسی — افزایش‌های قبلی برای حل transcript دیررس بود
    # حالا با دقت بالاتر: min_delay کمتر برای واکنش سریع، ولی max_delay محدود برای جلوگیری از انتظار طولانی
    # اگر STT کند بود و warning دیدی، AGENT_MIN_ENDPOINTING_DELAY=0.25 بگذار
    "ultra": {"endpointing": {"min_delay": 0.15, "max_delay": 1.0}, "preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 40.0}, "interruption": {"min_duration": 0.5, "false_interruption_timeout": 0.5}},
    "instant": {"endpointing": {"min_delay": 0.08, "max_delay": 0.8}, "preemptive_generation": {"preemptive_tts": True, "max_speech_duration": 40.0}, "interruption": {"min_duration": 0.4, "false_interruption_timeout": 0.4}},
}

def speed_profile(job_logger: logging.Logger) -> dict:
    profile = os.getenv("AGENT_SPEED_PROFILE", "ultra").strip().lower() or "ultra"
    if profile not in SPEED_PROFILES:
        job_logger.warning("Unknown AGENT_SPEED_PROFILE=%r; using 'ultra'. Valid: %s", profile, ", ".join(SPEED_PROFILES))
        profile = "ultra"
    turn_handling: dict = json.loads(json.dumps(SPEED_PROFILES[profile]))
    for env_key in ["AGENT_MIN_ENDPOINTING_DELAY", "AGENT_MAX_ENDPOINTING_DELAY"]:
        raw = os.getenv(env_key, "").strip()
        if raw:
            ep = turn_handling.setdefault("endpointing", {})
            try:
                if env_key == "AGENT_MIN_ENDPOINTING_DELAY": ep["min_delay"] = float(raw)
                else: ep["max_delay"] = float(raw)
            except ValueError: job_logger.warning("%s=%r not a number; ignored", env_key, raw)
    for env_key, target in [("AGENT_INTERRUPTION_MIN_DURATION", "min_duration"), ("AGENT_FALSE_INTERRUPTION_TIMEOUT", "false_interruption_timeout")]:
        raw=os.getenv(env_key,"").strip()
        if raw:
            try: turn_handling.setdefault("interruption", {})[target]=float(raw)
            except ValueError: job_logger.warning("%s=%r not a number", env_key, raw)
    pre = os.getenv("AGENT_PREEMPTIVE_TTS","").strip().lower()
    if pre in {"1","true","yes","on"}: turn_handling.setdefault("preemptive_generation", {})["preemptive_tts"]=True
    elif pre in {"0","false","no","off"}: turn_handling.setdefault("preemptive_generation", {})["preemptive_tts"]=False
    job_logger.info("Speed profile=%s → %s", profile, json.dumps(turn_handling, ensure_ascii=False))
    return turn_handling
