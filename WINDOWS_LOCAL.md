# اجرای بدون Docker — ویندوز

برای تست سریع بدون Docker، ۳ ترمینال جدا باز کن.

## ۰. پیش‌نیاز
- Python 3.11 + `pip`
- Go 1.22+ (`go version`) — اگر نداری از https://go.dev/dl نصب کن
- Node 18+ 
- `.env` در ریشه پروژه پر باشه:
```
OPENAI_API_KEY=sk-...
DEEPGRAM_API_KEY=...
CARTESIA_API_KEY=...
# یا OPENROUTER_API_KEY به جای OPENAI
```

## ۱. Agent سام (ترمینال ۱)
```powershell
cd J:\projects\HORNO\SalesCloser
git pull origin arena/7486e567-3d-assistant

python -m venv .venv
.\.venv\Scripts\activate
pip install -e apps/streamcore-agent

# تست health
uvicorn sam_streamcore.server:app --host 0.0.0.0 --port 8000 --app-dir apps/streamcore-agent/src --reload
```
باید ببینی:
```
System prompt  ... chars, model=openai/gpt-4o-mini
Uvicorn running on http://0.0.0.0:8000
```
تست:
```powershell
curl.exe http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/health | Format-List
```

## ۲. StreamCore Server (ترمینال ۲)
```powershell
cd J:\projects\HORNO\SalesCloser

# بار اول: دانلود سورس سرور (فقط یک بار)
git clone https://github.com/streamcoreai/streamcore-server.git C:\tmp\streamcore-server

cd C:\tmp\streamcore-server
copy J:\projects\HORNO\SalesCloser\streamcore\config.local.toml config.toml
copy J:\projects\HORNO\SalesCloser\.env .env

go run . 
# یا اگر باینری داری:
# go build -o streamcore.exe . ; .\streamcore.exe
```
باید ببینی:
```
streamcore listening on :8080 whip=/whip
```
تست:
```powershell
curl.exe http://localhost:8080/health
```

> نکته: اگر `go run` ارور `config.toml not found` داد، مطمئن شو `config.toml` کنار `go run .` هست (نه داخل streamcore/).

## ۳. وب کلاینت WHIP (ترمینال ۳)
```powershell
cd J:\projects\HORNO\SalesCloser
npm --workspace apps/web-streamcore install
npm --workspace apps/web-streamcore run dev
# باز کن http://localhost:5174
```

## عیب‌یابی
- `IndexError: 4` → `git pull` نکردی (فیکس PR98)
- `connection closed` روی :8000 → لاگ ترمینال ۱ رو بفرست
- `Unable to connect :8080` → ترمینال ۲ هنوز `listening` نشده
- صدا نمیاد → F12 Console رو چک کن، `DEEPGRAM_API_KEY` و `CARTESIA_API_KEY` پر باشن
