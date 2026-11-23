# گلوگاه‌های سرعت — بررسی از صفر (LiveKit Inference + Cloudflare LLM + TTS)

این فایل خلاصه بررسی کامل پایپ‌لاین صوتی سام است. هدف: کاربر می‌خواهد با **LiveKit Inference** بماند اما سرعت گاهی افت می‌کند (streaming گاهی غیرفعال).

## خلاصه پایپ‌لاین فعلی
```
Mic → STT (deepgram/nova-3 via Inference) → endpointing (turn_detection) → LLM (Cloudflare Workers AI) → TTS (google/gemini-3.8-flash via Inference) → Playback
```
هر مرحله streaming است اما در عمل چند گلوگاه دارد.

---

## گلوگاه‌های پیدا شده (به ترتیب اثر)

### 1) LLM TTFT = 70% کل تأخیر (اصلی)
- **سند:** در لاگ‌های قبلی `gpt-oss-120b` با `reasoning_effort=low` همچنان 1.0s – 5.4s TTFT داشت (scripts/check_llm_speed.py هم همین را نشان می‌دهد).
- حتی `llama-3.3-70b-fp8-fast` ~150–300ms است که از کل 800ms e2e حدود 30% است.
- **چرا گاهی streaming به نظر نمی‌رسد؟** اگر TTFT=2s باشد، TTS تا 2s بیکار است و کاربر فکر می‌کند TTS stream نیست، در حالی که مشکل LLM است.

**فیکس انجام شده:**
- هشدار خودکار اگر `CLOUDFLARE_LLM_MODEL` حاوی `gpt-oss` باشد.
- توصیه اکید: برای voice فقط `llama-3.3-70b-instruct-fp8-fast` یا `llama-3.1-8b-instruct` (TTFT ~80ms).
- `CLOUDFLARE_LLM_MAX_TOKENS=150` نگه داشته شد (پیشنهاد <200) و اگر >200 لاگ هشدار می‌دهد.
- `instructions` truncate به 7800 کاراکتر برای جلوگیری از processing اضافی.

### 2) Prompt حجیم = هر توکن ورودی هزینه
- `sales_playbook.md` = 19KB (~4500 توکن). این متن **هر نوبت** به LLM فرستاده می‌شود.
- Cloudflare Workers AI هر توکن ورودی را پردازش می‌کند → +200ms تاخیر تخمینی.

**فیکس:**
- `AGENT_COMPACT_PROMPT=true` پیش‌فرض → sales_playbook به 1800 کاراکتر truncate می‌شود + یک جمله خلاصه.
- `AGENT_SPEED_PROFILE=ultra/fastest` هم خودکار compact می‌کند.
- سخت‌گیرانه: اگر `instructions` >8000 بود truncate با `[truncated]`.

### 3) RAG تاریخچه نشت می‌کرد (Context Leakage)
- در `conversation_item_added` برای voice، `session.chat_ctx.add_message(system, preload)` انجام می‌شد و **هیچ‌وقت پاک نمی‌شد**.
- بعد از 10 نوبت، 10 پیام system (~15K توکن) در context می‌ماند → LLM هر نوبت کندتر.
- این مشابه streaming نبودن به نظر می‌رسد چون LLM دیرتر جواب می‌دهد.

**فیکس:**
- `_rag_preload_msg` نگهداری می‌شود، قبل از inject جدید پاک می‌شود، و بعد از `assistant` turn حذف می‌شود. هر نوبت context تمیز.

### 4) TTS streaming گاهی غیرفعال
- کاربر درست می‌گوید: `inference TTS` گاهی `capabilities.streaming=False` برمی‌گرداند (بسته به مدل/لود منطقه).
- اگر TTS non-streaming باشد، SDK منتظر می‌ماند تا کل جمله کامل شود → pause محسوس.
- لاگ قبلی `GeminiTTS via SDK StreamAdapter (sentence-level)` نشان می‌داد گاهی native نبود.

**فیکس:**
- اگر `tts.capabilities.streaming == False`، خودکار `StreamAdapter(sentence_tokenizer)` فعال می‌شود → همیشه جمله‌ای stream.
- `TrackedTTS` هر دو مسیر `synthesize` و `stream` را پوشش می‌دهد (PR #60).
- `tts.prewarm()` بعد از ساخت صدا زده می‌شود تا وب‌سوکت قبل از اولین نوبت باز شود (TTFB کمتر ~110ms).

### 5) SSL context بلوکه‌کننده event loop (3.2s روی Windows)
- لاگ: `create_default_context blocked for 3196ms` در `livekit/agents/cli/_legacy` و `openai.LLM` init.
- این بلوکه مستقیماً turn handling و audio را به تاخیر می‌اندازد (هشدار `event loop blocked`).

**فیکس:**
- `openai.LLM` ساخت به `await asyncio.to_thread(...)` منتقل شد → Offload از event loop.
- اگر thread شکست خورد fallback به ساخت مستقیم.

### 6) Inference retry کند
- پیش‌فرض: `max_retry=6, interval=3.0s, timeout=15s` → در صورت 429 تا 18 ثانیه retry (کاربر احساس می‌کند streaming خاموش شده).
- منطقی برای Batch، نه برای voice.

**فیکس:**
- `max_retry=4, interval=1.5s, timeout=10.0s` (تهاجمی‌تر اما مناسب voice).
- توصیه: برای Production از `SPEECH_PROVIDER=direct` با کلید Deepgram/Google استفاده کنید تا سهمیه LiveKit تمام نشود (Build plan 5 conn limit).

### 7) Endpointing vs Transcription
- `ultra` با `min_delay 0.08s` بسیار تهاجمی است (خوب برای سرعت، بد برای قطع صحبت کاربر).
- `transcription_delay` و `end_of_turn_delay` روی هم ~200ms هستند و قابل بهینه‌سازی نیستند مگر با مدل STT سریع‌تر.

---

## تغییرات این PR

| فایل | تغییر |
|---|---|
| `assistant/agent.py` | AGENT_COMPACT_PROMPT → truncate sales_playbook >2000 به 1800 |
| `session/entrypoint.py` | offload LLM SSL → to_thread، هشدار gpt-oss کند، هشدار max_tokens، StreamAdapter اجباری، prewarm TTS، inference retry tuning، RAG leak fix (remove after turn) |
| `.env.example` (قبلی) | قبلاً elevenlabs مستقیم اضافه شد |

## توصیه نهایی برای حداکثر سرعت با Inference

```env
CLOUDFLARE_LLM_MODEL=@cf/meta/llama-3.1-8b-instruct  # سریع‌ترین TTFT ~80ms
CLOUDFLARE_LLM_MAX_TOKENS=120
CLOUDFLARE_LLM_REASONING_EFFORT=low
AGENT_SPEED_PROFILE=ultra
AGENT_FAST_START=true
AGENT_COMPACT_PROMPT=true
RAG_ENABLED=false  # یا true با RAG_PRELOAD=true و TOP_K=2
LIVEKIT_INFERENCE_MAX_RETRY=4
LIVEKIT_INFERENCE_RETRY_INTERVAL=1.5
TTS_PROVIDER=inference
LIVEKIT_TTS_MODEL=google/gemini-3.8-flash-lite-tts  # یا cartesia/sonic-2 اگر inference داشت
```

اگر باز هم Inference گاهی non-streaming داد، `StreamAdapter` خودمان جبران می‌کند، اما برای حذف کامل 429 پیشنهاد `TTS_PROVIDER=elevenlabs` با `eleven_flash_v2_5` (~75ms TTFB مستقیم) است.

## اندازه‌گیری
از `scripts/check_llm_speed.py` برای TTFT واقعی و از پنل diagnostics گانت (STT→LLM→TTS هر کدام یک ردیف سگمنتی) برای e2e استفاده کنید. گلوگاه فعلی بعد از فیکس‌ها باید `llm_node_ttft` باشد؛ اگر `tts_node_ttfb` بیشترین شد، مدل TTS را عوض کنید.
