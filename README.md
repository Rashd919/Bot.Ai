# Rashd AI Intelligence System 🤖

نظام استخبارات متطور يعتمد على بوتين منفصلين لتتبع البيانات وتقديم خدمات الذكاء الاصطناعي.

## 🚀 الميزات الرئيسية

1.  **Rashd IP Tracker Bot:**
    *   سحب عنوان الـ IP والـ GPS للزوار.
    *   إرسال النتائج فوراً إلى القناة المخصصة.
    *   نظام تمويه (Camouflage) يحول الزائر لصفحة 404 بعد سحب البيانات.
    *   خادم Flask مدمج لضمان التشغيل المستمر (Uptime).

2.  **Rashid Thunder Bot:**
    *   مساعد ذكي يعتمد على نموذج Llama 3 (Groq).
    *   البحث المتقدم في الويب (Tavily).
    *   فحص تسريبات البيانات (DeHashed).
    *   فحص الروابط والملفات (VirusTotal).
    *   **نظام مراقبة المسؤول:** إشعارات فورية للمسؤول عن أي نشاط من مستخدمين آخرين.

## 🛠 الإعداد والتشغيل

### 1. المتطلبات
*   Python 3.10+
*   تثبيت المكتبات المطلوبة:
    ```bash
    pip install -r requirements.txt
    ```

### 2. إعداد المفاتيح (Secrets)
قم بإنشاء ملف باسم `.env` في المجلد الرئيسي للمشروع (استخدم `.env.example` كدليل) وضع فيه المفاتيح التالية:

```env
TRACKER_BOT_TOKEN=8346034907:AAHv4694Nf1Mn3JSwcUeb1Zkl1ZSlsODIx8
MAIN_BOT_TOKEN=8556004865:AAE_W9SXGVxgTcpSCufs_hemEb_mOX_ioj0
GROQ_API_KEY=your_groq_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
IPINFO_TOKEN=your_ipinfo_token_here
DEHASHED_API_KEY=your_dehashed_api_key_here
VIRUSTOTAL_API_KEY=your_virustotal_api_key_here
ADMIN_ID=8346034907
CHANNEL_ID=-1003835973914
```

### 3. التشغيل
يمكنك تشغيل البوتين معاً باستخدام الملف التنفيذي:
```bash
chmod +x run.sh
./run.sh
```

## 🔒 السرية والأمان
*   تمت إضافة ملف `.gitignore` لمنع رفع ملف `.env` الحقيقي إلى GitHub.
*   لا تشارك ملف `.env` الخاص بك مع أي شخص.
*   استخدم `UptimeRobot` لمراقبة الرابط الرئيسي لضمان بقاء البوت يعمل 24/7.

---
تم التطوير بواسطة **Manus AI** 🤖
