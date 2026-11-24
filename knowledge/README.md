# پایگاه دانش — Iran Full-Service Digital Agency (Phase 1)

این پوشه حالا حاوی **دیتاست کامل Phase 1** است — منبع: `agency_ai_dataset_phase1.zip` (حذف شد پس از ingestion).

## ساختار جدید (12 سند)
- `fa/sales/` — 4 سند فارسی فروش (پذیرش لید، کشف نیاز، پروپوزال، اعتراضات)
- `fa/crm/` — 2 سند فارسی CRM (ثبت داده، پیگیری)
- `en/sales/` — 3 سند انگلیسی فروش
- `en/crm/` — 2 سند انگلیسی CRM

همه اسناد synthesis مستقل با metadata کامل هستند (id, domain, language, tags, source_ids).

## RAG ingestion
هر Markdown به عنوان یک document جداگانه ingest می‌شود. برای فعال‌سازی:

```powershell
python scripts/build_rag_index.py
# در .env:
RAG_ENABLED=true
RAG_DOCS_DIR=knowledge
RAG_TOP_K=3
```

تست:
```
python scripts/build_rag_index.py --query "فرایند پذیرش لید"
python scripts/check_retrieval.py
```

## محدودیت
- همه منابع `review_required` — قبل از production بازبینی حقوقی/فنی لازم است
- قیمت/قانون/دسترسی پلتفرم را به عنوان fact قطعی نگیرید

دیتاست اصلی در `.rag/` ایندکس می‌شود؛ فایل zip پس از استخراج حذف شد.
