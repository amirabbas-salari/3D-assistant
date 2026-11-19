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

> **دستور اجرا:** `python agent.py dev` بزنید. اگر LiveKit CLI را نصب کرده‌اید، `lk agent dev` روی این پروژه کار **نمی‌کند** — چون `package.json` در ریشه وجود دارد، `lk` پروژه را Node.js می‌شناسد و حتی با آرگومان `agent.py` هم آن را با `node` اجرا می‌کند. راه‌حل در بخش «خطای `no agent entrypoint found`» آمده است.

در ترمینال دیگر رابط وب و API را اجرا کنید:

```bash
npm run dev
```

Vite (معمولاً `http://localhost:5173`) درخواست‌های `/api` را به API محلی روی پورت 3001 پروکسی می‌کند. برای production:

```bash
npm run build
NODE_ENV=production npm start
```

## خطای `no agent entrypoint found`

```
PS> lk agent dev
no agent entrypoint found, checked:
- main.ts
- src/main.js
- src/main.ts
- src/main.js
```

این پیام می‌گوید `lk` پروژه را **Node.js** تشخیص داده و فقط دنبال entrypointهای جاوااسکریپت گشته است. مشکل از `.env`، وابستگی‌ها یا کد پایتون نیست.

### علت دقیق

LiveKit CLI (`lk`) برای انتخاب runtime اول نوع پروژه را تشخیص می‌دهد. در `pkg/agentfs/detect.go` این ترتیب است و **اولین تطابق برنده می‌شود**:

```go
if util.FileExists(dir, "package.json") { return ProjectTypeNode }
if util.FileExists(dir, "uv.lock")      { return ProjectTypePythonUV }
if util.FileExists(dir, "requirements.txt") { return ProjectTypePythonPip }
if util.FileExists(dir, "pyproject.toml")   { return ProjectTypePythonPip }
```

این پروژه **هر دو** مانیفست را در ریشه دارد: `package.json` (رابط وب و API) و `requirements.txt` (ایجنت پایتون). چون `package.json` اول بررسی می‌شود، نوع پروژه `Node` می‌شود و فهرست entrypointهای جستجو‌شده هم `main.ts` / `src/main.js` می‌شود — همان‌هایی که در پیام خطا می‌بینید. `agent.py` حتی بررسی هم نمی‌شود.

### 🔴 آرگومان `agent.py` کافی نیست

این نکته مهم است و مستندات صریحاً آن را نمی‌گوید: دادن entrypoint دستی مشکل را حل نمی‌کند. با `lk agent dev agent.py`، تابع `findEntrypoint` فایل را پیدا می‌کند (چون بررسی `os.Stat` روی `.py` هم کار می‌کند)، ولی `buildAgentCommand` هنوز بر اساس `ProjectType` تصمیم می‌گیرد:

```go
if cfg.ProjectType.IsNode() {
    // node [--experimental-strip-types] ENTRYPOINT ...
    return nodeBin, args, nil
}
```

یعنی فایل پایتون به `node` داده می‌شود و با خطای اجرای Node شکست می‌خورد. **آرگومان، تشخیص نوع پروژه را عوض نمی‌کند.**

### راه‌حل درست

`package.json` را یک لحظه از مسیر تشخیص کنار بگذارید، دستور را اجرا کنید، و بعد برگردانید:

```powershell
Rename-Item package.json package.json.bak
lk agent dev agent.py
Rename-Item package.json.bak package.json
```

حالا `requirements.txt` پیدا می‌شود، نوع پروژه `PythonPip` می‌شود و CLI با `<python> -m livekit.agents dev agent.py` اجرا می‌کند — همان چیزی که انتظار دارید.

اگر این جابه‌جایی را نمی‌خواهید، `python agent.py dev` دقیقاً همان کار را می‌کند:

```powershell
python agent.py dev
```

این روش کاملاً سالم است و مشکل نوع پروژه هم ندارد، ولی SDK پایتون نسخه‌ی ۱.۸.۱۲ آن را منسوخ اعلام می‌کند و hot-reload ندارد:

```
WARNING: dev mode is deprecated and will be removed in a future release; use `lk agent dev` instead
WARNING: in-process auto-reload has been removed from the Python CLI; use `lk agent dev` for hot-reload
```

پس تا وقتی این پروژه هم `package.json` دارد، `python agent.py dev` ساده‌ترین گزینه است؛ اگر hot-reload می‌خواهید، جابه‌جایی موقت `package.json` لازم است.

### کامنت انتهای خط در `.env`

این خط کاملاً درست است و هر دو خواننده (python-dotenv در ایجنت و godotenv در `lk`) هم درست می‌خوانندش:

```env
LIVEKIT_URL="wss://horno-avatar-as3z5jer.livekit.cloud" # a2
```

قاعده این است:

- **مقدار داخل کوتیشن**: با کوتیشن بسته می‌شود و هر چیزی بعد از آن (مثل `# a2`) دور ریخته می‌شود.
- **مقدار بدون کوتیشن**: یک `#` که قبلش فاصله باشد، شروع کامنت است (`KEY=value123 # note` → `value123`).
- **`#` داخل کوتیشن** کامنت نیست: `KEY="pa#ssword"` مقدارش `pa#ssword` است.
- **کوتیشن بسته‌نشده** کل مقدار را خراب می‌کند، نه فقط همان خط.

پس اگر در `.env` خود `# a2` یا توضیح فارسی نوشته‌اید، مشکلی نیست و لازم نیست پاکش کنید.

### `lk agent dev agent.py` → `api-key is required`

بعد از حل مشکل entrypoint، `lk` جلوی دیگری می‌ایستد. این پیام از `resolveProject` در `cmd/lk/utils.go` می‌آید، یعنی **هیچ‌کدام** از این منابع مقدار نداشته‌اند:

1. فلگ `--project`
2. فلگ `--subdomain`
3. فلگ‌های `--url/--api-key/--api-secret` یا متغیرهای محیطی `LIVEKIT_*`
4. `--dev` (اعتبارنامه‌ی لوکال)
5. `livekit.toml`
6. پروژه‌ی پیش‌فرض تنظیم‌شده در `lk`

برخلاف خود ایجنت که `load_dotenv()` را روی `.env` صدا می‌زند، `lk` هیچ dotenvای را **در شل شما** بارگذاری نمی‌کند. فقط این دو فایل را می‌خواند:

```
.env.local
.env
```

و برای استفاده از کلید داخل فایل، شرطش این است که **هم** `LIVEKIT_API_KEY` و **هم** `LIVEKIT_API_SECRET` پر باشند. متغیرهای محیطی PowerShell بر اینها مقدم‌اند.

پس اول ببینید `.env` واقعاً چه دارد:

```powershell
python scripts/check_env.py --skip-network
```

این اسکریپت وجود فایل، خالی بودن هر کلید، جابه‌جایی احتمالی key/secret، و تعارض `.env` با `.env.local` را گزارش می‌دهد.

| علت | نشانه | راه‌حل |
| --- | --- | --- |
| `.env` ساخته نشده | `check_env.py` می‌گوید «.env وجود ندارد» | `Copy-Item .env.example .env` |
| `LIVEKIT_API_KEY=` خالی | پیام `api-key is required` | مقدار را از LiveKit Cloud → Settings → Keys بردارید |
| فقط یکی از key/secret پر است | همان پیام | هر دو لازم است |
| `.env.local` قدیمی برنده شده | `check_env.py` تعارض را نشان می‌دهد | `.env.local` را حذف یا به‌روز کنید |
| متغیر محیطی قدیمی در شل | `echo $env:LIVEKIT_API_KEY` | `Remove-Item Env:LIVEKIT_API_KEY` |

اگر نمی‌خواهید با `.env` درگیر شوید، دو راه دیگر هم هست:

**۱. کلید را مستقیم بدهید.** `--url`, `--api-key` و `--api-secret` فلگ‌های سراسری `lk` هستند، پس بعد از نام ساب‌کامند هم کار می‌کنند:

```powershell
lk agent dev agent.py --url wss://your-project.livekit.cloud --api-key APIxxxxxxxx --api-secret xxxxxxxxxxxxxxxx
```

**۲. یک بار پروژه را در `lk` ثبت کنید** تا از آن به بعد خودش پیدا شود:

```powershell
lk cloud auth
```

> **یادآوری:** `python agent.py dev` این مشکل را ندارد، چون `agent.py` خودش `.env` را با `load_dotenv()` می‌خواند. تفاوت اینجاست که `lk` و ایجنت دو مسیر جدا برای خواندن اعتبارنامه دارند.

### اگر باز هم کار نکرد

- **`lk` شناخته نمی‌شود:** LiveKit CLI جدا از SDK پایتون نصب می‌شود (`winget install LiveKit.LiveKitCLI`). نصبش اجباری نیست؛ `python agent.py dev` جایگزین کامل است.
- **`lk` پیام `could not detect project type` داد:** یعنی در آن پوشه نه `package.json` هست نه `requirements.txt`؛ از ریشه‌ی پروژه اجرا کنید.
- **هر خطای دیگری درباره‌ی اعتبارنامه یا اتصال:** `python scripts/check_env.py` را بزنید؛ وجود `.env`، خالی بودن هر کلید، جابه‌جایی key/secret، تعارض `.env.local`، کوتیشن بسته‌نشده، و پذیرش واقعی کلید توسط LiveKit را جدا گزارش می‌کند. مقادیر را دقیقاً با همان قاعده‌ی python-dotenv و godotenv می‌خواند (کامنت انتهای خط، کوتیشن، `export`).
- **`ModuleNotFoundError` برای `livekit` یا `latency`:** venv فعال نیست. با `python -c "import sys; print(sys.executable)"` مطمئن شوید از کدام مفسر استفاده می‌شود، بعد `pip install -r requirements.txt` را در همان محیط بزنید.
- **خطای `SPEECH_PROVIDER=direct requires ...`:** عمدی است؛ در حالت `direct` کلیدها از همان ابتدا بررسی می‌شوند. بخش «کلید مستقیم ارائه‌دهنده» را ببینید.
- **اجرا شد ولی اتصال برقرار نشد:** `LIVEKIT_URL`, `LIVEKIT_API_KEY` و `LIVEKIT_API_SECRET` را چک کنید؛ ایجنت برای dispatch شدن به پروژه‌ی LiveKit نیاز دارد.

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
- `شمارنده‌ی فریم بین دو نمونه بازنشانی شد` — در حالت Room، SDK برای هر نوبت یک `AvatarPlayer` تازه می‌سازد و شمارنده از صفر شروع می‌شود. این پیام خطا نیست؛ حداکثر می‌گوید تصویر تغییر کرده یا نه. قبلاً همین حالت «۰ فریم» گزارش می‌شد و شبیه خرابی به نظر می‌رسید.
- `فریم حرکت می‌رسد اما تصویر آواتار تغییر نمی‌کند` — مشکل سمت رندر است، نه شبکه. معمولاً یعنی `avatar_id` داده‌ی حرکت با `SPATIUS_AVATAR_ID` یکی نیست یا رندر متوقف شده است.

خطاهای رندر خود AvatarKit هم از طریق `controller.onError` در همان پنل لاگ با کد خطا ثبت می‌شوند؛ قبلاً این callback ثبت نمی‌شد و خطاها بی‌صدا از دست می‌رفتند.

### صدای Spatius در ویندوز

قالب پیش‌فرض `pcm_s16le` از نیاز به نصب جداگانه‌ی `libopus` روی ویندوز جلوگیری می‌کند. در صورت انتخاب `SPATIUS_AUDIO_FORMAT=ogg_opus`، باید کتابخانه‌ی بومی Opus در دسترس Python باشد؛ در غیر این صورت ارسال صدا به Spatius متوقف می‌شود و آواتار ممکن است بی‌حرکت بماند.

چت متنی مستقیم نیز در دسترس است. اگر اجازه‌ی میکروفون رد شود یا ورودی صوتی در دسترس نباشد، کاربر می‌تواند متن بفرستد.

## افزایش سرعت: پروفایل‌های آماده

اگر سرعت مهم است، لازم نیست تک‌تک متغیرها را دست بزنید. یک متغیر، سه پروفایل:

```env
AGENT_SPEED_PROFILE=fast
```

| پروفایل | endpointing | preemptive | چه زمانی |
| --- | --- | --- | --- |
| `balanced` (پیش‌فرض) | `0.3` / `2.5` s | خاموش | رفتار فعلی، بدون تغییر |
| `fast` | `0.2` / `2.0` s | LLM + TTS | **پیشنهاد شروع** — حدود ۱۰۰ تا ۴۰۰ میلی‌ثانیه در هر نوبت |
| `fastest` | `0.12` / `1.5` s | LLM + TTS | فقط با هدست؛ با مکث میان جمله پاسخ می‌دهد |

هر متغیر `AGENT_*` صریح بر پروفایل مقدم است، پس می‌توانید یک knob را جدا تنظیم کنید:

```env
AGENT_SPEED_PROFILE=fast
AGENT_MIN_ENDPOINTING_DELAY=0.25   # کمی محافظه‌کارتر از 0.2
```

### چه چیزی سریع‌تر می‌شود و چرا

**endpointing** انتظار سکوت بعد از آخرین کلمه است. با پیش‌فرض SDK (`0.3` ثانیه) ایجنت قبل از اینکه حتی به LLM درخواست بدهد این مدت صبر می‌کند؛ این تنها بخشی از تأخیر است که هیچ مدلی در آن دخیل نیست و مستقیماً کم می‌شود.

**preemptive generation** دو کار می‌کند: LLM را روی متن interim شروع می‌کند (نه متن نهایی)، و TTS را قبل از تأیید نوبت. یعنی وقتی نوبت تأیید شد، بخشی از کار قبلاً انجام شده. هزینه‌اش این است که اگر متن نهایی تغییر کند، آن کار دور ریخته می‌شود؛ برای نوبت‌های کوتاه صرفه دارد، و به همین دلیل `max_speech_duration` تعیین می‌کند بالای چند ثانیه گفتار اصلاً تلاش نشود.

### استریمینگ: از قبل روشن است

هر سه مرحله جریانی‌اند و کاری برای «روشن‌کردن» نمانده:

| مرحله | وضعیت |
| --- | --- |
| STT (Deepgram nova-3 یا گیت‌وی) | ✅ جریانی (`capabilities.streaming=True`)، با aligned transcript |
| LLM (Cloudflare Workers AI) | ✅ جریانی، token به token |
| TTS با `SPEECH_PROVIDER=inference` | ✅ جریانی |
| TTS با `SPEECH_PROVIDER=direct` (`GeminiTTS`) | ⚠️ خودش جریانی نیست، ولی SDK **خودکار** آن را در `StreamAdapter` جمله‌به‌جمله می‌پیچد |

مورد آخر مهم است: `GeminiTTS` مقدار `capabilities.streaming=False` دارد، ولی `Agent.tts_node` در SDK هر TTS غیرجریانی را در یک `StreamAdapter` با `SentenceTokenizer` می‌پیچد. نتیجه این است که صدا بعد از **اولین جمله** شروع می‌شود، نه بعد از کل پاسخ؛ پس نوبت پشت سر هم قفل نمی‌شود. در لاگ استارت‌آپ هم صریح نوشته می‌شود که کدام حالت فعال است.

### وقتی گلوگاه خودِ مدل است: `reasoning_effort`

اگر در لاگ `llm_node_ttft` گلوگاه شد، تنظیم‌های بالا دیگر کمکی نمی‌کنند؛ نه endpointing نه preemptive، چون همه‌شان **قبل** از درخواست LLM هستند. علت این است که `gpt-oss` پیش از اولین توکن «فکر» می‌کند و هر توکن فکر، اولین کلمه‌ای را که می‌شنوید عقب می‌اندازد.

اندازه‌گیری واقعی روی همین پروژه، پنج نوبت متنی با همان سؤال‌های کوتاه:

| نوبت | ttft | نویسه‌ی پاسخ |
| --- | --- | --- |
| 1 | 1.56 s | 36 |
| 2 | **5.40 s** | 123 |
| 3 | 2.64 s | 14 |
| 4 | 0.99 s | 84 |
| 5 | 2.80 s | 179 |

پراکندگی از ۱ تا ۵.۴ ثانیه برای سؤال‌های هم‌اندازه یعنی مسئله طول پاسخ یا شبکه نیست؛ عمق فکر کردن مدل است. دو تنظیم این را هدف می‌گیرند:

```env
CLOUDFLARE_LLM_REASONING_EFFORT=low   # پیش‌فرض همین است: low
AGENT_FAST_START=true                 # جمله‌ی اول کوتاه تا TTS زودتر شروع شود
```

`low` فقط برای نام‌های مدل OpenAI خودکار پر می‌شود و مدل‌های `@cf/...` بیرون از آن فهرست‌اند، پس این مقدار را خودمان صریح می‌فرستیم. مقدارهای مجاز `low`/`medium`/`high` و برای خاموش‌کردن `default`. اگر Workers AI این فیلد را نادیده بگیرد، `CLOUDFLARE_LLM_REASONING_NESTED=true` شکل تودرتوی `{"reasoning":{"effort":...}}` را می‌فرستد (پیش‌فرض خاموش است، چون فیلد ناشناس می‌تواند خطای 400 بدهد).

`AGENT_FAST_START` به دستور سیستم اضافه می‌کند که پاسخ با یک جمله‌ی کوتاه شروع شود و با «بگذار فکر کنم» آغاز نشود. چون TTS در مرز اولین جمله شروع می‌شود، این کار **زمان شروع صدا** را کم می‌کند بدون اینکه طول پاسخ عوض شود.

### اندازه‌گیری مستقیم مدل، بدون حرف زدن

برای اینکه اثر بالا را در چند ثانیه ببینید (بدون اجرای ایجنت):

```powershell
python scripts/check_llm_speed.py
python scripts/check_llm_speed.py --runs 5 --prompt "سلام، حالت چطوره؟"
```

چهار حالت را با هم مقایسه می‌کند و برای هرکدام زمان **اولین توکن** را می‌دهد — همان عددی که لاگ `llm_node_ttft` نشان می‌دهد:

| حالت | اولین توکن |
| --- | --- |
| بدون تنظیم (پیش‌فرض provider) | میانگین 616 ms |
| `reasoning_effort=low` | میانگین 155 ms (−461 ms) |
| `reasoning_effort=low` + پاسخ کوتاه | میانگین 155 ms (−462 ms) |
| `reasoning_effort=medium` | میانگین 454 ms (−162 ms) |

اعداد بالا از یک سرور آزمایشی محلی با تأخیر تزریق‌شده است و فقط **درستی ابزار** را نشان می‌دهد؛ روی حساب Cloudflare خودتان عدد واقعی را می‌بینید. اگر `low` تفاوت معناداری نساخت، یعنی Workers AI فیلد را نادیده می‌گیرد: `CLOUDFLARE_LLM_REASONING_NESTED=true` را امتحان کنید، یا `CLOUDFLARE_LLM_MODEL` را به مدلی بدون مرحله‌ی فکر تغییر دهید.

### کدام گلوگاه را با چه چیزی می‌شود کم کرد

خلاصه‌ی تأخیر (بخش قبل) خودش این را می‌گوید، ولی فهرست کامل:

| گلوگاه | ابزار |
| --- | --- |
| `end_of_turn_delay` | `AGENT_SPEED_PROFILE` یا `AGENT_MIN_ENDPOINTING_DELAY` — ارزان‌ترین برد |
| `transcription_delay` | مدل/زبان STT، یا `SPEECH_PROVIDER=direct` اگر گیت‌وی کند است |
| `llm_node_ttft` | `CLOUDFLARE_LLM_REASONING_EFFORT=low` — عمق فکر مدل، نه میکروفون؛ `llm_max_tokens` بی‌اثر است |
| `llm_node_ttfs` | `AGENT_FAST_START=true` (جمله‌ی اول کوتاه) یا پاسخ کوتاه‌تر |
| `tts_node_ttfb` | مسیر TTS؛ سهم معمولاً کوچک‌ترین است |
| `playback_latency` | با آواتار روشن بزرگ می‌شود — همان مسیر D-ID |

**ترتیب کار:** اول `AGENT_SPEED_PROFILE=fast` را بگذارید و چند نوبت حرف بزنید. خط `→ گلوگاه` را ببینید. اگر باز هم `end_of_turn_delay` بود، `fastest` را امتحان کنید؛ اگر جایش را به `llm_node_ttft` داد، آن‌وقت بحث مدل است و تنظیم پایپ‌لاین دیگر کمکی نمی‌کند — سراغ `CLOUDFLARE_LLM_REASONING_EFFORT` و `scripts/check_llm_speed.py` بروید.

**اگر با چت متنی تست می‌کنید:** مراحل «تشخیص پایان» و «متن» خالی می‌مانند (`—`)، چون میکروفونی در کار نیست. این طبیعی است و یعنی پروفایل سرعت اصلاً در آن تست دخیل نبوده؛ عدد باقی‌مانده صرفاً LLM است. برای سنجش کل پایپ‌لاین باید با میکروفون حرف بزنید.

## اندازه‌گیری تأخیر: پیدا کردن گلوگاه در حد میلی‌ثانیه

هر نوبت گفتگو از چند مرحله می‌گذرد و کندترین مرحله معمولاً همانی نیست که به نظر می‌رسد. برای همین `latency.py` زمان‌بندی خود SDK را (که فقط داخل `ChatMessage.metrics` پنهان بود) به یک خط لاگ میلی‌ثانیه‌ای تبدیل می‌کند:

```
⏱ نوبت #3 | سراسری 1.85s | تشخیص پایان 445ms · متن 321ms · LLM 613ms · TTS 68.6ms | 92 نویسه
⏱ نوبت #3 کندترین مراحل: درخواست LLM ← اولین توکن 613ms · پایان گفتار ← تشخیص پایان نوبت 445ms · پایان گفتار ← متن نهایی STT 321ms
⏱ نوبت #3 سهم‌ها: پایان‌نوبت+LLM+TTS = 1.13s از 1.85s سراسری → 725ms جای دیگر
```

و هر چند نوبت یک خلاصه که خودش گلوگاه را نام می‌برد:

```
میانگین (5 نوبت):
  • پایان گفتار ← تشخیص پایان نوبت: میانگین 497ms · بدترین 714ms
  • پایان گفتار ← متن نهایی STT: میانگین 418ms · بدترین 593ms
  • درخواست LLM ← اولین توکن: میانگین 380ms · بدترین 613ms
  • اولین جمله ← اولین بایت صدا: میانگین 99.0ms · بدترین 130ms
  • سراسری (e2e): میانگین 2.18s · میانه 2.15s · p95 2.53s
  → گلوگاه: پایان گفتار ← تشخیص پایان نوبت (497ms میانگین)
```

### هر عدد یعنی چه؟

| مرحله | از کجا تا کجا | اگر کند باشد |
| --- | --- | --- |
| `end_of_turn_delay` | پایان گفتار ← تصمیم به پایان نوبت | سکوت انتظار endpointing؛ با `AGENT_MIN_ENDPOINTING_DELAY` کم می‌شود |
| `transcription_delay` | پایان گفتار ← متن نهایی STT | STT کند است یا نتیجه‌ی interim را دیر نهایی می‌کند |
| `llm_node_ttft` | درخواست ← اولین توکن LLM | مدل یا شبکه؛ `@cf/openai/gpt-oss-120b` روی Cloudflare |
| `llm_node_ttfs` | درخواست ← اولین جمله‌ی کامل به TTS | مدل دیر جمله می‌بندد؛ جمله‌های کوتاه‌تر در system prompt کمک می‌کند |
| `tts_node_ttfb` | اولین جمله ← اولین بایت صدا | TTS یا اتصال به آن؛ معمولاً کوچک‌ترین سهم |
| `playback_latency` | اولین فریم ← شروع پخش | با آواتار روشن بزرگ می‌شود (D-ID باید صدا را همگام کند) |
| `e2e_latency` | پایان گفتار ← شروع صدای Agent | جمعِ حس‌شده‌ی کاربر؛ ملاک نهایی |

**`e2e` جمع بقیه نیست.** STT با انتظار endpointing هم‌زمان اجرا می‌شود و پخش با تولید هم‌پوشانی دارد. برای همین خط «سهم‌ها» اضافه شده: آن مقداری که بعد از کم‌کردن سه مرحله‌ی سریال باقی می‌ماند، وقتی است که در خود پایپ‌لاین می‌گذرد (زمان‌بندی، تحویل به آواتار، انتقال شبکه). این بخش با عوض‌کردن مدل یا کلید بهتر نمی‌شود، پس مهم است که از کندی ارائه‌دهنده جدا دیده شود.

### تنظیم‌ها

| متغیر | پیش‌فرض | کار |
| --- | --- | --- |
| `LATENCY_LOG` | `true` | یک خط میلی‌ثانیه‌ای برای هر نوبت |
| `LATENCY_REPORT_INTERVAL` | `5` | خلاصه هر N نوبت؛ `0` خاموش |
| `AGENT_MIN_ENDPOINTING_DELAY` | خالی (پیش‌فرض SDK: `0.3`) | حداقل سکوت بعد از آخرین گفتار قبل از پاسخ |
| `AGENT_MAX_ENDPOINTING_DELAY` | خالی (پیش‌فرض SDK: `2.5`) | حداکثر انتظار برای تشخیص پایان نوبت |
| `AGENT_PREEMPTIVE_TTS` | خالی (خاموش) | TTS را قبل از تأیید نوبت شروع می‌کند |

**برای شروع سریع، بخش «افزایش سرعت: پروفایل‌های آماده» را ببینید؛ همان تنظیم‌ها را یک‌جا اعمال می‌کند.**

**اعداد را قبل از تغییر اندازه بگیرید.** `AGENT_MIN_ENDPOINTING_DELAY=0.2` پاسخ را حدود ۱۰۰ میلی‌ثانیه جلو می‌اندازد، ولی روی کاربری که میان جمله مکث می‌کند زودتر می‌پرد و نوبت را قطع می‌کند. `AGENT_PREEMPTIVE_TTS=1` انتظار جمله‌ی اول را پنهان می‌کند ولی صدا را برای متنی می‌سازد که ممکن است هرگز خوانده نشود (هزینه‌ی TTS بیشتر). هر دو پیش‌فرض خاموش‌اند تا رفتار فعلی تغییر نکند.

### بدون ترمینال: پنل مرورگر

همین اعداد روی topic تشخیصی `diagnostics` هم منتشر می‌شوند و در بخش «اطلاعات اجرا» به‌صورت نوارهای افقی با مقدار میلی‌ثانیه دیده می‌شوند. خط لاگ هر نوبت هم در «گزارش نشست» ثبت می‌شود، پس با یک کلیک قابل کپی است.

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها؛ شامل `avatarEnabled`, `avatarProvider`, `didConfigured` و `spatiusConfigured`
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room به‌همراه `avatarProvider` و شناسه‌های عمومی Spatius
- `POST /api/sessions/cleanup` — بستن roomهای رهاشده با پیشوند `hamrah-` تا اتصال‌های STT/TTS آزاد شوند

زمان‌بندی نوبت‌ها از طریق data packet با `type: "latency"` روی topic `diagnostics` هم فرستاده می‌شود؛ شکل آن `{turns, averages, last}` است و `last.stages` همان مراحل جدول بالا با مقدار میلی‌ثانیه.

`agent.py` از LiveKit Inference برای STT و TTS، Cloudflare Workers AI برای LLM و پلاگین رسمی `livekit-plugins-spatius` برای آواتار استفاده می‌کند. متن تشخیص‌داده‌شده و پاسخ Agent به‌صورت data packet به رابط فرستاده می‌شوند.
