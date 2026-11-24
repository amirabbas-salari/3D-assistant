# مهاجرت از LiveKit به StreamCore — از صفر

این برنچ `arena/ac26ac7e-3d-assistant` پیاده‌سازی از صفر با https://github.com/streamcoreai/streamcore-server است.

## تصمیمات (بر اساس انتخاب شما)

- **scope: replace** — LiveKit کامل حذف، WHIP/WebRTC جایگزین
- **features: voice_only** — آواتار D-ID/Spatius حذف، تمرکز روی latency
- **deployment: local Docker** — `go run` یا `ghcr.io/streamcoreai/streamcore-server`
- **language: same** — Deepgram nova-3 fa + gpt-4o-mini + Cartesia sonic-3

## فایل‌های جدید

```
streamcore/
  config.toml.example   # STT/TTS/LLM/VAD برای سام
  docker-compose.yml    # streamcore-server + streamcore-agent
  README.md

apps/streamcore-agent/
  pyproject.toml
  src/sam_streamcore/
    prompt.py       # sales_playbook بدون وابستگی LiveKit
    rag.py          # RAG نازک (reuse chromadb)
    agent.py        # build_instructions (فارسی کوتاه)
    server.py       # FastAPI POST /agent — text/event-stream
  README.md

apps/web-streamcore/
  package.json      # @streamcore/js-sdk 0.1.8
  vite.config.js
  index.html
  src/
    hooks/useStreamCore.js  # StreamCoreAIClient
    App.jsx                 # WHIP_URL, transcript فارسی
    styles.css

infra/streamcore/
  Dockerfile.agent          # Python agent

STREAMCORE_MIGRATION.md     # همین فایل
```

## چطور اجرا می‌شه

### 1) کلیدها

```bash
cp .env.example .env
# پر کن:
# DEEPGRAM_API_KEY=...
# OPENAI_API_KEY=sk-...  یا OPENROUTER_API_KEY=...
# CARTESIA_API_KEY=...
```

### 2) StreamCore

```bash
cp streamcore/config.toml.example streamcore/config.toml
# اگر لوکال هستی نیازی به public_ip/turn_secret نیست

# با Docker (توصیه)
docker compose -f streamcore/docker-compose.yml up --build

# یا native
go run github.com/streamcoreai/streamcore-server@latest
# server روی :8080 و WHIP روی /whip
```

### 3) Agent (اگر Docker نخواستی)

```bash
pip install -e apps/streamcore-agent
uvicorn sam_streamcore.server:app --host 0.0.0.0 --port 8000 --reload
```

### 4) Web

```bash
npm install --workspace apps/web-streamcore
npm --workspace apps/web-streamcore run dev
# http://localhost:5174
# WHIP_URL پیش‌فرض http://localhost:8080/whip
```

## پروتکل StreamCore vs LiveKit

**LiveKit قبل:** `Room + Participant + TrackSubscribed + DataChannel latency`

**StreamCore الان:** `WHIP POST /whip` یک درخواست HTTP، بعد WebRTC P2P، و برای هر نوبت:

```json
// StreamCore → agent
{
  "session_id": "9f2c...",
  "resource_id": "user_8891_or_empty",
  "type": "chat",
  "text": "سلام یه سایت می‌خوام",
  "system": "skill text",
  "interrupted_text": "چیزی که نصف پخش شد",
  "context": ["chunk rag"],
  "summary": "digest"
}
```

پاسخ ما: `Content-Type: text/event-stream` با `data: {"delta": "..."}`
StreamCore هر جمله کامل رو بلافاصله به TTS می‌فرسته — مثل `StreamAdapter` قبلی.

## حفظ فیچرهای قبلی

- ✅ پرسونا سام (sales_playbook.md) — کامل منتقل شد
- ✅ RAG — reuse از `apps/agent/src/sam/rag` با _rag_preload
- ✅ تاریخچه ۱۲ پیام — keyed by session_id
- ✅ Fast start (۵-۹ کلمه + سوال)
- ❌ آواتار — حذف (voice_only)
- ❌ LiveKit Inference — حذف، مستقیم Deepgram/Cartesia

## گام‌های بعدی

- [ ] اضافه کردن `TURN` روی VPS آلمان (برای NAT ایران/آلمان)
- [ ] تست latency: هدف 1.4-1.6s E2E (قبل 2.4s)
- [ ] اگر خواستی RAG داخلی StreamCore (OpenSearch) جایگزین chromadb کن
- [ ] SIP telephony اگر خواستی: streamcoreai/sip-server
