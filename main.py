import os
import requests
import time
import hashlib
import json
import random
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Carrega variáveis de ambiente
load_dotenv()

class ShopeeAffiliateBot:
    def __init__(self):
        # Carrega e limpa as variáveis
        self.app_key = os.getenv("SHOPEE_APP_KEY", "").strip()
        self.app_secret = os.getenv("SHOPEE_APP_SECRET", "").strip()
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        
        self.shopee_url = "https://open-api.affiliate.shopee.com.br/graphql"
        self.telegram_url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
        
        # Cache para evitar duplicatas (limpa se ficar muito grande)
        self.sent_products = set()

    def _format_price(self, price: float) -> str:
        """Formata para padrão brasileiro"""
        return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _calculate_real_discount(self, p_min: float, p_max: float) -> int:
        """
        Calcula o desconto real baseando-se APENAS nos preços.
        Ignora o campo 'priceDiscountRate' da API que vem errado.
        """
        if p_max > p_min and p_max > 0:
            discount = int(((p_max - p_min) / p_max) * 100)
            # Só considera desconto se for maior que 5%
            return discount if discount >= 5 else 0
        return 0

    def get_products(self, keyword: str = "", sort_type: int = 2, limit: int = 50, page: int = 1):
        """
        Busca produtos com assinatura correta (Payload incluso).
        """
        params = [f'limit: {limit}', f'page: {page}', f'sortType: {sort_type}']
        if keyword:
            params.append(f'keyword: "{keyword}"')

        params_str = ', '.join(params)
        
        query = (
            f"query {{ productOfferV2({params_str}) {{ "
            f"nodes {{ itemId productName imageUrl priceMin priceMax offerLink sales ratingStar }} "
            f"pageInfo {{ hasNextPage }} }} }}"
        )

        # 1. Payload e Assinatura
        payload_dict = {"query": query}
        payload_str = json.dumps(payload_dict, separators=(',', ':'))
        
        timestamp = int(time.time())
        raw_signature = f"{self.app_key}{timestamp}{payload_str}{self.app_secret}"
        signature = hashlib.sha256(raw_signature.encode('utf-8')).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={self.app_key},Timestamp={timestamp},Signature={signature}"
        }

        try:
            print(f"🔎 [{datetime.now().strftime('%H:%M')}] Buscando: '{keyword}' (Pág {page})...")
            response = requests.post(self.shopee_url, headers=headers, data=payload_str, timeout=20)
            response.raise_for_status()
            
            data = response.json()
            if "errors" in data:
                print(f"❌ Erro API: {data['errors'][0]['message']}")
                return []
                
            return data.get("data", {}).get("productOfferV2", {}).get("nodes", [])

        except Exception as e:
            print(f"❌ Erro de conexão: {e}")
            return []

    def send_to_telegram(self, product: Dict) -> bool:
        """Retorna True se enviou com sucesso"""
        title = product.get("productName")
        image_url = product.get("imageUrl")
        link = product.get("offerLink")
        item_id = product.get("itemId")

        # Evita duplicatas
        if item_id in self.sent_products:
            return False

        # Extrai preços
        try:
            price_min = float(product.get("priceMin", 0))
            price_max = float(product.get("priceMax", 0))
        except:
            return False

        if price_min <= 0: return False

        # Dados para Marketing
        discount = self._calculate_real_discount(price_min, price_max)
        price_fmt = self._format_price(price_min)
        sales = product.get("sales", 0)
        rating = float(product.get("ratingStar", 0))

        # --- COPYWRITING MARKETING ---
        
        # 1. Headline baseada em dados
        if sales > 1000:
            header_emoji = "🏆 <b>ITEM VIRAL!</b>"
        elif discount > 40:
            header_emoji = "🚨 <b>SUPER OFERTA!</b>"
        elif rating >= 4.8:
            header_emoji = "⭐ <b>AVALIAÇÃO MÁXIMA!</b>"
        else:
            header_emoji = "🔥 <b>ACHADINHO!</b>"

        caption = f"{header_emoji}\n\n"
        caption += f"📦 <b>{title}</b>\n\n"
        
        if discount > 0:
            caption += f"📉 <b>-{discount}% OFF!</b>\n"
            caption += f"💰 De <s>{self._format_price(price_max)}</s> por <b>{price_fmt}</b>\n"
        else:
            caption += f"💰 Apenas: <b>{price_fmt}</b>\n"

        if sales > 0:
            caption += f"🔥 +{sales} vendidos | ⭐ {rating:.1f}/5.0\n"

        # 2. CTAs Rotativos
        ctas = [
            "👉 <b>COMPRE AQUI:</b>",
            "🏃‍♂️ <b>CORRA ANTES QUE ACABE:</b>",
            "⚡ <b>LINK PROMOCIONAL:</b>",
            "🛒 <b>GARANTA O SEU:</b>"
        ]
        chosen_cta = random.choice(ctas)

        caption += f"\n{chosen_cta} <a href='{link}'>Ver na Shopee</a>"

        payload = {
            "chat_id": self.telegram_chat_id,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }

        try:
            requests.post(self.telegram_url, json=payload)
            print(f"✅ Enviado: {title[:30]}... (R$ {price_min})")
            
            self.sent_products.add(item_id)
            if len(self.sent_products) > 500:
                self.sent_products.clear()
                
            return True
        except Exception as e:
            print(f"❌ Falha no Telegram: {e}")
            return False

    def _is_good_product(self, product: Dict, strict: bool = True) -> bool:
        """
        Valida o produto.
        strict = True -> Modo Elite (Só os melhores)
        strict = False -> Modo Repescagem (Aceita produtos OK para não ficar sem postar)
        """
        try:
            price = float(product.get("priceMin", 0))
            sales = product.get("sales", 0)
            rating = float(product.get("ratingStar", 0))
            
            # --- MODO ELITE (Rigoroso) ---
            if strict:
                if price < 15.00: return False
                if sales < 50: return False # Média de vendas razoável
                if rating < 4.4: return False
                return True
            
            # --- MODO REPESCAGEM (Flexível) ---
            else:
                # Aceita produtos mais baratos se tiverem MUITA venda
                if price >= 10.00 and sales > 200 and rating >= 4.1: return True
                # Ou produtos caros com menos vendas
                if price > 50.00 and rating >= 4.2: return True
                return False
        except:
            return False

    def run_forever(self):
        print("🚀 Bot Shopee: MARKETING MODE ON!")
        
        keywords = [
            # --- TECNOLOGIA & MOBILE ---
            "fone bluetooth original", "fone bluetooth barato", "fone gamer bluetooth",
            "earbuds esportivo", "fone com cancelamento de ruido",
            "smartwatch feminino", "smartwatch masculino", "smartwatch barato",
            "pulseira inteligente", "miband original",
            "carregador rapido", "carregador turbo tipo c",
            "cabo usb c reforçado", "cabo lightning original",
            "power bank 20000mah", "power bank mag safe",
            "suporte celular mesa", "suporte celular veicular",
            "tripé com ring light", "selfie stick bluetooth",
            "caixa de som potente", "caixa de som prova dagua",
            "alexa echo dot 5", "google nest mini",
            
            # --- GAMER & ESCRITÓRIO ---
            "mouse gamer", "teclado mecanico", "headset gamer", "mousepad gigante",
            "cadeira gamer", "mesa digitalizadora", "suporte notebook",
            "webcam", "microfone lapela", "pendrive",
            "mouse gamer rgb", "mouse gamer barato",
            "teclado mecanico rgb", "teclado mecanico 60%",
            "headset gamer com microfone",
            "suporte notebook ajustavel",
            "mesa articulada notebook",
            "webcam full hd",
            "microfone condensador usb",
            "ring light escritorio",
            "mousepad gamer grande",
            "cadeira ergonomica escritorio",
            
            # --- CASA INTELIGENTE & DECORAÇÃO ---
            "lampada smart wifi", "lampada rgb inteligente",
            "fita led quarto", "fita led tv",
            "interruptor wifi alexa",
            "luminaria led escritorio",
            "projetor galaxia", "projetor estrela",
            "umidificador ultrassonico",
            "difusor de aromas eletrico",
            "ventilador silencioso",
            "organizador multiuso",
            "quadro decorativo",
            "placa decorativa",
            "caixa organizadora plastica",
            "prateleira adesiva",
            "gancho adesivo forte",
            
            # --- COZINHA PRÁTICA ---
            "mini processador", "triturador de alho", "mixer portatil",
            "garrafa termica", "copo termico", "caneca stanley",
            "balança digital cozinha", "organizador geladeira", "potes hermeticos",
            "forma airfryer silicone", "afiador de facas", "mop giratorio",
            "airfryer acessorios",
            "forma silicone airfryer",
            "kit utensilios cozinha silicone",
            "triturador eletrico",
            "processador manual",
            "escorredor retratil",
            "organizador de temperos",
            "pote hermetico cozinha",
            "tampa silicone reutilizavel",
            "garrafa termica inox",
            "copo termico com tampa",
            "marmita eletrica",
            
            # --- BELEZA & CUIDADOS PESSOAIS ---
            "secador de cabelo", "escova secadora", "chapinha", "babyliss",
            "maquina de cortar cabelo", "barbeador eletrico", "aparador de pelos",
            "skincare", "serum facial", "protetor solar facial",
            "massageador eletrico", "kit pinceis maquiagem",
            "escova secadora original",
            "secador profissional",
            "chapinha ceramica",
            "babyliss automatico",
            "maquina cortar cabelo profissional",
            "aparador de barba",
            "massageador facial",
            "limpador facial eletrico",
            "kit skincare completo",
            "organizador maquiagem",
            "espelho led maquiagem",
            "kit manicure eletrico",
            
            # --- AUTOMOTIVO & FERRAMENTAS ---
            "aspirador portatil carro", "suporte celular carro", "compressor de ar portatil",
            "multimetro digital", "parafusadeira", "jogo de chaves",
            "aspirador carro potente",
            "compressor ar portatil",
            "calibrador digital pneus",
            "suporte celular painel",
            "camera de re automotiva",
            "carregador veicular turbo",
            "organizador porta malas",
            "capa banco automotivo",
            "tapete carro universal",

            # --- PETS ---
            "bebedouro automatico pet", "comedouro pet inox",
            "escova removedora pelos", "cama pet lavavel",
            "brinquedo interativo cachorro", "coleira peitoral cachorro",
            "areia higienica gato", "caixa transporte pet", "fonte agua gato",

            # --- BEBÊ & INFANTIL ---
            "babá eletrônica", "aspirador nasal bebe",
            "termometro digital bebe", "kit cuidados bebe",
            "organizadores quarto bebe", "tapete infantil educativo",
            "brinquedo educativo montessori", "luz noturna infantil",

            # --- SUPLEMENTOS ---
            "whey protein", "creatina", "pré treino", "bcaa",
            "multivitaminico", "omega 3", "colageno hidrolisado",
            "termogenico", "melatonina",

            # --- ACESSÓRIOS FITNESS & TREINO EM CASA ---
            "luva academia", "cinta abdominal", "faixa elastica fitness",
            "mini band elastico", "corda de pular crossfit",
            "hand grip exercitador", "joelheira esportiva",
            "tapete yoga antiderrapante", "roda abdominal",
            "flexao apoio", "peso russo kettlebell",

            # --- MODA ---
            "camiseta masculina basica", "camiseta oversized",
            "bermuda masculina", "calca jogger masculina",
            "bone masculino", "vestido feminino casual",
            "legging fitness", "top fitness", "bolsa feminina",
            "mochila impermeavel", "relogio masculino",
            
            # --- ACHADINHOS GERAIS ---
            "achadinhos shopee", "ofertas shopee hoje",
            "produtos mais vendidos shopee", "promoção shopee",
            "gadgets virais", "utilidades que facilitam a vida"
        ]
        
        while True:
            try:
                hour = datetime.now().hour
                
                # --- CRONOGRAMA INTELIGENTE 2.0 ---
                
                # PAUSA TOTAL (01h às 06h) - Para não irritar usuários
                if 1 <= hour < 6:
                    print(f"💤 [{hour}h] Modo Dormir Ativado. Pausando por 30 min...")
                    time.sleep(1800) # Dorme 30 minutos e verifica de novo
                    continue
                    
                # START DO DIA (06h às 08h) - Ritmo lento (Café da manhã)
                elif 6 <= hour < 8:
                    mode_name = "🌅 BOM DIA"
                    min_interval, max_interval = 40, 60
                    
                # PICO DO ALMOÇO (11h às 13h) e NOITE (18h às 22h) - Ritmo Turbo
                elif (11 <= hour < 14) or (18 <= hour < 22):
                    mode_name = "🔥 TURBO (ALTA CONVERSÃO)"
                    min_interval, max_interval = 15, 25 
                    
                # RESTO DO DIA - Ritmo Normal
                else:
                    mode_name = "🚶‍♂️ NORMAL"
                    min_interval, max_interval = 30, 45 

                print(f"\n⏰ Horário: {hour}h | Estratégia: {mode_name}")

                # 2. Execução da Busca
                keyword = random.choice(keywords)
                sort_type = 2 # Foco em Vendas
                page = random.randint(1, 2)
                
                products = self.get_products(keyword=keyword, sort_type=sort_type, page=page, limit=50)
                
                # Filtros Híbridos
                valid_products = [p for p in products if self._is_good_product(p, strict=True)]
                if not valid_products:
                    # Se não achou 'elite', tenta repescagem
                    valid_products = [p for p in products if self._is_good_product(p, strict=False)]
                
                if valid_products:
                    random.shuffle(valid_products)
                    chosen = valid_products[0]
                    
                    if self.send_to_telegram(chosen):
                        # Define espera baseada na estratégia do horário
                        wait_minutes = random.randint(min_interval, max_interval)
                        wait_seconds = wait_minutes * 60
                        
                        next_time = datetime.fromtimestamp(datetime.now().timestamp() + wait_seconds).strftime('%H:%M')
                        print(f"✅ Próximo post em {wait_minutes} min ({next_time})")
                        time.sleep(wait_seconds)
                    else:
                        print("⚠️ Erro envio (Telegram). Retentando em 30s...")
                        time.sleep(30)
                else:
                    print("🧹 Nenhum produto bom. Trocando keyword...")
                    time.sleep(5)

            except Exception as e:
                print(f"❌ Erro Crítico no Loop: {e}")
                time.sleep(60)

# --- SERVIDOR WEB FALSO (PARA RENDER) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot Online e Rodando!"

def run_http():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_http)
    t.start()

# --- EXECUÇÃO FINAL ---
if __name__ == "__main__":
    keep_alive() # Inicia o servidor web em segundo plano
    bot = ShopeeAffiliateBot()
    bot.run_forever()