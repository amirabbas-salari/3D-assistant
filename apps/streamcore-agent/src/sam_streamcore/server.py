"""
FastAPI HTTP Agent برای StreamCore — llm.provider = "agent"

پروتکل StreamCore (POST /agent):
  request: {session_id, resource_id, type: "chat"|"oneshot", text, system, interrupted_text, context, summary}
  response: text/plain streaming (هر جمله کامل بلافاصله به TTS می‌ره) یا application/json

ویژگی‌ها:
- history بر اساس session_id (TTL 30 دقیقه) — شبیه LiveKit chat_ctx
- RAG inject قبل از آخرین پیام کاربر (مثل before llm_node)
- streaming LLM via OpenAI-compatible (OpenRouter / OpenAI / LiveKit inference via OpenAI SDK)
- تاخیر کم: TTFT ~300ms با gpt-4o-mini، اولین جمله 80ms بعد TTFT بسته می‌شه چون StreamCore خودش sentence chunking می‌کنه
"""
import os
import time
import asyncio
import logging
from collections import OrderedDict
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
load_dotenv("apps/streamcore-agent/.env")
load_dotenv(".env")

from .agent import build_instructions
from .rag import rag_query

logger = logging.getLogger("sam-streamcore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

app = FastAPI(title="سام — StreamCore Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- session memory: session_id -> list[ {role, content} ] ---
_MAX_HISTORY = int(os.getenv("AGENT_MAX_HISTORY_ITEMS", "12").strip() or 12)
_SESSION_TTL_S = 1800  # 30 دقیقه
_sessions: OrderedDict[str, dict] = {}  # session_id -> {history: [...], updated: ts}

def _get_session(sid: str) -> list:
    now = time.time()
    # پاکسازی قدیمی‌ها
    if len(_sessions) > 200:
        for k, v in list(_sessions.items())[:50]:
            if now - v["updated"] > _SESSION_TTL_S:
                del _sessions[k]
    ent = _sessions.get(sid)
    if not ent:
        ent = {"history": [], "updated": now}
        _sessions[sid] = ent
    else:
        ent["updated"] = now
    return ent["history"]

def _trim_history(hist: list):
    # نگه‌داشتن فقط _MAX_HISTORY پیام آخر (user+assistant interleaved)
    if len(hist) > _MAX_HISTORY:
        del hist[0: len(hist) - _MAX_HISTORY]

# --- LLM client ---
def _get_openai_client():
    import openai
    # اولویت: OPENAI_API_KEY > OPENROUTER_API_KEY > LIVEKIT (که نداریم) — برای local از OPENAI_API_KEY استفاده کن
    api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip()
    # اگر OPENAI_API_KEY پره، base_url پیش‌فرض openai
    if os.getenv("OPENAI_API_KEY", "").strip() and not os.getenv("OPENROUTER_API_KEY", "").strip():
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    if not api_key:
        logger.warning("No OPENAI_API_KEY / OPENROUTER_API_KEY — LLM will fail")
        api_key = "sk-missing"
    # httpx client با keepalive
    import httpx
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=float(os.getenv("LLM_READ_TIMEOUT", "15")), write=5.0, pool=5.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60),
    )
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0, http_client=http_client)
    return client

_openai_client = None
def client():
    global _openai_client
    if _openai_client is None:
        _openai_client = _get_openai_client()
    return _openai_client

def _model() -> str:
    for k in ("OPENAI_MODEL", "OPENROUTER_LLM_MODEL", "LIVEKIT_LLM_MODEL", "LLM_MODEL"):
        v = (os.getenv(k) or "").strip()
        if v:
            if v.startswith("@cf/"):
                return "openai/gpt-4o-mini"
            return v
    return os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini")

SYSTEM_PROMPT = build_instructions()
logger.info("System prompt %d chars, model=%s, max_history=%d", len(SYSTEM_PROMPT), _model(), _MAX_HISTORY)

@app.get("/health")
async def health():
    return {"status": "ok", "model": _model(), "sessions": len(_sessions), "system_prompt_chars": len(SYSTEM_PROMPT)}

@app.post("/agent")
async def handle_agent(request: Request):
    """
    StreamCore POST /agent — هر turn کاربر
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    session_id = (body.get("session_id") or body.get("sessionId") or "default").strip() or "default"
    resource_id = (body.get("resource_id") or body.get("resourceId") or "").strip()
    typ = (body.get("type") or "chat").strip().lower()
    text = (body.get("text") or "").strip()
    system_extra = (body.get("system") or "").strip()
    interrupted_text = (body.get("interrupted_text") or body.get("interruptedText") or "").strip()
    context_chunks = body.get("context") or []
    summary = (body.get("summary") or "").strip()

    logger.info("→ [%s] type=%s len=%d interrupted=%s ctx=%d summary=%d", session_id[:8], typ, len(text), bool(interrupted_text), len(context_chunks) if isinstance(context_chunks, list) else 0, len(summary))

    if typ == "oneshot":
        # StreamCore برای summary داخلی صدا می‌زنه — پاسخ کوتاه و سریع
        sys = system_extra or "Summarize briefly in Persian."
        user = text
        return await _oneshot_response(sys, user)

    if not text:
        return JSONResponse({"text": ""})

    history = _get_session(session_id)

    # اگر قطع شده، به تاریخچه اضافه کن که نصف شنیده شده
    if interrupted_text:
        # آخرین assistant که ناقص مونده رو اصلاح کن (اختیاری)
        # اینجا فقط لاگ می‌کنیم
        logger.info("  interrupted_text: %r", interrupted_text[:80])

    # RAG: اگر StreamCore context نداده، خودمون query کنیم
    rag_text = None
    if context_chunks and isinstance(context_chunks, list) and len(context_chunks) > 0:
        rag_text = "\n\n".join(str(c)[:500] for c in context_chunks[:3])
    else:
        rag_text = rag_query(text)

    # history به OpenAI messages تبدیل کن
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if system_extra:
        messages.append({"role": "system", "content": system_extra})
    if summary:
        messages.append({"role": "system", "content": f"خلاصه مکالمات قبلی:\n{summary}"})
    if rag_text:
        messages.append({"role": "system", "content": f"دانش مرتبط (از پایگاه شرکت):\n{rag_text}"})
    # تاریخچه قبلی
    for m in history:
        messages.append(m)
    messages.append({"role": "user", "content": text})

    # برای اینکه StreamCore زود به TTS بره، باید streaming جواب بدیم
    # StreamCore هر جمله کامل رو بلافاصله می‌خونه — پس plain text chunked عالیه
    wants_stream = True
    # اگر کلاینت application/json خواست، buffered می‌دیم — ولی پیش‌فرض stream
    accept = request.headers.get("accept", "")

    # نگه‌داشتن history برای turn بعد — بعد از اینکه LLM کامل شد اضافه می‌کنیم (در generator)
    # برای اینکه اگر client قطع کرد (barge-in) history خراب نشه، فقط وقتی کامل شد append می‌کنیم
    async def stream_text_plain() -> AsyncGenerator[bytes, None]:
        full = []
        try:
            c = client()
            stream = await c.chat.completions.create(
                model=_model(),
                messages=messages,
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "120")),
                temperature=0.7,
                stream=True,
            )
            async for chunk in stream:
                # check if client disconnected (barge-in)
                if await request.is_disconnected():
                    logger.info("  ← client disconnected (barge-in), cancel")
                    # تلاش برای cancel LLM stream
                    try:
                        await stream.close()
                    except Exception:
                        pass
                    break
                try:
                    delta = chunk.choices[0].delta.content
                except Exception:
                    delta = None
                if delta:
                    full.append(delta)
                    yield delta.encode("utf-8")
                    # مهم: هر chunk رو flush کن تا StreamCore فوراً sentence detection کنه
                    # FastAPI StreamingResponse خودکار chunked encoding می‌کنه
        except asyncio.CancelledError:
            logger.info("  ← stream cancelled")
            raise
        except Exception as e:
            logger.error("LLM stream error: %s", e, exc_info=True)
            if not full:
                yield f"ببخشید، الان یکم شلوغیم — دوباره بگید؟".encode("utf-8")
                full.append("ببخشید، الان یکم شلوغیم — دوباره بگید؟")
        finally:
            text_out = "".join(full).strip()
            if text_out:
                # ذخیره در history
                history.append({"role": "user", "content": text})
                history.append({"role": "assistant", "content": text_out})
                _trim_history(history)
                logger.info("← [%s] %d chars: %r", session_id[:8], len(text_out), text_out[:80])

    # اگر کلاینت صریحاً json خواست، buffered
    if "application/json" in accept and "text/plain" not in accept:
        # buffered fallback
        buf = b"".join([c async for c in stream_text_plain()])
        return JSONResponse({"text": buf.decode("utf-8", "replace")})

    # پیش‌فرض: text/plain streaming — بهترین latency برای StreamCore
    return StreamingResponse(stream_text_plain(), media_type="text/plain; charset=utf-8", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })

async def _oneshot_response(system: str, user: str):
    # oneshot برای summary — سریع و کوتاه
    try:
        c = client()
        resp = await c.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        txt = (resp.choices[0].message.content or "").strip()
        return JSONResponse({"text": txt})
    except Exception as e:
        logger.warning("oneshot failed: %s", e)
        return JSONResponse({"text": user[:200]})

@app.post("/agent/json")
async def handle_agent_json(request: Request):
    # alias برای تست با curl -H "Accept: application/json"
    request.headers.__dict__["_list"] = [(k, v) for k, v in request.headers.items()]  # noop
    return await handle_agent(request)
