# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، LLM از Cloudflare Workers AI، STT/TTS از LiveKit Inference و آواتار ویدیویی Tavus که در همان LiveKit room حضور دارد و با صدا همگام می‌شود. مدل‌ها به‌صورت پیش‌فرض `deepgram/nova-3` با زبان `fa` برای STT، `@cf/meta/llama-3.3-70b-instruct-fp8-fast` برای LLM و `google/gemini-3.8-flash-tts` با صدای `Kore` و زبان `fa` برای TTS هستند.

توکن و شناسه‌ی حساب Cloudflare، کلیدهای LiveKit و Tavus فقط روی سرور/API و Agent نگهداری می‌شوند. مرورگر تنها یک توکن کوتاه‌عمرِ محدود به همان room دریافت می‌کند.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- حساب Cloudflare با دسترسی Workers AI و API Token مجاز برای اجرای مدل‌ها
- پروژه‌ی LiveKit Cloud با Inference فعال و دسترسی به مدل‌های انتخابی STT/TTS
- حساب Tavus با PAL و Face قابل استفاده در اتصال LiveKit

## راه‌اندازی

```bash
npm install
cp .env.example .env
```

در `.env` مقادیر LiveKit و Tavus را وارد کنید و `CLOUDFLARE_ACCOUNT_ID` و `CLOUDFLARE_API_TOKEN` را تنظیم کنید. توکن Cloudflare باید مجوز اجرای Workers AI داشته باشد. LLM از API سازگار با OpenAI در Cloudflare Workers AI استفاده می‌کند؛ STT و TTS همچنان از LiveKit Inference هستند. شناسه و توکن Cloudflare را فقط در `.env` سمت سرور/Agent نگه دارید و هرگز در کد مرورگر قرار ندهید. سپس Agent پایتون را در یک ترمینال نصب و اجرا کنید:

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
4. مدل‌های پیش‌فرض:
   - STT: `deepgram/nova-3` با `fa` از LiveKit Inference
   - TTS: `google/gemini-3.8-flash-tts` با صدای `Kore` و `fa` از LiveKit Inference
   - LLM: `@cf/meta/llama-3.3-70b-instruct-fp8-fast` از Cloudflare Workers AI.

   برای تغییر مدل‌ها از `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`, `CLOUDFLARE_LLM_MODEL`, `LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE` و `LIVEKIT_TTS_LANGUAGE` استفاده کنید. `CLOUDFLARE_ACCOUNT_ID` و `CLOUDFLARE_API_TOKEN` و کلیدهای LiveKit فقط در `.env` سمت سرور/Agent نگهداری می‌شوند. نام مدل باید در حساب Cloudflare Workers AI در دسترس باشد.

Agent درخواست راه‌اندازی Tavus را می‌فرستد و AgentSession را شروع می‌کند؛ انتظار برای ترک ویدیوی Tavus در پس‌زمینه است. صفحه‌ی نمونه چت متنی مستقیم هم دارد: اگر اجازه‌ی میکروفون رد شود یا ورودی صوتی در دسترس نباشد، کاربر می‌تواند متن بفرستد؛ پاسخ متنی حتی در صورت خطای TTS در چت نمایش داده می‌شود. گزارش نشست، رخدادهای مرورگر/API و لاگ‌های Agent (از جمله خطاها و جزئیات traceback) را داخل صفحه نمایش می‌دهد؛ گزارش ممکن است شامل متن گفتگو باشد و فقط برای عیب‌یابی همین نشست است. اگر پخش خودکار مرورگر مسدود باشد، دکمه‌ی فعال‌سازی صدا را بزنید. STT پیش‌فرض `deepgram/nova-3` با زبان `fa` است (قابل تغییر با `LIVEKIT_STT_MODEL` و `LIVEKIT_STT_LANGUAGE`).

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room

`agent.py` به LiveKit وصل می‌شود، STT/TTS را از LiveKit Inference و LLM را از Cloudflare Workers AI اجرا می‌کند و با پلاگین رسمی Tavus، آواتار را به همان room اضافه می‌کند. متن تشخیص‌داده‌شده از صدای کاربر از رویداد `user_input_transcribed` دریافت و به‌صورت data packet زنده به رابط فرستاده می‌شود؛ متن‌های نهایی و متن موقتِ در حال تشخیص در پنل گفتگو نمایش داده می‌شوند.
