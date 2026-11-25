# معماری پروژه — 3D Assistant (سام)

Monorepo استاندارد با مرز ماژولار تمیز، قابل نگهداری و ارتقا.

## نمای کلی

```
3D-assistant/
├── apps/
│   ├── agent/                  # Python LiveKit Agent (سام)
│   │   ├── src/sam/
│   │   │   ├── agent.py        # facade نازک (re-export از session)
│   │   │   ├── __main__.py     # python -m sam.agent
│   │   │   ├── config/         # env, llm, speed (profiles)
│   │   │   ├── speech/         # stt, tts, providers
│   │   │   ├── avatar/         # provider, tavus, manager
│   │   │   ├── rag/            # engine.py + tools.py (preload/tool)
│   │   │   ├── latency/        # tracker.py
│   │   │   ├── assistant/      # prompt + agent (PersianAssistant)
│   │   │   ├── session/        # entrypoint + publish
│   │   │   └── utils/          # logging (redact, RoomLogHandler)
│   │   ├── pyproject.toml      # src-layout, deps
│   │   └── README.md
│   ├── web/                    # Vite + React (RTL)
│   │   ├── src/
│   │   │   ├── main.jsx        # فقط createRoot
│   │   │   ├── app/App.jsx     # shell + wiring
│   │   │   ├── components/     # ChatPanel, VideoPanel, StatusPanel, LogsPanel, RemoteAudioOutput
│   │   │   ├── hooks/          # useAppState
│   │   │   ├── lib/            # latency, utils, lipsync-adapter
│   │   │   ├── api/            # client (health, session, cleanup)
│   │   │   ├── lipsync.js      # هماهنگی لب/صدا (legacy, Tavus داخلی دارد)
│   │   │   └── styles/         # globals.css
│   │   ├── vite.config.js
│   │   └── package.json (@3d-assistant/web)
│   └── api/                    # Express API
│       ├── src/
│       │   ├── index.js        # فقط setup + listen
│       │   ├── config/         # env, cors
│       │   ├── routes/         # health, session, cleanup
│       │   └── lib/            # livekit
│       └── package.json (@3d-assistant/api)
├── packages/
│   ├── contracts/              # shared constants (stages, providers)
│   └── config/                 # eslint, ruff presets
├── infra/
│   ├── docker/                 # Dockerfiles + compose (cloud) + compose.local (لوکال)
│   ├── livekit/                # livekit.yaml برای خود میزبان
│   └── ci/                     # (reserved)
├── knowledge/                  # RAG source (optional)
├── prompts/sales_playbook.md   # رفتار فروش (قابل ویرایش بدون کد)
├── scripts/                    # CLI tools
├── .github/workflows/ci.yml    # lint + build
├── turbo.json + Makefile + .editorconfig
├── package.json (workspaces: apps/*, packages/*)
└── pyproject.toml (ruff/pyright root)
```

### اصول طراحی

| اصل | پیاده‌سازی |
|---|---|
| **Monorepo + Workspaces** | `package.json` با `workspaces: [apps/web, apps/api, packages/*]`؛ هر app مستقل ولی `npm run dev` از ریشه هر دو را با `concurrently` اجرا می‌کند |
| **src-layout Python** | `apps/agent/src/sam` + `pyproject.toml` با `package-dir={"": "src"}` |
| **تفکیک deployable** | `apps/web` (استاتیک)، `apps/api` (Node)، `apps/agent` (Python worker) — هر کدام Dockerfile جدا |
| **Module boundaries** | `config` فقط env/llm/speed؛ `speech` فقط STT/TTS؛ `avatar` فقط Tavus؛ `session` فقط entrypoint؛ بدون چرخه‌ی وابستگی |
| **Facade pattern** | `apps/agent/src/sam/agent.py` فقط re-export؛ منطق داخل `session/entrypoint.py` |

## جریان صوت (streaming)

```
Mic → Deepgram STT (streaming) → endpointing (instant 0.05s) →
Cloudflare LLM (stream=True) → SentenceTokenizer → TTS (streaming/StreamAdapter) →
LiveKit audio → Browser / Avatar
RAG_PRELOAD=true: knowledge قبلِ LLM تزریق می‌شود (بدون roundtrip اضافه)
```

## اجرای محلی

**Cloud:**
```bash
npm install
cp .env.example .env  # پر کن
pip install -e apps/agent
npm run dev            # web + api
python -m sam.agent start  # agent (ترمینال جدا)
```

**لوکال (LiveKit خود میزبان):**
```bash
cp .env.local.example .env  # کلیدهای direct/openrouter را پر کن
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.local.yml up --build
# یا: make docker-local  (یا make livekit برای فقط LiveKit)
```

Production Cloud: `npm run build` → `NODE_ENV=production npm start` + `docker compose -f infra/docker/docker-compose.yml up`
Production لوکال: `docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.local.yml up --build`
