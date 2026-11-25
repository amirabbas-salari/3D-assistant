# LiveKit لوکال — راهنمای کامل (فارسی)

این سند نحوه اجرای 3D-assistant با LiveKit خود میزبان را توضیح می‌دهد — بدون نیاز به LiveKit Cloud.

## چرا لوکال؟

- بدون وابستگی به اینترنت برای سیگنالینگ
- کنترل کامل روی کلیدها و داده
- هزینه Cloud صفر (به جز STT/TTS/LLM که همچنان کلید مستقیم می‌خواهند)

> **محدودیت:** LiveKit لوکال **Inference ندارد**. یعنی STT/TTS/LLM که قبلاً از گیت‌وی Cloud می‌آمدند باید مستقیم صدا زده شوند.

## معماری لوکال vs Cloud

| بخش | Cloud | لوکال |
|---|---|---|
| **LiveKit SFU** | `wss://xxx.livekit.cloud` | `ws://localhost:7880` (Docker) |
| **کلیدها** | از LiveKit Cloud | `devkey / secret` (پیش‌فرض `--dev`) |
| **STT** | `inference: deepgram/nova-3` | `direct: deepgram` (نیاز DEEPGRAM_API_KEY) |
| **TTS** | `inference: google/gemini-tts` | `direct: google` یا `openrouter` یا `elevenlabs` |
| **LLM** | `livekit: gpt-4o-mini` | `openrouter` یا `cloudflare` (کلید جدا) |
| **Avatar** | Tavus Daily | همان (یا خاموش) |

## پیش‌نیازها

- Docker + Docker Compose
- کلیدهای مستقیم:
  - `DEEPGRAM_API_KEY` (https://console.deepgram.com)
  - `GOOGLE_API_KEY` (https://aistudio.google.com/apikey) — اگر TTS مستقیم گوگل
  - `OPENROUTER_API_KEY` (https://openrouter.ai/settings/keys) — اگر LLM/‌TTS از OpenRouter
  - `ELEVENLABS_API_KEY` — اگر TTS از ElevenLabs

## گام ۱: .env لوکال

```bash
cp .env.local.example .env
```

داخل `.env` حداقل این‌ها را پر کنید (بقیه در `.env.local.example` آماده است):

```env
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...

SPEECH_PROVIDER=direct
DEEPGRAM_API_KEY=...
GOOGLE_API_KEY=...
```

## گام ۲: اجرا با داکر (پیشنهادی)

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.local.yml up --build
```

بررسی:

```bash
curl http://localhost:3001/api/health | jq
# livekitLocal: true, configured: true

curl http://localhost:7880/  # LiveKit health
```

مرورگر: http://localhost:3000 → «شروع نشست» → باید وصل شود.

## گام ۳: اجرا بدون داکر (سه ترمینال)

```bash
# ترمینال ۱: LiveKit
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.local.yml up livekit

# ترمینال ۲: API + Web
npm install
npm run dev  # web روی 5173، api روی 3001

# ترمینال ۳: Agent
pip install -e apps/agent
python -m sam.agent dev
```

## پورت‌ها

| پورت | کار | پروتکل |
|---|---|---|
| 7880 | LiveKit WebSocket + API | TCP |
| 7881 | RTC TCP fallback | TCP |
| 7882 | RTC | TCP+UDP |
| 50000-60000 | WebRTC media | UDP |
| 3001 | API | TCP |
| 3000 | Web (docker) / 5173 (vite) | TCP |

اگر فایروال دارید، 7880 و 50000-60000/udp را باز کنید. بدون UDP، صدا قطع و وصل می‌شود.

## عیب‌یابی

| علامت | علت | راه‌حل |
|---|---|---|
| `api-key is required` | .env لود نشده | `python scripts/check_env.py --skip-network` |
| `Connection refused 7880` | LiveKit بالا نیست | `docker ps | grep livekit` |
| `LiveKit Inference requires...` | هنوز LLM_PROVIDER=livekit | `LLM_PROVIDER=openrouter` بگذارید |
| صدا نمی‌آید ولی وصل است | UDP بسته است | پورت‌های 50000-60000/udp را باز کنید |
| `DEEPGRAM_API_KEY missing` | SPEECH_PROVIDER=direct ولی کلید نیست | کلید Deepgram را در .env بگذارید |
| Tavus کار نمی‌کند لوکال | ربطی به LiveKit ندارد | همان کلید Tavus Cloud را استفاده می‌کند |

## تست سریع

```bash
python scripts/check_env.py
# باید LIVEKIT_URL=ws://localhost:7880 را ببیند و بگوید local

python scripts/check_env.py --skip-network
# بدون تماس شبکه فقط فایل‌ها را چک می‌کند
```

## بازگشت به Cloud

```bash
cp .env.example .env  # و کلیدهای Cloud را پر کنید
docker compose -f infra/docker/docker-compose.yml up --build
# یا npm run dev + python -m sam.agent dev
```

## فایل‌های مرتبط

- `infra/docker/docker-compose.yml` — Cloud (بدون LiveKit)
- `infra/docker/docker-compose.local.yml` — لوکال (LiveKit + overrides)
- `infra/livekit/livekit.yaml` — کانفیگ LiveKit (اختیاری، --dev کافی است)
- `.env.local.example` — نمونه آماده لوکال
- `apps/api/src/config/env.js` — livekitPublicUrl / livekitInternalUrl
- `apps/api/src/lib/livekit.js` — LiveKitAPI با host داخلی
- `scripts/check_env.py` — تشخیص ws:// و devkey

