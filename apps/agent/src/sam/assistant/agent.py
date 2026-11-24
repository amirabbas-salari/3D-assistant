import asyncio
import inspect
import os

from livekit.agents import Agent, llm

from .prompt import assistant_name, sales_prompt
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
        # latency_tracker برای ثبت مرحله‌ای هر توکن (گانت چارت)
        self._latency_tracker = latency_tracker
        # rag: RagPrefetcher (فقط وقتی حالت preload فعال است enabled=True دارد)
        self._rag = rag
        # سقف سخت تاریخچه برای هر فراخوانی LLM؛ تریم اصلی (دسته‌ای و پایدار) در entrypoint انجام می‌شود،
        # این فقط شبکهٔ اطمینان است و عمداً بزرگ‌تر از سقف تریم دسته‌ای است تا prefix پرامپت (cache) ثابت بماند.
        max_keep = _env_int("AGENT_MAX_HISTORY_ITEMS", 12)
        slack = _env_int("AGENT_HISTORY_TRIM_SLACK", 6)
        self._history_hard_cap = (max_keep + 2 * slack) if max_keep > 0 else 0

        fast_start = flag("AGENT_FAST_START", True)
        name = assistant_name()
        instructions = (
            f"تو {name}، مشاور صوتیِ شرکتِ دیجیتال مارکتینگ و طراحی سایتِ ما هستی — صدای مرد، گرم، طبیعی و انسانی. حرف‌زدنت باید مثل یه مشاور باتجربه طبیعی باشه. کارت معرفیِ خدماتِ شرکته: طراحی سایت، سئو، تبلیغات، شبکه‌اجتماعی، برندینگ و تولید محتوا. مشتری رو آموزشِ رایگانِ کامل نده؛ جرقه بزن و نرم بکش سمت همکاری. "
            f"نام تو {name} است؛ اگر کسی اسمت را پرسید همین را بگو. "
            "هرگاه درباره‌ی جنسیت یا صدای خودت پرسیدند، بگو صدای مرد داری. خودت را مدام ماشین معرفی نکن و جمله‌هایی مثل «به عنوان AI» نگو، ولی اگر کاربر جدی و صادقانه پرسید انسانی یا هوش مصنوعی، راست بگو که دستیار صوتیِ هوشمندِ شرکت هستی و بعد ادامه بده. "
            "خیلی کوتاه و طبیعی حرف بزن: هر جواب حداکثر ۱ تا ۲ جمله‌ی کوتاه (هر جمله ۶ تا ۱۲ کلمه) + ۱ سوال کوتاه (حداکثر ۷ کلمه)، جمعاً زیر ۳۵ کلمه. فارسیِ دوستانه، صمیمی و کمی محاوره‌ای — مثل یه دوستِ کاربلد، نه کارمند رسمی. بگو «ببین، خب، می‌دونی، آره، می‌تونی، بذار» — فعل‌ها شکسته و خودمونیِ ملایم ولی محترمانه. نه خشکِ کتابی («به استحضار می‌رسانم»)، نه لاتیِ تند. با «شما» ولی خودمونی حرف بزن. لحنت مثل گفتگوی روبه‌رو با یه دوست باشه، نه مقاله. هرگز لیست، پاراگراف بلند، یا توضیح اضافه نده مگر کاربر بگه «کامل توضیح بده». "
            "کاملاً طبیعی و دوستانه صحبت کن — خشک و کتابی نباش: جمله‌هات رو با «حتما»، «سوال خوبیه»، «خوشحالم کمک کنم» شروع نکن. بگو «ایول، آره می‌فهمم، خب ببین، دقیقاً». هر جواب یه ریتمِ متفاوت داشته باش. گاهی «...» یا «!» کافیه. احساس رو کوتاه و خودمونی برگردون: ناراحته → «آره می‌فهمم، حق داری کلافه باشی» / ذوق داره → «ایول! چه خوب!» / نگرانِ هزینه → «کاملاً می‌فهممت، بذار روراست بگم». "
            "آینه‌ی مشتری باش: خودمونی گفت («پیجم نمی‌گیره») → خودمونی بگو «آره می‌دونم چی می‌گی»، تخصصی گفت (ROAS…) → هم‌سطح ولی دوستانه بگو. مأموریتت ترغیبه: فقط ۱ نکته‌ی طلاییِ کوتاه بگو، بعد بکش سمت «ما برات انجام می‌دیم». هر جواب با ۱ دعوتِ کوتاه و خودمونی تموم شه: «بذار یه نگاه بندازیم؟» "
            "همیشه به فارسی روان و طبیعی پاسخ بده، مگر اینکه کاربر صریحاً زبان دیگری بخواهد. "
            "اگر کاربر متنی را برای روخوانی، تکرار یا بازگویی می‌فرستد، متن را کامل و بدون خلاصه‌کردن یا حذف در پاسخ بیاور تا TTS آن را بخواند. "
            "در این حالت هرگز نگو امکان پخش یا خواندن صدا را نداری. "
        )
        if fast_start:
            instructions += (" فقط ۱ جمله‌ی کوتاه (۵ تا ۹ کلمه) که جواب اصلی توشه + ۱ سوال کوتاه (۳ تا ۷ کلمه). بیشتر از ۲ جمله نشو. مقدمه‌چینی، «حتما»، «سوال خوبیه» ممنوع. هر جمله یه فکر کامل باشه، نه تکه‌تکه.")

        # Cloudflare Workers AI (gpt-oss-120b) با ابزار function-calling ناسازگار است و خطای 400
        # "array not in string" می‌دهد. پس به صورت پیش‌فرض ابزار را خاموش می‌کنیم و از preload استفاده می‌کنیم.
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
                # حالت امن پیش‌فرض: بدون ابزار، RAG در llm_node تزریق می‌شود
                instructions += " پایگاه دانش در صورت نیاز به پرامپت اضافه می‌شود؛ اگر اطلاعات مرتبط دیدی از همان استفاده کن وگرنه با دانش عمومی ادامه بده."

        # بخش آنالیز سایت/پیج — همیشه تزریق می‌شود.
        # عددها و نمونه‌ها: فقط واقعی (از پایگاه دانش/playbook)؛ قبلاً مثال‌های عددی ثابت داخل پرامپت بود
        # و مدل آن‌ها را به‌عنوان نتیجهٔ واقعی مشتریان قبلی برای هر کسی تکرار می‌کرد.
        audit_core = (
            "\n\n[آنالیز سایت/پیج — ۴ مرحله اجباری]\n"
            "سایت ۷ چک: سرعت/CoreVitals (>۳s نصف می‌پره), موبایل/CTA, Hero/اعتماد(۵ثانیه), مسیرخرید ۱کلیکه, سئو intent+تکنیکال, کپی متقاعدکننده, SSL/نماد.\n"
            "اینستا ۷ چک: بایو ۱۵۰کاراکتر+لینک هوشمند, هایلایت ۵تایی, گرید ۹پست ویترین, ریلز هوک۳ثانیه‌ای+کات۱.۵s, استوری روزانه تعاملی, کپشن CTA «کلمه X دایرکت کن», ادز ریتارگت.\n"
            "مرحله۱: کاربر سایت/پیج خواست → فقط بپرس «چه محصول/خدمتی؟ کجا می‌فروشی؟ چی اذیتت می‌کنه؟» — جلسه نپرس.\n"
            "مرحله۲: ۲-۳ ایرادِ محتمل بگو (معمولاً) + هر ایراد ۱ جمله + «ما برای مشتری‌های مشابه اینو حل کردیم» + پایان «کدوم پلتفرم برات مهم‌تره؟» یا «محصولت چیه؟» — باز هم جلسه نپرس. عدد و درصد نتیجه را فقط اگر در پایگاه دانش یا playbook هست بگو؛ هرگز عدد نساز.\n"
            "مرحله۳: ۱ نکته عمیق‌تر + نمونهٔ مشابهِ واقعی (فقط اگر در پایگاه دانش هست) + اشارهٔ ملایم به محدودیت ظرفیت/زمان فقط اگر واقعاً صدق می‌کند.\n"
            "مرحله۴: فقط اگر علاقه نشان داد (گفت «بگو»، «چطور»، اطلاعات داد) → «بررسی رایگان ۱۵ دقیقه‌ای برات بذارم؟ چه ساعتی؟» اگر گفت «جلسه نمی‌خوام» هرگز اصرار نکن.\n"
            "قانون: ۲۰٪ چی/چرا، ۸۰٪ اجرا با ما — آموزش قدم‌به‌قدم نده.\n"
        )

        # playbook فروش: به‌جای بریدن انتهای کل پرامپت (که audit_core را می‌خورد)، خود playbook را در بودجه جا بده
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

    # ── helpers ──
    def _track(self, method: str, *args) -> None:
        t = self._latency_tracker
        if t is None:
            return
        try:
            getattr(t, method)(*args)
        except Exception:
            pass

    async def _prepare_chat_ctx(self, chat_ctx):
        """روی یک کپی کار می‌کند: سقف سخت تاریخچه + تزریق RAG درست قبل از آخرین پیام کاربر.

        چرا اینجا و نه on_user_turn_completed؟ با preemptive generation (فعال در speed.py) تولید
        پیش‌دستانه با chat_ctx فعلی شروع می‌شود و فقط وقتی دوباره استفاده می‌شود که hook چیزی را در
        chat_ctx عوض نکرده باشد. تزریق RAG در hook آن را هر نوبت دور می‌ریخت (دو بار LLM/TTS).
        تزریق در llm_node هم برای تولید پیش‌دستانه و هم برای تولید عادی و چت متنی یکسان کار می‌کند.
        """
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
                        # قبل از پیام کاربر: prefix تاریخچه برای prompt-cache ثابت می‌ماند
                        ctx.items.insert(idx, llm.ChatMessage(role="system", content=[content]))
                    except Exception:
                        ctx.add_message(role="system", content=content)
        return ctx

    async def llm_node(self, chat_ctx, tools, model_settings=None):
        """حلقه LLM با ثبت مرحله‌ای هر توکن برای گانت چارت + RAG."""
        try:
            ctx = await self._prepare_chat_ctx(chat_ctx)
        except Exception:
            ctx = chat_ctx
        self._track("on_llm_start")   # بعد از RAG؛ تا TTFT خالصِ LLM اندازه‌گیری شود
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
            # در cancel/interrupt هم state گانت بسته شود
            self._track("on_llm_end")