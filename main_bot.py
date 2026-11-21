"""RASHED AI Telegram coach — MVP replacement for the legacy OSINT bot."""
from __future__ import annotations

import asyncio
import html
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from coach_data import (
    delete_user_data,
    get_plan,
    get_profile,
    get_state,
    init_db,
    recent_workouts,
    register_user,
    save_plan,
    save_profile,
    save_workout,
    set_state,
    user_count,
)
from coach_logic import format_plan, format_profile, starter_plan

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# Drafts are deliberately short-lived; approved data is stored in SQLite.
drafts: dict[int, dict[str, Any]] = {}


def esc(value: Any) -> str:
    return html.escape(str(value or ""))


def menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📝 ابدأ التقييم", callback_data="assessment"), InlineKeyboardButton("🏋️ خطتي", callback_data="plan")],
        [InlineKeyboardButton("✅ سجّل تمرين", callback_data="log"), InlineKeyboardButton("📈 تقدّمي", callback_data="progress")],
        [InlineKeyboardButton("👤 ملفي", callback_data="profile"), InlineKeyboardButton("💬 اسأل الكوتش", callback_data="ask")],
        [InlineKeyboardButton("🍽 نصائح غذائية", callback_data="nutrition"), InlineKeyboardButton("🔐 الخصوصية", callback_data="privacy")],
        [InlineKeyboardButton("🆘 مساعدة", callback_data="help"), InlineKeyboardButton("🗑 حذف بياناتي", callback_data="delete")],
    ]
    if is_admin:
        rows.insert(-1, [InlineKeyboardButton("📊 إحصائيات الإدارة", callback_data="stats")])
    return InlineKeyboardMarkup(rows)


def back_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة الرئيسية", callback_data="home")]])


def welcome(user) -> str:
    return (
        f"<b>مرحبًا {esc(user.first_name)}، أنا RASHED AI ✦</b>\n\n"
        "أنا كوتشك الذكي للتدريب والتغذية والمتابعة. أساعدك تبني عادة واقعية، وأتذكر هدفك وخطتك وسجلك بين المحادثات.\n\n"
        "<b>مهم:</b> أنا ذكاء اصطناعي ولست طبيبًا أو مدربًا بشريًا معتمدًا. نصائحي عامة وليست تشخيصًا أو علاجًا، ولا أتعامل مع الحالات الطبية المعقدة بدل المختص.\n\n"
        "يمكنك تعديل بياناتك أو حذفها متى شئت من داخل البوت. ابدأ بالتقييم حتى أصمم لك خطة مناسبة."
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    await update.effective_message.reply_text(welcome(user), parse_mode="HTML", reply_markup=menu(user.id == ADMIN_ID))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "<b>دليل RASHED AI</b>\n\n"
        "/start — البداية والقائمة\n/assessment — التقييم الأولي\n/profile — ملفك المحفوظ\n/my_plan — خطتك الحالية\n/log_workout — تسجيل تمرين\n/progress — سجل التقدم\n/weekly_review — مراجعة أسبوعية\n/edit — تعديل الملف\n/delete_data — حذف بياناتك\n/help — المساعدة\n\n"
        "أرسل أي سؤال تدريبي بعد تجهيز ملفك وسأجيبك ضمن حدود السلامة.",
        parse_mode="HTML", reply_markup=back_menu(update.effective_user.id),
    )


async def begin_assessment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    drafts[user.id] = {"preferred_name": user.first_name or ""}
    set_state(user.id, "name")
    await update.effective_message.reply_text("<b>التقييم 1/8</b>\nشو بتحب أناديك؟ يمكنك كتابة اسم مختصر أو اسم مستعار.", parse_mode="HTML")


async def cmd_assessment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await begin_assessment(update, context)


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_profile(update.effective_user.id)
    if not profile:
        await update.effective_message.reply_text("لسه ما جهزنا ملفك. ابدأ التقييم أولًا.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 ابدأ التقييم", callback_data="assessment")]]))
        return
    await update.effective_message.reply_text(format_profile(profile), parse_mode="HTML", reply_markup=back_menu(update.effective_user.id))


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan = get_plan(update.effective_user.id)
    if not plan:
        await update.effective_message.reply_text("حتى أبني خطتك، أكمل التقييم أولًا.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 ابدأ التقييم", callback_data="assessment")]]))
        return
    await update.effective_message.reply_text(format_plan(plan), parse_mode="HTML", reply_markup=back_menu(update.effective_user.id))


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_profile(update.effective_user.id):
        await update.effective_message.reply_text("أكمل التقييم أولًا حتى نسجل تمرينك ضمن خطتك.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 ابدأ التقييم", callback_data="assessment")]]))
        return
    await update.effective_message.reply_text("هل أنهيت تمرين اليوم؟", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("نعم، أنهيته ✅", callback_data="workout_done")], [InlineKeyboardButton("لا، لم أستطع اليوم", callback_data="workout_missed")]]))


async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logs = recent_workouts(update.effective_user.id)
    completed = sum(1 for log in logs if log["completed"])
    text = f"<b>📈 تقدّمك</b>\n\nآخر السجلات: <b>{len(logs)}</b>\nتمارين مكتملة: <b>{completed}</b>\n\n"
    if logs:
        text += "<b>آخر نشاط:</b>\n" + "\n".join(f"• {esc(log['workout_date'][:10])} — {'مكتمل ✅' if log['completed'] else 'غير مكتمل'}" for log in logs[:5])
    else:
        text += "لسه ما في سجلات. أول تمرين تسجله سيكون بداية خطك الجديد."
    await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=back_menu(update.effective_user.id))


async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logs = recent_workouts(update.effective_user.id, 7)
    completed = sum(1 for log in logs if log["completed"])
    await update.effective_message.reply_text(
        f"<b>مراجعة أسبوعية بسيطة</b>\n\nأنجزت <b>{completed}</b> تمارين من آخر {len(logs)} تسجيلات.\n\n"
        "اقتراحي: لا تغيّر الخطة بالكامل بسبب أسبوع صعب. حافظ على الحصة التالية، وخفف الحجم إذا كان الإرهاق أو الألم مستمرًا.\n\n"
        "هل تريد تعديل الخطة؟ اكتب <b>تعديل</b> أو استخدم /edit.", parse_mode="HTML", reply_markup=back_menu(update.effective_user.id),
    )


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await begin_assessment(update, context)


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("حذف ملفك وخطتك وسجل تمارينك نهائي. هل تريد المتابعة؟", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("نعم، احذف كل بياناتي", callback_data="delete_confirm")], [InlineKeyboardButton("إلغاء", callback_data="home")]]))


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.effective_message.reply_text(f"<b>إحصائيات RASHED AI</b>\n\nالمستخدمون المسجلون: <b>{user_count()}</b>", parse_mode="HTML")


async def handle_assessment_text(update: Update, state: str, text: str):
    uid = update.effective_user.id
    draft = drafts.setdefault(uid, {})
    if state == "name":
        draft["preferred_name"] = text[:120]
        set_state(uid, "goal")
        await update.effective_message.reply_text("<b>التقييم 2/8</b>\nما هدفك الأساسي؟\n\nاكتب: بناء عضلات، خسارة دهون، زيادة القوة، أو لياقة عامة.", parse_mode="HTML")
    elif state == "goal":
        draft["goal"] = text[:80]
        set_state(uid, "experience")
        await update.effective_message.reply_text("<b>التقييم 3/8</b>\nما مستواك؟ مبتدئ، متوسط، أم متقدم؟", parse_mode="HTML")
    elif state == "experience":
        draft["experience"] = text[:40]
        set_state(uid, "days")
        await update.effective_message.reply_text("<b>التقييم 4/8</b>\nكم يوم تستطيع التدريب أسبوعيًا؟ أرسل رقمًا من 1 إلى 7.", parse_mode="HTML")
    elif state == "days":
        if not text.isdigit() or not 1 <= int(text) <= 7:
            await update.effective_message.reply_text("أرسل رقمًا من 1 إلى 7 فقط.")
            return
        draft["days_per_week"] = int(text)
        set_state(uid, "minutes")
        await update.effective_message.reply_text("<b>التقييم 5/8</b>\nكم دقيقة تناسبك في الحصة؟ أرسل رقمًا بين 15 و180.", parse_mode="HTML")
    elif state == "minutes":
        if not text.isdigit() or not 15 <= int(text) <= 180:
            await update.effective_message.reply_text("أرسل عدد دقائق بين 15 و180.")
            return
        draft["session_minutes"] = int(text)
        set_state(uid, "place")
        await update.effective_message.reply_text("<b>التقييم 6/8</b>\nأين تتمرن؟ البيت، النادي، الخارج، أو مكان آخر؟", parse_mode="HTML")
    elif state == "place":
        draft["training_place"] = text[:40]
        set_state(uid, "equipment")
        await update.effective_message.reply_text("<b>التقييم 7/8</b>\nما المعدات المتوفرة؟ اكتبها أو أرسل: لا يوجد.", parse_mode="HTML")
    elif state == "equipment":
        draft["equipment"] = text[:600]
        set_state(uid, "safety")
        await update.effective_message.reply_text("<b>التقييم 8/8</b>\nهل لديك إصابة أو ألم أو تعليمات طبية تؤثر على التدريب؟ اكتب باختصار أو أرسل: لا يوجد.", parse_mode="HTML")
    elif state == "safety":
        draft["injury_note"] = "" if text in ("لا يوجد", "لا", "لاشيء", "none") else text[:800]
        draft["diet_preferences"] = ""
        set_state(uid, "confirm")
        summary = "\n".join(f"• <b>{label}:</b> {esc(draft.get(key) or '—')}" for key, label in [("preferred_name", "الاسم"), ("goal", "الهدف"), ("experience", "الخبرة"), ("days_per_week", "الأيام"), ("session_minutes", "المدة"), ("training_place", "المكان"), ("equipment", "المعدات"), ("injury_note", "الإصابة/الألم")])
        await update.effective_message.reply_text(f"<b>راجع معلوماتك قبل الحفظ</b>\n\n{summary}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("اعتماد وإنشاء الخطة ✅", callback_data="assessment_confirm")], [InlineKeyboardButton("إلغاء", callback_data="home")]]))
    elif state == "ask":
        await answer_coach(update, text)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    state = get_state(update.effective_user.id)
    if state:
        await handle_assessment_text(update, state, text)
        return
    profile = get_profile(update.effective_user.id)
    if profile:
        await answer_coach(update, text)
    else:
        await update.effective_message.reply_text("ابدأ بتقييمك أولًا، وبعدها اسألني أي سؤال يخص تدريبك.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 ابدأ التقييم", callback_data="assessment")]]))


async def answer_coach(update: Update, text: str):
    if not GROQ_API_KEY:
        await update.effective_message.reply_text("أنا جاهز أساعدك، لكن خدمة المحادثة الذكية غير مفعّلة الآن. استخدم القائمة للتقييم والخطة وتسجيل التمرين.", reply_markup=back_menu(update.effective_user.id))
        return
    profile = get_profile(update.effective_user.id) or {}
    system = (
        "أنت RASHED AI، كوتش لياقة عربي ودود. أنت ذكاء اصطناعي ولست طبيبًا أو مدربًا بشريًا. "
        "أعط إرشادات عامة قصيرة مبنية على ملف المستخدم، لا تشخّص ولا تغيّر أدوية ولا تعد بنتائج. "
        "إذا ظهر ألم شديد أو أعراض مقلقة أو اضطراب أكل أو حالة طبية معقدة، أوقف التخصيص ووجّه لمختص. "
        f"ملف المستخدم: {profile}"
    )
    def call():
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}], "temperature": 0.4, "max_tokens": 500}, timeout=25)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    try:
        reply = await asyncio.to_thread(call)
        await update.effective_message.reply_text(esc(reply), parse_mode="HTML")
    except Exception:
        await update.effective_message.reply_text("تعذر الاتصال بالكوتش الذكي الآن. أقدر أساعدك من خلال الخطة وتسجيل التمرين، أو جرّب بعد قليل.")


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    if data == "home":
        await query.edit_message_text(welcome(query.from_user), parse_mode="HTML", reply_markup=menu(uid == ADMIN_ID))
    elif data == "assessment":
        drafts[uid] = {"preferred_name": query.from_user.first_name or ""}
        set_state(uid, "name")
        await query.edit_message_text("<b>التقييم 1/8</b>\nشو بتحب أناديك؟", parse_mode="HTML")
    elif data == "assessment_confirm":
        profile = drafts.get(uid, {})
        save_profile(uid, profile)
        set_state(uid, "")
        plan = starter_plan(profile)
        save_plan(uid, plan)
        drafts.pop(uid, None)
        await query.edit_message_text("تم حفظ ملفك وإنشاء خطتك الأولى ✅\n\n" + format_plan(plan), parse_mode="HTML", reply_markup=back_menu(uid))
    elif data == "plan":
        plan = get_plan(uid)
        await query.edit_message_text(format_plan(plan) if plan else "أكمل التقييم أولًا حتى أنشئ خطتك.", parse_mode="HTML", reply_markup=menu(uid == ADMIN_ID) if not plan else back_menu(uid))
    elif data == "profile":
        profile = get_profile(uid)
        await query.edit_message_text(format_profile(profile) if profile else "لا يوجد ملف محفوظ بعد. ابدأ التقييم.", parse_mode="HTML", reply_markup=back_menu(uid))
    elif data == "progress":
        logs = recent_workouts(uid)
        completed = sum(1 for log in logs if log["completed"])
        await query.edit_message_text(f"<b>📈 تقدّمك</b>\n\nتمارين مكتملة: <b>{completed}</b> من آخر {len(logs)} تسجيلات.\n\nاستمر بهدوء؛ لا نحتاج للكمال.", parse_mode="HTML", reply_markup=back_menu(uid))
    elif data == "log":
        await cmd_log(update, context)
    elif data in ("workout_done", "workout_missed"):
        completed = data == "workout_done"
        set_state(uid, "workout_effort")
        drafts[uid] = {"completed": completed}
        await query.edit_message_text("كم كان الجهد من 1 إلى 10؟ أرسل رقمًا.")
    elif data == "ask":
        set_state(uid, "ask")
        await query.edit_message_text("اكتب سؤالك التدريبي، وسأجيبك ضمن حدود السلامة. لإلغاء الوضع أرسل /start.")
    elif data == "nutrition":
        await query.edit_message_text("<b>🍽 مبادئ تغذية بسيطة</b>\n\n• أضف مصدر بروتين لمعظم الوجبات.\n• اجعل الخضار أو الفاكهة جزءًا من يومك.\n• اشرب الماء بانتظام.\n• لا تحتاج حمية قاسية أو وعودًا سريعة.\n\nهذه إرشادات عامة وليست وصفة طبية.", parse_mode="HTML", reply_markup=back_menu(uid))
    elif data == "privacy":
        await query.edit_message_text("<b>🔐 الخصوصية</b>\n\nنحفظ فقط ما يلزم لتخصيص الخطة والمتابعة: ملفك، خطتك، وسجل التمارين. لا نحتاج معلومات بطاقات أو تتبع GPS. يمكنك طلب /delete_data لحذفها.", parse_mode="HTML", reply_markup=back_menu(uid))
    elif data == "help":
        await query.edit_message_text("استخدم /start للعودة، /assessment للتقييم، /profile لملفك، /my_plan للخطة، /log_workout لتسجيل تمرين، و/delete_data للحذف.", reply_markup=back_menu(uid))
    elif data == "delete":
        await cmd_delete(update, context)
    elif data == "delete_confirm":
        delete_user_data(uid)
        drafts.pop(uid, None)
        await query.edit_message_text("تم حذف ملفك وخططك وسجل تمارينك نهائيًا. إذا رجعت، سنبدأ من الصفر.")
    elif data == "stats" and uid == ADMIN_ID:
        await query.edit_message_text(f"<b>📊 الإحصائيات</b>\n\nالمستخدمون: <b>{user_count()}</b>", parse_mode="HTML", reply_markup=back_menu(uid))


async def workout_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = get_state(uid)
    text = (update.effective_message.text or "").strip()
    if state == "workout_effort":
        if not text.isdigit() or not 1 <= int(text) <= 10:
            await update.effective_message.reply_text("أرسل رقمًا من 1 إلى 10.")
            return
        drafts.setdefault(uid, {})["effort"] = int(text)
        set_state(uid, "workout_pain")
        await update.effective_message.reply_text("هل ظهر ألم غير معتاد؟", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لا ✅", callback_data="pain_no")], [InlineKeyboardButton("نعم ⚠️", callback_data="pain_yes")]]))
    elif state == "workout_pain":
        return
    elif state == "ask":
        await answer_coach(update, text)
    else:
        await handle_assessment_text(update, state, text)


async def pain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    draft = drafts.get(uid, {})
    pain = query.data == "pain_yes"
    save_workout(uid, bool(draft.get("completed")), draft.get("effort"), pain)
    set_state(uid, "")
    drafts.pop(uid, None)
    message = "تم تسجيل تمرينك ✅"
    if pain:
        message += "\n\n⚠️ أوقف التمرين عند الألم غير المعتاد، واستشر مختصًا إذا استمر أو كان شديدًا."
    await query.edit_message_text(message, reply_markup=back_menu(uid))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.exception("Unhandled Telegram error", exc_info=context.error)


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("MAIN_BOT_TOKEN is missing")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("assessment", cmd_assessment))
    application.add_handler(CommandHandler("profile", cmd_profile))
    application.add_handler(CommandHandler(["my_plan", "plan"], cmd_plan))
    application.add_handler(CommandHandler(["log_workout", "log"], cmd_log))
    application.add_handler(CommandHandler("progress", cmd_progress))
    application.add_handler(CommandHandler("weekly_review", cmd_weekly))
    application.add_handler(CommandHandler("edit", cmd_edit))
    application.add_handler(CommandHandler("delete_data", cmd_delete))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CallbackQueryHandler(pain_callback, pattern=r"^pain_(yes|no)$"))
    application.add_handler(CallbackQueryHandler(callbacks))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, workout_followup))
    application.add_error_handler(error_handler)
    return application


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/ping", "/status"):
            body = b'{"status":"operational","service":"rashd-ai-telegram"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="health-server").start()
    logging.info("Health server listening on port %s", port)


if __name__ == "__main__":
    init_db()
    start_health_server()
    logging.info("Starting RASHED AI Telegram coach")
    build_application().run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
