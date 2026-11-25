# Tavus فارسی — چرا انگلیسی می‌شود و چطور درست کنیم

> **علامت:** `AVATAR_ENABLED=true` ولی آواتار انگلیسی صحبت می‌کند، در حالی که LiveKit/سام فارسی است.

## علت

Tavus یک **pipeline جدا** دارد (LLM + TTS خودش). اگر Persona را با پیش‌فرض `languages=["en"]` و `system_prompt` انگلیسی بسازید، Tavus همیشه انگلیسی می‌ماند — حتی اگر `LIVEKIT_TTS_LANGUAGE=fa` یا `sales_playbook.md` فارسی باشد. آن‌ها به Tavus نمی‌رسند.

## دو راه حل

### راه A — Persona را در داشبورد فارسی کنید (پیشنهادی، پایدار)

1. بروید https://maker.tavus.io → Personas (یا Pals) → **Edit / Create**
2. `system_prompt` را فارسی بگذارید — می‌توانید از `prompts/sales_playbook.md` کپی کنید (خلاصه + لحن محاوره‌ای متعادل):
   ```
   تو سام هستی — مشاور ارشد دیجیتال مارکتینگ و طراحی سایت ما. همیشه فارسیِ محاوره‌ایِ متعادل حرف بزن (ببینید/می‌دونید/بذارید)،
   انگلیسی ممنوع مگر کاربر صریحاً بخواهد. کارت فروش خدمات است نه آموزش رایگان. هر جواب ۱-۲ جمله کوتاه (۶-۱۲ کلمه) + ۱ سوال کوتاه، جمعاً زیر ۳۵ کلمه.
   ```
3. `languages` را در Persona روی `fa` (یا اگر fa رد شد، خالی بگذارید و فقط prompt را فارسی کنید)
4. TTS: ترجیحاً `ElevenLabs` با صدای چندزبانه (چون `tavus-auto` لیست 42 زبانش `fa` ندارد) — یا `tavus-auto` با صدای خنثی
5. ذخیره کنید — `persona_id` (یا `pal_id`) جدید را در `.env` بگذارید:
   ```env
   TAVUS_PERSONA_ID=p_xxx
   TAVUS_REPLICA_ID=r_xxx
   ```

### راه B — هر conversation را از env override کنید (سریع، بدون ساخت Persona جدید)

`.env` را اینطور پر کنید — نیاز به تغییر Persona نیست، هر تماس Daily با این‌ها ساخته می‌شود:

```env
TAVUS_API_KEY=...
TAVUS_REPLICA_ID=r_...
TAVUS_PERSONA_ID=p_...
# زبان شروع — اولین زبان، زبان greeting است
TAVUS_LANGUAGES=fa
# greeting فارسی
TAVUS_GREETING=سلام! من سام هستم، مشاور دیجیتال مارکتینگ شما — چطور می‌تونم کمکتون کنم؟
# context فارسی (system_prompt کوتاه برای همین conversation)
TAVUS_CONTEXT=تو سام هستی، مشاور فارسیِ محاوره‌ایِ متعادل. انگلیسی ممنوع. کارت معرفی خدمات شرکت (طراحی سایت، سئو، تبلیغات) و دعوت نرم به همکاری است. هر جواب زیر ۳۵ کلمه.
```

سرور را ری‌استارت کنید (`npm run dev` یا `docker compose ... up --build`) و `/api/health` را چک کنید:

```bash
curl http://localhost:3001/api/health | jq .tavusLanguages,.tavusGreeting,.hint
# باید tavusLanguages: ["fa"] و hint خالی باشد
```

مرورگر: `POST /api/tavus/conversation` حالا با `languages: ["fa"]` می‌سازد — در لاگ API ببینید.

## اگر باز هم انگلیسی ماند

| چک | کار |
|---|---|
| Persona قدیمی انگلیسی هنوز ست است | `TAVUS_PERSONA_ID` را به persona فارسی عوض کنید |
| `fa` را Tavus رد می‌کند (400) | `TAVUS_LANGUAGES` را خالی بگذارید (`# TAVUS_LANGUAGES=fa` کامنت) — فقط Persona مهم است؛ یا `TAVUS_PROPERTIES='{"languages":["en"]}'` با context فارسی امتحان کنید |
| Replica صدای انگلیسی دارد | Replica با صدای فارسی بسازید (Phoenix face با语音 فارسی) یا TTS را به `external_voice_id` ElevenLabs فارسی سوییچ کنید |
| LiveKit خودش انگلیسی است | وقتی `AVATAR_ENABLED=true`، صدا از **Tavus** می‌آید نه LiveKit — `LIVEKIT_TTS_*` اثری ندارد. برای تست، `AVATAR_ENABLED=false` کنید تا صدای LiveKit (Charon/fa) را بشنوید |
| می‌خواهید کلاً فارسی بدون Tavus | `AVATAR_ENABLED=false` — صدا مستقیم از LiveKit/Carton فارسی می‌آید، Tavus خاموش |

## غیرفعال کردن Tavus (fallback)

اگر فقط صدای فارسی می‌خواهید و آواتار لازم نیست:

```env
AVATAR_ENABLED=false
```

سرور/ایجنت را ری‌استارت کنید. آواتار ویدیویی پنهان می‌شود، صدا از `LIVEKIT_TTS_VOICE=Charon` فارسی می‌آید، و `/api/health` باید `avatarEnabled:false` نشان دهد.

## تست سریع

```bash
# 1) health
curl -s http://localhost:3001/api/health | jq .avatarEnabled,.avatarProvider,.tavusConfigured,.tavusLanguages,.tavusHints

# 2) ساخت conversation دستی
curl -X POST http://localhost:3001/api/tavus/conversation -H 'Content-Type: application/json' -d '{"conversation_name":"test-fa"}' | jq

# 3) اگر انگلیسی بود: لاگ API را ببینید — body ارسالی به Tavus شامل languages/greeting/context هست یا نه
```

## فایل‌های مرتبط

- `apps/api/src/routes/tavus.js` — خواندن `TAVUS_LANGUAGES/GREETING/CONTEXT` و ساختن `body.properties`
- `apps/api/src/config/env.js` — `tavusLanguages()/tavusHints()`
- `apps/api/src/routes/health.js` — نمایش `tavusLanguages/greeting/context` در `/api/health`
- `.env.example` — توضیحات فارسی

