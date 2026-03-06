import os
import json
import time
import random
import hashlib
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional
from threading import Thread

import requests
from dotenv import load_dotenv
from flask import Flask
from google import genai
from google.genai import types
from keywords import KEYWORDS_POOL

load_dotenv()

# ============================================================
# LOGGING ESTRUTURADO
# ============================================================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ShopeeBot")



class ShopeeAffiliateBot:
    def __init__(self):
        self.app_key = os.getenv("SHOPEE_APP_KEY", "").strip()
        self.app_secret = os.getenv("SHOPEE_APP_SECRET", "").strip()
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        self.shopee_url = "https://open-api.affiliate.shopee.com.br/graphql"
        self.telegram_url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"

        # Persistência de produtos enviados em arquivo JSON
        self.sent_products_file = "sent_products.json"
        self.sent_products: set = self._load_sent_products()

        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.client = None
        self.model_id = "gemini-2.0-flash"

        if self.gemini_key:
            try:
                self.client = genai.Client(api_key=self.gemini_key)
                log.info("🤖 IA Cliente Inicializado")
            except Exception as e:
                log.warning(f"Erro ao criar cliente IA: {e}")

    # ============================================================
    # PERSISTÊNCIA DE PRODUTOS ENVIADOS
    # ============================================================
    def _load_sent_products(self) -> set:
        try:
            with open(self.sent_products_file, "r") as f:
                data = json.load(f)
                log.info(f"📂 {len(data)} produtos carregados do histórico")
                return set(data)
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def _save_sent_products(self):
        # Mantém apenas os últimos 1000 para o arquivo não crescer indefinidamente
        recent = list(self.sent_products)[-1000:]
        with open(self.sent_products_file, "w") as f:
            json.dump(recent, f)

    def _mark_as_sent(self, item_id):
        self.sent_products.add(str(item_id))
        self._save_sent_products()

    # ============================================================
    # HELPERS
    # ============================================================
    def _format_price(self, price: float) -> str:
        return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _calculate_real_discount(self, p_min: float, p_max: float) -> int:
        if p_max > p_min > 0:
            discount = int(((p_max - p_min) / p_max) * 100)
            return discount if discount >= 5 else 0
        return 0

    # ============================================================
    # IA COM RETRY
    # ============================================================
    def _call_ai_with_retry(self, prompt: str, max_tokens: int = 50, temperature: float = 0.2) -> Optional[str]:
        if not self.client:
            return None
        for attempt in range(3):
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
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait = 5 * (attempt + 1)
                    log.warning(f"IA congestionada. Aguardando {wait}s... (tentativa {attempt+1}/3)")
                    time.sleep(wait)
                else:
                    log.warning(f"Erro IA irrecuperável: {e}")
                    return None
        return None

    # ============================================================
    # SHOPEE API
    # ============================================================
    def get_products(self, keyword: str = "", sort_type: int = 2, limit: int = 50, page: int = 1) -> List[Dict]:
        params = [f'limit: {limit}', f'page: {page}', f'sortType: {sort_type}']
        if keyword:
            params.append(f'keyword: "{keyword}"')
        params_str = ', '.join(params)

        query = (
            f"query {{ productOfferV2({params_str}) {{ "
            f"nodes {{ itemId productName imageUrl priceMin priceMax offerLink sales ratingStar }} "
            f"pageInfo {{ hasNextPage }} }} }}"
        )
        payload_str = json.dumps({"query": query}, separators=(',', ':'))
        timestamp = int(time.time())
        signature = hashlib.sha256(
            f"{self.app_key}{timestamp}{payload_str}{self.app_secret}".encode()
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={self.app_key},Timestamp={timestamp},Signature={signature}"
        }

        try:
            log.info(f"🔎 Buscando: '{keyword}' (página {page})")
            response = requests.post(self.shopee_url, headers=headers, data=payload_str, timeout=30)
            response.raise_for_status()
            return response.json().get("data", {}).get("productOfferV2", {}).get("nodes", [])
        except requests.exceptions.RequestException as e:
            log.error(f"Erro Shopee API: {e}")
            return []

    # ============================================================
    # FILTROS
    # ============================================================
    def _math_filter(self, product: Dict, strict: bool = True) -> bool:
        try:
            price = float(product.get("priceMin", 0))
            sales = int(product.get("sales", 0))
            rating = float(product.get("ratingStar", 0))
            title = product.get("productName", "").lower()

            bad_words = [
                "parafuso", "resistência", "cabo usb", "capinha", "película",
                "dobradiça", "ferramenta", "peça de reposição", "adaptador",
                "carregador", "suporte celular", "cabo hdmi"
            ]
            if any(bad in title for bad in bad_words):
                return False
            if price < 15.00:
                return False

            if strict:
                # Faixa ideal de conversão (R$15–R$80)
                if 15.00 <= price <= 80.00:
                    return rating >= 4.5 and sales >= 10
                # Faixa intermediária (R$80–R$200)
                elif price <= 200.00:
                    return rating >= 4.6 and sales >= 5
                # Produtos premium (acima de R$200)
                else:
                    return rating >= 4.7 and sales >= 3
            else:
                # Fallback bem permissivo — a IA filtra depois
                return rating >= 4.0 and price >= 15.00
        except Exception:
            return False

    # ============================================================
    # SELEÇÃO POR IA
    # ============================================================
    def _ai_batch_selector(self, candidates: List[Dict]) -> Optional[Dict]:
        if not candidates:
            return None

        list_text = ""
        id_map = {}
        for idx, p in enumerate(candidates):
            p_min = float(p.get("priceMin", 0))
            rating = float(p.get("ratingStar", 0))
            sales = p.get("sales", 0)
            list_text += f"[{idx}] {p.get('productName')} | R$ {p_min:.2f} | Nota: {rating} | Vendas: {sales}\n"
            id_map[str(idx)] = p

        prompt = f"""
        Você é uma Especialista em Comportamento de Compra Feminino com 10 anos de experiência em marketing de influência no TikTok e Instagram Brasil.
        Sua missão: escolher o produto com MAIOR probabilidade de gerar clique e compra por impulso em uma comunidade VIP de mulheres no WhatsApp.

        CRITÉRIOS DE SELEÇÃO (em ordem de prioridade):

        1. GATILHO DE DESEJO IMEDIATO
           - O produto resolve uma "dor" feminina conhecida? (cabelo, pele, organização, corpo, casa bonita)
           - É algo que a mulher VÊ e pensa "quero isso agora"?
           - Tem apelo visual forte para foto/vídeo?

        2. PROVA SOCIAL E VIRALIDADE
           - Priorize produtos com muitas vendas (sinal de que já está convertendo)
           - Produtos que parecem ter saído de um vídeo viral do TikTok/Reels
           - "Dupes" de produtos caros de marcas famosas (ex: similar a Stanley, CeraVe, La Mer)

        3. CATEGORIAS DE ALTO IMPULSO (priorize nessa ordem)
           a) Skincare com ingrediente ativo famoso (niacinamida, retinol, vitamina C, ácido hialurônico)
           b) Maquiagem com efeito "antes e depois" claro (blush, iluminador, lip tint)
           c) Organização aesthetic (acrílico, rattan, pastel)
           d) Moda com tendência identificável (alfaiataria, slip dress, conjunto)
           e) Gadgets de beleza (secadora, massageador, LED)
           f) Decoração de quarto/home office fofa

        4. ELIMINE IMEDIATAMENTE
           - Produtos técnicos, eletrônicos genéricos, ferramentas, peças
           - Produtos sem apelo visual ou emocional
           - Itens masculinos ou neutros sem contexto feminino claro
           - Produtos muito nichados ou de uso médico

        5. PREÇO ESTRATÉGICO
           - Produtos entre R$20-R$120 convertem melhor (acessível, mas não barato demais)
           - Acima de R$120: só escolha se tiver vendas altíssimas E nota máxima

        CANDIDATOS:
        {list_text}

        Analise cada produto pelos critérios acima. Retorne APENAS o número do produto vencedor (Ex: 2).
        Se nenhum produto tiver potencial real de conversão feminina, retorne -1.
        """

        result = self._call_ai_with_retry(prompt, max_tokens=10, temperature=0.2)
        if result:
            match = re.search(r'-?\d+', result)
            if match:
                winner_idx = match.group()
                if winner_idx == "-1":
                    return None
                return id_map.get(winner_idx)
        return random.choice(candidates)

    # ============================================================
    # POLIDOR DE TÍTULO
    # ============================================================
    def _ai_polisher(self, raw_title: str, price: float) -> str:
        prompt = f"""
        Aja como uma Curadora Humana de um grupo VIP de ofertas femininas no WhatsApp.
        Seu objetivo é limpar o título deste produto da Shopee para que pareça escrito por uma pessoa real — como uma amiga indicando um achadinho.

        Título Original: "{raw_title}"
        Preço: R$ {price}

        DIRETRIZES DE ESTILO:
        1. O QUE É O PRODUTO? Foque em: Categoria + Marca (se relevante) + 1 Detalhe que desperta desejo (cor, material, função).
        2. ZERO MARKETING BARATO: Remova elogios genéricos ("Lindo", "Incrível", "Perfeito", "Envio Já", "Promoção").
        3. APELO FEMININO: Prefira palavras que remetem a tendência, beleza, praticidade ou aesthetic.
        4. QUANTIDADE: Se for kit, comece com "Kit X..." ou "Pack...".

        REGRAS DE FORMATAÇÃO:
        1. Use EXATAMENTE 1 Emoji no início que represente o produto visualmente (ex: 👗 roupa, 💄 maquiagem, 🛋️ casa, 💆 skincare/beleza, 💇 cabelo).
        2. Máximo de 6 a 8 palavras. Sem aspas.

        EXEMPLOS:
        Entrada: "Sérum Vitamina C Clareador Facial Anti-idade Envio Já Promoção"
        Saída: ✨ Sérum Vitamina C Clareador Facial

        Entrada: "Vestido Midi Feminino Fenda Lateral Estampado Floral Verão Lindo"
        Saída: 👗 Vestido Midi Floral com Fenda

        Entrada: "Blush Líquido Melu Ruby Rose Natural Maquiagem Cor de Pele"
        Saída: 🌸 Blush Líquido Melu Ruby Rose

        Entrada: "Escova Secadora Mondial Cabelos Bivolt 1000w Profissional"
        Saída: 💇 Escova Secadora Mondial Bivolt

        Entrada: "Organizador Acrílico Maquiagem Porta Batom Transparente"
        Saída: 🪞 Organizador Acrílico para Maquiagem

        Sua versão:
        """
        new_title = self._call_ai_with_retry(prompt, max_tokens=30, temperature=0.3)
        return new_title.replace('"', '') if new_title else raw_title

    # ============================================================
    # ENVIO AO TELEGRAM (com retry)
    # ============================================================
    def send_to_telegram(self, product: Dict) -> bool:
        raw_title = product.get("productName")
        image_url = product.get("imageUrl")
        link = product.get("offerLink")
        item_id = str(product.get("itemId"))

        if item_id in self.sent_products:
            log.info(f"⏭️ Produto já enviado, pulando: {item_id}")
            return False

        try:
            price_min = float(product.get("priceMin", 0))
            price_max = float(product.get("priceMax", 0))
        except (ValueError, TypeError):
            return False

        final_title = self._ai_polisher(raw_title, price_min)
        discount = self._calculate_real_discount(price_min, price_max)
        price_fmt = self._format_price(price_min)
        sales = product.get("sales", 0)
        rating = float(product.get("ratingStar", 0))

        if sales >= 2000:
            header_options = [
                "🎀 *O QUERIDINHO DAS BLOGUEIRAS!*",
                "✨ *TENDÊNCIA: TODO MUNDO COMPRANDO!*",
                "📦 *ESTOQUE VOANDO RAPIDINHO!*",
                "👑 *O MAIS VENDIDO DA SEMANA!*",
                "🔥 *ESSE AQUI TÁ BOMBANDO!*",
                "😍 *TODO MUNDO FALANDO DESSE!*",
                "📣 *VIRALIZOU E TEM MOTIVO!*",
                "🏆 *CAMPEÃO DE VENDAS!*",
            ]
        elif rating >= 4.9:
            header_options = [
                "⭐ *QUALIDADE PREMIUM APROVADA!*",
                "💎 *ACHADINHO NOTA MÁXIMA!*",
                "✅ *QUEM COMPROU, AMOU MUITO!*",
                "💖 *PERFEIÇÃO TEM NOME!*",
                "🌟 *AVALIAÇÃO PERFEITA, MENINAS!*",
                "👏 *APROVADO POR QUEM COMPROU!*",
                "💅 *NOTA 5 E A GENTE ENTENDE!*",
                "🥇 *MELHOR AVALIADO DA CATEGORIA!*",
            ]
        elif price_min < 25.00:
            header_options = [
                "🤑 *PRECINHO DE AMIGA!*",
                "👛 *BARATINHO QUE A GENTE AMA!*",
                "✨ *AESTHETIC E QUASE DE GRAÇA!*",
                "🧸 *PECHINCHA DO DIA!*",
                "💸 *ESSE PREÇO NÃO VAI DURAR!*",
                "🫶 *ACHADO QUE CABE NO BOLSO!*",
                "🛒 *TÃO BARATO QUE DÁ DOIS!*",
                "🎁 *PRESENTE PERFEITO SEM CULPA!*",
            ]
        else:
            header_options = [
                "🔥 *ACHADINHO DE MILHÕES!*",
                "🛒 *VALE A PENA CONFERIR!*",
                "💡 *DICA DE AMIGA PRA VOCÊS!*",
                "🛍️ *SELEÇÃO ESPECIAL DE HOJE!*",
                "✨ *ESSE EU PRECISAVA MOSTRAR!*",
                "💌 *ACHADINHO QUE A GENTE AMA!*",
                "🌸 *TÁ NA MINHA LISTA DE DESEJOS!*",
                "👀 *OLHA QUE COISA LINDA, GENTE!*",
                "🫶 *DICA QUE SÓ AMIGA DÁ!*",
                "💫 *ENCONTREI E TIVE QUE COMPARTILHAR!*",
            ]

        caption = f"{random.choice(header_options)}\n\n*{final_title}*\n\n"

        if discount > 0:
            caption += f"📉 *-{discount}% OFF!*\n💰 De ~{self._format_price(price_max)}~ por *{price_fmt}*\n"
        else:
            caption += f"💰 Apenas: *{price_fmt}*\n"

        sales_fmt = f"{sales/1000:.1f}k" if sales >= 1000 else str(sales)
        if sales > 0:
            caption += f"🔥 +{sales_fmt} vendidos | ⭐ {rating:.1f}/5.0\n"

        ctas = [
            "👉 *COMPRE PELO LINK:*", "🏃‍♀️ *GARANTA O SEU AQUI:*",
            "🛍️ *LINK DA OFERTA:*", "✨ *VER FOTOS E PREÇO:*",
        ]
        caption += f"\n{random.choice(ctas)}\n{link}"

        payload = {"chat_id": self.telegram_chat_id, "photo": image_url, "caption": caption, "parse_mode": "Markdown"}

        # Retry de envio ao Telegram (até 3 tentativas)
        for attempt in range(3):
            try:
                resp = requests.post(self.telegram_url, json=payload, timeout=30)
                resp.raise_for_status()
                log.info(f"✅ Enviado: {final_title} ({price_fmt})")
                self._mark_as_sent(item_id)
                return True
            except requests.exceptions.RequestException as e:
                wait = 10 * (attempt + 1)
                log.warning(f"Falha no Telegram (tentativa {attempt+1}/3): {e}. Aguardando {wait}s...")
                time.sleep(wait)

        log.error(f"❌ Falha definitiva ao enviar '{final_title}' após 3 tentativas.")
        return False

    # ============================================================
    # LOOP PRINCIPAL
    # ============================================================
    def run_forever(self):
        log.info("🚀 Bot Shopee Online!")
        consecutive_errors = 0

        while True:
            try:
                hour = datetime.now().hour

                # Madrugada: pausa longa
                if 1 <= hour < 7:
                    log.info(f"💤 [{hour}h] Madrugada. Dormindo 30min...")
                    time.sleep(1800)
                    continue

                # Intervalos por horário
                if 7 <= hour < 10:
                    min_int, max_int = 45, 60
                elif (11 <= hour < 14) or (18 <= hour < 22):
                    min_int, max_int = 20, 30
                else:
                    min_int, max_int = 35, 50

                keyword = random.choice(KEYWORDS_POOL)
                page = random.randint(1, 2)

                all_products = self.get_products(keyword=keyword, sort_type=2, page=page, limit=50)

                if not all_products:
                    consecutive_errors += 1
                    # Back-off progressivo: evita spam na API em caso de falha contínua
                    backoff = min(60 * consecutive_errors, 600)
                    log.warning(f"Sem produtos. Aguardando {backoff}s (erro #{consecutive_errors})")
                    time.sleep(backoff)
                    continue

                consecutive_errors = 0  # Reset ao ter sucesso

                # Diagnóstico: mostra distribuição dos produtos recebidos
                if all_products:
                    sample = all_products[:3]
                    for p in sample:
                        log.debug(
                            f"  📦 {p.get('productName','?')[:40]} | "
                            f"R${float(p.get('priceMin',0)):.0f} | "
                            f"⭐{float(p.get('ratingStar',0)):.1f} | "
                            f"🛒{p.get('sales',0)} vendas"
                        )

                candidates = [p for p in all_products if self._math_filter(p, strict=True)]
                if not candidates:
                    candidates = [p for p in all_products if self._math_filter(p, strict=False)]

                if not candidates:
                    log.info(f"Nenhum candidato passou nos filtros ({len(all_products)} produtos recebidos). Próxima busca em 5s.")
                    time.sleep(5)
                    continue

                chosen = self._ai_batch_selector(candidates)
                if chosen and self.send_to_telegram(chosen):
                    wait = random.randint(min_int, max_int) * 60
                    next_time = datetime.fromtimestamp(time.time() + wait).strftime('%H:%M')
                    log.info(f"⏰ Próximo envio em {wait // 60}min ({next_time})")
                    time.sleep(wait)
                else:
                    time.sleep(30)

            except Exception as e:
                log.exception(f"Erro inesperado no loop principal: {e}")
                time.sleep(60)


# ============================================================
# KEEP-ALIVE (Flask)
# ============================================================
app = Flask('')

@app.route('/')
def home():
    return "Bot Feminino Online! ✅"

def run_http():
    try:
        app.run(host='0.0.0.0', port=8080)
    except OSError as e:
        log.warning(f"Porta 8080 indisponível, tentando 8081: {e}")
        app.run(host='0.0.0.0', port=8081)

def keep_alive():
    t = Thread(target=run_http, daemon=True)
    t.start()


if __name__ == "__main__":
    keep_alive()
    bot = ShopeeAffiliateBot()
    bot.run_forever()