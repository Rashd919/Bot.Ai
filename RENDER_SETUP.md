# دليل التثبيت على Render 🚀

## المتطلبات
- حساب على [Render.com](https://render.com)
- رابط مستودع GitHub
- توكنات Telegram
- مفاتيح API (Groq, Tavily, وغيرها)

---

## الخطوة 1: إنشاء خدمة جديدة

1. اذهب إلى [Render Dashboard](https://dashboard.render.com)
2. اضغط **"New +"** ثم اختر **"Web Service"**
3. اختر **"Connect a repository"** وربط مستودع GitHub الخاص بك
4. ملأ التفاصيل:
   - **Name:** `rashd-ai-bot` (أو أي اسم تفضله)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python3 main_bot.py`

---

## الخطوة 2: تعيين متغيرات البيئة

في صفحة الخدمة، اذهب إلى **"Environment"** وأضف المتغيرات التالية:

### متغيرات Telegram (مطلوبة)
```
MAIN_BOT_TOKEN=your_main_bot_token_here
TRACKER_BOT_TOKEN=your_tracker_bot_token_here
ADMIN_ID=your_telegram_user_id
TARGET_CHANNEL_ID=-1003770774871
CONTROL_CHANNEL_ID=-1003751955886
```

### متغيرات الذكاء الاصطناعي والبحث (مطلوبة)
```
GROQ_API_KEY=your_groq_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

### متغيرات الخدمات الإضافية (اختيارية)
```
VIRUSTOTAL_API_KEY=your_virustotal_api_key_here
LEAKCHECK_KEY=your_leakcheck_api_key_here
IPINFO_TOKEN=your_ipinfo_token_here
```

### متغيرات Render (تلقائية)
```
PORT=5000
RENDER_EXTERNAL_URL=سيتم ملؤه تلقائياً من قبل Render
```

---

## الخطوة 3: التحقق من Procfile

تأكد من أن `Procfile` يحتوي على:
```
web: python3 main_bot.py
```

**ملاحظة:** يجب أن يكون `web` وليس `worker` لتفعيل الرابط العام.

---

## الخطوة 4: النشر

1. اضغط **"Deploy"** أو **"Manual Deploy"**
2. انتظر حتى ينتهي البناء (Build)
3. تحقق من **Logs** للتأكد من عدم وجود أخطاء

---

## الخطوة 5: اختبار الخدمة

### اختبار البوت
```
أرسل /start للبوت على Telegram
يجب أن ترى القائمة الرئيسية
```

### اختبار رابط التعقب
```
أرسل /grab لإنشاء رابط
انسخ الرابط واختبره في متصفح
يجب أن ترى صفحة إخبارية
```

### اختبار الذكاء الاصطناعي
```
اضغط على "🤖 ذكاء اصطناعي"
أرسل سؤال مثل: "من هو أذكى إنسان في العالم؟"
يجب أن يبحث عبر الإنترنت ويعطي إجابة محدثة
```

---

## استكشاف الأخطاء

### المشكلة: الرابط يعطي صفحة فارغة

**الحل:**
1. تحقق من أن `Procfile` يحتوي على `web:` وليس `worker:`
2. تحقق من أن `PORT` معرّف في Environment
3. تحقق من Logs للأخطاء

```bash
# في Render Logs، يجب أن ترى:
📡 خادم التعقب يعمل على المنفذ 5000
⚡ راشد الاستخباراتي v2.0 — يعمل الآن
```

### المشكلة: الذكاء الاصطناعي لا يبحث عبر الإنترنت

**الحل:**
1. تحقق من أن `GROQ_API_KEY` معرّف
2. تحقق من أن `TAVILY_API_KEY` معرّف
3. جرّب سؤالاً يتطلب بحثاً مثل: "أحدث أخبار التكنولوجيا"

### المشكلة: البوت لا يستجيب

**الحل:**
1. تحقق من أن `MAIN_BOT_TOKEN` صحيح
2. تحقق من أن البوت مفعّل على BotFather
3. تحقق من Logs للأخطاء

---

## الحد من الموارد

Render توفر خطة مجانية محدودة. للحصول على أفضل أداء:

1. **استخدم خطة مدفوعة** إذا كان لديك عدد كبير من المستخدمين
2. **استخدم UptimeRobot** للحفاظ على الخدمة نشطة
3. **راقب الموارد** في Render Dashboard

---

## الأمان

### ✅ أفضل الممارسات
- ✅ لا تشارك `MAIN_BOT_TOKEN` أو أي مفاتيح
- ✅ استخدم Environment Variables فقط
- ✅ فعّل Two-Factor Authentication على حسابك
- ✅ راجع Logs بانتظام

### ⚠️ تحذيرات
- ⚠️ لا تضع المفاتيح في الكود
- ⚠️ لا تشارك ملف `.env` الخاص بك
- ⚠️ غيّر المفاتيح إذا تم الكشف عنها

---

## الدعم والمساعدة

إذا واجهت مشكلة:

1. **تحقق من Logs:**
   - اذهب إلى Render Dashboard
   - اختر الخدمة
   - اضغط على "Logs"

2. **تحقق من المتطلبات:**
   - تأكد من أن `requirements.txt` محدث
   - تأكد من أن جميع المكتبات مثبتة

3. **تواصل مع المطور:**
   - البريد: `hhh123rrhhh@gmail.com`
   - الواتساب: `+962775866283`

---

## الموارد المفيدة

- [Render Documentation](https://render.com/docs)
- [Python on Render](https://render.com/docs/deploy-python)
- [Environment Variables](https://render.com/docs/environment-variables)
- [Telegram Bot API](https://core.telegram.org/bots/api)

---

## الملاحظات الأخيرة

- ✅ الخدمة ستعمل 24/7 على Render
- ✅ الرابط العام سيكون متاحاً دائماً
- ✅ الذكاء الاصطناعي سيبحث عبر الإنترنت تلقائياً
- ✅ يمكنك إعادة النشر في أي وقت

---

**تم آخر تحديث:** 2026-04-06  
**الإصدار:** v2.1
