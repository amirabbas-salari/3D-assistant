# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، LLM از Cloudflare Workers AI، STT از LiveKit Inference، TTS از Google Gemini و آواتار زنده‌ی Spatius که در مرورگر با AvatarKit (WebAssembly/WebGL/WebGPU) رندر می‌شود. مدل‌ها به‌صورت پیش‌فرض `deepgram/nova-3` با زبان `fa` برای STT، `@cf/meta/llama-3.3-70b-instruct-fp8-fast` برای LLM و `gemini-3.8-flash-lite-tts` برای TTS هستند.

کلید Google، Cloudflare، Spatius و LiveKit فقط در سرور/Agent نگهداری می‌شوند. مرورگر فقط شناسه‌های عمومی Spatius (App ID و Avatar ID) و یک توکن کوتاه‌عمر LiveKit محدود به همان room دریافت می‌کند.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- حساب Google AI Studio با Gemini API key و دسترسی به Gemini TTS
- حساب Spatius با App ID، API key و Avatar ID
- پروژه‌ی LiveKit Cloud با Inference فعال و دسترسی به مدل STT
- حساب Cloudflare با دسترسی Workers AI و API Token مجاز برای اجرای مدل‌ها

## راه‌اندازی

```bash
npm install
cp .env.example .env
```

مقادیر LiveKit، Spatius، Cloudflare Workers AI و Google AI Studio را در `.env` تنظیم کنید. `GOOGLE_API_KEY` و `SPATIUS_API_KEY` محرمانه‌اند و نباید در کد مرورگر یا متغیرهای `VITE_*` قرار بگیرند. `SPATIUS_APP_ID` و `SPATIUS_AVATAR_ID` برای بارگذاری AvatarKit در مرورگر استفاده می‌شوند. سپس Agent پایتون را نصب و اجرا کنید:

```bash
python -m venv .venv
source .venv/bin/activate       # ویندوز: .venv\\Scripts\\activate
pip install -r requirements.txt
python agent.py dev
```

در ترمینال دیگر رابط وب و API را اجرا کنید:

```bash
npm run dev
```

Vite (معمولاً `http://localhost:5173`) درخواست‌های `/api` را به API محلی روی پورت 3001 پروکسی می‌کند. پیکربندی Vite شامل پلاگین رسمی AvatarKit است که فایل‌های WASM را برای توسعه و build تولیدی سرو می‌کند. برای production:

```bash
npm run build
NODE_ENV=production npm start
```

## تنظیم Spatius و Gemini TTS

1. در LiveKit Cloud یک project بسازید و `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` را در `.env` قرار دهید.
2. در Spatius Studio یک App بسازید و `SPATIUS_API_KEY`, `SPATIUS_APP_ID` و `SPATIUS_AVATAR_ID` را تنظیم کنید. API key فقط در سرور و Agent می‌ماند. ناحیه به‌صورت خودکار انتخاب می‌شود؛ در صورت نیاز می‌توانید `SPATIUS_REGION` را روی `us-west`, `ap-northeast` یا `cn-beijing` تنظیم کنید. نرخ خروجی آواتار پیش‌فرض `24000` هرتز است تا با Ogg Opus سازگار باشد؛ در صورت تغییر `SPATIUS_SAMPLE_RATE` فقط از `8000`, `12000`, `16000`, `24000` یا `48000` استفاده کنید.
3. در Google AI Studio یک API key بسازید و در `GOOGLE_API_KEY` قرار دهید. مدل و voice از طریق `GOOGLE_TTS_MODEL` و `GOOGLE_TTS_VOICE` انتخاب می‌شوند؛ مقدارهای پیش‌فرض `gemini-3.8-flash-lite-tts` و `Kore` هستند. برای تغییر سبک گفتار از `GOOGLE_TTS_INSTRUCTIONS` استفاده کنید. Gemini زبان گفتار را از متن ورودی تشخیص می‌دهد؛ متن فارسی Agent باید به فارسی باقی بماند.
4. در Cloudflare مقدار `CLOUDFLARE_ACCOUNT_ID` و توکن دارای مجوز Workers AI را تنظیم کنید.
5. Agent با نام `hamrah-agent` dispatch می‌شود؛ همین نام را با `LIVEKIT_AGENT_NAME` هماهنگ نگه دارید. Agent را اجرا کنید.
6. مدل‌های پیش‌فرض:
   - STT: `deepgram/nova-3` با `fa` از LiveKit Inference
   - TTS: `gemini-3.8-flash-lite-tts` با صدای `Kore` از Google Gemini
   - LLM: `@cf/meta/llama-3.3-70b-instruct-fp8-fast` از Cloudflare Workers AI

برای تغییر مدل‌ها از `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`, `CLOUDFLARE_LLM_MODEL`, `GOOGLE_TTS_MODEL`, `GOOGLE_TTS_VOICE` و `GOOGLE_TTS_INSTRUCTIONS` استفاده کنید. Agent به LiveKit وصل می‌شود، جلسه‌ی Spatius را راه می‌اندازد و صدای Gemini را برای همگام‌سازی حرکت آواتار می‌فرستد. فرانت‌اند با `@spatius/avatarkit-rtc` ترک حرکت LiveKit را دریافت می‌کند و AvatarKit آواتار را در مرورگر رندر می‌کند؛ ترک حرکت تصویر ویدیویی عادی نیست و نباید با عنصر `<video>` نمایش داده شود. نیازمندی مرورگر شامل `RTCRtpScriptTransform` و پشتیبانی رندر WASM/WebGL یا WebGPU است.

چت متنی مستقیم نیز در دسترس است: اگر اجازه‌ی میکروفون رد شود یا ورودی صوتی در دسترس نباشد، کاربر می‌تواند متن بفرستد. گزارش نشست رخدادهای مرورگر/API و لاگ‌های Agent را برای عیب‌یابی نمایش می‌دهد؛ ممکن است شامل متن گفتگو باشد.

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room به‌همراه شناسه‌های عمومی Spatius

`agent.py` از LiveKit Inference برای STT، Google Gemini TTS از طریق Interactions API (`v1beta`) با SDK رسمی `google-genai` برای گفتار، Cloudflare Workers AI برای LLM و پلاگین رسمی `livekit-plugins-spatius` برای آواتار استفاده می‌کند. این مسیر Interactions API را به‌کار می‌برد؛ endpoint قدیمی `generateContent` برای Gemini 3.8 TTS این ساختار درخواست را قبول نمی‌کند. متن تشخیص‌داده‌شده و پاسخ Agent به‌صورت data packet به رابط فرستاده می‌شوند.
