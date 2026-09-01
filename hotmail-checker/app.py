import os
import json
import time
import threading
import subprocess
import signal
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PORT = int(os.environ.get('PORT', 5000))

# ============================================
# DATOS PERSISTENTES
# ============================================
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

def load_config():
    """Carga la configuración"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'token': '',
        'status': 'stopped',  # stopped, running, error
        'duration': 'infinito',  # 1h, 6h, 12h, 24h, infinito
        'started_at': None,
        'expires_at': None,
        'bot_pid': None
    }

def save_config(config):
    """Guarda la configuración"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_users():
    """Carga los usuarios que han usado el bot"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {'users': [], 'total_commands': 0}

def save_users(users):
    """Guarda los usuarios"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

# ============================================
# ESTADO GLOBAL
# ============================================
config = load_config()
users_data = load_users()
bot_process = None
bot_thread = None

# ============================================
# FUNCIONES DEL BOT
# ============================================
def get_duration_seconds(duration):
    """Convierte duración a segundos"""
    durations = {
        '1h': 3600,
        '6h': 21600,
        '12h': 43200,
        '24h': 86400,
        'infinito': None
    }
    return durations.get(duration, None)

def run_bot():
    """Ejecuta el bot en un proceso separado"""
    global bot_process, config
    
    token = config.get('token', '')
    if not token:
        return
    
    # Detener bot anterior si existe
    stop_bot()
    
    # Calcular expiración
    duration = config.get('duration', 'infinito')
    seconds = get_duration_seconds(duration)
    
    config['status'] = 'running'
    config['started_at'] = datetime.now().isoformat()
    if seconds:
        config['expires_at'] = (datetime.now() + timedelta(seconds=seconds)).isoformat()
    else:
        config['expires_at'] = None
    save_config(config)
    
    # Iniciar bot en proceso separado
    try:
        # Guardar token en variable de entorno para el subproceso
        env = os.environ.copy()
        env['BOT_TOKEN'] = token
        env['BOT_DURATION'] = str(seconds) if seconds else '0'
        
        bot_process = subprocess.Popen(
            [sys.executable, 'bot.py'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Guardar PID
        config['bot_pid'] = bot_process.pid
        save_config(config)
        
        # Iniciar hilo para monitorear
        monitor_thread = threading.Thread(target=monitor_bot)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return True
    except Exception as e:
        config['status'] = 'error'
        save_config(config)
        return False

def stop_bot():
    """Detiene el bot"""
    global bot_process, config
    
    if bot_process:
        try:
            bot_process.terminate()
            bot_process.wait(timeout=5)
        except:
            try:
                bot_process.kill()
            except:
                pass
        bot_process = None
    
    config['status'] = 'stopped'
    config['bot_pid'] = None
    save_config(config)
    return True

def monitor_bot():
    """Monitorea el bot y verifica expiración"""
    global config, bot_process
    
    while True:
        time.sleep(5)
        
        # Verificar si el proceso sigue vivo
        if bot_process and bot_process.poll() is not None:
            # El proceso terminó
            config['status'] = 'stopped'
            config['bot_pid'] = None
            save_config(config)
            bot_process = None
            break
        
        # Verificar expiración
        if config.get('expires_at'):
            expires = datetime.fromisoformat(config['expires_at'])
            if datetime.now() >= expires:
                stop_bot()
                break

# ============================================
# RUTAS DE LA API
# ============================================

@app.route('/')
def index():
    """Panel de control"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Obtiene configuración"""
    return jsonify({
        'token': config.get('token', ''),
        'status': config.get('status', 'stopped'),
        'duration': config.get('duration', 'infinito'),
        'started_at': config.get('started_at'),
        'expires_at': config.get('expires_at'),
        'bot_pid': config.get('bot_pid')
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """Actualiza configuración"""
    global config
    
    data = request.json
    token = data.get('token', '').strip()
    duration = data.get('duration', 'infinito')
    
    if not token:
        return jsonify({'error': 'Token requerido'}), 400
    
    # Actualizar configuración
    config['token'] = token
    config['duration'] = duration
    save_config(config)
    
    return jsonify({'success': True})

@app.route('/api/start', methods=['POST'])
def start_bot():
    """Inicia el bot"""
    if not config.get('token'):
        return jsonify({'error': 'Token no configurado'}), 400
    
    if run_bot():
        return jsonify({'success': True, 'status': 'running'})
    return jsonify({'error': 'Error al iniciar el bot'}), 500

@app.route('/api/stop', methods=['POST'])
def stop_bot_route():
    """Detiene el bot"""
    stop_bot()
    return jsonify({'success': True})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Obtiene estado detallado"""
    return jsonify({
        'status': config.get('status', 'stopped'),
        'started_at': config.get('started_at'),
        'expires_at': config.get('expires_at'),
        'duration': config.get('duration', 'infinito'),
        'users': users_data.get('users', []),
        'total_commands': users_data.get('total_commands', 0)
    })

@app.route('/api/users', methods=['GET'])
def get_users():
    """Obtiene lista de usuarios"""
    return jsonify({
        'users': users_data.get('users', []),
        'total': len(users_data.get('users', [])),
        'total_commands': users_data.get('total_commands', 0)
    })

@app.route('/api/clear_users', methods=['POST'])
def clear_users():
    """Limpia historial de usuarios"""
    users_data['users'] = []
    users_data['total_commands'] = 0
    save_users(users_data)
    return jsonify({'success': True})

@app.route('/api/receive_user', methods=['POST'])
def receive_user():
    """Recibe datos de usuario desde el bot"""
    data = request.json
    user_id = data.get('user_id')
    username = data.get('username')
    first_name = data.get('first_name')
    command = data.get('command', '/start')
    
    # Verificar si el usuario ya existe
    existing = next((u for u in users_data['users'] if u['id'] == user_id), None)
    
    if existing:
        existing['last_seen'] = datetime.now().isoformat()
        existing['commands_count'] = existing.get('commands_count', 0) + 1
    else:
        users_data['users'].append({
            'id': user_id,
            'username': username,
            'first_name': first_name,
            'first_seen': datetime.now().isoformat(),
            'last_seen': datetime.now().isoformat(),
            'commands_count': 1
        })
    
    users_data['total_commands'] += 1
    save_users(users_data)
    
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
