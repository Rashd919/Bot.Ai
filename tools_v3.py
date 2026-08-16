# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  🆕  أدوات بوت راشد v3 | نظام XP + الأدوات الذكية + التصميم الفاخر
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import os
import re
import json
import math
import base64
import random
import string
import threading
import requests
from datetime import datetime, timedelta

try:
    from collections import defaultdict
    import io
except Exception:
    pass

# ── نظام XP والمستويات ────────────────────────────────────────
LEVELS = [
    (0,     "عضو مبتدئ 🌱"),
    (20,    "باحث رقمي 🔎"),
    (60,    "محقق رقمي 🕵️"),
    (120,   "عميل راشد 🛡️"),
    (220,   "قائد استخباراتي 🎖️"),
    (360,   "نخبة راشد ⭐"),
    (550,   "أسطورة النظام 👑"),
    (800,   "خالد في راشد 💠"),
]

XP_FILE = "xp_db.json"

def _load_xp() -> dict:
    if os.path.exists(XP_FILE):
        try:
            with open(XP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_xp(db: dict):
    try:
        with open(XP_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False)
    except Exception:
        pass

def add_xp(user_id: int, amount: int = 10) -> dict:
    """تمنح نقاط خبرة وتعيد بيانات المستخدم المحدثة."""
    db = _load_xp()
    uid = str(user_id)
    rec = db.get(uid, {"xp": 0, "uses": 0, "joined": datetime.now().strftime("%Y-%m-%d")})
    rec["xp"] = rec.get("xp", 0) + amount
    rec["uses"] = rec.get("uses", 0) + 1
    db[uid] = rec
    _save_xp(db)
    return rec

def get_user_level(xp: int):
    title = LEVELS[0][1]
    for threshold, t in LEVELS:
        if xp >= threshold:
            title = t
    # حساب المستوى التالي
    next_xp = None
    for threshold, t in LEVELS:
        if xp < threshold:
            next_xp = threshold
            break
    return title, next_xp

def get_user_stats(user_id: int) -> dict:
    rec = _load_xp().get(str(user_id), {"xp": 0, "uses": 0, "joined": "—"})
    title, next_xp = get_user_level(rec.get("xp", 0))
    rec["title"] = title
    rec["next_xp"] = next_xp
    return rec

# ── عناصر التصميم الفاخر ──────────────────────────────────────
HEADER = (
    "┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
    "┃  ✦ 𝐑𝐚𝐬𝐡𝐞𝐝 𝐀𝐈  ✦     ┃\n"
    "┗━━━━━━━━━━━━━━━━━━━━━━┛"
)

DIVIDER = "─ ✦ ────────────── ✦ ─"

TITLE_BOX = {
    "ai":       "│   🤖  الذكاء الاصطناعي   │",
    "code":     "│   💻  مختبر تحليل الكود  │",
    "osint":    "│   🔍  مختبر OSINT        │",
    "grab":     "│   🕵️  مركز روابط السحب   │",
    "ip":       "│   🌐  محلل الشبكات IP    │",
    "whois":    "│   📡  رادار النطاقات     │",
    "leak":     "│   🧪  فحص التسريبات      │",
    "vt":       "│   🔬  مختبر VirusTotal   │",
    "tools":    "│   🧰  صندوق الأدوات      │",
    "game":     "│   🎮  ركن الألعاب        │",
    "stats":    "│   📊  غرفة الإحصائيات    │",
    "profile":  "│   🪪  بطاقة هويتك        │",
    "pass":     "│   🔑  مولّد الكلمات السرية│",
    "qr":       "│   📱  صانع QR Code       │",
    "text":     "│   🧩  ورشة النصوص        │",
    "age":      "│   🎂  حاسبة العمر        │",
    "news":     "│   📰  نشرة الأخبار       │",
    "remind":   "│   ⏰  منبه راشد          │",
    "help":     "│   ℹ️  دليل النظام         │",
}

def title_of(key: str) -> str:
    return f"```\n┌──────────────────────────┐\n{TITLE_BOX.get(key, '│   ✦  راشد AI          │')}\n└──────────────────────────┘\n```"


# ── مولّد كلمات مرور ─────────────────────────────────────────
def generate_password(length: int = 16, extra_chars: str = "") -> str:
    length = max(8, min(64, int(length or 16)))
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]" + extra_chars
    return ''.join(random.choice(chars) for _ in range(length))

def password_strength(pw: str) -> tuple[str, str]:
    score = 0
    if len(pw) >= 8:  score += 1
    if len(pw) >= 12: score += 1
    if len(pw) >= 16: score += 1
    if re.search(r"[A-Z]", pw): score += 1
    if re.search(r"[a-z]", pw): score += 1
    if re.search(r"\d", pw):    score += 1
    if re.search(r"[^A-Za-z0-9]", pw): score += 1
    if len(set(pw)) >= 8: score += 1
    if score <= 3:   return ("ضعيفة 🔴", "قصيرة أو بسيطة — استخدم 16 خانة مع رموز")
    if score <= 5:   return ("متوسطة 🟡", "جيدة لكن أضف رموزاً وأرقاماً")
    if score <= 7:   return ("قوية 🟢", "ممتازة تقريباً — غيّرها كل فترة")
    return ("خارقة 💠", "أقوى ما يمكن — لا يحتاج تغيير قريب")


# ── QR Code (صورة عبر PIL) ────────────────────────────────────
def make_qr_image(text: str) -> "io.BytesIO":
    import qrcode
    from PIL import Image
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=12, border=2)
    qr.add_data(text[:1500])
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a2e", back_color="#e8e8f0")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── أدوات النصوص ──────────────────────────────────────────────
MORSE_MAP = {
    'ا': '·−−−−', 'ب': '−···', 'ت': '−·', 'ث': '−··−', 'ج': '−··−',
    'ح': '····', 'خ': '−−··', 'د': '−··', 'ذ': '−−···', 'ر': '·−·',
    'ز': '−−··', 'س': '···', 'ش': '−−−', 'ص': '−·−·', 'ض': '−−·−',
    'ط': '·−−', 'ظ': '−−−·', 'ع': '·−−−', 'غ': '−−·', 'ف': '··−·',
    'ق': '−−·−', 'ك': '−·−', 'ل': '·−··', 'م': '−−', 'ن': '−·',
    'ه': '·····', 'و': '·−−', 'ي': '··', 'أ': '·−', 'ة': '···',
    'ى': '··', 'ء': '·', 'ئ': '···', 'ؤ': '·−−',
}
LAT_MORSE = {
    'A': '·−', 'B': '−···', 'C': '−·−·', 'D': '−··', 'E': '·',
    'F': '··−·', 'G': '−−·', 'H': '····', 'I': '··', 'J': '·−−−',
    'K': '−·−', 'L': '·−··', 'M': '−−', 'N': '−·', 'O': '−−−',
    'P': '·−−·', 'Q': '−−·−', 'R': '·−·', 'S': '···', 'T': '−',
    'U': '··−', 'V': '···−', 'W': '·−−', 'X': '−··−', 'Y': '−·−−',
    'Z': '−−··', '0': '−−−−−', '1': '·−−−−', '2': '··−−−', '3': '···−−',
    '4': '····−', '5': '·····', '6': '−····', '7': '−−···', '8': '−−−··', '9': '−−−−·',
}
LAT_MORSE_REV = {v: k for k, v in LAT_MORSE.items()}

def text_tools_report(text: str) -> str:
    text = text.strip()
    out = f"{DIVIDER}\n"
    # Base64
    b64 = base64.b64encode(text.encode("utf-8")).decode()
    out += f"🔐 *Base64 تشفير:*\n`{b64[:200]}`\n\n"
    try:
        # عكس
        rev = text[::-1]
        out += f"🪞 *معكوس النص:*\n`{rev[:200]}`\n\n"
    except Exception:
        pass
    # Morse (حروف لاتينية وأرقام فقط)
    morse_parts = []
    for ch in text.upper():
        if ch in LAT_MORSE:
            morse_parts.append(LAT_MORSE[ch])
        elif ch == ' ':
            morse_parts.append('   ')
    if morse_parts:
        out += f"📻 *Morse Code:*\n`{' '.join(morse_parts)[:200]}`\n\n"
    # إحصاءات سريعة
    out += f"🧮 *عدّاد النص:*\n• أحرف: `{len(text)}`\n• كلمات: `{len(text.split())}`\n"
    return out


# ── حاسبة العمر ───────────────────────────────────────────────
def age_report(text: str) -> str:
    m = re.search(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", text)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100: y += 2000
    try:
        birth = datetime(y, mo, d)
    except ValueError:
        return None
    now = datetime.now()
    years = now.year - birth.year
    if (now.month, now.day) < (mo, d):
        years -= 1
    days_total = (now - birth).days
    weeks = days_total // 7
    out = f"{DIVIDER}\n"
    out += f"🎂 *عمرك:*\n"
    out += f"• بالسنوات: `{years} سنة`\n"
    out += f"• بالأشهر: `{years*12 + now.month - mo} شهر`\n"
    out += f"• بالأسابيع: `{weeks:,} أسبوع`\n"
    out += f"• بالأيام: `{days_total:,} يوم`\n"
    out += f"• بالساعات: `{days_total*24:,} ساعة`\n"
    # الحساب القادم للميلاد
    next_bd = datetime(now.year, mo, d)
    if next_bd < now:
        next_bd = datetime(now.year + 1, mo, d)
    out += f"• عيد ميلادك القادم بعد `{(next_bd - now).days} يوم` 🎉\n"
    return out


# ── لعبة تخمين الرقم ──────────────────────────────────────────
GAMES = {}

def game_start(user_id: int) -> str:
    num = random.randint(1, 100)
    GAMES[user_id] = {"number": num, "attempts": 0}
    return "🎲 *لعبة التخمين بدأت!*\n\nاخترت رقماً من 1 إلى 100.\nأرسل تخمينك الآن — أقل عدد محاولات يكسبك نقاط XP أكثر! 🎯"

def game_guess(user_id: int, text: str) -> str:
    m = re.search(r"\d+", text)
    if not m:
        return "⚠️ أرسل رقماً فقط من 1 إلى 100."
    g = int(m.group())
    if user_id not in GAMES:
        return "⚠️ ابدأ لعبة جديدة أولاً: /play"
    game = GAMES[user_id]
    game["attempts"] += 1
    if g == game["number"]:
        att = game["attempts"]
        xp = max(5, 40 - att * 5)
        add_xp(user_id, xp)
        del GAMES[user_id]
        return f"🎉 *مبروك! الرقم كان {g}!*\n\n• المحاولات: `{att}`\n• نقاط XP المربوحة: `+{xp}`\n\nالعب مجدداً: /play"
    hint = "أكبر 🔼" if g < game["number"] else "أصغر 🔽"
    return f"❌ خطأ! الرقم {hint}.\n• محاولاتك: `{game['attempts']}`\n\nجرّب مرة أخرى."


# ── التذكيرات ─────────────────────────────────────────────────
PENDING_REMINDERS = {}

def schedule_reminder(bot, user_id: int, minutes: int, note: str):
    PENDING_REMINDERS[user_id] = {
        "at": datetime.now() + timedelta(minutes=minutes),
        "note": note[:100],
    }
    def _fire():
        while datetime.now() < PENDING_REMINDERS[user_id]["at"]:
            import time as _t
            _t.sleep(10)
        PENDING_REMINDERS.pop(user_id, None)
        try:
            requests.post(
                f"https://api.telegram.org/bot{os.getenv('MAIN_BOT_TOKEN', '')}/sendMessage",
                json={
                    "chat_id": user_id,
                    "text": f"⏰ *منبه راشد!*\n\n{PENDING_REMINDERS.get(user_id, {}).get('note', 'حان وقتك!') if False else ''}" if False else (
                        "⏰ *منبه راشد!*\n\n"
                        "📌 *التذكير:*\n"
                        f"{note[:200]}\n\n✦ راشد"
                    ),
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
        except Exception:
            pass
    t = threading.Thread(target=_fire, daemon=True)
    t.start()


# ── أخبار اليوم (RSS عام بدون API keys) ───────────────────────
def daily_news_report(category: str = "technology") -> str:
    feeds = {
        "technology": "https://rss.app/feeds/technology",
        "world":      "https://rss.app/feeds/world",
        "science":    "https://rss.app/feeds/science",
    }
    rss2json_apis = [
        f"https://api.rss2json.com/v1/api.json?rss_url=https://www.techtimes.com/rss",
        f"https://api.rss2json.com/v1/api.json?rss_url=https://techcrunch.com/feed/",
        f"https://api.rss2json.com/v1/api.json?rss_url=https://feeds.bbci.co.uk/news/technology/rss.xml",
    ]
    items = []
    for url in rss2json_apis:
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "ok" and data.get("items"):
                    items = data["items"]
                    break
        except Exception:
            continue
    if not items:
        return f"{DIVIDER}\n⚠️ تعذر جلب الأخبار الآن — تحقق من اتصالك أو أعد المحاولة بعد قليل."
    out = f"📰 *نشرة اليوم* — أحدث {min(5, len(items))} عناوين\n{DIVIDER}\n\n"
    for i, it in enumerate(items[:5], 1):
        title = it.get("title", "—")[:70]
        link = it.get("link", "#")
        desc = re.sub(r"<[^>]+>", "", it.get("description", ""))[:100]
        out += f"{i}▪ *{title}*\n"
        if desc:
            out += f"   ↳ {desc}...\n"
        out += f"   🔗 [اقرأ]{link}\n\n"
    out += "━━━━━━━━━━━━━━━━━━━━━\n✦ راشد"
    return out


# ── بطاقة البروفايل ───────────────────────────────────────────
def profile_card(user, all_users_db: dict = None) -> str:
    s = get_user_stats(user.id)
    db = all_users_db or {}
    rec = db.get(str(user.id), {})
    joined = rec.get("joined", s.get("joined", "—"))
    progress = ""
    if s.get("next_xp"):
        pct = int(s["xp"] * 100 / s["next_xp"])
        bar_len = 10
        filled = max(1, min(bar_len - 1, pct // 10))
        bar = "█" * filled + "░" * (bar_len - filled)
        progress = f"\n📈 التقدم للمستوى التالي: `{pct}%`\n[{bar}]"
    uname = f"@{user.username}" if user.username else "لا يوجد"
    return (
        f"┏━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃   🪪  بطاقة {user.first_name or 'راشد'}  ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"👤 *الاسم:* {user.full_name}\n"
        f"🆔 *ID:* `{user.id}`\n"
        f"📛 *المعرف:* {uname}\n"
        f"🏅 *اللقب:* {s['title']}\n"
        f"⭐ *نقاط XP:* `{s['xp']}`\n"
        f"🎯 *استخدامات:* `{s['uses']}`\n"
        f"📅 *الانضمام:* {joined}{progress}\n"
        f"{DIVIDER}\n✦ راشد"
    )


# ── قائمة الأدوات (زر رئيسي) ─────────────────────────────────
def build_tools_keyboard() -> str:
    """تُبنى كـ InlineKeyboardMarkup خارج هذا الملف."""
    pass
