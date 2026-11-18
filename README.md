# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، LLM از Cloudflare Workers AI، STT و TTS از LiveKit Inference، و آواتار زنده با دو پشتیبان: **D-ID** (ویدیوی لیپ‌سینک‌شده در همان اتاق LiveKit) و **Spatius** (رندر در مرورگر با AvatarKit). TTS پیش‌فرض `google/gemini-3.8-flash-lite-tts` با صدای مرد `Charon` و زبان `fa` است.

برای LiveKit Inference نیازی به کلید API جداگانه‌ی ارائه‌دهنده‌ی TTS نیست؛ احراز هویت با اطلاعات LiveKit انجام می‌شود و مصرف از طریق LiveKit مدیریت می‌شود. مرورگر فقط شناسه‌های عمومی Spatius (App ID و Avatar ID) و یک توکن کوتاه‌عمر LiveKit محدود به همان room دریافت می‌کند.

> **حالت فعلی: آواتار خاموش است.** `AVATAR_ENABLED=false` آواتار را کامل غیرفعال می‌کند تا روی STT، LLM و TTS تمرکز شود. در این حالت Agent خودش صدای TTS را در room منتشر می‌کند و مرورگر فقط صدا و متن را نشان می‌دهد. برای برگرداندن آواتار، همان متغیر را `true` کنید و با `AVATAR_PROVIDER` پشتیبان دلخواه (`did` یا `spatius`) را انتخاب کنید.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- یا حساب D-ID با API key و یک Expressive Agent (`DID_AGENT_ID`)، یا حساب Spatius با App ID، API key و Avatar ID
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

## خاموش‌کردن موقت آواتار

برای تمرکز روی موتور گفتار، آواتار را با یک متغیر خاموش کنید:

```env
AVATAR_ENABLED=false
```

این مقدار در سه جا خوانده می‌شود و هر سه با هم هماهنگ می‌مانند:

- `agent.py` جلسه‌ی Spatius را نمی‌سازد و به‌جای آن صدای TTS خودش را در LiveKit منتشر می‌کند (`audio_enabled=True`).
- `server/index.js` دیگر برای ساخت جلسه به `SPATIUS_API_KEY`, `SPATIUS_APP_ID` و `SPATIUS_AVATAR_ID` نیاز ندارد؛ نبودشان مانع شروع جلسه نیست. مقدار `avatarEnabled` در `/api/health` گزارش می‌شود.
- رابط کاربری پنل آواتار را پنهان می‌کند و به‌جایش کارت «صدا و متن» با وضعیت ترک صوتی نشان می‌دهد. المان پخش صدای remote در هر دو حالت فعال می‌ماند، وگرنه صدای دستیار قطع می‌شود.

مزیت این حالت برای آزمایش: صدای TTS مستقیم از LiveKit پخش می‌شود و Spatius در مسیر نیست، پس هر مشکل صدا یا متن فقط می‌تواند از STT، LLM یا TTS باشد.

برای روشن‌کردن دوباره‌ی آواتار: `AVATAR_ENABLED=true` بگذارید و با `AVATAR_PROVIDER` انتخاب کنید کدام پشتیبان اجرا شود.

## آواتار D-ID (پیشنهادی)

D-ID آواتار را به‌صورت ویدیوی زنده با لیپ‌سینک در **همان اتاق LiveKit** منتشر می‌کند. یعنی STT، LLM و TTS همان مسیر قبلی می‌مانند و فقط خروجی صدا به D-ID داده می‌شود؛ همان الگویی که پلاگین رسمی `livekit-plugins-did` پیاده می‌کند.

```env
AVATAR_ENABLED=true
AVATAR_PROVIDER=did
DID_API_KEY=your_did_api_key
DID_AGENT_ID=agt_your_agent_id
DID_AUDIO_SAMPLE_RATE=24000
```

### ساختن Agent در D-ID

1. کلید API را از D-ID Studio (Account Settings) بردارید و در `DID_API_KEY` بگذارید. این کلید فقط روی سرور و Agent می‌ماند.
2. یک **Expressive Agent** بسازید؛ در API یعنی `POST https://api.d-id.com/agents` با `presenter.type = "expressive"` و یک `presenter_id` (مثلاً `public_mia_elegant@avt_TJ0Tq5`) یا آواتار اختصاصی خودتان از V3 Instant Avatar. `id` برگشتی (`agt_...`) همان `DID_AGENT_ID` است. همین کار از رابط D-ID Studio هم انجام می‌شود.
3. `AVATAR_PROVIDER=did` را ست کنید و Agent را ری‌استارت کنید. در لاگ Agent خط `D-ID avatar session started` و در پنل «اطلاعات اجرا» مقدار `avatarProvider: did` دیده می‌شود.

نکته‌های مهم:

- D-ID فقط با **Expressive Agent** روی این مسیر کار می‌کند. ویدیوی V3 Instant Avatar که با `POST /scenes` ساخته می‌شود یک فایل از پیش تولیدشده است، نه آواتار زنده، و برای گفتگوی زنده مناسب نیست.
- D-ID نرخ‌های ۱۶۰۰۰، ۲۴۰۰۰ و ۴۸۰۰۰ هرتز را می‌پذیرد؛ مقدار دیگر خودش resample می‌شود. اگر TTS شما نرخ دیگری دارد، `DID_AUDIO_SAMPLE_RATE` را برابر همان بگذارید تا تبدیل دوگانه نشود.
- مرورگر برای D-ID به `<video>` معمولی وصل می‌شود (کلاس `avatar-video`)، پس `adaptiveStream` فقط برای Spatius خاموش می‌ماند و برای D-ID روشن است.
- اگر شروع آواتار شکست بخورد، Agent فقط لاگ خطا می‌دهد و با صدای مستقیم LiveKit ادامه می‌دهد؛ گفتگو قطع نمی‌شود.
- **پلاگین آواتار باید در بالای `agent.py` import شود، نه داخل `entrypoint`.** هر پلاگین LiveKit هنگام import خودش را ثبت می‌کند و `Plugin.register_plugin()` فقط روی main thread اجازه دارد. روی ویندوز LiveKit پیش‌فرض jobها را در thread اجرا می‌کند (`JobExecutorType.THREAD`)، پس import تنبل داخل job با `RuntimeError: Plugins must be registered on the main thread` کل job را می‌کشد. به همین دلیل `livekit.plugins.did` و `livekit.plugins.spatius` در سطح ماژول و داخل `try/except ImportError` import می‌شوند؛ نبودن پکیج فقط هنگام درخواست آواتار به‌صورت پیام خطا در لاگ دیده می‌شود.

## خطای ۴۲۹ در STT و TTS (سهمیه‌ی LiveKit Inference)

روی پلن Build، LiveKit Inference از دو جا می‌تواند ۴۲۹ بدهد و پیام هر دو یکی است: **سهمیه‌ی ماهانه‌ی اعتبار (credit)** که تمام شده باشد، یا **سقف ۵ اتصال هم‌زمان STT و ۵ اتصال هم‌زمان TTS** برای هر پروژه. حالت اول با هیچ تنظیمی در کد حل نمی‌شود و راه‌حلش فقط بخش «کلید مستقیم ارائه‌دهنده» در ادامه است؛ حالت دوم با بستن نشست‌های رهاشده برطرف می‌شود. هر Agent در حال اجرا یک اتصال STT و یک اتصال TTS نگه می‌دارد، و هر نشستی که با `POST /api/session` ساخته می‌شود یک Agent جدا دارد. پس چند نشست رهاشده (تب بسته‌شده، ری‌لود صفحه، یا نشستی که با «پایان نشست» تمام نشده) سقف را پر می‌کند و هر اتصال جدید با `429 Too Many Requests` رد می‌شود. سهمیه‌ی پروژه‌های رایگان بین همه‌ی پروژه‌های همان حساب تقسیم می‌شود و در داشبورد LiveKit، بخش **Settings → Project** دیده می‌شود.

این نسخه سه کار برای همین حالت انجام می‌دهد:

- **تلاش مجدد صبورانه**: `LIVEKIT_INFERENCE_MAX_RETRY`, `LIVEKIT_INFERENCE_RETRY_INTERVAL` و `LIVEKIT_INFERENCE_TIMEOUT` مقدارهای `APIConnectOptions` را تعیین می‌کنند و همان مقدارها هم روی خود مدل‌ها و هم روی `AgentSession` (`SessionConnectOptions`) گذاشته می‌شوند. مقدار روی مدل فقط به‌عنوان hint به گیت‌وی فرستاده می‌شود؛ حلقه‌ی تلاش مجددی که واقعاً اجرا می‌شود همان است که جلسه به stream می‌دهد. `LIVEKIT_MAX_UNRECOVERABLE_ERRORS` هم تعیین می‌کند چند خطای غیرقابل‌بازیابی پشت سر هم بگذرد تا کل جلسه بسته شود (پیش‌فرض `8`؛ قبلاً `3` بود و یک burst کوتاه جلسه را می‌بست).
- **مدل جایگزین STT**: `LIVEKIT_STT_FALLBACK` فهرست جداشده با ویرگول از مدل‌های Inference است که سمت سرور امتحان می‌شوند، مثلاً `assemblyai/universal-streaming`. خالی بماند، هیچ fallback فرستاده نمی‌شود.
- **بستن نشست‌های رهاشده**: دکمه‌ی «بستن نشست‌های باز قبلی» در پنل «صدا و متن» و اندپوینت `POST /api/sessions/cleanup` همه‌ی roomهای با پیشوند `hamrah-` را پاک می‌کنند و Agentهایشان را هم می‌بندند. اگر ۴۲۹ تکرار شد، اول این دکمه را بزنید، بعد دوباره نشست را شروع کنید. همچنین `startSession` با یک قفل داخلی از دو بار کلیک هم‌زمان جلوگیری می‌کند تا در یک نشست دو Agent ساخته نشود.

اگر ۴۲۹ بعد از خالی‌شدن نشست‌ها هم ادامه داشت، سهمیه‌ی ماهانه‌ی پروژه تمام شده است؛ در داشبورد LiveKit بخش Settings → Project را ببینید، پلن را ارتقا دهید، یا با `SPEECH_PROVIDER=direct` از کلید مستقیم ارائه‌دهنده استفاده کنید (بخش بعد).

### تشخیص قطعی: کدام ۴۲۹ است؟

پیام داخل ایجنت فقط می‌گوید `429 Too Many Requests` و دلیل را پنهان می‌کند؛ «سهمیه‌ی ماه تمام شده» و «اتصال‌های هم‌زمان پر شده» هر دو همین پیام را می‌دهند. برای دیدن پاسخ خود گیت‌وی:

```bash
python scripts/check_inference.py
```

این اسکریپت با همان `.env` و همان کلیدها، همان WebSocketهایی را باز می‌کند که ایجنت باز می‌کند (STT و TTS)، و بدنه‌ی پاسخ و هدرهای سهمیه (`X-LiveKit-Inference-*`, `Retry-After`) را چاپ می‌کند.

| خروجی | معنی | کار |
| --- | --- | --- |
| `accepted` | گیت‌وی اتصال را قبول کرد | مشکل از تنظیمات ایجنت است، نه سهمیه |
| `429` با بدنه‌ی حاوی سهمیه/اعتبار | سهمیه‌ی ماهانه‌ی پلن Build تمام شده | تا ریست ماهانه صبر کنید، پلن را ارتقا دهید، یا مدل را به ارائه‌دهنده‌ی دیگری با کلید مستقیم ببرید |
| `429` بدون بدنه | اتصال‌های هم‌زمان باز پر شده‌اند | دکمه‌ی «بستن نشست‌های باز قبلی» را بزنید |
| `ClientConnectorError` | مشکل شبکه/پراکسی/DNS روی سیستم شما | اتصال خروجی به `agent-gateway.livekit.cloud` را درست کنید |

با `--connections 3` می‌توانید چند اتصال هم‌زمان باز کنید و ببینید سقف از کجا شروع می‌شود.

در خود ایجنت هم اگر ۴۲۹ بعد از چهار تلاش ادامه پیدا کند، یک بار (و فقط یک بار) پیام هشدار کامل با ارجاع به همین اسکریپت در پنل لاگ ثبت می‌شود؛ تلاش‌های قبلی فقط `warning` سطح پایین هستند تا پنل پر از خطای تکراری نشود.

## کلید مستقیم ارائه‌دهنده: عبور از سهمیه‌ی LiveKit Inference

سهمیه‌ی اعتبار LiveKit Inference سقف ماهانه دارد و وقتی تمام شود، **هر** اتصال STT و TTS با `429` و هدر `X-Livekit-Inference-Quota-Category: MaxGatewayCredits` رد می‌شود؛ نه با تنظیم `max_retry`، نه با بستن نشست‌ها، و نه با هیچ کلید ارائه‌دهنده‌ای که به Inference بدهید. LiveKit Inference راه BYOK ندارد. تنها راه، صدا زدن مستقیم API خود Deepgram و Google است:

```bash
# .env
SPEECH_PROVIDER=direct
DEEPGRAM_API_KEY=...   # console.deepgram.com → API Keys
GOOGLE_API_KEY=...     # aistudio.google.com/apikey (کلید Gemini API، نه service account)
```

با این دو خط همان دو مدل قبلی استفاده می‌شوند، فقط مسیر اتصال عوض می‌شود:

| بخش | `SPEECH_PROVIDER=inference` (پیش‌فرض) | `SPEECH_PROVIDER=direct` |
| --- | --- | --- |
| STT | `deepgram/nova-3` از گیت‌وی LiveKit | `deepgram.Nova3` مستقیم با `DEEPGRAM_API_KEY` |
| TTS | `google/gemini-3.8-flash-lite-tts` از گیت‌وی LiveKit | `google.beta.GeminiTTS` مستقیم با `GOOGLE_API_KEY` |
| LLM | Cloudflare Workers AI | بدون تغییر (`CLOUDFLARE_*`) |
| آواتار | D-ID / Spatius | بدون تغییر (`DID_*` / `SPATIUS_*`) |
| سهمیه | سقف ماهانه‌ی پلن Build | سهمیه‌ی حساب Deepgram و Google |

نکته‌ها:

- **کلید Deepgram لازم است** و Nova-3 زبان فارسی (`fa`) را پشتیبانی می‌کند، پس کیفیت STT فارسی حفظ می‌شود.
- **`GOOGLE_API_KEY` کلید Gemini API است**، نه فایل service account. اگر کلید متعلق به پروژه‌ای باشد که Gemini API در آن فعال نیست، خطای ۴۰۳/۴۰۱ در لاگ ایجنت می‌آید؛ در AI Studio فعالش کنید.
- **زبان TTS دیگر پارامتر نیست.** `GeminiTTS` پارامتر `language` ندارد و زبان را از متن تشخیص می‌دهد؛ پس `LIVEKIT_TTS_LANGUAGE` فقط روی مسیر Inference اثر دارد. صدای مرد `Charon` در هر دو مسیر یکی است.
- **نام مدل‌ها همان می‌ماند.** کد پیشوند `provider/` را حذف می‌کند (`deepgram/nova-3` → `nova-3`)، پس `LIVEKIT_STT_MODEL` و `LIVEKIT_TTS_MODEL` را لازم نیست عوض کنید.
- **بدون کلید هم کد سالم است.** تا وقتی `SPEECH_PROVIDER=direct` نگذارید، هیچ‌کدام از دو پکیج لازم نیست و پروژه مثل قبل از Inference استفاده می‌کند.
- **اگر کلید خالی باشد، خطا صریح و از همان ابتدا است:** `agent.py` هنگام بالا آمدن (import) بررسی می‌کند و با پیام `SPEECH_PROVIDER=direct requires DEEPGRAM_API_KEY, GOOGLE_API_KEY` متوقف می‌شود، پس به‌جای میکروفن مرده در وسط نشست، همان اول می‌فهمید چه کم است.
- **`python scripts/check_inference.py` در حالت `direct` به‌جای گیت‌وی، فقط وجود دو کلید را بررسی می‌کند** و می‌گوید سهمیه‌ی LiveKit دیگر دخیل نیست.

بعد از تغییر `.env`، وابستگی‌های جدید را نصب و سرور و ایجنت را ری‌استارت کنید:

```powershell
uv pip install -r requirements.txt
```

پنل «صدا و متن» در ردیف `STT / TTS` نشان می‌دهد کدام مسیر فعال است، و `/api/health` هم فیلدهای `speechProvider` و `speechConfigured` را برمی‌گرداند. اگر `speechConfigured=false` باشد، `POST /api/session` با ۵۰۳ و پیام مشخص می‌گوید چه کلیدی کم است.

## تنظیم Spatius و LiveKit Inference TTS

این بخش فقط زمانی لازم است که `AVATAR_PROVIDER=spatius` باشد.

1. در LiveKit Cloud یک project بسازید و `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` را در `.env` قرار دهید. LiveKit Inference برای TTS از همین اطلاعات استفاده می‌کند و به Google API key جداگانه نیاز ندارد.
2. در Spatius Studio یک App بسازید و `SPATIUS_API_KEY`, `SPATIUS_APP_ID` و `SPATIUS_AVATAR_ID` را تنظیم کنید. API key فقط در سرور و Agent می‌ماند. ناحیه به‌صورت خودکار انتخاب می‌شود؛ در صورت نیاز `SPATIUS_REGION` را تنظیم کنید. قالب صدای ورودی پیش‌فرض `pcm_s16le` است تا به DLL بومی Opus وابسته نباشد. اگر `ogg_opus` را انتخاب کردید، نرخ‌های مجاز `8000`, `12000`, `16000`, `24000` و `48000` هرتز هستند و سیستم باید libopus داشته باشد.
3. مدل و صدای TTS را با `LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE` و `LIVEKIT_TTS_LANGUAGE` تنظیم کنید. پیش‌فرض‌ها به‌ترتیب `google/gemini-3.8-flash-lite-tts`, `Charon` و `fa` هستند. `Charon` صدای مرد است؛ صدای قبلی `Kore` زنانه بود. صداهای مرد دیگر Gemini عبارت‌اند از `Orus`, `Fenrir`, `Puck`, `Iapetus`, `Algenib`, `Schedar` و `Achird`. این مدل LiveKit Inference زبان فارسی را پشتیبانی می‌کند.
4. در Cloudflare مقدار `CLOUDFLARE_ACCOUNT_ID` و توکن دارای مجوز Workers AI را تنظیم کنید. سقف خروجی LLM با `CLOUDFLARE_LLM_MAX_TOKENS` کنترل می‌شود و پیش‌فرض آن `8192` است؛ این مقدار صریحاً برای جلوگیری از سقف پیش‌فرض 256 توکنی Workers AI فرستاده می‌شود. برای روخوانی، Agent باید متن کامل را در پاسخ تولید کند؛ TTS فقط همان پاسخ تولیدشده را می‌خواند.
5. Agent با نام `hamrah-agent` dispatch می‌شود؛ همین نام را با `LIVEKIT_AGENT_NAME` هماهنگ نگه دارید.

مدل‌های پیش‌فرض (با `SPEECH_PROVIDER=inference`؛ با `direct` همان مدل‌ها از API مستقیم ارائه‌دهنده می‌آیند):
- STT: `deepgram/nova-3` با زبان `fa`
- TTS: `google/gemini-3.8-flash-lite-tts` با صدای مرد `Charon` و زبان `fa`
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

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها؛ شامل `avatarEnabled`, `avatarProvider`, `didConfigured` و `spatiusConfigured`
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room به‌همراه `avatarProvider` و شناسه‌های عمومی Spatius
- `POST /api/sessions/cleanup` — بستن roomهای رهاشده با پیشوند `hamrah-` تا اتصال‌های STT/TTS آزاد شوند

`agent.py` از LiveKit Inference برای STT و TTS، Cloudflare Workers AI برای LLM و پلاگین رسمی `livekit-plugins-spatius` برای آواتار استفاده می‌کند. متن تشخیص‌داده‌شده و پاسخ Agent به‌صورت data packet به رابط فرستاده می‌شوند.
