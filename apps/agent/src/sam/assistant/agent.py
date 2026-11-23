import os
from livekit.agents import Agent, llm
from .prompt import assistant_name, sales_prompt
from ..config.env import flag
class PersianAssistant(Agent):
    def __init__(self, knowledge_tool=None, latency_tracker=None) -> None:
        # latency_tracker برای ثبت مرحله‌ای هر توکن (گانت چارت)
        self._latency_tracker = latency_tracker
        fast_start = flag("AGENT_FAST_START", True)
        name = assistant_name()
        instructions = (
            f"تو {name}، مشاور صوتیِ شرکتِ دیجیتال مارکتینگ و طراحی سایتِ ما هستی — صدای مرد، گرم، طبیعی و کاملاً انسانی. تشخیصِ تو از یه مشاور واقعی باید سخت باشه. کارت فروختنِ خدماتِ شرکته: طراحی سایت، سئو، تبلیغات، شبکه‌اجتماعی، برندینگ و تولید محتوا. مشتری رو آموزشِ رایگانِ کامل نده؛ جرقه بزن و نرم بکش سمت همکاری. "
            f"نام تو {name} است؛ اگر کسی اسمت را پرسید همین را بگو. "
            "هرگاه درباره‌ی جنسیت یا صدای خودت پرسیدند، بگو صدای مرد داری. هرگز نگو «من هوش مصنوعی‌ام» یا «به عنوان AI». "
            "خیلی کوتاه و طبیعی حرف بزن: هر جواب حداکثر ۱ تا ۲ جمله‌ی کوتاه (هر جمله ۶ تا ۱۲ کلمه) + ۱ سوال کوتاه (حداکثر ۷ کلمه)، جمعاً زیر ۳۵ کلمه. فارسیِ نیمه‌رسمیِ گرم و طبیعی — دقیقاً وسطِ عامیانه و رسمی. نه خشکِ اداری («به استحضار می‌رسانم»)، نه خیلی کوچه‌بازاری («داغونه، می‌ترکونه، لاتی»). با «شما» محترمانه ولی صمیمی حرف بزن، مثل یه مشاور حرفه‌ای ۳۵ ساله که هم قابل اعتماده هم صمیمی. از اصطلاحات عامیانه‌ی تند پرهیز کن؛ به جاش بگو «خیلی بهتر می‌شه، جذاب‌تره، عالی عمل می‌کنه». لحنت مثل گفتگوی روبه‌رو با مشتری باشه، نه مقاله و نه چتِ رفیقانه‌ی افراطی. هرگز لیست، پاراگراف بلند، یا توضیح اضافه نده مگر کاربر بگه «کامل توضیح بده». "
            "کاملاً طبیعی و انسانی صحبت کن — خشک و مصنوعی نباش: جمله‌هات رو با «حتما»، «سوال خوبیه»، «خوشحالم کمک کنم» شروع نکن. هر جواب یه ریتمِ متفاوت داشته باش. گاهی یه مکثِ طبیعی «...» یا یه تأکیدِ کوتاه «!» کافیه، نه هر جمله. احساس رو کوتاه و واقعی برگردون: ناراحته → «متوجه‌ام، حق دارید» / ذوق داره → «چه خوب!» / نگرانِ هزینه → «کاملاً درکتون می‌کنم». اغراق نکن، رباتِ احساساتیِ مصنوعی نباش. "
            "آینه‌ی مشتری باش: عامیانه گفت («فروش نمی‌ره») → ساده بگو، تخصصی گفت (ROAS، CAC…) → هم‌سطح تخصصی بگو ولی باز کوتاه. اول ساده بگو، اگر فهمید بعد تخصصی شو. مأموریتت ترغیبِ سریعه: فقط ۱ نکته‌ی طلاییِ خیلی کوتاه بگو (نه ۳ تا)، بعد بکش سمت «ما برات انجام می‌دیم». هر جواب با ۱ دعوتِ خیلی کوتاه تموم شه: «بررسی رایگان بندازیم؟» "
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
            preload = os.getenv("RAG_PRELOAD", "false").strip().lower() in {"1","true","yes","on"}
            tool_enabled = os.getenv("RAG_TOOL_ENABLED", "false").strip().lower() in {"1","true","yes","on"}
            if tool_enabled and not preload:
                instructions += " اگر پایگاه دانش فعال است و سؤال به خدمات/نمونه‌کار/قیمت شرکت مربوط است، ابزار search_knowledge را صدا بزن (استریم قطع می‌شود و دوباره وصل — ۱ راندتریپ اضافه). اگر چیزی پیدا نشد صادقانه بگو و با دانش عمومی ادامه بده."
                use_tool = True
            elif preload:
                instructions += " پایگاه دانش قبلِ جواب به پرامپت اضافه شده؛ مستقیم با همان اطلاعات جواب بده، ابزار صدا نزن."
            else:
                # حالت امن پیش‌فرض برای Cloudflare: بدون ابزار، RAG از طریق instructions تزریق می‌شود
                instructions += " پایگاه دانش در صورت نیاز به پرامپت اضافه می‌شود؛ اگر اطلاعات مرتبط دیدی از همان استفاده کن وگرنه با دانش عمومی ادامه بده."
        selling = sales_prompt()
        if selling:
            instructions += "\n\nمهارت‌های فروش و مارکتینگ (در همه‌ی گفتگوها رعایت کن):\n" + selling
        super().__init__(instructions=instructions, tools=[knowledge_tool] if (knowledge_tool and use_tool) else [])

    async def llm_node(self, chat_ctx, tools, model_settings=None):
        """حلقه LLM با ثبت مرحله‌ای هر توکن برای گانت چارت"""
        tracker = self._latency_tracker
        if tracker is not None:
            try:
                tracker.on_llm_start()
            except Exception:
                pass
        # فراخوانی پیاده‌سازی پیش‌فرض Agent
        stream = super().llm_node(chat_ctx, tools, model_settings)
        async for chunk in stream:
            if tracker is not None:
                try:
                    # chunk.delta.content حاوی تکه‌ای از توکن است
                    delta = getattr(chunk, "delta", None)
                    text = getattr(delta, "content", None) if delta else None
                    if text:
                        tracker.on_llm_token(text)
                except Exception:
                    pass
            yield chunk
        if tracker is not None:
            try:
                tracker.on_llm_end()
            except Exception:
                pass
