# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، LLM از Cloudflare Workers AI، STT از LiveKit Inference، TTS از ElevenLabs و آواتار ویدیویی Simli که در همان LiveKit room حضور دارد و با صدا همگام می‌شود. مدل‌ها به‌صورت پیش‌فرض `deepgram/nova-3` با زبان `fa` برای STT، `@cf/meta/llama-3.3-70b-instruct-fp8-fast` برای LLM و `eleven_multilingual_v2` برای TTS هستند.

توکن و شناسه‌ی حساب Cloudflare، کلیدهای LiveKit، Simli و ElevenLabs فقط روی سرور/API و Agent نگهداری می‌شوند. مرورگر تنها یک توکن کوتاه‌عمرِ محدود به همان room دریافت می‌کند.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- حساب Cloudflare با دسترسی Workers AI و API Token مجاز برای اجرای مدل‌ها
- پروژه‌ی LiveKit Cloud با Inference فعال و دسترسی به مدل STT
- حساب Simli با API key و Face ID قابل استفاده
- حساب ElevenLabs با API key و یک voice ID که برای فارسی مناسب باشد

## راه‌اندازی

```bash
npm install
cp .env.example .env
```

در `.env` مقادیر LiveKit و Simli را وارد کنید و `CLOUDFLARE_ACCOUNT_ID` و `CLOUDFLARE_API_TOKEN` را تنظیم کنید. توکن Cloudflare باید مجوز اجرای Workers AI داشته باشد. LLM از API سازگار با OpenAI در Cloudflare Workers AI، STT از LiveKit Inference و TTS از ElevenLabs استفاده می‌کند. شناسه‌ها و توکن‌های Cloudflare و ElevenLabs را فقط در `.env` سمت سرور/Agent نگه دارید و هرگز در کد مرورگر قرار ندهید. سپس Agent پایتون را در یک ترمینال نصب و اجرا کنید:

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

## تنظیم Simli، ElevenLabs و صدای فارسی

1. در LiveKit Cloud یک project بسازید و `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` را در `.env` قرار دهید.
2. از حساب Simli مقدار API key و Face ID را بگیرید و در `SIMLI_API_KEY` و `SIMLI_FACE_ID` وارد کنید. در صورت نیاز برای Faceهای سازگار، `SIMLI_EMOTION_ID` اختیاری است.
3. در ElevenLabs یک API key و voice ID انتخاب کنید؛ آن‌ها را در `ELEVEN_API_KEY` و `ELEVEN_VOICE_ID` قرار دهید. voice انتخابی باید فارسی را خوب پشتیبانی کند.
4. Agent به‌صورت صریح با نام `hamrah-agent` dispatch می‌شود؛ همین نام را با `LIVEKIT_AGENT_NAME` هماهنگ نگه دارید. Agent را با `python agent.py dev` اجرا کنید.
5. مدل‌های پیش‌فرض:
   - STT: `deepgram/nova-3` با `fa` از LiveKit Inference
   - TTS: `eleven_multilingual_v2` از ElevenLabs؛ `ELEVEN_VOICE_ID` را با voice ID حساب خود تنظیم کنید.
   - LLM: `@cf/meta/llama-3.3-70b-instruct-fp8-fast` از Cloudflare Workers AI.

   برای تغییر مدل‌ها از `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`, `CLOUDFLARE_LLM_MODEL`, `ELEVEN_TTS_MODEL`, `ELEVEN_VOICE_ID` و `ELEVEN_TTS_LANGUAGE` استفاده کنید. `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` و `ELEVEN_API_KEY` را فقط در `.env` سمت سرور/Agent نگهداری کنید. نام مدل باید در حساب Cloudflare Workers AI و voice ID باید در حساب ElevenLabs در دسترس باشد.

Agent درخواست راه‌اندازی Simli را می‌فرستد و AgentSession را شروع می‌کند؛ انتظار برای ترک ویدیویی Simli در پس‌زمینه است. صفحه‌ی نمونه چت متنی مستقیم هم دارد: اگر اجازه‌ی میکروفون رد شود یا ورودی صوتی در دسترس نباشد، کاربر می‌تواند متن بفرستد؛ پاسخ متنی حتی در صورت خطای TTS در چت نمایش داده می‌شود. گزارش نشست، رخدادهای مرورگر/API و لاگ‌های Agent (از جمله خطاها و جزئیات traceback) را داخل صفحه نمایش می‌دهد؛ گزارش ممکن است شامل متن گفتگو باشد و فقط برای عیب‌یابی همین نشست است. اگر پخش خودکار مرورگر مسدود باشد، دکمه‌ی فعال‌سازی صدا را بزنید. STT پیش‌فرض `deepgram/nova-3` با زبان `fa` است (قابل تغییر با `LIVEKIT_STT_MODEL` و `LIVEKIT_STT_LANGUAGE`).

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room

`agent.py` به LiveKit وصل می‌شود، STT را از LiveKit Inference، TTS را از ElevenLabs و LLM را از Cloudflare Workers AI اجرا می‌کند و با پلاگین رسمی Simli، آواتار را به همان room اضافه می‌کند. متن تشخیص‌داده‌شده از صدای کاربر از رویداد `user_input_transcribed` دریافت و به‌صورت data packet زنده به رابط فرستاده می‌شود؛ متن‌های نهایی و متن موقتِ در حال تشخیص در پنل گفتگو نمایش داده می‌شوند.
