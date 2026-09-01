import os
import json
import time
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================
# CONFIGURACIÓN
# ============================================
TOKEN = os.environ.get('BOT_TOKEN')
DURATION = int(os.environ.get('BOT_DURATION', 0))  # 0 = infinito

if not TOKEN:
    print("❌ Error: BOT_TOKEN no configurado")
    exit(1)

# URL de la API para registrar usuarios
API_URL = os.environ.get('API_URL', 'http://localhost:5000')

# ============================================
# COMANDOS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Registrar usuario en la web
    try:
        response = requests.post(
            f'{API_URL}/api/receive_user',
            json={
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'command': '/start'
            },
            timeout=5
        )
    except:
        pass
    
    # Calcular tiempo restante si hay duración
    time_msg = ""
    if DURATION > 0:
        remaining = DURATION - (time.time() - start_time)
        if remaining > 0:
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            time_msg = f"\n⏱️ Tiempo restante: {hours}h {minutes}m"
        else:
            time_msg = "\n⚠️ El bot está por expirar"
    
    await update.message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        f"✅ Bot funcionando correctamente.\n"
        f"🆔 Tu ID: `{user.id}`\n"
        f"💬 Chat ID: `{chat.id}`\n"
        f"{time_msg}\n\n"
        f"📌 *Comandos:*\n"
        f"/start - Este mensaje\n"
        f"/me - Tu información\n"
        f"/id - Tu ID\n\n"
        f"📝 Gestiona el bot desde la web.",
        parse_mode='Markdown'
    )

async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /me"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Registrar usuario
    try:
        requests.post(
            f'{API_URL}/api/receive_user',
            json={
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'command': '/me'
            },
            timeout=5
        )
    except:
        pass
    
    await update.message.reply_text(
        f"👤 *Tu información:*\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"👤 Nombre: {user.first_name}\n"
        f"👥 Apellido: {user.last_name or 'N/A'}\n"
        f"📛 Username: @{user.username or 'N/A'}\n"
        f"💬 Chat ID: `{chat.id}`\n"
        f"🤖 Bot: {'Sí' if user.is_bot else 'No'}",
        parse_mode='Markdown'
    )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /id"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Registrar usuario
    try:
        requests.post(
            f'{API_URL}/api/receive_user',
            json={
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'command': '/id'
            },
            timeout=5
        )
    except:
        pass
    
    await update.message.reply_text(
        f"🆔 *Tu ID:* `{user.id}`\n"
        f"💬 *Chat ID:* `{chat.id}`\n\n"
        f"📌 Usa estos IDs para configurar el bot.",
        parse_mode='Markdown'
    )

# ============================================
# MAIN
# ============================================
start_time = time.time()

def main():
    print("🤖 Iniciando bot de Telegram...")
    
    if DURATION > 0:
        print(f"⏱️ Duración: {DURATION//3600}h")
    else:
        print("♾️  Duración: Infinita")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("id", id_command))
    
    print("✅ Bot iniciado correctamente!")
    print("📱 Busca tu bot en Telegram y envía /start")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
