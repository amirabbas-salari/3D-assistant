# اتصال دستیار «سام» به سایت شرکت — راهنمای مرحله‌به‌مرحله

> این راهنما برای تست روی سایت دیجیتال مارکتینگ شماست. با **یک خط کد**، یک دکمه‌ی شناور مثل چت آنلاین به سایت اضافه می‌شود که کاربر با کلیک، با سام صوتی/متنی حرف می‌زند.

---

## ۱) معماری در یک نگاه

```
[سایت شما]  ──iframe/widget──>  [sam.yourdomain.com]  ──API──>  LiveKit + Cloudflare + TTS/STT
              یک خط <script>          هاستِ دستیار              (شما نگه می‌دارید)
```

شما **هاستِ دستیار** را جدا نگه می‌دارید (مثلاً `sam.yourdomain.com`). سایت اصلی شما فقط یک `iframe` یا `script` لود می‌کند — پس:

- نیازی نیست کد دستیار را داخل CMS شرکت کپی کنید
- آپدیت دستیار (پرومپت فروش، دانش مارکتینگ) بدون دست‌زدن به سایت انجام می‌شود
- رازها (`LIVEKIT_API_SECRET`, `CLOUDFLARE_API_TOKEN`) هرگز به مرورگر کاربر نمی‌رود

---

## ۲) آماده‌سازی هاست دستیار (۵ دقیقه)

### ۲-۱ — بیلد پروداکشن

روی سروری که دستیار را هاست می‌کنید (یا لوکال برای تست):

```bash
npm install
npm run build          # خروجی در apps/web/dist  و  dist/
```

### ۲-۲ — متغیرهای محیطی

از `.env.example` کپی کنید و حداقل این‌ها را پر کنید:

```env
LIVEKIT_URL=wss://xxx.livekit.cloud
LIVEKIT_API_KEY=APIxxx
LIVEKIT_API_SECRET=xxx

CLOUDFLARE_ACCOUNT_ID=xxx
CLOUDFLARE_API_TOKEN=xxx

# برای تست بدون آواتار (سریع‌تر، ارزان‌تر):
AVATAR_ENABLED=false

# نام دستیار که کاربر می‌شنود:
ASSISTANT_NAME=سام
```

> برای پروداکشن `SPEECH_PROVIDER=direct` + `DEEPGRAM_API_KEY` + `GOOGLE_API_KEY` را اضافه کنید تا سهمیه‌ی LiveKit تمام نشود. توضیح کامل در README بخش «کلید مستقیم ارائه‌دهنده».

### ۲-۳ — اجرا

```bash
NODE_ENV=production npm start
# API روی http://0.0.0.0:3001 بالا می‌آید
# در production همین سرور فایل‌های dist را هم سرو می‌کند
```

چک کنید:

```bash
curl http://localhost:3001/api/health
# باید configured: true برگردد
```

---

## ۳) نصب روی سایت شرکت — ۳ روش

### روش A — دکمه‌ی شناور (پیشنهادی برای تست) ⭐

یه دکمه‌ی گرد پایین صفحه + پاپ‌آپ تمام‌صفحه در موبایل. همین را به مدیر سایت بدهید:

**یک خط در `<head>` یا قبل از `</body>`:**

```html
<script src="https://sam.yourdomain.com/widget.js"
        data-sam-url="https://sam.yourdomain.com"
        data-sam-position="bottom-right"
        data-sam-color="#244f91"
        data-sam-greeting="سلام! من سام هستم — مشاور فروش و مارکتینگ شما. چطور می‌تونم کمکتون کنم؟"
        async></script>
```

همین! فایل `widget.js` در `apps/web/public/widget.js` همین پروژه است. بعد از `npm run build` خودکار در `apps/web/dist/widget.js` کپی می‌شود.

| ویژگی | توضیح |
|---|---|
| `data-sam-url` | آدرس هاست دستیار (بدون `/` آخر) |
| `data-sam-position` | `bottom-right` یا `bottom-left` |
| `data-sam-color` | رنگ برند شما (دکمه و هدر) |
| `data-sam-greeting` | پیام اول (اختیاری) |

> **تست لوکال بدون هاست:** `data-sam-url="http://localhost:3001"` بگذارید و سایت شرکت را هم لوکال باز کنید.

---

### روش B — آیکون ساده + لینک (سریع‌ترین برای دمو)

اگر نمی‌خواهید اسکریپت اضافه کنید:

```html
<a href="https://sam.yourdomain.com" target="_blank" rel="noopener"
   style="position:fixed;bottom:20px;right:20px;background:#244f91;color:#fff;
          padding:12px 18px;border-radius:999px;font-family:Vazirmatn;
          text-decoration:none;box-shadow:0 4px 12px rgba(0,0,0,.2);z-index:9999">
  💬 گفتگو با سام — مشاور مارکتینگ
</a>
```

کاربر در تب جدید با دستیار کامل (صوت + متن + آواتار) حرف می‌زند.

---

### روش C — جاسازی تمام‌صفحه (iframe)

برای صفحه‌ی اختصاصی مثل `yourdomain.com/moshaver`:

```html
<iframe src="https://sam.yourdomain.com"
        allow="microphone; camera; autoplay"
        style="width:100%;height:80vh;min-height:600px;border:0;border-radius:12px"
        title="دستیار سام"></iframe>
```

> `allow="microphone"` **الزامی** است، وگرنه مرورگر میکروفون را نمی‌دهد.

---

## ۴) تنظیمات مهم برای وردپرس

- **Elementor / المنتور:** یک HTML widget اضافه کنید و کد روش A را پیست کنید.
- **Header/Footer plugin:** کد را در بخش Footer بگذارید تا در همه صفحات بیاید.
- **کش:** بعد از اضافه کردن، کش Cloudflare/WP Rocket را خالی کنید.
- **HTTPS:** هاست دستیار باید `https://` باشد، وگرنه مرورگر میکروفون را بلوکه می‌کند (حتی در iframe).

## ۵) شخصی‌سازی برند (بدون کدنویسی)

| می‌خواهی... | کجا |
|---|---|
| نام دستیار را عوض کنی | `.env` → `ASSISTANT_NAME=سام مارکت` |
| پرامپت فروش را عوض کنی | `prompts/sales_playbook.md` — مهارت فروش/مارکتینگ همین‌جاست |
| دانش شرکت (خدمات، قیمت، FAQ) اضافه کنی | پوشه‌ی `knowledge/` → فایل `.md` → `python scripts/build_rag_index.py` |
| رنگ دکمه را عوض کنی | `data-sam-color` در تگ `<script>` |

## ۶) چک‌لیست قبل از انتشار

- [ ] `curl /api/health` → `configured: true`
- [ ] `npm run build` بدون خطا
- [ ] تست میکروفون در Chrome (آيکون 🔒 کنار آدرس → allow microphone)
- [ ] تست چت متنی وقتی میکروفون خاموش است (باید همچنان کار کند)
- [ ] `data-sam-url` دقیقاً همان دامنه‌ی هاست دستیار (با `https`)
- [ ] در موبایل هم تست شد (پاپ‌آپ تمام‌صفحه)

---

## عیب‌یابی

| مشکل | دلیل |
|---|---|
| دکمه می‌آید ولی «پیکربندی ناقص» | `.env` روی هاست دستیار ناقص — `/api/health` را چک کن |
| کلیک می‌کنم، میکروفون نمی‌آید | سایت شما `http` است یا iframe فاقد `allow="microphone"` |
| صدا می‌آید ولی آواتار نمی‌آید | عمدی است — `AVATAR_ENABLED=false` یعنی فقط صدا. برای آواتار `true` + `DID_API_KEY` |
| 429 Too Many Requests | سهمیه LiveKit تمام شده → `SPEECH_PROVIDER=direct` را فعال کن |

سؤالی بود، همین‌جا بگو؛ ویجت را هم می‌تونیم با لوگو و رنگ شرکتت ست کنیم.
