import os
import re
import time
import random
import threading
import json
import requests
import websocket
import urllib3
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from fake_useragent import UserAgent
import ssl

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
    'method': 'websocket',
    'target': 0
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
        'Sec-Fetch-Site': 'same-site'
    }

# ============================================
# OBTENER TOKEN DE AUTENTICACIÓN
# ============================================
def get_kick_token(channel):
    """Obtiene el token de autenticación para WebSocket"""
    try:
        url = f'https://kick.com/api/v2/channels/{channel}'
        headers = get_headers()
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            livestream = data.get('livestream', {})
            if livestream and livestream.get('is_live'):
                # Token para WebSocket
                return {
                    'success': True,
                    'token': livestream.get('key', ''),
                    'channel_id': data.get('id', ''),
                    'stream_id': livestream.get('id', '')
                }
            else:
                return {
                    'success': False,
                    'error': 'El canal no está en vivo'
                }
        return {'success': False, 'error': f'Error {response.status_code}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================
# CLASE VIEWER BOT CON WEBSOCKET CORRECTO
# ============================================
class KickViewerBot:
    def __init__(self):
        self.active_connections = []
        self.running = False
        self.target_channel = None
        self.target_count = 0
        self.current_count = 0
        self.method = 'websocket'
        self.ws_url = "wss://kick.com/ws"
        self.session = requests.Session()
        
    def get_cookies(self, channel):
        """Obtiene cookies necesarias para la conexión"""
        try:
            url = f'https://kick.com/{channel}'
            headers = get_headers()
            response = self.session.get(url, headers=headers, timeout=10)
            return response.cookies.get_dict()
        except:
            return {}
    
    # ========== MÉTODO 1: WEBSOCKET CON AUTENTICACIÓN COMPLETA ==========
    def inject_websocket(self, channel, count):
        """Inyecta viewers con WebSocket autenticado"""
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'websocket'
        
        add_log(f"🚀 Iniciando inyección WebSocket en {channel} - Objetivo: {count} viewers", 'info')
        
        # Obtener token de autenticación
        token_data = get_kick_token(channel)
        if not token_data.get('success'):
            add_log(f"❌ {token_data.get('error', 'No se pudo obtener token')}", 'error')
            self.running = False
            return 0
        
        token = token_data.get('token')
        channel_id = token_data.get('channel_id')
        stream_id = token_data.get('stream_id')
        
        add_log(f"✅ Token obtenido correctamente", 'success')
        
        # Obtener cookies
        cookies = self.get_cookies(channel)
        cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                # Headers completos para WebSocket
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Origin': 'https://kick.com',
                    'Referer': f'https://kick.com/{channel}',
                    'Cookie': cookie_str,
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
                    'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
                    'Sec-WebSocket-Version': '13'
                }
                
                # Crear conexión WebSocket con timeout
                ws = websocket.WebSocket()
                ws.connect(
                    self.ws_url,
                    header=headers,
                    cookie=cookie_str,
                    timeout=5,
                    skip_utf8_validation=True
                )
                
                # Enviar mensaje de autenticación
                auth_msg = {
                    "type": "auth",
                    "token": token,
                    "channel_id": channel_id,
                    "stream_id": stream_id
                }
                ws.send(json.dumps(auth_msg))
                time.sleep(0.3)
                
                # Enviar heartbeat
                heartbeat = {
                    "type": "heartbeat"
                }
                ws.send(json.dumps(heartbeat))
                
                # Recibir respuesta de confirmación
                try:
                    response = ws.recv(timeout=2)
                    resp_data = json.loads(response)
                    if resp_data.get('type') == 'auth_success':
                        self.active_connections.append(ws)
                        self.current_count += 1
                        checker_state['viewers_injected'] = self.current_count
                        checker_state['active_connections'] = len(self.active_connections)
                        add_log(f"✅ Conexión WS #{i+1} autenticada ({self.current_count}/{count})", 'success')
                    else:
                        add_log(f"⚠️ Conexión #{i+1} autenticación fallida: {resp_data}", 'warning')
                        ws.close()
                except websocket.WebSocketTimeoutException:
                    add_log(f"⚠️ Conexión #{i+1} timeout en respuesta", 'warning')
                    ws.close()
                
                # Pausa entre conexiones
                time.sleep(0.5 + random.uniform(0, 0.5))
                
            except websocket.WebSocketBadStatusException as e:
                add_log(f"❌ Error en conexión #{i+1}: {str(e)}", 'error')
                time.sleep(1)
            except websocket.WebSocketConnectionClosedException:
                add_log(f"❌ Conexión #{i+1} cerrada inesperadamente", 'error')
                time.sleep(1)
            except Exception as e:
                add_log(f"❌ Error en conexión #{i+1}: {str(e)[:100]}", 'error')
                time.sleep(1)
        
        if self.current_count >= count:
            add_log(f"🎉 Inyección completada: {self.current_count} viewers conectados", 'success')
        else:
            add_log(f"⚠️ Inyección parcial: {self.current_count}/{count} viewers conectados", 'warning')
        
        self.running = False
        return self.current_count

    # ========== MÉTODO 2: WEBSOCKET CON PROXIES ==========
    def inject_proxy_websocket(self, channel, count):
        """Inyecta viewers con WebSocket + proxies"""
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'proxy_websocket'
        
        add_log(f"🚀 Iniciando inyección con proxies en {channel} - Objetivo: {count} viewers", 'info')
        
        # Obtener token
        token_data = get_kick_token(channel)
        if not token_data.get('success'):
            add_log(f"❌ {token_data.get('error', 'No se pudo obtener token')}", 'error')
            self.running = False
            return 0
        
        token = token_data.get('token')
        channel_id = token_data.get('channel_id')
        stream_id = token_data.get('stream_id')
        cookies = self.get_cookies(channel)
        cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
        
        # Lista de proxies de prueba (en producción usar proxies residenciales)
        proxy_list = [
            None,  # Sin proxy para algunos
            None,  # Sin proxy para algunos
            None,  # Sin proxy para algunos
        ]
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                proxy = random.choice(proxy_list) if proxy_list else None
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Origin': 'https://kick.com',
                    'Referer': f'https://kick.com/{channel}',
                    'Cookie': cookie_str,
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
                
                ws = websocket.WebSocket()
                ws.connect(
                    self.ws_url,
                    header=headers,
                    cookie=cookie_str,
                    timeout=5
                )
                
                auth_msg = {
                    "type": "auth",
                    "token": token,
                    "channel_id": channel_id,
                    "stream_id": stream_id
                }
                ws.send(json.dumps(auth_msg))
                time.sleep(0.3)
                ws.send(json.dumps({"type": "heartbeat"}))
                
                try:
                    response = ws.recv(timeout=2)
                    resp_data = json.loads(response)
                    if resp_data.get('type') == 'auth_success':
                        self.active_connections.append(ws)
                        self.current_count += 1
                        checker_state['viewers_injected'] = self.current_count
                        add_log(f"✅ Conexión Proxy #{i+1} autenticada ({self.current_count}/{count})", 'success')
                    else:
                        ws.close()
                except:
                    ws.close()
                
                time.sleep(0.6 + random.uniform(0, 0.5))
                
            except Exception as e:
                add_log(f"❌ Error en proxy #{i+1}: {str(e)[:80]}", 'error')
                time.sleep(1)
        
        self.running = False
        return self.current_count

    # ========== MÉTODO 3: API DE VIEWER (POST) ==========
    def inject_requests(self, channel, count):
        """Inyecta viewers mediante peticiones HTTP"""
        self.running = True
        self.target_channel = channel
        self.target_count = count
        self.current_count = 0
        self.method = 'requests'
        
        add_log(f"🚀 Iniciando inyección HTTP en {channel} - Objetivo: {count} viewers", 'info')
        
        token_data = get_kick_token(channel)
        if not token_data.get('success'):
            add_log(f"❌ {token_data.get('error', 'No se pudo obtener token')}", 'error')
            self.running = False
            return 0
        
        token = token_data.get('token')
        url = f'https://kick.com/api/v1/channels/{channel}/viewer'
        headers = get_headers()
        headers['Content-Type'] = 'application/json'
        headers['X-Client-Token'] = token
        
        for i in range(count):
            if not self.running:
                break
            
            try:
                session = requests.Session()
                session.headers.update(headers)
                
                response = session.post(url, json={'channel': channel}, timeout=5)
                
                if response.status_code in [200, 201, 204]:
                    self.current_count += 1
                    checker_state['viewers_injected'] = self.current_count
                    add_log(f"✅ Viewer HTTP #{i+1} activo ({self.current_count}/{count})", 'success')
                else:
                    add_log(f"⚠️ HTTP #{i+1} falló ({response.status_code})", 'warning')
                
                session.close()
                time.sleep(0.3 + random.uniform(0, 0.2))
                
            except Exception as e:
                add_log(f"❌ Error HTTP #{i+1}: {str(e)[:80]}", 'error')
                time.sleep(0.5)
        
        self.running = False
        return self.current_count

# ============================================
# INFO DEL CANAL (3 MÉTODOS)
# ============================================
class KickChannelInfo:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
    
    def get_by_api(self, channel):
        try:
            url = f'https://kick.com/api/v2/channels/{channel}'
            headers = {'User-Agent': self.ua.random, 'Accept': 'application/json'}
            response = self.session.get(url, headers=headers, timeout=10)
            
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
            
            response = self.session.post(url, json=query, headers=headers, timeout=10)
            
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
    
    def get_by_scraping(self, channel):
        try:
            url = f'https://kick.com/{channel}'
            headers = {'User-Agent': self.ua.random, 'Accept': 'text/html'}
            response = self.session.get(url, headers=headers, timeout=10)
            
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
def get_channel_info():
    data = request.json
    channel = data.get('channel', '').strip()
    method = data.get('method', 'all')
    
    if not channel:
        return jsonify({'error': 'No channel provided'}), 400
    
    add_log(f"🔍 Buscando información de {channel}", 'info')
    
    results = []
    
    if method in ['all', 'api']:
        result = channel_info.get_by_api(channel)
        results.append(result)
        if result['success']:
            add_log(f"✅ API: {channel} - {'En vivo' if result['is_live'] else 'Offline'} ({result['viewers']} viewers)", 'success')
    
    if method in ['all', 'graphql']:
        result = channel_info.get_by_graphql(channel)
        results.append(result)
        if result['success']:
            add_log(f"✅ GraphQL: {channel} - {'En vivo' if result['is_live'] else 'Offline'} ({result['viewers']} viewers)", 'success')
    
    if method in ['all', 'scraping']:
        result = channel_info.get_by_scraping(channel)
        results.append(result)
        if result['success']:
            add_log(f"✅ Scraping: {channel} - {'En vivo' if result['is_live'] else 'Offline'} ({result['viewers']} viewers)", 'success')
    
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
    method = data.get('method', 'websocket')
    
    if not channel:
        return jsonify({'error': 'No channel provided'}), 400
    
    if count < 1 or count > 10000:
        return jsonify({'error': 'Count must be between 1 and 10000'}), 400
    
    checker_state['running'] = True
    checker_state['start_time'] = time.time()
    checker_state['target'] = count
    checker_state['method'] = method
    checker_state['viewers_injected'] = 0
    
    add_log(f"🚀 Iniciando inyección en {channel} con {count} viewers (método: {method})", 'info')
    
    thread = threading.Thread(target=run_viewer_injection, args=(channel, count, method))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'channel': channel, 'count': count, 'method': method})

def run_viewer_injection(channel, count, method):
    try:
        if method == 'websocket':
            viewer_bot.inject_websocket(channel, count)
        elif method == 'requests':
            viewer_bot.inject_requests(channel, count)
        elif method == 'proxy_websocket':
            viewer_bot.inject_proxy_websocket(channel, count)
        else:
            viewer_bot.inject_websocket(channel, count)
    except Exception as e:
        add_log(f"❌ Error en inyección: {str(e)}", 'error')
    finally:
        checker_state['running'] = False
        checker_state['active_connections'] = len(viewer_bot.active_connections)
        elapsed = time.time() - checker_state['start_time']
        add_log(f"⏹️ Proceso finalizado en {int(elapsed)}s - {checker_state['viewers_injected']} viewers inyectados", 'info')

@app.route('/api/viewers/stop', methods=['POST'])
def stop_viewer_injection():
    if not checker_state['running']:
        return jsonify({'error': 'No hay proceso en ejecución'}), 400
    
    viewer_bot.running = False
    checker_state['running'] = False
    
    for ws in viewer_bot.active_connections:
        try:
            ws.close()
        except:
            pass
    viewer_bot.active_connections = []
    
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
        'start_time': checker_state['start_time']
    })

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    checker_state['logs'] = []
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
