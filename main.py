import os
import requests
import time
import hashlib
import json
import random
import html
import re
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

from google import genai
from google.genai import types

# Carrega variáveis de ambiente
load_dotenv()

class ShopeeAffiliateBot:
    def __init__(self):
        # Credenciais
        self.app_key = os.getenv("SHOPEE_APP_KEY", "").strip()
        self.app_secret = os.getenv("SHOPEE_APP_SECRET", "").strip()
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        
        self.shopee_url = "https://open-api.affiliate.shopee.com.br/graphql"
        self.telegram_url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
        
        self.sent_products = set()

        # --- CONFIGURAÇÃO DA IA ---
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.client = None
        self.model_id = "gemini-2.0-flash" 

        if self.gemini_key:
            try:
                self.client = genai.Client(api_key=self.gemini_key)
                print("🤖 IA Cliente Inicializado (Nova Lib google-genai)")
            except Exception as e:
                print(f"⚠️ Erro ao criar cliente IA: {e}")

    def _call_ai_with_retry(self, prompt: str, max_tokens: int = 50, temperature: float = 0.2) -> Optional[str]:
        """
        Tenta chamar a IA. Se der erro 429, espera e tenta de novo (até 3x).
        """
        if not self.client: return None

        max_retries = 3
        base_delay = 5

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=max_tokens, 
                        temperature=temperature
                    )
                )
                return response.text.strip()

            except Exception as e:
                error_msg = str(e)
                # Se for erro de cota/limite (429), tenta de novo
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait_time = base_delay * (attempt + 1) # 5s, depois 10s, depois 15s
                    print(f"⚠️ IA Congestionada (429). Tentativa {attempt+1}/{max_retries}. Esperando {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # Se for outro erro (ex: 400, 500), imprime e desiste logo
                    print(f"⚠️ Erro IA Irrecuperável: {e}")
                    return None
        
        print("❌ IA falhou após 3 tentativas.")
        return None

    def _format_price(self, price: float) -> str:
        return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _calculate_real_discount(self, p_min: float, p_max: float) -> int:
        if p_max > p_min and p_max > 0:
            discount = int(((p_max - p_min) / p_max) * 100)
            return discount if discount >= 5 else 0
        return 0

    def get_products(self, keyword: str = "", sort_type: int = 2, limit: int = 50, page: int = 1):
        params = [f'limit: {limit}', f'page: {page}', f'sortType: {sort_type}']
        if keyword: params.append(f'keyword: "{keyword}"')
        params_str = ', '.join(params)
        
        query = (
            f"query {{ productOfferV2({params_str}) {{ "
            f"nodes {{ itemId productName imageUrl priceMin priceMax offerLink sales ratingStar }} "
            f"pageInfo {{ hasNextPage }} }} }}"
        )

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
            response = requests.post(self.shopee_url, headers=headers, data=payload_str, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("productOfferV2", {}).get("nodes", [])
        except Exception as e:
            print(f"❌ Erro Shopee: {e}")
            return []

    def _ai_polisher(self, raw_title: str, price: float) -> str:
        """Reescreve o título (Usa o sistema de Retry)"""
        prompt = f"""
        Aja como um Copywriter especialista em Telegram.
        Reescreva o título deste produto da Shopee para torná-lo curto, elegante, desejável e com alto potencial de clique.

        Título Original: "{raw_title}"
        Preço: R$ {price}

        Regras:
        1. Remova termos de SEO e spam (ex: pronta entrega, envio já, original, lançamento, 2024).
        2. Mantenha o nome do produto + 1 benefício ou característica desejável.
        3. Adicione EXATAMENTE 1 emoji relevante no início, e de preferência que tenha sentido com o produto (caso não tenha, coloque algum mais genérico).
        4. Máximo de 8 palavras.
        5. Linguagem simples, natural e comercial.
        6. NÃO use aspas, símbolos extras ou emojis no meio do texto.
        
        Exemplos: 
        "🎧 Fone Lenovo LP40 Pro: Som Imersivo"
        "👗 Vestido Alcinha Costas Abertas"

        Sua versão:
        """
        
        # Chama a função blindada
        new_title = self._call_ai_with_retry(prompt, max_tokens=30, temperature=0.3)
        
        if new_title:
            new_title = new_title.replace('"', '')
            print(f"✨ Título Polido: {new_title}")
            return new_title
        else:
            # Se falhou 3x, usa o original
            print("⚠️ Falha no polimento. Usando título original.")
            return raw_title

    def send_to_telegram(self, product: Dict) -> bool:
        raw_title = product.get("productName")
        image_url = product.get("imageUrl")
        link = product.get("offerLink")
        item_id = product.get("itemId")

        if item_id in self.sent_products: return False

        try:
            price_min = float(product.get("priceMin", 0))
            price_max = float(product.get("priceMax", 0))
        except: return False

        # --- APLICANDO O POLIDOR ---
        final_title = self._ai_polisher(raw_title, price_min)
        final_title = html.escape(final_title) 

        discount = self._calculate_real_discount(price_min, price_max)
        price_fmt = self._format_price(price_min)
        sales = product.get("sales", 0)
        rating = float(product.get("ratingStar", 0))

        # Copywriting Dinâmica
        header_options = []

        # CENÁRIO A: Super Desconto (>= 50%)
        if discount >= 50:
            header_options = [
                f"🚨 <b>ERRO DE PREÇO? -{discount}% OFF!</b>",
                f"📉 <b>QUEIMA DE ESTOQUE: -{discount}%!</b>",
                f"😱 <b>METADE DO PREÇO (OU MENOS)!</b>",
                f"💸 <b>DESCONTO INSANO DETECTADO!</b>",
                f"🔥 <b>PREÇO DE BLACK FRIDAY!</b>",
                f"🏃‍♂️ <b>CORRE ANTES QUE O VENDEDOR MUDE!</b>",
                f"🤯 <b>ISSO NÃO É UM TREINAMENTO: -{discount}%!</b>",
                f"🏷️ <b>A ETIQUETA FICOU LOUCA!</b>",
                f"⚡ <b>OPORTUNIDADE ÚNICA DO MÊS!</b>",
                f"💣 <b>EXPLOSÃO DE OFERTA!</b>"
            ]
        
        # CENÁRIO B: Produto Viral (>= 2.000 vendas)
        elif sales >= 2000:
            header_options = [
                "🏆 <b>O QUERIDINHO DA SHOPEE!</b>",
                "🔥 <b>ITEM VIRAL: TODO MUNDO TÁ COMPRANDO!</b>",
                "📦 <b>ESTOQUE VOANDO (MAIS DE 2MIL VENDAS)!</b>",
                "👀 <b>VOCÊ PRECISA VER ISSO!</b>",
                "🚀 <b>O MAIS VENDIDO DA SEMANA!</b>",
                "📢 <b>O BRASIL INTEIRO TÁ USANDO!</b>",
                "👑 <b>O REI DA CATEGORIA!</b>",
                "🛒 <b>CHUVA DE PEDIDOS NESSE LINK!</b>",
                "✨ <b>TENDÊNCIA CONFIRMADA!</b>",
                "📢 <b>SUCESSO ABSOLUTO DE VENDAS!</b>"
            ]

        # CENÁRIO C: Avaliação Perfeita (>= 4.9)
        elif rating >= 4.9:
            header_options = [
                "⭐ <b>NOTA MÁXIMA (5.0)!</b>",
                "💎 <b>QUALIDADE PREMIUM APROVADA!</b>",
                "✨ <b>ZERO DEFEITOS: AVALIAÇÃO MÁXIMA!</b>",
                "🏅 <b>O MELHOR DA CATEGORIA!</b>",
                "🛡️ <b>COMPRA 100% SEGURA (NOTA ALTA)!</b>",
                "✅ <b>QUEM COMPROU, AMOU!</b>",
                "🌟 <b>CLIENTES SATISFEITOS NÃO MENTEM!</b>",
                "🥇 <b>TOP DE LINHA: 5 ESTRELAS!</b>",
                "💖 <b>SATISFAÇÃO GARANTIDA!</b>",
                "🎯 <b>NÃO TEM COMO ERRAR NESSA!</b>"
            ]

        # CENÁRIO D: Preço Baixo (< R$ 20)
        elif price_min < 20.00:
            header_options = [
                "🤑 <b>PRECINHO DE PINGA!</b>",
                "🤏 <b>CUSTA MENOS DE 20 REAIS!</b>",
                "👛 <b>BARATINHO DO DIA!</b>",
                "⚡ <b>OFERTA RELÂMPAGO!</b>",
                "🍬 <b>PREÇO DE BALA!</b>",
                "🛑 <b>MAIS BARATO QUE COXINHA!</b>",
                "🤯 <b>QUASE DE GRAÇA!</b>",
                "🎩 <b>MÁGICA? NÃO, É BARATO MESMO!</b>",
                "🧸 <b>PECHINCHA ABSOLUTA!</b>",
                "🎫 <b>PREÇO DE CUSTO!</b>"
            ]
        
        # CENÁRIO E: Padrão (Achadinhos Bons)
        else:
            header_options = [
                "🔥 <b>ACHADINHO SHOPEE!</b>",
                "🛒 <b>VALE A PENA CONFERIR!</b>",
                "🔎 <b>GARIMPADO PRA VOCÊ!</b>",
                "💡 <b>OLHA O QUE EU ACHEI!</b>",
                "👀 <b>DICA DO DIA!</b>",
                "🛍️ <b>SELEÇÃO ESPECIAL!</b>",
                "🕹️ <b>GAME OVER: ACHEI O MELHOR!</b>",
                "🛸 <b>ACHADO DE OUTRO MUNDO!</b>",
                "🎁 <b>PRESENTE PRO SEU BOLSO!</b>",
                "🔔 <b>RADAR DE OFERTAS ATIVADO!</b>"
            ]

        header_emoji = random.choice(header_options)
        caption = f"{header_emoji}\n\n<b>{final_title}</b>\n\n"
        
        if discount > 0:
            caption += f"📉 <b>-{discount}% OFF!</b>\n💰 De <s>{self._format_price(price_max)}</s> por <b>{price_fmt}</b>\n"
        else:
            caption += f"💰 Apenas: <b>{price_fmt}</b>\n"

        sales_fmt = f"{sales/1000:.1f}k" if sales >= 1000 else sales
        if sales > 0:
            caption += f"🔥 +{sales_fmt} vendidos | ⭐ {rating:.1f}/5.0\n"

        ctas = [
            "👉 <b>COMPRE AQUI:</b>", "🏃‍♂️ <b>CORRA ANTES QUE ACABE:</b>", "⚡ <b>LINK PROMOCIONAL:</b>",
            "🛒 <b>GARANTA O SEU:</b>", "🔓 <b>VER PREÇO ATUALIZADO:</b>", "🔥 <b>APROVEITAR OFERTA:</b>"
        ]
        chosen_cta = random.choice(ctas)
        caption += f"\n{chosen_cta} <a href='{link}'>Ver na Shopee</a>"

        payload = {"chat_id": self.telegram_chat_id, "photo": image_url, "caption": caption, "parse_mode": "HTML"}

        try:
            requests.post(self.telegram_url, json=payload, timeout=30)
            print(f"✅ Enviado: {final_title} (R$ {price_min})")
            self.sent_products.add(item_id)
            if len(self.sent_products) > 500: self.sent_products.clear()
            return True
        except Exception as e:
            print(f"❌ Erro Telegram: {e}")
            return False

    def _math_filter(self, product: Dict, strict: bool = True) -> bool:
        try:
            price = float(product.get("priceMin", 0))
            sales = product.get("sales", 0)
            rating = float(product.get("ratingStar", 0))
            title = product.get("productName", "").lower()
            
            bad_words = ["capa", "capinha", "case", "película", "vidro 3d", "adaptador", "cabo usb", "parafuso", "adesivo", "bateria"]
            if price < 50.00 and any(bad in title for bad in bad_words): return False
            if price < 20.00: return False

            if strict:
                if 20.00 <= price <= 60.00: return rating >= 4.7 and sales >= 100
                else: return rating >= 4.5 and sales >= 50
            else:
                return sales >= 200 and rating >= 4.3
        except: return False

    def _ai_batch_selector(self, candidates: List[Dict]) -> Optional[Dict]:
        """IA: Escolhe o vencedor (Usa o sistema de Retry)"""
        if not candidates: return None

        list_text = ""
        id_map = {}
        for idx, p in enumerate(candidates):
            p_min = float(p.get("priceMin", 0))
            rating = float(p.get("ratingStar", 0))
            sales = p.get("sales", 0)
            list_text += f"[{idx}] {p.get('productName')} | R$ {p_min} | Nota: {rating} | Vendas: {sales}\n"
            id_map[str(idx)] = p

        prompt = f"""
        Atue como um Curador SÊNIOR de Ofertas e Especialista em Psicologia do Consumidor.
        Você gerencia um canal VIP no Telegram e seu objetivo é escolher o ÚNICO produto da lista abaixo com maior potencial VIRAL e de COMPRA POR IMPULSO.

        Analise os candidatos com rigor. Buscamos o "Efeito Uau", algo que desperte aquele desejo de compra impulsiva, não apenas utilidade.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━
        🏆 CRITÉRIOS PARA O VENCEDOR (O QUE BUSCAMOS):
        1. O TESTE DOS 2 SEGUNDOS: O produto é desejável visualmente ou resolve uma dor óbvia instantaneamente?
        2. FATOR "NÃO PRECISO, MAS QUERO": Gadgets, Casa Inteligente, Itens de Setup, Moda Hype, Cozinha Moderna.
        3. PROVA SOCIAL & QUALIDADE: Priorize notas altas (>4.8) e alto volume de vendas.
        4. PREÇO VS BENEFÍCIO: Parece uma oportunidade imperdível?

        ━━━━━━━━━━━━━━━━━━━━━━━━━━
        🗑️ CRITÉRIOS DE ELIMINAÇÃO (O QUE IGNORAR):
        1. O TÉDIO TÉCNICO: Peças de reposição, parafusos, baterias, resistências, etc.
        2. GENÉRICOS INVISÍVEIS: Cabos simples, adaptadores comuns, películas padrão, etc.
        3. MANUTENÇÃO CHATA: Coisas que a pessoa só compra obrigada (sifão, dobradiça, etc.).
        4. PRODUTOS RUINS: Notas baixas (<4.5) ou nomes confusos.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━
        LISTA DE CANDIDATOS:
        {list_text}

        Sua Missão:
        Retorne APENAS o número (índice) do melhor produto (Ex: 2).
        Se TODOS forem ruins ou genéricos, retorne -1.
        """

        # Chama a função blindada
        result = self._call_ai_with_retry(prompt, max_tokens=10, temperature=0.2)

        if result:
            import re
            match = re.search(r'-?\d+', result)
            if match:
                winner_idx = match.group()
                if winner_idx == "-1":
                    print("🤖 IA: Nenhum produto passou no crivo.")
                    return None
                
                winner = id_map.get(winner_idx)
                if winner:
                    print(f"🤖 IA Escolheu: {winner.get('productName')[:30]}...")
                    return winner

            print(f"⚠️ Resposta IA confusa ({result}). Aleatório.")
            return random.choice(candidates)
        else:
            # Se falhou 3x, fallback para aleatório
            print("⚠️ Falha total na IA. Usando aleatório.")
            return random.choice(candidates)

    def run_forever(self):
        print("🚀 Bot Shopee (V4.0)")
        
        # KEYWORDS ATUALIZADAS
        keywords = [
            # --- ÁUDIO & TECH VIRAIS ---
            "Lenovo GM2 Pro", "Lenovo LP40 Pro", "Lenovo XT80", "Fone Bluetooth Baseus Bowie", 
            "QCY T13 ANC", "QCY H3 Headphone", "Redmi Buds 5", "Redmi Buds 6 Active",
            "JBL Go 3 Original", "JBL Clip 4", "Caixa de Som Tronsmart", "Soundbar Redragon",
            "Smartwatch Haylou Solar", "Amazfit Bip 5", "Mi Band 9", "Smartwatch Colmi",
            "Alexa Echo Dot 5", "Fire TV Stick 4K", "Google Chromecast 4", "Roku Express 4K",
            "Kindle 11", "Tablet Samsung A9+", "Redmi Pad SE",
            "Carregador Baseus 20W", "Power Bank Baseus 20000mah", "Carregador Portátil Pineng",
            "Gimbal Estabilizador", "Microfone Lapela Sem Fio K9", "Fone Condução Óssea",
            "Ring Light Profissional RGB", "Tripé Flexivel Celular", "Suporte Celular Mesa Metal",

            # --- GAMER & SETUP ---
            "Teclado Mecanico Redragon Kumara", "Teclado Machenike K500", "Teclado Magnético", 
            "Mouse Logitech G203", "Mouse Attack Shark X3", "Mouse Attack Shark R1", "Mouse Redragon Cobra",
            "Mousepad Gamer 90x40 Map", "Mousepad RGB Grande", "Headset Havit H2002d", "Headset HyperX Cloud Stinger",
            "Controle 8BitDo Ultimate", "Controle Gamesir", "Controle PS4 Sem Fio", "Controle Xbox Series Original",
            "Microfone Fifine A6V", "Microfone HyperX Solocast", "Braço Articulado Elg",
            "Fita LED Neon 5m", "Barra de Luz Monitor", "Luminária Pixel Art", "Cadeira Gamer Reclinável",
            "Cooler Celular Magnético", "Luva de Dedo Gamer", "Switch HDMI 4k", 
            "Monitor Gamer Samsung Odyssey", "Monitor LG Ultragear", "Monitor Gamer AOC Hero", "Webcam Logitech C920",

            # --- CASA, COZINHA & ORGANIZAÇÃO ---
            "Mini Processador Elétrico Alho", "Copo Stanley Original", "Garrafa Térmica Pacco", "Garrafa Inteligente Temperatura",
            "Mop Giratório Flash Limp", "Mop Spray", "Robô Aspirador Kabum Smart", "Robô Aspirador Liectroux", "Aspirador Vertical Wapo",
            "Umidificador Chama", "Umidificador Anti Gravidade", "Difusor Óleos Essenciais Ultrassônico",
            "Projetor Hy300 4k", "Luminária G-Speaker", "Luminária Lua 3D", "Despertador Digital Espelhado",
            "Mini Liquidificador Portátil", "Seladora de Embalagem Vácuo", "Dispensador Pasta Dente Automático",
            "Organizador de Cabos Velcro", "Organizador Geladeira Acrilico", "Potes Herméticos Electrolux",
            "Forma Airfryer Silicone", "Tapete Super Absorvente Banheiro", "Cabides Veludo Antideslizante",
            "Sapateira Organizadora Vertical", "Escorredor Louça Dobravel Silicone", "Triturador Alho Inox",
            "Faca do Chef Damasco", "Balança de Cozinha Digital",

            # --- FITNESS & SAÚDE ---
            "Creatina Monohidratada Soldiers", "Creatina Max Titanium", "Creatina Dux",
            "Whey Protein Concentrado Dux", "Whey Growth", "Whey Max Titanium",
            "Pré Treino Haze", "Pasta de Amendoim Dr Peanut", "Barra de Proteína Bold",
            "Coqueteleira Inox", "Strap Musculação", "Hand Grip Ajustavel",
            "Corda de Pular Rolamento Speed", "Kit Elásticos Extensores 11pçs", "Mini Band Faixa",
            "Tapete Yoga Antiderrapante TPE", "Roda Abdominal Retorno", "Balança Bioimpedância App",
            "Garrafa Galão 2L Motivacional", "Luva Academia Musculação", "Corretor Postural",

            # --- SKINCARE & MAQUIAGEM ---
            "Serum Principia", "Kit Principia", "Creamy Skincare",
            "Protetor Solar Bioré Aqua", "Protetor Solar Neostrata", "Gel Limpeza CeraVe",
            "Hidratante CeraVe Loção", "Cicaplast Baume B5", "Oleo de Rosa Mosqueta Puro",
            "Ruby Rose Melu", "Gloss Labial Volumoso", "Lip Tint Bt", "Body Splash Wepink",
            "Pó Solto Boca Rosa", "Corretivo Fran", "Paleta Sombras Océane",
            "Esponja Maquiagem Mari Saad", "Kit Pincel Maquiagem Profissional", 
            "Escova Limpeza Facial Elétrica", "Espelho Led Maquiagem Mesa", "Secador de Cabelo Portátil",
            
            # --- PETS ---
            "Fonte Bebedouro Gato", "Fonte Gato Inox", "Comedouro Elevado Porcelana",
            "Arranhador Gato Torre", "Arranhador Papelão", "Cama Nuvem Pet",
            "Tapete Higiênico Lavavel", "Guia Retrátil Cachorro 5m", "Peitoral Antipuxão",
            "Brinquedo Kong Original", "Churu Gato", "Escova Removedora Pelos Pet",
            "Luva Tira Pelos", "Cortador Unha Pet Led", "Túnel para Gatos",

            # --- MODA FEMININA & LIFESTYL ---
            "Vestido Canelado Curto", "Vestido Canelado Midi Fenda", "Vestido Tubinho Feminino",
            "Vestido Longo Estampado Verão", "Vestido Alcinha Costas Abertas", "Vestido Slip Dress Cetim",
            "Vestido Cigana Manga Longa", "Vestido Tricot Decote V", "Conjunto Feminino Alfaiataria",
            "Conjunto Cropped e Saia Midi", "Conjunto Moletom Oversized Feminino", "Conjunto Linho Calça e Blusa",
            "Conjunto Tricot Canelado", "Cropped Canelado Gola Alta", "Cropped Ombro a Ombro Lastex",
            "Cropped Amarração Frente", "Body Canelado Decote Quadrado", "Body Manga Longa Gola Alta",
            "Blusa Ciganinha Lastex", "T-shirt Babylook Básica", "Regata Alcinha Fina Canelada",
            "Blazer Feminino Alfaiataria", "Jaqueta Couro Sintético Feminina", "Cardigã Oversized Tricot",
            "Saia Midi Fenda Lateral", "Calça Wide Leg Alfaiataria", "Short Saia Alfaiataria",
            "Top Argola Bojo",
            
            # FIT & SHAPEWEAR
            "Legging Cintura Alta Levanta Bumbum", "Legging Fitness Sem Costura", "Conjunto Fitness Feminino",
            "Top Fitness Alta Sustentação", "Shorts Fitness Cintura Alta", "Bermuda Ciclista Fitness",
            "Shorts Academia Levanta Bumbum", "Cinta Modeladora Abdominal", "Short Modelador Sem Costura",
            "Calcinha Sem Costura Kit", "Sutiã Sem Aro Conforto", "Sutiã Adesivo Invisível",
            
            # ACESSÓRIOS & BOLSAS
            "Bolsa Feminina Transversal", "Bolsa Feminina Tiracolo", "Bolsa Feminina Pequena Festa",
            "Bolsa Baguette Feminina", "Bolsa Feminina Estilo Zara", "Bolsa Feminina Grande Casual",
            "Mochila Feminina Casual", "Óculos de Sol Feminino", "Óculos de Sol Feminino Quadrado",
            "Kit Colar Feminino Dourado", "Brinco Argola Dourada", "Relógio Feminino Minimalista",
            "Cinto Feminino Moda",
            
            # CALÇADOS 
            "Tênis Feminino Casual Branco", "Tênis Feminino Academia", "Tênis Feminino Estilo Nike",
            "Tênis Feminino Estilo Vans", "Tênis Feminino Plataforma", "Chinelo Nuvem Feminino",
            "Sandália Plataforma Feminina", "Sandália Feminina Salto Bloco", "Papete Feminina Confortável",
            "Bota Feminina Coturno",

            # MASCULINO
            "Camiseta Oversized Streetwear", "Kit Camiseta Básica Masculina", 
            "Shorts Tactel Dry Fit", "Calça Jogger Cargo Masculina", 
            "Boné Aba Curva", "Carteira Slim Couro", "Relógio Masculino Esportivo",
            "Kit Meias Cano Alto", "Aparelho Barbear Elétrico", "Perfume Árabe Masculino",
            "Kit Cuecas Boxer Masculina",


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
                
                if 1 <= hour < 6:
                    print(f"💤 [{hour}h] Dormindo... (30min)")
                    time.sleep(1800)
                    continue
                elif 6 <= hour < 8: min_int, max_int = 60, 90
                elif (11 <= hour < 14) or (18 <= hour < 22): min_int, max_int = 25, 35 
                else: min_int, max_int = 50, 60

                print(f"\n⏰ {hour}h | Intervalo: {min_int}-{max_int}min")

                keyword = random.choice(keywords)
                page = random.randint(1, 2)
                
                all_products = self.get_products(keyword=keyword, sort_type=2, page=page, limit=50)
                
                if all_products:
                    candidates = [p for p in all_products if self._math_filter(p, strict=True)]
                    if not candidates: candidates = [p for p in all_products if self._math_filter(p, strict=False)]

                    if candidates:
                        print(f"🧠 Enviando {len(candidates)} candidatos para a IA...")
                        chosen = self._ai_batch_selector(candidates)
                        
                        if chosen and self.send_to_telegram(chosen):
                            wait = random.randint(min_int, max_int) * 60
                            next_time = datetime.fromtimestamp(datetime.now().timestamp() + wait).strftime('%H:%M')
                            print(f"✅ Próximo em {wait//60} min ({next_time})")
                            time.sleep(wait)
                        else:
                            print("⚠️ Falha envio. 30s...")
                            time.sleep(30)
                    else:
                        print("🧹 Nenhum aprovado matemática.")
                        time.sleep(5)
                else:
                    print("⚠️ Busca vazia.")
                    time.sleep(5)

            except Exception as e:
                print(f"❌ Erro Loop: {e}")
                time.sleep(60)

# Servidor Web
app = Flask('')
@app.route('/')
def home(): return "Bot V4.0 (Retry Logic) Online!"
def run_http(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): t = Thread(target=run_http); t.start()

if __name__ == "__main__":
    keep_alive()
    bot = ShopeeAffiliateBot()
    bot.run_forever()