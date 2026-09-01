import os
import json
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

app = Flask(__name__)
CORS(app)

PORT = int(os.environ.get('PORT', 5000))

# ============================================
# TU TOKEN - PUESTO DIRECTAMENTE
# ============================================
TOKEN = "8780478988:AAEgEU2q5kLo1vZ5deOkn_U3quhPQVx8dno"

# ============================================
# DATOS PERSISTENTES
# ============================================
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'token': TOKEN,
        'status': 'stopped',
        'duration': 'infinito',
        'started_at': None,
        'expires_at': None
    }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {'users': [], 'total_commands': 0}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

config = load_config()
users_data = load_users()

# ============================================
# VARIABLES DEL BOT
# ============================================
bot_application = None
bot_thread = None
bot_running = False
bot_start_time = None

# ============================================
# FUNCIONES DEL BOT
# ============================================

def get_duration_seconds(duration):
    durations = {
        '1h': 3600,
        '6h': 21600,
        '12h': 43200,
        '24h': 86400,
        'infinito': None
    }
    return durations.get(duration, None)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    print(f"📨 /start recibido de {user.first_name} (ID: {user.id})")
    
    # Registrar usuario
    try:
        users = load_users()
        existing = next((u for u in users['users'] if u['id'] == user.id), None)
        if existing:
            existing['last_seen'] = datetime.now().isoformat()
            existing['commands_count'] = existing.get('commands_count', 0) + 1
        else:
            users['users'].append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'first_seen': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat(),
                'commands_count': 1
            })
        users['total_commands'] += 1
        save_users(users)
    except Exception as e:
        print(f"⚠️ Error guardando usuario: {e}")
    
    # Calcular tiempo restante
    time_msg = ""
    if config.get('expires_at'):
        try:
            expires = datetime.fromisoformat(config['expires_at'])
            remaining = (expires - datetime.now()).total_seconds()
            if remaining > 0:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                time_msg = f"\n⏱️ Tiempo restante: {hours}h {minutes}m"
            else:
                time_msg = "\n⚠️ El bot está por expirar"
        except:
            pass
    
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

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    await update.message.reply_text(
        f"👤 *Tu información:*\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"👤 Nombre: {user.first_name}\n"
        f"👥 Apellido: {user.last_name or 'N/A'}\n"
        f"📛 Username: @{user.username or 'N/A'}\n"
        f"💬 Chat ID: `{chat.id}`",
        parse_mode='Markdown'
    )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    await update.message.reply_text(
        f"🆔 *Tu ID:* `{user.id}`\n"
        f"💬 *Chat ID:* `{chat.id}`",
        parse_mode='Markdown'
    )

def run_bot():
    global bot_application, bot_running, bot_start_time
    
    token = TOKEN
    if not token:
        print("❌ No hay token configurado")
        return
    
    print("🤖 Iniciando bot de Telegram...")
    print(f"🔑 Token: {token[:10]}...")
    
    try:
        bot_application = Application.builder().token(token).build()
        
        bot_application.add_handler(CommandHandler("start", start_command))
        bot_application.add_handler(CommandHandler("me", me_command))
        bot_application.add_handler(CommandHandler("id", id_command))
        
        print("✅ Comandos registrados: /start, /me, /id")
        
        bot_running = True
        bot_start_time = datetime.now()
        config['status'] = 'running'
        config['started_at'] = datetime.now().isoformat()
        
        duration = config.get('duration', 'infinito')
        seconds = get_duration_seconds(duration)
        if seconds:
            config['expires_at'] = (datetime.now() + timedelta(seconds=seconds)).isoformat()
        else:
            config['expires_at'] = None
        save_config(config)
        
        print("📱 Bot iniciado, esperando mensajes...")
        
        bot_application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ Error en el bot: {e}")
        config['status'] = 'error'
        save_config(config)
        bot_running = False
    
    bot_running = False

def stop_bot():
    global bot_application, bot_running
    
    if bot_application:
        try:
            bot_application.stop()
            bot_application.shutdown()
        except:
            pass
    
    bot_running = False
    config['status'] = 'stopped'
    save_config(config)
    print("⏹️ Bot detenido")

# ============================================
# RUTAS DE LA API
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'token': '••••••••••' if config.get('token') else '',
        'status': config.get('status', 'stopped'),
        'duration': config.get('duration', 'infinito'),
        'started_at': config.get('started_at'),
        'expires_at': config.get('expires_at')
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.json
    token = data.get('token', '').strip()
    duration = data.get('duration', 'infinito')
    
    if not token:
        return jsonify({'error': 'Token requerido'}), 400
    
    config['token'] = token
    config['duration'] = duration
    save_config(config)
    
    return jsonify({'success': True})

@app.route('/api/start', methods=['POST'])
def start_bot_route():
    global bot_thread
    
    if bot_running:
        return jsonify({'error': 'El bot ya está en ejecución'}), 400
    
    stop_bot()
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    time.sleep(2)
    
    if bot_running:
        return jsonify({'success': True, 'status': 'running'})
    else:
        status = config.get('status', 'error')
        return jsonify({'error': f'Error al iniciar el bot (estado: {status})'}), 500

@app.route('/api/stop', methods=['POST'])
def stop_bot_route():
    stop_bot()
    return jsonify({'success': True})

@app.route('/api/status', methods=['GET'])
def get_status():
    if bot_running and config.get('expires_at'):
        try:
            expires = datetime.fromisoformat(config['expires_at'])
            if datetime.now() >= expires:
                stop_bot()
        except:
            pass
    
    return jsonify({
        'status': config.get('status', 'stopped'),
        'started_at': config.get('started_at'),
        'expires_at': config.get('expires_at'),
        'duration': config.get('duration', 'infinito')
    })

@app.route('/api/users', methods=['GET'])
def get_users():
    users = load_users()
    return jsonify({
        'users': users.get('users', []),
        'total': len(users.get('users', [])),
        'total_commands': users.get('total_commands', 0)
    })

@app.route('/api/clear_users', methods=['POST'])
def clear_users():
    users = {'users': [], 'total_commands': 0}
    save_users(users)
    return jsonify({'success': True})

@app.route('/api/receive_user', methods=['POST'])
def receive_user():
    data = request.json
    user_id = data.get('user_id')
    username = data.get('username')
    first_name = data.get('first_name')
    
    users = load_users()
    existing = next((u for u in users['users'] if u['id'] == user_id), None)
    
    if existing:
        existing['last_seen'] = datetime.now().isoformat()
        existing['commands_count'] = existing.get('commands_count', 0) + 1
    else:
        users['users'].append({
            'id': user_id,
            'username': username,
            'first_name': first_name,
            'first_seen': datetime.now().isoformat(),
            'last_seen': datetime.now().isoformat(),
            'commands_count': 1
        })
    
    users['total_commands'] += 1
    save_users(users)
    
    return jsonify({'success': True})

if __name__ == '__main__':
    print(f"🌐 Servidor web iniciado en puerto {PORT}")
    print(f"🤖 Token configurado: {TOKEN[:10]}...")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
