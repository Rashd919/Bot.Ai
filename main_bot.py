import os
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

# Main Bot Credentials
MAIN_BOT_TOKEN = "8556004865:AAE_W9SXGVxgTcpSCufs_hemEb_mOX_ioj0"
ADMIN_ID = "6124349953"

# API Keys from Replit Secrets
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
DEHASHED_API_KEY = os.getenv("DEHASHED_API")
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API")

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
        return "\n\n".join([f"🔹 {res['title']}\n🔗 {res['url']}" for res in results[:3]])
    except:
        return "⚠️ Search engine error."

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
    welcome_text = f"Welcome {user_name} to **Rashid Thunder Bot 🤖**.\nChoose a tool below or send a message."
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    responses = {
        'scan_info': "Use /scan with a URL or IP.",
        'osint_info': "Use /osint with a name or topic.",
        'code_info': "Send any code for analysis.",
        'about_info': "Rashid Thunder Bot 🤖 is an advanced AI assistant."
    }
    await query.edit_message_text(text=responses[query.data])

async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_msg = update.message.text
    
    # Admin Monitoring: Notify Rashd about every message using the Main Bot Token
    if str(user.id) != str(ADMIN_ID):
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

def main_ai_bot():
    app_tg = Application.builder().token(MAIN_BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    print("Rashid Thunder Bot 🤖 is running...")
    app_tg.run_polling()

if __name__ == "__main__":
    main_ai_bot()
