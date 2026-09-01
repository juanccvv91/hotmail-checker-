
# app.py - CHECKER DASHBOARD UNIFICADO
import os
import sys
import asyncio
import threading
import time
import json
import re
import random
import base64
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_file
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# IMPORTAR CHECKERS
# ============================================
from checkers import CrunchyrollChecker, ParamountChecker, HotmailChecker

# ============================================
# CONFIGURACIÓN FLASK
# ============================================
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['SECRET_KEY'] = 'checker-dashboard-secret-key'

# ============================================
# DIRECTORIOS
# ============================================
BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
HITS_DIR = RESULTS_DIR / "hits"
LOGS_DIR = RESULTS_DIR / "logs"
UPLOADS_DIR = BASE_DIR / "uploads"

for d in [RESULTS_DIR, HITS_DIR, LOGS_DIR, UPLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================
# ESTADO GLOBAL
# ============================================
checker_status = {
    'running': False,
    'checker': None,
    'total': 0,
    'processed': 0,
    'hits': 0,
    'errors': 0,
    'invalid': 0,
    'logs': [],
    'results': [],
    'start_time': None,
    'elapsed': 0
}

checker_thread = None
stop_event = threading.Event()
current_hits = []

# ============================================
# UTILS
# ============================================
def load_accounts_from_text(content):
    """Carga cuentas desde texto"""
    accounts = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Probar diferentes separadores
        for sep in [':', '|', ';', ',', '\t']:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2 and '@' in parts[0]:
                    email = parts[0].strip()
                    password = parts[1].strip()
                    if email and password:
                        accounts.append((email, password))
                        break
    return accounts

def load_proxies_from_text(content):
    """Carga proxies desde texto"""
    proxies = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            proxies.append(line)
    return proxies

def format_proxy(proxy):
    """Formatea proxy para requests"""
    if not proxy:
        return None
    proxy = proxy.strip()
    if proxy.startswith('http://') or proxy.startswith('https://'):
        return proxy
    if '@' in proxy:
        return f"http://{proxy}"
    parts = proxy.split(':')
    if len(parts) == 4:
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    elif len(parts) == 2:
        return f"http://{proxy}"
    return None

# ============================================
# FUNCIONES DE CHECKER
# ============================================
def run_crunchyroll_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Crunchyroll"""
    global checker_status, current_hits
    
    total = len(accounts)
    checker_status['total'] = total
    checker_status['processed'] = 0
    checker_status['hits'] = 0
    checker_status['errors'] = 0
    checker_status['invalid'] = 0
    checker_status['logs'] = []
    checker_status['results'] = []
    current_hits = []
    checker_status['start_time'] = time.time()
    
    # Ejecutar en asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def process_accounts():
        sem = asyncio.Semaphore(50)  # Concurrency
        tasks = []
        
        for i, (email, password) in enumerate(accounts):
            if stop_event.is_set():
                break
            
            proxy = None
            if proxies:
                proxy = random.choice(proxies)
            
            tasks.append(process_single_crunchyroll(email, password, proxy, sem, i, total))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def process_single_crunchyroll(email, password, proxy, sem, index, total):
        global checker_status, current_hits
        
        async with sem:
            if stop_event.is_set():
                return
            
            try:
                result = await CrunchyrollChecker.check(email, password, proxy)
                
                checker_status['processed'] += 1
                
                if result.get('status') == 'HIT':
                    checker_status['hits'] += 1
                    current_hits.append(result)
                    checker_status['results'].append(result)
                    log_msg = f"[HIT] {email} | {result.get('plan', 'Unknown')} | {result.get('country', 'Unknown')}"
                    checker_status['logs'].append(log_msg)
                    
                    # Guardar hit en archivo
                    hit_file = HITS_DIR / f"crunchyroll_hits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    with open(hit_file, 'a', encoding='utf-8') as f:
                        f.write(f"{email}:{password} | {result.get('plan', 'Unknown')} | {result.get('country', 'Unknown')}\n")
                
                elif result.get('status') == 'FREE':
                    log_msg = f"[FREE] {email}"
                    checker_status['logs'].append(log_msg)
                
                elif result.get('status') == 'CUSTOM':
                    log_msg = f"[CUSTOM] {email} | {result.get('plan', 'Unknown')}"
                    checker_status['logs'].append(log_msg)
                
                elif result.get('status') == 'INVALID':
                    checker_status['invalid'] += 1
                    log_msg = f"[INVALID] {email}"
                    checker_status['logs'].append(log_msg)
                
                else:
                    checker_status['errors'] += 1
                    log_msg = f"[ERROR] {email} | {result.get('error', 'Unknown error')}"
                    checker_status['logs'].append(log_msg)
                
                # Mantener solo últimos 100 logs
                if len(checker_status['logs']) > 100:
                    checker_status['logs'] = checker_status['logs'][-100:]
                
                checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
                
            except Exception as e:
                checker_status['errors'] += 1
                checker_status['logs'].append(f"[ERROR] {email} | {str(e)}")
    
    try:
        loop.run_until_complete(process_accounts())
    except Exception as e:
        checker_status['logs'].append(f"[FATAL] {str(e)}")
    finally:
        loop.close()
        checker_status['running'] = False
        checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
        checker_status['logs'].append("[INFO] Checker finalizado")

def run_paramount_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Paramount+"""
    global checker_status, current_hits
    
    total = len(accounts)
    checker_status['total'] = total
    checker_status['processed'] = 0
    checker_status['hits'] = 0
    checker_status['errors'] = 0
    checker_status['invalid'] = 0
    checker_status['logs'] = []
    checker_status['results'] = []
    current_hits = []
    checker_status['start_time'] = time.time()
    
    for i, (email, password) in enumerate(accounts):
        if stop_event.is_set():
            break
        
        proxy = None
        if proxies:
            proxy = random.choice(proxies)
        
        try:
            result = ParamountChecker.check(email, password, proxy)
            
            checker_status['processed'] += 1
            
            if result.get('status') == 'HIT':
                checker_status['hits'] += 1
                current_hits.append(result)
                checker_status['results'].append(result)
                log_msg = f"[HIT] {email} | {result.get('plan', 'Unknown')} | {result.get('country', 'Unknown')}"
                checker_status['logs'].append(log_msg)
                
                # Guardar hit en archivo
                hit_file = HITS_DIR / f"paramount_hits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(hit_file, 'a', encoding='utf-8') as f:
                    f.write(f"{email}:{password} | {result.get('plan', 'Unknown')} | {result.get('country', 'Unknown')}\n")
            
            elif result.get('status') == 'FREE':
                log_msg = f"[FREE] {email}"
                checker_status['logs'].append(log_msg)
            
            elif result.get('status') == 'INVALID':
                checker_status['invalid'] += 1
                log_msg = f"[INVALID] {email}"
                checker_status['logs'].append(log_msg)
            
            else:
                checker_status['errors'] += 1
                log_msg = f"[ERROR] {email} | {result.get('error', 'Unknown error')}"
                checker_status['logs'].append(log_msg)
            
            # Mantener solo últimos 100 logs
            if len(checker_status['logs']) > 100:
                checker_status['logs'] = checker_status['logs'][-100:]
            
            checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
            
        except Exception as e:
            checker_status['errors'] += 1
            checker_status['logs'].append(f"[ERROR] {email} | {str(e)}")
    
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

def run_hotmail_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Hotmail"""
    global checker_status, current_hits
    
    total = len(accounts)
    checker_status['total'] = total
    checker_status['processed'] = 0
    checker_status['hits'] = 0
    checker_status['errors'] = 0
    checker_status['invalid'] = 0
    checker_status['logs'] = []
    checker_status['results'] = []
    current_hits = []
    checker_status['start_time'] = time.time()
    
    for i, (email, password) in enumerate(accounts):
        if stop_event.is_set():
            break
        
        proxy = None
        if proxies:
            proxy = random.choice(proxies)
        
        try:
            result = HotmailChecker.check(email, password, proxy)
            
            checker_status['processed'] += 1
            
            if result.get('status') == 'HIT':
                checker_status['hits'] += 1
                current_hits.append(result)
                checker_status['results'].append(result)
                
                inbox_info = ""
                if result.get('inbox_count', 0) > 0:
                    inbox_info = f" | Inbox: {result.get('inbox_count')} emails"
                
                log_msg = f"[HIT] {email} | {result.get('country', 'Unknown')}{inbox_info}"
                checker_status['logs'].append(log_msg)
                
                # Guardar hit en archivo
                hit_file = HITS_DIR / f"hotmail_hits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(hit_file, 'a', encoding='utf-8') as f:
                    f.write(f"{email}:{password} | {result.get('country', 'Unknown')}{inbox_info}\n")
            
            elif result.get('status') == '2FA':
                log_msg = f"[2FA] {email}"
                checker_status['logs'].append(log_msg)
            
            elif result.get('status') == 'INVALID':
                checker_status['invalid'] += 1
                log_msg = f"[INVALID] {email}"
                checker_status['logs'].append(log_msg)
            
            else:
                checker_status['errors'] += 1
                log_msg = f"[ERROR] {email} | {result.get('error', 'Unknown error')}"
                checker_status['logs'].append(log_msg)
            
            # Mantener solo últimos 100 logs
            if len(checker_status['logs']) > 100:
                checker_status['logs'] = checker_status['logs'][-100:]
            
            checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
            
        except Exception as e:
            checker_status['errors'] += 1
            checker_status['logs'].append(f"[ERROR] {email} | {str(e)}")
    
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

# ============================================
# RUTAS FLASK
# ============================================

@app.route('/')
def index():
    """Página principal"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    """Health check para Render"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Sube archivo de cuentas o proxies"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        content = file.read().decode('utf-8', errors='ignore')
        
        file_type = request.form.get('type', 'accounts')
        
        if file_type == 'accounts':
            accounts = load_accounts_from_text(content)
            if not accounts:
                return jsonify({'error': 'No valid accounts found'}), 400
            return jsonify({
                'success': True,
                'count': len(accounts),
                'type': 'accounts',
                'preview': accounts[:5]
            })
        else:
            proxies = load_proxies_from_text(content)
            return jsonify({
                'success': True,
                'count': len(proxies),
                'type': 'proxies',
                'preview': proxies[:5]
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/start', methods=['POST'])
def start_checker():
    """Inicia el checker seleccionado"""
    global checker_status, checker_thread, stop_event, current_hits
    
    if checker_status['running']:
        return jsonify({'error': 'Checker ya está en ejecución'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    checker_type = data.get('checker')
    accounts = data.get('accounts', [])
    proxies = data.get('proxies', [])
    
    if not accounts:
        return jsonify({'error': 'No accounts provided'}), 400
    
    # Mapeo de checkers
    checker_map = {
        'crunchyroll': run_crunchyroll_checker,
        'paramount': run_paramount_checker,
        'hotmail': run_hotmail_checker
    }
    
    if checker_type not in checker_map:
        return jsonify({'error': f'Checker {checker_type} no válido'}), 400
    
    # Resetear estado
    stop_event.clear()
    current_hits = []
    checker_status['running'] = True
    checker_status['checker'] = checker_type
    checker_status['logs'] = []
    checker_status['results'] = []
    checker_status['total'] = len(accounts)
    checker_status['processed'] = 0
    checker_status['hits'] = 0
    checker_status['errors'] = 0
    checker_status['invalid'] = 0
    checker_status['start_time'] = time.time()
    checker_status['elapsed'] = 0
    
    # Iniciar thread
    checker_thread = threading.Thread(
        target=checker_map[checker_type],
        args=(accounts, proxies, stop_event),
        daemon=True
    )
    checker_thread.start()
    
    return jsonify({
        'success': True,
        'message': f'Checker {checker_type} iniciado',
        'total': len(accounts)
    })

@app.route('/api/stop', methods=['POST'])
def stop_checker():
    """Detiene el checker en ejecución"""
    global stop_event
    
    if not checker_status['running']:
        return jsonify({'error': 'No hay checker en ejecución'}), 400
    
    stop_event.set()
    checker_status['running'] = False
    checker_status['logs'].append("[INFO] Checker detenido por usuario")
    
    return jsonify({'success': True, 'message': 'Checker detenido'})

@app.route('/api/status')
def get_status():
    """Obtiene el estado actual del checker"""
    return jsonify({
        'running': checker_status['running'],
        'checker': checker_status['checker'],
        'total': checker_status['total'],
        'processed': checker_status['processed'],
        'hits': checker_status['hits'],
        'errors': checker_status['errors'],
        'invalid': checker_status['invalid'],
        'logs': checker_status['logs'][-50:],
        'results': checker_status['results'][-20:],
        'elapsed': checker_status['elapsed'],
        'start_time': checker_status['start_time']
    })

@app.route('/api/export')
def export_hits():
    """Exporta los hits como archivo de texto"""
    global current_hits
    
    if not current_hits:
        return jsonify({'error': 'No hay hits para exportar'}), 400
    
    # Crear archivo de exportación
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"hits_export_{timestamp}.txt"
    filepath = EXPORTS_DIR / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("HITS EXPORT\n")
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total: {len(current_hits)}\n")
        f.write("=" * 60 + "\n\n")
        
        for hit in current_hits:
            email = hit.get('email', 'Unknown')
            password = hit.get('password', 'Unknown')
            country = hit.get('country', 'Unknown')
            plan = hit.get('plan', 'Unknown')
            
            f.write(f"Email: {email}\n")
            f.write(f"Password: {password}\n")
            f.write(f"País: {country}\n")
            f.write(f"Plan: {plan}\n")
            f.write("-" * 40 + "\n\n")
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/clear_logs', methods=['POST'])
def clear_logs():
    """Limpia los logs"""
    checker_status['logs'] = []
    return jsonify({'success': True})

# ============================================
# HTML TEMPLATE (EMBEBIDO)
# ============================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Checker Dashboard</title>
    <style>
        /* ===== RESET ===== */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a0f;
            color: #ffffff;
            min-height: 100vh;
        }
        
        /* ===== SCROLLBAR ===== */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #15161a; }
        ::-webkit-scrollbar-thumb { background: #E4751E; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #c9651a; }
        
        /* ===== HEADER ===== */
        .header {
            background: #15161a;
            border-bottom: 2px solid #E4751E;
            padding: 15px 30px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .header-logo {
            font-size: 32px;
        }
        .header-title {
            font-size: 20px;
            font-weight: bold;
            color: #E4751E;
        }
        .header-subtitle {
            color: #8a8c9e;
            font-size: 14px;
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .header-badge {
            background: #E4751E;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            color: #fff;
        }
        
        /* ===== MAIN LAYOUT ===== */
        .main {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 900px) {
            .main { grid-template-columns: 1fr; }
        }
        
        /* ===== CARDS ===== */
        .card {
            background: #15161a;
            border: 1px solid #2a2b35;
            border-radius: 12px;
            padding: 20px;
        }
        .card-title {
            font-size: 14px;
            font-weight: bold;
            color: #E4751E;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card-title span { color: #8a8c9e; font-weight: normal; font-size: 12px; }
        
        /* ===== FORMS ===== */
        .form-group {
            margin-bottom: 12px;
        }
        .form-group label {
            display: block;
            font-size: 12px;
            color: #8a8c9e;
            margin-bottom: 4px;
        }
        .form-group input, .form-group select {
            width: 100%;
            padding: 10px 12px;
            background: #0a0a0f;
            border: 1px solid #2a2b35;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            transition: border 0.3s;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #E4751E;
        }
        .form-group input[type="file"] {
            padding: 8px;
            cursor: pointer;
        }
        .form-group input[type="file"]::file-selector-button {
            background: #E4751E;
            border: none;
            color: #fff;
            padding: 6px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
        }
        .form-group input[type="file"]::file-selector-button:hover {
            background: #c9651a;
        }
        
        /* ===== BUTTONS ===== */
        .btn {
            padding: 10px 24px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-primary { background: #E4751E; color: #fff; }
        .btn-primary:hover { background: #c9651a; transform: translateY(-1px); }
        .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        
        .btn-danger { background: #ff4444; color: #fff; }
        .btn-danger:hover { background: #cc0000; }
        .btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .btn-success { background: #00cc88; color: #fff; }
        .btn-success:hover { background: #00aa77; }
        .btn-success:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .btn-secondary { background: #2a2b35; color: #fff; }
        .btn-secondary:hover { background: #3a3b45; }
        
        .btn-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 10px;
        }
        
        /* ===== STATS ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            margin-bottom: 15px;
        }
        .stat-item {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #E4751E;
        }
        .stat-label {
            font-size: 11px;
            color: #8a8c9e;
            margin-top: 2px;
        }
        .stat-hit { color: #00ff88; }
        .stat-error { color: #ff4444; }
        .stat-invalid { color: #ffaa44; }
        
        /* ===== PROGRESS BAR ===== */
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #2a2b35;
            border-radius: 4px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #E4751E, #ff9a44);
            border-radius: 4px;
            transition: width 0.5s;
            width: 0%;
        }
        
        /* ===== LOGS ===== */
        .log-container {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 10px;
            max-height: 300px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            line-height: 1.6;
        }
        .log-line { padding: 2px 0; border-bottom: 1px solid #0f0f14; }
        .log-hit { color: #00ff88; }
        .log-free { color: #8a8c9e; }
        .log-invalid { color: #ffaa44; }
        .log-error { color: #ff4444; }
        .log-info { color: #E4751E; }
        .log-2fa { color: #ff8800; }
        
        /* ===== HITS LIST ===== */
        .hits-container {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 10px;
            max-height: 300px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 12px;
        }
        .hit-item {
            padding: 4px 8px;
            border-bottom: 1px solid #0f0f14;
            color: #00ff88;
        }
        
        /* ===== UPLOAD STATUS ===== */
        .upload-status {
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            margin-top: 5px;
        }
        .upload-success { background: #00cc8822; color: #00cc88; border: 1px solid #00cc8844; }
        .upload-error { background: #ff444422; color: #ff4444; border: 1px solid #ff444444; }
        
        /* ===== RESPONSIVE ===== */
        @media (max-width: 600px) {
            .header-title { font-size: 16px; }
            .stats-grid { grid-template-columns: repeat(3, 1fr); }
            .btn { padding: 8px 16px; font-size: 12px; }
        }
        
        /* ===== CHECKER SELECTOR ===== */
        .checker-selector {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-bottom: 15px;
        }
        .checker-option {
            padding: 12px;
            background: #0a0a0f;
            border: 2px solid #2a2b35;
            border-radius: 8px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        .checker-option:hover { border-color: #E4751E44; }
        .checker-option.active {
            border-color: #E4751E;
            background: #E4751E11;
        }
        .checker-option .icon { font-size: 24px; }
        .checker-option .name { font-size: 12px; font-weight: bold; margin-top: 4px; }
        .checker-option .desc { font-size: 10px; color: #8a8c9e; }
    </style>
</head>
<body>
    <!-- ===== HEADER ===== -->
    <header class="header">
        <div class="header-left">
            <span class="header-logo">🚀</span>
            <div>
                <div class="header-title">Checker Dashboard</div>
                <div class="header-subtitle">Multi-Checker Unificado</div>
            </div>
        </div>
        <div class="header-right">
            <span class="header-badge" id="statusBadge">⏹ Detenido</span>
            <span style="color:#8a8c9e;font-size:12px;" id="timerDisplay">00:00:00</span>
        </div>
    </header>

    <!-- ===== MAIN ===== -->
    <div class="main">
        <!-- ===== COLUMNA IZQUIERDA ===== -->
        <div>
            <!-- Configuración -->
            <div class="card">
                <div class="card-title">⚙️ Configuración</div>
                
                <div class="form-group">
                    <label>📌 Seleccionar Checker</label>
                    <div class="checker-selector">
                        <div class="checker-option active" data-checker="crunchyroll" onclick="selectChecker(this)">
                            <div class="icon">🍥</div>
                            <div class="name">Crunchyroll</div>
                            <div class="desc">Premium Accounts</div>
                        </div>
                        <div class="checker-option" data-checker="paramount" onclick="selectChecker(this)">
                            <div class="icon">🎬</div>
                            <div class="name">Paramount+</div>
                            <div class="desc">Streaming Accounts</div>
                        </div>
                        <div class="checker-option" data-checker="hotmail" onclick="selectChecker(this)">
                            <div class="icon">📧</div>
                            <div class="name">Hotmail</div>
                            <div class="desc">Inbox Checker</div>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>📄 Cuentas (email:password)</label>
                    <input type="file" id="accountsFile" accept=".txt" onchange="uploadFile('accounts')">
                    <div id="accountsStatus" class="upload-status" style="display:none;"></div>
                </div>
                
                <div class="form-group">
                    <label>🌐 Proxies (opcional)</label>
                    <input type="file" id="proxiesFile" accept=".txt" onchange="uploadFile('proxies')">
                    <div id="proxiesStatus" class="upload-status" style="display:none;"></div>
                </div>
                
                <div class="btn-group">
                    <button class="btn btn-primary" id="btnStart" onclick="startChecker()">▶ Iniciar</button>
                    <button class="btn btn-danger" id="btnStop" onclick="stopChecker()" disabled>⏹ Detener</button>
                    <button class="btn btn-success" id="btnExport" onclick="exportHits()">💾 Exportar Hits</button>
                    <button class="btn btn-secondary" onclick="clearLogs()">🗑 Limpiar Logs</button>
                </div>
            </div>
            
            <!-- Estadísticas -->
            <div class="card" style="margin-top:20px;">
                <div class="card-title">📊 Estadísticas</div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="statTotal">0</div>
                        <div class="stat-label">Total</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="statProcessed">0</div>
                        <div class="stat-label">Procesadas</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value stat-hit" id="statHits">0</div>
                        <div class="stat-label">✅ Hits</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value stat-invalid" id="statInvalid">0</div>
                        <div class="stat-label">❌ Invalid</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value stat-error" id="statErrors">0</div>
                        <div class="stat-label">⚠️ Errors</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="statProgress">0%</div>
                        <div class="stat-label">Progreso</div>
                    </div>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
            </div>
        </div>
        
        <!-- ===== COLUMNA DERECHA ===== -->
        <div>
            <!-- Logs -->
            <div class="card">
                <div class="card-title">📜 Logs <span id="logCount">(0)</span></div>
                <div class="log-container" id="logContainer">
                    <div class="log-line log-info">[INFO] Esperando inicio...</div>
                </div>
            </div>
            
            <!-- Hits -->
            <div class="card" style="margin-top:20px;">
                <div class="card-title">🏆 Hits <span id="hitCount">(0)</span></div>
                <div class="hits-container" id="hitsContainer">
                    <div style="color:#8a8c9e;text-align:center;padding:20px;">Esperando hits...</div>
                </div>
            </div>
        </div>
    </div>

    <!-- ===== SCRIPTS ===== -->
    <script>
        // ===== VARIABLES =====
        let currentChecker = 'crunchyroll';
        let accountsData = [];
        let proxiesData = [];
        let isRunning = false;
        let statusInterval = null;
        let timerInterval = null;
        let startTime = null;
        let elapsedSeconds = 0;
        
        // ===== SELECTOR DE CHECKER =====
        function selectChecker(el) {
            document.querySelectorAll('.checker-option').forEach(c => c.classList.remove('active'));
            el.classList.add('active');
            currentChecker = el.dataset.checker;
        }
        
        // ===== SUBIDA DE ARCHIVOS =====
        async function uploadFile(type) {
            const input = document.getElementById(type === 'accounts' ? 'accountsFile' : 'proxiesFile');
            const status = document.getElementById(type === 'accounts' ? 'accountsStatus' : 'proxiesStatus');
            
            if (!input.files || !input.files[0]) return;
            
            const file = input.files[0];
            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', type);
            
            status.style.display = 'block';
            status.className = 'upload-status';
            status.textContent = '⏳ Subiendo...';
            
            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();
                
                if (data.success) {
                    status.className = 'upload-status upload-success';
                    status.textContent = `✅ ${data.count} ${type === 'accounts' ? 'cuentas' : 'proxies'} cargados`;
                    
                    if (type === 'accounts') {
                        accountsData = data.preview || [];
                    } else {
                        proxiesData = data.preview || [];
                    }
                } else {
                    status.className = 'upload-status upload-error';
                    status.textContent = `❌ ${data.error || 'Error al subir'}`;
                }
            } catch (e) {
                status.className = 'upload-status upload-error';
                status.textContent = `❌ Error: ${e.message}`;
            }
        }
        
        // ===== INICIAR CHECKER =====
        async function startChecker() {
            if (isRunning) return;
            
            if (!accountsData.length) {
                alert('⚠️ Carga un archivo de cuentas primero.');
                return;
            }
            
            const btn = document.getElementById('btnStart');
            btn.disabled = true;
            btn.textContent = '⏳ Iniciando...';
            
            try {
                const response = await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        checker: currentChecker,
                        accounts: accountsData,
                        proxies: proxiesData
                    })
                });
                const data = await response.json();
                
                if (data.success) {
                    isRunning = true;
                    document.getElementById('btnStart').disabled = true;
                    document.getElementById('btnStop').disabled = false;
                    document.getElementById('statusBadge').textContent = '▶ Ejecutando';
                    document.getElementById('statusBadge').style.color = '#00ff88';
                    
                    startTime = Date.now();
                    elapsedSeconds = 0;
                    
                    if (statusInterval) clearInterval(statusInterval);
                    if (timerInterval) clearInterval(timerInterval);
                    
                    statusInterval = setInterval(fetchStatus, 1000);
                    timerInterval = setInterval(updateTimer, 1000);
                    
                    // Limpiar logs y hits
                    document.getElementById('logContainer').innerHTML = '';
                    document.getElementById('hitsContainer').innerHTML = '';
                    document.getElementById('statTotal').textContent = data.total || 0;
                } else {
                    alert('❌ ' + (data.error || 'Error al iniciar'));
                }
            } catch (e) {
                alert('❌ Error: ' + e.message);
            }
            
            btn.disabled = false;
            btn.textContent = '▶ Iniciar';
        }
        
        // ===== DETENER CHECKER =====
        async function stopChecker() {
            if (!isRunning) return;
            
            try {
                const response = await fetch('/api/stop', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    isRunning = false;
                    document.getElementById('btnStart').disabled = false;
                    document.getElementById('btnStop').disabled = true;
                    document.getElementById('statusBadge').textContent = '⏹ Detenido';
                    document.getElementById('statusBadge').style.color = '#ff4444';
                    
                    if (statusInterval) clearInterval(statusInterval);
                    if (timerInterval) clearInterval(timerInterval);
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        // ===== EXPORTAR HITS =====
        async function exportHits() {
            try {
                const response = await fetch('/api/export');
                if (response.ok) {
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = response.headers.get('Content-Disposition')?.split('filename=')[1] || 'hits_export.txt';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                } else {
                    const data = await response.json();
                    alert('❌ ' + (data.error || 'Error al exportar'));
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        // ===== LIMPIAR LOGS =====
        async function clearLogs() {
            try {
                await fetch('/api/clear_logs', { method: 'POST' });
                document.getElementById('logContainer').innerHTML = '';
                document.getElementById('logCount').textContent = '(0)';
            } catch (e) {
                console.error(e);
            }
        }
        
        // ===== ACTUALIZAR ESTADO =====
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                document.getElementById('statProcessed').textContent = data.processed || 0;
                document.getElementById('statHits').textContent = data.hits || 0;
                document.getElementById('statInvalid').textContent = data.invalid || 0;
                document.getElementById('statErrors').textContent = data.errors || 0;
                
                const progress = data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0;
                document.getElementById('statProgress').textContent = progress + '%';
                document.getElementById('progressFill').style.width = progress + '%';
                
                // Logs
                if (data.logs && data.logs.length) {
                    const container = document.getElementById('logContainer');
                    const lastLogs = data.logs.slice(-20);
                    container.innerHTML = lastLogs.map(log => {
                        let className = 'log-info';
                        if (log.includes('[HIT]')) className = 'log-hit';
                        else if (log.includes('[FREE]')) className = 'log-free';
                        else if (log.includes('[INVALID]')) className = 'log-invalid';
                        else if (log.includes('[ERROR]')) className = 'log-error';
                        else if (log.includes('[2FA]')) className = 'log-2fa';
                        return `<div class="log-line ${className}">${escapeHtml(log)}</div>`;
                    }).join('');
                    container.scrollTop = container.scrollHeight;
                    document.getElementById('logCount').textContent = `(${data.logs.length})`;
                }
                
                // Hits
                if (data.results && data.results.length) {
                    const container = document.getElementById('hitsContainer');
                    const hits = data.results.slice(-10);
                    container.innerHTML = hits.map(hit => {
                        const email = hit.email || 'Unknown';
                        const plan = hit.plan || hit.tipo || 'Unknown';
                        const country = hit.country || 'Unknown';
                        return `<div class="hit-item">✅ ${email} | ${plan} | ${country}</div>`;
                    }).join('');
                    document.getElementById('hitCount').textContent = `(${data.hits || 0})`;
                }
                
                // Actualizar running state
                if (!data.running && isRunning) {
                    isRunning = false;
                    document.getElementById('btnStart').disabled = false;
                    document.getElementById('btnStop').disabled = true;
                    document.getElementById('statusBadge').textContent = '⏹ Finalizado';
                    document.getElementById('statusBadge').style.color = '#ffaa44';
                    if (statusInterval) clearInterval(statusInterval);
                    if (timerInterval) clearInterval(timerInterval);
                }
                
                elapsedSeconds = data.elapsed || 0;
                
            } catch (e) {
                console.error('Error fetching status:', e);
            }
        }
        
        // ===== TIMER =====
        function updateTimer() {
            elapsedSeconds++;
            const hours = String(Math.floor(elapsedSeconds / 3600)).padStart(2, '0');
            const minutes = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, '0');
            const seconds = String(elapsedSeconds % 60).padStart(2, '0');
            document.getElementById('timerDisplay').textContent = `${hours}:${minutes}:${seconds}`;
        }
        
        // ===== UTILS =====
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // ===== POLLING INICIAL =====
        setTimeout(() => {
            fetchStatus();
        }, 1000);
    </script>
</body>
</html>
'''

# ============================================
# PUNTO DE ENTRADA
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)