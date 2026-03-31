import os
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from flask import Flask  # أضفنا هذه
from threading import Thread  # أضفنا هذه

# --- Web Server for 24/7 Hosting ---
app = Flask('')

@app.route('/')
def home():
    return "Rashd AI 🤖 is Online and Running!"

def run_web_server():
    # Render يطلب استخدام Port محدد من البيئة
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web_server)
    t.start()

# --- Load environment variables ---
load_dotenv()

TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")

# --- Core Functions ---

def ask_groq_ai(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": "You are Rashd AI 🤖, an advanced assistant specialized in programming and cybersecurity. Respond in Arabic."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Error: {e}")
        return "⚠️ عذراً، حدث خطأ في الاتصال بمحرك الذكاء الاصطناعي."

# --- [بقيت الدوال كما هي: web_search, is_valid_ip, get_ip_info] ---

def web_search(query):
    url = "https://api.tavily.com/search"
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        results = r.json().get('results', [])
        if not results: return "لم يتم العثور على نتائج."
        return "\n\n".join([f"🔹 {res['title']}\n🔗 {res['url']}" for res in results[:3]])
    except: return "⚠️ خطأ في محرك البحث."

def is_valid_ip(ip):
    return re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", ip)

def get_ip_info(ip):
    url = f"https://api.ipinfo.io/{ip}/json"
    headers = {"Authorization": f"Bearer {IPINFO_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        return f"🌐 IP: {data.get('ip')}\n🌍 Country: {data.get('country')}\n🏙 City: {data.get('city')}\n🏢 ISP: {data.get('org')}"
    except: return "⚠️ خطأ في جلب بيانات الـ IP."

# --- UI / Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    keyboard = [
        [InlineKeyboardButton("🔍 Security Scan", callback_data='scan_info'),
         InlineKeyboardButton("🌐 OSINT Search", callback_data='osint_info')],
        [InlineKeyboardButton("💻 Code Help", callback_data='code_info'),
         InlineKeyboardButton("🤖 About", callback_data='about_info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = f"مرحباً {user_name} في **Rashd AI 🤖**.\nاختر أداة من الأسفل أو أرسل استفسارك مباشرة."
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    responses = {
        'scan_info': "استخدم الأمر /scan مع رابط أو IP.",
        'osint_info': "استخدم الأمر /osint مع اسم أو موضوع.",
        'code_info': "أرسل أي كود برمجي لتحليله.",
        'about_info': "Rashd AI 🤖 هو مساعدك التقني المتقدم."
    }
    await query.edit_message_text(text=responses[query.data])

async def osint_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = " ".join(context.args)
    if not target: return await update.message.reply_text("❌ الاستخدام: /osint اسم_الهدف")
    await update.message.reply_text(f"🔎 جاري البحث عن: {target}...")
    result = web_search(target)
    await update.message.reply_text(f"📊 النتائج:\n\n{result}")

async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ip = " ".join(context.args)
    if not ip or not is_valid_ip(ip): return await update.message.reply_text("❌ الاستخدام: /ip 8.8.8.8")
    await update.message.reply_text(f"🔎 فحص الـ IP: {ip}...")
    result = get_ip_info(ip)
    await update.message.reply_text(result)

async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    ai_reply = ask_groq_ai(user_msg)
    await update.message.reply_text(ai_reply)

# --- Run Bot ---

def main():
    # تشغيل خادم الويب في الخلفية قبل تشغيل البوت
    keep_alive()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("osint", osint_cmd))
    app.add_handler(CommandHandler("ip", ip_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    print("Rashd AI 🤖 is running 24/7...")
    app.run_polling()

if __name__ == "__main__":
    main()
