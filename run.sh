#!/bin/bash

# Start the IP Tracker bot and Flask app in the background
python3 /home/ubuntu/Bot.Ai/tracker_bot.py &

# Start the Main AI bot
python3 /home/ubuntu/Bot.Ai/main_bot.py

# Wait for all background processes to finish (though Telegram bots usually run indefinitely)
wait
