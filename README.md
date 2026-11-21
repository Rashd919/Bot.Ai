# RASHED AI — كوتشك الذكي عبر Telegram

بوت Telegram عربي للتدريب والتغذية والمتابعة، مبني ليكون كوتشًا ذكيًا ودودًا للبالغين. يحفظ هدف المستخدم وخطته وسجل تمارينه، ويقدّم إرشادات عامة قابلة للتعديل مع قواعد سلامة واضحة.

> RASHED AI ذكاء اصطناعي وليس طبيبًا أو مدربًا بشريًا معتمدًا. النصائح عامة وليست تشخيصًا أو علاجًا، ولا توجد وعود مضمونة بالنتائج.

## ما الذي يقدمه؟

- تقييم أولي متدرّج: الهدف، الخبرة، الأيام، مدة الحصة، المكان والمعدات.
- خطة تدريب منظمة قابلة للتعديل مع بدائل للتمارين.
- تسجيل التمرين والجهد والألم أو الانزعاج.
- ملف مستخدم دائم وخطة وسجل تقدم باستخدام SQLite.
- مراجعة أسبوعية بسيطة.
- أوامر واضحة لتعديل الملف أو حذف البيانات.
- واجهة أزرار عربية مناسبة للهاتف.
- خادم صحة `/status` متوافق مع Render.
- لا يوجد GPS أو روابط سحب أو جمع خفي لبيانات الزوار.

## التشغيل محليًا

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MAIN_BOT_TOKEN="توكن البوت"
export ADMIN_ID="معرّف المدير"
python3 main_bot.py
```

اختياريًا، يمكن تفعيل المحادثة الحرة للكوتش عبر:

```bash
export GROQ_API_KEY="مفتاح Groq"
```

## أوامر Telegram

```text
/start
/assessment
/profile
/my_plan
/log_workout
/progress
/weekly_review
/edit
/delete_data
/help
```

## النشر على Render

استخدم Web Service مع أمر التشغيل الموجود في `Procfile`:

```text
web: python3 main_bot.py
```

أضف `MAIN_BOT_TOKEN` و`ADMIN_ID` كـ Secrets في Render. لا تضع أي توكن داخل GitHub أو ملفات الكود. قاعدة SQLite مناسبة كبداية، لكن عند زيادة المستخدمين ينبغي نقلها إلى PostgreSQL أو خدمة تخزين دائمة.

## الاختبارات المحلية

```bash
python3 -m py_compile main_bot.py coach_data.py coach_logic.py
```
