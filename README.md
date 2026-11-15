# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، STT/TTS فارسی از LiveKit Inference، LLM از OpenRouter و آواتار ویدیویی Tavus که در همان LiveKit room حضور دارد و با صدا همگام می‌شود. STT اولیه `deepgram/nova-3` با زبان `fa` و TTS اولیه `google/gemini-3.8-flash-tts` با صدای `Kore` و زبان `fa` است. مدل زبانی با `OPENROUTER_MODEL` انتخاب می‌شود (پیش‌فرض `openrouter/auto`).

کلیدهای سرویس فقط روی سرور/API و Agent نگهداری می‌شوند. مرورگر تنها یک توکن کوتاه‌عمرِ محدود به همان room دریافت می‌کند.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- حساب LiveKit Cloud با Inference فعال
- حساب Tavus و Face/Replica قابل استفاده با LiveKit
- کلید API در OpenRouter و دسترسی به مدل انتخابی

## راه‌اندازی

```bash
npm install
cp .env.example .env
```

مقادیر LiveKit، Tavus و `OPENROUTER_API_KEY` را در `.env` وارد کنید. سپس agent پایتون را در یک ترمینال نصب و اجرا کنید:

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
   - LLM: مدل انتخابی OpenRouter؛ پیش‌فرض `openrouter/auto`. شناسه‌ی مدل‌هایی مانند `provider/model` را از فهرست OpenRouter انتخاب کنید.

   برای تغییر مدل‌ها از `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`, `LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE`, `LIVEKIT_TTS_LANGUAGE` و `OPENROUTER_MODEL` استفاده کنید. کلید OpenRouter فقط در `.env` سمت سرور/Agent نگهداری می‌شود. پشتیبانی زبان/voice و دسترسی به مدل‌ها ممکن است به حساب و مدل انتخابی وابسته باشد.

در راه‌اندازی Agent، آواتار پیش از پاسخ‌گویی منتظر join شدن Tavus می‌ماند و خروجی صوتی مستقل Agent خاموش است؛ TTS به Tavus فرستاده می‌شود تا خود Avatar Worker صدای همگام با ویدیو را منتشر کند. مرورگر ترک‌های صوتی راه‌دور را پخش می‌کند؛ اگر autoplay مسدود باشد از دکمه‌ی بلندگو یا دکمه‌ی «برای شنیدن صدا بزن» استفاده کنید. پنل گفتگو هم متن پاسخ همراه را کنار گفتار تشخیص‌داده‌شده نشان می‌دهد: اگر متن پاسخ می‌آید ولی صدا نه، LLM جواب داده و ایراد در TTS/ترک صوتی/پخش مرورگر است. خطاهای مدل با منبع `llm` یا `tts` در لاگ Agent ثبت می‌شوند. STT پیش‌فرض `deepgram/nova-3` با زبان `fa` است (قابل تغییر با `LIVEKIT_STT_MODEL` و `LIVEKIT_STT_LANGUAGE`).

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room

`agent.py` به LiveKit وصل می‌شود، STT/LLM/TTS فارسی را اجرا می‌کند و با پلاگین رسمی Tavus، آواتار را به همان room اضافه می‌کند. متن تشخیص‌داده‌شده از صدای کاربر از رویداد `user_input_transcribed` دریافت و به‌صورت data packet زنده به رابط فرستاده می‌شود؛ متن‌های نهایی و متن موقتِ در حال تشخیص در پنل گفتگو نمایش داده می‌شوند.
