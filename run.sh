#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  راشد الاستخباراتي — سكريبت التشغيل الموحّد
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ Rashd-Ai Intelligence System v2.0"
echo "◈ تصميم وتطوير: راشد خليل أبو زيتونه"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# إيقاف أي نسخ قديمة بشكل حازم
echo "🛑 إيقاف النسخ القديمة..."
pkill -TERM -f "main_bot.py"    2>/dev/null
pkill -TERM -f "tracker_server.py" 2>/dev/null
sleep 3
pkill -KILL -f "main_bot.py"    2>/dev/null
pkill -KILL -f "tracker_server.py" 2>/dev/null
sleep 2
echo "✅ تم إيقاف النسخ القديمة."

# تشغيل خادم التعقب (Flask) في الخلفية
echo "📡 تشغيل خادم التعقب (tracker_server.py)..."
python3 tracker_server.py &
TRACKER_PID=$!
echo "   PID: $TRACKER_PID"

# انتظار حتى يبدأ الـ Flask server
sleep 4

# تشغيل البوت الرئيسي
echo "🤖 تشغيل البوت الرئيسي (main_bot.py)..."
python3 main_bot.py

# عند إغلاق البوت الرئيسي، نقتل خادم التعقب أيضاً
echo "🛑 إغلاق خادم التعقب..."
kill $TRACKER_PID 2>/dev/null
echo "✅ النظام أُغلق بنجاح."
