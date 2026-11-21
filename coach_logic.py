"""Deterministic coaching rules for the Telegram MVP; AI can be layered on later."""
from __future__ import annotations

from html import escape


def starter_plan(profile: dict) -> dict:
    days = int(profile.get("days_per_week") or 3)
    minutes = int(profile.get("session_minutes") or 45)
    place = profile.get("training_place") or "gym"
    beginner = profile.get("experience") in ("مبتدئ", "beginner", "")
    sets = "2–3" if beginner else "3–4"
    plan_days = []
    templates = [
        ("اليوم 1", "قوة الجسم كامل", [("سكوات", "8–12", "كرسي/سكوات وزن الجسم"), ("ضغط مائل", "8–12", "ضغط على الحائط"), ("سحب مطاط أو دمبل", "10–12", "سحب منشفة بمقاومة خفيفة"), ("بلانك", "20–40 ثانية", "Dead bug")]),
        ("اليوم 2", "راحة وحركة خفيفة", []),
        ("اليوم 3", "تحكم وقوة", [("لانجز أو صعود درجة", "8–10 لكل جهة", "جلوس وقيام من كرسي"), ("ضغط كتف", "8–12", "رفع زجاجات خفيفة"), ("جسر الحوض", "10–15", "جسر الحوض على الأرض"), ("Side plank", "15–30 ثانية", "Bird dog")]),
        ("اليوم 4", "راحة وحركة خفيفة", []),
        ("اليوم 5", "تكرار اختياري", [("تمرين من اليوم 1", "8–12", "نسخة أسهل"), ("تمرين من اليوم 3", "8–12", "نسخة أسهل")]),
        ("اليوم 6", "راحة", []),
        ("اليوم 7", "راحة", []),
    ]
    for index, item in enumerate(templates):
        if index >= 5 and days < 5:
            break
        label, focus, exercises = item
        plan_days.append({
            "day": label,
            "focus": focus,
            "duration": minutes,
            "place": place,
            "exercises": [{"name": name, "sets": sets, "reps": reps, "alternative": alternative, "rest": "60–90 ثانية"} for name, reps, alternative in exercises],
        })
    injury = profile.get("injury_note", "").strip()
    safety = "إذا ظهر ألم غير معتاد، أوقف التمرين."
    if injury:
        safety += " ذكرت وجود ملاحظة صحية؛ لا نعدّل حولها تشخيصيًا، ومن الأفضل مراجعة مختص قبل التحميل على المنطقة المتأثرة."
    age = profile.get("age")
    weight = profile.get("weight_kg")
    height = profile.get("height_cm")
    measurements = {}
    if age:
        measurements["age"] = age
    if height:
        measurements["height_cm"] = height
    if weight:
        measurements["weight_kg"] = weight
    if age and int(age) < 18:
        safety += " بما أن عمرك أقل من 18 سنة، خذ موافقة ولي الأمر واستعن بمدرب أو مختص مؤهل قبل رفع الشدة."
    nutrition = [
        "ضع مصدر بروتين في أغلب الوجبات، مع خضار أو فاكهة.",
        "اشرب الماء بانتظام، ولا تحتاج إلى حمية قاسية كي تبدأ.",
        "زد التكرارات أو الوزن تدريجيًا فقط إذا كان الأداء مريحًا وبدون ألم.",
    ]
    if weight:
        nutrition.insert(1, f"نطاق بروتين إرشادي تقريبي: {round(float(weight) * 1.4)}–{round(float(weight) * 2.0)} غرام يوميًا؛ عدّله مع مختص حسب صحتك وهدفك.")
    return {
        "title": f"خطة {days} أيام — بداية ذكية",
        "summary": "خطة مبدئية مبنية على ملفك وقياساتك، وليست تشخيصًا طبيًا أو ضمانًا للنتيجة. نراجعها مع بيانات التقدم.",
        "safety": safety,
        "measurements": measurements,
        "days": plan_days,
        "nutrition": nutrition,
    }


def format_plan(plan: dict) -> str:
    lines = [f"<b>🏋️ {escape(plan['title'])}</b>", escape(plan["summary"]), ""]
    for day in plan["days"]:
        lines.append(f"<b>{escape(day['day'])} · {escape(day['focus'])}</b> — {day['duration']} دقيقة")
        if not day["exercises"]:
            lines.append("• راحة أو مشي خفيف وحركة مريحة")
        for exercise in day["exercises"]:
            lines.append(f"• {escape(exercise['name'])}: {exercise['sets']} مجموعات × {escape(exercise['reps'])} · راحة {escape(exercise['rest'])}")
            lines.append(f"  البديل: {escape(exercise['alternative'])}")
        lines.append("")
    lines.append("<b>🍽 مبادئ بسيطة للتغذية</b>")
    lines.extend(f"• {escape(tip)}" for tip in plan["nutrition"])
    lines.append("")
    lines.append(f"<b>🛡 السلامة:</b> {escape(plan['safety'])}")
    return "\n".join(lines)


def format_profile(profile: dict) -> str:
    labels = {
        "preferred_name": "الاسم المفضّل", "goal": "الهدف", "experience": "الخبرة",
        "age": "العمر", "height_cm": "الطول", "weight_kg": "الوزن",
        "days_per_week": "أيام التدريب", "session_minutes": "مدة الحصة", "training_place": "مكان التدريب",
        "equipment": "المعدات", "injury_note": "ملاحظة صحية", "diet_preferences": "التفضيلات الغذائية",
    }
    lines = ["<b>👤 ملفك التدريبي</b>"]
    for key, label in labels.items():
        value = profile.get(key) or "غير محدد"
        if key == "days_per_week" and value != "غير محدد": value = f"{value} أيام"
        if key == "session_minutes" and value != "غير محدد": value = f"{value} دقيقة"
        if key == "height_cm" and value != "غير محدد": value = f"{value} سم"
        if key == "weight_kg" and value != "غير محدد": value = f"{value} كغ"
        lines.append(f"<b>{label}:</b> {escape(str(value))}")
    lines.append("\n<i>يمكنك طلب تعديل ملفك أو حذفه في أي وقت.</i>")
    return "\n".join(lines)
