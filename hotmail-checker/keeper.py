# keeper.py - Servidor web para mantener vivo en Render
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "service": "Telegram Bot",
        "version": "1.0"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)