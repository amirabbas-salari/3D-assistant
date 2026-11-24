# StreamCore — استقرار از صفر

این پوشه جایگزین LiveKit شده.

## معماری جدید

```
[Browser] --WHIP/WebRTC--> [streamcore-server:8080] --POST /agent--> [streamcore-agent:8000]
                              | STT: Deepgram nova-3 fa
                              | TTS: Cartesia sonic-3 / ElevenLabs
                              | LLM: gpt-4o-mini via OpenRouter/OpenAI (داخل agent)
                              | VAD: silero + barge-in
```

* **voice_only**: آواتار حذف شد (درخواست شما)
* **local Docker**: یک باینری Go + یک سرویس Python
* **same providers**: Deepgram + gpt-4o-mini + Cartesia — فقط transport عوض شده

## اجرای سریع

```bash
# 1. کلیدها
cp .env.example .env
# پر کن: DEEPGRAM_API_KEY, OPENAI_API_KEY (یا OPENROUTER_API_KEY), CARTESIA_API_KEY

# 2. کانفیگ StreamCore
cp streamcore/config.toml.example streamcore/config.toml
# اگر خواستی base_url عوض کن

# 3. استارت
docker compose -f streamcore/docker-compose.yml up --build

# در ترمینال دیگر: web StreamCore
npm --workspace apps/web-streamcore install
npm --workspace apps/web-streamcore run dev
# باز کن http://localhost:5174
```

## توسعه agent

```bash
pip install -e apps/streamcore-agent
uvicorn sam_streamcore.server:app --host 0.0.0.0 --port 8000 --reload
# StreamCore رو لوکال با go run . اجرا کن و WHIP_URL رو به لوکال بده
```

## تفاوت با LiveKit قبلی

- **نداریم**: LiveKit Cloud, room token, avatar D-ID/Spatius
- **داریم**: WHIP یک POST، TURN داخلی، barge-in واقعی، ICE restart
- **حافظه**: keyed by session_id (مکالمه) + resource_id (شخص) — مثل قبل ۱۲ پیام نگه می‌داره
- **RAG**: همون chromadb قبلی، فقط inject قبل از LLM
