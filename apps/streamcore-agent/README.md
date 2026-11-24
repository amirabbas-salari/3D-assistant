# StreamCore Agent — سام

این سرویس **HTTP Agent** برای `streamcore-server` است (از صفر، جایگزین LiveKit).

* پروتکل: `llm.provider = "agent"` → StreamCore هر نوبت کاربر رو به `POST http://agent:8000/agent` می‌فرسته
* پاسخ: `text/plain` streaming — هر جمله کامل بلافاصله به TTS می‌ره (بدون انتظار برای کل جواب)
* حافظه: keyed by `session_id` (هر تماس) + `resource_id` (شخص) — اختیاری
* RAG، تاریخچه، و پرامپت فارسی «سام» از پروژه قبلی بازاستفاده شده

## اجرا

```bash
cp ../../.env.example .env  # OPENAI_API_KEY یا OPENROUTER_API_KEY
pip install -e .
uvicorn sam_streamcore.server:app --host 0.0.0.0 --port 8000 --reload
```

## پیکربندی StreamCore

```toml
[llm]
provider = "agent"

[agent]
url = "http://streamcore-agent:8000/agent"
timeout_ms = 30000

[stt]
provider = "deepgram"
[deepgram]
model = "nova-3"
language = "fa"

[tts]
provider = "cartesia" # یا elevenlabs
[cartesia]
model = "sonic-3"
language = "fa"

[openai]
api_key = "sk-..."
model = "gpt-4o-mini"
```

