# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، LLM از Cloudflare Workers AI، STT از LiveKit Inference، گفتار فارسی از Microsoft Edge Neural TTS (`edge-tts`) و آواتار زنده‌ی Spatius که در مرورگر با AvatarKit رندر می‌شود. صدای پیش‌فرض `fa-IR-DilaraNeural` است و می‌توان صدای مردانه‌ی `fa-IR-FaridNeural` را هم انتخاب کرد.

Edge TTS به کلید API نیاز ندارد، اما برای تولید گفتار باید Agent به اینترنت و سرویس Edge TTS مایکروسافت دسترسی داشته باشد. خروجی MP3 در Agent به PCM تک‌کاناله‌ی 24 kHz تبدیل می‌شود تا با Spatius هماهنگ باشد.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- حساب Spatius با App ID، API key و Avatar ID
- پروژه‌ی LiveKit Cloud با Inference فعال و دسترسی به مدل STT
- حساب Cloudflare با دسترسی Workers AI و API Token مجاز برای اجرای مدل‌ها

## راه‌اندازی

```bash
npm install
cp .env.example .env
```

مقادیر LiveKit، Spatius و Cloudflare Workers AI را در `.env` تنظیم کنید. `SPATIUS_API_KEY` و توکن Cloudflare محرمانه‌اند و نباید در کد مرورگر یا متغیرهای `VITE_*` قرار بگیرند. `SPATIUS_APP_ID` و `SPATIUS_AVATAR_ID` برای بارگذاری AvatarKit در مرورگر استفاده می‌شوند.

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

Vite (معمولاً `http://localhost:5173`) درخواست‌های `/api` را به API محلی روی پورت 3001 پروکسی می‌کند. برای production:

```bash
npm run build
NODE_ENV=production npm start
```

## تنظیم صدا و آواتار

1. در LiveKit Cloud یک project بسازید و `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` را در `.env` قرار دهید.
2. در Spatius Studio یک App بسازید و `SPATIUS_API_KEY`, `SPATIUS_APP_ID` و `SPATIUS_AVATAR_ID` را تنظیم کنید. API key فقط در سرور و Agent می‌ماند. ناحیه به‌صورت خودکار انتخاب می‌شود؛ در صورت نیاز `SPATIUS_REGION` را تنظیم کنید. نرخ خروجی آواتار پیش‌فرض `24000` هرتز است؛ نرخ‌های مجاز `8000`, `12000`, `16000`, `24000` و `48000` هستند.
3. صدای Edge TTS را با `EDGE_TTS_VOICE` انتخاب کنید: `fa-IR-DilaraNeural` (زن، پیش‌فرض) یا `fa-IR-FaridNeural` (مرد). در صورت نیاز سرعت و زیر و بمی را با `EDGE_TTS_RATE` (مثلاً `-10%`) و `EDGE_TTS_PITCH` (مثلاً `+5Hz`) تنظیم کنید. کلید API لازم نیست.
4. در Cloudflare مقدار `CLOUDFLARE_ACCOUNT_ID` و توکن دارای مجوز Workers AI را تنظیم کنید.
5. Agent با نام `hamrah-agent` dispatch می‌شود؛ همین نام را با `LIVEKIT_AGENT_NAME` هماهنگ نگه دارید.

مدل‌های پیش‌فرض:
- STT: `deepgram/nova-3` با زبان `fa` از LiveKit Inference
- TTS: Microsoft Edge Neural با `fa-IR-DilaraNeural`
- LLM: `@cf/meta/llama-3.3-70b-instruct-fp8-fast` از Cloudflare Workers AI

Agent به LiveKit وصل می‌شود, جلسه‌ی Spatius را راه می‌اندازد و MP3 دریافتی از Edge TTS را به PCM برای همگام‌سازی حرکت آواتار تبدیل می‌کند. فرانت‌اند با `@spatius/avatarkit-rtc` ترک حرکت LiveKit را دریافت می‌کند و AvatarKit آواتار را در مرورگر رندر می‌کند.

### عیب‌یابی Opus در ویندوز

Spatius برای فرستادن صدای آواتار به کدگذار Ogg Opus و کتابخانه‌ی بومی `libopus` نیاز دارد. نصب `opuslib-next` به‌تنهایی DLL را نصب نمی‌کند. اگر `ctypes.util.find_library('opus')` مقدار `None` داد، یک DLL x64 به نام `opus.dll` در مسیری که در `PATH` است قرار دهید و در همان PowerShell بررسی کنید:

```powershell
python -c "import ctypes.util; print(ctypes.util.find_library('opus')); import opuslib_next; print('Opus OK')"
```

این نیازمندی مربوط به Spatius است و با انتخاب Edge TTS حذف نمی‌شود.

چت متنی مستقیم نیز در دسترس است. اگر اجازه‌ی میکروفون رد شود یا ورودی صوتی در دسترس نباشد، کاربر می‌تواند متن بفرستد.

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room به‌همراه شناسه‌های عمومی Spatius

`agent.py` از LiveKit Inference برای STT، Edge Neural TTS برای گفتار، Cloudflare Workers AI برای LLM و پلاگین رسمی `livekit-plugins-spatius` برای آواتار استفاده می‌کند. متن تشخیص‌داده‌شده و پاسخ Agent به‌صورت data packet به رابط فرستاده می‌شوند.
