import os
import threading
import asyncio
from flask import Flask, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message

# ======================= CONFIGURACIÓN =======================
API_ID = 27113333
API_HASH = "cfe0755384e418f8b0ed6b762843aa68"
BOT_TOKEN = "6912365083:AAEviaiGxRUF0RFHjmgkPK7YswqFCuTcHNI"

# ======================= FLASK APP =======================
app = Flask(__name__)  # <--- CAMBIADO a "app"

@app.route('/')
def home():
    return jsonify({"status": "running", "service": "Telegram Bot"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# ======================= FUNCIÓN DEL BOT =======================
def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot = Client("telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    @bot.on_message(filters.command("start"))
    async def start_cmd(client, message):
        await message.reply_text("¡Hola! Soy un bot de Telegram.")

    @bot.on_message(filters.command("ping"))
    async def ping_cmd(client, message):
        await message.reply_text("🏓 Pong!")

    @bot.on_message()
    async def fallback(client, message):
        await message.reply_text("Comando no reconocido. Usa /start o /ping.")

    print("🤖 Bot iniciado correctamente.")
    bot.run()

# ======================= INICIO =======================
if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
else:
    threading.Thread(target=start_bot, daemon=True).start()