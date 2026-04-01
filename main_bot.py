import os
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

MAIN_BOT_TOKEN = "8556004865:AAE_W9SXGVxgTcpSCufs_hemEb_mOX_ioj0"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
DEHASHED_API_KEY = os.getenv("DEHASHED_API")
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API")
ADMIN_ID = 6124349953

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
        return r.json()["choices"][0]["message"]["content"]
    except:
        return "⚠️ AI engine connection error."

def web_search(query):
    url = "https://api.tavily.com/search"
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        results = r.json().get("results", [])
        if not results:
            return "No results found."
        return "\n\n".join([f"🔹 {res["title"]}\n🔗 {res["url"]}" for res in results[:3]])
    except:
        return "⚠️ Search engine error."

def dehashing_search(query):
    if not DEHASHED_API_KEY:
        return "DeHashed API key is not set."
    headers = {"X-Api-Key": DEHASHED_API_KEY}
    url = f"https://api.dehashed.com/search?query={query}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and data.get("entries"):
            results = "Found breaches:\n"
            for entry in data["entries"][:5]: # Limit to 5 results for brevity
                results += f"- Email: {entry.get("email", "N/A")}, Password: {entry.get("password", "N/A")}, Hashed Password: {entry.get("hashed_password", "N/A")}\n"
            return results
        else:
            return "No breaches found on DeHashed."
    except requests.exceptions.RequestException as e:
        return f"Error during DeHashed search: {e}"

def virustotal_scan(resource):
    if not VIRUSTOTAL_API_KEY:
        return "VirusTotal API key is not set."
    headers = {"x-apikey": VIRUSTOTAL_API_KEY}
    params = {"url": resource} if resource.startswith("http") else {"resource": resource}
    url = "https://www.virustotal.com/api/v3/urls" if resource.startswith("http") else "https://www.virustotal.com/api/v3/files"
    try:
        if resource.startswith("http"):
            # For URL submission, first submit the URL, then get the analysis report
            submit_url = "https://www.virustotal.com/api/v3/urls"
            submit_headers = {"x-apikey": VIRUSTOTAL_API_KEY, "Content-Type": "application/x-www-form-urlencoded"}
            submit_data = {"url": resource}
            submit_response = requests.post(submit_url, headers=submit_headers, data=submit_data, timeout=10)
            submit_response.raise_for_status()
            submission_id = submit_response.json()["data"]["id"]
            analysis_url = f"https://www.virustotal.com/api/v3/analyses/{submission_id}"
            
            # Poll for analysis report (simplified for example, in real app use a loop with delay)
            analysis_response = requests.get(analysis_url, headers=headers, timeout=10)
            analysis_response.raise_for_status()
            data = analysis_response.json()
        else:
            # For file hash, directly get report (assuming resource is a hash)
            report_url = f"https://www.virustotal.com/api/v3/files/{resource}"
            response = requests.get(report_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

        if data and data.get("data") and data["data"].get("attributes"):
            stats = data["data"]["attributes"].get("last_analysis_stats", {})
            return (
                f"VirusTotal Scan Results for {resource}:\n"
                f"Malicious: {stats.get("malicious", 0)}\n"
                f"Suspicious: {stats.get("suspicious", 0)}\n"
                f"Undetected: {stats.get("undetected", 0)}\n"
                f"Harmless: {stats.get("harmless", 0)}"
            )
        else:
            return "No VirusTotal report found or invalid resource."
    except requests.exceptions.RequestException as e:
        return f"Error during VirusTotal scan: {e}"

# --- UI / Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    keyboard = [
        [InlineKeyboardButton("🔍 Security Scan", callback_data=\'scan_info\'),
         InlineKeyboardButton("🌐 OSINT Search", callback_data=\'osint_info\')],
        [InlineKeyboardButton("💻 Code Help", callback_data=\'code_info\'),
         InlineKeyboardButton("🤖 About", callback_data=\'about_info\')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = f"Welcome {user_name} to **Rashid Thunder Bot 🤖**.\nChoose a tool below or send a message."
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=\'Markdown\')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    responses = {
        \'scan_info\': "Use /scan with a URL or IP for VirusTotal or /dehashed with email/username.",
        \'osint_info\': "Use /osint with a name or topic.",
        \'code_info\': "Send any code for analysis.",
        \'about_info\': "Rashid Thunder Bot 🤖 is an advanced AI assistant specialized in programming and cybersecurity."
    }
    await query.edit_message_text(text=responses[query.data])

async def osint_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = " ".join(context.args)
    if not target:
        return await update.message.reply_text("❌ Usage: /osint target")
    await update.message.reply_text(f"🔎 Searching: {target}...")
    result = web_search(target)
    await update.message.reply_text(f"📊 Results:\n\n{result}")

async def dehashed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        return await update.message.reply_text("❌ Usage: /dehashed email_or_username")
    await update.message.reply_text(f"🔎 Searching DeHashed for: {query}...")
    result = dehashing_search(query)
    await update.message.reply_text(f"📊 Results:\n\n{result}")

async def virustotal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resource = " ".join(context.args)
    if not resource:
        return await update.message.reply_text("❌ Usage: /virustotal url_or_hash")
    await update.message.reply_text(f"🔎 Scanning with VirusTotal: {resource}...")
    result = virustotal_scan(resource)
    await update.message.reply_text(f"📊 Results:\n\n{result}")

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
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, parse_mode=\'Markdown\')

    ai_reply = ask_groq_ai(user_msg)
    await update.message.reply_text(ai_reply)

# --- Run Bot ---

def main_ai_bot():
    app_tg = Application.builder().token(MAIN_BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("osint", osint_cmd))
    app_tg.add_handler(CommandHandler("dehashed", dehashed_cmd))
    app_tg.add_handler(CommandHandler("virustotal", virustotal_cmd))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    print("Rashid Thunder Bot 🤖 is running...")
    app_tg.run_polling()

if __name__ == "__main__":
    main_ai_bot()
