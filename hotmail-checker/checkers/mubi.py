# checkers/mubi.py
import requests
import random
import string
import threading
from queue import Queue
import time

class MubiChecker:
    # ===== USER AGENTS =====
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.71 Safari/537.36",
    ]

    @staticmethod
    def _random_user_agent():
        """Genera un User-Agent aleatorio"""
        return random.choice(MubiChecker.USER_AGENTS)

    @staticmethod
    def _generate_code():
        """Genera un código aleatorio de 6 letras minúsculas"""
        return ''.join(random.choices(string.ascii_lowercase, k=6))

    @staticmethod
    def _format_proxy(proxy):
        """Formatea el proxy para requests"""
        if not proxy:
            return None
        proxy = proxy.strip()
        if proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
            return proxy
        parts = proxy.split(":")
        if len(parts) == 4:
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        if len(parts) == 2:
            return f"http://{parts[0]}:{parts[1]}"
        return f"http://{proxy}"

    @staticmethod
    def check_code(code: str, proxy: str = None) -> dict:
        """
        Verifica un código de MUBI
        Retorna: {'status': 'HIT'|'BAD'|'ERROR', 'code': str, 'type': str, 'days': str, 'message': str}
        """
        url = f"https://mubi.com/services/api/special_promos/{code}?country=TR"
        
        proxy_url = MubiChecker._format_proxy(proxy)
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": MubiChecker._random_user_agent(),
                    "Pragma": "no-cache",
                    "Accept": "*/*"
                },
                proxies=proxies,
                timeout=15
            )

            # ===== VERIFICAR RATE LIMIT =====
            if "Retry Later" in response.text:
                return {
                    "status": "ERROR",
                    "code": code,
                    "error": "Rate limit"
                }

            # ===== VERIFICAR STATUS =====
            if response.status_code in [403, 404, 503]:
                return {
                    "status": "BAD",
                    "code": code,
                    "message": f"HTTP {response.status_code}"
                }

            # ===== VERIFICAR HIT =====
            if "plan_level" in response.text or "id" in response.text:
                try:
                    data = response.json()
                    code_type = data.get("type", "Unknown")
                    days = data.get("plan_period_days", "?")
                    
                    if code_type == "Discount":
                        type_name = "Discount Code"
                    else:
                        type_name = code_type
                    
                    return {
                        "status": "HIT",
                        "code": code,
                        "type": type_name,
                        "days": str(days),
                        "message": f"Type: {type_name} | Days: {days}"
                    }
                except:
                    return {
                        "status": "HIT",
                        "code": code,
                        "type": "Unknown",
                        "days": "?",
                        "message": "Hit but could not parse response"
                    }
            else:
                return {
                    "status": "BAD",
                    "code": code,
                    "message": "Invalid code"
                }

        except requests.exceptions.ProxyError:
            return {"status": "ERROR", "code": code, "error": "Proxy dead"}
        except requests.exceptions.Timeout:
            return {"status": "ERROR", "code": code, "error": "Timeout"}
        except requests.exceptions.ConnectionError:
            return {"status": "ERROR", "code": code, "error": "Connection failed"}
        except Exception as e:
            return {"status": "ERROR", "code": code, "error": str(e)[:80]}

    @staticmethod
    def generate_and_check(proxy: str = None, max_attempts: int = 1000) -> list:
        """
        Genera códigos y los verifica automáticamente
        Retorna: list de resultados
        """
        results = []
        stats = {"hit": 0, "bad": 0, "error": 0, "total": max_attempts}
        
        for i in range(max_attempts):
            code = MubiChecker._generate_code()
            result = MubiChecker.check_code(code, proxy)
            results.append(result)
            
            if result["status"] == "HIT":
                stats["hit"] += 1
            elif result["status"] == "BAD":
                stats["bad"] += 1
            else:
                stats["error"] += 1
            
            # Pequeña pausa para evitar rate limit
            if i % 10 == 0:
                time.sleep(0.1)
        
        return results, stats

    @staticmethod
    def process_batch(codes: list, proxies: list = None, threads: int = 5) -> list:
        """
        Procesa un lote de códigos con threads
        """
        results = []
        stats = {"hit": 0, "bad": 0, "error": 0, "total": len(codes)}
        
        proxy_index = 0
        proxy_lock = threading.Lock()
        result_lock = threading.Lock()
        
        def get_next_proxy():
            nonlocal proxy_index
            if not proxies:
                return None
            with proxy_lock:
                proxy = proxies[proxy_index % len(proxies)]
                proxy_index += 1
                return proxy
        
        def check_code_thread(code):
            proxy = get_next_proxy()
            return MubiChecker.check_code(code, proxy)
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(check_code_thread, code): code for code in codes}
            for future in as_completed(futures):
                result = future.result()
                with result_lock:
                    results.append(result)
                    
                    if result["status"] == "HIT":
                        stats["hit"] += 1
                    elif result["status"] == "BAD":
                        stats["bad"] += 1
                    else:
                        stats["error"] += 1
        
        return results, stats