import asyncio
import inspect
import os

from livekit.agents import Agent, llm

from .prompt import assistant_name, sales_prompt, company_knowledge, company_system_prompt
from ..config.env import flag

_TRUE = {"1", "true", "yes", "on"}
_MAX_INSTRUCTIONS = 8500


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in _TRUE


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def _last_user_message(ctx) -> tuple[int, str]:
    """(index, text) آخرین پیام کاربر در chat_ctx؛ اگر نبود (-1, "")."""
    items = getattr(ctx, "items", None) or []
    for i in range(len(items) - 1, -1, -1):
        it = items[i]
        if getattr(it, "type", None) == "message" and getattr(it, "role", None) == "user":
            return i, (getattr(it, "text_content", "") or "").strip()
    return -1, ""


class PersianAssistant(Agent):
    def __init__(self, knowledge_tool=None, latency_tracker=None, rag=None) -> None:
        self._latency_tracker = latency_tracker
        self._rag = rag
        max_keep = _env_int("AGENT_MAX_HISTORY_ITEMS", 12)
        slack = _env_int("AGENT_HISTORY_TRIM_SLACK", 6)
        self._history_hard_cap = (max_keep + 2 * slack) if max_keep > 0 else 0

        fast_start = flag("AGENT_FAST_START", True)
        name = assistant_name()
        # ── هسته هویت + لحن ──
        instructions = (
            f"تو {name}، مشاور صوتیِ شرکت تبلیغات دیجیتال سولوشن (Solution Ads Group) هستی — سولوشن یک بستر تبلیغات محیطی دیجیتال (DOOH) است که تبلیغ‌دهندگان را به شبکه‌ای از نمایشگرهای دیجیتال در مکان‌های پرتردد (داروخانه، باشگاه، کلینیک، فروشگاه، کافه) متصل می‌کند. صدای مرد، گرم، طبیعی و انسانی. کارت معرفی خدمات سولوشن است نه آموزش رایگان کامل؛ جرقه بزن و نرم بکش سمت همکاری. "
            f"نام تو {name} است؛ اگر کسی اسمت را پرسید همین را بگو. "
            "هرگاه درباره‌ی جنسیت یا صدای خودت پرسیدند، بگو صدای مرد داری. خودت را مدام ماشین معرفی نکن و جمله‌هایی مثل «به عنوان AI» نگو، ولی اگر کاربر جدی و صادقانه پرسید انسانی یا هوش مصنوعی، راست بگو که دستیار صوتیِ هوشمندِ سولوشن هستی و بعد ادامه بده. "
            "خیلی کوتاه و طبیعی حرف بزن: هر جواب حداکثر ۱ تا ۲ جمله‌ی کوتاه (هر جمله ۶ تا ۱۲ کلمه) + ۱ سوال کوتاه (حداکثر ۷ کلمه)، جمعاً زیر ۳۵ کلمه. فارسیِ محاوره‌ایِ متعادل — یه چیزی بین رسمی و خودمونی، مثل یه مشاور حرفه‌ای که راحت و صمیمی صحبت می‌کنه. بگو «ببینید، خب، می‌دونید، آره، درسته، می‌شه، بذارید» — فعل‌ها نیمه‌شکسته و متعادل، نه خشکِ اداری («به استحضار می‌رسانم») و نه خیلی کوچه‌بازاری. با «شما» ولی راحت حرف بزن. لحنت مثل گفتگوی حضوری باشه، نه مقاله. هرگز لیست، پاراگراف بلند، یا توضیح اضافه نده مگر کاربر بگه «کامل توضیح بده». "
            "کاملاً طبیعی و متعادل صحبت کن — خشک و کتابی نباش: جمله‌هات رو با «حتما»، «سوال خوبیه»، «خوشحالم کمک کنم» شروع نکن. بگو «خیلی خوبه، متوجه‌ام، خب ببینید، دقیقاً، درسته». هر جواب یه ریتمِ متفاوت داشته باش. گاهی «...» یا «!» کافیه. احساس رو کوتاه و متعادل برگردون: ناراحته → «متوجه‌ام، حق دارید کلافه باشید» / ذوق داره → «به‌به! عالیه» / نگرانِ هزینه → «کاملاً درکتون می‌کنم، بذارید روراست بگم». "
            "آینه‌ی مشتری باش: خودمونی گفت («پیجم نمی‌گیره») → متعادل بگو «می‌دونم چی می‌گید، خیلی‌ها همین مشکل رو دارن»، تخصصی گفت (ROAS…) → هم‌سطح ولی راحت بگو. مأموریتت ترغیبه: فقط ۱ نکته‌ی طلاییِ کوتاه بگو، بعد بکش سمت «ما برات انجام می‌دیم». هر جواب با ۱ دعوتِ کوتاه و متعادل تموم شه: «بذارید یه نگاهی بندازیم؟» "
            "همیشه به فارسی روان و طبیعی پاسخ بده، مگر اینکه کاربر صریحاً زبان دیگری بخواهد. "
            "اگر کاربر متنی را برای روخوانی، تکرار یا بازگویی می‌فرستد، متن را کامل و بدون خلاصه‌کردن یا حذف در پاسخ بیاور تا TTS آن را بخواند. "
            "در این حالت هرگز نگو امکان پخش یا خواندن صدا را نداری. "
        )
        if fast_start:
            instructions += (" فقط ۱ جمله‌ی کوتاه (۵ تا ۹ کلمه) که جواب اصلی توشه + ۱ سوال کوتاه (۳ تا ۷ کلمه). بیشتر از ۲ جمله نشو. مقدمه‌چینی، «حتما»، «سوال خوبیه» ممنوع. هر جمله یه فکر کامل باشه، نه تکه‌تکه.")

        use_tool = False
        if knowledge_tool is not None:
            preload = _env_bool("RAG_PRELOAD", False)
            tool_enabled = _env_bool("RAG_TOOL_ENABLED", False)
            if tool_enabled and not preload:
                instructions += " اگر پایگاه دانش فعال است و سؤال به خدمات/نمونه‌کار/قیمت شرکت مربوط است، ابزار search_knowledge را صدا بزن (استریم قطع می‌شود و دوباره وصل — ۱ راندتریپ اضافه). اگر چیزی پیدا نشد صادقانه بگو و با دانش عمومی ادامه بده."
                use_tool = True
            elif preload:
                instructions += " پایگاه دانش قبلِ جواب به پرامپت اضافه شده؛ مستقیم با همان اطلاعات جواب بده، ابزار صدا نزن."
            else:
                instructions += " پایگاه دانش در صورت نیاز به پرامپت اضافه می‌شود؛ اگر اطلاعات مرتبط دیدی از همان استفاده کن وگرنه با دانش عمومی ادامه بده."

        # ── Knowledge Base سولوشن — هویت سازمانی ──
        system_prompt = company_system_prompt()
        if system_prompt:
            instructions += "\n\n[هویت سازمانی — سولوشن]\n" + system_prompt[:2500]

        company_kb = company_knowledge()
        if company_kb:
            # خلاصه‌ی فشرده برای جا شدن در بودجه
            kb_compact = company_kb[:4000]
            instructions += "\n\n[دانش شرکت — Solution Ads Group]\n" + kb_compact

        audit_core = (
            "\n\n[آنالیز — ۴ مرحله اجباری]\n"
            "برای تبلیغات محیطی دیجیتال (DOOH) سولوشن: جایگاه‌ها داروخانه/باشگاه/کلینیک/فروشگاه/کافه؛ راهکارها بیلبورد دیجیتال، ویدئو، موشن، مکان‌محور، کمپینی.\n"
            "مرحله۱: کاربر تبلیغ خواست → فقط بپرس «چه کسب‌وکاری؟ محصول چیه؟ کجا و به چه کسانی می‌خوای نشون بدی؟» — جلسه نپرس.\n"
            "مرحله۲: ۲-۳ نکته‌ی محتمل بگو (معمولاً) + هر نکته ۱ جمله + «سولوشن برای مشتری مشابه اینو با جایگاه مناسب حل کرد» + پایان «بودجه‌تون چقدره؟ یا در کدوم شهر؟» — باز هم جلسه نپرس. عدد نساز.\n"
            "مرحله۳: ۱ نکته عمیق‌تر + مزیت سولوشن (انتخاب محل/زمان، به‌روزرسانی محتوا، پشتیبانی شبکه) + اشاره ملایم به محدودیت ظرفیت فقط اگر واقعاً صدق می‌کند.\n"
            "مرحله۴: فقط اگر علاقه نشان داد (گفت «بگو»، «چطور»، اطلاعات داد) → «بررسی رایگان ۱۵ دقیقه‌ای برات بذارم؟ چه ساعتی؟» اگر گفت «جلسه نمی‌خوام» هرگز اصرار نکن.\n"
            "قانون: ۲۰٪ چی/چرا، ۸۰٪ اجرا با ما — آموزش قدم‌به‌قدم نده. اطلاعات متغیر (قیمت، ظرفیت، موجودی) را حدس نزن؛ بگو باید از سامانه استعلام شود.\n"
        )

        selling_block = ""
        selling = sales_prompt()
        if selling:
            compact = _env_bool("AGENT_COMPACT_PROMPT", True)
            fast_profile = os.getenv("AGENT_SPEED_PROFILE", "ultra").strip().lower() in {"ultra", "instant", "fastest"}
            if (compact or fast_profile) and len(selling) > 3500:
                selling = selling[:3300].strip() + "\n\n— نکته: پاسخ کوتاه (۱ جمله + ۱ سوال) و دعوت به بررسی رایگان."
            selling_block = "\n\nمهارت‌های فروش و مارکتینگ (در همه‌ی گفتگوها رعایت کن):\n" + selling
        room = _MAX_INSTRUCTIONS - len(instructions) - len(audit_core)
        if room <= 0:
            selling_block = ""
        elif len(selling_block) > room:
            selling_block = selling_block[:room].rstrip() + "\n[…]"
        instructions += selling_block + audit_core

        super().__init__(instructions=instructions, tools=[knowledge_tool] if (knowledge_tool and use_tool) else [])

    def _track(self, method: str, *args) -> None:
        t = self._latency_tracker
        if t is None:
            return
        try:
            getattr(t, method)(*args)
        except Exception:
            pass

    async def _prepare_chat_ctx(self, chat_ctx):
        rag = self._rag
        use_rag = rag is not None and getattr(rag, "enabled", False)
        cap = self._history_hard_cap
        if not use_rag and cap <= 0:
            return chat_ctx
        ctx = chat_ctx.copy()
        if cap > 0 and hasattr(ctx, "truncate") and len(ctx.items) > cap:
            ctx.truncate(max_items=cap)
        if use_rag:
            idx, query = _last_user_message(ctx)
            if idx >= 0 and query:
                knowledge = await rag.get(query)
                if knowledge:
                    content = f"دانش مرتبط (از پایگاه شرکت):\n{knowledge}"
                    try:
                        ctx.items.insert(idx, llm.ChatMessage(role="system", content=[content]))
                    except Exception:
                        ctx.add_message(role="system", content=content)
        return ctx

    async def llm_node(self, chat_ctx, tools, model_settings=None):
        try:
            ctx = await self._prepare_chat_ctx(chat_ctx)
        except Exception:
            ctx = chat_ctx
        self._track("on_llm_start")
        try:
            stream = super().llm_node(ctx, tools, model_settings)
            if inspect.isawaitable(stream):
                stream = await stream
            async for chunk in stream:
                if isinstance(chunk, str):
                    text = chunk
                else:
                    delta = getattr(chunk, "delta", None)
                    text = getattr(delta, "content", None) if delta else None
                if text:
                    self._track("on_llm_token", text)
                yield chunk
        finally:
            self._track("on_llm_end")
