#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  تثبيت خدمة راشد — التشغيل المستمر 24/7
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_FILE="$BOT_DIR/systemd/rashd-bot.service"

# تحديث مسار المجلد ومترجم بايثون في ملف الخدمة تلقائياً
PYTHON_BIN="$(which python3)"
sed -i "s|WorkingDirectory=.*|WorkingDirectory=$BOT_DIR|" "$SERVICE_FILE"
sed -i "s|ExecStart=.*|ExecStart=$PYTHON_BIN $BOT_DIR/main_bot.py|" "$SERVICE_FILE"
sed -i "s|EnvironmentFile=.*|EnvironmentFile=$BOT_DIR/.env|" "$SERVICE_FILE"
sed -i "s|StandardOutput=.*|StandardOutput=append:$BOT_DIR/bot_service.log|" "$SERVICE_FILE"
sed -i "s|StandardError=.*|StandardError=append:$BOT_DIR/bot_service.log|" "$SERVICE_FILE"

# نسخ ملف الخدمة إلى systemd
sudo cp "$SERVICE_FILE" /etc/systemd/system/rashd-bot.service

# تفعيل الخدمة وتشغيلها
sudo systemctl daemon-reload
sudo systemctl enable rashd-bot.service
sudo systemctl restart rashd-bot.service

echo ""
echo "✅ تم تثبيت خدمة راشد بنجاح!"
echo "   الحالة:  sudo systemctl status rashd-bot"
echo "   السجل:   tail -f $BOT_DIR/bot_service.log"
echo "   إيقاف:   sudo systemctl stop rashd-bot"
echo "   إعادة:   sudo systemctl restart rashd-bot"
