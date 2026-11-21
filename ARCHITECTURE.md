# معماری پروژه — 3D Assistant (سام)

این سند ساختار فعلی را پس از بازبینی برای مقایسه با پروژه‌های بزرگ توضیح می‌دهد.
هدف: تفکیک مسئولیت‌ها، قابلیت توسعه‌ی تیمی، و حفظ سازگاری با دستورات قبلی
(`python agent.py dev` و `npm run dev`).

## نمای کلی (Monorepo)

```
3D-assistant/
├── apps/
│   ├── agent/              # Python LiveKit Agent (سام)
│   │   ├── src/sam/
│   │   │   ├── agent.py    # entrypoint + AgentServer
│   │   │   ├── rag/        # BM25 + Chroma (engine.py)
│   │   │   ├── latency/    # tracker.py (اندازه‌گیری تأخیر)
│   │   │   ├── avatar.py   # (آینده) تفکیک avatar
│   │   │   └── speech.py   # (آینده) STT/TTS builders
│   │   ├── pyproject.toml  # وابستگی‌های Python (setuptools src layout)
│   │   └── README.md
│   ├── web/                # Vite + React (UI راست‌چین)
│   │   ├── src/
│   │   │   ├── main.jsx
│   │   │   ├── lipsync.js  # هماهنگی لب و صدا (Spatius)
│   │   │   └── styles.css
│   │   ├── index.html
│   │   ├── vite.config.js  # root=apps/web, outDir=apps/web/dist
│   │   └── package.json    # @3d-assistant/web
│   └── api/                # Express API (LiveKit token + health)
│       ├── src/index.js
│       └── package.json    # @3d-assistant/api
├── knowledge/              # منبع RAG (اختیاری، بدون محصول — خالی تحویل می‌شود)
├── prompts/                # رفتار فروش (sales_playbook.md)
├── scripts/                # ابزار CLI (build_rag_index, check_*)
├── pyproject.toml          # تنظیمات lint/type در ریشه
├── package.json            # workspaces: apps/web, apps/api
├── agent.py                # shim سازگار عقب‌رو → apps/agent/src/sam/agent.py
├── rag.py / latency.py     # shim سازگار عقب‌رو
├── server/index.js         # shim → apps/api/src/index.js
└── src/                    # shim → apps/web/src (حفظ npm:dev:client قدیمی)
```

### چرا این ساختار؟

| الگوی پروژه‌های بزرگ | پیاده‌سازی ما |
|---|---|
| **Monorepo + Workspaces** (Turborepo/pnpm) | `package.json` با `workspaces: ["apps/web","apps/api"]`؛ هر app مستقل نصب/ساخت دارد ولی `npm run dev` از ریشه هر دو را با `concurrently` اجرا می‌کند |
| **src layout برای Python** | `apps/agent/src/sam` + `pyproject.toml` با `tool.setuptools.package-dir = {""="src"}`؛ تست‌ها و ابزارها با `PYTHONPATH=apps/agent/src` کار می‌کنند |
| **تفکیک deployable ها** | `apps/web` (استاتیک)، `apps/api` (Node سرویس)، `apps/agent` (Python worker) هر کدام Dockerfile/CI جدا می‌توانند داشته باشند |
| **Shared config در ریشه** | `.env.example`, `pyproject.toml`, `ARCHITECTURE.md` در ریشه تا همه‌ی تیم یک منبع ببینند |
| **Backward compat shims** | فایل‌های قدیمی (`agent.py`, `server/index.js`, `src/main.jsx`, `vite.config.js`) نگهداشته شدند تا `python agent.py dev` و `npm run dev` بدون تغییر بمانند؛ داخل آن‌ها هشدار deprecation و import از مسیر جدید است |

## جریان داده‌ی صوتی (Streaming واقعی)

```
Mic → Deepgram STT (streaming interim) → endpointing (0.3s balanced) →
Cloudflare LLM (openai.LLM, stream=True, token-by-token) →
SentenceTokenizer (هر جمله یک درخواست) → TTS (Inference streaming یا Gemini+StreamAdapter) →
LiveKit audio → Browser / Avatar
```

- **LLM streaming**: `livekit.agents.inference.llm.LLMStream` با `stream=True` در `chat.completions.create`؛
  توکن‌ها به‌محض رسیدن از Workers AI به SDK می‌رسند و `llm_node_ttft` همان TTFT است.
- **TTS بدون انتظار**: `StreamAdapter` جمله‌ی اول را که بسته شد فوراً به TTS می‌دهد؛
  نیازی به کامل‌شدن پاسخ نیست. `preemptive_tts=True` جمله‌ی بعدی را پیش‌ساخته می‌کند.
- **FAST_START**: جمله‌ی اول ۵-۹ کلمه‌ی حاوی جواب → مرز جمله زود می‌رسد → TTS زود شروع می‌شود.
  (`AGENT_FAST_START=true` پیش‌فرض؛ هر جمله ۶-۱۰ کلمه‌ی کامل، نه تکه‌تکه).

## RAG (اختیاری، بدون داده‌ی محصول)

- ذخیره: Chroma (`.rag/chroma`) + embedding هش‌شده‌ی محلی (بدون دانلود مدل)
- رتبه‌بندی: BM25 فارسی (نرمال‌سازی ی/ک، حذف نیم‌فاصله، بوست عنوان)
- ابزار: `search_knowledge` (top_k=3)؛ جست‌وجو <1ms
- دستیار **هیچ اطلاعات محصولی** ندارد؛ مهارتش فروش حرفه‌ای + دیجیتال مارکتینگ است. RAG فقط برای اسناد داخلی اختیاری سازمان است.

## تأخیر و مدل‌ها

| مدل Cloudflare | TTFT نمونه‌ی این پروژه | توصیه |
|---|---|---|
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | ~150-300ms | برای صوت — بدون مرحله‌ی reasoning |
| `@cf/openai/gpt-oss-120b` | 1.0–5.4s (۵ سؤال کوتاه: 0.99/1.56/2.64/2.80/5.40s)؛ بنچمارک Artificial Analysis: 1.9s (low) / 9.0s (high) @205 tok/s | فقط اگر reasoning لازم است؛ با `reasoning_effort=low` + `AGENT_FAST_START` + `fast` profile |

## دستورات

```bash
# کل استک
npm install
npm run dev          # web (5173) + api (3001)
npm run build        # → apps/web/dist (+ کپی به dist برای سازگاری)

# فقط یک app
npm run dev --workspace=@3d-assistant/web
npm run dev --workspace=@3d-assistant/api

# ایجنت
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # یا pip install -e apps/agent
python agent.py dev                      # shim قدیمی (همچنان کار می‌کند)
python -m sam.agent dev                  # مسیر جدید (PYTHONPATH=apps/agent/src)

# RAG
python scripts/build_rag_index.py
python scripts/check_retrieval.py        # 15/15 باید پاس شود
python scripts/check_voice_flow.py       # 7/7
python scripts/check_llm_speed.py        # مقایسه‌ی reasoning_effort
```

## مهاجرت از ساختار قدیمی

- `agent.py` ریشه → `apps/agent/src/sam/agent.py` (کپی + shim)
- `rag.py` → `apps/agent/src/sam/rag/engine.py`
- `latency.py` → `apps/agent/src/sam/latency/tracker.py`
- `src/` → `apps/web/src/` (کپی + shim)
- `server/index.js` → `apps/api/src/index.js` (کپی + shim)
- `vite.config.js` / `index.html` → `apps/web/` (کپی + نگهداری ریشه برای `npm run dev:legacy`)

هیچ دستور قدیمی حذف نشده؛ همه‌ی مسیرهای جدید علاوه بر قدیمی‌ها اضافه شدند.

## گام‌های بعدی پیشنهادی (اختیاری)

- تقسیم `apps/agent/src/sam/agent.py` (۹۰۰ خط) به `assistant.py`/`avatar.py`/`speech.py`
- افزودن `apps/agent/tests/` + CI (GitHub Actions)
- Docker برای هر app (`apps/agent/Dockerfile`, `apps/api/Dockerfile`)
- ESLint/Prettier (`apps/web`) و Ruff (`apps/agent`) در pre-commit
