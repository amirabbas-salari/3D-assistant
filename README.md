# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، LLM از Cloudflare Workers AI، STT و TTS از LiveKit Inference، و آواتار زنده‌ی Spatius که در مرورگر با AvatarKit رندر می‌شود. TTS پیش‌فرض `google/gemini-3.8-flash-lite-tts` با صدای `Kore` و زبان `fa` است.

برای LiveKit Inference نیازی به کلید API جداگانه‌ی ارائه‌دهنده‌ی TTS نیست؛ احراز هویت با اطلاعات LiveKit انجام می‌شود و مصرف از طریق LiveKit مدیریت می‌شود. مرورگر فقط شناسه‌های عمومی Spatius (App ID و Avatar ID) و یک توکن کوتاه‌عمر LiveKit محدود به همان room دریافت می‌کند.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- حساب Spatius با App ID، API key و Avatar ID
- پروژه‌ی LiveKit Cloud با Inference فعال و دسترسی به مدل‌های STT/TTS
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

## تنظیم Spatius و LiveKit Inference TTS

1. در LiveKit Cloud یک project بسازید و `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` را در `.env` قرار دهید. LiveKit Inference برای TTS از همین اطلاعات استفاده می‌کند و به Google API key جداگانه نیاز ندارد.
2. در Spatius Studio یک App بسازید و `SPATIUS_API_KEY`, `SPATIUS_APP_ID` و `SPATIUS_AVATAR_ID` را تنظیم کنید. API key فقط در سرور و Agent می‌ماند. ناحیه به‌صورت خودکار انتخاب می‌شود؛ در صورت نیاز `SPATIUS_REGION` را تنظیم کنید. قالب صدای ورودی پیش‌فرض `pcm_s16le` است تا به DLL بومی Opus وابسته نباشد. اگر `ogg_opus` را انتخاب کردید، نرخ‌های مجاز `8000`, `12000`, `16000`, `24000` و `48000` هرتز هستند و سیستم باید libopus داشته باشد.
3. مدل و صدای TTS را با `LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE` و `LIVEKIT_TTS_LANGUAGE` تنظیم کنید. پیش‌فرض‌ها به‌ترتیب `google/gemini-3.8-flash-lite-tts`, `Kore` و `fa` هستند. این مدل LiveKit Inference زبان فارسی را پشتیبانی می‌کند.
4. در Cloudflare مقدار `CLOUDFLARE_ACCOUNT_ID` و توکن دارای مجوز Workers AI را تنظیم کنید. سقف خروجی LLM با `CLOUDFLARE_LLM_MAX_TOKENS` کنترل می‌شود و پیش‌فرض آن `8192` است؛ این مقدار صریحاً برای جلوگیری از سقف پیش‌فرض 256 توکنی Workers AI فرستاده می‌شود. برای روخوانی، Agent باید متن کامل را در پاسخ تولید کند؛ TTS فقط همان پاسخ تولیدشده را می‌خواند.
5. Agent با نام `hamrah-agent` dispatch می‌شود؛ همین نام را با `LIVEKIT_AGENT_NAME` هماهنگ نگه دارید.

مدل‌های پیش‌فرض:
- STT: `deepgram/nova-3` با زبان `fa` از LiveKit Inference
- TTS: `google/gemini-3.8-flash-lite-tts` با صدای `Kore` و زبان `fa` از LiveKit Inference
- LLM: `@cf/meta/llama-3.3-70b-instruct-fp8-fast` از Cloudflare Workers AI

Agent به LiveKit وصل می‌شود، STT و TTS را از LiveKit Inference می‌گیرد و جلسه‌ی Spatius را برای همگام‌سازی حرکت آواتار راه می‌اندازد. فرانت‌اند با `@spatius/avatarkit-rtc` ترک حرکت LiveKit را دریافت می‌کند و AvatarKit آواتار را در مرورگر رندر می‌کند.

### الزام `adaptiveStream: false` برای حرکت آواتار

پخش صدا از خواندن متن جداست؛ حتی وقتی همه‌چیز درست است، آواتار ممکن است صدا داشته باشد ولی لب نزند. علت رایج این است که Spatius داده‌ی حرکت را روی یک ترک ویدیویی می‌فرستد که SDK آن را در یک المان `<video>` پنهان (`display:none`) می‌گذارد. اگر `Room` با `adaptiveStream: true` ساخته شود، LiveKit نتیجه می‌گیرد «کسی این ویدیو را نمی‌بیند» و به سرور می‌گوید ترک را متوقف کند؛ در نتیجه هیچ فریم حرکتی نمی‌رسد و صورت آواتار ثابت می‌ماند، در حالی که صدا عادی پخش می‌شود.

بنابراین `src/main.jsx` اتاق را با `adaptiveStream: false` می‌سازد و ترک حرکت را بعد از اشتراک صریحاً با `publication.setEnabled(true)` فعال نگه می‌دارد. این گزینه را دوباره روشن نکنید. `dynacast` فقط روی انتشار اثر دارد و روشن می‌ماند.

### تشخیص «لب نمی‌زند»

رسیدن فریم حرکتی و دیده‌شدن حرکت، دو چیز جدا هستند. Spatius برای ساختن حرکت چند ثانیه‌ای بعد از شروع جمله شروع می‌کند، بنابراین نمونه‌برداری از ثانیه‌ی اول نتیجه‌ی منفی کاذب می‌دهد. `src/main.jsx` حالا وسط هر جمله (از ثانیه‌ی ۱٫۵) دو نمونه‌ی ۱٫۲ ثانیه‌ای می‌گیرد و هم‌زمان شمارنده‌ی فریم Spatius و تصویر رندرشده را مقایسه می‌کند:

- `آواتار در حال حرکت است` — هم فریم می‌رسد و هم تصویر عوض می‌شود.
- `در این بازه فریم حرکتی به آواتار نرسید` — شبکه/ترک مشکل دارد؛ `adaptiveStream` و وضعیت publication را بررسی کنید.
- `فریم حرکت می‌رسد اما تصویر آواتار تغییر نمی‌کند` — مشکل سمت رندر است، نه شبکه. معمولاً یعنی `avatar_id` داده‌ی حرکت با `SPATIUS_AVATAR_ID` یکی نیست یا رندر متوقف شده است.

خطاهای رندر خود AvatarKit هم از طریق `controller.onError` در همان پنل لاگ با کد خطا ثبت می‌شوند؛ قبلاً این callback ثبت نمی‌شد و خطاها بی‌صدا از دست می‌رفتند.

### صدای Spatius در ویندوز

قالب پیش‌فرض `pcm_s16le` از نیاز به نصب جداگانه‌ی `libopus` روی ویندوز جلوگیری می‌کند. در صورت انتخاب `SPATIUS_AUDIO_FORMAT=ogg_opus`، باید کتابخانه‌ی بومی Opus در دسترس Python باشد؛ در غیر این صورت ارسال صدا به Spatius متوقف می‌شود و آواتار ممکن است بی‌حرکت بماند.

چت متنی مستقیم نیز در دسترس است. اگر اجازه‌ی میکروفون رد شود یا ورودی صوتی در دسترس نباشد، کاربر می‌تواند متن بفرستد.

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room به‌همراه شناسه‌های عمومی Spatius

`agent.py` از LiveKit Inference برای STT و TTS، Cloudflare Workers AI برای LLM و پلاگین رسمی `livekit-plugins-spatius` برای آواتار استفاده می‌کند. متن تشخیص‌داده‌شده و پاسخ Agent به‌صورت data packet به رابط فرستاده می‌شوند.
