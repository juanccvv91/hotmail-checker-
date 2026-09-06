import os
import re
import time
import threading
import asyncio
import requests
from datetime import datetime
from flask import Flask, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message, Document

# ======================= CONFIGURACIÓN =======================
API_ID = 27113333
API_HASH = "cfe0755384e418f8b0ed6b762843aa68"
BOT_TOKEN = "6912365083:AAEviaiGxRUF0RFHjmgkPK7YswqFCuTcHNI"

# ======================= FLASK APP =======================
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({"status": "running", "service": "Telegram Bot"})

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# ======================= BOT DE TELEGRAM =======================
def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Client("telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    # ===== VARIABLES GLOBALES DEL SCRAPPER =====
    CHANNEL_ID = None  # Se guarda con /id
    PROCESSING = False

    # ===== FUNCIÓN PARA OBTENER INFO DEL BIN =====
    def get_bin_info(bin_num):
        try:
            rs = requests.get(f"https://projectslost.xyz/bin/?bin={bin_num}", timeout=10).json()
            return {
                "country": rs["country"]["name"],
                "flag": rs["country"]["flag"],
                "bank": rs["bank"]["name"],
                "brand": rs["brand"],
                "type": rs["type"],
                "level": rs["level"],
                "currency": rs["country"]["currency"]
            }
        except:
            return None

    # ===== FUNCIÓN PARA PROCESAR UNA CC =====
    def process_cc(cc_line):
        """Procesa una línea de CC y retorna el mensaje formateado"""
        # Extraer números
        numbers = re.findall(r'\d+', cc_line)
        if len(numbers) < 4:
            return None
        
        cc = numbers[0]
        mm = numbers[1]
        yy = numbers[2]
        cvv = numbers[3]
        
        # Validaciones
        if len(cc) < 15 or len(cc) > 16:
            return None
        if len(mm) > 2:
            return None
        if len(yy) > 4 or len(yy) < 2:
            return None
        if len(cvv) > 4 or len(cvv) < 3:
            return None
        
        # Ajustar formato
        if mm.startswith('2'):
            mm, yy = yy, mm
        if len(mm) >= 3:
            mm, yy, cvv = yy, cvv, mm
        
        bin_num = cc[0:6]
        info = get_bin_info(bin_num)
        
        if info:
            mensaje = f"""
࿓ Scrapper 🏷    
━━━━━━━ቿ━━━━━━━
ꁴBin ⌯ <code>{bin_num}</code>
ꁴCC ⌯  <code>{cc}|{mm}|{yy}|{cvv}</code>
ꁴExtra ⌯ <code>{cc[0:12]}xxxx|{mm}|{yy}|xxx</code>
━━━━━━━ቿ━━━━━━━
ꁴBank ⌯ <code>{info['bank']}</code>
ꁴBinlevel ⌯ <code>{info['brand']}</code> - <code>{info['level']}</code>
ꁴCountry ⌯ <code>{info['country']} | {info['flag']}</code>
━━━━━━━ቿ━━━━━━━
owen:@darkbrx
━━━━━━━ቿ━━━━━━━
"""
            return mensaje
        return None

    # ===== COMANDO /start =====
    @app.on_message(filters.command("start"))
    async def start_cmd(client, message):
        await message.reply_text(
            "🤖 **Bot Scrapper de CCs**\n\n"
            "📌 **Comandos:**\n"
            "  `/id <ID_DEL_CANAL>` - Configurar canal de destino\n"
            "  📤 **Sube un archivo .txt** con las CCs\n\n"
            "📄 **Formato del archivo:**\n"
            "  `cc|mm|yy|cvv` o `cc:mm:yy:cvv`\n"
            "  Una CC por línea\n\n"
            "⚡ Desarrollado con Pyrogram"
        )

    # ===== COMANDO /id =====
    @app.on_message(filters.command("id"))
    async def set_channel(client, message):
        global CHANNEL_ID
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text("❌ Usa: `/id -100123456789`")
                return
            
            channel_id = int(parts[1])
            CHANNEL_ID = channel_id
            
            await message.reply_text(
                f"✅ Canal configurado correctamente.\n"
                f"📌 ID: `{channel_id}`\n\n"
                f"📤 Ahora sube un archivo .txt con las CCs."
            )
        except ValueError:
            await message.reply_text("❌ ID inválido. Debe ser un número.")

    # ===== MANEJADOR DE ARCHIVOS TXT =====
    @app.on_message(filters.document & filters.private)
    async def handle_document(client, message):
        global CHANNEL_ID, PROCESSING
        
        if not CHANNEL_ID:
            await message.reply_text(
                "❌ Primero configura el canal con `/id -100123456789`"
            )
            return
        
        if PROCESSING:
            await message.reply_text("⏳ Ya estoy procesando un archivo. Espera...")
            return
        
        document = message.document
        if not document.file_name.endswith('.txt'):
            await message.reply_text("❌ Solo acepto archivos .txt")
            return
        
        # Descargar archivo
        status_msg = await message.reply_text("📥 Descargando archivo...")
        file_path = await client.download_media(document)
        
        if not file_path:
            await status_msg.edit_text("❌ Error al descargar el archivo.")
            return
        
        # Leer y procesar
        await status_msg.edit_text("📖 Procesando tarjetas...")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            total = len([l for l in lines if l.strip()])
            validas = 0
            invalidas = 0
            
            PROCESSING = True
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                mensaje = process_cc(line)
                if mensaje:
                    try:
                        # Enviar al canal
                        photo_path = "img.jpg"  # Ruta de la imagen
                        if os.path.exists(photo_path):
                            await client.send_photo(CHANNEL_ID, photo_path, caption=mensaje)
                        else:
                            await client.send_message(CHANNEL_ID, mensaje)
                        validas += 1
                    except Exception as e:
                        print(f"Error enviando: {e}")
                        invalidas += 1
                else:
                    invalidas += 1
                
                # Actualizar progreso cada 10
                if i % 10 == 0:
                    await status_msg.edit_text(
                        f"📤 Procesando... {i+1}/{total} | ✅ {validas} | ❌ {invalidas}"
                    )
            
            await status_msg.edit_text(
                f"✅ **Procesamiento completado**\n\n"
                f"📊 Total: {total}\n"
                f"✅ Válidas: {validas}\n"
                f"❌ Inválidas: {invalidas}\n"
                f"📌 Enviadas al canal: {CHANNEL_ID}"
            )
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
        finally:
            PROCESSING = False
            if os.path.exists(file_path):
                os.remove(file_path)

    # ===== COMANDO /ping =====
    @app.on_message(filters.command("ping"))
    async def ping_cmd(client, message):
        await message.reply_text("🏓 Pong! Bot activo ✅")

    # ===== FALLBACK =====
    @app.on_message()
    async def fallback(client, message):
        await message.reply_text(
            "❌ Comando no reconocido.\n"
            "Usa /start para ver los comandos disponibles."
        )

    print("🤖 Bot iniciado correctamente.")
    app.run()

# ======================= INICIO =======================
if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
else:
    threading.Thread(target=start_bot, daemon=True).start()