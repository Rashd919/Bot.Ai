#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  راشد الاستخباراتي — سكريبت التشغيل الموحّد
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ Rashd-Ai Intelligence System v2.0"
echo "◈ تصميم وتطوير: راشد خليل أبو زيتونه"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# إيقاف أي نسخة قديمة بشكل حازم
echo "🛑 إيقاف النسخ القديمة..."
pkill -TERM -f "tracker_bot.py" 2>/dev/null
pkill -TERM -f "main_bot.py"    2>/dev/null
sleep 3
pkill -KILL -f "tracker_bot.py" 2>/dev/null
pkill -KILL -f "main_bot.py"    2>/dev/null
sleep 2
echo "✅ تم إيقاف النسخ القديمة."

# تشغيل خادم التعقب في الخلفية
echo "📡 تشغيل خادم التعقب (Flask)..."
python3 tracker_bot.py &
TRACKER_PID=$!
echo "   PID: $TRACKER_PID"

# انتظار حتى يبدأ Flask
sleep 3

# تشغيل البوت الرئيسي
echo "🤖 تشغيل البوت الرئيسي (راشد)..."
python3 main_bot.py

# إنهاء خادم التعقب عند توقف البوت الرئيسي
kill $TRACKER_PID 2>/dev/null
echo "النظام أُغلق."
