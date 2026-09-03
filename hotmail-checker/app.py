# app.py - Flask para mantener el servicio vivo
import os
from flask import Flask, jsonify

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return jsonify({
        "status": "running",
        "service": "Telegram Bot",
        "version": "1.0"
    })

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port)