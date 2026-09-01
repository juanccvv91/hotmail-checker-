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
# VARIABLES GLOBALES
# ============================================
uploaded_accounts = []
uploaded_proxies = []
current_checker_type = 'crunchyroll'

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
    checker_status['checker'] = 'crunchyroll'
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def process_accounts():
        sem = asyncio.Semaphore(50)
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
                    
                    hit_file = HITS_DIR / f"crunchyroll_hits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    with open(hit_file, 'a', encoding='utf-8') as f:
                        f.write(f"{email}:{password} | {result.get('plan', 'Unknown')} | {result.get('country', 'Unknown')}\n")
                
                elif result.get('status') == 'FREE':
                    log_msg = f"[FREE] {email}"
                    checker_status['logs'].append(log_msg)
                
                elif result.get('status') == 'CUSTOM':
                    checker_status['hits'] += 1
                    current_hits.append(result)
                    checker_status['results'].append(result)
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
                
                if len(checker_status['logs']) > 200:
                    checker_status['logs'] = checker_status['logs'][-200:]
                
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
    checker_status['checker'] = 'paramount'
    
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
            
            if len(checker_status['logs']) > 200:
                checker_status['logs'] = checker_status['logs'][-200:]
            
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
    checker_status['checker'] = 'hotmail'
    
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
            
            if len(checker_status['logs']) > 200:
                checker_status['logs'] = checker_status['logs'][-200:]
            
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
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Sube archivo de cuentas o proxies"""
    global uploaded_accounts, uploaded_proxies
    
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
            
            uploaded_accounts = accounts  # ✅ GUARDAR TODAS LAS CUENTAS
            
            return jsonify({
                'success': True,
                'count': len(accounts),
                'type': 'accounts',
                'preview': accounts[:5]
            })
        else:
            proxies = load_proxies_from_text(content)
            uploaded_proxies = proxies  # ✅ GUARDAR TODOS LOS PROXIES
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
    global checker_status, checker_thread, stop_event, current_hits, uploaded_accounts, uploaded_proxies, current_checker_type
    
    if checker_status['running']:
        return jsonify({'error': 'Checker ya está en ejecución'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    checker_type = data.get('checker')
    current_checker_type = checker_type
    
    # ✅ USAR LAS VARIABLES GLOBALES
    accounts = uploaded_accounts
    proxies = uploaded_proxies
    
    if not accounts:
        return jsonify({'error': 'No hay cuentas cargadas. Sube un archivo primero.'}), 400
    
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
    checker_status['logs'].append("[INFO] ⏹ Checker detenido por usuario")
    
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
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"hits_export_{timestamp}.txt"
    filepath = HITS_DIR / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("🏆 HITS EXPORT\n")
        f.write(f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"📊 Total: {len(current_hits)}\n")
        f.write("=" * 70 + "\n\n")
        
        for i, hit in enumerate(current_hits, 1):
            email = hit.get('email', 'Unknown')
            password = hit.get('password', 'Unknown')
            country = hit.get('country', 'Unknown')
            plan = hit.get('plan', hit.get('tipo', 'Unknown'))
            
            f.write(f"#{i}\n")
            f.write(f"📧 Email: {email}\n")
            f.write(f"🔑 Password: {password}\n")
            f.write(f"🌍 País: {country}\n")
            f.write(f"📡 Plan: {plan}\n")
            f.write("-" * 50 + "\n\n")
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/clear_logs', methods=['POST'])
def clear_logs():
    """Limpia los logs"""
    checker_status['logs'] = []
    return jsonify({'success': True})

@app.route('/api/clear_hits', methods=['POST'])
def clear_hits():
    """Limpia los hits"""
    global current_hits
    current_hits = []
    checker_status['results'] = []
    return jsonify({'success': True})

# ============================================
# HTML TEMPLATE (MEJORADO)
# ============================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Checker Dashboard Pro</title>
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
        ::-webkit-scrollbar-track { background: #15161a; border-radius: 3px; }
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
        .header-logo { font-size: 32px; }
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
            flex-wrap: wrap;
        }
        .header-badge {
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .badge-stopped { background: #ff4444; color: #fff; }
        .badge-running { background: #00cc88; color: #0a0a0f; }
        .badge-waiting { background: #ffaa44; color: #0a0a0f; }
        
        /* ===== MAIN LAYOUT ===== */
        .main {
            max-width: 1500px;
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
            justify-content: space-between;
            gap: 8px;
        }
        .card-title .badge {
            font-size: 11px;
            font-weight: normal;
            color: #8a8c9e;
            background: #0a0a0f;
            padding: 2px 10px;
            border-radius: 12px;
        }
        
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
        .form-group input {
            width: 100%;
            padding: 10px 12px;
            background: #0a0a0f;
            border: 1px solid #2a2b35;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            transition: border 0.3s;
        }
        .form-group input:focus {
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
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-primary { background: #E4751E; color: #fff; }
        .btn-primary:hover { background: #c9651a; transform: translateY(-1px); }
        .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
        
        .btn-danger { background: #ff4444; color: #fff; }
        .btn-danger:hover { background: #cc0000; }
        .btn-danger:disabled { opacity: 0.4; cursor: not-allowed; }
        
        .btn-success { background: #00cc88; color: #0a0a0f; }
        .btn-success:hover { background: #00aa77; }
        .btn-success:disabled { opacity: 0.4; cursor: not-allowed; }
        
        .btn-secondary { background: #2a2b35; color: #fff; }
        .btn-secondary:hover { background: #3a3b45; }
        
        .btn-group {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 10px;
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
        .checker-option:hover { border-color: #E4751E66; }
        .checker-option.active {
            border-color: #E4751E;
            background: #E4751E15;
        }
        .checker-option .icon { font-size: 28px; }
        .checker-option .name { font-size: 13px; font-weight: bold; margin-top: 4px; }
        .checker-option .desc { font-size: 10px; color: #8a8c9e; }
        .checker-option .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-top: 4px;
        }
        .dot-idle { background: #555; }
        .dot-running { background: #00cc88; animation: pulse 1s infinite; }
        .dot-done { background: #ffaa44; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        
        /* ===== STATS ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 8px;
            margin-bottom: 12px;
        }
        .stat-item {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }
        .stat-value {
            font-size: 22px;
            font-weight: bold;
            color: #E4751E;
        }
        .stat-label {
            font-size: 10px;
            color: #8a8c9e;
            margin-top: 2px;
        }
        .stat-hit { color: #00ff88; }
        .stat-error { color: #ff4444; }
        .stat-invalid { color: #ffaa44; }
        .stat-total { color: #E4751E; }
        
        /* ===== PROGRESS ===== */
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #2a2b35;
            border-radius: 4px;
            overflow: hidden;
            margin: 8px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #E4751E, #ff9a44);
            border-radius: 4px;
            transition: width 0.5s;
            width: 0%;
        }
        .progress-text {
            font-size: 12px;
            color: #8a8c9e;
            text-align: right;
        }
        
        /* ===== LOGS ===== */
        .log-container {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 10px;
            max-height: 280px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            line-height: 1.5;
        }
        .log-line { padding: 2px 0; border-bottom: 1px solid #0f0f14; }
        .log-hit { color: #00ff88; }
        .log-free { color: #8a8c9e; }
        .log-invalid { color: #ffaa44; }
        .log-error { color: #ff4444; }
        .log-info { color: #E4751E; }
        .log-2fa { color: #ff8800; }
        .log-custom { color: #cc88ff; }
        
        /* ===== HITS ===== */
        .hits-container {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 10px;
            max-height: 280px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 11px;
        }
        .hit-item {
            padding: 4px 8px;
            border-bottom: 1px solid #0f0f14;
            color: #00ff88;
        }
        .hit-item .badge-plan {
            background: #E4751E33;
            padding: 1px 8px;
            border-radius: 10px;
            font-size: 10px;
            color: #E4751E;
        }
        
        /* ===== UPLOAD STATUS ===== */
        .upload-status {
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            margin-top: 4px;
        }
        .upload-success { background: #00cc8822; color: #00cc88; border: 1px solid #00cc8844; }
        .upload-error { background: #ff444422; color: #ff4444; border: 1px solid #ff444444; }
        .upload-waiting { background: #ffaa4422; color: #ffaa44; border: 1px solid #ffaa4444; }
        
        /* ===== STATUS INDICATOR ===== */
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            background: #0a0a0f;
            border-radius: 8px;
        }
        .status-indicator .led {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
        }
        .led-red { background: #ff4444; }
        .led-green { background: #00cc88; animation: pulse 1s infinite; }
        .led-yellow { background: #ffaa44; }
        
        /* ===== RESPONSIVE ===== */
        @media (max-width: 600px) {
            .header-title { font-size: 16px; }
            .stats-grid { grid-template-columns: repeat(3, 1fr); }
            .btn { padding: 8px 14px; font-size: 12px; }
            .checker-selector { grid-template-columns: repeat(3, 1fr); }
        }
        
        /* ===== TIMER ===== */
        .timer-display {
            font-family: 'Courier New', monospace;
            font-size: 16px;
            color: #E4751E;
            font-weight: bold;
        }
        
        /* ===== EMPTY STATE ===== */
        .empty-state {
            text-align: center;
            padding: 30px 20px;
            color: #8a8c9e;
        }
        .empty-state .icon { font-size: 40px; }
        .empty-state .text { font-size: 14px; margin-top: 8px; }
    </style>
</head>
<body>
    <!-- ===== HEADER ===== -->
    <header class="header">
        <div class="header-left">
            <span class="header-logo">🚀</span>
            <div>
                <div class="header-title">Checker Dashboard Pro</div>
                <div class="header-subtitle">Multi-Checker Unificado v2.0</div>
            </div>
        </div>
        <div class="header-right">
            <div class="status-indicator">
                <span class="led led-red" id="statusLed"></span>
                <span id="statusText" style="font-size:13px;font-weight:bold;color:#ff4444;">Detenido</span>
            </div>
            <span class="timer-display" id="timerDisplay">00:00:00</span>
        </div>
    </header>

    <!-- ===== MAIN ===== -->
    <div class="main">
        <!-- ===== COLUMNA IZQUIERDA ===== -->
        <div>
            <!-- Configuración -->
            <div class="card">
                <div class="card-title">
                    ⚙️ Configuración
                    <span class="badge" id="accountsCount">0 cuentas</span>
                </div>
                
                <div class="form-group">
                    <label>📌 Seleccionar Checker</label>
                    <div class="checker-selector">
                        <div class="checker-option active" data-checker="crunchyroll" onclick="selectChecker(this)">
                            <div class="icon">🍥</div>
                            <div class="name">Crunchyroll</div>
                            <div class="desc">Premium Accounts</div>
                            <span class="status-dot dot-idle" id="dot-crunchyroll"></span>
                        </div>
                        <div class="checker-option" data-checker="paramount" onclick="selectChecker(this)">
                            <div class="icon">🎬</div>
                            <div class="name">Paramount+</div>
                            <div class="desc">Streaming Accounts</div>
                            <span class="status-dot dot-idle" id="dot-paramount"></span>
                        </div>
                        <div class="checker-option" data-checker="hotmail" onclick="selectChecker(this)">
                            <div class="icon">📧</div>
                            <div class="name">Hotmail</div>
                            <div class="desc">Inbox Checker</div>
                            <span class="status-dot dot-idle" id="dot-hotmail"></span>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>📄 Cuentas (email:password)</label>
                    <input type="file" id="accountsFile" accept=".txt" onchange="uploadFile('accounts')">
                    <div id="accountsStatus" class="upload-status upload-waiting" style="display:none;">Esperando archivo...</div>
                </div>
                
                <div class="form-group">
                    <label>🌐 Proxies (opcional)</label>
                    <input type="file" id="proxiesFile" accept=".txt" onchange="uploadFile('proxies')">
                    <div id="proxiesStatus" class="upload-status upload-waiting" style="display:none;">Esperando archivo...</div>
                </div>
                
                <div class="btn-group">
                    <button class="btn btn-primary" id="btnStart" onclick="startChecker()">▶ Iniciar</button>
                    <button class="btn btn-danger" id="btnStop" onclick="stopChecker()" disabled>⏹ Detener</button>
                    <button class="btn btn-success" id="btnExport" onclick="exportHits()">💾 Exportar Hits</button>
                    <button class="btn btn-secondary" onclick="clearLogs()">🗑 Logs</button>
                    <button class="btn btn-secondary" onclick="clearHits()">🗑 Hits</button>
                </div>
            </div>
            
            <!-- Estadísticas -->
            <div class="card" style="margin-top:20px;">
                <div class="card-title">
                    📊 Estadísticas
                    <span class="badge" id="progressText">0%</span>
                </div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value stat-total" id="statTotal">0</div>
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
                        <div class="stat-value" id="statSpeed">0</div>
                        <div class="stat-label">📈 /min</div>
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
                <div class="card-title">
                    📜 Logs
                    <span class="badge" id="logCount">(0)</span>
                </div>
                <div class="log-container" id="logContainer">
                    <div class="log-line log-info">[INFO] 🚀 Esperando inicio...</div>
                </div>
            </div>
            
            <!-- Hits -->
            <div class="card" style="margin-top:20px;">
                <div class="card-title">
                    🏆 Hits
                    <span class="badge" id="hitCount">(0)</span>
                </div>
                <div class="hits-container" id="hitsContainer">
                    <div class="empty-state">
                        <div class="icon">🎯</div>
                        <div class="text">Esperando hits premium...</div>
                    </div>
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
        let elapsedSeconds = 0;
        let lastProcessed = 0;
        let speedTimer = null;
        
        // ===== SELECTOR DE CHECKER =====
        function selectChecker(el) {
            if (isRunning) {
                alert('⚠️ Detén el checker antes de cambiar.');
                return;
            }
            document.querySelectorAll('.checker-option').forEach(c => c.classList.remove('active'));
            el.classList.add('active');
            currentChecker = el.dataset.checker;
            updateCheckerDots();
        }
        
        function updateCheckerDots() {
            document.querySelectorAll('.checker-option').forEach(c => {
                const dot = c.querySelector('.status-dot');
                if (c.classList.contains('active')) {
                    dot.className = 'status-dot dot-idle';
                } else {
                    dot.className = 'status-dot dot-idle';
                }
            });
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
                        document.getElementById('accountsCount').textContent = `${data.count} cuentas`;
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
                    document.getElementById('statusText').textContent = '▶ Ejecutando';
                    document.getElementById('statusText').style.color = '#00cc88';
                    document.getElementById('statusLed').className = 'led led-green';
                    
                    // Actualizar dots
                    document.querySelectorAll('.checker-option').forEach(c => {
                        const dot = c.querySelector('.status-dot');
                        if (c.dataset.checker === currentChecker) {
                            dot.className = 'status-dot dot-running';
                        }
                    });
                    
                    elapsedSeconds = 0;
                    lastProcessed = 0;
                    
                    if (statusInterval) clearInterval(statusInterval);
                    if (timerInterval) clearInterval(timerInterval);
                    if (speedTimer) clearInterval(speedTimer);
                    
                    statusInterval = setInterval(fetchStatus, 800);
                    timerInterval = setInterval(updateTimer, 1000);
                    speedTimer = setInterval(updateSpeed, 2000);
                    
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
                    document.getElementById('statusText').textContent = '⏹ Detenido';
                    document.getElementById('statusText').style.color = '#ff4444';
                    document.getElementById('statusLed').className = 'led led-red';
                    
                    document.querySelectorAll('.checker-option').forEach(c => {
                        const dot = c.querySelector('.status-dot');
                        dot.className = 'status-dot dot-idle';
                    });
                    
                    if (statusInterval) clearInterval(statusInterval);
                    if (timerInterval) clearInterval(timerInterval);
                    if (speedTimer) clearInterval(speedTimer);
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
                document.getElementById('logContainer').innerHTML = '<div class="log-line log-info">[INFO] Logs limpiados</div>';
                document.getElementById('logCount').textContent = '(0)';
            } catch (e) {
                console.error(e);
            }
        }
        
        // ===== LIMPIAR HITS =====
        async function clearHits() {
            try {
                await fetch('/api/clear_hits', { method: 'POST' });
                document.getElementById('hitsContainer').innerHTML = `
                    <div class="empty-state">
                        <div class="icon">🎯</div>
                        <div class="text">Hits limpiados</div>
                    </div>
                `;
                document.getElementById('hitCount').textContent = '(0)';
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
                document.getElementById('progressText').textContent = progress + '%';
                document.getElementById('progressFill').style.width = progress + '%';
                
                // Logs
                if (data.logs && data.logs.length) {
                    const container = document.getElementById('logContainer');
                    const lastLogs = data.logs.slice(-30);
                    container.innerHTML = lastLogs.map(log => {
                        let className = 'log-info';
                        if (log.includes('[HIT]')) className = 'log-hit';
                        else if (log.includes('[FREE]')) className = 'log-free';
                        else if (log.includes('[INVALID]')) className = 'log-invalid';
                        else if (log.includes('[ERROR]')) className = 'log-error';
                        else if (log.includes('[2FA]')) className = 'log-2fa';
                        else if (log.includes('[CUSTOM]')) className = 'log-custom';
                        return `<div class="log-line ${className}">${escapeHtml(log)}</div>`;
                    }).join('');
                    container.scrollTop = container.scrollHeight;
                    document.getElementById('logCount').textContent = `(${data.logs.length})`;
                }
                
                // Hits
                if (data.results && data.results.length) {
                    const container = document.getElementById('hitsContainer');
                    const hits = data.results.slice(-15);
                    if (hits.length > 0) {
                        container.innerHTML = hits.map(hit => {
                            const email = hit.email || 'Unknown';
                            const plan = hit.plan || hit.tipo || 'Unknown';
                            const country = hit.country || 'Unknown';
                            return `<div class="hit-item">✅ ${email} | <span class="badge-plan">${plan}</span> | ${country}</div>`;
                        }).join('');
                    }
                    document.getElementById('hitCount').textContent = `(${data.hits || 0})`;
                }
                
                // Actualizar running state
                if (!data.running && isRunning) {
                    isRunning = false;
                    document.getElementById('btnStart').disabled = false;
                    document.getElementById('btnStop').disabled = true;
                    document.getElementById('statusText').textContent = '✅ Finalizado';
                    document.getElementById('statusText').style.color = '#ffaa44';
                    document.getElementById('statusLed').className = 'led led-yellow';
                    
                    document.querySelectorAll('.checker-option').forEach(c => {
                        const dot = c.querySelector('.status-dot');
                        if (c.dataset.checker === currentChecker) {
                            dot.className = 'status-dot dot-done';
                        }
                    });
                    
                    if (statusInterval) clearInterval(statusInterval);
                    if (timerInterval) clearInterval(timerInterval);
                    if (speedTimer) clearInterval(speedTimer);
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
        
        // ===== SPEED =====
        function updateSpeed() {
            const processed = parseInt(document.getElementById('statProcessed').textContent) || 0;
            const speed = Math.round((processed - lastProcessed) * 30); // *30 porque cada 2s
            document.getElementById('statSpeed').textContent = speed > 0 ? speed : 0;
            lastProcessed = processed;
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