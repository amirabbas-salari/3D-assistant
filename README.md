# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، STT/LLM/TTS از LiveKit Inference و آواتار ویدیویی Tavus که در همان LiveKit room حضور دارد و با صدا همگام می‌شود. مدل‌ها به‌صورت پیش‌فرض `deepgram/nova-3` با زبان `fa` برای STT، `google/gemini-3.8-flash` برای LLM، و `google/gemini-3.8-flash-tts` با صدای `Kore` و زبان `fa` برای TTS هستند.

کلیدهای سرویس فقط روی سرور/API و Agent نگهداری می‌شوند. مرورگر تنها یک توکن کوتاه‌عمرِ محدود به همان room دریافت می‌کند.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- پروژه‌ی LiveKit Cloud با Inference فعال و دسترسی به مدل‌های انتخابی
- حساب Tavus با PAL و Face قابل استفاده در اتصال LiveKit

## راه‌اندازی

```bash
npm install
cp .env.example .env
```

مقادیر LiveKit و Tavus را در `.env` وارد کنید. برای LLM/STT/TTS از LiveKit Inference استفاده می‌شود و نیازی به کلید جداگانه‌ی OpenRouter نیست. سپس agent پایتون را در یک ترمینال نصب و اجرا کنید:

```bash
python -m venv .venv
source .venv/bin/activate       # ویندوز: .venv\\Scripts\\activate
pip install -r requirements.txt
python agent.py dev
```

در ترمینال دیگر، رابط وب و API را اجرا کنید:

```bash
npm run dev
```

Vite (معمولاً `http://localhost:5173`) درخواست‌های `/api` را به API محلی روی پورت 3001 پروکسی می‌کند. برای اجرای production، ابتدا agent را در حالت production بالا بیاورید، سپس:

```bash
npm run build
NODE_ENV=production npm start
```

## تنظیم Tavus و صدای فارسی

1. در LiveKit Cloud یک project بسازید و `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` را در `.env` قرار دهید.
2. در Tavus یک PAL بسازید که `pipeline_mode` آن `echo` و `layers.transport.transport_type` آن `livekit` باشد. شناسه‌ی PAL و API key را در `TAVUS_PAL_ID` و `TAVUS_API_KEY` بگذارید. شناسه‌ی Face/Replica را در `TAVUS_FACE_ID` تنظیم کنید.
3. Agent به‌صورت صریح با نام `hamrah-agent` dispatch می‌شود؛ همین نام را با `LIVEKIT_AGENT_NAME` هماهنگ نگه دارید. Agent را با `python agent.py dev` اجرا کنید.
4. مدل‌های فارسی پیش‌فرض:
   - STT: `deepgram/nova-3` با `fa`
   - TTS: `google/gemini-3.8-flash-tts` با صدای `Kore` و `fa`
   - LLM: `google/gemini-3.8-flash` از LiveKit Inference.

   برای تغییر مدل‌ها از `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`, `LIVEKIT_LLM_MODEL`, `LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE` و `LIVEKIT_TTS_LANGUAGE` استفاده کنید. کلیدهای LiveKit فقط در `.env` سمت سرور/Agent نگهداری می‌شوند. پشتیبانی زبان/voice و دسترسی به مدل‌ها ممکن است به حساب LiveKit و مدل انتخابی وابسته باشد.

Agent ابتدا درخواست راه‌اندازی Tavus را می‌فرستد و سپس بدون معطل‌کردن STT، AgentSession را شروع می‌کند؛ پیوستن participant و انتشار ترک ویدیوی Tavus در پس‌زمینه بررسی می‌شود. اگر شروع خود Tavus خطا بدهد، Agent با صدای مستقیم LiveKit به کار ادامه می‌دهد. وقتی Tavus بالا بیاید، TTS به Avatar Worker هدایت می‌شود تا صدا با ویدیو همگام باشد. مرورگر ترک‌های صوتی راه‌دور را پخش می‌کند؛ اگر autoplay مسدود باشد از دکمه‌ی بلندگو یا دکمه‌ی «برای شنیدن صدا بزن» استفاده کنید. پنل گفتگو هم متن پاسخ همراه را کنار گفتار تشخیص‌داده‌شده نشان می‌دهد: اگر متن پاسخ می‌آید ولی صدا نه، LLM جواب داده و ایراد در TTS/ترک صوتی/پخش مرورگر است. خطاهای مدل با منبع `llm` یا `tts` در لاگ Agent ثبت می‌شوند. STT پیش‌فرض `deepgram/nova-3` با زبان `fa` است (قابل تغییر با `LIVEKIT_STT_MODEL` و `LIVEKIT_STT_LANGUAGE`).

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room

`agent.py` به LiveKit وصل می‌شود، STT/LLM/TTS فارسی را اجرا می‌کند و با پلاگین رسمی Tavus، آواتار را به همان room اضافه می‌کند. متن تشخیص‌داده‌شده از صدای کاربر از رویداد `user_input_transcribed` دریافت و به‌صورت data packet زنده به رابط فرستاده می‌شود؛ متن‌های نهایی و متن موقتِ در حال تشخیص در پنل گفتگو نمایش داده می‌شوند.
