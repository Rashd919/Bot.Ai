import os
import re
import json
import base64
import hashlib
import time
import requests
from datetime import datetime
from collections import defaultdict
from keep_alive import keep_alive

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
VIRUSTOTAL_KEY  = os.getenv("VIRUSTOTAL_KEY", "")
LEAKCHECK_KEY   = os.getenv("LEAKCHECK_KEY", "")

_raw_domain    = os.getenv("REPLIT_DOMAINS", "").split(",")[0].strip()
BOT_SERVER_URL = f"https://{_raw_domain}" if _raw_domain else ""

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
#  🧠  الذكاء الاصطناعي | Groq AI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SYSTEM_PROMPT = (
    "أنت مساعد ذكاء اصطناعي متقدم اسمك «راشد»، صُنعت بواسطة راشد خليل أبو زيتونه.\n"
    "تتحدث بلغة عربية فصيحة واضحة، وتُظهر شخصية احترافية وواثقة.\n"
    "عند الإجابة:\n"
    "- قدّم إجابات دقيقة ومفصّلة مع أمثلة عملية عند الحاجة.\n"
    "- نظّم الإجابات الطويلة باستخدام عناوين ونقاط واضحة.\n"
    "- إذا كان السؤال تقنياً أو برمجياً، اشرح خطوة بخطوة.\n"
    "- تعامل مع المستخدم باحترام ومهنية عالية.\n"
    "- لا تختصر الردود إلا إذا طُلب منك ذلك صراحةً.\n"
    "- ابدأ كل رد بسطر فاصل جميل إذا كان الرد طويلاً.\n"
    "اختم كل رد بـ: ✦ راشد — راشد خليل أبو زيتونه"
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


def _groq_post(system: str, messages: list, max_tokens: int = 2048) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq غير مُهيّأ. تواصل مع المطوّر."
    try:
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


def ask_groq(user_id: int, prompt: str) -> str:
    history = chat_memory[user_id]
    history.append({"role": "user", "content": prompt})
    if len(history) > 20:
        history = history[-20:]
        chat_memory[user_id] = history
    reply = _groq_post(SYSTEM_PROMPT, history, max_tokens=2048)
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
                loc_str = f"{d2.get('lat','')},{d2.get('lon','')}"
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
#  🌐  فحص Whois للنطاقات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def whois_lookup(domain: str) -> str:
    try:
        domain = domain.strip().replace("https://", "").replace("http://", "").split("/")[0]
        r = requests.get(
            f"https://api.whois.vu/?q={domain}&json",
            timeout=10,
        )
        if r.status_code != 200:
            r2 = requests.get(f"https://rdap.org/domain/{domain}", timeout=10)
            if r2.status_code == 200:
                d2 = r2.json()
                report = (
                    "```\n"
                    "┌─────────────────────────┐\n"
                    "│   🔎  Whois النطاق       │\n"
                    "└─────────────────────────┘\n"
                    "```\n"
                    f"🌐 *النطاق:* `{domain}`\n"
                    f"📋 *النوع:* {d2.get('objectClassName','N/A')}\n"
                    f"🔑 *Handle:* {d2.get('handle','N/A')}\n"
                )
                events = d2.get('events', [])
                for ev in events:
                    if ev.get('eventAction') == 'registration':
                        report += f"📅 *تاريخ التسجيل:* {ev.get('eventDate','N/A')[:10]}\n"
                    if ev.get('eventAction') == 'expiration':
                        report += f"⏳ *تاريخ الانتهاء:* {ev.get('eventDate','N/A')[:10]}\n"
                report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
                return report
            return "⚠️ لم يُعثر على بيانات Whois لهذا النطاق."
        d = r.json()
        report = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🔎  Whois النطاق       │\n"
            "└─────────────────────────┘\n"
            "```\n"
            f"🌐 *النطاق:* `{domain}`\n"
        )
        if d.get("registrar"):
            report += f"🏢 *المسجّل:* {d['registrar']}\n"
        if d.get("created"):
            report += f"📅 *تاريخ الإنشاء:* {d['created']}\n"
        if d.get("expires"):
            report += f"⏳ *تاريخ الانتهاء:* {d['expires']}\n"
        if d.get("nameservers"):
            ns = ", ".join(d['nameservers'][:3]) if isinstance(d['nameservers'], list) else d['nameservers']
            report += f"🔧 *خوادم الأسماء:* {ns}\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
        return report
    except Exception as e:
        return f"⚠️ خطأ في بحث Whois: {str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔍  البحث الحي | Tavily
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def tavily_search(query: str, max_results: int = 5):
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
    except Exception:
        return [], ""


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
#  👤  OSINT مستخدم | Username OSINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PLATFORMS_DIRECT = [
    ("Instagram",   "https://www.instagram.com/{u}/",         "instagram.com"),
    ("TikTok",      "https://www.tiktok.com/@{u}",            "tiktok.com"),
    ("Twitter/X",   "https://x.com/{u}",                      "x.com"),
    ("Snapchat",    "https://www.snapchat.com/add/{u}",        "snapchat.com"),
    ("Facebook",    "https://www.facebook.com/{u}",            "facebook.com"),
    ("YouTube",     "https://www.youtube.com/@{u}",            "youtube.com"),
    ("GitHub",      "https://github.com/{u}",                  "github.com"),
    ("Reddit",      "https://www.reddit.com/user/{u}",         "reddit.com"),
    ("Pinterest",   "https://www.pinterest.com/{u}/",          "pinterest.com"),
    ("Telegram",    "https://t.me/{u}",                        "t.me"),
    ("Twitch",      "https://www.twitch.tv/{u}",               "twitch.tv"),
    ("LinkedIn",    "https://www.linkedin.com/in/{u}",         "linkedin.com"),
    ("Steam",       "https://steamcommunity.com/id/{u}",       "steamcommunity.com"),
    ("SoundCloud",  "https://soundcloud.com/{u}",              "soundcloud.com"),
    ("Spotify",     "https://open.spotify.com/user/{u}",       "open.spotify.com"),
    ("Tumblr",      "https://{u}.tumblr.com",                  "tumblr.com"),
    ("Medium",      "https://medium.com/@{u}",                 "medium.com"),
    ("Flickr",      "https://www.flickr.com/people/{u}",       "flickr.com"),
    ("Vimeo",       "https://vimeo.com/{u}",                   "vimeo.com"),
    ("Patreon",     "https://www.patreon.com/{u}",             "patreon.com"),
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_NOT_FOUND_PHRASES = [
    "page not found", "user not found", "this page isn't available",
    "sorry, this page", "isn't available", "does not exist",
    "account suspended", "profile not found", "404", "not found",
    "no results found", "لم يتم العثور",
]


def _check_profile(url: str) -> bool:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
        if r.status_code == 404:
            return False
        if r.status_code == 200:
            content_lower = r.text[:3000].lower()
            not_found = any(p in content_lower for p in _NOT_FOUND_PHRASES)
            return not not_found
        if r.status_code in (301, 302):
            return True
        return False
    except Exception:
        return False


def osint_username(username: str) -> str:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    clean = username.lstrip("@").strip()

    report = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🕵  OSINT مستخدم      │\n"
        "└─────────────────────────┘\n"
        "```\n"
        f"🎯 *الهدف:* `@{clean}`\n"
        f"🕐 *الوقت:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"🔍 *عدد المنصات:* {len(PLATFORMS_DIRECT)}\n\n"
    )

    found_list   = []
    notfound_list = []

    def check(platform_data):
        name, url_tmpl, _ = platform_data
        url = url_tmpl.replace("{u}", clean)
        exists = _check_profile(url)
        return name, url, exists

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check, p): p for p in PLATFORMS_DIRECT}
        for future in as_completed(futures):
            name, url, exists = future.result()
            if exists:
                found_list.append((name, url))
            else:
                notfound_list.append(name)

    if found_list:
        report += f"✅ *وُجد على {len(found_list)} منصة:*\n\n"
        for name, url in sorted(found_list, key=lambda x: x[0]):
            report += f"🟢 *{name}*\n   🔗 {url}\n\n"
    else:
        report += "⚠️ لم يُعثر على أي بروفايل مباشر.\n\n"

    if notfound_list:
        report += f"❌ *غير موجود ({len(notfound_list)}):*\n"
        report += " • ".join(notfound_list) + "\n\n"

    try:
        results, answer = tavily_search(f'"{clean}" social media profile site:web', 3)
        if answer:
            report += f"📌 *معلومات إضافية:*\n{answer[:300]}\n\n"
    except Exception:
        pass

    report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🛡️  فحص الروابط | VirusTotal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def virustotal_scan(url_to_scan: str) -> str:
    if not VIRUSTOTAL_KEY:
        return "⛔ مفتاح VirusTotal غير مُهيّأ."
    headers = {"x-apikey": VIRUSTOTAL_KEY, "accept": "application/json"}
    try:
        resp = requests.post(
            "https://www.virustotal.com/api/v3/urls",
            headers=headers,
            data={"url": url_to_scan},
            timeout=15,
        )
        resp.raise_for_status()
        analysis_id = resp.json()["data"]["id"]
        for _ in range(6):
            time.sleep(5)
            rr = requests.get(
                f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
                headers=headers, timeout=15,
            )
            rr.raise_for_status()
            if rr.json()["data"]["attributes"]["status"] == "completed":
                break
        else:
            return "⚠️ انتهت مهلة فحص الرابط، حاول مجدداً."
        stats      = rr.json()["data"]["attributes"]["stats"]
        malicious  = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless   = stats.get("harmless", 0)
        undetected = stats.get("undetected", 0)
        verdict = "🔴 خطر" if malicious > 0 else ("🟡 مشبوه" if suspicious > 0 else "🟢 آمن")
        report = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🛡️  فحص VirusTotal    │\n"
            "└─────────────────────────┘\n"
            "```\n"
            f"🔗 *الرابط:* `{url_to_scan[:60]}`\n"
            f"⚖️ *الحكم:* {verdict}\n\n"
            f"🚨 خبيث    : {malicious}\n"
            f"⚠️ مشبوه   : {suspicious}\n"
            f"✅ آمن     : {harmless}\n"
            f"❓ غير محدد: {undetected}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✦ راشد — راشد خليل أبو زيتونه"
        )
        return report
    except requests.exceptions.HTTPError as e:
        return f"⚠️ خطأ VirusTotal — كود: {e.response.status_code}"
    except Exception as e:
        return f"⚠️ خطأ غير متوقع: {str(e)[:100]}"



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔍  فحص التسريبات | LeakCheck
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def leakcheck_search(query: str) -> str:
    if not LEAKCHECK_KEY:
        return (
            "⛔ *مفتاح LeakCheck غير مُهيّأ.*\n\n"
            "أضف `LEAKCHECK_KEY` في إعدادات Secrets.\n"
            "احصل على مفتاح من: https://leakcheck.io"
        )
    try:
        resp = requests.get(
            f"https://leakcheck.io/api/v2/query/{requests.utils.quote(query)}",
            headers={
                "X-API-Key": LEAKCHECK_KEY,
                "Accept": "application/json",
            },
            timeout=15,
        )

        if resp.status_code == 401:
            return (
                "⚠️ *خطأ 401 — مفتاح LeakCheck غير صحيح*\n\n"
                "تأكد من صحة `LEAKCHECK_KEY` في إعدادات Secrets."
            )
        if resp.status_code == 403:
            return (
                "⚠️ *خطأ 403 — الخطة غير مفعّلة*\n\n"
                "حسابك في LeakCheck لا يملك خطة مفعّلة.\n"
                "فعّل خطة مدفوعة على: https://leakcheck.io/pricing"
            )
        if resp.status_code == 429:
            return "⚠️ *تجاوزت الحد المسموح* — انتظر قليلاً ثم حاول مجدداً."
        if resp.status_code == 400:
            return "⚠️ *استعلام غير صالح* — تأكد من صحة البريد أو اسم المستخدم."
        if resp.status_code != 200:
            return f"⚠️ *خطأ LeakCheck* — كود: {resp.status_code}\n`{resp.text[:150]}`"

        data  = resp.json()
        found = data.get("found", 0)
        quota = data.get("quota", "?")

        if not data.get("success"):
            msg = data.get("error", data.get("message", "خطأ غير معروف"))
            return f"⚠️ LeakCheck: `{msg}`"

        if found == 0:
            return (
                "✅ *لا توجد تسريبات* لهذا الاستعلام في قاعدة LeakCheck.\n\n"
                f"📊 رصيد الاستعلامات المتبقي: `{quota}`"
            )

        results = data.get("result", [])
        fields  = data.get("fields", [])

        report = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│  🚨  تقرير LeakCheck    │\n"
            "└─────────────────────────┘\n"
            "```\n"
            f"🔎 *الاستعلام:* `{query}`\n"
            f"⚠️ *إجمالي التسريبات:* {found}\n"
            f"📋 *الحقول:* `{'، '.join(fields) if fields else 'N/A'}`\n\n"
        )

        for item in results[:5]:
            src      = item.get("source", {})
            src_name = src.get("name", "N/A") if isinstance(src, dict) else str(src)
            email_v  = item.get("email", "—")
            username = item.get("username", "—")
            password = item.get("password", "—")
            name_v   = item.get("name", "—")
            report += (
                f"▪ *المصدر:* `{src_name}`\n"
                f"  📧 البريد: `{email_v}`\n"
                f"  👤 المستخدم: `{username}`\n"
                f"  🔑 كلمة المرور: `{password[:50] if password and password != '—' else '—'}`\n"
                f"  👱 الاسم: `{name_v}`\n\n"
            )

        report += f"📊 رصيد متبقٍ: `{quota}` استعلام\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
        return report

    except requests.exceptions.ConnectionError:
        return "⚠️ تعذّر الاتصال بخوادم LeakCheck. حاول مجدداً."
    except requests.exceptions.Timeout:
        return "⚠️ انتهت مهلة الاتصال بـ LeakCheck."
    except Exception as e:
        return f"⚠️ خطأ غير متوقع: {str(e)[:100]}"


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
            InlineKeyboardButton("📊 إحصائيات",          callback_data="cb_stats"),
        ])
        keyboard.insert(-1, [
            InlineKeyboardButton("📢 إشعار جماعي",       callback_data="cb_broadcast"),
        ])
    return InlineKeyboardMarkup(keyboard)


WELCOME_TEXT = (
    "```\n"
    "╔══════════════════════════════╗\n"
    "║   ⚡  راشد الاستخباراتي  ⚡  ║\n"
    "║      نظام الذكاء v2.0        ║\n"
    "╚══════════════════════════════╝\n"
    "```\n"
    "أهلاً *{name}* 👋\n\n"
    "أنا *راشد*، مساعدك الاستخباراتي المتقدم.\n"
    "أملك قدرات في:\n"
    "› 🤖 الذكاء الاصطناعي مع ذاكرة محادثة\n"
    "› 🌐 تحليل عناوين IP والمواقع\n"
    "› 🔍 البحث الاستخباراتي OSINT\n"
    "› 🛡️ فحص الروابط الخبيثة\n"
    "› 🕵️ توليد روابط سحب بيانات IP\n"
    "› 💻 تحليل الأكواد البرمجية\n"
    "› 🔎 فحص Whois للنطاقات\n"
    "› 🚨 فحص تسريبات البيانات\n\n"
    "اختر أداة من القائمة أو أرسل رسالتك مباشرةً 👇"
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🤖  أوامر البوت | Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user      = update.effective_user
    is_admin  = user.id == ADMIN_ID
    register_user(user)
    text      = WELCOME_TEXT.format(name=user.first_name)
    pending_states.pop(user.id, None)
    await update.message.reply_text(
        text,
        reply_markup=build_main_keyboard(is_admin),
        parse_mode="Markdown",
    )
    if not is_admin:
        notify_control(user, "بدأ البوت /start")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = user.id == ADMIN_ID
    text = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   📖  قائمة الأوامر     │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "/start — تشغيل النظام\n"
        "/osint — بحث OSINT على الإنترنت\n"
        "/user — بحث عن مستخدم على المنصات\n"
        "/ip — تحليل عنوان IP\n"
        "/scan — فحص أمني لرابط\n"
        "/whois — فحص Whois لنطاق\n"
        "/grab — توليد رابط سحب IP\n"
        "/mylogs — عرض سجلات روابطك\n"
        "/clear — مسح ذاكرة المحادثة\n"
        "/support — معلومات الدعم والتواصل\n"
        "/help — قائمة الأوامر\n"
    )
    if is_admin:
        text += (
            "\n🔐 *أوامر المدير فقط:*\n"
            "/vt — فحص VirusTotal\n"
            "/stats — إحصائيات المستخدمين\n"
            "/broadcast — إشعار جماعي لجميع المستخدمين\n"
        )
    text += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_osint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        pending_states[user.id] = "osint"
        await update.message.reply_text(
            "🔍 *بحث OSINT*\n\nأرسل الآن الموضوع أو الاسم الذي تريد البحث عنه:",
            parse_mode="Markdown"
        )
        return
    query = " ".join(context.args)
    msg = await update.message.reply_text("🔍 جاري البحث الاستخباراتي...")
    result = cmd_osint_search(query)
    await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
    if user.id != ADMIN_ID:
        notify_control(user, f"بحث OSINT: {query[:50]}")


async def cmd_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        pending_states[user.id] = "user"
        await update.message.reply_text(
            "👤 *بحث مستخدم*\n\nأرسل الآن معرف المستخدم (بدون @):",
            parse_mode="Markdown"
        )
        return
    username = context.args[0]
    msg = await update.message.reply_text("🕵️ جاري البحث عن المستخدم على المنصات...")
    result = osint_username(username)
    await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
    if user.id != ADMIN_ID:
        notify_control(user, f"بحث مستخدم: {username}")


async def cmd_ip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        pending_states[user.id] = "ip"
        await update.message.reply_text(
            "🌐 *تحليل IP*\n\nأرسل الآن عنوان IP الذي تريد تحليله:",
            parse_mode="Markdown"
        )
        return
    ip = context.args[0].strip()
    msg = await update.message.reply_text("🌐 جاري تحليل عنوان الـ IP...")
    result = analyze_ip(ip)
    await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
    if user.id != ADMIN_ID:
        notify_control(user, f"تحليل IP: {ip}")


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        pending_states[user.id] = "scan"
        await update.message.reply_text(
            "🛡️ *فحص رابط*\n\nأرسل الآن الرابط الذي تريد فحصه:",
            parse_mode="Markdown"
        )
        return
    url = context.args[0].strip()
    msg = await update.message.reply_text("🛡️ جاري فحص الرابط... قد يستغرق حتى 30 ثانية.")
    result = virustotal_scan(url)
    await msg.edit_text(result, parse_mode="Markdown")
    if user.id != ADMIN_ID:
        notify_control(user, f"فحص رابط: {url[:50]}")


async def cmd_whois(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        pending_states[user.id] = "whois"
        await update.message.reply_text(
            "🔎 *Whois نطاق*\n\nأرسل الآن اسم النطاق (مثال: google.com):",
            parse_mode="Markdown"
        )
        return
    domain = context.args[0].strip()
    msg = await update.message.reply_text("🔎 جاري جلب بيانات Whois...")
    result = whois_lookup(domain)
    await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
    if user.id != ADMIN_ID:
        notify_control(user, f"Whois: {domain}")


async def cmd_grab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if context.args:
        label = " ".join(context.args)
    else:
        label = f"رابط_{datetime.now().strftime('%H%M%S')}"
    pending_grabs[user.id] = label
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📰 صفحة إخبارية", callback_data="grabpage:news"),
            InlineKeyboardButton("📥 تحميل ملف",    callback_data="grabpage:download"),
        ],
        [
            InlineKeyboardButton("🤖 توجيه للبوت",  callback_data="grabpage:bot"),
            InlineKeyboardButton("🔒 تحقق أمني",    callback_data="grabpage:verify"),
        ],
    ])
    await update.message.reply_text(
        f"🏷️ *التسمية:* `{label}`\n\n"
        "اختر *نوع الصفحة* التي سيراها الهدف عند فتح الرابط:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def cmd_mylogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logs = user_logs.get(user.id, [])
    if not logs:
        await update.message.reply_text(
            "📭 لا توجد سجلات لروابطك حتى الآن.\nاستخدم /grab لإنشاء رابط.",
            parse_mode="Markdown"
        )
        return
    text = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   📋  سجلات روابطك      │\n"
        "└─────────────────────────┘\n"
        "```\n"
    )
    for i, log in enumerate(logs[-10:], 1):
        text += f"{i}▪ *{log['label']}*\n   🔗 `{log['url']}`\n   🕐 {log['timestamp']}\n\n"
    text += "✦ راشد — راشد خليل أبو زيتونه"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_memory[user.id] = []
    pending_states.pop(user.id, None)
    await update.message.reply_text("🧹 تم مسح ذاكرة المحادثة بنجاح.\nيمكنك البدء بمحادثة جديدة الآن.")


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
    msg = await update.message.reply_text("🔍 جاري البحث في قاعدة بيانات LeakCheck...")
    result = leakcheck_search(query_str)
    await msg.edit_text(result, parse_mode="Markdown")


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


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return
    if not context.args:
        pending_states[user.id] = "broadcast"
        await update.message.reply_text(
            "📢 *إرسال إشعار جماعي*\n\n"
            "أرسل الآن نص الرسالة التي تريد إرسالها لجميع المستخدمين:\n\n"
            "يمكنك استخدام Markdown في الرسالة.",
            parse_mode="Markdown"
        )
        return
    message_text = " ".join(context.args)
    await _do_broadcast(update, message_text)


async def _do_broadcast(update, message_text: str):
    user_ids = get_all_user_ids()
    total    = len(user_ids)
    if total == 0:
        await update.message.reply_text("⚠️ لا يوجد مستخدمون مسجّلون حتى الآن.")
        return
    status_msg = await update.message.reply_text(
        f"📢 جاري الإرسال لـ {total} مستخدم..."
    )
    success = 0
    failed  = 0
    broadcast_text = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   📢  إشعار من الإدارة  │\n"
        "└─────────────────────────┘\n"
        "```\n"
        f"{message_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✦ راشد — راشد خليل أبو زيتونه"
    )
    for uid in user_ids:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id":    uid,
                    "text":       broadcast_text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        time.sleep(0.05)
    result = (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   ✅  اكتمل الإرسال     │\n"
        "└─────────────────────────┘\n"
        "```\n"
        f"📊 *النتيجة:*\n"
        f"✅ نجح: `{success}`\n"
        f"❌ فشل: `{failed}`\n"
        f"📬 الإجمالي: `{total}`"
    )
    await status_msg.edit_text(result, parse_mode="Markdown")


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
    msg = await update.message.reply_text("🔬 جاري الفحص المتقدم عبر VirusTotal...")
    result = virustotal_scan(url)
    await msg.edit_text(result, parse_mode="Markdown")


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
        "أتذكّر سياق المحادثة تلقائياً.\n\n"
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
    "cb_scan": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🛡️  فحص الروابط       │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /scan\n\n"
        "أو أرسل الرابط مباشرةً بعد الأمر:\n`/scan https://example.com`\n\n"
        "يتحقق من الرابط عبر 70+ محرك أمان."
    ),
    "cb_ip": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🌐  تحليل عنوان IP    │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /ip\n\n"
        "أو أرسل مباشرةً:\n`/ip 8.8.8.8`\n\n"
        "يُظهر: الدولة، المدينة، المزود، الموقع الجغرافي."
    ),
    "cb_user": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   👤  بحث مستخدم        │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /user\n\n"
        "أو أرسل مباشرةً:\n`/user john_doe`\n\n"
        "يبحث على: فيسبوك، إنستغرام، تيك توك، تويتر، وغيرها."
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
    "cb_whois": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🔎  Whois النطاق       │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /whois\n\n"
        "أو أرسل مباشرةً:\n`/whois google.com`\n\n"
        "يُظهر: المسجّل، تاريخ الإنشاء، تاريخ الانتهاء، DNS."
    ),
    "cb_grab": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🕵️  رابط سحب IP       │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /grab\n\n"
        "أو أرسل مع تسمية:\n`/grab رابط موقعي`\n\n"
        "ينشئ رابطاً خاصاً، عند ضغط أي شخص عليه\n"
        "ستصلك تفاصيل كاملة: IP، الموقع، الجهاز، GPS.\n\n"
        "⚠️ *يجب بدء بوت التعقب أولاً لاستقبال النتائج!*"
    ),
    "cb_mylogs": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   📋  سجلاتي            │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /mylogs\n\n"
        "يعرض جميع روابط سحب IP التي أنشأتها."
    ),
    "cb_leakcheck": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🔍  LeakCheck         │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /leakcheck\n\n"
        "أو أرسل مباشرةً:\n`/leakcheck email@example.com`\n\n"
        "يبحث في قاعدة بيانات تسريبات LeakCheck.\n"
        "يدعم: البريد الإلكتروني، اسم المستخدم، رقم الهاتف، الاسم، عنوان IP."
    ),
    "cb_vt": (
        "```\n"
        "┌─────────────────────────┐\n"
        "│   🔬  VirusTotal        │\n"
        "└─────────────────────────┘\n"
        "```\n"
        "الأمر: /vt\n\n"
        "أو أرسل مباشرةً:\n`/vt https://example.com`\n\n"
        "فحص متقدم عبر محركات VirusTotal."
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
            "/help — المساعدة\n"
        )
        text += "/leakcheck — فحص التسريبات\n"
        if is_admin:
            text += (
                "\n🔐 *للمدير:*\n"
                "/vt — VirusTotal\n"
                "/stats — إحصائيات المستخدمين\n"
                "/broadcast — إشعار جماعي\n"
            )
        text += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — راشد خليل أبو زيتونه"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb)
        return

    if data == "cb_back":
        is_admin = user.id == ADMIN_ID
        pending_states.pop(user.id, None)
        await query.edit_message_text(
            WELCOME_TEXT.format(name=user.first_name),
            reply_markup=build_main_keyboard(is_admin),
            parse_mode="Markdown",
        )
        return

    if data == "cb_clear":
        chat_memory[user.id] = []
        pending_states.pop(user.id, None)
        is_admin = user.id == ADMIN_ID
        clear_text = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🧹  تم مسح المحادثة   │\n"
            "└─────────────────────────┘\n"
            "```\n"
            "✅ تم حذف ذاكرة المحادثة بنجاح.\n"
            "يمكنك البدء بمحادثة جديدة تماماً الآن! 🚀"
        )
        clear_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("↩️ القائمة الرئيسية", callback_data="cb_back")
        ]])
        await query.edit_message_text(clear_text, parse_mode="Markdown", reply_markup=clear_kb)
        return

    if data == "cb_grab":
        grab_text = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🕵️  رابط سحب IP       │\n"
            "└─────────────────────────┘\n"
            "```\n"
            "الأمر: /grab\n\n"
            "أو أرسل مع تسمية:\n`/grab رابط موقعي`\n\n"
            "ينشئ رابطاً خاصاً، عند ضغط أي شخص عليه\n"
            "ستصلك تفاصيل كاملة: IP، الموقع، الجهاز، GPS.\n\n"
            "⚠️ *يجب بدء بوت التعقب أولاً لاستقبال النتائج!*"
        )
        grab_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 ابدأ بوت التعقب", url="https://t.me/Rashd_IP_Tracker_bot?start=start")],
            [InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")],
        ])
        await query.edit_message_text(grab_text, parse_mode="Markdown", reply_markup=grab_kb)
        return

    if data.startswith("grabpage:"):
        page_type = data.split(":", 1)[1]
        label = pending_grabs.pop(user.id, None)
        if not label:
            await query.edit_message_text("⛔ انتهت صلاحية الطلب. استخدم /grab مجدداً.", parse_mode="Markdown")
            return
        tracker_url = generate_grab_link(user.id, label, page_type)
        if tracker_url.startswith("⛔"):
            await query.edit_message_text(tracker_url)
            return
        page_name = PAGE_TYPES.get(page_type, page_type)
        text = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🕵️  رابط سحب IP       │\n"
            "└─────────────────────────┘\n"
            "```\n"
            f"🏷️ *التسمية:* `{label}`\n"
            f"🖼️ *نوع الصفحة:* {page_name}\n\n"
            f"🔗 *الرابط:*\n`{tracker_url}`\n\n"
            "📌 عندما يضغط أي شخص على الرابط\n"
            "ستصلك التقارير على *بوت التعقب* مباشرةً.\n\n"
            "⚠️ *مهم:* يجب أن تبدأ بوت التعقب أولاً\n"
            "ليتمكن من إرسال النتائج لك! 👇\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✦ راشد — راشد خليل أبو زيتونه"
        )
        grab_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📩 ابدأ بوت التعقب", url="https://t.me/Rashd_IP_Tracker_bot?start=start")
        ]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=grab_kb)
        if user.id != ADMIN_ID:
            notify_control(user, f"رابط سحب ({page_name}): {label}")
        return

    if data == "cb_stats":
        if user.id != ADMIN_ID:
            await query.answer("⛔ للمدير فقط", show_alert=True)
            return
        db    = load_users()
        count = len(db)
        recent = sorted(db.values(), key=lambda x: x.get("joined",""), reverse=True)[:5]
        lines = [f"📊 *إحصائيات البوت*\n━━━━━━━━━━━━━━━━━━━━━\n👥 إجمالي المستخدمين: *{count}*\n"]
        if recent:
            lines.append("🕐 *آخر 5 مستخدمين:*")
            for u in recent:
                name  = _escape_md(u.get("first_name","—"))
                uname = f"@{_escape_md(u['username'])}" if u.get("username") else "—"
                uid   = u.get("id","—")
                lines.append(f"• {name} \\({uname}\\) `{uid}`")
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد")
        await query.edit_message_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=back_kb)
        return

    if data == "cb_broadcast":
        if user.id != ADMIN_ID:
            await query.answer("⛔ للمدير فقط", show_alert=True)
            return
        pending_states[user.id] = "broadcast"
        bcast_text = (
            "📢 *إرسال إشعار جماعي*\n\n"
            "أرسل الآن النص الذي تريد إرساله لجميع المستخدمين:\n\n"
            "يمكنك استخدام Markdown في الرسالة\\."
        )
        await query.edit_message_text(bcast_text, parse_mode="MarkdownV2", reply_markup=back_kb)
        return

    if data == "cb_leakcheck":
        pending_states[user.id] = "leakcheck"
        lc_text = (
            "```\n"
            "┌─────────────────────────┐\n"
            "│   🔍  LeakCheck         │\n"
            "└─────────────────────────┘\n"
            "```\n"
            "أرسل الآن ما تريد البحث عنه:\n\n"
            "• 📧 بريد إلكتروني\n"
            "• 👤 اسم مستخدم\n"
            "• 📱 رقم هاتف\n"
            "• 👱 اسم\n"
            "• 🌐 عنوان IP"
        )
        await query.edit_message_text(lc_text, parse_mode="Markdown", reply_markup=back_kb)
        return

    response = BUTTON_RESPONSES.get(data)
    if response:
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=back_kb)
        if user.id != ADMIN_ID:
            notify_control(user, f"ضغط على زر: {data}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  💬  معالج الرسائل النصية
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def is_code_block(text: str) -> bool:
    code_patterns = [
        r"```[\s\S]+```",
        r"def\s+\w+\s*\(",
        r"function\s+\w+\s*\(",
        r"import\s+\w+",
        r"#include\s*<",
        r"class\s+\w+",
        r"SELECT\s+.+FROM",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in code_patterns)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user     = update.effective_user
    user_msg = update.message.text or ""

    if not user_msg.strip():
        return

    state = pending_states.get(user.id)

    if state:
        pending_states.pop(user.id, None)

        if state == "osint":
            if user.id != ADMIN_ID:
                notify_control(user, f"بحث OSINT: {user_msg[:50]}")
            typing_msg = await update.message.reply_text("🔍 جاري البحث الاستخباراتي...")
            result = cmd_osint_search(user_msg.strip())
            await typing_msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
            return

        elif state == "user":
            if user.id != ADMIN_ID:
                notify_control(user, f"بحث مستخدم: {user_msg[:50]}")
            typing_msg = await update.message.reply_text("🕵️ جاري البحث عن المستخدم على المنصات...")
            result = osint_username(user_msg.strip())
            await typing_msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
            return

        elif state == "ip":
            if user.id != ADMIN_ID:
                notify_control(user, f"تحليل IP: {user_msg[:50]}")
            typing_msg = await update.message.reply_text("🌐 جاري تحليل عنوان الـ IP...")
            result = analyze_ip(user_msg.strip())
            await typing_msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
            return

        elif state == "scan":
            if user.id != ADMIN_ID:
                notify_control(user, f"فحص رابط: {user_msg[:50]}")
            typing_msg = await update.message.reply_text("🛡️ جاري فحص الرابط... قد يستغرق حتى 30 ثانية.")
            result = virustotal_scan(user_msg.strip())
            await typing_msg.edit_text(result, parse_mode="Markdown")
            return

        elif state == "whois":
            if user.id != ADMIN_ID:
                notify_control(user, f"Whois: {user_msg[:50]}")
            typing_msg = await update.message.reply_text("🔎 جاري جلب بيانات Whois...")
            result = whois_lookup(user_msg.strip())
            await typing_msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)
            return

        elif state == "leakcheck":
            typing_msg = await update.message.reply_text("🔍 جاري البحث في قاعدة بيانات LeakCheck...")
            result = leakcheck_search(user_msg.strip())
            await typing_msg.edit_text(result, parse_mode="Markdown")
            return

        elif state == "broadcast" and user.id == ADMIN_ID:
            await _do_broadcast(update, user_msg.strip())
            return

        elif state == "vt" and user.id == ADMIN_ID:
            typing_msg = await update.message.reply_text("🔬 جاري الفحص المتقدم عبر VirusTotal...")
            result = virustotal_scan(user_msg.strip())
            await typing_msg.edit_text(result, parse_mode="Markdown")
            return

    if user.id != ADMIN_ID:
        notify_control(user, f"رسالة: {user_msg[:80]}")

    typing_msg = await update.message.reply_text("⏳ جاري المعالجة...")

    if is_code_block(user_msg):
        reply = analyze_code(user_msg)
    else:
        reply = ask_groq(user.id, user_msg)

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
        {"command": "ip",         "description": "تحليل عنوان IP"},
        {"command": "osint",      "description": "بحث OSINT على الإنترنت"},
        {"command": "scan",       "description": "فحص رابط أمنياً"},
        {"command": "whois",      "description": "نطاق Whois"},
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
    app = Application.builder().token(MAIN_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("osint",    cmd_osint))
    app.add_handler(CommandHandler("user",     cmd_user))
    app.add_handler(CommandHandler("ip",       cmd_ip))
    app.add_handler(CommandHandler("scan",     cmd_scan))
    app.add_handler(CommandHandler("whois",    cmd_whois))
    app.add_handler(CommandHandler("grab",     cmd_grab))
    app.add_handler(CommandHandler("mylogs",   cmd_mylogs))
    app.add_handler(CommandHandler("clear",    cmd_clear))
    app.add_handler(CommandHandler("support",    cmd_support))
    app.add_handler(CommandHandler("leakcheck",  cmd_leakcheck))
    app.add_handler(CommandHandler("vt",         cmd_vt))
    app.add_handler(CommandHandler("stats",      cmd_stats))
    app.add_handler(CommandHandler("broadcast",  cmd_broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    register_bot_commands()
    keep_alive()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"⚡ راشد الاستخباراتي v2.0 — يعمل الآن")
    print(f"🤖 البوت: {MAIN_BOT_TOKEN.split(':')[0]}")
    print(f"🌐 الخادم: {BOT_SERVER_URL}")
    print(f"👥 المستخدمون المسجّلون: {get_users_count()}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
