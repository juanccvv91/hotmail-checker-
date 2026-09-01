import os
import re
import time
import random
import threading
import json
import requests
import urllib3
import asyncio
import socket
import ssl
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from fake_useragent import UserAgent

# Intentar importar librerías de bypass (opcionales)
try:
    import kscraper
    KSCRAPER_AVAILABLE = True
except ImportError:
    KSCRAPER_AVAILABLE = False
    print("⚠️ kscraper no instalado, usando requests normal")

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️ websocket-client no instalado")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

PORT = int(os.environ.get('PORT', 5000))

# ============================================
# ESTADO GLOBAL
# ============================================
checker_state = {
    'running': False,
    'channel_info': None,
    'viewers_injected': 0,
    'active_connections': 0,
    'logs': [],
    'start_time': None,
    'method': 'api',
    'target': 0,
    'injection_results': []
}

def add_log(message, level='info'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    checker_state['logs'].insert(0, {
        'time': timestamp,
        'message': message,
        'level': level
    })
    if len(checker_state['logs']) > 500:
        checker_state['logs'] = checker_state['logs'][:500]

def get_headers():
    ua = UserAgent()
    return {
        'User-Agent': ua.random,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Referer': 'https://kick.com/',
        'Origin': 'https://kick.com',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

# ============================================
# BYPASS DE CLOUDFLARE
# ============================================
def request_with_bypass(url, method='GET', data=None, headers=None, timeout=15):
    """Realiza petición con bypass de Cloudflare"""
    if KSCRAPER_AVAILABLE:
        try:
            if method == 'GET':
                response = kscraper.get(url, headers=headers, timeout=timeout)
            else:
                response = kscraper.post(url, data=data, headers=headers, timeout=timeout)
            return response
        except Exception as e:
            add_log(f"⚠️ kscraper falló: {str(e)[:50]}, usando requests normal", 'warning')
    
    # Fallback a requests normal
    session = requests.Session()
    session.headers.update(headers or get_headers())
    
    # Configurar socket con timeout
    session.timeout = timeout
    
    if method == 'GET':
        response = session.get(url, verify=False, timeout=timeout)
    else:
        response = session.post(url, json=data, verify=False, timeout=timeout)
    
    return response

# ============================================
# INFO DEL CANAL (5 MÉTODOS)
# ============================================
class KickChannelInfo:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
    
    # MÉTODO 1: API OFICIAL
    def get_by_api(self, channel):
        try:
            url = f'https://kick.com/api/v2/channels/{channel}'
            headers = {'User-Agent': self.ua.random, 'Accept': 'application/json'}
            response = request_with_bypass(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                livestream = data.get('livestream', {})
                user = data.get('user', {})
                
                return {
                    'success': True,
                    'method': 'API Oficial',
                    'channel': user.get('username', channel),
                    'display_name': user.get('display_name', channel),
                    'followers': data.get('followers_count', 0),
                    'is_live': livestream.get('is_live', False) if livestream else False,
                    'viewers': livestream.get('viewer_count', 0) if livestream else 0,
                    'title': livestream.get('session_title', '') if livestream else '',
                    'category': livestream.get('category', {}).get('name', '') if livestream and livestream.get('category') else ''
                }
            return {'success': False, 'error': f'Error {response.status_code}', 'method': 'API Oficial'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'method': 'API Oficial'}
    
    # MÉTODO 2: GRAPHQL
    def get_by_graphql(self, channel):
        try:
            url = 'https://kick.com/api/graphql'
            headers = {'User-Agent': self.ua.random, 'Content-Type': 'application/json', 'Accept': 'application/json'}
            
            query = {
                'query': '''
                    query ChannelPage($username: String!) {
                        channelByUsername(username: $username) {
                            id
                            username
                            displayName
                            followersCount
                            livestream {
                                isLive
                                viewerCount
                                sessionTitle
                                category { name }
                            }
                        }
                    }
                ''',
                'variables': {'username': channel}
            }
            
            response = request_with_bypass(url, method='POST', data=query, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                channel_data = data.get('data', {}).get('channelByUsername', {})
                livestream = channel_data.get('livestream', {})
                
                return {
                    'success': True,
                    'method': 'GraphQL',
                    'channel': channel_data.get('username', channel),
                    'display_name': channel_data.get('displayName', channel),
                    'followers': channel_data.get('followersCount', 0),
                    'is_live': livestream.get('isLive', False) if livestream else False,
                    'viewers': livestream.get('viewerCount', 0) if livestream else 0,
                    'title': livestream.get('sessionTitle', '') if livestream else '',
                    'category': livestream.get('category', {}).get('name', '') if livestream and livestream.get('category') else ''
                }
            return {'success': False, 'error': f'Error {response.status_code}', 'method': 'GraphQL'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'method': 'GraphQL'}
    
    # MÉTODO 3: SCRAPING HTML
    def get_by_scraping(self, channel):
        try:
            url = f'https://kick.com/{channel}'
            headers = {'User-Agent': self.ua.random, 'Accept': 'text/html'}
            response = request_with_bypass(url, headers=headers)
            
            if response.status_code != 200:
                return {'success': False, 'error': f'Error {response.status_code}', 'method': 'Scraping'}
            
            match = re.search(r'<script id="__NEXT_DATA__".*?>(.*?)</script>', response.text, re.DOTALL)
            if not match:
                return {'success': False, 'error': 'No se encontraron datos', 'method': 'Scraping'}
            
            data = json.loads(match.group(1))
            channel_data = data.get('props', {}).get('pageProps', {}).get('channel', {})
            livestream = channel_data.get('livestream', {})
            user = channel_data.get('user', {})
            
            return {
                'success': True,
                'method': 'Scraping',
                'channel': user.get('username', channel),
                'display_name': user.get('display_name', channel),
                'followers': channel_data.get('followers_count', 0),
                'is_live': livestream.get('is_live', False) if livestream else False,
                'viewers': livestream.get('viewer_count', 0) if livestream else 0,
                'title': livestream.get('session_title', '') if livestream else '',
                'category': livestream.get('category', {}).get('name', '') if livestream and livestream.get('category') else ''
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'method': 'Scraping'}
    
    # MÉTODO 4: API CON BYPASS CLOUDFLARE (KSCRAPER)
    def get_by_kscraper(self, channel):
        if not KSCRAPER_AVAILABLE:
            return {'success': False, 'error': 'kscraper no disponible', 'method': 'kscraper'}
        
        try:
            url = f'https://kick.com/api/v2/channels/{channel}'
            response = kscraper.get(url, headers={'Accept': 'application/json'})
            
            if response.status_code == 200:
                data = response.json()
                livestream = data.get('livestream', {})
                user = data.get('user', {})
                
                return {
                    'success': True,
                    'method': 'kscraper (Bypass CF)',
                    'channel': user.get('username', channel),
                    'display_name': user.get('display_name', channel),
                    'followers': data.get('followers_count', 0),
                    'is_live': livestream.get('is_live', False) if livestream else False,
                    'viewers': livestream.get('viewer_count', 0) if livestream else 0,
                    'title': livestream.get('session_title', '') if livestream else '',
                    'category': livestream.get('category', {}).get('name', '') if livestream and livestream.get('category') else ''
                }
            return {'success': False, 'error': f'Error {response.status_code}', 'method': 'kscraper'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'method': 'kscraper'}
    
    # MÉTODO 5: API PÚBLICA
    def get_by_public_api(self, channel):
        try:
            url = f'https://kick.com/api/v1/channels/{channel}'
            headers = {'User-Agent': self.ua.random, 'Accept': 'application/json'}
            response = request_with_bypass(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                livestream = data.get('livestream', {})
                user = data.get('user', {})
                
                return {
                    'success': True,
                    'method': 'API Pública',
                    'channel': user.get('username', channel),
                    'display_name': user.get('display_name', channel),
                    'followers': data.get('followers_count', 0),
                    'is_live': livestream.get('is_live', False) if livestream else False,
                    'viewers': livestream.get('viewer_count', 0) if livestream else 0,
                    'title': livestream.get('session_title', '') if livestream else '',
                    'category': livestream.get('category', {}).get('name', '') if livestream and livestream.get('category') else ''
                }
            return {'success': False, 'error': f'Error {response.status_code}', 'method': 'API Pública'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'method': 'API Pública'}

# ============================================
# VIEWER BOT - 5 MÉTODOS DIFERENTES
# ============================================
class KickViewerBot:
    def __init__(self):
        self.running = False
        self.target_channel = None
        self.target_count = 0
        self.current_count = 0
        self.method = 'api'
        self.session = requests.Session()
        self.active_connections = []
        
    # ========== MÉTODO 1: API VIEWER ==========
    def inject_api(self, channel, count):
        """Inyecta viewers mediante la API de Kick"""
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'api'
        
        add_log(f"🚀 Iniciando inyección API en {channel} - Objetivo: {count} viewers", 'info')
        
        url = f'https://kick.com/api/v1/channels/{channel}/viewer'
        headers = get_headers()
        headers['Content-Type'] = 'application/json'
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                session = requests.Session()
                session.headers.update(headers)
                session.get(f'https://kick.com/{channel}', timeout=5)
                
                response = session.post(url, json={'channel': channel}, timeout=5)
                
                if response.status_code in [200, 201, 204]:
                    self.current_count += 1
                    checker_state['viewers_injected'] = self.current_count
                    add_log(f"✅ Viewer #{i+1} activo ({self.current_count}/{count})", 'success')
                else:
                    add_log(f"⚠️ #{i+1} falló ({response.status_code})", 'warning')
                
                session.close()
                time.sleep(0.5 + random.uniform(0, 0.3))
                
            except Exception as e:
                add_log(f"❌ Error #{i+1}: {str(e)[:80]}", 'error')
                time.sleep(0.5)
        
        self.running = False
        return self.current_count
    
    # ========== MÉTODO 2: REFRESH PAGE ==========
    def inject_refresh(self, channel, count):
        """Simula viewers refrescando la página del stream"""
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'refresh'
        
        add_log(f"🚀 Iniciando inyección por refresco en {channel} - Objetivo: {count} viewers", 'info')
        
        url = f'https://kick.com/{channel}'
        headers = get_headers()
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                session = requests.Session()
                session.headers.update(headers)
                response = session.get(url, timeout=5)
                
                if response.status_code == 200:
                    self.current_count += 1
                    checker_state['viewers_injected'] = self.current_count
                    add_log(f"✅ Refresco #{i+1} completado ({self.current_count}/{count})", 'success')
                else:
                    add_log(f"⚠️ Refresco #{i+1} falló ({response.status_code})", 'warning')
                
                session.close()
                time.sleep(1 + random.uniform(0, 0.5))
                
            except Exception as e:
                add_log(f"❌ Error refresco #{i+1}: {str(e)[:80]}", 'error')
                time.sleep(0.5)
        
        self.running = False
        return self.current_count
    
    # ========== MÉTODO 3: WEBSOCKET SIMULADO ==========
    def inject_websocket(self, channel, count):
        """Simula conexiones WebSocket"""
        if not WEBSOCKET_AVAILABLE:
            add_log("❌ websocket-client no instalado", 'error')
            return 0
        
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'websocket'
        
        add_log(f"🚀 Iniciando inyección WebSocket en {channel} - Objetivo: {count} viewers", 'info')
        
        # Obtener token primero
        try:
            url = f'https://kick.com/api/v2/channels/{channel}'
            headers = get_headers()
            response = request_with_bypass(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                livestream = data.get('livestream', {})
                token = livestream.get('key', '')
            else:
                token = ''
        except:
            token = ''
        
        ws_url = "wss://kick.com/ws"
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                ws = websocket.WebSocket()
                ws.connect(ws_url, timeout=5)
                
                # Enviar autenticación
                if token:
                    auth_msg = json.dumps({
                        "type": "auth",
                        "token": token,
                        "channel": channel
                    })
                    ws.send(auth_msg)
                
                # Enviar heartbeat
                ws.send(json.dumps({"type": "heartbeat"}))
                
                self.current_count += 1
                checker_state['viewers_injected'] = self.current_count
                self.active_connections.append(ws)
                checker_state['active_connections'] = len(self.active_connections)
                add_log(f"✅ WebSocket #{i+1} conectado ({self.current_count}/{count})", 'success')
                
                time.sleep(0.5 + random.uniform(0, 0.3))
                
            except Exception as e:
                add_log(f"❌ WS #{i+1} falló: {str(e)[:80]}", 'error')
                time.sleep(0.5)
        
        self.running = False
        return self.current_count
    
    # ========== MÉTODO 4: KSCRAPER (BYPASS CLOUDFLARE) ==========
    def inject_kscraper(self, channel, count):
        """Inyecta usando kscraper con bypass de Cloudflare"""
        if not KSCRAPER_AVAILABLE:
            add_log("❌ kscraper no instalado", 'error')
            return 0
        
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'kscraper'
        
        add_log(f"🚀 Iniciando inyección con kscraper en {channel} - Objetivo: {count} viewers", 'info')
        
        url = f'https://kick.com/api/v1/channels/{channel}/viewer'
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                response = kscraper.post(url, json={'channel': channel}, headers=get_headers())
                
                if response.status_code in [200, 201, 204]:
                    self.current_count += 1
                    checker_state['viewers_injected'] = self.current_count
                    add_log(f"✅ kscraper #{i+1} activo ({self.current_count}/{count})", 'success')
                else:
                    add_log(f"⚠️ kscraper #{i+1} falló ({response.status_code})", 'warning')
                
                time.sleep(0.5 + random.uniform(0, 0.3))
                
            except Exception as e:
                add_log(f"❌ kscraper #{i+1}: {str(e)[:80]}", 'error')
                time.sleep(0.5)
        
        self.running = False
        return self.current_count
    
    # ========== MÉTODO 5: PROXY ROTATIVO ==========
    def inject_proxy(self, channel, count):
        """Inyecta con proxies rotativos (usa proxies públicos)"""
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'proxy'
        
        add_log(f"🚀 Iniciando inyección con proxies en {channel} - Objetivo: {count} viewers", 'info')
        
        # Proxies públicos de prueba (en producción usar residenciales)
        proxy_list = [
            None,
            None,
            None,
            # Agrega proxies reales aquí:
            # "http://user:pass@ip:port",
            # "http://ip:port",
        ]
        
        url_api = f'https://kick.com/api/v1/channels/{channel}/viewer'
        headers = get_headers()
        headers['Content-Type'] = 'application/json'
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                proxy = random.choice(proxy_list) if proxy_list else None
                session = requests.Session()
                session.headers.update(headers)
                
                if proxy:
                    session.proxies = {'http': proxy, 'https': proxy}
                
                # Obtener cookies primero
                session.get(f'https://kick.com/{channel}', timeout=5)
                
                response = session.post(url_api, json={'channel': channel}, timeout=5)
                
                if response.status_code in [200, 201, 204]:
                    self.current_count += 1
                    checker_state['viewers_injected'] = self.current_count
                    add_log(f"✅ Proxy #{i+1} activo ({self.current_count}/{count})", 'success')
                else:
                    add_log(f"⚠️ Proxy #{i+1} falló ({response.status_code})", 'warning')
                
                session.close()
                time.sleep(0.8 + random.uniform(0, 0.5))
                
            except Exception as e:
                add_log(f"❌ Proxy #{i+1}: {str(e)[:80]}", 'error')
                time.sleep(0.5)
        
        self.running = False
        return self.current_count

# ============================================
# INSTANCIAS
# ============================================
channel_info = KickChannelInfo()
viewer_bot = KickViewerBot()

# ============================================
# RUTAS DE LA API
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/channel/info', methods=['POST'])
def get_channel_info_route():
    data = request.json
    channel = data.get('channel', '').strip()
    method = data.get('method', 'all')
    
    if not channel:
        return jsonify({'error': 'No channel provided'}), 400
    
    add_log(f"🔍 Buscando información de {channel}", 'info')
    
    results = []
    methods = {
        'api': channel_info.get_by_api,
        'graphql': channel_info.get_by_graphql,
        'scraping': channel_info.get_by_scraping,
        'kscraper': channel_info.get_by_kscraper,
        'public': channel_info.get_by_public_api
    }
    
    if method == 'all':
        for name, func in methods.items():
            result = func(channel)
            results.append(result)
            if result['success']:
                add_log(f"✅ {result['method']}: {channel} - {'En vivo' if result['is_live'] else 'Offline'} ({result['viewers']} viewers)", 'success')
    else:
        func = methods.get(method)
        if func:
            result = func(channel)
            results.append(result)
            if result['success']:
                add_log(f"✅ {result['method']}: {channel} - {'En vivo' if result['is_live'] else 'Offline'} ({result['viewers']} viewers)", 'success')
        else:
            return jsonify({'error': 'Método no válido'}), 400
    
    if results and any(r.get('success') for r in results):
        best_result = next((r for r in results if r['success']), None)
        if best_result:
            checker_state['channel_info'] = best_result
    
    return jsonify({'success': True, 'channel': channel, 'results': results})

@app.route('/api/viewers/start', methods=['POST'])
def start_viewer_injection():
    if checker_state['running']:
        return jsonify({'error': 'Ya hay un proceso en ejecución'}), 400
    
    data = request.json
    channel = data.get('channel', '').strip()
    count = int(data.get('count', 10))
    method = data.get('method', 'api')
    
    if not channel:
        return jsonify({'error': 'No channel provided'}), 400
    
    if count < 1 or count > 10000:
        return jsonify({'error': 'Count must be between 1 and 10000'}), 400
    
    checker_state['running'] = True
    checker_state['start_time'] = time.time()
    checker_state['target'] = count
    checker_state['method'] = method
    checker_state['viewers_injected'] = 0
    
    method_names = {
        'api': 'API',
        'refresh': 'Refresco',
        'websocket': 'WebSocket',
        'kscraper': 'kscraper (Bypass CF)',
        'proxy': 'Proxy'
    }
    
    add_log(f"🚀 Iniciando inyección en {channel} con {count} viewers (método: {method_names.get(method, method)})", 'info')
    
    thread = threading.Thread(target=run_viewer_injection, args=(channel, count, method))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'channel': channel, 'count': count, 'method': method})

def run_viewer_injection(channel, count, method):
    try:
        methods = {
            'api': viewer_bot.inject_api,
            'refresh': viewer_bot.inject_refresh,
            'websocket': viewer_bot.inject_websocket,
            'kscraper': viewer_bot.inject_kscraper,
            'proxy': viewer_bot.inject_proxy
        }
        
        func = methods.get(method, viewer_bot.inject_api)
        func(channel, count)
        
    except Exception as e:
        add_log(f"❌ Error en inyección: {str(e)}", 'error')
    finally:
        checker_state['running'] = False
        elapsed = time.time() - checker_state['start_time']
        add_log(f"⏹️ Proceso finalizado en {int(elapsed)}s - {checker_state['viewers_injected']} viewers inyectados", 'info')

@app.route('/api/viewers/stop', methods=['POST'])
def stop_viewer_injection():
    if not checker_state['running']:
        return jsonify({'error': 'No hay proceso en ejecución'}), 400
    
    viewer_bot.running = False
    checker_state['running'] = False
    
    # Cerrar conexiones WebSocket
    for ws in viewer_bot.active_connections:
        try:
            ws.close()
        except:
            pass
    viewer_bot.active_connections = []
    checker_state['active_connections'] = 0
    
    add_log("⏹️ Inyección detenida por el usuario", 'warning')
    return jsonify({'success': True})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        'running': checker_state['running'],
        'channel_info': checker_state['channel_info'],
        'viewers_injected': checker_state['viewers_injected'],
        'active_connections': checker_state['active_connections'],
        'target': checker_state['target'],
        'method': checker_state['method'],
        'logs': checker_state['logs'][:50],
        'start_time': checker_state['start_time'],
        'kscraper_available': KSCRAPER_AVAILABLE,
        'websocket_available': WEBSOCKET_AVAILABLE
    })

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    checker_state['logs'] = []
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
