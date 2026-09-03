# bot.py - Bot de Telegram con Pyrogram
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# ============================================
# CONFIGURACIÓN
# ============================================
API_ID = 27113333
API_HASH = "cfe0755384e418f8b0ed6b762843aa68"
BOT_TOKEN = "6912365083:AAEviaiGxRUF0RFHjmgkPK7YswqFCuTcHNI"

# ============================================
# INICIALIZAR BOT
# ============================================
app = Client(
    "telegram_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ============================================
# COMANDOS
# ============================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Maneja el comando /start"""
    user = message.from_user
    first_name = user.first_name if user else "Usuario"
    
    await message.reply_text(
        f"👋 ¡Hola {first_name}!\n\n"
        f"🤖 Soy un bot de Telegram.\n"
        f"📌 Comandos disponibles:\n"
        f"  /start - Ver este mensaje\n"
        f"  /ping - Verificar que el bot está vivo\n\n"
        f"⚡ Desarrollado con Pyrogram"
    )

@app.on_message(filters.command("ping"))
async def ping_command(client: Client, message: Message):
    """Maneja el comando /ping"""
    await message.reply_text("🏓 Pong! Bot activo ✅")

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Maneja el comando /help"""
    await message.reply_text(
        "📌 Comandos disponibles:\n\n"
        "/start - Mensaje de bienvenida\n"
        "/ping - Verificar que el bot está vivo\n"
        "/help - Mostrar esta ayuda\n\n"
        "🤖 Bot creado con Pyrogram"
    )

# ============================================
# MANEJADOR DE ERRORES
# ============================================
@app.on_message()
async def echo(client: Client, message: Message):
    """Responde a cualquier mensaje no reconocido"""
    await message.reply_text(
        "❌ Comando no reconocido.\n"
        "Usa /help para ver los comandos disponibles."
    )

# ============================================
# INICIO
# ============================================
if __name__ == "__main__":
    print("🤖 Bot iniciado...")
    print(f"📌 Conectado con token: {BOT_TOKEN[:10]}...")
    app.run()