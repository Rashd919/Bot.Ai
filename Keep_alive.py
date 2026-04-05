import os
import threading
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running — راشد الاستخباراتي يعمل", 200

@app.route("/health")
def health():
    return {"status": "ok", "bot": "Rashd-Ai"}, 200

def keep_alive():
    port = int(os.getenv("PORT", 8080))
    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    t.start()
    print(f"🌐 Keep-alive server started on port {port}")
