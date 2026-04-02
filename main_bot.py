import os
import re
import base64
import hashlib
import time
import json
import requests
from datetime import datetime
from collections import defaultdict
from threading import Thread
from flask import Flask as _Flask

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

# Hardcoded Main Bot Token (Rashid_Thunder_bot)
MAIN_BOT_TOKEN     = "8556004865:AAE_W9SXGVxgTcpSCufs_hemEb_mOX_ioj0"
# Hardcoded Tracker Bot Token (Rashd_IP_Tracker_bot) - Used for sending tracker links
TRACKER_BOT_TOKEN  = "8346034907:AAHv4694Nf1Mn3JSwcUeb1Zkl1ZSlsODIx8"
# Hardcoded Target Channel ID for results (only you see this) - Not used directly in main_bot.py for sending
TARGET_CHANNEL_ID  = "-1003770774871"
# Hardcoded Control Channel ID for monitoring (where you see user activity)
CONTROL_CHANNEL_ID = "-1003751955886"

# API Keys from Replit Secrets
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY    = os.getenv("TAVILY_API_KEY", "")
IPINFO_TOKEN      = os.getenv("IPINFO_TOKEN", "")
VIRUSTOTAL_KEY    = os.getenv("VIRUSTOTAL_KEY", "")
DEHASHED_KEY      = os.getenv("DEHASHED_KEY", "")
BOT_SERVER_URL    = (
    os.getenv("BOT_SERVER_URL", "")
    or (os.getenv("REPLIT_DOMAINS", "").split(",")[0].strip())
)

# Hardcoded Admin ID (your personal chat ID)
ADMIN_ID = 6124349953

# سجل روابط التعقب لكل مستخدم (في الذاكرة)
# user_logs[user_id] = [ {session_id, url, label, timestamp}, ... ]
user_logs: dict[int, list] = defaultdict(list)

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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📤  إرسال للقناة عبر بوت التعقب (هذه الدالة لا تستخدم في main_bot.py مباشرة لإرسال تقارير التعقب)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_to_channel(message: str):
    """يرسل عبر بوت التعقب (8346034907) إلى القناة المستهدفة"""
    # هذه الدالة يجب أن لا تستخدم هنا لإرسال تقارير التعقب، بل في tracker_bot.py
    # ولكن يمكن استخدامها لإرسال رسائل عامة إذا لزم الأمر
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
    """إرسال نشاط المستخدم إلى قناة المراقبة (Rashd-Ai Control Center)"""
    uname = f"@{user.username}" if user.username else "N/A"
    msg = (
        f"👁 راشد — نشاط مستخدم\n\n"
        f"👤 الاسم    : {user.full_name}\n"
        f"🆔 ID       : {user.id}\n"
        f"📛 معرف     : {uname}\n"
        f"🕐 التوقيت  : {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}\n\n"
        f"{text}\n\n"
        "✦ راشد — تطوير أبو سعود"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CONTROL_CHANNEL_ID,
                "text": msg[:4000],
                "parse_mode": None,
                "disable_web_page_preview": True,
            },
            timeout=8,
        )
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🧠  الذكاء الاصطناعي | Groq AI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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


def _groq_post(system: str, user_msg: str, max_tokens: int = 2048) -> str:
    """الدالة الأساسية للتواصل مع Groq"""
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
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.6,
                "max_tokens": max_tokens,
            },
            timeout=40,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        return f"⚠️ خطأ في الاتصال بـ Groq — كود: {e.response.status_code}"
    except requests.exceptions.Timeout:
        return "⚠️ انتهت مهلة الاتصال بالذكاء الاصطناعي، حاول مجدداً."
    except Exception as e:
        return f"⚠️ خطأ غير متوقع: {str(e)[:100]}"


def ask_groq(prompt: str) -> str:
    return _groq_post(SYSTEM_PROMPT, prompt, max_tokens=2048)


def analyze_code(code: str, lang: str = "") -> str:
    lang_hint = f"اللغة: {lang}\n\n" if lang else ""
    user_msg  = f"{lang_hint}حلّل هذا الكود:\n\n```\n{code}\n```"
    return _groq_post(CODE_SYSTEM_PROMPT, user_msg, max_tokens=2048)


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
    report += f"🕐 {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}\n"
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

    report += "✦ راشد — تطوير أبو سعود"
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🛡️  فحص الروابط | VirusTotal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def virustotal_scan_url(url_to_scan: str) -> str:
    if not VIRUSTOTAL_KEY:
        return "⛔ مفتاح VirusTotal غير مُهيّأ."
    headers = {
        "x-apikey": VIRUSTOTAL_KEY,
        "accept": "application/json"
    }
    try:
        # Step 1: Submit URL for scanning
        response = requests.post(
            "https://www.virustotal.com/api/v3/urls",
            headers=headers,
            data={"url": url_to_scan},
            timeout=15
        )
        response.raise_for_status()
        analysis_id = response.json()["data"]["id"]

        # Step 2: Get analysis report
        for _ in range(5):  # Try up to 5 times
            time.sleep(5)  # Wait 5 seconds between checks
            report_response = requests.get(
                f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
                headers=headers,
                timeout=15
            )
            report_response.raise_for_status()
            status = report_response.json()["data"]["attributes"]["status"]
            if status == "completed":
                break
        else:
            return "⚠️ انتهت مهلة فحص الرابط، حاول مجدداً."

        stats = report_response.json()["data"]["attributes"]["stats"]
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless = stats.get("harmless", 0)

        report = "━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🛡️ [راشد // تقرير VirusTotal]\n"
        report += "━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🔗 الرابط: {url_to_scan}\n"
        report += f"🚨 خبيث: {malicious}\n"
        report += f" suspicious: {suspicious}\n"
        report += f"✅ آمن: {harmless}\n"
        report += "\n━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
        return report

    except requests.exceptions.HTTPError as e:
        return f"⚠️ خطأ في الاتصال بـ VirusTotal — كود: {e.response.status_code}"
    except Exception as e:
        return f"⚠️ خطأ غير متوقع: {str(e)[:100]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔒  فحص التسريبات | DeHashed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def dehased_search(query: str) -> str:
    if not DEHASHED_KEY:
        return "⛔ مفتاح DeHashed غير مُهيّأ."
    headers = {
        "Accept": "application/json",
        "X-Api-Key": DEHASHED_KEY
    }
    try:
        response = requests.get(
            f"https://api.dehased.com/v2/search?query={query}",
            headers=headers,
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        if data.get("success") and data.get("total") > 0:
            report = "━━━━━━━━━━━━━━━━━━━━━\n"
            report += f"🚨 [راشد // تقرير تسريبات]\n"
            report += "━━━━━━━━━━━━━━━━━━━━━\n"
            report += f"🔎 الاستعلام: {query}\n"
            report += f"⚠️ عدد التسريبات: {data.get("total")}\n\n"
            for item in data.get("data", [])[:3]:
                report += f"▪ المصدر: {item.get("source", "N/A")}\n"
                report += f"  تاريخ التسريب: {item.get("date", "N/A")}\n"
                report += f"  النوع: {item.get("type", "N/A")}\n"
                report += f"  الوصف: {item.get("description", "N/A")[:100]}...\n\n"
            report += "━━━━━━━━━━━━━━━━━━━━━\n◈ تصميم وتطوير: أبو سعود"
            return report
        else:
            return "✅ لا توجد تسريبات لهذا الاستعلام."

    except requests.exceptions.HTTPError as e:
        return f"⚠️ خطأ في الاتصال بـ DeHashed — كود: {e.response.status_code}"
    except Exception as e:
        return f"⚠️ خطأ غير متوقع: {str(e)[:100]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔗  توليد روابط التعقب | Tracker Link Generator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_tracker_link(user_id: int, label: str) -> str:
    if not BOT_SERVER_URL:
        return "⛔ رابط الخادم غير مُهيّأ. يرجى إعداد BOT_SERVER_URL في .env"
    
    session_id = hashlib.sha256(f"{user_id}-{label}-{datetime.now()}".encode()).hexdigest()[:10]
    tracker_url = f"{BOT_SERVER_URL}/track/{user_id}/{session_id}"
    
    # Store the generated link in user_logs
    user_logs[user_id].append({
        "session_id": session_id,
        "url": tracker_url,
        "label": label,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    
    return tracker_url


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🤖  أوامر البوت | Bot Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_name = user.first_name
    
    # Notify admin about new user
    if str(user.id) != str(ADMIN_ID):
        await context.bot.send_message(
            chat_id=CONTROL_CHANNEL_ID,
            text=f"🆕 مستخدم جديد بدأ البوت: {user.full_name} (ID: `{user.id}`)",
            parse_mode='Markdown'

        )

    keyboard = [
        [InlineKeyboardButton("🔍 فحص أمني", callback_data='scan_info'),
         InlineKeyboardButton("🌐 بحث OSINT", callback_data='osint_info')],
        [InlineKeyboardButton("💻 مساعدة برمجية", callback_data='code_info'),
         InlineKeyboardButton("🔗 رابط تعقب", callback_data='tracker_info')],
        [InlineKeyboardButton("🤖 عن البوت", callback_data='about_info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = f"أهلاً بك {user_name} في **راشد الاستخباراتي 🤖**، من تصميم وتطوير أبو سعود.\nاختر أداة من الأسفل أو أرسل استفسارك."
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=\'Markdown\')


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    responses = {
        'scan_info': "استخدم الأمر /scan متبوعاً برابط أو IP للفحص الأمني.",
        'osint_info': "استخدم الأمر /osint متبوعاً باسم أو موضوع للبحث الاستخباراتي.",
        'code_info': "أرسل أي كود برمجي لتحليله.",
        'tracker_info': "استخدم الأمر /track_link متبوعاً بتسمية للرابط (مثال: /track_link MyWebsite).",
        'about_info': "راشد الاستخباراتي 🤖 هو مساعد ذكاء اصطناعي متقدم، من تصميم وتطوير أبو سعود."
    }
    
    response_text = responses.get(query.data, "⚠️ أمر غير معروف.")
    await query.edit_message_text(text=response_text)
    
    # Log button click to control channel
    if str(user.id) != str(ADMIN_ID):
        await context.bot.send_message(
            chat_id=CONTROL_CHANNEL_ID,
            text=f"🔘 المستخدم {user.full_name} (ID: `{user.id}`) ضغط على زر: {query.data}",
            parse_mode='Markdown'
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_msg = update.message.text
    
    # Admin Monitoring: Notify control channel about every message
    if str(user.id) != str(ADMIN_ID):
        admin_alert = (
            f"💬 **رسالة مستخدم جديدة**\n"
            f"👤 المستخدم: {user.full_name} (@{user.username})\n"
            f"🆔 ID: `{user.id}`\n"
            f"📝 الرسالة: {user_msg}"
        )
        await context.bot.send_message(chat_id=CONTROL_CHANNEL_ID, text=admin_alert, parse_mode=\'Markdown\')

    # AI response
    ai_reply = ask_groq(user_msg)
    await update.message.reply_text(ai_reply)


async def cmd_track_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("الرجاء تزويد تسمية للرابط. مثال: `/track_link MyWebsite`")
        return
    
    label = " ".join(context.args)
    tracker_url = generate_tracker_link(user.id, label)
    
    await update.message.reply_text(
        f"🔗 تم إنشاء رابط التعقب بنجاح:\n`{tracker_url}`\n\n"\
        f"عندما يضغط أي شخص على هذا الرابط، ستصلك تقارير مفصلة في قناتك الخاصة بالنتائج (`{TARGET_CHANNEL_ID}`)."
    )
    
    # Log link generation to control channel
    if str(user.id) != str(ADMIN_ID):
        await context.bot.send_message(
            chat_id=CONTROL_CHANNEL_ID,
            text=f"🔗 المستخدم {user.full_name} (ID: `{user.id}`) أنشأ رابط تعقب: `{label}`\nالرابط: `{tracker_url}`",
            parse_mode=\'Markdown\'
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🚀  تشغيل البوت | Bot Startup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main_ai_bot():
    app_tg = Application.builder().token(MAIN_BOT_TOKEN).build()
    
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
    app_tg.add_handler(CommandHandler("track_link", cmd_track_link))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print(f"⚡ راشد الاستخباراتي (البوت الأساسي {MAIN_BOT_TOKEN.split(":")[0]}) يعمل...")
    app_tg.run_polling()

if __name__ == "__main__":
    main_ai_bot()
