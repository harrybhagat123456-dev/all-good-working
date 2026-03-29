import os
import threading
import time
import requests
from flask import Flask, jsonify

app = Flask(__name__)

PORT = int(os.environ.get("PORT", 5000))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html lang="en">
<body>
    <div style="text-align:center; margin-top:80px; font-family:monospace;">
        <pre style="color:blue; font-size:18px;">
&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;&#9608;
&#9608;&#9608;&#9617;&#9604;&#9604;&#9604;&#9617;&#9608;&#9617;&#9604;&#9604;&#9600;&#9608;&#9604;&#9617;&#9604;&#9608;&#9608;&#9617;&#9600;&#9608;&#9608;&#9617;&#9604;&#9617;&#9604;&#9608;&#9608;
&#9608;&#9608;&#9604;&#9604;&#9604;&#9600;&#9600;&#9608;&#9617;&#9600;&#9600;&#9617;&#9608;&#9608;&#9617;&#9608;&#9608;&#9617;&#9608;&#9617;&#9608;&#9617;&#9608;&#9608;&#9617;&#9608;&#9608;&#9608;
&#9608;&#9608;&#9617;&#9600;&#9600;&#9600;&#9617;&#9608;&#9617;&#9608;&#9608;&#9617;&#9608;&#9600;&#9617;&#9600;&#9608;&#9608;&#9617;&#9608;&#9608;&#9604;&#9617;&#9608;&#9600;&#9617;&#9600;&#9608;&#9608;
&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;&#9600;
        </pre>
        <b>Powered By SAINI BOTS</b>
        <br><br>
        <span style="color:green;">&#10003; Bot is alive and running!</span>
        <br><br>
        <footer style="color:gray; font-size:12px;">
            &copy; 2025 Video Downloader. All rights reserved.
        </footer>
    </div>
</body>
</html>
"""

@app.route("/ping")
def ping():
    return jsonify({"status": "alive", "message": "SAINI BOT is running!"}), 200

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


def self_ping():
    """
    Ping the server every 10 minutes to prevent Render free-plan spin-down.
    Runs in a daemon thread — completely isolated from Flask request handling
    so pings NEVER block or slow down ongoing bot processing.
    """
    if not RENDER_URL:
        print("[ALIVE] No RENDER_EXTERNAL_URL set — self-ping disabled.")
        return

    # Wait a bit on startup before first ping
    time.sleep(30)

    while True:
        try:
            resp = requests.get(f"{RENDER_URL}/ping", timeout=8)
            print(f"[ALIVE] Self-ping OK: {resp.status_code}")
        except requests.exceptions.Timeout:
            print("[ALIVE] Self-ping timed out — will retry next cycle.")
        except requests.exceptions.ConnectionError:
            print("[ALIVE] Self-ping connection error — will retry next cycle.")
        except Exception as e:
            print(f"[ALIVE] Self-ping error: {e}")

        time.sleep(600)  # 10 minutes


if __name__ == "__main__":
    # Self-ping runs in its own daemon thread — dies cleanly if the main
    # process exits, and NEVER shares state with Flask's request threads.
    ping_thread = threading.Thread(target=self_ping, daemon=True, name="self-ping")
    ping_thread.start()

    print(f"[ALIVE] Web server starting on port {PORT}")
    # threaded=True: each HTTP request gets its own thread so pings never
    # queue up or block one another, keeping response times fast.
    app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False)
