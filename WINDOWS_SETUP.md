# راهنمای Windows — رفع خطاهای شما

شما دو خطا دیدی:

## 1. Docker Desktop خاموش

```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
```

**علت:** Docker Desktop نصب هست ولی Engine اجراست نشده.

**فیکس:**
1. از Start Menu باز کن **Docker Desktop**
2. صبر کن پایین-چپ بنویسه `Engine running` (سبز)
3. بعد دوباره:
```powershell
docker ps
docker compose -f streamcore/docker-compose.yml up --build
```

اگر WSL2 نداری:
```powershell
wsl --update
```
و بعد Docker Desktop رو ری‌استارت کن.

اگر نمی‌خوای Docker استفاده کنی (لوکال بدون Docker):
```powershell
# ترمینال 1 — agent
pip install -e apps/streamcore-agent
$env:DEEPGRAM_API_KEY="..."
$env:OPENAI_API_KEY="..."
$env:CARTESIA_API_KEY="..."
uvicorn sam_streamcore.server:app --host 0.0.0.0 --port 8000 --app-dir apps/streamcore-agent/src --reload

# ترمینال 2 — StreamCore (نیاز به Go 1.25+)
go run github.com/streamcoreai/streamcore-server@latest
# یا اگر کلون کردی:
# git clone https://github.com/streamcoreai/streamcore-server C:\streamcore
# cd C:\streamcore; cp config.toml.example config.toml; go run .
```

## 2. npm workspaces not found

```
npm error No workspaces found: --workspace=apps/web-streamcore
```

**علت:** `package.json` قبلی `apps/web-streamcore` رو نمی‌شناخت — الان فیکس شد.

**فیکس:**
```powershell
# بعد از pull
npm install
npm --workspace apps/web-streamcore install
npm --workspace apps/web-streamcore run dev
# یا کوتاه:
npm run dev:web:streamcore
# → http://localhost:5174
```

اگر هنوز خطا داد:
```powershell
# مستقیم بدون workspace
cd apps/web-streamcore
npm install
npm run dev
```

## 3. کپی فایل‌های کانفیگ روی Windows

روی PowerShell دستور `cp` کار می‌کنه ولی اگر نشد از این استفاده کن:
```powershell
copy .env.example .env
copy streamcore\config.toml.example streamcore\config.toml
# بعد داخل streamcore\config.toml کلیدها رو بذار
notepad streamcore\config.toml
```

## 4. تست سریع بدون Docker/StreamCore

اگر فقط می‌خوای agent HTTP رو تست کنی:
```powershell
uvicorn sam_streamcore.server:app --host 0.0.0.0 --port 8000 --app-dir apps/streamcore-agent/src --reload
# ترمینال دیگر:
curl -N -X POST http://localhost:8000/agent -H "Content-Type: application/json" -d "{\"session_id\":\"test123\",\"type\":\"chat\",\"text\":\"سلام یه سایت می‌خوام\"}"
```

باید `text/event-stream` با `data: {\"delta\":\"...\"}` برگرده.
