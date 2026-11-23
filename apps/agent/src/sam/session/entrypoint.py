"""Main LiveKit entrypoint — wired from modular config/speech/avatar/rag."""
import asyncio, json, logging, os, time
from livekit import agents, rtc
from livekit.agents import APIConnectOptions, AgentSession, RoomOutputOptions, SessionConnectOptions, inference
from livekit.plugins import openai

from ..config.env import flag
from ..config.llm import llm_request_body
from ..config.speed import speed_profile
from ..speech.providers import speech_provider, stt_provider, tts_provider, validate_speech_config
from ..speech.stt import build_stt, build_tts
from ..avatar.provider import avatar_provider
from ..avatar.manager import start_avatar
from ..assistant.agent import PersianAssistant
from ..rag.tools import _load_knowledge, _make_knowledge_tool, _rag_preload
from ..utils.logging import RoomLogHandler
from .publish import publish_room_message
try:
    from ..latency.tracker import LatencyTracker
except ImportError:
    from latency import LatencyTracker  # type: ignore

logger = logging.getLogger("sam.session.entrypoint")

async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()

    job_logger = logging.getLogger(f"sam-voice-agent.{ctx.job.id}")
    job_logger.setLevel(logging.INFO)
    room_log_handler = RoomLogHandler(lambda message: publish_room_message(ctx, message, topic="diagnostics"))
    job_logger.addHandler(room_log_handler)
    async def detach_room_log_handler() -> None:
        job_logger.removeHandler(room_log_handler)
        room_log_handler.close()
    ctx.add_shutdown_callback(detach_room_log_handler)

    fast_start_enabled = flag("AGENT_FAST_START", True)
    from ..assistant.prompt import assistant_name, sales_prompt
    job_logger.info("Assistant: name=%s (dispatch=%s) · fast_start=%s", assistant_name(), os.getenv("LIVEKIT_AGENT_NAME","sam-voice-agent"), fast_start_enabled)
    if sales_prompt():
        job_logger.info("Sales playbook loaded — the assistant sells, it does not just answer")

    latency = LatencyTracker(job_logger)
    if latency.enabled:
        job_logger.info("Latency instrumentation on: summary every %s turns", latency.report_interval or "∞")

    stt_model = os.getenv("LIVEKIT_STT_MODEL", "deepgram/nova-3")
    stt_language = os.getenv("LIVEKIT_STT_LANGUAGE", "fa")
    stt_fallback_models = [i.strip() for i in os.getenv("LIVEKIT_STT_FALLBACK","").split(",") if i.strip()]
    cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID","").strip()
    cloudflare_api_token = os.getenv("CLOUDFLARE_API_TOKEN","").strip()
    llm_model = os.getenv("CLOUDFLARE_LLM_MODEL","").strip()
    try:
        llm_max_tokens = int(os.getenv("CLOUDFLARE_LLM_MAX_TOKENS","400"))
    except ValueError as exc:
        raise RuntimeError("CLOUDFLARE_LLM_MAX_TOKENS must be a positive integer") from exc
    if not 1 <= llm_max_tokens <= 24000:
        raise RuntimeError("CLOUDFLARE_LLM_MAX_TOKENS must be between 1 and 24000")
    if not cloudflare_account_id or not cloudflare_api_token:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required for Cloudflare Workers AI")
    cloudflare_base_url = f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/ai/v1"

    livekit_tts_model = os.getenv("LIVEKIT_TTS_MODEL", "google/gemini-3.8-flash-lite-tts").strip()
    livekit_tts_voice = os.getenv("LIVEKIT_TTS_VOICE", "Charon").strip() or "Charon"
    tts_language = os.getenv("LIVEKIT_TTS_LANGUAGE", "fa").strip() or "fa"
    # Effective TTS model/voice for logs — cloudflare uses its own vars, elevenlabs مستقیم از elevenlabs.io
    cf_tts_model = os.getenv("CLOUDFLARE_TTS_MODEL", "elevenlabs/eleven-v3").strip() or "elevenlabs/eleven-v3"
    cf_tts_voice = (
        os.getenv("CLOUDFLARE_TTS_VOICE_ID", "").strip()
        or os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        or livekit_tts_voice
    ) or "JBFqnCBsd6RMkjVDRZzb"
    eleven_tts_model = (
        os.getenv("ELEVENLABS_MODEL", "").strip()
        or os.getenv("ELEVENLABS_TTS_MODEL", "").strip()
        or "eleven_flash_v2_5"
    )
    eleven_tts_voice = (
        os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        or os.getenv("ELEVEN_VOICE_ID", "").strip()
        or livekit_tts_voice
    ) or "JBFqnCBsd6RMkjVDRZzb"

    inference_conn_options = APIConnectOptions(
        max_retry=int(os.getenv("LIVEKIT_INFERENCE_MAX_RETRY","6")),
        retry_interval=float(os.getenv("LIVEKIT_INFERENCE_RETRY_INTERVAL","3.0")),
        timeout=float(os.getenv("LIVEKIT_INFERENCE_TIMEOUT","15.0")),
    )
    session_conn_options = SessionConnectOptions(
        stt_conn_options=inference_conn_options,
        tts_conn_options=inference_conn_options,
        max_unrecoverable_errors=int(os.getenv("LIVEKIT_MAX_UNRECOVERABLE_ERRORS","8")),
    )

    # STT and TTS providers can be set independently; TTS_PROVIDER overrides SPEECH_PROVIDER for TTS
    stt_prov = stt_provider()
    tts_prov = tts_provider()
    stt = build_stt(stt_prov, model=stt_model, language=stt_language, conn_options=inference_conn_options, fallback=stt_fallback_models, job_logger=job_logger)
    tts = build_tts(tts_prov, model=livekit_tts_model, voice=livekit_tts_voice, language=tts_language, conn_options=inference_conn_options, job_logger=job_logger)

    # Fallback for Cloudflare 402 (insufficient credits) → LiveKit Inference
    # Set CLOUDFLARE_TTS_FALLBACK=false to disable
    if tts_prov == "cloudflare" and os.getenv("CLOUDFLARE_TTS_FALLBACK", "true").strip().lower() not in {"0", "false", "no", "off", ""}:
        try:
            from livekit.agents.tts import FallbackAdapter

            fallback_tts = build_tts("inference", model=livekit_tts_model, voice=livekit_tts_voice, language=tts_language, conn_options=inference_conn_options, job_logger=job_logger)
            job_logger.info("Cloudflare TTS fallback enabled: primary=cloudflare/%s → fallback=inference/%s", cf_tts_model, livekit_tts_model)
            # FallbackAdapter will try primary, then fallback on failure (e.g. 402)
            tts = FallbackAdapter([tts, fallback_tts])  # type: ignore
        except Exception as e:
            job_logger.warning("Could not enable Cloudflare TTS fallback: %s (continuing without fallback)", e)

    # Human-readable labels and effective model/voice for logs
    def _label(p: str) -> str:
        return {"cloudflare": "Cloudflare", "elevenlabs": "ElevenLabs", "direct": "Direct", "inference": "Inference"}.get(p, p)

    if tts_prov == "cloudflare":
        eff_tts_model, eff_tts_voice = cf_tts_model, cf_tts_voice
    elif tts_prov == "elevenlabs":
        eff_tts_model, eff_tts_voice = eleven_tts_model, eleven_tts_voice
    else:
        eff_tts_model, eff_tts_voice = livekit_tts_model, livekit_tts_voice
    # Use effective for metrics/logs
    tts_model = eff_tts_model
    tts_voice = eff_tts_voice

    job_logger.info(
        "Voice pipeline: STT=%s/%s/%s, LLM=%s (max_tokens=%s), TTS=%s/%s voice=%s lang=%s",
        _label(stt_prov),
        stt_model, stt_language, llm_model, llm_max_tokens,
        _label(tts_prov),
        eff_tts_model, eff_tts_voice, tts_language,
    )

    # Wrap TTS for per-chunk tracking (هر تکه صدا = یک سگمنت در یک ردیف)
    # روش: هر دو مسیر synthesize (ChunkedStream) و stream (SynthesizeStream) را پشتیبانی می‌کنیم
    try:
        from livekit.agents import tts as tts_api
        from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

        class TrackedTTS(tts_api.TTS):
            def __init__(self, inner, tracker, logger):
                super().__init__(capabilities=inner.capabilities, sample_rate=inner.sample_rate, num_channels=inner.num_channels)
                self._inner = inner
                self._tracker = tracker
                self._log = logger

            def synthesize(self, text: str, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
                try:
                    self._tracker.on_tts_start(text)
                except Exception:
                    pass
                stream = self._inner.synthesize(text, conn_options=conn_options)
                orig_run = getattr(stream, "_run", None)
                if callable(orig_run):
                    async def wrapped_run(output_emitter):
                        try:
                            return await orig_run(output_emitter)
                        finally:
                            try:
                                self._tracker.on_tts_end(text)
                            except Exception:
                                pass
                    stream._run = wrapped_run  # type: ignore
                else:
                    orig_aclose = getattr(stream, "aclose", None)
                    if callable(orig_aclose):
                        orig = orig_aclose
                        async def wrapped_close(*a, **kw):
                            try:
                                return await orig(*a, **kw)
                            finally:
                                try:
                                    self._tracker.on_tts_end(text)
                                except Exception:
                                    pass
                        stream.aclose = wrapped_close  # type: ignore
                return stream

            def stream(self, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
                # streaming TTS (Inference/Google) — inner باید stream داشته باشد
                try:
                    inner_stream = self._inner.stream(conn_options=conn_options)
                except NotImplementedError:
                    # inner واقعاً streaming نیست — بگذار خطای اصلی بالا بیاید تا SDK fallback کند
                    raise
                except Exception:
                    raise
                # هر flush یک سگمنت (= یک جمله) است؛ push_text تا flush بافر می‌شود
                orig_push = getattr(inner_stream, "push_text", None)
                orig_flush = getattr(inner_stream, "flush", None)
                orig_end = getattr(inner_stream, "end_input", None)

                if callable(orig_push) and callable(orig_flush):
                    buf = {"text": "", "started": False}

                    def tracked_push(token: str, *a, **kw):
                        if token:
                            if not buf["started"]:
                                try:
                                    self._tracker.on_tts_start(token)
                                except Exception:
                                    pass
                                buf["started"] = True
                            buf["text"] += token
                        return orig_push(token, *a, **kw)

                    def tracked_flush(*a, **kw):
                        txt = buf["text"].strip()
                        if txt and buf["started"]:
                            try:
                                self._tracker.on_tts_end(txt)
                            except Exception:
                                pass
                        buf["text"] = ""
                        buf["started"] = False
                        return orig_flush(*a, **kw)

                    def tracked_end(*a, **kw):
                        # اگر flush نشده باقی مانده، همین‌جا ببند
                        txt = buf["text"].strip()
                        if txt and buf["started"]:
                            try:
                                self._tracker.on_tts_end(txt)
                            except Exception:
                                pass
                            buf["text"] = ""
                            buf["started"] = False
                        if callable(orig_end):
                            return orig_end(*a, **kw)

                    inner_stream.push_text = tracked_push  # type: ignore[method-assign]
                    inner_stream.flush = tracked_flush  # type: ignore[method-assign]
                    if callable(orig_end):
                        inner_stream.end_input = tracked_end  # type: ignore[method-assign]

                return inner_stream

            def __getattr__(self, name):
                return getattr(self._inner, name)

        tts = TrackedTTS(tts, latency, job_logger)
        job_logger.info("TTS tracking enabled: هر تکه صدا به صورت سگمنت در گانت ثبت می‌شود")
    except Exception as e:
        job_logger.warning("TTS tracking wrap failed: %s", e)

    turn_handling = speed_profile(job_logger)
    # Use effective model for streaming log
    if tts_prov == "cloudflare":
        streaming_desc = "Cloudflare eleven-v3 (via StreamAdapter)"
    elif tts_prov == "elevenlabs":
        streaming_desc = f"ElevenLabs {eleven_tts_model} (native streaming)"
    else:
        streaming_desc = "GeminiTTS via SDK StreamAdapter (sentence-level)" if not tts.capabilities.streaming else "native streaming"
    job_logger.info("Streaming: STT=%s (streaming=%s) · LLM=%s streaming · TTS=%s (%s) · turn_handling=%s · FAST_START=%s",
        stt_model, getattr(stt.capabilities,"streaming","?"), llm_model, eff_tts_model,
        streaming_desc,
        json.dumps(turn_handling, ensure_ascii=False) if turn_handling else "SDK defaults", fast_start_enabled)

    extra_body = llm_request_body(llm_max_tokens, job_logger)

    session = AgentSession(
        stt=stt,
        llm=openai.LLM(model=llm_model, api_key=cloudflare_api_token, base_url=cloudflare_base_url, extra_body=extra_body),
        tts=tts,
        conn_options=session_conn_options,
        **({"turn_handling": turn_handling} if turn_handling else {}),
    )

    av_provider = avatar_provider()
    if av_provider == "none":
        job_logger.info("Avatar disabled (AVATAR_ENABLED=%s, AVATAR_PROVIDER=%s); using direct audio", os.getenv("AVATAR_ENABLED","false"), os.getenv("AVATAR_PROVIDER","spatius"))
    avatar = await start_avatar(av_provider, session, ctx.room, job_logger)

    async def publish_user_transcript(event) -> None:
        text = (event.transcript or "").strip()
        if text:
            await publish_room_message(ctx, {"type":"user_transcript","text":text,"final":event.is_final})

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        asyncio.create_task(publish_user_transcript(event))
        try:
            text = (getattr(event, "transcript", "") or "").strip()
            is_final = bool(getattr(event, "is_final", False))
            if text:
                # اگر نوبت جدید شروع شده، turn_start نداشتیم — اولین interim همان شروع نوبت است
                if latency._turn_start_ts is None or (latency._stt_last_ts is None and not latency._stt_tokens):
                    try:
                        latency.mark_turn_start()
                    except Exception:
                        pass
                latency.on_stt_token(text, is_final=is_final)
        except Exception:
            pass

    tts_requests = {"turn": 0}
    @session.on("metrics_collected")
    def on_metrics_collected(event) -> None:
        if getattr(event.metrics,"type","") == "tts_metrics":
            tts_requests["turn"] += 1

    rate_limit_hits = {"count":0,"hinted":False}
    @session.on("error")
    def on_session_error(event) -> None:
        error = event.error
        status = getattr(error,"status_code",None)
        body_str = str(getattr(error, "body", "") or str(error))
        # ارور 400 معروف Cloudflare وقتی ابزار (function calling) فرستاده می‌شود
        if status == 400 and "array not in string" in body_str:
            job_logger.error("LLM 400: Cloudflare gpt-oss-120b ابزار را نمی‌پذیرد (array not in string). فیکس: .env → RAG_PRELOAD=true و RAG_TOOL_ENABLED=false (یا خالی) بگذار و ری‌استارت کن. موقتاً بدون RAG جواب می‌دهد.")
            return
        if status == 429:
            rate_limit_hits["count"] += 1
            if not rate_limit_hits["hinted"] and rate_limit_hits["count"] >= 4:
                rate_limit_hits["hinted"]=True
                job_logger.error("LiveKit Inference still 429 after %d rejections. Run python scripts/check_inference.py", rate_limit_hits["count"])
            else:
                job_logger.warning("LiveKit Inference 429 on %s (attempt %d, retrying)", event.source, rate_limit_hits["count"])
            return
        if status == 402:
            # Cloudflare unified billing for provider models (elevenlabs)
            job_logger.error("Cloudflare TTS 402: %s — unified billing credits exhausted. Add credits at AI Gateway dashboard or set TTS_PROVIDER=inference to fallback. (CLOUDFLARE_TTS_FALLBACK=true enables auto fallback)", error)
            return
        job_logger.error("AgentSession %s error: %s", event.source, error)

    async def publish_latency_msg() -> None:
        await publish_room_message(ctx, {"type":"latency", **latency.as_dict()}, topic="diagnostics")
    async def publish_assistant_reply_msg(text: str) -> None:
        await publish_room_message(ctx, {"type":"assistant_reply","text":text})

    knowledge_index, knowledge_config = _load_knowledge(job_logger)
    tool_timings: dict[str,float] = {}
    knowledge_tool = _make_knowledge_tool(knowledge_index, knowledge_config, job_logger, tool_timings) if knowledge_index is not None else None

    @session.on("conversation_item_added")
    def on_conversation_item_added(event) -> None:
        item = event.item
        role = getattr(item,"role",None)
        if role == "user":
            text = (getattr(item,"text_content","") or "").strip()
            if text:
                job_logger.info("User turn committed (%d chars)", len(text))
                # برای Cloudflare: اگر ابزار خاموش است، حتی بدون RAG_PRELOAD هم preload را امتحان کن
                rag_tool_enabled_voice = os.getenv("RAG_TOOL_ENABLED", "false").strip().lower() in {"1","true","yes","on"}
                use_preload_voice = os.getenv("RAG_PRELOAD","false").strip().lower() in {"1","true","yes","on"} or not rag_tool_enabled_voice
                if knowledge_index is not None and use_preload_voice:
                    try:
                        preload_ctx = _rag_preload(text, knowledge_index, knowledge_config, job_logger, tool_timings)
                        if preload_ctx and hasattr(session,"chat_ctx") and session.chat_ctx is not None:
                            try:
                                session.chat_ctx.add_message(role="system", content=f"دانش مرتبط (از پایگاه شرکت):\n{preload_ctx}")
                                job_logger.info("RAG voice preload injected (%d chars)", len(preload_ctx))
                            except Exception as e:
                                job_logger.warning("RAG chat_ctx inject failed: %s", e)
                    except Exception as e:
                                job_logger.warning("RAG voice preload failed: %s", e)
            # اگر STT interim قبلاً جمع شده، turn_start را ریست نکن — وگرنه stt_tokens پاک می‌شود و گانت خالی می‌ماند
            if latency._turn_start_ts is None:
                try:
                    latency.mark_turn_start()
                except Exception:
                    pass
            latency.note_user_turn(getattr(item,"metrics",None))
        elif role == "assistant":
            text = (getattr(item,"text_content","") or "").strip()
            job_logger.info("LLM produced assistant text (%d chars)", len(text))
            if tts_requests["turn"]:
                tool_timings["tts_requests"]=float(tts_requests["turn"])
            latency.record_turn(getattr(item,"metrics",None), reply_text=text, interrupted=bool(getattr(item,"interrupted",False)), stt_model=stt_model, llm_model=llm_model, tts_model=tts_model, tool_ms=dict(tool_timings))
            tool_timings.clear()
            tts_requests["turn"]=0
            asyncio.create_task(publish_latency_msg())
            if text:
                asyncio.create_task(publish_assistant_reply_msg(text))

    @session.on("agent_state_changed")
    def on_agent_state_changed(event) -> None:
        job_logger.info("Assistant state: %s -> %s", event.old_state, event.new_state)

    async def respond_to_text(text: str, sender: str) -> None:
        job_logger.info("Text chat input from %s (%d chars)", sender, len(text))
        try:
            latency.mark_turn_start()
        except Exception:
            pass
        try:
            session.interrupt()
            # اگر ابزار خاموش است (حالت امن Cloudflare) حتی با RAG_PRELOAD=false هم preload کن
            rag_tool_enabled = os.getenv("RAG_TOOL_ENABLED", "false").strip().lower() in {"1","true","yes","on"}
            use_preload = os.getenv("RAG_PRELOAD","false").strip().lower() in {"1","true","yes","on"} or not rag_tool_enabled
            if knowledge_index is not None and use_preload:
                preload_ctx = _rag_preload(text, knowledge_index, knowledge_config, job_logger, tool_timings)
                if preload_ctx:
                    handle = session.generate_reply(user_input=text, instructions=f"دانش مرتبط از پایگاه شرکت (فقط از همین استفاده کن):\n{preload_ctx}")
                else:
                    handle = session.generate_reply(user_input=text)
            else:
                handle = session.generate_reply(user_input=text)
            await handle
            if handle.exception():
                exc = handle.exception()
                body = str(getattr(exc, "body", "") or str(exc))
                if "array not in string" in body:
                    job_logger.warning("Text reply با ابزار شکست خورد — یک بار بدون ابزار تلاش می‌کنم")
                    retry = session.generate_reply(user_input=text)
                    await retry
                    if retry.exception():
                        job_logger.error("Text chat retry هم شکست: %s", retry.exception())
                    return
                job_logger.error("Text chat reply failed: %s", exc)
        except Exception:
            job_logger.exception("Could not generate reply to text chat")

    def on_room_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic != "chat-input": return
        try:
            message = json.loads(packet.data.decode("utf-8"))
            if message.get("type") != "chat_input": return
            text = str(message.get("text","")).strip()[:4000]
            if not text: return
            sender = packet.participant.identity if packet.participant else "unknown"
            asyncio.create_task(respond_to_text(text, sender))
        except Exception:
            job_logger.exception("Invalid text chat data packet")
    ctx.room.on("data_received", on_room_data_received)

    await session.start(agent=PersianAssistant(knowledge_tool=knowledge_tool, latency_tracker=latency), room=ctx.room, room_output_options=RoomOutputOptions(audio_enabled=avatar is None))
    job_logger.info("Agent session started and ready for voice or text input")

    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata={}
    opening_line = str(metadata.get("opening_line","")).strip()[:300]
    greeting = f"به فارسی سلام کن و به این خواسته پاسخ بده: {opening_line}" if opening_line else "به فارسی گرم و کوتاه سلام کن و بپرس امروز چطور می‌توانی کمک کنی."
    session.generate_reply(instructions=greeting)

# export server — SDK expects entrypoint_fnc (LiveKit Agents >=1.0)
try:
    server = agents.WorkerOptions(entrypoint_fnc=entrypoint, agent_name=os.getenv("LIVEKIT_AGENT_NAME", "sam-voice-agent"))
except TypeError:
    # fallback for very old SDK that used `entrypoint`
    server = agents.WorkerOptions(entrypoint=entrypoint, agent_name=os.getenv("LIVEKIT_AGENT_NAME", "sam-voice-agent"))  # type: ignore[arg-type]
