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

    def get_products(self, keyword: str = "", sort_type: int = 2, limit: int = 10, page: int = 1):
        """
        Busca produtos.
        sort_type: 2 = Mais Vendidos, 5 = Maior Comissão
        """
        
        # Monta os parâmetros dinamicamente
        params = [f'limit: {limit}', f'page: {page}', f'sortType: {sort_type}']
        if keyword:
            params.append(f'keyword: "{keyword}"')

        params_str = ', '.join(params)
        
        query = (
            f"query {{ productOfferV2({params_str}) {{ "
            f"nodes {{ itemId productName imageUrl priceMin priceMax offerLink sales }} "
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
            print(f"🔎 Buscando na pág {page} (Tipo: {sort_type}, Keyword: '{keyword}')...")
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

        # Lógica de Desconto Corrigida
        discount = self._calculate_real_discount(price_min, price_max)
        price_fmt = self._format_price(price_min)

        # Monta Legenda
        caption = f"🔥 <b>{title}</b>\n\n"
        
        if discount > 0:
            caption += f"📉 <b>-{discount}% OFF!</b>\n"
            caption += f"💰 De <s>{self._format_price(price_max)}</s> por <b>{price_fmt}</b>\n"
        else:
            caption += f"💰 Apenas: <b>{price_fmt}</b>\n"

        sales = product.get("sales", 0)
        if sales > 0:
            caption += f"📦 +{sales} vendidos\n"

        caption += f"\n👉 <b>COMPRE AQUI:</b> <a href='{link}'>Ver na Shopee</a>"

        payload = {
            "chat_id": self.telegram_chat_id,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }

        try:
            requests.post(self.telegram_url, json=payload)
            print(f"✅ Enviado: {title[:40]}...")
            self.sent_products.add(item_id)
            
            # Limpa cache se ficar muito grande (500 itens)
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
                # Preço > R$ 15
                if price < 15.00: return False
                # Vendas > 100
                if sales < 100: return False
                # Nota > 4.5
                if rating < 4.5: return False
                return True
            
            # --- MODO REPESCAGEM (Flexível) ---
            else:
                # Aceita produtos mais baratos se tiverem MUITA venda
                if price >= 10.00 and sales > 100 and rating >= 4.0:
                    return True
                # Ou produtos caros com menos vendas
                if price > 50.00 and rating >= 4.0:
                    return True
                
                return False
        except:
            return False

    def get_products(self, keyword: str = "", sort_type: int = 2, limit: int = 50, page: int = 1):
        # ... (O código desta função permanece igual, apenas mude o padrão limit=50)
        # ... Certifique-se de que a query use esse 'limit'
        params = [f'limit: {limit}', f'page: {page}', f'sortType: {sort_type}']
        if keyword: params.append(f'keyword: "{keyword}"')
        params_str = ', '.join(params)
        
        query = (
            f"query {{ productOfferV2({params_str}) {{ "
            f"nodes {{ itemId productName imageUrl priceMin priceMax offerLink sales ratingStar }} "
            f"pageInfo {{ hasNextPage }} }} }}"
        )
        # ... (Resto da função de request e assinatura igual ao anterior) ...
        # (Vou omitir aqui para economizar espaço, mas use a mesma lógica de assinatura do código anterior)
        # Apenas lembre de copiar o bloco payload/assinatura/request aqui dentro.
        
        # --- CÓDIGO DO GET_PRODUCTS (RESUMIDO PARA CONTEXTO) ---
        payload_dict = {"query": query}
        payload_str = json.dumps(payload_dict, separators=(',', ':'))
        timestamp = int(time.time())
        raw_signature = f"{self.app_key}{timestamp}{payload_str}{self.app_secret}"
        signature = hashlib.sha256(raw_signature.encode('utf-8')).hexdigest()
        headers = {"Content-Type": "application/json", "Authorization": f"SHA256 Credential={self.app_key},Timestamp={timestamp},Signature={signature}"}
        try:
            response = requests.post(self.shopee_url, headers=headers, data=payload_str, timeout=20)
            data = response.json()
            return data.get("data", {}).get("productOfferV2", {}).get("nodes", [])
        except: return []

    def run_forever(self):
        print("🚀 Bot Shopee: Iniciado com CRONOGRAMA INTELIGENTE!")
        
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
            "alexa echo dot 5", "google nest mini"
            
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
            "cadeira ergonomica escritorio"
            
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
            "gancho adesivo forte"
            
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
            "marmita eletrica"
            
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
            "kit manicure eletrico"
            
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
            "tapete carro universal"

            # --- PETS ---
            "bebedouro automatico pet",
            "comedouro pet inox",
            "escova removedora pelos",
            "cama pet lavavel",
            "brinquedo interativo cachorro",
            "coleira peitoral cachorro",
            "areia higienica gato",
            "caixa transporte pet",
            "fonte agua gato"

            # --- BEBÊ & INFANTIL ---
            "babá eletrônica",
            "aspirador nasal bebe",
            "termometro digital bebe",
            "kit cuidados bebe",
            "organizadores quarto bebe",
            "tapete infantil educativo",
            "brinquedo educativo montessori",
            "luz noturna infantil"

            # --- SUPLEMENTOS ---
            "whey protein",
            "whey protein concentrado",
            "whey protein 1kg",
            "whey protein chocolate",
            "creatina",
            "creatina monohidratada",
            "creatina pura",
            "creatina em pó",
            "pré treino",
            "pre treino sem cafeina",
            "pre treino importado",
            "bcaa",
            "glutamina",
            "hipercalorico",
            "multivitaminico",
            "omega 3",
            "colageno hidrolisado",
            "termogenico",
            "capsulas cafeina",
            "vitamina d3",
            "vitamina c",
            "melatonina",
            "zma suplemento",

            # --- ACESSÓRIOS FITNESS ---
            "luva academia",
            "cinta lombar treino",
            "cinta abdominal",
            "faixa elastica fitness",
            "mini band elastico",
            "corda de pular crossfit",
            "hand grip exercitador",
            "strap musculacao",
            "joelheira esportiva",
            "tornozeleira com peso",
            "halter ajustavel",
            "barra musculacao",
            "tapete yoga antiderrapante",

            # --- TREINO EM CASA ---
            "kit treino em casa",
            "academia em casa",
            "roda abdominal",
            "abdominal roller",
            "flexao apoio",
            "step aerobico",
            "peso russo kettlebell",
            "elastico pilates",

            # --- RECUPERAÇÃO & BEM-ESTAR ---
            "massageador muscular",
            "pistola massageadora",
            "bola massageadora",
            "faixa compressao",
            "meia compressao",
            "corretor postura",
            "suporte lombar",
            "alongador coluna"

            # --- MODA MASCULINA ---
            "camiseta masculina basica",
            "camiseta oversized",
            "camisa dry fit masculina",
            "camiseta academia masculina",
            "bermuda masculina",
            "bermuda tactel",
            "short treino masculino",
            "calca jogger masculina",
            "moletom masculino",
            "jaqueta corta vento",
            "cueca boxer algodao",
            "kit cueca masculina",
            "meias masculinas kit",
            "bone masculino",
            "bone aba curva"

            # --- MODA FEMININA ---
            "vestido feminino casual",
            "vestido canelado",
            "vestido midi",
            "conjunto feminino",
            "conjunto academia feminino",
            "legging fitness",
            "legging cintura alta",
            "top fitness",
            "cropped feminino",
            "camiseta feminina basica",
            "blusa feminina",
            "short saia",
            "pijama feminino",
            "lingerie feminina",
            "kit calcinha"

            # --- ACESSÓRIOS ---
            "bolsa feminina",
            "bolsa transversal",
            "mochila feminina",
            "mochila masculina",
            "carteira masculina",
            "carteira feminina",
            "cinto masculino",
            "oculos de sol",
            "oculos polarizado",
            "relogio masculino",
            "relogio feminino",
            "pulseira masculina",
            "colar feminino",
            "anel masculino",
            "brincos femininos",
            "kit bijuterias"
            "mochila notebook",
            "mochila impermeavel",
            "bolsa academia",
            "bolsa viagem",
            "bolsa termica fitness",
            "pochete masculina",
            "pochete feminina",
            "shoulder bag"

            # --- ACHADINHOS GERAIS (Surpresa) ---
            "achadinhos shopee",
            "ofertas shopee hoje",
            "produtos mais vendidos shopee",
            "promoção shopee",
            "top shopee",
            "gadgets virais",
            "utilidades que facilitam a vida",
            "produtos virais tiktok"
        ]
        
        while True:
            try:
                # 1. Identifica a Hora Atual para definir a estratégia
                hour = datetime.now().hour
                
                # --- LÓGICA DE HORÁRIOS ---
                
                # MADRUGADA (23h às 07h) -> Modo Silencioso
                if 23 <= hour or hour < 7:
                    mode_name = "🌙 MODO NOTURNO"
                    min_interval, max_interval = 120, 180 # 2h a 3h entre posts
                    
                # PICO DO ALMOÇO (11h às 14h) ou NOITE (18h às 22h) -> Modo Turbo
                elif (11 <= hour < 14) or (18 <= hour < 22):
                    mode_name = "🔥 MODO TURBO (PICO)"
                    min_interval, max_interval = 15, 25 # 15 a 25 min entre posts
                    
                # HORÁRIO COMERCIAL (07h-11h e 14h-18h) -> Modo Normal
                else:
                    mode_name = "🚶‍♂️ MODO NORMAL"
                    min_interval, max_interval = 35, 55 # 35 a 55 min entre posts

                print(f"\n⏰ Horário: {hour}h | Estratégia: {mode_name}")

                # 2. Execução da Busca e Envio
                keyword = random.choice(keywords)
                sort_type = 2 # Foco em Vendas
                page = random.randint(1, 2)
                
                print(f"🔎 Buscando ofertas de: '{keyword}'...")
                products = self.get_products(keyword=keyword, sort_type=sort_type, page=page, limit=50)
                
                # Filtros
                valid_products = [p for p in products if self._is_good_product(p, strict=True)]
                if not valid_products:
                    valid_products = [p for p in products if self._is_good_product(p, strict=False)]
                
                if valid_products:
                    random.shuffle(valid_products)
                    chosen = valid_products[0]
                    
                    if self.send_to_telegram(chosen):
                        # Se enviou, aplica o intervalo da estratégia atual
                        wait_minutes = random.randint(min_interval, max_interval)
                        wait_seconds = wait_minutes * 60
                        
                        next_time = datetime.fromtimestamp(datetime.now().timestamp() + wait_seconds).strftime('%H:%M')
                        print(f"✅ Postado! Próximo envio em {wait_minutes} min (às {next_time})")
                        time.sleep(wait_seconds)
                    else:
                        print("⚠️ Erro no envio Telegram. Retentando em 1 min...")
                        time.sleep(60)
                else:
                    print("🧹 Nenhum produto bom encontrado. Tentando outra keyword em 10s...")
                    time.sleep(10)

            except KeyboardInterrupt:
                print("\n🛑 Bot parado.")
                break
            except Exception as e:
                print(f"❌ Erro: {e}")
                time.sleep(60)

# --- EXECUÇÃO ---
app = Flask('')

@app.route('/')
def home():
    return "Estou vivo!"

def run_http():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_http)
    t.start()

if __name__ == "__main__":
    keep_alive() # <--- Inicia o servidor web falso
    bot = ShopeeAffiliateBot()
    bot.run_forever()