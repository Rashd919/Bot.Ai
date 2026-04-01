# Rashd-Ai — النظام الاستخباراتي عبر تلجرام

## نظرة عامة
نظام بوتات تلجرام متقدم (Rashid_Thunder_bot) مع خادم تعقب IP/GPS مدمج.
**تصميم وتطوير: أبو سعود**

## هيكل الملفات
```
main_bot.py      — البوت الرئيسي (راشد الاستخباراتي)
tracker_bot.py   — خادم Flask لتعقب IP/GPS
run.sh           — سكريبت التشغيل الموحّد
```

## متغيرات البيئة المطلوبة
| المتغير | الوصف |
|---|---|
| MAIN_BOT_TOKEN | توكن البوت الرئيسي |
| TRACKER_BOT_TOKEN | توكن بوت التعقب |
| GROQ_API_KEY | مفتاح Groq AI (LLaMA 3 + Vision) |
| TAVILY_API_KEY | مفتاح Tavily للبحث الحي |
| IPINFO_TOKEN | مفتاح IPInfo لتحليل IP |
| VIRUSTOTAL_KEY | مفتاح VirusTotal لفحص الروابط |
| DEHASHED_KEY | مفتاح DeHashed لفحص التسريبات |
| TARGET_CHANNEL_ID | معرّف قناة التلجرام المستهدفة |
| BOT_SERVER_URL | عنوان الخادم العام لروابط التعقب |

## ميزات النظام
1. **الذكاء الاصطناعي** — Groq LLaMA 3 بأسلوب استخباراتي عربي
2. **الرؤية الحاسوبية** — تحليل الصور عبر Groq Vision
3. **البحث الحي** — Tavily API للبحث الفوري في الإنترنت
4. **تحليل IP** — IPInfo للتحليل الجغرافي والبنيوي
5. **فحص الروابط** — VirusTotal (70+ محرك أمني)
6. **فحص التسريبات** — DeHashed لقواعد البيانات العالمية
7. **روابط التعقب** — IP/GPS Logger مع تقارير فورية للقناة
8. **الكشف التلقائي** — يحدد URL/IP/إيميل تلقائياً من النص

## الأوامر
- `/start` — القائمة الرئيسية
- `/ip <IP>` — تحليل عنوان IP
- `/scan <URL>` — فحص رابط أمنياً
- `/breach <email|phone>` — فحص التسريبات
- `/search <query>` — بحث فوري
- `/logger [label]` — توليد رابط تعقب

## التقنيات المستخدمة
- Python 3.11
- python-telegram-bot v20+
- Flask (خادم التعقب)
- Groq AI API
- Tavily Search API
- VirusTotal API v3
- DeHashed API
- IPInfo API
