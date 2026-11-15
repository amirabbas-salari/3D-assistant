# همراه — دستیار صوتی و تصویری فارسی

دستیار مکالمه‌ای زنده با رابط فارسی راست‌چین، گفتار زنده از LiveKit Inference و آواتار ویدیویی Tavus که در همان LiveKit room حضور دارد و با صدا همگام می‌شود. STT اولیه `xai/stt-2` با زبان `fa` و TTS اولیه `google/gemini-3.8-flash-tts` با صدای `Kore` و زبان `fa` است؛ هر دو از LiveKit Inference فراخوانی می‌شوند. شناسه‌ی مدل‌ها و voice از `.env` قابل تغییرند.

کلیدهای سرویس فقط روی سرور/API و Agent نگهداری می‌شوند. مرورگر تنها یک توکن کوتاه‌عمرِ محدود به همان room دریافت می‌کند.

## پیش‌نیازها

- Node.js 18+
- Python 3.10+
- حساب LiveKit Cloud با Inference فعال
- حساب Tavus و Face/Replica قابل استفاده با LiveKit

## راه‌اندازی

```bash
npm install
cp .env.example .env
```

مقادیر LiveKit و Tavus را در `.env` وارد کنید. سپس agent پایتون را در یک ترمینال نصب و اجرا کنید:

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
   - STT: `xai/stt-2` با `fa`
   - TTS: `google/gemini-3.8-flash-tts` با صدای `Kore` و `fa`
   - LLM: `google/gemini-2.5-flash` با دستورالعمل فارسی

   برای تغییر مدل‌ها از `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`, `LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE`, `LIVEKIT_TTS_LANGUAGE` و `LIVEKIT_LLM_MODEL` استفاده کنید. پشتیبانی زبان/voice و در دسترس بودن مدل‌ها ممکن است با حساب یا نسخه‌ی سرویس تغییر کند؛ پیش از استفاده، مدل منتخب را در LiveKit Inference بررسی کنید. اگر Inference برای project فعال نباشد، مدل‌ها پاسخ نمی‌دهند.

با شروع گفتگو فقط میکروفون کاربر منتشر می‌شود؛ تصویر همراه از شرکت‌کننده‌ی ویدیویی Tavus می‌آید. مرورگر برای میکروفون اجازه می‌خواهد.

## API

- `GET /api/health` — وضعیت پیکربندی، بدون افشای رازها
- `POST /api/session` — ساخت LiveKit room، dispatch کردن Agent و برگرداندن JWT کوتاه‌عمر برای همان room

`agent.py` به LiveKit وصل می‌شود، STT/LLM/TTS فارسی را اجرا می‌کند و با پلاگین رسمی Tavus، آواتار را به همان room اضافه می‌کند.
