# گلوگاه‌های سرعت — بررسی از صفر (دور دوم: 2026-11-24)

> این فایل نتیجه‌ی بازبینی کامل کل پروژه از صفر (کل پایپ‌لاین، هر فایل، هر env) با ماندن روی **LiveKit Inference** است. دور اول (2026-11-23) در انتهای فایل آرشیو شده.

## پایپ‌لاین فعلی (تایید شده)
```
Mic → STT (deepgram/nova-3 via Inference, streaming) → endpointing (ultra 0.08/1.0 + preemptive) → LLM (Cloudflare @cf/meta/llama-3.3-70b-instruct-fp8-fast, max_tokens=150, reasoning low) → TTS (google/gemini-3.8-flash-lite-tts via Inference, Charon, fa) → Playback
```
`SPEECH_PROVIDER=TTS_PROVIDER=inference` ثابت است — مهاجرت به ElevenLabs/Cloudflare TTS انجام نشد (درخواست کاربر).

## گلوگاه‌های دور اول (قبلاً فیکس و مرج 974f43a)
1. LLM TTFT 70% → هشدار gpt-oss، max_tokens 150، compact prompt 19KB→1.8KB
2. RAG leak (context انباشت) → _rag_preload_msg حذف بعد هر نوبت
3. TTS non-streaming → StreamAdapter جمله‌ای
4. SSL 3.2s block → openai.LLM to_thread
5. Inference retry 18s → 4/1.5/10
6. TTS prewarm

## گلوگاه‌های جدید پیدا شده در دور دوم (کل پروژه)

### ۱) compact 1800 کاراکتر، مهم‌ترین قانون (۵-۱) را می‌بُرید ❌
- `sales_playbook.md` = 19KB، بخش `۵-۱ آنالیز ایراد+راه‌حل` از بایت ~6189 شروع می‌شد → با `len>2000 → [:1800]` کاملاً حذف می‌شد.
- نتیجه: بات حتی با قانون جدید، بدون آدرس «نمی‌دونم» می‌گفت — درخواست کاربر اجرا نمی‌شد.
- **فیکس:** حد به 3500/3300 افزایش، بخش ۵-۱ به ابتدای فایل (بخش ۰) منتقل شد، حجم کل فایل خود 19979→10958 (-45%) کوتاه شد، و مهم‌تر: `assistant/agent.py` یک `audit_core` مختصر (۷ چک سایت + ۷ چک اینستا + قانون ۳ ایراد) را **مستقل از sales_playbook و RAG** همیشه به `instructions` تزریق می‌کند. حتی اگر RAG خاموش یا compact فعال باشد، رفتار ترغیبی تضمین است.
- فایل‌ها: `prompts/sales_playbook.md` (بخش ۰ جدید), `knowledge/platform_audit.md` + `knowledge/instagram.md` (الگوی ۳ ایراد + راه‌حل شرکت), `apps/agent/src/sam/assistant/agent.py` (audit_core)

### ۲) تاریخچه‌ی مکالمه (chat_ctx) بدون سقف — TTFT خطی بالا می‌رفت 📈
- هر نوبت ۲ پیام (user+assistant) به `session.chat_ctx` اضافه می‌شد و **هیچ‌وقت trim نمی‌شد**. بعد از ۸ نوبت: 16 پیام + system (~15K توکن) هر نوبت به LLM فرستاده می‌شد → TTFT ~150ms → ~600ms.
- SDK سقف خودکار ندارد.
- **فیکس دو لایه:**
  - لایه ۱ در `assistant/agent.py:llm_node` — قبل از هر LLM call، اگر `chat_ctx.items|messages` > `AGENT_MAX_HISTORY_ITEMS` (پیش‌فرض 12 = ۶ نوبت) قدیمی‌ترین‌ها `remove()` می‌شود.
  - لایه ۲ در `session/entrypoint.py:conversation_item_added` (assistant) — بعد از هر نوبت همین trim تکرار، با حفظ پیام RAG موقت.
  - env جدید: `AGENT_MAX_HISTORY_ITEMS=12` در `.env.example` مستند شد.
- فایل‌ها: `assistant/agent.py`, `session/entrypoint.py`, `.env.example`

### ۳) RAG load بلوکه‌کننده event loop (200-500ms در startup)
- `_load_knowledge()` در `entrypoint` به صورت sync صدا زده می‌شد (Chroma read + BM25 build) و loop را بلوکه می‌کرد → اولین turn دیرتر آماده می‌شد.
- **فیکس:** `await asyncio.to_thread(_load_knowledge, job_logger)` با fallback sync. فایل: `session/entrypoint.py`

### ۴) LLM extra_body همیشه reasoning_effort می‌فرستاد — حتی برای llama
- `CLOUDFLARE_LLM_REASONING_EFFORT=low` برای `llama-3.3-70b` بی‌معنی است اما هر درخواست payload اضافی + ریسک 400 داشت.
- **فیکس:** `llm_request_body(..., model=...)` فقط برای `gpt-oss` reasoning می‌فرستد، برای llama نادیده می‌گیرد و لاگ می‌کند. فایل‌ها: `config/llm.py`, `session/entrypoint.py`

### ۵) TTS prewarm روی TrackedTTS کار نمی‌کرد
- `TrackedTTS` wrapper `prewarm` را پنهان می‌کرد؛ `hasattr(tts, "prewarm")` بعد از wrap همیشه False بود.
- **فیکس:** هر دو (`tts` و `tts._inner/_tts/tts`) چک می‌شود، اولین دارای prewarm صدا زده می‌شود. فایل: `session/entrypoint.py`

### ۶) .env.example با entrypoint ناهماهنگ بود
- `LIVEKIT_INFERENCE_MAX_RETRY=6/3.0/15` در example مانده بود در حالی که entrypoint پیش‌فرض 4/1.5/10 شده بود → کاربر با کپی example کند می‌شد.
- **فیکس:** example به 4/1.5/10 همگام شد + توضیح + `AGENT_COMPACT_PROMPT`, `AGENT_MAX_HISTORY_ITEMS` اضافه شد. فایل: `.env.example`

### ۷) عدم تمرکز فایل‌ها روی سرعت (جزئی)
- `sales_playbook` قبلاً verbose بود (۱۹KB). کوتاه به ۱۰.9KB شد (-45%) → توکن ورودی کمتر → TTFT کمتر حتی قبل از compact.
- توصیه نهایی ultra profile حفظ شد: `0.08/1.0 + preemptive + AGENT_FAST_START=true`.

## تغییرات این دور (خلاصه)

| فایل | تغییر | اثر |
|---|---|---|
| `prompts/sales_playbook.md` | بخش ۰ جدید (آنالیز ۳ ایراد) + کوتاه‌سازی 19KB→10.9KB | TTFT -~100ms + تضمین رفتار جدید |
| `knowledge/platform_audit.md` | ۷ چک سایت + الگوی جواب با عدد | RAG/ذخیره دانش فروش |
| `knowledge/instagram.md` | ۷ چک اینستا + الگوی ۳ ایراد | RAG/ذخیره |
| `apps/agent/src/sam/assistant/agent.py` | compact 3500 + audit_core تزریق همیشه + trim در llm_node | TTFT پایدار + فروش |
| `apps/agent/src/sam/config/llm.py` | model-aware reasoning | payload سبک‌تر |
| `apps/agent/src/sam/session/entrypoint.py` | prewarm fix + RAG to_thread + trim + model passthrough | startup -300ms + TTFT پایدار |
| `.env.example` | retry همگام + ۲ env جدید | DX |

## توصیه نهایی برای حداکثر سرعت (Inference ثابت)
```env
CLOUDFLARE_LLM_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast  # یا @cf/meta/llama-3.1-8b-instruct برای TTFT ~80ms
CLOUDFLARE_LLM_MAX_TOKENS=150
CLOUDFLARE_LLM_REASONING_EFFORT=low
AGENT_SPEED_PROFILE=ultra
AGENT_FAST_START=true
AGENT_COMPACT_PROMPT=true
AGENT_MAX_HISTORY_ITEMS=12
RAG_ENABLED=false  # یا true با RAG_PRELOAD=true, TOP_K=2
LIVEKIT_INFERENCE_MAX_RETRY=4
LIVEKIT_INFERENCE_RETRY_INTERVAL=1.5
LIVEKIT_INFERENCE_TIMEOUT=10.0
TTS_PROVIDER=inference
LIVEKIT_TTS_MODEL=google/gemini-3.8-flash-lite-tts
```

## آرشیو دور اول
---
# گلوگاه‌های سرعت — بررسی از صفر (LiveKit Inference + Cloudflare LLM + TTS) — 2026-11-23

## خلاصه پایپ‌لاین فعلی
```
Mic → STT (deepgram/nova-3 via Inference) → endpointing (turn_detection) → LLM (Cloudflare Workers AI) → TTS (google/gemini-3.8-flash via Inference) → Playback
```

### 1) LLM TTFT = 70% کل تأخیر
- `gpt-oss-120b` 1.0s–5.4s حتی با low. **فیکس:** هشدار gpt-oss، llm 70b-fp8-fast، max_tokens 150، truncate 7800.

### 2) Prompt حجیم 19KB→1.8KB
- هر نوبت 4500 توکن اضافه. **فیکس:** AGENT_COMPACT_PROMPT.

### 3) RAG leak
- preload هیچ‌وقت پاک نمی‌شد → 15K توکن بعد 10 نوبت. **فیکس:** _rag_preload_msg remove.

### 4) TTS streaming گاهی غیرفعال
- **فیکس:** StreamAdapter + TrackedTTS + tts.prewarm()

### 5) SSL block 3.2s
- **فیکس:** to_thread

### 6) Retry کند 6/3/15 → 18s
- **فیکس:** 4/1.5/10

### 7) Endpointing
- ultra 0.08/1.0 حفظ شد.
