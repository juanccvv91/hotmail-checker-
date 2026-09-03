import os
import threading
import asyncio
import re
import traceback
from flask import Flask, jsonify
from pyrogram import Client, filters

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
    """Inicia Pyrogram en un event loop propio, compatible con Gunicorn."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot = Client("telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    @bot.on_message(filters.regex(re.compile(r"^/start(?:@\w+)?(?:\s|$)", re.IGNORECASE)))
    async def start_cmd(client, message):
        await message.reply_text("¡Hola! Soy un bot de Telegram.")

    @bot.on_message(filters.command("ping"))
    async def ping_cmd(client, message):
        await message.reply_text("🏓 Pong!")

    @bot.on_message()
    async def fallback(client, message):
        await message.reply_text("Comando no reconocido. Usa /start o /ping.")

    try:
        loop.run_until_complete(bot.start())
        print("🤖 Bot iniciado correctamente y escuchando mensajes.", flush=True)
        loop.run_forever()
    except Exception:
        print("❌ Error iniciando el bot:", flush=True)
        traceback.print_exc()
    finally:
        try:
            if bot.is_connected:
                loop.run_until_complete(bot.stop())
        except Exception:
            traceback.print_exc()
        finally:
            loop.close()

# ======================= INICIO =======================
if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
else:
    threading.Thread(target=start_bot, daemon=True).start()