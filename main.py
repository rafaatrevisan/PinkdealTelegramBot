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

        # --- COPYWRITING DINÂMICA E ALEATÓRIA ---
        
        # 1. Definindo as categorias de headline baseadas nos dados
        header_options = []

        # CENÁRIO A: Super Desconto (> 50%) - URGÊNCIA MÁXIMA
        if discount >= 50:
            header_options = [
                f"🚨 <b>ERRO DE PREÇO? -{discount}% OFF!</b>",
                f"📉 <b>QUEIMA DE ESTOQUE: -{discount}%!</b>",
                f"😱 <b>METADE DO PREÇO (OU MENOS)!</b>",
                f"💸 <b>DESCONTO INSANO DETECTADO!</b>"
            ]
        
        # CENÁRIO B: Produto Viral (> 2.000 vendas) - PROVA SOCIAL
        elif sales >= 2000:
            header_options = [
                "🏆 <b>O QUERIDINHO DA SHOPEE!</b>",
                "🔥 <b>ITEM VIRAL: TODO MUNDO TÁ COMPRANDO!</b>",
                "📦 <b>ESTOQUE VOANDO (MAIS DE 2MIL VENDAS)!</b>",
                "👀 <b>VOCÊ PRECISA VER ISSO!</b>"
            ]

        # CENÁRIO C: Avaliação Perfeita (> 4.9) - QUALIDADE
        elif rating >= 4.9:
            header_options = [
                "⭐ <b>SATISFAÇÃO GARANTIDA (NOTA 5.0)!</b>",
                "💎 <b>QUALIDADE PREMIUM APROVADA!</b>",
                "✨ <b>ZERO DEFEITOS: AVALIAÇÃO MÁXIMA!</b>",
                "🏅 <b>O MELHOR DA CATEGORIA!</b>"
            ]

        # CENÁRIO D: Preço Baixo (< R$ 20) - IMPULSO BARATO
        elif price_min < 20.00:
            header_options = [
                "🤑 <b>PRECINHO DE PINGA!</b>",
                "🤏 <b>CUSTA MENOS DE 20 REAIS!</b>",
                "👛 <b>BARATINHO DO DIA!</b>",
                "⚡ <b>OFERTA RELÂMPAGO!</b>"
            ]
        
        # CENÁRIO E: Padrão (Achadinhos Bons)
        else:
            header_options = [
                "🔥 <b>ACHADINHO SHOPEE!</b>",
                "🛒 <b>VALE A PENA CONFERIR!</b>",
                "🔎 <b>GARIMPADO PRA VOCÊ!</b>",
                "💡 <b>OLHA O QUE EU ACHEI!</b>"
            ]

        # Escolhe uma frase aleatória da lista selecionada
        header_emoji = random.choice(header_options)

        # 2. Monta a Legenda
        caption = f"{header_emoji}\n\n"
        caption += f"📦 <b>{title}</b>\n\n"
        
        if discount > 0:
            caption += f"📉 <b>-{discount}% OFF!</b>\n"
            caption += f"💰 De <s>{self._format_price(price_max)}</s> por <b>{price_fmt}</b>\n"
        else:
            caption += f"💰 Apenas: <b>{price_fmt}</b>\n"

        # Formata o número de vendas para ficar bonito (ex: 1.2k)
        sales_fmt = f"{sales/1000:.1f}k" if sales >= 1000 else sales
        
        if sales > 0:
            caption += f"🔥 +{sales_fmt} vendidos | ⭐ {rating:.1f}/5.0\n"

        # 3. CTAs Rotativos (Call to Action)
        ctas = [
            "👉 <b>COMPRE AQUI:</b>",
            "🏃‍♂️ <b>CORRA ANTES QUE ACABE:</b>",
            "⚡ <b>LINK PROMOCIONAL:</b>",
            "🛒 <b>GARANTA O SEU:</b>",
            "🔓 <b>VER PREÇO ATUALIZADO:</b>"
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
        try:
            price = float(product.get("priceMin", 0))
            sales = product.get("sales", 0)
            rating = float(product.get("ratingStar", 0))
            title = product.get("productName", "").lower()
            
            # --- 1. LISTA NEGRA ---
            # Produtos que vendem muito mas ninguém clica por impulso
            bad_words = [
                "capa", "capinha", "case", "película", "pelicula", "vidro 3d", "vidro 9d",
                "adaptador", "cabo usb", "cabo de dados", "cordão", "suporte simples",
                "pezinho", "parafuso", "borracha", "adesivo", "sticker", "refil",
                "bateria", "pilha", "plug", "tomada", "extensão"
            ]
            
            # Se tiver qualquer palavra proibida no título, descarta IMEDIATAMENTE
            # (Exceto se custar mais de R$ 50,00, aí pode ser uma capa premium ou cabo de luxo)
            if price < 50.00:
                if any(bad in title for bad in bad_words):
                    return False

            # --- 2. FILTRO DE PREÇO (Ticket de Impulso) ---
            if price < 20.00: return False

            # --- 3. RATING DINÂMICO ---
            # Se for "barato" (25 a 60), tem que ser INCRÍVEL (Nota > 4.7)
            if 25.00 <= price <= 60.00:
                if rating < 4.7: return False
                if sales < 200: return False # Tem que ter muita prova social
            
            # Se for "caro" (> 60), aceitamos nota normal (4.5) pois tem menos reviews
            else:
                if rating < 4.5: return False
                if sales < 50: return False

            return True

        except:
            return False

    def run_forever(self):
        print("🚀 Bot Shopee: MARKETING MODE ON!")
        
        keywords = [
            # --- ELETRÔNICOS & TECH VIRAIS ---
            "Lenovo GM2 Pro", "Lenovo LP40", "Fone Bluetooth Baseus", "QCY T13", 
            "Redmi Buds 4", "JBL Go 3", "Caixa de Som Tronsmart", "Soundbar TV",
            "Smartwatch Haylou", "Amazfit Bip", "Mi Band 8", "Smartwatch Colmi",
            "Alexa Echo Dot", "Fire TV Stick", "Google Chromecast", "Roku Express",
            "Kindle 11", "Tablet Samsung A9", "Tablet Xiaomi",
            "Carregador Baseus 20W", "Power Bank Baseus", "Carregador Portátil Pineng",
            "Estabilizador Celular", "Gimbal", "Microfone Lapela Sem Fio",
            "Ring Light Profissional", "Tripé Flexivel", "Suporte Celular Mesa",

            # --- GAMER & SETUP (Alta Margem) ---
            "Teclado Mecanico Redragon", "Teclado Machenike", "Mouse Logitech Gamer", "Mouse Attack Shark",
            "Mousepad Gamer 90x40", "Mousepad RGB", "Headset Havit", "Headset HyperX",
            "Controle 8BitDo", "Controle PS4 Sem Fio", "Controle Xbox Wireless",
            "Microfone Fifine", "Microfone HyperX Solocast", "Braço Articulado Microfone",
            "Fita LED Neon", "Barra de Luz Monitor", "Luminária Pixel", "Cadeira Gamer",
            "Cooler Celular", "Luva de Dedo Gamer", "Switch HDMI", "Monitor Gamer", "Monitor LG Ultragear", 
            "Suporte Monitor", "Monitor Ultrawide", "Webcam 1080p",

            # --- CASA, COZINHA & ORGANIZAÇÃO (Ouro das Donas de Casa) ---
            "Mini Processador Elétrico", "Copo Stanley", "Garrafa Térmica Pacco",
            "Mop Giratório Flash Limp", "Robô Aspirador", "Aspirador Vertical",
            "Umidificador Chama", "Umidificador Anti Gravidade", "Difusor Óleos Essenciais",
            "Projetor Hy300", "Luminária", "Despertador Digital Led",
            "Mixer Portátil", "Seladora de Embalagem", "Dispensador Pasta Dente",
            "Organizador de Cabos", "Organizador Geladeira Acrilico", "Potes Herméticos",
            "Forma Airfryer Silicone", "Tapete Super Absorvente", "Cabides Veludo",
            "Sapateira Organizadora", "Escorredor Louça Dobravel", "Triturador Alho Manual",

            # --- FITNESS & SUPLEMENTOS (Recorrência Alta) ---
            "Creatina Monohidratada", "Creatina Max Titanium", "Creatina Soldiers",
            "Whey Protein Concentrado", "Whey Growth", "Whey Max Titanium",
            "Pré Treino Haze", "Pasta de Amendoim Integral", "Barra de Proteína",
            "Coqueteleira Inox", "Strap Musculação", "Hand Grip Ajustavel",
            "Corda de Pular Rolamento", "Elásticos Extensores Treino", "Kit Band Faixa",
            "Tapete Yoga Antiderrapante", "Roda Abdominal", "Balança Bioimpedância",
            "Garrafa Galão 2L", "Luva Academia",

            # --- SKINCARE & MAQUIAGEM (Marcas Shopee Friendly) ---
            "Serum Principia", "Sabonete Principia", "Creamy Skincare",
            "Protetor Solar Bioré", "Protetor Solar Neostrata", "Gel Limpeza CeraVe",
            "Hidratante CeraVe", "Cicaplast Baume", "Oleo de Rosa Mosqueta",
            "Ruby Rose Melu", "Gloss Labial Volumoso", "Lip Tint",
            "Pó Solto Boca Rosa", "Corretivo Fran", "Paleta Sombras Océane",
            "Esponja Maquiagem Mari Saad", "Pincel Maquiagem Kit", 
            "Escova Limpeza Facial Elétrica", "Espelho Led Maquiagem",
            
            # --- MODA & ACESSÓRIOS (Ticket Médio/Baixo) ---
            "Camiseta Oversized Masculina", "Camiseta Dry Fit", "Shorts Tactel Masculino", "Calça Jogger Masculina",
            "Mochila Impermeavel Notebook", "Bolsa Transversal Feminina", "Shoulder Bag",
            "Vestido Canelado", "Conjunto Alfaiataria Feminino", "Conjunto Alfaiataria Masculino", "Calça Wide Leg",
            "Legging Fitness Cintura Alta", "Top Fitness Sustentação", "Shorts Saia Academia",
            "Meias Nike", "Carteira Masculina Couro", "Cinto Couro Masculino", "Relógio Feminino Minimalista",

            # --- PETS (Público Apaixonado) ---
            "Fonte Bebedouro Gato", "Fonte Gato Inox", "Comedouro Elevado",
            "Arranhador Gato Torre", "Arranhador Papelão", "Cama Nuvem Pet",
            "Tapete Higiênico Lavavel", "Guia Retrátil Cachorro", "Peitoral Antipuxão",
            "Brinquedo Kong", "Churu Gato", "Escova Removedora Pelos Pet",
            "Luva Tira Pelos", "Cortador Unha Pet",

            # --- FERRAMENTAS & AUTOMOTIVO (Público Masculino) ---
            # "Parafusadeira Bateria", "Jogo Chaves Catraca", "Maleta Ferramentas",
            # "Multimetro Digital", "Trena Laser", "Nivel a Laser",
            # "Aspirador Portátil Carro", "Compressor Ar Portátil", "Auxiliar Partida",
            # "Suporte Celular Carro Magnético", "Capa Chave Canivete", "Som Automotivo Bluetooth"

            # --- SAZONALIDADE ---
            # "ovo de pascoa", "barra de chocolate", "forma de ovo de pascoa", # PÁSCOA
            # "kit dia das maes", "perfume feminino importado", "bolsa feminina luxo", # DIA DAS MÃES
            # "camisa time brasil", "bandeira do brasil", "corneta", # COPA/OLIMPÍADAS
            # "decoração de natal", "arvore de natal", "pisca pisca led", # NATAL
            "material escolar", "mochila escolar", "caderno inteligente", # VOLTA ÀS AULAS (JANEIRO)
            "ventilador de teto", "ar condicionado portatil", "climatizador", # VERÃO FORTE
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
                    min_interval, max_interval = 60, 90
                    
                # PICO DO ALMOÇO (11h às 13h) e NOITE (18h às 22h) - Ritmo Turbo
                elif (11 <= hour < 14) or (18 <= hour < 22):
                    mode_name = "🔥 TURBO (ALTA CONVERSÃO)"
                    min_interval, max_interval = 25, 35
                    
                # RESTO DO DIA - Ritmo Normal
                else:
                    mode_name = "🚶‍♂️ NORMAL"
                    min_interval, max_interval = 50, 60

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